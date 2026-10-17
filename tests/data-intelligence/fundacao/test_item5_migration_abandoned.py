"""Item 5: migration CANDIDATA running → abandoned do ledger Google Ads, em PostgreSQL descartável.

Base = reconstrução literal do catálogo de produção (item5_base_producao_reconstruida.sql), nunca produção.
Prova: idempotência, limite de 60 min pelo relógio do banco, recusa com execução n8n ativa, job longo com lote recente
não é órfão, conclusão tardia não desfaz o abandono (fica em receipt.late_activity), só a função marca abandoned,
evento append-only, permissões e rollback (recusado quando já há abandono; limpo quando não há).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

UP, DOWN, BASE = ("item5_0001_google_ads_run_abandoned.sql", "item5_0001_google_ads_run_abandoned.down.sql",
                  "item5_base_producao_reconstruida.sql")


def _run(pg, db, chave, inicio_min, lote_min=None, status="running"):
    fim = "now()" if status != "running" else "NULL"
    rid = pg.psql(f"""INSERT INTO google_ads_collection_run (idempotency_key, collector, collector_version, api_version, mode,
        trigger_kind, status, started_at, finished_at) VALUES ('{chave}', 'n8n-google-ads-terms-keywords', 1, 'v25', 'shadow',
        'schedule', '{status}', now() - interval '{inicio_min} minutes', {fim}) RETURNING run_id;""", db=db).splitlines()[-1]
    if lote_min is not None:
        pg.psql(f"""INSERT INTO google_ads_raw_batch (run_id, batch_key, customer_id, resource_type, grain, collected_at, row_count,
            payload, payload_sha256, created_at) VALUES ('{rid}', 'b', '1', 'search_term', 'search_term_day', now(), 1, '{{}}', 'x',
            now() - interval '{lote_min} minutes');""", db=db)
    return rid


def _abandonar(pg, db, rid, n8n="success", limite=60, papel=None):
    return json.loads(pg.psql(f"SELECT volc_abandon_google_ads_run('{rid}', '{n8n}', 'reaper-teste', '{{\"ex\":\"1\"}}', {limite});",
                              db=db, papel=papel).splitlines()[-1])


@pytest.fixture
def db(cluster_pg):
    nome = cluster_pg.novo_banco("item5_abandoned")
    cluster_pg.aplicar(BASE, db=nome)
    cluster_pg.aplicar(UP, db=nome)
    return nome


def test_abandona_orfao_uma_vez_e_e_idempotente(cluster_pg, db):
    rid = _run(cluster_pg, db, "orfao", inicio_min=600, lote_min=576)
    r = _abandonar(cluster_pg, db, rid)
    assert r["acao"] == "abandonado" and r["minutos_sem_atividade"] >= 575
    linha = cluster_pg.psql(f"SELECT status, finished_at IS NOT NULL, error_class FROM google_ads_collection_run WHERE run_id='{rid}';", db=db)
    assert linha == "abandoned|t|abandoned"
    assert _abandonar(cluster_pg, db, rid)["acao"] == "ja_abandonado"
    assert cluster_pg.psql("SELECT count(*) FROM google_ads_run_abandonment;", db=db) == "1"


def test_job_longo_com_lote_recente_nao_e_orfao(cluster_pg, db):
    rid = _run(cluster_pg, db, "longo", inicio_min=300, lote_min=10)
    assert _abandonar(cluster_pg, db, rid)["acao"] == "nenhuma:atividade_recente"
    assert cluster_pg.psql(f"SELECT status FROM google_ads_collection_run WHERE run_id='{rid}';", db=db) == "running"


def test_recusa_execucao_n8n_ativa_e_limite_curto(cluster_pg, db):
    rid = _run(cluster_pg, db, "ativo", inicio_min=600)
    assert "execução n8n ativa" in cluster_pg.falha(f"SELECT volc_abandon_google_ads_run('{rid}', 'running', 'r');", db=db)
    assert "limite mínimo" in cluster_pg.falha(f"SELECT volc_abandon_google_ads_run('{rid}', 'success', 'r', '{{}}', 30);", db=db)
    assert cluster_pg.psql(f"SELECT status FROM google_ads_collection_run WHERE run_id='{rid}';", db=db) == "running"


def test_run_finalizado_nao_muda(cluster_pg, db):
    rid = _run(cluster_pg, db, "ok", inicio_min=600, status="completed")
    assert _abandonar(cluster_pg, db, rid)["acao"] == "nenhuma:run_ja_finalizado"


def test_conclusao_tardia_nao_desfaz_abandono(cluster_pg, db):
    rid = _run(cluster_pg, db, "wf:exec", inicio_min=600, lote_min=590)
    _abandonar(cluster_pg, db, rid)
    doc = {"run_key": "wf:exec", "collector": "n8n-google-ads-terms-keywords", "collector_version": 1, "api_version": "v25",
           "mode": "shadow", "trigger_kind": "schedule", "status": "completed", "started_at": "2026-10-15T11:46:00Z",
           "finished_at": "2026-10-18T10:00:00Z", "receipt": {"finalized_by": "n8n-loop-complete"}}
    cluster_pg.psql(f"SELECT volc_finish_google_ads_run('{json.dumps(doc)}'::jsonb);", db=db)
    st, tardia = cluster_pg.psql(f"SELECT status, receipt->'late_activity' FROM google_ads_collection_run WHERE run_id='{rid}';", db=db).split("|")
    assert st == "abandoned"
    assert json.loads(tardia)[0]["status_pedido"] == "completed"


def test_so_a_funcao_marca_abandoned_e_evento_e_append_only(cluster_pg, db):
    rid = _run(cluster_pg, db, "direto", inicio_min=600)
    assert "só pela função" in cluster_pg.falha(
        f"UPDATE google_ads_collection_run SET status='abandoned', finished_at=now() WHERE run_id='{rid}';", db=db)
    _abandonar(cluster_pg, db, rid)
    assert "append-only" in cluster_pg.falha("UPDATE google_ads_run_abandonment SET decided_by='x';", db=db)
    assert "append-only" in cluster_pg.falha("DELETE FROM google_ads_run_abandonment;", db=db)


def test_permissoes(cluster_pg, db):
    rid = _run(cluster_pg, db, "perm", inicio_min=600)
    assert "permission denied" in cluster_pg.falha(f"SELECT volc_abandon_google_ads_run('{rid}', 'success', 'r');", db=db, papel="anon")
    assert _abandonar(cluster_pg, db, rid, papel="service_role")["acao"] == "abandonado"


def test_rollback_recusa_com_abandono_e_limpa_sem(cluster_pg, db):
    rid = _run(cluster_pg, db, "rb", inicio_min=600)
    _abandonar(cluster_pg, db, rid)
    assert "rollback recusado" in cluster_pg.falha(_ler(DOWN), db=db)
    limpo = cluster_pg.novo_banco("item5_abandoned_rb")
    cluster_pg.aplicar(BASE, db=limpo)
    cluster_pg.aplicar(UP, db=limpo)
    cluster_pg.aplicar(DOWN, db=limpo)
    assert cluster_pg.psql("SELECT to_regclass('public.google_ads_run_abandonment') IS NULL, "
                           "to_regprocedure('public.volc_abandon_google_ads_run(uuid,text,text,jsonb,integer)') IS NULL;", db=limpo) == "t|t"
    assert "google_ads_run_status" in cluster_pg.falha(
        "INSERT INTO google_ads_collection_run (idempotency_key, collector, collector_version, api_version, mode, trigger_kind,"
        " status, started_at, finished_at) VALUES ('x','c',1,'v25','shadow','schedule','abandoned', now(), now());", db=limpo)


def _ler(arquivo):
    return (Path(__file__).resolve().parents[3] / "experiments/data-intelligence-lab/migrations_candidatas" / arquivo).read_text(encoding="utf-8")
