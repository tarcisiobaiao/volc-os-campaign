// @vitest-environment jsdom
/**
 * O fluxo editorial v2 se liga POR FUNIL na tela de disparo — e nasce desligado.
 *
 * S2 · item 1 (30/09/2026). O motor e o backend já sabiam ligar o v2 pelo
 * perfil do run; faltava a tela. Contrato:
 *   1. desligado, o pedido é o de SEMPRE (sem a chave `editorial_v2`);
 *   2. ligado, o pedido leva `editorial_v2: true`;
 *   3. reaberta, a tela lembra a escolha do último run deste card.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const { destinosPublicacao, runsDoRedator, dispararRedator } = vi.hoisted(() => ({
  destinosPublicacao: vi.fn(),
  runsDoRedator: vi.fn(),
  dispararRedator: vi.fn(),
}));

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: { destinosPublicacao, runsDoRedator, dispararRedator },
  PautadorApiError: class extends Error {},
}));
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock('../BriefingAcoes', () => ({ BriefingAcoes: () => null, temBriefing: () => false }));

import { DispararRedatorDialog } from '../DispararRedatorDialog';

const CARD = { id: 42, display_title: 'Cursos Senac' } as never;
const DESTINO = { project_id: 9, nome: 'CreditoUp', apto: true, motivo: 'pronto' };

beforeAll(() => {
  // Radix pede ResizeObserver; o jsdom não tem.
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver ??= class {
    observe() {} unobserve() {} disconnect() {}
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function montar(runs: unknown[] = []) {
  destinosPublicacao.mockResolvedValue([DESTINO]);
  runsDoRedator.mockResolvedValue(runs);
  dispararRedator.mockResolvedValue({
    run: { id: 1, opportunity_id: 42, project_id: 9, status: 'queued', modo: 'publicado' },
    motor_conectado: true, aviso: null,
  });
  render(<DispararRedatorDialog card={CARD} aberto aoFechar={() => {}} />);
}

async function interruptor() {
  return screen.findByRole('switch', { name: /editorial v2/i });
}

describe('DispararRedatorDialog · fluxo editorial v2', () => {
  it('nasce desligado e, desligado, dispara o pedido de sempre', async () => {
    montar();
    const sw = await interruptor();
    expect(sw.getAttribute('aria-checked')).toBe('false');

    fireEvent.click(screen.getByRole('button', { name: /gerar funil/i }));
    await waitFor(() => expect(dispararRedator).toHaveBeenCalledTimes(1));
    expect(dispararRedator.mock.calls[0][0]).toEqual({ opportunity_id: 42, project_id: 9 });
  });

  it('ligado, o pedido leva editorial_v2: true', async () => {
    montar();
    const sw = await interruptor();
    fireEvent.click(sw);
    expect(sw.getAttribute('aria-checked')).toBe('true');

    fireEvent.click(screen.getByRole('button', { name: /gerar funil/i }));
    await waitFor(() => expect(dispararRedator).toHaveBeenCalledTimes(1));
    expect(dispararRedator.mock.calls[0][0]).toEqual({
      opportunity_id: 42, project_id: 9, editorial_v2: true,
    });
  });

  it('reabre com a escolha do último run deste card', async () => {
    montar([{ id: 7, opportunity_id: 42, project_id: 9, status: 'done',
              modo: 'publicado', editorial_v2: true }]);
    const sw = await interruptor();
    await waitFor(() => expect(sw.getAttribute('aria-checked')).toBe('true'));
  });
});
