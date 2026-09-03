"""
Gold Extractor + seed normalization — faithful port of n8n-peneirador-kw.json
node "⛏️ Gold Extractor1" (and the shared normalizeSeed helper).

Given one Google Ads `results` payload for the current seed, it:
  - extracts keyword metrics (micros -> currency),
  - merges into the running master_bank (highest volume wins per keyword),
  - picks the next seed (top gold not yet used, by normalized form),
  - decides whether to continue looping.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, List

_MICROS = 1_000_000


def normalize_seed(s: Any) -> str:
    """Port of normalizeSeed: lower, trim, strip accents, split, sort, join."""
    text = str(s or "").lower().strip()
    norm = unicodedata.normalize("NFD", text)
    no_accents = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    parts = [p for p in no_accents.split() if p]
    parts.sort()
    return " ".join(parts)


def _micros_to_2(micros: Any) -> float:
    return round((float(micros or 0) / _MICROS), 2)


def _estado(metricas: Dict[str, Any], chave: str) -> str:
    """O estado do campo, lido da PRESENÇA da chave — antes de coagir nada.

    ⚠️ ESTE É O PRIMEIRO SALTO DO PIPELINE, E ERA ONDE A AUSÊNCIA MORRIA.

    `int(m.get("avgMonthlySearches") or 0)` fazia uma keyword SEM bloco de
    métricas sair byte a byte idêntica a uma com zero MEDIDO:

        sem keywordIdeaMetrics   -> volume 0, cpc 0.0, competition_index 0
        zeros medidos            -> volume 0, cpc 0.0, competition_index 0

    Depois disso nenhuma camada a jusante pode recuperar a diferença — nem
    `Sinal.de_bruto`, que é justamente o tipo criado para preservá-la. Por
    isso o estado nasce aqui, ao LADO do número: os campos numéricos ficam
    como estão (nada a jusante quebra) e o estado viaja junto para quem
    souber lê-lo.

    `measured` inclui o zero: quando a API devolveu o campo, o zero é
    resposta. É a única fonte do pipeline que pode afirmar isso.
    """
    if chave not in metricas or metricas.get(chave) is None:
        return "absent"
    return "measured"


def _bloco_de_metricas(item: Dict[str, Any]) -> bool:
    """`keywordIdeaMetrics` chegou?

    `GenerateKeywordIdeaResult.keyword_idea_metrics` é campo de MENSAGEM sem
    `optional`: uma ideia pode chegar com o submensagem inteira não definida, e
    aí TODOS os escalares dentro dela leem 0. Sem esta bandeira, "a API não
    mandou métrica nenhuma" e "a API mandou zeros" são a mesma coisa a jusante.
    Ref.: developers.google.com/google-ads/api/reference/rpc/v25/GenerateKeywordIdeaResult
    """
    return isinstance(item.get("keywordIdeaMetrics"), dict) and bool(item["keywordIdeaMetrics"])


def extract_gold(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Port of the '⛏️ Gold Extractor1' Code node.

    `payload` carries: results, loop_iteration, max_loops, min_volume_gold,
    seed_keyword, master_bank (list), used_seeds (list), used_seeds_norm (list),
    plus the config passthrough fields.
    """
    raw_results: List[Dict[str, Any]] = payload.get("results") or []
    if not isinstance(raw_results, list):
        raw_results = []

    current_loop = int(payload.get("loop_iteration") or 0)
    max_loops = int(payload.get("max_loops") or 5)
    min_volume_gold = int(payload.get("min_volume_gold") or 10)
    current_seed = str(payload.get("seed_keyword") or "").lower().strip()
    current_seed_norm = normalize_seed(current_seed)

    master_bank = list(payload.get("master_bank") or [])
    used_seeds = list(payload.get("used_seeds") or [])
    used_seeds_norm = list(payload.get("used_seeds_norm") or [])

    if current_seed and current_seed not in used_seeds:
        used_seeds.append(current_seed)
    if current_seed_norm and current_seed_norm not in used_seeds_norm:
        used_seeds_norm.append(current_seed_norm)

    extracted: List[Dict[str, Any]] = []
    for item in raw_results:
        m = item.get("keywordIdeaMetrics") or {}
        kw = str(item.get("text") or "").lower().strip()
        if not kw:
            continue
        extracted.append(
            {
                "keyword": kw,
                "volume": int(m.get("avgMonthlySearches") or 0),
                "cpc": _micros_to_2(m.get("averageCpcMicros")),
                "low_bid": _micros_to_2(m.get("lowTopOfPageBidMicros")),
                "high_bid": _micros_to_2(m.get("highTopOfPageBidMicros")),
                # ⚠️ UNSPECIFIED ≠ UNKNOWN, E NENHUM DOS DOIS É "LOW".
                #
                # `competition` é o ÚNICO campo desta mensagem sem presença de
                # campo (enum proto3 puro), então um valor não populado
                # desserializa como UNSPECIFIED — "não especificado" — e é
                # indistinguível de um UNSPECIFIED explícito. `UNKNOWN` quer
                # dizer outra coisa: "valor que esta versão do cliente não
                # reconhece". Marcar o ausente como UNKNOWN, como se fazia
                # aqui, afirmava a segunda coisa tendo observado a primeira.
                # Ref.: .../v25/KeywordPlanCompetitionLevelEnum.KeywordPlanCompetitionLevel
                "competition": str(m.get("competition") or "UNSPECIFIED").upper(),
                "competition_index": int(m.get("competitionIndex") or 0),
                # O estado ao lado do número — ver `_estado`.
                "volume_estado": _estado(m, "avgMonthlySearches"),
                "cpc_estado": _estado(m, "averageCpcMicros"),
                "low_bid_estado": _estado(m, "lowTopOfPageBidMicros"),
                "high_bid_estado": _estado(m, "highTopOfPageBidMicros"),
                # "IF NOT ENOUGH DATA IS AVAILABLE, NULL IS RETURNED" — a
                # afirmação mais explícita de toda a superfície: ausente é
                # dado insuficiente, 0 é 0% de preenchimento de slot MEDIDO.
                "competition_index_estado": _estado(m, "competitionIndex"),
                # `average_cpc_micros` só é populado com
                # `include_average_cpc=true`, e o proto diz que ele existe
                # "only for legacy support". A ausência dele tem um TERCEIRO
                # sentido além de "sem dado": não solicitado.
                "cpc_motivo_de_ausencia": (
                    None if _estado(m, "averageCpcMicros") == "measured"
                    else "sem_dado_ou_nao_solicitado__include_average_cpc"
                ),
                "bloco_de_metricas_presente": _bloco_de_metricas(item),
                "found_in_loop": current_loop,
                "seed_origin": current_seed,
            }
        )

    bank_map: Dict[str, Dict[str, Any]] = {}
    for kw in master_bank:
        if kw and kw.get("keyword"):
            bank_map[kw["keyword"]] = kw
    for kw in extracted:
        existing = bank_map.get(kw["keyword"])
        if not existing or kw["volume"] > existing["volume"]:
            bank_map[kw["keyword"]] = kw
    updated_bank = list(bank_map.values())

    golds = [
        k
        for k in updated_bank
        if (k.get("volume") or 0) >= min_volume_gold
        and normalize_seed(k["keyword"]) not in used_seeds_norm
    ]
    golds.sort(key=lambda k: (k.get("volume") or 0), reverse=True)

    next_seed = golds[0]["keyword"] if golds else None
    should_continue = bool(
        next_seed
        and normalize_seed(next_seed) != current_seed_norm
        and current_loop < (max_loops - 1)
        and len(extracted) > 0
    )

    existing_keys = {m["keyword"] for m in master_bank if m.get("keyword")}
    new_keywords = len([k for k in extracted if k["keyword"] not in existing_keys])

    if not should_continue:
        if current_loop >= (max_loops - 1):
            reason = "MAX_LOOPS_REACHED"
        elif not next_seed:
            reason = "NO_MORE_GOLDS"
        elif len(extracted) == 0:
            reason = "API_EMPTY"
        else:
            reason = "DUPLICATE_SEED_NORM"
    else:
        reason = "GOLD_FOUND"

    return {
        "loop": {
            "current": current_loop,
            "max": max_loops,
            "should_continue": should_continue,
            "next_seed": next_seed,
            "reason": reason,
        },
        "master_bank": updated_bank,
        "used_seeds": used_seeds,
        "used_seeds_norm": used_seeds_norm,
        "iteration_stats": {
            "loop_number": current_loop,
            "seed_used": current_seed,
            "all_seeds_used": used_seeds,
            "api_results": len(raw_results),
            "new_keywords": new_keywords,
            "bank_before": len(master_bank),
            "bank_after": len(updated_bank),
            "golds_remaining": len(golds),
            "top_5_golds": [f"{g['keyword']} ({g['volume']})" for g in golds[:5]],
        },
    }
