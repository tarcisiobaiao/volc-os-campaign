"""Read-only persisted selection graph. This module never calls any LLM or Meta.

Selection→immutable pack revision→owned master/job→exact completed run. It
does not search globally, fetch a page/image, or follow the latest project run.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .copy_suggestions import CopyFailure, _SECRET, _text
from .dominio import referencia_opaca_conta, ContratoMetaInvalido
from app.trafego.meta_execucao.registro_de_midia import referencia_opaca_de_imagem

MAX_CONTEXT_CHARS = 18000
_URL = re.compile(r'https?://[^\s<>"\']+', re.I)
_PII = re.compile(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|(?:\+55\s*)?\(?\d{2}\)?[ -]\d{4,5}[ -]\d{4}\b|\b\d{11}\b')
_OPAQUE = re.compile(r'\b(?:fact|rule|copy|group|state|creative|crproj|crrun|metaacct|metapage|metaasset|metapost|metareg)_[a-z0-9_-]+\b', re.I)


def clean(value, limit=600):
    if not isinstance(value, str):
        return ''
    value = _URL.sub('[endereço omitido]', value)
    value = _SECRET.sub('[credencial omitida]', value)
    value = _OPAQUE.sub('[referência omitida]', value)
    value = _PII.sub('[dado pessoal omitido]', value)
    return _text(value)[:limit].strip()


def destination_identity(value):
    """Ignore tracking only, not query arguments that identify different pages."""
    try:
        url = urlsplit(value or '')
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            return None
        tracking = {'fbclid', 'gclid', 'campaign_id', 'adset_id', 'ad_id'}
        query = [(key, val) for key, val in parse_qsl(url.query, keep_blank_values=True)
                 if not key.lower().startswith('utm_') and key.lower() not in tracking]
        host = url.hostname.lower() + (f':{url.port}' if url.port and url.port != 443 else '')
        return urlunsplit(('https', host, url.path.rstrip('/') or '/', urlencode(sorted(query)), ''))
    except (ValueError, TypeError):
        return None


def _same_destination(brief, draft):
    page = brief.get('contexto_da_pagina') or {}
    if not isinstance(page, dict):
        return False
    current = destination_identity(draft.get('destinationUrl'))
    declared = destination_identity(brief.get('url_destino'))
    if current is None or (brief.get('url_destino') and declared is None):
        return False
    if page:
        requested, final = destination_identity(page.get('url_solicitada')), destination_identity(page.get('url_final'))
        # Requested/final may differ after a recorded redirect, but BOTH the
        # saved brief and current campaign must belong to that same snapshot.
        return requested is not None and final is not None and current in {requested, final} and (declared is None or declared in {requested, final})
    return declared is not None and current == declared


def _only(rows):
    return rows[0] if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) else None


def _objects(value):
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _refs(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


class Reader:
    def __init__(self, service, owner):
        self.service, self.owner, self.cache = service, owner, {}

    async def get(self, table, filters, select):
        params = {'owner_id': f'eq.{self.owner}', **filters, 'select': select, 'limit': 2}
        key = (table, json.dumps(params, sort_keys=True))
        if key not in self.cache:
            self.cache[key] = await self.service.select(table, params)
        return self.cache[key]

    async def master(self, ref):
        key = ('master', ref)
        if key not in self.cache:
            self.cache[key] = await self.service.select('criativo_master', {
                'id': f'eq.{ref}', 'criativo_job.criado_por': f'eq.{self.owner}', 'limit': 2,
                'select': 'id,job_id,content_hash,kind,arquivado_em,criativo_job!inner(criado_por)'})
        return _only(self.cache[key])

    async def upload_matches(self, account_ref, master, asset_ref):
        """Owner receipt is checked before any physical-account lookup.

        The read-model has no account_ref column; correlate its minimal stored
        IDs with the same canonical opaque-account function used by the UI.
        No credential resolution, Meta request, image download or ID export.
        """
        params = {'account_ref': f'eq.{account_ref}', 'actor_id': f'eq.{self.owner}',
            'master_ref': f'eq.{master["id"]}', 'content_sha256': f'eq.{master["content_hash"]}',
            'state': 'eq.REGISTRADO', 'select': 'account_ref,actor_id,master_ref,content_sha256,state,image_hash', 'limit': 2}
        key = ('upload', json.dumps(params, sort_keys=True))
        if key not in self.cache:
            self.cache[key] = await self.service.select('trafego_meta_asset_registration', params)
        receipt = _only(self.cache[key])
        if (not receipt or receipt.get('account_ref') != account_ref or receipt.get('actor_id') != self.owner
                or receipt.get('master_ref') != master['id'] or receipt.get('content_sha256') != master['content_hash']
                or receipt.get('state') != 'REGISTRADO' or not isinstance(receipt.get('image_hash'), str)):
            return False
        account_key = ('physical-account', account_ref)
        if account_key not in self.cache:
            self.cache[account_key] = None
            for offset in range(0, 1000, 100):
                rows = await self.service.select('trafego_meta_ad_account', {
                    'select': 'account_external_id', 'order': 'account_external_id.asc', 'limit': 100, 'offset': offset})
                if not _objects(rows):
                    break
                for row in rows:
                    external = row.get('account_external_id')
                    if not isinstance(external, str) or not re.fullmatch(r'[0-9]{1,40}', external):
                        continue
                    if referencia_opaca_conta(external) == account_ref:
                        self.cache[account_key] = external
                        break
                if self.cache[account_key] or len(rows) < 100:
                    break
        physical = self.cache[account_key]
        return bool(physical and referencia_opaca_de_imagem(physical, receipt['image_hash']) == asset_ref)

    async def pack(self, pack_id, digest):
        current = _only(await self.get('criativo_reuso_pack', {'id': f'eq.{pack_id}'}, 'id,nome,manifest,manifest_sha256'))
        if not current:
            return None
        result = current if current.get('manifest_sha256') == digest else _only(await self.get(
            'criativo_reuso_pack_revision', {'pack_id': f'eq.{pack_id}', 'manifest_sha256': f'eq.{digest}'},
            'nome,manifest,manifest_sha256'))
        if not result:
            return None
        manifest = result.get('manifest')
        if not isinstance(manifest, dict) or not _objects(manifest.get('items')):
            return None
        canonical = json.dumps(result.get('manifest'), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return result if hashlib.sha256(canonical.encode()).hexdigest() == digest else None


def _run_context(run, bridge, draft):
    brief, output = run.get('input') or {}, run.get('output') or {}
    if not isinstance(brief, dict) or not isinstance(output, dict):
        return None, 'O briefing salvo está indisponível; ele não foi incluído.'
    if brief.get('project_ref') != bridge['project_ref'] or output.get('project_ref') != bridge['project_ref']:
        return None, 'A origem da estratégia não pôde ser confirmada; ela não foi incluída.'
    if not _same_destination(brief, draft):
        return None, 'O contexto salvo pertence a outro destino ou não possui URL vinculada; ele foi excluído.'
    malformed = 'A estratégia salva contém campos antigos ou inválidos; seu contexto foi excluído.'
    page = brief.get('contexto_da_pagina') or {}
    if (not _objects(output.get('pecas', [])) or not _objects(output.get('copies_compartilhadas', []))
            or not _objects(brief.get('fatos_da_oferta', [])) or not _objects(page.get('fatos', []))
            or not _objects(page.get('motivacoes_sugeridas', []))):
        return None, malformed
    piece = _only([item for item in output.get('pecas', []) if item.get('ref') == bridge['creative_ref']])
    copy = _only([item for item in output.get('copies_compartilhadas', []) if item.get('ref') == bridge['copy_ref']])
    if (not piece or not copy or piece.get('group_ref') != bridge['group_ref']
            or copy.get('group_ref') != bridge['group_ref'] or piece.get('shared_copy_ref') != bridge['copy_ref']):
        return None, 'Uma peça não possui estratégia e copy de origem inequívocas; contexto excluído.'
    if not _refs(piece.get('fato_refs', [])) or not _refs(copy.get('fato_refs', [])):
        return None, malformed
    refs = set(piece.get('fato_refs', [])) | set(copy.get('fato_refs', []))
    facts = [f for f in brief.get('fatos_da_oferta', []) if isinstance(f, dict) and f.get('ref') in refs][:8]
    fact_refs = {fact['ref'] for fact in facts}
    page_refs = {f.get('ref') for f in page.get('fatos', []) if isinstance(f.get('ref'), str)}
    motives = [{key: clean(item.get(key), 300) for key in ('tipo', 'hipotese', 'pergunta_latente', 'entrega_da_pagina')}
               for item in page.get('motivacoes_sugeridas', [])
               if _refs(item.get('fato_refs')) and item.get('fato_refs') and set(item['fato_refs']) <= fact_refs & page_refs][:8]
    idea, art = piece.get('big_idea') or {}, piece.get('direcao_de_arte') or {}
    if not isinstance(idea, dict) or not isinstance(art, dict):
        return None, malformed
    result = {
        'topic': clean(brief.get('assunto_principal'), 160),
        'desire_anchor': clean(brief.get('ancora_de_desejo'), 80),
        'facts_from_saved_briefing': [clean(f.get('declaracao'), 700) for f in facts],
        'motivations_hypotheses': motives,
        'strategy_hypothesis': {key: clean(piece.get(key), 400) for key in ('angulo', 'subangulo', 'hipotese', 'hook', 'headline_interna')},
        'big_idea_hypothesis': {key: clean(idea.get(key), 300) for key in ('ideia_central', 'pergunta_latente', 'promessa_do_clique', 'cena_chave')},
        'visual_summary_saved_not_inspected': clean(art.get('cena') or piece.get('direcao_visual'), 600),
        'original_copy_not_approval': {key: clean(copy.get(key), 1400) for key in ('texto_principal', 'titulo', 'descricao')},
    }
    if page:
        result['page_snapshot'] = {key: clean(page.get(key), 400) for key in ('titulo', 'assunto', 'proposta', 'momento_sugerido')}
    return result, None


async def read_saved_context(service, owner, draft_ref, draft, adset_key):
    """Read sanitized data locally; caller decides whether any model may see it."""
    if not any(item['key'] == adset_key for item in draft['conjuntos']):
        raise CopyFailure('META_COPY_ADSET_NOT_FOUND', 'O conjunto não pertence a este rascunho.', 404)
    warnings, contexts, sources = [], [], {}
    reader = None
    ads = [ad for ad in draft['variations'] if ad['adsetKey'] == adset_key]
    origins = [ad['packOrigin'] for ad in ads if ad.get('packOrigin')]
    def warn(message):
        if message not in warnings and len(warnings) < 20:
            warnings.append(message)
    def source(kind, name):
        key = (kind, clean(name, 160) or 'Contexto salvo')
        sources[key] = sources.get(key, 0) + 1
    if service is None:
        warn('Contexto salvo indisponível. Somente os textos atuais e o assunto informado estão disponíveis.')
    else:
        try:
            async with asyncio.timeout(20):
                reader = Reader(service, owner)
                selection = _only(await reader.get('trafego_meta_rascunho_pack',
                    {'draft_ref': f'eq.{draft_ref}', 'adset_key': f'eq.{adset_key}'},
                    'pack_id,manifest_sha256,master_refs,version'))
                if not selection:
                    warn('Nenhum pack vinculado a este conjunto. Contexto de imagem não confirmado.')
                else:
                    if not _refs(selection.get('master_refs')):
                        raise ValueError('malformed selection')
                    if origins:
                        valid = [o for o in origins if o.get('packId') == selection['pack_id']
                            and o.get('manifestHash') == selection['manifest_sha256']
                            and o.get('selectionVersion') == selection['version']
                            and o.get('accountRef') == draft.get('accountRef')
                            and o.get('masterRef') in selection['master_refs']]
                        if len(valid) != len(origins):
                            warn('Uma origem mudou desde a seleção do pack; seu contexto foi excluído. Atualize a montagem.')
                        masters = list(dict.fromkeys(o['masterRef'] for o in valid))
                    else:
                        if any(ad.get('assetRef') or ad.get('videoRef') or ad.get('existingPostRef') for ad in ads):
                            masters = []
                            warn('Os anúncios atuais não confirmam vínculo com o pack salvo; contexto do pack excluído.')
                        else:
                            # A locked pack can supply context before media upload.
                            masters = list(dict.fromkeys(selection['master_refs']))
                    pack = await reader.pack(selection['pack_id'], selection['manifest_sha256'])
                    if not pack or (pack.get('manifest') or {}).get('source') != 'STUDIO':
                        warn('A revisão exata do pack está indisponível; contexto excluído.')
                    else:
                        for ref in masters[:10]:
                            item = _only([x for x in pack['manifest'].get('items', []) if x.get('master_ref') == ref])
                            master = await reader.master(ref)
                            if (not item or not master or master.get('arquivado_em') or master.get('kind') != 'imagem'
                                    or master.get('content_hash') != item.get('content_hash') or master.get('job_id') != item.get('job_id')):
                                warn('Uma peça está indisponível ou mudou; seu contexto foi excluído.')
                                continue
                            selected_ads = [ad for ad in ads if (ad.get('packOrigin') or {}).get('masterRef') == ref]
                            binding_ok = True
                            for ad in selected_ads:
                                if (ad.get('midia') != 'image' or ad.get('videoRef') or ad.get('existingPostRef')
                                        or not ad.get('assetRef') or not await reader.upload_matches(draft['accountRef'], master, ad['assetRef'])):
                                    binding_ok = False
                                    break
                            if not binding_ok:
                                warn('A imagem atual não possui vínculo de envio confirmado com esta peça do pack; contexto excluído.')
                                continue
                            bridge = _only(await reader.get('criativo_agente_peca_job', {'job_id': f'eq.{master["job_id"]}'},
                                'project_ref,run_ref,creative_ref,copy_ref,group_ref'))
                            if not bridge or bridge != item.get('strategy'):
                                warn('Uma peça não tem vínculo de estratégia confirmado; contexto excluído.')
                                continue
                            run = _only(await reader.get('criativo_agente_run', {
                                'project_ref': f'eq.{bridge["project_ref"]}', 'run_ref': f'eq.{bridge["run_ref"]}',
                                'status': 'eq.COMPLETED'}, 'input,output'))
                            if not run:
                                warn('Uma estratégia de origem está indisponível; seu contexto foi excluído.')
                                continue
                            context, issue = _run_context(run, bridge, draft)
                            if issue:
                                warn(issue)
                                continue
                            if len(json.dumps([*contexts, context], ensure_ascii=False)) > MAX_CONTEXT_CHARS:
                                warn('O contexto atingiu o limite de tamanho; parte dos detalhes não foi incluída.')
                                continue
                            contexts.append(context)
                            source('BRIEFING', 'Briefing salvo')
                            source('STRATEGY', 'Estratégia da peça selecionada')
                            source('PACK_COPY', pack.get('nome', 'Pack selecionado'))
                            if context.get('page_snapshot'):
                                source('LP_SNAPSHOT', context['page_snapshot'].get('titulo') or 'Página de destino salva')
        except (httpx.HTTPError, TimeoutError, KeyError, TypeError, ValueError, AttributeError, ContratoMetaInvalido):
            warn('Parte do contexto salvo não pôde ser recuperada; somente as fontes confirmadas estão disponíveis.')
    if contexts:
        warn('Contexto recuperado de snapshots salvos; a página e as imagens não foram acessadas novamente.')
    incomplete = len(ads) > len(origins) if origins else False
    mode = ('MIXED' if incomplete or len(warnings) > 1
            else 'SAVED_CREATIVE_CONTEXT') if contexts else 'CURRENT_TEXTS_ONLY'
    # Private fence, never sent to the model or public preview. Includes the
    # owner/account/parent and the exact queried witnesses, so selection changes
    # outside CampaignDraft.version are detectable even when prose is identical.
    witness = {'owner': owner, 'draft': str(draft_ref), 'account': draft.get('accountRef'),
        'adset': adset_key, 'origins': origins,
        'media_selection': [{key: ad.get(key) for key in ('key', 'assetRef', 'videoRef', 'existingPostRef')} for ad in ads],
        'reads': sorted((repr(key), value) for key, value in reader.cache.items()) if reader else []}
    stamp = hashlib.sha256(json.dumps(witness, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return {'selection_stamp': stamp, 'saved_creative_context': contexts, 'context_summary': {'mode': mode,
        'sources': [{'kind': kind, 'name': name, 'item_count': count} for (kind, name), count in sources.items()],
        'facts_count': sum(len(c['facts_from_saved_briefing']) for c in contexts), 'warnings': warnings}}
