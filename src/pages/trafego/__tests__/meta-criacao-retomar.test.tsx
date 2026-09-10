// @vitest-environment jsdom
import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import MetaCriacaoPage from '@/pages/trafego/MetaCriacaoPage';
import { conjuntoInicial, variacaoInicial, type Draft } from '@/components/trafego/meta/rascunho';

const mocks = vi.hoisted(() => ({ read: vi.fn(), save: vi.fn(), accounts: vi.fn(), assets: vi.fn(), measurement: vi.fn(), bindPack: vi.fn() }));
vi.mock('@/lib/metaCampaignDraftApi', async original => ({
  ...await original<typeof import('@/lib/metaCampaignDraftApi')>(),
  readMetaCampaignDraft: mocks.read, saveMetaCampaignDraft: mocks.save,
}));
vi.mock('@/lib/pautadorApi', async original => ({
  ...await original<typeof import('@/lib/pautadorApi')>(),
  pautadorApi: {
    capacidadesCriacaoMeta: vi.fn().mockResolvedValue({ create_paused: 'DISABLED' }),
    receitasCriacaoMetaV2: vi.fn().mockRejectedValue(new Error('Recipe catalog not used by hydration')),
    contasMetaLocal: mocks.accounts, ativosCriacaoMeta: mocks.assets,
    catalogoDeMensuracaoMeta: mocks.measurement,
    trackingAutomaticoMeta: vi.fn().mockRejectedValue(new Error('No tracking read in this test')),
  },
}));
vi.mock('@/features/creative-studio/api', async original => ({
  ...await original<typeof import('@/features/creative-studio/api')>(),
  listarSelecoesDePack: vi.fn().mockResolvedValue({ selections: [] }),
  fixarPackNoConjunto: mocks.bindPack,
}));
vi.mock('@/features/creative-studio/componentes/EscolherPack', () => ({ EscolherPack: () => <p>Biblioteca de packs</p> }));
vi.mock('@/components/trafego/meta/PrepararPackMeta', () => ({ PrepararPackMeta: () => <p>Pack pronto para preparar</p> }));
vi.mock('@/components/layout/Layout', () => ({ Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/trafego/meta/MetaConfiguracaoLocal', () => ({ MetaConfiguracaoLocal: () => null }));
vi.mock('@/components/trafego/meta/RascunhosMeta', () => ({ RascunhosMeta: () => null }));

const ref = '00000000-0000-4000-8000-000000000001';
const account = { referencia_opaca: 'metaacct_saved', nome: 'TF Saved', moeda: 'BRL', id_mascarado: '••••1234' };
const page = { referencia_opaca: 'metapage_saved', nome: 'Saved Page', tipo: 'page', id_mascarado: '••••4321' };
function saved(): Draft {
  return { accountRef: account.referencia_opaca, pageRef: page.referencia_opaca, instagramActorRef: '',
    campaignName: 'Campaign from server', destinationUrl: 'https://example.com/saved-article',
    recipeId: 'TRAFFIC_WEBSITE_LPV_STATIC', nivelDeOrcamento: 'ADSET', periodoDeOrcamento: 'DAILY',
    budgetBrl: '25,00', categoryConfirmed: false, creativeMode: 'single',
    conjuntos: [conjuntoInicial('adset-saved', 'Saved audience', '', '25,00')],
    variations: [{ ...variacaoInicial('variation-saved', 1, 'adset-saved'), assetRef: 'metaasset_saved',
      adName: 'Saved ad', message: 'Saved ad copy', headline: 'Saved headline' }],
  };
}
function open(query = '') {
  return render(<MemoryRouter initialEntries={[`/trafego/meta/nova?rascunho=${ref}${query}`]}><MetaCriacaoPage /></MemoryRouter>);
}
beforeEach(() => {
  mocks.read.mockReset().mockResolvedValue({ draft_ref: ref, draft: saved(), version: 8 });
  mocks.save.mockReset().mockImplementation(async (_id, version, draft) => ({ draft_ref: ref, version: version + 1, draft }));
  mocks.accounts.mockReset().mockResolvedValue({ contas: [account] });
  mocks.assets.mockReset().mockResolvedValue({ paginas: [page], imagens: [{ referencia_opaca: 'metaasset_saved',
    nome: 'Saved image', tipo: 'image_asset', preview_disponivel: false, largura: 1080, altura: 1350 }], videos: [] });
  mocks.measurement.mockReset();
  mocks.bindPack.mockReset();
  Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });
});
afterEach(cleanup);

describe('resume the real wizard with persisted choices', () => {
  it('a late pack response updates its target but not the newly focused creative origin', async () => {
    const draft = saved();
    draft.conjuntos.push(conjuntoInicial('adset-b', 'Audience B', '', '25,00'));
    draft.creativeMode = 'batch';
    draft.variations.push({ ...variacaoInicial('variation-b', 2, 'adset-b'), message: 'Copy B' });
    mocks.read.mockResolvedValue({ draft_ref: ref, draft, version: 8 });
    let complete!: (value: unknown) => void;
    mocks.bindPack.mockImplementation(() => new Promise(resolve => { complete = resolve; }));
    const packId = '00000000-0000-4000-8000-000000000099';
    open(`&pergunta=criativos&etapa=criativo&pack=${packId}`);
    await waitFor(() => expect(mocks.bindPack).toHaveBeenCalledTimes(1));
    const conjuntos = screen.getByRole('group', { name: 'Escolher conjunto dos anúncios' });
    fireEvent.click(within(conjuntos).getByRole('button', { name: /Audience B/ }));
    fireEvent.click(screen.getByRole('radio', { name: /Usar imagens da conta/ }));
    await act(async () => complete({ draft_ref: ref, adset_key: 'adset-saved', pack_id: packId,
      pack_name: 'Pack A', version: 1, manifest_sha256: 'a'.repeat(64), master_refs: [] }));
    expect(screen.getByRole('radio', { name: /Usar imagens da conta/ }).getAttribute('aria-checked')).toBe('true');
    expect(mocks.bindPack).toHaveBeenCalledTimes(1);
    expect(within(conjuntos).getByRole('button', { name: /Saved audience/ }).textContent).toContain('Pack A');
  });

  it('a failed deep-link pack is not silently applied to the next ad set', async () => {
    const draft = saved(); draft.conjuntos.push(conjuntoInicial('adset-b', 'Audience B', '', '25,00'));
    mocks.read.mockResolvedValue({ draft_ref: ref, draft, version: 8 });
    mocks.bindPack.mockRejectedValue(new Error('Pack unavailable'));
    open('&pergunta=criativos&etapa=criativo&pack=00000000-0000-4000-8000-000000000099');
    await screen.findByText('Pack unavailable');
    fireEvent.click(within(screen.getByRole('group', { name: 'Escolher conjunto dos anúncios' })).getByRole('button', { name: /Audience B/ }));
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 50)); });
    expect(mocks.bindPack).toHaveBeenCalledTimes(1);
  });

  it('recupera bancos flexíveis por conjunto, edita, troca de conjunto e salva todas as opções', async () => {
    const draft = saved();
    draft.creativeMode = 'flexible'; draft.recipeId = 'WEB_SALES_CONVERSION';
    draft.conjuntos[0].flexibleTexts = { primary_text: ['Copy A', 'Copy A2'], headline: ['Título A'], description: [] };
    draft.conjuntos.push({ ...conjuntoInicial('adset-b', 'Audience B', '', '25,00'),
      flexibleTexts: { primary_text: ['Copy B'], headline: ['Título B'], description: [] } });
    draft.variations.push({ ...variacaoInicial('variation-b', 2, 'adset-b'), assetRef: 'metaasset_saved' });
    mocks.read.mockResolvedValue({ draft_ref: ref, draft, version: 8 });
    open('&pergunta=criativos&etapa=criativo');
    expect(await screen.findByDisplayValue('Copy A2')).toBeTruthy();
    expect(screen.queryByLabelText('Texto principal do anúncio')).toBeNull();
    fireEvent.change(screen.getByLabelText('Texto principal 2'), { target: { value: 'Copy A2 editada' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar título' }));
    fireEvent.change(screen.getByLabelText('Título 2'), { target: { value: 'Título A2' } });
    const conjuntos = screen.getByRole('group', { name: 'Escolher conjunto dos anúncios' });
    fireEvent.click(within(conjuntos).getByRole('button', { name: /Audience B/ }));
    expect(await screen.findByDisplayValue('Copy B')).toBeTruthy();
    expect(screen.queryByDisplayValue('Copy A2 editada')).toBeNull();
    fireEvent.click(within(conjuntos).getByRole('button', { name: /Saved audience/ }));
    expect(await screen.findByDisplayValue('Copy A2 editada')).toBeTruthy();
    await waitFor(() => expect(mocks.save).toHaveBeenCalled(), { timeout: 3000 });
    const persisted = mocks.save.mock.calls.at(-1)![2];
    expect(persisted.conjuntos[0].flexibleTexts).toEqual({ primary_text: ['Copy A', 'Copy A2 editada'], headline: ['Título A', 'Título A2'], description: [] });
    expect(persisted.conjuntos[1].flexibleTexts).toEqual(draft.conjuntos[1].flexibleTexts);
  });

  it('recovers the saved destination and does not replace it with initial defaults', async () => {
    open('&pergunta=destino');
    expect(await screen.findByDisplayValue('https://example.com/saved-article')).toBeTruthy();
    expect(await screen.findByText(/Montagem salva no servidor · versão 8/)).toBeTruthy();
    expect(mocks.read).toHaveBeenCalledWith(ref);
    expect(mocks.save).not.toHaveBeenCalled();
  });

  it('rehydrates the account label automatically without selecting a different first account', async () => {
    mocks.accounts.mockResolvedValue({ contas: [{ ...account, referencia_opaca: 'metaacct_other', nome: 'Other account' }, account] });
    open('&pergunta=conta');
    await waitFor(() => expect(screen.getByLabelText('Conta de anúncios')).toHaveProperty('value', account.referencia_opaca));
    expect(await screen.findByRole('option', { name: /TF Saved/ })).toBeTruthy();
    expect(mocks.accounts).toHaveBeenCalledTimes(1);
    expect(mocks.assets).toHaveBeenCalledWith(account.referencia_opaca);
    expect(mocks.save).not.toHaveBeenCalled();
  });

  it('keeps saved account visible while catalog access is pending', async () => {
    let done!: (result: unknown) => void;
    mocks.accounts.mockImplementation(() => new Promise(resolve => { done = resolve; }));
    open('&pergunta=conta');
    expect(await screen.findByRole('option', { name: /Conta salva/ })).toBeTruthy();
    expect(screen.getByLabelText('Conta de anúncios')).toHaveProperty('value', account.referencia_opaca);
    await act(async () => { done({ contas: [account] }); });
    expect(await screen.findByRole('option', { name: /TF Saved/ })).toBeTruthy();
  });

  it('plain Continue recovers saved ads at the creative decision, not an empty destination screen', async () => {
    open();
    expect(await screen.findByRole('heading', { name: 'Vamos dar forma à campanha?' })).toBeTruthy();
    expect(await screen.findByDisplayValue('Saved ad copy')).toBeTruthy();
    expect(screen.getByDisplayValue('Saved ad')).toBeTruthy();
    expect(screen.getByDisplayValue('Saved headline')).toBeTruthy();
  });

  it('recovers the saved pixel and its label without replacing the standard event', async () => {
    const draft = saved(); draft.recipeId = 'WEB_SALES_CONVERSION';
    draft.conjuntos[0].mensuracao = { proposito: 'OPTIMIZE', fonteTipo: 'PIXEL',
      fonteRef: 'metapixel_saved', eventoPadrao: 'CONTENT_VIEW', conversaoRef: '' };
    mocks.read.mockResolvedValue({ draft_ref: ref, draft, version: 8 });
    const base = { ok: true, referencia_opaca_da_conta: account.referencia_opaca,
      estado: 'AVAILABLE', completo: true, total: 1, paginas_lidas: 1, invalidos: 0, desconhecidos: 0,
      motivo: null, retryable: false, observado_em: new Date().toISOString(), estado_do_catalogo: 'FRESH' };
    mocks.measurement.mockResolvedValue({ fontes: { ...base, items: [{ referencia_opaca: 'metapixel_saved',
      nome: 'Pixel Saved', source_kind: 'PIXEL', estado: 'AVAILABLE_FIRED' }] },
      conversoes: { ...base, items: [], total: 0 } });
    open('&pergunta=conversao');
    expect(await screen.findByRole('option', { name: /Pixel Saved/ })).toBeTruthy();
    expect(screen.getByLabelText('Fonte do evento (pixel ou dataset)')).toHaveProperty('value', 'metapixel_saved');
    expect(mocks.measurement).toHaveBeenCalledWith(account.referencia_opaca);
    expect(mocks.save).not.toHaveBeenCalled();
  });

  it('an unavailable explicit draft renders recovery guidance and never writes a replacement', async () => {
    const { MetaDraftError } = await import('@/lib/metaCampaignDraftApi');
    mocks.read.mockRejectedValue(new MetaDraftError('Missing', 'META_DRAFT_NOT_FOUND', 404));
    open('&pergunta=destino');
    expect(await screen.findByText(/Este rascunho não está disponível/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Continuar' })).toHaveProperty('disabled', true);
    expect(screen.getByRole('link', { name: 'Iniciar uma nova campanha' })).toBeTruthy();
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 800)); });
    expect(mocks.save).not.toHaveBeenCalled();
  });
});
