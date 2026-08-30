"""
Funnel Factory — faithful port of n8n-peneirador-kw.json node
"🏭 FUNNEL FACTORY" (V7 — OUTPUT UNIFICADO). Turns the Funnel Prospector's
`funis_sugeridos` into a production queue (1 item per funnel) with date
normalization (previous year -> current, drop past months) and dedup.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

MONTHS_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _fmt_int_ptbr(n: int) -> str:
    """toLocaleString('pt-BR') for integers: thousands separated by '.'."""
    return f"{int(n):,}".replace(",", ".")


def funnel_factory(ai_output: Dict[str, Any], *, today: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Port of the '🏭 FUNNEL FACTORY' Code node."""
    date = today or datetime.now(timezone.utc)
    current_year = date.year
    current_month = date.month
    previous_year = current_year - 1

    def process_keyword_date(keyword: str, volume: Any) -> Tuple[Optional[str], bool, Optional[str]]:
        processed = keyword or ""
        if str(previous_year) in processed:
            processed = processed.replace(str(previous_year), str(current_year))
        if str(current_year) in processed:
            for month_name, month_num in MONTHS_PT.items():
                if month_name in processed.lower() and month_num < current_month:
                    return None, True, f"Mês {month_name} já passou"
        return processed, False, None

    def deduplicate_keywords(keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: Dict[str, Dict[str, Any]] = {}
        result: List[Dict[str, Any]] = []
        for kw in keywords:
            normalized = str(kw.get("keyword", "")).lower().strip()
            if normalized not in seen:
                seen[normalized] = kw
                result.append(kw)
            else:
                existing = seen[normalized]
                if (kw.get("volume") or 0) > (existing.get("volume") or 0):
                    idx = next(
                        (i for i, k in enumerate(result) if str(k.get("keyword", "")).lower().strip() == normalized),
                        -1,
                    )
                    if idx != -1:
                        result[idx] = kw
                        seen[normalized] = kw
        return result

    funnels = ai_output.get("funis_sugeridos") or []

    batch_info = {
        "total_funnels": len(funnels),
        "processed_at": date.isoformat(),
        "ano_referencia": current_year,
        "priorizacao": ai_output.get("priorizacao") or {},
        "observacoes": ai_output.get("observacoes") or [],
        "alertas_anti_canibalizacao": ai_output.get("alertas_anti_canibalizacao") or [],
    }

    VOLUME_THRESHOLD = 20000
    MIN_ITEMS = 3
    MAX_ITEMS = 10

    production_queue: List[Dict[str, Any]] = []
    for funnel in funnels:
        sub_intencoes = funnel.get("sub_intencoes") or []
        all_keywords_for_campaign: List[Dict[str, Any]] = []
        removed_keywords: List[Dict[str, Any]] = []
        processed_intents: List[Dict[str, Any]] = []

        for intent in sub_intencoes:
            keywords = intent.get("keywords") or []
            processed_kws: List[Dict[str, Any]] = []
            for kw in keywords:
                new_kw, removed, reason = process_keyword_date(kw.get("keyword", ""), kw.get("volume"))
                if removed:
                    removed_keywords.append(
                        {"original": kw.get("keyword"), "reason": reason, "volume_lost": kw.get("volume") or 0}
                    )
                else:
                    processed_kws.append(
                        {
                            "keyword": new_kw,
                            "volume": kw.get("volume") or 0,
                            "cpc": kw.get("cpc") or 0,
                            "original": kw.get("keyword") if kw.get("keyword") != new_kw else None,
                        }
                    )
            deduped = deduplicate_keywords(processed_kws)
            ordered = sorted(deduped, key=lambda a: a.get("volume") or 0, reverse=True)
            selected = [k for k in ordered if (k.get("volume") or 0) >= VOLUME_THRESHOLD]
            if len(selected) < MIN_ITEMS:
                selected = ordered[: min(MAX_ITEMS, len(ordered))]
            else:
                selected = selected[:MAX_ITEMS]

            for kw in deduped:
                all_keywords_for_campaign.append(
                    {"keyword": kw["keyword"], "volume": kw["volume"], "cpc": kw["cpc"], "sub_intencao": intent.get("tipo")}
                )

            keywords_text = "\n".join(
                f"  - {k['keyword']} (Vol: {_fmt_int_ptbr(k['volume'])}, CPC: {float(k['cpc']):.2f})"
                for k in selected
            )
            processed_intents.append(
                {
                    "tipo": intent.get("tipo"),
                    "descricao": intent.get("descricao") or "",
                    "volume_sub": intent.get("volume_sub") or 0,
                    "keywords": selected,
                    "keywords_text": keywords_text,
                }
            )

        processed_intents.sort(key=lambda a: a.get("volume_sub") or 0, reverse=True)

        final_campaign = deduplicate_keywords(all_keywords_for_campaign)
        final_campaign.sort(key=lambda a: a.get("volume") or 0, reverse=True)

        formatted_subs = "\n\n".join(
            f"📌 {intent['tipo']} ({_fmt_int_ptbr(intent['volume_sub'])} vol)\n"
            + (f'   "{intent["descricao"]}"\n' if intent["descricao"] else "")
            + intent["keywords_text"]
            for intent in processed_intents
        )
        keywords_for_ads = "\n".join(k["keyword"] for k in final_campaign)
        keywords_for_clickup = "\n".join(
            f"{k['keyword']} | Vol: {_fmt_int_ptbr(k['volume'])} | CPC: R${float(k['cpc']):.2f} | {k['sub_intencao']}"
            for k in final_campaign
        )

        total_valid_volume = sum(k["volume"] for k in final_campaign)
        total_lost_volume = sum(k["volume_lost"] for k in removed_keywords)
        metricas = funnel.get("metricas") or {}

        avg_cpc = (
            f"{(sum(k['cpc'] for k in final_campaign) / len(final_campaign)):.2f}"
            if final_campaign
            else 0
        )

        production_queue.append(
            {
                "_batch_info": batch_info,
                "project_name": funnel.get("nome_funil"),
                "execution_rank": funnel.get("rank"),
                "funnel_context": {
                    "theme": funnel.get("keyword_ancora"),
                    "anchor_volume": funnel.get("volume_ancora") or 0,
                    "metrics": {
                        "total_volume": metricas.get("volume_agregado") or 0,
                        "valid_volume": total_valid_volume,
                        "lost_volume": total_lost_volume,
                        "avg_cpc": metricas.get("cpc_medio") or 0,
                        "total_keywords": metricas.get("qtd_keywords") or 0,
                        "valid_keywords": len(final_campaign),
                        "removed_keywords": len(removed_keywords),
                        "sub_intents_count": metricas.get("qtd_sub_intencoes") or len(processed_intents),
                    },
                    "strategic_direction": funnel.get("justificativa"),
                    "tags": ", ".join(funnel.get("tags") or []),
                    "sub_intencoes_raw": processed_intents,
                    "sub_intencoes_text": formatted_subs,
                },
                "keywords_campanha": {
                    "lista_google_ads": keywords_for_ads,
                    "lista_clickup": keywords_for_clickup,
                    "keywords_array": final_campaign,
                    "stats": {
                        "total_keywords": len(final_campaign),
                        "total_volume": total_valid_volume,
                        "avg_cpc": avg_cpc,
                    },
                },
                "keywords_removidas": {
                    "lista": removed_keywords,
                    "total_removidas": len(removed_keywords),
                    "volume_perdido": total_lost_volume,
                },
                "processamento": {
                    "data_processamento": date.isoformat(),
                    "ano_referencia": current_year,
                    "mes_atual": current_month,
                    "regras_aplicadas": [
                        f"Substituição {previous_year} → {current_year}",
                        f"Remoção de meses passados (< mês {current_month})",
                        "Deduplicação por keyword normalizada",
                    ],
                },
            }
        )

    production_queue.sort(key=lambda a: a.get("execution_rank") or 0)
    return production_queue
