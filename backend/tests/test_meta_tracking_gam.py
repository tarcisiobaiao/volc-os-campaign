"""Tracking GAM faz parte do hash, não é edição no navegador ou após aprovação.

⚠️ O GRÃO MUDOU EM 08/09/2026, e este arquivo é onde a mudança é cobrada.

A versão anterior provava `utm_campaign={{campaign.id}}`. A operação real usa
`utm_campaign={{adset.id}}` — é esse valor que o GAM materializa em
`utm_campaign_value`, e é por ele que a receita chega. Um criativo nascido com
o tracking antigo produziria receita que o pipeline não casaria, e o defeito só
apareceria dias depois como "receita ausente" num criativo que nasceu certo.
"""
from urllib.parse import parse_qs

import pytest

from app.trafego.meta_execucao.compilador import (
    JOIN_DE_RECEITA,
    RESOLUCAO_DE_CAMPANHA,
    TRACKING_GAM_ADSET_ID,
    compilar_plano_pausado,
    resolver_dependencias,
)
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from test_meta_contrato_endurecido import _plano, _refs


# ---------------------------------------------------------------------------
# O template canônico
# ---------------------------------------------------------------------------

def test_tracking_compilado_leva_o_adset_e_preserva_a_lp():
    plano = _plano()
    compilado = compilar_plano_pausado(plano, _refs())
    creative = next(op for op in compilado.operacoes if op.tipo_objeto == 'creative')
    tags = parse_qs(creative.payload['url_tags'])
    # A dimensão que o GAM materializa.
    assert tags['utm_campaign'] == ['{{adset.id}}']
    assert tags['utm_term'] == ['{{adset.id}}']
    # A procedência do anúncio, para a instrumentação do site.
    assert tags['utm_content'] == ['{{ad.id}}']
    assert tags['utm_source'] == ['{{site_source_name}}']
    assert tags['utm_medium'] == ['paid_social']
    assert tags['placement'] == ['{{placement}}']
    # A campanha continua disponível — em parâmetro SEPARADO.
    assert tags['campaign_id'] == ['{{campaign.id}}']
    # A LP não é reescrita.
    assert creative.payload['object_story_spec']['link_data']['link'] == plano.destination_url


def test_a_macro_do_provedor_sobrevive_a_resolucao_de_dependencia():
    """`{{...}}` é da Meta e fica literal; `$adset.id` é nosso e é resolvido."""
    plano = _plano()
    compilado = compilar_plano_pausado(plano, _refs())
    creative = next(op for op in compilado.operacoes if op.tipo_objeto == 'creative')
    resolvido = resolver_dependencias(creative.payload, {'campaign': '123', 'adset': '456'})
    assert resolvido['url_tags'] == TRACKING_GAM_ADSET_ID
    assert '{{adset.id}}' in resolvido['url_tags'], 'a macro não pode virar 456 aqui'
    assert '456' not in resolvido['url_tags']


def test_o_tracking_entra_no_plano_publico_e_no_snapshot():
    compilado = compilar_plano_pausado(_plano(), _refs())
    publico = compilado.publico()
    assert publico['tracking']['url_tags'] == [TRACKING_GAM_ADSET_ID]
    assert publico['tracking']['revenue_join'] == JOIN_DE_RECEITA == 'GAM.utm_campaign_value = adset_id'
    assert publico['tracking']['resolucao_de_campanha'] == RESOLUCAO_DE_CAMPANHA
    assert 'conjunto' in publico['tracking']['grao_da_receita'].lower()
    assert 'url_tags' in str(compilado.congelar())


def test_o_contrato_nao_declara_dimensao_que_o_gam_nao_persiste():
    """O GAM materializa `utm_campaign_value`. Só ela é chave de atribuição."""
    publico = compilar_plano_pausado(_plano(), _refs()).publico()
    join = publico['tracking']['revenue_join']
    assert 'adset_id' in join
    for nao_persistida in ('utm_term', 'utm_content', 'placement', 'campaign_id'):
        assert nao_persistida not in join, (
            f'{nao_persistida} viaja na URL mas o GAM não a persiste; '
            'declará-la como chave de atribuição seria prometer o que não existe')
    # A campanha é resolvida pelo read model, não pelo GAM.
    assert 'read model' in publico['tracking']['resolucao_de_campanha']
    assert 'trafego_meta_adset' in publico['tracking']['resolucao_de_campanha']


# ---------------------------------------------------------------------------
# Parâmetros conflitantes na URL de destino
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('query', [
    'utm_campaign=outra', 'campaign_id=123', '%75tm_campaign=123',
    'utm_source=google', 'utm_medium=cpc',
    # Os três que entraram no contrato em 08/09/2026.
    'utm_term=marca', 'utm_content=banner', 'placement=feed',
])
def test_destino_com_tracking_conflitante_recusa_sem_reescrever(query):
    with pytest.raises(ErroDeNascimentoMeta, match='tracking'):
        _plano(destination_url='https://example.com/oferta/?' + query)


def test_destino_sem_conflito_continua_aceito():
    plano = _plano(destination_url='https://example.com/oferta/?ref=parceiro&gclid=x')
    assert plano.destination_url.endswith('ref=parceiro&gclid=x')


# ---------------------------------------------------------------------------
# Read-back: o que voltou tem de ser o que foi enviado
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('lido', [
    None,
    'utm_campaign=outra',
    # O tracking ANTIGO voltando: um criativo nascido antes do grão novo.
    'utm_source=meta&utm_medium=paid_social&utm_campaign={{campaign.id}}&campaign_id={{campaign.id}}',
    # Parâmetro duplicado.
    TRACKING_GAM_ADSET_ID + '&campaign_id=outro',
    # A macro trocada de dimensão: utm_campaign com a campanha em vez do conjunto.
    TRACKING_GAM_ADSET_ID.replace('utm_campaign={{adset.id}}', 'utm_campaign={{campaign.id}}'),
])
def test_readback_recusa_tracking_ausente_trocado_ou_duplicado(lido):
    from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta
    with pytest.raises(ErroRemotoMeta, match='url_tags'):
        ExecutorMetaPausado._validar_read_back('creative', {
            'id': '77', 'account_id': '88', 'url_tags': lido,
        }, payload={'url_tags': TRACKING_GAM_ADSET_ID}, identificador='77', ids={}, conta_externa='88')


def test_readback_aceita_mesmos_parametros_em_ordem_diferente():
    from app.trafego.meta_execucao.executor import ExecutorMetaPausado
    ExecutorMetaPausado._validar_read_back('creative', {
        'id': '77', 'account_id': '88', 'status': 'ACTIVE',
        'url_tags': '&'.join(reversed(TRACKING_GAM_ADSET_ID.split('&'))),
    }, payload={'url_tags': TRACKING_GAM_ADSET_ID}, identificador='77', ids={}, conta_externa='88')


def test_readback_divergente_levanta_em_vez_de_devolver_ok():
    """⚠️ ESTE TESTE FOI RENOMEADO, e o nome antigo era a mentira.

    Ele se chamava `test_readback_divergente_nao_reenvia_criacao` e NÃO prova
    isso: chama `_validar_read_back` direto, sem percorrer a saga, sem ledger e
    sem contar POSTs. Se o executor passasse a capturar a divergência e
    reenviar, este teste continuaria verde — achado do revisor adversarial.

    O que ele prova de fato é o degrau anterior: a validação LEVANTA em vez de
    devolver "ok". Quem prova a não-repetição do POST é
    `test_meta_paused_birth.py::test_retomada_de_passo_criado_nao_repete_post_real`,
    que percorre a saga inteira e conta as chamadas.
    """
    from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta
    with pytest.raises(ErroRemotoMeta) as erro:
        ExecutorMetaPausado._validar_read_back('creative', {
            'id': '77', 'account_id': '88', 'url_tags': 'utm_campaign=outra',
        }, payload={'url_tags': TRACKING_GAM_ADSET_ID}, identificador='77', ids={}, conta_externa='88')
    assert 'url_tags' in str(erro.value)


# ---------------------------------------------------------------------------
# O hash: o tracking faz parte da identidade do plano
# ---------------------------------------------------------------------------

def test_tracking_diferente_produz_hash_diferente(monkeypatch):
    """Um plano aprovado com outro tracking não é o mesmo plano."""
    from app.trafego.meta_execucao import compilador as comp
    antes = compilar_plano_pausado(_plano(), _refs()).plano_sha256
    monkeypatch.setattr(comp, 'TRACKING_GAM_ADSET_ID',
                        'utm_source=meta&utm_medium=paid_social&utm_campaign={{campaign.id}}')
    depois = compilar_plano_pausado(_plano(), _refs()).plano_sha256
    assert antes != depois, 'o tracking precisa entrar no hash do plano'


def test_o_mesmo_plano_compila_para_o_mesmo_hash():
    a = compilar_plano_pausado(_plano(), _refs()).plano_sha256
    b = compilar_plano_pausado(_plano(), _refs()).plano_sha256
    assert a == b
