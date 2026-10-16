"""Regressões da revisão adversarial R1 no banco (achados F1–F22 da thread A, mutações e hipóteses H3/H4).

Cada teste reproduz a prova do revisor (`r1-scratch/pg/*.py`) como asserção: falhava em `0c58f4ce` e
passa agora. Cluster PostgreSQL 16 descartável (conftest); relógio do banco simulado por
`ClusterPG.sql_relogio` (só no cluster de teste).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest

UP = "dil_obs_0001_schema_observacao.sql"
DOWN = "dil_obs_0001_schema_observacao.down.sql"
BRT = timezone(timedelta(hours=-3))
BASE = datetime(2026, 8, 1, tzinfo=BRT)
RESIDUO = ("SELECT (SELECT count(*) FROM pg_namespace WHERE nspname = 'dil_obs') || '|' || "
           "(SELECT count(*) FROM pg_roles WHERE rolname LIKE 'dil\\_obs\\_%');")


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _obs_json(obs, *, conta: str, payload: bytes, run_id: str, lote_id: str, h: float = 30, **kw) -> dict:
    t = BASE + timedelta(hours=h)
    kw.setdefault("observed_at", BASE + timedelta(hours=24))
    o = obs(payload=payload, conta=conta, janela_inicio=BASE, janela_fim=BASE + timedelta(days=1),
            available_at=t, ingested_at=t, run_id=run_id, lote_id=lote_id, **kw)
    return o.para_json()


def _preparo(c, *, run_id: str, payload: bytes, lote_id: str, fonte="google_ads", coletor=("coleta_canonica_google_ads", "1.0.0"),
             schema="google_ads.gaql.campaign_day.v1", t: datetime) -> str:
    return (c.sql_relogio(t, "dil_obs_escritor")
            + f"SELECT dil_obs.registrar_run({_lit(run_id)}, {_lit(fonte)}, {_lit(coletor[0])}, {_lit(coletor[1])}, {_lit(BASE.isoformat())});\n"
            + f"SELECT dil_obs.registrar_payload({_lit(_sha(payload))}, decode({_lit(payload.hex())}, 'hex'), 'application/json');\n"
            + f"SELECT dil_obs.registrar_lote({_lit(lote_id)}, {_lit(run_id)}, {_lit(_sha(payload))}, {_lit(schema)}, '{{}}', NULL);\n")


def _reg(j: dict) -> str:
    return f"SELECT 'R:' || dil_obs.registrar_observacao({_lit(json.dumps(j))}::json);\n"


@pytest.fixture
def banco(cluster_pg):
    db = cluster_pg.novo_banco("dil_r1")
    cluster_pg.aplicar(UP, db=db)
    yield db
    cluster_pg.psql(cluster_pg.sql_relogio(None), db=db)


# ============================================================== F2 / F22: quem aplica não fica dono
def test_r1_f2_aplicador_nao_superusuario_nao_continua_dono(cluster_pg_dedicado, obs):
    c = cluster_pg_dedicado
    c.psql("CREATE ROLE aplicador LOGIN CREATEROLE NOSUPERUSER;")
    db = c.novo_banco("dil_aplicador")
    c.psql(f"GRANT CREATE ON DATABASE {db} TO aplicador;")
    c.aplicar(UP, db=db, usuario="aplicador")
    assert c.psql("SELECT pg_has_role('aplicador', 'dil_obs_dono', 'SET')::text || pg_has_role('aplicador', 'dil_obs_dono', 'USAGE')::text;",
                  db=db) == "falsefalse"
    j = _obs_json(obs, conta="c", payload=b"abc", run_id="r", lote_id="l")
    c.psql(_preparo(c, run_id="r", payload=b"abc", lote_id="l", t=BASE + timedelta(hours=30)) + _reg(j), db=db, papel="dil_obs_escritor")
    # ataque do revisor (pg/t_dono2.py), agora sem efeito
    assert "permission denied to set role" in c.falha("SET ROLE dil_obs_dono;", db=db, usuario="aplicador")
    assert "permission denied" in c.falha("UPDATE dil_obs.observacao SET valor = 999999;", db=db, usuario="aplicador")
    assert "permission denied" in c.falha("TRUNCATE dil_obs.observacao;", db=db, usuario="aplicador")
    erro = c.falha("ALTER TABLE dil_obs.observacao DISABLE TRIGGER tg_obs_append_only;", db=db, usuario="aplicador")
    assert "permission denied" in erro or "must be owner" in erro
    assert c.psql("SELECT valor FROM dil_obs.observacao;", db=db) == "5000000"
    # o mesmo aplicador desfaz (ele criou os papéis, tem ADMIN OPTION) e não sobra nada
    c.psql(c.sql_relogio(None), db=db)
    c.aplicar(DOWN, db=db, usuario="aplicador")
    assert c.psql(RESIDUO, db=db) == "0|0"


def test_r1_f22_papeis_existentes_reaplicacao_por_nao_superusuario(cluster_pg_dedicado):
    c = cluster_pg_dedicado
    outro = c.novo_banco("dil_outro")
    c.aplicar(UP, db=outro)  # superusuário cria os papéis noutro banco
    c.psql("CREATE ROLE aplicador2 LOGIN CREATEROLE NOSUPERUSER;")
    db = c.novo_banco("dil_aplicador2")
    c.psql(f"GRANT CREATE ON DATABASE {db} TO aplicador2;")
    erro = c.falha(_ler(UP), db=db, usuario="aplicador2")
    assert "não pode administrar o papel dil_obs_dono" in erro and "WITH ADMIN OPTION" in erro
    assert c.psql("SELECT count(*) FROM pg_namespace WHERE nspname = 'dil_obs';", db=db) == "0"  # nada pela metade
    c.psql("GRANT dil_obs_dono TO aplicador2 WITH ADMIN OPTION, INHERIT FALSE, SET FALSE;")
    c.aplicar(UP, db=db, usuario="aplicador2")
    assert c.psql("SELECT count(*) FROM pg_namespace WHERE nspname = 'dil_obs';", db=db) == "1"
    assert "permission denied to set role" in c.falha("SET ROLE dil_obs_dono;", db=db, usuario="aplicador2")


def test_r1_f2_membro_permanente_recebe_aviso(cluster_pg_dedicado):
    c = cluster_pg_dedicado
    c.psql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dil_obs_dono') THEN "
           "CREATE ROLE dil_obs_dono NOLOGIN NOINHERIT NOBYPASSRLS; END IF; END $$;"
           "CREATE ROLE aplicador3 LOGIN CREATEROLE NOSUPERUSER; GRANT dil_obs_dono TO aplicador3 WITH ADMIN OPTION;")
    db = c.novo_banco("dil_aplicador3")
    c.psql(f"GRANT CREATE ON DATABASE {db} TO aplicador3;")
    saida = subprocess.run(
        [str(_bin("psql")), "-h", c.socket, "-p", str(c.porta), "-U", "aplicador3", "-d", db, "-X", "-q", "-v", "ON_ERROR_STOP=1"],
        input=_ler(UP), capture_output=True, text=True, env=c.env(), timeout=120)
    assert saida.returncode == 0 and "membresia" in saida.stderr  # WARNING explícito; a membresia era do admin, fica


# ============================================================== F3: linhagem
@pytest.mark.parametrize(
    "mut, trecho",
    [
        (dict(run_id="r-outro"), "difere do run do lote"),
        (dict(fonte="joinads"), "fonte/coletor"),
        (dict(coletor_nome="coletor-que-o-run-nao-tem"), "fonte/coletor"),
        (dict(coletor_versao="9"), "fonte/coletor"),
        (dict(schema_version="schema-que-o-lote-nao-tem"), "schema_version"),
    ],
)
def test_r1_f3_linhagem_conferida(cluster_pg, banco, obs, mut, trecho):
    c = cluster_pg
    prep = _preparo(c, run_id="r-lin", payload=b"lin", lote_id="l-lin", t=BASE + timedelta(hours=30))
    prep += "SELECT dil_obs.registrar_run('r-outro', 'joinads', 'n8n_joinads', '2', " + _lit(BASE.isoformat()) + ");\n"
    j = {**_obs_json(obs, conta="lin", payload=b"lin", run_id="r-lin", lote_id="l-lin"), **mut}
    assert trecho in c.falha(prep + _reg(j), db=banco, papel="dil_obs_escritor")


def test_r1_f3_lote_de_run_finalizado_nao_recebe(cluster_pg, banco, obs):
    """Prova do revisor (pg/t_linhagem.py): obs de outro run apontando para lote de run finalizado."""
    c = cluster_pg
    prep = _preparo(c, run_id="r-fin", payload=b"fin", lote_id="l-fin", t=BASE + timedelta(hours=30))
    prep += "SELECT dil_obs.finalizar_run('r-fin', 'succeeded', 0, NULL, 0, NULL, NULL);\n"
    j = _obs_json(obs, conta="fin", payload=b"fin", run_id="r-fin", lote_id="l-fin")
    assert "já finalizada" in c.falha(prep + _reg(j), db=banco, papel="dil_obs_escritor")
    # e um run novo não pode reaproveitar o lote do run fechado: precisa de lote próprio (mesmo payload)
    prep2 = c.sql_relogio(BASE + timedelta(hours=31), "dil_obs_escritor")
    prep2 += ("SELECT dil_obs.registrar_run('r-novo', 'google_ads', 'coleta_canonica_google_ads', '1.0.0', " + _lit(BASE.isoformat()) + ");\n"
              f"SELECT dil_obs.registrar_lote('l-novo', 'r-novo', {_lit(_sha(b'fin'))}, 'google_ads.gaql.campaign_day.v1', '{{}}', NULL);\n")
    j2 = _obs_json(obs, conta="fin", payload=b"fin", run_id="r-novo", lote_id="l-novo", h=31)
    assert "R:inserido" in c.psql(prep2 + _reg(j2), db=banco, papel="dil_obs_escritor")
    assert "difere do run do lote" in c.falha(prep2 + _reg({**j2, "lote_id": "l-fin"}), db=banco, papel="dil_obs_escritor")


# ============================================================== F8: fechamento de run
def test_r1_f8_fechamento_com_contagens_do_banco_e_idempotente(cluster_pg, banco, obs):
    c = cluster_pg
    prep = _preparo(c, run_id="r-cnt", payload=b"cnt", lote_id="l-cnt", t=BASE + timedelta(hours=30))
    j = _obs_json(obs, conta="cnt", payload=b"cnt", run_id="r-cnt", lote_id="l-cnt")
    c.psql(prep + _reg(j) + _reg(j), db=banco, papel="dil_obs_escritor")
    fim = "SELECT dil_obs.finalizar_run('r-cnt', 'succeeded', {}, {}, {}, NULL, NULL);"
    # prova do revisor (pg/t_run.py): NULLs e contagens incoerentes eram aceitos
    assert "n_lidas e n_noop são obrigatórios" in c.falha(fim.format("NULL", "NULL", "NULL"), db=banco, papel="dil_obs_escritor")
    assert "o banco contou inseridas=1" in c.falha(fim.format(5, 999, 0), db=banco, papel="dil_obs_escritor")
    assert "n_lidas (1) menor" in c.falha(fim.format(1, "NULL", 1), db=banco, papel="dil_obs_escritor")
    assert c.psql(fim.format(2, 1, 1), db=banco, papel="dil_obs_escritor") == "finalizado"
    assert c.psql(fim.format(2, 1, 1), db=banco, papel="dil_obs_escritor") == "noop"  # retry após timeout do cliente
    assert c.psql(fim.format(2, "NULL", 1), db=banco, papel="dil_obs_escritor") == "noop"
    assert "já finalizada como succeeded" in c.falha(fim.format(3, "NULL", 1), db=banco, papel="dil_obs_escritor")
    assert c.psql("SELECT n_lidas || '/' || n_inseridas || '/' || n_noop || '/' || n_dead_letter "
                  "FROM dil_obs.run_coleta WHERE run_id = 'r-cnt';", db=banco) == "2/1/1/0"


def test_r1_m4_check_de_contagens_no_banco(cluster_pg, banco):
    """Inserção direta (superusuário) de run fechado com contagem nula ou incoerente: o CHECK segura."""
    base = ("INSERT INTO dil_obs.run_coleta (run_id, fonte, coletor_nome, coletor_versao, iniciado_em, finalizado_em, status, "
            "n_lidas, n_inseridas, n_noop, n_dead_letter) VALUES ('{r}', 'google_ads', 'c', '1', now(), now(), "
            "'succeeded', {v});")
    assert "ck_run_contagens" in cluster_pg.falha(base.format(r="m4a", v="NULL, NULL, NULL, NULL"), db=banco)
    assert "ck_run_contagens" in cluster_pg.falha(base.format(r="m4b", v="1, 5, 0, 0"), db=banco)
    cluster_pg.psql(base.format(r="m4c", v="5, 5, 0, 0"), db=banco)


# ============================================================== M5: payload do lote
def test_r1_m5_payload_da_observacao_tem_de_ser_o_do_lote(cluster_pg, banco, obs):
    c = cluster_pg
    prep = _preparo(c, run_id="r-m5", payload=b"m5-a", lote_id="l-m5", t=BASE + timedelta(hours=30))
    prep += f"SELECT dil_obs.registrar_payload({_lit(_sha(b'm5-b'))}, decode({_lit(b'm5-b'.hex())}, 'hex'), 'x');\n"
    j = _obs_json(obs, conta="m5", payload=b"m5-b", run_id="r-m5", lote_id="l-m5")  # payload existe, mas é de outro lote
    assert "difere do payload do lote" in c.falha(prep + _reg(j), db=banco, papel="dil_obs_escritor")


# ============================================================== M7 no banco
def test_r1_m7_releitura_no_instante_da_vigente_e_noop_no_banco(cluster_pg, banco, obs):
    c = cluster_pg
    sql = _preparo(c, run_id="r-m7", payload=b"K1", lote_id="l-k1", t=BASE + timedelta(hours=30))
    sql += _reg(_obs_json(obs, conta="m7", payload=b"K1", run_id="r-m7", lote_id="l-k1", h=30))
    sql += c.sql_relogio(BASE + timedelta(hours=40), "dil_obs_escritor")
    sql += f"SELECT dil_obs.registrar_payload({_lit(_sha(b'K2'))}, decode({_lit(b'K2'.hex())}, 'hex'), 'x');\n"
    sql += f"SELECT dil_obs.registrar_lote('l-k2', 'r-m7', {_lit(_sha(b'K2'))}, 'google_ads.gaql.campaign_day.v1', '{{}}', NULL);\n"
    sql += f"SELECT dil_obs.registrar_lote('l-k1b', 'r-m7', {_lit(_sha(b'K1'))}, 'google_ads.gaql.campaign_day.v1', '{{}}', NULL);\n"
    sql += _reg(_obs_json(obs, conta="m7", payload=b"K2", run_id="r-m7", lote_id="l-k2", h=40, valor=7_000_000))
    sql += _reg(_obs_json(obs, conta="m7", payload=b"K1", run_id="r-m7", lote_id="l-k1b", h=40))
    res = [ln[2:] for ln in c.psql(sql, db=banco, papel="dil_obs_escritor").splitlines() if ln.startswith("R:")]
    assert res == ["inserido", "inserido", "noop"]


# ============================================================== D1/D2 no banco
def _asof_banco(c, db, t: datetime, conta: str) -> list[str]:
    return c.psql(f"SELECT coalesce(valor::text, 'NULL') || ':' || status FROM dil_obs.observacao_as_of({_lit(t.isoformat())}) "
                  f"WHERE conta = {_lit(conta)} ORDER BY chave_natural;", db=db).splitlines()


def test_d1_leitura_antiga_atrasada_nao_desfaz_a_nova_no_banco(cluster_pg, banco, obs):
    c = cluster_pg
    sql = _preparo(c, run_id="r-d1a", payload=b"nova", lote_id="l-d1a", t=BASE + timedelta(hours=31))
    sql += _reg(_obs_json(obs, conta="d1", payload=b"nova", run_id="r-d1a", lote_id="l-d1a", h=31,
                          observed_at=BASE + timedelta(hours=30), valor=7_000_000))
    sql += _preparo(c, run_id="r-d1b", payload=b"antiga", lote_id="l-d1b", t=BASE + timedelta(hours=40))
    sql += _reg(_obs_json(obs, conta="d1", payload=b"antiga", run_id="r-d1b", lote_id="l-d1b", h=40,
                          observed_at=BASE + timedelta(hours=26), valor=5_000_000))
    res = [ln[2:] for ln in c.psql(sql, db=banco, papel="dil_obs_escritor").splitlines() if ln.startswith("R:")]
    assert res == ["inserido", "inserido"]
    assert _asof_banco(c, banco, BASE + timedelta(hours=41), "d1") == ["7000000:observed"]
    assert _asof_banco(c, banco, BASE + timedelta(hours=35), "d1") == ["7000000:observed"]
    assert c.psql("SELECT count(*) FROM dil_obs.observacao WHERE conta = 'd1';", db=banco) == "2"  # antiga no histórico


def test_d2_releitura_d0_no_banco_igual_ao_registro(cluster_pg, banco, obs):
    """Mesmo payload relido de hora em hora e depois com a janela fechada: tudo `inserido`, nada de conflito,
    e o as_of do banco é o do Registro em cada corte."""
    from volc_dil.fundacao.observacao import Registro

    c = cluster_pg
    leituras = []
    for h, custo in ((6, 5_000_000), (7, 5_000_000), (8, 5_200_000), (9, 5_200_000), (30, 5_200_000)):
        aberta = h < 24
        kw = dict(status="partial", motivo="janela_aberta;cobertura_desconhecida") if aberta else {}
        leituras.append((h, f"d2-{custo}".encode(), _obs_json(obs, conta="d2", payload=f"d2-{custo}".encode(),
                                                              run_id=f"r-d2-{h}", lote_id=f"l-d2-{h}", h=h,
                                                              observed_at=BASE + timedelta(hours=h), valor=custo, **kw)))
    sql = ""
    for h, payload, j in leituras:
        sql += _preparo(c, run_id=f"r-d2-{h}", payload=payload, lote_id=f"l-d2-{h}", t=BASE + timedelta(hours=h)) + _reg(j)
    res = [ln[2:] for ln in c.psql(sql, db=banco, papel="dil_obs_escritor").splitlines() if ln.startswith("R:")]
    from volc_dil.fundacao.observacao import Observacao

    reg = Registro()
    assert res == [reg.registrar(Observacao.de_json(j)).value for _, _, j in leituras] == ["inserido"] * 5
    for h in (6, 8, 9, 31):
        t = BASE + timedelta(hours=h, minutes=30)
        py = [f"{o.valor}:{o.status.value}" for o in reg.as_of(t).values()]
        assert _asof_banco(c, banco, t, "d2") == py
    assert _asof_banco(c, banco, BASE + timedelta(hours=31), "d2") == ["5200000:observed"]


# ============================================================== relógio do banco
def test_relogio_de_producao_e_now_e_escritor_nao_troca(cluster_pg, banco):
    corpo = cluster_pg.psql("SELECT prosrc FROM pg_proc WHERE proname = '_agora' AND pronamespace = 'dil_obs'::regnamespace;", db=banco)
    assert corpo.strip() == "SELECT pg_catalog.now()"
    erro = cluster_pg.falha("CREATE OR REPLACE FUNCTION dil_obs._agora() RETURNS timestamptz LANGUAGE sql AS $$ SELECT now() - interval '1 year' $$;",
                            db=banco, papel="dil_obs_escritor")
    assert "permission denied" in erro or "must be owner" in erro


# ============================================================== F21: down sem CASCADE cego
def test_r1_f21_down_recusa_dependente_fora_do_schema(cluster_pg):
    c = cluster_pg
    db = c.novo_banco("dil_down_dep")
    c.aplicar(UP, db=db)
    c.psql("CREATE VIEW public.painel_receita AS SELECT count(*) AS n FROM dil_obs.observacao;", db=db)
    erro = c.falha(_ler(DOWN), db=db)
    assert "objetos fora de dil_obs dependem" in erro and "painel_receita" in erro
    assert c.psql("SELECT count(*) FROM pg_namespace WHERE nspname = 'dil_obs';", db=db) == "1"
    assert c.psql("SELECT count(*) FROM public.painel_receita;", db=db) == "1"  # nada apagado
    c.psql("DROP VIEW public.painel_receita;", db=db)
    c.aplicar(DOWN, db=db)
    assert c.psql("SELECT count(*) FROM pg_namespace WHERE nspname = 'dil_obs';", db=db) == "0"


# ============================================================== M6: collation de sistema
def test_r1_m6_chaves_e_ordem_iguais_em_cluster_utf8(cluster_pg_utf8, obs):
    c, loc = cluster_pg_utf8
    db = c.novo_banco("dil_utf8")
    c.psql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF; "
           "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF; END $$;")
    c.aplicar(UP, db=db)
    # pré-condição: a collation do banco NÃO é byte a byte (senão o teste não provaria nada)
    assert c.psql("SELECT ('B' < 'a')::text || ('B' < 'a' COLLATE \"C\")::text;", db=db) == "falsetrue", loc
    o = obs(dimensoes=(("B", "1"), ("a", "2"), ("é", "3")), entidade_id="Zz", payload=b"utf8",
            janela_inicio=BASE, janela_fim=BASE + timedelta(days=1), observed_at=BASE + timedelta(hours=24),
            available_at=BASE + timedelta(hours=30), ingested_at=BASE + timedelta(hours=30), run_id="r-u", lote_id="l-u")
    j = o.para_json()
    sql = (_preparo(c, run_id="r-u", payload=b"utf8", lote_id="l-u", t=o.available_at) + _reg(j)
           + "RESET ROLE; SELECT 'K:' || encode(chave_natural, 'hex') || '|' || encode(chave_idempotencia, 'hex') FROM dil_obs.observacao WHERE conta = " + _lit(o.conta) + ";")
    out = c.psql(sql, db=db, papel="dil_obs_escritor")
    assert "R:inserido" in out  # ordem por ponto de código aceita (sem COLLATE "C" seria recusada)
    chaves = [ln[2:] for ln in out.splitlines() if ln.startswith("K:")][0].split("|")
    assert chaves == [o.chave_natural, o.chave_base]


# ============================================================== H3/H4: duas sessões concorrentes
def _bin(nome: str):
    from pathlib import Path
    import os
    return Path(os.environ.get("DIL_PG_BIN", "/opt/homebrew/bin")) / nome


def _sessao(c, db: str, sql: str) -> subprocess.Popen:
    """Sessão psql paralela (processo próprio) lendo o script de um arquivo no diretório do cluster."""
    arq = c.raiz / f"sessao_{time.monotonic_ns()}.sql"
    arq.write_text(sql, encoding="utf-8")
    return subprocess.Popen(
        [str(_bin("psql")), "-h", c.socket, "-p", str(c.porta), "-U", "postgres", "-d", db, "-X", "-q", "-A", "-t",
         "-v", "ON_ERROR_STOP=1", "-f", str(arq)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=c.env())


def _esperar_trava(c, db: str, tipo: str, limite: float = 10.0) -> None:
    """Espera a sessão A segurar a trava (advisory ou de linha) antes de soltar a sessão B."""
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if c.psql(f"SELECT count(*) FROM pg_locks WHERE locktype = '{tipo}' AND granted;", db=db) != "0":
            return
        time.sleep(0.05)
    raise AssertionError(f"sessão A não pegou a trava {tipo}")


def test_r1_h3_retry_concorrente_e_noop_em_read_committed(cluster_pg, banco, obs):
    c = cluster_pg
    c.psql(_preparo(c, run_id="r-h3", payload=b"h3", lote_id="l-h3", t=BASE + timedelta(hours=30)), db=banco, papel="dil_obs_escritor")
    reg = _reg(_obs_json(obs, conta="h3", payload=b"h3", run_id="r-h3", lote_id="l-h3"))
    a = _sessao(c, banco, "SET ROLE dil_obs_escritor; BEGIN;\n" + reg + "SELECT pg_sleep(1.5);\nCOMMIT;\n")
    _esperar_trava(c, banco, "advisory")
    b = c.psql(reg, db=banco, papel="dil_obs_escritor")  # espera a trava de A e então enxerga o commit
    sa, ea = a.communicate(timeout=30)
    assert a.returncode == 0, ea
    assert "R:inserido" in sa and b == "R:noop"
    assert c.psql("SELECT count(*) FROM dil_obs.observacao WHERE conta = 'h3';", db=banco) == "1"
    erro = c.falha("BEGIN ISOLATION LEVEL REPEATABLE READ;\n" + reg + "COMMIT;", db=banco, papel="dil_obs_escritor")
    assert "exige READ COMMITTED" in erro


def test_r1_h4_fechamento_concorrente_espera_a_observacao_em_voo(cluster_pg, banco, obs):
    c = cluster_pg
    c.psql(_preparo(c, run_id="r-h4", payload=b"h4", lote_id="l-h4", t=BASE + timedelta(hours=30)), db=banco, papel="dil_obs_escritor")
    reg = _reg(_obs_json(obs, conta="h4", payload=b"h4", run_id="r-h4", lote_id="l-h4"))
    a = _sessao(c, banco, "SET ROLE dil_obs_escritor; BEGIN;\n" + reg + "SELECT pg_sleep(1.5);\nCOMMIT;\n")
    _esperar_trava(c, banco, "advisory")
    fim = c.psql("SELECT dil_obs.finalizar_run('r-h4', 'succeeded', 1, NULL, 0, NULL, NULL);", db=banco, papel="dil_obs_escritor")
    sa, ea = a.communicate(timeout=30)
    assert a.returncode == 0, ea
    assert fim == "finalizado" and "R:inserido" in sa
    assert c.psql("SELECT n_inseridas FROM dil_obs.run_coleta WHERE run_id = 'r-h4';", db=banco) == "1"  # contou a obs em voo
    reg2 = _reg(_obs_json(obs, conta="h4", payload=b"h4", run_id="r-h4", lote_id="l-h4", entidade_id="222"))
    assert "já finalizada" in c.falha(c.sql_relogio(BASE + timedelta(hours=30), "dil_obs_escritor") + reg2, db=banco, papel="dil_obs_escritor")


def _ler(nome: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[3] / "experiments" / "data-intelligence-lab" / "migrations_candidatas" / nome).read_text()
