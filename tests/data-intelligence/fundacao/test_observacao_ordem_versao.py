"""D1–D3 (achados da thread D): ordem de versão por observed_at, releitura D0 sem conflito, ambiguidade sem ordem."""
from __future__ import annotations

import hashlib
import itertools
import json
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import pytest

from volc_dil.contracts import VersaoAmbigua
from volc_dil.fundacao.observacao import (
    Coletor,
    ConflitoIdempotencia,
    ContextoLeitura,
    ObservacaoInvalida,
    PayloadBruto,
    Registro,
    ResultadoRegistro,
    StatusObservacao,
    adaptar_google_ads_v21,
    as_of,
    normalizar,
    vigente_entre,
)

BRT = timezone(timedelta(hours=-3))


def _t(obs, h):
    return obs().janela_inicio + timedelta(hours=h)


def _leitura(obs, *, observed_h, available_h, payload, **kw):
    return obs(payload=payload, observed_at=_t(obs, observed_h), available_at=_t(obs, available_h),
               ingested_at=_t(obs, available_h), **kw)


# ============================================================== D1: ordem de versão
def test_d1_leitura_antiga_atrasada_nao_desfaz_a_nova(obs):
    nova = _leitura(obs, observed_h=30, available_h=31, payload=b"nova", valor=7_000_000)
    antiga = _leitura(obs, observed_h=26, available_h=40, payload=b"antiga", valor=5_000_000,
                      run_id="run-atrasado", lote_id="lote-atrasado")  # medida antes, entregue depois
    r = Registro()
    assert r.registrar_todas([nova, antiga]) == [ResultadoRegistro.INSERIDO, ResultadoRegistro.INSERIDO]
    nat = nova.chave_natural
    for t in (41, 1000):
        assert as_of([nova, antiga], _t(obs, t))[nat].valor == 7_000_000
        assert r.as_of(_t(obs, t))[nat].valor == 7_000_000
    assert as_of([antiga], _t(obs, 41))[nat].valor == 5_000_000  # sozinha ela vale: fica no histórico
    assert r.vigente(nat).observacao is nova and len(r.historico(nat)) == 2
    # mesmo observed_at: vence a conhecida por último
    a = _leitura(obs, observed_h=30, available_h=32, payload=b"a", valor=1_000_000)
    b = _leitura(obs, observed_h=30, available_h=35, payload=b"b", valor=2_000_000)
    assert as_of([b, a], _t(obs, 40))[nat].valor == 2_000_000


def test_d1_equivale_ao_consumidor_do_simulador_em_atraso_receita_longo():
    """Mede o que a thread D mediu (06 §10.1): com a regra nova, 0 divergências contra `visao_as_of` da E;
    com a regra antiga (maior available_at), há divergências — o teste discrimina."""
    pytest.importorskip("numpy")
    from volc_dil.fundacao.shadow.fonte_simulador import registro_para_observacao
    from volc_dil.fundacao.simulador import simular
    from volc_dil.fundacao.simulador.consumidor import _versao, chave_fato
    from volc_dil.fundacao.simulador.registro import STATUS_COM_VALOR

    sim = simular("atraso_receita_longo", 20261016, n_campanhas=20, n_dias=20)
    pares = []
    for r in sim.leituras.registros:
        if r.status not in STATUS_COM_VALOR or r.custom_key_efetiva != r.custom_key_solicitada:
            continue  # mesmo filtro de visao_as_of
        try:
            o = registro_para_observacao(r)
        except ObservacaoInvalida:
            continue
        if o is not None:
            pares.append((r, o))
    cortes = sorted({r.available_at[:13] for r, _ in pares})[::6]
    div_nova = div_antiga = total = 0
    for c in cortes:
        grupos = defaultdict(list)
        for r, o in pares:
            if r.available_at[:13] <= c:
                grupos[chave_fato(r)].append((r, o))
        for itens in grupos.values():
            total += 1
            certo = max(itens, key=lambda x: _versao(x[0]))[0]
            nova = vigente_entre(itens, obs=lambda x: x[1])[0]
            antiga = max(itens, key=lambda x: x[1].available_at)[0]
            div_nova += nova.valor != certo.valor
            div_antiga += antiga.valor != certo.valor
    assert total > 10_000 and div_nova == 0 and div_antiga > 0, (total, div_nova, div_antiga)


# ============================================================== D2: releitura D0
def _linha_v21(campanha: str, hora_coleta: datetime, custo: int, *, dia: date) -> dict:
    payload = {"campaign": {"id": campanha}, "metrics": {"costMicros": str(custo), "impressions": "10", "clicks": "1"},
               "customer": {"currencyCode": "BRL"}}
    return {
        "observation_id": f"{campanha}:{hora_coleta.isoformat()}", "run_id": f"run-{hora_coleta:%Y%m%d%H}",
        "batch_id": f"lote-{campanha}-{hora_coleta:%Y%m%d%H}", "customer_id": "1234567890", "campaign_id": campanha,
        "ad_group_id": None, "criterion_id": None, "resource_type": "campaign", "resource_id": campanha,
        "grain": "campaign_day", "metric_date": dia, "metric_hour": None, "currency_code": "BRL",
        "dimensions": {}, "metrics": {"cost_micros": custo, "impressions": 10, "clicks": 1, "conversions": 0},
        "collected_at": hora_coleta, "created_at": hora_coleta + timedelta(seconds=30),
        "batch_payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        "batch_request_id": None, "batch_payload": payload, "run_collector": "n8n-google-ads-d0",
        "run_collector_version": 1, "run_api_version": "v25", "run_timezone": "America/Sao_Paulo",
    }


def _padrao_real_d0(dia: date = date(2026, 10, 15)):
    """5 campanhas, coleta de hora em hora (01h–23h) e a de D+1 06h; a cada hora 1 campanha muda (~80% repete)."""
    custos = {f"2310000000{i}": 1_000_000 * (i + 1) for i in range(5)}
    linhas = []
    for h in range(1, 24):
        muda = f"2310000000{h % 5}"
        custos[muda] += 100_000
        hora = datetime(dia.year, dia.month, dia.day, h, 5, tzinfo=BRT)
        linhas += [_linha_v21(c, hora, v, dia=dia) for c, v in sorted(custos.items())]
    fecha = datetime(dia.year, dia.month, dia.day, 6, 5, tzinfo=BRT) + timedelta(days=1)
    linhas += [_linha_v21(c, fecha, v, dia=dia) for c, v in sorted(custos.items())]
    return linhas, custos


def test_d2_releitura_d0_do_padrao_real_nao_conflita_e_fecha_a_janela():
    linhas, custos_finais = _padrao_real_d0()
    custos = [o for l in linhas for o in adaptar_google_ads_v21(l) if o.metrica.value == "cost"]
    repete = sum(1 for a, b in zip(linhas, linhas[5:]) if a["batch_payload_sha256"] == b["batch_payload_sha256"])
    assert repete / (len(linhas) - 5) >= 0.75  # ~80% das leituras repetem o payload da hora anterior
    r = Registro()
    res = r.registrar_todas(custos)  # antes (cobertura fabricada na mesma chave): ConflitoIdempotencia
    assert set(res) == {ResultadoRegistro.INSERIDO} and len(r) == len(custos)  # cada hora é uma leitura nova
    assert r.registrar_todas(custos) == [ResultadoRegistro.NOOP] * len(custos)  # retry é no-op
    fim = r.as_of(datetime(2026, 10, 16, 7, tzinfo=BRT))
    assert {o.status for o in fim.values()} == {StatusObservacao.OBSERVED}  # o mesmo payload, agora com a janela fechada
    assert sorted(o.valor for o in fim.values()) == sorted(custos_finais.values())
    meio = r.as_of(datetime(2026, 10, 15, 12, 30, tzinfo=BRT))
    assert {o.status for o in meio.values()} == {StatusObservacao.PARTIAL}
    assert {o.cobertura_ppm for o in meio.values()} == {None}  # R1-F17: sem cobertura fabricada


def test_d2_cobertura_declarada_que_muda_e_versao_nova_mesma_leitura_com_outra_e_conflito(obs):
    d = obs().janela_inicio
    corpo = PayloadBruto("v1", b'[{"id": "1", "impressions": 8}]')
    from volc_dil.contracts.vocab import Metrica
    from volc_dil.fundacao.observacao import CampoMetrica, EsquemaPayload, Unidade

    esq = {"v1": EsquemaPayload("v1", ("id",), (CampoMetrica(("impressions",), Metrica.IMPRESSOES, Unidade.CONTAGEM),))}

    def ctx(h, cob):
        t = d + timedelta(hours=h)
        return ContextoLeitura(fonte="joinads", conta="dom", entidade_tipo="campaign", grao=("campaign", "day"),
                               janela_inicio=d, janela_fim=d + timedelta(days=1), timezone="America/Sao_Paulo",
                               observed_at=t, available_at=t, ingested_at=t, run_id=f"r{h}", lote_id=f"l{h}",
                               coletor=Coletor("c", "1"), cobertura_ppm=cob)

    leituras = [normalizar(corpo, esq, ctx(h, h * 1_000_000 // 24)).observacoes[0] for h in (6, 12, 18)]
    r = Registro()
    assert r.registrar_todas(leituras) == [ResultadoRegistro.INSERIDO] * 3
    assert r.as_of(d + timedelta(hours=13))[leituras[0].chave_natural].cobertura_ppm == 500_000
    mesma_hora_outra_cobertura = normalizar(corpo, esq, ctx(12, 1)).observacoes[0]
    with pytest.raises(ConflitoIdempotencia):  # mesma leitura (mesmo observed_at e payload) não pode mudar
        r.registrar(mesma_hora_outra_cobertura)


# ============================================================== D3: ambiguidade independente da ordem
def test_d3_ambiguidade_superada_nao_levanta_em_nenhuma_permutacao(obs):
    x = _leitura(obs, observed_h=30, available_h=31, payload=b"x", valor=1_000_000)
    y = _leitura(obs, observed_h=30, available_h=31, payload=b"y", valor=2_000_000)  # empata com x: ambígua
    z = _leitura(obs, observed_h=40, available_h=41, payload=b"z", valor=3_000_000)  # supera as duas
    nat = z.chave_natural
    for perm in itertools.permutations([x, y, z, x]):
        assert as_of(perm, _t(obs, 50))[nat].valor == 3_000_000
        with pytest.raises(VersaoAmbigua):
            as_of(perm, _t(obs, 35))  # no corte em que a ambígua É o topo, levanta sempre


def test_d3_propriedade_resultado_e_erro_independem_da_ordem(obs):
    rng = random.Random(16)
    for _ in range(200):
        n = rng.randint(2, 6)
        itens = []
        for k in range(n):
            o_h = rng.choice([30, 31, 32])
            a_h = rng.choice([33, 34, 35])
            itens.append(_leitura(obs, observed_h=o_h, available_h=a_h, payload=f"p{rng.randint(0, 3)}".encode(),
                                  valor=1_000_000 * (k + 1), run_id=f"r{k}", lote_id=f"l{k}"))

        def resultado(seq):
            try:
                return ("ok", {k: v.chave_base for k, v in as_of(seq, _t(obs, 40)).items()})
            except (VersaoAmbigua, ConflitoIdempotencia) as e:
                return ("erro", type(e).__name__)

        ref = resultado(itens)
        for _ in range(10):
            embaralhado = list(itens)
            rng.shuffle(embaralhado)
            assert resultado(embaralhado) == ref
