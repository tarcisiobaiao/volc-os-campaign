"""Tracking GAM faz parte do hash, não é edição no navegador ou após aprovação."""
from urllib.parse import parse_qs

import pytest

from app.trafego.meta_execucao.compilador import compilar_plano_pausado, resolver_dependencias, TRACKING_GAM_CAMPAIGN_ID
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from test_meta_contrato_endurecido import _plano, _refs


def test_tracking_campaign_id_compilado_preserva_macro_e_lp():
    plano = _plano()
    compilado = compilar_plano_pausado(plano, _refs())
    creative = next(op for op in compilado.operacoes if op.tipo_objeto == 'creative')
    tags = parse_qs(creative.payload['url_tags'])
    assert tags['utm_campaign'] == ['{{campaign.id}}']
    assert tags['campaign_id'] == ['{{campaign.id}}']
    assert creative.payload['object_story_spec']['link_data']['link'] == plano.destination_url
    assert resolver_dependencias(creative.payload, {'campaign': '123'})['url_tags'] == TRACKING_GAM_CAMPAIGN_ID
    assert compilado.publico()['tracking']['url_tags'] == [TRACKING_GAM_CAMPAIGN_ID]
    assert 'url_tags' in str(compilado.congelar())


@pytest.mark.parametrize('query', ['utm_campaign=outra', 'campaign_id=123', '%75tm_campaign=123', 'utm_source=google', 'utm_medium=cpc'])
def test_destino_com_tracking_conflitante_recusa_sem_reescrever(query):
    with pytest.raises(ErroDeNascimentoMeta, match='tracking'):
        _plano(destination_url='https://example.com/oferta/?' + query)


@pytest.mark.parametrize('lido', [None, 'utm_campaign=outra', TRACKING_GAM_CAMPAIGN_ID + '&campaign_id=outro'])
def test_readback_recusa_tracking_ausente_trocado_ou_duplicado(lido):
    from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta
    with pytest.raises(ErroRemotoMeta, match='url_tags'):
        ExecutorMetaPausado._validar_read_back('creative', {
            'id': '77', 'account_id': '88', 'url_tags': lido,
        }, payload={'url_tags': TRACKING_GAM_CAMPAIGN_ID}, identificador='77', ids={}, conta_externa='88')


def test_readback_aceita_mesmos_parametros_em_ordem_diferente():
    from app.trafego.meta_execucao.executor import ExecutorMetaPausado
    ExecutorMetaPausado._validar_read_back('creative', {
        'id': '77', 'account_id': '88', 'status': 'ACTIVE',
        'url_tags': '&'.join(reversed(TRACKING_GAM_CAMPAIGN_ID.split('&'))),
    }, payload={'url_tags': TRACKING_GAM_CAMPAIGN_ID}, identificador='77', ids={}, conta_externa='88')
