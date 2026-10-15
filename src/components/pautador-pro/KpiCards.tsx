import React from 'react';

import { FaixaDeMetricas, PainelInstrumento } from '@/components/sistema/PainelInstrumento';
import { Metrica } from '@/components/sistema/Metrica';
import type { Verdade } from '@/components/sistema/VerdadeDoDado';

interface KpiCardsProps {
  total: number;
  gold: number;
  aTier: number;
  /** `null` = nenhum card tem nota. Nunca 0 inventado. */
  avg: number | null;
  /** Quantos cards entraram na média. */
  comNota?: number;
  ready: number;
  /** De onde vêm os cards: persistidos são reais; efêmeros são demonstração. */
  verdade: Verdade;
  carregando?: boolean;
}

/**
 * O pulso do Pautador como faixa de instrumento (V3, D0), não como cinco
 * cartões iguais com ícone em caixa — PRODUCT.md §9 recusa a grade de cartões
 * idênticos para o mesmo tipo de fato.
 *
 * A métrica dominante é "prontos para escrever": é o número que passa a vez ao
 * Redator. As demais descrevem a qualidade do quadro.
 */
export const KpiCards: React.FC<KpiCardsProps> = ({
  total, gold, aTier, avg, comNota, ready, verdade, carregando,
}) => {
  const detalhe = verdade === 'demo' ? 'descoberta efêmera, não persistida' : undefined;
  return (
    <PainelInstrumento aria-label="Pulso do Pautador">
      <FaixaDeMetricas>
        <Metrica tamanho="hero" rotulo="Prontos para escrever" valor={ready}
                 formato={{ tipo: 'inteiro' }} verdade={verdade} detalheDaVerdade={detalhe}
                 carregando={carregando} />
        <Metrica rotulo="Oportunidades" valor={total} formato={{ tipo: 'inteiro' }}
                 verdade={verdade} detalheDaVerdade={detalhe} carregando={carregando} />
        <Metrica rotulo="Ouro puro (S)" valor={gold} formato={{ tipo: 'inteiro' }}
                 verdade={verdade} detalheDaVerdade={detalhe} carregando={carregando} />
        <Metrica rotulo="Ouro (A)" valor={aTier} formato={{ tipo: 'inteiro' }}
                 verdade={verdade} detalheDaVerdade={detalhe} carregando={carregando} />
        <Metrica rotulo={comNota != null && comNota < total ? `Nota média · ${comNota} de ${total}` : 'Nota média'}
                 valor={avg} formato={{ tipo: 'decimal', casas: 2 }}
                 verdade={avg == null ? 'desconhecido' : comNota != null && comNota < total ? 'parcial' : verdade}
                 detalheDaVerdade={avg == null ? 'nenhum card tem nota ainda' : comNota != null && comNota < total ? 'cards sem nota ficam fora da média' : detalhe}
                 carregando={carregando} />
      </FaixaDeMetricas>
    </PainelInstrumento>
  );
};
