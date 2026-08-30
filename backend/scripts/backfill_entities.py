"""
Backfill — migra os cards LEGADOS (pautador_opportunities, keyword-first) para a
camada ENTITY-FIRST, SEM apagar os dados antigos.

Para cada oportunidade antiga:
  1. extrai a entidade provável do título (normalize_entity_slug + siglas);
  2. cria/reaproveita pautador_entities (dedup country_code + slug + aliases);
  3. cria pautador_entity_opportunities (card) reaproveitando tier/score/levels;
  4. move o título antigo para pautador_entity_seed_queries.query.

Uso:
  cd backend && python scripts/backfill_entities.py            # DRY-RUN (preview)
  cd backend && python scripts/backfill_entities.py --apply    # grava de fato

Idempotente: re-rodar não duplica (dedup por country+slug e por query). Não
imprime secrets. Requer Supabase (service role) configurado em .env.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.mining.geo import resolve_geo
from app.config import get_settings
from app.entities.normalize import (
    canonical_acronym,
    entity_keys,
    find_matching_entity,
    normalize_entity_slug,
    suggest_official_source,
)
from app.services.supabase_service import SupabaseService

APPLY = "--apply" in sys.argv


def _canonical_name(main_keyword: str) -> str:
    acro = canonical_acronym(main_keyword)
    if acro:
        return acro
    # Title-case the cleaned slug words
    slug = normalize_entity_slug(main_keyword)
    return " ".join(w.capitalize() for w in slug.split("-")) or (main_keyword or "Entidade")


def _country_code(opp: dict) -> str:
    code = opp.get("country_code")
    if code:
        return code.upper()
    geo = resolve_geo(opp.get("country"))
    return (geo or {}).get("country_code") or "XX"


async def main() -> int:
    settings = get_settings()
    supa = SupabaseService(settings)
    if not supa.enabled:
        print("[STOP] Supabase não configurado — backfill exige service role em .env.")
        return 2

    print(f"=== Backfill entity-first ({'APPLY' if APPLY else 'DRY-RUN'}) ===")
    runs = await supa.list_runs(limit=200)
    total_opps = created_ent = reused_ent = created_cards = added_queries = 0
    # cache existing entities per country to dedup across the whole backfill
    ent_cache: dict[str, list] = {}

    for run in runs:
        opps = await supa.list_opportunities(run["id"])
        for opp in opps:
            total_opps += 1
            code = _country_code(opp)
            main = opp.get("main_keyword") or opp.get("keyword") or ""
            old_title = opp.get("keyword") or main
            canonical = _canonical_name(main)
            slug = normalize_entity_slug(canonical) or normalize_entity_slug(main) or "entidade"
            source = suggest_official_source(f"{main} {old_title}")
            aliases = list({a for a in [opp.get("main_keyword"), opp.get("keyword_pt_translation")] if a})

            if code not in ent_cache:
                ent_cache[code] = await supa.list_entities(code) if APPLY else []
            cand = entity_keys(canonical, None, aliases)
            cand.add(slug)
            match = find_matching_entity(cand, ent_cache[code])

            print(f"  [{code}] {old_title[:48]!r:50} -> entidade={canonical!r} slug={slug!r} src={source} {'(merge)' if match else '(novo)'}")

            if not APPLY:
                if match:
                    reused_ent += 1
                else:
                    created_ent += 1
                added_queries += 1
                continue

            try:
                if match:
                    reused_ent += 1
                    entity_id = match["id"]
                    opp_row = await supa.get_opportunity_by_entity(entity_id)
                    opp_id = opp_row.get("id") if opp_row else None
                else:
                    created_ent += 1
                    ent = await supa.insert_entity({
                        "run_id": run["id"], "country_code": code, "country": opp.get("country"),
                        "canonical_name": canonical, "full_name": opp.get("main_keyword"),
                        "slug": slug, "official_source": source, "aliases": aliases,
                        "description": opp.get("reasoning"), "language": opp.get("native_language"),
                        "source": "backfill",
                    })
                    entity_id = ent.get("id") if ent else None
                    ent_cache[code].append(ent or {})
                    card = await supa.insert_entity_opportunity({
                        "entity_id": entity_id, "run_id": run["id"], "country_code": code,
                        "status": "discovered", "kanban_stage": "discovered",
                        "gold_tier": opp.get("tier"), "strategic_stage": opp.get("category"),
                        "score": opp.get("arbitrage_score"), "roi_signal": opp.get("estimated_roi_signal"),
                        "cpc_min": opp.get("cpc_min"), "cpc_max": opp.get("cpc_max"), "cpc_currency": opp.get("currency"),
                        "volume_level": opp.get("volume_estimate"), "rpm_level": opp.get("rpm_potential"),
                        "competition_level": opp.get("competition_estimate"), "confidence_level": opp.get("confidence"),
                        "temporal_window": opp.get("timing"), "concrete_pain": opp.get("pain_point"),
                        "gold_reason": opp.get("reasoning"), "notes": {"backfilled_from_opportunity_id": opp.get("id")},
                    })
                    opp_id = card.get("id") if card else None
                    created_cards += 1

                # move old title -> seed query (dedup)
                existing_q = await supa.existing_seed_query_set(entity_id)
                if old_title and old_title.lower().strip() not in existing_q:
                    await supa.insert_seed_queries([{
                        "entity_id": entity_id, "opportunity_id": opp_id, "query": old_title,
                        "query_type": "seed", "intent": opp.get("intent"), "source": "backfill",
                    }])
                    added_queries += 1
            except Exception as exc:  # noqa: BLE001
                print(f"    ! erro: {exc}")

    print("\n=== Resumo ===")
    print(f"opps legados analisados: {total_opps}")
    print(f"entidades novas: {created_ent} | reaproveitadas: {reused_ent} | cards criados: {created_cards} | seed queries: {added_queries}")
    if not APPLY:
        print("\n(DRY-RUN — nada gravado. Rode com --apply para persistir. Dados antigos NÃO são apagados.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
