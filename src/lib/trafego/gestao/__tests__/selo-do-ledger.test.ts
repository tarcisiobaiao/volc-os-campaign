/**
 * O selo V3 de uma proposta do ledger não pode afirmar mais do que o ledger sabe.
 */
import { describe, expect, it } from 'vitest';

import { seloDoLedger } from '@/lib/trafego/gestao/fila';

const p = (estado: string, extra: { vencida?: boolean; proximo_passo?: string } = {}) => ({
  estado,
  vencida: extra.vencida ?? false,
  proximo_passo: extra.proximo_passo ?? 'nada',
});

describe('seloDoLedger', () => {
  it('traduz os estados que têm palavra no ciclo P09', () => {
    expect(seloDoLedger(p('aguardando_aprovacao'))).toBe('aguardando');
    expect(seloDoLedger(p('aprovada'))).toBe('aprovada');
    expect(seloDoLedger(p('recusada'))).toBe('recusada');
    expect(seloDoLedger(p('revertida'))).toBe('revertida');
    expect(seloDoLedger(p('expirada'))).toBe('vencida');
  });

  it('vencida ganha do estado: aprovação vencida não autoriza nada', () => {
    expect(seloDoLedger(p('aprovada', { vencida: true }))).toBe('vencida');
  });

  it('aplicada só vira "com recibo" depois da conferência', () => {
    expect(seloDoLedger(p('aplicada', { proximo_passo: 'acompanhar' }))).toBe('aplicada');
    expect(seloDoLedger(p('aplicada', { proximo_passo: 'verificar' }))).toBeNull();
  });

  it('estado sem palavra no ciclo fica com o texto do ledger', () => {
    expect(seloDoLedger(p('cancelada'))).toBeNull();
    expect(seloDoLedger(p('estado_novo_do_servidor'))).toBeNull();
  });
});
