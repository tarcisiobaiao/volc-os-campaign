// @vitest-environment jsdom
import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useDetalheDoReadModel, usePaginaDoReadModel } from '../MetaCampaignReadView';
import { MetaCampaignDemoContext, type MetaCampaignDataApi } from '../MetaCampaignData';
import type { DetalheMetaReadModel, EntidadeMetaReadModel, PaginaMetaReadModel } from '@/lib/pautadorApi';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function pagina(conta: string, nome: string, cursor: string | null = null): PaginaMetaReadModel {
  return { ok: true, has_snapshot: true, estado: 'COM_SNAPSHOT', entidade: 'anuncios',
    conta_ref: conta, items: [{ nome, entity_ref: `${conta}:${nome}`, spend: conta === 'A' ? 10 : 20 }],
    completo: !cursor, has_more: !!cursor, proximo_cursor: cursor, motivo: null };
}
function detalhe(conta: string, nome: string): DetalheMetaReadModel {
  return { ok: true, has_snapshot: true, estado: 'COM_SNAPSHOT', entidade: 'anuncios', conta_ref: conta,
    item: { nome, entity_ref: `${conta}:${nome}`, spend: conta === 'A' ? 10 : 20 } };
}
function apiFake() {
  return { inventarioMetaReadModel: vi.fn(), detalheMetaReadModel: vi.fn(),
    contasMetaReadModel: vi.fn(), financeiroMeta: vi.fn(), planejarGestaoMeta: vi.fn() } as MetaCampaignDataApi;
}
type Props = { conta: string | null; entidade?: EntidadeMetaReadModel; ativo?: boolean; referencia?: string };
function harness(api: MetaCampaignDataApi, initial: Props, kind: 'pagina' | 'detalhe' = 'pagina') {
  let current!: ReturnType<typeof usePaginaDoReadModel> | ReturnType<typeof useDetalheDoReadModel>;
  const renders: Array<{ conta: string | null; leitura: typeof current.leitura }> = [];
  function PageProbe(props: Props) {
    current = usePaginaDoReadModel(props.entidade ?? 'anuncios', props.conta, props.ativo ?? true);
    renders.push({ conta: props.conta, leitura: current.leitura });
    return null;
  }
  function DetailProbe(props: Props) {
    current = useDetalheDoReadModel(props.entidade ?? 'anuncios', props.referencia ?? 'ad', props.conta);
    renders.push({ conta: props.conta, leitura: current.leitura });
    return null;
  }
  const Probe = kind === 'pagina' ? PageProbe : DetailProbe;
  const ui = (props: Props, source = api) => <MetaCampaignDemoContext.Provider value={source}><Probe {...props} /></MetaCampaignDemoContext.Provider>;
  const view = render(ui(initial));
  return { renders, get current() { return current; }, get page() { return current as ReturnType<typeof usePaginaDoReadModel>; },
    rerender: (props: Props, source = api) => view.rerender(ui(props, source)), unmount: view.unmount };
}
function nomes(h: ReturnType<typeof harness>) {
  const leitura = h.current.leitura;
  if (leitura.fase !== 'respondeu') return [];
  const resposta = leitura.resposta;
  return ('items' in resposta ? resposta.items : resposta.item ? [resposta.item] : []).map(item => item.nome);
}

beforeEach(() => { vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Rede real proibida neste teste')); });
afterEach(() => { cleanup(); expect(globalThis.fetch).not.toHaveBeenCalled(); vi.restoreAllMocks(); });

it('oculta a conta anterior no primeiro render e descarta paginação tardia sem misturar métricas ou referências de ações', async () => {
  const api = apiFake();
  const firstA = deferred<PaginaMetaReadModel>();
  const moreA = deferred<PaginaMetaReadModel>();
  const firstB = deferred<PaginaMetaReadModel>();
  vi.mocked(api.inventarioMetaReadModel).mockReturnValueOnce(firstA.promise).mockReturnValueOnce(moreA.promise).mockReturnValueOnce(firstB.promise);
  const h = harness(api, { conta: 'A' });
  await act(async () => firstA.resolve(pagina('A', 'A1', 'cursor-A')));
  act(() => h.page.carregarMais?.());
  const beforeSwitch = h.renders.length;
  h.rerender({ conta: 'B' });
  expect(h.renders[beforeSwitch].leitura).toEqual({ fase: 'lendo' });
  expect(h.page.carregandoMais).toBe(false);
  await act(async () => firstB.resolve(pagina('B', 'B1')));
  await act(async () => moreA.resolve(pagina('A', 'A2')));
  expect(nomes(h)).toEqual(['B1']);
  for (const render of h.renders.slice(beforeSwitch)) {
    if (render.leitura.fase !== 'respondeu' || !('items' in render.leitura.resposta)) continue;
    expect(render.leitura.resposta.conta_ref).toBe('B');
    expect(render.leitura.resposta.items).toEqual([{ nome: 'B1', entity_ref: 'B:B1', spend: 20 }]);
  }
});

it('não usa uma página antiga como fallback enquanto a primeira página da nova conta está pendente', async () => {
  const api = apiFake();
  const more = deferred<PaginaMetaReadModel>();
  const next = deferred<PaginaMetaReadModel>();
  vi.mocked(api.inventarioMetaReadModel).mockResolvedValueOnce(pagina('A', 'A1', 'cursor-A')).mockReturnValueOnce(more.promise).mockReturnValueOnce(next.promise);
  const h = harness(api, { conta: 'A' });
  await act(async () => {});
  act(() => h.page.carregarMais?.());
  h.rerender({ conta: 'B' });
  await act(async () => more.resolve(pagina('A', 'A2')));
  expect(h.current.leitura.fase).toBe('lendo');
  await act(async () => next.resolve(pagina('B', 'B1')));
  expect(nomes(h)).toEqual(['B1']);
});

it('trava cliques síncronos no mesmo cursor e permite avançar para o próximo sem duplicar linhas', async () => {
  const api = apiFake();
  const more = deferred<PaginaMetaReadModel>();
  vi.mocked(api.inventarioMetaReadModel).mockResolvedValueOnce(pagina('A', 'A1', 'c1')).mockReturnValueOnce(more.promise).mockResolvedValueOnce(pagina('A', 'A3'));
  const h = harness(api, { conta: 'A' });
  await act(async () => {});
  const oldCallback = h.page.carregarMais!;
  act(() => { oldCallback(); oldCallback(); oldCallback(); });
  expect(api.inventarioMetaReadModel).toHaveBeenCalledTimes(2);
  await act(async () => more.resolve(pagina('A', 'A2', 'c2')));
  act(() => oldCallback());
  expect(api.inventarioMetaReadModel).toHaveBeenCalledTimes(2);
  await act(async () => h.page.carregarMais?.());
  expect(nomes(h)).toEqual(['A1', 'A2', 'A3']);
  expect(api.inventarioMetaReadModel).toHaveBeenNthCalledWith(3, 'anuncios', { contaRef: 'A', cursor: 'c2' });
  expect(h.page.carregarMais).toBeNull();
  act(() => oldCallback());
  expect(api.inventarioMetaReadModel).toHaveBeenCalledTimes(3);
});

it('descarta erro de paginação da conta anterior sem apagar a resposta atual', async () => {
  const api = apiFake();
  const more = deferred<PaginaMetaReadModel>();
  vi.mocked(api.inventarioMetaReadModel).mockResolvedValueOnce(pagina('A', 'A1', 'c1')).mockReturnValueOnce(more.promise).mockResolvedValueOnce(pagina('B', 'B1'));
  const h = harness(api, { conta: 'A' });
  await act(async () => {});
  act(() => h.page.carregarMais?.());
  h.rerender({ conta: 'B' });
  await act(async () => more.reject(new Error('Conta anterior desconectou')));
  expect(nomes(h)).toEqual(['B1']);
  expect(h.page.carregandoMais).toBe(false);
});

it('trocar entidade, instância API ou desativar a leitura esconde o resultado já durante render', async () => {
  const api = apiFake();
  const other = apiFake();
  vi.mocked(api.inventarioMetaReadModel).mockResolvedValue(pagina('A', 'Anúncio'));
  vi.mocked(other.inventarioMetaReadModel).mockResolvedValue(pagina('A', 'Outro provedor'));
  const h = harness(api, { conta: 'A' });
  await act(async () => {});
  let start = h.renders.length;
  h.rerender({ conta: 'A', entidade: 'conjuntos' });
  expect(h.renders[start].leitura.fase).toBe('lendo');
  await act(async () => {});
  start = h.renders.length;
  h.rerender({ conta: 'A', entidade: 'conjuntos' }, other);
  expect(h.renders[start].leitura.fase).toBe('lendo');
  await act(async () => {});
  start = h.renders.length;
  h.rerender({ conta: 'A', entidade: 'conjuntos', ativo: false }, other);
  expect(h.renders[start].leitura).toMatchObject({ fase: 'respondeu', resposta: { items: [], has_snapshot: false } });
  expect(other.inventarioMetaReadModel).toHaveBeenCalledOnce();
});

it('recarregar invalida paginação em curso e não reanexa seus itens à nova tentativa', async () => {
  const api = apiFake();
  const more = deferred<PaginaMetaReadModel>();
  vi.mocked(api.inventarioMetaReadModel).mockResolvedValueOnce(pagina('A', 'A1', 'c1')).mockReturnValueOnce(more.promise).mockResolvedValueOnce(pagina('A', 'Atualizado'));
  const h = harness(api, { conta: 'A' });
  await act(async () => {});
  act(() => h.page.carregarMais?.());
  const start = h.renders.length;
  await act(async () => h.current.recarregar());
  expect(h.renders[start].leitura.fase).toBe('lendo');
  await act(async () => more.resolve(pagina('A', 'Obsoleto')));
  expect(nomes(h)).toEqual(['Atualizado']);
});

it('detalhe protege conta, referência, entidade e API desde o primeiro render', async () => {
  const api = apiFake();
  const other = apiFake();
  const old = deferred<DetalheMetaReadModel>();
  vi.mocked(api.detalheMetaReadModel).mockResolvedValueOnce(detalhe('A', 'Original')).mockReturnValueOnce(old.promise).mockResolvedValue(detalhe('B', 'Novo'));
  vi.mocked(other.detalheMetaReadModel).mockResolvedValue(detalhe('B', 'Outro provedor'));
  const h = harness(api, { conta: 'A', referencia: 'ad1' }, 'detalhe');
  await act(async () => {});
  let start = h.renders.length;
  h.rerender({ conta: 'A', referencia: 'ad2' });
  expect(h.renders[start].leitura.fase).toBe('lendo');
  h.rerender({ conta: 'B', referencia: 'ad2' });
  await act(async () => {});
  await act(async () => old.resolve(detalhe('A', 'Obsoleto')));
  expect(nomes(h)).toEqual(['Novo']);
  start = h.renders.length;
  h.rerender({ conta: 'B', referencia: 'ad2', entidade: 'conjuntos' });
  expect(h.renders[start].leitura.fase).toBe('lendo');
  await act(async () => {});
  start = h.renders.length;
  h.rerender({ conta: 'B', referencia: 'ad2', entidade: 'conjuntos' }, other);
  expect(h.renders[start].leitura.fase).toBe('lendo');
  await act(async () => {});
  expect(nomes(h)).toEqual(['Outro provedor']);
  start = h.renders.length;
  h.rerender({ conta: null, referencia: 'ad2' }, other);
  expect(h.renders[start].leitura).toMatchObject({ fase: 'respondeu', resposta: { item: null, has_snapshot: false } });
});

it('detalhe recarregado ignora a tentativa anterior ainda pendente', async () => {
  const api = apiFake();
  const old = deferred<DetalheMetaReadModel>();
  vi.mocked(api.detalheMetaReadModel).mockReturnValueOnce(old.promise).mockResolvedValueOnce(detalhe('A', 'Atualizado'));
  const h = harness(api, { conta: 'A' }, 'detalhe');
  await act(async () => h.current.recarregar());
  await act(async () => old.resolve(detalhe('A', 'Obsoleto')));
  expect(nomes(h)).toEqual(['Atualizado']);
});
