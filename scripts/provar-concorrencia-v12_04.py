#!/usr/bin/env python3
"""Contraprova concorrente da RPC volc_registrar_gads_campanha_dia.

Duas ou mais sessões PostgreSQL reais, sincronizadas por advisory locks e
triggers de barreira — não por sleep. Nunca fala com o Supabase oficial.
O container Docker é exclusivo desta execução e só ele é removido no fim.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from typing import Any

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOCK_NS = 120417  # namespace exclusivo do runner (não colide com 120404/120405 da RPC)
LOCK_TOCTOU = 12
LOCK_LEDGER = 13
RPC_LOCK_IDEMP = 120405

SHA = "a" * 64


class Falhou(Exception):
    pass


def _run(cmd: list[str], *, input_text: str | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


class Cluster:
    def __init__(self, image: str, name: str) -> None:
        self.image = image
        self.name = name
        self.pg_version = ""

    def start(self) -> None:
        r = _run(
            [
                "docker", "run", "-d", "--name", self.name,
                "-e", "POSTGRES_PASSWORD=descartavel",
                "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                self.image,
            ]
        )
        if r.returncode != 0:
            raise SystemExit(f"docker run falhou: {r.stderr}")
        pronto = False
        for _ in range(90):
            logs = _run(["docker", "logs", self.name], timeout=20)
            if "PostgreSQL init process complete" in (logs.stdout + logs.stderr):
                ping = self.psql("select 1", timeout=10)
                if ping.returncode == 0 and ping.stdout.strip() == "1":
                    pronto = True
                    break
            time.sleep(1)
        if not pronto:
            tail = _run(["docker", "logs", self.name], timeout=20)
            raise SystemExit("cluster descartável não subiu:\n" + (tail.stderr + tail.stdout)[-2000:])
        self.pg_version = self.q("show server_version")

    def stop(self) -> None:
        _run(["docker", "rm", "-f", self.name], timeout=30)

    def psql(self, sql: str, *, timeout: int = 60, on_error_stop: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = [
            "docker", "exec", "-i", self.name,
            "psql", "-U", "postgres", "-d", "postgres", "-X", "-q", "-At",
        ]
        if on_error_stop:
            cmd.extend(["-v", "ON_ERROR_STOP=1"])
        body = sql if sql.rstrip().endswith(";") else sql + ";"
        return _run(cmd, input_text=body, timeout=timeout)

    def q(self, sql: str, timeout: int = 30) -> str:
        r = self.psql(sql, timeout=timeout)
        if r.returncode != 0:
            raise Falhou(f"psql falhou ({r.returncode}): {r.stderr or r.stdout}")
        return r.stdout.strip()

    def apply_file(self, path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            sql = fh.read()
        r = self.psql(sql, timeout=120)
        if r.returncode != 0:
            raise SystemExit(f"falha aplicando {path}: {r.stderr or r.stdout}")


def linha(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "customer_id": "8017851692",
        "campaign_id": "24155134757",
        "metric_date": "2026-08-30",
        "colhida_em": "2026-08-31T09:00:00Z",
        "currency_code": "BRL",
        "segmentos": {},
        "campaign_name": "Maquininha",
        "impressoes": 1200,
        "cliques": 35,
        "custo_micros": 15230000,
        "conversoes": 2,
        "ctr": 0.0291,
    }
    base.update(patch)
    return base


def linha_empate(campaign_id: str, **patch: Any) -> dict[str, Any]:
    """Fato persistível completo para empate total (não o subconjunto Hermes)."""
    base = linha(
        campaign_id=campaign_id,
        colhida_em="2026-08-31T09:00:00Z",
        campaign_name="Maquininha",
        campaign_status="ENABLED",
        advertising_channel_type="SEARCH",
        impressoes=11,
        cliques=2,
        interacoes=2,
        custo_micros=1000,
        conversoes=1,
        todas_conversoes=1,
        valor_conversoes=10,
        valor_todas_conversoes=10,
        ctr=0.1,
        cpc_medio_micros=500,
        custo_por_conversao_micros=1000,
        search_impression_share=0.5,
        search_budget_lost_impression_share=0.1,
        search_rank_lost_impression_share=0.2,
        search_top_impression_share=0.3,
        search_absolute_top_impression_share=0.05,
        search_click_share=0.4,
        search_exact_match_impression_share=0.6,
        top_impression_percentage=0.7,
        absolute_top_impression_percentage=0.2,
        segmentos={"device": "MOBILE"},
        metricas_extras={"origem_api": "search"},
    )
    base.update(patch)
    return base


def doc(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "chave_idempotencia": "base|1",
        "execucao_chave": "gads_dia_d1:D-1:2026-08-30:06",
        "fonte": "n8n",
        "job": "gads_dia_d1",
        "disparo": "agenda",
        "api_versao": "v25",
        "contrato_versao": "gads-dia-v1",
        "contrato_sha256": SHA,
        "tipo_lote": "contas",
        "lote_ordinal": 1,
        "origem_janela": "D-1",
        "janela_inicio": "2026-08-30",
        "janela_fim": "2026-08-30",
        "iniciada_em": "2026-08-31T09:00:00Z",
        "encerrada_em": "2026-08-31T09:00:05Z",
        "duracao_ms": 5000,
        "batimento_em": "2026-08-31T09:00:05Z",
        "resultado": "ok",
        "contas_tentadas": ["8017851692"],
        "contas_aceitas": ["8017851692"],
        "projetar_compat": False,
        "linhas": [linha()],
    }
    base.update(patch)
    return base


class LockHolder:
    """Sessão viva: advisory lock de sessão + pg_sleep, liberado por terminate."""

    def __init__(self, cluster: Cluster) -> None:
        self.cluster = cluster
        self.proc: subprocess.Popen[str] | None = None
        self.app = f"volc-holder-{os.getpid()}-{threading.get_ident()}"
        self.held: tuple[int, int] | None = None

    def hold(self, classid: int, objid: int) -> None:
        sql = (
            f"SET application_name = '{self.app}'; "
            f"SELECT pg_advisory_lock({classid}, {objid}); "
            "SELECT pg_sleep(180);"
        )
        self.proc = subprocess.Popen(
            [
                "docker", "exec", self.cluster.name,
                "psql", "-U", "postgres", "-d", "postgres", "-X", "-q", "-At",
                "-c", sql,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        q = (
            "SELECT count(*) FROM pg_locks "
            f"WHERE locktype='advisory' AND classid={classid} AND objid={objid} "
            "AND objsubid IN (1,2) AND granted"
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            if int(self.cluster.q(q) or "0") >= 1:
                self.held = (classid, objid)
                return
            if self.proc.poll() is not None:
                err = self.proc.stderr.read() if self.proc.stderr else ""
                raise Falhou(f"holder saiu cedo: {err}")
            time.sleep(0.03)
        raise Falhou(f"holder não concedeu lock ({classid},{objid})")

    def release(self, classid: int, objid: int) -> None:
        self.cluster.q(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE application_name = '{self.app}'"
        )
        if self.proc is not None:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.held = None

    def close(self) -> None:
        if self.held is not None:
            try:
                self.release(*self.held)
            except Exception:
                pass
        elif self.proc is not None and self.proc.poll() is None:
            self.proc.kill()


def worker_sql(
    who: str,
    documento: dict[str, Any],
    *,
    hold_origem: str | None = None,
    hold_campaign: str | None = None,
    hold_ledger: bool = False,
    extra_pre: str = "",
    extra_post: str = "",
) -> str:
    sets = [
        "SET statement_timeout = '25s'",
        "SET lock_timeout = '20s'",
        f"SET application_name = '{who}'",
    ]
    if hold_origem:
        sets.append(f"SELECT set_config('volc.p10t17_hold_origem', '{hold_origem}', false)")
    if hold_campaign:
        sets.append(f"SELECT set_config('volc.p10t17_hold_campaign', '{hold_campaign}', false)")
    if hold_ledger:
        sets.append("SELECT set_config('volc.p10t17_hold_ledger', 'contas', false)")
    payload = json.dumps(documento, ensure_ascii=False, separators=(",", ":"))
    # Dollar-quote: o JSON de prova não contém a tag.
    return "\n".join(s + ";" for s in sets) + f"""
{extra_pre}
DO $outer$
DECLARE
  r jsonb;
  estado text;
  msg text;
BEGIN
  BEGIN
    r := public.volc_registrar_gads_campanha_dia($json${payload}$json$::jsonb);
    INSERT INTO public.volc_p10t17_out(who, ok, sqlstate, payload)
    VALUES ('{who}', true, '00000', r);
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS estado = RETURNED_SQLSTATE, msg = MESSAGE_TEXT;
    INSERT INTO public.volc_p10t17_out(who, ok, sqlstate, payload)
    VALUES ('{who}', false, estado, jsonb_build_object('message', msg));
  END;
END
$outer$;
{extra_post}
"""


def spawn_worker(cluster: Cluster, sql: str, bucket: dict[str, Any], key: str) -> threading.Thread:
    def run() -> None:
        try:
            r = cluster.psql(sql, timeout=40, on_error_stop=True)
            bucket[key] = {
                "returncode": r.returncode,
                "stdout": r.stdout,
                "stderr": r.stderr,
            }
        except subprocess.TimeoutExpired as exc:
            bucket[key] = {"returncode": 124, "stdout": "", "stderr": f"TIMEOUT: {exc}"}
        except Exception as exc:  # noqa: BLE001 — o runner materializa, não engole
            bucket[key] = {"returncode": 99, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}

    t = threading.Thread(target=run, name=key, daemon=True)
    t.start()
    return t


def wait_advisory_waiter(cluster: Cluster, objid: int, timeout: float = 12.0) -> None:
    deadline = time.time() + timeout
    sql = (
        "SELECT count(*) FROM pg_locks "
        f"WHERE locktype='advisory' AND classid={LOCK_NS} AND objid={objid} "
        "AND objsubid IN (1,2) AND NOT granted"
    )
    while time.time() < deadline:
        n = int(cluster.q(sql) or "0")
        if n >= 1:
            return
        time.sleep(0.03)
    raise Falhou(f"ninguém esperou o advisory lock ({LOCK_NS},{objid}) em {timeout}s")


def wait_idemp_waiter(cluster: Cluster, chave: str, timeout: float = 12.0) -> dict[str, Any]:
    """Espera B aparecer em pg_locks como waiter do advisory 120405 da chave."""
    lit = "'" + chave.replace("'", "''") + "'"
    sql = (
        "SELECT json_build_object("
        " 'holders', count(*) FILTER (WHERE l.granted),"
        " 'waiters', count(*) FILTER (WHERE NOT l.granted),"
        " 'classid', 120405,"
        " 'objid', min(l.objid),"
        " 'hashtext', hashtext('v12_04:idemp:' || " + lit + "),"
        " 'locks', coalesce(json_agg(json_build_object("
        "    'pid', l.pid, 'granted', l.granted, 'objsubid', l.objsubid,"
        "    'application_name', a.application_name"
        "  ) ORDER BY l.granted DESC, l.pid), '[]'::json)"
        ") "
        "FROM pg_locks l "
        "LEFT JOIN pg_stat_activity a ON a.pid = l.pid "
        "WHERE l.locktype = 'advisory' AND l.classid = 120405 "
        "AND l.objid = hashtext('v12_04:idemp:' || " + lit + ")::oid "
        "AND l.objsubid IN (1, 2)"
    )
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        raw = cluster.q(sql) or "{}"
        last = json.loads(raw)
        if int(last.get("holders") or 0) >= 1 and int(last.get("waiters") or 0) >= 1:
            return last
        time.sleep(0.03)
    raise Falhou(
        f"B não esperou o advisory classid={RPC_LOCK_IDEMP} da chave {chave!r}: {last}"
    )


def out_rows(cluster: Cluster) -> list[dict[str, Any]]:
    raw = cluster.q(
        "SELECT coalesce(json_agg(json_build_object("
        "'who', who, 'ok', ok, 'sqlstate', sqlstate, 'payload', payload"
        ") ORDER BY who), '[]'::json) FROM public.volc_p10t17_out"
    )
    return json.loads(raw or "[]")


def out_by_who(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["who"]: r for r in rows}


def reset_data(cluster: Cluster) -> None:
    cluster.q(
        "TRUNCATE public.google_ads_campanha_dia, "
        "public.trafego_coleta_execucao, "
        "public.volc_p10t17_out"
    )


def fato(cluster: Cluster, campaign_id: str, customer_id: str = "8017851692") -> dict[str, Any]:
    raw = cluster.q(
        "SELECT row_to_json(t) FROM ("
        "SELECT customer_id, campaign_id, origem_janela, precedencia, colhida_em, "
        "impressoes, cliques, conversoes, execucao_id, campaign_name, "
        "search_click_share, metricas_extras "
        f"FROM public.google_ads_campanha_dia "
        f"WHERE campaign_id = '{campaign_id}' AND customer_id = '{customer_id}'"
        ") t"
    )
    if not raw:
        return {}
    return json.loads(raw)


def n_fatos(cluster: Cluster, **where: str) -> int:
    clauses = " AND ".join(f"{k} = '{v}'" for k, v in where.items())
    return int(cluster.q(f"SELECT count(*) FROM public.google_ads_campanha_dia WHERE {clauses}"))


def n_recibos(cluster: Cluster, **where: str) -> int:
    clauses = " AND ".join(f"{k} = '{v}'" for k, v in where.items())
    return int(cluster.q(f"SELECT count(*) FROM public.trafego_coleta_execucao WHERE {clauses}"))


def setup_schema(cluster: Cluster) -> None:
    cluster.q(
        "CREATE ROLE anon NOLOGIN; "
        "CREATE ROLE authenticated NOLOGIN; "
        "CREATE ROLE service_role NOLOGIN BYPASSRLS; "
        "GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role; "
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT ALL ON TABLES TO anon, authenticated, service_role; "
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role"
    )
    cluster.apply_file(os.path.join(RAIZ, "supabase/migrations/v9_01_trafego_inventario.sql"))
    cluster.apply_file(os.path.join(RAIZ, "supabase/migrations/v12_04_gads_fato_canonico_dia.sql"))
    cluster.q(
        """
        CREATE TABLE public.volc_p10t17_out (
          who text NOT NULL,
          ok boolean NOT NULL,
          sqlstate text NOT NULL,
          payload jsonb,
          registrada_em timestamptz NOT NULL DEFAULT now()
        );
        CREATE OR REPLACE FUNCTION public.volc_p10t17_gate()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $fn$
        BEGIN
          IF TG_TABLE_NAME = 'google_ads_campanha_dia' THEN
            IF current_setting('volc.p10t17_hold_origem', true) = NEW.origem_janela THEN
              PERFORM pg_advisory_xact_lock(120417, 12);
            END IF;
            IF current_setting('volc.p10t17_hold_campaign', true) = NEW.campaign_id THEN
              PERFORM pg_advisory_xact_lock(120417, 12);
            END IF;
          ELSIF TG_TABLE_NAME = 'trafego_coleta_execucao' THEN
            IF current_setting('volc.p10t17_hold_ledger', true) = 'contas'
               AND NEW.tipo_lote = 'contas' THEN
              PERFORM pg_advisory_xact_lock(120417, 13);
            END IF;
          END IF;
          RETURN NEW;
        END
        $fn$;
        CREATE TRIGGER volc_p10t17_gate_fato
          BEFORE INSERT OR UPDATE ON public.google_ads_campanha_dia
          FOR EACH ROW EXECUTE FUNCTION public.volc_p10t17_gate();
        CREATE TRIGGER volc_p10t17_gate_ledger
          BEFORE INSERT ON public.trafego_coleta_execucao
          FOR EACH ROW EXECUTE FUNCTION public.volc_p10t17_gate();
        """
    )


def run_toctou(
    cluster: Cluster,
    *,
    inferior: dict[str, Any],
    superior: dict[str, Any],
    hold_origem: str,
    campaign_id: str,
    expect_origem: str,
    expect_impressoes: int,
) -> dict[str, Any]:
    """Inferior chega no INSERT (SELECT já ocorreu), superior commita, inferior termina."""
    reset_data(cluster)
    holder = LockHolder(cluster)
    bucket: dict[str, Any] = {}
    try:
        holder.hold(LOCK_NS, LOCK_TOCTOU)
        t_inf = spawn_worker(
            cluster,
            worker_sql("inferior", inferior, hold_origem=hold_origem),
            bucket,
            "inferior",
        )
        wait_advisory_waiter(cluster, LOCK_TOCTOU)
        t_sup = spawn_worker(cluster, worker_sql("superior", superior), bucket, "superior")
        t_sup.join(timeout=20)
        if t_sup.is_alive():
            raise Falhou("superior não terminou enquanto o inferior estava na barreira")
        holder.release(LOCK_NS, LOCK_TOCTOU)
        t_inf.join(timeout=20)
        if t_inf.is_alive():
            raise Falhou("inferior não terminou depois de liberar a barreira")
    finally:
        holder.close()

    f = fato(cluster, campaign_id)
    rows = out_by_who(out_rows(cluster))
    if f.get("origem_janela") != expect_origem:
        raise Falhou(
            f"fato rebaixado: origem={f.get('origem_janela')!r} "
            f"impressoes={f.get('impressoes')!r} esperado {expect_origem}/{expect_impressoes}; "
            f"workers={rows}"
        )
    imp = f.get("impressoes")
    if imp is None or int(imp) != expect_impressoes:
        raise Falhou(f"impressoes={imp!r} esperado {expect_impressoes}; {rows}")
    if n_fatos(cluster, campaign_id=campaign_id) != 1:
        raise Falhou("fato duplicado")
    return {"fato": f, "out": rows, "workers": bucket}


def case_a(cluster: Cluster) -> None:
    cid = "1710000001"
    inferior = doc(
        chave_idempotencia="A-d0|1",
        execucao_chave="A-d0",
        job="gads_dia_d0",
        origem_janela="D0",
        janela_inicio="2026-08-30",
        janela_fim="2026-08-30",
        linhas=[linha(campaign_id=cid, metric_date="2026-08-30",
                      colhida_em="2026-08-30T12:00:00Z", impressoes=10)],
    )
    superior = doc(
        chave_idempotencia="A-d1|1",
        execucao_chave="A-d1",
        job="gads_dia_d1",
        origem_janela="D-1",
        linhas=[linha(campaign_id=cid, metric_date="2026-08-30",
                      colhida_em="2026-08-31T09:00:00Z", impressoes=99)],
    )
    result = run_toctou(
        cluster, inferior=inferior, superior=superior, hold_origem="D0",
        campaign_id=cid, expect_origem="D-1", expect_impressoes=99,
    )
    inf = result["out"]["inferior"]
    if inf["ok"] is not True:
        raise Falhou(f"D0 deveria gravar recibo preterido, não abortar: {inf}")
    if int(inf["payload"].get("linhas_preteridas") or 0) != 1:
        raise Falhou(f"D0 deveria ser preterida: {inf}")
    if int(inf["payload"].get("linhas_aceitas") or 0) != 0:
        raise Falhou(f"D0 não pode contar aceita: {inf}")
    sup = result["out"]["superior"]
    if int(sup["payload"].get("linhas_aceitas") or 0) != 1:
        raise Falhou(f"D-1 deveria ser aceita: {sup}")


def case_b(cluster: Cluster) -> None:
    cid = "1710000002"
    inferior = doc(
        chave_idempotencia="B-d1|1",
        execucao_chave="B-d1",
        origem_janela="D-1",
        linhas=[linha(campaign_id=cid, colhida_em="2026-08-31T09:00:00Z", impressoes=20)],
    )
    superior = doc(
        chave_idempotencia="B-bf|1",
        execucao_chave="B-bf",
        job="gads_backfill",
        origem_janela="backfill",
        linhas=[linha(campaign_id=cid, colhida_em="2026-09-01T00:00:00Z", impressoes=77)],
    )
    run_toctou(
        cluster, inferior=inferior, superior=superior, hold_origem="D-1",
        campaign_id=cid, expect_origem="backfill", expect_impressoes=77,
    )


def case_c(cluster: Cluster) -> None:
    cid = "1710000003"
    cedo = doc(
        chave_idempotencia="C-early|1",
        execucao_chave="C-early",
        origem_janela="D-1",
        linhas=[linha(campaign_id=cid, colhida_em="2026-08-31T09:00:00Z", impressoes=1)],
    )
    tarde = doc(
        chave_idempotencia="C-late|1",
        execucao_chave="C-late",
        origem_janela="D-1",
        linhas=[linha(campaign_id=cid, colhida_em="2026-08-31T11:00:00Z", impressoes=2)],
    )
    # A colheita mais antiga é a inferior no desempate.
    result = run_toctou(
        cluster, inferior=cedo, superior=tarde, hold_origem="D-1",
        campaign_id=cid, expect_origem="D-1", expect_impressoes=2,
    )
    f = result["fato"]
    if not str(f.get("colhida_em", "")).startswith("2026-08-31T11:00:00"):
        raise Falhou(f"colhida_em perdeu o desempate: {f}")


def case_d(cluster: Cluster) -> None:
    """Fonte inferior iniciada antes e commitada depois — não rebaixa o superior."""
    cid = "1710000004"
    inferior = doc(
        chave_idempotencia="D-d0|1",
        execucao_chave="D-d0",
        job="gads_dia_d0",
        origem_janela="D0",
        janela_inicio="2026-08-30",
        janela_fim="2026-08-30",
        linhas=[linha(campaign_id=cid, colhida_em="2026-09-02T00:00:00Z", impressoes=3)],
    )
    superior = doc(
        chave_idempotencia="D-d1|1",
        execucao_chave="D-d1",
        origem_janela="D-1",
        linhas=[linha(campaign_id=cid, colhida_em="2026-08-31T09:00:00Z", impressoes=50)],
    )
    run_toctou(
        cluster, inferior=inferior, superior=superior, hold_origem="D0",
        campaign_id=cid, expect_origem="D-1", expect_impressoes=50,
    )


def _parallel_rpc(cluster: Cluster, a: dict[str, Any], b: dict[str, Any],
                  who_a: str = "a", who_b: str = "b",
                  **hold_a: Any) -> dict[str, dict[str, Any]]:
    reset_data(cluster)
    bucket: dict[str, Any] = {}
    t1 = spawn_worker(cluster, worker_sql(who_a, a, **hold_a), bucket, who_a)
    t2 = spawn_worker(cluster, worker_sql(who_b, b), bucket, who_b)
    t1.join(timeout=25)
    t2.join(timeout=25)
    if t1.is_alive() or t2.is_alive():
        raise Falhou(f"worker travou: alive a={t1.is_alive()} b={t2.is_alive()} bucket={bucket}")
    for key, val in bucket.items():
        if val["returncode"] not in (0, 1) and "TIMEOUT" in (val.get("stderr") or ""):
            raise Falhou(f"{key} timeout: {val}")
    return out_by_who(out_rows(cluster))


def case_e(cluster: Cluster) -> None:
    """A toma 120405 e para no INSERT; B é observado em pg_locks esperando 120405."""
    cid = "1710000005"
    chave = "E-same|1"
    payload = doc(
        chave_idempotencia=chave,
        execucao_chave="E-same",
        linhas=[linha(campaign_id=cid, impressoes=11)],
    )
    reset_data(cluster)
    holder = LockHolder(cluster)
    bucket: dict[str, Any] = {}
    try:
        holder.hold(LOCK_NS, LOCK_TOCTOU)
        t_a = spawn_worker(
            cluster, worker_sql("a", payload, hold_origem="D-1"), bucket, "a"
        )
        wait_advisory_waiter(cluster, LOCK_TOCTOU)
        t_b = spawn_worker(
            cluster,
            worker_sql("b", json.loads(json.dumps(payload))),
            bucket,
            "b",
        )
        evidencia = wait_idemp_waiter(cluster, chave)
        if not t_b.is_alive():
            raise Falhou(
                f"B concluiu antes da sobreposição no lock 120405: {evidencia} bucket={bucket}"
            )
        print("          EVIDENCIA_E=" + json.dumps(evidencia, ensure_ascii=False, sort_keys=True))
        holder.release(LOCK_NS, LOCK_TOCTOU)
        t_a.join(timeout=20)
        t_b.join(timeout=20)
        if t_a.is_alive() or t_b.is_alive():
            raise Falhou(f"worker travou depois da barreira: bucket={bucket}")
    finally:
        holder.close()
    rows = out_by_who(out_rows(cluster))
    for key, val in bucket.items():
        blob = (val.get("stdout") or "") + (val.get("stderr") or "")
        if "23505" in blob:
            raise Falhou(f"{key} expôs 23505 no cliente: {val}")
    oks = [r for r in rows.values() if r["ok"]]
    if len(oks) != 2:
        raise Falhou(f"as duas chamadas idênticas devem concluir: {rows}")
    if any(r.get("sqlstate") == "23505" for r in rows.values()):
        raise Falhou(f"23505 exposto: {rows}")
    execs = {r["payload"]["execucao_id"] for r in oks}
    if len(execs) != 1:
        raise Falhou(f"execucao_id divergiu: {execs}")
    repetidas = sorted(bool(r["payload"].get("repetida")) for r in oks)
    if repetidas != [False, True]:
        raise Falhou(f"esperado uma aplicada e uma repetida: {rows}")
    if n_recibos(cluster, chave_idempotencia=chave) != 1:
        raise Falhou("recibo duplicado")
    if n_fatos(cluster, campaign_id=cid) != 1:
        raise Falhou("fato duplicado")


def case_f(cluster: Cluster) -> None:
    cid = "1710000006"
    a = doc(
        chave_idempotencia="F-div|1",
        execucao_chave="F-div",
        linhas=[linha(campaign_id=cid, impressoes=4)],
    )
    b = doc(
        chave_idempotencia="F-div|1",
        execucao_chave="F-div",
        linhas=[linha(campaign_id=cid, impressoes=8)],
    )
    reset_data(cluster)
    holder = LockHolder(cluster)
    bucket: dict[str, Any] = {}
    try:
        holder.hold(LOCK_NS, LOCK_TOCTOU)
        t_a = spawn_worker(
            cluster, worker_sql("a", a, hold_origem="D-1"), bucket, "a"
        )
        wait_advisory_waiter(cluster, LOCK_TOCTOU)
        t_b = spawn_worker(cluster, worker_sql("b", b), bucket, "b")
        t_b.join(timeout=15)
        if t_b.is_alive():
            # RPC nova: B espera o lock de idempotência de A. Libera A e deixa B recusar.
            holder.release(LOCK_NS, LOCK_TOCTOU)
            t_a.join(timeout=20)
            t_b.join(timeout=20)
        else:
            holder.release(LOCK_NS, LOCK_TOCTOU)
            t_a.join(timeout=20)
    finally:
        holder.close()
    rows = out_by_who(out_rows(cluster))
    if n_recibos(cluster, chave_idempotencia="F-div|1") != 1:
        raise Falhou(f"devia haver um recibo: {rows}")
    if n_fatos(cluster, campaign_id=cid) != 1:
        raise Falhou("fato duplicado ou órfão")
    impressoes = int(fato(cluster, cid)["impressoes"])
    if impressoes not in (4, 8):
        raise Falhou(f"impressoes inesperadas: {impressoes}")
    recusadas = [r for r in rows.values() if r["ok"] is False]
    aceitas = [r for r in rows.values() if r["ok"] is True]
    if len(aceitas) != 1 or len(recusadas) != 1:
        raise Falhou(f"exatamente uma versão aceita e uma recusada: {rows}")
    msg = json.dumps(recusadas[0].get("payload") or {})
    if "CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE" not in msg:
        raise Falhou(f"recusa precisa ser nominal, não {recusadas[0]}")
    # A versão recusada não pode ter deixado o número dela se a aceita foi a outra.
    aceita_imp = int(aceitas[0]["payload"].get("linhas_aceitas") or 0)
    if aceita_imp != 1:
        raise Falhou(f"vencedora deveria aceitar 1 linha: {aceitas[0]}")


def case_g(cluster: Cluster) -> None:
    cid_a = "1710000007"
    cid_b = "1710000008"
    a = doc(
        chave_idempotencia="G-k1|1",
        execucao_chave="G-slot",
        linhas=[linha(campaign_id=cid_a, impressoes=1)],
    )
    b = doc(
        chave_idempotencia="G-k2|1",
        execucao_chave="G-slot",
        linhas=[linha(campaign_id=cid_b, impressoes=2)],
    )
    rows = _parallel_rpc(cluster, a, b)
    oks = [r for r in rows.values() if r["ok"]]
    kos = [r for r in rows.values() if not r["ok"]]
    if len(oks) != 1 or len(kos) != 1:
        raise Falhou(f"um vence, o outro falha fechado: {rows}")
    msg = json.dumps(kos[0].get("payload") or {})
    if "LOTE_JA_OCUPADO" not in msg and kos[0]["sqlstate"] not in {"23505"}:
        raise Falhou(f"falha fechada esperada: {kos[0]}")
    if n_recibos(cluster, execucao_chave="G-slot") != 1:
        raise Falhou("dois recibos no mesmo slot")
    total = n_fatos(cluster, campaign_id=cid_a) + n_fatos(cluster, campaign_id=cid_b)
    if total != 1:
        raise Falhou(f"órfão: fatos={total} rows={rows}")


def case_h(cluster: Cluster) -> None:
    cid = "1710000009"
    d0 = doc(
        chave_idempotencia="H-d0|1",
        execucao_chave="H-d0",
        job="gads_dia_d0",
        origem_janela="D0",
        janela_inicio="2026-08-30",
        janela_fim="2026-08-30",
        linhas=[linha(campaign_id=cid, colhida_em="2026-08-30T10:00:00Z", impressoes=5)],
    )
    d1 = doc(
        chave_idempotencia="H-d1|1",
        execucao_chave="H-d1",
        origem_janela="D-1",
        linhas=[linha(campaign_id=cid, colhida_em="2026-08-31T10:00:00Z", impressoes=9)],
    )
    run_toctou(
        cluster, inferior=d0, superior=d1, hold_origem="D0",
        campaign_id=cid, expect_origem="D-1", expect_impressoes=9,
    )
    rows = out_by_who(out_rows(cluster))
    if int(rows["superior"]["payload"]["linhas_aceitas"]) != 1:
        raise Falhou("H: D-1 não aceitou")
    if int(rows["inferior"]["payload"]["linhas_preteridas"]) != 1:
        raise Falhou("H: D0 não foi preterida")
    f = fato(cluster, cid)
    if f["origem_janela"] != "D-1":
        raise Falhou(f"H: recibo e fato divergem: {f} {rows}")


def case_i(cluster: Cluster) -> None:
    cid = "1710000010"
    lote = doc(
        chave_idempotencia="I-lote|1",
        execucao_chave="I-exec",
        linhas=[linha(campaign_id=cid, impressoes=13)],
    )
    fecha_falso = doc(
        chave_idempotencia="I-fecha|0",
        execucao_chave="I-exec",
        tipo_lote="fechamento",
        lote_ordinal=0,
        linhas=[],
        linhas_aceitas=0,
        linhas_preteridas=0,
        linhas_rejeitadas=0,
    )
    fecha_honesto = doc(
        chave_idempotencia="I-fecha|0",
        execucao_chave="I-exec",
        tipo_lote="fechamento",
        lote_ordinal=0,
        linhas=[],
        linhas_aceitas=1,
        linhas_preteridas=0,
        linhas_rejeitadas=0,
    )
    reset_data(cluster)
    holder = LockHolder(cluster)
    bucket: dict[str, Any] = {}
    try:
        holder.hold(LOCK_NS, LOCK_LEDGER)
        t_lote = spawn_worker(
            cluster, worker_sql("lote", lote, hold_ledger=True), bucket, "lote"
        )
        wait_advisory_waiter(cluster, LOCK_LEDGER)
        t_fecha = spawn_worker(cluster, worker_sql("fecha", fecha_falso), bucket, "fecha")
        t_fecha.join(timeout=3)
        if not t_fecha.is_alive():
            mid = out_by_who(out_rows(cluster)).get("fecha", {})
            if mid.get("ok"):
                raise Falhou(
                    "fechamento declarou conclusão enquanto o lote ainda não tinha commitado"
                )
        holder.release(LOCK_NS, LOCK_LEDGER)
        t_lote.join(timeout=20)
        t_fecha.join(timeout=20)
    finally:
        holder.close()
    rows = out_by_who(out_rows(cluster))
    if not rows.get("lote", {}).get("ok"):
        raise Falhou(f"lote deveria persistir: {rows}")
    fecha = rows.get("fecha")
    if fecha and fecha.get("ok"):
        raise Falhou(f"fechamento zero não pode fechar sobre lote já escrito: {fecha}")
    # Depois da escrita durável, o fechamento honesto funciona.
    r = cluster.psql(worker_sql("fecha2", fecha_honesto), timeout=20)
    if r.returncode != 0:
        raise Falhou(f"fechamento honesto falhou: {r.stderr}")
    rows2 = out_by_who(out_rows(cluster))
    if not rows2.get("fecha2", {}).get("ok"):
        raise Falhou(f"fechamento honesto recusado: {rows2}")
    if n_recibos(cluster, execucao_chave="I-exec", tipo_lote="fechamento") != 1:
        raise Falhou("fechamento duplicado ou ausente")


def case_j(cluster: Cluster) -> None:
    cid = "1710000011"
    ruim = doc(
        chave_idempotencia="J-fail|1",
        execucao_chave="J-fail",
        contrato_sha256="zzz",  # viola o CHECK depois dos fatos
        linhas=[linha(campaign_id=cid, impressoes=21, conversoes=None)],
    )
    reset_data(cluster)
    r = cluster.psql(worker_sql("j", ruim), timeout=20)
    if r.returncode != 0:
        raise Falhou(f"worker J quebrou o psql: {r.stderr}")
    rows = out_by_who(out_rows(cluster))
    if rows["j"]["ok"]:
        raise Falhou("J deveria recusar o recibo inválido")
    if n_fatos(cluster, campaign_id=cid) != 0:
        raise Falhou("J deixou fato órfão")
    if n_recibos(cluster, chave_idempotencia="J-fail|1") != 0:
        raise Falhou("J deixou recibo órfão")


def case_k(cluster: Cluster) -> None:
    cid = "1710000012"
    a = doc(
        chave_idempotencia="K-a|1",
        execucao_chave="K-a",
        linhas=[linha(customer_id="8017851692", campaign_id=cid, impressoes=1)],
    )
    b = doc(
        chave_idempotencia="K-b|1",
        execucao_chave="K-b",
        linhas=[linha(customer_id="7788990011", campaign_id=cid, impressoes=2)],
    )
    rows = _parallel_rpc(cluster, a, b)
    if not all(r["ok"] for r in rows.values()):
        raise Falhou(f"contas distintas não podem colidir: {rows}")
    if n_fatos(cluster, campaign_id=cid) != 2:
        raise Falhou("contaminação/colisão entre contas")
    fa = fato(cluster, cid, "8017851692")
    fb = fato(cluster, cid, "7788990011")
    if int(fa["impressoes"]) != 1 or int(fb["impressoes"]) != 2:
        raise Falhou(f"números cruzados: {fa} {fb}")


def case_l(cluster: Cluster) -> None:
    """Fato B commita enquanto o INSERT do fato A ainda está na barreira — sem lock global."""
    reset_data(cluster)
    holder = LockHolder(cluster)
    bucket: dict[str, Any] = {}
    a = doc(
        chave_idempotencia="L-a|1",
        execucao_chave="L-a",
        linhas=[linha(campaign_id="1710000013", impressoes=1)],
    )
    b = doc(
        chave_idempotencia="L-b|1",
        execucao_chave="L-b",
        linhas=[linha(campaign_id="1710000014", impressoes=2)],
    )
    try:
        holder.hold(LOCK_NS, LOCK_TOCTOU)
        t_a = spawn_worker(
            cluster, worker_sql("a", a, hold_campaign="1710000013"), bucket, "a"
        )
        wait_advisory_waiter(cluster, LOCK_TOCTOU)
        t_b = spawn_worker(cluster, worker_sql("b", b), bucket, "b")
        t_b.join(timeout=15)
        if t_b.is_alive():
            raise Falhou("fato distinto serializou atrás de um lock global/table lock")
        rows_mid = out_by_who(out_rows(cluster))
        if not rows_mid.get("b", {}).get("ok"):
            raise Falhou(f"B deveria ter commitado com A ainda na barreira: {rows_mid} {bucket.get('b')}")
        if n_fatos(cluster, campaign_id="1710000014") != 1:
            raise Falhou("B não persistiu durante a contenção de A")
        holder.release(LOCK_NS, LOCK_TOCTOU)
        t_a.join(timeout=15)
    finally:
        holder.close()
    rows = out_by_who(out_rows(cluster))
    if not rows.get("a", {}).get("ok"):
        raise Falhou(f"A deveria concluir depois da barreira: {rows}")


def case_m(cluster: Cluster, repeats: int) -> None:
    deadlocks = 0
    for i in range(repeats):
        try:
            case_a(cluster)
            case_c(cluster)
            case_e(cluster)
            case_g(cluster)
            case_k(cluster)
        except Falhou as exc:
            if "40P01" in str(exc) or "deadlock" in str(exc).lower():
                deadlocks += 1
                raise Falhou(f"deadlock na repetição {i}: {exc}") from exc
            raise
    if deadlocks:
        raise Falhou(f"{deadlocks} deadlocks em {repeats} ciclos")


def case_n(cluster: Cluster) -> None:
    cid = "1710000015"
    inferior = doc(
        chave_idempotencia="N-d0|1",
        execucao_chave="N-d0",
        job="gads_dia_d0",
        origem_janela="D0",
        janela_inicio="2026-08-30",
        janela_fim="2026-08-30",
        linhas=[linha(campaign_id=cid, conversoes=0, cliques=0, impressoes=0,
                      colhida_em="2026-08-30T12:00:00Z")],
    )
    superior = doc(
        chave_idempotencia="N-d1|1",
        execucao_chave="N-d1",
        origem_janela="D-1",
        linhas=[linha(campaign_id=cid, conversoes=None, cliques=0, impressoes=0,
                      colhida_em="2026-08-31T09:00:00Z")],
    )
    run_toctou(
        cluster, inferior=inferior, superior=superior, hold_origem="D0",
        campaign_id=cid, expect_origem="D-1", expect_impressoes=0,
    )
    f = fato(cluster, cid)
    raw = cluster.q(
        "SELECT (conversoes IS NULL), (cliques = 0 AND cliques IS NOT NULL), "
        "(impressoes = 0 AND impressoes IS NOT NULL) "
        f"FROM public.google_ads_campanha_dia WHERE campaign_id = '{cid}'"
    )
    parts = raw.split("|") if "|" in raw else raw.split()
    # -At with two bools: t|t|t or t\nt
    packed = raw.replace("\n", "|")
    if packed.count("t") < 3:
        raise Falhou(f"NULL/zero não preservados: fato={f} raw={raw!r} parts={parts}")


def case_o(cluster: Cluster) -> None:
    """Empate total de conteúdo idêntico: first-writer permanece, a outra é preterida."""
    cid = "1710000016"
    corpo = linha_empate(cid)
    gated = doc(
        chave_idempotencia="O-a|1",
        execucao_chave="O-a",
        origem_janela="D-1",
        linhas=[corpo],
    )
    first = doc(
        chave_idempotencia="O-b|1",
        execucao_chave="O-b",
        origem_janela="D-1",
        linhas=[json.loads(json.dumps(corpo))],
    )
    result = run_toctou(
        cluster, inferior=gated, superior=first, hold_origem="D-1",
        campaign_id=cid, expect_origem="D-1", expect_impressoes=11,
    )
    inf = result["out"]["inferior"]
    sup = result["out"]["superior"]
    if inf["ok"] is not True or sup["ok"] is not True:
        raise Falhou(f"empate idêntico deve gravar dois recibos coerentes: {result['out']}")
    if any(r.get("sqlstate") == "23505" for r in result["out"].values()):
        raise Falhou(f"23505 no empate idêntico: {result['out']}")
    if int(sup["payload"].get("linhas_aceitas") or 0) != 1:
        raise Falhou(f"first-writer deveria aceitar: {sup}")
    if int(inf["payload"].get("linhas_preteridas") or 0) != 1:
        raise Falhou(f"segunda execução deveria ser preterida: {inf}")
    if int(inf["payload"].get("linhas_aceitas") or 0) != 0:
        raise Falhou(f"segunda execução não pode aceitar: {inf}")
    f = result["fato"]
    if f.get("execucao_id") != sup["payload"]["execucao_id"]:
        raise Falhou(f"first-writer não permaneceu: fato={f} first={sup}")
    if f.get("campaign_name") != "Maquininha":
        raise Falhou(f"conteúdo idêntico foi alterado: {f}")
    if n_recibos(cluster, chave_idempotencia="O-a|1") != 1:
        raise Falhou("recibo do perdedor idêntico ausente")
    if n_recibos(cluster, chave_idempotencia="O-b|1") != 1:
        raise Falhou("recibo do first-writer ausente")
    if n_fatos(cluster, campaign_id=cid) != 1:
        raise Falhou("fato duplicado no empate idêntico")


def case_p(cluster: Cluster) -> None:
    """Empate total com conteúdo persistível divergente: recusa nominal, sem parcial."""
    cid = "1710000017"
    canonico = linha_empate(cid)
    divergente = linha_empate(
        cid,
        campaign_name="Outra",
        search_click_share=0.99,
        metricas_extras={"origem_api": "search", "nota": 2},
    )
    gated = doc(
        chave_idempotencia="P-div|1",
        execucao_chave="P-div",
        origem_janela="D-1",
        linhas=[divergente],
    )
    first = doc(
        chave_idempotencia="P-win|1",
        execucao_chave="P-win",
        origem_janela="D-1",
        linhas=[canonico],
    )
    result = run_toctou(
        cluster, inferior=gated, superior=first, hold_origem="D-1",
        campaign_id=cid, expect_origem="D-1", expect_impressoes=11,
    )
    inf = result["out"]["inferior"]
    sup = result["out"]["superior"]
    if sup["ok"] is not True:
        raise Falhou(f"first-writer deveria persistir: {sup}")
    if inf["ok"] is not False:
        raise Falhou(f"divergente deveria recusar: {inf}")
    msg = json.dumps(inf.get("payload") or {}, ensure_ascii=False)
    if "FATO_EMPATE_CONTEUDO_DIVERGENTE" not in msg:
        raise Falhou(f"recusa precisa ser FATO_EMPATE_CONTEUDO_DIVERGENTE, não {inf}")
    if inf.get("sqlstate") == "23505":
        raise Falhou(f"23505 no empate divergente: {inf}")
    if n_recibos(cluster, chave_idempotencia="P-div|1") != 0:
        raise Falhou("perdedor divergente deixou recibo")
    if n_recibos(cluster, chave_idempotencia="P-win|1") != 1:
        raise Falhou("first-writer sem recibo")
    if n_fatos(cluster, campaign_id=cid) != 1:
        raise Falhou("fato duplicado ou órfão no empate divergente")
    f = result["fato"]
    if f.get("campaign_name") != "Maquininha":
        raise Falhou(f"versão parcial do perdedor sobreviveu: {f}")
    extras = f.get("metricas_extras") or {}
    if extras.get("nota") is not None:
        raise Falhou(f"metricas_extras do perdedor vazaram: {f}")
    share = f.get("search_click_share")
    if share is not None and abs(float(share) - 0.4) > 0.0001:
        raise Falhou(f"share do perdedor vazou: {f}")


def case_q(cluster: Cluster) -> None:
    """Isolamento diferente de READ COMMITTED é recusado com nome, sem persistir."""
    cid = "1710000018"
    reset_data(cluster)

    def recusa(who: str, level: str, chave: str) -> None:
        payload = doc(
            chave_idempotencia=chave,
            execucao_chave=who,
            linhas=[linha(campaign_id=cid, impressoes=1)],
        )
        sql = worker_sql(
            who,
            payload,
            extra_pre=f"BEGIN;\nSET TRANSACTION ISOLATION LEVEL {level};",
            extra_post="COMMIT;",
        )
        r = cluster.psql(sql, timeout=20)
        if r.returncode != 0:
            raise Falhou(f"{who} quebrou o psql: {r.stderr}")
        row = out_by_who(out_rows(cluster)).get(who) or {}
        if row.get("ok") is not False:
            raise Falhou(f"{level} deveria ser recusado: {row}")
        msg = json.dumps(row.get("payload") or {}, ensure_ascii=False)
        if "ISOLAMENTO_NAO_SUPORTADO_V12_04" not in msg:
            raise Falhou(f"{level} sem erro nominal: {row}")
        if n_fatos(cluster, campaign_id=cid) != 0:
            raise Falhou(f"{level} persistiu fato")
        if n_recibos(cluster, chave_idempotencia=chave) != 0:
            raise Falhou(f"{level} persistiu recibo")

    recusa("rr", "REPEATABLE READ", "Q-rr|1")
    recusa("sr", "SERIALIZABLE", "Q-sr|1")
    rc = doc(
        chave_idempotencia="Q-rc|1",
        execucao_chave="Q-rc",
        linhas=[linha(campaign_id=cid, impressoes=1)],
    )
    r = cluster.psql(worker_sql("rc", rc), timeout=20)
    if r.returncode != 0:
        raise Falhou(f"READ COMMITTED quebrou o psql: {r.stderr}")
    row = out_by_who(out_rows(cluster)).get("rc") or {}
    if row.get("ok") is not True:
        raise Falhou(f"READ COMMITTED deveria passar: {row}")
    if n_fatos(cluster, campaign_id=cid) != 1:
        raise Falhou("READ COMMITTED não persistiu o fato de controle")


CASES = [
    ("A", "D0 vs D-1: D-1 vence independente da ordem de commit", case_a),
    ("B", "D-1 vs backfill: backfill vence independente da ordem de commit", case_b),
    ("C", "mesma precedência: maior colhida_em vence", case_c),
    ("D", "inferior iniciada antes e commitada depois não rebaixa", case_d),
    ("E", "mesma chave: espera 120405, um recibo, repetida true/false", case_e),
    ("F", "mesma chave + payload divergente: uma aceita, outra recusa nominal", case_f),
    ("G", "duas chaves no mesmo slot de lote: uma vence, sem órfão", case_g),
    ("H", "duas execuções no mesmo fato: recibo condiz com o que persistiu", case_h),
    ("I", "fechamento não fecha falso contra lote in-flight; fecha depois", case_i),
    ("J", "falha depois da escrita desfaz fato e recibo", case_j),
    ("K", "contas distintas com o mesmo campaign_id não colidem", case_k),
    ("L", "fatos distintos não serializam a tabela", case_l),
    ("M", "repetição controlada sem deadlock", lambda c: case_m(c, 3)),
    ("N", "NULL continua NULL; zero medido continua zero", case_n),
    ("O", "empate total idêntico: first-writer permanece, outra preterida", case_o),
    ("P", "empate total divergente: FATO_EMPATE_CONTEUDO_DIVERGENTE, sem parcial", case_p),
    ("Q", "isolamento ≠ READ COMMITTED recusa ISOLAMENTO_NAO_SUPORTADO_V12_04", case_q),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("VOLC_PG_IMAGE", "postgres:16-alpine"))
    ap.add_argument("--only", default="")
    ap.add_argument("--repeat-toctou", type=int, default=3)
    args = ap.parse_args()
    name = f"volc-p10-t17-conc-{os.getpid()}"
    cluster = Cluster(args.image, name)
    started = time.time()
    ok = 0
    ko = 0
    results: list[tuple[str, str, str]] = []
    try:
        cluster.start()
        print(f"cluster descartável: container {cluster.name} ({args.image} → {cluster.pg_version})")
        setup_schema(cluster)
        wanted = {x.strip().upper() for x in args.only.split(",") if x.strip()}
        for code, titulo, fn in CASES:
            if wanted and code not in wanted:
                continue
            repeats = args.repeat_toctou if code in {"A", "B", "C", "D", "H", "N", "O", "P"} else 1
            if code == "M":
                repeats = 1
            try:
                for i in range(repeats):
                    fn(cluster)
                print(f"  ok   {code}  {titulo}" + (f"  ×{repeats}" if repeats > 1 else ""))
                ok += 1
                results.append((code, "ok", titulo))
            except Exception as exc:  # noqa: BLE001
                print(f"  FALHOU  {code}  {titulo}")
                print(f"          {exc}")
                ko += 1
                results.append((code, "FALHOU", f"{titulo} :: {exc}"))
        print()
        print("════════════════════════════════════════════════════════")
        print(f"  concorrência v12_04  passaram {ok} · falharam {ko}  "
              f"({cluster.pg_version}, {time.time()-started:.1f}s)")
        if ko:
            return 1
        print("  CONTRAPROVA CONCORRENTE VERDE")
        return 0
    finally:
        cluster.stop()


if __name__ == "__main__":
    sys.exit(main())
