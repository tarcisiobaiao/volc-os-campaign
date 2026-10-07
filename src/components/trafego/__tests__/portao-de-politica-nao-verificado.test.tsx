// @vitest-environment jsdom
/**
 * O portão de política quando a LISTA DE PAÍSES não veio.
 *
 * `paises_exigem: string[]` é não-opcional no contrato (`types/trafego.ts`), e
 * o `|| []` no componente existe justamente porque a ausência em runtime é
 * possível. Até 02/09/2026 essa ausência não produzia "não sei": produzia
 * VERDE — o chip "sem portão em BR" e uma nota com escudo verde afirmando que
 * não há portão de habilitação naquele país.
 *
 * A regra é a mesma de `tomDoEstado` em `lib/trafego/portoes.ts`: só `PRONTO`
 * é positivo, e `INDETERMINADO` é cinza, nunca verde e nunca amarelo.
 */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PortaoDePolitica, vereditoDoPortao } from '../PortaoDePolitica';
import type { VerticalDePolitica } from '@/types/trafego';

afterEach(cleanup);

const FINANCEIRO_COMPLETO: VerticalDePolitica = {
  id: 'financeiro', titulo: 'Financeiro',
  descricao: 'Verificação obrigatória por PAÍS de segmentação.',
  exige: 'verificacao_servicos_financeiros', severidade: 'bloqueio',
  paises_exigem: ['BR', 'MX'],
};

const INFORMATIVO: VerticalDePolitica = {
  id: 'informativo', titulo: 'Informativo',
  descricao: 'O site explica e compara. Não presta o serviço.',
  exige: null, severidade: null, paises_exigem: [],
};

/** O que o servidor devolveu de verdade quando a lista não veio no payload. */
const FINANCEIRO_SEM_PAISES = {
  ...FINANCEIRO_COMPLETO,
  paises_exigem: undefined,
} as unknown as VerticalDePolitica;

const montar = (props: Partial<React.ComponentProps<typeof PortaoDePolitica>> = {}) =>
  render(
    <PortaoDePolitica
      verticais={[INFORMATIVO, FINANCEIRO_COMPLETO]} escolhida="financeiro"
      onEscolher={vi.fn()} certificacoes={[]} onCertificacoes={vi.fn()}
      pais="BR" sugeridaPelaEntidade="financeiro"
      {...props}
    />,
  );

describe('#4 · `paises_exigem` ausente não vira "sem portão"', () => {
  it('a nota de rodapé não afirma ausência de portão quando a lista não veio', () => {
    montar({ verticais: [INFORMATIVO, FINANCEIRO_SEM_PAISES] });
    expect(screen.queryByText(/Sem portão de habilitação em BR/)).toBeNull();
    expect(screen.getByText(/não foi possível verificar/i)).toBeTruthy();
  });

  it('o chip da vertical diz "não verificado", e não "sem portão"', () => {
    montar({ verticais: [INFORMATIVO, FINANCEIRO_SEM_PAISES] });
    const botao = screen.getByRole('button', { name: /Financeiro/ });
    expect(within(botao).queryByText('sem portão em BR')).toBeNull();
    expect(within(botao).getByText(/portão não verificado em BR/)).toBeTruthy();
  });

  it('lista de países PRESENTE e sem o país continua sendo uma conclusão verde', () => {
    montar({ pais: 'PT' });
    expect(screen.getByText(/Sem portão de habilitação em PT/)).toBeTruthy();
  });

  it('vertical sem exigência nenhuma continua sendo conclusão, não ignorância', () => {
    montar({ escolhida: 'informativo' });
    expect(screen.getByText(/Sem portão de habilitação em BR/)).toBeTruthy();
  });
});

describe('#5 · o veredito do portão é uma função pura, legível pelo pai', () => {
  it('barra quando exige no país e a conta não declara', () => {
    const v = vereditoDoPortao([INFORMATIVO, FINANCEIRO_COMPLETO], 'financeiro', [], 'BR');
    expect(v).toMatchObject({ estado: 'exige', barra: true, indeterminado: false });
  });

  it('não barra quando a conta declara a certificação', () => {
    const v = vereditoDoPortao(
      [INFORMATIVO, FINANCEIRO_COMPLETO], 'financeiro',
      ['verificacao_servicos_financeiros'], 'BR',
    );
    expect(v.barra).toBe(false);
  });

  it('lista de verticais VAZIA é indeterminado — nunca liberação', () => {
    const v = vereditoDoPortao([], 'financeiro', [], 'BR');
    expect(v.indeterminado).toBe(true);
    expect(v.estado).toBe('nao_verificavel');
  });

  it('`paises_exigem` ausente é indeterminado, e indeterminado não é `barra`', () => {
    const v = vereditoDoPortao([FINANCEIRO_SEM_PAISES], 'financeiro', [], 'BR');
    expect(v.estado).toBe('nao_verificavel');
    expect(v.indeterminado).toBe(true);
    // ⚠️ São coisas diferentes: `barra` afirma que o Google recusa;
    // `indeterminado` afirma que ninguém sabe. O pai trata as duas como
    // pendência, e a tela diz frases diferentes.
    expect(v.barra).toBe(false);
  });

  it('vertical sem exigência não é indeterminada — é conclusão', () => {
    const v = vereditoDoPortao([INFORMATIVO], 'informativo', [], 'BR');
    expect(v).toMatchObject({ estado: 'nao_exige', barra: false, indeterminado: false });
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// O QUE O SERVIDOR REALMENTE EMITE
//
// A primeira leva destas provas usava `paises_exigem: undefined` e `severidade`
// fora do contrato — formatos que o transporte não produz. `regra.get(...)` no
// backend devolve `[]` e `null`, e JSON não carrega `undefined`. Endurecer
// contra hipótese é barato; o que morde é o formato alcançável.
// ═══════════════════════════════════════════════════════════════════════════

describe('os formatos que o backend de fato emite', () => {
  it('severidade null com portão que se aplica NÃO abre o botão', () => {
    // `regra.get("severidade")` sem a chave no spec => null.
    const v = {
      id: 'financeiro', titulo: 'Financeiro', exige: 'cert_financeira',
      paises_exigem: ['BR'], severidade: null,
    } as unknown as VerticalDePolitica;

    const r = vereditoDoPortao([v], 'financeiro', [], 'BR');

    expect(r.estado).toBe('exige');
    // o portão existe e se aplica: seguir seria seguir por ignorância
    expect(r.barra || r.limita || r.indeterminado).toBe(true);
    expect(r.indeterminado).toBe(true);
  });

  it('lista de países VAZIA ao lado de exige preenchido não é "sem portão"', () => {
    // `regra.get("paises_exigem", [])` sem a chave no spec => [].
    const v = {
      id: 'saude', titulo: 'Saúde', exige: 'cert_saude',
      paises_exigem: [], severidade: 'bloqueio',
    } as unknown as VerticalDePolitica;

    const r = vereditoDoPortao([v], 'saude', [], 'BR');

    expect(r.estado).not.toBe('nao_exige');
    expect(r.estado).toBe('nao_verificavel');
    expect(r.indeterminado).toBe(true);
  });

  it('o caminho bom continua bom: lista com o país, severidade lida', () => {
    const v = {
      id: 'varejo', titulo: 'Varejo', exige: null,
      paises_exigem: ['BR'], severidade: null,
    } as unknown as VerticalDePolitica;
    const r = vereditoDoPortao([v], 'varejo', [], 'BR');
    expect(r.estado).toBe('nao_exige');
    expect(r.barra).toBe(false);
    expect(r.limita).toBe(false);
    expect(r.indeterminado).toBe(false);
  });
});
