"""Immutable, owner-scoped reuse snapshots. No provider calls or launch approval."""
import hashlib
import json
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.criativo.persistencia import ConflitoDeChave

TABLE = 'criativo_reuso_pack'


class PedidoPackMeta(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conta_ref: str = Field(pattern=r'^[A-Za-z0-9:_-]{8,180}$')
    campanha_ref: str = Field(pattern=r'^[A-Za-z0-9:_-]{8,180}$')
    referencia: str = Field(pattern=r'^[A-Za-z0-9:_-]{8,180}$')
    entidade: Literal['conjunto', 'anuncio']
    nome: str = Field(min_length=1, max_length=120)


async def inventario_completo(meta, entity, account):
    items, cursors, cursor = [], set(), None
    for _ in range(100):
        page = await meta.listar(entity, account, cursor=cursor, tamanho=200)
        if page.get('estado') != 'COM_SNAPSHOT':
            raise ValueError('A leitura da hierarquia está indisponível; nenhum pack foi salvo.')
        items.extend(page.get('items', []))
        if page.get('completo') is True:
            return items
        cursor = page.get('proximo_cursor')
        if not cursor or cursor in cursors:
            break
        cursors.add(cursor)
    raise ValueError('A hierarquia está incompleta. Atualize a leitura antes de salvar.')


async def salvar_meta(repo, meta, owner, pedido):
    from app.trafego.meta.gestao import PedidoDeGestaoMeta, alvo_validado
    # Same server-side hierarchy checks as management, without Meta transport.
    target = await alvo_validado(meta, PedidoDeGestaoMeta(
        **pedido.model_dump(exclude={'nome'}), nome=pedido.nome,
        acao='DUPLICAR_ANUNCIO' if pedido.entidade == 'anuncio' else 'DUPLICAR_CONJUNTO'))
    ads = [target] if pedido.entidade == 'anuncio' else [
        x for x in await inventario_completo(meta, 'anuncios', pedido.conta_ref)
        if x.get('meta_adset_id') == target['meta_adset_id']]
    if not 1 <= len(ads) <= 10:
        raise ValueError('Escolha de 1 a 10 anúncios por pack; conjuntos maiores devem ser divididos.')
    bindings = await inventario_completo(meta, 'vinculos', pedido.conta_ref)
    items = []
    for ad in sorted(ads, key=lambda x: x['meta_ad_id']):
        links = [x for x in bindings if x.get('meta_ad_id') == ad['meta_ad_id']]
        ids = {x.get('meta_creative_id') for x in links}
        if len(ids) != 1 or None in ids:
            raise ValueError('A peça de um anúncio não foi identificada de forma única; atualize a leitura.')
        items.append({'account_ref': pedido.conta_ref, 'campaign_ref': pedido.campanha_ref,
                      'adset_ref': ad['meta_adset_id'], 'ad_ref': ad.get('entity_ref'),
                      'creative_ref': next(iter(ids)), 'nome': ad.get('nome'),
                      'observado_em': ad.get('observado_em'), 'post_ref': None,
                      'post_identity': 'NOT_OBSERVED', 'scope': 'READ_MODEL_REFERENCES'})
    return await guardar(repo, owner, pedido.nome.strip(), items, source='META_SNAPSHOT')


class PedidoPack(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nome: str = Field(min_length=1, max_length=120)
    master_refs: list[UUID] = Field(min_length=1, max_length=10)

    @field_validator('nome')
    @classmethod
    def nome_valido(cls, value):
        if not value.strip():
            raise ValueError('Dê um nome ao pack.')
        return value.strip()


def dto(row):
    return {k: row[k] for k in ('id', 'nome', 'manifest', 'manifest_sha256', 'created_at')}


async def guardar(repo, owner, nome, items, *, source='STUDIO'):
    manifest = {'version': 'creative-pack-v1', 'nome': nome, 'source': source,
                'items': items, 'launch_authorized': False,
                'post_reuse': 'REQUIRES_ACCOUNT_AND_POST_VERIFICATION',
                'revenue_grain': 'ADSET'}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()
    try:
        row = await repo._inserir(TABLE, {'owner_id': owner, 'nome': nome,
                                         'manifest': manifest, 'manifest_sha256': digest})
    except ConflitoDeChave:
        rows = await repo._get(TABLE, {'owner_id': f'eq.{owner}',
                                      'manifest_sha256': f'eq.{digest}', 'limit': 1})
        if not rows:
            raise
        row = rows[0]
    return dto(row)


async def salvar_assets(repo, owner, pedido):
    items = []
    for ref in sorted({str(x) for x in pedido.master_refs}):
        master = await repo.buscar_master_do_dono(ref, criado_por=owner)
        if not master or master.get('arquivado_em') or master.get('kind') != 'imagem':
            raise ValueError('Uma peça não está disponível para sua conta. Atualize a seleção.')
        # Whitelist: no storage paths, signed URLs, credentials or sensitive prompts.
        item = {k: master.get(k) for k in ('job_id', 'slot', 'content_hash', 'mime',
                                          'largura', 'altura', 'versao', 'raiz_id')}
        item['master_ref'] = ref
        bridges = await repo._get('criativo_agente_peca_job', {
            'owner_id': f'eq.{owner}', 'job_id': f'eq.{master["job_id"]}',
            'select': 'project_ref,run_ref,creative_ref,copy_ref,group_ref', 'limit': 2})
        if len(bridges) > 1:
            raise ValueError('A origem da peça está ambígua; nenhuma seleção foi salva.')
        item['strategy'] = bridges[0] if bridges else None
        item['copy_snapshot'] = None
        if bridges:
            bridge = bridges[0]
            runs = await repo._get('criativo_agente_run', {
                'owner_id': f'eq.{owner}', 'run_ref': f'eq.{bridge["run_ref"]}',
                'project_ref': f'eq.{bridge["project_ref"]}', 'status': 'eq.COMPLETED',
                'select': 'output', 'limit': 1})
            from app.criativo.agente.contrato import CopyCompartilhada
            copies = [c for c in (runs[0].get('output') or {}).get('copies_compartilhadas', [])
                      if c.get('ref') == bridge['copy_ref']] if runs else []
            if len(copies) != 1 or copies[0].get('group_ref') != bridge['group_ref']:
                raise ValueError('A copy de origem não pôde ser conferida. Nenhum pack foi salvo.')
            try:
                copy = CopyCompartilhada.model_validate(copies[0]).model_dump(mode='json')
            except ValueError:
                raise ValueError('A copy de origem está fora do contrato.') from None
            item['copy_snapshot'] = copy
            item['copy_scope'] = 'REFERENCE_NOT_APPROVAL'
        items.append(item)
    return await guardar(repo, owner, pedido.nome, items)


async def selecionar_assets(repo, owner, pack_id):
    rows = await repo._get(TABLE, {'id': f'eq.{pack_id}', 'owner_id': f'eq.{owner}', 'limit': 1})
    if not rows:
        raise ValueError('Pack não encontrado para sua conta.')
    manifest = rows[0]['manifest']
    if manifest['source'] != 'STUDIO':
        raise ValueError('Este pack registra anúncios Meta. Reuso do post exige conferência na conta de destino.')
    refs = []
    for item in manifest['items']:
        master = await repo.buscar_master_do_dono(item['master_ref'], criado_por=owner)
        if not master or master.get('kind') != 'imagem' or master.get('arquivado_em') or master.get('content_hash') != item['content_hash']:
            raise ValueError('Uma peça do pack mudou ou não está disponível. Nenhuma peça foi enviada.')
        refs.append(item['master_ref'])
    return {'master_refs': refs, 'launch_authorized': False, 'scope': 'DRAFT_MEDIA_ONLY'}
