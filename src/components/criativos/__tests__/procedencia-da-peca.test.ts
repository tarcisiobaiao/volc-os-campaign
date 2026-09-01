/**
 * A regra que a tela de criativos não pode quebrar:
 * **peça local ou de fixture nunca é apresentada como produção.**
 */
import { describe, expect, it } from 'vitest';

import { procedenciaDaPeca } from '@/components/criativos/laboratorio/procedencia';
import {
  custoLegivel,
  dimensoes,
  mimeLegivel,
} from '@/components/criativos/comum/formato';

describe('procedência', () => {
  it('peça local é rotulada como ensaio, e não é publicável', () => {
    const p = procedenciaDaPeca({ natureza: 'local', publicavel: false });
    expect(p.palavra).toContain('ensaio');
    expect(p.publicavel).toBe(false);
  });

  it('peça de fixture também é ensaio, com frase própria', () => {
    const p = procedenciaDaPeca({ natureza: 'fixture', publicavel: false });
    expect(p.natureza).toBe('fixture');
    expect(p.descricao).not.toBe(
      procedenciaDaPeca({ natureza: 'local', publicavel: false }).descricao,
    );
  });

  it('procedência ausente NÃO vira produção', () => {
    // Assumir produção publicaria um ensaio.
    const p = procedenciaDaPeca({});
    expect(p.natureza).toBe('nao_declarada');
    expect(p.publicavel).toBe(false);
  });

  it('procedência ausente também não vira ensaio', () => {
    // Assumir ensaio esconderia uma peça boa. O rótulo diz o que houve.
    expect(procedenciaDaPeca(undefined).palavra).toContain('não declarada');
  });

  it('valor desconhecido de natureza cai em não declarada, não em produção', () => {
    expect(procedenciaDaPeca({ natureza: 'PRODUÇÃO_TYPO' }).natureza).toBe(
      'nao_declarada',
    );
  });

  it('publicável só quando o servidor declarou, e não derivado da natureza', () => {
    // Recalcular no navegador criaria uma segunda definição de "publicável", e
    // ela discordaria do servidor exatamente na direção perigosa.
    expect(procedenciaDaPeca({ natureza: 'producao' }).publicavel).toBe(false);
    expect(
      procedenciaDaPeca({ natureza: 'producao', publicavel: true }).publicavel,
    ).toBe(true);
  });
});


describe('a formatação de ausência já tinha dono, e ele continua sendo o dono', () => {
  it('dimensão não medida vira frase, não traço', () => {
    // ⚠️ Eu tinha escrito uma segunda versão disto. Duas funções para a mesma
    // pergunta divergem no dia em que só uma é corrigida, e a que a tela usa
    // pode ser a errada.
    expect(dimensoes(null, null)).toBe('não medido');
    expect(dimensoes(600, null)).toBe('não medido');
  });

  it('dimensão medida aparece inteira', () => {
    expect(dimensoes(600, 314)).toBe('600 x 314 px');
  });

  it('custo não apurado não vira grátis', () => {
    // Um relatório de COGS que soma zeros inventados fecha bonito e erra.
    expect(custoLegivel(null)).toBe('custo não apurado');
    expect(custoLegivel(0)).toBe('US$ 0.0000');
  });

  it('MIME ausente é declarado, não vazio', () => {
    expect(mimeLegivel(null)).toBe('não informado');
    expect(mimeLegivel('image/png')).toBe('image/png');
  });
});
