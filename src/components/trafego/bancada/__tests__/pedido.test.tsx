// @vitest-environment jsdom
/**
 * O Pedido: projeção pura, ausência declarada, e nenhuma região viva.
 *
 * Três leis convergem neste componente e nenhuma delas é opcional:
 *
 * 1. `SCREEN-CONTRACTS.md:309-311` — toda linha tem rótulo, valor, fonte e,
 *    quando é medida, frescor; `FALTA` vem do servidor; `próximo ato` é frase.
 * 2. `src/types/trafego.ts:289` — `null` é ausência, escreve "—" e diz quem não
 *    leu. Nunca `0`, nunca célula vazia.
 * 3. `RESPONSIVE-AND-A11Y.md:227` — o Pedido NÃO é região viva. Ele muda a cada
 *    decisão e falaria o tempo todo, por cima da parada que está sendo lida.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';

import type { LinhaDoPedido } from '@/types/trafego';
import { Pedido } from '../Pedido';

afterEach(cleanup);

const LINHAS: LinhaDoPedido[] = [
  { rotulo: 'Conta', valor: 'Crédito Up (801-785-1692)', fonte: 'o projeto' },
  { rotulo: 'Teto de gasto diário', valor: null, fonte: 'você, ainda não' },
  { rotulo: 'CPC de referência', valor: 'R$ 3,40', fonte: 'a mineração', frescor: 'lido há 6 min' },
];

describe('Pedido', () => {
  it('ausência vira travessão e a companhia de quem não leu — nunca zero', () => {
    const { container } = render(
      <Pedido linhas={LINHAS} faltas={[]} proximoAto="Provar contra a conta." />,
    );
    const texto = container.textContent ?? '';
    expect(texto).toContain('Teto de gasto diário');
    expect(texto).toContain('—');
    expect(texto).toContain('você, ainda não');
    // A linha ausente não pode ter virado um zero em lugar nenhum da projeção.
    expect(texto).not.toContain('R$ 0');
    expect(texto).not.toContain('0,00');
  });

  it('frescor só nas linhas em que ele veio', () => {
    const { container } = render(<Pedido linhas={LINHAS} faltas={[]} proximoAto={null} />);
    const texto = container.textContent ?? '';
    expect(texto).toContain('lido há 6 min');
    // Três linhas, um único carimbo de frescor: nenhum foi copiado para as
    // vizinhas nem inventado a partir do relógio local.
    expect(texto.match(/lido há 6 min/g)?.length).toBe(1);
  });

  it('as faltas vêm do servidor e aparecem inteiras', () => {
    const faltas = ['nenhum termo marcado', 'teto de gasto não informado'];
    const { container } = render(
      <Pedido linhas={LINHAS} faltas={faltas} proximoAto="Marcar ao menos um termo." />,
    );
    expect(container.textContent).toContain('Falta (2)');
    for (const f of faltas) expect(container.textContent).toContain(f);
  });

  it('próximo ato é frase, nunca botão', () => {
    const { container } = render(
      <Pedido linhas={LINHAS} faltas={[]} proximoAto="Provar contra a conta antes de criar." />,
    );
    expect(container.querySelectorAll('button').length).toBe(0);
    expect(container.textContent).toContain('Provar contra a conta antes de criar.');
  });

  it('sem próximo ato, a ausência é DECLARADA', () => {
    const { container } = render(<Pedido linhas={LINHAS} faltas={[]} proximoAto={null} />);
    // Uma frase que some lê-se como "não há mais nada a fazer".
    expect(container.textContent).toContain('nenhum próximo ato declarado');
  });

  it('sem linha nenhuma, não escreve "tudo certo"', () => {
    const { container } = render(<Pedido linhas={[]} faltas={[]} proximoAto={null} />);
    expect(container.textContent).toContain('nenhuma decisão registrada ainda');
    expect(container.textContent).not.toContain('tudo certo');
  });

  it('não é região viva', () => {
    const { container } = render(<Pedido linhas={LINHAS} faltas={[]} proximoAto={null} />);
    expect(container.querySelectorAll('[aria-live]').length).toBe(0);
    expect(container.querySelectorAll('[role="alert"]').length).toBe(0);
    expect(container.querySelectorAll('[role="status"]').length).toBe(0);
  });

  it('é superfície de trabalho, não cartão dentro de cartão', () => {
    const { container } = render(<Pedido linhas={LINHAS} faltas={['x']} proximoAto={null} />);
    const secao = container.querySelector('section') as HTMLElement;
    expect(secao.className).toContain('shadow-card');
    // O agrupamento interno das faltas é poço, sem sombra.
    const poco = container.querySelector('.bg-muted\\/20') as HTMLElement | null;
    expect(poco, 'as faltas perderam o poço').toBeTruthy();
    expect(poco?.className).not.toContain('shadow-card');
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('O pedido');
  });
});
