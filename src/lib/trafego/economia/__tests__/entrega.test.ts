/**
 * A entrega de uma campanha na faixa de instrumento: zero medido é afirmação,
 * nulo é ausência, e dinheiro sem moeda não vira reais.
 */
import { describe, expect, it } from 'vitest';

import { entregaNaFaixa } from '@/lib/trafego/economia/entrega';
import type { Entrega } from '@/types/trafego';

const entrega = (over: Partial<Entrega> = {}): { entrega: Entrega } => ({
  entrega: {
    impressoes: 1000,
    cliques: 40,
    custo_micros: 30_000_000,
    moeda: 'BRL',
    leitura: { lido_em: '2026-10-15T12:00:00Z', idade_s: 60 },
    ...over,
  },
});

describe('entregaNaFaixa', () => {
  it('custo em moeda, CPC derivado, frescor da leitura', () => {
    const n = entregaNaFaixa(entrega());
    expect(n.custo).toMatchObject({ valor: 30, verdade: 'real' });
    expect(n.cpc.valor).toBeCloseTo(0.75, 6);
    expect(n.formatoDeDinheiro).toEqual({ tipo: 'moeda', moeda: 'BRL' });
    expect(n.lidoEm).toBe('2026-10-15T12:00:00Z');
  });

  it('zero medido vira "zero", não "desconhecido"', () => {
    const n = entregaNaFaixa(entrega({ custo_micros: 0, cliques: 0 }));
    expect(n.custo.verdade).toBe('zero');
    expect(n.cliques.verdade).toBe('zero');
    expect(n.cpc).toMatchObject({ valor: null, verdade: 'desconhecido' });
    expect(n.cpc.detalhe).toMatch(/nenhum clique/);
  });

  it('nulo continua nulo', () => {
    const n = entregaNaFaixa(entrega({ impressoes: null, custo_micros: null }));
    expect(n.impressoes).toMatchObject({ valor: null, verdade: 'desconhecido' });
    expect(n.custo.valor).toBeNull();
    expect(n.cpc.valor).toBeNull();
  });

  it('sem moeda declarada o dinheiro é parcial e não é formatado como moeda', () => {
    const n = entregaNaFaixa(entrega({ moeda: null }));
    expect(n.formatoDeDinheiro.tipo).toBe('decimal');
    expect(n.custo.verdade).toBe('parcial');
    expect(n.custo.detalhe).toMatch(/moeda/);
  });
});
