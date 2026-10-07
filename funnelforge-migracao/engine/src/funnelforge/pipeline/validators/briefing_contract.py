"""CONTRATO DO BRIEFING-V1 — o que o código confere no plano persuasivo.

O briefing (ramo `editorial_v2`) é escrito por LLM a partir do inventário
factual da página. Este módulo NÃO julga se ele persuade bem: confere o que é
objetivamente verificável e devolve duas listas.

ERROS (recusam o briefing; o runner retenta com o motivo; esgotadas as
tentativas, a página fica FAILED sem gastar redação):
- estrutura mínima ausente ou JSON ilegível;
- afirmação persuasiva sem base declarada, ou com base que não vale ali:
  `fato` exige ref a fato do inventário; `hipotese` exige evidência que existe
  (termo observado, pergunta PAA, fato, tensão, anúncio, campo do arquiteto);
  `briefing_do_arquiteto` exige ref a um campo que o arquiteto de fato definiu;
- intenção real da busca declarada como fato (é sempre hipótese);
- benefício sem fato, com fato inexistente ou não citável, sem limite, ou com
  número que não está no fato citado (fato `contexto` nunca sustenta número);
- próximo passo para destino que não está nas rotas nem nos canais oficiais, ou
  cujo "o que encontra" não vem do contrato do destino nem de um fato.

AVISOS (não recusam; ficam no artefato e no relatório para inspeção) — o que é
heurística, pela diretriz 2 do operador (30/09, item 8): rótulo genérico, tom
"calmo" que o arquiteto não pediu, número fora dos fatos fora dos benefícios,
URL fora do inventário, lista de objeções ou de limites vazia, `visual_plan`
ausente ou com padrão atípico para a intenção.

PLANO VISUAL (D2): `visual_plan` presente mas fora da estrutura ou do
vocabulário fechado (`INTENCOES_VISUAIS`/`PADROES_VISUAIS`) é ERRO de contrato.

Sem dependência do resto do pipeline (é registrado em `checks.VALIDATORS`).
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from funnelforge.domain.models import Issue

VERSAO = "briefing-v1"
BASES = ("fato", "hipotese", "briefing_do_arquiteto")
FORMATOS_DE_ENTREGA = ("resposta_direta", "passo_a_passo", "comparacao", "checklist",
                       "guia_de_escolha")
TIPOS_DE_PASSO = ("funnel", "external_official", "cross_funnel")
# Fato que pode sustentar número, prazo ou condição num benefício.
TIPOS_QUE_SUSTENTAM_NUMERO = frozenset({"numero", "prazo", "data", "condicao",
                                        "mudanca", "fonte_legal"})
# Rótulo que não diz nada sobre o ganho do leitor (comparação do rótulo INTEIRO,
# nunca de palavra solta).
ROTULOS_GENERICOS = frozenset({
    "saiba mais", "clique aqui", "leia mais", "ver mais", "veja mais", "continuar",
    "continue lendo", "continuar lendo", "acessar", "acesse", "proximo", "avancar",
    "ler o guia", "ver o guia", "leia o guia", "ler o artigo", "ver artigo", "ler mais",
})
_PREFIXOS_DE_EVIDENCIA = ("termo", "paa", "fato", "arquiteto", "anuncio", "tensao")

# PLANO VISUAL (D2): intenção semântica de cada seção -> padrões Gutenberg do
# catálogo `blocks_gutenberg_v2.jinja` que a servem (o 1º é o preferido). É o
# vocabulário FECHADO do `visual_plan`: o código confere só a estrutura e o
# vocabulário; se o padrão serve bem à seção é julgamento do revisor.
INTENCOES_VISUAIS: dict[str, tuple[str, ...]] = {
    "comparar": ("table", "columns"),
    "passo_a_passo": ("list", "group"),
    "checklist": ("list",),
    "fato_chave": ("group", "pullquote"),
    "navegacao_por_regiao": ("table", "details", "list"),
    "atencao": ("group",),
    "faq": ("details",),
    "exemplos_numericos": ("table", "columns"),
}
PADROES_VISUAIS: tuple[str, ...] = ("table", "columns", "list", "group", "details",
                                    "pullquote")


def canon_padrao(valor: object) -> str:
    """'core/table', 'wp:table' e 'table' são o mesmo padrão; fora do vocabulário
    devolve ''."""
    bruto = str(valor or "").strip().lower()
    for prefixo in ("core/", "wp:"):
        if bruto.startswith(prefixo):
            bruto = bruto[len(prefixo):]
    return bruto if bruto in PADROES_VISUAIS else ""


def exigencia_visual_do_plano(briefing: Any) -> list[str]:
    """Os padrões que o `visual_plan` do briefing pede, sem repetir, na ordem das
    seções. Item fora do vocabulário não vira exigência (o contrato já o recusou)."""
    plano = briefing.get("visual_plan") if isinstance(briefing, dict) else None
    saida: list[str] = []
    for item in plano if isinstance(plano, list) else []:
        padrao = canon_padrao(item.get("padrao")) if isinstance(item, dict) else ""
        if padrao and padrao not in saida:
            saida.append(padrao)
    return saida


def _checar_plano_visual(dados: dict, conf: "_Conferencia") -> None:
    if "visual_plan" not in dados:
        conf.aviso("aviso_sem_plano_visual",
                   "visual_plan ausente: nenhuma seção declarou o formato que a entrega "
                   "pede; a página pode sair só em parágrafos.")
        return
    plano = dados["visual_plan"]
    if not isinstance(plano, list):
        conf.erro("plano_visual_invalido", "visual_plan: deve ser uma lista de seções.")
        return
    for i, item in enumerate(plano):
        onde = f"visual_plan[{i}]"
        if not isinstance(item, dict):
            conf.erro("plano_visual_invalido", f"{onde}: cada item é um objeto.")
            continue
        faltando = [c for c in ("secao", "motivo") if not _texto(item, c)]
        if faltando:
            conf.erro("plano_visual_invalido", f"{onde}: falta {', '.join(faltando)}.")
        intencao = str(item.get("intencao") or "").strip()
        padrao = canon_padrao(item.get("padrao"))
        if intencao not in INTENCOES_VISUAIS:
            conf.erro("plano_visual_invalido",
                      f"{onde}.intencao '{item.get('intencao')}' fora do vocabulário "
                      f"({', '.join(INTENCOES_VISUAIS)}).")
        if not padrao:
            conf.erro("plano_visual_invalido",
                      f"{onde}.padrao '{item.get('padrao')}' fora do vocabulário "
                      f"({', '.join(PADROES_VISUAIS)}).")
        if intencao in INTENCOES_VISUAIS and padrao and padrao not in INTENCOES_VISUAIS[intencao]:
            conf.aviso("aviso_padrao_atipico_para_a_intencao",
                       f"{onde}: '{padrao}' não é o padrão usual para '{intencao}' "
                       f"({', '.join(INTENCOES_VISUAIS[intencao])}) — verificar.")

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|```\s*$")
_NUMERO_RE = re.compile(r"\d+(?:[.,]\d+)*")
_URL_RE = re.compile(r"https?://[^\s<>\"'()\]]+", re.I)


def parse_briefing(texto: str) -> dict:
    """JSON tolerante (cercas de código, texto em volta). Levanta ValueError."""
    limpo = _FENCE_RE.sub("", (texto or "").strip()).strip()
    inicio, fim = limpo.find("{"), limpo.rfind("}")
    if inicio == -1 or fim < inicio:
        raise ValueError("nenhum objeto JSON na resposta")
    dados = json.loads(limpo[inicio:fim + 1])
    if not isinstance(dados, dict):
        raise ValueError("o briefing deve ser um objeto JSON")
    return dados


def _canon(texto: object) -> str:
    bruto = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = "".join(ch for ch in bruto if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def numeros(texto: object) -> set[str]:
    """Os números de um texto, na forma canônica só-dígitos, sem zero à esquerda
    ("66,67%" -> "6667"; "8.621" -> "8621"; "01" -> "1")."""
    saida: set[str] = set()
    for bruto in _NUMERO_RE.findall(str(texto or "")):
        digitos = re.sub(r"\D", "", bruto).lstrip("0") or "0"
        saida.add(digitos)
    return saida


def _lista(valor: Any) -> list[str]:
    if isinstance(valor, str):
        return [valor.strip()] if valor.strip() else []
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if str(v).strip()]
    return []


def _texto(obj: Any, chave: str = "texto") -> str:
    if isinstance(obj, dict):
        valor = obj.get(chave)
        return valor.strip() if isinstance(valor, str) else ""
    return ""


class _Conferencia:
    """Acumula erros e avisos de UMA validação, com a régua (`ref`) da página."""

    def __init__(self, ref: dict) -> None:
        self.ref = ref
        self.erros: list[Issue] = []
        self.avisos: list[Issue] = []
        self.fatos: dict[str, dict] = ref.get("fatos") or {}
        self.termos = {_canon(t) for t in ref.get("termos") or []}
        self.paa = [_canon(p) for p in ref.get("paa") or []]
        self.arquiteto = set(ref.get("arquiteto") or [])
        self.destinos: dict[str, dict] = {str(k).rstrip("/"): v
                                          for k, v in (ref.get("destinos") or {}).items()}

    def erro(self, code: str, message: str) -> None:
        self.erros.append(Issue(code=code, message=message))

    def aviso(self, code: str, message: str) -> None:
        self.avisos.append(Issue(code=code, message=message))

    # --- referências ---------------------------------------------------------

    def ref_de_fato(self, bruto: str, onde: str) -> dict | None:
        fid = bruto.split(":", 1)[1] if bruto.startswith("fato:") else bruto
        fato = self.fatos.get(fid)
        if fato is None:
            self.erro("ref_inexistente",
                      f"{onde}: o fato '{fid}' não existe no inventário desta página."
                      + (" 'destino:' vai com base 'briefing_do_arquiteto'; base 'fato' pede o "
                         "id de um fato do inventário." if fid.startswith("destino:") else ""))
            return None
        if fato.get("citavel") is False:
            self.erro("fato_nao_citavel",
                      f"{onde}: o fato '{fid}' está marcado como não citável (fonte "
                      "contraditória ou instável) e não sustenta nada.")
        return fato

    def evidencia(self, bruto: str, onde: str) -> None:
        prefixo, _, valor = bruto.partition(":")
        prefixo, valor = prefixo.strip().lower(), valor.strip()
        ok = False
        if prefixo == "termo":
            ok = _canon(valor) in self.termos
        elif prefixo == "paa":
            if valor.isdigit():
                ok = 1 <= int(valor) <= len(self.paa)
            else:
                ok = _canon(valor) in self.paa
        elif prefixo == "fato":
            ok = valor in self.fatos
        elif prefixo == "arquiteto":
            ok = valor in self.arquiteto
        elif prefixo == "anuncio":
            ok = valor.isdigit() and 1 <= int(valor) <= int(self.ref.get("anuncio") or 0)
        elif prefixo == "tensao":
            ok = bool(self.ref.get("tensao"))
        if not ok and prefixo == "termo":
            self.erro("evidencia_inexistente",
                      f"{onde}: a evidência '{bruto}' não vale: "
                      + ("nenhum termo de busca observado nesta página, então não há 'termo:' "
                         "a citar; apoie em arquiteto:, fato: ou paa: e diga que não há termo "
                         "observado." if not self.termos else
                         "o termo não está entre os termos observados; copie um termo literal "
                         "da lista ou, se nenhum trata do assunto da página, não use 'termo:'."))
        elif not ok:
            self.erro("evidencia_inexistente",
                      f"{onde}: a evidência '{bruto}' não existe nos dados desta página "
                      f"(formas válidas: {', '.join(p + ':...' for p in _PREFIXOS_DE_EVIDENCIA[:5])}"
                      ", tensao).")

    def ref_do_arquiteto(self, bruto: str, onde: str) -> None:
        prefixo, _, valor = bruto.partition(":")
        prefixo, valor = prefixo.strip().lower(), valor.strip()
        if prefixo == "arquiteto" and valor in self.arquiteto:
            return
        if prefixo == "destino" and valor.rstrip("/") in self.destinos:
            return
        self.erro("ref_do_arquiteto_inexistente",
                  f"{onde}: '{bruto}' não é um campo que o arquiteto definiu para esta "
                  f"página (disponíveis: {', '.join(sorted('arquiteto:' + a for a in self.arquiteto))}).")

    # --- afirmação com base ----------------------------------------------------

    def fundamentado(self, obj: Any, onde: str, permitidas: tuple[str, ...], *,
                     codigo_base: str = "base_invalida", texto: str | None = None) -> str | None:
        """Confere um campo {texto, base, ref|evidencia}. Devolve a base aceita."""
        conteudo = texto if texto is not None else _texto(obj)
        if not isinstance(obj, dict) or not conteudo:
            self.erro("campo_ausente", f"{onde}: falta o texto.")
            return None
        base = obj.get("base")
        if base not in permitidas:
            self.erro(codigo_base,
                      f"{onde}: base '{base}' não vale aqui; use {' ou '.join(permitidas)}.")
            return None
        if base == "fato":
            refs = _lista(obj.get("ref"))
            if not refs:
                self.erro("fato_sem_ref", f"{onde}: base 'fato' sem 'ref' (ids do inventário).")
            for r in refs:
                self.ref_de_fato(r, onde)
        elif base == "hipotese":
            evidencias = _lista(obj.get("evidencia"))
            if not evidencias:
                self.erro("hipotese_sem_evidencia",
                          f"{onde}: hipótese sem 'evidencia' (termo, PAA, fato, tensão, "
                          "anúncio ou campo do arquiteto).")
            for e in evidencias:
                self.evidencia(e, onde)
        elif base == "briefing_do_arquiteto":
            refs = _lista(obj.get("ref"))
            if not refs:
                self.erro("ref_do_arquiteto_inexistente",
                          f"{onde}: base 'briefing_do_arquiteto' sem 'ref'.")
            for r in refs:
                self.ref_do_arquiteto(r, onde)
        return base


def _secao(dados: dict, chave: str, tipo: type, conf: _Conferencia) -> Any:
    valor = dados.get(chave)
    if not isinstance(valor, tipo):
        conf.erro("campo_ausente", f"{chave}: campo obrigatório ausente ou com formato errado.")
        return None
    return valor


def _numeros_do_fato(fato: dict) -> set[str]:
    return set(fato.get("numeros") or [])


def _checar_beneficios(beneficios: list, conf: _Conferencia) -> None:
    for i, ben in enumerate(beneficios):
        onde = f"beneficios[{i}]"
        if not isinstance(ben, dict) or not _texto(ben):
            conf.erro("campo_ausente", f"{onde}: falta o texto do benefício.")
            continue
        ids = _lista(ben.get("fatos"))
        if not ids:
            conf.erro("beneficio_sem_fato",
                      f"{onde}: benefício sem fato citado — benefício só com fato do inventário.")
        citados = [f for f in (conf.ref_de_fato(fid, onde) for fid in ids) if f is not None]
        if not _texto(ben, "limite"):
            conf.erro("beneficio_sem_limite",
                      f"{onde}: falta o 'limite' (para quem vale, onde, até quanto, em que condição).")
        for numero in sorted(numeros(_texto(ben)) | numeros(_texto(ben, "limite"))):
            com_o_numero = [f for f in citados if numero in _numeros_do_fato(f)]
            if not com_o_numero:
                conf.erro("numero_fora_dos_fatos",
                          f"{onde}: o número '{numero}' não está nos fatos citados.")
                continue
            if not any(f.get("tipo") in TIPOS_QUE_SUSTENTAM_NUMERO
                       and f.get("verificada_ao_vivo") for f in com_o_numero):
                conf.erro("numero_sem_fato_compativel",
                          f"{onde}: o número '{numero}' só aparece em fato que não sustenta "
                          "número (tipo contexto, ou sem fonte verificada ao vivo).")


def _checar_passos(passos: list, conf: _Conferencia) -> None:
    if not passos and conf.ref.get("tem_rotas"):
        conf.erro("proximo_passo_ausente",
                  "proximos_passos: a página tem destinos; diga pelo menos um próximo passo.")
    for i, passo in enumerate(passos):
        onde = f"proximos_passos[{i}]"
        if not isinstance(passo, dict):
            conf.erro("campo_ausente", f"{onde}: formato errado.")
            continue
        tipo = passo.get("tipo")
        destino = str(passo.get("destino") or "").strip().rstrip("/")
        if tipo not in TIPOS_DE_PASSO:
            conf.erro("proximo_passo_tipo_invalido",
                      f"{onde}: tipo '{tipo}' inválido; use {', '.join(TIPOS_DE_PASSO)}.")
        alvo = conf.destinos.get(destino)
        if alvo is None or (tipo in TIPOS_DE_PASSO and alvo.get("tipo") != tipo):
            conf.erro("destino_fora_das_rotas",
                      f"{onde}: '{destino}' ({tipo}) não é uma rota desta página nem um "
                      "canal oficial verificado na pesquisa dela.")
        rotulo = _texto(passo, "rotulo")
        if not rotulo:
            conf.erro("rotulo_ausente", f"{onde}: falta o rótulo do botão.")
        elif _canon(rotulo).rstrip(" .!>»") in ROTULOS_GENERICOS:
            conf.aviso("aviso_rotulo_generico",
                       f"{onde}: rótulo '{rotulo}' não diz o que o leitor ganha — verificar.")
        conf.fundamentado(passo.get("intencao_do_leitor"), f"{onde}.intencao_do_leitor",
                          ("hipotese", "briefing_do_arquiteto"))
        encontra = passo.get("o_que_encontra")
        base = conf.fundamentado(encontra, f"{onde}.o_que_encontra",
                                 ("briefing_do_arquiteto", "fato"))
        if base == "briefing_do_arquiteto":
            refs = {r.split(":", 1)[1].strip().rstrip("/") for r in _lista(encontra.get("ref"))
                    if r.startswith("destino:")}
            if destino not in refs:
                conf.erro("o_que_encontra_sem_lastro",
                          f"{onde}.o_que_encontra: precisa vir do contrato DESTE destino "
                          f"(ref 'destino:{destino}') ou de um fato do inventário.")


def _varrer(valor: Any, caminho: str = ""):
    """(caminho, texto) de toda string, fora de 'ref' e 'evidencia'."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            if k in ("ref", "evidencia"):
                continue
            yield from _varrer(v, f"{caminho}.{k}" if caminho else k)
    elif isinstance(valor, list):
        for i, v in enumerate(valor):
            yield from _varrer(v, f"{caminho}[{i}]")
    elif isinstance(valor, str):
        yield caminho, valor


def _avisos_de_numero_e_url(dados: dict, conf: _Conferencia) -> None:
    permitidos = set(conf.ref.get("numeros_permitidos") or [])
    urls = {str(u).rstrip("/") for u in conf.ref.get("urls") or []}
    campos_de_afirmacao = ("promessa_da_pagina", "entrega_concreta", "leitor.objecoes",
                           "proximos_passos", "limites")
    for caminho, texto in _varrer(dados):
        for url in _URL_RE.findall(texto):
            if url.rstrip("/.,;") not in urls:
                conf.aviso("aviso_url_fora_do_inventario",
                           f"{caminho}: a URL {url} não está no inventário — verificar.")
        if caminho.startswith(campos_de_afirmacao) and not caminho.endswith(".destino"):
            fora = sorted(numeros(texto) - permitidos)
            if fora:
                conf.aviso("aviso_numero_fora_dos_fatos",
                           f"{caminho}: número(s) {', '.join(fora)} fora dos fatos e do plano "
                           "— verificar antes de virar texto.")


def validar_briefing(dados: Any, ref: dict) -> tuple[list[Issue], list[Issue]]:
    """(erros, avisos) do briefing contra a régua `ref` da página."""
    conf = _Conferencia(ref)
    if not isinstance(dados, dict):
        conf.erro("briefing_json_invalido", "o briefing deve ser um objeto JSON.")
        return conf.erros, conf.avisos

    intencao = _secao(dados, "intencao", dict, conf)
    if intencao is not None:
        conf.fundamentado(intencao.get("pergunta_do_leitor"), "intencao.pergunta_do_leitor",
                          ("hipotese", "briefing_do_arquiteto"))
        conf.fundamentado(intencao.get("intencao_real_da_busca"),
                          "intencao.intencao_real_da_busca", ("hipotese",),
                          codigo_base="intencao_nao_e_fato")

    leitor = _secao(dados, "leitor", dict, conf)
    if leitor is not None:
        conf.fundamentado(leitor.get("conhecimento_previo"), "leitor.conhecimento_previo",
                          ("hipotese", "briefing_do_arquiteto"))
        conf.fundamentado(leitor.get("desejo_ou_problema"), "leitor.desejo_ou_problema",
                          ("hipotese", "briefing_do_arquiteto"))
        objecoes = leitor.get("objecoes")
        if not isinstance(objecoes, list):
            conf.erro("campo_ausente", "leitor.objecoes: lista obrigatória (pode ser vazia).")
            objecoes = []
        if not objecoes:
            conf.aviso("aviso_sem_objecoes",
                       "leitor.objecoes vazia: nenhuma dúvida que trave a decisão foi prevista.")
        for i, obj in enumerate(objecoes):
            onde = f"leitor.objecoes[{i}]"
            if not isinstance(obj, dict):
                conf.erro("campo_ausente", f"{onde}: formato errado.")
                continue
            conf.fundamentado(obj.get("objecao"), f"{onde}.objecao",
                              ("hipotese", "briefing_do_arquiteto"))
            if not _texto(obj.get("resposta")):
                conf.erro("objecao_sem_resposta", f"{onde}: objeção sem resposta.")
            else:
                conf.fundamentado(obj.get("resposta"), f"{onde}.resposta",
                                  ("fato", "hipotese", "briefing_do_arquiteto"))

    promessa = _secao(dados, "promessa_da_pagina", dict, conf)
    if promessa is not None:
        conf.fundamentado(promessa, "promessa_da_pagina", ("fato", "briefing_do_arquiteto"))
        if not _texto(promessa, "cumprida_em"):
            conf.erro("promessa_sem_lugar",
                      "promessa_da_pagina: diga onde a promessa é cumprida (seção, passo, tabela).")

    entrega = _secao(dados, "entrega_concreta", dict, conf)
    if entrega is not None:
        if entrega.get("formato") not in FORMATOS_DE_ENTREGA:
            conf.erro("entrega_formato_invalido",
                      f"entrega_concreta.formato '{entrega.get('formato')}' inválido; use "
                      f"{', '.join(FORMATOS_DE_ENTREGA)}.")
        itens = entrega.get("itens")
        if not isinstance(itens, list) or not itens:
            conf.erro("entrega_vazia", "entrega_concreta.itens: diga o que o leitor leva.")
            itens = []
        for i, item in enumerate(itens):
            conf.fundamentado(item, f"entrega_concreta.itens[{i}]",
                              ("fato", "briefing_do_arquiteto"))

    beneficios = _secao(dados, "beneficios", list, conf)
    if beneficios is not None:
        _checar_beneficios(beneficios, conf)

    passos = _secao(dados, "proximos_passos", list, conf)
    if passos is not None:
        _checar_passos(passos, conf)

    limites = _secao(dados, "limites", list, conf)
    if limites is not None:
        if not limites:
            conf.aviso("aviso_sem_limites", "limites vazio: nada que a página não possa prometer?")
        for i, lim in enumerate(limites):
            conf.fundamentado(lim, f"limites[{i}]",
                              ("fato", "hipotese", "briefing_do_arquiteto", "identidade"))

    hipoteses = _secao(dados, "hipoteses", list, conf)
    for i, hip in enumerate(hipoteses or []):
        if not _texto(hip):
            conf.erro("campo_ausente", f"hipoteses[{i}]: falta o texto da hipótese.")
        elif not _texto(hip, "como_confirmar"):
            conf.aviso("aviso_hipotese_sem_confirmacao",
                       f"hipoteses[{i}]: diga como a hipótese poderia ser confirmada.")

    tom = _secao(dados, "tom", dict, conf)
    if tom is not None:
        justificativa = _texto(tom, "justificativa")
        if not (_texto(tom, "registro") and _texto(tom, "intensidade") and justificativa):
            conf.erro("tom_sem_justificativa",
                      "tom: registro, intensidade e justificativa são obrigatórios — o tom "
                      "sai da intenção e dos fatos, não de um padrão.")
        else:
            conf.fundamentado(tom, "tom", ("hipotese", "briefing_do_arquiteto", "fato"),
                              texto=justificativa)
            falado = _canon(" ".join((_texto(tom, "registro"), _texto(tom, "intensidade"),
                                      justificativa)))
            if "calm" in falado and "calm" not in _canon(ref.get("tom_do_arquiteto")):
                conf.aviso("aviso_tom_calmo_sem_pedido",
                           "tom 'calmo' sem pedido do arquiteto — verificar se é proporcional "
                           "à intenção do leitor e aos fatos.")

    _checar_plano_visual(dados, conf)
    _avisos_de_numero_e_url(dados, conf)
    return conf.erros, conf.avisos


def briefing_contract(content: str, ctx: dict) -> list[Issue]:
    """Validador do runner: só os ERROS (os avisos o passo guarda à parte).

    Sem `briefing_ref` no ctx não há régua — fora do passo do briefing ele não
    opina (devolve lista vazia)."""
    ref = ctx.get("briefing_ref")
    if ref is None:
        return []
    try:
        dados = parse_briefing(content)
    except (ValueError, json.JSONDecodeError) as exc:
        return [Issue(code="briefing_json_invalido",
                      message=f"Responda SOMENTE com o objeto JSON do briefing ({exc}).")]
    erros, _avisos = validar_briefing(dados, ref)
    return erros
