"""Read-only validation failure is not an ambiguous remote creation."""
from dataclasses import replace
import asyncio

import httpx
import pytest

from app.routers.trafego_meta_criacao import _erro
from app.trafego.meta_execucao.executor import ExecutorMetaPausado, ErroRemotoMeta
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from test_meta_paused_birth import (
    RegistroEmMemoria, SegredoEfemero, TOKEN, autorizacao, compilado,
    formulario, transport_sucesso,
)
from test_meta_contrato_v2 import _plano_v2, _conjunto, _variacao, c2
import test_meta_criacao_pausada_rotas as routes


class DurableFake(RegistroEmMemoria):
    async def fechar_passo(self, **kwargs):
        token = await super().fechar_passo(**kwargs)
        self.retomados[kwargs['passo_ref'].removeprefix('passo_')] = kwargs['id_externo']
        return token


@pytest.mark.asyncio
@pytest.mark.parametrize('edge,prior', [
    ('campaigns', ()), ('adsets', ('campaign',)),
    ('adcreatives', ('campaign', 'adset')), ('ads', ('campaign', 'adset', 'creative')),
])
async def test_validation_timeout_reports_retriable_same_approval_without_false_ambiguity(edge, prior):
    calls, journal = [], DurableFake()
    success = transport_sucesso(calls)
    fail_validation = True
    async def handler(request):
        if fail_validation and request.method == 'POST' and request.url.path.endswith('/' + edge) and 'execution_options' in formulario(request):
            raise httpx.ReadTimeout('synthetic validation timeout', request=request)
        return await success.handle_async_request(request)
    plan = compilado()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        executor = ExecutorMetaPausado(client, registro=journal)
        with pytest.raises(ErroRemotoMeta) as failure:
            await executor.criar_pausada(plan, SegredoEfemero(TOKEN), autorizacao(plan.plano_sha256))
        error = failure.value
        assert error.codigo == 'META_VALIDATE_TIMEOUT'
        assert error.retryable and not error.exige_reconciliacao
        assert error.objetos_criados == prior
        assert not any(action in {'ambiguo', 'falhar'} for action, _ in journal.eventos)
        assert tuple(name for action, name in journal.eventos if action == 'preparar') == prior
        public = _erro(error, recibo={'steps': list(prior)})
        assert public.status_code == 504
        assert public.detail['retry_permitido'] is True
        assert public.detail['reconciliacao_necessaria'] is False
        assert public.detail['recibo']['steps'] == list(prior)
        assert TOKEN not in str(public.detail)
        # Same approval, no new remote object for any previously completed step.
        fail_validation = False
        result = await executor.criar_pausada(plan, SegredoEfemero(TOKEN), autorizacao(plan.plano_sha256))
    assert result.desfecho == 'CREATED_PAUSED'
    real_posts = [endpoint for method, endpoint, payload in calls if method == 'POST' and 'execution_options' not in payload]
    assert real_posts == ['campaigns', 'adsets', 'adcreatives', 'ads']


def test_created_timeout_still_requires_reconciliation_not_http_504():
    public = _erro(ErroRemotoMeta('META_REMOTE_RESULT_AMBIGUOUS', 'creation unknown', exige_reconciliacao=True))
    assert public.status_code == 502 and public.detail['reconciliacao_necessaria'] is True
    assert public.detail['retry_permitido'] is False


def test_duplicate_variation_key_across_adsets_is_already_rejected_before_compilation():
    first = _variacao('same-key')
    second = replace(first, creative_name='Second creative', ad_name='Second ad')
    with pytest.raises(ErroDeNascimentoMeta) as failure:
        _plano_v2(conjuntos=(_conjunto('first', nome='First'), _conjunto('second', nome='Second')),
                  anuncios=(c2.AnuncioMeta(variacao=first, adset_key='first'), c2.AnuncioMeta(variacao=second, adset_key='second')))
    assert failure.value.codigo == 'META_STATIC_BATCH_DUPLICATE_KEY'


@pytest.mark.parametrize('edge,created', [('campaigns', []), ('adsets', ['campaign'])])
def test_http_route_returns_current_ledger_and_resumes_same_approval(monkeypatch, edge, created):
    setup = routes._cenario_limpo.__wrapped__(monkeypatch)
    next(setup)
    try:
        ledger = routes._LedgerEmMemoria()
        routes._abrir(monkeypatch, ledger)
        client = routes._cliente()
        approval = asyncio.run(routes._aprovar(client, ledger, routes._plano_para_envio())).json()['aprovacao']
        original_post = routes._GraphFalso.post
        fail_validation = True
        async def post(self, url, *, data=None, headers=None):
            if fail_validation and url.endswith('/' + edge) and 'execution_options' in (data or {}):
                raise httpx.ReadTimeout('synthetic validation timeout')
            return await original_post(self, url, data=data, headers=headers)
        monkeypatch.setattr(routes._GraphFalso, 'post', post)
        body = {'approval_id': approval['approval_id'], 'plano_sha256_esperado': approval['plano_sha256']}
        response = client.post('/api/trafego/meta/local/criacao/criar-pausada', json=body)
        assert response.status_code == 504, response.text
        detail = response.json()['detail']
        assert detail['codigo'] == 'META_VALIDATE_TIMEOUT'
        assert detail['retry_permitido'] is True and detail['reconciliacao_necessaria'] is False
        assert detail['objetos_criados'] == created
        assert [step['name'] for step in detail['recibo']['steps']] == created
        assert all(step['state'] == 'CREATED' for step in detail['recibo']['steps'])
        fail_validation = False
        resumed = client.post('/api/trafego/meta/local/criacao/criar-pausada', json=body)
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()['desfecho'] == 'CREATED_PAUSED'
        assert routes.CENARIO.criados == ['campaign', 'adset', 'creative', 'ad']
    finally:
        next(setup, None)
