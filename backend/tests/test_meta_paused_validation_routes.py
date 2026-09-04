from __future__ import annotations

import asyncio
from typing import Any

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import meta_local, trafego_meta_validacao
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.ativos import ResolvedorAtivosMeta
from app.trafego.meta_execucao.contrato import ErroDeNascimentoMeta
from app.trafego.meta_execucao.registro import RegistroSagaMetaSupabase
from app.trafego.meta.read_model import RepositorioMetaReadModelSupabase


class _Resposta:
    def __init__(self, body: dict[str, Any]) -> None:
        self.status_code = 200
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body


class _GraphFake:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, dict[str, str]]] = []

    async def get(self, url: str, *, params=None, headers=None):
        del params
        self.chamadas.append((url, dict(headers or {})))
        if url.endswith('/me/adaccounts'):
            return _Resposta({'data': [{
                'id': 'act_123456789', 'name': 'Conta teste', 'account_status': 1,
                'currency': 'BRL', 'timezone_name': 'America/Sao_Paulo',
            }]})
        if url.endswith('/promote_pages'):
            return _Resposta({'data': [{'id': '99887766', 'name': 'Página teste'}]})
        if url.endswith('/adimages'):
            return _Resposta({'data': [{
                'hash': 'hashImagem_123456', 'name': 'Imagem teste',
                'width': 1080, 'height': 1080,
            }]})
        raise AssertionError(url)


def _cliente() -> TestClient:
    app = FastAPI()
    app.include_router(trafego_meta_validacao.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade(
        sub='operador-meta', email='admin@volc', papel='ADMIN', origem='sessao')
    return TestClient(app, headers={'host': 'localhost'})


def test_router_nao_monta_create_approve_ou_enable(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, 'platform', 'darwin')
    paths = {route.path for route in trafego_meta_validacao.router.routes}
    assert '/api/trafego/meta/local/criacao/compilar' in paths
    assert '/api/trafego/meta/local/criacao/validar' in paths
    assert all('criar-pausada' not in path for path in paths)
    assert all('aprovar' not in path for path in paths)
    assert all('ativar' not in path for path in paths)


def test_capacidades_declaram_create_nao_montado(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, 'platform', 'darwin')
    monkeypatch.delenv('META_VALIDATE_ONLY_ENABLED', raising=False)
    resposta = _cliente().get('/api/trafego/meta/local/criacao/capacidades')
    assert resposta.status_code == 200
    assert resposta.json()['validate_only'] == 'BLOCKED_BY_SERVER_FLAG'
    assert resposta.json()['create_paused'] == 'NOT_MOUNTED'
    assert resposta.json()['activation'] == 'NOT_IMPLEMENTED'


def test_validate_only_fechado_recusa_antes_de_ler_token_ou_rede(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, 'platform', 'darwin')
    monkeypatch.delenv('META_VALIDATE_ONLY_ENABLED', raising=False)
    monkeypatch.setattr(
        trafego_meta_validacao,
        '_credencial_salva',
        lambda *_: pytest.fail('nao deveria ler token'),
    )
    resposta = _cliente().post('/api/trafego/meta/local/criacao/validar', json={
        'confirmar_validate_only': True,
        'plano': {
            'account_ref': 'metaacct_exemplo', 'page_ref': 'metapage_exemplo',
            'asset_ref': 'metaasset_exemplo', 'campaign_name': 'Campanha',
            'adset_name': 'Conjunto', 'creative_name': 'Criativo', 'ad_name': 'Anuncio',
            'destination_url': 'https://example.com/', 'message': 'Mensagem',
            'headline': 'Titulo', 'description': 'Descricao', 'daily_budget_minor': 1000,
            'start_time': '2027-01-01T12:00:00Z', 'special_ad_categories': [],
            'special_categories_confirmed': True, 'call_to_action_type': 'LEARN_MORE',
        },
    })
    assert resposta.status_code == 409
    assert resposta.json()['detail']['codigo'] == 'META_VALIDATE_ONLY_BLOCKED'


def test_inventario_de_criacao_so_devolve_referencias_opacas() -> None:
    async def cenario() -> None:
        graph = _GraphFake()
        resolvedor = ResolvedorAtivosMeta(graph)  # type: ignore[arg-type]
        segredo = SegredoEfemero('token-meta-falso-seguro')
        conta_ref = 'metaacct_7fefce36c70ca00f5dc1a04b'
        # Derive the handle through the public domain function, avoiding a
        # brittle digest literal if its namespace changes.
        from app.trafego.meta.dominio import referencia_opaca_conta
        conta_ref = referencia_opaca_conta('123456789')
        publico = await resolvedor.inventariar(conta_ref, segredo)
        texto = str(publico)
        assert '123456789' not in texto
        assert '99887766' not in texto
        assert 'hashImagem_123456' not in texto
        assert publico['paginas'][0]['referencia_opaca'].startswith('metaobj_')
        assert publico['imagens'][0]['referencia_opaca'].startswith('metaasset_')
        assert all(headers == {'Authorization': 'Bearer token-meta-falso-seguro'}
                   for _, headers in graph.chamadas)
    asyncio.run(cenario())


def test_inventario_recusa_conta_inativa_antes_de_ler_ativos() -> None:
    class GraphInativo(_GraphFake):
        async def get(self, url: str, *, params=None, headers=None):
            if url.endswith('/me/adaccounts'):
                return _Resposta({'data': [{
                    'id': 'act_123456789', 'name': 'Conta inativa',
                    'account_status': 2, 'currency': 'BRL',
                    'timezone_name': 'America/Sao_Paulo',
                }]})
            raise AssertionError('nao deveria ler ativos de conta inativa')

    async def cenario() -> None:
        from app.trafego.meta.dominio import referencia_opaca_conta
        resolvedor = ResolvedorAtivosMeta(GraphInativo())  # type: ignore[arg-type]
        with pytest.raises(ErroDeNascimentoMeta) as erro:
            await resolvedor.inventariar(
                referencia_opaca_conta('123456789'), SegredoEfemero('token-meta-falso-seguro'))
        assert erro.value.codigo == 'META_ACCOUNT_NOT_ACTIVE'

    asyncio.run(cenario())


class _SupabaseFake:
    enabled = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(self, funcao: str, argumentos: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((funcao, argumentos))
        return {'step_ref': 'passo_meta_01', 'state': 'DESPACHAR'}


def test_adapter_persistente_fica_fechado_por_flag_e_vincula_ator(monkeypatch) -> None:
    async def cenario() -> None:
        supa = _SupabaseFake()
        registro = RegistroSagaMetaSupabase(supa)  # type: ignore[arg-type]
        monkeypatch.delenv('META_CREATE_LEDGER_WRITE_ENABLED', raising=False)
        with pytest.raises(ErroDeNascimentoMeta) as erro:
            await registro.preparar_passo(
                plano_sha256='a' * 64, approval_id='approval-01', ator='operador-01',
                nome='campaign', payload_sha256='b' * 64)
        assert erro.value.codigo == 'META_CREATE_LEDGER_WRITE_BLOCKED'
        assert supa.calls == []

        monkeypatch.setenv('META_CREATE_LEDGER_WRITE_ENABLED', '1')
        passo = await registro.preparar_passo(
            plano_sha256='a' * 64, approval_id='approval-01', ator='operador-01',
            nome='campaign', payload_sha256='b' * 64)
        assert passo.estado == 'DESPACHAR'
        assert supa.calls[0][1]['p_actor_id'] == 'operador-01'
    asyncio.run(cenario())


def test_read_model_sem_migration_e_estado_nomeado_em_vez_de_500() -> None:
    class SupaSemSchema:
        enabled = True

        async def select(self, *_args, **_kwargs):
            request = httpx.Request('GET', 'https://database.example/rest/v1/tabela')
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError('not found', request=request, response=response)

    async def cenario() -> None:
        repo = RepositorioMetaReadModelSupabase(SupaSemSchema())
        contas = await repo.contas()
        recibo = await repo.ultimo_recibo()
        assert contas == {
            'ok': True, 'has_snapshot': False, 'contas': [],
            'motivo': 'meta_schema_not_applied',
        }
        assert recibo['has_snapshot'] is False
        assert recibo['motivo'] == 'meta_schema_not_applied'

    asyncio.run(cenario())
