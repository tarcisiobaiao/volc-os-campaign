/**
 * A matriz do recibo: 0/4, 1/4, 3/4, ids sem leitura, divergência e 4/4.
 *
 * ⚠️ O defeito que estes testes fixam tinha UMA linha:
 * `steps.every((p) => p.state === 'CREATED')`. `steps` é a lista dos passos que
 * JÁ APARECERAM no livro — não a dos passos APROVADOS. Uma Campaign criada de
 * quatro objetos satisfazia o `every()` sozinha, e a bancada escrevia
 * "Criada pausada · 1 de 1".
 *
 * O módulo é puro de propósito: a matriz inteira é provável sem DOM, e cada
 * caso aqui falha contra a expressão antiga.
 */
import { describe, expect, it } from 'vitest';

import type { PassoDoReciboMeta, ReciboCriacaoMeta } from '@/lib/pautadorApi';

import {
  TOM_DA_OPERACAO,
  fraseDaOperacao,
  lerOperacao,
} from '../estadoDaOperacao';

const MANIFESTO = ['campaign', 'adset', 'creative:variation-001', 'ad:variation-001'];

function recibo(
  steps: PassoDoReciboMeta[],
  extras: Partial<ReciboCriacaoMeta> = {},
): ReciboCriacaoMeta {
  return {
    approval_id: 'approval-0001',
    plan_sha256: 'b'.repeat(64),
    capability: 'META_CREATE_PAUSED',
    state: 'APPROVED',
    expires_at: '2026-09-05T12:15:00+00:00',
    steps_expected: MANIFESTO,
    operations_expected: 4,
    steps,
    ...extras,
  };
}

const criado = (name: string): PassoDoReciboMeta => ({
  name, state: 'CREATED', has_external_id: true, error_code: null,
});

const conferido = (name: string, status = 'PAUSED'): PassoDoReciboMeta => ({
  ...criado(name),
  readback_at: '2026-09-07T12:00:00+00:00',
  readback_evidence: {
    matched: true, tipo: name.split(':')[0], status, effective_status: status,
  },
});

const divergente = (name: string): PassoDoReciboMeta => ({
  ...criado(name),
  readback_error: 'META_READBACK_DIVERGENT',
  readback_at: '2026-09-07T12:00:00+00:00',
  readback_evidence: {
    matched: false, tipo: name.split(':')[0], status: 'ACTIVE', effective_status: 'ACTIVE',
  },
});

describe('o estado da operação sai do manifesto aprovado, nunca dos passos que existem', () => {
  it('1 de 4 é PARCIAL — e esta é a reprodução exata do achado', () => {
    const leitura = lerOperacao(recibo([conferido('campaign')]));
    expect(leitura.estado.tipo).toBe('PARCIAL');
    // ⚠️ O denominador é 4, e não 1. Era o `steps.length` que produzia "1 de 1".
    expect(leitura.esperados).toBe(4);
    expect(leitura.confirmados).toBe(1);
    expect(leitura.naoDespachados).toBe(3);
    expect(fraseDaOperacao(leitura)).not.toMatch(/^Criada pausada/);
  });

  it('0 de 4 é aprovação sem despacho, não campanha criada', () => {
    const leitura = lerOperacao(recibo([]));
    expect(leitura.estado.tipo).toBe('NAO_DESPACHADA');
    expect(leitura.esperados).toBe(4);
    expect(leitura.naoDespachados).toBe(4);
  });

  it('3 de 4 continua parcial', () => {
    const leitura = lerOperacao(recibo([
      conferido('campaign'), conferido('adset'), conferido('creative:variation-001'),
    ]));
    expect(leitura.estado.tipo).toBe('PARCIAL');
    expect(leitura.confirmados).toBe(3);
    expect(leitura.naoDespachados).toBe(1);
  });

  it('quatro ids gravados SEM leitura não é sucesso, e não é verde', () => {
    const leitura = lerOperacao(recibo(MANIFESTO.map(criado)));
    expect(leitura.estado.tipo).toBe('CRIADA_SEM_LEITURA');
    // Existir e estar conferido são fatos diferentes, e a tela mostra os dois.
    expect(leitura.comIdGravado).toBe(4);
    expect(leitura.confirmados).toBe(0);
    expect(TOM_DA_OPERACAO[leitura.estado.tipo]).not.toBe('verificado');
  });

  it('uma divergência domina três confirmações', () => {
    const leitura = lerOperacao(recibo([
      conferido('campaign'), conferido('adset'), conferido('creative:variation-001'),
      divergente('ad:variation-001'),
    ]));
    expect(leitura.estado.tipo).toBe('DIVERGENTE');
    expect(leitura.confirmados).toBe(3);
    expect(leitura.divergentes).toBe(1);
  });

  it('4 de 4 conferidos é o ÚNICO estado verde', () => {
    const leitura = lerOperacao(recibo(MANIFESTO.map((nome) => conferido(nome))));
    expect(leitura.estado.tipo).toBe('CONFIRMADA');
    expect(leitura.confirmados).toBe(4);
    expect(TOM_DA_OPERACAO[leitura.estado.tipo]).toBe('verificado');
    expect(fraseDaOperacao(leitura)).toBe('Criada pausada e conferida');
  });

  it('ambiguidade vem antes de qualquer contagem boa', () => {
    const leitura = lerOperacao(recibo([
      conferido('campaign'),
      { name: 'adset', state: 'AMBIGUOUS', has_external_id: false, error_code: null },
    ]));
    expect(leitura.estado.tipo).toBe('AMBIGUA');
    expect(leitura.ambiguos).toBe(1);
  });

  it('um passo em voo é operação em curso, nunca completa', () => {
    const leitura = lerOperacao(recibo([
      { name: 'campaign', state: 'IN_FLIGHT', has_external_id: false, error_code: null },
    ]));
    expect(leitura.estado.tipo).toBe('EM_CURSO');
  });
});

describe('ausência de manifesto é DESCONHECIDO, nunca sucesso', () => {
  it('sem denominador declarado a tela não conclui nada', () => {
    const leitura = lerOperacao(recibo([conferido('campaign')], {
      steps_expected: undefined, operations_expected: undefined,
    }));
    expect(leitura.estado.tipo).toBe('DESCONHECIDO');
    expect(leitura.esperados).toBeNull();
  });

  it('recibo que se contradiz sobre a contagem também é desconhecido', () => {
    const leitura = lerOperacao(recibo(MANIFESTO.map((n) => conferido(n)), {
      operations_expected: 7,
    }));
    expect(leitura.estado.tipo).toBe('DESCONHECIDO');
  });

  it('passo fora do manifesto APARECE em vez de ser escondido', () => {
    const leitura = lerOperacao(recibo([
      ...MANIFESTO.map((n) => conferido(n)), conferido('adset:intruso'),
    ]));
    expect(leitura.estado.tipo).toBe('DESCONHECIDO');
    expect(leitura.passos.some((p) => p.foraDoManifesto)).toBe(true);
  });

  it('CREATED sem id é o livro se contradizendo, e não vira sucesso', () => {
    const leitura = lerOperacao(recibo([
      { name: 'campaign', state: 'CREATED', has_external_id: false, error_code: null },
    ]));
    expect(leitura.estado.tipo).toBe('DESCONHECIDO');
  });

  it('sem recibo nenhum a resposta é ausência, não zero', () => {
    const leitura = lerOperacao(null);
    expect(leitura.estado.tipo).toBe('SEM_RECIBO');
    expect(leitura.esperados).toBeNull();
  });
});

describe('confirmação exige as duas metades', () => {
  it('carimbo sem "matched" não confirma', () => {
    const leitura = lerOperacao(recibo([{
      ...criado('campaign'), readback_at: '2026-09-07T12:00:00+00:00',
    }]));
    expect(leitura.passos[0].estado).toBe('CRIADO_SEM_LEITURA');
  });

  it('"matched" sem carimbo também não confirma', () => {
    const leitura = lerOperacao(recibo([{
      ...criado('campaign'),
      readback_evidence: {
        matched: true, tipo: 'campaign', status: 'PAUSED', effective_status: 'PAUSED',
      },
    }]));
    expect(leitura.passos[0].estado).toBe('CRIADO_SEM_LEITURA');
  });

  it('divergência registrada vence uma evidência que diz ter conferido', () => {
    const leitura = lerOperacao(recibo([{
      ...conferido('campaign'), readback_error: 'META_READBACK_DIVERGENT',
    }]));
    expect(leitura.passos[0].estado).toBe('DIVERGENTE');
  });
});
