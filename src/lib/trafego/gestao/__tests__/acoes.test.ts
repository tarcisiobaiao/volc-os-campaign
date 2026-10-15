/**
 * MONTAGEM DO PAYLOAD — um bloco por grupo, os 15 tipos.
 *
 * O payload que sai daqui é exatamente o de `docs/contracts/GADS-GESTAO-v1.md`
 * §5.2, e a recusa local espelha o `__post_init__` do motor
 * (`volc_ads/gestao/acoes.py`): micros múltiplos de 10.000, faixa de tROAS,
 * negativa com caractere proibido, IP fora de /24–/32, janela fora da grade…
 */
import { describe, expect, it } from 'vitest';

import {
  GRUPOS,
  ajusteParaModificador,
  alvoDaEstrategia,
  errosDe,
  lerIp,
  lerPlacement,
  lerTermo,
  montarAgenda,
  montarAlvo,
  montarEstrategia,
  montarIp,
  montarNegativas,
  montarOrcamento,
  montarPlacements,
  montarRecomendacao,
  montarStatus,
  percentualParaRazao,
  reaisParaMicros,
  type ContextoDaCampanha,
  type FormAgenda,
  type FormNegativas,
  type Montagem,
} from '../acoes';

const ctx: ContextoDaCampanha = {
  customerId: '5478096539',
  campaignId: '24278665189',
  estrategia: 'MAXIMIZE_CONVERSIONS',
  canal: 'SEARCH',
};

function acao(m: Montagem) {
  expect(errosDe(m)).toBeNull();
  return m.ok ? m.acao : null;
}

describe('os 9 grupos cobrem os 15 tipos do contrato', () => {
  it('nenhum tipo fica sem grupo', () => {
    const tipos = GRUPOS.flatMap((g) => g.tipos);
    expect(GRUPOS).toHaveLength(9);
    expect(new Set(tipos).size).toBe(15);
  });
});

describe('dinheiro em micros', () => {
  it('converte pt-BR sem ponto flutuante', () => {
    expect(reaisParaMicros('33,00')).toBe(33_000_000);
    expect(reaisParaMicros('R$ 1.234,56')).toBe(1_234_560_000);
    expect(reaisParaMicros('0,10')).toBe(100_000);
    expect(reaisParaMicros('33.5')).toBe(33_500_000);
  });
  it('recusa mais de 2 casas e texto', () => {
    expect(reaisParaMicros('1,234')).toBeNull();
    expect(reaisParaMicros('abc')).toBeNull();
    expect(reaisParaMicros('')).toBeNull();
  });
});

describe('1 · status', () => {
  it('campanha', () => {
    expect(acao(montarStatus({ nivel: 'campanha', ident: '24278665189', status: 'PAUSED' }))).toEqual({
      tipo: 'status',
      nivel: 'campanha',
      ident: '24278665189',
      status: 'PAUSED',
    });
  });
  it('anúncio é <grupo>~<anúncio>', () => {
    expect(acao(montarStatus({ nivel: 'anuncio', ident: '111~222', status: 'ENABLED' }))).toMatchObject({
      nivel: 'anuncio',
      ident: '111~222',
    });
    expect(errosDe(montarStatus({ nivel: 'anuncio', ident: '222', status: 'ENABLED' }))?.ident).toBeTruthy();
  });
  it('sem status escolhido, recusa', () => {
    expect(errosDe(montarStatus({ nivel: 'grupo', ident: '9', status: '' }))?.status).toBeTruthy();
  });
});

describe('2 · orçamento diário', () => {
  it('monta com micros e ciência do compartilhado', () => {
    expect(acao(montarOrcamento({ valor: '33', budgetId: '', compartilhadoCiente: false }, ctx))).toEqual({
      tipo: 'orcamento.diario',
      campaign_id: '24278665189',
      amount_micros: 33_000_000,
      origem: 'operador',
      compartilhado_ciente: false,
    });
    expect(
      acao(montarOrcamento({ valor: '33,10', budgetId: '15886629542', compartilhadoCiente: true }, ctx)),
    ).toMatchObject({ budget_id: '15886629542', amount_micros: 33_100_000, compartilhado_ciente: true });
  });
  it('zero e fração de centavo são recusados', () => {
    expect(errosDe(montarOrcamento({ valor: '0', budgetId: '', compartilhadoCiente: false }, ctx))?.valor).toBeTruthy();
    expect(errosDe(montarOrcamento({ valor: '1,005', budgetId: '', compartilhadoCiente: false }, ctx))?.valor).toBeTruthy();
  });
});

describe('3 · alvo de lance — o campo certo conforme a estratégia lida', () => {
  it('Maximizar conversões → tcpa em micros, com a estratégia lida junto', () => {
    expect(acao(montarAlvo({ valor: '25' }, ctx))).toEqual({
      tipo: 'lance.alvo',
      campaign_id: '24278665189',
      alvo: 'tcpa',
      valor: 25_000_000,
      origem: 'operador',
      estrategia: 'MAXIMIZE_CONVERSIONS',
    });
  });
  it('Maximizar valor → troas como razão (450% = 4.5)', () => {
    expect(acao(montarAlvo({ valor: '450' }, { ...ctx, estrategia: 'MAXIMIZE_CONVERSION_VALUE' }))).toMatchObject({
      alvo: 'troas',
      valor: 4.5,
    });
    expect(percentualParaRazao('350')).toBe(3.5);
  });
  it('Maximizar cliques → teto de CPC', () => {
    expect(acao(montarAlvo({ valor: '2,50' }, { ...ctx, estrategia: 'TARGET_SPEND' }))).toMatchObject({
      alvo: 'teto_cpc',
      valor: 2_500_000,
    });
  });
  it('CPA desejado padrão não aceita 0; Maximizar aceita (limpa)', () => {
    expect(errosDe(montarAlvo({ valor: '0' }, { ...ctx, estrategia: 'TARGET_CPA' }))?.valor).toBeTruthy();
    expect(acao(montarAlvo({ valor: '0' }, ctx))).toMatchObject({ valor: 0 });
  });
  it('CPC manual não tem alvo de campanha', () => {
    expect(alvoDaEstrategia('MANUAL_CPC')).toBeNull();
    expect(errosDe(montarAlvo({ valor: '1' }, { ...ctx, estrategia: 'MANUAL_CPC' }))?.valor).toMatch(/grupo e na palavra-chave/);
  });
});

describe('4 · troca de estratégia', () => {
  it('só o campo da estratégia nova', () => {
    expect(
      acao(montarEstrategia({ nova: 'MAXIMIZE_CONVERSION_VALUE', tcpa: '', troas: '400', tetoCpc: '', portfolio: '' }, ctx)),
    ).toEqual({ tipo: 'lance.estrategia', campaign_id: '24278665189', nova: 'MAXIMIZE_CONVERSION_VALUE', troas: 4 });
  });
  it('alvo em dinheiro na troca leva a origem operador', () => {
    expect(
      acao(montarEstrategia({ nova: 'TARGET_SPEND', tcpa: '', troas: '', tetoCpc: '2,50', portfolio: '' }, ctx)),
    ).toEqual({
      tipo: 'lance.estrategia', campaign_id: '24278665189', nova: 'TARGET_SPEND',
      teto_cpc_micros: 2_500_000, origem: 'operador',
    });
  });
  it('portfólio exige resource name', () => {
    const f = { nova: 'PORTFOLIO' as const, tcpa: '', troas: '', tetoCpc: '', portfolio: 'x' };
    expect(errosDe(montarEstrategia(f, ctx))?.portfolio).toBeTruthy();
    expect(acao(montarEstrategia({ ...f, portfolio: 'customers/1/biddingStrategies/2' }, ctx))).toMatchObject({
      portfolio: 'customers/1/biddingStrategies/2',
    });
  });
  it('a estratégia atual e a fora do canal são recusadas', () => {
    const f = { nova: 'MAXIMIZE_CONVERSIONS' as const, tcpa: '', troas: '', tetoCpc: '', portfolio: '' };
    expect(errosDe(montarEstrategia(f, ctx))?.nova).toMatch(/já está/);
    expect(errosDe(montarEstrategia({ ...f, nova: 'MANUAL_CPC' }, { ...ctx, canal: 'PERFORMANCE_MAX' }))?.nova).toBeTruthy();
  });
});

describe('5 · negativas e listas', () => {
  const base: FormNegativas = {
    subtipo: 'negativa.keyword',
    escopo: 'campanha',
    alvo: '24278665189',
    termos: 'grátis\n[curso gratuito]\n"pdf"',
    correspondencia: 'BROAD',
    tipoLista: 'NEGATIVE_KEYWORDS',
    nome: '',
    tipoPlacement: 'site',
    placements: '',
    sharedSetId: '',
    campanhas: '',
  };
  it('negativa.keyword entende "frase" e [exata]', () => {
    expect(acao(montarNegativas(base))).toEqual({
      tipo: 'negativa.keyword',
      escopo: 'campanha',
      alvo: '24278665189',
      termos: [
        { texto: 'grátis', correspondencia: 'BROAD' },
        { texto: 'curso gratuito', correspondencia: 'EXACT' },
        { texto: 'pdf', correspondencia: 'PHRASE' },
      ],
    });
  });
  it('caractere proibido e repetido são recusados', () => {
    expect(typeof lerTermo('promo!', 'PHRASE')).toBe('string');
    expect(errosDe(montarNegativas({ ...base, termos: 'a\nA' , correspondencia: 'PHRASE'}))?.termos).toMatch(/repetido/);
  });
  it('lista.criar com placements', () => {
    expect(
      acao(
        montarNegativas({
          ...base,
          subtipo: 'lista.criar',
          nome: '  Lixo  de display ',
          tipoLista: 'NEGATIVE_PLACEMENTS',
          placements: 'https://www.Exemplo.com.br/\napp.exemplo.com',
          campanhas: '24278665189, 1',
        }),
      ),
    ).toEqual({
      tipo: 'lista.criar',
      tipo_lista: 'NEGATIVE_PLACEMENTS',
      nome: 'Lixo de display',
      itens: [
        { tipo: 'site', valor: 'exemplo.com.br' },
        { tipo: 'site', valor: 'app.exemplo.com' },
      ],
      campanhas: ['24278665189', '1'],
    });
  });
  it('lista.adicionar e lista.anexar', () => {
    expect(acao(montarNegativas({ ...base, subtipo: 'lista.adicionar', sharedSetId: '77', termos: 'vagas' }))).toEqual({
      tipo: 'lista.adicionar',
      shared_set_id: '77',
      tipo_lista: 'NEGATIVE_KEYWORDS',
      itens: [{ texto: 'vagas', correspondencia: 'BROAD' }],
    });
    expect(acao(montarNegativas({ ...base, subtipo: 'lista.anexar', sharedSetId: '77', campanhas: '1 2' }))).toEqual({
      tipo: 'lista.anexar',
      shared_set_id: '77',
      campanhas: ['1', '2'],
    });
    expect(errosDe(montarNegativas({ ...base, subtipo: 'lista.anexar', sharedSetId: '77', campanhas: '' }))?.campanhas).toBeTruthy();
  });
});

describe('6 · exclusão de placement', () => {
  it('campanha leva campaign_id; conta não', () => {
    expect(acao(montarPlacements({ escopo: 'campanha', tipo: 'youtube_video', valores: 'dQw4w9WgXcQ' }, ctx))).toEqual({
      tipo: 'exclusao.placement',
      escopo: 'campanha',
      campaign_id: '24278665189',
      itens: [{ tipo: 'youtube_video', valor: 'dQw4w9WgXcQ' }],
    });
    expect(acao(montarPlacements({ escopo: 'conta', tipo: 'app', valores: '2-com.jogo.ruim' }, ctx))).toEqual({
      tipo: 'exclusao.placement',
      escopo: 'conta',
      itens: [{ tipo: 'app', valor: '2-com.jogo.ruim' }],
    });
  });
  it('formato do placement é conferido', () => {
    expect(typeof lerPlacement('youtube_canal', 'canal-qualquer')).toBe('string');
    expect(typeof lerPlacement('app', 'com.jogo')).toBe('string');
  });
});

describe('7 · exclusão de IP', () => {
  it('endereço e faixa /24–/32', () => {
    expect(acao(montarIp({ escopo: 'campanha', ips: '203.0.113.7\n198.51.100.0/24' }, ctx))).toEqual({
      tipo: 'exclusao.ip',
      escopo: 'campanha',
      campaign_id: '24278665189',
      ips: ['203.0.113.7', '198.51.100.0/24'],
    });
  });
  it('faixa larga, desalinhada, repetida e inválida são recusadas', () => {
    expect(typeof lerIp('10.0.0.0/16')).toBe('string');
    expect(typeof lerIp('10.0.0.7/24')).toBe('string');
    expect(typeof lerIp('300.1.1.1')).toBe('string');
    expect(errosDe(montarIp({ escopo: 'conta', ips: '1.1.1.1 1.1.1.1' }, ctx))?.ips).toMatch(/repetido/);
  });
});

describe('8 · agenda e ajustes', () => {
  const base: FormAgenda = {
    subtipo: 'programacao.anuncios',
    janelas: [{ dia: 'MONDAY', inicio: '08:00', fim: '12:00', ajuste: '+20' }],
    remover: '',
    substituir: false,
    dispositivo: 'MOBILE',
    ajuste: '',
    criterionId: '',
  };
  it('programação na grade de 15 min, ajuste em % vira multiplicador', () => {
    expect(acao(montarAgenda(base, ctx))).toEqual({
      tipo: 'programacao.anuncios',
      campaign_id: '24278665189',
      janelas: [{ dia: 'MONDAY', inicio: '08:00', fim: '12:00', modificador: 1.2 }],
    });
    expect(acao(montarAgenda({ ...base, janelas: [], substituir: true }, ctx))).toMatchObject({ substituir: true, janelas: [] });
  });
  it('fora da grade, sobreposta e vazia são recusadas', () => {
    expect(errosDe(montarAgenda({ ...base, janelas: [{ ...base.janelas[0], inicio: '08:10' }] }, ctx))?.janelas).toBeTruthy();
    expect(
      errosDe(
        montarAgenda(
          { ...base, janelas: [base.janelas[0], { dia: 'MONDAY', inicio: '11:00', fim: '13:00', ajuste: '' }] },
          ctx,
        ),
      )?.janelas,
    ).toMatch(/sobrepostas/);
    expect(errosDe(montarAgenda({ ...base, janelas: [] }, ctx))?.janelas).toBeTruthy();
  });
  it('dispositivo aceita −100% (0); horário não', () => {
    expect(ajusteParaModificador('-100')).toBe(0);
    expect(acao(montarAgenda({ ...base, subtipo: 'ajuste.dispositivo', dispositivo: 'TABLET', ajuste: '-100' }, ctx))).toEqual({
      tipo: 'ajuste.dispositivo',
      campaign_id: '24278665189',
      dispositivo: 'TABLET',
      modificador: 0,
    });
    expect(errosDe(montarAgenda({ ...base, subtipo: 'ajuste.horario', criterionId: '5', ajuste: '-100' }, ctx))?.ajuste).toBeTruthy();
    expect(acao(montarAgenda({ ...base, subtipo: 'ajuste.horario', criterionId: '5', ajuste: '-20' }, ctx))).toEqual({
      tipo: 'ajuste.horario',
      campaign_id: '24278665189',
      criterion_id: '5',
      modificador: 0.8,
    });
  });
});

describe('9 · recomendações', () => {
  it('aplicar e dispensar levam o resource name', () => {
    const rn = 'customers/5478096539/recommendations/abc~123';
    expect(acao(montarRecomendacao('recomendacao.aplicar', rn))).toEqual({ tipo: 'recomendacao.aplicar', recurso: rn });
    expect(acao(montarRecomendacao('recomendacao.dispensar', rn))).toEqual({ tipo: 'recomendacao.dispensar', recurso: rn });
    expect(errosDe(montarRecomendacao('recomendacao.aplicar', 'abc'))).toBeTruthy();
  });
});
