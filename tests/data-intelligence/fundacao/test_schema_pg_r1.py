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


# ============================================================== F2 / F22 / R2-G1: só superusuário aplica
def _aplicar_bruto(c, db, usuario, arquivo=UP):
    """psql direto, para ver WARNING/HINT no stderr mesmo quando dá certo."""
    return subprocess.run(
        [str(_bin("psql")), "-h", c.socket, "-p", str(c.porta), "-U", usuario, "-d", db, "-X", "-q", "-v", "ON_ERROR_STOP=1"],
        input=_ler(arquivo), capture_output=True, text=True, env=c.env(), timeout=120)


def test_r2_g1_nao_superusuario_nao_aplica_e_nao_fica_com_admin_option(cluster_pg_dedicado, obs):
    """Prova do revisor (r2 probes/q_f2.py): o CREATEROLE que criava os papéis ficava com ADMIN OPTION em
    dil_obs_dono e, com um GRANT a si mesmo, desligava o trigger e fazia TRUNCATE."""
    c = cluster_pg_dedicado
    c.psql("CREATE ROLE aplicador LOGIN CREATEROLE NOSUPERUSER;")
    db = c.novo_banco("dil_aplicador")
    c.psql(f"GRANT CREATE ON DATABASE {db} TO aplicador;")
    r = _aplicar_bruto(c, db, "aplicador")
    assert r.returncode != 0 and "aplique como superusuário" in r.stderr and "supabase_admin" in r.stderr
    assert c.psql(RESIDUO, db=db) == "0|0"  # nem papéis nem schema pela metade
    c.aplicar(UP, db=db)  # superusuário
    assert c.psql("SELECT count(*) FROM pg_auth_members a JOIN pg_roles r ON r.oid = a.roleid "
                  "WHERE r.rolname = 'dil_obs_dono';", db=db) == "0"  # ninguém administra nem é membro do dono
    j = _obs_json(obs, conta="c", payload=b"abc", run_id="r", lote_id="l")
    c.psql(_preparo(c, run_id="r", payload=b"abc", lote_id="l", t=BASE + timedelta(hours=30)) + _reg(j), db=db, papel="dil_obs_escritor")
    # o ataque do revisor, agora sem efeito
    assert "permission denied" in c.falha("GRANT dil_obs_dono TO aplicador;", db=db, usuario="aplicador")
    assert "permission denied to set role" in c.falha("SET ROLE dil_obs_dono;", db=db, usuario="aplicador")
    assert "permission denied" in c.falha("TRUNCATE dil_obs.observacao;", db=db, usuario="aplicador")
    erro = c.falha("ALTER TABLE dil_obs.observacao DISABLE TRIGGER tg_obs_append_only;", db=db, usuario="aplicador")
    assert "permission denied" in erro or "must be owner" in erro
    assert c.psql("SELECT valor FROM dil_obs.observacao;", db=db) == "5000000"
    # desfazer também exige superusuário
    c.psql(c.sql_relogio(None), db=db)
    r = _aplicar_bruto(c, db, "aplicador", DOWN)
    assert r.returncode != 0 and "aplique como superusuário" in r.stderr
    c.aplicar(DOWN, db=db)
    assert c.psql(RESIDUO, db=db) == "0|0"


def test_r1_f22_reaplicacao_com_papeis_existentes_e_aviso_de_membresia_previa(cluster_pg_dedicado):
    c = cluster_pg_dedicado
    outro = c.novo_banco("dil_outro")
    c.aplicar(UP, db=outro)  # papéis já existem no cluster
    c.psql("CREATE ROLE aplicador2 LOGIN CREATEROLE NOSUPERUSER; GRANT dil_obs_dono TO aplicador2 WITH ADMIN OPTION;")
    db = c.novo_banco("dil_aplicador2")
    c.psql(f"GRANT CREATE ON DATABASE {db} TO aplicador2;")
    r = _aplicar_bruto(c, db, "aplicador2")  # mesmo com ADMIN OPTION: recusado (administrar o dono = poder desligar o append-only)
    assert r.returncode != 0 and "aplique como superusuário" in r.stderr
    assert c.psql("SELECT count(*) FROM pg_namespace WHERE nspname = 'dil_obs';", db=db) == "0"
    r = _aplicar_bruto(c, db, "postgres")  # superusuário reaplica com os papéis existentes...
    assert r.returncode == 0, r.stderr
    assert "aplicador2 (ADMIN OPTION)" in r.stderr and "REVOKE dil_obs_dono FROM" in r.stderr  # ...e avisa da membresia prévia
    assert c.psql("SELECT count(*) FROM pg_namespace WHERE nspname = 'dil_obs';", db=db) == "1"


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
            "n_lidas, n_inseridas, n_noop, n_dead_letter, n_confirmadas) VALUES ('{r}', 'google_ads', 'c', '1', now(), now(), "
            "'succeeded', {v});")
    assert "ck_run_contagens" in cluster_pg.falha(base.format(r="m4a", v="NULL, NULL, NULL, NULL, NULL"), db=banco)
    assert "ck_run_contagens" in cluster_pg.falha(base.format(r="m4b", v="1, 5, 0, 0, 0"), db=banco)
    cluster_pg.psql(base.format(r="m4c", v="5, 5, 0, 0, 0"), db=banco)


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
    # D2': releitura com o mesmo estado = confirmação; o fechamento da janela (partial → observed) = versão
    assert res == [reg.registrar(Observacao.de_json(j)).value for _, _, j in leituras] == \
        ["inserido", "confirmado", "inserido", "confirmado", "inserido"]
    assert c.psql("SELECT count(*) FROM dil_obs.confirmacao WHERE lote_id LIKE 'l-d2-%';", db=banco) == "2"
    for h in (6, 8, 9, 31):
        t = BASE + timedelta(hours=h, minutes=30)
        py = [f"{o.valor}:{o.status.value}" for o in reg.as_of(t).values()]
        assert _asof_banco(c, banco, t, "d2") == py
    assert _asof_banco(c, banco, BASE + timedelta(hours=31), "d2") == ["5200000:observed"]


def test_d2_linha_banco_igual_ao_registro_em_permutacoes_e_estado_independe_da_ordem(cluster_pg, banco, obs):
    """D2' no banco: igual leitura atrasada vira confirmação, A→B→A continua, leitura antiga e diferente atrasada
    materializa a confirmação mais nova; em toda permutação, banco = Registro e o estado em cada corte = dado bruto."""
    import itertools
    import random

    from volc_dil.fundacao.observacao import Observacao, Registro, as_of

    # (observed_h, available_h, valor): A, A igual atrasada, B, A de novo, B antiga atrasada
    base = [(30, 31, 5), (32, 50, 5), (40, 41, 7), (45, 46, 5), (35, 55, 7)]
    perms = list(itertools.permutations(range(len(base))))
    random.Random(7).shuffle(perms)
    c = cluster_pg
    vistos = set()
    for n, perm in enumerate(perms[:8]):
        conta = f"perm{n}"
        leituras = []
        for i in perm:
            oh, ah, v = base[i]
            payload = f"{conta}-{i}".encode()
            j = _obs_json(obs, conta=conta, payload=payload, run_id=f"r-{conta}-{i}", lote_id=f"l-{conta}-{i}", h=ah,
                          observed_at=BASE + timedelta(hours=oh), valor=v * 1_000_000)
            leituras.append((ah, payload, j, f"r-{conta}-{i}", f"l-{conta}-{i}"))
        sql = ""
        for ah, payload, j, run, lote in leituras:
            sql += _preparo(c, run_id=run, payload=payload, lote_id=lote, t=BASE + timedelta(hours=ah)) + _reg(j)
        res = [ln[2:] for ln in c.psql(sql, db=banco, papel="dil_obs_escritor").splitlines() if ln.startswith("R:")]
        reg = Registro()
        esperado = [reg.registrar(Observacao.de_json(j)).value for _, _, j, _, _ in leituras]
        assert res == esperado, (perm, res, esperado)
        vistos.update(res)
        brutas = [Observacao.de_json(j) for _, _, j, _, _ in leituras]
        for h in (32, 42, 47, 52, 56, 80):
            t = BASE + timedelta(hours=h)
            bruto = [f"{o.valor}:{o.status.value}" for o in as_of(brutas, t).values()]
            assert _asof_banco(c, banco, t, conta) == bruto, (perm, h)
    assert {"inserido", "confirmado"} <= vistos  # D2': a amostra exercitou a confirmação (e materializações)
    assert int(c.psql("SELECT count(*) FROM dil_obs.confirmacao;", db=banco)) > 0


# ============================================================== R2-G4 / G6 / G20
def test_r2_g4_retry_de_leitura_confirmada_com_conteudo_diferente_e_conflito_no_banco(cluster_pg, banco, obs):
    """Prova do revisor (p_conf.py / q_g.py): antes, a mesma leitura (mesma chave) já confirmada e reenviada com
    outro valor virava versão em silêncio."""
    c = cluster_pg
    v1 = _obs_json(obs, conta="g4", payload=b"P", run_id="r-g4", lote_id="l-g4-1", h=30,
                   observed_at=BASE + timedelta(hours=28))
    r2 = _obs_json(obs, conta="g4", payload=b"P", run_id="r-g4", lote_id="l-g4-2", h=31,
                   observed_at=BASE + timedelta(hours=29))  # releitura igual → confirmação
    sql = (_preparo(c, run_id="r-g4", payload=b"P", lote_id="l-g4-1", t=BASE + timedelta(hours=30)) + _reg(v1)
           + c.sql_relogio(BASE + timedelta(hours=31), "dil_obs_escritor")
           + f"SELECT dil_obs.registrar_lote('l-g4-2', 'r-g4', {_lit(_sha(b'P'))}, 'google_ads.gaql.campaign_day.v1', '{{}}', NULL);\n"
           + _reg(r2))
    res = [ln[2:] for ln in c.psql(sql, db=banco, papel="dil_obs_escritor").splitlines() if ln.startswith("R:")]
    assert res == ["inserido", "confirmado"]
    retry_igual = c.psql(c.sql_relogio(BASE + timedelta(hours=32), "dil_obs_escritor") + _reg({**r2, "available_at": (BASE + timedelta(hours=32)).isoformat(), "ingested_at": (BASE + timedelta(hours=32)).isoformat()}),
                         db=banco, papel="dil_obs_escritor")
    assert retry_igual == "R:noop"
    diferente = {**r2, "valor": 6_000_000, "available_at": (BASE + timedelta(hours=32)).isoformat(),
                 "ingested_at": (BASE + timedelta(hours=32)).isoformat()}
    erro = c.falha(c.sql_relogio(BASE + timedelta(hours=32), "dil_obs_escritor") + _reg(diferente), db=banco, papel="dil_obs_escritor")
    assert "conflito_idempotencia" in erro and "já confirmada" in erro
    assert c.psql("SELECT count(*) FROM dil_obs.observacao WHERE conta = 'g4';", db=banco) == "1"


def test_r2_g6_dead_letter_so_em_run_aberto_e_fechamento_coerente(cluster_pg, banco, obs):
    """Prova do revisor (q_core.py): dead letter era aceito depois do fechamento e um run só com dead letters
    fechava 'succeeded' com n_lidas = 0."""
    c = cluster_pg
    c.psql(c.sql_relogio(BASE + timedelta(hours=30), "dil_obs_escritor")
           + f"SELECT dil_obs.registrar_run('r-g6', 'google_ads', 'c', '1', {_lit(BASE.isoformat())});\n"
           + "SELECT dil_obs.registrar_dead_letter('r-g6', NULL, NULL, 'esquema_desconhecido', '{}'::jsonb);\n"
           + "SELECT dil_obs.registrar_dead_letter('r-g6', NULL, NULL, 'esquema_desconhecido', '{}'::jsonb);",
           db=banco, papel="dil_obs_escritor")
    fim = "SELECT dil_obs.finalizar_run('r-g6', '{}', {}, NULL, 0, NULL, {});"
    assert "n_lidas (0) menor que inseridas+noop+confirmadas+dead_letter (2)" in c.falha(fim.format("partial", 0, "NULL"), db=banco, papel="dil_obs_escritor")
    assert "não fecha succeeded" in c.falha(fim.format("succeeded", 2, "NULL"), db=banco, papel="dil_obs_escritor")
    assert c.psql(fim.format("partial", 2, "NULL"), db=banco, papel="dil_obs_escritor") == "finalizado"
    erro = c.falha("SELECT dil_obs.registrar_dead_letter('r-g6', NULL, NULL, 'linha_sem_identidade', '{}'::jsonb);", db=banco, papel="dil_obs_escritor")
    assert "já finalizada (dead letter recusado)" in erro
    assert "inexistente ou já finalizada" in c.falha("SELECT dil_obs.registrar_dead_letter('r-nao-existe', NULL, NULL, 'x', '{}'::jsonb);",
                                                    db=banco, papel="dil_obs_escritor")
    assert c.psql("SELECT n_dead_letter || '/' || status FROM dil_obs.run_coleta WHERE run_id = 'r-g6';", db=banco) == "2/partial"
    # o CHECK também segura inserção direta (superusuário)
    erro = c.falha("INSERT INTO dil_obs.run_coleta (run_id, fonte, coletor_nome, coletor_versao, iniciado_em, finalizado_em, status, "
                   "n_lidas, n_inseridas, n_noop, n_dead_letter, n_confirmadas) VALUES ('g6x', 'google_ads', 'c', '1', now(), now(), "
                   "'succeeded', 2, 0, 0, 2, 0);", db=banco)
    assert "ck_run_contagens" in erro


def test_r2_g20_retry_de_lote_e_noop_mesmo_com_recebido_em_original_antigo(cluster_pg, banco):
    """Prova do revisor (q_core.py): o retry do MESMO lote, depois de 5 min, com o recebido_em original, falhava
    como 'no passado'. recebido_em NULL é aceito (o banco carimba) — decisão documentada."""
    c = cluster_pg
    sha = _sha(b"g20")
    t0 = BASE + timedelta(hours=30)
    c.psql(c.sql_relogio(t0, "dil_obs_escritor")
           + f"SELECT dil_obs.registrar_run('r-g20', 'google_ads', 'c', '1', {_lit(BASE.isoformat())});\n"
           + f"SELECT dil_obs.registrar_payload({_lit(sha)}, decode({_lit(b'g20'.hex())}, 'hex'), 'x');\n"
           + f"SELECT dil_obs.registrar_lote('l-g20', 'r-g20', {_lit(sha)}, 'v', '{{}}', {_lit(t0.isoformat())});",
           db=banco, papel="dil_obs_escritor")
    retry = (c.sql_relogio(t0 + timedelta(hours=2), "dil_obs_escritor")
             + f"SELECT dil_obs.registrar_lote('l-g20', 'r-g20', {_lit(sha)}, 'v', '{{}}', {_lit(t0.isoformat())});")
    assert c.psql(retry, db=banco, papel="dil_obs_escritor") == "noop"
    assert c.psql(retry.replace(_lit(t0.isoformat()) + ");", "NULL);"), db=banco, papel="dil_obs_escritor") == "noop"
    # lote NOVO com o mesmo recebido_em antigo continua recusado; com NULL, o banco carimba
    novo = (c.sql_relogio(t0 + timedelta(hours=2), "dil_obs_escritor")
            + f"SELECT dil_obs.registrar_lote('l-g20b', 'r-g20', {_lit(sha)}, 'v', '{{}}', __REC__);")
    assert "no passado" in c.falha(novo.replace("__REC__", _lit(t0.isoformat())), db=banco, papel="dil_obs_escritor")
    assert c.psql(novo.replace("__REC__", "NULL"), db=banco, papel="dil_obs_escritor") == "inserido"
    assert c.psql("SELECT recebido_em = registrado_em FROM dil_obs.lote WHERE lote_id = 'l-g20b';", db=banco) == "t"


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
