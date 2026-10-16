"""Gerador sintético de linhas no formato das tabelas REAIS (v21 Google Ads, JoinAds v2, raw_events).

Uso: fixture do Postgres descartável, equivalência Python × SQL e recibo de saúde sintético.
NÃO é dado real. Os cenários reproduzem a FORMA dos achados de produção já conhecidos (recibo de
leituras externas de 16/10: L9 runs presos, L11 zero sintetizado, L4 sensor sem campanha), não os
valores. Valores monetários são inventados.

Cenários:
- `limpo`: nenhuma regra deve disparar acima de `info` (contraprova negativa);
- `producao_conhecida`: só os três achados reais (órfãos de termos, 80% zero sintetizado, 0/28 sensor);
- `estressado`: todas as regras com fixture disparam (contraprova positiva).
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from volc_dil.contracts.fingerprint import sha256_de

TZ = ZoneInfo("America/Sao_Paulo")
AGORA_PADRAO = datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)  # 12:00 em São Paulo
CONTA = "1234567890"
CONTA2 = "9876543210"
DOMINIO = "creditoup.com.br"
CAMPANHAS = ("21000000001", "21000000002", "21000000003", "21000000004", "21000000005")
TERMOS = ("emprestimo rapido", "cartao sem anuidade", "credito pessoal")


@dataclass(frozen=True)
class Cenario:
    nome: str
    zero_sintetizado: bool = False
    orfaos_termos: bool = False
    termos_sem_sucesso: bool = False
    sensor_sem_campanha: bool = False
    d0_atrasado: bool = False
    joinads_intraday_parado: bool = False
    conflito_dup: bool = False
    reingestao: bool = False
    kv_baixa: bool = False
    kv_excesso: bool = False
    falha_silenciosa: bool = False
    substituicao: bool = False
    deriva_esquema: bool = False
    divergencia_custo: bool = False
    deriva_serie: bool = False


_LIMPO = Cenario("limpo")
_PRODUCAO = replace(_LIMPO, nome="producao_conhecida", zero_sintetizado=True, orfaos_termos=True,
                    sensor_sem_campanha=True)
_ESTRESSADO = Cenario("estressado", **{k: True for k in Cenario.__dataclass_fields__ if k != "nome"})
CENARIOS = {c.nome: c for c in (_LIMPO, _PRODUCAO, _ESTRESSADO)}


def _local(d: date, h: int, m: int, s: int = 0) -> datetime:
    return datetime.combine(d, time(h, m, s), tzinfo=TZ).astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class _Gerador:
    def __init__(self, seed: int, cenario: Cenario, agora: datetime):
        self.rng = random.Random(seed)
        self.c = cenario
        self.agora = agora
        self.hoje = agora.astimezone(TZ).date()
        self.ontem = self.hoje - timedelta(days=1)
        self.t: dict[str, list[dict]] = {k: [] for k in (
            "google_ads_collection_run", "google_ads_raw_batch", "google_ads_observation",
            "joinads_collection_run", "joinads_raw_batch", "joinads_observation", "raw_events")}
        # custo final por campanha e dia (micros), fixo por seed
        self.custo_final = {(cp, d): self.rng.randint(80, 400) * 1_000_000
                            for cp in CAMPANHAS for d in self._dias(10)}
        self.earnings_final = {d: round(self.rng.uniform(150, 400), 2) for d in self._dias(10)}
        self.share = [0.30, 0.25, 0.20, 0.15, 0.10]
        self._exec = 1000

    def _dias(self, n: int) -> list[date]:
        return [self.hoje - timedelta(days=k) for k in range(n - 1, -1, -1)]

    def _uuid(self) -> str:
        return str(uuid.UUID(int=self.rng.getrandbits(128)))

    def _execucao(self) -> str:
        self._exec += 1
        return str(self._exec)

    # ------------------------------------------------------------------ Google Ads v21

    def _run_google(self, collector: str, inicio: datetime, status: str, *, janela: tuple[date, date] | None,
                    trigger: str = "schedule", fim: datetime | None = None) -> dict:
        exe = self._execucao()
        wf = {"n8n-google-ads-d0": "Ps9yLfQkHeaAbyZZ", "n8n-google-ads-d1": "7yxs1aOlzWkkkSf9",
              "n8n-google-ads-terms-keywords": "TFlmThr4930oPneE"}[collector]
        run = {
            "run_id": self._uuid(), "idempotency_key": f"{wf}:{exe}", "workflow_id": wf,
            "workflow_execution_id": exe, "collector": collector, "collector_version": 1,
            "api_version": "v25", "mode": "shadow", "trigger_kind": trigger,
            "window_start": janela[0].isoformat() if janela else None,
            "window_end": janela[1].isoformat() if janela else None,
            "timezone": "America/Sao_Paulo", "status": status, "started_at": _iso(inicio),
            "finished_at": None if status == "running" else _iso(fim or inicio + timedelta(minutes=3)),
            "accounts_seen": 0, "batches_written": 0, "rows_read": 0, "rows_written": 0, "rows_rejected": 0,
            "error_class": "http_500" if status == "failed" else None,
            "error_code": "500" if status == "failed" else None,
            "receipt": {}, "created_at": _iso(inicio),
        }
        self.t["google_ads_collection_run"].append(run)
        return run

    def _lote_google(self, run: dict, *, batch_key: str, conta: str, resource: str, grao: str,
                     janela: tuple[date, date] | None, coletado: datetime, payload: Any,
                     observacoes: list[dict]) -> None:
        lote = {
            "batch_id": self._uuid(), "run_id": run["run_id"], "batch_key": batch_key, "customer_id": conta,
            "resource_type": resource, "grain": grao,
            "window_start": janela[0].isoformat() if janela else None,
            "window_end": janela[1].isoformat() if janela else None,
            "collected_at": _iso(coletado), "request_id": None, "row_count": len(observacoes),
            "payload": payload, "payload_sha256": sha256_de(payload), "created_at": _iso(coletado + timedelta(seconds=1)),
        }
        self.t["google_ads_raw_batch"].append(lote)
        for o in observacoes:
            o.update({"observation_id": self._uuid(), "run_id": run["run_id"], "batch_id": lote["batch_id"],
                      "customer_id": conta, "resource_type": resource, "grain": grao,
                      "collected_at": _iso(coletado), "created_at": _iso(coletado + timedelta(seconds=1))})
            o.setdefault("dimensions", {})
            o.setdefault("attributes", {})
            self.t["google_ads_observation"].append(o)
        run["batches_written"] += 1
        run["rows_read"] += len(observacoes)
        run["rows_written"] += len(observacoes)
        run["accounts_seen"] = 1

    def _campanha_dia(self, run: dict, dia: date, fator: float, coletado: datetime, *,
                      d1: bool = False) -> None:
        for i, cp in enumerate(CAMPANHAS):
            sem_linha = self.c.zero_sintetizado and i >= 1
            zero_real = (not self.c.zero_sintetizado) and i == 4
            if sem_linha or zero_real:
                custo = imp = 0
            else:
                custo = int(round(self.custo_final[(cp, dia)] * fator))
                if d1 and self.c.divergencia_custo and i == 0:
                    custo = int(round(custo * 1.2))
                imp = max(1, custo // 50_000)
            conta = CONTA2 if (self.c.substituicao and i == 3 and run["started_at"] == self._sub_marca) else CONTA
            linha = {} if sem_linha else {"campaign": {"resourceName": f"customers/{conta}/campaigns/{cp}"},
                                          "metrics": {} if zero_real else {"costMicros": str(custo),
                                                                           "impressions": str(imp)}}
            payload = {"campaign": {"campaign": {"id": cp, "status": "ENABLED"}}, "metrics": linha,
                       "budget": {}, "goal": {}}
            obs = {"observation_key": f"{conta}:{cp}:{dia.isoformat()}", "campaign_id": cp, "resource_id": cp,
                   "metric_date": dia.isoformat(), "currency_code": "BRL",
                   "metrics": {"cost_micros": custo, "impressions": imp, "clicks": imp // 20,
                               "conversions": 0, "ctr": None},
                   "dimensions": {"campaign_name": f"camp-{i}", "status": "ENABLED"}}
            self._lote_google(run, batch_key=f"{conta}:{cp}:{dia.isoformat()}", conta=conta,
                              resource="campaign", grao="campaign_day", janela=(dia, dia),
                              coletado=coletado + timedelta(seconds=i), payload=payload, observacoes=[obs])

    def google(self) -> None:
        c = self.c
        # D0 horário 06–23 a partir de ontem 06:07
        self._sub_marca = _iso(_local(self.hoje, 6, 7, 20))
        for dia in (self.ontem, self.hoje):
            for h in range(6, 24):
                slot = _local(dia, h, 7)
                if slot + timedelta(minutes=30) > self.agora and slot > self.agora:
                    continue
                if slot > self.agora:
                    continue
                if c.d0_atrasado and dia == self.hoje and h == 11:
                    continue  # ausência silenciosa
                status = "failed" if (c.d0_atrasado and dia == self.hoje and h == 10) else "completed"
                inicio = slot + timedelta(seconds=20)
                run = self._run_google("n8n-google-ads-d0", inicio, status, janela=(dia, dia))
                if status == "completed":
                    self._campanha_dia(run, dia, (h - 5) / 18, inicio + timedelta(seconds=30))
        # D0 manuais fora de slot: um recente (não órfão) e um antigo com heartbeat recente (não órfão)
        manual = self._run_google("n8n-google-ads-d0", _local(self.hoje, 11, 50), "running",
                                  janela=(self.hoje, self.hoje), trigger="manual")
        hb = self._run_google("n8n-google-ads-d0", _local(self.hoje, 10, 40), "running",
                              janela=(self.hoje, self.hoje), trigger="manual")
        self._campanha_parcial(hb, _local(self.hoje, 11, 45))
        del manual
        # D-1: 06:17 e 14:17
        for dia in (self.ontem, self.hoje):
            for h in (6, 14):
                slot = _local(dia, h, 17)
                if slot > self.agora:
                    continue
                inicio = slot + timedelta(seconds=15)
                alvo = dia - timedelta(days=1)
                run = self._run_google("n8n-google-ads-d1", inicio, "completed", janela=(alvo, alvo))
                if c.falha_silenciosa and dia == self.ontem and h == 14:
                    continue  # completed com 0 linhas
                self._campanha_dia(run, alvo, 1.0, inicio + timedelta(seconds=30), d1=True)
                if c.reingestao and dia == self.hoje and h == 6:
                    origem = [o for o in self.t["google_ads_observation"] if o["run_id"] == run["run_id"]][2]
                    replay = self._run_google("n8n-google-ads-d1", inicio + timedelta(minutes=23), "completed",
                                              janela=(alvo, alvo), trigger="replay")
                    lote_origem = next(b for b in self.t["google_ads_raw_batch"] if b["batch_id"] == origem["batch_id"])
                    copia = {k: origem[k] for k in ("observation_key", "campaign_id", "resource_id", "metric_date",
                                                    "currency_code", "metrics", "dimensions")}
                    self._lote_google(replay, batch_key=lote_origem["batch_key"], conta=CONTA, resource="campaign",
                                      grao="campaign_day", janela=(alvo, alvo),
                                      coletado=datetime.fromisoformat(origem["collected_at"]),
                                      payload=lote_origem["payload"], observacoes=[copia])
        self._termos()

    def _campanha_parcial(self, run: dict, coletado: datetime) -> None:
        cp = CAMPANHAS[0]
        obs = {"observation_key": f"{CONTA}:{cp}:{self.hoje.isoformat()}", "campaign_id": cp, "resource_id": cp,
               "metric_date": self.hoje.isoformat(), "currency_code": "BRL",
               "metrics": {"cost_micros": int(self.custo_final[(cp, self.hoje)] * 0.3), "impressions": 10,
                           "clicks": 1, "conversions": 0, "ctr": None}}
        self._lote_google(run, batch_key=f"{CONTA}:{cp}:{self.hoje.isoformat()}:manual", conta=CONTA,
                          resource="campaign", grao="campaign_day", janela=(self.hoje, self.hoje),
                          coletado=coletado, payload={"campaign": {}, "metrics": {"metrics": {"costMicros": "1"}}},
                          observacoes=[obs])

    def _obs_termos(self, dia_run: date, moeda: str = "BRL") -> tuple[list[dict], list[dict], tuple[date, date]]:
        dias = [dia_run - timedelta(days=2), dia_run - timedelta(days=1)]
        obs, payload = [], []
        for d in dias:
            for j, termo in enumerate(TERMOS):
                cp = CAMPANHAS[j]
                custo = 1_000_000 * (j + 1) + d.toordinal() % 7 * 10_000
                obs.append({"observation_key": f"{CONTA}:{cp}:5000{j}:{d.isoformat()}:term:{termo}",
                            "campaign_id": cp, "ad_group_id": f"5000{j}", "metric_date": d.isoformat(),
                            "currency_code": moeda,
                            "metrics": {"impressions": 100 + j, "clicks": 5, "cost_micros": custo,
                                        "conversions": 0, "conversions_value": 0, "ctr": 0.05,
                                        "average_cpc_micros": None},
                            "dimensions": {"search_term": termo}})
                payload.append({"searchTermView": {"searchTerm": termo}, "segments": {"date": d.isoformat()}})
        return obs, payload, (dias[0], dias[-1])

    def _termos(self) -> None:
        c = self.c
        if c.orfaos_termos:
            for k in range(3):
                inicio = _local(self.ontem, 11, 48, 20 * k)
                run = self._run_google("n8n-google-ads-terms-keywords", inicio, "running", janela=None)
                obs, payload, jan = self._obs_termos(self.ontem, "USD" if c.substituicao else "BRL")
                self._lote_google(run, batch_key=f"{CONTA}:search_term:{jan[0]}:{jan[1]}", conta=CONTA,
                                  resource="search_term", grao="search_term_day", janela=jan,
                                  coletado=inicio + timedelta(minutes=1), payload=payload, observacoes=obs[:1])
        for dia in (self.ontem, self.hoje):
            for h in (0, 4, 8, 12, 16, 20):
                slot = _local(dia, h, 23)
                if slot > self.agora:
                    continue
                inicio = slot + timedelta(seconds=40)
                status = "failed" if c.termos_sem_sucesso else "completed"
                run = self._run_google("n8n-google-ads-terms-keywords", inicio, status, janela=None)
                if status != "completed":
                    continue
                obs, payload, jan = self._obs_termos(dia)
                self._lote_google(run, batch_key=f"{CONTA}:search_term:{jan[0]}:{jan[1]}", conta=CONTA,
                                  resource="search_term", grao="search_term_day", janela=jan,
                                  coletado=inicio + timedelta(minutes=1), payload=payload, observacoes=obs)

    # ------------------------------------------------------------------ JoinAds v2

    def _run_joinads(self, inicio: datetime, janela: tuple[date, date], status: str = "completed",
                     avisos: list[dict] | None = None) -> dict:
        slot_utc = inicio.astimezone(timezone.utc).strftime("%Y%m%d%H")
        run = {
            "run_key": f"joinads-v4:shadow:{janela[0]}:{janela[1]}:schedule:{slot_utc}",
            "workflow_id": "cpb6tNxt211UkAn2" if janela[0] == janela[1] else "jDX397ViVcRQft4A",
            "workflow_execution_id": self._execucao(), "collector": "n8n_joinads_v2", "collector_version": 4,
            "mode": "shadow", "trigger_kind": "schedule", "window_start": janela[0].isoformat(),
            "window_end": janela[1].isoformat(), "timezone": "America/Sao_Paulo", "status": status,
            "started_at": _iso(inicio), "finished_at": None if status == "running" else _iso(inicio + timedelta(minutes=2)),
            "endpoint_count": 2, "batches_written": 0, "rows_read": 0, "observations_written": 0,
            "rows_rejected": len(avisos or []), "warning_count": len(avisos or []), "error_class": None,
            "error_code": None, "receipt": {"warnings": avisos or [], "collector_version": 4, "source": "joinads_api"},
            "created_at": _iso(inicio), "updated_at": _iso(inicio + timedelta(minutes=2)),
        }
        self.t["joinads_collection_run"].append(run)
        return run

    def _lote_joinads(self, run: dict, endpoint: str, grao: str, dia: date, idx: int, linhas: list[dict],
                      coletado: datetime, request_meta: dict, transform) -> None:
        batch_key = f"{run['run_key']}:{endpoint}:{dia}:{idx}"
        payload = {"data": linhas}
        self.t["joinads_raw_batch"].append({
            "batch_key": batch_key, "run_key": run["run_key"], "endpoint": endpoint, "grain": grao,
            "request_meta": {"start_date": dia.isoformat(), "end_date": dia.isoformat(), "domain": DOMINIO,
                             **request_meta},
            "http_status": 200, "row_count": len(linhas), "payload": payload, "collected_at": _iso(coletado),
            "created_at": _iso(coletado + timedelta(seconds=1)),
        })
        for i, ln in enumerate(linhas):
            o = transform(ln)
            o.update({"observation_key": f"{batch_key}:{i}", "run_key": run["run_key"], "batch_key": batch_key,
                      "endpoint": endpoint, "grain": grao, "metric_date": dia.isoformat(), "metric_hour": None,
                      "domain": DOMINIO, "currency_code": "USD", "collected_at": _iso(coletado),
                      "created_at": _iso(coletado + timedelta(seconds=1))})
            o.setdefault("data_status", "observed")
            o.setdefault("dimensions", {})
            o.setdefault("attributes", {})
            self.t["joinads_observation"].append(o)
        run["batches_written"] += 1
        run["rows_read"] += len(linhas)
        run["observations_written"] += len(linhas)

    def _dia_joinads(self, run: dict, dia: date, fator: float, coletado: datetime, idx: int) -> None:
        c = self.c
        earnings = round(self.earnings_final[dia] * fator, 2)
        cobertura = 0.98
        if c.kv_baixa and dia == self.ontem:
            cobertura = 0.60
        if c.kv_excesso and dia == self.ontem - timedelta(days=1):
            cobertura = 1.15
        linha_e = {"date": dia.isoformat(), "domain": DOMINIO, "revenue": round(earnings * 1.25, 2),
                   "revenue_client": earnings, "impressions": int(earnings * 900)}
        if c.deriva_esquema and run["started_at"] == self._esquema_marca:
            linha_e["revenue_bonus"] = 0.0
        self._lote_joinads(run, "earnings", "domain_day", dia, idx, [linha_e], coletado, {},
                           lambda ln: {"revenue_gross": ln["revenue"], "revenue_client": ln["revenue_client"],
                                       "impressions": ln["impressions"]})
        linhas_kv = []
        for i, cp in enumerate(CAMPANHAS):
            rc = round(earnings * cobertura * self.share[i], 4)
            linhas_kv.append({"custom_key": "utm_campaign", "custom_value": cp, "ad_unit_name": "top",
                              "revenue": round(rc * 1.25, 4), "revenue_client": rc, "impressions": int(rc * 900)})
        if c.conflito_dup and run["started_at"] == self._dup_marca:
            conflito = dict(linhas_kv[0], revenue_client=round(linhas_kv[0]["revenue_client"] * 0.5, 4))
            linhas_kv += [conflito, dict(linhas_kv[1])]
        self._lote_joinads(run, "key_value_campaign_adunit", "campaign_adunit_day", dia, idx, linhas_kv,
                           coletado, {"report_type": "Analytical", "custom_key": "utm_campaign",
                                      "include": "ad_unit_name"},
                           lambda ln: {"campaign_id": ln["custom_value"], "custom_key": ln["custom_key"],
                                       "custom_value": ln["custom_value"], "ad_unit_name": ln["ad_unit_name"],
                                       "revenue_gross": ln["revenue"], "revenue_client": ln["revenue_client"],
                                       "impressions": ln["impressions"]})

    def joinads(self) -> None:
        c = self.c
        self._dup_marca = _iso(_local(self.hoje, 8, 15, 30))
        self._esquema_marca = _iso(_local(self.hoje, 6, 15, 30))
        sub_marca = _local(self.hoje, 10, 15, 30)
        for dia in (self.ontem, self.hoje):
            for h in range(6, 23, 2):
                slot = _local(dia, h, 15)
                if slot > self.agora:
                    continue
                if c.joinads_intraday_parado and slot > _local(self.ontem, 18, 15):
                    continue
                inicio = slot + timedelta(seconds=30)
                avisos = None
                status = "completed"
                if c.substituicao and inicio == sub_marca:
                    avisos = [{"endpoint": "key_value_campaign_adunit", "code": "custom_key_substituted",
                               "expected": "utm_campaign", "received": "utm_source"}]
                    status = "partial"
                run = self._run_joinads(inicio, (dia, dia), status, avisos)
                self._dia_joinads(run, dia, (h - 5) / 18, inicio + timedelta(seconds=60), 0)
        for dia in (self.ontem, self.hoje):
            slot = _local(dia, 6, 20)
            inicio = slot + timedelta(seconds=30)
            jan = (dia - timedelta(days=7), dia - timedelta(days=1))
            run = self._run_joinads(inicio, jan)
            for k in range(7):
                alvo = jan[0] + timedelta(days=k)
                self._dia_joinads(run, alvo, 1.0, inicio + timedelta(seconds=60), k)

    # ------------------------------------------------------------------ raw_events (sensor)

    def sensor(self) -> None:
        pagas_por_dia = {self.ontem: 15, self.hoje: 13}
        for dia, n_pagas in pagas_por_dia.items():
            fim_h = 21 if dia == self.ontem else 11
            for k in range(n_pagas + 10 + 5):
                ts = _local(dia, 6 + (k * 7) % (fim_h - 6), (k * 13) % 60, k % 60)
                if k < n_pagas:
                    utm = {"paid": 1, "source": "google", "medium": "cpc", "term": "x"}
                    if not self.c.sensor_sem_campanha:
                        utm["campaign"] = CAMPANHAS[k % 5]
                    nome, payload = "volc_sensor_ready", {"utm": utm, "v": 3}
                elif k < n_pagas + 10:
                    nome, payload = "volc_sensor_ready", {"utm": {"paid": 0}, "v": 3}
                else:
                    nome, payload = "volc_page_view", {"utm": {"paid": 1, "campaign": "999"}}
                self.t["raw_events"].append({
                    "sid": "%016x" % self.rng.getrandbits(64), "pid": "%08x" % self.rng.getrandbits(32),
                    "event_name": nome, "ts": _iso(ts), "ts_sec": int(ts.timestamp()), "payload": payload,
                })

    def series_deriva(self) -> dict[str, list[float | None]]:
        import numpy as np

        from .deriva import _serie_sintetica

        rng = np.random.default_rng(self.rng.getrandbits(32))
        series = {}
        for i, cp in enumerate(CAMPANHAS):
            x = _serie_sintetica(rng, 35, 0.3, 0.05)
            if self.c.deriva_serie and i == 0:
                x[28:] = np.round(x[28:] * 0.1)  # quebra: custo despenca para 10%
            series[f"{CONTA}:{cp}"] = [float(v) for v in x]
        return series


def gerar_tabelas(seed: int = 20261016, cenario: str | Cenario = "producao_conhecida",
                  agora: datetime = AGORA_PADRAO) -> dict[str, list[dict]]:
    c = CENARIOS[cenario] if isinstance(cenario, str) else cenario
    g = _Gerador(seed, c, agora)
    g.google()
    g.joinads()
    g.sensor()
    return g.t


def gerar_series_deriva(seed: int = 20261016, cenario: str | Cenario = "producao_conhecida",
                        agora: datetime = AGORA_PADRAO) -> dict[str, list[float | None]]:
    c = CENARIOS[cenario] if isinstance(cenario, str) else cenario
    return _Gerador(seed, c, agora).series_deriva()
