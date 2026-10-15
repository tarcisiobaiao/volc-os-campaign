/**
 * A origem do valor aparece no diff que o aprovador lê (W5): quem disse o
 * número, por quê, e a evidência — e proposta antiga sem origem não inventa uma.
 */
import { describe, expect, it } from 'vitest';

import { linhasDoDiff, valorLegivel } from '../diff';

const ORIGEM = {
  origem: 'operador',
  evidencia: 'operador:u2/OPERATOR@2026-10-15T12:00:00+00:00',
  justificativa: 'verba limita a entrega no fim do dia',
};

describe('origem do valor no diff', () => {
  it('mostra quem, por quê e a evidência', () => {
    expect(valorLegivel('origem_valor', ORIGEM, 'BRL')).toBe(
      'operador — verba limita a entrega no fim do dia (operador:u2/OPERATOR@2026-10-15T12:00:00+00:00)',
    );
  });
  it('vira uma linha "origem do valor" ao lado da verba', () => {
    const linhas = linhasDoDiff({
      valor_atual: { verba_diaria_micros: 30_000_000 },
      valor_proposto: { verba_diaria_micros: 36_000_000, budget_id: 1, origem_valor: ORIGEM },
      moeda: 'BRL',
    });
    const origem = linhas.find((l) => l.rotulo === 'origem do valor');
    expect(origem?.antes).toBeNull();
    expect(origem?.depois).toMatch(/^operador — verba limita/);
  });
  it('medição mostra a referência à leitura guardada', () => {
    const medido = { origem: 'medido_na_conta', evidencia: 'medicao:trafego_proposta.valor_atual/p1#verba_diaria_micros@x sha256=ab' };
    expect(valorLegivel('origem_valor', medido, 'BRL')).toBe(`medido_na_conta (${medido.evidencia})`);
  });
  it('proposta antiga sem origem não ganha linha de origem', () => {
    const linhas = linhasDoDiff({
      valor_atual: { verba_diaria_micros: 30_000_000 },
      valor_proposto: { verba_diaria_micros: 36_000_000 },
      moeda: 'BRL',
    });
    expect(linhas.some((l) => l.rotulo === 'origem do valor')).toBe(false);
  });
});
