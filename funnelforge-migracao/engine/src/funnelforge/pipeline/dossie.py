"""DOSSIÊ FACTUAL PRÉ-REDAÇÃO: pesquisa forte uma vez, fatos congelados.

ESQUELETO APROVADO → PESQUISA ÚNICA DO FUNIL → DOSSIÊ → PORTÃO DE COBERTURA
→ (páginas liberadas) redação.

Composição, não arquitetura nova:
- a pesquisa é o mesmo caminho de grounding (`adapters/research_perplexity`):
  citações do PROVEDOR, redirects resolvidos; URL que o modelo só digitou não
  vira fonte;
- a verificação ao vivo é o mesmo `url_verifier` do run (cache compartilhado);
- cada página recebe seus fatos verificados em `state.facts[n]` — o formato
  que redator, juiz, revisor, `base_factual` e `critical_fact_grounding` já
  leem — e seus canais oficiais por `registrar_canais_oficiais`;
- a jornada diz o que cada página precisa provar (`requisitos`, entregas,
  saída oficial, plano visual, ativos).

O portão de cobertura é determinístico: página sem lastro para a promessa não
chama briefing, redação, SEO, widget, revisão, imagem, print, build nem publish.
Lacuna gera no máximo DUAS rodadas de pesquisa dirigida, e só para o que falta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import re
from typing import Any, Callable
from urllib.parse import urlparse

from funnelforge.domain.dossie import (
    TIPOS_TEMPORAIS,
    CoberturaDaPagina,
    CoberturaDoRequisito,
    DossieDaPagina,
    DossieDoFunil,
    FatoDoDossie,
    FonteDoDossie,
    TelemetriaDaPesquisa,
    id_do_fato,
    sha256_canonico,
    nucleo_da_unidade,
    numeros_do_texto,
    texto_normal,
)
from funnelforge.domain.models import (
    TIPOS_DE_FATO,
    Issue,
    Page,
    RequisitoFactual,
    ResearchFacts,
    RunState,
    StepResult,
    StepStatus,
    canon_rotulo,
    canon_tipo_de_fato,
    effective_role,
)
from funnelforge.pipeline.jornada._comum import estado_do_leitor, links, por_slug
from funnelforge.pipeline.jornada.contexto import ativos_validos, politica_da_saida_oficial

MAX_RODADAS_DE_COMPLEMENTO = 2


@dataclass
class RespostaDaPesquisa:
    """O que uma rodada de pesquisa do funil devolve (porta da pesquisa)."""
    dados: dict
    citacoes: list[str]               # URLs CANÔNICAS que o grounding citou
    modelo_pedido: str = ""
    modelo_servido: str = ""
    auth_mode: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    custo_usd: float = 0.0
    latencia_ms: int = 0
    consultas_de_busca: int = 0       # cobradas por consulta, fora de `custo_usd`
    finish_reason: str = ""
    defeito: str = ""                 # resposta vazia/ilegível: aborta o dossiê
    # False quando o servidor não devolve preço (plano ChatGPT): o custo fica
    # NÃO INFORMADO, nunca US$ 0,00 como cobrança comprovada.
    custo_informado: bool = True
    # Metadados sanitizados de CADA chamada ao provedor nesta rodada
    # (finishReason, bloqueio, segurança, busca, grounding, tokens, texto).
    metadados: list[dict] = field(default_factory=list)


class PesquisaSemResposta(RuntimeError):
    """A pesquisa do dossiê voltou vazia ou ilegível: nada a compilar, nenhuma
    complementação às cegas."""


# pesquisar(assunto, paginas_spec, faltantes) -> RespostaDaPesquisa
Pesquisar = Callable[[str, list[dict], list[dict] | None], RespostaDaPesquisa]


def requisitos_da_pagina(page: Page) -> list[RequisitoFactual]:
    """Requisitos declarados ou contrato factual seguro para cards legados.

    Cards anteriores ao contrato tipado trazem uma promessa complexa e um
    plano visual, mas nenhum ``jornada.requisitos``. Aceitar um único fato
    genérico para a página inteira deixa passar exatamente o caso perigoso:
    uma fonte prova que o programa existe, enquanto passos, números e regras
    do bloco visual continuam sem lastro. O fallback deriva uma necessidade
    para a promessa completa e uma para cada entrega visual. Não inventa fato;
    só torna explícito o que o próprio esqueleto já prometeu pesquisar.
    """
    j = page.jornada
    if j is None:
        return []
    if j.requisitos:
        return list(j.requisitos)
    tipos = [t for t in TIPOS_DE_FATO if t != "contexto"]
    promessa = (j.resposta_imediata or "").strip()
    requisitos = [RequisitoFactual(
        id="resposta_principal",
        descricao=(f"provas suficientes para sustentar integralmente esta resposta: {promessa}"
                   if promessa else
                   f"fato que sustenta a resposta de '{j.pergunta_principal}'"),
        tipos=tipos,
    )]
    for index, bloco in enumerate(j.plano_visual, start=1):
        descricao = " ".join(
            part.strip() for part in (bloco.secao, bloco.funcao) if part and part.strip()
        )
        if not descricao:
            continue
        requisitos.append(RequisitoFactual(
            id=f"entrega_visual_{index}",
            descricao=f"fatos e regras que permitem entregar este bloco sem extrapolar: {descricao}",
            tipos=tipos,
        ))
    return requisitos


def especificacao_das_paginas(pages: list[Page]) -> list[dict]:
    spec = []
    for p in pages:
        j = p.jornada
        spec.append({
            "duvida_id": j.duvida_id, "pergunta": j.pergunta_principal,
            "promessa": j.resposta_imediata,
            "entregas": list(j.valor.entregas) if j.valor else [],
            "requisitos": [{"id": r.id, "descricao": r.descricao, "tipos": r.tipos}
                           for r in requisitos_da_pagina(p)],
        })
    return spec


def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _tipo_da_fonte(url: str, oficiais: set[str], prov: dict | None = None) -> str:
    """Rótulo da fonte para o recibo: pela proveniência comprovada ou pelo canal
    oficial da jornada. Nenhuma lista fixa de domínios."""
    prov = prov or {}
    if prov.get("emissor_verificado") and prov.get("tipo_de_emissor") in EMISSORES_OFICIAIS:
        return "oficial"
    if _canal_oficial(url, list(oficiais)):
        return "canal_oficial"
    return "secundaria"


def _data(valor: Any) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


_SINAIS_DE_METODO_DE_CALCULO = re.compile(
    r"(?:\bcalcul\w*|\bmultiplic\w*|\bsom\w*|\badicion\w*|\bal[ií]quot\w*|"
    r"\bpercent\w*|\bfaixa\w*|\bf[oó]rmula\w*|\bcalculation\w*|\bmultipl\w*|"
    r"\bpercentage\w*|\bformula\w*|\bc[aá]lculo\w*|\bporcentaje\w*|\btasa\w*)",
    re.IGNORECASE,
)


def _tipo_semantico(tipo: str, afirmacao: str, evidencia: str, valor: str,
                    vigente_desde: date | None) -> str:
    """Distingue um valor temporal de um método de cálculo com exemplo.

    Um exemplo numérico não transforma a regra de cálculo em cotação vigente.
    O canário real do FGTS trouxe, na página oficial, ``saldo × alíquota +
    parcela adicional`` e o exemplo de R$ 450. O estruturador marcou tudo como
    ``numero``; exigir uma data para o exemplo descartou a própria fórmula.

    A correção é estreita: só reclassifica ``numero`` sem vigência quando há
    valor *e* linguagem inequívoca de cálculo. Um benefício de R$ X, um limite
    percentual ou qualquer número comum continua temporal e fail-closed.
    """
    if tipo != "numero" or not valor or vigente_desde is not None:
        return tipo
    texto = f"{afirmacao} {evidencia}"
    tem_operacao = bool(re.search(r"(?:[×*+]\s*\d|\d\s*[×*+]|\bmais\b|\bplus\b)",
                                  texto, re.IGNORECASE))
    return "processo" if tem_operacao and _SINAIS_DE_METODO_DE_CALCULO.search(texto) else tipo


def fatos_da_resposta(resp: RespostaDaPesquisa) -> list[FatoDoDossie]:
    """Converte a saída do modelo em fatos com status INICIAL. Só a citação do
    provedor torna uma URL candidata a fonte; o resto nasce `unverified`."""
    citadas = {_norm_url(c) for c in resp.citacoes}
    saida: list[FatoDoDossie] = []
    for bruto in (resp.dados.get("fatos") or []):
        if not isinstance(bruto, dict):
            continue
        afirmacao = str(bruto.get("afirmacao") or bruto.get("fato") or "").strip()
        url = str(bruto.get("fonte") or bruto.get("source_url") or "").strip()
        tipo = canon_tipo_de_fato(bruto.get("tipo")) or ""
        if not afirmacao or not url:
            continue
        valor, unidade = str(bruto.get("valor") or "").strip(), str(bruto.get("unidade") or "").strip()
        vigente_desde = _data(bruto.get("vigente_desde"))
        tipo = _tipo_semantico(
            tipo, afirmacao,
            str(bruto.get("evidencia_resumida") or bruto.get("evidencia") or ""),
            valor, vigente_desde)
        fato = FatoDoDossie(
            fact_id=id_do_fato(url, tipo, afirmacao, valor), afirmacao=afirmacao, tipo=tipo,
            valor=valor, unidade=unidade, source_url=url,
            vigente_desde=vigente_desde,
            paginas=[canon_rotulo(p) for p in (bruto.get("paginas") or []) if isinstance(p, str)],
            requisitos=[canon_rotulo(r) for r in (bruto.get("requisitos") or [])
                        if isinstance(r, str)],
            evidencia=str(bruto.get("evidencia_resumida") or bruto.get("evidencia") or "")[:300],
            dispositivo=str(bruto.get("dispositivo") or "")[:200])
        from funnelforge.pipeline.proveniencia import CAMPOS_DECLARADOS
        declarado = {k: str(bruto.get(k) or (bruto.get("declarado") or {}).get(k) or "")
                     for k in CAMPOS_DECLARADOS}
        if any(declarado.values()):
            # O que a pesquisa DIZ sobre o emissor: só vale depois de conferido
            # no documento (`proveniencia_do_documento`).
            fato.proveniencia = {"declarado": declarado}
        if resp.auth_mode == "hint_do_operador":
            # Só a rodada de hints (código, sem modelo) marca a origem e traz a
            # proveniência lida no documento. Resposta de modelo nunca escolhe
            # a própria origem nem se declara derivada.
            fato.origem = "hint_do_operador"
            if bruto.get("proveniencia"):
                fato.proveniencia = dict(bruto["proveniencia"])
        if bruto.get("motivo_nao_verificado"):
            # O provedor já conferiu e reprovou (ex.: a página citada não
            # confirma o valor): o fato fica com o motivo dele.
            fato.motivo_do_status = str(bruto["motivo_nao_verificado"])[:300]
        elif tipo not in TIPOS_DE_FATO:
            fato.motivo_do_status = f"tipo '{bruto.get('tipo')}' fora do vocabulário"
        elif _norm_url(url) not in citadas:
            fato.motivo_do_status = "fonte não citada pelo grounding do provedor"
        elif tipo in TIPOS_TEMPORAIS and (not valor or not fato.vigente_desde):
            fato.motivo_do_status = "número/data sem valor ou sem referência temporal"
        elif not url.startswith("https://"):
            fato.motivo_do_status = "fonte não é https"
        if bruto.get("indisponivel") and fato.motivo_do_status:
            fato.status = "unavailable"       # leitura falhou: não é refutação
        saida.append(fato)
    return saida


def verificar_ao_vivo(fatos: list[FatoDoDossie], verificador: Any, hoje: date) -> None:
    """Promove a `verified` só o fato sem reprovação prévia cuja fonte RESPONDEU.
    Bloqueio de transporte (WAF, timeout, rede) não é prova NEM refutação: o
    fato fica `unavailable`. Página que não existe (404) fica `unverified`."""
    for f in fatos:
        if f.status != "unverified" or f.motivo_do_status:
            continue
        if verificador is None:
            f.motivo_do_status = "sem verificador de URL no run"
            continue
        try:
            ok = bool(verificador.verify_url(f.source_url))
        except Exception:  # noqa: BLE001 - falha de verificação é resultado, não exceção
            ok = False
        if ok:
            f.status, f.verificado_em = "verified", hoje
        else:
            motivo = getattr(verificador, "motivo", None)
            bloqueada = getattr(verificador, "bloqueada", None)
            f.motivo_do_status = ("fonte não respondeu na verificação ao vivo"
                                  + (f" ({motivo(f.source_url)})" if callable(motivo) else ""))
            if callable(bloqueada) and bloqueada(f.source_url):
                f.status = "unavailable"


def marcar_conflitos(fatos: list[FatoDoDossie]) -> list[str]:
    """Fatos VERIFICADOS que cobrem o mesmo requisito com valores diferentes
    entram em conflito: nenhum deles sustenta a página até alguém decidir."""
    grupos: dict[str, list[FatoDoDossie]] = {}
    for f in fatos:
        if f.status == "verified" and f.valor:
            for r in f.requisitos:
                grupos.setdefault(r, []).append(f)
    conflitos: list[str] = []
    for grupo in grupos.values():
        # Mesma DIMENSÃO (núcleo da unidade) e números diferentes = conflito.
        # "até 2" e "2" salários mínimos concordam; "2 salários" e "R$ 3.242"
        # são grandezas diferentes, não divergência.
        por_dimensao: dict[str, list[FatoDoDossie]] = {}
        for f in grupo:
            por_dimensao.setdefault(nucleo_da_unidade(f.unidade), []).append(f)
        for fatos_da_dimensao in por_dimensao.values():
            valores = {frozenset(numeros_do_texto(f.valor)) or texto_normal(f.valor).strip()
                       for f in fatos_da_dimensao}
            if len(valores) > 1:
                for f in fatos_da_dimensao:
                    f.status = "conflict"
                    f.motivo_do_status = "fontes divergem sobre o mesmo requisito"
                    conflitos.append(f.fact_id)
    return sorted(set(conflitos))


def _fatos_para_a_pagina(fatos: list[FatoDoDossie], page: Page) -> list[FatoDoDossie]:
    duvida = page.jornada.duvida_id
    return [f for f in fatos if duvida in f.paginas]


def _research_facts(fatos: list[FatoDoDossie]) -> ResearchFacts:
    """A PROJEÇÃO no formato que o motor já lê: só fatos verificados."""
    verificados = [f for f in fatos if f.status == "verified"]
    fatos_verificados, dados = [], []
    for f in verificados:
        url = f.source_url or f.derivacao.get("fonte_base", "")
        if f.tipo in TIPOS_TEMPORAIS and f.valor and f.vigente_desde:
            fatos_verificados.append({
                "valor": f.valor, "unidade": f.unidade or "-", "fonte_primaria": url,
                "dispositivo": f.dispositivo or f.afirmacao[:160],
                "vigente_desde": f.vigente_desde, "verificado_em": f.verificado_em, "tipo": f.tipo})
        else:
            dados.append({"fato": f.afirmacao, "fonte": url, "tipo": f.tipo})
    fontes = list(dict.fromkeys(f.source_url or f.derivacao.get("fonte_base", "")
                                for f in verificados))
    fontes = [u for u in fontes if u]
    return ResearchFacts(resumo="", dados_validados=dados, fatos_verificados=fatos_verificados,
                         fontes=fontes, fontes_resolvidas=fontes, sparse=not verificados)


#: Tipos de emissor cuja palavra é OFICIAL quando o emissor está comprovado no
#: documento — vale para qualquer país e nicho.
EMISSORES_OFICIAIS = frozenset({"governo", "regulador", "orgao_publico", "banco_central",
                                "tribunal", "legislativo", "instituicao_oficial"})
#: Emissores reputados (não oficiais): contam como fontes independentes.
EMISSORES_REPUTADOS = frozenset({"academico", "editorial", "fabricante",
                                 "documentacao_tecnica", "associacao_profissional"})
#: Afirmações de risco alto (dinheiro, elegibilidade, datas, prazos, direito,
#: legislação) exigem evidência FORTE: fonte oficial, derivado de premissas
#: verificadas ou duas fontes independentes reputadas que concordam.
TIPOS_DE_RISCO_ALTO = frozenset({"numero", "prazo", "data", "mudanca", "condicao", "fonte_legal"})
_SEGUNDO_NIVEL = frozenset({"com", "gov", "gob", "gouv", "org", "net", "edu", "co", "ac", "go",
                            "or", "ne", "mil", "nic"})


def publicador(url: str) -> str:
    """O domínio registrável aproximado ('gov.br', 'bcb.gov.br' -> 'bcb.gov.br',
    'bbc.co.uk'): quem publica, para dizer se duas fontes são independentes."""
    host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    r = host.split(".")
    if len(r) >= 4 and len(r[-1]) == 2 and r[-2] in _SEGUNDO_NIVEL:
        return ".".join(r[-3:])
    if len(r) >= 3 and len(r[-1]) == 2 and r[-2] in _SEGUNDO_NIVEL:
        return ".".join(r[-3:])
    return ".".join(r[-2:])


def _canal_oficial(url: str, oficiais: list[str]) -> bool:
    """A fonte é do mesmo publicador de um canal oficial que a JORNADA já
    verificou para a página (o destino oficial do próprio funil)."""
    return bool(url) and publicador(url) in {publicador(o) for o in oficiais}


def _prov(f: FatoDoDossie) -> dict:
    return f.proveniencia or {}


def _fato_oficial(f: FatoDoDossie, oficiais: list[str]) -> bool:
    if f.origem == "derivado":
        return bool(f.derivacao.get("oficial"))
    p = _prov(f)
    if p.get("emissor_verificado") and p.get("tipo_de_emissor") in EMISSORES_OFICIAIS:
        return True
    return _canal_oficial(f.source_url, oficiais)


def _fato_reputado(f: FatoDoDossie, oficiais: list[str]) -> bool:
    p = _prov(f)
    return _fato_oficial(f, oficiais) or bool(
        p.get("emissor_verificado") and p.get("tipo_de_emissor") in EMISSORES_REPUTADOS)


def evidencia_forte(fatos: list[FatoDoDossie], oficiais: list[str]) -> bool:
    """Oficial, derivado, ou duas fontes reputadas de publicadores diferentes
    concordando (o conflito já tirou as que divergem)."""
    if any(f.origem == "derivado" or _fato_oficial(f, oficiais) for f in fatos):
        return True
    return len({publicador(f.source_url) for f in fatos
                if f.source_url and _fato_reputado(f, oficiais)}) >= 2


def escopo_do_fato(f: FatoDoDossie) -> tuple[str, str]:
    """(escopo, jurisdição ISO) comprovados: derivado pelas premissas; o resto,
    pelo emissor VERIFICADO no documento. Sem isso: ('desconhecido', '') —
    hostname não decide autoridade."""
    if f.origem == "derivado":
        return f.derivacao.get("escopo", "desconhecido"), f.derivacao.get("jurisdicao", "")
    p = _prov(f)
    if p.get("emissor_verificado") and p.get("escopo") in ("internacional", "nacional",
                                                           "subnacional", "local"):
        return p["escopo"], str(p.get("jurisdicao") or "").upper()
    return "desconhecido", ""


def cobre_jurisdicao(escopo: str, jurisdicao: str, do_conteudo: list[str]) -> bool:
    """A fonte vale para a jurisdição do conteúdo? Fonte de subdivisão só vale
    para a própria subdivisão; fonte do país vale para o país e suas partes."""
    paises = {j.split("-")[0] for j in do_conteudo}
    if escopo in ("internacional", "nacional"):
        return not paises or not jurisdicao or jurisdicao.split("-")[0] in paises
    if escopo in ("subnacional", "local"):
        return bool(jurisdicao) and jurisdicao in do_conteudo
    return False


def _ordem(f: FatoDoDossie) -> tuple:
    """Vigência mais recente primeiro, depois o id (determinístico)."""
    return (-(f.vigente_desde.toordinal() if f.vigente_desde else 0), f.fact_id)


def _melhor_fonte(candidatos: list[FatoDoDossie], niveis: list[tuple[str, Callable]]):
    for nivel, aceita in niveis:
        dele = [f for f in candidatos if aceita(f)]
        if dele:
            return sorted(dele, key=_ordem)[0], nivel
    return None, ""


def _melhor_por_escopo(candidatos: list[FatoDoDossie]) -> FatoDoDossie | None:
    """Premissa de derivado: escopo de país antes de subdivisão; o mais novo."""
    if not candidatos:
        return None
    return sorted(candidatos, key=lambda f: (escopo_do_fato(f)[0] not in
                                             ("internacional", "nacional"),) + _ordem(f))[0]


def vincular_ativo(ativo: Any, page: Page, verificados: list[FatoDoDossie],
                   oficiais: list[str], jurisdicao: list[str], hoje: date
                   ) -> tuple[list[dict], list[str], list[dict]]:
    """Liga cada necessidade declarada do ativo ao melhor fato CITADO,
    VERIFICADO e de fonte oficial/reputada: primeiro a fonte que cobre a
    jurisdição do conteúdo; para valor vigente, depois a publicação oficial do
    ano de uma subjurisdição, com a abrangência explícita. Sem rebind
    arbitrário. Devolve (vínculos, motivos de falha, faltas)."""
    reqs = {r.id: r for r in requisitos_da_pagina(page)}
    cobre = ("fonte que cobre a jurisdição do conteúdo",
             lambda f: cobre_jurisdicao(*escopo_do_fato(f), jurisdicao))
    sub = ("publicação oficial atual de subjurisdição (abrangência explícita)",
           lambda f: escopo_do_fato(f)[0] in ("subnacional", "local")
           and _fato_oficial(f, oficiais))
    vinculos, falhas, faltas = [], [], []
    for papel, req_id in (("regra", ativo.rule_source_fact_id),
                          ("valor_vigente", ativo.current_value_source_fact_id)):
        if not req_id:
            continue
        r = reqs.get(req_id)
        candidatos = [f for f in verificados
                      if req_id in f.requisitos and _fato_reputado(f, oficiais)
                      and (r is None or f.tipo in r.tipos)]
        if papel == "valor_vigente":
            candidatos = [f for f in candidatos if f.valor and f.vigente_desde
                          and f.vigente_desde.year == hoje.year]
            niveis = [cobre, sub]
            exige = (f"valor vigente em {hoje.year}, com data e abrangência explícitas, de "
                     "fonte oficial ou reputada")
        else:
            niveis = [cobre]
            exige = ("fonte de emissor comprovado cujo escopo cubra a jurisdição do "
                     "conteúdo; fonte de subdivisão não prova regra do país")
        fato, nivel = _melhor_fonte(candidatos, niveis)
        if fato is None:
            falhas.append(f"ativo '{ativo.pergunta}': {papel} ('{req_id}') sem {exige}")
            faltas.append({"requisito": req_id, "papel": papel,
                           "descricao": f"{r.descricao if r else req_id} — {exige}",
                           "tipos": list(r.tipos) if r else []})
            continue
        escopo, jur = escopo_do_fato(fato)
        vinculos.append({"ativo": ativo.pergunta, "papel": papel, "requisito": req_id,
                         "fact_id": fato.fact_id, "url": fato.source_url, "nivel": nivel,
                         "origem": fato.origem,
                         "formula": fato.derivacao.get("formula", ""),
                         "premissas": list(fato.derivacao.get("premissas", [])),
                         "emissor": _prov(fato).get("issuer", ""),
                         "abrangencia": escopo, "jurisdicao": jur, "valor": fato.valor,
                         "unidade": fato.unidade,
                         "vigente_desde": fato.vigente_desde.isoformat()
                         if fato.vigente_desde else ""})
    return vinculos, falhas, faltas


_INSTRUCAO = {
    "unavailable": ("a fonte de '{d}' está indisponível agora (não quer dizer que é falso): não "
                    "afirme valor, prazo nem precisão sobre isso; explique só o que está "
                    "comprovado e diga onde o leitor confere na fonte oficial"),
    "unsupported": ("não há evidência suficiente sobre '{d}': omita a afirmação; não diga que o "
                    "leitor tem direito, não cite número nem prazo"),
    "conflicting": ("as fontes divergem sobre '{d}': não afirme nenhuma das versões; diga que "
                    "a informação varia e indique a fonte oficial para conferir"),
}


def cobertura_da_pagina(state: RunState, page: Page, fatos: list[FatoDoDossie],
                        hoje: date | None = None, *,
                        pesquisa_falhou: bool = False) -> CoberturaDaPagina:
    """Estado de cada requisito e o que a página faz com isso. Só conflito
    material na promessa central BLOQUEIA; lacuna degrada (a afirmação sai) e,
    se for da promessa central, manda a página para revisão humana."""
    j = page.jornada
    cob = CoberturaDaPagina()
    oficiais = list(state.official_links.get(page.page_number) or [])
    # Para a FORÇA da evidência vale qualquer canal oficial que a jornada
    # verificou no funil (a LP não tem saída oficial, mas a fonte do órgão que
    # a p4 verificou é oficial para ela também). A exigência de link oficial
    # da página continua sendo da própria página.
    oficiais_do_funil = list(dict.fromkeys(
        u for links in state.official_links.values() for u in (links or [])))
    verificados = [f for f in fatos if f.status == "verified"]
    for r in requisitos_da_pagina(page):
        alto = bool(set(r.tipos) & TIPOS_DE_RISCO_ALTO)
        dele = [f for f in fatos if f.tipo in r.tipos and (
            r.id in f.requisitos or (r.id == "resposta_principal" and f.tipo != "contexto"))]
        candidatos = [f for f in dele if f.status == "verified"]
        if candidatos and (not alto or evidencia_forte(candidatos, oficiais_do_funil)):
            estado = ("derived" if all(f.origem == "derivado" for f in candidatos)
                      else "verified")
            motivo = ""
        elif any(f.status == "conflict" for f in dele):
            estado, motivo = "conflicting", "fontes em conflito"
        elif pesquisa_falhou or any(f.status == "unavailable" for f in dele):
            estado, motivo = "unavailable", "fonte ou transporte indisponível"
        else:
            estado = "unsupported"
            motivo = ("evidência fraca para afirmação de risco alto (falta fonte oficial ou "
                      "segunda fonte independente)" if candidatos else "sem fato verificado")
        coberto = estado in ("verified", "derived")
        cob.requisitos.append(CoberturaDoRequisito(
            requisito_id=r.id, coberto=coberto, fatos=[f.fact_id for f in candidatos]
            if coberto else [], motivo=motivo, estado=estado, central=r.critico,
            risco="alto" if alto else "baixo"))
        if coberto:
            continue
        if estado == "conflicting" and r.critico:
            cob.blockers.append(f"requisito '{r.id}' ({r.descricao}): {motivo} na promessa "
                                "central")
            continue
        cob.degradacoes.append({"requisito": r.id, "estado": estado,
                                "risco": "alto" if alto else "baixo", "central": r.critico,
                                "instrucao": _INSTRUCAO[estado].format(d=r.descricao)})
        if r.critico:
            cob.requer_revisao = True
    politica = politica_da_saida_oficial(page)
    if politica and politica.exige and not oficiais:
        # Canal oficial não verificado (fonte fora, UA recusado, pesquisa sem
        # resultado): a página segue SEM link oficial e ensina onde procurar.
        # Quando a saída oficial é a conclusão útil (`boa`), revisão humana.
        cob.desativados.append({"tipo": "saida_oficial", "nome": "link oficial",
                                "motivo": "nenhum canal oficial verificado para a página"})
        cob.degradacoes.append({
            "requisito": "saida_oficial", "estado": "unavailable", "risco": "alto",
            "central": politica.classe == "boa",
            "instrucao": ("não há canal oficial verificado agora: não ponha link oficial nem "
                          "endereço; diga ao leitor para procurar o canal oficial pelo nome do "
                          "órgão responsável")})
        if politica.classe == "boa":
            cob.requer_revisao = True
    numericos = [f for f in verificados if f.tipo in ("numero", "condicao", "prazo")]
    for bloco in j.plano_visual:
        if bloco.intencao in ("calculo", "exemplos_numericos") and not numericos:
            cob.desativados.append({"tipo": "bloco", "nome": bloco.secao,
                                    "motivo": f"'{bloco.intencao}' sem número verificado"})
        if bloco.intencao == "prova_oficial" and not oficiais:
            cob.desativados.append({"tipo": "bloco", "nome": bloco.secao,
                                    "motivo": "prova oficial sem canal oficial verificado"})
    lastro = {_norm_url(f.source_url) for f in verificados} | {_norm_url(o) for o in oficiais}
    jurisdicao = list(state.plan.jornada.jurisdicao) if state.plan and state.plan.jornada else []
    for ativo in ativos_validos(page):
        if ativo.rule_source_fact_id:
            vinculos, falhas, faltas = vincular_ativo(ativo, page, verificados,
                                                      oficiais_do_funil, jurisdicao,
                                                      hoje or date.today())
            cob.vinculos += vinculos
            cob.vinculos_faltantes += faltas
            if falhas:
                # Só a FERRAMENTA que depende do dado sai; a página segue.
                cob.desativados.append({"tipo": "ativo", "nome": ativo.pergunta,
                                        "motivo": "; ".join(falhas)})
        elif _norm_url(ativo.fonte_da_regra) not in lastro:
            # LEGADO: card sem o contrato semântico.
            cob.desativados.append({"tipo": "ativo", "nome": ativo.pergunta,
                                    "motivo": "fonte da regra fora das fontes verificadas "
                                              "desta página"})
    cob.estado = ("blocked" if cob.blockers else "review" if cob.requer_revisao
                  else "degraded" if (cob.degradacoes or cob.desativados) else "ready")
    cob.ready_to_write = cob.estado != "blocked"
    return cob


def _faltantes(paginas: dict[int, CoberturaDaPagina], pages: list[Page]) -> list[dict]:
    por_numero = {p.page_number: p for p in pages}
    faltam = []
    for n, cob in paginas.items():
        reqs = {r.id: r for r in requisitos_da_pagina(por_numero[n])}
        for c in cob.requisitos:
            if not c.coberto and c.requisito_id in reqs:
                r = reqs[c.requisito_id]
                faltam.append({"duvida_id": por_numero[n].jornada.duvida_id,
                               "requisito": r.id, "descricao": r.descricao, "tipos": r.tipos})
        for v in cob.vinculos_faltantes:
            duvida = por_numero[n].jornada.duvida_id
            faltam = [f for f in faltam
                      if not (f["duvida_id"] == duvida and f["requisito"] == v["requisito"])]
            faltam.append({"duvida_id": duvida, "requisito": v["requisito"],
                           "descricao": v["descricao"], "tipos": v["tipos"]})
    return faltam


class CompiladorDeDossie:
    """A MEMÓRIA FACTUAL do funil — cache compartilhado, não portão global.

    `compilar` faz a pesquisa global (e as complementações, quando pedidas);
    `complementar_pagina` é a pesquisa SOB DEMANDA de um worker de página:
    uma busca por lacuna, deduplicada entre páginas (duas páginas com a mesma
    lacuna esperam a mesma busca), registrada aqui sob trava, e só então a
    página é reavaliada. `montar` devolve o dossiê consolidado (SHA final).

    Pesquisa que falha (provedor fora, defeito, troca de modelo) não derruba o
    funil: não entra fato, e os requisitos sem fato ficam `unavailable`."""

    def __init__(self, state: RunState, deps: Any, pesquisar: Pesquisar, *,
                 registrar_canais: Callable[[RunState, Page, Any], None],
                 hoje: date | None = None,
                 ler_documento: Callable[[str], dict] | None = None) -> None:
        import threading
        self.state, self.deps, self.pesquisar = state, deps, pesquisar
        self.registrar_canais, self.ler_documento = registrar_canais, ler_documento
        self.hoje = hoje or date.today()
        self.pages = [p for p in (state.plan.pages if state.plan else []) if p.jornada is not None]
        self.assunto = (state.plan.jornada.intencao_principal if state.plan and state.plan.jornada
                        else (self.pages[0].h1_title if self.pages else ""))
        self.spec = especificacao_das_paginas(self.pages)
        self.fatos: dict[str, FatoDoDossie] = {}
        self.citacoes: set[str] = set()
        self.telemetria: list[TelemetriaDaPesquisa] = []
        self.coberturas: dict[int, CoberturaDaPagina] = {}
        self.conflitos: list[str] = []
        self.documentos: dict[str, dict] = {}
        self.recusas: list[dict] = []
        self.pesquisa_falhou = False
        self.pesquisados: set[str] = set()        # lacunas já pesquisadas sob demanda
        self.em_voo: dict[str, Any] = {}          # lacuna -> Event da busca em andamento
        self.reaproveitadas = 0                    # lacuna resolvida por fato já existente
        self.deduplicadas = 0                      # lacuna que esperou a busca de outra página
        self.trava = threading.RLock()

    # -- uma rodada ----------------------------------------------------------
    def _pesquisar(self, faltantes: list[dict] | None):
        from funnelforge.pipeline.dossie import RespostaDaPesquisa as _R
        try:
            return self.pesquisar(self.assunto, self.spec, faltantes)
        except Exception as exc:  # noqa: BLE001 - provedor fora não derruba o funil
            return _R(dados={"fatos": []}, citacoes=[], defeito=f"{type(exc).__name__}: "
                      f"{str(exc)[:300]}")

    def absorver(self, resp: "RespostaDaPesquisa", rodada: int, faltantes: list[dict] | None,
                 *, state: RunState | None = None, pages: list[Page] | None = None,
                 pagina: int = 0) -> None:
        from funnelforge.pipeline.proveniencia import derivar_fatos, proveniencia_do_documento
        state = state or self.state
        pages = pages or self.pages
        self.telemetria.append(TelemetriaDaPesquisa(
            rodada=rodada, modelo_pedido=resp.modelo_pedido, modelo_servido=resp.modelo_servido,
            auth_mode=resp.auth_mode, citacoes=len(resp.citacoes),
            prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
            custo_usd=resp.custo_usd, latencia_ms=resp.latencia_ms,
            consultas_de_busca=getattr(resp, "consultas_de_busca", 0),
            finish_reason=getattr(resp, "finish_reason", ""),
            chamadas=list(getattr(resp, "metadados", []) or []), pagina=pagina,
            defeito=getattr(resp, "defeito", ""),
            faltantes_pedidos=[f"{f['duvida_id']}:{f['requisito']}" for f in (faltantes or [])]))
        if getattr(resp, "defeito", ""):
            self.pesquisa_falhou = self.pesquisa_falhou or not self.fatos
        else:
            self.citacoes.update(_norm_url(c) for c in resp.citacoes)
            novos = [f for f in fatos_da_resposta(resp) if f.fact_id not in self.fatos]
            verificar_ao_vivo(novos, getattr(self.deps, "url_verifier", None), self.hoje)
            for f in novos:
                self.fatos[f.fact_id] = f
                if (self.ler_documento is not None and f.status in ("verified", "unavailable")
                        and not _prov(f).get("issuer") and _prov(f).get("declarado")):
                    if f.source_url not in self.documentos:
                        self.documentos[f.source_url] = self.ler_documento(f.source_url)
                    doc = self.documentos[f.source_url]
                    if doc.get("ok"):
                        f.proveniencia = proveniencia_do_documento(
                            f.source_url, doc, _prov(f).get("declarado"))
        self.recalcular(state, pages)

    def recalcular(self, state: RunState, pages: list[Page]) -> None:
        from funnelforge.pipeline.proveniencia import derivar_fatos
        for fid in [k for k, f in self.fatos.items() if f.origem == "derivado"]:
            del self.fatos[fid]                  # derivado é recalculado do zero
        for f in self.fatos.values():            # conflito é recalculado do zero
            if f.status == "conflict":
                f.status, f.motivo_do_status = "verified", ""
        marcar_conflitos(list(self.fatos.values()))
        # Canais oficiais a partir dos fatos LITERAIS; depois o derivado; depois
        # a cobertura com tudo.
        for page in pages:
            state.facts[page.page_number] = _research_facts(
                _fatos_para_a_pagina(list(self.fatos.values()), page))
            state.official_links.pop(page.page_number, None)
            self.registrar_canais(state, page, self.deps)
        oficiais = [u for p in pages for u in (state.official_links.get(p.page_number) or [])]
        # Recuperação 3: fonte oficial inacessível ao NOSSO UA, mas citada e
        # ancorada pelo provedor de Web Search — vale, com o nível registrado.
        for f in self.fatos.values():
            if (f.status == "unavailable" and f.origem == "pesquisa" and f.evidencia
                    and _canal_oficial(f.source_url, oficiais)):
                f.status, f.verificado_em = "verified", self.hoje
                f.nivel_de_evidencia = "citacao_do_provedor"
        derivados, self.recusas = derivar_fatos(list(self.fatos.values()), pages, self.hoje,
                                                lambda f: _fato_oficial(f, oficiais))
        for f in derivados:
            self.fatos[f.fact_id] = f
        for f in self.fatos.values():
            if f.status == "conflict":
                f.status, f.motivo_do_status = "verified", ""
        self.conflitos = marcar_conflitos(list(self.fatos.values()))
        for page in pages:
            state.facts[page.page_number] = _research_facts(
                _fatos_para_a_pagina(list(self.fatos.values()), page))
            cob = cobertura_da_pagina(state, page,
                                      _fatos_para_a_pagina(list(self.fatos.values()), page),
                                      self.hoje, pesquisa_falhou=self.pesquisa_falhou)
            for rec in self.recusas:
                if rec["pagina"] == page.page_number:
                    cob.degradacoes.append({"requisito": rec["requisito"], "estado": "unsupported",
                                            "risco": "alto", "central": False,
                                            "instrucao": f"derivado recusado: {rec['motivo']}"})
            self.coberturas[page.page_number] = cob

    # -- a pesquisa global -----------------------------------------------------
    def compilar(self, *, hints: list[dict] | None = None,
                 complementos: int = MAX_RODADAS_DE_COMPLEMENTO) -> DossieDoFunil:
        from funnelforge.pipeline.proveniencia import verificar_hints
        faltantes: list[dict] | None = None
        if hints:
            self.absorver(verificar_hints(hints, self.ler_documento), 0, None)
        for rodada in range(1, complementos + 2):
            resp = self._pesquisar(faltantes)
            self.absorver(resp, rodada, faltantes)
            if getattr(resp, "defeito", ""):
                break                            # nunca repetir a consulta após erro
            faltantes = _faltantes(self.coberturas, self.pages)
            if not faltantes:
                break
        return self.montar(self.state)

    # -- sob demanda, por página -------------------------------------------------
    @staticmethod
    def _chave(lacuna: dict) -> str:
        """A identidade de uma lacuna para deduplicar. `resposta_principal` é
        o requisito DERIVADO de cada página (a pergunta dela): duas páginas
        nunca compartilham essa lacuna — no card real #65 a p5 esperou a busca
        da p4 e ficou sem pesquisa."""
        if (lacuna["requisito"] == "resposta_principal"
                or lacuna["requisito"].startswith("entrega_visual_")):
            return f"{lacuna['duvida_id']}:{lacuna['requisito']}"
        return lacuna["requisito"]

    def lacunas(self, numero: int) -> list[dict]:
        page = next(p for p in self.pages if p.page_number == numero)
        return _faltantes({numero: self.coberturas[numero]}, [page])

    def complementar_pagina(self, page: Page, state: RunState) -> dict:
        """UMA busca para as lacunas desta página (as que outra página já está
        buscando são esperadas, não repetidas), registrada no dossiê
        compartilhado; depois a página é reavaliada sobre `state` (a cópia do
        worker). Devolve o resumo para o recibo."""
        import threading
        n = page.page_number
        with self.trava:
            self.recalcular(state, [page])
            faltam = self.lacunas(n)
            chaves = [self._chave(f) for f in faltam]
            esperar = [self.em_voo[k] for k in chaves if k in self.em_voo]
            minhas = [f for f in faltam if self._chave(f) not in self.em_voo
                      and self._chave(f) not in self.pesquisados]
            for f in minhas:
                self.em_voo[self._chave(f)] = threading.Event()
            self.deduplicadas += len(esperar)
        for ev in esperar:
            ev.wait(timeout=600)
        resp = None
        if minhas:
            resp = self._pesquisar(minhas)
        with self.trava:
            if resp is not None:
                self.absorver(resp, 100 + n, minhas, state=state, pages=[page], pagina=n)
                for f in minhas:
                    self.pesquisados.add(self._chave(f))
                    self.em_voo.pop(self._chave(f)).set()
            else:
                self.recalcular(state, [page])
            antes = {f["requisito"] for f in faltam}
            depois = {f["requisito"] for f in self.lacunas(n)}
            if not minhas:
                self.reaproveitadas += len(antes - depois)
            return {"lacunas": sorted(antes), "pesquisadas": [f["requisito"] for f in minhas],
                    "esperadas": len(esperar), "resolvidas": sorted(antes - depois),
                    "restantes": sorted(depois), "defeito": getattr(resp, "defeito", "")
                    if resp is not None else "",
                    "estado": self.coberturas[n].estado}

    def complementar_lote(self, pages: list[Page], state: RunState) -> dict:
        """Uma única complementação para todas as lacunas do perfil rápido.

        O perfil completo continua pesquisando por página e pode sobrepor a
        escrita das páginas prontas. No perfil rápido, uma busca consolidada
        evita o padrão medido de 5 páginas × (busca + estruturação) sem abrir
        mão do dossiê global nem inventar evidência.
        """
        alvo = [p for p in pages if p.page_number in self.coberturas]
        with self.trava:
            self.recalcular(state, alvo)
            faltam = _faltantes(
                {p.page_number: self.coberturas[p.page_number] for p in alvo}, alvo)
            unicas: dict[str, dict] = {}
            for lacuna in faltam:
                chave = self._chave(lacuna)
                if chave not in self.pesquisados:
                    unicas.setdefault(chave, lacuna)
            minhas = list(unicas.values())
        resp = self._pesquisar(minhas) if minhas else None
        with self.trava:
            if resp is not None:
                self.absorver(resp, 90, minhas, state=state, pages=alvo, pagina=-1)
                self.pesquisados.update(unicas)
            else:
                self.recalcular(state, alvo)
            restantes = _faltantes(
                {p.page_number: self.coberturas[p.page_number] for p in alvo}, alvo)
            return {
                "lacunas": len(faltam),
                "pesquisadas": len(minhas),
                "resolvidas": len(faltam) - len(restantes),
                "restantes": len(restantes),
                "defeito": getattr(resp, "defeito", "") if resp is not None else "",
            }

    def montar(self, state: RunState) -> DossieDoFunil:
        oficiais = {u for p in self.pages for u in (state.official_links.get(p.page_number) or [])}
        for f in self.fatos.values():
            f.tipo_da_fonte = _tipo_da_fonte(f.source_url, oficiais, f.proveniencia)
        return montar_dossie(state, self.pages, list(self.fatos.values()), self.coberturas,
                             self.conflitos, self.citacoes, self.telemetria, self.assunto)


def compilar_dossie(state: RunState, deps: Any, pesquisar: Pesquisar, *,
                    registrar_canais: Callable[[RunState, Page, Any], None],
                    hoje: date | None = None, hints: list[dict] | None = None,
                    ler_documento: Callable[[str], dict] | None = None,
                    complementos: int | None = None) -> DossieDoFunil:
    """Pesquisa global + até `complementos` complementações dirigidas → dossiê.
    Escreve `state.facts[n]` e `state.official_links[n]` das páginas da jornada."""
    comp = CompiladorDeDossie(state, deps, pesquisar, registrar_canais=registrar_canais,
                              hoje=hoje, ler_documento=ler_documento)
    return comp.compilar(hints=hints, complementos=MAX_RODADAS_DE_COMPLEMENTO
                         if complementos is None else complementos)


def montar_dossie(state: RunState, pages: list[Page], fatos: list[FatoDoDossie],
                  coberturas: dict[int, CoberturaDaPagina], conflitos: list[str],
                  citacoes: set[str], telemetria: list[TelemetriaDaPesquisa],
                  assunto: str) -> DossieDoFunil:
    fatos = sorted(fatos, key=lambda f: f.fact_id)
    slugs = por_slug(state.plan)
    paginas: list[DossieDaPagina] = []
    lacunas: list[dict] = []
    for page in pages:
        j = page.jornada
        dela = _fatos_para_a_pagina(fatos, page)
        cob = coberturas[page.page_number]
        politica = politica_da_saida_oficial(page)
        dp = DossieDaPagina(
            page_number=page.page_number, slug=page.slug, role=effective_role(page).value,
            duvida_id=j.duvida_id, pergunta=j.pergunta_principal, promessa=j.resposta_imediata,
            entregas=list(j.valor.entregas) if j.valor else [],
            ja_resolvido=sorted(estado_do_leitor(state.plan, page).certamente),
            proxima_duvida=j.proxima_duvida,
            requisitos=[r.id for r in requisitos_da_pagina(page)],
            fatos_verificados=sorted(f.fact_id for f in dela if f.status == "verified"),
            fatos_nao_confirmados=sorted(f.fact_id for f in dela if f.status == "unverified"),
            conflitos=sorted(f.fact_id for f in dela if f.status == "conflict"),
            urls_oficiais=list(state.official_links.get(page.page_number) or []),
            cta={"destinos": [{"slug": l.target, "resolve": slugs[l.target].jornada.duvida_id
                               if l.target in slugs and slugs[l.target].jornada else ""}
                              for l in links(page)],
                 "saida_oficial": politica.classe if politica else "nao_aplicavel"},
            layout=[b.intencao for b in j.plano_visual],
            assets=[a.pergunta for a in ativos_validos(page)]
                   + (["print_oficial"] if state.official_links.get(page.page_number) else []),
            cobertura=cob)
        dp.sha256 = sha256_canonico({"pagina": dp.model_dump(mode="json", exclude={"sha256"}),
                                     "fatos": [f.model_dump(mode="json") for f in dela]})
        paginas.append(dp)
        for c in cob.requisitos:
            if not c.coberto:
                lacunas.append({"pagina": page.page_number, "requisito": c.requisito_id,
                                "motivo": c.motivo})
    oficiais = {u for p in paginas for u in p.urls_oficiais}
    fontes = []
    for url in sorted({f.source_url for f in fatos if f.source_url}):
        dos = [f for f in fatos if f.source_url == url]
        fontes.append(FonteDoDossie(
            proveniencia=next((f.proveniencia for f in dos if f.proveniencia), {}),
            url=url, tipo_da_fonte=_tipo_da_fonte(url, oficiais, next(
                (f.proveniencia for f in dos if f.proveniencia), {})),
            citada_pelo_grounding=_norm_url(url) in citacoes,
            verificada=any(f.status in ("verified", "conflict") for f in dos),
            motivo="; ".join(sorted({f.motivo_do_status for f in dos if f.motivo_do_status}))))
    dossie = DossieDoFunil(run_id=state.run_id, assunto=assunto,
                           gerado_em=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           fontes=fontes, fatos=fatos, paginas=paginas, conflitos=conflitos,
                           lacunas=lacunas, pesquisa=telemetria)
    dossie.sha256 = hash_do_dossie(dossie)
    return dossie


def hash_do_dossie(dossie: DossieDoFunil) -> str:
    """O hash do CONTEÚDO canônico: fatos e páginas. Hora, run e telemetria da
    pesquisa ficam fora — o mesmo conteúdo tem o mesmo hash em qualquer run."""
    return sha256_canonico(dossie.model_dump(
        mode="json", include={"schema_version", "assunto", "fatos", "paginas", "conflitos"}))


def paginas_afetadas(antigo: dict, novo: DossieDoFunil) -> list[int]:
    """Páginas cujo pacote mudou entre dois dossiês (hash por página)."""
    antes = {p["page_number"]: p.get("sha256") for p in (antigo or {}).get("paginas", [])}
    return sorted(p.page_number for p in novo.paginas if antes.get(p.page_number) != p.sha256)


_ESTADO_POR_PAGINA = ("drafts", "seo", "images", "image_reviews", "screenshots", "briefings",
                      "revisoes", "recibos", "decisoes_humanas", "normalizacoes",
                      "decoracoes", "metadados")


def invalidar_paginas(state: RunState, paginas: list[int]) -> None:
    """Mudança factual invalida SÓ as páginas afetadas: tira o que foi escrito
    a partir do pacote antigo (e o veredito), mantém o resto do run."""
    for n in paginas:
        for campo in _ESTADO_POR_PAGINA:
            getattr(state, campo).pop(n, None)
        sufixo = f"_p{n}"
        for chave in [k for k in state.step_status if k.endswith(sufixo)
                      and not k.startswith(("research_", "dossie_"))]:
            state.step_status.pop(chave)
        state.step_status.pop(f"page_{n}", None)


def _abrangencia_do_fato(f: dict) -> str:
    escopo, jur = escopo_do_fato(FatoDoDossie.model_validate(f))
    return "" if escopo == "desconhecido" else f"{escopo}{' ' + jur if jur else ''}"


def projecao_para_o_prompt(dossie: dict, numero: int) -> dict:
    """O PageDossier congelado como o redator, o juiz e o revisor o recebem:
    curto — fatos verificados com id, fonte e vigência; nada de dump."""
    pagina = next((p for p in dossie.get("paginas", []) if p.get("page_number") == numero), None)
    if pagina is None:
        return {}
    por_id = {f["fact_id"]: f for f in dossie.get("fatos", [])}
    return {
        "sha256": pagina.get("sha256", ""),
        "fatos": [{"id": i, "afirmacao": por_id[i]["afirmacao"], "tipo": por_id[i]["tipo"],
                   "valor": por_id[i].get("valor", ""), "unidade": por_id[i].get("unidade", ""),
                   "fonte": por_id[i]["source_url"],
                   "abrangencia": _abrangencia_do_fato(por_id[i]),
                   "derivacao": (por_id[i].get("derivacao") or {}).get("formula", ""),
                   "premissas": list((por_id[i].get("derivacao") or {}).get("premissas", [])),
                   "emissor": (por_id[i].get("proveniencia") or {}).get("issuer", ""),
                   "vigente_desde": por_id[i].get("vigente_desde") or ""}
                  for i in pagina.get("fatos_verificados", []) if i in por_id],
        "urls_oficiais": list(pagina.get("urls_oficiais") or []),
        "vinculos": list((pagina.get("cobertura") or {}).get("vinculos") or []),
        "estado": (pagina.get("cobertura") or {}).get("estado", "ready"),
        "degradacoes": list((pagina.get("cobertura") or {}).get("degradacoes") or []),
        "desativados": list((pagina.get("cobertura") or {}).get("desativados") or []),
    }


@dataclass
class ResultadoDoPortao:
    prontas: list[int] = field(default_factory=list)
    bloqueadas: dict[int, list[str]] = field(default_factory=dict)


def aplicar_portao(state: RunState, dossie: DossieDoFunil) -> ResultadoDoPortao:
    """Grava o veredito por PÁGINA: `dossie_pN` OK para ready/degraded/review
    (com as degradações e o pedido de revisão nas issues) e FAILED só para
    `blocked` — conflito material na promessa central. Nada aqui bloqueia o
    funil inteiro."""
    res = ResultadoDoPortao()
    for pg in dossie.paginas:
        n = pg.page_number
        cob = pg.cobertura
        state.step_status[f"research_p{n}"] = StepResult(
            step=f"research_p{n}", status=StepStatus.OK, model_used="dossie",
            issues=[Issue(code="fatos_do_dossie",
                          message=f"{len(pg.fatos_verificados)} fato(s) verificado(s) do dossiê "
                                  f"{dossie.sha256[:12]}")])
        issues = ([Issue(code=f"evidencia_{d['estado']}",
                         message=f"{d['requisito']}: {d['instrucao']}") for d in cob.degradacoes]
                  + [Issue(code="desativado", message=f"{d['tipo']} '{d['nome']}': {d['motivo']}")
                     for d in cob.desativados])
        if cob.requer_revisao:
            issues.insert(0, Issue(code="revisao_humana_por_evidencia",
                                   message="requisito da promessa central sem evidência: a "
                                           "página é escrita, mas não publica sem decisão "
                                           "humana"))
        if cob.ready_to_write:
            state.step_status[f"dossie_p{n}"] = StepResult(
                step=f"dossie_p{n}", status=StepStatus.OK, model_used=cob.estado, issues=issues)
            state.step_status.pop(f"blocked_p{n}", None)
            res.prontas.append(n)
        else:
            issues = [Issue(code="dossie_conflito", message=b) for b in cob.blockers] + issues
            state.step_status[f"dossie_p{n}"] = StepResult(
                step=f"dossie_p{n}", status=StepStatus.FAILED, model_used=cob.estado,
                issues=issues)
            state.step_status[f"blocked_p{n}"] = StepResult(
                step=f"blocked_p{n}", status=StepStatus.FAILED,
                issues=[Issue(code="fail_closed",
                              message="conflito material na promessa central: nenhuma chamada "
                                      "de redação para ESTA página (as outras seguem)")] + issues)
            res.bloqueadas[n] = list(cob.blockers)
    return res
