// @vitest-environment jsdom
/**
 * A linha que não pode transformar ausência em zero.
 *
 * Este é o defeito mais caro que uma tela de gasto sabe cometer, e ele nasce de
 * duas linhas que parecem inofensivas:
 *
 *   {valor || ausencia}   // um zero MEDIDO vira "não medido"
 *   {valor ?? 0}          // "não perguntei" vira "perguntei e deu zero"
 *
 * As duas leituras levam a decisões opostas — a primeira manda medir de novo o
 * que já foi medido, a segunda manda gastar contra um número que ninguém leu.
 * `design.md:148` separa os quatro estados por nome ("Absence, failure, stale
 * data and measured zero are different states") e `src/types/trafego.ts:289`
 * repete a lei no tipo do Pedido.
 *
 * Por isso o teste é literal: com `valor={null}` a string "0" não pode aparecer
 * em lugar nenhum do DOM.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';

import { BlocoDeEvidencia, LinhaDeFato } from '../BlocoDeEvidencia';

afterEach(cleanup);

describe('LinhaDeFato', () => {
  it('com valor null escreve a palavra de ausência e nunca "0"', () => {
    const { container } = render(
      <LinhaDeFato rotulo="CPC medido" valor={null} fonte="a mineração" />,
    );
    const texto = container.textContent ?? '';
    expect(texto).toContain('não medido');
    expect(texto, 'ausência virou zero').not.toContain('0');
  });

  it('com valor undefined faz o mesmo — ausência não tem duas formas', () => {
    const { container } = render(<LinhaDeFato rotulo="Teto de gasto" valor={undefined} />);
    expect(container.textContent).toContain('não medido');
    expect(container.textContent).not.toContain('0');
  });

  it('zero MEDIDO continua sendo zero', () => {
    const { container } = render(
      <LinhaDeFato rotulo="Cliques" valor={0} fonte="a conta" frescor="lido há 6 min" />,
    );
    // O ramo de ausência não pode capturar um zero de verdade: "a conta
    // respondeu 0" e "ninguém perguntou" são fatos opostos.
    expect(container.textContent).toContain('0');
    expect(container.textContent).not.toContain('não medido');
    expect(container.textContent).toContain('lido há 6 min');
  });

  it('a palavra de ausência pode ser o travessão, e quem ouve recebe "ausente"', () => {
    const { container } = render(
      <LinhaDeFato rotulo="Meta efetiva" valor={null} fonte="a conta" ausencia="—" />,
    );
    // `RESPONSIVE-AND-A11Y.md §5.5`: "—" sozinho não é conteúdo para leitor de
    // tela. O símbolo fica `aria-hidden` e a palavra entra em `sr-only`.
    expect(container.textContent).toContain('—');
    expect(container.textContent).toContain('ausente');
    expect(container.querySelector('[aria-hidden="true"]')?.textContent).toBe('—');
    expect(container.textContent).toContain('fonte: a conta');
  });

  it('frescor só aparece quando veio', () => {
    const { container } = render(<LinhaDeFato rotulo="Volume" valor="1.240" fonte="a mineração" />);
    expect(container.textContent).toContain('fonte: a mineração');
    expect(container.textContent).not.toContain('·');
  });
});

describe('BlocoDeEvidencia', () => {
  it('não é cartão: sem sombra, com poço e hairline no topo', () => {
    const { container } = render(
      <BlocoDeEvidencia titulo="O que a conta respondeu" tom="atencao">
        <LinhaDeFato rotulo="Moeda" valor="BRL" fonte="a conta" />
      </BlocoDeEvidencia>,
    );
    const secao = container.querySelector('section');
    const classe = secao?.className ?? '';
    // `design.md:100`: cartão dentro de cartão é sempre errado.
    expect(classe).not.toContain('shadow-card');
    expect(classe).toContain('bg-muted/20');
    // `design.md:99`: estado num cartão é hairline de 2px no TOPO.
    expect(classe).toContain('before:top-0');
    expect(classe).toContain('before:h-[2px]');
    expect(classe).not.toContain('border-l-2');
    expect(screen.getByRole('heading', { level: 3 }).textContent).toBe('O que a conta respondeu');
  });

  it('a calha de 24px é a mesma em todo bloco', () => {
    const { container } = render(
      <BlocoDeEvidencia titulo="Destino">
        <p>conteúdo</p>
      </BlocoDeEvidencia>,
    );
    expect(container.innerHTML).toContain('grid-cols-[24px_minmax(0,1fr)]');
  });
});
