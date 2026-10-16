"""Construtores de linhas SINTÉTICAS no formato exato da junção de 02 §9 (v21 e JoinAds v2).

Servem a dois consumidores: o gerador provisório (que passa pelos adaptadores da thread A, como
o dado real passará) e a fixture `fixture_padroes_reais()`, que reproduz os padrões medidos no
recibo do integrador (RECIBO-LEITURAS-20261016): 5 campanhas, 1 muda por hora (~80% das leituras
D0 repetem a anterior), zeros sintetizados pelo coletor v21 (R3/L11), 3 runs presos em `running`
(L9) e re-execução do mesmo slot que duplica a janela (idempotência por execução do v21: UNIQUE
`(run_id, observation_key)`). Nenhum valor real: ids, contas e domínio são inventados.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from volc_dil.contracts.fingerprint import json_canonico

FUSO = "America/Sao_Paulo"
CONTA_SINTETICA = "1234567890"
DOMINIO_SINTETICO = "exemplo-sintetico.com.br"


def _sha(obj) -> str:
    return hashlib.sha256(json_canonico(obj).encode("utf-8")).hexdigest()


def instante_local(dia: date, hora: int, minuto: int = 0, fuso: str = FUSO) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=ZoneInfo(fuso))


def linha_v21(*, run_id: str, batch_id: str, customer_id: str, campaign_id: str, dia: date, custo_micros: int,
              impressoes: int, cliques: int, collected_at: datetime, created_at: datetime,
              linha_metrica_presente: bool = True, currency: str = "BRL", run_status: str = "completed",
              collector_version: str = "21.0") -> dict:
    """Linha `google_ads_observation` ⋈ lote ⋈ execução (campaign_day). Sem linha de métrica, o coletor
    v21 sintetiza 0 (`basic()` do Code node) e o payload bruto tem `metrics: {}`."""
    if linha_metrica_presente:
        api = {"costMicros": str(custo_micros), "impressions": str(impressoes), "clicks": str(cliques)}
        metrics = {"cost_micros": custo_micros, "impressions": impressoes, "clicks": cliques, "conversions": 0}
    else:
        api = {}
        metrics = {"cost_micros": 0, "impressions": 0, "clicks": 0, "conversions": 0}
    # [thread A, R1-F4] moeda só vale com prova no payload bruto: a fixture assume o coletor endurecido que
    # pede `customer.currency_code` no GAQL (o v21 de hoje grava 'BRL' fixo e não traz a moeda no payload)
    payload = {"campaign": {"id": campaign_id, "status": "ENABLED"}, "metrics": api, "customer": {"currencyCode": currency}}
    return {
        "observation_id": f"{run_id}:{campaign_id}:{dia.isoformat()}", "run_id": run_id, "batch_id": batch_id,
        "observation_key": f"campaign_day:{customer_id}:{campaign_id}:{dia.isoformat()}", "customer_id": customer_id,
        "campaign_id": campaign_id, "ad_group_id": None, "criterion_id": None, "resource_type": "campaign",
        "resource_id": campaign_id, "grain": "campaign_day", "metric_date": dia.isoformat(), "metric_hour": None,
        "currency_code": currency, "dimensions": {}, "metrics": metrics,
        "collected_at": collected_at.isoformat(), "created_at": created_at.isoformat(),
        "batch_payload_sha256": _sha(payload), "batch_request_id": f"req-{batch_id}", "batch_payload": payload,
        "run_collector": "coleta_canonica_google_ads", "run_collector_version": collector_version,
        "run_api_version": "v21", "run_timezone": FUSO, "run_status": run_status,
    }


def _dec(micros: int) -> str:
    return str((Decimal(micros) / Decimal(1_000_000)).quantize(Decimal("0.01")))


def linha_joinads_kv(*, run_key: str, batch_key: str, domain: str, dia: date, campaign_id: Optional[str],
                     custom_key: str, custom_value: str, receita_micros: Optional[int], collected_at: datetime,
                     created_at: datetime, currency: str = "USD", pedida: str = "utm_campaign",
                     data_status: str = "observed", impressoes: int = 0, cliques: int = 0) -> dict:
    """Linha `joinads_observation` ⋈ lote ⋈ execução, endpoint key-value por campanha × dia."""
    rc = None if receita_micros is None else _dec(receita_micros)
    rg = None if receita_micros is None else _dec(receita_micros * 5 // 4)
    corpo = {"date": dia.isoformat(), "custom_key": custom_key, "custom_value": custom_value, "revenue_client": rc,
             "revenue_gross": rg, "impressions": impressoes, "clicks": cliques, "currency": currency}
    return {
        "observation_key": f"kv:{domain}:{custom_key}:{custom_value}:{dia.isoformat()}", "run_key": run_key,
        "batch_key": batch_key, "endpoint": "key_value_campaign", "grain": "campaign_day",
        "metric_date": dia.isoformat(), "metric_hour": None, "domain": domain, "campaign_id": campaign_id,
        "custom_key": custom_key, "custom_value": custom_value, "post_id": None, "land_uri": None,
        "ad_unit_name": None, "country_iso": None, "currency_code": currency, "revenue_client": rc,
        "revenue_gross": rg, "impressions": impressoes, "clicks": cliques, "data_status": data_status,
        "collected_at": collected_at.isoformat(), "created_at": created_at.isoformat(),
        "batch_payload_sha256": _sha(corpo), "batch_request_meta": {"custom_key": pedida},
        "batch_payload": corpo,  # [thread A, R1-F4] o corpo bruto (com `currency`) prova a moeda
        "run_collector": "n8n_joinads_v2", "run_collector_version": "4", "run_timezone": FUSO,
    }


def linha_joinads_earnings(*, run_key: str, batch_key: str, domain: str, dia: date, receita_micros: int,
                           collected_at: datetime, created_at: datetime, currency: str = "USD") -> dict:
    corpo = {"date": dia.isoformat(), "earnings": _dec(receita_micros), "currency": currency, "domain": domain}
    return {
        "observation_key": f"earnings:{domain}:{dia.isoformat()}", "run_key": run_key, "batch_key": batch_key,
        "endpoint": "earnings", "grain": "domain_day", "metric_date": dia.isoformat(), "metric_hour": None,
        "domain": domain, "campaign_id": None, "custom_key": None, "custom_value": None, "post_id": None,
        "land_uri": None, "ad_unit_name": None, "country_iso": None, "currency_code": currency,
        "revenue_client": _dec(receita_micros), "revenue_gross": _dec(receita_micros * 5 // 4), "impressions": 0,
        "clicks": 0, "data_status": "observed", "collected_at": collected_at.isoformat(),
        "created_at": created_at.isoformat(), "batch_payload_sha256": _sha(corpo), "batch_request_meta": {},
        "batch_payload": corpo,  # [thread A, R1-F4] o corpo bruto (com `currency`) prova a moeda
        "run_collector": "n8n_joinads_v2", "run_collector_version": "4", "run_timezone": FUSO,
    }


def fixture_padroes_reais(dia: date = date(2026, 10, 15)) -> dict:
    """Linhas v21 + JoinAds v2 com os padrões do recibo. Devolve linhas e o que se espera delas."""
    ids = [f"2427866518{k}" for k in range(5)]
    base = [80_000_000, 40_000_000, 25_000_000, 0, 0]  # 2 campanhas sem tráfego → zero sintetizado (R3)
    v21: list[dict] = []
    presos = {"gads-d0-0900", "gads-d0-1300", "gads-d0-1700"}  # L9: 3 runs presos em running
    custo_atual = list(base)
    for h in range(6, 24):  # D0 1 leitura/h; só 1 campanha muda por hora (L10/(a))
        k = h % 3
        custo_atual[k] += 1_000_000 * (k + 1)
        run = f"gads-d0-{h:02d}00"
        col = instante_local(dia, h, 0)
        for i, cid in enumerate(ids):
            presente = custo_atual[i] > 0
            v21.append(linha_v21(run_id=run, batch_id=f"{run}:{cid}", customer_id=CONTA_SINTETICA, campaign_id=cid,
                                 dia=dia, custo_micros=custo_atual[i] if presente else 0,
                                 impressoes=custo_atual[i] // 100_000, cliques=custo_atual[i] // 1_000_000,
                                 collected_at=col, created_at=col + timedelta(minutes=2), linha_metrica_presente=presente,
                                 run_status="running" if run in presos else "completed"))
    # D-1 fechado às 04:00 do dia seguinte, executado DUAS vezes no mesmo slot (re-execução duplica a janela)
    for rodada, (run, atraso) in enumerate((("gads-d1-a", 3), ("gads-d1-b", 9))):
        col = instante_local(dia + timedelta(days=1), 4, atraso)
        for i, cid in enumerate(ids):
            presente = custo_atual[i] > 0
            v21.append(linha_v21(run_id=run, batch_id=f"{run}:{cid}", customer_id=CONTA_SINTETICA, campaign_id=cid,
                                 dia=dia, custo_micros=custo_atual[i] if presente else 0,
                                 impressoes=custo_atual[i] // 100_000, cliques=custo_atual[i] // 1_000_000,
                                 collected_at=col, created_at=col + timedelta(minutes=1), linha_metrica_presente=presente))
    joinads: list[dict] = []
    for r, (desloc, fator) in enumerate(((1, 70), (2, 95), (3, 100))):
        col = instante_local(dia + timedelta(days=desloc), 8, 15)
        run = f"join-{desloc}"
        total = 0
        for i, cid in enumerate(ids[:3]):
            rec = custo_atual[i] // 5 * fator // 100 // 10_000 * 10_000
            total += rec
            joinads.append(linha_joinads_kv(run_key=run, batch_key=f"{run}:{cid}", domain=DOMINIO_SINTETICO, dia=dia,
                                            campaign_id=cid, custom_key="utm_campaign", custom_value=cid,
                                            receita_micros=rec, collected_at=col, created_at=col + timedelta(minutes=1)))
        joinads.append(linha_joinads_earnings(run_key=run, batch_key=f"{run}:earnings", domain=DOMINIO_SINTETICO, dia=dia,
                                              receita_micros=total * 102 // 100 // 10_000 * 10_000, collected_at=col,
                                              created_at=col + timedelta(minutes=1)))
    return {"v21": v21, "joinads": joinads, "ids": ids, "runs_presos": sorted(presos), "dia": dia,
            "campanhas_sem_metrica": ids[3:]}
