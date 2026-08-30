"""
MockEngine — deterministic, network-free data generator used when no LLM
key is configured. It produces fully schema-valid output (correct tier
distribution 8/14/12/6, valid enums, country flavor) so the whole pipeline,
UI, and persistence work end-to-end before real keys exist.

Everything is clearly marked engine='mock'. This is the documented fallback.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.llm.base import DiscoveryEngine, GroundingClient

# Tier -> ordered categories to cycle through, and target counts (8/14/12/6 = 40)
_TIER_CATEGORIES = {
    "S": ["S1", "S2", "S3", "S4", "S5", "S6"],
    "A": ["A1", "A2", "A3", "A4"],
    "B": ["B1", "B2", "B3"],
    "EXPERIMENTAL": ["EXP"],
}
_TIER_TARGETS = {"S": 8, "A": 14, "B": 12, "EXPERIMENTAL": 6}

# qualitative pools per tier (S biased to gold; EXP riskier) — index-rotated for variety
_TIER_QUAL = {
    "S": {"volume": ["very_high", "high"], "rpm": ["very_high", "high"], "comp": ["low", "medium"], "conf": ["very_high", "high"]},
    "A": {"volume": ["high", "very_high", "medium"], "rpm": ["high", "very_high"], "comp": ["medium", "low", "high"], "conf": ["high", "medium"]},
    "B": {"volume": ["medium", "high"], "rpm": ["medium", "low"], "comp": ["low", "medium"], "conf": ["high", "medium"]},
    "EXPERIMENTAL": {"volume": ["low", "medium"], "rpm": ["medium", "high"], "comp": ["low", "high"], "conf": ["low", "medium"]},
}
_TIMINGS = ["evergreen", "evergreen", "seasonal", "trending", "event_driven"]

_CATEGORY_THEME = {
    "S1": ("acesso portal", "como acessar o portal {token} sem perder o login"),
    "S2": ("declarar {token}", "como declarar {token} passo a passo este ano"),
    "S3": ("quem tem direito", "quem tem direito ao {token} e como solicitar"),
    "S4": ("calcular {token}", "calculadora de {token} atualizada"),
    "S5": ("regras {token}", "novas regras do {token} para o próximo ano"),
    "S6": ("dor {token}", "como lidar com {token} (problema cultural local)"),
    "A1": ("erro {token}", "{token} não está funcionando o que fazer"),
    "A2": ("comparar {token}", "{token} vale a pena ou não comparativo"),
    "A3": ("sintomas {token}", "sintomas e tratamento de {token} sem emergência"),
    "A4": ("direito {token}", "meus direitos sobre {token} e como reivindicar"),
    "B1": ("usar app {token}", "como usar o aplicativo {token} passo a passo"),
    "B2": ("documento {token}", "como tirar o documento {token} e prazos"),
    "B3": ("calendário {token}", "datas e calendário de {token} deste ano"),
    "EXP": ("experimental {token}", "tendência emergente sobre {token} pouco explorada"),
}

# Country flavor: institutions / programs / health tokens / currency / persona names
_COUNTRY_PROFILE: Dict[str, Dict[str, Any]] = {
    "GB": {
        "native_language": "en-GB", "market_tier": "high_value", "currency": "GBP", "cpc": (1.0, 5.0),
        "institutions": ["HMRC", "DWP", "DVLA", "NHS", "Home Office"],
        "programs": ["Universal Credit", "PIP", "State Pension", "Child Benefit"],
        "health": ["NHS waiting list", "ADHD assessment", "mental health"],
        "names": ["Liam", "Chloe", "Raj", "Fiona", "Gareth", "Sarah", "Tariq", "Margaret"],
    },
    "PT": {
        "native_language": "pt-PT", "market_tier": "medium_value", "currency": "EUR", "cpc": (0.3, 1.5),
        "institutions": ["Finanças", "Segurança Social", "SNS", "IMT", "AIMA"],
        "programs": ["RSI", "Abono de Família", "Complemento Solidário", "IRS Jovem"],
        "health": ["lista de espera SNS", "saúde mental", "médico de família"],
        "names": ["João", "Maria", "Tiago", "Beatriz", "Rui", "Inês", "Carlos", "Ana"],
    },
    "GT": {
        "native_language": "es-GT", "market_tier": "volume_play", "currency": "GTQ", "cpc": (0.05, 0.4),
        "institutions": ["SAT", "IGSS", "RENAP", "MINEDUC"],
        "programs": ["Bono Social", "Mi Bono Seguro", "Beca Social"],
        "health": ["seguro IGSS", "salud pública", "vacunación"],
        "names": ["Carlos", "María", "Luis", "Ana", "José", "Sofía", "Pedro", "Lucía"],
    },
}
_GENERIC_PROFILE = {
    "native_language": "en", "market_tier": "medium_value", "currency": "USD", "cpc": (0.3, 1.5),
    "institutions": ["Tax Agency", "Social Security", "Health Service", "Vehicle Authority"],
    "programs": ["Welfare Benefit", "Child Support", "Pension Scheme", "Housing Aid"],
    "health": ["public health waiting list", "mental health", "chronic condition"],
    "names": ["Alex", "Sam", "Maria", "Chen", "Omar", "Sofia", "Ivan", "Nina"],
}

_CPC_TIER_FACTOR = {"S": 1.4, "A": 1.2, "B": 0.8, "EXPERIMENTAL": 0.6}


def _profile(country_code: Optional[str]) -> Dict[str, Any]:
    return _COUNTRY_PROFILE.get((country_code or "").upper(), _GENERIC_PROFILE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_tier_plan(count: int) -> List[str]:
    """Return a list of tiers of length `count`, scaled from 8/14/12/6."""
    if count == 40:
        plan: List[str] = []
        for tier, n in _TIER_TARGETS.items():
            plan.extend([tier] * n)
        return plan
    # scale proportionally, then top up / trim to exactly `count`
    total = sum(_TIER_TARGETS.values())
    plan = []
    for tier, n in _TIER_TARGETS.items():
        plan.extend([tier] * max(1, round(n * count / total)))
    if len(plan) < count:
        plan.extend(["A"] * (count - len(plan)))
    return plan[:count]


class MockEngine(DiscoveryEngine):
    name = "mock"
    model = "mock-oracle-v1"

    async def discover(
        self,
        country: str,
        native_language: Optional[str],
        count: int,
        grounding_notes: str = "",
    ) -> Dict[str, Any]:
        # infer a country_code from native_language hint or default generic
        prof = _GENERIC_PROFILE
        code = None
        for c, p in _COUNTRY_PROFILE.items():
            if p["native_language"] == (native_language or "") or country.lower() in (
                "reino unido" if c == "GB" else "portugal" if c == "PT" else "guatemala" if c == "GT" else ""
            ):
                prof, code = p, c
                break
        lang = native_language or prof["native_language"]

        seeds = self._build_seeds(country, lang, prof, count)
        personas = self._build_personas(prof)

        return {
            "meta": {
                "country": country,
                "native_language": lang,
                "market_tier": prof["market_tier"],
                "generated_at": _now_iso(),
                "perplexity_calls_made": 0,
            },
            "cultural_intelligence": {
                "key_institutions": list(prof["institutions"]),
                "main_benefits_programs": list(prof["programs"]),
                "unique_cultural_pains": [
                    f"[mock] Dor cultural específica de {country} #{i + 1}" for i in range(3)
                ],
                "upcoming_events": [
                    f"[mock] Mudança regulatória em {country} nos próximos 12 meses #{i + 1}"
                    for i in range(3)
                ],
                "digital_friction_apps": [f"App/portal {inst}" for inst in prof["institutions"][:4]],
            },
            "personas": personas,
            "seeds": seeds,
            "insights": {
                "market_observation": f"[mock] {country} é um mercado {prof['market_tier']} com forte atrito burocrático digital.",
                "untapped_angle": "[mock] Nichos de transição burocrática e calculadoras de elegibilidade.",
                "recommended_deep_dive": "[mock] Aprofundar nas calculadoras de imposto e benefícios sazonais.",
                "cultural_warning": f"[mock] Respeite a ortografia e os nomes oficiais dos órgãos de {country}.",
            },
        }

    def _build_personas(self, prof: Dict[str, Any]) -> List[Dict[str, Any]]:
        literacy = ["low", "medium", "high"]
        out = []
        for i, name in enumerate(prof["names"][:8]):
            out.append(
                {
                    "name": name,
                    "demographics": f"[mock] {25 + i * 5} anos, perfil demográfico {i + 1}",
                    "core_pain": f"[mock] Dor central relacionada a {prof['programs'][i % len(prof['programs'])]}",
                    "digital_literacy": literacy[i % 3],
                    "typing_style": "[mock] busca longa e descritiva",
                    "main_systems": [prof["institutions"][i % len(prof["institutions"])]],
                }
            )
        return out

    def _build_seeds(
        self, country: str, lang: str, prof: Dict[str, Any], count: int
    ) -> List[Dict[str, Any]]:
        plan = _build_tier_plan(count)
        names = prof["names"][:8]
        lo, hi = prof["cpc"]
        ccy = prof["currency"]
        per_cat_index: Dict[str, int] = {}
        seen_keywords: set = set()
        seeds: List[Dict[str, Any]] = []

        for i, tier in enumerate(plan):
            cats = _TIER_CATEGORIES[tier]
            ci = per_cat_index.get(tier, 0)
            category = cats[ci % len(cats)]
            per_cat_index[tier] = ci + 1

            token_pool = prof["programs"] + prof["institutions"]
            token = token_pool[i % len(token_pool)]
            if category in ("A3", "S6"):
                token = prof["health"][i % len(prof["health"])]

            main_tpl, long_tpl = _CATEGORY_THEME[category]
            main_keyword = main_tpl.format(token=token)
            keyword = long_tpl.format(token=token)
            # guarantee unique keywords so the critic does not dedupe them away
            if keyword.lower() in seen_keywords:
                keyword = f"{keyword} ({category.lower()}-{i + 1})"
            seen_keywords.add(keyword.lower())

            q = _TIER_QUAL[tier]
            volume = q["volume"][i % len(q["volume"])]
            rpm = q["rpm"][i % len(q["rpm"])]
            comp = q["comp"][i % len(q["comp"])]
            conf = q["conf"][i % len(q["conf"])]

            intent = "calculator" if category == "S4" else "comparison" if category == "A2" else "informational"
            timing = _TIMINGS[i % len(_TIMINGS)]

            factor = _CPC_TIER_FACTOR[tier]
            cpc_lo = round(lo * factor, 2)
            cpc_hi = round(hi * factor, 2)

            seeds.append(
                {
                    "keyword": keyword,
                    "main_keyword": main_keyword,
                    "keyword_pt_translation": f"[{lang}] {keyword}",
                    "tier": tier,
                    "category": category,
                    "volume_estimate": volume,
                    "cpc_estimate_local": f"{cpc_lo}-{cpc_hi} {ccy}",
                    "rpm_potential": rpm,
                    "competition_estimate": comp,
                    "intent": intent,
                    "persona": names[i % len(names)],
                    "pain_point": f"[mock] Dor concreta sobre {token} em {country}.",
                    "reasoning": f"[mock] {token} atrai anúncios de alto RPM em {country}; gerado pelo motor mock.",
                    "variations": [f"{main_keyword} {suffix}" for suffix in ("guia", "2026", "online")],
                    "expansion_hooks": [f"Conteúdo sobre {token} — ângulo {n}" for n in (1, 2, 3)],
                    "timing": timing,
                    "confidence": conf,
                }
            )
        return seeds

    async def mine(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        main = opportunity.get("main_keyword") or opportunity.get("keyword") or "keyword"
        volumes = ["high", "very_high", "medium", "high", "medium", "low", "high", "medium"]
        comps = ["low", "medium", "low", "high", "medium", "low", "medium", "low"]
        suffixes = ["guia", "passo a passo", "2026", "online", "requisitos", "prazo", "calculadora", "documentos"]
        cpc_local = opportunity.get("cpc_estimate_local") or "0.50-1.50 USD"
        nodes = [
            {
                "keyword": f"{main} {suffix}",
                "volume": volumes[i % len(volumes)],
                "cpc_local": cpc_local,
                "competition": comps[i % len(comps)],
                "intent": "informational",
            }
            for i, suffix in enumerate(suffixes)
        ]
        return {
            "cluster_name": f"Cluster: {main}",
            "main_keyword": main,
            "intent": opportunity.get("intent") or "informational",
            "keywords": nodes,
        }

    async def build_funnel(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        main = opportunity.get("main_keyword") or opportunity.get("keyword") or "tema"
        persona = opportunity.get("persona") or "Persona alvo"
        stages = ["tofu", "tofu", "mofu", "mofu", "bofu"]
        goals = [
            "Nomear a dor e gerar identificação imediata",
            "Aprofundar o problema e suas consequências",
            "Entregar um guia prático / calculadora",
            "Comparar opções e apresentar prova",
            "Conduzir à ação concreta e captura",
        ]
        pages = []
        for i in range(5):
            pages.append(
                {
                    "position": i + 1,
                    "page_title": f"{main} — página {i + 1}",
                    "avatar": persona,
                    "stage": stages[i],
                    "emotional_goal": goals[i],
                    "subtitles": [f"Subtítulo {i + 1}.{j}" for j in range(1, 5)],
                    "internal_links": (
                        [f"-> Página {i + 2}: continuar a jornada"] if i < 4 else ["-> CTA: captura de lead"]
                    ),
                }
            )
        return {"funnel_name": f"Funil: {main}", "pages": pages}


class MockGrounding(GroundingClient):
    """No-op grounding used when Perplexity is not configured."""

    name = "mock-grounding"

    async def search(self, query: str) -> str:
        return f"[mock-grounding] (sem Perplexity configurada) consulta: {query[:120]}"
