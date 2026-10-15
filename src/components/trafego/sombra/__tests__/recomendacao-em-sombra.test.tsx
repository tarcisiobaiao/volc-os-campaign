// @vitest-environment jsdom
/**
 * A recomendação em sombra, provada com fixture e sem serviço no ar.
 *
 * O que importa provar: a direção aparece com o nome do vocabulário; o grão
 * campanha × dia mostra ausência como ausência; as ressalvas aparecem; o ROAS
 * nativo do Google é marcado não confiável; e NÃO EXISTE controle algum que
 * execute a recomendação. Cada forma de não saber tem frase própria.
 */
import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { RecomendacaoEmSombra } from '@/components/trafego/sombra/RecomendacaoEmSombra';
import { RECOMENDACAO_SENAC } from '@/components/trafego/sombra/fixtureSenac';
import type { DirecaoShadow } from '@/types/recomendacaoShadow';

afterEach(cleanup);

const pronta = (direcao: DirecaoShadow = 'pausar') =>
  render(
    <RecomendacaoEmSombra
      leitura={{ estado: 'pronta', recomendacao: { ...RECOMENDACAO_SENAC, direcao } }}
    />,
  );

describe('RecomendacaoEmSombra', () => {
  it('mostra a direção, os motivos e a faixa de sombra', () => {
    pronta();
    expect(screen.getAllByText('pausar').length).toBeGreaterThan(0);
    expect(screen.getByText('ROAS maduro 0.073 em 634 cliques')).toBeTruthy();
    expect(screen.getByTestId('faixa-sombra').textContent).toMatch(/Nada foi\s+executado/);
  });

  it.each<[DirecaoShadow, string]>([
    ['manter', 'manter'],
    ['reduzir', 'reduzir'],
    ['aumentar', 'aumentar'],
    ['evidencia_insuficiente', 'evidência insuficiente'],
  ])('nomeia a direção %s', (direcao, palavra) => {
    pronta(direcao);
    expect(screen.getAllByText(palavra).length).toBeGreaterThan(0);
  });

  it('não oferece nenhum controle que execute a recomendação', () => {
    const { container } = pronta();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryAllByRole('link')).toHaveLength(0);
    expect(container.querySelectorAll('input, select, textarea, form')).toHaveLength(0);
  });

  it('marca o ROAS nativo do Google como não confiável', () => {
    pronta();
    const nota = screen.getByRole('note', { name: /ROAS nativo do Google não confiável/ });
    expect(nota.textContent).toMatch(/não confiável/);
    expect(nota.textContent).toMatch(/fixo em 10/);
    expect(nota.textContent).toMatch(/2\.380,00/);
  });

  it('mostra o grão campanha × dia com ausência como ausência, não zero', () => {
    pronta();
    const tabela = screen.getByRole('table');
    expect(within(tabela).getByText(/Grão campanha × dia/)).toBeTruthy();
    const semNada = within(tabela).getByRole('row', { name: /2026-09-23/ });
    expect(within(semNada).getAllByText('—')).toHaveLength(4);
    expect(semNada.textContent).not.toMatch(/0,00/);
    const semReceita = within(tabela).getByRole('row', { name: /2026-10-01/ });
    expect(within(semReceita).getAllByText('—')).toHaveLength(2);
    const imatura = within(tabela).getByRole('row', { name: /2026-10-14/ });
    expect(imatura.textContent).toMatch(/imatura/);
  });

  it('lista as ressalvas e a procedência conferida', () => {
    pronta();
    expect(screen.getByText(/câmbio fixo 5\.25/)).toBeTruthy();
    expect(screen.getByText(/integridade conferida/)).toBeTruthy();
  });

  it('ausência de experimento não vira recomendação de manter', () => {
    render(<RecomendacaoEmSombra leitura={{ estado: 'ausente' }} />);
    expect(screen.getByRole('status').textContent).toMatch(/não recomendação de manter/);
    expect(screen.queryByText('manter')).toBeNull();
  });

  it('integridade quebrada é alerta, e o número não aparece', () => {
    render(
      <RecomendacaoEmSombra
        leitura={{ estado: 'integridade', mensagem: 'transformacao.csv não bate.' }}
      />,
    );
    expect(screen.getByRole('alert').textContent).toMatch(/conferência de integridade/);
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('falha de leitura é alerta com a mensagem do servidor', () => {
    render(
      <RecomendacaoEmSombra
        leitura={{ estado: 'falhou', mensagem: 'Backend indisponível (503).', status: 503 }}
      />,
    );
    expect(screen.getByRole('alert').textContent).toMatch(/503/);
  });
});
