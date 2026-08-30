/**
 * O RECIBO, LIDO DO FORMATO REAL.
 *
 * A fixture abaixo é a forma exata de `volc_ads/dados/recibos/*.json` — os
 * cinco existentes foram lidos, e todos são `ACEITO` com `falha: null`. Isso
 * significa que o ramo de FALHA não tem amostra observada, e é por isso que a
 * leitura é tolerante: assumir a forma de um erro que nunca se viu produz uma
 * tela que quebra no primeiro erro real.
 */
import { describe, expect, it } from 'vitest';

import type { Aprovacao } from '@/types/diagnostico';
import {
  conferirImpressao,
  contagemConfere,
  lerRecibo,
  momentoDoCarimbo,
  porTipo,
} from '../recibo';

/** Recorte fiel de `20260819_123825_8017851692_9d86b302.json`. */
const RECIBO_REAL = {
  estado: 'ACEITO',
  carimbo: '20260819_123825',
  customer_id: '8017851692',
  login_customer_id: '6016739364',
  nome_campanha: 'FORGE BR 20260819_123824 Maquininha de Cartão',
  n_operacoes: 4,
  impressao: '9d86b30209adf16f240e6c8c5bcdb02b6834f91c82c78f1d48febed983355e4b',
  motivo: 'lançamento de "Maquininha de Cartão"',
  criados: [
    { posicao: 0, tipo: 'campaign_budget_result', resource_name: 'customers/8017851692/campaignBudgets/15805293297' },
    { posicao: 1, tipo: 'campaign_result', resource_name: 'customers/8017851692/campaigns/24155028398' },
    { posicao: 2, tipo: 'campaign_criterion_result', resource_name: 'customers/8017851692/campaignCriteria/24155028398~2076' },
    { posicao: 3, tipo: 'campaign_criterion_result', resource_name: 'customers/8017851692/campaignCriteria/24155028398~1014' },
  ],
  request_id: '',
  falha: null,
  explicacao:
    'a API confirmou a criação do grafo inteiro. A campanha está PAUSED: não entra em leilão e não gasta.',
  nada_foi_criado: false,
};

describe('leitura do formato real', () => {
  it('lê os campos do recibo de 19/08 sem perder nada', () => {
    const r = lerRecibo(RECIBO_REAL)!;
    expect(r.estado).toBe('ACEITO');
    expect(r.nome_campanha).toContain('Maquininha');
    expect(r.criados).toHaveLength(4);
    expect(r.nada_foi_criado).toBe(false);
    expect(r.falha).toBeNull();
  });

  it('`request_id` vazio continua vazio — a tela é que diz "não devolvido"', () => {
    expect(lerRecibo(RECIBO_REAL)!.request_id).toBe('');
  });

  it('sem carimbo ou sem impressão não é recibo: não diz quando nem o quê', () => {
    expect(lerRecibo({ ...RECIBO_REAL, carimbo: '' })).toBeNull();
    expect(lerRecibo({ ...RECIBO_REAL, impressao: '' })).toBeNull();
    expect(lerRecibo(null)).toBeNull();
    expect(lerRecibo('recibo')).toBeNull();
  });
});

describe('o ramo de falha, que não tem amostra observada', () => {
  it('falha em objeto é lida campo a campo', () => {
    const r = lerRecibo({
      ...RECIBO_REAL,
      estado: 'RECUSADO',
      nada_foi_criado: true,
      criados: [],
      falha: { mensagem: 'INVALID_ARGUMENT', codigo: 'FIELD_ERROR', posicao: 7, campo: 'final_urls' },
    })!;
    expect(r.falha).toEqual({
      mensagem: 'INVALID_ARGUMENT',
      codigo: 'FIELD_ERROR',
      posicao: 7,
      campo: 'final_urls',
    });
  });

  it('⚠️ falha que chega como TEXTO puro não é descartada — ela é a evidência', () => {
    const r = lerRecibo({ ...RECIBO_REAL, falha: 'a conta recusou o pedido' })!;
    expect(r.falha?.mensagem).toBe('a conta recusou o pedido');
  });

  it('falha com nomes em inglês também é lida', () => {
    const r = lerRecibo({ ...RECIBO_REAL, falha: { message: 'boom', code: 'E1' } })!;
    expect(r.falha?.mensagem).toBe('boom');
    expect(r.falha?.codigo).toBe('E1');
  });
});

describe('o carimbo', () => {
  it('vira leitura humana e declara que não tem fuso', () => {
    expect(momentoDoCarimbo('20260819_123825')).toEqual({
      texto: '19/08/2026 12:38:25',
      semFuso: true,
    });
  });

  it('carimbo fora do formato não vira data inventada', () => {
    expect(momentoDoCarimbo('ontem')).toBeNull();
  });
});

describe('o que o recibo prova', () => {
  it('agrupa as operações por tipo, da mais numerosa para a menos', () => {
    expect(porTipo(lerRecibo(RECIBO_REAL)!)).toEqual([
      { tipo: 'campaign_criterion_result', n: 2 },
      { tipo: 'campaign_budget_result', n: 1 },
      { tipo: 'campaign_result', n: 1 },
    ]);
  });

  it('a contradição entre o número declarado e o entregue é detectável', () => {
    expect(contagemConfere(lerRecibo(RECIBO_REAL)!)).toBe('confere');
    expect(contagemConfere(lerRecibo({ ...RECIBO_REAL, n_operacoes: 34 })!)).toBe('difere');
  });

  /**
   * A regressão que este teste guarda: enquanto `n_operacoes` ausente virava
   * `0`, um recibo saudável com operações confirmadas era acusado de
   * contradição material — a tela gritava sobre uma divergência inventada pelo
   * próprio leitor. Ausência não é divergência.
   */
  it('recibo sem `n_operacoes` não é acusado de contradição', () => {
    const { n_operacoes, ...semContagem } = RECIBO_REAL as Record<string, unknown>;
    const r = lerRecibo(semContagem)!;
    expect(r).not.toBeNull();
    expect(r.n_operacoes).toBeNull();
    expect(contagemConfere(r)).toBe('nao_da_para_conferir');
  });
});

describe('a impressão amarra aprovação e recibo', () => {
  const aprovacao = (impressao: string | null): Aprovacao => ({
    estado: 'aprovada',
    por: 'tarcisio',
    em: '2026-08-19T15:00:00.000Z',
    impressao,
    motivo: 'lançamento aprovado',
    vale_ate: null,
  });

  it('mesma impressão: o que saiu é o que foi autorizado', () => {
    expect(conferirImpressao(aprovacao(RECIBO_REAL.impressao), lerRecibo(RECIBO_REAL))).toBe(
      'confere',
    );
  });

  it('impressão diferente é fato material, não detalhe', () => {
    expect(conferirImpressao(aprovacao('outra'), lerRecibo(RECIBO_REAL))).toBe('difere');
  });

  it('⚠️ sem impressão de um dos lados, a resposta é "não dá para conferir" — nunca "confere"', () => {
    expect(conferirImpressao(aprovacao(null), lerRecibo(RECIBO_REAL))).toBe(
      'nao_da_para_conferir',
    );
    expect(conferirImpressao(null, lerRecibo(RECIBO_REAL))).toBe('nao_da_para_conferir');
  });
});
