// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AcoesDaHierarquia } from '../AcoesDaHierarquia';
import { MetaCampaignDemoContext } from '../MetaCampaignData';
import { criarDadosDemoCampanha, CONTA_DEMO_META } from '../demoCampaignData';
import { salvarPackMeta } from '@/features/creative-studio/api';
vi.mock('@/features/creative-studio/api', () => ({ salvarPackMeta: vi.fn() }));
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

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
