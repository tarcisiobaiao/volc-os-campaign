"""Item 5: contrato CANDIDATO de cotação USD/BRL e conversão única, em PostgreSQL descartável (nunca produção).

Prova: sem cotação não há fallback (nao_convertido); vigência e as_of (o que se sabia antes de uma correção não muda);
correção por linha nova (supersedes), nunca UPDATE; conversão half-even em micros, idempotente e append-only;
recusa converter valor já na moeda alvo e moeda original não provada; rollback recusado com histórico.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MIG = Path(__file__).resolve().parents[3] / "experiments/data-intelligence-lab/migrations_candidatas"


@pytest.fixture
def db(cluster_pg):
    nome = cluster_pg.novo_banco("item5_fx")
    cluster_pg.psql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role; END IF;"
                    " IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF;"
                    " IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF; END $$;", db=nome)
    cluster_pg.aplicar("item5_0002_cotacao_usd_brl.sql", db=nome)
    return nome


def _taxa(pg, db, rate, de, ate="NULL", rec="2026-10-17T12:00:00Z", sup="NULL"):
    return pg.psql(f"INSERT INTO fx_rate_observation (base_currency, quote_currency, rate, rate_kind, source, source_ref, valid_from,"
                   f" valid_to, recorded_at, recorded_by, supersedes) VALUES ('USD','BRL',{rate},'ptax_venda','bcb_ptax','ref-{rate}',"
                   f"'{de}',{ate},'{rec}','teste',{sup}) RETURNING fx_id;", db=db).splitlines()[-1]


def _conv(pg, db, chave, micros, dia="2026-10-16", st="attested", moeda="USD", as_of="2026-10-17T20:00:00Z"):
    return json.loads(pg.psql(f"SELECT volc_convert_revenue('{chave}', '{dia}', {micros}, '{moeda}', '{st}', 'BRL', 'ptax_venda',"
                              f" '{as_of}');", db=db).splitlines()[-1])


def test_sem_cotacao_nao_ha_fallback(cluster_pg, db):
    assert _conv(cluster_pg, db, "k1", 1_000_000) == {"status": "nao_convertido", "motivo": "cotacao_vigente_nao_provada"}
    assert cluster_pg.psql("SELECT count(*) FROM revenue_conversion;", db=db) == "0"


def test_vigencia_as_of_e_correcao_por_linha_nova(cluster_pg, db):
    a = _taxa(cluster_pg, db, 5.4, "2026-10-16", "'2026-10-17'", rec="2026-10-16T16:00:00Z")
    _taxa(cluster_pg, db, 5.41, "2026-10-16", "'2026-10-17'", rec="2026-10-17T15:00:00Z", sup=f"'{a}'")
    antes = _conv(cluster_pg, db, "k2", 1_000_000, as_of="2026-10-17T10:00:00Z")
    depois = _conv(cluster_pg, db, "k3", 1_000_000, as_of="2026-10-17T20:00:00Z")
    assert (float(antes["rate"]), antes["revenue_converted_micros"]) == (5.4, 5_400_000)
    assert (float(depois["rate"]), depois["revenue_converted_micros"]) == (5.41, 5_410_000)
    # a conversão antiga não é reescrita pela correção
    assert cluster_pg.psql("SELECT revenue_converted_micros FROM revenue_conversion WHERE observation_key='k2';", db=db) == "5400000"
    assert "append-only" in cluster_pg.falha("UPDATE fx_rate_observation SET rate = 6;", db=db)
    assert "append-only" in cluster_pg.falha("DELETE FROM revenue_conversion;", db=db)
    # fora da vigência: sem taxa
    assert _conv(cluster_pg, db, "k4", 1, dia="2026-10-18")["motivo"] == "cotacao_vigente_nao_provada"


def test_half_even_idempotencia_e_recusas(cluster_pg, db):
    _taxa(cluster_pg, db, 2.5, "2026-10-01")
    assert _conv(cluster_pg, db, "k5", 1)["revenue_converted_micros"] == 2      # 2,5 → 2 (par)
    assert _conv(cluster_pg, db, "k6", 3)["revenue_converted_micros"] == 8      # 7,5 → 8 (par)
    assert _conv(cluster_pg, db, "k5", 1)["idempotente"] is True
    assert cluster_pg.psql("SELECT count(*) FROM revenue_conversion WHERE observation_key='k5';", db=db) == "1"
    assert "já está na moeda alvo" in cluster_pg.falha(
        "SELECT volc_convert_revenue('k7','2026-10-16',1,'BRL','observed','BRL','ptax_venda',now());", db=db)
    assert _conv(cluster_pg, db, "k8", 1, st="unproven")["motivo"] == "moeda_original_nao_provada"


def test_rollback_recusado_com_historico(cluster_pg, db):
    _taxa(cluster_pg, db, 5.4, "2026-10-16")
    assert "rollback recusado" in cluster_pg.falha((MIG / "item5_0002_cotacao_usd_brl.down.sql").read_text(), db=db)
    limpo = cluster_pg.novo_banco("item5_fx_rb")
    cluster_pg.psql("SELECT 1;", db=limpo)
    cluster_pg.aplicar("item5_0002_cotacao_usd_brl.sql", db=limpo)
    cluster_pg.aplicar("item5_0002_cotacao_usd_brl.down.sql", db=limpo)
    assert cluster_pg.psql("SELECT to_regclass('public.fx_rate_observation') IS NULL;", db=limpo) == "t"
