/**
 * Fiação: o dashboard (supabaseDataService.getCampaignsWithRevenue com período)
 * tem de ler a RPC pelo helper paginado, com a assinatura de 3 parâmetros que
 * existe em produção. Se alguém religar a chamada antiga (p_limit/p_offset), o
 * teste do helper continua verde; este quebra.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

type Chamada = { fn: string; params: Record<string, unknown>; ordem?: string; de?: number; ate?: number };
const chamadas: Chamada[] = [];

vi.mock('@/lib/supabase', () => {
  const consulta: any = new Proxy(
    {},
    {
      get: (_alvo, prop) =>
        prop === 'then'
          ? (resolve: (v: unknown) => void) => resolve({ data: [], error: null, count: 0 })
          : () => consulta,
    },
  );
  return {
    supabase: {
      rpc(fn: string, params: Record<string, unknown>) {
        const chamada: Chamada = { fn, params };
        chamadas.push(chamada);
        const builder = {
          order(coluna: string) {
            chamada.ordem = coluna;
            return builder;
          },
          range(de: number, ate: number) {
            chamada.de = de;
            chamada.ate = ate;
            return Promise.resolve({ data: [], error: null });
          },
          then(resolve: (v: unknown) => void) {
            resolve({ data: [], error: null });
          },
        };
        return builder;
      },
      from: () => consulta,
    },
  };
});

describe('getCampaignsWithRevenue com período', () => {
  beforeEach(() => {
    chamadas.length = 0;
    const mem = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => mem.get(k) ?? null,
      setItem: (k: string, v: string) => void mem.set(k, v),
      removeItem: (k: string) => void mem.delete(k),
    });
  });

  it('chama get_campaigns_aggregated pelo helper: 3 parâmetros, order por campaign_id e range', async () => {
    const { supabaseDataService } = await import('../supabaseDataService');
    await supabaseDataService
      .getCampaignsWithRevenue({ period: 'custom', date: '2026-10-14' })
      .catch(() => undefined);

    const rpc = chamadas.filter((c) => c.fn === 'get_campaigns_aggregated');
    expect(rpc.length).toBeGreaterThan(0);
    expect(rpc[0].params).toEqual({ p_project_id: null, p_start_date: '2026-10-14', p_end_date: '2026-10-14' });
    expect(rpc[0].params).not.toHaveProperty('p_limit');
    expect(rpc[0].ordem).toBe('campaign_id');
    expect([rpc[0].de, rpc[0].ate]).toEqual([0, 499]);
  });
});
