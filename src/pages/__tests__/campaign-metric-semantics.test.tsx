/**
 * Semântica das métricas de arbitragem (T09 / F16).
 *
 * Três medidas com três unidades e três nomes; ausência que continua ausência;
 * e a garantia de que a fórmula legada do Google não mudou de valor.
 */
import { describe, expect, it } from 'vitest';

import {
  calculateROAS,
  getROASColorCategory,
  lucroBruto,
  retornoExcedentePct,
  roasRatio,
  roiLiquidoPct,
} from '@/utils/roasCalculations';

describe('vocabulário de retorno', () => {
  it('o caso conhecido: receita 200 / gasto 100 => razão 2 e excedente 100%', () => {
    expect(roasRatio(200, 100)).toBe(2);
    expect(retornoExcedentePct(200, 100)).toBe(100);
    expect(lucroBruto(200, 100)).toBe(100);
  });

  it('nenhuma delas devolve 100 como se fosse um alvo de plataforma', () => {
    // `target_roas` do Google Ads é uma RAZÃO. Enviar o excedente (100) no
    // lugar da razão (2) perseguiria um alvo cinquenta vezes maior.
    expect(roasRatio(200, 100)).not.toBe(retornoExcedentePct(200, 100));
  });

  it('gasto zero, ausente ou nulo é indisponível, nunca zero nem 100 simbólico', () => {
    for (const gasto of [0, null, undefined, NaN]) {
      expect(roasRatio(200, gasto as number)).toBeNull();
      expect(retornoExcedentePct(200, gasto as number)).toBeNull();
    }
    expect(roasRatio(null, 100)).toBeNull();
    expect(lucroBruto(null, 100)).toBeNull();
  });

  it('receita sem gasto não vira lucro infinito nem 100%', () => {
    expect(roasRatio(500, 0)).toBeNull();
    // A função legada devolvia um 100 simbólico exatamente aqui.
    expect(calculateROAS(500, 0)).toBe(100);
  });

  it('gasto sem receita é prejuízo medido, não ausência', () => {
    expect(roasRatio(0, 100)).toBe(0);
    expect(retornoExcedentePct(0, 100)).toBe(-100);
    expect(lucroBruto(0, 100)).toBe(-100);
  });

  it('ROI líquido exige a regra de deduções resolvida', () => {
    expect(roiLiquidoPct(200, 100, null)).toBeNull();
    // 200 de receita, 100 de mídia, 20 de impostos/taxas => 120 investidos
    expect(roiLiquidoPct(200, 100, 20)).toBeCloseTo(((200 - 120) / 120) * 100, 10);
    expect(roiLiquidoPct(200, 0, 0)).toBeNull();
  });

  it('denominador zero nunca produz Infinity nem NaN', () => {
    for (const f of [roasRatio, retornoExcedentePct]) {
      const v = f(1, 0);
      expect(v === null || Number.isFinite(v)).toBe(true);
    }
  });
});

describe('a fórmula legada do Google não mudou de valor', () => {
  // Se qualquer um destes mudar, cinco painéis do Google mudam de número e de
  // cor junto, e relatórios históricos passam a renderizar outra coisa.
  const casos: Array<[number, number, number]> = [
    [167, 100, 67],
    [200, 100, 100],
    [100, 100, 0],
    [50, 100, -50],
    [500, 0, 100],
    [0, 0, 0],
  ];
  it.each(casos)('calculateROAS(%i, %i) === %i', (receita, gasto, esperado) => {
    expect(calculateROAS(receita, gasto)).toBeCloseTo(esperado, 10);
  });

  it('as faixas de cor continuam calibradas na escala do excedente', () => {
    expect(getROASColorCategory(80)).toBe('green');
    expect(getROASColorCategory(40)).toBe('yellow');
    expect(getROASColorCategory(0)).toBe('orange');
    expect(getROASColorCategory(-1)).toBe('red');
  });

  it('a razão jamais deve ser passada às faixas do excedente', () => {
    // razão 2 (= 100% de excedente, "verde") cairia em "laranja" se alguém
    // trocasse as escalas sem trocar as faixas.
    expect(getROASColorCategory(roasRatio(200, 100) as number)).toBe('orange');
    expect(getROASColorCategory(retornoExcedentePct(200, 100) as number)).toBe('green');
  });
});
