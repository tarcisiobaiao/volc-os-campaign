"""
SMOKE TEST — Mineração (n8n) dos 5 top candidatos creditoup/BR.

Fluxo (exatamente como pedido):
  1. persiste as 5 entidades no Supabase (slug '-smk' p/ NUNCA colidir com o board real);
  2. dispara o webhook n8n de KW mining p/ cada uma (mesmo payload do produto);
  3. faz poll de pautador_keyword_clusters até o n8n gravar o cluster (timeout);
  4. HARVEST: salva card + cluster minerado em arquivo local JSON;
  5. APAGA as 5 do Supabase (cascade) -> board fica limpo.

Nada de fallback aqui: se o n8n não gravar no timeout, registra cluster_found=false
(o passo de funil decide o fallback). Idempotente-ish: usa slug único de smoke test.

Uso: cd backend && python scripts/smoke_mine_top5.py [--timeout 360]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from app.config import get_settings
from app.data.countries import resolve_country
from app.entities.normalize import normalize_entity_slug
from app.services.supabase_service import SupabaseService

TOP5_PATH = "/private/tmp/claude-502/-Users-mac-Desktop-SISTEMAS-WEBGO-Sistema-Webgo/3b8e7df7-072e-4638-9828-1b2be5f353c1/scratchpad/top5_entities.json"
HARVEST_DIR = "/private/tmp/claude-502/-Users-mac-Desktop-SISTEMAS-WEBGO-Sistema-Webgo/3b8e7df7-072e-4638-9828-1b2be5f353c1/scratchpad/mining_smoke"
COUNTRY = "Brasil"
CODE = "BR"
LANG = "pt-BR"

_OPP_COLS_MAP = ["gold_tier", "score", "estimated_volume", "ecpm_band", "temporal_window",
                 "concrete_pain", "gold_reason"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _entity_type(vertical: str) -> str:
    return "product" if vertical in ("credito", "financas", "seguros") else "topic"


async def dispatch_n8n(settings, supa, entity: dict, opp_id: int) -> tuple[bool, str]:
    geo = resolve_country(entity.get("country"), code=entity.get("country_code")) or {}
    payload = {
        "entity_id": entity.get("id"),
        "opportunity_id": opp_id,
        "run_id": entity.get("run_id"),
        "country": entity.get("country"),
        "country_code": geo.get("country_code") or entity.get("country_code"),
        "nicho": entity.get("canonical_name") or entity.get("full_name"),
        "objective": entity.get("description") or f"Mineração de KW da entidade {entity.get('canonical_name')}",
        "geo_target": geo.get("google_ads_geo_target"),
        "language_code": geo.get("language_code"),
        "language_short": geo.get("language_short"),
        "language_constant": geo.get("language_constant"),
    }
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.post(settings.pautador_n8n_kw_webhook_url, json=payload)
            resp.raise_for_status()
        return True, f"HTTP {resp.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


async def main() -> None:
    timeout_s = 360
    if "--timeout" in sys.argv:
        timeout_s = int(sys.argv[sys.argv.index("--timeout") + 1])

    os.makedirs(HARVEST_DIR, exist_ok=True)
    settings = get_settings()
    supa = SupabaseService(settings)
    if not supa.enabled:
        log("ERRO: Supabase não habilitado."); sys.exit(1)

    top5 = json.load(open(TOP5_PATH, encoding="utf-8"))
    log(f"Carregadas {len(top5)} entidades. n8n webhook set={bool(settings.pautador_n8n_kw_webhook_url)}")

    created = []  # {rank, name, entity_id, opp_id, slug, seed_queries, meta, dispatched, dispatch_msg}
    try:
        await _run(settings, supa, top5, created, timeout_s)
    finally:
        # BLINDAGEM: garante que nenhuma linha de smoke test fique em produção,
        # mesmo se algo quebrar no meio (harvest já foi salvo em arquivo antes).
        for c in created:
            try:
                if await supa.get_entity(c["entity_id"]):
                    await supa.delete_entity(c["entity_id"])
                    log(f"  🧹 (finally) removido entity_id={c['entity_id']}")
            except Exception as exc:  # noqa: BLE001
                log(f"  ⚠ (finally) falha ao remover entity_id={c.get('entity_id')}: {exc}")


async def _run(settings, supa, top5, created, timeout_s) -> None:
    # 1) PERSISTE + 2) DISPARA n8n
    for x in top5:
        name = x["canonical_name"]
        slug = (normalize_entity_slug(name) or "entidade") + "-smk"
        vertical = x.get("vertical")
        desc = f'{x.get("full_name") or name}. {x.get("gold_reason") or ""}'.strip()[:500]
        ent_row = {
            "run_id": None, "country_code": CODE, "country": COUNTRY,
            "canonical_name": name, "full_name": x.get("full_name"), "slug": slug,
            "entity_type": _entity_type(vertical), "entity_category": None, "vertical": vertical,
            "official_source": x.get("official_source") or None, "related_systems": [], "aliases": [],
            "description": desc, "language": LANG, "status": "discovered", "source": "manual",
        }
        # remove se já existir um smk anterior (idempotência do smoke test)
        prev = await supa.get_entity_by_slug(CODE, slug)
        if prev:
            await supa.delete_entity(prev["id"]); log(f"  (limpou smk anterior: {name})")
        ent = await supa.insert_entity(ent_row)
        entity_id = ent["id"]
        opp_row = {
            "entity_id": entity_id, "run_id": None, "country_code": CODE,
            "status": "discovered", "kanban_stage": "discovered", "notes": {"smoketest": True},
            "gold_tier": x.get("gold_tier"), "score": x.get("score"),
            "estimated_volume": x.get("estimated_volume"), "ecpm_band": x.get("ecpm_band"),
            "temporal_window": x.get("temporal_window"), "concrete_pain": x.get("concrete_pain"),
            "gold_reason": x.get("gold_reason"),
        }
        opp = await supa.insert_entity_opportunity(opp_row)
        opp_id = opp["id"]
        # dores/queries que já temos (seed p/ a mineração e p/ o funil)
        await supa.insert_pains([{
            "entity_id": entity_id, "opportunity_id": opp_id,
            "pain_name": f"Dor principal — {name}", "pain_description": x.get("concrete_pain"),
            "user_goal": None, "intent": "informational", "severity": "high",
        }])
        await supa.insert_seed_queries([
            {"entity_id": entity_id, "opportunity_id": opp_id, "query": q,
             "query_type": "seed", "intent": "informational", "score": None, "source": "discovery"}
            for q in (x.get("seed_queries") or [])
        ])

        ent_full = await supa.get_entity(entity_id)
        ok, msg = await dispatch_n8n(settings, supa, ent_full, opp_id)
        if ok:
            await supa.update_entity_opportunity(opp_id, {"status": "mining", "kanban_stage": "mining"})
            await supa.update_entity(entity_id, {"status": "mining"})
        created.append({
            "rank": x["rank"], "name": name, "slug": slug, "vertical": vertical,
            "entity_id": entity_id, "opp_id": opp_id,
            "seed_queries": x.get("seed_queries") or [], "meta": {k: x.get(k) for k in _OPP_COLS_MAP},
            "full_name": x.get("full_name"), "official_source": x.get("official_source"),
            "description": desc, "dispatched": ok, "dispatch_msg": msg,
        })
        log(f"  #{x['rank']} {name}: entity_id={entity_id} opp_id={opp_id} | n8n dispatch={'OK' if ok else 'FALHOU'} ({msg})")

    # 3) POLL clusters (baseline = 0, entidades novas)
    log(f"\nAguardando o n8n gravar clusters (timeout {timeout_s}s)...")
    pending = {c["opp_id"] for c in created if c["dispatched"]}
    clusters: dict[int, dict] = {}
    start = time.monotonic()
    interval = 15
    while pending and (time.monotonic() - start) < timeout_s:
        await asyncio.sleep(interval)
        for opp_id in list(pending):
            cl = await supa.get_latest_cluster(opp_id)
            if cl:
                clusters[opp_id] = cl
                pending.discard(opp_id)
                nk = len(cl.get("keywords") or [])
                log(f"  ✓ cluster gravado p/ opp_id={opp_id} ({nk} keywords)")
        if pending:
            log(f"  ... {len(pending)} pendente(s), {int(time.monotonic()-start)}s decorridos")

    # 4) HARVEST -> arquivo local
    log("\nHarvest -> arquivos locais...")
    harvested = []
    cards = await supa.list_entity_cards(CODE)
    cards_by_opp = {c.get("id"): c for c in cards}
    for c in created:
        opp_id = c["opp_id"]
        card = cards_by_opp.get(opp_id) or {}
        cluster = clusters.get(opp_id)
        rec = {
            **c,
            "cluster_found": bool(cluster),
            "cluster": cluster,
            "card_pains": card.get("pains") or [],
            "card_seed_queries": card.get("seed_queries") or [],
            "harvested_at": datetime.now(timezone.utc).isoformat(),
        }
        fp = os.path.join(HARVEST_DIR, f'{c["rank"]:02d}_{c["slug"]}.json')
        json.dump(rec, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        harvested.append(rec)
        log(f"  #{c['rank']} {c['name']}: cluster_found={rec['cluster_found']} -> {os.path.basename(fp)}")

    # 5) DELETE do Supabase (cascade)
    log("\nApagando as 5 do Supabase (cascade)...")
    for c in created:
        await supa.delete_entity(c["entity_id"])
        log(f"  🗑  apagado entity_id={c['entity_id']} ({c['name']})")
    # verificação
    remaining = [c for c in created if await supa.get_entity(c["entity_id"])]
    log(f"\nVerificação: {len(remaining)} entidade(s) de smoke test remanescente(s) (esperado 0).")

    summary = {
        "dispatched": sum(1 for c in created if c["dispatched"]),
        "clusters_found": sum(1 for h in harvested if h["cluster_found"]),
        "total": len(created),
        "harvest_dir": HARVEST_DIR,
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
