// @vitest-environment jsdom
/**
 * U0 do Hub multicanal: histórico, totais, URL, Meta honesta, teclado.
 *
 * Os números 5 e 79 NÃO aparecem neste arquivo como expectativa mágica da UI.
 * A prova manda totais 4 e 12 no contrato e cobra que a tela os repita.
 */
import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LeituraDoInventario } from '@/hooks/useInventario';
import type { FiltrosDoInventario, Inventario, QuadroDeAlertas } from '@/types/trafego';

import HubDeTrafegoPage from '@/pages/trafego/HubDeTrafegoPage';
import {
  campanhaRemovida,
  creditoUp,
  fgts,
  inventarioDeProva,
  maquininha,
  quadroDeAlertasDeProva,
} from '@/components/trafego/inventario/fixtureDeProvas';

const { escolher, chamadas } = vi.hoisted(() => ({
  escolher: {
    fn: (_filtros?: FiltrosDoInventario): LeituraDoInventario => {
      throw new Error('dublê do inventário ainda não configurado');
    },
  },
  chamadas: {
    inventario: [] as Array<boolean | undefined>,
    notificacoes: [] as Array<boolean | undefined>,
    atencao: [] as Array<boolean | undefined>,
  },
}));

function leituraDe(inv: Inventario, extra: Partial<LeituraDoInventario> = {}): LeituraDoInventario {
  return {
    inventario: inv,
    carregando: false,
    atualizando: false,
    falhou: false,
    motivoDaFalha: null,
    temMais: false,
    carregandoMais: false,
    carregarMais: vi.fn(),
    recarregar: vi.fn(),
    ...extra,
  };
}

const operacional = inventarioDeProva({
  frescor: 'recente',
  parcial: false,
  faltou: [],
  contas: [{ ...creditoUp, quantidade: 2, campanhas: [maquininha, fgts] }],
  totais: { contas: 1, operacionais: 4, historicas: 12, geral: 16, atencao: 2 },
});

const removido = inventarioDeProva({
  frescor: 'recente',
  parcial: false,
  faltou: [],
  contas: [{ ...creditoUp, quantidade: 1, campanhas: [campanhaRemovida] }],
  totais: { contas: 1, operacionais: 0, historicas: 12, geral: 12, atencao: 0 },
});

const universo = inventarioDeProva({
  totais: { contas: 3, operacionais: 4, historicas: 12, geral: 16, atencao: 2 },
});

vi.mock('@/hooks/useInventario', () => ({
  useInventario: (
    filtros?: FiltrosDoInventario,
    opcoes?: { habilitado?: boolean },
  ) => {
    chamadas.inventario.push(opcoes?.habilitado);
    return escolher.fn(filtros);
  },
  usePedirLeituraDaConta: () => ({ pedir: vi.fn(), contaEmLeitura: null, recados: {} }),
}));

vi.mock('@/hooks/useNotificacoes', () => ({
  useNotificacoes: (opcoes?: { habilitado?: boolean }) => {
    chamadas.notificacoes.push(opcoes?.habilitado);
    return {
      data: quadroDeAlertasDeProva() as QuadroDeAlertas,
      isLoading: false,
      isError: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    };
  },
  INTERVALO_NOTIFICACOES_MS: 600000,
  CHAVE_NOTIFICACOES: ['notificacoes', 'trafego'],
}));

vi.mock('@/components/trafego/atencao/useAtencao', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/trafego/atencao/useAtencao')>()),
  useContadorDeAtencao: (habilitado?: boolean) => {
    chamadas.atencao.push(habilitado);
    return habilitado === false ? null : 2;
  },
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const Endereco: React.FC = () => {
  const loc = useLocation();
  return <div data-testid="endereco">{loc.search}</div>;
};

function montar(endereco = '/trafego') {
  return render(
    <MemoryRouter initialEntries={[endereco]}>
      <Endereco />
      <HubDeTrafegoPage oportunidades={<div>quadro de oportunidades</div>} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  chamadas.inventario.length = 0;
  chamadas.notificacoes.length = 0;
  chamadas.atencao.length = 0;
  escolher.fn = (filtros?: FiltrosDoInventario) => {
    const estados = filtros?.estado_externo ?? [];
    if (filtros?.incluir_historico || (estados.length === 1 && estados[0] === 'REMOVED')) {
      return leituraDe(removido);
    }
    return leituraDe(operacional, { temMais: true });
  };
  Object.defineProperty(window, 'innerWidth', { value: 1440, writable: true, configurable: true });
});

afterEach(cleanup);

describe('1–4 · campanhas operacionais e histórico', () => {
  it('no padrão o histórico não compete com o que está no ar', () => {
    montar();
    expect(screen.getByText('BR - Maquininha de Cartão')).toBeTruthy();
    expect(screen.queryByText('BR - Maquininha de Cartão (primeira versão)')).toBeNull();
    expect(screen.queryByRole('region', { name: 'histórico removido' })).toBeNull();
  });

  it('o histórico é uma ação explícita, com a quantidade do contrato', () => {
    montar();
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar histórico removido: 12' }));
    expect(screen.getByRole('region', { name: 'histórico removido' })).toBeTruthy();
    expect(screen.getByText('BR - Maquininha de Cartão (primeira versão)')).toBeTruthy();
    expect(screen.getByTestId('endereco').textContent).toMatch(/historico=1/);
  });

  it('a contagem operacional vem da leitura, nunca de um 5 ou 79 escrito', () => {
    montar();
    expect(document.body.textContent ?? '').toMatch(/4 campanhas operacionais/);
    expect(screen.getByRole('button', { name: 'Mostrar histórico removido: 12' })).toBeTruthy();
    const aba = screen.getByRole('tab', { name: /campanhas/ });
    expect(within(aba).getByText('4')).toBeTruthy();
  });

  it('Carregar mais aparece quando a leitura diz que há continuação', () => {
    montar();
    expect(screen.getByRole('button', { name: 'Carregar mais' })).toBeTruthy();
  });
});

describe('8–9 · seletor e filtros persistem na URL', () => {
  it('Google/Meta persiste na URL', () => {
    montar('/trafego?canal=SEARCH');
    fireEvent.click(screen.getByRole('button', { name: 'Meta Ads' }));
    expect(screen.getByTestId('endereco').textContent).toMatch(/rede=meta/);
    expect(screen.getByTestId('endereco').textContent).not.toMatch(/canal=/);
  });

  it('canal e busca do Google persistem', () => {
    montar('/trafego?canal=SEARCH&busca=FGTS');
    expect(screen.getByTestId('endereco').textContent).toMatch(/canal=SEARCH/);
    expect(screen.getByTestId('endereco').textContent).toMatch(/busca=FGTS/);
    expect(screen.getByRole('button', { name: 'Search' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('novas URLs emitem canal=PERFORMANCE_MAX; PMAX legado é normalizado', () => {
    montar('/trafego?canal=PMAX');
    expect(screen.getByRole('button', { name: 'Performance Max' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    fireEvent.click(screen.getByRole('button', { name: 'Performance Max' }));
    expect(screen.getByTestId('endereco').textContent).toMatch(/canal=PERFORMANCE_MAX/);
    expect(screen.getByTestId('endereco').textContent).not.toMatch(/canal=PMAX/);
  });
});

describe('11 · Meta não finge integração', () => {
  it('escolhe Meta e declara que a leitura ainda não existe', () => {
    montar('/trafego?rede=meta');
    expect(screen.getByRole('heading', { name: 'Fundação instalada · conexão real pendente' })).toBeTruthy();
    expect(screen.getByText(/não inventa campanhas ou desempenho/)).toBeTruthy();
    expect(screen.queryByText(/ROAS/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Carregar mais' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Atualizar dados' })).toBeNull();
    expect(chamadas.inventario.length).toBeGreaterThan(0);
    expect(chamadas.inventario.every((habilitado) => habilitado === false)).toBe(true);
    expect(chamadas.notificacoes).toEqual([false]);
    expect(chamadas.atencao).toEqual([false]);
  });

  it('aceita plataforma=meta sem projetar a situação do Google', () => {
    montar('/trafego?plataforma=meta');
    expect(screen.getByRole('heading', { name: 'Fundação instalada · conexão real pendente' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Atualizar dados' })).toBeNull();
    expect(chamadas.inventario.every((habilitado) => habilitado === false)).toBe(true);
    expect(screen.getByTestId('endereco').textContent).toContain('rede=meta');
    expect(screen.getByTestId('endereco').textContent).not.toContain('plataforma=');
  });
});

describe('12–15 · recorte, tema, teclado, jargão', () => {
  it('no telefone a lista continua existindo, sem grade de cartões', () => {
    Object.defineProperty(window, 'innerWidth', { value: 390, writable: true, configurable: true });
    const { container } = montar();
    expect(screen.getByText('BR - Maquininha de Cartão')).toBeTruthy();
    expect(container.querySelector('.overflow-x-clip')).toBeTruthy();
  });

  it('no tema escuro as tags continuam sendo palavra', () => {
    const { container } = render(
      <div className="dark bg-background text-foreground">
        <MemoryRouter initialEntries={['/trafego']}>
          <HubDeTrafegoPage oportunidades={<div>quadro</div>} />
        </MemoryRouter>
      </div>,
    );
    expect(screen.getAllByText('Google Ads').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Google Ads').length).toBeGreaterThan(0);
  });

  it('o seletor de rede é alcançável por teclado e declara o pressionado', () => {
    montar();
    const google = screen.getByRole('button', { name: 'Google Ads' });
    const meta = screen.getByRole('button', { name: 'Meta Ads' });
    expect(google.getAttribute('aria-pressed')).toBe('true');
    google.focus();
    expect(document.activeElement).toBe(google);
    fireEvent.click(meta);
    expect(meta.getAttribute('aria-pressed')).toBe('true');
  });

  it('nenhuma palavra de máquina chega à tela operacional', () => {
    const { container } = montar();
    const texto = (container.textContent ?? '').toLowerCase();
    for (const proibido of ['gaql', 'postgrest', 'snapshot', 'payload', 'cursor']) {
      expect(texto, proibido).not.toContain(proibido);
    }
  });
});
