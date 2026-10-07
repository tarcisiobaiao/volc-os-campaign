"""REVISÃO GLOBAL do funil pronto: uma passada determinística ANTES de qualquer
publicação, só sobre as páginas estruturalmente aprovadas.

Duas severidades, e a fronteira é a prova:
- `bloqueio` — prova ESTRUTURAL no texto escrito (href para dúvida resolvida
  em todo caminho, ciclo real sem justificativa, link oficial na LP, saída
  prematura antes da próxima dúvida, página sem saída nem conclusão). A página
  apontada não vai ao rascunho; o pipeline registra `blocked_pN`.
- `aviso` — proxy (sobreposição de termos, message match, CTA universal,
  órfã por falta de link de entrada). Vai à pessoa; não bloqueia.

Nenhum texto é alterado: a revisão por página já usou a única rodada de
microajuste.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from funnelforge.domain.models import FunnelPlan, Page, PageRole, RunState, StepStatus, effective_role
from funnelforge.pipeline.jornada._comum import (
    ciclo_justificado,
    ciclos,
    classificar_saida_oficial,
    descreve_ciclo,
    estado_do_leitor,
    justificado,
    por_slug,
    rotulo,
    tem_jornada,
    tokens,
)
from funnelforge.pipeline.jornada.contexto import alvo_da_proxima_duvida
from funnelforge.pipeline.jornada.esqueleto import termos_de_aquisicao

_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_P_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")

#: Passos cuja reprovação tira a página da revisão do funil pronto.
_PASSOS_QUE_REPROVAM = ("research", "write", "judge", "revisor", "content_gate")


def pagina_aprovada(state: RunState, page: Page) -> bool:
    """Estruturalmente aprovada = tem rascunho, passou pelo portão final e nada
    a condenou. Rascunho de página reprovada não é página pronta."""
    n = page.page_number
    if n not in state.drafts or f"blocked_p{n}" in state.step_status:
        return False
    gate = state.step_status.get(f"content_gate_p{n}")
    if gate is None or gate.status is StepStatus.FAILED:
        return False
    return not any((r := state.step_status.get(f"{k}_p{n}")) is not None
                   and r.status is StepStatus.FAILED for k in _PASSOS_QUE_REPROVAM)


def _texto_lp(conteudo: str) -> str:
    try:
        obj = json.loads(conteudo)
    except (ValueError, TypeError):
        return ""
    dobra = " ".join(str(obj.get(k) or "") for k in ("hero_title", "hero_subtitle", "intro"))
    return _TAG_RE.sub(" ", dobra)


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


def revisar_funil_pronto(state: RunState, settings: Any) -> dict:
    plan: FunnelPlan | None = state.plan
    if not tem_jornada(plan) or not state.drafts:
        return {}
    assert plan is not None
    host = urlparse(settings.site.domain).netloc.lower()
    ancoras = list(getattr(settings.ads, "paragraph_anchors", []) or [1])
    primeira_ancora = min(ancoras) if ancoras else 1
    slugs = por_slug(plan)
    aprovadas = [p for p in plan.pages if p.jornada is not None and pagina_aprovada(state, p)]
    fora = [p.page_number for p in plan.pages
            if p.page_number in state.drafts and p not in aprovadas]
    achados: list[dict] = []

    def achado(page: Page, regra: str, localizador: str, evidencia: str,
               proposta: str, severidade: str) -> None:
        achados.append({"pagina": page.page_number, "slug": page.slug,
                        "duvida_id": rotulo(page), "regra": regra,
                        "localizador": localizador, "evidencia": evidencia,
                        "proposta": proposta, "severidade": severidade})

    grafo: dict[str, list[str]] = {}
    for p in aprovadas:
        draft = state.drafts[p.page_number]
        j = p.jornada
        if draft.format == "lp_json":
            dobra = _texto_lp(draft.content)
            internos = [r.target for r in p.routes if r.kind == "funnel"]
            _, externos = _hrefs(draft.content.replace('\\"', '"'), host)
            local = "hero_title + hero_subtitle + intro"
        else:
            dobra = _primeira_dobra_html(draft.content, primeira_ancora)
            internos, externos = _hrefs(draft.content, host)
            local = (f"primeiro(s) {max(1, primeira_ancora)} parágrafo(s), antes do "
                     "1º slot do Ad Inserter")
        internos = [s for s in dict.fromkeys(internos) if s in slugs and s != p.slug]
        grafo[p.slug] = internos

        if j.resposta_imediata.strip() and not (tokens(j.resposta_imediata) & tokens(dobra)):
            achado(p, "resposta_fora_da_primeira_dobra", local,
                   f"a primeira dobra não ecoa a promessa: '{j.resposta_imediata[:160]}'",
                   "Abrir a página com a resposta imediata antes de qualquer slot de "
                   "anúncio ou CTA.", "aviso")
        estado = estado_do_leitor(plan, p)
        for slug in internos:
            alvo = slugs[slug]
            if (alvo.jornada and alvo.jornada.duvida_id in estado.certamente
                    and not justificado(p, alvo)):
                achado(p, "cta_repetido_apos_resolvido", f"href → {slug}",
                       f"oferece de novo '{alvo.jornada.duvida_id}', resolvida em todo "
                       "caminho até aqui",
                       "Remover o link ou declarar retorno justificado.", "bloqueio")
        classe = classificar_saida_oficial(p)
        if externos and effective_role(p) is PageRole.LP and classe != "boa":
            achado(p, "saida_oficial_prematura", f"href → {externos[0]}",
                   "link para fonte oficial na LP antes da qualificação",
                   "Levar a saída oficial para a página que resolve a tarefa.", "bloqueio")
        principal = alvo_da_proxima_duvida(plan, p)
        if classe == "prematura" and externos and principal and principal in internos:
            pos_ext = draft.content.find(externos[0])
            pos_int = draft.content.find(f"/{principal}")
            if 0 <= pos_ext < pos_int:
                achado(p, "saida_oficial_antes_da_proxima_duvida", f"href → {externos[0]}",
                       f"a saída oficial (prematura aqui) vem antes do CTA da próxima "
                       f"dúvida ({principal})",
                       "Colocar o CTA da próxima dúvida antes da saída oficial e dizer "
                       "quando a fonte oficial passa a servir.", "bloqueio")
        if classe == "boa" and j.saida_oficial.esperada and not externos:
            achado(p, "saida_oficial_ausente", "corpo inteiro",
                   "a saída oficial boa prevista não aparece no rascunho",
                   "Conferir o canal oficial que a pesquisa trouxe.", "aviso")
        if not internos and not externos and not j.condicao_terminal.strip():
            achado(p, "beco_sem_saida", "corpo inteiro",
                   "nenhum link interno ou oficial e nenhuma conclusão declarada",
                   "Ligar a página à próxima dúvida ou declarar a condição terminal.",
                   "bloqueio")

    entrada: dict[str, int] = {s: 0 for s in grafo}
    for destinos in grafo.values():
        for d in destinos:
            if d in entrada:
                entrada[d] += 1
    for p in aprovadas:
        if (effective_role(p) is not PageRole.LP and entrada.get(p.slug, 0) == 0
                and len(aprovadas) > 1):
            achado(p, "pagina_orfa", "links de entrada",
                   "nenhuma outra página aprovada leva até aqui",
                   "Conferir se o link planejado sobreviveu à redação.", "aviso")
    for ciclo in ciclos(grafo):
        if not ciclo_justificado(ciclo, slugs):
            achado(slugs[ciclo[0]], "loop_sem_ganho", "links entre " + ", ".join(ciclo),
                   f"ciclo {descreve_ciclo(ciclo, slugs)} no texto escrito",
                   "Tirar a aresta de volta ou justificá-la na jornada.", "bloqueio")
    internas = [p for p in aprovadas if effective_role(p) is not PageRole.LP]
    if len(internas) >= 3:
        for alvo in internas:
            outras = [p for p in internas if p is not alvo]
            if all(alvo.slug in grafo.get(o.slug, []) for o in outras):
                achado(alvo, "cta_universal", "todas as páginas internas",
                       "o mesmo destino aparece em todas as outras páginas",
                       "Mostrar o CTA só onde a dúvida ainda está aberta.", "aviso")
    termos = termos_de_aquisicao(plan)
    lp = next((p for p in aprovadas if effective_role(p) is PageRole.LP), None)
    if termos and lp is not None:
        if not (tokens(_texto_lp(state.drafts[lp.page_number].content)) & termos):
            achado(lp, "message_match_fraco", "hero_title + hero_subtitle + intro",
                   "a primeira dobra da LP não ecoa nenhum termo do anúncio/busca",
                   "Retomar na primeira dobra o termo que trouxe o clique.", "aviso")

    bloqueadas = sorted({a["pagina"] for a in achados if a["severidade"] == "bloqueio"})
    return {
        "versao": "revisao-global-v2",
        "decisao": ("bloqueio_estrutural" if bloqueadas
                    else "avisos_para_humano" if achados else "sem_achados"),
        "paginas_revisadas": [p.page_number for p in aprovadas],
        "paginas_fora_da_revisao": fora,
        "paginas_bloqueadas": bloqueadas,
        "achados": achados,
        "microajustes_aplicados": 0,
        "observacao": ("Nenhum texto foi alterado. Bloqueio só com prova estrutural; "
                       "avisos são propostas localizadas para decisão humana."),
    }
