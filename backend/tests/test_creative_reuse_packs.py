from copy import deepcopy
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.criativo.packs import (
    PedidoPack, PedidoSelecaoPack, fixar_pack_no_conjunto, guardar,
    inventario_completo, listar_selecoes_do_rascunho, retirar_pack_do_conjunto,
    salvar_assets, selecionar_assets,
)
from app.criativo.packs import PedidoPackMeta, salvar_meta
from app.criativo.persistencia import ConflitoDeChave
from app.trafego.meta.gestao import PedidoDeGestaoMeta, planejar_gestao

OWNER = str(uuid4())
MASTER = str(uuid4())

class Repo:
    def __init__(self):
        self.master = {'id': MASTER, 'job_id': str(uuid4()), 'kind': 'imagem',
                       'content_hash': 'sha256:' + 'a' * 64, 'storage_chave': 'NEVER_EXPOSE'}
        self.rows = []
    async def buscar_master_do_dono(self, ref, *, criado_por):
        return self.master if criado_por == OWNER and ref == MASTER else None
    async def _inserir(self, table, row):
        if table == 'criativo_reuso_pack' and any(
            r.get('owner_id') == row['owner_id']
            and r.get('manifest_sha256') == row['manifest_sha256']
            and 'nome' in r for r in self.rows
        ):
            raise ConflitoDeChave()
        if table == 'trafego_meta_rascunho_pack' and any(
            r.get('owner_id') == row['owner_id']
            and r.get('draft_ref') == row['draft_ref']
            and r.get('adset_key') == row['adset_key'] for r in self.rows
        ):
            raise ConflitoDeChave()
        result = dict(row, id=str(uuid4()), created_at='2026-09-08T00:00:00Z')
        self.rows.append(result)
        return result
    async def _get(self, table, params):
        if table == 'criativo_agente_peca_job': return []
        return [r for r in self.rows if all(str(r.get(k)) == v[3:] for k, v in params.items() if str(v).startswith('eq.'))]

    async def _atualizar(self, table, params, fields):
        found = await self._get(table, params)
        for row in found: row.update(fields)
        return found

    async def _apagar(self, table, params):
        found = await self._get(table, params)
        self.rows = [row for row in self.rows if row not in found]
        return found

@pytest.mark.asyncio
async def test_pack_immutable_selection_owner_and_idempotency():
    repo = Repo(); pedido = PedidoPack(nome='Teste', master_refs=[MASTER, MASTER])
    a = await salvar_assets(repo, OWNER, pedido)
    b = await salvar_assets(repo, OWNER, pedido)
    assert a['id'] == b['id'] and len(repo.rows) == 1
    assert len(a['manifest']['items']) == 1
    assert a['manifest']['launch_authorized'] is False
    assert 'NEVER_EXPOSE' not in str(a) and OWNER not in str(a)
    assert (await selecionar_assets(repo, OWNER, a['id']))['master_refs'] == [MASTER]
    with pytest.raises(ValueError): await selecionar_assets(repo, str(uuid4()), a['id'])
    repo.master['content_hash'] = 'sha256:' + 'b' * 64
    with pytest.raises(ValueError): await selecionar_assets(repo, OWNER, a['id'])

@pytest.mark.asyncio
async def test_foreign_or_archived_master_never_creates_pack():
    repo = Repo(); pedido = PedidoPack(nome='Teste', master_refs=[MASTER])
    with pytest.raises(ValueError): await salvar_assets(repo, 'other', pedido)
    repo.master['arquivado_em'] = '2026-09-08'
    with pytest.raises(ValueError): await salvar_assets(repo, OWNER, pedido)
    assert not repo.rows


@pytest.mark.asyncio
async def test_pack_binding_is_durable_per_adset_and_versioned():
    repo = Repo()
    pack = await salvar_assets(repo, OWNER, PedidoPack(nome='Pack A', master_refs=[MASTER]))
    draft = uuid4()
    first = await fixar_pack_no_conjunto(
        repo, OWNER, draft, 'adset-001',
        PedidoSelecaoPack(pack_id=pack['id'], expected_version=0),
    )
    second = await fixar_pack_no_conjunto(
        repo, OWNER, draft, 'adset-002',
        PedidoSelecaoPack(pack_id=pack['id'], expected_version=0),
    )
    assert first['version'] == second['version'] == 1
    listed = await listar_selecoes_do_rascunho(repo, OWNER, draft)
    assert [item['adset_key'] for item in listed['selections']] == ['adset-001', 'adset-002']
    assert all(item['state'] == 'LOCKED' for item in listed['selections'])

    with pytest.raises(ValueError, match='outra aba'):
        await fixar_pack_no_conjunto(
            repo, OWNER, draft, 'adset-001',
            PedidoSelecaoPack(pack_id=pack['id'], expected_version=0),
        )
    removed = await retirar_pack_do_conjunto(repo, OWNER, draft, 'adset-001', 1)
    assert removed['state'] == 'REMOVED'
    assert [item['adset_key'] for item in
            (await listar_selecoes_do_rascunho(repo, OWNER, draft))['selections']] == ['adset-002']

@pytest.mark.asyncio
async def test_changed_kind_is_not_valid_image_selection():
    repo = Repo()
    p = await salvar_assets(repo, OWNER, PedidoPack(nome='Teste', master_refs=[MASTER]))
    repo.master['kind'] = 'video'
    with pytest.raises(ValueError): await selecionar_assets(repo, OWNER, p['id'])

@pytest.mark.asyncio
async def test_strategy_copy_is_snapshotted_without_inheriting_approval():
    copy = {'ref':'copy_primeira','group_ref':'group_primeiro','texto_principal':'Texto de origem',
            'titulo':'Titulo','descricao':'Descricao','cta_nativa':'LEARN_MORE','fato_refs':['fact_um']}
    class WithStrategy(Repo):
        async def _get(self, table, params):
            if table == 'criativo_agente_peca_job':
                assert params['owner_id'] == f'eq.{OWNER}'
                return [{'project_ref':'project','run_ref':'run','copy_ref':'copy_primeira',
                         'creative_ref':'creative_um','group_ref':'group_primeiro'}]
            if table == 'criativo_agente_run':
                assert params['owner_id'] == f'eq.{OWNER}' and params['status'] == 'eq.COMPLETED'
                return [{'output':{'copies_compartilhadas':[copy]}}]
            return await super()._get(table, params)
    repo = WithStrategy()
    p = await salvar_assets(repo, OWNER, PedidoPack(nome='Teste', master_refs=[MASTER]))
    assert p['manifest']['items'][0]['copy_snapshot']['texto_principal'] == 'Texto de origem'
    assert p['manifest']['items'][0]['copy_scope'] == 'REFERENCE_NOT_APPROVAL'
    assert p['manifest']['launch_authorized'] is False

def test_pack_routes_require_authentication():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers.criativos_packs import router
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as cli:
        assert cli.get('/api/criativos/meta/agente/packs').status_code == 401
        assert cli.get(f'/api/criativos/meta/agente/packs/{MASTER}').status_code == 401
        assert cli.post('/api/criativos/meta/agente/packs',json={'nome':'Teste','master_refs':[MASTER]}).status_code == 401

@pytest.mark.asyncio
async def test_pack_detail_is_owner_scoped_and_does_not_expose_storage():
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.routers.criativos_packs import detalhe
    repo = Repo()
    p = await salvar_assets(repo, OWNER, PedidoPack(nome='Pack', master_refs=[MASTER]))
    detail = await detalhe(p['id'], SimpleNamespace(sub=OWNER), repo)
    assert detail == p
    assert 'owner_id' not in detail and 'storage_chave' not in str(detail)
    with pytest.raises(HTTPException) as error:
        await detalhe(p['id'], SimpleNamespace(sub=str(uuid4())), repo)
    assert error.value.status_code == 404

@pytest.mark.asyncio
async def test_meta_pack_uses_exact_validated_snapshot_without_second_target_read():
    class Meta:
        reads = 0
        async def detalhe(self, entity, ref, account):
            if entity == 'campanhas': return {'estado':'COM_SNAPSHOT','item':{'meta_campaign_id':'campaign_a'}}
            if entity == 'conjuntos': return {'estado':'COM_SNAPSHOT','item':{'meta_campaign_id':'campaign_a' if ref == 'adset_one' else 'campaign_b'}}
            self.reads += 1
            return {'estado':'COM_SNAPSHOT','item':{'meta_ad_id':'ad_one','entity_ref':'anuncio_one','status':'ACTIVE','meta_adset_id':'adset_one' if self.reads == 1 else 'adset_two'}}
        async def listar(self, *a, **kw):
            return {'estado':'COM_SNAPSHOT','completo':True,'items':[{'meta_ad_id':'ad_one','meta_creative_id':'creative_one'}]}
    meta = Meta(); repo = Repo()
    p = await salvar_meta(repo, meta, OWNER, PedidoPackMeta(conta_ref='account_one', campanha_ref='campaign_a', referencia='anuncio_one', entidade='anuncio', nome='Pack'))
    assert meta.reads == 1
    assert p['manifest']['items'][0]['adset_ref'] == 'adset_one'
    assert p['manifest']['items'][0]['post_ref'] is None

@pytest.mark.parametrize('patch', [{'nome':' '}, {'master_refs':[]}, {'master_refs':['bad']},
                                 {'master_refs':[str(uuid4()) for _ in range(11)]}, {'launch_authorized':True}])
def test_invalid_payloads(patch):
    with pytest.raises(ValidationError): PedidoPack(**dict({'nome':'Teste', 'master_refs':[MASTER]}, **patch))

@pytest.mark.asyncio
async def test_meta_snapshot_cannot_be_selected_as_studio_assets():
    repo = Repo()
    p = await guardar(repo, OWNER, 'Referencia', [{'ad_ref':'ad'}], source='META_SNAPSHOT')
    with pytest.raises(ValueError, match='post'): await selecionar_assets(repo, OWNER, p['id'])

@pytest.mark.asyncio
async def test_repeated_cursor_and_incomplete_page_fail_closed():
    class Meta:
        async def listar(self, *args, **kw):
            return {'estado':'COM_SNAPSHOT','items':[], 'completo':False,'proximo_cursor':'same'}
    with pytest.raises(ValueError, match='incompleta'): await inventario_completo(Meta(), 'anuncios', 'account')

class Hierarchy:
    def __init__(self):
        self.items = {'campanhas': {'meta_campaign_id':'campaign'},
                      'conjuntos': {'meta_campaign_id':'campaign', 'meta_adset_id':'adset'},
                      'anuncios': {'meta_adset_id':'adset','status':'ACTIVE', 'nome':'Anuncio'}}
    async def detalhe(self, entity, ref, account):
        return {'estado':'COM_SNAPSHOT', 'item':deepcopy(self.items[entity])}

@pytest.mark.asyncio
async def test_ad_actions_validate_parent_and_never_transfer_revenue():
    repo = Hierarchy()
    pedido = PedidoDeGestaoMeta(conta_ref='account_ref', campanha_ref='campaign_ref', entidade='anuncio',
                               referencia='ad_reference', acao='DUPLICAR_ANUNCIO', nome='Copia')
    result = await planejar_gestao(repo, pedido, ator=OWNER)
    assert result['executavel'] is False and result['depois']['status'] == 'PAUSED'
    assert result['depois']['incluir_anuncios'] is False
    repo.items['conjuntos']['meta_campaign_id'] = 'another'
    with pytest.raises(ValueError, match='campanha aberta'): await planejar_gestao(repo, pedido, ator=OWNER)

@pytest.mark.parametrize('action', ['LANCE','ORCAMENTO_DIARIO','DUPLICAR_CONJUNTO'])
def test_ad_never_has_own_budget_or_bid(action):
    with pytest.raises(ValidationError):
        PedidoDeGestaoMeta(conta_ref='account_ref', campanha_ref='campaign_ref', entidade='anuncio',
                          referencia='ad_reference', acao=action, valor_minor=100, nome='Copy')
