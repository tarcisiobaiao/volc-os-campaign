// @vitest-environment jsdom
/**
 * H0: só o endpoint canônico. 404 ≠ indisponibilidade. Sem inventário, sem id externo.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CampanhaCanonPage from '@/pages/trafego/CampanhaCanonPage';
import { maquininha } from '@/components/trafego/inventario/fixtureDeProvas';
import { FRASES_DE_FALHA } from '@/components/trafego/inventario/erros';
import type { CampanhaCanonica, CampanhaNoInventario, ManifestoDeCanal } from '@/types/trafego';

class ErroComStatus extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const api = vi.hoisted(() => ({
  campanhaCanonica: vi.fn(),
  // A rota de diagnóstico ainda não existe neste servidor, e o dublê diz isso
  // com o status real em vez de estourar: assim a página exercita o ramo
  // "capacidade não ligada", que é o estado de produção hoje.
  diagnosticoDeEntrega: vi.fn(() =>
    Promise.reject(Object.assign(new Error('rota ausente'), { status: 404 })),
  ),
  inventario: vi.fn(() => {
    throw new Error('H0 não pode percorrer o inventário');
  }),
}));

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: api,
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const manifestoSearch: ManifestoDeCanal = {
  plataforma: 'GOOGLE_ADS',
  canal: 'SEARCH',
  rotulo: 'Search',
  hierarquia: ['campanha', 'grupo', 'anúncio'],
  paineis: ['resumo'],
  campos_do_pedido: ['orçamento'],
  capacidades: ['ler', 'propor'],
  provas_obrigatorias: [],
  indisponibilidades: ['nenhuma regra de bidding está aprovada'],
  sabe_criar: false,
};

function detalheDe(
  campanha: CampanhaNoInventario,
  manifesto: ManifestoDeCanal | null,
): CampanhaCanonica {
  return {
    versao: 2,
    campanha,
    identidade: {
      volc_campaign_id: campanha.volc_campaign_id,
      campaign_lineage_id: campanha.campaign_lineage_id,
      plataforma: 'GOOGLE_ADS',
      conta_externa: campanha.externa.customer_id,
      id_externo: campanha.externa.campaign_id,
    },
    conta: {
      customer_id: campanha.externa.customer_id,
      frescor: 'recente',
      tentativa_resultado: 'ok',
    },
    manifesto,
  };
}

function montar(endereco: string) {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[endereco]}>
        <Routes>
          <Route path="/trafego/campanhas/:volcCampaignId" element={<CampanhaCanonPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.campanhaCanonica.mockReset();
  api.inventario.mockClear();
  Object.defineProperty(window, 'innerWidth', { value: 1440, writable: true, configurable: true });
});
afterEach(cleanup);

describe('H0 usa somente o endpoint canônico', () => {
  it('o código não percorre o inventário', () => {
    const page = readFileSync('src/pages/trafego/CampanhaCanonPage.tsx', 'utf8');
    const hook = readFileSync('src/hooks/useCampanhaCanonica.ts', 'utf8');
    expect(page + hook).not.toMatch(/useInventario/);
    expect(page + hook).not.toMatch(/pautadorApi\.inventario/);
    expect(hook).toMatch(/campanhaCanonica/);
  });

  it('o detalhe vem de campanhaCanonica, e o inventário não é chamado', async () => {
    api.campanhaCanonica.mockResolvedValue(detalheDe(maquininha, manifestoSearch));
    montar(`/trafego/campanhas/${maquininha.volc_campaign_id}`);
    await screen.findByRole('heading', { name: 'BR - Maquininha de Cartão' });
    expect(api.campanhaCanonica).toHaveBeenCalledTimes(1);
    expect(api.campanhaCanonica).toHaveBeenCalledWith(maquininha.volc_campaign_id);
    expect(api.inventario).not.toHaveBeenCalled();
  });

  it('um campaign_id externo não abre a campanha interna', async () => {
    api.campanhaCanonica.mockRejectedValue(new ErroComStatus('não encontrada', 404));
    montar(`/trafego/campanhas/${maquininha.externa.campaign_id}`);
    await screen.findByRole('heading', { name: 'Campanha não encontrada' });
    expect(screen.queryByRole('heading', { name: 'BR - Maquininha de Cartão' })).toBeNull();
    expect(api.campanhaCanonica).toHaveBeenCalledWith(maquininha.externa.campaign_id);
    expect(api.inventario).not.toHaveBeenCalled();
  });

  it('404 e indisponibilidade têm estados diferentes', async () => {
    api.campanhaCanonica.mockRejectedValue(new ErroComStatus('não encontrada', 404));
    const { unmount } = montar('/trafego/campanhas/vc_inexistente');
    await screen.findByRole('heading', { name: 'Campanha não encontrada' });
    expect(screen.queryByRole('heading', { name: 'Não consegui ler esta campanha' })).toBeNull();
    unmount();

    api.campanhaCanonica.mockRejectedValue(new ErroComStatus('snapshot indisponível', 503));
    montar('/trafego/campanhas/vc_24155134757');
    await screen.findByRole('heading', { name: 'Não consegui ler esta campanha' });
    expect(screen.getByText(FRASES_DE_FALHA.sistema_fora_do_ar.mensagem)).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Campanha não encontrada' })).toBeNull();
  });

  it('manifesto ausente não libera ação e não inventa capacidades zeradas', async () => {
    const video: CampanhaNoInventario = { ...maquininha, canal: 'VIDEO', nome: 'BR - Vídeo institucional' };
    api.campanhaCanonica.mockResolvedValue(detalheDe(video, null));
    montar(`/trafego/campanhas/${video.volc_campaign_id}`);
    await screen.findByRole('heading', { name: 'BR - Vídeo institucional' });
    expect(screen.getByText(/este canal aparece no inventário e o Hub não o opera/i)).toBeTruthy();
    expect(screen.queryByText(/sabe criar/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /criar/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /montar campanha/ })).toBeNull();
    expect(screen.queryByText(/Alterar orçamento/)).toBeNull();
  });

  it('rede e canal na URL não viram identidade factual', async () => {
    api.campanhaCanonica.mockResolvedValue(detalheDe(maquininha, manifestoSearch));
    montar(`/trafego/campanhas/${maquininha.volc_campaign_id}?rede=meta&canal=PERFORMANCE_MAX&secao=estrutura`);
    await screen.findByRole('heading', { name: 'BR - Maquininha de Cartão' });
    expect(screen.queryByText('Meta Ads')).toBeNull();
    expect(screen.queryByText('Performance Max')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Integração ainda não configurada' })).toBeNull();
    expect(screen.queryByText(/ad group/i)).toBeNull();
    expect(screen.queryByText(/ROAS/)).toBeNull();
  });

  it('não dispara escrita nem Google Ads no render', async () => {
    api.campanhaCanonica.mockResolvedValue(detalheDe(maquininha, manifestoSearch));
    montar(`/trafego/campanhas/${maquininha.volc_campaign_id}`);
    await waitFor(() => {
      expect(api.campanhaCanonica).toHaveBeenCalled();
    });
    expect(screen.queryByRole('button', { name: /alterar|duplicar|criar/i })).toBeNull();
    expect(api.inventario).not.toHaveBeenCalled();
  });
});
