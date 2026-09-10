"""Owner-scoped pack library with immutable revisions. No provider calls or launch approval."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.criativo.persistencia import ConflitoDeChave

TABLE = 'criativo_reuso_pack'
DRAFT_TABLE = 'trafego_meta_rascunho_pack'
REVISION_TABLE = 'criativo_reuso_pack_revision'


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


class PedidoSelecaoPack(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pack_id: UUID
    expected_version: int = Field(ge=0)


class PedidoAdicionarAssets(BaseModel):
    model_config = ConfigDict(extra='forbid')
    master_refs: list[UUID] = Field(min_length=1, max_length=10)
    expected_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


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


async def _snapshot_assets(repo, owner, master_refs):
    items = []
    for ref in sorted({str(x) for x in master_refs}):
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
    return items


async def salvar_assets(repo, owner, pedido):
    return await guardar(repo, owner, pedido.nome, await _snapshot_assets(repo, owner, pedido.master_refs))


async def adicionar_assets(repo, owner, pack_id, pedido):
    pack = await _pack_do_dono(repo, owner, pack_id)
    if not pack or pack['manifest'].get('source') != 'STUDIO':
        raise ValueError('Escolha um pack de imagens do seu Estúdio.')
    if pack['manifest_sha256'] != pedido.expected_manifest_sha256:
        raise ValueError('O pack mudou em outra aba. Atualize antes de adicionar imagens.')
    existentes = {item['master_ref'] for item in pack['manifest']['items']}
    novas = sorted({str(ref) for ref in pedido.master_refs} - existentes)
    if len(existentes) + len(novas) > 10:
        raise ValueError('Um pack comporta até 10 imagens. Crie outro pack para as demais.')
    if not novas:
        return dto(pack)
    items = await _snapshot_assets(repo, owner, novas)
    manifest = {**pack['manifest'], 'items': [*pack['manifest']['items'], *items]}
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    result = await repo._req('POST', 'rpc/criativo_reuso_pack_append', headers=repo._headers(), json={
        'p_owner_id': str(owner), 'p_pack_id': str(pack_id),
        'p_expected_manifest_sha256': pedido.expected_manifest_sha256,
        'p_manifest_canonical': canonical,
    })
    if not result or not result.get('ok'):
        raise ValueError('O pack mudou em outra aba ou não está disponível. Atualize antes de adicionar imagens.')
    return dto(result['pack'])


async def selecionar_assets(repo, owner, pack_id, manifest_sha256=None):
    pack = await _pack_do_dono(repo, owner, pack_id, manifest_sha256)
    if not pack:
        raise ValueError('Pack não encontrado para sua conta.')
    manifest = pack['manifest']
    if manifest['source'] != 'STUDIO':
        raise ValueError('Este pack registra anúncios Meta. Reuso do post exige conferência na conta de destino.')
    refs = []
    for item in manifest['items']:
        master = await repo.buscar_master_do_dono(item['master_ref'], criado_por=owner)
        if not master or master.get('kind') != 'imagem' or master.get('arquivado_em') or master.get('content_hash') != item['content_hash']:
            raise ValueError('Uma peça do pack mudou ou não está disponível. Nenhuma peça foi enviada.')
        refs.append(item['master_ref'])
    return {'master_refs': refs, 'launch_authorized': False, 'scope': 'DRAFT_MEDIA_ONLY'}


def selecao_dto(row, *, pack_name):
    return {
        'draft_ref': row['draft_ref'], 'adset_key': row['adset_key'],
        'pack_id': row['pack_id'], 'pack_name': pack_name,
        'manifest_sha256': row['manifest_sha256'],
        'master_refs': row['master_refs'], 'version': row['version'],
        'state': 'LOCKED', 'selected_at': row['selected_at'],
        'launch_authorized': False, 'scope': 'DRAFT_MEDIA_ONLY',
    }


async def _pack_do_dono(repo, owner, pack_id, manifest_sha256=None):
    rows = await repo._get(TABLE, {
        'id': f'eq.{pack_id}', 'owner_id': f'eq.{owner}', 'limit': 1})
    if not rows:
        return None
    if not manifest_sha256 or rows[0]['manifest_sha256'] == manifest_sha256:
        return rows[0]
    versions = await repo._get(REVISION_TABLE, {'pack_id': f'eq.{pack_id}',
        'owner_id': f'eq.{owner}', 'manifest_sha256': f'eq.{manifest_sha256}', 'limit': 1})
    return {**versions[0], 'id': str(pack_id)} if versions else None


async def listar_selecoes_do_rascunho(repo, owner, draft_ref):
    rows = await repo._get(DRAFT_TABLE, {
        'owner_id': f'eq.{owner}', 'draft_ref': f'eq.{draft_ref}',
        'order': 'adset_key.asc'})
    saida = []
    for row in rows:
        pack = await _pack_do_dono(repo, owner, row['pack_id'])
        if not pack:
            # A FK torna isto impossível no estado íntegro. Falhar fechado evita
            # desenhar um vínculo que o operador não consegue conferir.
            raise ValueError('Um vínculo do rascunho aponta para um pack indisponível.')
        saida.append(selecao_dto(row, pack_name=pack['nome']))
    return {'draft_ref': str(draft_ref), 'selections': saida}


async def fixar_pack_no_conjunto(repo, owner, draft_ref, adset_key, pedido):
    pack = await _pack_do_dono(repo, owner, str(pedido.pack_id))
    if not pack:
        raise ValueError('Pack não encontrado para sua conta.')
    selecao = await selecionar_assets(repo, owner, str(pedido.pack_id), pack['manifest_sha256'])
    atuais = await repo._get(DRAFT_TABLE, {
        'owner_id': f'eq.{owner}', 'draft_ref': f'eq.{draft_ref}',
        'adset_key': f'eq.{adset_key}', 'limit': 1})
    base = {
        'pack_id': str(pedido.pack_id),
        'manifest_sha256': pack['manifest_sha256'],
        'master_refs': selecao['master_refs'],
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    if not atuais:
        if pedido.expected_version != 0:
            raise ValueError('A seleção mudou em outra aba. Atualize antes de escolher novamente.')
        try:
            row = await repo._inserir(DRAFT_TABLE, {
                'owner_id': owner, 'draft_ref': str(draft_ref),
                'adset_key': adset_key, 'version': 1,
                'selected_at': base['updated_at'], **base,
            })
        except ConflitoDeChave as exc:
            raise ValueError('A seleção mudou em outra aba. Atualize antes de escolher novamente.') from exc
    else:
        atual = atuais[0]
        if int(atual['version']) != pedido.expected_version:
            raise ValueError('A seleção mudou em outra aba. Atualize antes de escolher novamente.')
        linhas = await repo._atualizar(DRAFT_TABLE, {
            'id': f'eq.{atual["id"]}', 'owner_id': f'eq.{owner}',
            'version': f'eq.{pedido.expected_version}',
        }, {**base, 'version': pedido.expected_version + 1})
        if not linhas:
            raise ValueError('A seleção mudou em outra aba. Atualize antes de escolher novamente.')
        row = linhas[0]
    return selecao_dto(row, pack_name=pack['nome'])


async def retirar_pack_do_conjunto(repo, owner, draft_ref, adset_key, expected_version):
    linhas = await repo._apagar(DRAFT_TABLE, {
        'owner_id': f'eq.{owner}', 'draft_ref': f'eq.{draft_ref}',
        'adset_key': f'eq.{adset_key}', 'version': f'eq.{expected_version}',
    })
    if not linhas:
        raise ValueError('A seleção mudou em outra aba. Atualize antes de retirar o pack.')
    return {'draft_ref': str(draft_ref), 'adset_key': adset_key, 'state': 'REMOVED'}
