"""Adaptadores mínimos: linhas das tabelas REAIS -> protocolo `RunDQ`/`ObservacaoDQ`/`CoberturaSensorDia`.

Tabelas (DDL citado):
- Google Ads v21: `google_ads_collection_run`, `google_ads_raw_batch`, `google_ads_observation`
  (`043c77f5:supabase/migrations/v21_01_google_ads_coleta_canonica.sql`, `v21_02_*`, `v21_03_*`).
- JoinAds v2: `joinads_collection_run`, `joinads_raw_batch`, `joinads_observation`
  (`192bc065` = `wip/historico-joinads-20261015`: `supabase/migrations/20261015163704_*`, `20261015170000_*`).
- `raw_events` (DDL não versionado; só `ts`, `event_name`, `payload` são usados — recibo L4).

Estes adaptadores existem para a equivalência Python × SQL e para o recibo de saúde. Os adaptadores
oficiais para o contrato rico de observação são do worker A; o integrador pode trocar um pelo outro
desde que preserve as regras abaixo (cada uma espelha uma expressão das views).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from volc_dil.contracts.fingerprint import sha256_de

from .agenda import TZ_PADRAO
from .integridade import campos_de_payload
from .modelo import CoberturaSensorDia, ObservacaoDQ, RunDQ, StatusDado, para_date, para_datetime

JOINADS_METRICAS = (
    "revenue_gross", "revenue_client", "impressions", "clicks", "requests_served", "unfilled",
    "active_view", "pmr", "ctr", "ecpm_gross", "ecpm_client", "pageviews", "unique_views", "first_views",
)
JOINADS_CHAVE_NATURAL = (
    "endpoint", "grain", "metric_date", "metric_hour", "domain", "campaign_id", "custom_key",
    "custom_value", "post_id", "land_uri", "ad_unit_name", "country_iso",
)


def _txt(v: Any) -> str:
    return "" if v is None else str(v)


def chave_natural_joinads(row: Mapping[str, Any]) -> str:
    """Mesma chave do DISTINCT ON de `joinads_observation_latest`; mesmo formato de `dq_duplicacao`
    (`concat_ws('|', …)` com `coalesce(…,'')`)."""
    return "|".join(_txt(row.get(k)) for k in JOINADS_CHAVE_NATURAL)


def linha_metrica_presente(payload: Any) -> bool | None:
    """Prova de linha de métrica no payload bruto do D0/D-1 (`raw_source.metrics`, instalador
    `043c77f5:scripts/instalar_coleta_canonica_google_ads_n8n.py:133,167`). `{}` = campanha listada
    sem linha de métrica (zero sintetizado, R3). Sem a chave, ou payload não-objeto: não se sabe."""
    if isinstance(payload, dict) and isinstance(payload.get("metrics"), dict):
        return bool(payload["metrics"])
    return None


def coletor_logico_joinads(row: Mapping[str, Any]) -> str:
    """O coletor JoinAds v2 tem o mesmo nome no intraday e no D-1; o papel sai da janela:
    `window_end` >= data local do início -> intraday; senão D-1. (Mesma expressão em `dq_runs`.)"""
    tz = row.get("timezone") or TZ_PADRAO
    inicio = para_datetime(row["started_at"]).astimezone(ZoneInfo(tz)).date()
    papel = "intraday" if para_date(row["window_end"]) >= inicio else "d1"
    return f"{row['collector']}:{papel}"


def _max_dt(valores: Iterable[Any]) -> datetime | None:
    vs = [para_datetime(v) for v in valores if v is not None]
    return max(vs) if vs else None


def runs_de_tabelas(tabelas: Mapping[str, list[dict]]) -> list[RunDQ]:
    saida: list[RunDQ] = []
    lotes_g: dict[str, list] = defaultdict(list)
    for b in tabelas.get("google_ads_raw_batch", []):
        lotes_g[str(b["run_id"])].append(b["collected_at"])
    for r in tabelas.get("google_ads_collection_run", []):
        saida.append(
            RunDQ.de_dict({
                "run_id": str(r["run_id"]), "fonte": "google_ads", "coletor": r["collector"],
                "status": r["status"], "started_at": r["started_at"], "finished_at": r.get("finished_at"),
                "ultimo_sinal": _max_dt(lotes_g.get(str(r["run_id"]), [])),
                "linhas_escritas": r.get("rows_written"), "lotes": r.get("batches_written"),
                "versao_coletor": r.get("collector_version"), "janela_inicio": r.get("window_start"),
                "janela_fim": r.get("window_end"), "modo": r.get("mode"),
            })
        )
    lotes_j: dict[str, list] = defaultdict(list)
    for b in tabelas.get("joinads_raw_batch", []):
        lotes_j[b["run_key"]].append(b["collected_at"])
    for r in tabelas.get("joinads_collection_run", []):
        sinal = _max_dt([*lotes_j.get(r["run_key"], []), r.get("updated_at")])
        receipt = r.get("receipt") or {}
        saida.append(
            RunDQ.de_dict({
                "run_id": r["run_key"], "fonte": "joinads", "coletor": coletor_logico_joinads(r),
                "status": r["status"], "started_at": r["started_at"], "finished_at": r.get("finished_at"),
                "ultimo_sinal": sinal, "linhas_escritas": r.get("observations_written"),
                "lotes": r.get("batches_written"), "versao_coletor": r.get("collector_version"),
                "janela_inicio": r.get("window_start"), "janela_fim": r.get("window_end"),
                "modo": r.get("mode"), "avisos": receipt.get("warnings") or (),
            })
        )
    return saida


def observacoes_de_tabelas(tabelas: Mapping[str, list[dict]]) -> list[ObservacaoDQ]:
    saida: list[ObservacaoDQ] = []
    runs_g = {str(r["run_id"]): r for r in tabelas.get("google_ads_collection_run", [])}
    lotes_g = {str(b["batch_id"]): b for b in tabelas.get("google_ads_raw_batch", [])}
    for o in tabelas.get("google_ads_observation", []):
        run = runs_g.get(str(o["run_id"]), {})
        lote = lotes_g.get(str(o["batch_id"]), {})
        metricas = dict(o.get("metrics") or {})
        saida.append(
            ObservacaoDQ(
                fonte="google_ads", grao=o["grain"], chave=o["observation_key"], run_id=str(o["run_id"]),
                coletor=run.get("collector"), versao_coletor=run.get("collector_version"),
                entidade=o.get("campaign_id"), conta=o.get("customer_id"),
                metric_date=para_date(o.get("metric_date")), metric_hour=o.get("metric_hour"),
                observed_at=para_datetime(o["collected_at"]), ingested_at=para_datetime(o.get("created_at")),
                lote_id=str(o["batch_id"]), payload_sha256=sha256_de(metricas), metricas=metricas,
                atributos={"linha_metrica_presente": linha_metrica_presente(lote.get("payload")),
                           "resource_type": o.get("resource_type")},
                moeda=o.get("currency_code"),
            )
        )
    runs_j = {r["run_key"]: r for r in tabelas.get("joinads_collection_run", [])}
    lotes_j = {b["batch_key"]: b for b in tabelas.get("joinads_raw_batch", [])}
    for o in tabelas.get("joinads_observation", []):
        run = runs_j.get(o["run_key"], {})
        lote = lotes_j.get(o["batch_key"], {})
        metricas = {k: o.get(k) for k in JOINADS_METRICAS}
        status = o.get("data_status") or "observed"
        saida.append(
            ObservacaoDQ(
                fonte="joinads", grao=o["grain"], chave=chave_natural_joinads(o), run_id=o["run_key"],
                status=StatusDado(status), coletor=coletor_logico_joinads(run) if run else None,
                versao_coletor=run.get("collector_version"), entidade=o.get("campaign_id"),
                conta=o.get("domain"), metric_date=para_date(o.get("metric_date")),
                metric_hour=o.get("metric_hour"), observed_at=para_datetime(o["collected_at"]),
                ingested_at=para_datetime(o.get("created_at")), lote_id=o["batch_key"],
                payload_sha256=sha256_de(metricas), metricas=metricas,
                atributos={"endpoint": o["endpoint"], "observation_key": o["observation_key"],
                           "custom_key": o.get("custom_key"),
                           "custom_key_pedido": (lote.get("request_meta") or {}).get("custom_key")},
                campos_payload=campos_de_payload(lote["payload"]) if "payload" in lote else None,
                moeda=o.get("currency_code"),
            )
        )
    return saida


def _texto_json(v: Any) -> str | None:
    """Réplica de `->>` do PostgreSQL para escalares JSON."""
    if v is None:
        return None
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (dict, list)):
        import json

        return json.dumps(v)
    return str(v)


def cobertura_de_raw_events(
    linhas: Iterable[Mapping[str, Any]],
    agora: datetime,
    tz: str = TZ_PADRAO,
    dias: int = 14,
) -> list[CoberturaSensorDia]:
    """Réplica de `dq_cobertura_atribuicao_sensor`: só `volc_sensor_ready`, janela (agora-14d, agora],
    paga = `utm.paid` ∈ {'1','true'}; com campanha = `utm.campaign` não vazio após trim."""
    zona = ZoneInfo(tz)
    acc: dict = defaultdict(lambda: [0, 0, 0, 0])  # total, pagas, com_campanha, com_source
    for e in linhas:
        if e.get("event_name") != "volc_sensor_ready":
            continue
        ts = para_datetime(e["ts"])
        if not (agora - timedelta(days=dias) < ts <= agora):
            continue
        payload = e.get("payload") or {}
        utm = payload.get("utm") if isinstance(payload, dict) else None
        utm = utm if isinstance(utm, dict) else {}
        paga = _texto_json(utm.get("paid")) in ("1", "true")
        campanha = (_texto_json(utm.get("campaign")) or "").strip()
        source = _texto_json(utm.get("source")) or ""
        c = acc[ts.astimezone(zona).date()]
        c[0] += 1
        if paga:
            c[1] += 1
            c[2] += bool(campanha)
            c[3] += bool(source)
    return [CoberturaSensorDia(dia, c[1], c[2], c[3], c[0]) for dia, c in sorted(acc.items())]
