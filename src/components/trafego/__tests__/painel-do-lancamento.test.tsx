// @vitest-environment jsdom
/**
 * O painel que responde "o que vai acontecer quando eu clicar".
 *
 * Existe porque o cockpit pedia vinte minutos de triagem e só revelava o
 * essencial DENTRO do overlay de lançamento — trava, conta, moeda, meta.
 * Descobrir a trava fechada depois de montar tudo desperdiça o trabalho.
 *
 * O caso mais importante é o último: conta em `maximize_conversions` SEM ação
 * primária gasta o orçamento sem sinal nenhum, e isso tem de gritar antes.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import type { Cockpit, EstadoDaTrava } from '@/types/trafego';
import { PainelDoLancamento } from '../PainelDoLancamento';

const FECHADA: EstadoDaTrava = {
  escrita_permitida: false, destravado_no_codigo: false, env_presente: false,
  motivo: '', explicacao: '',
};

function cockpitCom(conta: Partial<NonNullable<Cockpit['conta']>> = {}): Cockpit {
  return {
    opportunity_id: 74, cluster_id: 5,
    origem: {} as never, triagem: null, grupos: [], descartadas: [],
    procedencia: null, avisos: [],
    conta: {
      project_id: 2, dominio: 'creditoup.com.br', customer_id: '8017851692',
      login_customer_id: '6016739364', vinculada: true, motivo: null,
      nome: 'Crédito Up', moeda: 'BRL', fuso: 'America/Sao_Paulo',
      teste: false, auto_tagging: true,
      meta_conversao: {
        acoes: [], por_que: 'A campanha nasce em `maximize_conversions`…',
        primaria: { id: '7718441216', nome: 'adViewInterstitial',
                    categoria: 'PURCHASE', tipo: 'WEBPAGE' },
      },
      ...conta,
    },
  } as unknown as Cockpit;
}

const GRUPOS = [
  { tipo: 'INFORMACIONAL', keywords: ['a', 'b', 'c', 'd'] },
  { tipo: 'VALOR', keywords: ['e'] },
];

afterEach(cleanup);

describe('PainelDoLancamento', () => {
  it('diz a conta, a moeda, os ad groups e a meta antes de qualquer trabalho', () => {
    render(<PainelDoLancamento cockpit={cockpitCom()} trava={FECHADA}
                               gruposEscolhidos={GRUPOS} budget="10" estrategia="MANUAL_CPC" />);
    expect(screen.getByText('Crédito Up')).toBeTruthy();
    expect(screen.getByText(/8017851692 · BRL/)).toBeTruthy();
    // ⚠️ Era "2 · 5 keywords" e listava as sub-intenções como ad groups.
    // A doutrina fechada em 19/08/2026 é UM conjunto (SPEC-ARBITRAGEM P7): a
    // sub-intenção é a lente da triagem, não o recorte que vai para a conta.
    // Contar grupos aqui faria o operador esperar N RSAs e receber um.
    expect(screen.getByText('1 · 5 keywords')).toBeTruthy();
    expect(screen.getByText(/um conjunto, um RSA/)).toBeTruthy();
    expect(screen.getByText('adViewInterstitial')).toBeTruthy();
    // O fuso decide a que hora a verba do dia zera.
    expect(screen.getByText(/dia vira em America\/Sao_Paulo/)).toBeTruthy();
    expect(screen.getByText('nasce pausada')).toBeTruthy();
  });

  it('trava fechada é dita como convite, não como erro', () => {
    render(<PainelDoLancamento cockpit={cockpitCom()} trava={FECHADA}
                               gruposEscolhidos={GRUPOS} budget="10" estrategia="MANUAL_CPC" />);
    expect(screen.getByText(/validate_only/)).toBeTruthy();
    expect(screen.queryByText(/A trava de escrita está ABERTA/)).toBeNull();
  });

  // ⚠️ `env_presente`, não `escrita_permitida`.
  //
  // `modo.escrita_permitida()` é `_destravado_no_codigo AND env`, e o primeiro
  // só é verdadeiro DENTRO do `with destravar()` no servidor. Em repouso ele é
  // sempre falso — mesmo com a chave posta. Medido em 19/08/2026: o operador
  // subiu o backend com FORGE_PERMITIR_ESCRITA=1, o /trava devolveu
  // `env_presente: true, escrita_permitida: false`, e a tela concluiu
  // "travada". A escrita nunca seria tentada com a chave na fechadura.
  it('trava ABERTA avisa que o clique cria de verdade', () => {
    render(<PainelDoLancamento cockpit={cockpitCom()}
                               trava={{ ...FECHADA, env_presente: true }}
                               gruposEscolhidos={GRUPOS} budget="10" estrategia="MANUAL_CPC" />);
    expect(screen.getByText(/A trava de escrita está ABERTA/)).toBeTruthy();
  });

  it('conta SEM meta primária grita — é orçamento sem sinal', () => {
    // ⚠️ `maximize_conversions` sem ação primária otimiza para nada. É o pior
    // desfecho possível, e ele só aparecia depois do dinheiro gasto.
    const semMeta = cockpitCom({
      meta_conversao: {
        acoes: [], primaria: null,
        por_que: '⚠️ Esta conta não tem ação de conversão primária.',
      },
    });
    render(<PainelDoLancamento cockpit={semMeta} trava={FECHADA}
                               gruposEscolhidos={GRUPOS} budget="10" estrategia="MANUAL_CPC" />);
    expect(screen.getByText('sem meta primária')).toBeTruthy();
    expect(screen.getByText(/não tem ação de conversão primária/)).toBeTruthy();
  });

  it('auto-tagging desligado é dito; ligado não polui a tela', () => {
    render(<PainelDoLancamento cockpit={cockpitCom({ auto_tagging: false })}
                               trava={FECHADA} gruposEscolhidos={GRUPOS} budget="10" estrategia="MANUAL_CPC" />);
    expect(screen.getByText(/auto-tagging da conta está/)).toBeTruthy();
    cleanup();
    render(<PainelDoLancamento cockpit={cockpitCom({ auto_tagging: true })}
                               trava={FECHADA} gruposEscolhidos={GRUPOS} budget="10" estrategia="MANUAL_CPC" />);
    expect(screen.queryByText(/auto-tagging da conta está/)).toBeNull();
  });

  it('conta de teste é marcada — é a que serve ao primeiro disparo', () => {
    render(<PainelDoLancamento cockpit={cockpitCom({ teste: true })} trava={FECHADA}
                               gruposEscolhidos={GRUPOS} budget="10" estrategia="MANUAL_CPC" />);
    expect(screen.getByText(/CONTA DE TESTE/)).toBeTruthy();
  });
});

// ── a semântica dos dois campos da trava ────────────────────────────────────

describe('PainelDoLancamento · qual campo diz que a chave está posta', () => {
  it('env_presente sozinho JÁ significa autorizado — é o caso real', () => {
    // O que o /trava devolve com o backend subido com FORGE_PERMITIR_ESCRITA=1:
    // env_presente true, escrita_permitida false (só abre dentro do destravar).
    render(<PainelDoLancamento cockpit={cockpitCom()}
                               trava={{ ...FECHADA, env_presente: true,
                                        escrita_permitida: false }}
                               gruposEscolhidos={GRUPOS} budget="10" estrategia="MANUAL_CPC" />);
    expect(screen.getByText(/A trava de escrita está ABERTA/)).toBeTruthy();
  });

  it('sem env_presente continua dizendo que está fechada', () => {
    render(<PainelDoLancamento cockpit={cockpitCom()} trava={FECHADA}
                               gruposEscolhidos={GRUPOS} budget="10" estrategia="MANUAL_CPC" />);
    expect(screen.getByText(/A trava de escrita está fechada/)).toBeTruthy();
  });
});
