"""Simulator Lab — relógios: available_at respeita fim de janela e atrasos declarados."""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache

import pytest

from volc_dil.fundacao.simulador import NOMES, simular

SEED = 20261016
TAM = {"escala_10x": (20, 5)}


@lru_cache(maxsize=None)
def _sim(nome: str):
    n, d = TAM.get(nome, (6, 10))
    return simular(nome, SEED, n_campanhas=n, n_dias=d)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


@pytest.mark.parametrize("nome", NOMES)
def test_ordem_dos_relogios_e_janela(nome):
    regs = _sim(nome).leituras.registros
    assert regs, nome
    anterior = ""
    for r in regs:
        assert r.observed_at <= r.available_at <= r.ingested_at, r.obs_id
        assert r.janela_inicio < r.janela_fim
        assert r.observed_at >= r.janela_inicio
        assert r.available_at >= anterior  # emitidos em ordem de conhecimento
        anterior = r.available_at
        if r.available_at < r.janela_fim:
            # só leitura intradiária pode chegar antes do fim da janela, e nunca como valor fechado
            assert r.tipo_leitura == "intradia", (nome, r.obs_id, r.tipo_leitura)
            assert r.status in {"partial", "unavailable", "missing", "invalid"}, (nome, r.obs_id, r.status)
        else:
            assert r.status != "partial", (nome, r.obs_id)
        if r.tipo_leitura != "intradia":
            assert r.available_at >= r.janela_fim
        if r.status == "late":
            assert r.available_previsto is not None and r.available_previsto < r.available_at
        if r.tipo_leitura == "intradia":
            assert r.cobertura_ate is not None and r.cobertura_ate <= r.observed_at


@pytest.mark.parametrize("nome", ["estavel", "atraso_receita_longo", "restatement_custo"])
def test_atrasos_declarados_respeitados(nome):
    sim = _sim(nome)
    po = sim.espec.observador
    minimo = {("google_ads", "d1"): po.gads_d1_hora,
              ("google_ads", "backfill"): 24 * (po.gads_backfill_dias - 1) + po.gads_backfill_hora,
              ("joinads", "d1"): po.join_d1_hora, ("site_analytics", "d1"): po.site_d1_hora}
    for r in sim.leituras.registros:
        h = minimo.get((r.fonte, r.tipo_leitura))
        if h is not None and r.entidade_tipo != "account":
            atraso = _dt(r.available_at) - _dt(r.janela_fim)
            assert atraso >= timedelta(hours=h), (nome, r.obs_id, atraso)
        if r.fonte == "joinads" and r.tipo_leitura == "releitura":
            assert _dt(r.available_at) - _dt(r.janela_fim) >= timedelta(hours=24 + po.join_d1_hora)


def test_atraso_receita_longo_sem_receita_antes_de_d1_10h():
    sim = _sim("atraso_receita_longo")
    rec = [r for r in sim.leituras.registros if r.fonte == "joinads" and r.metrica == "revenue" and r.valor is not None]
    assert rec
    assert min(_dt(r.available_at) - _dt(r.janela_fim) for r in rec) >= timedelta(hours=10)
    finais = [r for r in rec if r.maturidade == "final"]
    assert min(_dt(r.available_at) - _dt(r.janela_fim) for r in finais) >= timedelta(days=5)


def test_intradiaria_google_e_exatamente_a_verdade_coberta():
    sim = _sim("estavel")
    n = 0
    for r in sim.leituras.registros:
        if r.fonte == "google_ads" and r.tipo_leitura == "intradia" and r.status == "partial" and r.entidade_tipo == "campaign":
            g = sim.leituras.gabarito[r.obs_id]
            assert r.valor == g.valor_verdade_cobertura
            n += 1
    assert n > 0
