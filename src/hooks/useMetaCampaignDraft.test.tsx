// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { conjuntoInicial, variacaoInicial, type Draft } from '@/components/trafego/meta/rascunho';
import { useMetaCampaignDraft } from './useMetaCampaignDraft';

const api = vi.hoisted(() => {
  class ErrorDraft extends Error {
    constructor(message: string, readonly code: string, readonly status: number) { super(message); }
  }
  return { read: vi.fn(), save: vi.fn(), ErrorDraft };
});
vi.mock('@/lib/metaCampaignDraftApi', () => ({
  readMetaCampaignDraft: api.read, saveMetaCampaignDraft: api.save, MetaDraftError: api.ErrorDraft,
  draftWithoutAuthority: (draft: Draft) => ({ ...draft, categoryConfirmed: false,
    variations: draft.variations.map(ad => ({ ...ad, assetRightsConfirmed: false,
      thirdPartyIdentityCleared: false, assetPolicyConfirmedAt: '' })),
  }),
}));

function initial(): Draft {
  return { recipeId: 'TRAFFIC_WEBSITE_LPV_STATIC', accountRef: '', pageRef: '', instagramActorRef: '',
    campaignName: 'Initial', destinationUrl: '', nivelDeOrcamento: 'ADSET', periodoDeOrcamento: 'DAILY', budgetBrl: '10,00',
    categoryConfirmed: false, creativeMode: 'single', conjuntos: [conjuntoInicial('adset-001', 'BR', '', '10,00')],
    variations: [variacaoInicial('variation-001', 1, 'adset-001')],
  };
}
const ref = '00000000-0000-4000-8000-000000000001';
function record(draft: Draft, version = 1) {
  return { draft_ref: ref, draft, version, updated_at: 'now', scope: 'DRAFT_ONLY', launch_authorized: false };
}
function harness(enabled = true, requireExisting = false) {
  return renderHook(() => {
    const [draft, setDraft] = useState(initial);
    const persistence = useMetaCampaignDraft({ draftRef: ref, draft, onRestore: setDraft, enabled, requireExisting });
    return { ...persistence, draft, setDraft };
  });
}

beforeEach(() => { api.read.mockReset(); api.save.mockReset(); });
describe('durable Meta campaign draft', () => {
  it('keeps explicit missing drafts read-only and never recreates blank defaults', async () => {
    api.read.mockRejectedValue(new api.ErrorDraft('Missing', 'META_DRAFT_NOT_FOUND', 404));
    const h = harness(true, true);
    await waitFor(() => expect(h.result.current.error).toMatch(/não está disponível/));
    expect(h.result.current.blocked).toBe(true);
    await act(async () => { expect(await h.result.current.saveNow()).toBe(false); });
    expect(api.save).not.toHaveBeenCalled(); h.unmount();
  });

  it('permits version-zero creation only for a newly allocated identity', async () => {
    api.read.mockRejectedValue(new api.ErrorDraft('Missing', 'META_DRAFT_NOT_FOUND', 404));
    api.save.mockImplementation((_id, version, draft) => Promise.resolve(record(draft, version + 1)));
    const h = harness();
    await waitFor(() => expect(h.result.current.loading).toBe(false));
    expect(h.result.current.blocked).toBe(false);
    await act(async () => { expect(await h.result.current.saveNow()).toBe(true); });
    expect(api.save.mock.calls[0][1]).toBe(0); h.unmount();
  });

  it('failed restoration cannot enable the editor or save defaults', async () => {
    api.read.mockRejectedValue(new api.ErrorDraft('Session expired', 'META_DRAFT_SESSION_REQUIRED', 401));
    const h = harness(true, true);
    await waitFor(() => expect(h.result.current.error).toBe('Session expired'));
    expect(h.result.current.blocked).toBe(true);
    await act(async () => { expect(await h.result.current.saveNow()).toBe(false); });
    expect(api.save).not.toHaveBeenCalled(); h.unmount();
  });

  it('rejects a late read from the previous identity after switching drafts', async () => {
    let oldRead!: (value: ReturnType<typeof record>) => void;
    const second = { ...initial(), campaignName: 'Second draft', accountRef: 'account_selected' };
    api.read.mockImplementationOnce(() => new Promise(resolve => { oldRead = resolve; }))
      .mockResolvedValueOnce(record(second, 7));
    const h = renderHook(({ identity }) => {
      const [draft, setDraft] = useState(initial);
      return { ...useMetaCampaignDraft({ draftRef: identity, draft, onRestore: setDraft, requireExisting: true }), draft };
    }, { initialProps: { identity: ref } });
    h.rerender({ identity: '00000000-0000-4000-8000-000000000002' });
    await waitFor(() => expect(h.result.current.draft.campaignName).toBe('Second draft'));
    await act(async () => { oldRead(record({ ...initial(), campaignName: 'Stale first draft' }, 2)); });
    expect(h.result.current.draft.campaignName).toBe('Second draft');
    expect(h.result.current.version).toBe(7);
    expect(api.save).not.toHaveBeenCalled(); h.unmount();
  });

  it('reload invalidates an in-flight write before waiting for its completion', async () => {
    api.read.mockResolvedValueOnce(record(initial(), 1))
      .mockResolvedValueOnce(record({ ...initial(), campaignName: 'Recovered server value' }, 3));
    let write!: (value: ReturnType<typeof record>) => void;
    api.save.mockImplementationOnce(() => new Promise(resolve => { write = resolve; }));
    const h = harness(true, true);
    await waitFor(() => expect(h.result.current.loading).toBe(false));
    act(() => h.result.current.setDraft(d => ({ ...d, campaignName: 'Sent edit' })));
    let saving!: Promise<boolean>; let recovering!: Promise<void>;
    act(() => { saving = h.result.current.saveNow(); });
    await waitFor(() => expect(api.save).toHaveBeenCalledTimes(1));
    act(() => h.result.current.setDraft(d => ({ ...d, campaignName: 'Must not be flushed by recovery' })));
    act(() => { recovering = h.result.current.reload(); });
    expect(h.result.current.blocked).toBe(true);
    await act(async () => { write(record(api.save.mock.calls[0][2], 2)); await saving; await recovering; });
    expect(api.save).toHaveBeenCalledTimes(1);
    expect(h.result.current.draft.campaignName).toBe('Recovered server value');
    expect(h.result.current.version).toBe(3);
    expect(h.result.current.saved).toBe(true); h.unmount();
  });

  it('hydrates persisted assembly without replacing it by defaults', async () => {
    const persisted = initial(); persisted.campaignName = 'Saved'; persisted.variations[0].message = 'Persisted copy';
    persisted.accountRef = 'metaacct_saved'; persisted.pageRef = 'metapage_saved';
    persisted.destinationUrl = 'https://example.com/article';
    persisted.conjuntos[0].mensuracao = { proposito: 'OPTIMIZE', fonteTipo: 'PIXEL',
      fonteRef: 'metapixel_saved', eventoPadrao: 'CONTENT_VIEW', conversaoRef: '' };
    persisted.variations[0].assetRef = 'metaasset_saved';
    persisted.variations[0].packOrigin = { packId: '00000000-0000-4000-8000-000000000005',
      manifestHash: 'a'.repeat(64), masterRef: '00000000-0000-4000-8000-000000000006',
      accountRef: persisted.accountRef, selectionVersion: 2 };
    persisted.conjuntos.push(conjuntoInicial('adset-002', 'Second audience', '', '15,00'));
    persisted.variations.push({ ...variacaoInicial('variation-002', 2, 'adset-002'), message: 'Second copy' });
    api.read.mockResolvedValue(record(persisted, 4));
    const h = harness();
    await waitFor(() => expect(h.result.current.loading).toBe(false));
    expect(h.result.current.draft.campaignName).toBe('Saved');
    expect(h.result.current.draft.variations[0].message).toBe('Persisted copy');
    expect(h.result.current.draft).toEqual(persisted);
    expect(h.result.current.version).toBe(4);
    expect(h.result.current.saved).toBe(true);
    expect(api.save).not.toHaveBeenCalled(); h.unmount();
  });

  it('serializes edits made during a save using the returned CAS version', async () => {
    api.read.mockResolvedValue(record(initial(), 1));
    let resolveFirst!: (value: ReturnType<typeof record>) => void;
    api.save.mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve; }))
      .mockImplementationOnce((_id, version, draft) => Promise.resolve(record(draft, version + 1)));
    const h = harness(); await waitFor(() => expect(h.result.current.loading).toBe(false));
    act(() => h.result.current.setDraft(d => ({ ...d, campaignName: 'First edit' })));
    let saving!: Promise<boolean>;
    act(() => { saving = h.result.current.saveNow(); });
    await waitFor(() => expect(api.save).toHaveBeenCalledTimes(1));
    act(() => h.result.current.setDraft(d => ({ ...d, campaignName: 'Latest edit' })));
    await act(async () => { resolveFirst(record(api.save.mock.calls[0][2], 2)); await saving; });
    expect(api.save).toHaveBeenCalledTimes(2);
    expect(api.save.mock.calls[1][1]).toBe(2);
    expect(api.save.mock.calls[1][2].campaignName).toBe('Latest edit');
    expect(h.result.current.version).toBe(3);
    expect(h.result.current.saved).toBe(true); h.unmount();
  });

  it('a CAS conflict stops further writes until explicit reload', async () => {
    api.read.mockResolvedValue(record(initial(), 1));
    api.save.mockRejectedValue(new api.ErrorDraft('Changed in another tab', 'META_DRAFT_VERSION_CONFLICT', 409));
    const h = harness(); await waitFor(() => expect(h.result.current.loading).toBe(false));
    act(() => h.result.current.setDraft(d => ({ ...d, campaignName: 'Local edit' })));
    await act(async () => { expect(await h.result.current.saveNow()).toBe(false); });
    expect(h.result.current.conflict).toBe(true);
    await act(async () => { expect(await h.result.current.saveNow()).toBe(false); });
    expect(api.save).toHaveBeenCalledTimes(1);
    expect(h.result.current.draft.campaignName).toBe('Local edit'); h.unmount();
  });

  it('retries a transient autosave error only after a new edit, never in a timer loop', async () => {
    api.read.mockResolvedValue(record(initial(), 1));
    api.save.mockRejectedValueOnce(new api.ErrorDraft('Temporary failure', 'TEMPORARY', 503))
      .mockImplementation((_id, version, draft) => Promise.resolve(record(draft, version + 1)));
    const h = harness(); await waitFor(() => expect(h.result.current.loading).toBe(false));
    act(() => h.result.current.setDraft(d => ({ ...d, campaignName: 'First edit' })));
    await act(async () => { expect(await h.result.current.saveNow()).toBe(false); });
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 800)); });
    expect(api.save).toHaveBeenCalledTimes(1);
    act(() => h.result.current.setDraft(d => ({ ...d, campaignName: 'New operator edit' })));
    await waitFor(() => expect(h.result.current.saved).toBe(true), { timeout: 2000 });
    expect(api.save).toHaveBeenCalledTimes(2);
    expect(api.save.mock.calls[1][2].campaignName).toBe('New operator edit');
    h.unmount();
  });

  it('demo never reads or saves official data', async () => {
    const h = harness(false);
    await act(async () => { expect(await h.result.current.saveNow()).toBe(true); });
    expect(api.read).not.toHaveBeenCalled(); expect(api.save).not.toHaveBeenCalled(); h.unmount();
  });

  it('a no-op save does not lock out the next edit', async () => {
    api.read.mockResolvedValue(record(initial(), 1));
    api.save.mockImplementation((_id, version, draft) => Promise.resolve(record(draft, version + 1)));
    const h = harness(); await waitFor(() => expect(h.result.current.loading).toBe(false));
    await act(async () => { expect(await h.result.current.saveNow()).toBe(true); });
    expect(api.save).not.toHaveBeenCalled();
    act(() => h.result.current.setDraft(d => ({ ...d, campaignName: 'Edit after confirmation' })));
    await act(async () => { expect(await h.result.current.saveNow()).toBe(true); });
    expect(api.save).toHaveBeenCalledTimes(1);
    expect(h.result.current.version).toBe(2);
    expect(h.result.current.saved).toBe(true); h.unmount();
  });

  it('accepts identical server JSON whose keys were reordered by PostgreSQL', async () => {
    function reverse(value: unknown): unknown {
      if (Array.isArray(value)) return value.map(reverse);
      if (value && typeof value === 'object') return Object.fromEntries(
        Object.entries(value).reverse().map(([key, child]) => [key, reverse(child)]));
      return value;
    }
    api.read.mockResolvedValue(record(initial(), 1));
    api.save.mockImplementation((_id, version, draft) => Promise.resolve(record(reverse(draft) as Draft, version + 1)));
    const h = harness(); await waitFor(() => expect(h.result.current.loading).toBe(false));
    act(() => h.result.current.setDraft(d => ({ ...d, campaignName: 'New name' })));
    await act(async () => { expect(await h.result.current.saveNow()).toBe(true); });
    expect(h.result.current.conflict).toBe(false);
    expect(h.result.current.saved).toBe(true); h.unmount();
  });
});
