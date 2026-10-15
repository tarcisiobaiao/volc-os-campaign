// @vitest-environment jsdom
/**
 * A recomendação em sombra DENTRO da página canônica, com fixture e sem rede.
 *
 * Prova a tradução da leitura: o 404 com o código do contrato é "nenhum
 * experimento olhou", e um 404 sem ele (backend antigo, rota inexistente) é
 * falha — nunca as duas coisas com a mesma frase.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CampanhaCanonPage from '@/pages/trafego/CampanhaCanonPage';
import { maquininha } from '@/components/trafego/inventario/fixtureDeProvas';
import { RECOMENDACAO_SENAC } from '@/components/trafego/sombra/fixtureSenac';
import type { CampanhaCanonica } from '@/types/trafego';

const api = vi.hoisted(() => ({
  campanhaCanonica: vi.fn(),
  recomendacaoShadow: vi.fn(),
  // As outras seções ficam pendentes: as provas aqui são só sobre a sombra.
  diagnosticoDeEntrega: vi.fn(() => new Promise(() => {})),
  correspondenciasDaCampanha: vi.fn(() => new Promise(() => {})),
  capacidades: vi.fn(() => new Promise(() => {})),
}));

vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: api }));
vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const detalhe: CampanhaCanonica = {
  versao: 2,
  campanha: maquininha,
  identidade: {
    volc_campaign_id: 'gads-5470000539-24278665189',
    campaign_lineage_id: null,
    plataforma: 'GOOGLE_ADS',
    conta_externa: '5470000539',
    id_externo: '24278665189',
  },
  conta: { customer_id: '5470000539', frescor: 'recente', tentativa_resultado: 'ok' },
  manifesto: null,
};

const erro = (status: number, corpo?: unknown) =>
  Object.assign(new Error(`falha ${status}`), { status, corpo });

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/trafego/campanhas/${detalhe.identidade.volc_campaign_id}`]}>
        <Routes>
          <Route path="/trafego/campanhas/:volcCampaignId" element={<CampanhaCanonPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Sob carga (load > 20 medido em 15/10), getByRole numa página inteira passa
// de 1 s; o teto maior não muda o que é provado.
const ESPERA = { timeout: 8000 };

const secao = () => screen.getByRole('region', { name: 'Recomendação em sombra' });

beforeEach(() => {
  vi.clearAllMocks();
  api.campanhaCanonica.mockResolvedValue(detalhe);
});
afterEach(cleanup);

describe('recomendação em sombra na página da campanha', () => {
  it('pede pelo id no Google e mostra a direção, sem botão na seção', async () => {
    api.recomendacaoShadow.mockResolvedValue(RECOMENDACAO_SENAC);
    montar();
    await waitFor(() => expect(secao().querySelector('table')).not.toBeNull(), ESPERA);
    expect(api.recomendacaoShadow).toHaveBeenCalledWith('24278665189');
    expect(within(secao()).getAllByText('pausar').length).toBeGreaterThan(0);
    expect(within(secao()).queryAllByRole('button')).toHaveLength(0);
  });

  it('404 do contrato é ausência de análise', async () => {
    api.recomendacaoShadow.mockRejectedValue(
      erro(404, { codigo: 'sem_recomendacao_shadow', mensagem: 'não há' }),
    );
    montar();
    await waitFor(() =>
      expect(within(secao()).getByRole('status').textContent).toMatch(/Nenhum experimento/),
      ESPERA,
    );
  });

  it('404 sem o código do contrato é falha, não ausência', async () => {
    api.recomendacaoShadow.mockRejectedValue(erro(404));
    montar();
    await waitFor(() =>
      expect(within(secao()).getByRole('alert').textContent).toMatch(/Não consegui ler/),
      ESPERA,
    );
    expect(within(secao()).queryByText(/Nenhum experimento/)).toBeNull();
  });

  it('409 de integridade não mostra número', async () => {
    api.recomendacaoShadow.mockRejectedValue(
      erro(409, { codigo: 'integridade_quebrada', mensagem: 'transformacao.csv não bate' }),
    );
    montar();
    await waitFor(() =>
      expect(within(secao()).getByRole('alert').textContent).toMatch(/integridade/),
      ESPERA,
    );
    expect(within(secao()).queryByRole('table')).toBeNull();
  });

  it('503 fonte indisponível não vira "nenhum experimento"', async () => {
    api.recomendacaoShadow.mockRejectedValue(
      erro(503, { codigo: 'fonte_indisponivel', mensagem: 'a pasta não existe neste servidor.' }),
    );
    montar();
    await waitFor(() =>
      expect(within(secao()).getByRole('alert').textContent).toMatch(/fonte .*indisponível/i),
      ESPERA,
    );
    expect(within(secao()).queryByText(/Nenhum experimento/)).toBeNull();
    expect(within(secao()).queryByRole('table')).toBeNull();
  });

  it('409 de experimentos ambíguos não escolhe um nem mostra número', async () => {
    api.recomendacaoShadow.mockRejectedValue(
      erro(409, { codigo: 'experimentos_ambiguos', mensagem: '2 experimentos com o mesmo as_of' }),
    );
    montar();
    await waitFor(() =>
      expect(within(secao()).getByRole('alert').textContent).toMatch(/mais de um experimento/),
      ESPERA,
    );
    expect(within(secao()).queryByRole('table')).toBeNull();
  });
});
