import hashlib
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from app.criativo.packs import PedidoAdicionarAssets, PedidoPack, adicionar_assets, salvar_assets, selecionar_assets
from test_creative_reuse_packs import Repo, OWNER, MASTER


class AppendRepo(Repo):
    def __init__(self):
        super().__init__()
        self.extra = str(uuid4())
        self.revisions = []
        self.cas_calls = 0
    def _headers(self): return {}
    async def buscar_master_do_dono(self, ref, *, criado_por):
        if criado_por == OWNER and ref == self.extra:
            return {**self.master, 'id': ref, 'content_hash': 'sha256:' + 'b' * 64}
        return await super().buscar_master_do_dono(ref, criado_por=criado_por)
    async def _get(self, table, params):
        if table == 'criativo_reuso_pack_revision':
            return [r for r in self.revisions if all(str(r.get(k)) == v[3:] for k,v in params.items() if str(v).startswith('eq.'))]
        return await super()._get(table, params)
    async def _req(self, method, path, *, headers, json):
        import json as codec
        self.cas_calls += 1
        row = next(r for r in self.rows if r['id'] == json['p_pack_id'])
        assert json['p_owner_id'] == OWNER
        if row['manifest_sha256'] != json['p_expected_manifest_sha256']:
            return {'ok': False}
        self.revisions.append({**deepcopy(row), 'pack_id': row['id']})
        row['manifest'] = codec.loads(json['p_manifest_canonical'])
        row['manifest_sha256'] = hashlib.sha256(json['p_manifest_canonical'].encode()).hexdigest()
        return {'ok': True, 'pack': row}


@pytest.mark.asyncio
async def test_append_preserves_old_snapshot_and_deduplicates():
    repo = AppendRepo()
    pack = await salvar_assets(repo, OWNER, PedidoPack(nome='Pack', master_refs=[MASTER]))
    original = deepcopy(pack)
    result = await adicionar_assets(repo, OWNER, pack['id'], PedidoAdicionarAssets(
        master_refs=[MASTER, repo.extra, repo.extra], expected_manifest_sha256=pack['manifest_sha256']))
    assert result['id'] == original['id']
    assert len(result['manifest']['items']) == 2
    assert result['manifest']['items'][0] == original['manifest']['items'][0]
    assert (await selecionar_assets(repo, OWNER, pack['id'], original['manifest_sha256']))['master_refs'] == [MASTER]
    assert (await selecionar_assets(repo, OWNER, pack['id']))['master_refs'] == [MASTER, repo.extra]
    again = await adicionar_assets(repo, OWNER, pack['id'], PedidoAdicionarAssets(
        master_refs=[repo.extra], expected_manifest_sha256=result['manifest_sha256']))
    assert again == result and repo.cas_calls == 1


@pytest.mark.asyncio
async def test_append_refuses_foreign_master_owner_and_stale_manifest():
    repo = AppendRepo()
    pack = await salvar_assets(repo, OWNER, PedidoPack(nome='Pack', master_refs=[MASTER]))
    for owner, refs, digest in [(str(uuid4()), [repo.extra], pack['manifest_sha256']),
            (OWNER, [str(uuid4())], pack['manifest_sha256']), (OWNER, [repo.extra], 'f' * 64)]:
        with pytest.raises(ValueError):
            await adicionar_assets(repo, owner, pack['id'], PedidoAdicionarAssets(master_refs=refs, expected_manifest_sha256=digest))
    assert repo.cas_calls == 0


@pytest.mark.asyncio
async def test_append_limit_is_combined_with_existing_items():
    repo = AppendRepo()
    pack = await salvar_assets(repo, OWNER, PedidoPack(nome='Pack', master_refs=[MASTER]))
    repo.rows[0]['manifest']['items'] += [{'master_ref': str(uuid4())} for _ in range(9)]
    with pytest.raises(ValueError, match='10 imagens'):
        await adicionar_assets(repo, OWNER, pack['id'], PedidoAdicionarAssets(master_refs=[repo.extra], expected_manifest_sha256=pack['manifest_sha256']))
    assert repo.cas_calls == 0


@pytest.mark.asyncio
async def test_name_search_is_owner_scoped_paginated_and_escapes_wildcards():
    from app.routers.criativos_packs import listar
    from types import SimpleNamespace
    class SearchRepo:
        async def _get(self, table, params):
            assert table == 'criativo_reuso_pack'
            assert params == {'owner_id': f'eq.{OWNER}', 'order': 'created_at.desc,id.asc',
                'limit': 21, 'offset': 20, 'nome': r'ilike.%50\%\_\*%'}
            return []
    result = await listar(SimpleNamespace(sub=OWNER), SearchRepo(), 20, ' 50%_* ')
    assert result == {'packs': [], 'has_more': False}


@pytest.mark.asyncio
async def test_concurrent_append_cas_refusal_never_claims_success():
    class RacingRepo(AppendRepo):
        async def _req(self, *args, **kwargs): return {'ok': False, 'code': 'PACK_CHANGED'}
    repo = RacingRepo()
    pack = await salvar_assets(repo, OWNER, PedidoPack(nome='Pack', master_refs=[MASTER]))
    with pytest.raises(ValueError, match='outra aba'):
        await adicionar_assets(repo, OWNER, pack['id'], PedidoAdicionarAssets(master_refs=[repo.extra], expected_manifest_sha256=pack['manifest_sha256']))
    assert len(repo.rows[0]['manifest']['items']) == 1
