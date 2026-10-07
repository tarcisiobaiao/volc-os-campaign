"""O CONTRATO DA JORNADA do lado do backend: normalizar, validar e preservar.

Roda logo depois do arquiteto e de novo depois do revisor do arquiteto, ANTES
de qualquer chamada cara do motor. Três funções puras (sem I/O, sem LLM):

- `preservar_jornada` — o revisor devolve páginas inteiras e o exemplo de saída
  dele traz uma jornada resumida. O código faz o merge por página e por campo:
  o que o revisor não mudou EXPLICITAMENTE fica como o arquiteto escreveu, e os
  campos protegidos nunca são apagados por omissão ou valor vazio.
- `normalizar_arquitetura` — variação SEGURA vira valor canônico: caixa,
  acento, espaço, hífen e aliases conhecidos ("Google Ads Search" ->
  `paid_search`, "MiroFish" como fonte de simulação -> `simulacao:mirofish`).
  Campo que controla rota e portão continua estrito: valor desconhecido é ERRO
  com campo e motivo. Campo descritivo com variação cosmética não derruba o
  card (vira aviso). Nunca há fallback silencioso para "sem jornada".
- o relatório (`estado`, `erros`, `avisos`, `normalizacoes`) vai para
  `revisao_arquitetura.jornada`, que o operador e o motor leem.

O vocabulário é o MESMO do motor (`funnelforge.domain.models`); o teste de
ponta a ponta do motor passa esta saída pela ponte real.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any, Dict, List, Tuple

CANAIS = ("paid_search", "organic_search", "discover", "social", "display", "direct")
ENTREGAS = ("resposta_direta", "passo_a_passo", "comparacao", "exemplo", "checklist",
            "calculo", "tabela", "fonte_oficial_explicada", "ferramenta",
            "decisao_pratica", "proximo_passo_concreto")

_ALIASES: Dict[str, Dict[str, str]] = {
    "canal": {
        "google_ads": "paid_search", "google_ads_search": "paid_search",
        "search_pago": "paid_search", "busca_paga": "paid_search", "pesquisa_paga": "paid_search",
        "paid": "paid_search", "sem": "paid_search",
        "organico": "organic_search", "organic": "organic_search", "seo": "organic_search",
        "busca_organica": "organic_search", "google_organico": "organic_search",
        "google_discover": "discover", "discover_native": "discover",
        "whatsapp": "social", "social_whatsapp": "social", "compartilhado": "social",
        "redes_sociais": "social", "facebook": "social", "instagram": "social",
        "native": "display", "nativo": "display", "gdn": "display",
        "direto": "direct",
    },
    "natureza": {"suposicao": "hipotese", "hypothesis": "hipotese",
                 "simulado": "simulacao", "simulation": "simulacao",
                 "observado": "observacao_real", "dado_real": "observacao_real",
                 "real": "observacao_real", "observacao": "observacao_real"},
    "classificacao": {"good": "boa", "adequada": "boa", "premature": "prematura",
                      "cedo": "prematura", "n/a": "nao_aplicavel", "na": "nao_aplicavel",
                      "nao_se_aplica": "nao_aplicavel", "nenhuma": "nao_aplicavel"},
    "entrada_direta": {"autocontido": "autocontida", "sim": "autocontida",
                       "true": "autocontida", "dependente": "depende_de_contexto",
                       "depende": "depende_de_contexto"},
    "profundidade": {"direta": "resposta_direta", "rapida": "resposta_direta",
                     "guiado": "guiada", "profunda": "guiada"},
    "papel": {"sem": "nenhum", "none": "nenhum", "apoio": "secundario",
              "secondary": "secundario", "primary": "principal"},
    "confianca": {"low": "baixa", "medium": "media", "high": "alta"},
    "entrega": {"step_by_step": "passo_a_passo", "comparativo": "comparacao",
                "exemplos": "exemplo", "lista_de_verificacao": "checklist",
                "simulador": "ferramenta", "calculadora": "calculo"},
}
_VALIDOS: Dict[str, Tuple[str, ...]] = {
    "canal": CANAIS,
    "natureza": ("hipotese", "simulacao", "observacao_real"),
    "classificacao": ("boa", "prematura", "nao_aplicavel"),
    "entrada_direta": ("autocontida", "depende_de_contexto"),
    "profundidade": ("resposta_direta", "guiada"),
    "papel": ("nenhum", "secundario", "principal"),
    "confianca": ("baixa", "media", "alta"),
    "entrega": ENTREGAS,
}
_ID_RE = re.compile(r"^[a-z0-9_]+$")
_MARCAS_DE_NAO_OBSERVACAO = ("simulacao", "simulation", "simulad", "mirofish",
                             "hipotese", "hypothesis")

#: Campos que o revisor nunca apaga por omissão ou valor vazio.
CAMPOS_PROTEGIDOS = ("retornos_justificados", "coortes_de_entrada", "evidencias",
                     "monetizacao", "hipotese_de_medicao", "condicao_terminal",
                     "saida_oficial", "valor", "plano_visual", "ativos",
                     "resposta_imediata", "pergunta_principal", "duvida_id")
CAMPOS_PROTEGIDOS_DO_FUNIL = ("coortes", "evidencias", "hipotese_de_medicao",
                              "intencao_principal", "checkpoint", "solucao_principal")


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(ch for ch in normal if not unicodedata.combining(ch))


def canon(valor: Any) -> Any:
    if not isinstance(valor, str):
        return valor
    return re.sub(r"[\s\-]+", "_", _sem_acento(valor).strip().lower())


def fonte_nao_observada(fonte: str) -> bool:
    bruto = re.sub(r"\s+", "", _sem_acento(fonte or "").lower())
    return any(m in bruto for m in _MARCAS_DE_NAO_OBSERVACAO)


def _vazio(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


# ---------------------------------------------------------------------------
# merge protegido (arquiteto -> revisor)
# ---------------------------------------------------------------------------

def _mesclar(original: Dict[str, Any], revisado: Dict[str, Any], protegidos: Tuple[str, ...],
             onde: str, registro: List[Dict[str, str]]) -> Dict[str, Any]:
    saida = copy.deepcopy(original)
    for chave, valor in (revisado or {}).items():
        antigo = original.get(chave)
        if chave in protegidos and _vazio(valor):
            # Vazio num campo protegido nunca apaga o que o arquiteto escreveu
            # (nem cria um campo que ele não declarou).
            if not _vazio(antigo):
                registro.append({"campo": f"{onde}.{chave}", "motivo": "revisor apagou; mantido"})
            continue
        if isinstance(valor, dict) and isinstance(antigo, dict):
            saida[chave] = _mesclar(antigo, valor, tuple(antigo), f"{onde}.{chave}", registro)
        else:
            saida[chave] = copy.deepcopy(valor)
    for chave in original:
        if chave not in (revisado or {}) and chave in protegidos:
            registro.append({"campo": f"{onde}.{chave}", "motivo": "revisor omitiu; mantido"})
    return saida


def preservar_jornada(original: Dict[str, Any], revisado: Dict[str, Any]
                      ) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Arquitetura revisada com a jornada do arquiteto preservada por campo.

    Casa a página revisada com a original pelo `duvida_id` (canônico) e, se o
    revisor o trocou, pelo slug. Página nova do revisor (fusão) fica como veio."""
    registro: List[Dict[str, str]] = []
    paginas_orig = [p for p in (original.get("pages") or []) if isinstance(p, dict)]
    por_duvida = {canon((p.get("jornada") or {}).get("duvida_id")): p
                  for p in paginas_orig if isinstance(p.get("jornada"), dict)}
    por_slug = {str(p.get("slug") or ""): p for p in paginas_orig}
    paginas: List[Dict[str, Any]] = []
    for p in revisado.get("pages") or []:
        if not isinstance(p, dict):
            continue
        p = copy.deepcopy(p)
        jr = p.get("jornada") if isinstance(p.get("jornada"), dict) else None
        orig = (por_duvida.get(canon((jr or {}).get("duvida_id")))
                or por_slug.get(str(p.get("slug") or "")))
        if orig is not None:
            jo = orig.get("jornada")
            onde = f"pagina[{p.get('slug') or p.get('page_number')}].jornada"
            if isinstance(jo, dict):
                if jr is None:
                    registro.append({"campo": onde, "motivo": "revisor omitiu a jornada; mantida"})
                    p["jornada"] = copy.deepcopy(jo)
                else:
                    p["jornada"] = _mesclar(jo, jr, CAMPOS_PROTEGIDOS, onde, registro)
            if _vazio(p.get("editorial")) and not _vazio(orig.get("editorial")):
                registro.append({"campo": f"pagina[{p.get('slug')}].editorial",
                                 "motivo": "revisor omitiu o editorial; mantido"})
                p["editorial"] = copy.deepcopy(orig["editorial"])
        paginas.append(p)
    estrategia_o = original.get("funnel_strategy") or {}
    estrategia_r = copy.deepcopy(revisado.get("funnel_strategy") or {})
    fjo = estrategia_o.get("jornada")
    if isinstance(fjo, dict):
        fjr = estrategia_r.get("jornada")
        estrategia_r["jornada"] = (
            _mesclar(fjo, fjr, CAMPOS_PROTEGIDOS_DO_FUNIL, "funnel_strategy.jornada", registro)
            if isinstance(fjr, dict) else copy.deepcopy(fjo))
        if not isinstance(fjr, dict):
            registro.append({"campo": "funnel_strategy.jornada",
                             "motivo": "revisor omitiu a jornada do funil; mantida"})
    return {**revisado, "funnel_strategy": estrategia_r, "pages": paginas}, registro


# ---------------------------------------------------------------------------
# normalização e validação
# ---------------------------------------------------------------------------

class _Relatorio:
    def __init__(self) -> None:
        self.erros: List[Dict[str, str]] = []
        self.avisos: List[Dict[str, str]] = []
        self.normalizacoes: List[Dict[str, Any]] = []

    def erro(self, campo: str, motivo: str) -> None:
        self.erros.append({"campo": campo, "motivo": motivo})

    def aviso(self, campo: str, motivo: str) -> None:
        self.avisos.append({"campo": campo, "motivo": motivo})


def _enum(obj: Dict[str, Any], chave: str, vocab: str, onde: str, rel: _Relatorio,
          *, estrito: bool = True) -> None:
    if chave not in obj or obj[chave] is None:
        return
    bruto = obj[chave]
    valor = canon(bruto)
    valor = _ALIASES.get(vocab, {}).get(valor, valor)
    if valor in _VALIDOS[vocab]:
        if valor != bruto:
            rel.normalizacoes.append({"campo": f"{onde}.{chave}", "de": bruto, "para": valor})
        obj[chave] = valor
        return
    if estrito:
        rel.erro(f"{onde}.{chave}", f"'{bruto}' fora do vocabulário ({', '.join(_VALIDOS[vocab])})")
    else:
        rel.aviso(f"{onde}.{chave}", f"'{bruto}' fora do vocabulário; campo descartado")
        del obj[chave]


def _id(obj: Dict[str, Any], chave: str, onde: str, rel: _Relatorio) -> None:
    bruto = obj.get(chave)
    if not isinstance(bruto, str) or not bruto.strip():
        return
    valor = canon(bruto)
    if valor != bruto:
        rel.normalizacoes.append({"campo": f"{onde}.{chave}", "de": bruto, "para": valor})
        obj[chave] = valor
    if not _ID_RE.match(valor):
        rel.erro(f"{onde}.{chave}", f"'{bruto}' não é um id snake_case válido")


def _evidencias(lista: Any, onde: str, rel: _Relatorio) -> None:
    if lista is None:
        return
    if not isinstance(lista, list):
        rel.erro(onde, "evidencias deve ser lista")
        return
    for i, ev in enumerate(lista):
        local = f"{onde}[{i}]"
        if not isinstance(ev, dict):
            rel.erro(local, "evidência deve ser objeto")
            continue
        _enum(ev, "natureza", "natureza", local, rel)
        _enum(ev, "confianca", "confianca", local, rel, estrito=False)
        natureza, fonte = ev.get("natureza"), str(ev.get("fonte") or "").strip()
        if natureza == "simulacao":
            if not fonte:
                rel.erro(f"{local}.fonte", "simulação sem fonte")
            elif not canon(fonte).startswith("simulacao:"):
                novo = "simulacao:" + canon(fonte).replace("simulacao_", "", 1)
                rel.normalizacoes.append({"campo": f"{local}.fonte", "de": fonte, "para": novo})
                ev["fonte"] = novo
        if natureza == "observacao_real":
            if fonte_nao_observada(fonte):
                rel.erro(f"{local}.fonte", f"'{fonte}' é simulação/hipótese, não observação real")
            if not fonte or not ev.get("coletado_em") or not str(ev.get("referencia") or "").strip():
                rel.erro(local, "observação real exige fonte, coletado_em e referencia")


def _normalizar_pagina(j: Dict[str, Any], onde: str, rel: _Relatorio) -> None:
    _id(j, "duvida_id", onde, rel)
    if not str(j.get("pergunta_principal") or "").strip():
        rel.erro(f"{onde}.pergunta_principal", "obrigatória")
    if not j.get("duvida_id"):
        rel.erro(f"{onde}.duvida_id", "obrigatório")
    _id(j, "proxima_duvida", onde, rel)
    for chave in ("ja_resolvido",):
        if isinstance(j.get(chave), list):
            j[chave] = [canon(v) for v in j[chave]]
    if isinstance(j.get("retornos_justificados"), dict):
        j["retornos_justificados"] = {canon(k): v for k, v in j["retornos_justificados"].items()}
    canais = j.get("coortes_de_entrada")
    if isinstance(canais, list):
        normal = []
        for k, c in enumerate(canais):
            item = {"canal": c}
            _enum(item, "canal", "canal", f"{onde}.coortes_de_entrada[{k}]", rel)
            normal.append(item["canal"])
        j["coortes_de_entrada"] = normal
    _enum(j, "entrada_direta", "entrada_direta", onde, rel)
    saida = j.get("saida_oficial")
    if isinstance(saida, dict):
        _enum(saida, "classificacao", "classificacao", f"{onde}.saida_oficial", rel)
        if isinstance(saida.get("esperada"), str):
            saida["esperada"] = canon(saida["esperada"]) in ("sim", "true", "1", "verdadeiro")
    if isinstance(j.get("monetizacao"), dict):
        _enum(j["monetizacao"], "papel", "papel", f"{onde}.monetizacao", rel)
    valor = j.get("valor")
    if isinstance(valor, dict) and isinstance(valor.get("entregas"), list):
        ok = []
        for e in valor["entregas"]:
            item = {"entrega": e}
            _enum(item, "entrega", "entrega", f"{onde}.valor.entregas", rel, estrito=False)
            if "entrega" in item:
                ok.append(item["entrega"])
        valor["entregas"] = ok
    _evidencias(j.get("evidencias"), f"{onde}.evidencias", rel)


def normalizar_arquitetura(arq: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Saída do arquiteto (ou do revisor) com a jornada canônica, e o
    relatório. Sem jornada em lugar nenhum -> estado `ausente` (card antigo)."""
    arq = copy.deepcopy(arq or {})
    rel = _Relatorio()
    paginas = [p for p in (arq.get("pages") or []) if isinstance(p, dict)]
    estrategia = arq.get("funnel_strategy") if isinstance(arq.get("funnel_strategy"), dict) else {}
    com_jornada = [p for p in paginas if p.get("jornada") is not None]
    if not com_jornada and estrategia.get("jornada") is None:
        return arq, {"estado": "ausente", "erros": [], "avisos": [], "normalizacoes": []}
    ids: set = set()
    for p in paginas:
        onde = f"pagina[{p.get('slug') or p.get('page_number')}].jornada"
        j = p.get("jornada")
        if j is None:
            rel.erro(onde, "página sem jornada num funil com jornada")
            continue
        if not isinstance(j, dict):
            rel.erro(onde, "jornada deve ser objeto")
            continue
        _normalizar_pagina(j, onde, rel)
        if j.get("duvida_id"):
            ids.add(j["duvida_id"])
    for p in paginas:
        j = p.get("jornada")
        if not isinstance(j, dict):
            continue
        onde = f"pagina[{p.get('slug') or p.get('page_number')}].jornada"
        for d in [*(j.get("ja_resolvido") or []), j.get("proxima_duvida") or "",
                  *(j.get("retornos_justificados") or {})]:
            if d and d not in ids:
                rel.erro(onde, f"referência à dúvida '{d}', que nenhuma página responde")
    fj = estrategia.get("jornada")
    if fj is not None:
        if not isinstance(fj, dict):
            rel.erro("funnel_strategy.jornada", "deve ser objeto")
        else:
            if not str(fj.get("intencao_principal") or "").strip():
                rel.erro("funnel_strategy.jornada.intencao_principal", "obrigatória")
            for chave in ("checkpoint", "solucao_principal"):
                _id(fj, chave, "funnel_strategy.jornada", rel)
                if fj.get(chave) and fj[chave] not in ids:
                    rel.erro(f"funnel_strategy.jornada.{chave}", f"'{fj[chave]}' não é dúvida do funil")
            for k, c in enumerate(fj.get("coortes") or []):
                local = f"funnel_strategy.jornada.coortes[{k}]"
                if not isinstance(c, dict):
                    rel.erro(local, "coorte deve ser objeto")
                    continue
                _enum(c, "canal", "canal", local, rel)
                _enum(c, "profundidade", "profundidade", local, rel)
                for chave in ("entrada", "proximo_passo"):
                    _id(c, chave, local, rel)
                    if c.get(chave) and c[chave] not in ids:
                        rel.erro(f"{local}.{chave}", f"'{c[chave]}' não é dúvida do funil")
                if not c.get("entrada") or not str(c.get("promessa") or "").strip():
                    rel.erro(local, "coorte exige entrada e promessa")
            _evidencias(fj.get("evidencias"), "funnel_strategy.jornada.evidencias", rel)
    return arq, {"estado": "invalida" if rel.erros else "valida", "erros": rel.erros,
                 "avisos": rel.avisos, "normalizacoes": rel.normalizacoes}
