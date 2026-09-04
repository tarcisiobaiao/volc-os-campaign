// @vitest-environment jsdom
/**
 * Provas do Hub: as quatro abas, o contador no rótulo, e a aba que abre primeiro.
 *
 * A aba padrão é decisão de produto, não de implementação: abrir em
 * Oportunidades é o que produz o convite ao segundo lançamento do mesmo termo.
 * Por isso ela é provada aqui e não deixada para o acaso da ordem do JSX.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LeituraDoInventario } from '@/hooks/useInventario';
import type { QuadroDeAlertas } from '@/types/trafego';

import HubDeTrafegoPage from '@/pages/trafego/HubDeTrafegoPage';
import {
  inventarioDeProva,
  inventarioSaudavel,
  quadroDeAlertasDeProva,
} from '@/components/trafego/inventario/fixtureDeProvas';

// ── dublês ──────────────────────────────────────────────────────────────────

const leituraBase: LeituraDoInventario = {
  inventario: inventarioDeProva(),
  carregando: false,
  atualizando: false,
  falhou: false,
  motivoDaFalha: null,
  temMais: false,
  carregandoMais: false,
  carregarMais: vi.fn(),
  recarregar: vi.fn(),
};

let leitura: LeituraDoInventario = leituraBase;

interface DubleDeNotificacoes {
  data: QuadroDeAlertas | null;
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => void;
}

let notificacoes: DubleDeNotificacoes = {
  data: quadroDeAlertasDeProva(),
  isLoading: false,
  isError: false,
  isFetching: false,
  error: null,
  refetch: vi.fn(),
};

vi.mock('@/hooks/useInventario', () => ({
  useInventario: () => leitura,
  usePedirLeituraDaConta: () => ({ pedir: vi.fn(), contaEmLeitura: null, recados: {} }),
}));

// O painel dos canais tem prova própria em
// `src/components/trafego/canais/__tests__`. Aqui ele é dublado porque o objeto
// desta prova são as ABAS — e porque o painel real pede um `QueryClient`, que
// esta moldura não monta. Sem o dublê, ativar a aba derruba a árvore inteira e
// o teste passa a falhar por um motivo que não é o que ele investiga.
vi.mock('@/components/trafego/canais/PainelDeCanais', () => ({
  PainelDeCanais: () => 'painel dos canais',
  default: () => 'painel dos canais',
}));

vi.mock('@/hooks/useNotificacoes', () => ({
  useNotificacoes: () => notificacoes,
  INTERVALO_NOTIFICACOES_MS: 600000,
  CHAVE_NOTIFICACOES: ['notificacoes', 'trafego'],
}));

// A moldura da aplicação inteira não é o objeto desta prova.
// O contador da aba Atenção passou a vir da MESMA projeção que a fila e o sino
// usam, e não de `alertas.length`. Dublar aqui é o que mantém o teste medindo o
// contrato ("o número vive no rótulo da aba") em vez de medir a implementação
// de onde ele sai.
// Só o CONTADOR é dublado; o resto do módulo continua real, porque a fila da
// aba Atenção usa os outros exports daqui. Dublar o módulo inteiro deixaria os
// testes da fila medindo o dublê em vez da projeção.
/**
 * Só o CONTADOR é dublado; o resto do módulo continua real, porque a fila da
 * aba Atenção usa os outros exports daqui. Dublar o módulo inteiro deixaria os
 * testes da fila medindo o dublê em vez da projeção.
 *
 * E ele é uma variável, não uma constante: o contador precisa poder ser `null`
 * para provar que "sem leitura" não vira "zero". Zero é uma afirmação — diz que
 * olhamos e não havia nada — e o teste existe justamente para impedir que a
 * ausência de leitura seja apresentada como boa notícia.
 */
let contadorDeAtencao: number | null = 2;
vi.mock('@/components/trafego/atencao/useAtencao', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/trafego/atencao/useAtencao')>()),
  useContadorDeAtencao: () => contadorDeAtencao,
}));

vi.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// O quadro de funis é preservado como está; aqui basta saber que ele aparece
// na aba certa, e só nela.
vi.mock('@/pages/trafego/TrafegoPage', () => ({
  default: () => <div>quadro de oportunidades</div>,
}));

vi.mock('@/components/trafego/estudio/EstudioLigado', () => ({
  EstudioLigado: () => <div>estúdio de criação</div>,
  default: () => <div>estúdio de criação</div>,
}));

function montar(endereco = '/trafego') {
  return render(
    <MemoryRouter initialEntries={[endereco]}>
      <HubDeTrafegoPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
    contadorDeAtencao = 2;
  leitura = { ...leituraBase, inventario: inventarioDeProva() };
  notificacoes = {
    data: quadroDeAlertasDeProva(),
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  };
  Object.defineProperty(window, 'innerWidth', {
    value: 1440, writable: true, configurable: true,
  });
});
afterEach(cleanup);

describe('as quatro abas', () => {
  it('Campanhas é a aba padrão', () => {
    montar();
    const campanhas = screen.getByRole('tab', { name: /campanhas/ });
    expect(campanhas.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('BR - Maquininha de Cartão')).toBeTruthy();
    expect(screen.queryByText('quadro de oportunidades')).toBeNull();
  });

  it('tem exatamente três tarefas primárias, na ordem do fluxo de trabalho', () => {
    montar();
    const abas = screen.getAllByRole('tab').map((t) => t.textContent);
    // "Criar" era uma antessala técnica de capacidades, não uma tarefa. O ato
    // começa em Preparar e segue para a bancada da campanha.
    expect(abas).toEqual(['campanhas7', 'preparar', 'atenção2']);
  });

  it('o contador vive no rótulo da aba — não numa faixa de números no topo', () => {
    montar();
    const campanhas = screen.getByRole('tab', { name: /campanhas/ });
    expect(within(campanhas).getByText('7')).toBeTruthy();
    const atencao = screen.getByRole('tab', { name: /atenção/ });
    expect(within(atencao).getByText('2')).toBeTruthy();
  });

  it('sem leitura, a aba não mostra número — porque zero seria uma afirmação', () => {
    leitura = { ...leituraBase, inventario: null, carregando: true };
    notificacoes = { ...notificacoes, data: null, isLoading: true };
    contadorDeAtencao = null;
    montar();
    const abas = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(abas).toEqual(['campanhas', 'preparar', 'atenção']);
  });

  it('troca de aba pelo ponteiro e preserva o quadro de oportunidades', () => {
    montar();
    fireEvent.mouseDown(screen.getByRole('tab', { name: /preparar/ }));
    expect(screen.getByText('quadro de oportunidades')).toBeTruthy();
    expect(screen.queryByText('BR - Maquininha de Cartão')).toBeNull();
  });

  it('o endereço antigo aba=oportunidades ainda abre Preparar', () => {
    montar('/trafego?aba=oportunidades');
    expect(screen.getByRole('tab', { name: /preparar/ }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('quadro de oportunidades')).toBeTruthy();
  });

  it('Nova campanha é ação primária visível e abre o trabalho em Preparar', () => {
    montar();
    const nova = screen.getByRole('button', { name: 'Nova campanha' });
    expect(nova.className).toMatch(/bg-primary/);
    fireEvent.click(nova);
    expect(screen.getByRole('tab', { name: /preparar/ }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('quadro de oportunidades')).toBeTruthy();
  });
});

describe('navegação por teclado', () => {
  it('a seta troca de aba e o foco itinerante acompanha', async () => {
    // Foco itinerante: uma parada só de Tab para o grupo inteiro, e as setas
    // percorrem dentro. É o que evita que três abas custem três Tabs para
    // quem só quer chegar à tabela.
    montar();
    // ⚠️ A seta anda UMA casa. Com `Canais` consolidada em `criar`, a casa
    // seguinte a Campanhas voltou a ser Preparar.
    const [campanhas, preparar, atencao] = screen.getAllByRole('tab');
    campanhas.focus();
    fireEvent.keyDown(campanhas, { key: 'ArrowRight' });

    await waitFor(() => {
      expect(preparar.getAttribute('aria-selected')).toBe('true');
    });
    expect(preparar.getAttribute('tabindex')).toBe('0');
    expect(campanhas.getAttribute('tabindex')).toBe('-1');

    // ⚠️ O foco precisa ACOMPANHAR antes da segunda seta. No navegador o
    // Radix move o foco junto com a seleção; no jsdom o `focus()` do elemento
    // seguinte é o que reproduz isso. Sem ele, a segunda tecla chega a um
    // elemento que não está focado e o teste falharia por um motivo que não é
    // o que ele investiga.
    preparar.focus();
    fireEvent.keyDown(preparar, { key: 'ArrowRight' });
    await waitFor(() => {
      expect(atencao.getAttribute('aria-selected')).toBe('true');
    });
    expect(atencao.getAttribute('tabindex')).toBe('0');
  });

  it('a lista de abas se anuncia, e o painel ativo pertence à aba ativa', () => {
    montar();
    expect(screen.getByRole('tablist', { name: 'seções do tráfego' })).toBeTruthy();
    const painel = screen.getByRole('tabpanel');
    const aba = screen.getByRole('tab', { name: /campanhas/ });
    expect(painel.getAttribute('aria-labelledby')).toBe(aba.id);
  });
});

describe('o sino manda para cá', () => {
  it('abre direto na aba Atenção quando o endereço pede', () => {
    montar('/trafego?aba=atencao');
    expect(screen.getByRole('tab', { name: /atenção/ }).getAttribute('aria-selected')).toBe('true');
    // O título do grupo é o sintoma, e ele aparece uma vez para todas as linhas
    // que estão nele: repetir o rótulo em cada linha é o ruído que faz o olho
    // parar de ler o rótulo.
    expect(
      screen.getByRole('heading', { level: 3, name: /ligada e sem impressão/ }),
    ).toBeTruthy();
    expect(screen.getAllByText('BR - Maquininha de Cartão').length).toBeGreaterThan(0);
  });

  it('foca a campanha que o alerta apontou', () => {
    montar('/trafego?aba=atencao&foco=8017851692-24155134757');
    const alvo = document.getElementById('alerta-8017851692-24155134757');
    expect(alvo).toBeTruthy();
    expect(document.activeElement).toBe(alvo);
  });
});

describe('a fila de atenção', () => {
  it('agrupa por condição observada e diz o que cada uma afirma', () => {
    montar('/trafego?aba=atencao');
    const grupo = screen.getByRole('region', { name: 'ligada e sem impressão' });
    expect(within(grupo).getByText('2 campanhas')).toBeTruthy();
    expect(within(grupo).getAllByText(/Não entrou no leilão/).length).toBeGreaterThan(0);
    // Cada item traz a próxima ação segura na linha fechada: uma fila que só
    // nomeia problemas é uma lista de becos sem saída.
    expect(within(grupo).getAllByText(/próxima ação segura/).length).toBe(2);
  });

  it('conta não lida não vira "sem alertas"', () => {
    montar('/trafego?aba=atencao');
    expect(screen.getByText('1 conta não pôde ser lida')).toBeTruthy();
    expect(screen.getByText(/há ausência de leitura/)).toBeTruthy();
  });

  it('declara o que ainda não foi construído', () => {
    montar('/trafego?aba=atencao');
    expect(screen.getByText(/ainda não agrupa\s+reincidência/)).toBeTruthy();
  });

  it('o vazio diz sobre o que ele é vazio', () => {
    // ⚠️ As DUAS fontes precisam estar limpas. A fila projeta a varredura de
    // entrega E o registro de campanhas; zerar só a primeira deixaria em cena as
    // condições que vêm do inventário — e a prova passaria a dizer que o vazio
    // é vazio quando ele não é.
    notificacoes = {
      ...notificacoes,
      data: quadroDeAlertasDeProva({ alertas: [], contas: [], verificadas: 2 }),
    };
    leitura = { ...leituraBase, inventario: inventarioSaudavel() };
    montar('/trafego?aba=atencao');
    expect(screen.getByText('Nenhuma condição ativa entre o que foi lido')).toBeTruthy();
    expect(screen.getByText(/2 campanhas ligadas foram conferidas/)).toBeTruthy();
  });
});
