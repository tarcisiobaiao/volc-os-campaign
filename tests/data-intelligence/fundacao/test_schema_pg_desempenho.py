"""Desempenho e tamanho do `dil_obs` (achados da frente B sobre o DDL 0001): as_of inlinável e chaves compactas.

- Na suíte: escala pequena (~2e4 linhas), prova o PLANO (a função `observacao_as_of` e a view
  `observacao_latest` são inlinadas: nenhum "Function Scan") e o formato das chaves (bytea de 32 bytes).
- Medição grande (fora da suíte): `DIL_BENCH_N=1000000 pytest ...::test_medicao_grande -s` imprime JSON com
  tempos e bytes; `DIL_BENCH_DDL=<arquivo.sql>` mede outra versão do DDL (ex.: a anterior, para o antes/depois).
  O cluster é o descartável do conftest (dedicado) e é apagado no fim.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest

UP = "dil_obs_0001_schema_observacao.sql"
MIGRACOES = Path(__file__).resolve().parents[3] / "experiments" / "data-intelligence-lab" / "migrations_candidatas"


def _carga_sql(n_ent: int, dias: int, versoes: int, contas: int = 10) -> str:
    """Carga direta (superusuário, sem as funções de escrita: mede leitura e espaço, não ingestão)."""
    return f"""
INSERT INTO dil_obs.run_coleta (run_id, fonte, coletor_nome, coletor_versao, iniciado_em, status)
VALUES ('r', 'google_ads', 'c', '1', '2025-01-01T00:00:00Z', 'running');
INSERT INTO dil_obs.payload_bruto (sha256, corpo_bruto, content_type, recebido_em)
VALUES (encode(sha256('x'::bytea), 'hex'), 'x'::bytea, 'text/plain', '2025-01-01T00:00:00Z');
INSERT INTO dil_obs.lote (lote_id, run_id, payload_sha256, schema_version, pedido, recebido_em, registrado_em)
VALUES ('l', 'r', encode(sha256('x'::bytea), 'hex'), 'v1', '{{}}', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
WITH b AS (
  SELECT c, e, d, v, timestamptz '2025-01-02 00:00:00-03' + make_interval(days => d) AS ji
    FROM generate_series(1, {contas}) c, generate_series(1, {n_ent}) e, generate_series(0, {dias} - 1) d,
         generate_series(1, {versoes}) v
), k AS (
  SELECT b.*, dil_obs._chave_natural('google_ads', 'c' || c, 'campaign', 'e' || e, ARRAY['campaign', 'day'], '[]'::jsonb,
                                      'cost', NULL, ji, ji + interval '1 day', 'America/Sao_Paulo') AS nat,
         ji + interval '1 day' + make_interval(hours => v * 7) AS obs_at
    FROM b
)
INSERT INTO dil_obs.observacao (chave_idempotencia, chave_natural, fonte, conta, entidade_tipo, entidade_id, grao,
  dimensoes, metrica, value_kind, valor, unidade, moeda, janela_inicio, janela_fim, timezone, observed_at,
  source_updated_at, available_at, ingested_at, run_id, request_id, lote_id, payload_sha256, payload_ref,
  schema_version, coletor_nome, coletor_versao, status, motivo, cobertura_ppm)
SELECT dil_obs._chave_base(nat, encode(sha256('x'::bytea), 'hex'), 'v1', 'c', '1', obs_at), nat, 'google_ads',
       'c' || c, 'campaign', 'e' || e, ARRAY['campaign', 'day'], '[]'::jsonb, 'cost', NULL, 1000000 * v + e, 'micros',
       'BRL', ji, ji + interval '1 day', 'America/Sao_Paulo', obs_at, NULL,
       -- chegada fora da ordem de medição em parte das versões (exercita a ordem do D1)
       obs_at + make_interval(mins => CASE WHEN (e + d + v) % 5 = 0 THEN 600 ELSE 5 END),
       obs_at + interval '11 hours', 'r', NULL, 'l', encode(sha256('x'::bytea), 'hex'),
       'sha256:' || encode(sha256('x'::bytea), 'hex'), 'v1', 'c', '1', 'observed', NULL, NULL
  FROM k;
ANALYZE dil_obs.observacao;
"""

# D2': uma confirmação por observação (releitura de mesmo estado uma hora depois), só para medir bytes/linha
CARGA_CONFIRMACOES = """
INSERT INTO dil_obs.confirmacao (chave_natural, observed_at, available_at, run_id, lote_id,
                                 observacao_confirmada, registrado_em)
SELECT chave_natural, observed_at + interval '1 hour',
       available_at + interval '1 hour', run_id, lote_id, observacao_id, ingested_at + interval '1 hour'
  FROM dil_obs.observacao;
ANALYZE dil_obs.confirmacao;
"""


def _plano(c, db, sql: str) -> str:
    return c.psql("EXPLAIN " + sql, db=db, papel="dil_obs_leitor")


def _tempo(c, db, sql: str, repeticoes: int = 3) -> list[float]:
    """Tempo no servidor (Planning + Execution do EXPLAIN ANALYZE), em segundos."""
    saida = []
    for _ in range(repeticoes):
        out = c.psql("EXPLAIN (ANALYZE, TIMING OFF) " + sql, db=db, papel="dil_obs_leitor", timeout=1800)
        ms = sum(float(x) for x in re.findall(r"(?:Planning|Execution) Time: ([0-9.]+) ms", out))
        saida.append(ms / 1000)
    return saida


def _tamanhos(c, db) -> dict:
    linhas = int(c.psql("SELECT count(*) FROM dil_obs.observacao;", db=db))
    heap = int(c.psql("SELECT pg_table_size('dil_obs.observacao');", db=db))
    idx = dict(ln.split("|") for ln in c.psql(
        "SELECT indexrelid::regclass::text, pg_relation_size(indexrelid) FROM pg_index "
        "WHERE indrelid = 'dil_obs.observacao'::regclass ORDER BY 1;", db=db).splitlines())
    total_idx = sum(int(v) for v in idx.values())
    saida = {"linhas": linhas, "heap_por_linha": round(heap / linhas, 1), "indices_por_linha": round(total_idx / linhas, 1),
             "total_por_valor": round((heap + total_idx) / linhas, 1), "indices_bytes": {k: int(v) for k, v in idx.items()}}
    if c.psql("SELECT to_regclass('dil_obs.confirmacao') IS NOT NULL;", db=db) == "t":
        nconf = int(c.psql("SELECT count(*) FROM dil_obs.confirmacao;", db=db))
        if nconf:
            tot = int(c.psql("SELECT pg_total_relation_size('dil_obs.confirmacao');", db=db))
            saida["confirmacao_por_linha"] = round(tot / nconf, 1)
    return saida


CONSULTAS = {
    "as_of_funcao_meio": "SELECT count(*), sum(valor) FROM dil_obs.observacao_as_of('{meio}')",
    "as_of_funcao_fim": "SELECT count(*), sum(valor) FROM dil_obs.observacao_as_of('{fim}')",
    "latest_view": "SELECT count(*), sum(valor) FROM dil_obs.observacao_latest",
    "as_of_ponto": "SELECT valor FROM dil_obs.observacao_as_of('{fim}') WHERE chave_natural = (SELECT chave_natural "
                   "FROM dil_obs.observacao ORDER BY observacao_id DESC LIMIT 1)",
}


def _medir(c, db, n_ent, dias, versoes, ddl: str = UP) -> dict:
    t0 = time.monotonic()
    c.psql((Path(ddl) if os.path.isabs(ddl) else MIGRACOES / ddl).read_text(encoding="utf-8"), db=db)
    c.psql(_carga_sql(n_ent, dias, versoes), db=db, timeout=3600)
    if c.psql("SELECT to_regclass('dil_obs.confirmacao') IS NOT NULL;", db=db) == "t":
        c.psql(CARGA_CONFIRMACOES, db=db, timeout=3600)
    carga = time.monotonic() - t0
    meio, fim = "2025-01-02T00:00:00Z", "2030-01-01T00:00:00Z"
    if dias > 1:
        meio = c.psql(f"SELECT (timestamptz '2025-01-02 00:00:00-03' + make_interval(days => {dias // 2}))::text;", db=db)
    res = {"n_ent": n_ent, "dias": dias, "versoes": versoes, "carga_s": round(carga, 1), "tamanho": _tamanhos(c, db)}
    for nome, sql in CONSULTAS.items():
        q = sql.format(meio=meio, fim=fim)
        plano = _plano(c, db, q)
        res[nome] = {"inlinada": "Function Scan" not in plano, "tempos_s": [round(x, 3) for x in _tempo(c, db, q)]}
    return res


def test_as_of_e_latest_sao_inlinados_e_chaves_compactas(cluster_pg):
    c = cluster_pg
    db = c.novo_banco("dil_desempenho")
    r = _medir(c, db, n_ent=20, dias=25, versoes=4)  # 10 × 20 × 25 × 4 = 20.000 linhas
    assert r["tamanho"]["linhas"] == 20_000
    for nome in CONSULTAS:
        assert r[nome]["inlinada"], (nome, r)
    tipos = c.psql("SELECT string_agg(attname || ':' || format_type(atttypid, atttypmod), ',' ORDER BY attname) "
                   "FROM pg_attribute WHERE attrelid = 'dil_obs.observacao'::regclass "
                   "AND attname IN ('chave_natural', 'chave_idempotencia');", db=db)
    assert tipos == "chave_idempotencia:bytea,chave_natural:bytea"
    assert c.psql("SELECT bool_and(octet_length(chave_natural) = 32 AND octet_length(chave_idempotencia) = 32) "
                  "FROM dil_obs.observacao;", db=db) == "t"
    # D2': a confirmação custa uma fração da observação (sem payload, dimensões, textos de linhagem)
    assert r["tamanho"]["confirmacao_por_linha"] < r["tamanho"]["total_por_valor"] / 2, r["tamanho"]
    nomes = set(r["tamanho"]["indices_bytes"])
    assert nomes == {"dil_obs.observacao_pkey", "dil_obs.uq_obs_chave_idempotencia", "dil_obs.uq_obs_versao",
                     "dil_obs.ix_obs_asof", "dil_obs.ix_obs_entidade", "dil_obs.ix_obs_run"}, nomes
    # o as_of inlinado continua igual ao da função escrita à mão (mesma ordem de versão do D1)
    manual = c.psql("SELECT count(*) || ':' || sum(valor) FROM (SELECT DISTINCT ON (chave_natural) valor FROM dil_obs.observacao "
                    "WHERE available_at <= '2030-01-01' ORDER BY chave_natural, observed_at DESC, available_at DESC) s;", db=db)
    funcao = c.psql("SELECT count(*) || ':' || sum(valor) FROM dil_obs.observacao_as_of('2030-01-01');", db=db, papel="dil_obs_leitor")
    assert manual == funcao


@pytest.mark.skipif(not os.environ.get("DIL_BENCH_N"), reason="medição grande: defina DIL_BENCH_N (ex.: 100000 ou 1000000)")
def test_medicao_grande(cluster_pg_dedicado):
    n = int(os.environ["DIL_BENCH_N"])
    escalas = {100_000: (50, 50, 4), 1_000_000: (100, 250, 4)}
    n_ent, dias, versoes = escalas.get(n, (100, max(1, n // 4000), 4))
    c = cluster_pg_dedicado
    db = c.novo_banco("dil_bench")
    r = _medir(c, db, n_ent, dias, versoes, ddl=os.environ.get("DIL_BENCH_DDL", UP))
    r["ddl"] = os.environ.get("DIL_BENCH_DDL", UP)
    r["dir_cluster_bytes"] = sum(f.stat().st_size for f in c.raiz.rglob("*") if f.is_file())
    print("\nMEDICAO " + json.dumps(r, ensure_ascii=False))
    c.psql(f"DROP DATABASE {db};")
