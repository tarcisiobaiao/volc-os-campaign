/**
 * Os números de entrega de UMA campanha, prontos para a faixa de instrumento.
 *
 * Módulo puro. Mesmas leis da faixa do Hub (PRODUCT §4): nulo fica nulo, zero
 * medido é `zero`, e dinheiro sem moeda declarada não é desenhado como reais.
 */
import type { Verdade } from '@/components/sistema/VerdadeDoDado';
import type { FormatoDeNumero } from '@/lib/instrumento';
import type { CampanhaNoInventario } from '@/types/trafego';

import type { NumeroDaFaixa } from './faixaDoHub';

export interface EntregaNaFaixa {
  formatoDeDinheiro: FormatoDeNumero;
  custo: NumeroDaFaixa;
  cliques: NumeroDaFaixa;
  impressoes: NumeroDaFaixa;
  cpc: NumeroDaFaixa;
  lidoEm: string | null;
}

const SEM_MOEDA = 'a conta não declarou a moeda: o valor é real, a unidade não';

function numero(valor: number | null, base: Verdade, detalhe?: string): NumeroDaFaixa {
  if (valor == null) return { valor: null, verdade: 'desconhecido', detalhe };
  return { valor, verdade: valor === 0 && base === 'real' ? 'zero' : base, detalhe };
}

export function entregaNaFaixa(c: Pick<CampanhaNoInventario, 'entrega'>): EntregaNaFaixa {
  const e = c.entrega;
  const moeda = e.moeda;
  const formatoDeDinheiro: FormatoDeNumero = moeda
    ? { tipo: 'moeda', moeda }
    : { tipo: 'decimal', casas: 2 };
  const custo = e.custo_micros == null ? null : e.custo_micros / 1_000_000;
  const verdadeDoDinheiro: Verdade = moeda ? 'real' : 'parcial';
  const detalheDoDinheiro = moeda ? undefined : SEM_MOEDA;
  const cpc =
    custo != null && e.cliques != null && e.cliques > 0
      ? numero(custo / e.cliques, verdadeDoDinheiro, detalheDoDinheiro)
      : {
          valor: null,
          verdade: 'desconhecido' as Verdade,
          detalhe: e.cliques === 0 ? 'nenhum clique medido; custo por clique não se aplica' : undefined,
        };
  return {
    formatoDeDinheiro,
    custo: numero(custo, verdadeDoDinheiro, detalheDoDinheiro),
    cliques: numero(e.cliques, 'real'),
    impressoes: numero(e.impressoes, 'real'),
    cpc,
    lidoEm: e.leitura?.lido_em ?? null,
  };
}
