from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.trafego.meta.draft_media_authority import check_draft_upload
from app.routers import trafego_meta_ativos as rota
from test_meta_revisao_de_midia import setup, _client, _payload


@pytest.mark.anyio
async def test_authority_rpc_is_official_and_exact():
    ref,master=uuid4(),uuid4()
    service=SimpleNamespace(base='https://database.agenciavolc.com.br',enabled=True,rpc=AsyncMock(return_value={'allowed':True}))
    assert (await check_draft_upload('owner',ref,'metaacct_test',[str(master)],service))['allowed']
    service.rpc.assert_awaited_once_with('trafego_meta_draft_upload_check',{'p_owner_id':'owner','p_draft_ref':str(ref),'p_account_ref':'metaacct_test','p_master_refs':[str(master)]})
    service.rpc.reset_mock()
    assert not (await check_draft_upload('owner',ref,'metaacct_test',[],service))['allowed']
    service.rpc.assert_not_awaited()
    service.base='https://wrong.example'
    with pytest.raises(RuntimeError): await check_draft_upload('owner',ref,'metaacct_test',[str(master)],service)


@pytest.mark.anyio
async def test_draft_never_falls_back_to_account_flag(monkeypatch):
    monkeypatch.setattr(rota.capacidades_meta,'upload_de_ativo_liberado',lambda _:True)
    checker=AsyncMock(return_value={'allowed':False})
    monkeypatch.setattr(rota,'check_draft_upload',checker)
    assert not (await rota._upload_authority('owner','account',uuid4(),[str(uuid4())]))['allowed']
    assert (await rota._upload_authority('owner','account'))['allowed']


def test_revocation_after_inspection_stops_before_credential_access(setup,monkeypatch):
    client=_client(monkeypatch,setup)
    checker=AsyncMock(side_effect=[{'allowed':True},{'allowed':False}])
    token=AsyncMock(side_effect=AssertionError('Must not read credentials'))
    monkeypatch.setattr(rota,'check_draft_upload',checker)
    monkeypatch.setattr(rota,'credencial_operacional',token)
    body={**_payload(setup),'draft_ref':str(uuid4())}
    result=client.post('/api/trafego/meta/ativos/registrar',json=body)
    assert result.status_code==409 and result.json()['detail']['codigo']=='META_ASSET_UPLOAD_BLOCKED'
    assert checker.await_count==2
    assert all(call.args[0]=='owner' for call in checker.await_args_list)
    token.assert_not_awaited()


def test_draft_capability_uses_grant_even_when_account_closed(setup,monkeypatch):
    monkeypatch.setattr(rota,'_media_schema_ready',AsyncMock(return_value=True))
    client=_client(monkeypatch,setup)
    monkeypatch.setattr(rota.capacidades_meta,'upload_de_ativo_liberado',lambda _:False)
    checker=AsyncMock(return_value={'allowed':True,'scope':'DRAFT_SELECTED_MEDIA_ONLY'})
    monkeypatch.setattr(rota,'check_draft_upload',checker)
    ref,master=str(uuid4()),str(uuid4())
    result=client.get('/api/trafego/meta/ativos/capacidades',params={'account_ref':'metaacct_example','draft_ref':ref,'master_refs':master})
    assert result.status_code==200 and result.json()['registro_de_imagem']=='ENABLED'
    assert result.json()['escopo_do_envio']=='DRAFT_SELECTED_MEDIA_ONLY'
    assert checker.await_args.args[0]=='owner'


def test_grant_without_schema_does_not_enable_upload(setup,monkeypatch):
    client=_client(monkeypatch,setup)
    monkeypatch.setattr(rota,'check_draft_upload',AsyncMock(return_value={'allowed':True}))
    monkeypatch.setattr(rota,'_media_schema_ready',AsyncMock(return_value=False))
    result=client.get('/api/trafego/meta/ativos/capacidades',params={'account_ref':'metaacct_example','draft_ref':str(uuid4()),'master_refs':str(uuid4())})
    assert result.status_code==200
    assert result.json()['registro_de_imagem']=='BLOCKED_SCHEMA_UNAVAILABLE'
    assert result.json()['registro_duravel_disponivel'] is False


@pytest.mark.anyio
async def test_missing_media_rpc_has_actionable_code_without_private_body():
    import httpx
    from app.trafego.meta_execucao.registro_de_midia import LivroDeRegistroDeMidiaSupabase, ErroDeRegistroDeMidia
    response=httpx.Response(404,json={'message':'private database details'},request=httpx.Request('POST','https://database.agenciavolc.com.br/rest/v1/rpc/missing'))
    service=SimpleNamespace(enabled=True,base='https://database.agenciavolc.com.br',rpc=AsyncMock(side_effect=httpx.HTTPStatusError('private',request=response.request,response=response)))
    book=LivroDeRegistroDeMidiaSupabase(service,autorizar_escrita=AsyncMock(return_value=True))
    with pytest.raises(ErroDeRegistroDeMidia) as exc:
        await book.reservar(account_ref='metaacct_test',content_sha256='a'*64,ator='owner',master_ref='master')
    assert exc.value.codigo=='META_ASSET_SCHEMA_REQUIRED'
    assert 'private' not in str(exc.value)


def test_missing_authority_is_recoverable_not_silent(setup,monkeypatch):
    client=_client(monkeypatch,setup)
    monkeypatch.setattr(rota,'check_draft_upload',AsyncMock(side_effect=RuntimeError('private error')))
    response=client.get('/api/trafego/meta/ativos/capacidades',params={'account_ref':'metaacct_example','draft_ref':str(uuid4()),'master_refs':str(uuid4())})
    assert response.status_code==503
    assert response.json()['detail']['codigo']=='META_DRAFT_UPLOAD_AUTHORITY_UNAVAILABLE'
    assert 'private error' not in response.text
