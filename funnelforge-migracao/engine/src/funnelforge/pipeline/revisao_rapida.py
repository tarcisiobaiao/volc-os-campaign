"""Perfil RÁPIDO: o pacote de cada página (por código) e UMA revisão global do
funil (por modelo), com patches mínimos aplicados uma vez pelo código.

Só `block` vai para revisão humana — e é UMA revisão consolidada do funil.
Aviso não manda página para humano."""
from __future__ import annotations

import html as _html
import json
import re
from collections import Counter
from typing import Any

from funnelforge.domain.models import Issue, Page, RunState, StepResult, StepStatus

LIMITE_DE_TEXTO_POR_PAGINA = 7000

BLOQUEIOS = (
    "conflito na promessa central",
    "afirmação crítica sem evidência",
    "número, prazo, direito ou elegibilidade sem sustentação no dossiê",
    "destino ou CTA quebrado (leva a lugar errado ou inexistente)",
    "estrutura Gutenberg inválida",
    "violação real de política (promessa enganosa, coleta de dado pessoal, falsa oficialidade)",
)
NAO_BLOQUEIOS = (
    "detalhe opcional ausente", "fonte temporariamente indisponível", "sugestão de estilo",
    "pequena repetição", "widget desligado", "oportunidade editorial adicional",
)


# ---------------------------------------------------------------------------
# texto e pacote da página (código)
# ---------------------------------------------------------------------------

def _valores(no: Any) -> list[str]:
    if isinstance(no, dict):
        return [v for x in no.values() for v in _valores(x)]
    if isinstance(no, list):
        return [v for x in no for v in _valores(x)]
    return [str(no)] if isinstance(no, str) else []


def texto_da_pagina(draft: Any) -> str:
    """O texto legível da página: títulos marcados, links com destino."""
    if draft is None:
        return ""
    if draft.format == "lp_json":
        try:
            return "\n".join(_valores(json.loads(draft.content)))
        except ValueError:
            return draft.content
    t = re.sub(r"<!--.*?-->", "", draft.content, flags=re.S)
    t = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", lambda m: f"\n{'#' * int(m.group(1))} {m.group(2)}\n",
               t, flags=re.S)
    t = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", t, flags=re.S)
    t = re.sub(r"<(li|p|tr|summary)[^>]*>", "\n", t)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def pacote_da_pagina(state: RunState, page: Page) -> dict:
    """Tudo o que a página entrega, extraído do texto escrito, do dossiê e do
    plano — sem modelo."""
    n = page.page_number
    draft = state.drafts.get(n)
    conteudo = draft.content if draft else ""
    lp = draft is not None and draft.format == "lp_json"
    hrefs = re.findall(r'href="([^"]+)"', conteudo) if not lp else []
    ancoras = re.findall(r'<a [^>]*href="[^"]+"[^>]*>(.*?)</a>', conteudo, flags=re.S) if not lp else []
    dados_lp = {}
    if lp:
        try:
            dados_lp = json.loads(conteudo)
        except ValueError:
            dados_lp = {}
    funil = [r for r in page.routes if r.kind == "funnel"]
    dossie = next((p for p in (state.dossie or {}).get("paginas", []) if p.get("page_number") == n), {})
    por_id = {f["fact_id"]: f for f in (state.dossie or {}).get("fatos", [])}
    texto = texto_da_pagina(draft)
    usados = []
    for fid in dossie.get("fatos_verificados", []):
        f = por_id.get(fid) or {}
        numeros = re.findall(r"\d+(?:[.,]\d+)*", f.get("valor") or "")
        if (numeros and all(x in texto for x in numeros)) or (
                f.get("source_url") and f["source_url"] in conteudo):
            usados.append(fid)
    j = page.jornada
    meta = state.metadados.get(n) or {}
    return {
        "page_number": n, "slug": page.slug, "papel": page.page_type,
        "titulo": page.h1_title,
        "subtitulos": (re.findall(r"<h2[^>]*>(.*?)</h2>", conteudo, flags=re.S) if not lp
                       else [s for s in dados_lp.get("section_titles", []) if isinstance(s, str)]),
        "cta_principal": funil[0].anchor if funil else (dados_lp.get("cta_texts") or [""])[0],
        "ctas_secundarios": [r.anchor for r in funil[1:]],
        "seo": state.seo.get(n, {}),
        "plano_gutenberg": dict(Counter(re.findall(r"<!-- wp:([a-z0-9/-]+)", conteudo))),
        "schema": [b.get("@type") for b in (meta.get("jsonld") or []) if isinstance(b, dict)],
        "screenshot_oficial": {
            "necessario": bool(j and any(b.intencao == "prova_oficial" for b in j.plano_visual)),
            "canal": (state.official_links.get(n) or [""])[0]},
        "ativo": [{"pergunta": a.pergunta,
                   "estado": "desligado neste perfil (registrado para geração)"}
                  for a in (j.ativos if j else [])],
        "fatos_usados": usados,
        "links": hrefs, "ancoras": [re.sub(r"<[^>]+>", "", a).strip() for a in ancoras],
        "canais_oficiais": [u for u in (state.official_links.get(n) or []) if u in conteudo],
        "palavras": len(texto.split()),
        "estado_da_evidencia": (dossie.get("cobertura") or {}).get("estado", ""),
    }


# ---------------------------------------------------------------------------
# a revisão global (modelo)
# ---------------------------------------------------------------------------

def prompt_da_revisao(state: RunState) -> str:
    plan = state.plan
    jornada = plan.jornada.model_dump() if plan and plan.jornada else {}
    promessas = [c.get("promessa") for c in jornada.get("coortes", []) if c.get("promessa")]
    por_id = {f["fact_id"]: f for f in (state.dossie or {}).get("fatos", [])}
    blocos = []
    for page in plan.pages:
        n = page.page_number
        dp = next((p for p in (state.dossie or {}).get("paginas", [])
                   if p.get("page_number") == n), {})
        fatos = "\n".join(f"  - [{fid}] {por_id[fid]['afirmacao']} ({por_id[fid].get('valor', '')} "
                          f"{por_id[fid].get('unidade', '')}) — {por_id[fid].get('source_url') or 'derivado'}"
                          for fid in dp.get("fatos_verificados", []) if fid in por_id)
        degr = "\n".join(f"  - {d['instrucao']}" for d in
                         (dp.get("cobertura") or {}).get("degradacoes", []))
        j = page.jornada
        blocos.append(
            f"=== PÁGINA {n} ({page.page_type}, /{page.slug}) ===\n"
            f"Pergunta: {j.pergunta_principal if j else page.h1_title}\n"
            f"Próxima dúvida: {j.proxima_duvida if j else ''}\n"
            f"Resposta imediata planejada: {j.resposta_imediata if j else ''}\n"
            f"Destinos: {[r.target + ' (' + r.kind + ')' for r in page.routes]}\n"
            f"Fatos verificados do dossiê:\n{fatos or '  (nenhum)'}\n"
            f"Não pode ser afirmado:\n{degr or '  (nada)'}\n"
            f"TEXTO:\n{texto_da_pagina(state.drafts.get(n))[:LIMITE_DE_TEXTO_POR_PAGINA]}\n")
    return (
        "Você é o REVISOR GLOBAL de um funil editorial pronto. Leia as páginas inteiras e julgue "
        "o funil como um todo: congruência com o anúncio e a intenção, progressão da jornada, "
        "repetição entre páginas, utilidade, fatos críticos contra o dossiê, naturalidade, CTAs, "
        "compliance e consistência entre páginas.\n\n"
        f"Intenção do funil: {jornada.get('intencao_principal', '')}\n"
        f"Promessas dos anúncios: {promessas}\n\n"
        "VEREDITO por página: 'pass', 'warning' ou 'block'. Só é BLOCK:\n"
        + "\n".join(f"- {b}" for b in BLOQUEIOS)
        + "\nNUNCA é block (no máximo warning): " + "; ".join(NAO_BLOQUEIOS) + ".\n\n"
        "Para cada block, proponha o PATCH MÍNIMO: um trecho que existe LITERALMENTE no texto da "
        "página (copie exato, curto) e o trecho novo. Patch nunca acrescenta número, prazo, "
        "direito ou link que não esteja no dossiê; remover ou generalizar é permitido.\n\n"
        "Responda SOMENTE um objeto JSON (sem markdown):\n"
        '{"paginas": [{"page_number": 1, "veredito": "pass|warning|block", "achados": '
        '[{"categoria": "...", "severidade": "warning|block", "motivo": "...", "trecho": "..."}], '
        '"patches": [{"trecho_original": "...", "trecho_novo": "...", "motivo": "..."}]}], '
        '"resumo": "..."}\n\n' + "\n".join(blocos))


def _substituir(draft: Any, original: str, novo: str) -> bool:
    """Aplica o patch se o trecho original existir UMA vez (no HTML ou num
    valor do JSON da LP). Senão, não aplica."""
    if not original or original == novo:
        return False
    if draft.format == "lp_json":
        try:
            dados = json.loads(draft.content)
        except ValueError:
            return False
        achados = [v for v in _valores(dados) if original in v]
        if len(achados) != 1 or achados[0].count(original) != 1:
            return False

        def trocar(no):
            if isinstance(no, dict):
                return {k: trocar(v) for k, v in no.items()}
            if isinstance(no, list):
                return [trocar(v) for v in no]
            return no.replace(original, novo) if isinstance(no, str) else no
        draft.content = json.dumps(trocar(dados), ensure_ascii=False)
        return True
    if draft.content.count(original) != 1:
        return False
    draft.content = draft.content.replace(original, novo)
    return True


def revisar_funil_rapido(state: RunState, deps: Any) -> dict:
    """UMA chamada de revisão global; patches de block aplicados uma vez; o que
    continua block vira a revisão humana consolidada do funil."""
    from funnelforge.pipeline import steps as st
    cfg = deps.settings.steps.get("revisor") or deps.settings.steps.get("judge")
    texto, res = deps.runner.run_llm_step(
        "revisao_global_rapida", cfg, [{"role": "user", "content": prompt_da_revisao(state)}],
        ctx={}, run_id=state.run_id)
    try:
        dados = st._tolerant_json(texto)
    except (ValueError, json.JSONDecodeError):
        dados = {}
    paginas = {int(p.get("page_number", 0)): p for p in (dados.get("paginas") or [])
               if isinstance(p, dict)}
    resultado = {"versao": "revisao-global-rapida-v1", "resumo": dados.get("resumo", ""),
                 "paginas": [], "revisao_humana": [], "patches_aplicados": 0}
    por_numero = {p.page_number: p for p in state.plan.pages}
    for n, page in sorted(por_numero.items()):
        r = paginas.get(n, {"veredito": "warning", "achados": [{
            "categoria": "revisao", "severidade": "warning",
            "motivo": "o revisor não devolveu veredito para esta página"}], "patches": []})
        veredito = r.get("veredito") if r.get("veredito") in ("pass", "warning", "block") else "warning"
        aplicados, recusados = [], []
        draft = state.drafts.get(n)
        if veredito == "block" and draft is not None:
            for patch in r.get("patches") or []:
                ok = _substituir(draft, str(patch.get("trecho_original") or ""),
                                 str(patch.get("trecho_novo") or ""))
                (aplicados if ok else recusados).append(patch)
            if aplicados:
                # remonta e reconfere a página, por código
                state.step_status.pop(f"build_p{n}", None)
                state.step_status.pop(f"content_gate_p{n}", None)
                st.step_build(state, page, deps)
                st.step_content_gate(state, page, deps)
            gate = state.step_status.get(f"content_gate_p{n}")
            corrigida = (bool(aplicados) and not recusados
                         and (gate is None or gate.status is not StepStatus.FAILED))
            veredito = "warning" if corrigida else "block"
        resultado["patches_aplicados"] += len(aplicados)
        item = {"page_number": n, "veredito_do_revisor": r.get("veredito"), "veredito": veredito,
                "achados": r.get("achados") or [], "patches_aplicados": aplicados,
                "patches_recusados": recusados}
        resultado["paginas"].append(item)
        if veredito == "block":
            resultado["revisao_humana"].append(item)
            state.step_status[f"blocked_p{n}"] = StepResult(
                step=f"blocked_p{n}", status=StepStatus.FAILED,
                issues=[Issue(code="revisao_global_block",
                              message="; ".join(a.get("motivo", "") for a in r.get("achados") or []
                                                if a.get("severidade") == "block")[:500])])
    res.issues = [Issue(code="revisao_global_rapida", message=(
        f"{sum(1 for p in resultado['paginas'] if p['veredito'] == 'pass')} pass, "
        f"{sum(1 for p in resultado['paginas'] if p['veredito'] == 'warning')} warning, "
        f"{len(resultado['revisao_humana'])} block; {resultado['patches_aplicados']} patch(es) "
        "aplicado(s)"))]
    state.step_status["revisao_global_rapida"] = res
    return resultado
