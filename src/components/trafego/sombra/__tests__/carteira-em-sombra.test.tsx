// @vitest-environment jsdom
/**
 * A carteira em sombra (W13), provada com fixture e sem serviço no ar.
 *
 * O que importa provar: cada campanha aparece com estado do dado e direção;
 * "sem dado" é dito com essas palavras e o ROAS fica "—", nunca 0; a linha
 * ambígua não mostra direção; e não existe controle algum que execute nada.
 */
import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { CarteiraEmSombra } from '@/components/trafego/sombra/CarteiraEmSombra';
import type { CarteiraShadow, LinhaCarteiraShadow } from '@/types/recomendacaoShadow';

afterEach(cleanup);

const janela = (roas: number | null, custo: number | null, receita: number | null) => ({
  dias: roas === null ? 0 : 16, custo_brl: custo, receita_brl: receita, cliques: roas === null ? null : 634,
  roas, cpc: null, rpc: null, contribuicao_bruta: null,
});

const linha = (over: Partial<LinhaCarteiraShadow>): LinhaCarteiraShadow => ({
  campanha_externa: '900000000001', campanha_nome: 'Campanha A', campanha_status: 'ENABLED',
  conta: '111****334', situacao: 'lida', mensagem: null, direcao: 'pausar', estado_dado: 'completo',
  motivo_estado_dado: null, as_of: '2026-10-15', experimento_id: 'gads-900000000001-sombra-20261015',
  janela_madura: janela(0.0735, 554.75, 40.79), fracao_custo_maduro_sem_receita: 0.0006,
  valor_sugerido: null, executada: false, ...over,
});

const CARTEIRA: CarteiraShadow = {
  contrato: 'carteira_shadow.v1',
  integridade: 'coerente_com_manifesto',
  isolamento: { chamadas_externas: 0, mutacoes_executadas: 0, oferece_aplicar: false },
  campanhas: [
    linha({}),
    linha({
      campanha_externa: '900000000002', campanha_nome: 'Campanha B', direcao: 'evidencia_insuficiente',
      estado_dado: 'sem_dado', janela_madura: janela(null, null, null), fracao_custo_maduro_sem_receita: 1,
      motivo_estado_dado: '100% do custo maduro não tem receita reconciliada em BRL: cambio_defasado R$ 170,00',
    }),
    linha({ campanha_externa: '900000000003', campanha_nome: 'Campanha C', direcao: 'aumentar',
            janela_madura: janela(1.62, 340, 550.8) }),
    linha({ campanha_externa: '900000000004', situacao: 'ambigua', direcao: null, estado_dado: null,
            mensagem: '2 experimentos da campanha têm o mesmo as_of', janela_madura: null }),
  ],
};

const pronta = () => render(<CarteiraEmSombra leitura={{ estado: 'pronta', carteira: CARTEIRA }} />);
const linhaDe = (id: string) => document.querySelector(`tr[data-campanha="${id}"]`) as HTMLElement;

describe('CarteiraEmSombra', () => {
  it('lista cada campanha com estado do dado e direção', () => {
    pronta();
    expect(within(linhaDe('900000000001')).getAllByText('pausar').length).toBeGreaterThan(0);
    expect(within(linhaDe('900000000001')).getByText('dado completo')).toBeTruthy();
    expect(within(linhaDe('900000000003')).getAllByText('aumentar').length).toBeGreaterThan(0);
    expect(screen.getByTestId('resumo-carteira').textContent).toMatch(/4 campanhas/);
    expect(screen.getByTestId('resumo-carteira').textContent).toMatch(/1 sem dado/);
  });

  it('sem dado é dito em palavras e o ROAS fica ausente, nunca 0', () => {
    pronta();
    const l = linhaDe('900000000002');
    expect(within(l).getByText('sem dado')).toBeTruthy();
    expect(within(l).getAllByText('evidência insuficiente').length).toBeGreaterThan(0);
    expect(l.textContent).not.toMatch(/R\$\s?0,00/);
    expect(l.textContent).not.toMatch(/(^|\s)0,00(\s|$)/);
    expect(within(l).getAllByText('—').length).toBeGreaterThanOrEqual(3);
  });

  it('linha ambígua não mostra direção', () => {
    pronta();
    const l = linhaDe('900000000004');
    expect(l.textContent).toMatch(/nenhum é exibido/);
    expect(within(l).queryByText('pausar')).toBeNull();
  });

  it('não oferece nenhum controle que execute a recomendação', () => {
    const { container } = pronta();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryAllByRole('link')).toHaveLength(0);
    expect(container.querySelectorAll('input, select, textarea, form, a')).toHaveLength(0);
    expect(screen.getByTestId('faixa-sombra-carteira').textContent).toMatch(/Nada foi\s+executado/);
  });

  it('cada forma de não saber tem frase própria', () => {
    render(<CarteiraEmSombra leitura={{ estado: 'integridade', mensagem: 'x' }} />);
    expect(screen.getByRole('alert').textContent).toMatch(/nenhuma linha pode ser afirmada/);
    cleanup();
    render(<CarteiraEmSombra leitura={{ estado: 'fonte_indisponivel', mensagem: 'x' }} />);
    expect(screen.getByRole('alert').textContent).toMatch(/não quer dizer que a carteira esteja vazia/);
    cleanup();
    render(<CarteiraEmSombra leitura={{ estado: 'pronta', carteira: { ...CARTEIRA, campanhas: [] } }} />);
    expect(screen.getByRole('status').textContent).toMatch(/ausência de análise/);
  });
});
