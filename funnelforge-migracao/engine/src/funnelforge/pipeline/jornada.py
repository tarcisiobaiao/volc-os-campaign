"""A JORNADA DO FUNIL: régua determinística do mapa e do funil pronto.

O VOLC não deve gerar páginas que parecem boas isoladas; deve gerar um caminho
`intenção → entrada → resposta imediata → qualificação → próxima dúvida →
saída oficial`. Este módulo confere o que é OBJETIVO nesse caminho, usando o
contrato `Page.jornada` / `FunnelPlan.jornada` (ver `domain/models.py`):

- `revisar_esqueleto` — ANTES de qualquer chamada paga. Os bloqueantes entram
  no `funnel_graph` (via `routing.validate_funnel_graph`), que é o portão que já
  aborta o run antes da pesquisa. Os avisos vão para o relatório.
- `classificar_saida_oficial` — boa ou prematura, por regra declarada.
- `contexto_de_jornada` — o que o redator (e o juiz/revisor) recebem.
- `revisar_funil_pronto` — UMA verificação consolidada depois da redação, com
  achados localizados e propostas para decisão humana. Não reescreve nada.
- `contrato_de_medicao` — o artefato tipado de medição (sem tracking novo).

O que exige julgamento de sentido (a resposta está boa? o tom serve à coorte?)
continua com o juiz/revisor por página. Aqui só entra regra que um teste
consegue provar. Nenhum número da apresentação Pubx ou da simulação MiroFish
vira limiar: não há taxa de progressão "esperada" em lugar nenhum deste código.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from funnelforge.domain.medicao import (
    ContratoDeMedicao,
    MudancaSugerida,
    PropostaDeNovaVersao,
    SinalPrevisto,
)
from funnelforge.domain.models import (
    CANAIS_FRIOS,
    FunnelPlan,
    Issue,
    Page,
    PageRole,
    effective_role,
)

# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------

_STOP = frozenset({
    "como", "seu", "sua", "seus", "suas", "para", "pelo", "pela", "fazer", "quem",
    "pode", "sobre", "qual", "quais", "onde", "minha", "meu", "meus", "minhas",
    "esta", "este", "isso", "isto", "mais", "voce", "voces", "cada", "entre",
    "depois", "antes", "aqui", "ver", "veja", "achar", "escolher", "clique",
    "ainda", "tambem", "quando", "porque", "pois", "ate", "sem", "com", "nos",
    "das", "dos", "que", "uma", "uns", "umas", "num", "numa",
})


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(ch for ch in normal if not unicodedata.combining(ch)).lower()


def _tokens(texto: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", _sem_acento(texto)) if t not in _STOP}


def _norm(texto: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", _sem_acento(texto)))


def tem_jornada(plan: FunnelPlan | None) -> bool:
    return bool(plan and (plan.jornada is not None
                          or any(p.jornada is not None for p in plan.pages)))


def _por_slug(plan: FunnelPlan) -> dict[str, Page]:
    return {p.slug: p for p in plan.pages}


def _por_duvida(plan: FunnelPlan) -> dict[str, Page]:
    return {p.jornada.duvida_id: p for p in plan.pages if p.jornada is not None}


def _links(page: Page) -> list:
    return list(page.editorial.links) if page.editorial is not None else []


def _rotulo(page: Page) -> str:
    return page.jornada.duvida_id if page.jornada else page.slug


def _justificado(origem: Page, destino: Page) -> str:
    if origem.jornada is None or destino.jornada is None:
        return ""
    return (origem.jornada.retornos_justificados.get(destino.jornada.duvida_id) or "").strip()


# ---------------------------------------------------------------------------
# saída oficial
# ---------------------------------------------------------------------------

def classificar_saida_oficial(page: Page) -> str:
    """`boa` | `prematura` | `nao_aplicavel`, por regra declarada:

    - sem saída esperada -> não se aplica;
    - justificativa explícita do arquiteto -> boa (e fica registrada);
    - na LP -> prematura: o leitor ainda não se qualificou;
    - com condição terminal declarada (a tarefa da página está resolvida) -> boa;
    - qualquer outro caso -> prematura: sair para a fonte oficial antes de a
      tarefa estar resolvida é o que faz o leitor chegar lá sem saber usá-la.
    """
    j = page.jornada
    if j is None or not j.saida_oficial.esperada:
        return "nao_aplicavel"
    if j.saida_oficial.justificativa.strip():
        return "boa"
    if effective_role(page) is PageRole.LP:
        return "prematura"
    if j.condicao_terminal.strip():
        return "boa"
    return "prematura"


def _conclusiva(page: Page) -> bool:
    j = page.jornada
    return bool(j and (j.condicao_terminal.strip() or classificar_saida_oficial(page) == "boa"))


# ---------------------------------------------------------------------------
# ciclos (o funil tem ~5 páginas: enumeração simples é suficiente e legível)
# ---------------------------------------------------------------------------

def _ciclos(adj: dict[str, list[str]]) -> list[list[str]]:
    """Ciclos elementares, cada um uma vez (começando no menor nó)."""
    nos = sorted(adj)
    achados: list[list[str]] = []
    for inicio in nos:
        pilha: list[tuple[str, list[str]]] = [(inicio, [inicio])]
        while pilha:
            no, caminho = pilha.pop()
            for prox in adj.get(no, []):
                if prox == inicio and len(caminho) > 1:
                    achados.append(list(caminho))
                elif prox not in caminho and prox > inicio:
                    pilha.append((prox, [*caminho, prox]))
    return achados


def _descreve_ciclo(ciclo: list[str], por_slug: dict[str, Page]) -> str:
    nomes = [_rotulo(por_slug[s]) for s in ciclo]
    return " → ".join([*nomes, nomes[0]])


def _ciclo_justificado(ciclo: list[str], por_slug: dict[str, Page]) -> str:
    for a, b in zip(ciclo, [*ciclo[1:], ciclo[0]]):
        motivo = _justificado(por_slug[a], por_slug[b])
        if motivo:
            return motivo
    return ""


# ---------------------------------------------------------------------------
# revisor global do ESQUELETO (antes da redação cara)
# ---------------------------------------------------------------------------

@dataclass
class RevisaoDoEsqueleto:
    bloqueantes: list[Issue] = field(default_factory=list)
    avisos: list[Issue] = field(default_factory=list)


def _lp_so_roteia(page: Page, por_slug: dict[str, Page]) -> bool:
    """A resposta da LP diz algo além do menu de destinos?

    Regra objetiva e deliberadamente estreita: tira da resposta os termos que
    já estão nos rótulos/H1/motivos dos destinos. Se não sobra nada, a LP só
    repete o menu. Se a resposta é BOA é julgamento — fica com o juiz."""
    resposta = _tokens(page.jornada.resposta_imediata) if page.jornada else set()
    if not resposta:
        return True
    do_menu: set[str] = set()
    for link in _links(page):
        alvo = por_slug.get(link.target)
        if alvo is None:
            continue
        do_menu |= _tokens(link.reason) | _tokens(alvo.h1_title)
        if alvo.editorial is not None:
            do_menu |= _tokens(alvo.editorial.cta_label)
    return not (resposta - do_menu)


def revisar_esqueleto(plan: FunnelPlan | None) -> RevisaoDoEsqueleto:
    """Valida o MAPA inteiro da jornada. Sem jornada no plano: nada a dizer
    (card anterior ao contrato segue exatamente como antes)."""
    rev = RevisaoDoEsqueleto()
    if not tem_jornada(plan):
        return rev
    assert plan is not None
    b, a = rev.bloqueantes.append, rev.avisos.append
    sem = [p.slug for p in plan.pages if p.jornada is None]
    if sem:
        b(Issue(code="jornada_incompleta",
                message=f"Páginas sem jornada num funil com jornada: {sem}. "
                        "O arquiteto precisa declarar a jornada de todas."))
        return rev
    for p in plan.pages:
        if p.editorial is None:
            b(Issue(code="jornada_sem_editorial",
                    message=f"[{p.jornada.duvida_id}] jornada sem contrato editorial: "
                            "os destinos da página vêm de `editorial.links`."))
    if rev.bloqueantes:
        return rev

    por_slug, ids = _por_slug(plan), {}
    for p in plan.pages:
        ids.setdefault(p.jornada.duvida_id, []).append(p.slug)
    for duvida, slugs in ids.items():
        if len(slugs) > 1:
            b(Issue(code="duvida_duplicada",
                    message=f"[{duvida}] a mesma dúvida em {slugs}: uma pergunta principal "
                            "por página; funda as páginas ou separe as dúvidas."))
    perguntas: dict[str, str] = {}
    for p in plan.pages:
        chave = _norm(p.jornada.pergunta_principal)
        if chave in perguntas and perguntas[chave] != p.jornada.duvida_id:
            b(Issue(code="duvida_duplicada",
                    message=f"[{p.jornada.duvida_id}] repete a pergunta de "
                            f"[{perguntas[chave]}]: '{p.jornada.pergunta_principal}'."))
        perguntas.setdefault(chave, p.jornada.duvida_id)

    def _ref(origem: str, campo: str, valor: str) -> None:
        if valor and valor not in ids:
            b(Issue(code="referencia_de_duvida_inexistente",
                    message=f"[{origem}] {campo} aponta para a dúvida '{valor}', "
                            "que nenhuma página do funil responde."))

    for p in plan.pages:
        j = p.jornada
        for r in j.ja_resolvido:
            _ref(j.duvida_id, "ja_resolvido", r)
        if j.duvida_id in j.ja_resolvido:
            b(Issue(code="referencia_de_duvida_inexistente",
                    message=f"[{j.duvida_id}] declara a própria dúvida como já resolvida."))
        _ref(j.duvida_id, "proxima_duvida", j.proxima_duvida)
        for alvo in j.retornos_justificados:
            _ref(j.duvida_id, "retornos_justificados", alvo)
    if plan.jornada is not None:
        _ref("funil", "checkpoint", plan.jornada.checkpoint)
        _ref("funil", "solucao_principal", plan.jornada.solucao_principal)
        for c in plan.jornada.coortes:
            _ref(f"coorte:{c.canal}", "entrada", c.entrada)
            _ref(f"coorte:{c.canal}", "proximo_passo", c.proximo_passo)
    if rev.bloqueantes:
        return rev

    por_duvida = _por_duvida(plan)

    # --- cada página: resposta própria, autocontida, próxima dúvida coerente
    for p in plan.pages:
        j, papel = p.jornada, effective_role(p)
        destinos = [por_slug[l.target] for l in _links(p) if l.target in por_slug]
        ids_destino = {d.jornada.duvida_id for d in destinos}
        if papel is PageRole.LP:
            if _lp_so_roteia(p, por_slug):
                b(Issue(code="lp_so_roteia",
                        message=f"[{j.duvida_id}] a LP só roteia: a resposta imediata está "
                                "vazia ou repete o menu de destinos. Ela precisa responder "
                                "algo por si antes de pedir o clique."))
        elif not j.resposta_imediata.strip():
            b(Issue(code="resposta_imediata_ausente",
                    message=f"[{j.duvida_id}] sem resposta imediata: a primeira dobra não "
                            "tem promessa a cumprir."))
        if papel is not PageRole.LP and j.entrada_direta == "depende_de_contexto":
            b(Issue(code="entrada_direta_dependente",
                    message=f"[{j.duvida_id}] depende da página anterior para fazer "
                            "sentido; quem entra direto pela busca ou por um link "
                            "compartilhado precisa resolver a tarefa aqui."))
        if j.proxima_duvida and j.proxima_duvida not in ids_destino:
            b(Issue(code="proxima_duvida_sem_destino",
                    message=f"[{j.duvida_id}] a próxima dúvida é '{j.proxima_duvida}', mas "
                            "nenhum destino da página a resolve; o CTA principal tem de "
                            "levar à próxima dúvida."))
        for d in destinos:
            alvo = d.jornada.duvida_id
            if alvo in j.ja_resolvido:
                motivo = _justificado(p, d)
                if motivo:
                    a(Issue(code="retorno_justificado",
                            message=f"[{j.duvida_id}] volta a '{alvo}' (já resolvida) com "
                                    f"justificativa: {motivo}. Apresente como secundário."))
                else:
                    b(Issue(code="cta_repetido_apos_resolvido",
                            message=f"[{j.duvida_id}] oferece de novo '{alvo}', que o "
                                    "leitor já resolveu ao chegar aqui: é convite para "
                                    "circular, não orientação."))
        if not destinos and not _conclusiva(p):
            b(Issue(code="beco_sem_saida",
                    message=f"[{j.duvida_id}] sem destino e sem conclusão declarada "
                            "(condição terminal ou saída oficial boa)."))
        if not j.proxima_duvida and not j.condicao_terminal.strip() and destinos:
            a(Issue(code="proxima_duvida_nao_declarada",
                    message=f"[{j.duvida_id}] tem destinos mas não declara a próxima "
                            "dúvida: o CTA principal fica sem critério."))

        # saída oficial: classificação recalculada x declarada
        calculada = classificar_saida_oficial(p)
        declarada = j.saida_oficial.classificacao
        if papel is PageRole.LP and calculada == "prematura":
            a(Issue(code="saida_oficial_prematura",
                    message=f"[{j.duvida_id}] saída oficial direto na LP antes da "
                            "qualificação: prematura (salvo justificativa explícita)."))
        if j.saida_oficial.esperada and declarada != calculada:
            a(Issue(code="saida_oficial_divergente",
                    message=f"[{j.duvida_id}] o arquiteto declarou a saída oficial como "
                            f"'{declarada}', a régua calcula '{calculada}' "
                            "(boa exige condição terminal ou justificativa)."))

    # --- ciclos sem ganho de informação
    adj = {p.slug: [l.target for l in _links(p) if l.target in por_slug]
           for p in plan.pages}
    for ciclo in _ciclos(adj):
        descricao = _descreve_ciclo(ciclo, por_slug)
        motivo = _ciclo_justificado(ciclo, por_slug)
        if motivo:
            a(Issue(code="retorno_justificado",
                    message=f"ciclo {descricao} mantido com justificativa: {motivo}."))
        else:
            b(Issue(code="loop_sem_ganho",
                    message=f"ciclo {descricao} sem ganho de informação: o clique devolve "
                            "o leitor a uma dúvida que ele já resolveu. Declare "
                            "`retornos_justificados` ou tire uma das arestas."))

    # --- toda entrada chega a uma conclusão
    entradas = {p.slug for p in plan.pages
                if effective_role(p) is PageRole.LP or p.jornada.coortes_de_entrada}
    if plan.jornada is not None:
        entradas |= {por_duvida[c.entrada].slug for c in plan.jornada.coortes}
    for slug in sorted(entradas):
        vistos, pilha = set(), [slug]
        while pilha:
            atual = pilha.pop()
            if atual in vistos:
                continue
            vistos.add(atual)
            pilha.extend(adj.get(atual, []))
        if not any(_conclusiva(por_slug[s]) for s in vistos):
            b(Issue(code="entrada_sem_conclusao",
                    message=f"[{_rotulo(por_slug[slug])}] quem entra aqui não tem caminho "
                            "até uma conclusão (condição terminal ou saída oficial boa)."))

    # --- funil: checkpoint, coortes, message match
    fj = plan.jornada
    if fj is not None:
        if fj.checkpoint and not _conclusiva(por_duvida[fj.checkpoint]):
            a(Issue(code="checkpoint_sem_conclusao",
                    message=f"o checkpoint '{fj.checkpoint}' não declara condição terminal "
                            "nem saída oficial boa."))
        for c in fj.coortes:
            entrada = por_duvida[c.entrada]
            ids_destino = {por_slug[l.target].jornada.duvida_id for l in _links(entrada)
                           if l.target in por_slug}
            if c.proximo_passo and c.proximo_passo not in ids_destino:
                b(Issue(code="coorte_proximo_passo_fora_do_mapa",
                        message=f"[coorte:{c.canal}] o próximo passo '{c.proximo_passo}' "
                                f"não é destino de '{c.entrada}'."))
            if c.canal in CANAIS_FRIOS and c.profundidade == "guiada":
                a(Issue(code="coorte_fria_sem_resposta_direta",
                        message=f"[coorte:{c.canal}] tráfego frio com profundidade guiada: "
                                "quem chega sem tarefa decide em um ou dois olhares."))
        quentes = [c for c in fj.coortes if c.canal == "paid_search"]
        frias = [c for c in fj.coortes if c.canal in CANAIS_FRIOS]
        for q in quentes:
            for f in frias:
                if q.entrada == f.entrada and _norm(q.promessa) == _norm(f.promessa):
                    a(Issue(code="promessa_identica_entre_coortes",
                            message=f"[coorte:{q.canal} x coorte:{f.canal}] mesma promessa "
                                    f"na mesma entrada ('{q.promessa}'): busca paga de alta "
                                    "intenção e tráfego frio não deveriam receber a mesma "
                                    "promessa, profundidade e próximo passo por padrão."))
    _message_match(plan, a)
    return rev


def _termos_de_aquisicao(plan: FunnelPlan) -> set[str]:
    termos: set[str] = set()
    anuncio = plan.contexto_de_anuncio
    if anuncio is not None and anuncio.estado == "presente":
        for t in [*anuncio.titulos, *anuncio.descricoes]:
            termos |= _tokens(t)
    busca = plan.contexto_de_busca
    if busca is not None and busca.estado == "presente":
        for t in busca.termos:
            termos |= _tokens(t.termo)
    return termos


def _message_match(plan: FunnelPlan, aviso) -> None:
    """Congruência query/anúncio → LP: proxy por termo, então só AVISO. O juiz
    Search (que já recebe a promessa da LP) é quem julga o sentido."""
    termos = _termos_de_aquisicao(plan)
    if not termos:
        return
    lp = next((p for p in plan.pages if effective_role(p) is PageRole.LP and p.jornada), None)
    if lp is None:
        return
    texto = f"{lp.jornada.pergunta_principal} {lp.jornada.resposta_imediata}"
    if plan.jornada is not None:
        texto += " " + " ".join(c.promessa for c in plan.jornada.coortes
                                if c.canal == "paid_search")
    if not (_tokens(texto) & termos):
        aviso(Issue(code="message_match_fraco",
                    message="a pergunta, a resposta e a promessa paga da LP não ecoam "
                            "nenhum termo do anúncio nem da busca."))


# ---------------------------------------------------------------------------
# o que o redator recebe
# ---------------------------------------------------------------------------

def alvo_da_proxima_duvida(plan: FunnelPlan, page: Page) -> str | None:
    """O slug do destino que resolve a próxima dúvida (o CTA principal)."""
    if page.jornada is None or not page.jornada.proxima_duvida:
        return None
    por_slug = _por_slug(plan)
    for link in _links(page):
        alvo = por_slug.get(link.target)
        if alvo is not None and alvo.jornada is not None and (
                alvo.jornada.duvida_id == page.jornada.proxima_duvida):
            return alvo.slug
    return None


def contexto_de_jornada(plan: FunnelPlan | None, page: Page) -> dict[str, Any]:
    """O contrato da jornada desta página, pronto para o prompt. `{}` quando a
    página não tem jornada — e aí os templates não mudam um byte."""
    if plan is None or page.jornada is None:
        return {}
    j = page.jornada
    por_slug, por_duvida = _por_slug(plan), _por_duvida(plan)
    principal = alvo_da_proxima_duvida(plan, page)
    destinos = []
    for link in _links(page):
        alvo = por_slug.get(link.target)
        if alvo is None or alvo.jornada is None:
            continue
        destinos.append({
            "slug": alvo.slug,
            "cta": alvo.editorial.cta_label if alvo.editorial else "",
            "resolve": alvo.jornada.pergunta_principal,
            "motivo": link.reason,
            "principal": alvo.slug == principal,
            "retorno_justificado": _justificado(page, alvo),
        })
    destinos.sort(key=lambda d: not d["principal"])
    return {
        "duvida_id": j.duvida_id,
        "pergunta": j.pergunta_principal,
        "trabalho": j.trabalho_do_leitor,
        "resposta_imediata": j.resposta_imediata,
        "coortes": list(j.coortes_de_entrada),
        "ja_resolvido": [por_duvida[d].jornada.pergunta_principal
                         for d in j.ja_resolvido if d in por_duvida],
        "proxima_duvida": (por_duvida[j.proxima_duvida].jornada.pergunta_principal
                           if j.proxima_duvida in por_duvida else ""),
        "destinos": destinos,
        "condicao_terminal": j.condicao_terminal,
        "entrada_direta": j.entrada_direta,
        "saida_oficial": {"classificacao": classificar_saida_oficial(page),
                          "condicao": j.saida_oficial.condicao,
                          "justificativa": j.saida_oficial.justificativa},
        "monetizacao": j.monetizacao.model_dump(),
    }


# ---------------------------------------------------------------------------
# revisão GLOBAL do funil pronto (depois da redação)
# ---------------------------------------------------------------------------

_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_P_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _texto_lp(conteudo: str) -> tuple[str, str]:
    """(primeira dobra, texto inteiro) do JSON da LP."""
    try:
        obj = json.loads(conteudo)
    except (ValueError, TypeError):
        return "", conteudo
    dobra = " ".join(str(obj.get(k) or "") for k in ("hero_title", "hero_subtitle", "intro"))
    return _TAG_RE.sub(" ", dobra), _TAG_RE.sub(" ", conteudo)


def _primeira_dobra_html(conteudo: str, ancora: int) -> str:
    paragrafos = _P_RE.findall(conteudo)[:max(1, ancora)]
    return _TAG_RE.sub(" ", " ".join(paragrafos))


def _hrefs(conteudo: str, host: str) -> tuple[list[str], list[str]]:
    """(slugs internos, URLs externas) na ordem em que aparecem."""
    internos, externos = [], []
    for href in _HREF_RE.findall(conteudo):
        partes = urlparse(href)
        if not partes.netloc or partes.netloc.lower() == host:
            seg = [s for s in partes.path.split("/") if s]
            if seg:
                internos.append(seg[-1])
        elif partes.scheme == "https":
            externos.append(href)
    return internos, externos


def revisar_funil_pronto(state: Any, settings: Any) -> dict:
    """UMA passada consolidada sobre os rascunhos prontos. Devolve o registro
    `revisao-global-v1` com achados LOCALIZADOS (página, regra, localizador,
    evidência, proposta). Nenhum texto é alterado: a revisão por página já
    consumiu a única rodada de microajuste; conflito material vai à pessoa."""
    plan: FunnelPlan | None = state.plan
    if not tem_jornada(plan) or not state.drafts:
        return {}
    assert plan is not None
    host = urlparse(settings.site.domain).netloc.lower()
    ancoras = list(getattr(settings.ads, "paragraph_anchors", []) or [1])
    primeira_ancora = min(ancoras) if ancoras else 1
    por_slug = _por_slug(plan)
    achados: list[dict] = []

    def achado(page: Page, regra: str, localizador: str, evidencia: str,
               proposta: str, severidade: str = "material") -> None:
        achados.append({"pagina": page.page_number, "slug": page.slug,
                        "duvida_id": _rotulo(page), "regra": regra,
                        "localizador": localizador, "evidencia": evidencia,
                        "proposta": proposta, "severidade": severidade})

    saidas: dict[str, list[str]] = {}
    grafo: dict[str, list[str]] = {}
    escritas = [p for p in plan.pages
                if p.page_number in state.drafts and p.jornada is not None]
    for p in escritas:
        draft = state.drafts[p.page_number]
        j = p.jornada
        if draft.format == "lp_json":
            dobra, _ = _texto_lp(draft.content)
            internos = [r.target for r in p.routes if r.kind == "funnel"]
            _, externos = _hrefs(draft.content.replace('\\"', '"'), host)
            local = "hero_title + hero_subtitle + intro"
        else:
            dobra = _primeira_dobra_html(draft.content, primeira_ancora)
            internos, externos = _hrefs(draft.content, host)
            local = (f"primeiro(s) {max(1, primeira_ancora)} parágrafo(s), antes do "
                     "1º slot do Ad Inserter")
        internos = [s for s in dict.fromkeys(internos) if s in por_slug and s != p.slug]
        grafo[p.slug] = internos
        saidas[p.slug] = externos

        if j.resposta_imediata.strip() and not (_tokens(j.resposta_imediata) & _tokens(dobra)):
            achado(p, "resposta_fora_da_primeira_dobra", local,
                   f"a primeira dobra não ecoa a promessa: '{j.resposta_imediata[:160]}'",
                   "Abrir a página com a resposta imediata antes de qualquer slot de "
                   "anúncio ou CTA.")
        for slug in internos:
            alvo = por_slug[slug]
            if alvo.jornada and alvo.jornada.duvida_id in j.ja_resolvido and not _justificado(p, alvo):
                achado(p, "cta_repetido_apos_resolvido", f"href → {slug}",
                       f"oferece de novo '{alvo.jornada.duvida_id}', já resolvida aqui",
                       "Remover o link ou declarar retorno justificado e apresentá-lo "
                       "como secundário.")
        classe = classificar_saida_oficial(p)
        if externos and effective_role(p) is PageRole.LP and classe != "boa":
            achado(p, "saida_oficial_prematura", f"href → {externos[0]}",
                   "link para fonte oficial na LP antes da qualificação",
                   "Levar a saída oficial para a página que resolve a tarefa.")
        principal = alvo_da_proxima_duvida(plan, p)
        if (classe == "prematura" and externos and principal
                and principal in internos):
            conteudo = draft.content
            pos_ext = conteudo.find(externos[0])
            pos_int = conteudo.find(f"/{principal}")
            if 0 <= pos_ext < pos_int:
                achado(p, "saida_oficial_antes_da_proxima_duvida", f"href → {externos[0]}",
                       f"a saída oficial (prematura aqui) vem antes do CTA da próxima "
                       f"dúvida ({principal})",
                       "Colocar o CTA da próxima dúvida antes da saída oficial e dizer "
                       "quando a fonte oficial passa a servir.")
        if classe == "boa" and j.saida_oficial.esperada and not externos:
            achado(p, "saida_oficial_ausente", "corpo inteiro",
                   "a saída oficial boa prevista não aparece no rascunho",
                   "Conferir o canal oficial que a pesquisa trouxe.", "aviso")
        if not internos and not externos and not j.condicao_terminal.strip():
            achado(p, "beco_sem_saida", "corpo inteiro",
                   "nenhum link interno ou oficial e nenhuma conclusão declarada",
                   "Ligar a página à próxima dúvida ou declarar a condição terminal.")

    # órfãs, loops e CTA universal no grafo REAL (o que foi escrito)
    entrada: dict[str, int] = {s: 0 for s in grafo}
    for origem, destinos in grafo.items():
        for d in destinos:
            if d in entrada:
                entrada[d] += 1
    for p in escritas:
        if effective_role(p) is not PageRole.LP and entrada.get(p.slug, 0) == 0 and len(escritas) > 1:
            achado(p, "pagina_orfa", "links de entrada",
                   "nenhuma outra página escrita leva até aqui",
                   "Conferir se o link planejado sobreviveu à redação.")
    for ciclo in _ciclos(grafo):
        if not _ciclo_justificado(ciclo, por_slug):
            p = por_slug[ciclo[0]]
            achado(p, "loop_sem_ganho", "links entre " + ", ".join(ciclo),
                   f"ciclo {_descreve_ciclo(ciclo, por_slug)} no texto publicado",
                   "Tirar a aresta de volta ou justificá-la na jornada.")
    internas = [p for p in escritas if effective_role(p) is not PageRole.LP]
    if len(internas) >= 3:
        for alvo in internas:
            outras = [p for p in internas if p is not alvo]
            if all(alvo.slug in grafo.get(o.slug, []) for o in outras):
                achado(alvo, "cta_universal", "todas as páginas internas",
                       "o mesmo destino aparece em todas as outras páginas",
                       "Mostrar o CTA só onde a dúvida ainda está aberta.", "aviso")

    termos = _termos_de_aquisicao(plan)
    lp = next((p for p in escritas if effective_role(p) is PageRole.LP), None)
    if termos and lp is not None:
        dobra, _ = _texto_lp(state.drafts[lp.page_number].content)
        if not (_tokens(dobra) & termos):
            achado(lp, "message_match_fraco", "hero_title + hero_subtitle + intro",
                   "a primeira dobra da LP não ecoa nenhum termo do anúncio/busca",
                   "Retomar na primeira dobra o termo que trouxe o clique.", "aviso")

    materiais = [x for x in achados if x["severidade"] == "material"]
    return {
        "versao": "revisao-global-v1",
        "decisao": "revisao_humana" if materiais else "sem_achados",
        "paginas_revisadas": [p.page_number for p in escritas],
        "achados": achados,
        "microajustes_aplicados": 0,
        "observacao": ("Nenhum texto foi alterado: cada achado é uma proposta "
                       "localizada para decisão humana. A revisão por página já usou "
                       "a única rodada de microajuste."),
    }


# ---------------------------------------------------------------------------
# contrato de medição
# ---------------------------------------------------------------------------

_FONTE_CTA = "telemetria comportamental: clique em CTA (P08-T07)"
_FONTE_ENGAJ = ("telemetria comportamental: scroll/engagement como PROXY de resolução "
                "(P08-T07) — resolução declarada não é medida direta")
_FONTE_SAIDA = "telemetria comportamental: clique de saída para a fonte oficial (P08-T07)"
_FONTE_RECEITA = "receita AdSense/GAM por URL do funil (campaign_funnel_urls, P08-T02)"
_FONTE_CHEGADA = "vínculo campanha → funil → URLs e UTM do clique (P08-T02)"


def contrato_de_medicao(plan: FunnelPlan, run_id: str,
                        achados: list[dict] | None = None) -> ContratoDeMedicao:
    """O que o funil precisa medir para validar o próprio desenho. Nenhuma
    leitura é inventada: `leituras` nasce vazia e `observadas()` também."""
    sinais: list[SinalPrevisto] = []
    s = sinais.append
    por_slug = _por_slug(plan)
    fj = plan.jornada
    if fj is not None:
        for c in fj.coortes:
            s(SinalPrevisto(sinal="chegada_lp", escopo=f"coorte:{c.canal}->{c.entrada}",
                            hipotese=c.promessa, fonte_prevista=_FONTE_CHEGADA,
                            coleta="existente_parcial"))
    for p in plan.pages:
        if p.jornada is None:
            continue
        j = p.jornada
        for link in _links(p):
            alvo = por_slug.get(link.target)
            if alvo is None or alvo.jornada is None:
                continue
            sinal = "escolha_de_ramo" if effective_role(p) is PageRole.LP else "progressao"
            s(SinalPrevisto(sinal=sinal, escopo=f"aresta:{j.duvida_id}->{alvo.jornada.duvida_id}",
                            hipotese=link.reason, fonte_prevista=_FONTE_CTA,
                            coleta="existente_parcial"))
            motivo = _justificado(p, alvo)
            if motivo:
                s(SinalPrevisto(sinal="loop_revisita",
                                escopo=f"aresta:{j.duvida_id}->{alvo.jornada.duvida_id}",
                                hipotese=f"retorno justificado: {motivo}",
                                fonte_prevista="sequência de pageviews na sessão — não coletada hoje"))
        s(SinalPrevisto(sinal="resolucao", escopo=f"pagina:{j.duvida_id}",
                        hipotese=j.condicao_terminal or j.resposta_imediata or j.pergunta_principal,
                        fonte_prevista=_FONTE_ENGAJ, coleta="existente_parcial"))
        s(SinalPrevisto(sinal="abandono", escopo=f"pagina:{j.duvida_id}",
                        hipotese=j.hipotese_de_medicao or "abandono depois da resposta é sucesso; antes dela é falha",
                        fonte_prevista=_FONTE_ENGAJ, coleta="existente_parcial"))
        classe = classificar_saida_oficial(p)
        if classe != "nao_aplicavel":
            s(SinalPrevisto(sinal=f"saida_oficial_{classe}", escopo=f"pagina:{j.duvida_id}",
                            hipotese=j.saida_oficial.condicao or f"saída oficial {classe}",
                            fonte_prevista=_FONTE_SAIDA, coleta="existente_parcial"))
        s(SinalPrevisto(sinal="core_web_vitals", escopo=f"pagina:{j.duvida_id}",
                        hipotese="anúncio e widget não pioram LCP/INP/CLS a ponto de "
                                 "atrasar a resposta",
                        fonte_prevista="CrUX/PageSpeed por URL publicada — não automatizado"))
    s(SinalPrevisto(sinal="loop_revisita", escopo="funil",
                    hipotese="nenhuma revisita sem ganho: retornos só onde justificados",
                    fonte_prevista="sequência de pageviews na sessão — não coletada hoje"))
    s(SinalPrevisto(sinal="receita_por_sessao", escopo="funil",
                    hipotese=(fj.hipotese_de_medicao if fj and fj.hipotese_de_medicao
                              else "monetização sem destruir clareza nem velocidade"),
                    fonte_prevista=_FONTE_RECEITA, coleta="existente_parcial"))
    s(SinalPrevisto(sinal="rpm_valor_de_sessao", escopo="funil",
                    hipotese="valor de sessão vem de progressão útil, não de páginas extras",
                    fonte_prevista=_FONTE_RECEITA, coleta="existente_parcial"))

    premissas = list(fj.evidencias) if fj else []
    for p in plan.pages:
        if p.jornada is not None:
            premissas.extend(p.jornada.evidencias)
    hipoteses = [f"{e.natureza}: {e.afirmacao}" + (f" ({e.fonte})" if e.fonte else "")
                 for e in premissas if e.natureza != "observacao_real"]
    hipoteses += [f"hipotese: {p.jornada.hipotese_de_medicao}"
                  for p in plan.pages if p.jornada and p.jornada.hipotese_de_medicao]
    mudancas = [MudancaSugerida(alvo=x.get("duvida_id") or "funil",
                                proposta=x["proposta"],
                                motivo=f"[{x['regra']}] {x['evidencia']}",
                                natureza_da_base="hipotese")
                for x in (achados or []) if x.get("severidade") == "material"]
    return ContratoDeMedicao(
        run_id=run_id, sinais=sinais,
        saidas_oficiais={p.jornada.duvida_id: classificar_saida_oficial(p)
                         for p in plan.pages if p.jornada is not None},
        premissas=premissas,
        proposta=PropostaDeNovaVersao(hipoteses_a_testar=hipoteses,
                                      mudancas_sugeridas=mudancas),
    )
