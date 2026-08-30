/**
 * O LOTE: FALHA DE UM ITEM NÃO MASCARA OS DEMAIS — E `indeterminado` NÃO É `falhou`.
 *
 * A segunda regra é a cara. `falhou` AFIRMA que nada foi criado, e essa
 * afirmação autoriza reenviar. `indeterminado` diz que a chamada saiu e não se
 * sabe o desfecho — reenviar ali cria a segunda campanha real disputando o
 * mesmo leilão contra a primeira, e nenhuma tela mostra isso acontecendo.
 *
 * O vocabulário é o de `backend/app/trafego/lote.py` (`ESTADOS_DO_ITEM` e as
 * ações de `proxima_acao`). A tela consome; não recalcula.
 */
import { describe, expect, it } from 'vitest';

import type { AcaoDoItem, EstadoDoItemDoLote, ItemDoLote, Lote } from '@/types/diagnostico';
import { exigeAlguem, podeRetomar, resumoDoLote } from '../lote';

function item(
  estado: EstadoDoItemDoLote,
  proxima_acao: AcaoDoItem,
  over: Partial<ItemDoLote> = {},
): ItemDoLote {
  return {
    id: `i-${estado}-${Math.random().toString(36).slice(2, 7)}`,
    rotulo: `campanha ${estado}`,
    estado,
    proxima_acao,
    falha: estado === 'falhou' ? { mensagem: 'a conta recusou', codigo: 'POLICY' } : null,
    recibo: null,
    recibo_em_voo: false,
    encontradas_na_conta: null,
    ...over,
  };
}

function lote(itens: ItemDoLote[], over: Partial<Lote> = {}): Lote {
  return {
    id: 'lote-1',
    estado: 'executando',
    aprovado_em: '2026-08-26T12:00:00.000Z',
    aprovado_por: 'tarcisio',
    itens,
    cancelado_por: null,
    cancelado_em: null,
    motivo_do_cancelamento: null,
    ...over,
  };
}

describe('⚠️ os baldes que nunca se somam', () => {
  it('`indeterminado` tem balde próprio, separado de `falhou`', () => {
    const r = resumoDoLote(
      lote([
        item('criada_pausada', 'verificar'),
        item('falhou', 'decidir_retomada'),
        item('indeterminado', 'verificar'),
      ]),
    );
    expect(r.falharam).toBe(1);
    expect(r.indeterminados).toBe(1);
    expect(r.frase).toContain('não sabemos se criaram, e nenhuma será reenviada');
    expect(r.frase).toContain('1 falhou');
    // ⚠️ Os baldes somam o total, e nem um a mais. Antes disto eram 4 para 3.
    expect(r.criados + r.falharam + r.indeterminados + r.aguardando + r.emVoo + r.cancelados)
      .toBe(r.total);
  });

  /**
   * ⚠️ A regressão: "aguardando a vez" é o balde do que NUNCA FOI TENTADO, e
   * essa é exatamente a crença que autoriza reenviar. `indeterminado` diz o
   * oposto — a chamada saiu e a resposta não voltou. Um lote com um único item
   * indeterminado chegou a dizer as duas coisas na mesma frase.
   */
  it('`indeterminado` NUNCA é anunciado como "aguardando a vez"', () => {
    const r = resumoDoLote(lote([item('indeterminado', 'verificar')]));
    expect(r.total).toBe(1);
    expect(r.indeterminados).toBe(1);
    expect(r.aguardando).toBe(0);
    expect(r.frase).not.toContain('aguardando a vez');
  });

  /** `criando` é "enviado agora", que não é "na fila" nem "não sabemos". */
  it('`criando` sem recibo em voo tem balde próprio, e não é fila', () => {
    const r = resumoDoLote(lote([item('criando', 'verificar')]));
    expect(r.emVoo).toBe(1);
    expect(r.aguardando).toBe(0);
    expect(r.indeterminados).toBe(0);
    expect(r.frase).toContain('esperando resposta');
    expect(r.frase).not.toContain('aguardando a vez');
  });

  it('recibo em voo conta como indeterminado mesmo com o estado ainda em `criando`', () => {
    const r = resumoDoLote(lote([item('criando', 'verificar', { recibo_em_voo: true })]));
    expect(r.indeterminados).toBe(1);
  });

  it('duplicidade é o primeiro da frase: ela trava o lote inteiro', () => {
    const r = resumoDoLote(
      lote([
        item('criada_pausada', 'parar_duplicidade', { encontradas_na_conta: 2 }),
        item('falhou', 'decidir_retomada'),
      ]),
    );
    expect(r.duplicados).toBe(1);
    expect(r.frase.startsWith('1 com mais de uma campanha na conta')).toBe(true);
  });

  it('a frase começa pelo que exige alguém, e a boa notícia vai para o fim', () => {
    const r = resumoDoLote(
      lote([
        item('ativa', 'nada'),
        item('verificada', 'ativar_canario'),
        item('criada_pausada', 'verificar'),
        item('falhou', 'decidir_retomada'),
      ]),
    );
    expect(r.frase.startsWith('1 falhou')).toBe(true);
    expect(r.frase.endsWith('3 criadas, todas pausadas')).toBe(true);
  });

  it('`criados` conta todos os degraus pós-criação, porque todos existem na conta', () => {
    const r = resumoDoLote(
      lote([
        item('criada_pausada', 'verificar'),
        item('verificada', 'ativar_canario'),
        item('canario', 'ativar'),
        item('ativa', 'nada'),
      ]),
    );
    expect(r.criados).toBe(4);
  });

  it('lote vazio diz que está vazio, e não "0 criadas"', () => {
    expect(resumoDoLote(lote([])).frase).toBe('nenhum item neste lote');
  });
});

describe('⚠️ retomar é recusado enquanto houver o que não pode ser reenviado', () => {
  it('item indeterminado fecha a retomada, e a frase diz por quê', () => {
    const r = podeRetomar(
      lote([item('indeterminado', 'verificar'), item('falhou', 'decidir_retomada')]),
    );
    expect(r.pode).toBe(false);
    expect(r.motivo).toContain('Verificar na conta vem antes de retomar');
    expect(r.motivo).toContain('duplicada');
  });

  it('duplicidade também fecha', () => {
    const r = podeRetomar(
      lote([item('criada_pausada', 'parar_duplicidade', { encontradas_na_conta: 2 })]),
    );
    expect(r.pode).toBe(false);
  });

  it('sem aprovação humana, nada é executado — nem retomada', () => {
    const r = podeRetomar(lote([item('falhou', 'decidir_retomada')], { aprovado_em: null }));
    expect(r.pode).toBe(false);
    expect(r.motivo).toContain('aprovação humana');
  });

  it('lote cancelado exige decisão nova, não um botão', () => {
    const r = podeRetomar(
      lote([item('falhou', 'decidir_retomada')], {
        cancelado_em: '2026-08-26T18:00:00.000Z',
        cancelado_por: 'tarcisio',
        motivo_do_cancelamento: 'verba do mês esgotada',
      }),
    );
    expect(r.pode).toBe(false);
    expect(r.motivo).toContain('decisão nova');
  });

  it('com falha limpa, aprovação dada e nada em voo, a retomada abre', () => {
    const r = podeRetomar(lote([item('criada_pausada', 'nada'), item('falhou', 'decidir_retomada')]));
    expect(r).toEqual({ pode: true, motivo: null });
  });

  it('lote concluído não se retoma', () => {
    expect(podeRetomar(lote([item('ativa', 'nada')], { estado: 'concluido' })).pode).toBe(false);
  });
});

describe('quem exige alguém', () => {
  it('verificar, decidir retomada e parar duplicidade exigem uma pessoa', () => {
    expect(exigeAlguem(item('indeterminado', 'verificar'))).toBe(true);
    expect(exigeAlguem(item('falhou', 'decidir_retomada'))).toBe(true);
    expect(exigeAlguem(item('criada_pausada', 'parar_duplicidade'))).toBe(true);
  });

  it('ligar e criar são execução, não decisão pendente', () => {
    expect(exigeAlguem(item('canario', 'ativar'))).toBe(false);
    expect(exigeAlguem(item('aprovado', 'criar'))).toBe(false);
    expect(exigeAlguem(item('ativa', 'nada'))).toBe(false);
  });
});
