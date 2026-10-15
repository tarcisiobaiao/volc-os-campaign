import { describe, expect, it } from 'vitest';
import { carimboMaisRecente, interpretarCarimbo } from '../carimboDeAtualizacao';

describe('interpretarCarimbo', () => {
  it('lê ISO com fuso (formato do frontend e do joinads_last_update)', () => {
    expect(interpretarCarimbo('2026-02-19T22:29:20.083Z')?.toISOString()).toBe('2026-02-19T22:29:20.083Z');
  });

  it('lê o formato pt-BR gravado pelo n8n como horário de Brasília', () => {
    // Valor medido em produção em 15/10/2026 (google_ads_last_update).
    expect(interpretarCarimbo('15/10/2026, 06:00:17')?.toISOString()).toBe('2026-10-15T09:00:17.000Z');
  });

  it('aceita dia e mês sem zero à esquerda', () => {
    expect(interpretarCarimbo('5/3/2026, 6:00:17')?.toISOString()).toBe('2026-03-05T09:00:17.000Z');
  });

  it('devolve null para vazio e para formato desconhecido, nunca "agora"', () => {
    expect(interpretarCarimbo(null)).toBeNull();
    expect(interpretarCarimbo('')).toBeNull();
    expect(interpretarCarimbo('ontem de manhã')).toBeNull();
    expect(interpretarCarimbo('32/13/2026, 06:00:17')).toBeNull();
  });
});

describe('carimboMaisRecente', () => {
  it('compara formatos diferentes pelo instante, não pelo texto', () => {
    // Estado real de produção: GAM parado em fevereiro (ISO), Google Ads em outubro (pt-BR).
    expect(carimboMaisRecente(['2026-02-19T22:29:20.083Z', '15/10/2026, 06:00:17'])).toBe('15/10/2026, 06:00:17');
    expect(carimboMaisRecente(['2026-10-15T09:00:18Z', '15/10/2026, 06:00:17'])).toBe('2026-10-15T09:00:18Z');
  });

  it('ignora valores ilegíveis e devolve null quando nenhum é legível', () => {
    expect(carimboMaisRecente([null, 'lixo', '2026-02-19T22:29:20.083Z'])).toBe('2026-02-19T22:29:20.083Z');
    expect(carimboMaisRecente([null, 'lixo'])).toBeNull();
    expect(carimboMaisRecente([])).toBeNull();
  });
});
