// @vitest-environment jsdom
/**
 * O painel de bloqueio: projeção do veredito do servidor, e nada além disso.
 *
 * A regra que este teste guarda é a de `src/types/trafego.ts:184-200`: até
 * 03/09/2026 existiam DUAS réguas para o mesmo veredito — o engine barrava só
 * `bloqueio`, a tela barrava tudo que não fosse `informacao`/`atencao`. Agora o
 * servidor adjudica e o navegador projeta. Se este componente voltar a filtrar
 * por severidade, a divergência volta com ele.
 *
 * O segundo caso é o vazio. Lista vazia NÃO é "tudo certo": é ausência de
 * bloqueio. Um painel vazio dizendo "nenhum bloqueio" ocuparia o lugar mais
 * alto da tela com uma não-notícia — e `VISUAL-DIRECTION.md §8` proíbe por nome
 * desenhar lista vazia como "tudo certo".
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';

import type { AvisoDoCockpit } from '@/types/trafego';
import { PainelDeBloqueio } from '../PainelDeBloqueio';

afterEach(cleanup);

const BLOQUEIOS: AvisoDoCockpit[] = [
  {
    codigo: 'CONTA_NAO_VINCULADA',
    severidade: 'bloqueio',
    titulo: 'A conta do projeto não está vinculada',
    detalhe: 'sem customer_id não há onde criar a campanha',
  },
  {
    codigo: 'POLITICA_FULLY_LIMITED',
    severidade: 'limitacao',
    titulo: 'A vertical está totalmente limitada',
    detalhe: 'anúncio que não veicula é reprovação com outro nome',
  },
];

describe('PainelDeBloqueio', () => {
  it('com lista vazia não renderiza NADA', () => {
    const { container } = render(<PainelDeBloqueio bloqueios={[]} />);
    expect(container.innerHTML).toBe('');
  });

  it('mostra título, detalhe e código de cada bloqueio', () => {
    const { container } = render(<PainelDeBloqueio bloqueios={BLOQUEIOS} />);
    const texto = container.textContent ?? '';
    for (const b of BLOQUEIOS) {
      expect(texto).toContain(b.titulo);
      expect(texto).toContain(b.detalhe);
      expect(texto).toContain(b.codigo);
    }
    expect(container.querySelectorAll('li').length).toBe(2);
  });

  it('não reclassifica severidade: conta o que recebeu', () => {
    // `limitacao` BARRA (`src/types/trafego.ts:145`). Se o painel refiltrasse
    // por severidade, o segundo item sumiria e a contagem cairia para 1.
    const { container } = render(<PainelDeBloqueio bloqueios={BLOQUEIOS} />);
    expect(container.textContent).toContain('2 impedimentos');
    expect(container.textContent).toContain('Bloqueado');
  });

  it('sem carimbo de leitura, DIZ que não tem carimbo', () => {
    const { container } = render(<PainelDeBloqueio bloqueios={BLOQUEIOS} lidoEm={null} />);
    // `new Date()` aqui mediria a hora de quem olha, não a idade do dado.
    expect(container.textContent).toContain('sem carimbo de leitura');
  });

  it('com carimbo, mostra o instante lido — não uma distância inventada', () => {
    const { container } = render(
      <PainelDeBloqueio bloqueios={BLOQUEIOS} lidoEm="2026-09-03T14:32:00.000Z" />,
    );
    expect(container.textContent).toContain('lido em');
    expect(container.textContent).not.toContain('sem carimbo de leitura');
  });

  it('o estado entra por hairline no topo, nunca por faixa lateral', () => {
    const { container } = render(<PainelDeBloqueio bloqueios={BLOQUEIOS} />);
    const secao = container.querySelector('section');
    const classe = secao?.className ?? '';
    expect(classe).toContain('before:top-0');
    expect(classe).toContain('before:h-[2px]');
    expect(classe).not.toContain('border-l-2');
    expect(classe).toContain('shadow-card');
  });

  it('não anima: bloqueio aparece no primeiro quadro', () => {
    const { container } = render(<PainelDeBloqueio bloqueios={BLOQUEIOS} />);
    // `MOTION-AND-INTERACTION.md §2`: "Bloqueio — nada." Um impedimento que
    // entra suave sugere que chegou depois e que talvez saia sozinho.
    expect(container.innerHTML).not.toContain('transition');
    expect(container.innerHTML).not.toContain('animate-');
    expect(container.innerHTML).not.toContain('reveal');
  });

  it('aceita outro título sem perder a identidade do painel', () => {
    render(<PainelDeBloqueio bloqueios={BLOQUEIOS} titulo="Não dá para provar ainda" />);
    expect(screen.getByRole('heading', { level: 3 }).textContent).toBe('Não dá para provar ainda');
  });
});
