"""Budget authority derived exclusively from the immutable dispatch payloads."""
from __future__ import annotations

from typing import Any, Mapping

from .contrato import ErroDeNascimentoMeta


def manifesto_orcamentario(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    operations = snapshot.get("operacoes") or []
    campaigns = [op for op in operations if op.get("tipo") == "campaign"]
    adsets = [op for op in operations if op.get("tipo") == "adset"]
    ads = [op for op in operations if op.get("tipo") == "ad"]
    if len(campaigns) != 1 or not 1 <= len(adsets) <= 10 or not 1 <= len(ads) <= 10 or len(operations) > 31:
        raise ErroDeNascimentoMeta("META_APPROVAL_OPERATION_LIMIT", "a aprovação aceita uma campanha, até dez conjuntos e dez anúncios")
    entries: list[dict[str, Any]] = []
    for op in campaigns + adsets:
        payload = op["payload"]
        fields = [key for key in ("daily_budget", "lifetime_budget") if key in payload]
        if len(fields) > 1:
            raise ErroDeNascimentoMeta("META_BUDGET_INVALID", "um orçamento não pode ser diário e vitalício ao mesmo tempo")
        if not fields:
            continue
        field = fields[0]
        amount = payload[field]
        if type(amount) is not int or not 0 < amount <= 9_007_199_254_740_991:
            raise ErroDeNascimentoMeta("META_BUDGET_INVALID", "o orçamento precisa ser inteiro positivo em centavos")
        entries.append({
            "step": op["nome"], "level": op["tipo"],
            "period": "DAILY" if field == "daily_budget" else "LIFETIME",
            "amount_minor": amount, "currency": "BRL",
            "start_time": payload.get("start_time"), "end_time": payload.get("end_time"),
            "bid_strategy": payload.get("bid_strategy"), "bid_amount": payload.get("bid_amount"),
        })
    cbo = any(entry["level"] == "campaign" for entry in entries)
    if (cbo and len(entries) != 1) or (not cbo and len(entries) != len(adsets)):
        raise ErroDeNascimentoMeta("META_BUDGET_NOT_IN_PLAN", "o plano deve ter verba na campanha ou em cada conjunto")
    # Preserve every adset schedule/bid even under campaign-level budgeting.
    schedules = [{"step": op["nome"], **{
        key: op["payload"].get(key) for key in
        ("start_time", "end_time", "bid_strategy", "bid_amount", "optimization_goal", "billing_event")
    }} for op in adsets]
    daily_total = sum(entry["amount_minor"] for entry in entries) if all(entry["period"] == "DAILY" for entry in entries) else None
    if daily_total is not None and daily_total > 9_007_199_254_740_991:
        raise ErroDeNascimentoMeta("META_BUDGET_INVALID", "a soma excede o limite numérico seguro")
    return {"version": 1, "scope": "CBO" if cbo else "ABO", "currency": "BRL",
            "entries": entries, "adsets": schedules, "daily_total_minor": daily_total}


def conferir_orcamento(snapshot: Mapping[str, Any], approval: Mapping[str, Any]) -> None:
    actual = manifesto_orcamentario(snapshot)
    saved = approval.get("budget_manifest")
    if saved is not None:
        matches = saved == actual
    else:
        # Old approvals remain readable and executable only under their exact
        # original single-adset DAILY contract. Never infer a V2 approval.
        matches = (actual["scope"] == "ABO" and len(actual["entries"]) == 1
                   and actual["entries"][0]["step"] == "adset"
                   and actual["daily_total_minor"] is not None)
    if not matches or approval.get("daily_budget_minor") != actual["daily_total_minor"]:
        raise ErroDeNascimentoMeta("META_BUDGET_DIVERGED", "o manifesto de verba, período e lances difere do aprovado")
