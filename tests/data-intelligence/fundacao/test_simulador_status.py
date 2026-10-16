"""Simulator Lab — coerência de status, campos do contrato, runs e adaptador para o contrato herdado."""
from __future__ import annotations

from functools import lru_cache

import pytest

from volc_dil.contracts import ContratoViolado, EstadoMedida, Observacao
from volc_dil.fundacao.simulador import (
    CAMPOS_CONTRATO,
    NOMES,
    STATUS,
    STATUS_COM_VALOR,
    STATUS_SEM_VALOR,
    para_observacao_contrato,
    simular,
)

SEED = 20261016
TAM = {"escala_10x": (20, 5)}


@lru_cache(maxsize=None)
def _sim(nome: str):
    n, d = TAM.get(nome, (6, 10))
    return simular(nome, SEED, n_campanhas=n, n_dias=d)


def test_campos_do_contrato_exatos():
    assert CAMPOS_CONTRATO == (
        "fonte", "conta", "entidade", "grao", "metrica", "valor", "moeda", "janela_inicio", "janela_fim",
        "timezone", "observed_at", "available_at", "ingested_at", "run_id", "payload_sha256", "status", "motivo")
    assert set(STATUS) == {"observed", "zero_confirmed", "missing", "late", "unavailable", "unsupported", "invalid",
                           "partial"}
    r = _sim("estavel").leituras.registros[0]
    assert tuple(r.contrato()) == CAMPOS_CONTRATO


@pytest.mark.parametrize("nome", NOMES)
def test_status_coerentes(nome):
    sim = _sim(nome)
    vistos = set()
    for r in sim.leituras.registros:
        vistos.add(r.status)
        assert r.status in STATUS
        if r.status in STATUS_SEM_VALOR:
            assert r.valor is None and r.motivo, (nome, r.obs_id)  # null ≠ 0 e todo null tem motivo
        else:
            assert r.status in STATUS_COM_VALOR
            assert isinstance(r.valor, int) and not isinstance(r.valor, bool) and r.valor >= 0, (nome, r.obs_id)
        if r.status == "zero_confirmed":
            assert r.valor == 0
        if r.unidade == "micros":
            assert r.metrica in ("cost", "revenue")
            assert r.moeda in ("BRL", "USD") or (r.valor is None and r.status == "unsupported")
        else:
            assert r.unidade == "contagem" and r.moeda is None
        assert r.timezone == "America/Sao_Paulo"
        assert r.metrica == "cost" and r.moeda in (None, "BRL") or r.metrica != "cost"
        assert len(r.payload_sha256) == 64 and r.run_id.startswith("run-")
        assert r.natureza == "sintetico"
    assert {"partial", "observed"} <= vistos
    assert "unsupported" in vistos  # dimensão não suportada aparece em todo cenário (dispositivo na JoinAds)


@pytest.mark.parametrize("nome", ["estavel", "fonte_fora_do_ar", "execucao_presa"])
def test_livro_de_execucoes(nome):
    L = _sim(nome).leituras
    runs = {x["run_id"]: x for x in L.execucoes}
    for x in L.execucoes:
        assert x["status"] in ("completed", "failed", "running")
        if x["status"] == "running":
            assert x["concluido_em"] is None and x["n_registros"] == 0
    contagem: dict[str, int] = {}
    for r in L.registros:
        assert r.run_id in runs, r.obs_id  # todo registro tem run no livro
        contagem[r.run_id] = contagem.get(r.run_id, 0) + 1
    for rid, x in runs.items():
        assert contagem.get(rid, 0) == x["n_registros"]


def test_duplicata_e_reingestao_identica():
    L = _sim("estavel").leituras
    dups = L.com_armadilha("duplicata")
    assert dups
    por_leitura = {}
    for r in L.registros:
        por_leitura.setdefault(r.leitura_id, []).append(r)
    for d in dups:
        irmaos = por_leitura[d.leitura_id]
        assert len(irmaos) == 2
        a, b = irmaos
        assert (a.valor, a.payload_sha256, a.run_id, a.available_at) == (b.valor, b.payload_sha256, b.run_id, b.available_at)
        assert a.ingested_at != b.ingested_at


@pytest.mark.parametrize("nome", ["estavel", "zero_falso", "identidade_trocada", "moeda_misturada", "fonte_fora_do_ar",
                                  "sensor_sem_campanha", "zero_sintetizado_coletor", "gatilho_legado_joinads",
                                  "vazamento_tentado"])
def test_adaptador_para_contrato_herdado(nome):
    n_ok = 0
    for r in _sim(nome).leituras.registros:
        try:
            o = para_observacao_contrato(r)
        except ContratoViolado as exc:  # pragma: no cover - mensagem útil em caso de falha
            raise AssertionError(f"{nome} {r.obs_id} {r.status} {r.metrica}: {exc}") from exc
        if o is None:
            assert r.metrica == "pageviews"
            continue
        assert isinstance(o, Observacao)
        assert (o.valor is None) == (r.valor is None)
        if r.status == "zero_confirmed":
            assert o.estado is EstadoMedida.ZERO_CONFIRMADO
        n_ok += 1
    assert n_ok > 0
