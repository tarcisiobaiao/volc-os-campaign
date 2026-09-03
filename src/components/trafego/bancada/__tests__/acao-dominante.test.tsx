// @vitest-environment jsdom
/**
 * A ação que, quando não pode agir, diz TUDO o que falta.
 *
 * O contra-modelo está medido em `NovaCampanhaPage.tsx:461-479`: "Lançar outra"
 * desabilita em silêncio, e a razão de "Lançar campanha" existe apenas de
 * `sm:` para cima (`hidden … sm:block`) — some no telefone, onde o operador tem
 * menos contexto e mais pressa. Um botão cinza mudo não distingue "o sistema
 * falhou" de "você não pode", e essas duas conclusões levam a ligações
 * diferentes para pessoas diferentes.
 *
 * Este teste prova as três coisas que impedem a regressão: todas as faltas em
 * texto VISÍVEL, `aria-describedby` que resolve, e nenhuma classe que esconda a
 * razão em algum breakpoint.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';

import { AcaoDominante } from '../AcaoDominante';

afterEach(cleanup);

const FALTAS = [
  'a conta do projeto não está vinculada',
  'nenhum termo foi marcado na mesa',
  'o teto de gasto diário não foi informado',
];

describe('AcaoDominante', () => {
  it('com pode=false mostra TODAS as faltas em texto visível', () => {
    const { container } = render(
      <AcaoDominante pode={false} faltas={FALTAS}>
        Provar contra a conta
      </AcaoDominante>,
    );
    for (const falta of FALTAS) {
      expect(container.textContent, `falta omitida: ${falta}`).toContain(falta);
    }
    expect(container.querySelectorAll('li').length).toBe(3);
    // Nem "+N", nem corte.
    expect(container.textContent).not.toMatch(/\+\d/);
    // E nada de esconder a razão por breakpoint.
    expect(container.innerHTML).not.toContain('hidden sm:');
    expect(container.innerHTML).not.toContain('sr-only">a conta do projeto');
  });

  it('o botão desabilitado aponta para a razão, e a razão existe', () => {
    render(
      <AcaoDominante pode={false} faltas={FALTAS}>
        Provar contra a conta
      </AcaoDominante>,
    );
    const botao = screen.getByRole('button', { name: /provar contra a conta/i });
    expect((botao as HTMLButtonElement).disabled).toBe(true);
    expect(botao.getAttribute('aria-disabled')).toBe('true');
    const id = botao.getAttribute('aria-describedby') ?? '';
    const razao = document.getElementById(id);
    expect(razao, 'aria-describedby apontando para o vazio').toBeTruthy();
    for (const falta of FALTAS) {
      expect(razao?.textContent).toContain(falta);
    }
  });

  it('quando pode, age — e nenhuma falta é inventada', () => {
    const aoAgir = vi.fn();
    const { container } = render(
      <AcaoDominante pode faltas={[]} onClick={aoAgir}>
        Criar campanha pausada
      </AcaoDominante>,
    );
    const botao = screen.getByRole('button');
    expect((botao as HTMLButtonElement).disabled).toBe(false);
    expect(botao.getAttribute('aria-describedby')).toBeNull();
    expect(container.querySelectorAll('li').length).toBe(0);
    botao.click();
    expect(aoAgir).toHaveBeenCalledTimes(1);
  });

  it('enviando declara aria-busy e trava sem apagar o rótulo', () => {
    render(
      <AcaoDominante pode enviando faltas={[]}>
        Criar campanha pausada
      </AcaoDominante>,
    );
    const botao = screen.getByRole('button');
    expect(botao.getAttribute('aria-busy')).toBe('true');
    expect((botao as HTMLButtonElement).disabled).toBe(true);
    // O rótulo continua legível: trocá-lo por "Enviando…" apaga o que o
    // operador autorizou no momento em que ele quer conferir.
    expect(botao.textContent).toContain('Criar campanha pausada');
  });

  it('só anima o que o contrato autoriza', () => {
    render(
      <AcaoDominante pode faltas={[]}>
        Confirmar e seguir
      </AcaoDominante>,
    );
    const classe = screen.getByRole('button').className;
    expect(classe).not.toContain('transition-all');
    expect(classe).toContain('transition-[background-color,transform]');
    // `design.md:117`: press em 0.96, nunca abaixo de 0.95.
    expect(classe).toContain('active:scale-[0.96]');
    // Hover-lift só em ponteiro fino.
    expect(classe).toContain('[@media(hover:hover)and(pointer:fine)]:hover:-translate-y-px');
    // 44px no toque, 40px no desktop.
    expect(classe).toContain('h-11');
    expect(classe).toContain('md:h-10');
  });
});
