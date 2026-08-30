"""
One-off DRY: descoberta de entidades ENVIESADA para o nicho do creditoup.com.br
(finanças pessoais + crédito + benefícios sociais/gov) no Brasil.

NÃO toca no produto, NÃO grava no Supabase, NÃO dispara ClickUp/n8n.
Reaproveita o system prompt real (ENTITY_DISCOVERY_SYSTEM_PROMPT), o motor Gemini
real e a normalização/score real (_norm_item + compute_entity_score) — só troca a
MISSION por uma versão com foco de nicho dominante. Imprime a lista rankeada.

Uso:
  cd backend && python scripts/discovery_creditoup_br.py
  cd backend && python scripts/discovery_creditoup_br.py --count 30
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.entities.orchestrator import _norm_item
from app.entities.prompts import ENTITY_DISCOVERY_SYSTEM_PROMPT
from app.llm.gemini import GeminiClient

COUNTRY = "Brasil"
COUNTRY_CODE = "BR"
LANGUAGE = "pt-BR"
MARKET_TIER = "medium_value"

# --- nicho creditoup.com.br ---------------------------------------------------
FOCUS_VERTICALS_DOMINANT = ["financas", "credito", "gov_beneficios", "empregos_concursos"]
FOCUS_VERTICALS_ADJACENT = ["seguros"]  # + consórcio/financiamento e trânsito só financeiro (IPVA)

SITE_BRIEF = (
    "creditoup.com.br — publisher informacional para brasileiros de renda baixa/média-baixa, "
    "monetizado por Google AdSense. Temas-âncora do site: Meu INSS (restituição, revisão, "
    "empréstimo consignado do INSS), FGTS (saque, saque-aniversário, Caixa FGTS), Abono "
    "Salarial/PIS, Bolsa Família/Auxílio Brasil, Pix, Caixa Tem, conta digital, empréstimo "
    "pessoal/consignado, nome negativado/Serasa/limpa-nome, vagas de emprego e cursos gratuitos. "
    "Público busca 'como acessar', 'quem tem direito', 'calendário', 'passo a passo', evitando golpes."
)


def build_biased_mission(count: int, today: str) -> str:
    dom = ", ".join(FOCUS_VERTICALS_DOMINANT)
    adj = ", ".join(FOCUS_VERTICALS_ADJACENT)
    return f"""HOJE É DIA {today}

# MISSÃO: DESCOBERTA DE ARBITRAGEM COM FOCO DE NICHO (PUBLISHER DEDICADO)

## PARÂMETROS
- **PAÍS-ALVO**: {COUNTRY}
- **MARKET_TIER**: {MARKET_TIER}
- **IDIOMA NATIVO**: pt-BR

## 🎯 FOCO DE NICHO (OBRIGATÓRIO — ISTO SOBREPÕE A REGRA GENÉRICA DE DIVERSIFICAR)
Este NÃO é um publisher multi-vertical genérico. É um publisher DEDICADO ao nicho abaixo.
Ignore a instrução padrão de "diversifique todas as verticais": aqui você CONCENTRA no nicho.

- **BRIEFING DO SITE**: {SITE_BRIEF}
- **VERTICAIS DOMINANTES (>= 75% das entidades)**: {dom}
- **VERTICAIS ADJACENTES PERMITIDAS (no máx. ~25%, só se casarem com o público de baixa renda)**:
  {adj}; consórcio/financiamento; trânsito SOMENTE com ângulo financeiro (IPVA, licenciamento, multas com custo).
- **PROIBIDO**: tecnologia pura, saúde clínica, educação sem viés financeiro, imóveis de luxo,
  jurídico corporativo, e qualquer vertical fora do universo "dinheiro/benefício do brasileiro comum".

## TAREFA
Descubra **{count} TÓPICOS-ENTIDADE** do Brasil dentro DESTE nicho, com o melhor SPREAD de
arbitragem (alta busca recorrente × bom eCPM ÷ concorrência), que rendam FUNIL DE CONTEÚDO
informacional monetizável por AdSense e que sejam coerentes com o {SITE_BRIEF.split('—')[0].strip()}.

Regras do nicho:
- Priorize entidades com PICOS SAZONAIS reais (calendários de pagamento, saque-aniversário FGTS,
  restituição, 13º, declaração, abono) — geram busca massiva e recorrente.
- Misture CRÉDITO/FINANÇAS (eCPM premium: consignado, empréstimo, financiamento, refinanciamento,
  Serasa/negativado) com BENEFÍCIOS/GOV (volume massivo: INSS, FGTS, Bolsa Família, Abono, BPC/LOAS).
- Traga a ENTIDADE (ex.: "Saque-aniversário FGTS", "Consignado INSS", "BPC/LOAS", "Serasa Limpa Nome"),
  não a keyword solta. Cada uma com 2+ dores e 3+ seed queries em pt-BR.

Refaça a inteligência cultural do Brasil focada no nicho (bancos/apps: Caixa Tem, Meu INSS, gov.br,
Pix; calendários e prazos dos próximos 12 meses). Inclua 3-5 personas curtas (aposentado, trabalhador
CLT, MEI/informal, beneficiário, negativado).

## OUTPUT
Retorne EXCLUSIVAMENTE o JSON do schema. Nenhum texto antes/depois. Nenhum markdown."""


_TIER_ORDER = {"S": 0, "A": 1, "B": 2, "EXPERIMENTAL": 3}


def _rank_key(card: dict):
    opp = card["opportunity"]
    tier = (opp.get("gold_tier") or "EXPERIMENTAL").upper()
    score = opp.get("score")
    return (_TIER_ORDER.get(tier, 9), -(score if isinstance(score, (int, float)) else -1))


async def main() -> None:
    count = 30
    if "--count" in sys.argv:
        count = int(sys.argv[sys.argv.index("--count") + 1])

    settings = get_settings()
    if not settings.resolved_gemini_key:
        print("ERRO: GEMINI_API_KEY não configurada em backend/.env", file=sys.stderr)
        sys.exit(1)

    client = GeminiClient(settings)
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    mission = build_biased_mission(count, today)

    print(f"# Disparando descoberta enviesada — Brasil × creditoup.com.br", file=sys.stderr)
    print(f"# engine=gemini model={client.model} count={count}\n", file=sys.stderr)

    raw = await client.complete_json(ENTITY_DISCOVERY_SYSTEM_PROMPT, mission)

    cards = []
    warnings = []
    for item in raw.get("entities") or []:
        try:
            cards.append(_norm_item(item, COUNTRY, COUNTRY_CODE, LANGUAGE))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"entidade ignorada: {exc}")

    cards.sort(key=_rank_key)

    out = {
        "meta": {**(raw.get("meta") or {}), "count_requested": count, "count_returned": len(cards),
                 "model": client.model},
        "insights": raw.get("insights"),
        "cultural_intelligence": raw.get("cultural_intelligence"),
        "ranked": [
            {
                "rank": i + 1,
                "canonical_name": c["entity"]["canonical_name"],
                "full_name": c["entity"].get("full_name"),
                "vertical": c["entity"].get("vertical"),
                "official_source": c["entity"].get("official_source"),
                "gold_tier": c["opportunity"].get("gold_tier"),
                "score": c["opportunity"].get("score"),
                "estimated_volume": c["opportunity"].get("estimated_volume"),
                "ecpm_band": c["opportunity"].get("ecpm_band"),
                "temporal_window": c["opportunity"].get("temporal_window"),
                "concrete_pain": c["opportunity"].get("concrete_pain"),
                "gold_reason": c["opportunity"].get("gold_reason"),
                "seed_queries": [q.get("query") for q in c.get("seed_queries") or []][:3],
            }
            for i, c in enumerate(cards)
        ],
        "warnings": warnings,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
