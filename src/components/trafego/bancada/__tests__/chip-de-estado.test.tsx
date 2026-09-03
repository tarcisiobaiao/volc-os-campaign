// @vitest-environment jsdom
/**
 * O chip que nunca comunica só por cor.
 *
 * `PRODUCT.md:36` e `design.md:166` dizem a mesma coisa: cor não é o único
 * portador de significado. A descrição não é enfeite — `Selos.tsx:11-14` já
 * registra o porquê com o exemplo que dói: "não encontrada" e "sincronização
 * falhou" parecem vizinhas e são opostas, uma afirma que a conta respondeu e a
 * outra que ela não respondeu. Sem a frase, as duas viram "sumiu".
 *
 * `title` não basta: ele não é lido por leitor de tela em toque nem alcançado
 * por teclado. Por isso a descrição vive no DOM, em `sr-only`.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { CircleCheck, Lock } from 'lucide-react';
import React from 'react';

import { ChipDeEstado } from '../ChipDeEstado';

afterEach(cleanup);

describe('ChipDeEstado', () => {
  it('sempre emite a descrição para leitor de tela', () => {
    const { container } = render(
      <ChipDeEstado
        glifo={Lock}
        palavra="Bloqueado"
        descricao="a conta do projeto não está vinculada"
        tom="ruim"
      />,
    );
    const srOnly = container.querySelector('.sr-only');
    expect(srOnly, 'o chip perdeu a descrição para quem ouve').toBeTruthy();
    expect(srOnly?.textContent).toContain('a conta do projeto não está vinculada');
    expect(container.querySelector('[title]')?.getAttribute('title')).toBe(
      'Bloqueado — a conta do projeto não está vinculada',
    );
  });

  it('a cor fica na borda, no leito e no glifo — nunca na palavra', () => {
    const { container } = render(
      <ChipDeEstado glifo={CircleCheck} palavra="Confirmado" descricao="a conta respondeu" tom="bom" />,
    );
    const chip = container.firstElementChild as HTMLElement;
    const classe = chip.className;
    // `--warning` a 28% de luminosidade contra o leito do cartão torna
    // ilegível justamente o rótulo que decide (`Selos.tsx:70-78`).
    expect(classe).toContain('text-foreground');
    expect(classe).toContain('border-success/40');
    expect(classe).toContain('bg-success/[0.08]');
    expect(classe).not.toContain('text-success');
    // O glifo, sim, carrega a cor.
    expect(chip.querySelector('svg')?.getAttribute('class')).toContain('text-success');
  });

  it('tem a geometria de pílula que o front-matter fixa, em caixa de sentença', () => {
    const { container } = render(
      <ChipDeEstado glifo={CircleCheck} palavra="Verificado" descricao="observado na conta" tom="verificado" />,
    );
    const classe = (container.firstElementChild as HTMLElement).className;
    // `design.md:56-58`: state-chip radius 999px, height 24px.
    expect(classe).toContain('rounded-full');
    expect(classe).toContain('h-6');
    // 13px, e sem `uppercase` — `VISUAL-DIRECTION.md §8` proíbe caixa alta
    // fora do `.kicker`.
    expect(classe).toContain('text-[0.8125rem]');
    expect(classe).not.toContain('uppercase');
  });

  it('o tom neutro é o padrão e continua legível', () => {
    const { container } = render(
      <ChipDeEstado glifo={CircleCheck} palavra="Pendente" descricao="ninguém decidiu ainda" />,
    );
    const classe = (container.firstElementChild as HTMLElement).className;
    expect(classe).toContain('bg-muted/50');
    expect(classe).toContain('text-foreground');
  });
});
