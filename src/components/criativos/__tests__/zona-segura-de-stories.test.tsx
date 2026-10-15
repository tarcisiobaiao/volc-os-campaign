// @vitest-environment jsdom
/**
 * A zona segura de Stories como régua de prévia (EV-META-20).
 *
 * O que se trava aqui: os mesmos números que a Prensa usa para reservar a
 * interface numa variante 9:16 (W6b: 1080x1920 → 269/672/65), a recusa de
 * desenhar moldura fora de 9:16 ou sem medida, e a frase que nunca vira
 * veredito sobre a peça.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { MesaDeProporcoes } from '../job/MesaDeProporcoes';
import {
  eStory,
  fraseDaZonaSegura,
  proporcaoLegivel,
  zonaSeguraDeStories,
} from '../job/zonaSegura';
import type { Rendition } from '@/types/criativos';

afterEach(cleanup);

const peca = (over: Partial<Rendition>): Rendition => ({
  id: 'r1',
  slot: '1x1',
  rotulo: 'Quadrado',
  estado: 'pronta',
  larguraPedida: 1080,
  alturaPedida: 1080,
  nativoLargura: 1024,
  nativoAltura: 1024,
  largura: 1080,
  altura: 1080,
  bytesTotais: 1000,
  mime: 'image/png',
  contentHash: 'abc',
  enquadramento: null,
  masterId: null,
  previewUrl: 'https://exemplo.test/p.png',
  erro: null,
  custoUsd: null,
  concluidaEm: null,
  ...over,
});

describe('a zona segura', () => {
  it('bate com a Prensa (W6b) em 1080x1920 e 1440x2560', () => {
    expect(zonaSeguraDeStories(1080, 1920)?.px).toEqual({
      topo: 269, base: 672, esquerda: 65, direita: 65,
    });
    expect(zonaSeguraDeStories(1440, 2560)?.px).toEqual({
      topo: 359, base: 896, esquerda: 87, direita: 87,
    });
  });

  it('só existe em 9:16, com 1% de tolerância', () => {
    expect(eStory(1080, 1920)).toBe(true);
    expect(eStory(1080, 1910)).toBe(true); // 0,5654 vs 0,5625: 0,5%, dentro
    expect(eStory(1080, 1900)).toBe(false); // 1,05%: fora da tolerância
    expect(eStory(1080, 1350)).toBe(false);
    expect(zonaSeguraDeStories(1080, 1080)).toBeNull();
  });

  it('ausência de medida não vira 9:16', () => {
    expect(eStory(null, 1920)).toBe(false);
    expect(eStory(1080, 0)).toBe(false);
    expect(zonaSeguraDeStories(null, null)).toBeNull();
  });

  it('a frase cita a fonte e não declara a peça aprovada', () => {
    const frase = fraseDaZonaSegura(zonaSeguraDeStories(1080, 1920)!);
    expect(frase).toContain('EV-META-20');
    expect(frase).toContain('verificação da Prensa');
    expect(frase.toLowerCase()).not.toContain('dentro da zona');
    expect(frase.toLowerCase()).not.toContain('aprovad');
  });

  it('dá nome às proporções conhecidas', () => {
    expect(proporcaoLegivel(1080, 1080)).toBe('1:1');
    expect(proporcaoLegivel(1080, 1350)).toBe('4:5');
    expect(proporcaoLegivel(1080, 1920)).toBe('9:16');
    expect(proporcaoLegivel(1200, 628)).toBe('1,91:1');
    expect(proporcaoLegivel(1000, 300)).toBe('1000:300');
  });
});

describe('a mesa de proporções', () => {
  const familia = [
    peca({ id: 'a' }),
    peca({ id: 'b', slot: '4x5', rotulo: 'Feed', larguraPedida: 1080, alturaPedida: 1350 }),
    peca({ id: 'c', slot: '9x16', rotulo: 'Stories', larguraPedida: 1080, alturaPedida: 1920 }),
  ];

  it('não aparece com menos de duas peças com arquivo', () => {
    const { container } = render(
      <MesaDeProporcoes
        pecas={[familia[0], peca({ id: 'x', previewUrl: null })]}
        molduraLigada
        aoAlternarMoldura={() => undefined}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('peça falhada ou sem arquivo fica fora da mesa', () => {
    render(
      <MesaDeProporcoes
        pecas={[...familia, peca({ id: 'f', estado: 'falhou', previewUrl: null })]}
        molduraLigada
        aoAlternarMoldura={() => undefined}
      />,
    );
    expect(screen.getAllByRole('img')).toHaveLength(3);
  });

  it('desenha a moldura só na 9:16, e o botão a desliga', () => {
    let ligada = true;
    const { container, rerender } = render(
      <MesaDeProporcoes pecas={familia} molduraLigada={ligada} aoAlternarMoldura={() => { ligada = !ligada; }} />,
    );
    expect(container.querySelectorAll('[data-moldura-stories]')).toHaveLength(1);
    const botao = screen.getByRole('button', { name: /zona de stories/i });
    expect(botao.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(botao);
    rerender(
      <MesaDeProporcoes pecas={familia} molduraLigada={ligada} aoAlternarMoldura={() => undefined} />,
    );
    expect(container.querySelectorAll('[data-moldura-stories]')).toHaveLength(0);
  });

  it('sem 9:16 na família, não oferece moldura', () => {
    render(
      <MesaDeProporcoes pecas={familia.slice(0, 2)} molduraLigada aoAlternarMoldura={() => undefined} />,
    );
    expect(screen.queryByRole('button', { name: /zona de stories/i })).toBeNull();
  });
});
