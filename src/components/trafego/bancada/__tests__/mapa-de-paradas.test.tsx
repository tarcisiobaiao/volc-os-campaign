// @vitest-environment jsdom
/**
 * O mapa das paradas: o que ele promete e o que ele nunca conta.
 *
 * Dois defeitos são medidos aqui porque os dois são invisíveis a olho nu:
 *
 * 1. **Parada bloqueada como `<button disabled>`.** Um botão desabilitado sai
 *    da ordem de foco. Quem navega por teclado nunca chega nele e a causa — a
 *    única informação útil de uma parada bloqueada — desaparece junto. O
 *    contrato de tela manda `<span aria-disabled="true">` com a causa ligada
 *    por `aria-describedby` (`SCREEN-CONTRACTS.md:139`).
 *
 * 2. **`nao_se_aplica` dentro do denominador.** Um canal sem construtor de
 *    anúncio não tem parada de anúncio; contá-la faz a tela escrever "parada 3
 *    de 6" num lançamento que tem cinco, e o operador passa a sessão
 *    procurando a sexta. A lei está no tipo (`src/types/trafego.ts:250`).
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

import type { ParadaProjetada } from '@/types/trafego';
import { MapaDeParadas } from '../MapaDeParadas';

afterEach(cleanup);

const CAUSA = 'a conta do projeto não está vinculada, então não há onde criar';

const PARADAS: ParadaProjetada[] = [
  { parada: 'destino', rotulo: 'Destino', estado: 'confirmada', causa: null },
  { parada: 'politica', rotulo: 'Política', estado: 'confirmada', causa: null },
  { parada: 'termos', rotulo: 'Termos', estado: 'atual', causa: null },
  { parada: 'anuncio', rotulo: 'Anúncio', estado: 'nao_se_aplica', causa: null },
  { parada: 'economia', rotulo: 'Economia', estado: 'pendente', causa: null },
  { parada: 'revisao', rotulo: 'Revisão', estado: 'bloqueada', causa: CAUSA },
];

function montar(atual: ParadaProjetada['parada'] = 'termos') {
  return render(
    <MemoryRouter>
      <MapaDeParadas paradas={PARADAS} atual={atual} hrefDaParada={(p) => `/trafego/nova/74/${p}`} />
    </MemoryRouter>,
  );
}

describe('MapaDeParadas', () => {
  it('não emite nenhum <button disabled> — nem um', () => {
    const { container } = montar();
    expect(container.querySelectorAll('button').length).toBe(0);
    expect(container.querySelectorAll('[disabled]').length).toBe(0);
  });

  it('a parada bloqueada é um span com a causa ligada por aria-describedby', () => {
    const { container } = montar();
    // A busca é pelo RÓTULO e não pelo primeiro `aria-disabled` do documento:
    // "não se aplica" também é inalcançável e aparece antes no DOM. Confundir
    // os dois é o mesmo achatamento que o tipo proíbe
    // (`src/types/trafego.ts:247-250`).
    const bloqueada = Array.from(
      container.querySelectorAll('[aria-disabled="true"][aria-describedby]'),
    ).find((el) => el.textContent?.includes('Revisão'));
    expect(bloqueada, 'a parada bloqueada sumiu do DOM').toBeTruthy();
    expect(bloqueada?.tagName).toBe('SPAN');
    expect(bloqueada?.textContent).toContain('Revisão');

    const id = bloqueada?.getAttribute('aria-describedby') ?? '';
    // A causa precisa EXISTIR no documento: um `aria-describedby` apontando
    // para o vazio é pior que nenhum, porque parece resolvido.
    expect(document.getElementById(id)?.textContent).toBe(CAUSA);
  });

  it('a parada bloqueada não vira link', () => {
    const { container } = montar();
    const hrefs = Array.from(container.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(hrefs).not.toContain('/trafego/nova/74/revisao');
    expect(hrefs).not.toContain('/trafego/nova/74/anuncio');
    expect(hrefs).toContain('/trafego/nova/74/destino');
  });

  it('não conta a parada que não se aplica no progresso', () => {
    const { container } = montar('termos');
    // Cinco paradas se aplicam; Termos é a terceira delas.
    expect(container.textContent).toContain('parada 3 de 5');
    expect(container.textContent, 'a parada que não se aplica entrou no denominador')
      .not.toContain('de 6');
  });

  it('a parada que não se aplica também não é alcançável, e diz por quê', () => {
    const { container } = montar();
    const naoSeAplica = Array.from(container.querySelectorAll('[aria-disabled="true"]')).find(
      (el) => el.textContent?.includes('Anúncio'),
    );
    expect(naoSeAplica?.tagName).toBe('SPAN');
    const id = naoSeAplica?.getAttribute('aria-describedby') ?? '';
    expect(document.getElementById(id)?.textContent).toContain('não se aplica');
  });

  it('a causa de uma parada indeterminada não some por ela ser alcançável', () => {
    // "não consegui ler" e "falta fazer" são fatos diferentes
    // (`src/types/trafego.ts:247-250`). Uma parada indeterminada continua
    // clicável, então a causa dela não passa pelo `aria-describedby` do ramo
    // bloqueado — e sem esta rota ela desapareceria da tela inteira.
    const naoSeSabe = 'a auditoria do destino não respondeu na janela de 24h';
    const paradas: ParadaProjetada[] = PARADAS.map((p) =>
      p.parada === 'economia'
        ? { ...p, estado: 'indeterminada' as const, causa: naoSeSabe }
        : p,
    );
    const { container } = render(
      <MemoryRouter>
        <MapaDeParadas paradas={paradas} atual="termos" hrefDaParada={(x) => `/p/${x}`} />
      </MemoryRouter>,
    );
    const link = Array.from(container.querySelectorAll('a')).find((a) =>
      a.textContent?.includes('Economia'),
    );
    expect(link?.getAttribute('href')).toBe('/p/economia');
    expect(link?.getAttribute('title')).toBe(naoSeSabe);
    expect(link?.textContent).toContain('não se sabe');
    expect(link?.textContent).toContain(naoSeSabe);
  });

  it('a parada atual é o marco de passo, e o marcador é primary — nunca aurora', () => {
    const { container } = montar();
    const atual = container.querySelector('[aria-current="step"]');
    expect(atual?.textContent).toContain('Termos');
    // `design.md:104`: a aurora nunca é status operacional, e um marcador de
    // passo numa navegação de trabalho é operacional.
    expect(container.innerHTML).toContain('bg-primary');
    expect(container.innerHTML).not.toContain('aurora');
  });

  it('é navegação ordenada, não um controle de abas', () => {
    montar();
    const nav = screen.getByRole('navigation', { name: 'paradas do lançamento' });
    expect(nav.querySelector('ol')).toBeTruthy();
    expect(nav.querySelectorAll('[role="tab"]').length).toBe(0);
  });

  it('o estado de cada parada chega a quem ouve, não só a quem vê', () => {
    const { container } = montar();
    const texto = container.textContent ?? '';
    expect(texto).toContain('confirmada');
    expect(texto).toContain('bloqueada');
    expect(texto).toContain('não se aplica');
  });

  it('o marcador anima transform e nunca width', () => {
    const { container } = montar();
    const marcador = container.querySelector('.transition-transform');
    expect(marcador, 'o marcador da parada atual não foi medido').toBeTruthy();
    const classe = marcador?.className ?? '';
    // `design.md:122` proíbe animar `width`. A largura entra por `style`,
    // fora de qualquer transição.
    expect(classe).not.toContain('transition-all');
    expect(classe).not.toContain('transition-[width');
    expect((marcador as HTMLElement).style.width).toBeTruthy();
  });
});
