// @vitest-environment jsdom
/**
 * O DIAGNÓSTICO DENTRO DA PÁGINA CANÔNICA.
 *
 * A prova principal deste arquivo é sobre SILÊNCIO. Uma seção de diagnóstico
 * que simplesmente não aparece quando não há diagnóstico lê-se como "não há
 * nada de errado" — e é assim que uma tela induz a conclusão mais cara sem
 * escrever uma única frase falsa. Aqui, cada forma de não saber tem palavra:
 * apurando, capacidade não ligada, leitura falhou.
 *
 * Também prova que a visão do canal continua derivada do MANIFESTO, e que a
 * página segue sem tocar o Google Ads e sem percorrer a listagem paginada.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CampanhaCanonPage from '@/pages/trafego/CampanhaCanonPage';
import { maquininha } from '@/components/trafego/inventario/fixtureDeProvas';
import { derivarDiagnostico } from '@/lib/diagnostico/derivar';
import { proporMudancas } from '@/lib/diagnostico/propor';
import { evidenciaDeProva, ID_FGTS } from '@/lib/diagnostico/fixtureDeEvidencia';
import type { CampanhaCanonica, ManifestoDeCanal } from '@/types/trafego';

const api = vi.hoisted(() => ({
  campanhaCanonica: vi.fn(),
  diagnosticoDeEntrega: vi.fn(),
  // A página passou a perguntar de quem é a campanha e o que o operador pode.
  // ⚠️ Mockados como PROMESSA PENDENTE de propósito: assim as duas seções novas
  // ficam em carregamento e não emitem alerta próprio, e as provas abaixo
  // continuam sendo sobre o diagnóstico. Um `mockResolvedValue` aqui ligaria o
  // estado das outras seções ao acaso da fixture.
  correspondenciasDaCampanha: vi.fn(() => new Promise(() => {})),
  capacidades: vi.fn(() => new Promise(() => {})),
  inventario: vi.fn(() => {
    throw new Error('a página canônica não pode percorrer o inventário');
  }),
}));

vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: api }));
vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const manifesto: ManifestoDeCanal = {
  plataforma: 'GOOGLE_ADS',
  canal: 'SEARCH',
  rotulo: 'Search',
  hierarquia: ['campanha', 'grupo'],
  paineis: [],
  campos_do_pedido: ['orçamento'],
  capacidades: ['ler', 'propor'],
  provas_obrigatorias: [],
  indisponibilidades: ['nenhuma regra de bidding está aprovada (ADR-11)'],
  sabe_criar: false,
};

const detalhe = (m: ManifestoDeCanal | null): CampanhaCanonica => ({
  versao: 2,
  campanha: maquininha,
  identidade: {
    volc_campaign_id: 'gads-8017851692-241',
    campaign_lineage_id: null,
    plataforma: 'GOOGLE_ADS',
    conta_externa: '8017851692',
    id_externo: '241',
  },
  conta: { customer_id: '8017851692', frescor: 'recente', tentativa_resultado: 'ok' },
  manifesto: m,
});

function erroCom(status: number): Error {
  return Object.assign(new Error('falha de prova'), { status });
}

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={['/trafego/campanhas/gads-8017851692-241']}>
        <Routes>
          <Route path="/trafego/campanhas/:volcCampaignId" element={<CampanhaCanonPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.campanhaCanonica.mockResolvedValue(detalhe(manifesto));
});
afterEach(cleanup);

describe('⚠️ nenhuma forma de não saber é silêncio', () => {
  it('enquanto apura, mostra a FORMA do que vem e anuncia o estado', async () => {
    api.diagnosticoDeEntrega.mockReturnValue(new Promise(() => {}));
    const { container } = montar();
    await waitFor(() => expect(screen.getAllByText('diagnóstico de entrega').length).toBe(1));
    expect(screen.getByText('apurando por que esta campanha entrega ou não')).toBeTruthy();
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(3);
    for (const osso of container.querySelectorAll('.animate-pulse')) {
      expect(osso.className).toContain('motion-reduce:animate-none');
    }
  });

  it('servidor sem a rota diz que a AUSÊNCIA é da capacidade, não da campanha', async () => {
    api.diagnosticoDeEntrega.mockRejectedValue(erroCom(404));
    montar();
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /Este servidor ainda não apura diagnóstico/ }),
      ).toBeTruthy(),
    );
    expect(
      screen.getByText(/nada aqui afirma que a\s+campanha esteja bem/),
    ).toBeTruthy();
  });

  it('501 é lido como a mesma capacidade não ligada', async () => {
    api.diagnosticoDeEntrega.mockRejectedValue(erroCom(501));
    montar();
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /Este servidor ainda não apura diagnóstico/ }),
      ).toBeTruthy(),
    );
  });

  it('falha de verdade vira alerta com código para copiar — e não "sem diagnóstico"', async () => {
    api.diagnosticoDeEntrega.mockRejectedValue(erroCom(503));
    montar();
    // ⚠️ Escopado à seção do diagnóstico, e não `getByRole('alert')` na página
    // inteira. A página tem mais de uma seção que pode falhar de forma
    // independente — a revisão de correspondência é outra —, e duas falhas
    // simultâneas produzem dois alertas legitimamente. Ancorar no rótulo da
    // seção prova o que esta prova quer provar, sem depender de o resto da
    // página estar em silêncio.
    const secao = await screen.findByLabelText('diagnóstico de entrega');
    await waitFor(() => expect(within(secao).getByRole('alert')).toBeTruthy());
    expect(within(secao).getByRole('alert').textContent).toContain('não respondeu');
    expect(screen.getByText(/código desta ocorrência|Código da ocorrência/i)).toBeTruthy();
  });
});

describe('com diagnóstico, a escada e a caixa aparecem juntas', () => {
  it('mostra o veredito e a proposta que ele sustenta', async () => {
    const diagnostico = derivarDiagnostico(evidenciaDeProva(), ID_FGTS, {
      agora: new Date('2026-08-26T18:10:11.000Z'),
    });
    api.diagnosticoDeEntrega.mockResolvedValue({
      versao: 1,
      diagnostico,
      propostas: proporMudancas(diagnostico),
    });
    montar();

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /Entrega abaixo do possível — orçamento/ }),
      ).toBeTruthy(),
    );
    expect(screen.getByRole('heading', { name: /1 mudança recomendada/ })).toBeTruthy();
    expect(screen.getByText('Subir a verba diária')).toBeTruthy();
  });
});

describe('o canal continua derivado do manifesto', () => {
  it('manifesto sem construtor mostra a recusa declarada, não um botão cinza', async () => {
    api.diagnosticoDeEntrega.mockRejectedValue(erroCom(404));
    montar();
    await waitFor(() => expect(screen.getByLabelText('capacidades do canal')).toBeTruthy());
    expect(
      screen.getByText('criação indisponível: nenhuma regra de bidding está aprovada (ADR-11).'),
    ).toBeTruthy();
  });

  it('⚠️ `manifesto: null` diz que o Hub não opera o canal — e usa o nome do canal', async () => {
    api.campanhaCanonica.mockResolvedValue(detalhe(null));
    api.diagnosticoDeEntrega.mockRejectedValue(erroCom(404));
    montar();
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /não é operado pelo Hub/ })).toBeTruthy(),
    );
  });
});

describe('o portão da página', () => {
  it('não percorre a listagem paginada para montar o diagnóstico', async () => {
    api.diagnosticoDeEntrega.mockRejectedValue(erroCom(404));
    montar();
    await waitFor(() => expect(api.diagnosticoDeEntrega).toHaveBeenCalled());
    expect(api.inventario).not.toHaveBeenCalled();
  });

  it('pede o diagnóstico pela identidade INTERNA, nunca pelo id externo', async () => {
    api.diagnosticoDeEntrega.mockRejectedValue(erroCom(404));
    montar();
    await waitFor(() => expect(api.diagnosticoDeEntrega).toHaveBeenCalled());
    expect(api.diagnosticoDeEntrega).toHaveBeenCalledWith('gads-8017851692-241');
  });
});
