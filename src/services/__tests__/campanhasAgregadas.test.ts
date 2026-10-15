import { describe, expect, it } from 'vitest';
import { lerCampanhasAgregadas, type ClienteRpc } from '../campanhasAgregadas';

type Chamada = { fn: string; params: Record<string, unknown>; ordem?: string; de?: number; ate?: number };

/** Dublê do PostgREST: devolve fatias de `linhas` conforme o range pedido. */
function clienteFalso(linhas: unknown[], erroNaPagina?: number): { cliente: ClienteRpc; chamadas: Chamada[] } {
  const chamadas: Chamada[] = [];
  const cliente: ClienteRpc = {
    rpc(fn, params) {
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
          const pagina = chamadas.length - 1;
          if (pagina === erroNaPagina) {
            return Promise.resolve({ data: null, error: { message: 'boom', code: 'XX000' } });
          }
          return Promise.resolve({ data: linhas.slice(de, ate + 1), error: null });
        },
      };
      return builder;
    },
  };
  return { cliente, chamadas };
}

const PARAMS = { p_project_id: null, p_start_date: '2026-10-14', p_end_date: '2026-10-14' };

describe('lerCampanhasAgregadas', () => {
  it('chama a assinatura de 3 parâmetros que existe em produção, sem p_limit/p_offset', async () => {
    const { cliente, chamadas } = clienteFalso([{ campaign_id: 'a' }]);
    await lerCampanhasAgregadas(cliente, PARAMS);
    expect(chamadas[0].fn).toBe('get_campaigns_aggregated');
    expect(chamadas[0].params).toEqual(PARAMS);
    expect(chamadas[0].params).not.toHaveProperty('p_limit');
    expect(chamadas[0].params).not.toHaveProperty('p_offset');
  });

  it('pagina pelo range do PostgREST com ordem estável por campaign_id', async () => {
    const linhas = Array.from({ length: 5 }, (_, i) => ({ campaign_id: `c${i}` }));
    const { cliente, chamadas } = clienteFalso(linhas);
    const r = await lerCampanhasAgregadas(cliente, PARAMS, { tamanhoPagina: 2 });
    expect(r.erro).toBeNull();
    expect(r.linhas).toEqual(linhas);
    expect(chamadas.map((c) => [c.ordem, c.de, c.ate])).toEqual([
      ['campaign_id', 0, 1],
      ['campaign_id', 2, 3],
      ['campaign_id', 4, 5],
    ]);
  });

  it('para quando a página volta cheia e a seguinte vazia', async () => {
    const linhas = Array.from({ length: 4 }, (_, i) => ({ campaign_id: `c${i}` }));
    const { cliente, chamadas } = clienteFalso(linhas);
    const r = await lerCampanhasAgregadas(cliente, PARAMS, { tamanhoPagina: 2 });
    expect(r.linhas).toHaveLength(4);
    expect(chamadas).toHaveLength(3);
  });

  it('devolve o erro do PostgREST e descarta páginas parciais', async () => {
    const linhas = Array.from({ length: 5 }, (_, i) => ({ campaign_id: `c${i}` }));
    const { cliente } = clienteFalso(linhas, 1);
    const r = await lerCampanhasAgregadas(cliente, PARAMS, { tamanhoPagina: 2 });
    expect(r.erro).toMatchObject({ message: 'boom' });
    expect(r.linhas).toEqual([]);
  });

  it('acusa truncamento quando bate no teto de páginas, em vez de devolver lista cortada', async () => {
    const linhas = Array.from({ length: 10 }, (_, i) => ({ campaign_id: `c${i}` }));
    const { cliente } = clienteFalso(linhas);
    const r = await lerCampanhasAgregadas(cliente, PARAMS, { tamanhoPagina: 2, tetoPaginas: 3 });
    expect(r.erro).toMatchObject({ code: 'teto_de_paginas' });
    expect(r.linhas).toEqual([]);
  });
});
