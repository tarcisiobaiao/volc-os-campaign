/**
 * O briefing só vira pedido quando as respostas obrigatórias existem, e o modo
 * não implementado não passa pela validação.
 */
import { describe, expect, it } from 'vitest';

import {
  MODOS,
  RASCUNHO_VAZIO,
  chaveDeIdempotencia,
  fraseDeConsequencia,
  linhasDaRevisao,
  modoDisponivel,
  paraPedido,
  podeGerar,
  validarEtapa,
  type RascunhoDeImagem,
} from '@/components/criativos/briefing/contrato';
import { FORMATOS_DE_IMAGEM } from '@/types/criativos';

const cheio: RascunhoDeImagem = {
  projetoTitulo: 'Campanha de agosto',
  objetivo: 'Levar tráfego para a página do curso',
  mensagem: 'Inscrições abertas para a turma de agosto',
  audiencia: '',
  brandPackId: '',
  modo: 'full_llm',
  slots: ['1x1', '9x16'],
  destinosPretendidos: ['meta_feed'],
};

describe('validação do briefing', () => {
  it('rascunho vazio não pode gerar', () => {
    expect(podeGerar(RASCUNHO_VAZIO)).toBe(false);
  });

  it('rascunho completo pode gerar', () => {
    expect(podeGerar(cheio)).toBe(true);
  });

  it('sem formato escolhido, a etapa aponta o custo por peça', () => {
    const erros = validarEtapa('formatos', { ...cheio, slots: [] });
    expect(erros.slots).toContain('chamada ao motor');
  });

  it('apenas full_llm está disponível, e os outros trazem o motivo', () => {
    expect(modoDisponivel('full_llm')).toBe(true);
    const indisponiveis = MODOS.filter((m) => !m.disponivel);
    expect(indisponiveis).toHaveLength(5);
    expect(indisponiveis.every((m) => Boolean(m.motivo))).toBe(true);
  });

  it('modo não implementado é recusado na validação, não só desabilitado na tela', () => {
    const erros = validarEtapa('marca', { ...cheio, modo: 'prensa_hybrid' });
    expect(erros.modo).toBeTruthy();
    expect(podeGerar({ ...cheio, modo: 'prensa_hybrid' })).toBe(false);
  });
});

describe('contrato enviado ao servidor', () => {
  it('público em branco vira null, não string vazia', () => {
    expect(paraPedido(cheio).audiencia).toBeNull();
    expect(paraPedido({ ...cheio, audiencia: ' pais ' }).audiencia).toBe('pais');
  });

  it('brand pack não escolhido vira null', () => {
    expect(paraPedido(cheio).brandPackId).toBeNull();
  });

  it('a chave de idempotência é estável para o mesmo conteúdo e muda com ele', () => {
    expect(chaveDeIdempotencia(cheio)).toBe(chaveDeIdempotencia({ ...cheio }));
    // Ordem de slots não é conteúdo diferente.
    expect(chaveDeIdempotencia({ ...cheio, slots: ['9x16', '1x1'] })).toBe(
      chaveDeIdempotencia(cheio),
    );
    expect(chaveDeIdempotencia({ ...cheio, mensagem: 'outra coisa' })).not.toBe(
      chaveDeIdempotencia(cheio),
    );
  });
});

describe('revisão antes de gastar', () => {
  it('a consequência conta as peças e não estima valor', () => {
    const frase = fraseDeConsequencia(cheio);
    expect(frase).toContain('2 peças');
    expect(frase).toContain('2 chamadas reais');
    expect(frase).not.toMatch(/US\$/);
  });

  it('nenhum formato escolhido não promete geração', () => {
    expect(fraseDeConsequencia({ ...cheio, slots: [] })).toContain('não há o que gerar');
  });

  it('a revisão mostra nome de formato e nome de pack, nunca identificador cru', () => {
    const linhas = linhasDaRevisao(
      { ...cheio, brandPackId: 'uuid-ilegivel' },
      FORMATOS_DE_IMAGEM,
      () => 'Positivo v3',
    );
    const pecas = linhas.find((l) => l.rotulo === 'Peças');
    expect(pecas?.valor).toContain('Quadrado 1080x1080');
    expect(linhas.find((l) => l.rotulo === 'Brand pack')?.valor).toBe('Positivo v3');
  });
});
