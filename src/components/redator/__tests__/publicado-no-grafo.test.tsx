// @vitest-environment jsdom
/**
 * O que está NO AR — e o que NÃO está — visível no grafo do funil.
 *
 * ⚠️ O teste do aninhamento não é zelo: o cartão inteiro é um `<Link>`, e as
 * marcas do WordPress precisam levar para fora. Âncora dentro de âncora é HTML
 * inválido — o navegador desfaz o aninhamento silenciosamente e o clique passa
 * a cair no lugar errado. Isso não aparece no `tsc`, não aparece no build, e só
 * aparece clicando.
 *
 * ## Duas decisões deste arquivo mudaram em 19/08/2026
 *
 * 1. **Rascunho passou a ter link de edição.** A regra antiga — "rascunho não
 *    oferece link externo" — protegia contra divulgar um endereço provisório
 *    (`?post_type=r&p=2198`) que troca ao publicar. Isso continua valendo para
 *    a URL PÚBLICA. Mas o link de edição aponta para o painel do WordPress, não
 *    para o endereço público, e é justamente no rascunho que ele mais serve: é
 *    lá que se confere se o run deu certo.
 *
 * 2. **Página não publicada passou a dizer que não foi publicada.** A regra
 *    antiga chamava o silêncio de "não inventa estado nenhum". A intenção era
 *    boa; o efeito, não. Num funil recuperado, "publicada", "pronta e parada" e
 *    "barrada" ficavam visualmente idênticas, e não dava para saber se o
 *    trabalho tinha dado certo.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import type { PaginaEscrita } from '@/types/redatorPaginas';

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: { urlDoArtefato: (_r: number, n: string) => `/artefato/${n}` },
}));

import { GrafoDoFunil } from '../GrafoDoFunil';

function pagina(over: Partial<PaginaEscrita> = {}): PaginaEscrita {
  return {
    page_number: 1, papel: 'LP', slug: 'maquininha-de-cartao-menor-taxa',
    h1: 'Maquininha de cartão com a menor taxa', engajamento: '', objetivo: '',
    gancho: '', proxima: '', estrutura: [], palavras_alvo: [], rotas: [],
    seo: { titulo: '', descricao: '', foco: '', slug: '' },
    links_oficiais: [], prints: [],
    texto: { formato: 'gutenberg', conteudo: '', palavras: 900 },
    publicada: null, bloqueada: false, custo_usd: 0.81, issues: [],
    imagem: null, meta: null, anuncios: null, arquivos: [],
    ...over,
  } as PaginaEscrita;
}

const NO_AR = {
  post_id: 2163, slug: 'maquininha-de-cartao-menor-taxa',
  url_wp: 'https://creditoup.com.br/r/maquininha-de-cartao-menor-taxa/',
  status_wp: 'publish',
};
const RASCUNHO = {
  post_id: 2198, slug: 'como-cancelar-saque-aniversario-p3',
  url_wp: 'https://creditoup.com.br/?post_type=rec&p=2198',
  status_wp: 'draft',
};

const renderizar = (paginas: PaginaEscrita[]) =>
  render(<MemoryRouter><GrafoDoFunil paginas={paginas} runId={7} /></MemoryRouter>);

const hrefs = (c: HTMLElement) =>
  Array.from(c.querySelectorAll('a[target="_blank"]')).map((a) => a.getAttribute('href'));

afterEach(cleanup);

describe('GrafoDoFunil · o estado de publicação de cada página', () => {
  it('no ar: diz "no ar", abre o permalink e leva ao editor', () => {
    const { container } = renderizar([pagina({ publicada: NO_AR })]);

    expect(screen.getByText('no ar')).toBeTruthy();
    expect(hrefs(container)).toEqual([
      'https://creditoup.com.br/r/maquininha-de-cartao-menor-taxa/',
      'https://creditoup.com.br/wp-admin/post.php?post=2163&action=edit',
    ]);
  });

  it('rascunho: leva ao editor, e NÃO oferece o endereço provisório', () => {
    const { container } = renderizar([pagina({ publicada: RASCUNHO })]);

    expect(screen.getByText('rascunho no WP')).toBeTruthy();
    expect(screen.getByText('editar')).toBeTruthy();
    // A rigidez que PERMANECE: `?post_type=rec&p=2198` troca no momento da
    // publicação, e é por igualdade de string exata que a receita é atribuída
    // à campanha. Oferecê-lo convidaria a divulgar um endereço que vai mudar.
    expect(hrefs(container))
      .toEqual(['https://creditoup.com.br/wp-admin/post.php?post=2198&action=edit']);
    expect(screen.queryByText('ver')).toBeNull();
  });

  it('não publicada: diz isso por escrito, e não oferece link nenhum', () => {
    const { container } = renderizar([pagina()]);

    expect(screen.getByText('não publicada')).toBeTruthy();
    expect(hrefs(container)).toEqual([]);
    expect(screen.queryByText('no ar')).toBeNull();
    expect(screen.queryByText('rascunho no WP')).toBeNull();
  });

  it('barrada: o estado da página vence o de publicação', () => {
    renderizar([pagina({
      bloqueada: true,
      issues: [{ etapa: 'content_gate', code: 'required_widget_missing', message: 'x' }],
    })]);

    expect(screen.getByText('barrada')).toBeTruthy();
    expect(screen.queryByText('não publicada')).toBeNull();
  });

  it('toda página tem um estado — nenhuma fica muda', () => {
    // O caso literal da run 9 depois da recuperação: duas no ar, uma em
    // rascunho, duas prontas e paradas. Era aqui que o operador não conseguia
    // distinguir uma da outra.
    renderizar([
      pagina({ page_number: 1, publicada: NO_AR }),
      pagina({ page_number: 2, papel: 'PRESELL', slug: 'p2' }),
      pagina({ page_number: 3, papel: 'SOLUTION', slug: 'p3' }),
      pagina({ page_number: 4, papel: 'SOLUTION', slug: 'p4' }),
      pagina({ page_number: 5, papel: 'SOLUTION', slug: 'p5', publicada: RASCUNHO }),
    ]);

    expect(screen.getAllByText('não publicada').length).toBe(3);
    expect(screen.getAllByText('no ar').length).toBe(1);
    expect(screen.getAllByText('rascunho no WP').length).toBe(1);
  });

  it('nenhuma âncora dentro de âncora', () => {
    const { container } = renderizar([
      pagina({ publicada: NO_AR }),
      pagina({ page_number: 2, papel: 'PRESELL', slug: 'p2', publicada: RASCUNHO }),
      pagina({ page_number: 3, papel: 'SOLUTION', slug: 'p3' }),
    ]);
    expect(container.querySelectorAll('a a').length).toBe(0);
  });

  it('sem post_id não há link de edição inventado', () => {
    // `linkDeEdicao` deriva a origem de `url_wp`. Sem URL analisável não há
    // para onde mandar — e link quebrado para o admin é pior que link nenhum:
    // leva o operador a um erro do WordPress sem ele saber de quem é a culpa.
    const { container } = renderizar([pagina({
      publicada: { post_id: 0, slug: 'x', url_wp: '', status_wp: 'draft' },
    })]);
    expect(hrefs(container)).toEqual([]);
  });
});
