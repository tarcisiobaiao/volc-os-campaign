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

  it('carimbo real em pt-BR antigo aparece vencido, não "relógio fora" nem "nunca lido"', async () => {
    getSettings.mockResolvedValue([
      { key: 'google_ads_last_update', value: '11/03/2026, 06:00:17' },
      { key: 'gam_last_update', value: '25/06/2026, 06:00:17' },
    ]);
    montar();
    await waitFor(() => expect(document.querySelectorAll('[data-frescor]')).toHaveLength(2));
    const niveis = Array.from(document.querySelectorAll('[data-frescor]')).map((e) => e.getAttribute('data-frescor'));
    expect(niveis).toEqual(['vencido', 'vencido']);
    expect(document.body.textContent).not.toContain('Relógio fora de sincronia');
    expect(document.body.textContent).not.toContain('Nunca lido');
  });

  it('carimbo em formato desconhecido diz "Carimbo ilegível"', async () => {
    getSettings.mockResolvedValue([{ key: 'google_ads_last_update', value: 'ontem às 6h' }]);
    montar();
    await waitFor(() => expect(screen.getByText('Carimbo ilegível')).toBeTruthy());
    // A outra fonte não tem carimbo: essa sim é "nunca lido".
    expect(screen.getByText('Nunca lido')).toBeTruthy();
  });
});
