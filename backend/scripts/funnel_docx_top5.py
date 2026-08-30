"""
ETAPA 2 — Funil + DOCX dos 5 top candidatos (a partir dos dados MINERADOS salvos).

Roda o MESMO motor da API (EntityFunnelOrchestrator -> FunnelProOrchestrator, o
arquiteto do FUNNEL.json) in-process, alimentado com as dores + seed_queries que o
n8n minerou (harvest local), e gera o DOCX no modelo VOLC (build_funnel_briefing).
Salva os 5 .docx em ~/Downloads.

In-process (não via HTTP) porque as linhas já foram apagadas do Supabase na Etapa 1
— o endpoint HTTP daria 404. É o mesmo código/engine que a API usa.

Uso: cd backend && python scripts/funnel_docx_top5.py
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.base import AgentContext
from app.config import get_settings
from app.docx import briefing_filename, build_funnel_briefing
from app.entities.orchestrator import EntityFunnelOrchestrator
from app.llm import get_engine, get_grounding

HARVEST_DIR = "/private/tmp/claude-502/-Users-mac-Desktop-SISTEMAS-WEBGO-Sistema-Webgo/3b8e7df7-072e-4638-9828-1b2be5f353c1/scratchpad/mining_smoke"
DOWNLOADS = "/Users/mac/Downloads"
MONTH, YEAR = 7, 2026


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _ctx() -> AgentContext:
    s = get_settings()
    return AgentContext(settings=s, engine=get_engine(s), grounding=get_grounding(s))


def _entity_from_harvest(r: dict) -> dict:
    return {
        "id": None,
        "run_id": None,
        "country": "Brasil",
        "country_code": "BR",
        "language": "pt-BR",
        "native_language": "pt-BR",
        "canonical_name": r["name"],
        "full_name": r.get("full_name"),
        "official_source": r.get("official_source"),
        "description": r.get("description"),
        "aliases": [],
    }


def _card_for_docx(r: dict, entity: dict) -> dict:
    return {
        "country_code": "BR",
        "insights": None,
        "entity": {
            "canonical_name": entity["canonical_name"],
            "full_name": entity.get("full_name"),
            "country": "Brasil",
            "country_code": "BR",
            "entity_category": r.get("vertical"),
            "language": "pt-BR",
        },
    }


async def build_one(ctx: AgentContext, path: str) -> dict:
    r = json.load(open(path, encoding="utf-8"))
    name = r["name"]
    entity = _entity_from_harvest(r)
    pains = r.get("card_pains") or []
    seed_queries = r.get("card_seed_queries") or []
    log(f"→ {name}: arquitetando funil ({len(pains)} dores, {len(seed_queries)} queries mineradas)...")

    built = await EntityFunnelOrchestrator(ctx).run(entity, pains, seed_queries)
    pages = built.get("pages") or []
    wjobs = built.get("writing_jobs") or []

    card = _card_for_docx(r, entity)
    docx_bytes = build_funnel_briefing(card, built, month=MONTH, year=YEAR)
    fname = briefing_filename(card, YEAR)
    out = os.path.join(DOWNLOADS, fname)
    with open(out, "wb") as fh:
        fh.write(docx_bytes)

    engine = built.get("engine")
    log(f"  ✓ {name}: {len(pages)} páginas · {len(wjobs)} briefings · engine={engine} → {fname} ({len(docx_bytes)//1024} KB)")
    return {"name": name, "file": out, "pages": len(pages), "writing_jobs": len(wjobs),
            "engine": engine, "funnel_name": (built.get("funnel_hypotheses") or [{}])[-1].get("title"),
            "warnings": built.get("warnings") or []}


async def main() -> None:
    files = sorted(glob.glob(os.path.join(HARVEST_DIR, "*.json")))
    if not files:
        log(f"ERRO: nenhum harvest em {HARVEST_DIR}"); sys.exit(1)
    log(f"{len(files)} entidades mineradas encontradas. Gerando funis + DOCX em {DOWNLOADS}\n")
    ctx = _ctx()

    results = []
    for f in files:
        try:
            results.append(await build_one(ctx, f))
        except Exception as exc:  # noqa: BLE001
            log(f"  ✗ FALHA em {os.path.basename(f)}: {type(exc).__name__}: {exc}")
            results.append({"name": os.path.basename(f), "error": str(exc)})

    print("\n=== RESULTADO ===")
    ok = [r for r in results if not r.get("error")]
    for r in ok:
        print(f'  • {r["name"]}: {r["pages"]}p · funil="{r.get("funnel_name")}" · {os.path.basename(r["file"])}')
    fail = [r for r in results if r.get("error")]
    for r in fail:
        print(f'  ✗ {r["name"]}: {r["error"]}')
    print(f"\n{len(ok)}/{len(results)} DOCX gerados em {DOWNLOADS}")


if __name__ == "__main__":
    asyncio.run(main())
