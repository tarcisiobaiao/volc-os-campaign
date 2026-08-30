// @vitest-environment jsdom
/**
 * A prosa do motor: fatiada, sanitizada e renderizada.
 *
 * Duas coisas são testadas aqui, e as duas já quebraram uma vez:
 *
 * **O script não pode executar.** O texto é escrito por um modelo e traz blocos
 * `wp:html` com script — é assim que o widget funciona. Rodá-lo aqui seria
 * executar código de IA na nossa origem, com a sessão do operador.
 *
 * **O `style` não pode ser removido.** Foi o que a primeira versão fez, e o
 * widget da página 3 desabou numa lista de texto solto que parecia página
 * quebrada. Blocos `wp:html` não podem usar CSS externo: todo o visual deles
 * vive em atributo inline.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { LpEmSlots, ProsaDaPagina, fatiar } from '../ProsaDaPagina';

afterEach(cleanup);

const WIDGET_REAL = `<!-- wp:paragraph --><p>Conseguir a aprovação de um cartão.</p><!-- /wp:paragraph -->
<!-- wp:html -->
<section class="wg-container" style="padding: 24px; border: 1px solid #e2e8f0; background-color: #ffffff;">
  <h3 style="font-size: 1.25rem; font-weight: 700;">Roteador de Elegibilidade</h3>
  <select><option>Não sei meu score</option></select>
  <script>window.__RODOU__ = true;</script>
</section>
<!-- /wp:html -->
<!-- wp:paragraph --><p>Depois do widget.</p><!-- /wp:paragraph -->`;

describe('fatiar separa o widget da prosa', () => {
  it('reconhece os três pedaços na ordem', () => {
    const p = fatiar(WIDGET_REAL);
    expect(p.map((x) => x.tipo)).toEqual(['prosa', 'widget', 'prosa']);
    expect(p[0].html).toContain('Conseguir a aprovação');
    expect(p[1].html).toContain('Roteador de Elegibilidade');
    expect(p[2].html).toContain('Depois do widget');
  });

  it('conta os scripts do widget antes de removê-los', () => {
    expect(fatiar(WIDGET_REAL)[1].scripts).toBe(1);
  });

  it('fatia ANTES de tirar os comentários do WordPress', () => {
    // São os comentários que marcam onde o widget começa e acaba. Removê-los
    // primeiro apagaria a fronteira e o widget viraria prosa.
    const p = fatiar(WIDGET_REAL);
    expect(p).toHaveLength(3);
    for (const x of p) expect(x.html).not.toContain('wp:');
  });

  it('texto sem widget continua sendo um pedaço só', () => {
    const p = fatiar('<!-- wp:paragraph --><p>Só prosa.</p><!-- /wp:paragraph -->');
    expect(p).toHaveLength(1);
    expect(p[0].tipo).toBe('prosa');
  });

  it('vários widgets viram vários pedaços', () => {
    const dois = WIDGET_REAL + WIDGET_REAL;
    expect(fatiar(dois).filter((x) => x.tipo === 'widget')).toHaveLength(2);
  });
});

describe('o que roda e o que não roda', () => {
  it('o script do widget não executa', () => {
    const { container } = render(<ProsaDaPagina bruto={WIDGET_REAL} />);
    expect(container.ownerDocument.querySelectorAll('script')).toHaveLength(0);
    expect((window as unknown as Record<string, unknown>).__RODOU__).toBeUndefined();
  });

  it('⚠️ o `style` inline SOBREVIVE — sem ele o widget desaba', () => {
    // O defeito que este teste tranca: `style` no FORBID_ATTR fazia o widget
    // perder fundo, borda, espaçamento e tipografia de uma vez, e ele
    // renderizava como uma lista de texto solto no meio do artigo.
    const { container } = render(<ProsaDaPagina bruto={WIDGET_REAL} />);
    const secao = container.ownerDocument.querySelector('.wg-container') as HTMLElement | null;
    expect(secao).not.toBeNull();
    expect(secao!.getAttribute('style')).toContain('padding');
    expect(secao!.getAttribute('style')).toContain('background-color');
  });

  it('CSS perigoso é varrido — e essa varredura é NOSSA, não do DOMPurify', () => {
    // Medido em Chromium de verdade: com `style` permitido, o DOMPurify deixa
    // passar `url(javascript:)`, `expression()`, `-moz-binding` e `behavior`.
    // Ele filtra nome de atributo e URI de href/src; CSS não está no escopo.
    for (const veneno of [
      '<p style="background:url(javascript:alert(1))">x</p>',
      '<p style="width:expression(alert(1))">x</p>',
      '<p style="-moz-binding:url(http://mau/x.xml)">x</p>',
      '<p style="behavior:url(#default#time2)">x</p>',
    ]) {
      cleanup();
      const { container } = render(<ProsaDaPagina bruto={veneno} />);
      const html = container.ownerDocument.body.innerHTML;
      for (const marca of ['javascript:', 'expression(', '-moz-binding', 'behavior:']) {
        expect(html, veneno).not.toContain(marca);
      }
    }
  });

  it('a varredura tira só a declaração suspeita, não o estilo inteiro', () => {
    // Derrubar o `style` todo apagaria o visual do widget — o defeito exato que
    // manter o `style` veio consertar.
    const { container } = render(<ProsaDaPagina bruto={
      '<p style="padding:24px;background:url(javascript:alert(1));color:#111">x</p>'} />);
    const p = container.ownerDocument.querySelector('p') as HTMLElement;
    const estilo = p.getAttribute('style') || '';
    expect(estilo).toContain('padding');
    expect(estilo).toContain('color');
    expect(estilo).not.toContain('javascript:');
  });

  it('mata manipulador em atributo', () => {
    const { container } = render(<ProsaDaPagina bruto={'<img src=x onerror="window.__Y__=1">'} />);
    expect(container.ownerDocument.body.innerHTML).not.toContain('onerror');
    expect((window as unknown as Record<string, unknown>).__Y__).toBeUndefined();
  });

  it('mata iframe e form — exfiltração não precisa de script', () => {
    const { container } = render(<ProsaDaPagina bruto={
      '<iframe src="https://mau"></iframe><form action="https://mau"><input name="s"></form>'} />);
    const d = container.ownerDocument;
    expect(d.querySelectorAll('iframe')).toHaveLength(0);
    expect(d.querySelectorAll('form')).toHaveLength(0);
  });
});

describe('o widget aparece emoldurado, não solto na prosa', () => {
  it('ganha rótulo e o aviso de comportamento desligado', () => {
    render(<ProsaDaPagina bruto={WIDGET_REAL} />);
    expect(screen.getByText('widget interativo')).toBeTruthy();
    expect(screen.getByText(/comportamento desligado/i)).toBeTruthy();
  });

  it('widget sem script não recebe o aviso', () => {
    const semScript = '<!-- wp:html --><div style="padding:8px">estático</div><!-- /wp:html -->';
    render(<ProsaDaPagina bruto={semScript} />);
    expect(screen.getByText('widget interativo')).toBeTruthy();
    expect(screen.queryByText(/comportamento desligado/i)).toBeNull();
  });
});

describe('a LP é JSON de slots', () => {
  it('mostra os slots nomeados, com o underscore virando espaço', () => {
    render(<LpEmSlots bruto={JSON.stringify({ hero_title: 'Cartão', faq: ['Pergunta?'] })} />);
    expect(screen.getByText('hero title')).toBeTruthy();
    expect(screen.getByText('Cartão')).toBeTruthy();
  });

  it('JSON quebrado cai para o texto cru em vez de sumir', () => {
    render(<LpEmSlots bruto={'{isso não é json'} />);
    expect(screen.getByText(/isso não é json/)).toBeTruthy();
  });
});
