"""Contraprovas do contrato econômico: cada teste tenta quebrar um invariante."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from volc_dil.contracts import (
    ChaveUnidade,
    Circularidade,
    Cobertura,
    ContratoViolado,
    Dinheiro,
    EstadoMedida,
    IdentidadeIncompativel,
    Maturidade,
    Metrica,
    MetodoAtribuicao,
    MoedasDiferentes,
    Observacao,
    Snapshot,
    ValueKind,
    ValueKindsMisturados,
    VazamentoDeFuturo,
    VersaoAmbigua,
    agregar,
    contribuicao,
    rotulo_economico,
    verificar_nao_circular,
)

SP = timezone(timedelta(hours=-3))
D0 = datetime(2026, 9, 1, tzinfo=SP)
UNI = ChaveUnidade("acc-1", "campaign", "c-1", ("campaign", "day"))


def obs(**kw) -> Observacao:
    base = dict(
        unidade=UNI,
        metrica=Metrica.CUSTO,
        valor=Dinheiro(10_000_000, "BRL"),
        estado=EstadoMedida.MEDIDO,
        janela_inicio=D0,
        janela_fim=D0 + timedelta(days=1),
        timezone="America/Sao_Paulo",
        observado_em=D0 + timedelta(days=1, hours=2),
        disponivel_em=D0 + timedelta(days=1, hours=3),
        fonte="google_ads",
        versao_fonte="v21",
        coleta_id="run-1",
        cobertura=Cobertura.COMPLETA,
        maturidade=Maturidade.MADURA,
        metodo=MetodoAtribuicao.NAO_APLICAVEL,
    )
    base.update(kw)
    return Observacao(**base)


def receita(**kw) -> Observacao:
    base = dict(
        metrica=Metrica.RECEITA,
        valor=Dinheiro(15_000_000, "BRL"),
        value_kind=ValueKind.REPORTED_REVENUE,
        fonte="joinads",
        coleta_id="run-r1",
        metodo=MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE,
    )
    base.update(kw)
    return obs(**base)


# ── dinheiro, null, tempo ───────────────────────────────────────────────────

def test_float_em_dinheiro_e_recusado():
    with pytest.raises(TypeError):
        Dinheiro(1.5, "BRL")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Dinheiro.de_decimal(1.5, "BRL")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Dinheiro.de_json({"micros": 1.5, "moeda": "BRL"})


def test_moedas_nao_se_somam():
    with pytest.raises(MoedasDiferentes):
        Dinheiro(1, "BRL") + Dinheiro(1, "USD")


def test_null_nao_e_zero_ausente_sem_valor_exige_motivo():
    with pytest.raises(ContratoViolado):
        obs(valor=None, estado=EstadoMedida.AUSENTE)  # sem motivo
    o = obs(valor=None, estado=EstadoMedida.NAO_COLETADO, motivo="coleta não rodou")
    assert o.valor is None
    with pytest.raises(ContratoViolado):
        obs(valor=Dinheiro(0, "BRL"), estado=EstadoMedida.AUSENTE, motivo="x")  # ausente carregando zero
    with pytest.raises(ContratoViolado):
        obs(valor=Dinheiro(5, "BRL"), estado=EstadoMedida.ZERO_CONFIRMADO)


def test_instante_sem_timezone_e_recusado():
    with pytest.raises(ContratoViolado):
        obs(disponivel_em=datetime(2026, 9, 2, 3))


def test_timezone_invalido_e_recusado():
    with pytest.raises(ContratoViolado):
        obs(timezone="Marte/Olympus")


def test_linhagem_obrigatoria():
    with pytest.raises(ContratoViolado):
        obs(coleta_id="")


# ── value_kind ─────────────────────────────────────────────────────────────

def test_receita_sem_value_kind_e_recusada():
    with pytest.raises(ContratoViolado):
        receita(value_kind=None)


def test_sinal_de_leilao_nao_e_receita():
    with pytest.raises(ContratoViolado):
        receita(value_kind=ValueKind.OBSERVED_AUCTION_SIGNAL)
    s = obs(metrica=Metrica.SINAL, valor=Dinheiro(2_100_000, "USD"), value_kind=ValueKind.OBSERVED_AUCTION_SIGNAL,
            metodo=MetodoAtribuicao.DETERMINISTIC_SESSION)
    assert s.value_kind is ValueKind.OBSERVED_AUCTION_SIGNAL
    with pytest.raises(ContratoViolado):
        obs(metrica=Metrica.SINAL, valor=Dinheiro(2_100_000, "USD"), value_kind=ValueKind.REPORTED_REVENUE)


def test_receita_agregada_nao_vira_reconciliada_por_sessao():
    sessao = ChaveUnidade("acc-1", "session", "s-1", ("session",))
    with pytest.raises(ContratoViolado):
        receita(unidade=sessao, value_kind=ValueKind.RECONCILED_REVENUE)


def test_reconciliada_nao_aceita_metodo_inferido():
    with pytest.raises(ContratoViolado):
        receita(value_kind=ValueKind.RECONCILED_REVENUE, metodo=MetodoAtribuicao.INFERRED)


# ── agregação anulável ─────────────────────────────────────────────────────

def test_soma_vazia_e_ausente_nao_zero():
    a = agregar([])
    assert a.valor is None and a.estado is EstadoMedida.AUSENTE


def test_membro_sem_valor_anula_agregado_por_padrao():
    xs = [obs(), obs(unidade=ChaveUnidade("acc-1", "campaign", "c-2", ("campaign", "day")),
                     valor=None, estado=EstadoMedida.FALHA, motivo="timeout")]
    a = agregar(xs)
    assert a.valor is None and a.estado is EstadoMedida.FALHA and a.n_sem_valor == 1
    p = agregar(xs, aceitar_parcial=True)
    assert p.valor == Dinheiro(10_000_000, "BRL") and p.cobertura is Cobertura.PARCIAL


def test_agregacao_recusa_moeda_e_value_kind_misturados():
    with pytest.raises(MoedasDiferentes):
        agregar([obs(), obs(valor=Dinheiro(1, "USD"))])
    with pytest.raises(ValueKindsMisturados):
        agregar([receita(), receita(value_kind=ValueKind.ESTIMATED_REVENUE)])


# ── identidade ─────────────────────────────────────────────────────────────

def test_identidade_trocada_bloqueia_contribuicao():
    outra_conta = ChaveUnidade("acc-2", "campaign", "c-1", ("campaign", "day"))  # mesmo id, outra conta
    with pytest.raises(IdentidadeIncompativel):
        contribuicao(obs(), receita(unidade=outra_conta))
    with pytest.raises(IdentidadeIncompativel):
        contribuicao(obs(), receita(timezone="UTC"))


def test_contribuicao_so_com_receita_contabil():
    ok = contribuicao(obs(), receita())
    assert ok.valor == Dinheiro(5_000_000, "BRL")
    est = contribuicao(obs(), receita(value_kind=ValueKind.ESTIMATED_REVENUE))
    assert est.valor is None and "não é contábil" in est.motivo
    nulo = contribuicao(obs(), receita(valor=None, estado=EstadoMedida.NAO_COLETADO, motivo="atraso"))
    assert nulo.valor is None


# ── snapshot as_of ─────────────────────────────────────────────────────────

def test_snapshot_exclui_e_conta_futuro_e_falha_quando_estrito():
    as_of = D0 + timedelta(days=1, hours=4)
    futura = obs(coleta_id="run-2", disponivel_em=as_of + timedelta(minutes=1), observado_em=as_of)
    s = Snapshot.construir([obs(), futura], as_of)
    assert s.manifesto["n_futuras_excluidas"] == 1
    with pytest.raises(VazamentoDeFuturo):
        Snapshot.construir([obs(), futura], as_of, politica_futuro="falhar")


def test_snapshot_usa_versao_conhecida_no_as_of_nao_a_final():
    prelim = receita(maturidade=Maturidade.PRELIMINAR, cobertura=Cobertura.PARCIAL)
    revisada = receita(valor=Dinheiro(12_000_000, "BRL"), maturidade=Maturidade.REVISADA, coleta_id="run-r2",
                       observado_em=D0 + timedelta(days=3), disponivel_em=D0 + timedelta(days=3, hours=1))
    cedo = Snapshot.construir([prelim, revisada], D0 + timedelta(days=2))
    tarde = Snapshot.construir([prelim, revisada], D0 + timedelta(days=4))
    assert cedo.filtrar(metrica=Metrica.RECEITA)[0].valor == Dinheiro(15_000_000, "BRL")
    assert tarde.filtrar(metrica=Metrica.RECEITA)[0].valor == Dinheiro(12_000_000, "BRL")
    assert tarde.manifesto["n_versoes_substituidas"] == 1
    assert cedo.fingerprint != tarde.fingerprint


def test_snapshot_recusa_versoes_conflitantes_no_mesmo_instante():
    with pytest.raises(VersaoAmbigua):
        Snapshot.construir([receita(), receita(valor=Dinheiro(1, "BRL"), coleta_id="run-x")], D0 + timedelta(days=2))


def test_cobertura_completa_em_janela_aberta_e_indicio_de_futuro():
    as_of = D0 + timedelta(hours=12)
    intradia = obs(observado_em=D0 + timedelta(hours=10), disponivel_em=D0 + timedelta(hours=11))
    with pytest.raises(ContratoViolado):
        Snapshot.construir([intradia], as_of)
    ok = Snapshot.construir([replace(intradia, cobertura=Cobertura.PARCIAL)], as_of)
    assert ok.manifesto["n_incluidas"] == 1


def test_fingerprint_deterministico_e_independente_da_ordem():
    as_of = D0 + timedelta(days=2)
    a = Snapshot.construir([obs(), receita()], as_of)
    b = Snapshot.construir([receita(), obs()], as_of)
    assert a.fingerprint == b.fingerprint
    a.verificar_integridade()


def test_roundtrip_json_preserva_fato():
    for o in (obs(), receita(), obs(valor=None, estado=EstadoMedida.FALHA, motivo="erro"),
              obs(metrica=Metrica.CLIQUES, valor=12), obs(metrica=Metrica.SINAL, valor=Decimal("0.73"))):
        assert Observacao.de_json(o.para_json()) == o


# ── rótulo e circularidade ─────────────────────────────────────────────────

def test_rotulo_economico_exige_reconciliado_maduro_completo():
    rec = receita(value_kind=ValueKind.RECONCILED_REVENUE)
    assert rotulo_economico(rec)[0] == Dinheiro(15_000_000, "BRL")
    assert rotulo_economico(receita())[0] is None  # reported não é rótulo
    assert rotulo_economico(replace(rec, maturidade=Maturidade.PRELIMINAR))[0] is None
    assert rotulo_economico(replace(rec, cobertura=Cobertura.PARCIAL))[0] is None


def test_circularidade_detectada():
    rotulo = receita(value_kind=ValueKind.RECONCILED_REVENUE, linhagem=("joinads:batch-9",))
    feat_mesma_origem = obs(metrica=Metrica.SINAL, valor=Decimal("1"), linhagem=("joinads:batch-9",),
                            metodo=MetodoAtribuicao.DETERMINISTIC_SESSION)
    with pytest.raises(Circularidade):
        verificar_nao_circular([feat_mesma_origem], rotulo)
    feat_receita_mesma_janela = receita(coleta_id="run-zz", value_kind=ValueKind.ESTIMATED_REVENUE)
    with pytest.raises(Circularidade):
        verificar_nao_circular([feat_receita_mesma_janela], rotulo)
    verificar_nao_circular([obs(metrica=Metrica.CLIQUES, valor=3, coleta_id="gads-run")], rotulo)


# ── fixture versionada ─────────────────────────────────────────────────────

def test_fixture_do_contrato_reproduz_manifesto():
    import json
    from pathlib import Path

    from volc_dil.contracts import sha256_arquivo

    pasta = Path(__file__).resolve().parents[2] / "experiments" / "data-intelligence-lab" / "fixtures" / "contract"
    manifesto = json.loads((pasta / "MANIFEST.json").read_text(encoding="utf-8"))
    arquivo = pasta / manifesto["arquivo"]
    assert sha256_arquivo(str(arquivo)) == manifesto["sha256"]
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    observacoes = [Observacao.de_json(d) for d in dados["observacoes"]]
    for nome, esperado in manifesto["snapshots"].items():
        s = Snapshot.construir(observacoes, datetime.fromisoformat(esperado["as_of"]), rotulo=nome)
        assert s.manifesto == esperado
