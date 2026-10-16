"""Dataset temporal: índice do fluxo, as_of por corte, snapshot imutável e fingerprint."""
from __future__ import annotations

import dataclasses
import random
from datetime import timedelta

import pytest

from volc_dil.contracts.snapshot import VersaoAmbigua
from volc_dil.fundacao.observacao import Observacao, as_of
from volc_dil.fundacao.shadow._gerador_provisorio import preparar
from volc_dil.fundacao.shadow.fluxo import FluxoIndexado, cortes_regulares
from volc_dil.fundacao.shadow.politicas import Manter, SnapshotObrigatorio
from volc_dil.fundacao.shadow.snapshot import SnapshotAdulterado, SnapshotShadow, construir_snapshot


@pytest.fixture(scope="module")
def base():
    return preparar("base", passo_horas=7)


def test_as_of_do_indice_igual_ao_da_thread_a_em_todos_os_cortes(base):
    fs, cortes, _ = base
    fi = FluxoIndexado(fs.observacoes)
    for t in cortes[::3]:
        esperado = as_of(fs.observacoes, t)
        obtido = {k: i.obs for k, i in fi.as_of(t).items()}
        assert obtido == dict(esperado)


def test_fingerprint_independe_da_ordem_e_de_reentrega_identica(base):
    fs, cortes, cfg = base
    t = cortes[len(cortes) // 2]
    embaralhado = list(fs.observacoes)
    random.Random(7).shuffle(embaralhado)
    reentregue = embaralhado + embaralhado[:50]
    a = construir_snapshot(FluxoIndexado(fs.observacoes), t, cfg.corte)
    b = construir_snapshot(FluxoIndexado(reentregue), t, cfg.corte)
    assert a.fingerprint == b.fingerprint and a.para_json() == b.para_json()


def test_observacao_futura_nao_muda_snapshot_nem_fingerprint(base):
    fs, cortes, cfg = base
    t = cortes[5]
    import hashlib

    def h(i):
        return hashlib.sha256(f"futuro-{i}".encode()).hexdigest()

    futura = [dataclasses.replace(o, available_at=t + timedelta(days=30), ingested_at=t + timedelta(days=30),
                                  observed_at=max(o.observed_at, o.janela_fim), payload_sha256=h(i),
                                  payload_ref="futuro:" + h(i), valor=o.valor + 10_000)
              for i, o in enumerate(fs.observacoes[:200]) if o.status.value in ("observed",)]
    futura = list({o.chave_natural: o for o in futura}.values())  # uma versão futura por fato
    assert futura
    a = construir_snapshot(FluxoIndexado(fs.observacoes), t, cfg.corte)
    b = construir_snapshot(FluxoIndexado(list(fs.observacoes) + futura), t, cfg.corte)
    assert a.fingerprint == b.fingerprint
    # e muda depois que a observação fica disponível
    t2 = t + timedelta(days=31)
    c = construir_snapshot(FluxoIndexado(fs.observacoes), t2, cfg.corte)
    d = construir_snapshot(FluxoIndexado(list(fs.observacoes) + futura), t2, cfg.corte)
    assert c.fingerprint != d.fingerprint


def test_snapshot_imutavel_sem_observacao_e_com_integridade(base):
    fs, cortes, cfg = base
    s = construir_snapshot(FluxoIndexado(fs.observacoes), cortes[10], cfg.corte)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.fatos = ()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.fatos[0].idade_h = 999  # type: ignore[misc]

    def varrer(x, profundidade=0):
        assert not isinstance(x, Observacao), "snapshot carrega Observacao (porta para o fluxo)"
        if profundidade > 6:
            return
        if dataclasses.is_dataclass(x) and not isinstance(x, type):
            for f in dataclasses.fields(x):
                varrer(getattr(x, f.name), profundidade + 1)
        elif isinstance(x, (tuple, list)):
            for v in x:
                varrer(v, profundidade + 1)

    varrer(s)
    s.verificar_integridade()
    adulterado = object.__new__(SnapshotShadow)
    adulterado.__dict__.update(s.__dict__)
    object.__setattr__(adulterado, "fatos", s.fatos[1:])
    with pytest.raises(SnapshotAdulterado):
        adulterado.verificar_integridade()
    with pytest.raises(SnapshotAdulterado):
        dataclasses.replace(s, fatos=s.fatos[1:], fingerprint=s.fingerprint)


def test_politica_recusa_o_que_nao_e_snapshot(base):
    fs, _, _ = base
    with pytest.raises(SnapshotObrigatorio):
        Manter().decidir(fs.observacoes)  # type: ignore[arg-type]
    with pytest.raises(SnapshotObrigatorio):
        Manter().decidir(FluxoIndexado(fs.observacoes))  # type: ignore[arg-type]


def test_juncao_por_dia_com_cobertura_e_nao_atribuivel():
    fs, cortes, cfg = preparar("identidade_trocada", passo_horas=24)
    s = construir_snapshot(FluxoIndexado(fs.observacoes), cortes[-1], cfg.corte)
    dias_trocados = [c for c in s.cobertura if "custom_key_substituida" in c.bloqueios]
    assert dias_trocados, "dia com custom_key trocada precisa virar bloqueio de dia"
    for c in dias_trocados:
        assert c.receita_nao_atribuida >= 1 and c.sem_receita_valida
        assert c.fracao_minima is not None and c.fracao_minima < 1
    limpos = [c for c in s.cobertura if not c.bloqueios and c.fracoes]
    assert limpos and all(c.denominador == "earnings_dominio_dia" for c in limpos)
    # custo do dia em curso é parcial; dias fechados vêm com idade
    hoje = [f for f in s.fatos if f.dia == s.dia_corte]
    assert all(f.custo_status in ("partial", None) for f in hoje)
    assert all(f.idade_h >= 0 for f in s.fatos if f.dia < s.dia_corte)


def test_quarentena_de_versao_ambigua(base):
    fs, cortes, cfg = base
    o = next(x for x in fs.observacoes if x.status.value == "observed" and x.metrica.value == "cost")
    gemea = dataclasses.replace(o, payload_sha256="a" * 64, payload_ref="gemea:" + "a" * 64, valor=o.valor + 10_000)
    t = o.available_at + timedelta(hours=1)
    with pytest.raises(VersaoAmbigua):
        FluxoIndexado(list(fs.observacoes) + [gemea]).as_of(t)
    fi = FluxoIndexado(list(fs.observacoes) + [gemea], ambiguidade="quarentena")
    assert len(fi.quarentena) == 2
    assert not fi.quarentena_visivel(o.available_at - timedelta(seconds=1))
    s = construir_snapshot(fi, t, cfg.corte)
    assert any(d.codigo == "versao_ambigua_em_quarentena" for d in s.diagnosticos_dados)


def test_cortes_regulares_exigem_timezone():
    from datetime import datetime

    with pytest.raises(Exception):
        cortes_regulares(datetime(2026, 1, 1), datetime(2026, 1, 2))
