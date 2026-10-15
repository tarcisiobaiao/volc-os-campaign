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
import re
import time
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

# O dump de produção é schema-only: cofre_gaveta e cofre_tipo chegam vazias.
# O teste reproduz isso esvaziando as duas depois da v13_01, e semeia só o par
# de que a fixture precisa, igual à suíte do lab (ON CONFLICT DO NOTHING).
ESVAZIAR_REFERENCIA = "DELETE FROM public.cofre_tipo; DELETE FROM public.cofre_gaveta;"
REFERENCIA = [
    "INSERT INTO public.cofre_gaveta (cluster, rotulo, descricao, ordem) VALUES ('paid_media', "
    "'Midia paga', 'Gerenciadores e contas que compram midia nas plataformas.', 2) ON CONFLICT DO NOTHING",
    "INSERT INTO public.cofre_tipo (kind, cluster, rotulo) VALUES ('meta_ad_account', 'paid_media', "
    "'Conta de anuncios Meta') ON CONFLICT DO NOTHING",
]

SEMENTE = [f"""
INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade,
  resumo, dono_nome, dono_custodia, capacidades, proxima_acao)
VALUES ('{ATIVO}', 'meta_ad_account', 'paid_media', 'Conta Meta lab W15', 'Meta Ads', 'ready',
  'high', 'Conta sintetica do laboratorio W15.', 'VOLC', 'verified', ARRAY['meta_read'], 'Nenhuma acao: fixture de teste descartavel.')
""", f"""
INSERT INTO public.trafego_meta_ad_account (cofre_ativo_id, account_external_id, moeda,
  timezone_name, readiness_state)
VALUES ('{ATIVO}', '9990001', 'BRL', 'America/Sao_Paulo', 'READY_FOR_READ')
"""]


def _fato(fid: str, objeto: str, dia: str, observado: str, spend: str, completo: bool) -> str:
    spend_sql = "NULL" if spend is None else spend
    return f"""
INSERT INTO public.trafego_meta_insight_daily (meta_insight_daily_id, ad_account_ativo_id,
  conta_externa, nivel, objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao,
  breakdown, observado_em, spend, impressions, currency, account_timezone, completo)
VALUES ('{fid}', '{ATIVO}', '9990001', 'adset', '{objeto}', '{dia}', '{dia}', 'default',
  'none', '{observado}', {spend_sql}, 100, 'BRL', 'America/Sao_Paulo', {str(completo).lower()})
"""


# Cenários, um grão (objeto) cada, todos no dia 2026-10-10:
#   A: D-1 completo (11/10) e recoleta INCOMPLETA mais nova (15/10) → vence o D-1
#   B: D-1 completo e recoleta COMPLETA mais nova                  → vence a recoleta
#   C: só incompletas                                              → a mais nova, completo=false
#   D: completa velha, incompleta nova, completa mais nova ainda   → a completa mais nova
FATOS = [
    _fato("w15-a1", "1001", "2026-10-10", "2026-10-11T10:00:00Z", "10.00", True),
    _fato("w15-a2", "1001", "2026-10-10", "2026-10-15T11:30:00Z", "3.00", False),
    _fato("w15-b1", "1002", "2026-10-10", "2026-10-11T10:00:00Z", "10.00", True),
    _fato("w15-b2", "1002", "2026-10-10", "2026-10-15T11:30:00Z", "12.50", True),
    _fato("w15-c1", "1003", "2026-10-10", "2026-10-11T10:00:00Z", "4.00", False),
    _fato("w15-c2", "1003", "2026-10-10", "2026-10-15T11:30:00Z", "5.00", False),
    _fato("w15-d1", "1004", "2026-10-10", "2026-10-11T10:00:00Z", "10.00", True),
    _fato("w15-d2", "1004", "2026-10-10", "2026-10-13T11:30:00Z", "1.00", False),
    _fato("w15-d3", "1004", "2026-10-10", "2026-10-15T11:30:00Z", "11.00", True),
]

CORRENTE = """SELECT string_agg(objeto_externo || '=' || meta_insight_daily_id || ':' || completo, ',' ORDER BY objeto_externo)
  FROM public.vw_trafego_meta_insight_latest WHERE ad_account_ativo_id = '""" + ATIVO + "'"

# Fail-closed: ACL nula vira NULL (leitura vazia) e Banco.fp() recusa; COMMENT
# nulo é marcado, não some do concat_ws.
FINGERPRINT = """SELECT CASE WHEN c.relacl IS NULL THEN NULL ELSE md5(concat_ws('|',
  pg_get_viewdef(c.oid, true),
  coalesce(array_to_string(c.reloptions, ','), '<sem reloptions>'),
  array_to_string(c.relacl, ','),
  coalesce(obj_description(c.oid, 'pg_class'), '<sem COMMENT>'),
  (SELECT string_agg(attname || ':' || format_type(atttypid, atttypmod), ',' ORDER BY attnum)
     FROM pg_attribute WHERE attrelid = c.oid AND attnum > 0))) END
  FROM pg_class c WHERE c.oid = 'public.vw_trafego_meta_insight_latest'::regclass"""


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

    def inserir(self, insert: str) -> int:
        """Roda um INSERT (sem ';') e devolve quantas linhas entraram."""
        return int(self.valor(f"WITH w15_ins AS ({insert} RETURNING 1) SELECT count(*) FROM w15_ins"))

    def fp(self) -> str:
        v = self.valor(FINGERPRINT)
        assert re.fullmatch(r"[0-9a-f]{32}", v), f"fingerprint invalido (erro ou ACL nula): {v!r}"
        return v

    def meta(self) -> str:
        v = self.valor(COMMENT_E_ACL)
        assert v, "COMMENT/ACL/dono invalido (ACL nula)"
        return v

    def valor(self, sql: str, **kw) -> str:
        p = self.run(sql, **kw)
        assert p.returncode == 0, p.stderr
        return p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""


# Estados de partida da view. A v26_01 e o rollback só trocam a definição;
# dono, grants e COMMENT têm de sobreviver exatamente como estavam.
#   repositorio: como 20260907210000 deixa (com COMMENT)
#   producao:    como o integrador achou no lab do Mac: view SEM COMMENT
#   acl_extra:   sem COMMENT e com um grant a mais que a migration não conhece
ESTADOS = {
    "repositorio": "",
    "producao": "COMMENT ON VIEW public.vw_trafego_meta_insight_latest IS NULL;",
    "acl_extra": (
        "COMMENT ON VIEW public.vw_trafego_meta_insight_latest IS NULL; "
        "DO $$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='w15_leitor') "
        "THEN CREATE ROLE w15_leitor NOLOGIN; END IF; END$$; "
        "GRANT SELECT ON public.vw_trafego_meta_insight_latest TO w15_leitor;"
    ),
}

COMMENT_E_ACL = """SELECT coalesce(obj_description('public.vw_trafego_meta_insight_latest'::regclass, 'pg_class'), '<sem COMMENT>')
  || ' | ' || array_to_string(relacl, ',') || ' | ' || pg_get_userbyid(relowner)
  FROM pg_class WHERE oid = 'public.vw_trafego_meta_insight_latest'::regclass"""


@pytest.fixture(scope="module", params=sorted(ESTADOS))
def banco(request):
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
            if f.startswith("v13_01"):
                # como o dump schema-only de produção: referência vazia
                p = b.run(ESVAZIAR_REFERENCIA)
                assert p.returncode == 0, p.stderr
                assert b.valor("SELECT count(*) FROM public.cofre_tipo") == "0"
                assert b.valor("SELECT count(*) FROM public.cofre_gaveta") == "0"
        for ins in REFERENCIA:
            b.inserir(ins)
        assert b.valor("SELECT count(*) FROM public.cofre_tipo "
                       "WHERE kind = 'meta_ad_account' AND cluster = 'paid_media'") == "1"
        # cada INSERT de prova confere exatamente 1 linha
        for ins in SEMENTE + FATOS:
            assert b.inserir(ins) == 1, ins
        assert b.valor("SELECT count(*) FROM public.trafego_meta_insight_daily "
                       f"WHERE ad_account_ativo_id = '{ATIVO}'") == "9"
        if ESTADOS[request.param]:
            p = b.run(ESTADOS[request.param])
            assert p.returncode == 0, p.stderr
        b.estado = request.param
        yield b
    finally:
        subprocess.run(admin + ["-c", f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)"],
                       capture_output=True)


def test_ciclo_completo_da_v26_01(banco):
    # ── antes: o defeito, medido ────────────────────────────────────────────
    fp_antes = banco.fp()
    meta_antes = banco.meta()
    if banco.estado != "repositorio":
        assert meta_antes.startswith("<sem COMMENT> | "), meta_antes
    assert banco.valor(CORRENTE) == (
        "1001=w15-a2:false,1002=w15-b2:true,1003=w15-c2:false,1004=w15-d3:true")

    # ── aplicar ─────────────────────────────────────────────────────────────
    p = banco.run(arquivo=APLICAR)
    assert p.returncode == 0, p.stderr
    assert banco.valor(CORRENTE) == (
        "1001=w15-a1:true,1002=w15-b2:true,1003=w15-c2:false,1004=w15-d3:true")
    # só a definição muda: COMMENT, grants e dono ficam exatamente como estavam
    assert banco.meta() == meta_antes
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
    fp_depois = banco.fp()
    p = banco.run(arquivo=APLICAR)
    assert p.returncode != 0 and "ja parece aplicada" in p.stderr
    assert banco.fp() == fp_depois

    # ── reverter devolve exatamente o antes, e é idempotente ────────────────
    p = banco.run(arquivo=REVERTER)
    assert p.returncode == 0, p.stderr
    assert banco.fp() == fp_antes
    assert banco.meta() == meta_antes
    assert banco.valor(CORRENTE).startswith("1001=w15-a2:false")
    p = banco.run(arquivo=REVERTER)
    assert p.returncode == 0, p.stderr
    assert banco.fp() == fp_antes

    # ── reaplicar depois do rollback dá o mesmo estado de antes ─────────────
    p = banco.run(arquivo=APLICAR)
    assert p.returncode == 0, p.stderr
    assert banco.fp() == fp_depois
    assert banco.valor(CORRENTE) == (
        "1001=w15-a1:true,1002=w15-b2:true,1003=w15-c2:false,1004=w15-d3:true")


def test_papel_sem_ser_dono_e_recusado(banco):
    p = banco.run("CREATE ROLE w15_intruso NOLOGIN;")
    assert p.returncode == 0 or "already exists" in p.stderr
    corpo = APLICAR.read_text(encoding="utf-8").replace("\\set ON_ERROR_STOP on", "")
    p = banco.run("SET ROLE w15_intruso;\n" + corpo)
    assert p.returncode != 0 and "deve rodar como postgres ou supabase_admin" in p.stderr


def test_reloptions_diferentes_sao_recusadas_sem_mudar_nada(banco):
    # O WITH (security_invoker = true) reescreveria reloptions; as duas
    # guardas recusam em vez de mudar a view em silêncio.
    p = banco.run("ALTER VIEW public.vw_trafego_meta_insight_latest SET (security_barrier = true);")
    assert p.returncode == 0, p.stderr
    try:
        fp = banco.fp()
        for arquivo in (APLICAR, REVERTER):
            p = banco.run(arquivo=arquivo)
            assert p.returncode != 0 and "reloptions da view nao sao exatamente" in p.stderr, arquivo
            assert banco.fp() == fp
    finally:
        p = banco.run("ALTER VIEW public.vw_trafego_meta_insight_latest RESET (security_barrier);")
        assert p.returncode == 0, p.stderr


def test_lock_timeout_falha_e_desfaz_em_vez_de_esperar(banco):
    # Uma leitura longa segura AccessShareLock na view. O CREATE OR REPLACE
    # pede AccessExclusiveLock: com lock_timeout = 5s a migration e o rollback
    # falham, desfazem e não mudam nada, em vez de esperar indefinidamente.
    # Parte da view revertida, para a guarda da v26_01 deixar chegar ao lock.
    p = banco.run(arquivo=REVERTER)
    assert p.returncode == 0, p.stderr
    fp = banco.fp()
    leitor = subprocess.Popen(
        ["psql", banco.dsn, "-X", "-q", "-v", "ON_ERROR_STOP=1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        leitor.stdin.write("BEGIN; SELECT count(*) FROM public.vw_trafego_meta_insight_latest; "
                           "SELECT pg_sleep(60);\n")
        leitor.stdin.flush()
        for _ in range(50):
            if banco.valor("SELECT count(*) FROM pg_locks l JOIN pg_class c ON c.oid = l.relation "
                           "WHERE c.relname = 'vw_trafego_meta_insight_latest' AND l.granted "
                           "AND l.pid <> pg_backend_pid()") != "0":
                break
            time.sleep(0.1)
        else:
            pytest.fail("o leitor não chegou a segurar a view")
        for arquivo in (APLICAR, REVERTER):
            t0 = time.monotonic()
            try:
                p = subprocess.run(["psql", banco.dsn, "-v", "ON_ERROR_STOP=1", "-X", "-q", "-At",
                                    "-f", str(arquivo)], capture_output=True, text=True, timeout=30)
            except subprocess.TimeoutExpired:
                pytest.fail(f"{arquivo.name} esperou o lock por 30s: sem lock_timeout")
            gasto = time.monotonic() - t0
            assert p.returncode != 0 and "lock timeout" in p.stderr, (arquivo, p.stderr)
            assert 4 <= gasto < 30, (arquivo, gasto)
            assert banco.fp() == fp
    finally:
        # matar o psql não encerra o backend parado em pg_sleep: termina-o
        banco.valor("SELECT count(pg_terminate_backend(l.pid)) FROM pg_locks l "
                    "JOIN pg_class c ON c.oid = l.relation "
                    "WHERE c.relname = 'vw_trafego_meta_insight_latest' AND l.pid <> pg_backend_pid()")
        leitor.kill()
        leitor.wait()
    # sem o leitor, as duas voltam a passar
    p = banco.run(arquivo=APLICAR)
    assert p.returncode == 0, p.stderr
    assert banco.fp() != fp
