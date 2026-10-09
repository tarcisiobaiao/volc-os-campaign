"""A conferência técnica não autoriza PMax sem mensuração para lançamento."""
import copy
import pytest

from volc_ads.campanha import pmax
from volc_ads.campanha.testes_pmax import (
    CID, MCC, _acao, _brief, _cliente_sem_rede, _configuracao, _mensuracao,
)


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    monkeypatch.setattr(pmax, 'cliente', lambda _: _cliente_sem_rede())


def test_validate_only_envia_mesmo_sem_acao_na_metrica_mas_nao_libera_construir(monkeypatch):
    b = _brief(pmax=_configuracao(mensuracao=_mensuracao(
        _acao(inclui_em_conversoes=False))))
    enviados = []
    monkeypatch.setattr(pmax, 'validar_mutacoes',
                        lambda cid, ops, **kw: enviados.append((cid, ops, kw)))
    resultado, falha, quantidade = pmax.validar(CID, b, login_customer_id=MCC)
    assert resultado.ok and falha is None and quantidade > 0 and len(enviados) == 1
    assert any(a.campo == 'pmax.mensuracao' for a in resultado.achados)
    _, criacao = pmax.construir(CID, b, login_customer_id=MCC)
    assert not criacao.ok


@pytest.mark.parametrize('troca', [dict(mensuracao=None),
    dict(mensuracao=_mensuracao(cid='1234567890')),
    dict(mensuracao=_mensuracao(mcc='1234567890'))])
def test_validate_only_ainda_exige_recibo_real_da_conta_e_do_mcc(monkeypatch, troca):
    monkeypatch.setattr(pmax, 'validar_mutacoes',
                        lambda *a, **kw: pytest.fail('não deveria chegar à API'))
    resultado, _, quantidade = pmax.validar(CID, _brief(pmax=_configuracao(**troca)),
                                           login_customer_id=MCC)
    assert not resultado.ok and quantidade == 0


def test_validate_only_recusa_recibo_tamperado_sem_chamar_api(monkeypatch):
    recibo = copy.copy(_mensuracao())
    object.__setattr__(recibo, 'customer_id', '1234567890')
    monkeypatch.setattr(pmax, 'validar_mutacoes',
                        lambda *a, **kw: pytest.fail('recibo adulterado chegou à API'))
    resultado, _, quantidade = pmax.validar(
        CID, _brief(pmax=_configuracao(mensuracao=recibo)), login_customer_id=MCC)
    assert not resultado.ok and quantidade == 0


@pytest.mark.parametrize('troca', [dict(status='PAUSED'), dict(primaria_para_meta=False)])
def test_validacao_tecnica_nao_promove_planejamento_operacional(monkeypatch, troca):
    b = _brief(pmax=_configuracao(mensuracao=_mensuracao(_acao(**troca))))
    enviados = []
    monkeypatch.setattr(pmax, 'validar_mutacoes', lambda *a, **kw: enviados.append(a))
    resultado, falha, _ = pmax.validar(CID, b, login_customer_id=MCC)
    assert resultado.ok and falha is None and len(enviados) == 1
    operacional = pmax.planejar(CID, b, login_customer_id=MCC)
    assert not operacional.prontidao.pode_criar
    assert any(b.codigo == 'MENSURACAO_INADEQUADA' for b in operacional.bloqueios)
