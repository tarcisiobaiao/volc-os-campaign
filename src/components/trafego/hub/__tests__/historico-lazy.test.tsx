// @vitest-environment jsdom
/**
 * Histórico lazy: zero request de removidas enquanto o operador não abre.
 *
 * Conta chamadas à API, não o que a tela desenhou.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { FiltrosDoInventario, QuadroDeAlertas } from '@/types/trafego';
import HubDeTrafegoPage from '@/pages/trafego/HubDeTrafegoPage';
import {
  campanhaRemovida,
  creditoUp,
  inventarioDeProva,
  maquininha,
  quadroDeAlertasDeProva,
} from '@/components/trafego/inventario/fixtureDeProvas';

const api = vi.hoisted(() => ({
  inventario: vi.fn(),
  atualizarConta: vi.fn(),
}));

vi.mock('@/lib/pautadorApi', () => ({ pautadorApi: api }));

vi.mock('@/hooks/useNotificacoes', () => ({
  useNotificacoes: () => ({
    data: quadroDeAlertasDeProva() as QuadroDeAlertas,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
  INTERVALO_NOTIFICACOES_MS: 600000,
  CHAVE_NOTIFICACOES: ['notificacoes', 'trafego'],
}));

vi.mock('@/components/trafego/atencao/useAtencao', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/trafego/atencao/useAtencao')>()),
  useContadorDeAtencao: () => 0,
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

function pedeHistorico(filtros?: FiltrosDoInventario) {
  if (!filtros) return false;
  if (filtros.incluir_historico === true) return true;
  return (filtros.estado_externo ?? []).includes('REMOVED');
}

const operacional = inventarioDeProva({
  frescor: 'recente',
  parcial: false,
  faltou: [],
  contas: [{ ...creditoUp, quantidade: 1, campanhas: [maquininha] }],
  totais: { contas: 1, operacionais: 4, historicas: 12, geral: 16, atencao: 0 },
});

const removido = inventarioDeProva({
  frescor: 'recente',
  parcial: false,
  faltou: [],
  contas: [{ ...creditoUp, quantidade: 1, campanhas: [campanhaRemovida] }],
  totais: { contas: 1, operacionais: 0, historicas: 12, geral: 12, atencao: 0 },
});

function montar() {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0, gcTime: 5 * 60 * 1000 } },
  });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={['/trafego']}>
        <HubDeTrafegoPage oportunidades={<div>quadro</div>} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.inventario.mockImplementation((filtros?: FiltrosDoInventario) => {
    if (pedeHistorico(filtros)) return Promise.resolve(removido);
    return Promise.resolve(operacional);
  });
  Object.defineProperty(window, 'innerWidth', { value: 1440, writable: true, configurable: true });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('histórico realmente lazy', () => {
  it('fechado: zero request com incluir_historico ou REMOVED; a contagem vem do envelope operacional', async () => {
    montar();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Mostrar histórico removido: 12' })).toBeTruthy();
    });
    const historicas = api.inventario.mock.calls.filter(([filtros]) => pedeHistorico(filtros));
    expect(historicas).toHaveLength(0);
    expect(screen.queryByRole('region', { name: 'histórico removido' })).toBeNull();
  });

  it('abrir dispara a leitura; fechar e reabrir reusa o cache e mantém a contagem', async () => {
    montar();
    const botao = await screen.findByRole('button', { name: 'Mostrar histórico removido: 12' });
    expect(api.inventario.mock.calls.filter(([filtros]) => pedeHistorico(filtros))).toHaveLength(0);

    fireEvent.click(botao);
    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'histórico removido' })).toBeTruthy();
    });
    expect(api.inventario.mock.calls.filter(([filtros]) => pedeHistorico(filtros))).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'ocultar histórico removido' }));
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: 'histórico removido' })).toBeNull();
    });
    expect(screen.getByRole('button', { name: 'Mostrar histórico removido: 12' })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Mostrar histórico removido: 12' }));
    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'histórico removido' })).toBeTruthy();
    });
    expect(api.inventario.mock.calls.filter(([filtros]) => pedeHistorico(filtros))).toHaveLength(1);
  });
});
