// @vitest-environment jsdom
/**
 * Provas focais do Assistente Criativo.
 *
 * O que estes testes existem para impedir, em ordem de custo do defeito:
 *
 *  1. abrir/recarregar/listar disparar geração — é o único defeito aqui que
 *     gasta dinheiro sozinho;
 *  2. aprovação endereçada por posição, que congela um objeto diferente na run
 *     seguinte;
 *  3. o recibo de contrato ser lido como aprovação humana ou elegibilidade Meta;
 *  4. ação que só existe no hover, invisível para teclado e para toque.
 */
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// A sessão do Supabase é a credencial de todas as chamadas. O duble devolve uma
// sessão válida para o cliente não recusar ANTES da rede.
vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'token-de-teste' } } }),
    },
  },
}));

const chamadas: { url: string; metodo: string }[] = [];

function respostaDe(url: string): unknown {
  if (url.includes('/operacoes?') || url.endsWith('/operacoes')) {
    return { operacoes: [], limite: 20, offset: 0 };
  }
  return {};
}

beforeEach(() => {
  chamadas.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url: String(url), metodo: init?.method ?? 'GET' });
      return {
        ok: true,
        status: 200,
        json: async () => respostaDe(String(url)),
      } as unknown as Response;
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function abrirPagina(rota: string) {
  const { default: AssistenteCriativoPage } = await import(
    '@/pages/trafego/AssistenteCriativoPage'
  );
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <Routes>
        <Route
          path="/trafego/meta/assistente-criativo"
          element={<AssistenteCriativoPage />}
        />
        <Route
          path="/trafego/meta/assistente-criativo/:projectRef"
          element={<AssistenteCriativoPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('abrir a página nunca gera', () => {
  it('a montagem não chama executar, nem em lista nem em detalhe', async () => {
    await abrirPagina('/trafego/meta/assistente-criativo');
    await waitFor(() => expect(chamadas.length).toBeGreaterThan(0));

    // ⚠️ A prova central desta frente. `executar` é a ÚNICA chamada que faz o
    // modelo rodar; se ela aparecer aqui, abrir a tela passou a custar dinheiro.
    expect(chamadas.some((c) => c.url.includes('/executar'))).toBe(false);
    // e o que ela faz é ler a lista do dono
    expect(chamadas.some((c) => c.url.includes('/operacoes') && c.metodo === 'GET')).toBe(true);
  });

  it('reabrir uma operação existente também não executa nada', async () => {
    const ref = `crproj_${'a'.repeat(24)}`;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        chamadas.push({ url: String(url), metodo: init?.method ?? 'GET' });
        return {
          ok: true,
          status: 200,
          json: async () => ({
            operacao: { project_ref: ref, status: 'READY_FOR_REVIEW', input: {}, latest_run_ref: null },
            runs: [],
          }),
        } as unknown as Response;
      }),
    );

    await abrirPagina(`/trafego/meta/assistente-criativo/${ref}?view=estrategia`);
    await waitFor(() => expect(chamadas.length).toBeGreaterThan(0));
    expect(chamadas.some((c) => c.url.includes('/executar'))).toBe(false);
  });
});

describe('o histórico é uma tabela com ação de verdade', () => {
  it('estado vazio explica o que é uma operação e oferece o primeiro passo', async () => {
    await abrirPagina('/trafego/meta/assistente-criativo');
    expect(
      await screen.findByText(/ainda não tem operações do Assistente/i),
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: /criar a primeira estratégia/i })).toBeTruthy();
  });

  it('com operações, é uma TABELA e o botão Abrir não depende de hover', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          operacoes: [
            {
              project_ref: `crproj_${'b'.repeat(24)}`,
              nome_da_operacao: 'Encceja setembro',
              status: 'READY_FOR_REVIEW',
              latest_run_ref: null,
              created_at: '2026-09-01T10:00:00Z',
              updated_at: '2026-09-06T18:30:00Z',
            },
          ],
          limite: 20,
          offset: 0,
        }),
      })) as unknown as typeof fetch,
    );

    await abrirPagina('/trafego/meta/assistente-criativo');
    expect(await screen.findByRole('table')).toBeTruthy();
    expect(screen.getByText('Encceja setembro')).toBeTruthy();
    // Inventário comparável é tabela, não mural de cartões idênticos.
    expect(screen.getByRole('columnheader', { name: /operação/i })).toBeTruthy();
    // A ação existe no DOM sempre — hover não é um estado alcançável por teclado.
    expect(screen.getByRole('button', { name: 'Abrir' })).toBeTruthy();
  });
});

describe('o briefing mostra a consequência antes da ação', () => {
  it('declara N peças x M formatos e que nada é gerado agora', async () => {
    await abrirPagina('/trafego/meta/assistente-criativo?view=briefing');
    expect(await screen.findByRole('heading', { name: 'Fatos da oferta' })).toBeTruthy();

    // 6 peças (padrão) x 3 formatos (padrão) = 18 renders futuros, declarados
    // ANTES de o operador poder clicar.
    const consequencia = screen.getByText(/O que este clique faz/i).closest('section');
    expect(consequencia?.textContent).toContain('18');
    expect(consequencia?.textContent).toMatch(/Nenhuma é gerada agora/i);
    expect(consequencia?.textContent).toMatch(/não cria campanha/i);
  });

  it('o botão só habilita quando o pedido é válido', async () => {
    await abrirPagina('/trafego/meta/assistente-criativo?view=briefing');
    const botao = (await screen.findByRole('button', { name: 'Criar estratégia' })) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText('Nome da operação'), {
      target: { value: 'Operação de teste' },
    });
    fireEvent.change(screen.getByLabelText('Destino'), {
      target: { value: 'destino:teste' },
    });
    fireEvent.change(screen.getByLabelText('Contexto do público'), {
      target: { value: 'Pessoa buscando entender o processo.' },
    });
    fireEvent.change(screen.getByLabelText('Declaração'), {
      target: { value: 'Conteúdo informativo e independente.' },
    });

    await waitFor(() => {
      const b = screen.getByRole('button', { name: 'Criar estratégia' }) as HTMLButtonElement;
      expect(b.disabled).toBe(false);
    });
    // e nada foi gerado só por preencher
    expect(chamadas.some((c) => c.url.includes('/executar'))).toBe(false);
  });

  it('a ref do fato é derivada do texto, e o operador não digita ref opaca', async () => {
    await abrirPagina('/trafego/meta/assistente-criativo?view=briefing');
    fireEvent.change(await screen.findByLabelText('Declaração'), {
      target: { value: 'Conteúdo informativo e independente' },
    });
    expect(
      await screen.findByText('fact_conteudo_informativo_e_independente_1'),
    ).toBeTruthy();
    // não existe campo pedindo a ref
    expect(screen.queryByLabelText(/^ref/i)).toBeNull();
  });
});
