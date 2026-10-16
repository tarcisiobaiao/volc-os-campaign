"""Views candidatas de qualidade (thread G) no PostgreSQL 16 descartável.

Base: DDL REAL do v21 Google Ads (043c77f5) e JoinAds v2 (192bc065), copiado byte a byte em
`migrations_candidatas/views_qualidade/base_real/` + `raw_events` mínima (DDL real não versionado).
Três bancos: cenário `limpo` (nenhuma regra acima de info), `producao_conhecida` e `estressado`
(todas as regras com fixture disparam). Cada view tem caso que dispara e caso que não dispara, e
o espelho Python é comparado com a view no MESMO dataset (equivalência).
Fixtures de PG: `cluster_pg` do conftest da thread A (socket unix, porta alta, derrubado no teardown).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from volc_dil.fundacao.observacao import Coletor
from volc_dil.fundacao.qualidade import sql_views
from volc_dil.fundacao.qualidade.adaptadores import cobertura_de_raw_events, observacoes_de_tabelas, runs_de_tabelas
from volc_dil.fundacao.qualidade.agenda import LIMIARES_PADRAO, SLA_PADRAO
from volc_dil.fundacao.qualidade.integridade import avaliar_cobertura_atribuicao
from volc_dil.fundacao.qualidade.leituras import classificar_duplicacao, medir_zero_sintetizado
from volc_dil.fundacao.qualidade.reconciliacao import (
    agregar_receita_joinads,
    avaliar_reconciliacao_custo,
    avaliar_reconciliacao_receita,
)
from volc_dil.fundacao.qualidade.runs import (
    avaliar_completude_slots,
    avaliar_frescor,
    avaliar_runs_orfaos,
    checar_falha_silenciosa,
)
from volc_dil.fundacao.qualidade.sintetico import AGORA_PADRAO, gerar_tabelas

RAIZ = Path(__file__).resolve().parents[3]
DIR_VIEWS = RAIZ / "experiments" / "data-intelligence-lab" / "migrations_candidatas" / "views_qualidade"
BASE = DIR_VIEWS / "base_real"
ARQUIVOS_BASE = (
    ("v21_01_google_ads_coleta_canonica.sql", "043c77f545aeb182758694544511d25152f1dcf3"),
    ("v21_02_google_ads_hash_no_servidor.sql", "043c77f545aeb182758694544511d25152f1dcf3"),
    ("v21_03_google_ads_finalizacao_run.sql", "043c77f545aeb182758694544511d25152f1dcf3"),
    ("20261015163704_joinads_collection_canonical.sql", "192bc06525944984d7fad9def4ce4ca34a4b0f02"),
    ("20261015170000_joinads_latest_collector_version_guard.sql", "192bc06525944984d7fad9def4ce4ca34a4b0f02"),
)
ORDEM_TABELAS = ("google_ads_collection_run", "google_ads_raw_batch", "google_ads_observation",
                 "joinads_collection_run", "joinads_raw_batch", "joinads_observation", "raw_events")
CENARIOS = ("limpo", "producao_conhecida", "estressado")
SEED = 20261016
VIEWS_DQ01 = ("dq_parametros_sla", "dq_parametros_limiares", "dq_runs", "dq_slots", "dq_freshness",
              "dq_completude_hora", "dq_runs_orfaos", "dq_falha_silenciosa", "dq_duplicacao",
              "dq_zero_sintetizado", "dq_reconciliacao_joinads", "dq_reconciliacao_custo_d0_d1",
              "dq_cobertura_atribuicao_sensor", "dq_esquema_joinads", "dq_substituicao_fonte")


# --------------------------------------------------------------------------- utilidades


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def aplicar_base(cluster, db: str) -> None:
    cluster.psql((BASE / "00_prelude_somente_teste.sql").read_text(encoding="utf-8"), db=db)
    for nome, _ in ARQUIVOS_BASE:
        cluster.psql((BASE / nome).read_text(encoding="utf-8"), db=db)


def carregar(cluster, db: str, tabelas: dict[str, list[dict]]) -> None:
    partes = []
    for t in ORDEM_TABELAS:
        linhas = tabelas.get(t) or []
        if not linhas:
            continue
        cols = sorted({k for ln in linhas for k in ln})
        corpo = json.dumps(linhas, ensure_ascii=False)
        assert "$dq$" not in corpo
        lista = ", ".join(cols)
        partes.append(f"INSERT INTO public.{t} ({lista}) SELECT {lista} "
                      f"FROM jsonb_populate_recordset(NULL::public.{t}, $dq${corpo}$dq$::jsonb);")
    cluster.psql("\n".join(partes), db=db)


def consultar(cluster, db: str, sql: str, agora: datetime | None = AGORA_PADRAO, papel: str | None = None) -> list[dict]:
    pre = f"SET dil_qualidade.agora = {_lit(agora.isoformat())};\n" if agora else ""
    saida = cluster.psql(f"{pre}SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM ({sql}) t;", db=db, papel=papel)
    return json.loads(saida.splitlines()[-1])


def ts(v) -> datetime | None:
    if v is None:
        return None
    return datetime.fromisoformat(str(v)).astimezone(timezone.utc)


@pytest.fixture(scope="module")
def bancos(cluster_pg):
    """cenário -> (db, tabelas). Base real + views dq_01 + carga sintética."""
    out = {}
    up = (DIR_VIEWS / "dq_01_views_qualidade.sql").read_text(encoding="utf-8")
    for c in CENARIOS:
        db = cluster_pg.novo_banco(f"dq_{c}")
        aplicar_base(cluster_pg, db)
        tabelas = gerar_tabelas(SEED, c, AGORA_PADRAO)
        carregar(cluster_pg, db, tabelas)
        cluster_pg.psql(up, db=db)
        out[c] = (db, tabelas)
    return out


# --------------------------------------------------------------------------- base e segurança


def test_ddl_base_igual_a_ref():
    """As cópias em base_real/ são byte a byte o DDL das refs citadas (skip se a ref não existir)."""
    git = shutil.which("git")
    if not git:
        pytest.skip("git indisponível para conferir as refs")
    for nome, ref in ARQUIVOS_BASE:
        p = subprocess.run([git, "-C", str(RAIZ), "show", f"{ref}:supabase/migrations/{nome}"],
                           capture_output=True, timeout=30)
        if p.returncode != 0:
            pytest.skip(f"ref {ref[:12]} indisponível neste clone: {p.stderr.decode()[:120]}")
        assert p.stdout == (BASE / nome).read_bytes(), nome


def test_views_security_invoker_grants_e_somente_leitura(cluster_pg, bancos):
    db, _ = bancos["limpo"]
    linhas = consultar(cluster_pg, db, """
        SELECT c.relname, c.relkind, coalesce(array_to_string(c.reloptions, ','), '') AS opcoes,
               has_table_privilege('service_role', c.oid, 'SELECT') AS sr_select,
               has_table_privilege('service_role', c.oid, 'INSERT') AS sr_insert,
               has_table_privilege('anon', c.oid, 'SELECT') AS anon_select,
               has_table_privilege('authenticated', c.oid, 'SELECT') AS auth_select
        FROM pg_class c WHERE c.relnamespace = 'dil_qualidade'::regnamespace ORDER BY 1""", agora=None)
    assert sorted(r["relname"] for r in linhas) == sorted(VIEWS_DQ01)
    for r in linhas:
        assert r["relkind"] == "v", r
        assert "security_invoker=true" in r["opcoes"], r
        assert r["sr_select"] and not r["sr_insert"] and not r["anon_select"] and not r["auth_select"], r
    erro = cluster_pg.falha("SELECT * FROM dil_qualidade.dq_freshness;", db=db, papel="anon")
    assert "permission denied" in erro
    assert consultar(cluster_pg, db, "SELECT count(*) AS n FROM dil_qualidade.dq_freshness", papel="service_role")[0]["n"] == 5
    erro = cluster_pg.falha("INSERT INTO dil_qualidade.dq_parametros_limiares VALUES ('x', 1);", db=db,
                            papel="service_role")
    assert "permission denied" in erro or "cannot insert" in erro


def test_nenhuma_view_expoe_sid_ou_pid(cluster_pg, bancos):
    db, _ = bancos["estressado"]
    cols = consultar(cluster_pg, db, """
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema = 'dil_qualidade'""", agora=None)
    nomes = {c["column_name"] for c in cols}
    assert not nomes & {"sid", "pid", "ts_sec", "payload"}
    sensor = {c["column_name"] for c in cols if c["table_name"] == "dq_cobertura_atribuicao_sensor"}
    assert sensor == {"dia", "sessoes_total", "sessoes_pagas", "pagas_com_campanha", "pagas_com_source",
                      "cobertura", "estado", "severidade"}


def test_parametros_sql_iguais_aos_python(cluster_pg, bancos):
    db, _ = bancos["limpo"]
    sla = {r["coletor_logico"]: r for r in consultar(cluster_pg, db, """
        SELECT fonte, coletor_logico, grao, minuto, horas, extract(epoch FROM tolerancia)::int AS tol,
               extract(epoch FROM timeout_running)::int AS timeout, min_linhas, extract(epoch FROM folga)::int AS folga, tz
        FROM dil_qualidade.dq_parametros_sla""", agora=None)}
    assert set(sla) == set(SLA_PADRAO)
    for k, s in SLA_PADRAO.items():
        r = sla[k]
        assert (r["fonte"], r["grao"], r["minuto"], tuple(r["horas"]), r["tol"], r["timeout"], r["min_linhas"],
                r["folga"], r["tz"]) == (s.fonte, s.grao, s.minuto, s.horas, int(s.tolerancia.total_seconds()),
                                         int(s.timeout_running.total_seconds()), s.min_linhas,
                                         int(s.folga.total_seconds()), s.tz), k
    lim = {r["nome"]: float(r["valor"]) for r in consultar(
        cluster_pg, db, "SELECT nome, valor FROM dil_qualidade.dq_parametros_limiares", agora=None)}
    assert lim == {k: float(v) for k, v in LIMIARES_PADRAO.items()}


# --------------------------------------------------------------------------- dispara / não dispara


def _q(cluster, bancos, cenario, sql):
    return consultar(cluster, bancos[cenario][0], sql)


def test_dq_freshness_dispara_e_nao_dispara(cluster_pg, bancos):
    est = {r["coletor_logico"]: r["estado"] for r in _q(cluster_pg, bancos, "estressado", "SELECT * FROM dil_qualidade.dq_freshness")}
    assert est == {"n8n-google-ads-d0": "atrasado", "n8n-google-ads-d1": "fresco",
                   "n8n-google-ads-terms-keywords": "sem_registro", "n8n_joinads_v2:intraday": "parado",
                   "n8n_joinads_v2:d1": "fresco"}
    limpo = _q(cluster_pg, bancos, "limpo", "SELECT * FROM dil_qualidade.dq_freshness")
    assert {r["estado"] for r in limpo} == {"fresco"} and {r["severidade"] for r in limpo} == {"ok"}


def test_dq_freshness_fora_do_horario_nao_e_buraco(cluster_pg, bancos):
    """02:00 local de 16/10: o último slot D0 vencido é 23:07 de 15/10; nenhum slot entre 23:07 e 06:07."""
    db, _ = bancos["limpo"]
    madrugada = datetime(2026, 10, 16, 5, 0, tzinfo=timezone.utc)
    r = {x["coletor_logico"]: x for x in consultar(cluster_pg, db, "SELECT * FROM dil_qualidade.dq_freshness", agora=madrugada)}
    assert r["n8n-google-ads-d0"]["estado"] == "fresco"
    assert ts(r["n8n-google-ads-d0"]["slot_referencia"]) == datetime(2026, 10, 16, 2, 7, tzinfo=timezone.utc)
    horas = {x["hora_local"] for x in consultar(cluster_pg, db, "SELECT * FROM dil_qualidade.dq_completude_hora "
                                                "WHERE coletor_logico = 'n8n-google-ads-d0'", agora=madrugada)}
    assert horas.isdisjoint({0, 1, 2, 3, 4, 5})


def test_dq_completude_hora(cluster_pg, bancos):
    est = _q(cluster_pg, bancos, "estressado", "SELECT coletor_logico, hora_local, dia_local, classe FROM dil_qualidade.dq_completude_hora")
    classes = {(r["coletor_logico"], r["dia_local"], r["hora_local"]): r["classe"] for r in est}
    assert classes[("n8n-google-ads-d0", "2026-10-16", 10)] == "falha_declarada"
    assert classes[("n8n-google-ads-d0", "2026-10-16", 11)] == "ausente_silencioso"
    assert ("n8n-google-ads-d0", "2026-10-16", 12) not in classes  # 12:07 ainda não chegou: nem slot é
    limpo = {r["classe"] for r in _q(cluster_pg, bancos, "limpo", "SELECT classe FROM dil_qualidade.dq_completude_hora")}
    assert limpo <= {"ok", "pendente"}


def test_dq_runs_orfaos(cluster_pg, bancos):
    est = _q(cluster_pg, bancos, "estressado", "SELECT * FROM dil_qualidade.dq_runs_orfaos")
    assert len(est) == 3 and {r["coletor_logico"] for r in est} == {"n8n-google-ads-terms-keywords"}
    # limpo tem 2 runs `running` manuais: um recente e um antigo com sinal de vida recente -> nenhum órfão
    assert _q(cluster_pg, bancos, "limpo", "SELECT * FROM dil_qualidade.dq_runs_orfaos") == []
    n_running = _q(cluster_pg, bancos, "limpo", "SELECT count(*) AS n FROM dil_qualidade.dq_runs WHERE status = 'running'")
    assert n_running[0]["n"] == 2


def test_dq_falha_silenciosa(cluster_pg, bancos):
    est = _q(cluster_pg, bancos, "estressado", "SELECT * FROM dil_qualidade.dq_falha_silenciosa")
    assert len(est) == 1 and est[0]["coletor_logico"] == "n8n-google-ads-d1" and est[0]["linhas_escritas"] == 0
    assert _q(cluster_pg, bancos, "limpo", "SELECT * FROM dil_qualidade.dq_falha_silenciosa") == []


def test_dq_duplicacao(cluster_pg, bancos):
    est = {r["classe"] for r in _q(cluster_pg, bancos, "estressado", "SELECT classe FROM dil_qualidade.dq_duplicacao")}
    assert {"conflito_no_run", "duplicata_exata_no_run", "reingestao_suspeita"} <= est
    limpo = _q(cluster_pg, bancos, "limpo", "SELECT classe, severidade FROM dil_qualidade.dq_duplicacao")
    assert limpo and {r["severidade"] for r in limpo} == {"info"}  # releituras esperadas existem e não alarmam


def test_dq_zero_sintetizado(cluster_pg, bancos):
    prod = _q(cluster_pg, bancos, "producao_conhecida", "SELECT * FROM dil_qualidade.dq_zero_sintetizado")
    assert prod and all(r["severidade"] == "alto" for r in prod)
    d0 = [r for r in prod if r["coletor"] == "n8n-google-ads-d0" and r["metric_date"] == "2026-10-15"][0]
    assert d0["sintetizados"] / d0["total"] == pytest.approx(0.8)  # forma do achado real L11 (88/110)
    limpo = _q(cluster_pg, bancos, "limpo", "SELECT * FROM dil_qualidade.dq_zero_sintetizado")
    assert {r["severidade"] for r in limpo} == {"ok"}
    assert sum(r["zeros_com_linha"] for r in limpo) > 0 and sum(r["sintetizados"] for r in limpo) == 0


def test_dq_reconciliacao_joinads(cluster_pg, bancos):
    est = {r["metric_date"]: r for r in _q(cluster_pg, bancos, "estressado", "SELECT * FROM dil_qualidade.dq_reconciliacao_joinads")}
    assert est["2026-10-15"]["estado"] == "cobertura_baixa" and float(est["2026-10-15"]["cobertura"]) == pytest.approx(0.6)
    assert est["2026-10-14"]["estado"] == "excesso"
    limpo = _q(cluster_pg, bancos, "limpo", "SELECT * FROM dil_qualidade.dq_reconciliacao_joinads")
    assert limpo and {r["estado"] for r in limpo} == {"ok"}
    assert all(float(r["cobertura"]) == pytest.approx(0.98, abs=1e-3) for r in limpo)


def test_dq_reconciliacao_custo(cluster_pg, bancos):
    est = _q(cluster_pg, bancos, "estressado", "SELECT * FROM dil_qualidade.dq_reconciliacao_custo_d0_d1 WHERE estado = 'divergente'")
    assert len(est) == 1 and est[0]["campaign_id"] == "21000000001"
    limpo = {r["estado"] for r in _q(cluster_pg, bancos, "limpo", "SELECT estado FROM dil_qualidade.dq_reconciliacao_custo_d0_d1")}
    assert "divergente" not in limpo and "ok" in limpo


def test_dq_cobertura_atribuicao_sensor(cluster_pg, bancos):
    prod = _q(cluster_pg, bancos, "producao_conhecida", "SELECT * FROM dil_qualidade.dq_cobertura_atribuicao_sensor")
    assert sum(r["sessoes_pagas"] for r in prod) == 28 and sum(r["pagas_com_campanha"] for r in prod) == 0  # forma de L4
    assert {r["severidade"] for r in prod} == {"alto"}
    limpo = _q(cluster_pg, bancos, "limpo", "SELECT * FROM dil_qualidade.dq_cobertura_atribuicao_sensor")
    assert {r["estado"] for r in limpo} == {"ok"}


def test_dq_esquema_e_substituicao(cluster_pg, bancos):
    esq = _q(cluster_pg, bancos, "estressado", "SELECT * FROM dil_qualidade.dq_esquema_joinads WHERE classe <> 'estavel'")
    assert [r["endpoint"] for r in esq] == ["earnings"]
    assert {r["classe"] for r in _q(cluster_pg, bancos, "limpo", "SELECT classe FROM dil_qualidade.dq_esquema_joinads")} == {"estavel"}
    sub = {r["regra"] for r in _q(cluster_pg, bancos, "estressado", "SELECT regra FROM dil_qualidade.dq_substituicao_fonte")}
    assert sub == {"custom_key_substituida", "campanha_mudou_de_conta", "moeda_trocada"}
    assert _q(cluster_pg, bancos, "limpo", "SELECT * FROM dil_qualidade.dq_substituicao_fonte") == []


# --------------------------------------------------------------------------- equivalência Python × SQL


@pytest.mark.parametrize("cenario", CENARIOS)
def test_equivalencia_python_sql(cluster_pg, bancos, cenario):
    db, tabelas = bancos[cenario]
    agora = AGORA_PADRAO
    runs = runs_de_tabelas(tabelas)
    obs = observacoes_de_tabelas(tabelas)
    q = lambda sql: consultar(cluster_pg, db, sql, agora)  # noqa: E731

    # frescor
    py = {(e.coletor, e.estado, e.slots_perdidos, e.ultimo_sucesso, e.slot_referencia, e.severidade)
          for e in avaliar_frescor(runs, agora)}
    sq = {(r["coletor_logico"], r["estado"], r["slots_perdidos"], ts(r["ultimo_sucesso"]), ts(r["slot_referencia"]),
           r["severidade"]) for r in q("SELECT * FROM dil_qualidade.dq_freshness")}
    assert py and py == sq

    # completude por slot
    py = {(s.coletor, s.slot, s.classe, s.n_runs) for s in avaliar_completude_slots(runs, agora)}
    sq = {(r["coletor_logico"], ts(r["slot"]), r["classe"], r["n_runs"])
          for r in q("SELECT * FROM dil_qualidade.dq_completude_hora")}
    assert py and py == sq

    # órfãos e falha silenciosa
    assert {o.run_id for o in avaliar_runs_orfaos(runs, agora)} == \
        {r["run_id"] for r in q("SELECT run_id FROM dil_qualidade.dq_runs_orfaos")}
    assert {a.chave for a in checar_falha_silenciosa(runs, agora)} == \
        {r["run_id"] for r in q("SELECT run_id FROM dil_qualidade.dq_falha_silenciosa")}

    # duplicação
    py = {(c.fonte, c.grao, c.chave, c.escopo, c.run_id, c.classe, c.n_leituras, c.n_runs, c.n_payloads, c.severidade)
          for c in classificar_duplicacao(obs, agora)}
    sq = {(r["fonte"], r["grao"], r["chave"], r["escopo"], r["run_id"], r["classe"], r["n_leituras"], r["n_runs"],
           r["n_payloads"], r["severidade"]) for r in q("SELECT * FROM dil_qualidade.dq_duplicacao")}
    assert py and py == sq

    # zero sintetizado
    py = {(z.coletor, z.metric_date.isoformat(), z.total, z.zeros, z.sintetizados, z.zeros_com_linha, z.ambiguos,
           z.nulos, z.proporcao_sintetizada, z.severidade()) for z in
          medir_zero_sintetizado([o for o in obs if o.fonte == "google_ads"], agora)}
    sq = {(r["coletor"], r["metric_date"], r["total"], r["zeros"], r["sintetizados"], r["zeros_com_linha"],
           r["ambiguos"], r["nulos"], float(r["proporcao_sintetizada"]), r["severidade"])
          for r in q("SELECT * FROM dil_qualidade.dq_zero_sintetizado")}
    assert py and py == sq

    # reconciliação de receita
    py = {(e.metric_date.isoformat(), e.estado, e.severidade, e.cobertura)
          for e in avaliar_reconciliacao_receita(agregar_receita_joinads(obs, runs, agora))}
    sq = {(r["metric_date"], r["estado"], r["severidade"], None if r["cobertura"] is None else float(r["cobertura"]))
          for r in q("SELECT * FROM dil_qualidade.dq_reconciliacao_joinads")}
    assert py and py == sq

    # reconciliação de custo
    inf = float("inf")
    py = {(e.conta, e.campanha, e.metric_date.isoformat(), e.estado, e.severidade,
           None if e.diferenca_relativa in (None, inf) else e.diferenca_relativa)
          for e in avaliar_reconciliacao_custo(obs, runs, agora)}
    sq = {(r["customer_id"], r["campaign_id"], r["metric_date"], r["estado"], r["severidade"],
           None if r["diferenca_relativa"] is None else float(r["diferenca_relativa"]))
          for r in q("SELECT * FROM dil_qualidade.dq_reconciliacao_custo_d0_d1")}
    assert py and py == sq

    # cobertura do sensor
    py = {(ln.dia.isoformat(), ln.sessoes_total, ln.sessoes_pagas, ln.pagas_com_campanha, cob, estado, sev)
          for ln, cob, estado, sev in avaliar_cobertura_atribuicao(cobertura_de_raw_events(tabelas["raw_events"], agora))}
    sq = {(r["dia"], r["sessoes_total"], r["sessoes_pagas"], r["pagas_com_campanha"],
           None if r["cobertura"] is None else float(r["cobertura"]), r["estado"], r["severidade"])
          for r in q("SELECT * FROM dil_qualidade.dq_cobertura_atribuicao_sensor")}
    assert py and py == sq


# --------------------------------------------------------------------------- SELECTs somente leitura


def test_selects_somente_leitura_atualizados_e_equivalentes(cluster_pg, bancos):
    """O arquivo commitado é o gerado; cada SELECT roda em transação READ ONLY e devolve o mesmo que a view."""
    assert sql_views.CAMINHO_SELECTS.read_text(encoding="utf-8") == sql_views.gerar_selects()
    db, _ = bancos["estressado"]
    views = sql_views.ler_views(sql_views.CAMINHO_UP.read_text(encoding="utf-8"))
    for nome in views:
        if nome in sql_views.AUXILIARES:
            continue
        sel = sql_views.select_autocontido(nome, views)
        assert "dil_qualidade." not in sel and "CREATE" not in sel.upper().split("WITH", 1)[0]
        saida = cluster_pg.psql(
            "BEGIN READ ONLY;\n"
            f"SELECT coalesce(jsonb_agg(t ORDER BY t::text), '[]'::jsonb) FROM ({sel}) t;\n"
            f"SELECT coalesce(jsonb_agg(t ORDER BY t::text), '[]'::jsonb) FROM dil_qualidade.{nome} t;\n"
            "COMMIT;", db=db)
        a, b = [ln for ln in saida.splitlines() if ln.startswith("[")]
        assert json.loads(a) == json.loads(b), nome


def test_export_read_only_minimizado_reproduz_os_achados(cluster_pg, bancos):
    """O export (um SELECT, sem payload bruto, sensor agregado) rodado em transação READ ONLY dá ao recibo
    os mesmos achados que as tabelas completas — menos deriva de esquema, que fica com a view."""
    from volc_dil.fundacao.qualidade.motor import ConjuntoSaude, avaliar_saude

    db, tabelas = bancos["estressado"]
    sql = (DIR_VIEWS / "export_recibo_somente_leitura.sql").read_text(encoding="utf-8")
    sql = sql.replace("now()", f"{_lit(AGORA_PADRAO.isoformat())}::timestamptz")
    saida = cluster_pg.psql(f"BEGIN READ ONLY;\n{sql}\nCOMMIT;", db=db)
    export = json.loads([ln for ln in saida.splitlines() if ln.startswith("{")][0])
    assert "payload" not in json.dumps(export["tabelas"]["joinads_raw_batch"])
    assert '"sid"' not in json.dumps(export) and '"pid"' not in json.dumps(export)
    via_export = avaliar_saude(ConjuntoSaude.de_dict(export, AGORA_PADRAO), AGORA_PADRAO)
    completo = avaliar_saude(ConjuntoSaude.de_tabelas(tabelas, AGORA_PADRAO), AGORA_PADRAO)
    tira = lambda xs: [a.como_dict() for a in xs if not a.regra.startswith("esquema_")]  # noqa: E731
    assert tira(via_export) == tira(completo) and len(tira(completo)) > 10
    assert any(a.regra.startswith("esquema_") for a in completo)


# --------------------------------------------------------------------------- rollback


def test_rollback_dq01_e_reaplicacao(cluster_pg):
    db = cluster_pg.novo_banco("dq_rollback")
    aplicar_base(cluster_pg, db)
    up = (DIR_VIEWS / "dq_01_views_qualidade.sql").read_text(encoding="utf-8")
    down = (DIR_VIEWS / "dq_01_views_qualidade.down.sql").read_text(encoding="utf-8")
    contar_base = "SELECT count(*) FROM pg_class WHERE relnamespace = 'public'::regnamespace"
    n_base = cluster_pg.psql(contar_base, db=db)
    cluster_pg.psql(up, db=db)
    cluster_pg.psql(down, db=db)
    assert cluster_pg.psql("SELECT to_regnamespace('dil_qualidade') IS NULL", db=db) == "t"
    assert cluster_pg.psql(contar_base, db=db) == n_base  # nada da base foi tocado
    cluster_pg.psql(up, db=db)  # reaplicável depois do rollback
    assert cluster_pg.psql("SELECT count(*) FROM pg_class WHERE relnamespace = 'dil_qualidade'::regnamespace", db=db) == str(len(VIEWS_DQ01))


def test_dq01_recusa_sem_tabelas_base(cluster_pg):
    db = cluster_pg.novo_banco("dq_sem_base")
    erro = cluster_pg.falha((DIR_VIEWS / "dq_01_views_qualidade.sql").read_text(encoding="utf-8"), db=db)
    assert "tabelas-base ausentes" in erro
    assert cluster_pg.psql("SELECT to_regnamespace('dil_qualidade') IS NULL", db=db) == "t"


# --------------------------------------------------------------------------- dq_02 sobre dil_obs (depende de A)


def _relogio_dil_obs(t):
    """[thread A, R1-F1] troca o relógio do banco dil_obs._agora() (só no cluster descartável); None = now()."""
    corpo = "pg_catalog.now()" if t is None else f"'{t.isoformat()}'::timestamptz"
    return ("RESET ROLE; CREATE OR REPLACE FUNCTION dil_obs._agora() RETURNS timestamptz LANGUAGE sql STABLE "
            f"PARALLEL SAFE SET search_path = '' AS $$ SELECT {corpo} $$; SET ROLE dil_obs_escritor;")


def _carga_dil_obs(obs_fab, agora_real: datetime):
    """Observações via funções públicas de dil_obs: um coletor lento (p95 alto) e um rápido; um run com 20%
    de dead letter e um limpo."""
    import hashlib

    def sha(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()

    ji = (agora_real - timedelta(days=2)).replace(microsecond=0)
    jf = ji + timedelta(days=1)
    linhas, obs_lista = [], []
    for fonte, atraso, run in (("google_ads", timedelta(hours=3), "run-lento"), ("joinads", timedelta(seconds=30), "run-rapido")):
        payload = f'{{"fonte":"{fonte}"}}'.encode()
        avail = agora_real - atraso
        linhas.append(f"SELECT dil_obs.registrar_run({_lit(run)}, {_lit(fonte)}, 'coletor_{fonte}', '1.0.0', {_lit(ji.isoformat())});")
        # [thread A, resposta à R1-F1] o banco data payload e lote pelo PRÓPRIO relógio (dil_obs._agora()):
        # para simular bytes recebidos há 3 h, o relógio do banco vai a avail-5s e volta a now() antes das observações
        recebido = avail - timedelta(seconds=5)
        linhas.append(_relogio_dil_obs(recebido))
        linhas.append(f"SELECT dil_obs.registrar_payload({_lit(sha(payload))}, decode({_lit(payload.hex())}, 'hex'), 'application/json');")
        linhas.append(f"SELECT dil_obs.registrar_lote({_lit('lote-' + run)}, {_lit(run)}, {_lit(sha(payload))}, 'v1', '{{}}'::jsonb, {_lit(recebido.isoformat())});")
        linhas.append(_relogio_dil_obs(None))
        for i in range(5):
            o = obs_fab(fonte=fonte, payload=payload, entidade_id=str(100 + i), janela_inicio=ji, janela_fim=jf,
                        observed_at=jf + timedelta(hours=1), available_at=avail, ingested_at=avail,
                        run_id=run, lote_id="lote-" + run, coletor=Coletor(f"coletor_{fonte}", "1.0.0"),
                        schema_version="v1")  # [thread A, R1-F3] schema_version da observação = o do lote
            obs_lista.append(o)
            linhas.append(f"SELECT dil_obs.registrar_observacao({_lit(json.dumps(o.para_json()))}::json);")  # [A, R1-F9] entrada json
        n_dl = 1 if run == "run-lento" else 0
        for _ in range(n_dl):
            linhas.append(f"SELECT dil_obs.registrar_dead_letter({_lit(run)}, {_lit('lote-' + run)}, NULL, 'chave_substituida', '{{}}'::jsonb);")
        # [thread A, R1-F8] inseridas e dead letter são contadas pelo banco (NULL = "conte você")
        # [thread A, R2-G6] dead letter também conta em n_lidas, e run com dead letter fecha 'partial', não 'succeeded'
        linhas.append(f"SELECT dil_obs.finalizar_run({_lit(run)}, {_lit('partial' if n_dl else 'succeeded')}, {5 + n_dl}, NULL, 0, NULL, NULL);")
    return "\n".join(linhas), obs_lista


def test_dq02_views_dil_obs(cluster_pg, obs):
    from volc_dil.fundacao.qualidade.ponte_observacao import checar_latencia_ingestao, de_observacoes

    db = cluster_pg.novo_banco("dq_dil_obs")
    cluster_pg.aplicar("dil_obs_0001_schema_observacao.sql", db=db)
    cluster_pg.psql((DIR_VIEWS / "dq_02_views_dil_obs.sql").read_text(encoding="utf-8"), db=db)
    agora_real = datetime.now(timezone.utc)
    script, lista = _carga_dil_obs(obs, agora_real)
    cluster_pg.psql(script, db=db, papel="dil_obs_escritor")

    lat = {r["fonte"]: r for r in consultar(cluster_pg, db, "SELECT * FROM dil_qualidade.dq_obs_latencia_ingestao",
                                             agora=None, papel="dil_obs_leitor")}
    assert lat["google_ads"]["severidade"] == "aviso" and lat["google_ads"]["p95_s"] > 3600
    assert lat["joinads"]["severidade"] == "ok"
    dl = {r["run_id"]: r for r in consultar(cluster_pg, db, "SELECT * FROM dil_qualidade.dq_obs_dead_letter",
                                            agora=None, papel="dil_obs_leitor")}
    assert dl["run-lento"]["severidade"] == "alto" and dl["run-lento"]["motivos"] == {"chave_substituida": 1}
    assert dl["run-rapido"]["severidade"] == "ok"
    status = consultar(cluster_pg, db, "SELECT * FROM dil_qualidade.dq_obs_status", agora=None, papel="dil_obs_leitor")
    assert {r["status"] for r in status} == {"observed"}
    assert consultar(cluster_pg, db, "SELECT * FROM dil_qualidade.dq_obs_runs_orfaos", agora=None) == []
    assert "permission denied" in cluster_pg.falha("SELECT * FROM dil_qualidade.dq_obs_status;", db=db, papel="anon")

    # Python: a ponte agrupa as observações de A e a latência medida no BANCO (ingested_at = now()) dispara igual
    linhas_db = consultar(cluster_pg, db, "SELECT fonte, available_at, ingested_at FROM dil_obs.observacao", agora=None)
    assert len(de_observacoes(lista)) == 10
    from volc_dil.fundacao.qualidade.modelo import ObservacaoDQ
    dq = [ObservacaoDQ(fonte=r["fonte"], grao="campaign_day", chave=str(i), run_id="r",
                       coletor=f"coletor_{r['fonte']}", available_at=ts(r["available_at"]),
                       ingested_at=ts(r["ingested_at"])) for i, r in enumerate(linhas_db)]
    assert {a.fonte for a in checar_latencia_ingestao(dq)} == {"google_ads"}

    # rollback dq_02: some sem tocar dil_obs
    cluster_pg.psql((DIR_VIEWS / "dq_02_views_dil_obs.down.sql").read_text(encoding="utf-8"), db=db)
    assert cluster_pg.psql("SELECT to_regnamespace('dil_qualidade') IS NULL", db=db) == "t"
    assert cluster_pg.psql("SELECT count(*) FROM dil_obs.observacao", db=db) == "10"
