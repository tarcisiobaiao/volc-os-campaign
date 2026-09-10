import { supabase } from '@/lib/supabase';
import type { Draft } from '@/components/trafego/meta/rascunho';

export interface SavedMetaCampaignDraft {
  draft_ref: string;
  version: number;
  draft: Draft;
  updated_at: string;
  scope: 'DRAFT_ONLY';
  launch_authorized: false;
}

export class MetaDraftError extends Error {
  constructor(message: string, readonly code: string, readonly status: number) { super(message); }
}

/** Choices are durable; attestations must be made again after resuming. */
export function draftWithoutAuthority(draft: Draft): Draft {
  return { ...draft, categoryConfirmed: false,
    variations: draft.variations.map(ad => {
      const { packOrigin, ...fields } = ad;
      return { ...fields, ...(packOrigin ? { packOrigin } : {}),
        assetRightsConfirmed: false, thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '',
      };
    }),
  };
}

async function transport(path: string, init?: RequestInit) {
  const base = (import.meta.env.VITE_PAUTADOR_API_URL || '').trim().replace(/\/$/, '');
  if (!base) throw new MetaDraftError('O endereço do servidor não está configurado.', 'META_DRAFT_API_MISSING', 0);
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new MetaDraftError('Entre novamente para acessar seus rascunhos.', 'META_DRAFT_SESSION_REQUIRED', 401);
  let response: Response;
  try {
    response = await fetch(`${base}/api/trafego/meta/drafts${path}`, {
      signal: AbortSignal.timeout(20000), ...init, cache: 'no-store', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new MetaDraftError('Não foi possível salvar ou recuperar o rascunho.', 'META_DRAFT_NETWORK', 0);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new MetaDraftError(body?.detail?.mensagem || 'Não foi possível acessar o rascunho salvo.',
      body?.detail?.codigo || 'META_DRAFT_ERROR', response.status);
  }
  return body;
}

async function request(draftRef: string, init?: RequestInit): Promise<SavedMetaCampaignDraft> {
  const body = await transport(`/${encodeURIComponent(draftRef)}`, init);
  if (!body || body.draft_ref !== draftRef || !Number.isInteger(body.version) || body.version < 1
      || body.scope !== 'DRAFT_ONLY' || body.launch_authorized !== false || !Array.isArray(body.draft?.conjuntos)
      || !Array.isArray(body.draft?.variations)) {
    throw new MetaDraftError('O servidor não confirmou a versão do rascunho.', 'META_DRAFT_INVALID_RESPONSE', 502);
  }
  return { ...body, draft: draftWithoutAuthority(body.draft) };
}

export interface MetaDraftSummary {
  draft_ref: string; version: number; updated_at: string; campaign_name: string;
  adset_count: number; ad_count: number;
}
export interface MetaDraftList { items: MetaDraftSummary[]; has_more: boolean; next_offset: number | null }
export async function listMetaCampaignDrafts(offset = 0): Promise<MetaDraftList> {
  const body = await transport(`?offset=${offset}`);
  if (!body || body.scope !== 'DRAFT_ONLY' || body.launch_authorized !== false
      || !Array.isArray(body.items) || typeof body.has_more !== 'boolean'
      || (body.has_more ? body.next_offset !== offset + 20 : body.next_offset !== null)
      || body.items.some((item: MetaDraftSummary) => !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(item.draft_ref)
        || typeof item.campaign_name !== 'string' || !Number.isInteger(item.version)
        || !Number.isInteger(item.adset_count) || !Number.isInteger(item.ad_count)
        || !Number.isFinite(Date.parse(item.updated_at)))) {
    throw new MetaDraftError('Não foi possível conferir a lista de rascunhos.', 'META_DRAFT_LIST_INVALID', 502);
  }
  return body;
}

export const readMetaCampaignDraft = (ref: string) => request(ref);
export async function archiveMetaCampaignDraft(ref: string, expectedVersion: number): Promise<void> {
  const body = await transport(`/${encodeURIComponent(ref)}`, {
    method: 'DELETE', body: JSON.stringify({ expected_version: expectedVersion }),
  });
  if (body?.draft_ref !== ref || body?.archived !== true) {
    throw new MetaDraftError('O servidor não confirmou a exclusão. Atualize a lista antes de repetir.', 'META_DRAFT_ARCHIVE_UNCONFIRMED', 502);
  }
}
export const saveMetaCampaignDraft = (ref: string, expectedVersion: number, draft: Draft) => request(ref, {
  method: 'PUT', body: JSON.stringify({ expected_version: expectedVersion, draft: draftWithoutAuthority(draft) }),
});

export interface CopyContextSummary {
  mode: 'SAVED_CREATIVE_CONTEXT' | 'MIXED' | 'CURRENT_TEXTS_ONLY';
  sources: { kind: 'LP_SNAPSHOT' | 'BRIEFING' | 'STRATEGY' | 'PACK_COPY'; name: string; item_count: number }[];
  facts_count: number; warnings: string[];
}
export interface CopySuggestions { primary_text: string[]; headline: string[]; description: string[]; model: string; context_sha256: string; context_summary?: CopyContextSummary }
function validateCopyContext(value: CopyContextSummary) {
  if (!value || !['SAVED_CREATIVE_CONTEXT', 'MIXED', 'CURRENT_TEXTS_ONLY'].includes(value.mode)
    || !Number.isSafeInteger(value.facts_count) || value.facts_count < 0
    || !Array.isArray(value.sources) || value.sources.length > 50
    || value.sources.some(s => !['LP_SNAPSHOT', 'BRIEFING', 'STRATEGY', 'PACK_COPY'].includes(s.kind)
      || typeof s.name !== 'string' || s.name.length > 400 || !Number.isSafeInteger(s.item_count) || s.item_count < 0)
    || !Array.isArray(value.warnings) || value.warnings.length > 20
    || value.warnings.some(w => typeof w !== 'string' || w.length > 1200)) {
    throw new MetaDraftError('Não foi possível conferir as fontes da sugestão. Seus textos foram preservados.', 'META_COPY_CONTEXT_INVALID', 502);
  }
  return value;
}
export async function readMetaCopyContext(ref: string, adsetKey: string) {
  const body = await transport(`/${encodeURIComponent(ref)}/copy-context?adset_key=${encodeURIComponent(adsetKey)}`);
  if (!Number.isSafeInteger(body?.draft_version) || body.draft_version < 1) throw new MetaDraftError('O contexto do rascunho não foi confirmado.', 'META_COPY_CONTEXT_INVALID', 502);
  return { draft_version: body.draft_version as number, context_summary: validateCopyContext(body.context_summary) };
}
export async function suggestMetaCopy(ref: string, version: number, adsetKey: string, count: number, brief: string, signal?: AbortSignal): Promise<CopySuggestions> {
  const body = await transport(`/${encodeURIComponent(ref)}/copy-suggestions`, { method: 'POST',
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(75000)]) : AbortSignal.timeout(75000), body: JSON.stringify({ expected_version: version, adset_key: adsetKey, count, brief }) });
  for (const key of ['primary_text', 'headline', 'description'] as const) {
    if (!Array.isArray(body?.[key]) || body[key].length > 5 || (key !== 'description' && body[key].length < 1)
      || body[key].some((t: unknown) => typeof t !== 'string' || !t.trim() || Array.from(t).length > (key === 'primary_text' ? 2200 : 255))) {
      throw new MetaDraftError('A sugestão veio incompleta. Seus textos foram preservados.', 'META_COPY_INVALID', 502);
    }
  }
  if (!/^[a-f0-9]{64}$/.test(body.context_sha256) || typeof body.model !== 'string') throw new MetaDraftError('Não foi possível conferir a sugestão.', 'META_COPY_INVALID', 502);
  if (body.context_summary !== undefined) validateCopyContext(body.context_summary);
  return body;
}
export async function reserveMetaNaming(ref: string, version: number) {
  const body = await transport(`/${encodeURIComponent(ref)}/naming-reservation`, { method: 'POST',
    signal: AbortSignal.timeout(90000), body: JSON.stringify({ expected_version: version }) });
  if (body?.draft_ref !== ref || !Number.isSafeInteger(body.campaign_number) || body.campaign_number < 1
    || body.history_complete !== true || typeof body.account_ref !== 'string'
    || !Number.isSafeInteger(body.history_count) || body.history_count < 0) {
    throw new MetaDraftError('A sequência não foi confirmada. Nenhum nome foi alterado.', 'META_NAMING_INVALID', 502);
  }
  return body as { draft_ref: string; account_ref: string; campaign_number: number; history_complete: true; history_count: number };
}
