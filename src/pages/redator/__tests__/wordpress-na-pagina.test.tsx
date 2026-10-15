// @vitest-environment jsdom
/**
 * O painel "no wordpress" da página do funil — inclusive quando NÃO há post.
 *
 * ⚠️ Medido em 19/08/2026, run 9. O painel inteiro vivia dentro de
 * `{p.publicada && …}`: uma página não publicada não dizia NADA sobre
 * WordPress — nem link, nem número de post, nem uma palavra explicando a
 * ausência.
 *
 * Isso passa despercebido enquanto tudo publica. Depois de recuperar p2, p3 e
 * p4 — três páginas escritas, aprovadas nos portões e paradas — o operador
 * abriu a tela e não tinha como saber se o trabalho tinha dado certo: a página
 * pronta era visualmente idêntica à que nunca existiu.
 *
 * Silêncio não é neutralidade. Dizer "não foi enviada ao WordPress" não é
 * inventar estado; é relatar o que existe.
 */
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { PaginaEscrita } from '@/types/redatorPaginas';

const paginasDoRun = vi.hoisted(() => vi.fn());
const publicarPagina = vi.hoisted(() => vi.fn());

vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: {
    paginasDoRun,
    publicarPagina,
    urlDoArtefato: (_r: number, n: string) => `/artefato/${n}`,
    tirarProvaVisual: vi.fn(),
  },
}));
vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import PaginaDoFunilPage from '../PaginaDoFunilPage';

afterEach(() => { cleanup(); vi.clearAllMocks(); });

function pagina(over: Partial<PaginaEscrita> = {}): PaginaEscrita {
  return {
    page_number: 3, papel: 'SOLUTION', slug: 'como-ativar-saque-aniversario-p1',
    h1: 'Como ativar o saque-aniversário', engajamento: 'sequencial', objetivo: '',
    gancho: '', proxima: '', estrutura: [], palavras_alvo: [], rotas: [],
    seo: { titulo: '', descricao: '', foco: '', slug: '' },
    links_oficiais: [], prints: [],
    texto: { formato: 'gutenberg', conteudo: '<p>corpo</p>', palavras: 801 },
    publicada: null, bloqueada: false, custo_usd: 0.67, issues: [],
    imagem: null, meta: null, anuncios: null, arquivos: [],
    ...over,
  } as PaginaEscrita;
}

const montar = async (p: PaginaEscrita) => {
  paginasDoRun.mockResolvedValue({ paginas: [p], sem_artefatos: false });
  const r = render(
    <MemoryRouter initialEntries={['/redator/funil/9/p/3']}>
      <Routes>
        <Route path="/redator/funil/:runId/p/:n" element={<PaginaDoFunilPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() => expect(paginasDoRun).toHaveBeenCalled());
  return r;
};

describe('painel "no wordpress" da página do funil', () => {
  it('página pronta e não publicada diz isso, em vez de calar', async () => {
    const { container } = await montar(pagina());

    await waitFor(() => expect(
      screen.getByRole('heading', { name: /no wordpress/i })).toBeTruthy());
    expect(container.textContent).toContain('ainda não foi enviada ao WordPress');
    // e não oferece link nenhum — não há post para abrir nem para editar
    expect(container.querySelector('a[href*="wp-admin"]')).toBeNull();
  });

  it('página barrada explica que nem chegou a ser enviada', async () => {
    const { container } = await montar(pagina({
      bloqueada: true,
      issues: [{ etapa: 'content_gate', code: 'required_widget_missing', message: 'x' }],
    }));

    await waitFor(() => expect(
      screen.getByRole('heading', { name: /no wordpress/i })).toBeTruthy());
    expect(container.textContent).toContain('barrada por um portão');
  });

  it('rascunho leva ao editor do WordPress', async () => {
    const { container } = await montar(pagina({
      publicada: {
        post_id: 2198, slug: 'x',
        url_wp: 'https://creditoup.com.br/?post_type=rec&p=2198', status_wp: 'draft',
      },
    }));

    await waitFor(() => expect(screen.getByText('editar no WordPress')).toBeTruthy());
    const editar = container.querySelector('a[href*="wp-admin"]') as HTMLAnchorElement;
    expect(editar.getAttribute('href'))
      .toBe('https://creditoup.com.br/wp-admin/post.php?post=2198&action=edit');
    expect(container.textContent).toContain('post #2198');
  });

  it('publicada oferece o permalink e o editor', async () => {
    const { container } = await montar(pagina({
      publicada: {
        post_id: 2191, slug: 'fgts-saque-aniversario',
        url_wp: 'https://creditoup.com.br/r/fgts-saque-aniversario/', status_wp: 'publish',
      },
    }));

    await waitFor(() => expect(screen.getByText('editar no WordPress')).toBeTruthy());
    const hrefs = Array.from(container.querySelectorAll('a[target="_blank"]'))
      .map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('https://creditoup.com.br/r/fgts-saque-aniversario/');
    expect(hrefs).toContain('https://creditoup.com.br/wp-admin/post.php?post=2191&action=edit');
  });
});


// ── O GATILHO QUE FECHA O FUNIL ───────────────────────────────────────────
//
// ⚠️ O motor publicava tudo ou nada. Uma página consertada depois de cair num
// portão não tinha caminho de volta ao WordPress — só terminal. Na run 9, três
// páginas prontas ficaram órfãs, e funil pela metade não é meio funil: os links
// internos apontam para páginas que não existem.

describe('enviar ao WordPress', () => {
  // A confirmação deixou de ser `window.confirm` e virou o diálogo do
  // produto. O contrato é o mesmo: sem o segundo clique, nada sobe.
  let resposta = true;
  const confirmar = (r: boolean) => { resposta = r; };
  const clicarEnviar = async () => {
    screen.getByRole('button', { name: /enviar ao WordPress/i }).click();
    const dialogo = await screen.findByRole('alertdialog');
    const alvo = resposta ? /enviar como rascunho/i : /manter só no VOLC/i;
    within(dialogo).getByRole('button', { name: alvo }).click();
  };

  it('publica a página e relê o funil para mostrar os links', async () => {
    confirmar(true);
    publicarPagina.mockResolvedValue({
      ok: true,
      publicada: { post_id: 2201, slug: 'x', url_wp: 'https://c.com/?p=2201',
                   status_wp: 'draft' },
    });
    const { container } = await montar(pagina());

    await clicarEnviar();

    await waitFor(() => expect(publicarPagina).toHaveBeenCalledWith(9, 3));
    // relê: é do servidor que vem `publicada`, e sem reler o painel continuaria
    // dizendo que a página não foi enviada
    await waitFor(() => expect(paginasDoRun).toHaveBeenCalledTimes(2));
    expect(container.textContent).not.toContain('Falhei');
  });

  it('desistir da confirmação NÃO publica nada', async () => {
    confirmar(false);
    await montar(pagina());

    await clicarEnviar();

    await new Promise((r) => setTimeout(r, 50));
    expect(publicarPagina).not.toHaveBeenCalled();
  });

  it('página barrada não ganha botão — enviar contornaria o portão', async () => {
    await montar(pagina({
      bloqueada: true,
      issues: [{ etapa: 'content_gate', code: 'x', message: 'y' }],
    }));

    expect(screen.queryByRole('button', { name: /enviar ao WordPress/i })).toBeNull();
  });

  it('página já publicada não ganha botão — seria um segundo post', async () => {
    await montar(pagina({
      publicada: { post_id: 2198, slug: 'x',
                   url_wp: 'https://c.com/?p=2198', status_wp: 'draft' },
    }));

    expect(screen.queryByRole('button', { name: /enviar ao WordPress/i })).toBeNull();
  });

  it('o motor rodar sem publicar é DITO, não engolido', async () => {
    // O laço do motor engole a exceção da página e sai com código 0. Foi assim
    // que um 401 do WordPress passou despercebido por três tentativas.
    confirmar(true);
    publicarPagina.mockResolvedValue({ ok: false, erro: '401 Unauthorized no WordPress' });
    const { container } = await montar(pagina());

    await clicarEnviar();

    await waitFor(() => expect(container.textContent).toContain('401 Unauthorized'));
    // e não finge que deu certo
    expect(paginasDoRun).toHaveBeenCalledTimes(1);
  });

  it('recusa do servidor aparece na tela', async () => {
    confirmar(true);
    publicarPagina.mockRejectedValue(new Error('A página 3 já está no WordPress (post #2198).'));
    const { container } = await montar(pagina());

    await clicarEnviar();

    await waitFor(() => expect(container.textContent).toContain('já está no WordPress'));
  });
});


// ── NAVEGAR ENTRE PÁGINAS NÃO PODE MUDAR A ORDEM DOS HOOKS ─────────────────
//
// ⚠️ Revisão R-nuvem-20261015-d2: o `useState` do diálogo de envio ficou
// depois do `return` da página bloqueada. Ir de uma página desbloqueada para
// uma bloqueada renderizava menos hooks que antes, e o React derrubava a tela.

describe('navegar de página desbloqueada para bloqueada', () => {
  it('mantém a tela de pé e explica o bloqueio', async () => {
    const livre = pagina({ page_number: 3 });
    const barrada = pagina({
      page_number: 4, slug: 'p4', h1: 'Página barrada', bloqueada: true,
      issues: [{ etapa: 'content_gate', code: 'x', message: 'y' }],
    });
    paginasDoRun.mockResolvedValue({ paginas: [livre, barrada], sem_artefatos: false });

    let ir: (para: string) => void = () => undefined;
    const Navegador = () => { ir = useNavigate(); return null; };
    const erroDoConsole = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { container } = render(
      <MemoryRouter initialEntries={['/redator/funil/9/p/3']}>
        <Navegador />
        <Routes>
          <Route path="/redator/funil/:runId/p/:n" element={<PaginaDoFunilPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(
      screen.getByRole('button', { name: /enviar ao WordPress/i })).toBeTruthy());

    await act(async () => { ir('/redator/funil/9/p/4'); });

    await waitFor(() => expect(container.textContent).toContain('barrada por um portão'));
    expect(screen.queryByRole('button', { name: /enviar ao WordPress/i })).toBeNull();
    const reclamouDeHook = erroDoConsole.mock.calls.some((c) => String(c[0]).includes('hooks'));
    erroDoConsole.mockRestore();
    expect(reclamouDeHook).toBe(false);
  });
});
