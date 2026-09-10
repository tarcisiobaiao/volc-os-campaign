// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AcoesDaHierarquia } from '../AcoesDaHierarquia';
import { MetaCampaignDemoContext } from '../MetaCampaignData';
import { criarDadosDemoCampanha, CONTA_DEMO_META } from '../demoCampaignData';
import { salvarPackMeta } from '@/features/creative-studio/api';
import { pautadorApi } from '@/lib/pautadorApi';
vi.mock('@/features/creative-studio/api', () => ({ salvarPackMeta: vi.fn() }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
beforeEach(() => vi.clearAllMocks());

it('conjunto oferece propostas de gestão, nunca salvar em pack', () => {
  render(<AcoesDaHierarquia contaRef="account_ref" campanhaRef="campaign_ref" referencia="adset_reference" nome="Público amplo" entidade="conjunto" />);
  expect(screen.getByRole('group', { name: 'Ações de Público amplo' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Preparar pausa: Público amplo' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Preparar duplicação: Público amplo' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: /Salvar pack/ })).toBeNull();
  expect(salvarPackMeta).not.toHaveBeenCalled();
});

it('compacto preserva nomes acessíveis, foco e alvos de toque sem margem superior', () => {
  render(<AcoesDaHierarquia compacto contaRef="account_ref" campanhaRef="campaign_ref" referencia="ad_reference" nome="Peça compacta" entidade="anuncio" />);
  const grupo = screen.getByRole('group', { name: 'Ações de Peça compacta' });
  expect(grupo.classList.contains('inline-flex')).toBe(true);
  expect(grupo.classList.contains('mt-3')).toBe(false);
  const controles = within(grupo).getAllByRole('button');
  expect(controles).toHaveLength(3);
  expect(controles.map(button => button.getAttribute('aria-label'))).toEqual([
    'Preparar pausa: Peça compacta', 'Preparar duplicação: Peça compacta', 'Salvar pack: Peça compacta',
  ]);
  expect(controles.map(button => button.title)).toEqual([
    'Conferir proposta de pausa', 'Conferir proposta de duplicação', 'Guardar criativo e copy para reutilizar',
  ]);
  for (const button of controles) {
    expect(button.getAttribute('type')).toBe('button');
    expect(button.tabIndex).toBe(0);
    expect(button.classList.contains('h-11')).toBe(true);
    expect(button.classList.contains('w-11')).toBe(true);
    expect(button.classList.contains('md:h-10')).toBe(true);
    expect(button.className).toContain('focus-visible:ring-2');
    expect(button.querySelector('span')?.classList.contains('sr-only')).toBe(true);
    button.focus();
    expect(document.activeElement).toBe(button);
  }
  expect(salvarPackMeta).not.toHaveBeenCalled();
});

it('compacto do conjunto não oferece pack e modo padrão mantém rótulos visíveis', () => {
  const { rerender } = render(<AcoesDaHierarquia compacto contaRef="account_ref" campanhaRef="campaign_ref" referencia="adset_reference" nome="Público amplo" entidade="conjunto" />);
  expect(screen.queryByRole('button', { name: /Salvar pack/ })).toBeNull();
  expect(screen.getAllByRole('button')).toHaveLength(2);
  rerender(<AcoesDaHierarquia contaRef="account_ref" campanhaRef="campaign_ref" referencia="adset_reference" nome="Público amplo" entidade="conjunto" />);
  expect(screen.getByRole('group').classList.contains('mt-3')).toBe(true);
  expect(screen.getByText('Preparar pausa').classList.contains('sr-only')).toBe(false);
});

it('compacto em demo prepara pausa só após conferir, sem invocar API real', async () => {
  const api = criarDadosDemoCampanha('campanha-descoberta-01')!;
  const ads = await api.inventarioMetaReadModel('anuncios', CONTA_DEMO_META);
  const ad = ads.items[0];
  const demoSpy = vi.spyOn(api, 'planejarGestaoMeta');
  const realSpy = vi.spyOn(pautadorApi, 'planejarGestaoMeta');
  const network = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Nenhuma rede esperada'));
  render(<MetaCampaignDemoContext.Provider value={api}><AcoesDaHierarquia compacto contaRef={CONTA_DEMO_META} campanhaRef="campanha-descoberta-01" entidade="anuncio" referencia={String(ad.entity_ref)} nome="Peça demo" /></MetaCampaignDemoContext.Provider>);
  fireEvent.click(screen.getByRole('button', { name: 'Preparar pausa: Peça demo' }));
  expect(screen.getByRole('dialog')).toBeTruthy();
  expect(demoSpy).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Conferir proposta' }));
  await screen.findByText('Proposta pronta · não aplicada');
  expect(demoSpy).toHaveBeenCalledOnce();
  expect(demoSpy).toHaveBeenCalledWith(expect.objectContaining({ entidade: 'anuncio', referencia: ad.entity_ref, acao: 'PAUSAR' }));
  expect(realSpy).not.toHaveBeenCalled();
  expect(network).not.toHaveBeenCalled();
  expect(salvarPackMeta).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: 'Ativar' })).toBeNull();
});

it('anúncio abre proposta no escopo demo, sem mutação e sem chamada ao banco', async () => {
  const api = criarDadosDemoCampanha('campanha-descoberta-01')!;
  const ads = await api.inventarioMetaReadModel('anuncios', CONTA_DEMO_META);
  const ad = ads.items[0];
  const spy = vi.spyOn(api, 'planejarGestaoMeta');
  render(<MetaCampaignDemoContext.Provider value={api}><AcoesDaHierarquia contaRef={CONTA_DEMO_META} campanhaRef="campanha-descoberta-01" entidade="anuncio" referencia={String(ad.entity_ref)} nome="Peça A" /></MetaCampaignDemoContext.Provider>);
  expect(spy).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Preparar duplicação: Peça A' }));
  fireEvent.click(screen.getByRole('button', { name: 'Conferir proposta' }));
  await screen.findByText('Proposta pronta · não aplicada');
  expect(spy).toHaveBeenCalledWith(expect.objectContaining({ entidade:'anuncio', referencia:ad.entity_ref, acao:'DUPLICAR_ANUNCIO' }));
  expect(salvarPackMeta).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: 'Ativar' })).toBeNull();
});

it('pack real somente é salvo após confirmação e inclui o alvo correto', async () => {
  vi.mocked(salvarPackMeta).mockResolvedValue({ id:'pack' } as never);
  render(<AcoesDaHierarquia contaRef="account_ref" campanhaRef="campaign_ref" referencia="ad_reference" nome="Peça A" entidade="anuncio" />);
  fireEvent.click(screen.getByRole('button', { name:'Salvar pack: Peça A' }));
  expect(salvarPackMeta).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name:'Salvar pack' }));
  await waitFor(() => expect(salvarPackMeta).toHaveBeenCalledTimes(1));
  expect(salvarPackMeta).toHaveBeenCalledWith({ conta_ref:'account_ref', campanha_ref:'campaign_ref', referencia:'ad_reference', entidade:'anuncio', nome:'Peça A · pack' });
  await screen.findByText(/Pack salvo em Meus packs/);
});
