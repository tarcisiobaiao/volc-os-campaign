"""CTAs DO FUNIL: os botões do funil inteiro numa chamada, antes da redação.

O rótulo de cada botão nascia no arquiteto, antes de existir pesquisa, entrega
confirmada ou ferramenta pronta; o redator recebia esse rótulo congelado e, se
a ferramenta do destino saía, reescrevia o botão sozinho, página por página.

Aqui o mesmo modelo e o mesmo cliente autenticado do redator recebem, uma vez,
todas as arestas com o que cada destino de fato entrega, e devolvem o texto de
cada botão. O código só confere o que é objetivo (todas as arestas, até 60
caracteres, sem URL, sem número fora dos fatos do destino, rótulos distintos
para destinos distintos da mesma página) e aplica o rótulo na rota. Destino e
href nunca mudam aqui. Rótulo recusado ou chamada que falha: fica o rótulo do
plano aprovado, com o motivo no recibo.

Numa nova congelada de pacotes, só as arestas cujo destino mudou de capacidade
(entrega ou ferramenta) voltam ao modelo.
"""
from __future__ import annotations

import json
import re
from typing import Any

from funnelforge.domain.dossie import numeros_do_texto, sha256_canonico
from funnelforge.domain.models import Issue, StepResult, StepStatus, effective_role

VERSAO = "ctas-do-funil-v1"
MAX_ROTULO = 60          # copy_contract.CTA_MAX_CHARS
SUFIXO_DE_SAIDA = " >>>"
_PROIBIDO_RE = re.compile(r"https?://|www\.|<|>|\[|\]|\"", re.I)
_NUMERO_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _chave(url: str) -> str:
    return (url or "").split("#", 1)[0].rstrip("/")


def _fatos(state, numero: int) -> list[dict]:
    from funnelforge.pipeline.dossie import projecao_para_o_prompt
    return projecao_para_o_prompt(state.dossie or {}, numero).get("fatos") or []


def _ferramentas_prontas(ferramentas: dict) -> list[dict]:
    itens = [a for a in ferramentas.get("itens") or [] if a.get("estado") == "pronta"]
    if ferramentas.get("orientacao"):
        itens.append(ferramentas["orientacao"])
    return [{"nome": a.get("nome") or a.get("pergunta") or "",
             "entradas": a.get("entradas") or [],
             "resultado": a.get("resultado") or a.get("entrega") or "",
             "limites": a.get("limites") or "resultado informativo; não confirma direito"}
            for a in itens]


def _assinatura(entrega: str, ferramentas: list[dict]) -> str:
    return sha256_canonico({"entrega": entrega,
                            "ferramentas": [(f["nome"], f["resultado"]) for f in ferramentas]})[:16]


def _oficial(state, url: str) -> dict:
    """Quem publica a saída oficial e o que a fonte sustenta, pelo dossiê."""
    from urllib.parse import urlparse
    fatos = [f for f in (state.dossie or {}).get("fatos", [])
             if _chave(f.get("source_url")) == _chave(url) and f.get("status") == "verified"]
    prov = next((f.get("proveniencia") or {} for f in fatos if f.get("proveniencia")), {})
    emissor = prov.get("issuer") or (prov.get("declarado") or {}).get("emissor") or ""
    titulo = next(((f.get("documento") or {}).get("titulo") for f in fatos
                   if (f.get("documento") or {}).get("titulo")), "")
    return {"instituicao": re.sub(r"\s+", " ", str(emissor)).strip(),
            "host": (urlparse(url).hostname or "").removeprefix("www."),
            "titulo": titulo or "", "fatos": [f["afirmacao"][:160] for f in fatos[:3]]}


def _arestas(state, deps, ferramentas: dict, entregas: dict) -> tuple[list[dict], dict]:
    """Uma aresta por (origem, destino), com a assinatura do que o destino entrega."""
    from funnelforge.pipeline import steps as st
    por_slug = {p.slug: p for p in state.plan.pages}
    arestas, oficiais = [], {}
    for p in state.plan.pages:
        st._write_ctx(state, p, deps)            # liga a saída oficial (rota tardia)
        vistos = set()
        for r in p.routes:
            if r.kind == "funnel" and r.target in por_slug and r.target not in vistos:
                vistos.add(r.target)
                alvo = por_slug[r.target]
                entrega = entregas.get(alvo.page_number) or (
                    alvo.jornada.resposta_imediata if alvo.jornada else
                    (alvo.editorial.useful_delivery if alvo.editorial else ""))
                prontas = _ferramentas_prontas(ferramentas.get(alvo.page_number) or {})
                arestas.append({"origem": p.page_number, "tipo": "funnel", "destino": r.target,
                                "destino_pagina": alvo.page_number, "posicao": r.placement,
                                "rotulo_atual": r.anchor,
                                "assinatura": _assinatura(entrega, prontas)})
            elif r.kind == "external_official" and _chave(r.target) not in vistos:
                vistos.add(_chave(r.target))
                info = oficiais.setdefault(_chave(r.target), _oficial(state, r.target))
                arestas.append({"origem": p.page_number, "tipo": "oficial", "destino": r.target,
                                "posicao": r.placement, "rotulo_atual": r.anchor,
                                "assinatura": sha256_canonico(info)[:16]})
    return arestas, oficiais


def _contexto(state, ferramentas: dict, entregas: dict, oficiais: dict) -> dict:
    brief = state.brief_pre_arquitetura
    plano = state.plan
    anuncio = plano.contexto_de_anuncio if plano is not None else None
    paginas = []
    for p in plano.pages:
        j = p.jornada
        paginas.append({
            "pagina": p.page_number, "papel": effective_role(p).value, "h1": p.h1_title,
            "pergunta": j.pergunta_principal if j else "",
            "entrega": entregas.get(p.page_number) or (j.resposta_imediata if j else ""),
            "proxima_duvida": (j.proxima_duvida if j else "") or "",
            "ferramentas": _ferramentas_prontas(ferramentas.get(p.page_number) or {}),
            "fatos": [f["afirmacao"][:180] for f in _fatos(state, p.page_number)[:6]]})
    return {
        "chegada": {"intencao": brief.intencao_principal if brief else "",
                    "perguntas": [d.jornada.pergunta_principal
                                  for d in (brief.duvidas if brief else [])][:8],
                    "anuncio": list(anuncio.titulos)[:5]
                    if anuncio is not None and anuncio.estado == "presente" else []},
        "paginas": paginas,
        "oficiais": [{"id": f"o{i}", "url": url, **info}
                     for i, (url, info) in enumerate(oficiais.items(), start=1)],
    }


def _conferir(rotulo: Any, aresta: dict, contexto_do_destino: str) -> tuple[str, str]:
    """(rótulo limpo, motivo da recusa). Só o que é objetivo."""
    if not isinstance(rotulo, str) or not rotulo.strip():
        return "", "rótulo vazio"
    limpo = re.sub(r"\s+", " ", rotulo).strip().removesuffix(">>>").strip()
    if _PROIBIDO_RE.search(limpo):
        return "", "rótulo com URL, tag, colchete ou aspas"
    final = limpo + (SUFIXO_DE_SAIDA if aresta["tipo"] == "oficial" else "")
    if len(final) > MAX_ROTULO:
        return "", f"rótulo com {len(final)} caracteres (máx. {MAX_ROTULO})"
    digitos = {float(n.replace(".", "").replace(",", ".")) for n in _NUMERO_RE.findall(limpo)}
    if not digitos <= numeros_do_texto(contexto_do_destino):
        return "", "número que não está nos fatos nem na entrega do destino"
    return final, ""


def definir_ctas_do_funil(state, deps, ferramentas: dict, entregas: dict) -> set:
    """Aplica nas rotas os rótulos do sniper; devolve {(origem, slug)} rotulados."""
    cfg = deps.settings.steps.get("ctas") or deps.settings.steps.get("write_page")
    if state.plan is None or cfg is None:
        return set()
    arestas, oficiais = _arestas(state, deps, ferramentas, entregas)
    if not arestas:
        return set()
    anteriores = {(b["origem"], _chave(b["destino"])): b
                  for b in (state.ctas_do_funil or {}).get("botoes") or []
                  if b.get("rotulo")}
    reusados, pedir = [], []
    for a in arestas:
        antigo = anteriores.get((a["origem"], _chave(a["destino"])))
        if antigo is not None and antigo.get("assinatura") == a["assinatura"]:
            reusados.append({**a, "rotulo": antigo["rotulo"],
                             "justificativa": antigo.get("justificativa", ""),
                             "origem_do_rotulo": "reaproveitado"})
        else:
            pedir.append(a)
    for i, a in enumerate(pedir, start=1):
        a["id"] = f"b{i}"
        if a["tipo"] == "oficial":
            a["oficial"] = next(f"o{k}" for k, url in enumerate(oficiais, start=1)
                                if url == _chave(a["destino"]))
    contexto = _contexto(state, ferramentas, entregas, oficiais)
    recusas: dict[str, str] = {}
    novos: list[dict] = []
    res = StepResult(step="ctas_do_funil", status=StepStatus.SKIPPED, attempts=0)
    if pedir:
        from funnelforge.pipeline import steps as st
        from funnelforge.prompts import render
        prompt = render("ctas_do_funil", botoes=pedir, **contexto)
        try:
            texto, res = deps.runner.run_llm_step(
                "ctas_do_funil", cfg.model_copy(update={"validators": []}),
                [{"role": "user", "content": prompt}], ctx={}, run_id=state.run_id)
            resposta = {str(b.get("id")): b for b in st._tolerant_json(texto).get("botoes") or []
                        if isinstance(b, dict)}
        except Exception as exc:  # noqa: BLE001 - sem rótulo novo, fica o do plano
            res = getattr(exc, "step_result", StepResult(step="ctas_do_funil",
                                                         status=StepStatus.FAILED))
            resposta = {}
            recusas["*"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        paginas = {p["pagina"]: p for p in contexto["paginas"]}
        oficiais_por_id = {o["id"]: o for o in contexto["oficiais"]}
        for a in pedir:
            b = resposta.get(a["id"])
            if b is None:
                recusas.setdefault(a["id"], "sem resposta para este botão")
                continue
            if a["tipo"] == "funnel":
                d = paginas.get(a["destino_pagina"]) or {}
                base = " ".join([d.get("entrega", ""), d.get("pergunta", ""), *d.get("fatos", []),
                                 *(f["nome"] for f in d.get("ferramentas", []))])
            else:
                o = oficiais_por_id.get(a["oficial"]) or {}
                base = " ".join([o.get("titulo", ""), *o.get("fatos", [])])
            rotulo, motivo = _conferir(b.get("rotulo"), a, base)
            if motivo:
                recusas[a["id"]] = motivo
                continue
            novos.append({**a, "rotulo": rotulo,
                          "justificativa": str(b.get("justificativa") or "")[:300],
                          "origem_do_rotulo": "sniper"})
        # Destinos diferentes da mesma página com o mesmo texto: o leitor não
        # distingue os botões. Ficam os do plano nos dois.
        por_origem: dict[tuple[int, str], list[dict]] = {}
        for b in novos + reusados:
            base = b["rotulo"].removesuffix(">>>").strip().casefold()
            por_origem.setdefault((b["origem"], base), []).append(b)
        repetidos = {id(b) for grupo in por_origem.values() if len(grupo) > 1 for b in grupo}
        for b in [b for b in novos if id(b) in repetidos]:
            recusas[b["id"]] = "mesmo rótulo para destinos diferentes da mesma página"
        novos = [b for b in novos if id(b) not in repetidos]
    aplicados = novos + reusados
    _aplicar(state, aplicados)
    state.ctas_do_funil = {"versao": VERSAO, "botoes": aplicados, "recusas": recusas,
                           "pedidos": len(pedir), "reaproveitados": len(reusados),
                           "modelo": res.model_used or "", "auth_mode": res.auth_mode or ""}
    res.issues = list(res.issues) + [Issue(code="ctas_do_funil", message=json.dumps({
        "arestas": len(arestas), "pedidas": len(pedir), "aplicadas": len(novos),
        "reaproveitadas": len(reusados), "recusas": recusas}, ensure_ascii=False))]
    state.step_status["ctas_do_funil"] = res
    pasta = deps.runner.runs_dir / state.run_id
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "ctas_do_funil.json").write_text(
        json.dumps(state.ctas_do_funil, ensure_ascii=False, indent=2), encoding="utf-8")
    return {(b["origem"], b["destino"]) for b in aplicados if b["tipo"] == "funnel"}


def _aplicar(state, botoes: list[dict]) -> None:
    """O rótulo vai para a rota e para o link editorial da mesma aresta. A saída
    oficial é religada no `_write_ctx`, que lê o rótulo daqui."""
    por_numero = {p.page_number: p for p in state.plan.pages}
    for b in botoes:
        if b["tipo"] != "funnel":
            continue
        p = por_numero[b["origem"]]
        for r in p.routes:
            if r.kind == "funnel" and r.target == b["destino"]:
                r.anchor = b["rotulo"]
        for link in (p.editorial.links if p.editorial else []):
            if link.target == b["destino"]:
                link.cta = b["rotulo"]


def rotulo_da_saida_oficial(state, page, url: str) -> str:
    """O rótulo que o sniper deu à saída oficial desta página, se houver."""
    for b in (getattr(state, "ctas_do_funil", None) or {}).get("botoes") or []:
        if (b.get("tipo") == "oficial" and b.get("origem") == page.page_number
                and _chave(b.get("destino")) == _chave(url)):
            return b.get("rotulo") or ""
    return ""

