// @vitest-environment jsdom
/**
 * O funil sincroniza com o WordPress sozinho.
 *
 * ⚠️ Medido em 19/08/2026: o operador publicou as 6 páginas do run 7 no
 * WordPress e a tela continuou dizendo "rascunho no WP" nas seis. O botão
 * "reler do WordPress" existia — exigir que alguém lembre de clicá-lo é o
 * defeito, não a solução.
 *
 * Quem publica é o humano, no WordPress, fora deste sistema. `status_wp` é
 * gravado UMA vez pelo worker; daí em diante o nosso banco é cache. Cache que
 * só atualiza no botão mente por padrão.
 *
 * O risco de sincronizar sozinho é o LAÇO — reler dispara `recarregar()`, que
 * muda a matriz, que reavalia o efeito. A guarda por run é o que impede, e é o
 * que estes testes protegem.
 */
import { cleanup, render, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const relerDoWordPress = vi.hoisted(() => vi.fn());
const paginasDoRun = vi.hoisted(() => vi.fn());
const runsDoRedator = vi.hoisted(() => vi.fn());
const usarMatriz = vi.hoisted(() => vi.fn());

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: { relerDoWordPress, paginasDoRun, runsDoRedator },
}));
// A matriz vem de um hook, não da api direto — mockar o hook é o que permite
// controlar `publicadas`, que é o gatilho da sincronia.
vi.mock('@/hooks/redator/useMatrizDoRun', () => ({
  useMatrizDoRun: () => usarMatriz(),
}));
vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import FunilPage from '../FunilPage';

afterEach(() => { cleanup(); vi.clearAllMocks(); });

const comMatriz = (publicadas: unknown[]) => ({
  matriz: {
    run: { id: 7, status: 'done', paginas_planejadas: 6,
           opportunity_id: 74, nicho: 'Maquininha' },
    publicadas, celulas: {}, faixa: {}, titulo: 'Maquininha de Cartão',
    custo_total: 1.23, teto_usd: 5, passos: [],
  },
  carregando: false, erro: null, pulsou: false, corrente: null,
  segundosSemCobranca: 0, recarregar: vi.fn(),
});

const seis = (status: string) => Array.from({ length: 6 }, (_, i) => ({
  page_number: i + 1, status_wp: status, url: null, post_id: 2160 + i,
}));

const montar = () => render(
  <MemoryRouter initialEntries={['/redator/funil/7']}>
    <Routes><Route path="/redator/funil/:runId" element={<FunilPage />} /></Routes>
  </MemoryRouter>,
);

describe('sincronia com o WordPress', () => {
  it('relê ao abrir, sem o operador pedir', async () => {
    usarMatriz.mockReturnValue(comMatriz(seis('draft')));
    paginasDoRun.mockResolvedValue(null);
    runsDoRedator.mockResolvedValue([]);
    relerDoWordPress.mockResolvedValue({
      run_row_id: 7, paginas: [], mudaram: 6, no_ar: 6,
      resumo: '6 páginas passaram a publish',
    });
    montar();
    await waitFor(() => expect(relerDoWordPress).toHaveBeenCalledWith(7));
  });

  it('NÃO relê em laço — uma vez por run', async () => {
    usarMatriz.mockReturnValue(comMatriz(seis('draft')));
    paginasDoRun.mockResolvedValue(null);
    runsDoRedator.mockResolvedValue([]);
    relerDoWordPress.mockResolvedValue({
      run_row_id: 7, paginas: [], mudaram: 6, no_ar: 6, resumo: 'ok',
    });
    montar();
    await waitFor(() => expect(relerDoWordPress).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 150));
    expect(relerDoWordPress).toHaveBeenCalledTimes(1);
  });

  it('não relê quando não há página publicada — nada a sincronizar', async () => {
    usarMatriz.mockReturnValue(comMatriz([]));
    paginasDoRun.mockResolvedValue(null);
    runsDoRedator.mockResolvedValue([]);
    montar();
    await new Promise((r) => setTimeout(r, 150));
    expect(relerDoWordPress).not.toHaveBeenCalled();
  });

  it('falha na leitura não derruba a tela', async () => {
    usarMatriz.mockReturnValue(comMatriz(seis('draft')));
    paginasDoRun.mockResolvedValue(null);
    runsDoRedator.mockResolvedValue([]);
    relerDoWordPress.mockRejectedValue(new Error('WordPress fora do ar'));
    const { container } = montar();
    await waitFor(() => expect(relerDoWordPress).toHaveBeenCalled());
    expect(container.textContent).toBeTruthy();
  });
});
