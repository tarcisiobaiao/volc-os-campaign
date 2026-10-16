"""Resposta à revisão adversarial R2 (thread G): cada teste falhava antes da correção.

G6  dead letter: run com n_lidas = 0 e dead letters (taxa NULL) não é `ok`; dead letter registrado depois do
    fechamento também alerta.
G7  `dq_obs_status` conta o estado VIGENTE (`dil_obs.observacao_as_of(agora)`), não versões.
G8  reconciliação JoinAds por domínio × dia, só onde há earnings válido E kv (universo da junção da C);
    casos de `probes/p_recon.py` e o mascaramento 60% + domínio sem earnings. Python e SQL.
G13 testes de comportamento que matam os mutantes G4 (invalid vira ok) e G7 (missing filtrado) aplicando a
    mutação na view e exigindo que a checagem acuse (sem depender da guarda do arquivo gerado).
G17 nenhum domínio real de cliente no gerador sintético.
G23 run só de confirmações (D2') não é "0 linhas".
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from volc_dil.fundacao.qualidade import SLA, checar_dead_letter, checar_falha_silenciosa, runs_de_run_coleta
from volc_dil.fundacao.qualidade.modelo import ObservacaoDQ, RunDQ, StatusDado, StatusRun
from volc_dil.fundacao.qualidade.reconciliacao import agregar_receita_joinads, avaliar_reconciliacao_receita

RAIZ = Path(__file__).resolve().parents[3]
DIR_VIEWS = RAIZ / "experiments" / "data-intelligence-lab" / "migrations_candidatas" / "views_qualidade"
SRC_QUALIDADE = RAIZ / "experiments" / "data-intelligence-lab" / "src" / "volc_dil" / "fundacao" / "qualidade"
UTC = timezone.utc


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _json(cluster, db, sql, papel=None):
    return json.loads(cluster.psql(f"SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM ({sql}) t;", db=db,
                                   papel=papel).splitlines()[-1])


# --------------------------------------------------------------------------- G8 (Python)

AGORA = datetime(2026, 10, 16, 15, tzinfo=UTC)
DIA = date(2026, 10, 14)
T = datetime(2026, 10, 15, 12, tzinfo=UTC)
RUN = RunDQ("r1", "joinads", "n8n_joinads_v2:d1", StatusRun.COMPLETED, T, T, versao_coletor=4)


def _o(chave, dominio, endpoint, campanha, receita, status=StatusDado.OBSERVED):
    return ObservacaoDQ("joinads", "x", chave, "r1", status, coletor="n8n_joinads_v2:d1", versao_coletor=4,
                        entidade=campanha, conta=dominio, metric_date=DIA, observed_at=T,
                        metricas={"revenue_client": receita}, atributos={"endpoint": endpoint}, moeda="USD")


def _estados(obs):
    return {e.linha.dominio: (e.estado, e.severidade, e.cobertura)
            for e in avaliar_reconciliacao_receita(agregar_receita_joinads(obs, [RUN], AGORA))}


CENARIOS_RECON = {
    # p_recon.py: B com earnings indisponível e kv coletado — antes B entrava no numerador e A virava excesso
    "earnings_B_indisponivel": (
        [_o("eA", "a.exemplo", "earnings", None, 100.0), _o("kA", "a.exemplo", "key_value_campaign_adunit", "1", 97.0),
         _o("eB", "b.exemplo", "earnings", None, None, StatusDado.UNAVAILABLE),
         _o("kB", "b.exemplo", "key_value_campaign_adunit", "2", 50.0)],
        {"a.exemplo": ("ok", "ok", 0.97), "b.exemplo": ("earnings_indisponivel", "aviso", None)}),
    # p_recon.py: B sem kv coletado — antes o earnings de B entrava no denominador e A virava cobertura baixa
    "kv_B_nao_coletado": (
        [_o("eA", "a.exemplo", "earnings", None, 100.0), _o("kA", "a.exemplo", "key_value_campaign_adunit", "1", 97.0),
         _o("eB", "b.exemplo", "earnings", None, 100.0)],
        {"a.exemplo": ("ok", "ok", 0.97), "b.exemplo": ("earnings_sem_kv", "alto", None)}),
    "so_A": (
        [_o("eA", "a.exemplo", "earnings", None, 100.0), _o("kA", "a.exemplo", "key_value_campaign_adunit", "1", 97.0)],
        {"a.exemplo": ("ok", "ok", 0.97)}),
    # mascaramento: A com 60% de cobertura + kv de B sem earnings somavam 98% -> `ok` no agregado do dia
    "mascaramento_60pct": (
        [_o("eA", "a.exemplo", "earnings", None, 100.0), _o("kA", "a.exemplo", "key_value_campaign_adunit", "1", 60.0),
         _o("kB", "b.exemplo", "key_value_campaign_adunit", "2", 38.0)],
        {"a.exemplo": ("cobertura_baixa", "aviso", 0.6), "b.exemplo": ("kv_sem_earnings", "aviso", None)}),
}


@pytest.mark.parametrize("nome", sorted(CENARIOS_RECON))
def test_g8_reconciliacao_por_dominio_dia_python(nome):
    obs, esperado = CENARIOS_RECON[nome]
    assert _estados(obs) == esperado


# --------------------------------------------------------------------------- G8 (SQL, mesmo cenário)


def _tabelas_joinads(obs_cen):
    """Converte o cenário em linhas reais de joinads_collection_run/raw_batch/observation (um run D-1)."""
    run_key = "joinads-v4:shadow:2026-10-08:2026-10-14:schedule:2026101509"
    run = {"run_key": run_key, "collector": "n8n_joinads_v2", "collector_version": 4, "mode": "shadow",
           "trigger_kind": "schedule", "window_start": "2026-10-08", "window_end": "2026-10-14",
           "timezone": "America/Sao_Paulo", "status": "completed", "started_at": T.isoformat(),
           "finished_at": (T + timedelta(minutes=2)).isoformat(), "observations_written": len(obs_cen),
           "receipt": {}, "created_at": T.isoformat(), "updated_at": T.isoformat()}
    lotes, observacoes = [], []
    for i, o in enumerate(obs_cen):
        ep = o.atributos["endpoint"]
        bk = f"{run_key}:{ep}:{o.conta}:{i}"
        lotes.append({"batch_key": bk, "run_key": run_key, "endpoint": ep,
                      "grain": "domain_day" if ep == "earnings" else "campaign_adunit_day",
                      "request_meta": {"domain": o.conta}, "http_status": 200, "row_count": 1,
                      "payload": {"data": [{}]}, "collected_at": T.isoformat(), "created_at": T.isoformat()})
        observacoes.append({"observation_key": f"{bk}:0", "run_key": run_key, "batch_key": bk, "endpoint": ep,
                            "grain": lotes[-1]["grain"], "metric_date": DIA.isoformat(), "domain": o.conta,
                            "campaign_id": o.entidade, "custom_key": "utm_campaign" if o.entidade else None,
                            "custom_value": o.entidade, "ad_unit_name": "top" if o.entidade else None,
                            "currency_code": "USD", "revenue_client": o.metricas["revenue_client"],
                            "data_status": o.status.value, "collected_at": T.isoformat(),
                            "created_at": T.isoformat(), "dimensions": {}, "attributes": {}})
    return {"joinads_collection_run": [run], "joinads_raw_batch": lotes, "joinads_observation": observacoes}


@pytest.mark.parametrize("nome", sorted(CENARIOS_RECON))
def test_g8_reconciliacao_por_dominio_dia_sql_igual_python(cluster_pg, nome):
    from test_qualidade_pg_views import aplicar_base, carregar  # mesma base real (DDL das refs) e carga

    obs, esperado = CENARIOS_RECON[nome]
    db = cluster_pg.novo_banco(f"dq_r2_{nome.lower()}")  # tabelas append-only: um banco por cenário
    aplicar_base(cluster_pg, db)
    cluster_pg.psql((DIR_VIEWS / "dq_01_views_qualidade.sql").read_text(encoding="utf-8"), db=db)
    carregar(cluster_pg, db, _tabelas_joinads(obs))
    pre = f"SET dil_qualidade.agora = {_lit(AGORA.isoformat())};\n"
    linhas = json.loads(cluster_pg.psql(pre + "SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM (SELECT dominio, "
                                        "estado, severidade, cobertura FROM dil_qualidade.dq_reconciliacao_joinads) t;",
                                        db=db).splitlines()[-1])
    sql = {r["dominio"]: (r["estado"], r["severidade"], None if r["cobertura"] is None else float(r["cobertura"]))
           for r in linhas}
    assert sql == esperado


# --------------------------------------------------------------------------- dil_obs (G6, G7, G13)

P = b'{"x":1}'
SHA = hashlib.sha256(P).hexdigest()


def _obs_json(base: datetime, entidade: str, **kw) -> str:
    ji, jf = base, base + timedelta(days=1)
    d = {"fonte": "google_ads", "conta": "c1", "entidade_tipo": "campaign", "entidade_id": entidade,
         "grao": ["campaign", "day"], "dimensoes": [], "metrica": "cost", "value_kind": None, "valor": 5,
         "unidade": "micros", "moeda": "BRL", "janela_inicio": ji.isoformat(), "janela_fim": jf.isoformat(),
         "timezone": "America/Sao_Paulo", "observed_at": (ji + timedelta(hours=12)).isoformat(),
         "source_updated_at": None, "available_at": (ji + timedelta(hours=12, minutes=5)).isoformat(),
         "ingested_at": (ji + timedelta(hours=12, minutes=5)).isoformat(), "run_id": "r1", "request_id": None,
         "lote_id": "l1", "payload_sha256": SHA, "payload_ref": "sha256:" + SHA, "schema_version": "v",
         "coletor_nome": "c", "coletor_versao": "1", "status": "partial",
         "motivo": "janela_aberta;cobertura_desconhecida", "cobertura_ppm": None}
    d.update(kw)
    return json.dumps(d)


def _relogio(t: datetime | None) -> str:
    """Fixa o relógio do banco de dil_obs (`dil_obs._agora()`), como a sonda q_g.py da R2: o lote é datado
    pelo relógio do banco, então cada passo da carga roda no seu instante."""
    corpo = "pg_catalog.now()" if t is None else f"{_lit(t.isoformat())}::timestamptz"
    return ("RESET ROLE; CREATE OR REPLACE FUNCTION dil_obs._agora() RETURNS timestamptz LANGUAGE sql STABLE "
            f"PARALLEL SAFE SET search_path = '' AS $$ SELECT {corpo} $$;\nSET ROLE dil_obs_escritor;\n")


def _carga_estados(cluster, db: str, base: datetime) -> None:
    """111: partial superado por observed (só o observed é vigente); 222 missing; 333 invalid; 444 partial vigente."""
    fim = base + timedelta(days=1)
    t_lote = base + timedelta(hours=12)
    t_fech = fim + timedelta(hours=4, minutes=5)
    fechado = dict(observed_at=(fim + timedelta(hours=4)).isoformat(), available_at=t_fech.isoformat(),
                   ingested_at=t_fech.isoformat())
    passos = [
        (t_lote, f"SELECT dil_obs.registrar_run('r1','google_ads','c','1',{_lit(base.isoformat())});"
                 f"SELECT dil_obs.registrar_payload('{SHA}', decode('{P.hex()}','hex'),'application/json');"
                 f"SELECT dil_obs.registrar_lote('l1','r1','{SHA}','v','{{}}'::jsonb,{_lit(t_lote.isoformat())});"),
        (t_lote + timedelta(minutes=6), f"SELECT dil_obs.registrar_observacao($${_obs_json(base, '111')}$$::json);"
                                        f"SELECT dil_obs.registrar_observacao($${_obs_json(base, '444')}$$::json);"),
        (t_fech + timedelta(minutes=1),
         f"SELECT dil_obs.registrar_observacao($${_obs_json(base, '111', status='observed', motivo=None, valor=7, **fechado)}$$::json);"
         f"SELECT dil_obs.registrar_observacao($${_obs_json(base, '222', status='missing', motivo='sem_linha', valor=None, **fechado)}$$::json);"
         f"SELECT dil_obs.registrar_observacao($${_obs_json(base, '333', status='invalid', motivo='texto_no_valor', valor=None, **fechado)}$$::json);"
         "SELECT dil_obs.finalizar_run('r1','succeeded',5,NULL,0,NULL,NULL);"),
    ]
    for t, sql in passos:
        cluster.psql(_relogio(t) + sql, db=db)
    cluster.psql(_relogio(None), db=db)


def _status_vigente(cluster, db) -> dict:
    return {r["status"]: (r["n"], r["severidade"]) for r in _json(
        cluster, db, "SELECT status, sum(n)::int AS n, max(severidade) AS severidade FROM dil_qualidade.dq_obs_status "
        "GROUP BY status", papel="dil_obs_leitor")}


def _banco_dil_obs(cluster, nome: str, dq02_sql: str) -> str:
    db = cluster.novo_banco(nome)
    cluster.aplicar("dil_obs_0001_schema_observacao.sql", db=db)
    cluster.psql(dq02_sql, db=db)
    base = (datetime.now(UTC) - timedelta(days=3)).replace(microsecond=0)
    _carga_estados(cluster, db, base)
    return db


ESPERADO_STATUS = {"observed": (1, "ok"), "missing": (1, "aviso"), "invalid": (1, "alto"), "partial": (1, "info")}


def test_g7_dq_obs_status_conta_estado_vigente(cluster_pg):
    db = _banco_dil_obs(cluster_pg, "dq_r2_status", (DIR_VIEWS / "dq_02_views_dil_obs.sql").read_text(encoding="utf-8"))
    vigente = {r["status"]: r["n"] for r in _json(
        cluster_pg, db, "SELECT status, count(*)::int AS n FROM dil_obs.observacao_as_of(now()) GROUP BY status")}
    assert vigente == {"observed": 1, "missing": 1, "invalid": 1, "partial": 1}  # a base tem 5 versões
    assert _status_vigente(cluster_pg, db) == ESPERADO_STATUS


@pytest.mark.parametrize("mutante,antes,depois", [
    ("G4_invalid_vira_ok", "WHEN o.status IN ('invalid') THEN 'alto'", "WHEN o.status IN ('invalid') THEN 'ok'"),
    ("G7_missing_filtrado", "WHERE o.janela_inicio > st_ag.agora - interval '14 days'",
     "WHERE o.janela_inicio > st_ag.agora - interval '14 days' AND o.status <> 'missing'"),
])
def test_g13_mutantes_de_dq_obs_status_sao_mortos_por_comportamento(cluster_pg, mutante, antes, depois):
    sql = (DIR_VIEWS / "dq_02_views_dil_obs.sql").read_text(encoding="utf-8")
    assert antes in sql, "âncora do mutante sumiu: atualizar o teste junto com a view"
    db = _banco_dil_obs(cluster_pg, f"dq_r2_{mutante.lower()}", sql.replace(antes, depois))
    assert _status_vigente(cluster_pg, db) != ESPERADO_STATUS


def test_g6_dead_letter_sem_linhas_lidas_e_apos_fechamento(cluster_pg):
    db = cluster_pg.novo_banco("dq_r2_dl")
    cluster_pg.aplicar("dil_obs_0001_schema_observacao.sql", db=db)
    cluster_pg.psql((DIR_VIEWS / "dq_02_views_dil_obs.sql").read_text(encoding="utf-8"), db=db)
    ini = _lit((datetime.now(UTC) - timedelta(hours=2)).isoformat())
    cluster_pg.psql("\n".join([
        f"SELECT dil_obs.registrar_run('so_dl','google_ads','c','1',{ini});",
        "SELECT dil_obs.registrar_dead_letter('so_dl',NULL,NULL,'esquema_desconhecido','{}'::jsonb);",
        "SELECT dil_obs.registrar_dead_letter('so_dl',NULL,NULL,'esquema_desconhecido','{}'::jsonb);",
        "SELECT dil_obs.finalizar_run('so_dl','succeeded',0,NULL,0,NULL,NULL);",
        f"SELECT dil_obs.registrar_run('limpo','google_ads','c','1',{ini});",
        "SELECT dil_obs.finalizar_run('limpo','succeeded',0,NULL,0,NULL,NULL);",
        f"SELECT dil_obs.registrar_run('tardio','google_ads','c','1',{ini});",
        "SELECT dil_obs.finalizar_run('tardio','succeeded',0,NULL,0,NULL,NULL);",
        "SELECT dil_obs.registrar_dead_letter('tardio',NULL,NULL,'linha_sem_identidade','{}'::jsonb);",
    ]), db=db, papel="dil_obs_escritor")
    r = {x["run_id"]: x for x in _json(cluster_pg, db, "SELECT run_id, n_lidas, n_dead_letter, dead_letter_registrados, "
                                       "taxa, classe, severidade FROM dil_qualidade.dq_obs_dead_letter",
                                       papel="dil_obs_leitor")}
    assert (r["so_dl"]["taxa"], r["so_dl"]["classe"], r["so_dl"]["severidade"]) == (None, "so_dead_letter", "alto")
    assert (r["tardio"]["classe"], r["tardio"]["severidade"], r["tardio"]["dead_letter_registrados"]) == \
        ("dead_letter_apos_fechamento", "alto", 1)
    assert (r["limpo"]["classe"], r["limpo"]["severidade"]) == ("ok", "ok")
    # Python sobre as mesmas linhas de run_coleta + contagem real: mesma decisão
    linhas = _json(cluster_pg, db, "SELECT r.*, (SELECT count(*) FROM dil_obs.dead_letter d WHERE d.run_id = r.run_id)"
                   "::int AS dead_letter_registrados FROM dil_obs.run_coleta r")
    assert {a.chave: a.regra for a in checar_dead_letter(linhas)} == \
        {"so_dl": "dead_letter_sem_linhas_lidas", "tardio": "dead_letter_apos_fechamento"}


def test_g6_python_taxa_nula_nao_e_ok():
    base = {"fonte": "f", "status": "succeeded", "iniciado_em": "2026-10-16T10:00:00Z",
            "finalizado_em": "2026-10-16T10:05:00Z", "coletor_nome": "c"}
    achados = checar_dead_letter([dict(base, run_id="a", n_lidas=0, n_dead_letter=3),
                                  dict(base, run_id="b", n_lidas=0, n_dead_letter=0),
                                  dict(base, run_id="c", n_lidas=None, n_dead_letter=2)])
    assert {a.chave: (a.regra, a.severidade.value) for a in achados} == {
        "a": ("dead_letter_sem_linhas_lidas", "alto"), "c": ("dead_letter_sem_linhas_lidas", "alto")}


# --------------------------------------------------------------------------- G23 e G17


def test_g23_run_so_de_confirmacoes_nao_e_zero_linhas():
    sla = {"c": SLA("google_ads", "c", "campaign_day", "7 6-23 * * *", timedelta(minutes=30), timedelta(minutes=30))}
    base = {"fonte": "google_ads", "coletor_nome": "c", "coletor_versao": "1", "status": "succeeded",
            "iniciado_em": "2026-10-16T13:00:00Z", "finalizado_em": "2026-10-16T13:05:00Z", "n_lidas": 5,
            "n_noop": 0, "n_dead_letter": 0}
    runs = runs_de_run_coleta([dict(base, run_id="conf", n_inseridas=0, n_confirmadas=5),
                               dict(base, run_id="vazio", n_inseridas=0, n_confirmadas=0, n_lidas=0)])
    assert {r.run_id: r.linhas_escritas for r in runs} == {"conf": 5, "vazio": 0}
    assert [a.chave for a in checar_falha_silenciosa(runs, AGORA, sla)] == ["vazio"]


def test_g17_sem_dominio_real_de_cliente():
    from volc_dil.fundacao.qualidade import sintetico

    assert sintetico.DOMINIO == "site.exemplo"
    proibidos = ("creditoup", "agenciavolc", "GTM-")
    arquivos = [*SRC_QUALIDADE.glob("*.py"), *DIR_VIEWS.glob("*.sql"), *Path(__file__).parent.glob("test_qualidade_*.py")]
    for p in arquivos:
        texto = p.read_text(encoding="utf-8")
        if p.name == Path(__file__).name:
            texto = texto.replace('("creditoup", "agenciavolc", "GTM-")', "")
        for termo in proibidos:
            assert termo not in texto, (p.name, termo)
