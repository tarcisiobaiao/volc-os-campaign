/**
 * A faixa econômica do Hub: um número herói e o resto da economia da carteira,
 * cada um com verdade e frescor (design.md §V3, PRODUCT §4).
 *
 * Quem decide valor e verdade é `projetarFaixaDoHub`; aqui só se desenha.
 * Receita e ROAS aparecem DE PROPÓSITO como indisponíveis: o lugar deles na
 * faixa é o que mostra ao operador que a economia ainda está aberta, em vez de
 * deixá-lo concluir que ela não importa.
 */
import React from 'react';

import { Metrica } from '@/components/sistema/Metrica';
import { FaixaDeMetricas, PainelInstrumento } from '@/components/sistema/PainelInstrumento';
import type { FormatoDeNumero } from '@/lib/instrumento';
import { JANELA_DO_ESPELHO, projetarFaixaDoHub } from '@/lib/trafego/economia/faixaDoHub';
import type { Inventario } from '@/types/trafego';

export interface FaixaEconomicaProps {
  inventario: Inventario | null;
  carregando: boolean;
  /** Relógio injetável, para teste e captura. */
  agora?: Date;
}

const INTEIRO: FormatoDeNumero = { tipo: 'inteiro' };
const RAZAO: FormatoDeNumero = { tipo: 'razao' };
/** Sem moeda declarada o número não ganha símbolo de ninguém. */
const SEM_MOEDA: FormatoDeNumero = { tipo: 'decimal' };

export const FaixaEconomica: React.FC<FaixaEconomicaProps> = ({ inventario, carregando, agora }) => {
  const faixa = projetarFaixaDoHub(inventario);
  const moeda: FormatoDeNumero = faixa?.moeda ? { tipo: 'moeda', moeda: faixa.moeda } : SEM_MOEDA;
  const lendo = carregando && !faixa;

  const legenda = faixa
    ? `${faixa.somadas} de ${faixa.operacionais} campanhas na soma · ${JANELA_DO_ESPELHO}, espelho do inventário`
    : carregando
      ? 'lendo a carteira'
      : 'carteira não lida';

  return (
    <PainelInstrumento
      titulo="Economia da carteira"
      lateral={<span className="text-micro text-muted-foreground">{legenda}</span>}
      className="mt-4"
      data-testid="faixa-economica"
    >
      <FaixaDeMetricas>
        <Metrica
          tamanho="hero"
          rotulo="custo medido"
          valor={faixa?.custo.valor ?? null}
          formato={moeda}
          verdade={faixa?.custo.verdade ?? 'desconhecido'}
          detalheDaVerdade={faixa?.custo.detalhe}
          lidoEm={faixa ? faixa.lidoEm : undefined}
          fonte={`Google Ads · ${JANELA_DO_ESPELHO}`}
          agora={agora}
          carregando={lendo}
        />
        <Metrica
          rotulo="cliques"
          valor={faixa?.cliques.valor ?? null}
          formato={INTEIRO}
          verdade={faixa?.cliques.verdade ?? 'desconhecido'}
          detalheDaVerdade={faixa?.cliques.detalhe}
          carregando={lendo}
        />
        <Metrica
          rotulo="custo por clique"
          valor={faixa?.cpc.valor ?? null}
          formato={moeda}
          verdade={faixa?.cpc.verdade ?? 'desconhecido'}
          detalheDaVerdade={faixa?.cpc.detalhe}
          carregando={lendo}
        />
        <Metrica
          rotulo="com entrega"
          valor={faixa?.entregando.valor ?? null}
          formato={INTEIRO}
          verdade={faixa?.entregando.verdade ?? 'desconhecido'}
          detalheDaVerdade={faixa?.entregando.detalhe}
          carregando={lendo}
        />
        <Metrica
          rotulo="receita"
          valor={null}
          formato={moeda}
          verdade="indisponivel"
          detalheDaVerdade={faixa?.receita.detalhe}
          carregando={lendo}
        />
        <Metrica
          rotulo="ROAS"
          valor={null}
          formato={RAZAO}
          verdade="indisponivel"
          detalheDaVerdade={faixa?.roas.detalhe}
          carregando={lendo}
        />
      </FaixaDeMetricas>
    </PainelInstrumento>
  );
};

export default FaixaEconomica;
