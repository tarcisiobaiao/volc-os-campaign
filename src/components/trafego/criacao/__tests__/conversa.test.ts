/**
 * A CONVERSA DE CRIAÇÃO: capacidade vem do manifesto, e trava não lida não é
 * trava aberta.
 *
 * As três leis provadas aqui:
 *
 *  1. `manifesto: null` não é "canal com formulário vazio" — a conversa inteira
 *     não existe, e a frase diz por quê;
 *  2. `travaAberta: null` (não apurado) bloqueia a criação. A leitura otimista
 *     aqui custaria uma campanha criada por engano;
 *  3. criar e ligar são etapas separadas, e a ativação depende da criação.
 */
import { describe, expect, it } from 'vitest';

import type { EtapaDaCriacao } from '@/types/diagnostico';
import { ETAPAS_DA_CRIACAO } from '@/types/diagnostico';
import type { ManifestoDeCanal } from '@/types/trafego';

import { etapaAtual, montarConversa, progressoDaConversa } from '../conversa';

const manifestoSearch: ManifestoDeCanal = {
  plataforma: 'GOOGLE_ADS',
  canal: 'SEARCH',
  rotulo: 'Search',
  hierarquia: ['campanha', 'grupo', 'anuncio'],
  paineis: ['resumo', 'estrutura'],
  campos_do_pedido: ['objetivo', 'conta', 'url_final', 'conversion_action', 'geo', 'verba'],
  capacidades: ['ler', 'propor'],
  provas_obrigatorias: ['validate_only'],
  indisponibilidades: [],
  sabe_provar: true,
  sabe_criar: true,
};

const passo = (passos: ReturnType<typeof montarConversa>, etapa: EtapaDaCriacao) =>
  passos.find((p) => p.etapa === etapa)!;

const base = {
  manifesto: manifestoSearch,
  respostas: {} as Partial<Record<EtapaDaCriacao, string>>,
  travaAberta: null as boolean | null,
  podeAprovar: true,
};

describe('a conversa é derivada do manifesto', () => {
  it('⚠️ `manifesto: null` bloqueia TUDO, com a frase que ensina', () => {
    const passos = montarConversa({ ...base, manifesto: null });
    expect(passos).toHaveLength(ETAPAS_DA_CRIACAO.length);
    expect(passos.every((p) => p.estado === 'bloqueada')).toBe(true);
    expect(passos[0].dependencia?.destrava).toBe('manifesto');
    expect(passos[0].dependencia?.dependencia).toContain('não declara construtor');
  });

  it('`sabe_criar: false` usa a recusa do próprio manifesto, e não uma frase enlatada', () => {
    const passos = montarConversa({
      ...base,
      manifesto: {
        ...manifestoSearch,
        sabe_provar: false,
        sabe_criar: false,
        indisponibilidades: ['Performance Max não tem construtor aprovado (ADR-11).'],
      },
    });
    expect(passos[0].dependencia?.dependencia).toBe(
      'Performance Max não tem construtor aprovado (ADR-11).',
    );
  });

  it('canal cujo pedido não tem conversão não ganha a pergunta de conversão', () => {
    const passos = montarConversa({
      ...base,
      manifesto: { ...manifestoSearch, campos_do_pedido: ['objetivo', 'conta', 'verba'] },
    });
    expect(passo(passos, 'conversao').estado).toBe('nao_se_aplica');
    // E ela NÃO some da lista: sumir lê-se como etapa cumprida.
    expect(passos).toHaveLength(ETAPAS_DA_CRIACAO.length);
    expect(progressoDaConversa(passos).aplicaveis).toBe(ETAPAS_DA_CRIACAO.length - 1);
  });
});

describe('a trava de escrita', () => {
  const respondidoAte = (etapas: EtapaDaCriacao[]) =>
    Object.fromEntries(etapas.map((e) => [e, `resposta de ${e}`])) as Partial<
      Record<EtapaDaCriacao, string>
    >;

  const ateAProva = respondidoAte([
    'objetivo',
    'conta',
    'destino',
    'conversao',
    'targeting',
    'orcamento',
    'criativos',
    'revisao',
    'validacao_local',
    'prova',
    'aprovacao',
  ]);

  it('⚠️ trava NÃO LIDA bloqueia a criação — não apurado nunca vira aberta', () => {
    const passos = montarConversa({ ...base, respostas: ateAProva, travaAberta: null });
    const criacao = passo(passos, 'criacao');
    expect(criacao.estado).toBe('bloqueada');
    expect(criacao.dependencia?.dependencia).toContain('não foi lido');
  });

  it('trava fechada bloqueia, e diz que ela é aberta fora desta tela', () => {
    const passos = montarConversa({ ...base, respostas: ateAProva, travaAberta: false });
    expect(passo(passos, 'criacao').dependencia?.dependencia).toContain('fora desta tela');
  });

  it('trava aberta com prova feita libera a etapa de criação', () => {
    const passos = montarConversa({ ...base, respostas: ateAProva, travaAberta: true });
    expect(passo(passos, 'criacao').estado).toBe('atual');
  });

  it('sem prova, a criação fica bloqueada mesmo com a trava aberta', () => {
    const passos = montarConversa({ ...base, respostas: {}, travaAberta: true });
    expect(passo(passos, 'criacao').dependencia?.destrava).toBe('prova');
  });
});

describe('criar e ligar são duas decisões', () => {
  it('a ativação depende de haver campanha criada', () => {
    const passos = montarConversa({ ...base, travaAberta: true });
    const ativacao = passo(passos, 'ativacao');
    expect(ativacao.estado).toBe('bloqueada');
    expect(ativacao.dependencia?.dependencia).toContain('não há campanha criada');
  });

  it('a pergunta da ativação diz, em letras, que é ela que faz gastar', () => {
    const passos = montarConversa({ ...base, travaAberta: true });
    expect(passo(passos, 'ativacao').pergunta).toContain('faz a campanha gastar');
  });
});

describe('quem aprova', () => {
  it('sem papel, a aprovação é bloqueada e o motivo é o papel — não "erro"', () => {
    const passos = montarConversa({ ...base, podeAprovar: false });
    expect(passo(passos, 'aprovacao').dependencia?.destrava).toBe('papel');
  });
});

describe('onde a conversa está', () => {
  it('a primeira etapa sem resposta é a atual', () => {
    const passos = montarConversa({
      ...base,
      respostas: { objetivo: 'lead de FGTS', conta: 'Crédito Up · Search' },
    });
    expect(etapaAtual(passos)).toBe('destino');
    expect(progressoDaConversa(passos).respondidas).toBe(2);
  });
});
