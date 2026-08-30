"""
Unit tests for the faithful n8n KW-mining + funnel ports.

Run:  cd backend && pytest -q
      (or python -m pytest tests/test_mining_pipeline.py)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

# allow `import app...` when run from the backend dir or repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.funnel_pro.page_factory import architect_pages_to_funnel_pages, page_factory
from app.agents.mining.classifier import gold_miner_classify
from app.agents.mining.funnel_factory import funnel_factory
from app.agents.mining.geo import GeoLanguageMapper
from app.agents.mining.gold_extractor import extract_gold, normalize_seed
from app.agents.mining.merger import final_classifier, mega_merge
from app.agents.mining.mocks import mock_keyword_ideas
from app.agents.mining.seed_queue import SeedQueueError, fallback_seeds, parse_seed_optimizer_output
from app.llm.base import extract_json
from app.services.dataforseo import extract_autocomplete, extract_related


# --- Seed Optimizer parsing ---------------------------------------------------
def test_seed_queue_parse_ranks_and_dedupes():
    ai = {
        "seed_keywords": [
            {"keyword": "ICETEX", "angle": "institucional", "reasoning": "head"},
            {"keyword": "icetex", "angle": "dup"},  # dedup vs first (lowercased)
            {"keyword": "deuda icetex", "angle": "dor"},
            {"keyword": "alivios icetex", "angle": "alivio_popular"},
        ]
    }
    seeds = parse_seed_optimizer_output(ai)
    assert [s["seed_keyword"] for s in seeds] == ["icetex", "deuda icetex", "alivios icetex"]
    assert seeds[0]["seed_rank"] == 1


def test_seed_queue_requires_three():
    with pytest.raises(SeedQueueError):
        parse_seed_optimizer_output({"seed_keywords": [{"keyword": "a"}, {"keyword": "b"}]})


def test_fallback_seeds_keeps_original_first():
    seeds = fallback_seeds("universal credit")
    assert seeds[0]["seed_keyword"] == "universal credit"
    assert len(seeds) >= 3


# --- normalize / Gold Extractor -----------------------------------------------
def test_normalize_seed_sorts_and_strips_accents():
    assert normalize_seed("Olá   Mundo  2025") == "2025 mundo ola"
    assert normalize_seed("MÉXICO bono") == "bono mexico"


def test_gold_extractor_builds_bank_and_decides_loop():
    results = mock_keyword_ideas("bolsa familia", 2076, 1014)
    out = extract_gold(
        {
            "results": results, "loop_iteration": 0, "max_loops": 5, "min_volume_gold": 10,
            "seed_keyword": "bolsa familia", "master_bank": [], "used_seeds": [], "used_seeds_norm": [],
        }
    )
    assert len(out["master_bank"]) > 0
    assert "bolsa familia" in out["used_seeds"]
    assert out["loop"]["reason"] in {"GOLD_FOUND", "NO_MORE_GOLDS", "MAX_LOOPS_REACHED", "DUPLICATE_SEED_NORM", "API_EMPTY"}
    # micros converted to currency
    assert all(isinstance(k["cpc"], float) for k in out["master_bank"])


def test_gold_extractor_stops_at_max_loops():
    results = mock_keyword_ideas("x", 2840, 1000)
    out = extract_gold(
        {
            "results": results, "loop_iteration": 4, "max_loops": 5, "min_volume_gold": 10,
            "seed_keyword": "x", "master_bank": [], "used_seeds": [], "used_seeds_norm": [],
        }
    )
    assert out["loop"]["should_continue"] is False
    assert out["loop"]["reason"] == "MAX_LOOPS_REACHED"


# --- Mega Merge / Final Classifier --------------------------------------------
def test_mega_merge_enriched_wins_autocomplete_fills():
    enriched = {"keywords": [{"keyword": "a", "volume": 100, "source": "related_keywords_labs"}]}
    autocomplete = {"keywords": [{"keyword": "a", "volume": 0, "source": "google_autocomplete", "needs_enrichment": True},
                                 {"keyword": "b", "volume": 0, "source": "google_autocomplete", "needs_enrichment": True}]}
    control = {"build_queue": [{"keyword": "z", "volume": 5}]}
    out = mega_merge([autocomplete, enriched, control])
    kws = {k["keyword"]: k for k in out["keywords"]}
    assert kws["a"]["volume"] == 100  # enriched won over autocomplete
    assert "b" in kws
    assert out["control_state"] is control


def test_final_classifier_consolidates_runs():
    runs = [
        {"geo_target": 2076, "language_code": "pt-BR", "seed_keyword": "s1", "loop_iteration": 0,
         "master_bank": [{"keyword": "bolsa familia", "volume": 1000, "cpc": 0.1}]},
        {"seed_keyword": "s2", "loop_iteration": 0,
         "master_bank": [{"keyword": "Bolsa Familia", "volume": 2000, "cpc": 0.2}]},
    ]
    out = final_classifier(runs)
    # both map to same normalized key -> highest volume wins
    assert len(out["build_queue"]) == 1
    assert out["build_queue"][0]["volume"] == 2000
    assert out["geo_target"] == 2076  # base_config picked from the run that has it


# --- Gold Miner classifier ----------------------------------------------------
def test_gold_miner_time_warp_and_classification():
    today = datetime(2026, 6, 25, tzinfo=timezone.utc)
    kws = [
        {"keyword": "inscricao enem 2025", "volume": 30000, "cpc": 0.5, "competition": "MEDIUM"},
        {"keyword": "divida 2025 atrasada", "volume": 8000, "cpc": 0.3, "competition": "LOW"},
        {"keyword": "como consultar bolsa familia", "volume": 500, "cpc": 0.05, "competition": "LOW"},
    ]
    out = gold_miner_classify(kws, today=today)
    ads = {k["keyword"]: k for k in out["production_ads_queue"]}
    # warped to 2026, titan
    assert "inscricao enem 2026" in ads
    assert "VOLUME_TITAN" in ads["inscricao enem 2026"]["tags"]
    assert "[2025→2026]" in ads["inscricao enem 2026"]["reason"]
    # debt keyword NOT warped (historical reference) -> stays 2025
    assert any("divida 2025 atrasada" == k["keyword"] for k in out["production_ads_queue"])
    # question keyword present in content queue
    assert any("como consultar" in k["keyword"] for k in out["content_seo_queue"])


def test_gold_miner_caps_queues():
    big = [{"keyword": f"kw {i}", "volume": 25000 + i, "cpc": 0.1, "competition": "LOW"} for i in range(300)]
    out = gold_miner_classify(big, today=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert len(out["production_ads_queue"]) <= 200


# --- Funnel Factory -----------------------------------------------------------
def test_funnel_factory_date_normalization():
    today = datetime(2026, 6, 25, tzinfo=timezone.utc)
    ai = {
        "funis_sugeridos": [
            {
                "rank": 1, "nome_funil": "PIS", "keyword_ancora": "pis 2025", "volume_ancora": 100000,
                "metricas": {"volume_agregado": 100000, "cpc_medio": 0.1, "qtd_keywords": 3, "qtd_sub_intencoes": 1},
                "justificativa": "x", "tags": ["VOLUME_TITAN"],
                "sub_intencoes": [
                    {"tipo": "TEMPORAL", "descricao": "datas", "volume_sub": 100000, "keywords": [
                        {"keyword": "calendario pis 2025", "volume": 50000, "cpc": 0.1},
                        {"keyword": "pis janeiro 2025", "volume": 30000, "cpc": 0.1},  # janeiro<junho -> removed
                        {"keyword": "pis valor", "volume": 20000, "cpc": 0.1},
                    ]},
                ],
            }
        ]
    }
    out = funnel_factory(ai, today=today)
    assert len(out) == 1
    item = out[0]
    kws = item["keywords_campanha"]["keywords_array"]
    texts = [k["keyword"] for k in kws]
    assert "calendario pis 2026" in texts  # 2025 -> 2026
    assert all("janeiro" not in t for t in texts)  # past month dropped
    assert item["keywords_removidas"]["total_removidas"] == 1


# --- Page Factory -------------------------------------------------------------
def test_page_factory_writing_jobs_and_links():
    architect = {
        "funnel_strategy": {"avatar_summary": "avatar", "tone_voice": "tom", "total_pages": 2},
        "pages": [
            {"page_number": 1, "page_type": "LANDING PAGE", "h1_title": "P1", "slug": "p1",
             "emotional_objective": "obj1", "main_content_structure": ["H2: a", "H2: b"],
             "hook_to_next_page": "Avançar", "next_page_slug": "p2", "target_keywords": ["kw1"]},
            {"page_number": 2, "page_type": "HUB", "h1_title": "P2", "slug": "p2",
             "emotional_objective": "obj2", "main_content_structure": ["H2: c"],
             "hook_to_next_page": "Fim", "target_keywords": ["kw2"]},
        ],
    }
    out = page_factory(architect)
    assert len(out["writingJobs"]) == 2
    assert out["writingJobs"][0]["writer_briefing"]["cta_link"] == "/p2"
    assert out["writingJobs"][1]["writer_briefing"]["cta_link"] == "/inicio"  # last page, no slug
    pages = architect_pages_to_funnel_pages(architect)
    assert pages[0]["stage"] == "tofu"
    assert pages[1]["stage"] == "mofu"


def test_page_factory_empty_pages():
    out = page_factory({"pages": [], "funnel_strategy": {}})
    assert out["writingJobs"] == []


# --- robust JSON parser -------------------------------------------------------
def test_extract_json_handles_fences_and_noise():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('prefixo {"b": 2} sufixo') == {"b": 2}
    assert extract_json({"c": 3}) == {"c": 3}


# --- geo + dataforseo extractors ----------------------------------------------
def test_geo_mapper_resolves_code_and_name():
    gb = GeoLanguageMapper.map("Reino Unido", "GB")
    assert gb["Criteria_ID"] == 2826 and gb["language_constant"] == 1000 and gb["resolved"]
    br = GeoLanguageMapper.map("brasil", None)  # accent/case-insensitive
    assert br["country_code"] == "BR" and br["Criteria_ID"] == 2076


def test_dataforseo_extractors():
    ac_raw = {"tasks": [{"result": [{"items": [{"type": "x", "keyword": "como pagar"}]}]}]}
    rel_raw = {"tasks": [{"result": [{"items": [
        {"keyword_data": {"keyword": "pagar boleto", "keyword_info": {"search_volume": 500, "cpc": 0.2}}}
    ]}]}]}
    ac = extract_autocomplete(ac_raw)
    rel = extract_related(rel_raw)
    assert ac[0]["keyword"] == "como pagar" and ac[0]["needs_enrichment"] is True
    assert rel[0]["volume"] == 500 and rel[0]["source"] == "related_keywords_labs"
