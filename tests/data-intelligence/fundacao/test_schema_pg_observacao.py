"""Migration candidata dil_obs_0001 em PostgreSQL 16 descartável: cada gate do contrato provado no banco.

Nada aqui fala com rede ou produção: o cluster é local, só socket unix, criado e destruído pela
fixture `cluster_pg` (conftest). Se o PostgreSQL não subir, estes testes ficam SKIP com motivo.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone

import pytest

from volc_dil.fundacao.observacao import (
    Observacao,
    ObservacaoInvalida,
    Registro,
    ResultadoRegistro,
    instante_canonico,
)

BRT = timezone(timedelta(hours=-3))
BASE = datetime(2026, 8, 1, tzinfo=BRT)  # passado: ingested_at = now() do banco precisa ser >= available_at
BYTES: dict[str, bytes] = {}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def o_pg(obs, h: float, *, payload: bytes, conta: str = "c1", entidade_id: str = "111", **kw) -> Observacao:
    t = BASE + timedelta(hours=h)
    BYTES[_sha(payload)] = payload
    kw.setdefault("run_id", f"run-{conta}")
    kw.setdefault("lote_id", f"lote-{conta}-{_sha(payload)[:12]}-{h}")
    kw.setdefault("observed_at", BASE + timedelta(hours=24))
    return obs(payload=payload, conta=conta, entidade_id=entidade_id, janela_inicio=BASE,
               janela_fim=BASE + timedelta(days=1), available_at=t, ingested_at=t, **kw)


@pytest.fixture(autouse=True)
def _relogio_real_depois(request):
    """Um script que falha no meio deixaria o relógio do banco compartilhado no passado: restaura sempre."""
    yield
    if "banco_obs" in request.fixturenames:
        request.getfixturevalue("cluster_pg").psql(sql_relogio(None, None), db=request.getfixturevalue("banco_obs"))


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def sql_relogio(t, papel):
    """Mesma troca de relógio que `ClusterPG.sql_relogio` (conftest): `dil_obs._agora()` vira `t` (None = now())."""
    corpo = "pg_catalog.now()" if t is None else f"'{t.isoformat()}'::timestamptz"
    return ("RESET ROLE;\nCREATE OR REPLACE FUNCTION dil_obs._agora() RETURNS timestamptz LANGUAGE sql STABLE "
            f"PARALLEL SAFE SET search_path = '' AS $$ SELECT {corpo} $$;\n" + (f"SET ROLE {papel};\n" if papel else ""))


def script_carga(observacoes, *, papel: str = "dil_obs_escritor", relogio="available_at", finalizar: bool = False,
                 sem_observacoes: bool = False, recebido_declarado: bool = False) -> str:
    """SQL que registra runs, payloads, lotes e observações pelas funções públicas, na ordem de chegada.

    O relógio do banco acompanha o `available_at` de cada observação (`relogio="available_at"`), fica fixo
    (`relogio=<datetime>`) ou não é tocado (`relogio=None`). No fim volta a `now()`.
    """
    linhas, runs, lotes, payloads, atual = [], set(), set(), set(), object()
    chamadas: dict[str, int] = {}
    if relogio not in ("available_at", None):
        linhas.append(sql_relogio(relogio, papel))
    for o in observacoes:
        if relogio == "available_at" and o.available_at != atual:
            linhas.append(sql_relogio(o.available_at, papel))
            atual = o.available_at
        if o.run_id not in runs:
            runs.add(o.run_id)
            linhas.append(f"SELECT dil_obs.registrar_run({_lit(o.run_id)}, {_lit(o.fonte)}, {_lit(o.coletor.nome)}, "
                          f"{_lit(o.coletor.versao)}, {_lit(BASE.isoformat())});")
        if o.payload_sha256 not in payloads:
            payloads.add(o.payload_sha256)
            linhas.append(f"SELECT dil_obs.registrar_payload({_lit(o.payload_sha256)}, "
                          f"decode({_lit(BYTES[o.payload_sha256].hex())}, 'hex'), 'application/json');")
        if o.lote_id not in lotes:
            lotes.add(o.lote_id)
            rec = _lit(o.available_at.isoformat()) if recebido_declarado else "NULL"
            linhas.append(f"SELECT dil_obs.registrar_lote({_lit(o.lote_id)}, {_lit(o.run_id)}, {_lit(o.payload_sha256)}, "
                          f"{_lit(o.schema_version)}, '{{}}'::jsonb, {rec});")
        if not sem_observacoes:
            chamadas[o.run_id] = chamadas.get(o.run_id, 0) + 1
            linhas.append(f"SELECT 'R:' || dil_obs.registrar_observacao({_lit(json.dumps(o.para_json()))}::json);")
    if finalizar:
        for run_id in sorted(runs):
            # inseridas/reafirmadas/dead letter: o banco conta; n_lidas = chamadas feitas, n_noop desconhecido = 0
            linhas.append(f"SELECT dil_obs.finalizar_run({_lit(run_id)}, 'succeeded', {chamadas.get(run_id, 0)}, NULL, 0, NULL, NULL, NULL);")
    if relogio is not None:
        linhas.append(sql_relogio(None, papel))
    return "\n".join(linhas)


def carregar(cluster, db, observacoes, *, papel: str = "dil_obs_escritor", **kw) -> list[str]:
    saida = cluster.psql(script_carga(observacoes, papel=papel, **kw), db=db, papel=papel)
    return [ln[2:] for ln in saida.splitlines() if ln.startswith("R:")]


def as_of_sql(cluster, db, t: datetime, conta: str) -> list[tuple]:
    sql = (f"SELECT chave_natural, chave_base, status, coalesce(valor::text, 'NULL'), dil_obs._ts(available_at) "
           f"FROM dil_obs.observacao_as_of({_lit(t.isoformat())}) WHERE conta = {_lit(conta)} ORDER BY chave_natural;")
    # _ts é interno (sem EXECUTE para o leitor): a formatação canônica roda como superusuário;
    # o caminho do papel leitor é provado em test_rls_e_grants_minimos e no latest
    out = cluster.psql(sql, db=db)
    return [tuple(ln.split("|")) for ln in out.splitlines() if ln]


def as_of_py(registro: Registro, t: datetime, conta: str) -> list[tuple]:
    return sorted(
        (o.chave_natural, o.chave_base, o.status.value, "NULL" if o.valor is None else str(o.valor),
         instante_canonico(o.available_at))
        for o in registro.as_of(t).values() if o.conta == conta
    )


# ============================================================== estrutura e chaves
def test_migracao_cria_objetos_rls_forcado_e_sem_default_em_metrica(cluster_pg, banco_obs):
    tabelas = cluster_pg.psql(
        "SELECT string_agg(relname || ':' || relrowsecurity || relforcerowsecurity, ',' ORDER BY relname) "
        "FROM pg_class WHERE relnamespace = 'dil_obs'::regnamespace AND relkind = 'r';", db=banco_obs)
    assert tabelas == "dead_letter:truetrue,lote:truetrue,observacao:truetrue,payload_bruto:truetrue,run_coleta:truetrue"
    defaults = cluster_pg.psql(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'dil_obs' AND table_name = 'observacao' "
        "AND column_default IS NOT NULL AND column_name NOT IN ('observacao_id');", db=banco_obs)
    assert defaults == "0"
    definers = cluster_pg.psql(
        "SELECT string_agg(proname || ':' || array_to_string(proconfig, ';'), ',' ORDER BY proname) FROM pg_proc "
        "WHERE pronamespace = 'dil_obs'::regnamespace AND prosecdef;", db=banco_obs)
    assert definers.split(",") == [f"{n}:search_path=\"\"" for n in (
        "finalizar_run", "registrar_dead_letter", "registrar_lote", "registrar_observacao", "registrar_payload", "registrar_run")]
    dono = cluster_pg.psql("SELECT rolsuper::text || rolbypassrls::text FROM pg_roles WHERE rolname = 'dil_obs_dono';", db=banco_obs)
    assert dono == "falsefalse"


def test_chaves_python_iguais_as_do_postgres(cluster_pg, banco_obs, obs):
    casos = [
        obs(),
        obs(dimensoes=(("joinads_domain", "exemplo.com.br"), ("zeta", "ação/ç")), entidade_id="campanha 'x' ü"),
        obs(metrica="revenue", value_kind="reported_revenue", grao=("day", "campaign", "day")),
        obs(janela_inicio=datetime(2026, 3, 8, 1, 2, 3, 456789, tzinfo=timezone.utc),
            janela_fim=datetime(2026, 3, 9, tzinfo=timezone(timedelta(hours=5, minutes=30))), timezone="Asia/Kolkata"),
    ]
    for o in casos:
        j = o.para_json()
        sql = (
            "WITH p AS (SELECT " + _lit(json.dumps(j)) + "::jsonb AS p), n AS (SELECT dil_obs._chave_natural("
            "p->>'fonte', p->>'conta', p->>'entidade_tipo', p->>'entidade_id', "
            "ARRAY(SELECT jsonb_array_elements_text(p->'grao')), p->'dimensoes', p->>'metrica', p->>'value_kind', "
            "(p->>'janela_inicio')::timestamptz, (p->>'janela_fim')::timestamptz, p->>'timezone') AS nat, p FROM p) "
            "SELECT nat || '|' || dil_obs._chave_base(nat, p->>'payload_sha256', p->>'schema_version', p->>'coletor_nome', "
            "p->>'coletor_versao') || '|' || dil_obs._chave_reafirmacao(dil_obs._chave_base(nat, p->>'payload_sha256', "
            "p->>'schema_version', p->>'coletor_nome', p->>'coletor_versao'), (p->>'available_at')::timestamptz) FROM n;"
        )
        nat, base, reaf = cluster_pg.psql(sql, db=banco_obs).split("|")
        from volc_dil.fundacao.observacao import chave_reafirmacao

        assert (nat, base) == (o.chave_natural, o.chave_base)
        assert reaf == chave_reafirmacao(chave_base_hex=o.chave_base, available_at=o.available_at)


# ============================================================== idempotência e versões
def test_reinsercao_e_noop_contagem_igual(cluster_pg, banco_obs, obs):
    o = o_pg(obs, 30, payload=b"idem-1", conta="idem")
    assert carregar(cluster_pg, banco_obs, [o, o, o]) == ["inserido", "noop", "noop"]
    assert carregar(cluster_pg, banco_obs, [o]) == ["noop"]
    n = cluster_pg.psql("SELECT count(*) FROM dil_obs.observacao WHERE conta = 'idem';", db=banco_obs)
    assert n == "1"


def test_reprocessamento_tardio_aparece_depois_de_T_e_nao_antes(cluster_pg, banco_obs, obs):
    v1 = o_pg(obs, 30, payload=b"rest-P1", conta="rest", valor=5_000_000)
    v2 = o_pg(obs, 100, payload=b"rest-P2", conta="rest", valor=5_400_000, run_id="run-rest-2")
    assert carregar(cluster_pg, banco_obs, [v1, v2]) == ["inserido", "inserido"]
    antes = as_of_sql(cluster_pg, banco_obs, BASE + timedelta(hours=99), "rest")
    depois = as_of_sql(cluster_pg, banco_obs, BASE + timedelta(hours=100), "rest")
    assert [r[3] for r in antes] == ["5000000"] and [r[3] for r in depois] == ["5400000"]
    assert as_of_sql(cluster_pg, banco_obs, BASE + timedelta(hours=29), "rest") == []
    hist = cluster_pg.psql("SELECT string_agg(valor::text, ',' ORDER BY available_at) FROM dil_obs.observacao WHERE conta='rest';",
                           db=banco_obs)
    assert hist == "5000000,5400000"  # histórico intacto
    latest = cluster_pg.psql("SELECT valor FROM dil_obs.observacao_latest WHERE conta = 'rest';", db=banco_obs, papel="dil_obs_leitor")
    assert latest == "5400000"


def test_reafirmacao_conflito_e_versao_ambigua(cluster_pg, banco_obs, obs):
    falta = dict(status="missing", valor=None, moeda=None, motivo="linha_ausente_na_resposta")
    a1 = o_pg(obs, 30, payload=b"aba-vazio", conta="aba", **falta)
    b = o_pg(obs, 36, payload=b"aba-P1", conta="aba")
    a2 = o_pg(obs, 40, payload=b"aba-vazio", conta="aba", run_id="run-aba-3", **falta)
    assert carregar(cluster_pg, banco_obs, [a1, b, a2, a2]) == ["inserido", "inserido", "reafirmado", "noop"]
    tipos = cluster_pg.psql("SELECT string_agg(tipo_registro, ',' ORDER BY available_at) FROM dil_obs.observacao WHERE conta='aba';",
                            db=banco_obs)
    assert tipos == "leitura,leitura,reafirmacao"
    assert [r[2] for r in as_of_sql(cluster_pg, banco_obs, BASE + timedelta(hours=41), "aba")] == ["missing"]

    conflito = o_pg(obs, 30, payload=b"aba-vazio", conta="aba", status="unavailable", valor=None, moeda=None, motivo="x")
    assert "conflito_idempotencia" in cluster_pg.falha(script_carga([conflito]), db=banco_obs, papel="dil_obs_escritor")
    ambigua = o_pg(obs, 36, payload=b"aba-P2", conta="aba", valor=9_000_000)
    assert "versao_ambigua" in cluster_pg.falha(script_carga([ambigua]), db=banco_obs, papel="dil_obs_escritor")


# ============================================================== append-only
@pytest.mark.parametrize("tabela", ["observacao", "payload_bruto", "lote", "dead_letter"])
@pytest.mark.parametrize("comando", ["UPDATE dil_obs.{t} SET {c} = {c}", "DELETE FROM dil_obs.{t}", "TRUNCATE dil_obs.{t} CASCADE"])
def test_append_only_ate_para_superusuario(cluster_pg, banco_obs, obs, tabela, comando):
    carregar(cluster_pg, banco_obs, [o_pg(obs, 30, payload=b"ao-1", conta="ao")])
    coluna = {"observacao": "valor", "payload_bruto": "content_type", "lote": "pedido", "dead_letter": "motivo"}[tabela]
    erro = cluster_pg.falha(comando.format(t=tabela, c=coluna) + ";", db=banco_obs)
    assert "append_only" in erro


def test_append_only_papeis_sem_privilegio_e_run_finalizada(cluster_pg, banco_obs, obs):
    o = o_pg(obs, 30, payload=b"fin-1", conta="fin", run_id="run-fin")
    cluster_pg.psql(script_carga([o], finalizar=True), db=banco_obs, papel="dil_obs_escritor")
    assert "permission denied" in cluster_pg.falha("UPDATE dil_obs.observacao SET valor = 1;", db=banco_obs, papel="dil_obs_escritor")
    assert "permission denied" in cluster_pg.falha("DELETE FROM dil_obs.observacao;", db=banco_obs, papel="dil_obs_leitor")
    # run finalizada não recebe observação nova nem muda de novo
    o2 = o_pg(obs, 50, payload=b"fin-2", conta="fin", run_id="run-fin")
    assert "finalizada" in cluster_pg.falha(script_carga([o2]), db=banco_obs, papel="dil_obs_escritor")
    assert "append_only" in cluster_pg.falha("UPDATE dil_obs.run_coleta SET erro = 'x' WHERE run_id = 'run-fin';", db=banco_obs)


# ============================================================== null != 0 (CHECKs no próprio banco)
def _insert_mutado(overrides: dict, conta: str) -> str:
    cols = ["chave_idempotencia", "chave_base", "chave_natural", "tipo_registro", "fonte", "conta", "entidade_tipo",
            "entidade_id", "grao", "dimensoes", "metrica", "value_kind", "valor", "unidade", "moeda", "janela_inicio",
            "janela_fim", "timezone", "observed_at", "source_updated_at", "available_at", "ingested_at", "run_id",
            "request_id", "lote_id", "payload_sha256", "payload_ref", "schema_version", "coletor_nome", "coletor_versao",
            "status", "motivo", "cobertura_ppm"]
    novo = {"chave_idempotencia": "encode(sha256('mut'::bytea), 'hex')", "chave_base": "encode(sha256('mut'::bytea), 'hex')",
            "available_at": "available_at + interval '1 hour'", "ingested_at": "now()"}
    novo.update(overrides)
    sel = ", ".join(novo.get(c, c) for c in cols)
    return (f"INSERT INTO dil_obs.observacao ({', '.join(cols)}) SELECT {sel} FROM dil_obs.observacao "
            f"WHERE conta = {_lit(conta)} LIMIT 1;")


@pytest.mark.parametrize(
    "overrides, constraint",
    [
        ({"status": "'missing'", "valor": "0", "motivo": "'sem linha'"}, "ck_obs_sem_valor"),
        ({"status": "'unavailable'", "valor": "0", "motivo": "'HTTP 503'"}, "ck_obs_sem_valor"),
        ({"status": "'late'", "valor": "0", "motivo": "'D-1'"}, "ck_obs_sem_valor"),
        ({"status": "'observed'", "valor": "NULL"}, "ck_obs_observed"),
        ({"status": "'observed'", "valor": "0"}, "ck_obs_observed"),
        ({"status": "'zero_confirmed'", "valor": "NULL"}, "ck_obs_zero_confirmed"),
        ({"status": "'missing'", "valor": "NULL", "motivo": "NULL"}, "ck_obs_motivo"),
        ({"status": "'partial'", "motivo": "'x'"}, "ck_obs_partial"),
        ({"moeda": "NULL"}, "ck_obs_micros_moeda"),
        ({"moeda": "'BR'"}, "ck_obs_moeda"),
        ({"unidade": "'contagem'", "moeda": "NULL"}, "ck_obs_unidade_metrica"),
        ({"observed_at": "available_at + interval '2 hours'"}, "ck_obs_relogios"),
        ({"ingested_at": "available_at - interval '1 second'"}, "ck_obs_relogios"),
        ({"janela_fim": "janela_inicio"}, "ck_obs_janela"),
        ({"payload_ref": "'s3://bucket/ultimo.json'"}, "ck_obs_payload"),
        ({"metrica": "'revenue'"}, "ck_obs_value_kind_regra"),
        ({"tipo_registro": "'reafirmacao'"}, "ck_obs_tipo_registro"),
        ({"grao": "ARRAY['semana']"}, "ck_obs_grao"),
        # R1-F20: mutações que sobreviviam
        ({"observed_at": "janela_fim - interval '1 hour'"}, "ck_obs_janela_fechada"),  # M1
        ({"source_updated_at": "available_at + interval '1 hour 1 second'"}, "ck_obs_relogios"),  # M2 (a nova available_at é +1h)
        ({"status": "'partial'", "motivo": "'janela_aberta'", "cobertura_ppm": "NULL"}, "ck_obs_partial"),  # F17
        ({"schema_version": "'v' || chr(31) || 'c'"}, "ck_obs_identidade"),  # F9
        ({"request_id": "' r '"}, "ck_obs_identidade"),
        ({"run_id": "'run-ck' || chr(7)"}, "ck_obs_identidade"),
    ],
)
def test_checks_do_banco_rejeitam_insercao_direta(cluster_pg, banco_obs, obs, overrides, constraint):
    carregar(cluster_pg, banco_obs, [o_pg(obs, 30, payload=b"ck-1", conta="ck")])
    erro = cluster_pg.falha(_insert_mutado(overrides, "ck"), db=banco_obs)  # superusuário: só os CHECKs seguram
    assert constraint in erro


def test_checks_aceitam_partial_com_cobertura_desconhecida(cluster_pg, banco_obs, obs):
    carregar(cluster_pg, banco_obs, [o_pg(obs, 30, payload=b"ckp-1", conta="ckp")])
    cluster_pg.psql(_insert_mutado({"status": "'partial'", "motivo": "'janela_aberta;cobertura_desconhecida'",
                                    "observed_at": "janela_inicio + interval '1 hour'"}, "ckp"), db=banco_obs)
    assert cluster_pg.psql("SELECT count(*) FROM dil_obs.observacao WHERE conta = 'ckp' AND status = 'partial' "
                           "AND cobertura_ppm IS NULL;", db=banco_obs) == "1"


def _troca_valor(literal: str):
    return lambda txt: txt.replace('"valor": 5000000', f'"valor": {literal}')


# (nome, mutação do dict OU função sobre o texto JSON). Python lê o texto com `Observacao.de_json_texto`,
# o banco com `registrar_observacao(json)`: os dois precisam concordar (R1-F9).
MUTACOES = [
    ("valor float", {"valor": 1.5}),
    ("valor string", {"valor": "5000000"}),
    ("valor bool", {"valor": True}),
    ("valor 5e6 (inteiro em notação científica)", _troca_valor("5e6")),
    ("valor 5000000.0", _troca_valor("5000000.0")),
    ("chave repetida", lambda txt: txt[:-1] + ', "valor": 1}'),
    ("missing com 0", {"status": "missing", "valor": 0, "motivo": "sem linha"}),
    ("observed nulo", {"status": "observed", "valor": None}),
    ("zero com 5", {"status": "zero_confirmed", "valor": 5}),
    ("partial sem cobertura nem marcador", {"status": "partial", "motivo": "janela_aberta"}),
    ("unavailable sem motivo", {"status": "unavailable", "valor": None, "motivo": None}),
    ("moeda minúscula", {"moeda": "brl"}),
    ("micros sem moeda", {"moeda": None}),
    ("receita sem value_kind", {"metrica": "revenue"}),
    ("receita sinal", {"metrica": "revenue", "value_kind": "observed_auction_signal"}),
    ("dimensões fora de ordem", {"dimensoes": [["b", "1"], ["a", "2"]]}),
    ("campo desconhecido", {"valor_bruto": "1,5"}),
    ("timezone inválido", {"timezone": "America/Sao_Paolo"}),
    ("timezone minúsculo", {"timezone": "america/sao_paulo"}),
    ("payload_ref mutável", {"payload_ref": "s3://bucket/ultimo.json"}),
    ("fonte maiúscula", {"fonte": "Google_Ads"}),
    ("conta com espaço", {"conta": " mut"}),
    ("conta número JSON", {"conta": 1234567890}),
    ("entidade com controle", {"entidade_id": "1\u001f2"}),
    ("schema_version com US", {"schema_version": "v\u001fc"}),
    ("schema_version com espaço final", {"schema_version": "google_ads.gaql.campaign_day.v1 "}),
    ("request_id com espaço/controle", {"request_id": " r\u0007 "}),
    ("janela sem offset", {"janela_inicio": "2026-08-01T00:00:00", "janela_fim": "2026-08-02T00:00:00"}),
    ("instante como número", {"observed_at": 1785639600}),
    ("ingested_at < available_at", {"ingested_at": "2026-08-02T05:59:00-03:00"}),
    ("available antes de observed", {"available_at": "2026-08-01T23:00:00-03:00"}),
    ("grão desconhecido", {"grao": ["semana"]}),
    ("contagem negativa", {"metrica": "clicks", "unidade": "contagem", "moeda": None, "valor": -1}),
    ("controle: válida", {}),
    ("controle: zero válido", {"status": "zero_confirmed", "valor": 0}),
    ("controle: partial válido", {"status": "partial", "motivo": "janela_aberta", "cobertura_ppm": 10}),
    ("controle: offset Z", {"available_at": "2026-08-02T09:00:00Z", "ingested_at": "2026-08-02T09:00:00Z"}),
]


def test_validacao_python_e_sql_concordam(cluster_pg, banco_obs, obs):
    base = o_pg(obs, 30, payload=b"mut-1", conta="mut")  # available_at = 2026-08-02T06:00-03:00
    cluster_pg.psql(script_carga([base], sem_observacoes=True), db=banco_obs, papel="dil_obs_escritor")
    partes = ["\\set ON_ERROR_STOP off", sql_relogio(base.available_at + timedelta(hours=4), "dil_obs_escritor")]
    esperado = {}
    for i, (nome, mut) in enumerate(MUTACOES):
        if callable(mut):
            txt = mut(json.dumps(base.para_json()))
        else:
            txt = json.dumps({**base.para_json(), **mut})
        try:
            Observacao.de_json_texto(txt)
            esperado[i] = True
        except (ObservacaoInvalida, TypeError, ValueError):
            esperado[i] = False
        partes.append(f"BEGIN; SELECT dil_obs.registrar_observacao({_lit(txt)}::json); SELECT 'OK:{i}'; ROLLBACK;")
    out = cluster_pg.psql("\n".join(partes), db=banco_obs, papel="dil_obs_escritor", check=False)
    aceitos_sql = {int(ln[3:]) for ln in out.splitlines() if ln.startswith("OK:")}
    divergencias = [MUTACOES[i][0] for i in esperado if esperado[i] != (i in aceitos_sql)]
    assert divergencias == []
    assert [MUTACOES[i][0] for i in esperado if esperado[i]] == [n for n, _ in MUTACOES if n.startswith("controle")]


@pytest.mark.parametrize("literal", ["1.5", "5e0", "5000000.0", "\"5\""])
def test_r1_m18_guarda_de_inteiro_tem_mensagem_propria(cluster_pg, banco_obs, obs, literal):
    """Sem a regex, o cast para bigint também falharia — a mensagem prova que é a guarda que recusa."""
    base = o_pg(obs, 30, payload=b"m18-1", conta="m18")
    cluster_pg.psql(script_carga([base], sem_observacoes=True), db=banco_obs, papel="dil_obs_escritor")
    txt = json.dumps(base.para_json()).replace('"valor": 5000000', f'"valor": {literal}')
    erro = cluster_pg.falha(sql_relogio(base.available_at, "dil_obs_escritor")
                            + f"SELECT dil_obs.registrar_observacao({_lit(txt)}::json);", db=banco_obs, papel="dil_obs_escritor")
    assert "valor precisa ser inteiro" in erro


def test_r1_f1_nunca_retroativo_pelo_relogio_do_banco(cluster_pg, banco_obs, obs):
    # (a) cenário do revisor (pg/t_retro.py): banco no relógio real, observação de janeiro → recusada
    jan = obs(payload=b"retro-jan", conta="retro", janela_inicio=datetime(2026, 1, 10, tzinfo=BRT),
              janela_fim=datetime(2026, 1, 11, tzinfo=BRT), observed_at=datetime(2026, 1, 11, 4, tzinfo=BRT),
              available_at=datetime(2026, 1, 11, 4, 5, tzinfo=BRT), ingested_at=datetime(2026, 1, 11, 4, 6, tzinfo=BRT),
              run_id="run-retro", lote_id="lote-retro")
    BYTES[jan.payload_sha256] = b"retro-jan"
    erro = cluster_pg.falha(script_carga([jan], relogio=None), db=banco_obs, papel="dil_obs_escritor")
    assert "retroativo" in erro
    assert cluster_pg.psql("SELECT count(*) FROM dil_obs.observacao WHERE conta = 'retro';", db=banco_obs) == "0"
    # (b) lote declarado no passado é recusado mesmo que o resto bata
    o = o_pg(obs, 30, payload=b"retro-1", conta="retro2")
    erro = cluster_pg.falha(script_carga([o], relogio=o.available_at + timedelta(hours=1), recebido_declarado=True),
                            db=banco_obs, papel="dil_obs_escritor")
    assert "recebido_em no passado" in erro
    # (c) M3: lote declarado no futuro
    erro = cluster_pg.falha(sql_relogio(o.available_at, "dil_obs_escritor")
                            + f"SELECT dil_obs.registrar_run('run-retro3', 'google_ads', 'coleta_canonica_google_ads', '1.0.0', {_lit(BASE.isoformat())});"
                            + f"SELECT dil_obs.registrar_payload({_lit(o.payload_sha256)}, decode({_lit(b'retro-1'.hex())}, 'hex'), 'x');"
                            + f"SELECT dil_obs.registrar_lote('lote-retro3', 'run-retro3', {_lit(o.payload_sha256)}, 'v', '{{}}', "
                            + f"{_lit((o.available_at + timedelta(minutes=1)).isoformat())});", db=banco_obs, papel="dil_obs_escritor")
    assert "recebido_em no futuro" in erro
    # (d) bytes recebidos às 06:00 pelo banco; observação dizendo que o VOLC sabia às 05:00 → recusada
    cedo = o_pg(obs, 29, payload=b"retro-1", conta="retro4", lote_id="lote-retro4")
    erro = cluster_pg.falha(script_carga([cedo], relogio=o.available_at), db=banco_obs, papel="dil_obs_escritor")
    assert "retroativo" in erro
    # (e) futuro: available_at depois do relógio do banco → ingested_at < available_at
    futuro = o_pg(obs, 50, payload=b"futuro-1", conta="futuro")
    assert "ck_obs_relogios" in cluster_pg.falha(script_carga([futuro], relogio=futuro.available_at - timedelta(hours=1)),
                                                 db=banco_obs, papel="dil_obs_escritor")


def test_payload_hash_conferido_pelo_banco(cluster_pg, banco_obs):
    erro = cluster_pg.falha(f"SELECT dil_obs.registrar_payload({_lit('0' * 64)}, 'abc'::bytea, 'text/plain');",
                            db=banco_obs, papel="dil_obs_escritor")
    assert "sha256 não confere" in erro
    erro = cluster_pg.falha(f"INSERT INTO dil_obs.payload_bruto (sha256, corpo_bruto, content_type, recebido_em) "
                            f"VALUES ({_lit('0' * 64)}, 'abc'::bytea, 'text/plain', now());", db=banco_obs)
    assert "ck_payload_hash_confere" in erro
    # corpo não-JSON é guardado (bruto) com corpo jsonb nulo
    corpo = b"<html>502 Bad Gateway</html>"
    cluster_pg.psql(f"SELECT dil_obs.registrar_payload({_lit(_sha(corpo))}, decode({_lit(corpo.hex())}, 'hex'), 'text/html');",
                    db=banco_obs, papel="dil_obs_escritor")
    assert cluster_pg.psql(f"SELECT corpo IS NULL FROM dil_obs.payload_bruto WHERE sha256 = {_lit(_sha(corpo))};", db=banco_obs) == "t"


# ============================================================== ausência != falha, ponta a ponta
def test_missing_unavailable_late_distintos_no_banco(cluster_pg, banco_obs, obs):
    sem = dict(valor=None, moeda=None)
    lista = [
        o_pg(obs, 30, payload=b"amf-ok", conta="amf", entidade_id="1"),
        o_pg(obs, 30, payload=b"amf-vazio", conta="amf", entidade_id="2", status="missing", motivo="linha_ausente_na_resposta", **sem),
        o_pg(obs, 30, payload=b"amf-503", conta="amf", entidade_id="3", status="unavailable", motivo="http_503", **sem),
        o_pg(obs, 30, payload=b"amf-tarde", conta="amf", entidade_id="4", status="late", motivo="d-1_nao_publicado", **sem),
        o_pg(obs, 30, payload=b"amf-zero", conta="amf", entidade_id="5", status="zero_confirmed", valor=0),
    ]
    carregar(cluster_pg, banco_obs, lista)
    out = cluster_pg.psql(
        "SELECT entidade_id || ':' || status || ':' || coalesce(valor::text, 'NULL') FROM dil_obs.observacao_latest "
        "WHERE conta = 'amf' ORDER BY entidade_id;", db=banco_obs, papel="dil_obs_leitor")
    assert out.splitlines() == ["1:observed:5000000", "2:missing:NULL", "3:unavailable:NULL", "4:late:NULL", "5:zero_confirmed:0"]
    # SUM do SQL ignora NULL: o número sozinho mente; a contagem por status é obrigatória ao lado
    soma = cluster_pg.psql("SELECT sum(valor) || '|' || count(*) FILTER (WHERE valor IS NULL) FROM dil_obs.observacao_latest "
                           "WHERE conta = 'amf';", db=banco_obs, papel="dil_obs_leitor")
    assert soma == "5000000|3"


def test_dead_letter_registra_rejeicao(cluster_pg, banco_obs, obs):
    o = o_pg(obs, 30, payload=b"dl-1", conta="dl")
    cluster_pg.psql(script_carga([o]), db=banco_obs, papel="dil_obs_escritor")
    det = json.dumps({"pedida": "utm_campaign", "devolvida": "land_uri", "indice": 0})
    cluster_pg.psql(f"SELECT dil_obs.registrar_dead_letter({_lit(o.run_id)}, {_lit(o.lote_id)}, {_lit(o.payload_sha256)}, "
                    f"'chave_substituida', {_lit(det)}::jsonb);", db=banco_obs, papel="dil_obs_escritor")
    assert cluster_pg.psql("SELECT detalhe->>'devolvida' FROM dil_obs.dead_letter WHERE motivo = 'chave_substituida';",
                           db=banco_obs, papel="dil_obs_leitor") == "land_uri"


# ============================================================== RLS e grants
def test_rls_e_grants_minimos(cluster_pg, banco_obs, obs):
    carregar(cluster_pg, banco_obs, [o_pg(obs, 30, payload=b"rls-1", conta="rls")])
    db = banco_obs
    assert cluster_pg.psql("SELECT count(*) > 0 FROM dil_obs.observacao;", db=db, papel="dil_obs_leitor") == "t"
    assert cluster_pg.psql("SELECT count(*) > 0 FROM dil_obs.observacao_as_of(now());", db=db, papel="dil_obs_leitor") == "t"
    o = o_pg(obs, 31, payload=b"rls-2", conta="rls")
    # leitor não insere (nem direto, nem pela função)
    assert "permission denied" in cluster_pg.falha(_insert_mutado({}, "rls"), db=db, papel="dil_obs_leitor")
    assert "permission denied" in cluster_pg.falha(script_carga([o], papel="dil_obs_leitor"), db=db, papel="dil_obs_leitor")
    # escritor não lê nem escreve direto na tabela: só pelas funções
    assert "permission denied" in cluster_pg.falha("SELECT * FROM dil_obs.observacao;", db=db, papel="dil_obs_escritor")
    assert "permission denied" in cluster_pg.falha(_insert_mutado({}, "rls"), db=db, papel="dil_obs_escritor")
    # anon/authenticated (com o default ACL aberto do Supabase simulado no cluster) não veem nada
    for papel in ("anon", "authenticated"):
        assert "permission denied" in cluster_pg.falha("SELECT * FROM dil_obs.observacao;", db=db, papel=papel)
        assert "permission denied" in cluster_pg.falha("SELECT * FROM dil_obs.observacao_latest;", db=db, papel=papel)
        assert "permission denied" in cluster_pg.falha("SELECT dil_obs.observacao_as_of(now());", db=db, papel=papel)
        assert "permission denied" in cluster_pg.falha(script_carga([o], papel=papel), db=db, papel=papel)
    # PUBLIC: um papel qualquer também não executa nada
    cluster_pg.psql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='qualquer') THEN "
                    "CREATE ROLE qualquer NOLOGIN; END IF; END $$;", db=db)
    assert "permission denied" in cluster_pg.falha(script_carga([o], papel="qualquer"), db=db, papel="qualquer")
    # privilégios efetivos, conferidos pelo catálogo
    priv = cluster_pg.psql(
        "SELECT has_table_privilege('dil_obs_leitor','dil_obs.observacao','INSERT')::text || "
        "has_table_privilege('dil_obs_leitor','dil_obs.observacao','UPDATE')::text || "
        "has_table_privilege('dil_obs_escritor','dil_obs.observacao','SELECT')::text || "
        "has_function_privilege('anon','dil_obs.registrar_observacao(json)','EXECUTE')::text || "
        "has_function_privilege('dil_obs_escritor','dil_obs.registrar_observacao(json)','EXECUTE')::text;", db=db)
    assert priv == "falsefalsefalsefalsetrue"


# ============================================================== equivalência SQL × Python
def _sequencia(obs, rng: random.Random, conta: str, n: int):
    eventos = []
    for h in sorted(rng.sample(range(25, 400), n)):
        ent, met = rng.choice(["1", "2", "3"]), rng.choice(["cost", "clicks"])
        p = rng.choice([b"A", b"B", b"C", b"[]", b"ERR"])
        status = {b"[]": "missing", b"ERR": "unavailable", b"B": "zero_confirmed"}.get(p, "observed")
        valor = {b"A": 10, b"B": 0, b"C": 30}.get(p)
        kw = dict(entidade_id=ent, status=status, valor=valor, motivo=None if valor is not None else status,
                  run_id=f"run-{conta}-{h}")
        if met == "clicks":
            kw.update(metrica="clicks", unidade="contagem", moeda=None)
        elif valor is not None:
            kw["valor"] = valor * 1_000_000
        else:
            kw["moeda"] = None
        # conta no payload: bytes são endereçados por conteúdo e o relógio simulado volta entre sequências
        eventos.append(o_pg(obs, h, payload=p + ent.encode() + met.encode() + conta.encode(), conta=conta, **kw))
        if rng.random() < 0.3:
            eventos.append(eventos[-1])
    return eventos


def test_equivalencia_as_of_sql_python(cluster_pg, banco_obs, obs):
    rng = random.Random(1610)
    total = {"inserido": 0, "noop": 0, "reafirmado": 0}
    for k in range(8):
        conta = f"eq{k}"
        seq = _sequencia(obs, rng, conta, rng.randint(8, 30))
        reg = Registro()
        esperado = [reg.registrar(o).value for o in seq]
        obtido = carregar(cluster_pg, banco_obs, seq)
        assert obtido == esperado, f"registro divergiu na sequência {conta}"
        for r in obtido:
            total[r] += 1
        for h in sorted(rng.sample(range(20, 420), 8)) + [5000]:
            t = BASE + timedelta(hours=h)
            assert as_of_sql(cluster_pg, banco_obs, t, conta) == as_of_py(reg, t, conta), f"as_of divergiu em {conta} h={h}"
    assert all(v > 0 for v in total.values()), f"amostra não exercitou todos os caminhos: {total}"
