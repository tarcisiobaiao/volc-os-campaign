"""v26_01 (W15): `vw_trafego_meta_insight_latest` prefere a revisão COMPLETA.

Prova num PostgreSQL DESCARTÁVEL, nunca no Supabase oficial. O teste cria um
banco novo e efêmero no servidor apontado por `VOLC_PG_DESCARTAVEL` (DSN de
superusuário de um servidor de laboratório, em forma de palavras-chave), aplica a cadeia Meta do repositório
e a v26_01, prova, reverte e apaga o banco. Sem a variável, o teste é PULADO
com motivo — pulado não é prova; a prova oficial é a suíte
`tools/freedom-lab/db/suites/v26_w15.sh` pelo `lab.sh` no Mac.

Dados 100% sintéticos (conta `9990001`, ativo `meta_account_metaacct_w15lab`).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MIG = RAIZ / "supabase" / "migrations"
CADEIA = [
    "v13_01_cofre_de_ativos.sql",
    "v15_01_meta_ads_read_model.sql",
    "v15_02_meta_ads_insights.sql",
    "20260907210000_meta_read_model_consistency.sql",
    "20260908000000_meta_insights_escopo.sql",
    "20260908120000_meta_financeiro_conjunto_dia.sql",
]
APLICAR = MIG / "v26_01_meta_insight_latest_completa.sql"
REVERTER = MIG / "v26_01_rollback.sql"
DSN = os.environ.get("VOLC_PG_DESCARTAVEL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN or shutil.which("psql") is None,
    reason="sem VOLC_PG_DESCARTAVEL/psql: prova SQL nao executada (lacuna, nao aprovacao)",
)

ATIVO = "meta_account_metaacct_w15lab"

SEMENTE = f"""
INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade,
  resumo, dono_nome, dono_custodia, capacidades, proxima_acao)
VALUES ('{ATIVO}', 'meta_ad_account', 'paid_media', 'Conta Meta lab W15', 'Meta Ads', 'ready',
  'high', 'Conta sintetica do laboratorio W15.', 'VOLC', 'verified', ARRAY['meta_read'], 'Nenhuma acao: fixture de teste descartavel.');
INSERT INTO public.trafego_meta_ad_account (cofre_ativo_id, account_external_id, moeda,
  timezone_name, readiness_state)
VALUES ('{ATIVO}', '9990001', 'BRL', 'America/Sao_Paulo', 'READY_FOR_READ');
"""


def _fato(fid: str, objeto: str, dia: str, observado: str, spend: str, completo: bool) -> str:
    spend_sql = "NULL" if spend is None else spend
    return f"""
INSERT INTO public.trafego_meta_insight_daily (meta_insight_daily_id, ad_account_ativo_id,
  conta_externa, nivel, objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao,
  breakdown, observado_em, spend, impressions, currency, account_timezone, completo)
VALUES ('{fid}', '{ATIVO}', '9990001', 'adset', '{objeto}', '{dia}', '{dia}', 'default',
  'none', '{observado}', {spend_sql}, 100, 'BRL', 'America/Sao_Paulo', {str(completo).lower()});
"""


# Cenários, um grão (objeto) cada, todos no dia 2026-10-10:
#   A: D-1 completo (11/10) e recoleta INCOMPLETA mais nova (15/10) → vence o D-1
#   B: D-1 completo e recoleta COMPLETA mais nova                  → vence a recoleta
#   C: só incompletas                                              → a mais nova, completo=false
#   D: completa velha, incompleta nova, completa mais nova ainda   → a completa mais nova
FATOS = "".join([
    _fato("w15-a1", "1001", "2026-10-10", "2026-10-11T10:00:00Z", "10.00", True),
    _fato("w15-a2", "1001", "2026-10-10", "2026-10-15T11:30:00Z", "3.00", False),
    _fato("w15-b1", "1002", "2026-10-10", "2026-10-11T10:00:00Z", "10.00", True),
    _fato("w15-b2", "1002", "2026-10-10", "2026-10-15T11:30:00Z", "12.50", True),
    _fato("w15-c1", "1003", "2026-10-10", "2026-10-11T10:00:00Z", "4.00", False),
    _fato("w15-c2", "1003", "2026-10-10", "2026-10-15T11:30:00Z", "5.00", False),
    _fato("w15-d1", "1004", "2026-10-10", "2026-10-11T10:00:00Z", "10.00", True),
    _fato("w15-d2", "1004", "2026-10-10", "2026-10-13T11:30:00Z", "1.00", False),
    _fato("w15-d3", "1004", "2026-10-10", "2026-10-15T11:30:00Z", "11.00", True),
])

CORRENTE = """SELECT string_agg(objeto_externo || '=' || meta_insight_daily_id || ':' || completo, ',' ORDER BY objeto_externo)
  FROM public.vw_trafego_meta_insight_latest WHERE ad_account_ativo_id = '""" + ATIVO + "'"

FINGERPRINT = """SELECT md5(concat_ws('|',
  pg_get_viewdef('public.vw_trafego_meta_insight_latest'::regclass, true),
  (SELECT array_to_string(reloptions, ',') FROM pg_class WHERE oid = 'public.vw_trafego_meta_insight_latest'::regclass),
  (SELECT array_to_string(relacl, ',') FROM pg_class WHERE oid = 'public.vw_trafego_meta_insight_latest'::regclass),
  obj_description('public.vw_trafego_meta_insight_latest'::regclass, 'pg_class'),
  (SELECT string_agg(attname || ':' || format_type(atttypid, atttypmod), ',' ORDER BY attnum)
     FROM pg_attribute WHERE attrelid = 'public.vw_trafego_meta_insight_latest'::regclass AND attnum > 0)))"""


class Banco:
    def __init__(self, dsn_db: str):
        self.dsn = dsn_db

    def run(self, sql: str | None = None, *, arquivo: Path | None = None, papel: str | None = None):
        args = ["psql", self.dsn, "-v", "ON_ERROR_STOP=1", "-X", "-q", "-At"]
        if arquivo is not None:
            args += ["-f", str(arquivo)]
            entrada = None
        else:
            corpo = sql if papel is None else f"BEGIN; SET LOCAL ROLE {papel};\n{sql}\nROLLBACK;"
            entrada = corpo
        return subprocess.run(args, input=entrada, capture_output=True, text=True)

    def valor(self, sql: str, **kw) -> str:
        p = self.run(sql, **kw)
        assert p.returncode == 0, p.stderr
        return p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""


@pytest.fixture(scope="module")
def banco():
    nome = "w15_v26_" + uuid.uuid4().hex[:10]
    admin = ["psql", DSN, "-v", "ON_ERROR_STOP=1", "-X", "-q"]
    subprocess.run(admin + ["-c", f"CREATE DATABASE {nome}"], check=True, capture_output=True)
    # DSN em forma de palavras-chave (`host=... port=... user=...`): o último
    # `dbname=` vence, e o teste nunca toca o banco do DSN além de criar e apagar.
    b = Banco(f"{DSN} dbname={nome}")
    try:
        prep = ("DO $$BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF; "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF; "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF; "
                "END$$; CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        p = b.run(prep)
        assert p.returncode == 0, p.stderr
        for f in CADEIA:
            p = b.run(arquivo=MIG / f)
            assert p.returncode == 0, f"{f}: {p.stderr[-2000:]}"
        p = b.run(SEMENTE + FATOS)
        assert p.returncode == 0, p.stderr
        yield b
    finally:
        subprocess.run(admin + ["-c", f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)"],
                       capture_output=True)


def test_ciclo_completo_da_v26_01(banco):
    # ── antes: o defeito, medido ────────────────────────────────────────────
    fp_antes = banco.valor(FINGERPRINT)
    assert banco.valor(CORRENTE) == (
        "1001=w15-a2:false,1002=w15-b2:true,1003=w15-c2:false,1004=w15-d3:true")

    # ── aplicar ─────────────────────────────────────────────────────────────
    p = banco.run(arquivo=APLICAR)
    assert p.returncode == 0, p.stderr
    assert banco.valor(CORRENTE) == (
        "1001=w15-a1:true,1002=w15-b2:true,1003=w15-c2:false,1004=w15-d3:true")
    # uma linha por grão, nunca duas
    assert banco.valor(f"SELECT count(*) FROM public.vw_trafego_meta_insight_latest "
                       f"WHERE ad_account_ativo_id = '{ATIVO}'") == "4"
    # o financeiro conjunto-dia continua de pé e lê o número completo
    assert banco.valor("SELECT to_regclass('public.vw_trafego_meta_financeiro_conjunto_dia') IS NOT NULL "
                       "AND to_regclass('public.vw_trafego_meta_financeiro_campanha_dia') IS NOT NULL") == "t"
    assert banco.valor("SELECT spend FROM public.vw_trafego_meta_insight_latest "
                       "WHERE objeto_externo = '1001'") == "10.00"

    # ── segurança: invoker preservado, só service_role lê ───────────────────
    assert banco.valor("SELECT array_to_string(reloptions, ',') FROM pg_class "
                       "WHERE oid = 'public.vw_trafego_meta_insight_latest'::regclass") \
        == "security_invoker=true"
    for papel in ("anon", "authenticated"):
        p = banco.run("SELECT 1 FROM public.vw_trafego_meta_insight_latest LIMIT 1;", papel=papel)
        assert p.returncode != 0 and "permission denied" in p.stderr, papel
    assert banco.valor("SELECT has_table_privilege('service_role', "
                       "'public.vw_trafego_meta_insight_latest', 'SELECT')") == "t"
    assert banco.valor("SELECT has_table_privilege('service_role', "
                       "'public.vw_trafego_meta_insight_latest', 'INSERT')") == "f"

    # ── reaplicar por cima é recusado, e a recusa não muda nada ─────────────
    fp_depois = banco.valor(FINGERPRINT)
    p = banco.run(arquivo=APLICAR)
    assert p.returncode != 0 and "ja parece aplicada" in p.stderr
    assert banco.valor(FINGERPRINT) == fp_depois

    # ── reverter devolve exatamente o antes, e é idempotente ────────────────
    p = banco.run(arquivo=REVERTER)
    assert p.returncode == 0, p.stderr
    assert banco.valor(FINGERPRINT) == fp_antes
    assert banco.valor(CORRENTE).startswith("1001=w15-a2:false")
    p = banco.run(arquivo=REVERTER)
    assert p.returncode == 0, p.stderr
    assert banco.valor(FINGERPRINT) == fp_antes

    # ── reaplicar depois do rollback dá o mesmo estado de antes ─────────────
    p = banco.run(arquivo=APLICAR)
    assert p.returncode == 0, p.stderr
    assert banco.valor(FINGERPRINT) == fp_depois
    assert banco.valor(CORRENTE) == (
        "1001=w15-a1:true,1002=w15-b2:true,1003=w15-c2:false,1004=w15-d3:true")


def test_papel_sem_ser_dono_e_recusado(banco):
    p = banco.run("CREATE ROLE w15_intruso NOLOGIN;")
    assert p.returncode == 0 or "already exists" in p.stderr
    corpo = APLICAR.read_text(encoding="utf-8").replace("\\set ON_ERROR_STOP on", "")
    p = banco.run("SET ROLE w15_intruso;\n" + corpo)
    assert p.returncode != 0 and "deve rodar como postgres ou supabase_admin" in p.stderr
