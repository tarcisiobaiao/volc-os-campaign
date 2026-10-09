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


def test_porta_do_selo_continua_recusando_pmax_sem_mensuracao(monkeypatch):
    """O selo só nasce em `subir.preparar`, que monta pelo construtor do perfil.
    O ramo técnico de `pmax.validar` não pode alcançá-lo: sem ação na métrica,
    nada vai ao Google e nenhum selo é emitido."""
    from volc_ads import subir

    b = _brief(pmax=_configuracao(mensuracao=_mensuracao(
        _acao(inclui_em_conversoes=False))))
    monkeypatch.setattr(subir, 'validar_mutacoes',
                        lambda *a, **kw: pytest.fail('preparar chegou à API sem mensuração'))
    preparo = subir.preparar(CID, b, login_customer_id=MCC, canal='PERFORMANCE_MAX')
    assert preparo.selo is None
    assert preparo.recusa_local and 'mensuracao' in preparo.recusa_local


# ── meta da campanha × campo depreciado (revisão 09/10/2026, doc v25) ───────

def _achados_de_mensuracao(r):
    return {(a.severidade, a.valor) for a in r.achados if a.campo == "pmax.mensuracao"}


def _brief_compra(metas=()):
    from volc_ads.campanha.pmax_config import MetaDeConversao  # noqa: F401
    acao = _acao(categoria="PURCHASE", inclui_em_conversoes=False)
    from volc_ads.campanha.testes_pmax import _v25
    return _brief(pmax=_v25(mensuracao=_mensuracao(acao), metas_de_conversao=tuple(metas)))


def test_sem_meta_da_campanha_a_recusa_continua_e_diz_que_e_heranca_da_conta():
    _, r = pmax.construir(CID, _brief_compra(), login_customer_id=MCC)
    assert ("erro", "FORA_DA_METRICA_DE_CONVERSOES") in _achados_de_mensuracao(r)
    texto = " ".join(a.motivo for a in r.achados if a.valor == "FORA_DA_METRICA_DE_CONVERSOES")
    assert "HERDA" in texto and "metas_de_conversao" in texto


def test_meta_da_campanha_biddable_declarada_tira_o_campo_depreciado_do_veto():
    from volc_ads.campanha.pmax_config import MetaDeConversao
    _, r = pmax.construir(CID, _brief_compra([MetaDeConversao("PURCHASE", "WEBSITE", True)]),
                          login_customer_id=MCC)
    achados = _achados_de_mensuracao(r)
    assert ("erro", "FORA_DA_METRICA_DE_CONVERSOES") not in achados
    assert ("aviso", "CAMPO_DEPRECADO_DIVERGENTE") in achados


def test_meta_da_campanha_declarada_nao_biddable_e_recusa_real():
    from volc_ads.campanha.pmax_config import MetaDeConversao
    acao = _acao(categoria="PURCHASE")
    from volc_ads.campanha.testes_pmax import _v25
    b = _brief(pmax=_v25(mensuracao=_mensuracao(acao),
                         metas_de_conversao=(MetaDeConversao("PURCHASE", "WEBSITE", False),)))
    _, r = pmax.construir(CID, b, login_customer_id=MCC)
    assert ("erro", "META_NAO_BIDDABLE") in _achados_de_mensuracao(r)
