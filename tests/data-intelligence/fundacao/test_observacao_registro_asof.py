"""Registro append-only, idempotência, restatement, as_of/latest e agregação sem zero inventado."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from volc_dil.contracts import EstadoMedida, Snapshot, VersaoAmbigua
from volc_dil.contracts.vocab import Cobertura
from volc_dil.fundacao.observacao import (
    ConflitoIdempotencia,
    Registro,
    ResultadoRegistro,
    StatusObservacao,
    agregar_observacoes,
    as_of,
    latest,
    para_contrato_economico,
)

H = timedelta(hours=1)


def _t(obs, horas: float):
    return obs().janela_inicio + timedelta(hours=horas)


def _versao(obs, horas: float, *, payload: bytes, **kw):
    t = _t(obs, horas)
    kw.setdefault("observed_at", min(t, _t(obs, 28)) if horas >= 28 else _t(obs, 24))
    return obs(payload=payload, available_at=t, ingested_at=t + timedelta(minutes=1), **kw)


# ---------------------------------------------------------------- idempotência
def test_reinsercao_e_noop_e_contagem_igual(obs):
    r = Registro()
    o = obs()
    assert r.registrar(o) is ResultadoRegistro.INSERIDO
    for _ in range(5):
        assert r.registrar(o) is ResultadoRegistro.NOOP
    assert len(r) == 1


def test_releitura_mesmo_payload_em_outra_execucao_e_noop(obs):
    r = Registro()
    a = _versao(obs, 28, payload=b"P1")
    b = _versao(obs, 34, payload=b"P1", run_id="run-2", lote_id="lote-2")  # cron seguinte, mesmo dado
    assert r.registrar_todas([a, b]) == [ResultadoRegistro.INSERIDO, ResultadoRegistro.NOOP]
    assert len(r) == 1
    # conhecimento continua datado da PRIMEIRA leitura
    assert r.as_of(_t(obs, 30))[a.chave_natural].available_at == a.available_at


def test_payload_diferente_mesma_janela_e_nova_versao_nunca_update(obs):
    r = Registro()
    v1 = _versao(obs, 28, payload=b"P1", valor=5_000_000)
    v2 = _versao(obs, 100, payload=b"P2", valor=5_400_000)  # restatement D+4
    assert r.registrar_todas([v1, v2]) == [ResultadoRegistro.INSERIDO, ResultadoRegistro.INSERIDO]
    hist = r.historico(v1.chave_natural)
    assert [h.observacao.valor for h in hist] == [5_000_000, 5_400_000]
    assert r.versoes[0].observacao is v1  # a primeira versão não foi tocada


def test_conflito_mesma_leitura_conteudo_diferente(obs):
    r = Registro([obs(valor=5_000_000)])
    with pytest.raises(ConflitoIdempotencia):
        r.registrar(obs(valor=6_000_000))  # mesmo payload/coletor, número diferente: coletor não determinístico


def test_versao_ambigua_mesmo_available_at(obs):
    r = Registro([obs(payload=b"P1")])
    with pytest.raises(VersaoAmbigua):
        r.registrar(obs(payload=b"P2", valor=7_000_000))


def test_aba_missing_observed_missing(obs):
    """A→B→A: a fonte volta a não ter a linha (ex.: JoinAds retrata). A volta é uma leitura nova (outro observed_at)."""
    r = Registro()
    falta = dict(status="missing", valor=None, moeda=None, motivo="linha_ausente_na_resposta")
    a1 = _versao(obs, 28, payload=b"[]", observed_at=_t(obs, 28), **falta)
    b = _versao(obs, 34, payload=b"P1", observed_at=_t(obs, 34))
    a2 = _versao(obs, 40, payload=b"[]", run_id="run-3", lote_id="lote-3", observed_at=_t(obs, 40), **falta)
    res = r.registrar_todas([a1, b, a2, a2])
    assert res == [ResultadoRegistro.INSERIDO, ResultadoRegistro.INSERIDO, ResultadoRegistro.INSERIDO, ResultadoRegistro.NOOP]
    assert len(r) == 3
    assert r.as_of(_t(obs, 36))[b.chave_natural].status is StatusObservacao.OBSERVED
    assert r.as_of(_t(obs, 41))[b.chave_natural].status is StatusObservacao.MISSING


def test_reentrega_fora_de_ordem_nunca_antecipa_conhecimento(obs):
    r = Registro()
    tarde = _versao(obs, 40, payload=b"P1")
    cedo = _versao(obs, 30, payload=b"P1")  # mesma leitura, available_at anterior, chega depois
    assert r.registrar_todas([tarde, cedo]) == [ResultadoRegistro.INSERIDO, ResultadoRegistro.NOOP]
    assert r.as_of(_t(obs, 35)) == {}  # conservador: não passa a "saber" antes


# ---------------------------------------------------------------- as_of / latest
def test_reprocessamento_tardio_aparece_depois_de_T_e_nao_antes(obs):
    v1 = _versao(obs, 28, payload=b"P1", valor=5_000_000)
    v2 = _versao(obs, 100, payload=b"P2", valor=5_400_000, coletor=obs().coletor.__class__("coleta_canonica_google_ads", "1.1.0"))
    hist = [v1, v2]
    nat = v1.chave_natural
    assert as_of(hist, _t(obs, 27)) == {}
    assert as_of(hist, _t(obs, 99))[nat].valor == 5_000_000
    assert as_of(hist, _t(obs, 100))[nat].valor == 5_400_000
    assert latest(hist, _t(obs, 1000))[nat] is v2
    assert len(hist) == 2  # latest não destrói histórico


def test_as_of_preserva_status_e_independe_da_ordem(obs):
    a = obs(entidade_id="1", status="missing", valor=None, motivo="linha_ausente_na_resposta")
    b = obs(entidade_id="2", status="unavailable", valor=None, motivo="HTTP 503")
    c = obs(entidade_id="3", status="late", valor=None, motivo="D-1 não publicado")
    d = obs(entidade_id="4", status="zero_confirmed", valor=0)
    t = _t(obs, 200)
    e1 = as_of([a, b, c, d], t)
    e2 = as_of([d, c, b, a, a], t)
    assert dict(e1) == dict(e2)
    assert sorted(o.status.value for o in e1.values()) == ["late", "missing", "unavailable", "zero_confirmed"]


def test_as_of_exige_timezone(obs):
    with pytest.raises(Exception, match="timezone"):
        as_of([obs()], datetime(2026, 10, 20))


def test_as_of_detecta_ambiguidade_em_dado_bruto(obs):
    with pytest.raises(VersaoAmbigua):
        as_of([obs(payload=b"P1"), obs(payload=b"P2", valor=1)], _t(obs, 200))
    with pytest.raises(ConflitoIdempotencia):
        as_of([obs(valor=1), obs(valor=2)], _t(obs, 200))


# ---------------------------------------------------------------- null != 0 e ausência != falha
def test_agregacao_nao_converte_missing_em_zero(obs):
    obsv = [obs(entidade_id="1", valor=5_000_000),
            obs(entidade_id="2", status="missing", valor=None, motivo="linha_ausente_na_resposta"),
            obs(entidade_id="3", status="unavailable", valor=None, motivo="HTTP 503")]
    ag = agregar_observacoes(obsv)
    assert ag.valor is None and not ag.tem_valor
    assert ag.agregado.estado is EstadoMedida.FALHA  # pior causa vence (herdado)
    assert dict(ag.por_status) == {"missing": 1, "observed": 1, "unavailable": 1}
    parcial = agregar_observacoes(obsv, aceitar_parcial=True)
    assert parcial.valor.micros == 5_000_000 and parcial.agregado.cobertura is Cobertura.PARCIAL
    so_falta = agregar_observacoes([obsv[1]])
    assert so_falta.valor is None and so_falta.agregado.estado is EstadoMedida.AUSENTE
    assert agregar_observacoes([]).valor is None


def test_mapeamento_para_contrato_herdado_distingue_causas(obs):
    casos = {
        "observed": (dict(), EstadoMedida.MEDIDO, Cobertura.COMPLETA),
        "zero_confirmed": (dict(valor=0), EstadoMedida.ZERO_CONFIRMADO, Cobertura.COMPLETA),
        "missing": (dict(valor=None, motivo="m"), EstadoMedida.AUSENTE, Cobertura.DESCONHECIDA),
        "late": (dict(valor=None, motivo="m"), EstadoMedida.NAO_COLETADO, Cobertura.DESCONHECIDA),
        "unavailable": (dict(valor=None, motivo="m"), EstadoMedida.FALHA, Cobertura.DESCONHECIDA),
        "unsupported": (dict(valor=None, motivo="m"), EstadoMedida.NAO_APLICAVEL, Cobertura.DESCONHECIDA),
        "invalid": (dict(valor=None, motivo="m"), EstadoMedida.FALHA, Cobertura.DESCONHECIDA),
    }
    for st, (kw, estado, cob) in casos.items():
        e = para_contrato_economico(obs(status=st, **kw))
        assert (e.estado, e.cobertura) == (estado, cob), st
        assert e.disponivel_em == obs().available_at and e.coleta_id == "run-1"
        if e.valor is None:
            assert st in e.motivo
    d = obs().janela_inicio
    p = para_contrato_economico(obs(status="partial", motivo="janela_aberta", cobertura_ppm=5,
                                    observed_at=d + H, available_at=d + H, ingested_at=d + H))
    assert (p.estado, p.cobertura, p.valor.micros) == (EstadoMedida.MEDIDO, Cobertura.PARCIAL, 5_000_000)


def test_snapshot_herdado_sobre_observacoes_canonicas(obs):
    v1 = _versao(obs, 28, payload=b"P1", valor=5_000_000)
    v2 = _versao(obs, 100, payload=b"P2", valor=5_400_000)
    snap = Snapshot.construir([para_contrato_economico(o) for o in (v1, v2)], _t(obs, 50))
    assert snap.manifesto["n_incluidas"] == 1 and snap.manifesto["n_futuras_excluidas"] == 1
    assert snap.observacoes[0].valor.micros == 5_000_000


# ---------------------------------------------------------------- propriedade (seed fixa)
def _gerar_sequencia(obs, rng: random.Random, n: int):
    """Leituras aleatórias de poucas chaves e poucos payloads, chegando em ordem de available_at."""
    ents, metricas = ["1", "2", "3"], ["cost", "clicks"]
    eventos = []
    horas = sorted(rng.sample(range(25, 400), n))
    for h in horas:
        ent, met = rng.choice(ents), rng.choice(metricas)
        p = rng.choice([b"A", b"B", b"C", b"[]", b"ERR"])
        status = {b"[]": "missing", b"ERR": "unavailable", b"B": "zero_confirmed"}.get(p, "observed")
        valor = {b"A": 10, b"B": 0, b"C": 30}.get(p)
        kw = dict(entidade_id=ent, status=status, valor=valor, motivo=None if valor is not None else status)
        if met == "clicks":
            kw.update(metrica="clicks", unidade="contagem", moeda=None)
        elif valor is not None:
            kw["valor"] = valor * 1_000_000
        # o conteúdo de uma leitura é função do (payload, entidade, métrica): determinístico por construção
        kw["payload"] = p + ent.encode() + met.encode()
        # D1: observed_at varia e nem sempre acompanha a chegada (leitura antiga que chega atrasada)
        kw["observed_at"] = _t(obs, rng.randint(24, h))
        eventos.append(_versao(obs, h, run_id=f"run-{h}", lote_id=f"lote-{h}", **kw))
        if rng.random() < 0.3:  # retry imediato da mesma leitura
            eventos.append(eventos[-1])
    return eventos


def _conteudo(estado):
    # D2': a linha vigente pode ser outra leitura com o MESMO estado (a releitura igual vira confirmação)
    return {k: (o.status.value, o.valor) for k, o in estado.items()}


def test_propriedade_idempotencia_e_as_of(obs):
    rng = random.Random(20261016)
    caminhos = {x: 0 for x in ResultadoRegistro}
    for _ in range(150):
        seq = _gerar_sequencia(obs, rng, rng.randint(1, 25))
        r = Registro()
        for x in r.registrar_todas(seq):
            caminhos[x] += 1
        n = len(r)
        assert all(x is ResultadoRegistro.NOOP for x in r.registrar_todas(seq)), "reaplicar a sequência não é no-op"
        assert len(r) == n
        cortes = [_t(obs, h) for h in rng.sample(range(20, 420), 6)] + [_t(obs, 10_000)]
        for t in cortes:
            bruto, reg = as_of(seq, t), r.as_of(t)
            assert _conteudo(bruto) == _conteudo(reg), "as_of do registro diverge do as_of do dado bruto"
            assert all(o.available_at <= t for o in reg.values()), "as_of olhou o futuro"
            embaralhado = list(seq)
            rng.shuffle(embaralhado)
            assert _conteudo(as_of(embaralhado, t)) == _conteudo(bruto), "as_of depende da ordem"
        fim = latest(r.observacoes, _t(obs, 10_000))
        for o in fim.values():
            assert (o.valor is None) == (o.status in (StatusObservacao.MISSING, StatusObservacao.UNAVAILABLE))
    assert all(v > 0 for v in caminhos.values()), f"gerador não exercitou todos os caminhos: {caminhos}"


# ---------------------------------------------------------------- R1
def test_r1_m7_reentrega_no_instante_de_outra_versao_e_noop(obs):
    """k1@t1, k2@t2, reentrega de k1 com available_at = t2: é a MESMA leitura (mesmo observed_at) → no-op, não ambígua."""
    r = Registro()
    k1 = _versao(obs, 30, payload=b"K1")
    k2 = _versao(obs, 40, payload=b"K2", valor=7_000_000)
    k1_tarde = _versao(obs, 40, payload=b"K1", run_id="run-x", lote_id="lote-x")
    assert r.registrar_todas([k1, k2, k1_tarde]) == [ResultadoRegistro.INSERIDO, ResultadoRegistro.INSERIDO, ResultadoRegistro.NOOP]


def test_r1_f16_partial_fora_do_total_por_padrao(obs):
    d = obs().janela_inicio
    fechado = obs(entidade_id="1")
    aberto = obs(entidade_id="2", status="partial", valor=1_000_000, motivo="janela_aberta", cobertura_ppm=10,
                 observed_at=d + H, available_at=d + H, ingested_at=d + H)
    desconhecido = obs(entidade_id="3", status="partial", valor=2_000_000, motivo="janela_aberta;cobertura_desconhecida",
                       observed_at=d + H, available_at=d + H, ingested_at=d + H)
    ag = agregar_observacoes([fechado, aberto, desconhecido])
    assert ag.valor is None and ag.agregado.estado is EstadoMedida.NAO_COLETADO  # 1% de cobertura não vira `medido`
    assert (ag.cobertura_minima_ppm, ag.n_cobertura_desconhecida) == (10, 1)
    opt = agregar_observacoes([fechado, aberto], aceitar_parcial=True)
    assert opt.valor.micros == 6_000_000 and opt.agregado.cobertura is Cobertura.PARCIAL
