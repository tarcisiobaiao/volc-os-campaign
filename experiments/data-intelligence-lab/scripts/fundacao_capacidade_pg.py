"""Medição de capacidade num PostgreSQL 16 DESCARTÁVEL (frente B da Fundação Data Intelligence).

Sobe um cluster temporário (initdb em diretório próprio, socket unix próprio, listen_addresses='',
porta alta), mede tamanho real de linhas/índices/JSONB/partições, latência de ingestão em lote e de
consulta `as_of`, e DERRUBA E APAGA o cluster no fim (também em erro). Nada de rede, nada de
produção. Dados 100% sintéticos e determinísticos (sem random(): valores derivados das chaves).

DDL de medição: APROXIMAÇÃO própria do desenho do manifesto (`observacao` + `payload_bruto` jsonb
deduplicado por sha256) — o SQL candidato do worker A não existia quando esta medição rodou.

Uso (do worktree):
  OMP_NUM_THREADS=2 <python> -I experiments/data-intelligence-lab/scripts/fundacao_capacidade_pg.py \
      --escalas 1e5,1e6,1e7 --saida docs/data-intelligence/fundacao-20261016/benchmarks/capacidade/pg_medicoes.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BIN = Path("/opt/homebrew/bin")
GIB = 1024**3
# macOS: sem LC_ALL válido o postmaster aborta ("became multithreaded during startup")
ENV = {**os.environ, "LC_ALL": "C", "LANG": "C"}
LIMITE_CLUSTER = 4 * GIB  # teto de disco temporário combinado com o integrador
MARGEM_LIVRE = 6 * GIB  # nunca deixar o disco com menos que isto livre

SEED = 20261016
N_MET = 5  # métricas por linha no formato longo (impressions, clicks, cost, conversions, conv_value)
N_MET_LARGO = 8


class Cluster:
    def __init__(self, raiz: Path, porta: int):
        self.dados = raiz / "dados"
        self.sock = Path(tempfile.mkdtemp(prefix="pgfb-", dir="/private/tmp"))  # caminho curto (<104 chars)
        self.porta = porta
        self.log = raiz / "pg.log"

    def iniciar(self) -> None:
        subprocess.run([str(BIN / "initdb"), "-D", str(self.dados), "-U", "bench", "--auth=trust", "-E", "UTF8",
                        "--no-locale", "--no-sync"], check=True, capture_output=True, env=ENV)
        opts = (f"-k {self.sock} -p {self.porta} -c listen_addresses='' -c fsync=on -c synchronous_commit=on "
                "-c wal_level=minimal -c max_wal_senders=0 -c max_wal_size=512MB -c min_wal_size=80MB "
                "-c shared_buffers=256MB -c work_mem=64MB -c maintenance_work_mem=512MB -c jit=off "
                "-c max_parallel_workers_per_gather=2 -c max_parallel_maintenance_workers=2 "
                "-c default_toast_compression=pglz -c autovacuum=off")
        subprocess.run([str(BIN / "pg_ctl"), "-D", str(self.dados), "-o", opts, "-l", str(self.log), "-w", "start"],
                       check=True, capture_output=True, env=ENV)

    def parar_e_apagar(self) -> None:
        if self.dados.exists():
            subprocess.run([str(BIN / "pg_ctl"), "-D", str(self.dados), "-m", "fast", "-w", "stop"], capture_output=True, env=ENV)
        shutil.rmtree(self.dados.parent, ignore_errors=True)
        shutil.rmtree(self.sock, ignore_errors=True)

    def sql(self, texto: str, entrada: str | None = None) -> str:
        r = subprocess.run([str(BIN / "psql"), "-h", str(self.sock), "-p", str(self.porta), "-U", "bench", "-d",
                            "postgres", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", texto],
                           input=entrada, capture_output=True, text=True, env=ENV)
        if r.returncode != 0:
            raise RuntimeError(f"psql falhou: {r.stderr.strip()}\nSQL: {texto[:400]}")
        return r.stdout.strip()

    def copiar(self, tabela_cols: str, dados: str) -> None:
        r = subprocess.run([str(BIN / "psql"), "-h", str(self.sock), "-p", str(self.porta), "-U", "bench", "-d",
                            "postgres", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", f"\\copy {tabela_cols} from stdin"],
                           input=dados, capture_output=True, text=True, env=ENV)
        if r.returncode != 0:
            raise RuntimeError(r.stderr)

    def tamanho_dir(self) -> int:
        return sum(f.stat().st_size for f in self.dados.rglob("*") if f.is_file())


def _guarda_disco(cl: Cluster, previsto: int) -> None:
    livre = shutil.disk_usage(cl.dados).free
    usado = cl.tamanho_dir()
    if usado + previsto > LIMITE_CLUSTER:
        raise RuntimeError(f"previsto {previsto/GIB:.2f} GiB + usado {usado/GIB:.2f} GiB > teto {LIMITE_CLUSTER/GIB} GiB")
    if livre - previsto < MARGEM_LIVRE:
        raise RuntimeError(f"disco livre {livre/GIB:.1f} GiB insuficiente para {previsto/GIB:.2f} GiB + margem")


# ---------------------------------------------------------------- DDL de medição (aproximação)

COLS_LONGO = ("fonte smallint not null, conta_id bigint not null, nivel smallint not null, entidade_id bigint not null, "
              "segmento text not null default '', dia date not null, metrica smallint not null, valor bigint, "
              "moeda char(3), estado smallint not null, observado_em timestamptz not null, "
              "disponivel_em timestamptz not null, run_id bigint not null, payload_sha256 bytea not null")
COLS_TEXTO = ("fonte text not null, conta_id text not null, nivel text not null, entidade_id text not null, "
              "segmento text not null default '', dia date not null, metrica text not null, valor numeric, "
              "moeda text, estado text not null, observado_em timestamptz not null, "
              "disponivel_em timestamptz not null, run_id text not null, payload_sha256 text not null")
METRICAS_LARGO = ("impressions", "clicks", "cost_micros", "conversions_micros", "conversions_value_micros",
                  "interactions", "all_conversions_micros", "view_through_conversions")
COLS_LARGO = ("fonte smallint not null, conta_id bigint not null, nivel smallint not null, entidade_id bigint not null, "
              "segmento text not null default '', dia date not null, "
              + ", ".join(f"{m} bigint" for m in METRICAS_LARGO)
              + ", moeda char(3), observado_em timestamptz not null, disponivel_em timestamptz not null, "
                "run_id bigint not null, payload_sha256 bytea not null")
COLS_JSONB = ("fonte smallint not null, conta_id bigint not null, nivel smallint not null, entidade_id bigint not null, "
              "segmento text not null default '', dia date not null, valores jsonb not null, moeda char(3), "
              "observado_em timestamptz not null, disponivel_em timestamptz not null, run_id bigint not null, "
              "payload_sha256 bytea not null")

# Réplica de medição de `google_ads_observation` (v21_01, ref wip/historico-joinads-20261015,
# supabase/migrations/v21_01_google_ads_coleta_canonica.sql:94-145): ids text, métricas em jsonb,
# UNIQUE (run_id, observation_key) — sem dedup entre runs —, 2 btree parciais/compostos + 2 GIN.
# FKs omitidas (não ocupam espaço); PK uuid aleatória.
COLS_V21 = ("observation_id uuid not null default gen_random_uuid(), run_id uuid not null, batch_id uuid not null, "
            "observation_key text not null, customer_id text not null, campaign_id text, ad_group_id text, "
            "criterion_id text, resource_type text not null, resource_id text, grain text not null, metric_date date, "
            "metric_hour smallint, currency_code text, dimensions jsonb not null default '{}', "
            "metrics jsonb not null default '{}', attributes jsonb not null default '{}', "
            "collected_at timestamptz not null, created_at timestamptz not null default now()")

# chave determinística: nenhuma chamada a random() no servidor
_V = "case when ((c*7919 + e*104729 + d*1299709 + m*15485863) % 10) = 0 then 2 else 1 end"
_V_W = "case when ((c*7919 + e*104729 + d*1299709) % 10) = 0 then 2 else 1 end"
_DISP = "(timestamptz '2026-07-01 09:00+00' + (d+1) * interval '1 day' + v * interval '6 hours')"


def _nomes(cols: str) -> str:
    return ", ".join(parte.strip().split()[0] for parte in cols.split(", "))


def _dims(n_linhas: int, por_chave: int) -> tuple[int, int, int]:
    """(contas, entidades por conta, dias) para ~n_linhas, com 10 contas e 90 dias fixos."""
    contas, dias = 10, 90
    ent = max(1, round(n_linhas / (contas * dias * por_chave * 1.1)))
    return contas, ent, dias


def _insert_longo(tab: str, contas: int, ent: int, dias: int, texto: bool = False) -> str:
    if texto:
        sel = ("'google_ads', 'customers/' || (1000000000 + c), 'campaign', (20000000000 + c*100000 + e)::text, '', "
               "date '2026-07-01' + d, (array['impressions','clicks','cost_micros','conversions','conversions_value'])[m], "
               "((c*31 + e*17 + d*13 + m*7 + v) * 2654435761::bigint) % 50000000, 'BRL', 'medido', "
               f"{_DISP}, {_DISP}, 'run-' || (d*10+v), encode(sha256(int8send(c*1000000000000 + e*1000000 + d*10 + v)), 'hex')")
    else:
        sel = ("1, 1000000000 + c, 2, 20000000000 + c*100000 + e, '', date '2026-07-01' + d, m, "
               "((c*31 + e*17 + d*13 + m*7 + v) * 2654435761::bigint) % 50000000, 'BRL', 1, "
               f"{_DISP}, {_DISP}, d*10+v, sha256(int8send(c*1000000000000 + e*1000000 + d*10 + v))")
    cols = _nomes(COLS_TEXTO if texto else COLS_LONGO)
    return (f"insert into {tab} ({cols}) select {sel} from generate_series(1,{contas}) c, generate_series(1,{ent}) e, "
            f"generate_series(0,{dias-1}) d, generate_series(1,{N_MET}) m, lateral generate_series(1, {_V}) v")


def _insert_largo(tab: str, contas: int, ent: int, dias: int, jsonb: bool) -> str:
    vals = [f"((c*31 + e*17 + d*13 + {k}*7 + v) * 2654435761::bigint) % 50000000" for k in range(N_MET_LARGO)]
    vals[6] = "null"  # duas métricas sem valor: null (≠ 0)
    vals[7] = "null"
    if jsonb:
        corpo = "jsonb_build_object(" + ", ".join(f"'{m}', {v}" for m, v in zip(METRICAS_LARGO, vals)) + ")"
    else:
        corpo = ", ".join(vals)
    return (f"insert into {tab} ({_nomes(COLS_JSONB if jsonb else COLS_LARGO)}) select 1, 1000000000 + c, 2, 20000000000 + c*100000 + e, '', date '2026-07-01' + d, "
            f"{corpo}, 'BRL', {_DISP}, {_DISP}, d*10+v, sha256(int8send(c*1000000000000 + e*1000000 + d*10 + v)) "
            f"from generate_series(1,{contas}) c, generate_series(1,{ent}) e, generate_series(0,{dias-1}) d, "
            f"lateral generate_series(1, {_V_W}) v")


def _insert_v21(tab: str, contas: int, ent: int, dias: int) -> str:
    met = ", ".join(f"'{m}', ((c*31 + e*17 + d*13 + {k}*7 + v) * 2654435761::bigint) % 50000000"
                    for k, m in enumerate(METRICAS_LARGO[:6]))
    cols = "run_id, batch_id, observation_key, customer_id, campaign_id, resource_type, resource_id, grain, " \
           "metric_date, currency_code, dimensions, metrics, attributes, collected_at"
    return (f"insert into {tab} ({cols}) select "
            "md5('run' || (d*10+v))::uuid, md5('batch' || c || ':' || (d*10+v))::uuid, "
            "'campaign:' || (20000000000 + c*100000 + e) || ':' || (date '2026-07-01' + d), (1000000000 + c)::text, "
            "(20000000000 + c*100000 + e)::text, 'campaign', (20000000000 + c*100000 + e)::text, 'campaign_day', "
            "date '2026-07-01' + d, 'BRL', '{}'::jsonb, "
            f"jsonb_build_object({met}, 'all_conversions_micros', null, 'view_through_conversions', null), "
            "jsonb_build_object('campaign_name', 'VOLC | site-' || lpad((e % 50)::text, 2, '0') || ' | Search | 2026-10', "
            "'campaign_status', 'ENABLED', 'channel', 'SEARCH'), "
            f"{_DISP} from generate_series(1,{contas}) c, generate_series(1,{ent}) e, "
            f"generate_series(0,{dias-1}) d, lateral generate_series(1, {_V_W}) v")


def _indices_v21(cl: Cluster, tab: str) -> dict[str, float]:
    tempos = {}
    for nome, ddl in (
        ("pk", f"alter table {tab} add constraint {tab}_pk primary key (observation_id)"),
        ("as_of", f"alter table {tab} add constraint {tab}_uq unique (run_id, observation_key)"),
        ("campaign_ix", f"create index {tab}_cix on {tab} (customer_id, campaign_id, metric_date desc, collected_at desc) "
                        "where campaign_id is not null"),
        ("resource_ix", f"create index {tab}_rix on {tab} (resource_type, grain, metric_date desc, collected_at desc)"),
        ("gin_dim", f"create index {tab}_gd on {tab} using gin (dimensions jsonb_path_ops)"),
        ("gin_met", f"create index {tab}_gm on {tab} using gin (metrics jsonb_path_ops)"),
    ):
        t0 = time.perf_counter()
        cl.sql(ddl)
        tempos[nome] = time.perf_counter() - t0
    cl.sql(f"analyze {tab}")
    return tempos


def _criar(cl: Cluster, tab: str, cols: str, particionada: bool) -> None:
    if particionada:
        cl.sql(f"create table {tab} (id bigint generated always as identity, {cols}) partition by range (dia)")
        for mes in range(7, 11):
            cl.sql(f"create table {tab}_2026_{mes:02d} partition of {tab} for values from "
                   f"('2026-{mes:02d}-01') to ('2026-{mes+1:02d}-01')")
    else:
        cl.sql(f"create table {tab} (id bigint generated always as identity, {cols})")


def _indices(cl: Cluster, tab: str, largo: bool, particionada: bool) -> dict[str, float]:
    chave = "conta_id, nivel, entidade_id, segmento, dia" + ("" if largo else ", metrica")
    tempos = {}
    # PK: em tabela particionada a PK precisa conter a chave de partição
    pk = "(id, dia)" if particionada else "(id)"
    for nome, ddl in (("pk", f"alter table {tab} add constraint {tab}_pk primary key {pk}"),
                      ("as_of", f"create unique index {tab}_as_of on {tab} ({chave}, disponivel_em desc)"),
                      ("brin_disp", f"create index {tab}_brin on {tab} using brin (disponivel_em)")):
        t0 = time.perf_counter()
        cl.sql(ddl)
        tempos[nome] = time.perf_counter() - t0
    cl.sql(f"analyze {tab}")
    return tempos


def _tamanhos(cl: Cluster, tab: str) -> dict:
    """Soma as folhas se particionada. heap = pg_table_size (main+fsm+vm+toast)."""
    folhas = (f"(select relid from pg_partition_tree('{tab}') where isleaf union select '{tab}'::regclass "
              f"where (select count(*) from pg_partition_tree('{tab}')) <= 1)")
    q = (f"select coalesce(sum(pg_table_size(relid)),0), coalesce(sum(pg_indexes_size(relid)),0), "
         f"coalesce(sum(pg_total_relation_size(relid)),0), (select count(*) from {tab}), count(*) from {folhas} f")
    heap, idx, total, linhas, nfolhas = (int(x) for x in cl.sql(q).split("|"))
    por_indice: dict[str, int] = {}
    for linha in cl.sql(f"""select case when i.indisprimary then 'pk' when am.amname = 'brin' then 'brin_disp'
                                   when i.indisunique then 'unico' else am.amname end, pg_relation_size(i.indexrelid)
                            from pg_index i join pg_class ci on ci.oid = i.indexrelid join pg_am am on am.oid = ci.relam
                            where i.indrelid in {folhas}""").splitlines():
        nome, b = linha.split("|")
        por_indice[nome] = por_indice.get(nome, 0) + int(b)
    return {"linhas": linhas, "heap_bytes": heap, "indices_bytes": idx, "total_bytes": total,
            "por_indice_bytes": por_indice, "folhas": nfolhas,
            "heap_por_linha": heap / linhas if linhas else None, "indices_por_linha": idx / linhas if linhas else None}


def _percentis(ms: list[float]) -> dict:
    s = sorted(ms)
    q = lambda p: s[min(len(s) - 1, int(round(p * (len(s) - 1))))]  # noqa: E731
    return {"n": len(s), "p50_ms": statistics.median(s), "p95_ms": q(0.95), "p99_ms": q(0.99), "max_ms": s[-1],
            "media_ms": statistics.fmean(s)}


PROC = """
create table if not exists bench_tempos (teste text, ms double precision);
create or replace procedure bench_as_of(tab text, contas int, ent int, dias int, n int, rotulo text)
language plpgsql as $$
declare t0 timestamptz; i int; c int; e int; d int; m int; r bigint; asof timestamptz;
begin
  for i in 1..n loop
    c := 1 + ((i * 2654435761::bigint) % contas); e := 1 + ((i * 40503::bigint) % ent);
    d := (i * 7919) % dias; m := 1 + (i % 5);
    asof := timestamptz '2026-07-01 09:00+00' + (d+1) * interval '1 day' + interval '3 hours';
    t0 := clock_timestamp();
    execute format('select valor from %I where conta_id=$1 and nivel=2 and entidade_id=$2 and segmento=$5 '
                   'and dia=$3 and metrica=$4 and disponivel_em <= $6 order by disponivel_em desc limit 1', tab)
      into r using 1000000000 + c, 20000000000 + c*100000 + e, date '2026-07-01' + d, m::smallint, ''::text, asof;
    insert into bench_tempos values (rotulo, extract(epoch from clock_timestamp() - t0) * 1000);
  end loop;
end $$;
create or replace procedure bench_as_of_v21(tab text, contas int, ent int, dias int, n int, rotulo text)
language plpgsql as $$
declare t0 timestamptz; i int; c int; e int; d int; r jsonb; asof timestamptz;
begin
  for i in 1..n loop
    c := 1 + ((i * 2654435761::bigint) % contas); e := 1 + ((i * 40503::bigint) % ent); d := (i * 7919) % dias;
    asof := timestamptz '2026-07-01 09:00+00' + (d+1) * interval '1 day' + interval '3 hours';
    t0 := clock_timestamp();
    execute format('select metrics from %I where customer_id=$1 and campaign_id=$2 and metric_date=$3 '
                   'and collected_at <= $4 order by collected_at desc limit 1', tab)
      into r using (1000000000 + c)::text, (20000000000 + c*100000 + e)::text, date '2026-07-01' + d, asof;
    insert into bench_tempos values (rotulo, extract(epoch from clock_timestamp() - t0) * 1000);
  end loop;
end $$;
create or replace procedure bench_snapshot(tab text, n int, dias int, rotulo text)
language plpgsql as $$
declare t0 timestamptz; i int; d int; k bigint; asof timestamptz;
begin
  for i in 1..n loop
    d := (i * 7919) % dias;
    asof := timestamptz '2026-07-01 09:00+00' + (d+1) * interval '1 day' + interval '3 hours';
    t0 := clock_timestamp();
    execute format('select count(*) from (select distinct on (entidade_id, segmento, metrica) valor from %I '
                   'where conta_id = $1 and nivel = 2 and dia = $2 and disponivel_em <= $3 '
                   'order by entidade_id, segmento, metrica, disponivel_em desc) s', tab)
      into k using 1000000001::bigint, date '2026-07-01' + d, asof;
    insert into bench_tempos values (rotulo, extract(epoch from clock_timestamp() - t0) * 1000);
  end loop;
end $$;
create or replace procedure bench_ingest(tab text, lote int, reps int, dedup boolean, rotulo text, base bigint, ent int)
language plpgsql as $$
declare t0 timestamptz; i int; lote_json jsonb;
begin
  for i in 1..reps loop
    -- lote no formato da RPC de ingestão (jsonb array), metade das linhas repete o valor vigente
    -- uma linha por chave lógica (entidade × dia × métrica), como numa resposta real
    select jsonb_agg(jsonb_build_object('c', 1000000001, 'e', 20000100000 + 1 + ((g-1)/5) % ent,
             'd', date '2026-09-28' - (((g-1)/(5*ent)) % 90), 'm', 1 + ((g-1) % 5),
             'v', case when g % 2 = 0 then 0 else base + i*100000 + g end, 'k', base + i*100000 + g))
      into lote_json from generate_series(1, lote) g;
    t0 := clock_timestamp();
    if dedup then
      execute format($q$insert into %I (fonte, conta_id, nivel, entidade_id, segmento, dia, metrica, valor, moeda, estado,
          observado_em, disponivel_em, run_id, payload_sha256)
        select 1, x.c, 2, x.e, '', x.d, x.m, x.v, 'BRL', 1, now(), clock_timestamp() + make_interval(secs => x.k), x.k,
               sha256(int8send(x.k))
        from jsonb_to_recordset($1) as x(c bigint, e bigint, d date, m smallint, v bigint, k bigint)
        where not exists (select 1 from (select o.valor from %I o where o.conta_id = x.c and o.nivel = 2
                            and o.entidade_id = x.e and o.segmento = '' and o.dia = x.d and o.metrica = x.m
                            order by o.disponivel_em desc limit 1) ult where ult.valor is not distinct from x.v)
        on conflict do nothing$q$, tab, tab) using lote_json;
    else
      execute format($q$insert into %I (fonte, conta_id, nivel, entidade_id, segmento, dia, metrica, valor, moeda, estado,
          observado_em, disponivel_em, run_id, payload_sha256)
        select 1, x.c, 2, x.e, '', x.d, x.m, x.v, 'BRL', 1, now(), clock_timestamp() + make_interval(secs => x.k), x.k,
               sha256(int8send(x.k))
        from jsonb_to_recordset($1) as x(c bigint, e bigint, d date, m smallint, v bigint, k bigint)
        on conflict do nothing$q$, tab) using lote_json;
    end if;
    commit;
    insert into bench_tempos values (rotulo, extract(epoch from clock_timestamp() - t0) * 1000);
    commit;
  end loop;
end $$;
"""


def _tempos(cl: Cluster, rotulo: str) -> dict:
    ms = [float(x) for x in cl.sql(f"select ms from bench_tempos where teste = '{rotulo}'").splitlines()]
    return _percentis(ms)


def medir_variante(cl: Cluster, nome: str, n_alvo: int, particionada: bool, latencias: bool) -> dict:
    tab = f"{nome}_{'p' if particionada else 'h'}_{n_alvo:.0e}".replace("+", "").replace(".", "")
    largo = nome in ("largo", "jsonb", "v21")
    contas, ent, dias = _dims(n_alvo, 1 if largo else N_MET)
    cols = {"longo": COLS_LONGO, "texto": COLS_TEXTO, "largo": COLS_LARGO, "jsonb": COLS_JSONB, "v21": COLS_V21}[nome]
    previsto = int(n_alvo * {"texto": 400, "v21": 1400}.get(nome, 260) * (1 if not largo else 1.5))
    _guarda_disco(cl, previsto)
    _criar(cl, tab, cols, particionada)
    t0 = time.perf_counter()
    if nome == "v21":
        cl.sql(_insert_v21(tab, contas, ent, dias))
    elif largo:
        cl.sql(_insert_largo(tab, contas, ent, dias, jsonb=(nome == "jsonb")))
    else:
        cl.sql(_insert_longo(tab, contas, ent, dias, texto=(nome == "texto")))
    t_carga = time.perf_counter() - t0
    cl.sql(f"vacuum (freeze, analyze) {tab}")
    sem_idx = _tamanhos(cl, tab)
    t_idx = _indices_v21(cl, tab) if nome == "v21" else _indices(cl, tab, largo, particionada)
    tam = _tamanhos(cl, tab)
    tam["heap_sem_indices_bytes"] = sem_idx["heap_bytes"]
    valores = tam["linhas"] * (N_MET_LARGO if largo else 1)
    if nome == "v21":
        rot = f"{tab}_asof"
        cl.sql(f"call bench_as_of_v21('{tab}', {contas}, {ent}, {dias}, 2000, '{rot}')")
        as_of_v21 = _tempos(cl, rot)
    res = {"variante": nome, "particionada": particionada, "n_alvo": n_alvo, "dims": {"contas": contas,
           "entidades_por_conta": ent, "dias": dias}, "carga_s": t_carga, "linhas_por_s_carga": tam["linhas"] / t_carga,
           "indices_s": t_idx, "tamanho": tam, "valores_de_metrica": valores,
           "bytes_por_valor_total": tam["total_bytes"] / valores, "bytes_por_valor_heap": tam["heap_bytes"] / valores,
           "dir_cluster_bytes_apos": cl.tamanho_dir()}
    if nome == "v21":
        res["as_of_ponto"] = as_of_v21
    if latencias and nome == "longo":
        rot = f"{tab}_asof"
        cl.sql(f"call bench_as_of('{tab}', {contas}, {ent}, {dias}, 2000, '{rot}')")
        res["as_of_ponto"] = _tempos(cl, rot)
        rot = f"{tab}_snap"
        cl.sql(f"call bench_snapshot('{tab}', 30, {dias}, '{rot}')")
        res["snapshot_conta_dia"] = _tempos(cl, rot)
        res["snapshot_conta_dia"]["linhas_por_snapshot"] = ent * N_MET
        for lote in (1000, 5000):
            for dedup in (False, True):
                rot = f"{tab}_ing_{lote}_{'dedup' if dedup else 'cru'}"
                base = 10**12 + lote * 10**7 + (10**6 if dedup else 0)
                cl.sql(f"call bench_ingest('{tab}', {lote}, 15, {str(dedup).lower()}, '{rot}', {base}, {ent})")
                t = _tempos(cl, rot)
                t["linhas_por_s_p50"] = lote / (t["p50_ms"] / 1000)
                res[f"ingestao_lote_{lote}_{'dedup' if dedup else 'cru'}"] = t
        res["explain_as_of"] = cl.sql(
            f"explain (costs off) select valor from {tab} where conta_id=1000000001 and nivel=2 and entidade_id=20000100001 "
            f"and segmento='' and dia='2026-07-10' and metrica=1 and disponivel_em <= now() order by disponivel_em desc limit 1")
    cl.sql(f"drop table {tab} cascade")
    cl.sql("checkpoint")
    return res


# ---------------------------------------------------------------- payload bruto (JSON estilo GAQL)

TERMOS = ("curso de inglês online", "como fazer currículo", "concurso público 2026 edital", "receita de bolo de cenoura",
          "melhor cartão de crédito sem anuidade", "simulado enem matemática", "previsão do tempo curitiba",
          "aposentadoria por idade regras", "tabela fipe moto", "horóscopo de hoje")


def linha_gaql(rng: random.Random, i: int, tipo: str) -> dict:
    cid, camp = 1234567890, 2345678900 + (i % 50)
    base = {"customer": {"resourceName": f"customers/{cid}", "id": str(cid)},
            "campaign": {"resourceName": f"customers/{cid}/campaigns/{camp}", "id": str(camp),
                         "name": f"VOLC | site-{i % 50:02d} | Search | 2026-10", "status": "ENABLED",
                         "advertisingChannelType": "SEARCH"},
            "segments": {"date": f"2026-10-{1 + i % 28:02d}"},
            "metrics": {"impressions": str(rng.randint(0, 5000)), "clicks": str(rng.randint(0, 300)),
                        "costMicros": str(rng.randint(0, 90_000_000)), "conversions": round(rng.random() * 10, 2),
                        "conversionsValue": round(rng.random() * 400, 2), "interactions": str(rng.randint(0, 300)),
                        "allConversions": round(rng.random() * 12, 2)}}
    if tipo == "termo":
        ag = 3456789000 + (i % 400)
        termo = f"{TERMOS[i % len(TERMOS)]} {i % 997}"
        base["adGroup"] = {"resourceName": f"customers/{cid}/adGroups/{ag}", "id": str(ag), "name": f"grupo {i % 400}"}
        base["searchTermView"] = {"resourceName": f"customers/{cid}/searchTermViews/{camp}~{ag}~{i:012d}",
                                  "searchTerm": termo, "status": "NONE"}
        base["segments"]["keyword"] = {"info": {"text": termo.split()[0], "matchType": "BROAD"}}
    return base


def medir_payload(cl: Cluster, n_linhas: int, por_lote: int) -> dict:
    rng = random.Random(SEED)
    out = {}
    for tipo in ("campanha", "termo"):
        linhas = [json.dumps(linha_gaql(rng, i, tipo), ensure_ascii=False, separators=(",", ":")) for i in range(n_linhas)]
        bytes_json = sum(len(x.encode()) for x in linhas)
        for compressao in ("pglz", "lz4"):
            for gr, nome in ((1, "linha"), (por_lote, "lote")):
                tab = f"payload_{tipo}_{nome}_{compressao}"
                cl.sql(f"create table {tab} (sha256 bytea primary key, fonte smallint not null, "
                       f"primeiro_visto_em timestamptz not null default now(), payload jsonb compression {compressao} not null)")
                buf = []
                for k in range(0, n_linhas, gr):
                    corpo = linhas[k] if gr == 1 else "[" + ",".join(linhas[k:k + gr]) + "]"
                    h = hashlib.sha256(corpo.encode()).hexdigest()
                    buf.append(f"\\\\x{h}\t1\t{corpo}")
                cl.copiar(f"{tab} (sha256, fonte, payload)", "\n".join(buf) + "\n")
                cl.sql(f"vacuum analyze {tab}")
                total = int(cl.sql(f"select pg_total_relation_size('{tab}')"))
                toast = int(cl.sql(f"select coalesce(pg_total_relation_size(reltoastrelid),0) from pg_class where oid='{tab}'::regclass"))
                out[f"{tipo}_{nome}_{compressao}"] = {
                    "linhas_api": n_linhas, "linhas_tabela": len(buf), "json_bytes_por_linha": bytes_json / n_linhas,
                    "total_bytes": total, "toast_bytes": toast, "bytes_por_linha_api": total / n_linhas,
                    "razao_compressao": bytes_json / total}
                cl.sql(f"drop table {tab}")
    return out


# ---------------------------------------------------------------- comparação analítica (DuckDB/Polars)

def comparar_analitico(n_alvo: int, dir_tmp: Path) -> dict:
    """Snapshot as_of completo (última versão ≤ as_of por chave) sobre Parquet: DuckDB × Polars.

    Mesmo gerador determinístico do formato longo. Só leitura analítica de snapshot — não é
    proposta de engine para ingestão.
    """
    import duckdb
    import polars as pl

    contas, ent, dias = _dims(n_alvo, N_MET)
    con = duckdb.connect()
    con.execute("set threads=2; set memory_limit='3GB'")
    t0 = time.perf_counter()
    sel = ("select 1000000000 + c as conta_id, 20000000000 + c*100000 + e as entidade_id, "
           "date '2026-07-01' + d::int as dia, m::smallint as metrica, "
           "((c*31 + e*17 + d*13 + m*7 + {v}) * 2654435761) % 50000000 as valor, "
           "timestamptz '2026-07-01 09:00:00+00' + to_days((d+1)::int) + to_hours(({v}*6)::int) as disponivel_em "
           f"from range(1,{contas}+1) t1(c), range(1,{ent}+1) t2(e), range(0,{dias}) t3(d), range(1,{N_MET}+1) t4(m)")
    con.execute("create table obs as " + sel.format(v=1) + " union all " + sel.format(v=2)
                + " where ((c*7919 + e*104729 + d*1299709 + m*15485863) % 10) = 0")
    pq = dir_tmp / f"obs_{n_alvo:.0e}.parquet".replace("+", "")
    con.execute(f"copy obs to '{pq}' (format parquet, compression zstd)")
    t_ger = time.perf_counter() - t0
    linhas = con.execute("select count(*) from obs").fetchone()[0]
    con.execute("drop table obs")
    asof = "2026-08-15 12:00:00+00"
    q = f"""select count(*), sum(valor) from (select valor, row_number() over (partition by conta_id, entidade_id, dia,
            metrica order by disponivel_em desc) rn from read_parquet('{pq}') where disponivel_em <= timestamptz '{asof}')
            where rn = 1"""
    tempos_duck = []
    for _ in range(4):
        t0 = time.perf_counter()
        r_duck = con.execute(q).fetchone()
        tempos_duck.append(time.perf_counter() - t0)
    os.environ.setdefault("POLARS_MAX_THREADS", "2")
    tempos_pl = []
    from datetime import datetime, timezone
    corte = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
    for _ in range(4):
        t0 = time.perf_counter()
        r_pl = (pl.scan_parquet(pq).filter(pl.col("disponivel_em") <= corte)
                .group_by(["conta_id", "entidade_id", "dia", "metrica"])
                .agg(pl.col("valor").sort_by("disponivel_em").last())
                .select(pl.len(), pl.col("valor").sum()).collect())
        tempos_pl.append(time.perf_counter() - t0)
    r_pl_t = (int(r_pl.item(0, 0)), int(r_pl.item(0, 1)))
    res = {"n_alvo": n_alvo, "linhas": linhas, "parquet_bytes": pq.stat().st_size, "parquet_bytes_por_linha": pq.stat().st_size / linhas,
           "geracao_s": t_ger, "duckdb_snapshot_s": statistics.median(tempos_duck[1:]),
           "polars_snapshot_s": statistics.median(tempos_pl[1:]), "chaves_no_snapshot": int(r_duck[0]),
           "resultados_iguais": (int(r_duck[0]), int(r_duck[1])) == r_pl_t}
    pq.unlink()
    con.close()
    return res


def snapshot_pg_total(cl: Cluster, n_alvo: int) -> dict:
    """Mesmo snapshot as_of completo no PostgreSQL (sem partição), para comparar com DuckDB/Polars."""
    tab = f"snap_{n_alvo:.0e}".replace("+", "")
    contas, ent, dias = _dims(n_alvo, N_MET)
    _guarda_disco(cl, int(n_alvo * 260))
    _criar(cl, tab, COLS_LONGO, False)
    cl.sql(_insert_longo(tab, contas, ent, dias))
    cl.sql(f"vacuum (freeze, analyze) {tab}")
    _indices(cl, tab, False, False)
    q = (f"select count(*), sum(valor) from (select distinct on (conta_id, nivel, entidade_id, segmento, dia, metrica) valor "
         f"from {tab} where disponivel_em <= timestamptz '2026-08-15 12:00:00+00' "
         f"order by conta_id, nivel, entidade_id, segmento, dia, metrica, disponivel_em desc) s")
    tempos = []
    for _ in range(4):
        t0 = time.perf_counter()
        r = cl.sql(q)
        tempos.append(time.perf_counter() - t0)
    cl.sql(f"drop table {tab}")
    cl.sql("checkpoint")
    return {"n_alvo": n_alvo, "pg_snapshot_s": statistics.median(tempos[1:]), "resultado": r,
            "nota": "inclui ~10-20 ms de processo psql"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--escalas", default="1e5,1e6,1e7")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--porta", type=int, default=54931)
    ap.add_argument("--raiz-tmp", default=None, help="diretório do cluster (padrão: artifacts/ do lab, gitignored)")
    ap.add_argument("--payload-linhas", type=int, default=20000)
    a = ap.parse_args()
    escalas = [int(float(x)) for x in a.escalas.split(",")]
    lab = Path(__file__).resolve().parents[1]
    raiz = Path(a.raiz_tmp) if a.raiz_tmp else lab / "artifacts" / "fundacao_capacidade_pg"
    if raiz.exists():
        shutil.rmtree(raiz)
    raiz.mkdir(parents=True)
    cl = Cluster(raiz, a.porta)
    resultado: dict = {"seed": SEED, "escalas": escalas, "ddl": "aproximação própria (SQL do worker A ausente)",
                       "medicoes": [], "inicio_epoch": time.time()}
    disco_ini = shutil.disk_usage(raiz).free
    pico = 0
    try:
        cl.iniciar()
        resultado["postgres"] = cl.sql("select version()")
        resultado["config"] = dict(x.split("|") for x in cl.sql(
            "select name, setting from pg_settings where name in ('fsync','synchronous_commit','wal_level',"
            "'shared_buffers','work_mem','default_toast_compression','block_size','autovacuum')").splitlines())
        cl.sql(PROC)
        t0 = time.perf_counter()
        resultado["payload"] = medir_payload(cl, a.payload_linhas, 200)
        resultado["payload_s"] = time.perf_counter() - t0
        for n in escalas:
            variantes = ["longo"] if n >= 10**7 else ["longo", "texto", "largo", "jsonb", "v21"]
            for v in variantes:
                for part in ((False, True) if v == "longo" else (False,)):
                    print(f"[pg] {v} part={part} n={n:.0e}", file=sys.stderr, flush=True)
                    m = medir_variante(cl, v, n, part, latencias=True)
                    pico = max(pico, m["dir_cluster_bytes_apos"])
                    resultado["medicoes"].append(m)
                    Path(a.saida).write_text(json.dumps(resultado, ensure_ascii=False, indent=1, default=str) + "\n")
        resultado["snapshot_pg"] = [snapshot_pg_total(cl, n) for n in escalas if n <= 10**6]
        pico = max(pico, cl.tamanho_dir())
    finally:
        cl.parar_e_apagar()
        resultado["cluster_apagado"] = not raiz.exists()
        resultado["pico_dir_cluster_bytes"] = pico
        resultado["disco_livre_inicio_gib"] = disco_ini / GIB
    dir_an = raiz.parent / "fundacao_capacidade_analitico"
    dir_an.mkdir(parents=True, exist_ok=True)
    try:
        resultado["analitico"] = [comparar_analitico(n, dir_an) for n in escalas if n <= 10**7]
    finally:
        shutil.rmtree(dir_an, ignore_errors=True)
    resultado["fim_epoch"] = time.time()
    resultado["duracao_s"] = resultado["fim_epoch"] - resultado["inicio_epoch"]
    Path(a.saida).write_text(json.dumps(resultado, ensure_ascii=False, indent=1, default=str) + "\n")
    print(json.dumps({"ok": True, "duracao_s": resultado["duracao_s"], "cluster_apagado": resultado["cluster_apagado"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
