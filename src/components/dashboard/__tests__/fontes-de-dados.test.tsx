// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';

const getSettings = vi.fn();
vi.mock('@/lib/secureApi', () => ({ secureApi: { getSettings: (...a: unknown[]) => getSettings(...a) } }));

import { FontesDeDados } from '@/components/dashboard/FontesDeDados';

afterEach(() => {
  cleanup();
  getSettings.mockReset();
});

const montar = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FontesDeDados />
    </QueryClientProvider>,
  );

describe('fontes de dados da home', () => {
  it('sem carimbo, não afirma "online": diz que não há leitura', async () => {
    getSettings.mockResolvedValue([]);
    montar();
    await waitFor(() => expect(getSettings).toHaveBeenCalled());
    await waitFor(() => expect(document.body.textContent).not.toContain('Consultando'));
    expect(document.body.textContent?.toLowerCase()).not.toContain('online');
  });

  it('com a rota fora, diz que não foi possível consultar', async () => {
    getSettings.mockRejectedValue(new Error('503'));
    montar();
    // O componente tenta uma vez de novo antes de desistir (retry: 1).
    await waitFor(() => expect(screen.getAllByText('Não foi possível consultar')).toHaveLength(2), { timeout: 4000 });
  });
});
