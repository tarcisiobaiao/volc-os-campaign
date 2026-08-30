"""Governança bidirecional de termos e negativas, sem mutate.

O caminho inverso é de primeira classe: além de sugerir negativa, a mesa deve
detectar uma negativa existente que bloqueia um termo explicitamente marcado
como valioso pela evidência de negócio.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


def normalizar_termo(valor: object) -> str:
    # Decisão conservadora pendente de prova adicional no contrato real:
    # preservar acento evita colapsar termos semanticamente distintos.
    return re.sub(r"\s+", " ", str(valor or "").strip().casefold())


def _bloqueia(termo: str, negativa: str, match_type: str) -> bool:
    if not termo or not negativa:
        return False
    if match_type not in {"EXACT", "PHRASE", "BROAD"}:
        return False
    if match_type == "EXACT":
        return termo == negativa
    if match_type == "PHRASE":
        palavras, frase = termo.split(), negativa.split()
        return any(palavras[i : i + len(frase)] == frase for i in range(len(palavras) - len(frase) + 1))
    palavras = termo.split()
    return all(p in palavras for p in negativa.split())


def _mesmo_escopo(termo: Mapping[str, Any], negativa: Mapping[str, Any]) -> bool:
    """Confere conta/campanha e, quando aplicável, grupo de anúncios."""

    for campo in ("customer_id", "campaign_id"):
        if not termo.get(campo) or not negativa.get(campo) or str(termo.get(campo)) != str(negativa.get(campo)):
            return False
    nivel_bruto = negativa.get("level")
    if not nivel_bruto:
        return False
    nivel = str(nivel_bruto).upper()
    if nivel == "AD_GROUP":
        return bool(termo.get("ad_group_id") and negativa.get("ad_group_id")) and str(termo.get("ad_group_id")) == str(negativa.get("ad_group_id"))
    return nivel == "CAMPAIGN"


def conflitos_de_negativa(
    termos: Sequence[Mapping[str, Any]],
    negativas: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    conflitos: list[dict[str, Any]] = []
    for termo in termos:
        if termo.get("valor_negocio") != "valioso":
            continue
        normalizado = normalizar_termo(termo.get("search_term"))
        for negativa in negativas:
            if not _mesmo_escopo(termo, negativa):
                continue
            negativo = normalizar_termo(negativa.get("keyword_text"))
            match_type_bruto = negativa.get("match_type")
            if not match_type_bruto:
                continue
            match_type = str(match_type_bruto).upper()
            if _bloqueia(normalizado, negativo, match_type):
                conflitos.append({
                    "search_term": termo.get("search_term"),
                    "negative_keyword": negativa.get("keyword_text"),
                    "match_type": match_type,
                    "negative_criterion_id": negativa.get("criterion_id"),
                    "customer_id": termo.get("customer_id"),
                    "campaign_id": termo.get("campaign_id"),
                    "ad_group_id": termo.get("ad_group_id"),
                    "level": negativa.get("level"),
                    "motivo_valor": termo.get("motivo_valor"),
                    "evidencia": termo.get("evidencia_ref"),
                })
    return conflitos
