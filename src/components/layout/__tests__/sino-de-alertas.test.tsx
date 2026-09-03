// @vitest-environment jsdom
/**
 * O sino, estado por estado.
 *
 * ⚠️ A prova que não pode sair daqui é a que separa "não consegui perguntar" de
 * "perguntei e não há nada". As duas produzem uma central silenciosa, e levam a
 * ações opostas: uma manda tentar de novo, a outra manda seguir o dia. Um
 * contador alimentado por falha de consulta faz o operador procurar um problema
 * que ninguém observou — e o silêncio de uma falha lida como calmaria faz ele
 * não procurar o problema que existe.
 *
 * Os dublês são das FONTES (`useNotificacoes` e `useInventario`), não da
 * projeção: assim a prova atravessa a derivação de verdade, que é onde a
 * divergência entre o sino e a aba Atenção nasceria.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import SinoDeAlertas from '@/components/layout/SinoDeAlertas';
import { estadoDoSino } from '@/components/trafego/atencao/useAtencao';
import type { LeituraDoInventario } from '@/hooks/useInventario';
import type { QuadroDeAlertas } from '@/types/trafego';
import {
  alertaDaMaquininha,
  inventarioDeProva,
  inventarioSaudavel,
  quadroDeAlertasDeProva,
} from '@/components/trafego/inventario/fixtureDeProvas';

// ── dublês ──────────────────────────────────────────────────────────────────

const inventarioBase: LeituraDoInventario = {
  inventario: inventarioSaudavel(),
  carregando: false,
  atualizando: false,
  falhou: false,
  motivoDaFalha: null,
  temMais: false,
  carregandoMais: false,
  carregarMais: vi.fn(),
  recarregar: vi.fn(),
};

interface DubleDeNotificacoes {
  data: QuadroDeAlertas | null;
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => void;
}

let inventario: LeituraDoInventario = inventarioBase;
let notificacoes: DubleDeNotificacoes;

vi.mock('@/hooks/useInventario', () => ({
  useInventario: () => inventario,
  usePedirLeituraDaConta: () => ({ pedir: vi.fn(), contaEmLeitura: null, recados: {} }),
}));

vi.mock('@/hooks/useNotificacoes', () => ({
  useNotificacoes: () => notificacoes,
  INTERVALO_NOTIFICACOES_MS: 600_000,
  CHAVE_NOTIFICACOES: ['notificacoes', 'trafego'],
}));

/** Varredura de entrega que respondeu e não achou nada, sem conta em falha. */
const semCondicao = quadroDeAlertasDeProva({ alertas: [], contas: [], verificadas: 2 });

function notificacao(
  data: QuadroDeAlertas | null,
  ajuste: Partial<DubleDeNotificacoes> = {},
): DubleDeNotificacoes {
  return {
    data,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...ajuste,
  };
}

function montar() {
  return render(
    <MemoryRouter>
      <SinoDeAlertas side="bottom" />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // Base neutra: as duas fontes responderam e nada pede atenção.
  inventario = { ...inventarioBase, inventario: inventarioSaudavel() };
  notificacoes = notificacao(semCondicao);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ── 1 · nenhuma condição ativa ───────────────────────────────────────────────

describe('1 · nenhuma condição ativa', () => {
  it('continua visível, sem contador, e diz sobre o que o silêncio é', async () => {
    montar();
    const gatilho = screen.getByRole('button', { name: /nenhuma condição ativa/i });
    fireEvent.click(gatilho);

    expect(await screen.findByText('Nenhuma condição ativa')).toBeTruthy();
    expect(screen.getByText(/2 campanhas ligadas foram verificadas/)).toBeTruthy();
  });
});

// ── 2 · condições ativas ─────────────────────────────────────────────────────

describe('2 · condições ativas', () => {
  it('conta, nomeia o sintoma e aponta para o item na aba Atenção', async () => {
    notificacoes = notificacao(
      quadroDeAlertasDeProva({ alertas: [alertaDaMaquininha], contas: [], verificadas: 2 }),
    );
    montar();
    fireEvent.click(screen.getByRole('button', { name: /1 condição ativa/i }));

    expect(await screen.findByText('BR - Maquininha de Cartão')).toBeTruthy();
    // Sem a palavra do sintoma, o sino diria "há três coisas" sem dizer de que
    // tipo — e três tipos diferentes pedem três ações diferentes.
    expect(screen.getByText(/ligada e sem impressão/)).toBeTruthy();
    expect(screen.getByText('Crédito Up')).toBeTruthy();

    const destino = screen.getByRole('link', { name: /BR - Maquininha de Cartão/i });
    expect(destino.getAttribute('href')).toBe(
      '/trafego?aba=atencao&foco=8017851692-24155134757',
    );
  });

  it('a mesma projeção da aba: condição do registro também acende o sino', async () => {
    // Nenhum alerta de entrega, e mesmo assim há o que olhar: o inventário de
    // prova traz uma conta que não respondeu e três linhas de legado. Um sino
    // que só enxergasse a varredura diria "tudo bem" com isso em cena.
    notificacoes = notificacao(quadroDeAlertasDeProva({ alertas: [], contas: [], verificadas: 2 }));
    inventario = { ...inventarioBase, inventario: inventarioDeProva() };
    montar();

    const gatilho = screen.getByRole('button', { name: /condições ativas/i });
    fireEvent.click(gatilho);
    const lista = await screen.findByRole('list', { name: 'condições ativas' });
    expect(within(lista).getByText(/sincronização falhou/)).toBeTruthy();
  });
});

// ── 3 · atualização em andamento ─────────────────────────────────────────────

describe('3 · atualização em andamento', () => {
  it('a primeira consulta se anuncia como consulta, não como vazio', async () => {
    notificacoes = notificacao(null, { isLoading: true, isFetching: true });
    inventario = { ...inventarioBase, inventario: null, carregando: true, atualizando: true };
    montar();

    fireEvent.click(screen.getByRole('button', { name: /consultando a operação/i }));
    expect(await screen.findByLabelText('Consultando a operação')).toBeTruthy();
    // Nada de "nenhuma condição ativa" enquanto ninguém respondeu: seria
    // afirmar ausência sobre algo que ainda não foi apurado.
    expect(screen.queryByText('Nenhuma condição ativa')).toBeNull();
  });

  it('releitura por cima de dado bom não apaga a contagem que já está na tela', async () => {
    notificacoes = notificacao(
      quadroDeAlertasDeProva({ alertas: [alertaDaMaquininha], contas: [], verificadas: 2 }),
      { isFetching: true },
    );
    montar();

    // ⚠️ O nome do botão NÃO vira "consultando": trocar o nome de um controle
    // enquanto alguém está com o foco nele faz o controle mudar de identidade
    // debaixo da mão — e esta releitura acontece sozinha, sem ninguém pedir.
    const gatilho = screen.getByRole('button', { name: /1 condição ativa/i });
    fireEvent.click(gatilho);
    expect(await screen.findByText('BR - Maquininha de Cartão')).toBeTruthy();
  });
});

// ── 4 · consulta indisponível ────────────────────────────────────────────────

describe('4 · consulta indisponível', () => {
  it('não vira sino vazio nem contador, e diz que não foi possível perguntar', async () => {
    notificacoes = notificacao(null, { isError: true, error: new Error('x') });
    inventario = { ...inventarioBase, inventario: null, falhou: true };
    montar();

    const gatilho = screen.getByRole('button', { name: /não foi possível consultar/i });
    // O contador é uma AFIRMAÇÃO. Sem consulta boa não há o que afirmar.
    expect(gatilho.textContent).toBe('');
    fireEvent.click(gatilho);

    expect(await screen.findByText('Não foi possível verificar a operação')).toBeTruthy();
    expect(
      screen.getByText(/não quer dizer que está tudo bem/i),
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: /tentar novamente/i })).toBeTruthy();
  });

  it('a falha traz um código copiável — "deu erro" sozinho não acha nada no log', async () => {
    notificacoes = notificacao(null, { isError: true, error: new Error('x') });
    inventario = {
      ...inventarioBase,
      inventario: null,
      falhou: true,
      ocorrencia: {
        motivo: 'sistema_fora_do_ar',
        mensagem: 'O registro de campanhas não respondeu.',
        proximoPasso: 'Tente de novo em alguns minutos.',
        complemento: null,
        etapa: 'inventario',
        id: 'VOLC-ABC234',
        quando: '24/08/2026 17:06:00',
        paraCopiar: 'VOLC-ABC234',
      },
    };
    montar();
    fireEvent.click(screen.getByRole('button', { name: /não foi possível consultar/i }));

    expect(await screen.findByText('VOLC-ABC234')).toBeTruthy();
    expect(screen.getByRole('button', { name: /copiar código/i })).toBeTruthy();
  });
});

// ── 5 · último estado conhecido preservado ───────────────────────────────────

describe('5 · último estado conhecido preservado', () => {
  it('mostra o que sabia antes e diz que é de antes', async () => {
    notificacoes = notificacao(
      quadroDeAlertasDeProva({ alertas: [alertaDaMaquininha], contas: [], verificadas: 2 }),
      { isError: true, error: new Error('x') },
    );
    montar();

    fireEvent.click(screen.getByRole('button', { name: /último estado conhecido/i }));
    expect(await screen.findByText('BR - Maquininha de Cartão')).toBeTruthy();
    expect(screen.getByText(/ele é de antes, não de agora/)).toBeTruthy();
  });
});

// ── indisponibilidade não é alerta ───────────────────────────────────────────

describe('indisponibilidade de leitura não soma ao contador', () => {
  it('conta que não pôde ser verificada aparece fora da contagem', async () => {
    notificacoes = notificacao(
      quadroDeAlertasDeProva({
        alertas: [],
        contas: [{ customer_id: '3849678045', nome: 'PMUNDO+', erro: 'a conta não respondeu' }],
        verificadas: 2,
      }),
    );
    montar();

    // Nenhuma condição ativa: a conta que não respondeu é ausência de leitura,
    // e ausência de leitura não é ausência nem presença de problema.
    const gatilho = screen.getByRole('button', { name: /nenhuma condição ativa/i });
    expect(gatilho.textContent).toBe('');
    fireEvent.click(gatilho);
    expect(await screen.findByText(/há ausência de leitura/)).toBeTruthy();
  });
});

// ── a regra, isolada da tela ─────────────────────────────────────────────────

describe('estadoDoSino — um estado por vez, e a ordem é a regra', () => {
  it('"não consegui perguntar" vem antes de qualquer contagem', () => {
    expect(
      estadoDoSino({
        indisponivel: true,
        carregando: false,
        ultimoEstadoConhecido: false,
        quantos: 3,
      }),
    ).toBe('indisponivel');
  });

  it('cada um dos outros quatro tem o seu', () => {
    const base = {
      indisponivel: false,
      carregando: false,
      ultimoEstadoConhecido: false,
      quantos: 0,
    };
    expect(estadoDoSino({ ...base, carregando: true })).toBe('consultando');
    expect(estadoDoSino({ ...base, ultimoEstadoConhecido: true, quantos: 2 })).toBe(
      'ultimo_conhecido',
    );
    expect(estadoDoSino({ ...base, quantos: 2 })).toBe('com_condicao');
    expect(estadoDoSino(base)).toBe('sem_condicao');
  });
});

// ── o falso verde do sino ────────────────────────────────────────────────────

describe('zero numa lista incompleta não é "não há nada"', () => {
  const base = {
    indisponivel: false,
    carregando: false,
    ultimoEstadoConhecido: false,
    quantos: 0,
  };

  it('contagem zero com lista incompleta NÃO cai em sem_condicao', () => {
    // ⚠️ Medido em 03/09/2026: com `quantos === 0` e `parcial === true` — o que
    // acontece toda vez que o inventário tem mais páginas do que esta sessão
    // carregou — o sino caía em `sem_condicao` e desenhava o check verde de
    // "Nenhuma condição ativa". A ressalva existia, num bloco cinza abaixo, e o
    // operador lia o glifo.
    expect(estadoDoSino({ ...base, parcial: true })).toBe('lista_incompleta');
    expect(estadoDoSino({ ...base, parcial: true })).not.toBe('sem_condicao');
  });

  it('lista completa e zero continua sendo sem_condicao', () => {
    expect(estadoDoSino({ ...base, parcial: false })).toBe('sem_condicao');
    expect(estadoDoSino(base)).toBe('sem_condicao');
  });

  it('uma condição achada vence a ressalva de método', () => {
    // Uma condição achada é uma afirmação VERDADEIRA mesmo com a busca
    // incompleta. Escondê-la atrás do aviso trocaria um alarme real por um
    // aviso sobre como a lista foi montada.
    expect(estadoDoSino({ ...base, quantos: 2, parcial: true })).toBe('com_condicao');
  });

  it('não saber perguntar continua vencendo tudo', () => {
    expect(estadoDoSino({ ...base, indisponivel: true, parcial: true })).toBe(
      'indisponivel',
    );
    expect(estadoDoSino({ ...base, carregando: true, parcial: true })).toBe(
      'consultando',
    );
  });
});
