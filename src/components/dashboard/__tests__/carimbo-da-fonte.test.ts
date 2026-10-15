import { describe, expect, it } from 'vitest';

import { lerCarimboDaFonte } from '@/components/dashboard/carimboDaFonte';

const iso = (v: unknown) => {
  const r = lerCarimboDaFonte(v);
  return r.tipo === 'data' ? r.instante.toISOString() : r.tipo;
};

describe('carimbo das fontes (system_settings)', () => {
  it('lê dd/mm/aaaa, hh:mm:ss como dia/mês em Brasília (UTC−3)', () => {
    // O valor medido no self-hosted: 11 de março, não 3 de novembro.
    expect(iso('11/03/2026, 06:00:17')).toBe('2026-03-11T09:00:17.000Z');
  });

  it('dia maior que 12 não vira data inválida', () => {
    expect(iso('25/06/2026, 06:00:17')).toBe('2026-06-25T09:00:17.000Z');
  });

  it('aceita sem segundos, sem vírgula e com espaço não separável', () => {
    expect(iso('25/06/2026 06:00')).toBe('2026-06-25T09:00:00.000Z');
    expect(iso('25/06/2026,\u00a006:00:17')).toBe('2026-06-25T09:00:17.000Z');
  });

  it('aceita ISO 8601', () => {
    expect(iso('2026-03-11T09:00:17Z')).toBe('2026-03-11T09:00:17.000Z');
    expect(iso('2026-03-11T06:00:17-03:00')).toBe('2026-03-11T09:00:17.000Z');
  });

  it('vazio é vazio, não ilegível', () => {
    expect(iso(null)).toBe('vazio');
    expect(iso(undefined)).toBe('vazio');
    expect(iso('  ')).toBe('vazio');
  });

  it('formato desconhecido ou data impossível é ilegível, nunca "nunca lido"', () => {
    expect(iso('ontem às 6h')).toBe('ilegivel');
    expect(iso('31/02/2026, 06:00:17')).toBe('ilegivel');
    expect(iso('11/13/2026, 06:00:17')).toBe('ilegivel');
    expect(iso('11/03/2026, 25:00:00')).toBe('ilegivel');
    expect(iso('03/11/2026 6pm')).toBe('ilegivel');
  });
});
