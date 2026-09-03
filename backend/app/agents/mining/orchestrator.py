"""
Mining Orchestrator (Fase 2) — wires the faithful n8n peneirador-kw pipeline:

  GeoLanguageMapper -> SeedOptimizer -> KeywordPlanner loop (Google Ads) ->
  GoldExtractor -> FinalClassifier -> DataForSEO (autocomplete + related) ->
  MegaMerger -> GoldMiner classifier -> FunnelProspector -> FunnelFactory

External data sources (Google Ads / DataForSEO) are used when configured; when
absent the deterministic mocks run so the whole pipeline works end-to-end.
LLM steps (SeedOptimizer, FunnelProspector) use Gemini (kw model) when a key
exists, else a deterministic fallback. Everything is logged to ctx.logs and the
data source for each step is reported in `services_used`.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agents.base import AgentContext, BaseAgent
from app.agents.mining.classifier import gold_miner_classify
from app.agents.mining.funnel_factory import funnel_factory
from app.agents.mining.paid_eligibility import Sinal
from app.agents.mining.geo import GeoLanguageMapper
from app.agents.mining.gold_extractor import extract_gold
from app.agents.mining.merger import final_classifier, mega_merge
from app.agents.mining.mocks import mock_autocomplete, mock_keyword_ideas, mock_related
from app.agents.mining.seed_queue import (
    SeedQueueError,
    fallback_seeds,
    parse_seed_optimizer_output,
)
from app.n8n_prompts import (
    FUNNEL_PROSPECTOR_SYSTEM_MESSAGE,
    SEED_OPTIMIZER_SYSTEM_MESSAGE,
    build_funnel_prospector_user,
    build_seed_optimizer_user,
)
from app.services.dataforseo import (
    DataForSeoClient,
    extract_autocomplete,
    extract_related,
)
from app.services.google_ads import GoogleAdsKeywordPlannerClient

# country -> ad-account currency (best-effort, for cluster display)
_CURRENCY_BY_CODE = {
    "GB": "GBP", "US": "USD", "PT": "EUR", "DE": "EUR", "ES": "EUR",
    "BR": "BRL", "GT": "GTQ", "CO": "COP", "MX": "MXN", "AR": "ARS",
    "PE": "PEN", "CL": "CLP", "EC": "USD", "BO": "BOB", "PY": "PYG",
    "UY": "UYU", "CA": "CAD",
}

_VOL_BUCKETS = [(1000, "low"), (10000, "medium"), (50000, "high")]


def _vol_to_qual(vol: int) -> str:
    for threshold, label in _VOL_BUCKETS:
        if vol < threshold:
            return label
    return "very_high"


def _comp_to_qual(comp: str) -> Optional[str]:
    c = (comp or "").upper()
    if c == "LOW":
        return "low"
    if c == "MEDIUM":
        return "medium"
    if c == "HIGH":
        return "high"
    return None


def _volume_comparavel(k: Optional[Dict[str, Any]]) -> Optional[float]:
    """O volume pela MESMA régua de `Sinal` — `None` quando não há número.

    O desempate da união lia `(k.get("volume") or 0)`, então uma keyword sem
    volume medido valia 0 e perdia para qualquer outra — inclusive quando a
    outra também não tinha volume, e inclusive por motivo errado.
    """
    sinal = Sinal.de_bruto(k or {}, "volume", fonte="uniao")
    return sinal.valor if sinal.tem_numero else None



class MiningOrchestrator(BaseAgent):
    name = "MiningOrchestrator"
    phase = "mining"

    def __init__(self, ctx: AgentContext):
        super().__init__(ctx)
        self.settings = ctx.settings
        self.services_used: List[str] = []
        self.warnings: List[str] = []

    # ---- LLM helper ---------------------------------------------------------
    def _gemini(self):
        if not self.settings.resolved_gemini_key:
            return None
        from app.llm.gemini import GeminiClient

        return GeminiClient(self.settings, model=self.settings.pautador_kw_gemini_model)

    # ---- pipeline -----------------------------------------------------------
    async def run(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        start = self._timer()
        country = opportunity.get("country")
        country_code = opportunity.get("country_code") or opportunity.get("country_code_iso")
        nicho = opportunity.get("main_keyword") or opportunity.get("keyword") or "keyword"
        objective = (
            opportunity.get("reasoning")
            or opportunity.get("pain_point")
            or f"Arbitragem de atenção para '{nicho}'"
        )

        # 1) Geo + Language Mapper
        geo = GeoLanguageMapper.map(country, country_code)
        if not geo["resolved"]:
            self.warnings.append(
                f"País '{country}' não mapeado em geo/idioma — usando defaults (geo_target ausente)."
            )
        self.log(
            f"Geo: {geo['País_Geo']} (geo_target={geo['Criteria_ID']}, lang={geo['language_code']}).",
            step="geo",
        )
        geo_target = geo["Criteria_ID"]              # may be None (geo desconhecido)
        language_constant = geo["language_constant"]  # may be None
        language_code = geo["language_code"] or "en"
        language_short = geo["language_short"] or "en"

        kw_engine = self.settings.resolve_kw_engine()
        if geo["resolved"] and geo_target is None and kw_engine == "live":
            self.warnings.append(
                f"geo_target/idioma do Google Ads desconhecido para '{country}' — keyword mining via mock."
            )

        # 2) Seed Optimizer
        seeds = await self._seed_optimizer(
            objective=objective, nicho=nicho, pais_geo=geo["País_Geo"],
            geo_target=geo_target, language_code=language_code,
        )
        self.log(f"Seeds: {[s['seed_keyword'] for s in seeds]}.", step="seeds")

        # 3) Keyword Planner loop (per seed branch) -> runs
        runs = await self._keyword_planner(
            seeds=seeds, geo_target=geo_target, language_constant=language_constant,
            language_code=language_code, language_short=language_short,
            pais_geo=geo["País_Geo"], nicho=nicho, engine=kw_engine,
        )

        # 4) Final Classifier
        control_state = final_classifier(runs)
        build_queue = control_state.get("build_queue") or []
        self.log(f"Consolidado: {len(build_queue)} keywords únicas (Google Ads).", step="classify")

        # 5) DataForSEO autocomplete + related (on the main nicho)
        autocomplete_kws, related_kws = await self._dataforseo(
            nicho=nicho, location_code=geo_target,
            language_code=language_code, language_short=language_short, engine=kw_engine,
        )

        # 6) Mega Merge (autocomplete + related + control_state)
        merged = mega_merge(
            [
                {"keywords": autocomplete_kws},
                {"keywords": related_kws},
                control_state,
            ]
        )
        self.log(f"Mega merge: {merged['total']} keywords (DataForSEO).", step="merge")

        # Enhancement over the literal n8n wiring: also fold the Google Ads
        # build_queue into the keywords the Gold Miner classifies, so the
        # primary source (Keyword Planner) is never dropped from the final queues.
        classify_input = self._union_keywords(merged["keywords"], build_queue)

        # 7) Gold Miner classifier
        gm = gold_miner_classify(classify_input)
        self.log(
            f"Gold Miner: {gm['summary']['ads_approved']} ads / {gm['summary']['content_ideas']} conteúdo.",
            step="goldminer",
        )

        # 8) Funnel Prospector
        funis = await self._funnel_prospector(
            pais_geo=geo["País_Geo"], geo_target=geo_target, language_code=language_code,
            nicho=nicho, objective=objective, gold_miner=gm,
        )

        # 9) Funnel Factory
        factory_output = funnel_factory({"funis_sugeridos": funis.get("funis_sugeridos") or []})
        self.log(f"Funnel Factory: {len(factory_output)} funis preparados.", step="factory")

        cluster = self._build_cluster(opportunity, nicho, gm, geo)

        return {
            "cluster": cluster,
            "summary": gm["summary"],
            "production_ads_queue": gm["production_ads_queue"],
            "content_seo_queue": gm["content_seo_queue"],
            "funis_sugeridos": funis.get("funis_sugeridos") or [],
            "funnel_prospector": funis,
            "factory_output": factory_output,
            "raw_keywords": classify_input,
            "metrics": {
                "seeds": len(seeds),
                "google_ads_keywords": len(build_queue),
                "dataforseo_keywords": merged["total"],
                "classified": len(classify_input),
                "ads_approved": gm["summary"]["ads_approved"],
                "content_ideas": gm["summary"]["content_ideas"],
                "funnels": len(factory_output),
            },
            "services_used": self.services_used,
            "engine": "live" if kw_engine == "live" else "mock",
            "warnings": self.warnings,
            "duration_ms": self._elapsed_ms(start),
        }

    # ---- steps --------------------------------------------------------------
    async def _seed_optimizer(self, *, objective, nicho, pais_geo, geo_target, language_code) -> List[Dict[str, Any]]:
        client = self._gemini()
        if client is None:
            self.services_used.append("seed_optimizer:fallback")
            return fallback_seeds(nicho)
        try:
            user = build_seed_optimizer_user(
                objective=objective, nicho=nicho, pais_geo=pais_geo,
                geo_target=geo_target, language_code=language_code,
            )
            data = await client.complete_json(SEED_OPTIMIZER_SYSTEM_MESSAGE, user)
            seeds = parse_seed_optimizer_output(data)
            self.services_used.append("gemini:seed_optimizer")
            return seeds
        except (SeedQueueError, Exception) as exc:  # noqa: BLE001
            self.warnings.append(f"Seed Optimizer (LLM) falhou, usando fallback: {exc}")
            self.services_used.append("seed_optimizer:fallback")
            return fallback_seeds(nicho)

    async def _keyword_planner(
        self, *, seeds, geo_target, language_constant, language_code, language_short, pais_geo, nicho, engine
    ) -> List[Dict[str, Any]]:
        client = GoogleAdsKeywordPlannerClient(self.settings)
        # live needs a KNOWN geo_target + language_constant; else fall to mock
        geo_known = geo_target is not None and language_constant is not None
        use_live = engine == "live" and client.enabled and geo_known
        if engine == "live" and not client.enabled:
            st = self.settings.google_ads_auth_status()
            self.warnings.append(
                f"Google Ads não configurado (modo={st['mode']}; faltando: {', '.join(st['missing'])}) — usando mock."
            )
        self.services_used.append(
            f"google_ads:live:{client.auth_mode}" if use_live else "google_ads:mock"
        )

        max_loops = int(self.settings.pautador_kw_max_loops or 5)
        min_vol = int(self.settings.pautador_kw_min_volume_gold or 10)
        base = {
            "geo_target": geo_target, "language_constant": language_constant,
            "language_code": language_code, "language_short": language_short,
            "nicho": nicho, "país_geo": pais_geo,
            "max_loops": max_loops, "min_volume_gold": min_vol,
        }

        runs: List[Dict[str, Any]] = []
        for seed_entry in seeds:
            initial_seed = seed_entry["seed_keyword"]
            seed = initial_seed
            master_bank: List[Dict[str, Any]] = []
            used_seeds: List[str] = []
            used_seeds_norm: List[str] = []
            loop_iteration = 0
            while True:
                try:
                    if use_live:
                        results = await client.generate_keyword_ideas(
                            seed_keyword=seed, geo_target=geo_target, language_constant=language_constant
                        )
                    else:
                        results = mock_keyword_ideas(seed, geo_target, language_constant)
                except Exception as exc:  # noqa: BLE001
                    self.warnings.append(f"Keyword Planner falhou para '{seed}': {exc}")
                    results = []
                out = extract_gold(
                    {
                        "results": results, "loop_iteration": loop_iteration,
                        "max_loops": max_loops, "min_volume_gold": min_vol,
                        "seed_keyword": seed, "master_bank": master_bank,
                        "used_seeds": used_seeds, "used_seeds_norm": used_seeds_norm,
                    }
                )
                master_bank = out["master_bank"]
                used_seeds = out["used_seeds"]
                used_seeds_norm = out["used_seeds_norm"]
                if out["loop"]["should_continue"]:
                    seed = out["loop"]["next_seed"]
                    loop_iteration += 1
                    if use_live:
                        await asyncio.sleep(1.0)  # be gentle with the real API
                    continue
                break
            runs.append({**base, "seed_keyword": initial_seed, "loop_iteration": loop_iteration, "master_bank": master_bank})
        self.log(f"Keyword Planner: {len(runs)} branches processados.", step="planner")
        return runs

    async def _dataforseo(self, *, nicho, location_code, language_code, language_short, engine):
        client = DataForSeoClient(self.settings)
        use_live = engine == "live" and client.enabled and location_code is not None
        if engine == "live" and not client.enabled:
            self.warnings.append("PAUTADOR_KW_ENGINE=live mas DataForSEO não configurado — usando mock.")
        self.services_used.append("dataforseo:live" if use_live else "dataforseo:mock")

        try:
            if use_live:
                ac_raw = await client.autocomplete(nicho, location_code, language_code)
                rel_raw = await client.related_keywords(nicho, location_code, language_short)
            else:
                ac_raw = mock_autocomplete(nicho, location_code, language_code)
                rel_raw = mock_related(nicho, location_code, language_short)
            return extract_autocomplete(ac_raw), extract_related(rel_raw)
        except Exception as exc:  # noqa: BLE001
            self.warnings.append(f"DataForSEO falhou: {exc}")
            return [], []

    async def _funnel_prospector(self, *, pais_geo, geo_target, language_code, nicho, objective, gold_miner):
        mined = {
            "summary": gold_miner["summary"],
            "production_ads_queue": gold_miner["production_ads_queue"],
            "content_seo_queue": gold_miner["content_seo_queue"],
        }
        client = self._gemini()
        if client is None:
            self.services_used.append("funnel_prospector:fallback")
            return self._fallback_funnels(nicho, gold_miner)
        try:
            today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
            user = build_funnel_prospector_user(
                data=today, pais_geo=pais_geo, geo_target=geo_target,
                language_code=language_code, nicho=nicho, objective=objective,
                mined_keywords=mined,
            )
            data = await client.complete_json(FUNNEL_PROSPECTOR_SYSTEM_MESSAGE, user)
            self.services_used.append("gemini:funnel_prospector")
            if not isinstance(data.get("funis_sugeridos"), list):
                data["funis_sugeridos"] = []
            return data
        except Exception as exc:  # noqa: BLE001
            self.warnings.append(f"Funnel Prospector (LLM) falhou, usando fallback: {exc}")
            self.services_used.append("funnel_prospector:fallback")
            return self._fallback_funnels(nicho, gold_miner)

    # ---- helpers ------------------------------------------------------------
    @staticmethod
    def _union_keywords(merged: List[Dict[str, Any]], build_queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for k in merged:
            out[str(k.get("keyword", "")).lower().strip()] = k
        for k in build_queue:
            key = str(k.get("keyword", "")).lower().strip()
            existing = out.get(key)
            # O desempate lê o ESTADO antes do número: um volume ausente valia
            # 0 aqui e perdia para qualquer coisa, inclusive por motivo errado.
            novo_v = _volume_comparavel(k)
            velho_v = _volume_comparavel(existing) if existing else None
            if not existing or (novo_v is not None and (velho_v is None or novo_v > velho_v)):
                out[key] = {
                    "keyword": k.get("keyword"),
                    "volume": k.get("volume") or 0,
                    "cpc": k.get("cpc") or 0,
                    "competition": k.get("competition") or "UNKNOWN",
                    "competition_index": k.get("competition_index") or 0,
                    "monthly_searches": k.get("monthly_searches") or [],
                    "source": "google_ads_keyword_planner",
                }
        return list(out.values())

    def _fallback_funnels(self, nicho: str, gold_miner: Dict[str, Any]) -> Dict[str, Any]:
        ads = gold_miner["production_ads_queue"][:10]
        anchor = ads[0] if ads else {"keyword": nicho, "volume": 0, "cpc": 0}
        kws = [{"keyword": a["keyword"], "volume": a.get("volume", 0), "cpc": a.get("cpc", 0)} for a in ads]
        volume_sub = sum(a.get("volume", 0) for a in ads)
        return {
            "resumo": {
                "total_keywords": len(ads),
                "temas_pai_identificados": 1,
                "funis_sugeridos": 1 if ads else 0,
                "keywords_descartadas": 0,
            },
            "funis_sugeridos": (
                [
                    {
                        "rank": 1,
                        "nome_funil": nicho,
                        "keyword_ancora": anchor["keyword"],
                        "volume_ancora": anchor.get("volume", 0),
                        "sub_intencoes": [
                            {
                                "tipo": "OUTROS",
                                "descricao": "[mock] Agrupamento determinístico (sem LLM).",
                                "keywords": kws,
                                "volume_sub": volume_sub,
                                "qtd_keywords": len(kws),
                            }
                        ],
                        "metricas": {
                            "volume_agregado": volume_sub,
                            "cpc_medio": round(sum(a.get("cpc", 0) for a in ads) / len(ads), 2) if ads else 0,
                            "qtd_keywords": len(kws),
                            "qtd_sub_intencoes": 1,
                        },
                        "justificativa": "[mock] Funil determinístico a partir das keywords de maior volume.",
                        "tags": ["MULTI_INTENT"],
                    }
                ]
                if ads
                else []
            ),
            "priorizacao": {"fazer_primeiro": nicho, "razao": "[mock]"},
            "observacoes": ["[mock] Funnel Prospector determinístico (sem LLM)."],
            "alertas_anti_canibalizacao": [],
        }

    def _build_cluster(self, opportunity, nicho, gm, geo) -> Dict[str, Any]:
        ads = gm["production_ads_queue"]
        currency = _CURRENCY_BY_CODE.get((geo.get("country_code") or "").upper())
        nodes = []
        cpcs = []
        total_volume = 0
        for k in ads[:25]:
            vol = int(k.get("volume") or 0)
            cpc = float(k.get("cpc") or 0)
            total_volume += vol
            if cpc:
                cpcs.append(cpc)
            nodes.append(
                {
                    "keyword": k.get("keyword"),
                    "volume": _vol_to_qual(vol),
                    "cpc_local": f"{cpc:.2f} {currency}".strip() if currency else f"{cpc:.2f}",
                    "competition": _comp_to_qual(k.get("competition")),
                    "intent": "informational",
                }
            )
        avg_cpc = round(sum(cpcs) / len(cpcs), 4) if cpcs else None
        return {
            "opportunity_id": opportunity.get("id"),
            "run_id": opportunity.get("run_id"),
            "cluster_name": f"Cluster: {nicho}",
            "main_keyword": nicho,
            "intent": opportunity.get("intent") or "informational",
            "keywords": nodes,
            "total_volume": float(total_volume) if nodes else None,
            "avg_cpc_local": avg_cpc,
            "currency": currency,
        }
