// @vitest-environment jsdom
/**
 * `/trafego` mostra o estado REAL dos quatro canais — e nunca verde sem prova.
 *
 * Estes testes montam a tela sobre um contrato de servidor e cobram o que ela
 * escreve. Não é teste de estilo: cada asserção é sobre uma FRASE que muda a
 * decisão de quem lê.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ContratoDeCanal, RespostaDosCanais } from '@/lib/trafego/canais';

const contratoDosCanais = vi.fn();
vi.mock('@/lib/pautadorApi', () => ({
  pautadorApi: { contratoDosCanais: (...a: unknown[]) => contratoDosCanais(...a) },
  PautadorApiError: class extends Error {},
}));

// Importado DEPOIS do mock, para o componente receber o dublê.
const { PainelDeCanais } = await import(
  '@/components/trafego/canais/PainelDeCanais'
);

function canal(over: Partial<ContratoDeCanal> = {}): ContratoDeCanal {
  return {
    plataforma: 'GOOGLE_ADS',
    canal: 'PERFORMANCE_MAX',
    rotulo: 'Performance Max',
    manifesto: {
      plataforma: 'GOOGLE_ADS',
      canal: 'PERFORMANCE_MAX',
      rotulo: 'Performance Max',
      hierarquia: ['campanha', 'asset_group', 'asset'],
      paineis: [],
      campos_do_pedido: [],
      capacidades: ['ler'],
      provas_obrigatorias: [],
      indisponibilidades: [],
      sabe_criar: false,
      sabe_provar: false,
    },
    portoes: [
      { nome: 'planejavel', estado: 'PERMITIDO', aberto: true, bloqueadores: [] },
      {
        nome: 'validavel',
        estado: 'BLOQUEADO',
        aberto: false,
        bloqueadores: [{
          codigo: 'PMAX_FORA_DO_EXECUTOR',
          causa: 'Performance Max monta o plano inteiro aqui e não está habilitado nesta versão.',
          origem: 'produto',
          observado_em: '2026-09-01',
          revalidacao: null,
        }],
      },
      {
        nome: 'criavel_pausada',
        estado: 'BLOQUEADO',
        aberto: false,
        bloqueadores: [{
          codigo: 'PMAX_FORA_DO_EXECUTOR',
          causa: 'idem',
          origem: 'produto',
          observado_em: '2026-09-01',
          revalidacao: null,
        }],
      },
      {
        nome: 'ativavel',
        estado: 'BLOQUEADO',
        aberto: false,
        bloqueadores: [{
          codigo: 'ativacao_fora_de_escopo',
          causa: 'despausar campanha não é uma ação que este sistema executa.',
          origem: 'produto',
          observado_em: null,
          revalidacao: null,
        }],
      },
    ],
    assets: {
      estado: 'PERMITIDO',
      recursos: ['marketing', 'marketing_quadrada'],
      quantidade: 2,
      fonte: 'volc_ads/campanha/brief.py',
      causa: null,
    },
    mensuracao: {
      lida: false,
      conversion_goal_status: 'INDETERMINADO',
      conversion_signal_status: 'INDETERMINADO',
      signal_sources: [],
      measurement_readiness: 'INDETERMINADO',
      data_manager_status: 'INDETERMINADO',
      observability_status: 'INDETERMINADO',
      smart_bidding_eligible: false,
      fonte: 'esta tela não consulta a conta do Google',
      notas: {},
    },
    observabilidade: {
      estado: 'INDETERMINADO',
      coletor: 'varredura do Hub de Tráfego',
      causa: 'ninguém contou quantas campanhas deste canal foram lidas de volta',
      campanhas_no_espelho: null,
      contagem_truncada: false,
    },
    operacional: {},
    ...over,
  };
}

function resposta(canais: ContratoDeCanal[]): RespostaDosCanais {
  return {
    operador: {
      is_admin: true, lab_mode: false, google_read: true,
      google_validate_only: true, google_mutate: false,
      google_demand_gen_validate_only: false,
      porque_sem_mutacao: 'a permissão está fechada neste servidor.',
    },
    politica_canario: {},
    canais,
    fontes: {
      espelho_lido: false,
      leitura_viva_do_google: false,
      por_que_sem_leitura_viva: 'esta tela não consulta a conta do Google.',
    },
  };
}

function montar() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <PainelDeCanais />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  contratoDosCanais.mockReset();
});

// Sem isto, o render anterior continua montado e `getByText` acha dois nós —
// o teste falha por uma razão que não é a que ele investiga.
afterEach(cleanup);

describe('a tela mostra o estado real, e o motivo de cada recusa', () => {
  it('os quatro portões aparecem, inclusive os fechados', async () => {
    contratoDosCanais.mockResolvedValue(resposta([canal()]));
    montar();
    await waitFor(() => screen.getByText('Performance Max'));
    for (const r of ['Planejável', 'Validável', 'Criável pausada', 'Ativável']) {
      expect(screen.getByText(r)).toBeTruthy();
    }
  });

  it('nenhum portão fechado aparece sem causa', async () => {
    contratoDosCanais.mockResolvedValue(resposta([canal()]));
    montar();
    await waitFor(() => screen.getByText('Performance Max'));
    expect(
      screen.getAllByText(/não está habilitado nesta versão/).length,
    ).toBeGreaterThan(0);
  });

  it('a recusa diz A QUEM PEDIR', async () => {
    // É a informação que transforma um botão cinza numa próxima ação.
    contratoDosCanais.mockResolvedValue(resposta([canal()]));
    montar();
    await waitFor(() => screen.getByText('Performance Max'));
    expect(
      screen.getAllByText(/Depende de uma decisão registrada/).length,
    ).toBeGreaterThan(0);
  });

  it('o contador de portões abertos usa o veredito do servidor', async () => {
    contratoDosCanais.mockResolvedValue(resposta([canal()]));
    montar();
    await waitFor(() => screen.getByText('Performance Max'));
    expect(screen.getByText('1 de 4 portões liberados')).toBeTruthy();
  });
});

describe('nada aparece verde sem evidência', () => {
  it('mensuração não lida diz "não lida", nunca "não pronto"', async () => {
    contratoDosCanais.mockResolvedValue(resposta([canal()]));
    montar();
    await waitFor(() => screen.getByText('Performance Max'));
    expect(screen.getByText(/Mensuração — não lida/)).toBeTruthy();
  });

  it('espelho não contado aparece como traço, e não como zero', async () => {
    contratoDosCanais.mockResolvedValue(resposta([canal()]));
    montar();
    await waitFor(() => screen.getByText('Performance Max'));
    const rotulo = screen.getByText('campanhas lidas de volta');
    expect(rotulo.parentElement?.textContent).toContain('—');
    expect(rotulo.parentElement?.textContent).not.toContain('0');
  });

  it('a tela declara que não consultou o Google', async () => {
    contratoDosCanais.mockResolvedValue(resposta([canal()]));
    montar();
    await waitFor(() => screen.getByText('Performance Max'));
    // Aparece no cabeçalho e ao lado da mensuração não lida: as duas são
    // legítimas, e a pergunta do teste é se a tela declara, não onde.
    expect(
      screen.getAllByText(/esta tela não consulta a conta do Google/).length,
    ).toBeGreaterThan(0);
  });

  it('um contrato incoerente é denunciado em vez de lido pela metade', async () => {
    const incoerente = canal({
      portoes: [
        {
          nome: 'planejavel', estado: 'PERMITIDO', aberto: true,
          bloqueadores: [{
            codigo: 'x', causa: 'motivo qualquer', origem: 'produto',
            observado_em: null, revalidacao: null,
          }],
        },
      ],
    });
    contratoDosCanais.mockResolvedValue(resposta([incoerente]));
    montar();
    await waitFor(() => screen.getByText('Performance Max'));
    expect(screen.getByText(/está incoerente/)).toBeTruthy();
  });
});

describe('falha de leitura não vira afirmação sobre os canais', () => {
  it('erro diz que não sabe, e não que não há canal', async () => {
    contratoDosCanais.mockRejectedValue(new Error('rede caiu'));
    montar();
    // ⚠️ `useCanais` tenta de novo UMA vez antes de desistir — uma leitura
    // que falhou por um blip não deve virar tela de erro. O teste espera
    // essa tentativa em vez de exigir que ela não exista.
    await waitFor(
      () => screen.getByText(/Não foi possível ler o estado dos canais/),
      { timeout: 5000 },
    );
    expect(screen.getByText(/eles\s+continuam existindo/)).toBeTruthy();
  });
});

describe('o canário pausado', () => {
  it('mostra as duas razões do estado, e "em revisão" não some', async () => {
    const search = canal({
      canal: 'SEARCH',
      rotulo: 'Search',
      operacional: {
        canario: {
          campaign_id: '24195821946',
          conta: '547-809-6539',
          conta_label: 'Portal Mundo Mais',
          canal: 'SEARCH',
          estado_declarado: 'PAUSED',
          leitura_de_campo: {
            observado_em: '2026-09-01',
            estrategia_de_lance: {
              valor: 'MANUAL_CPC',
              estado: 'escolhido',
              por_que_importa: 'lance manual não aprende com conversão.',
            },
            primary_status: 'PAUSED',
            primary_status_reasons: [
              { codigo: 'CAMPAIGN_PAUSED', natureza: 'por_desenho',
                texto: 'a campanha está pausada porque foi criada assim.' },
              { codigo: 'MOST_ADS_UNDER_REVIEW', natureza: 'em_revisao',
                texto: 'ainda em revisão; não é aprovação nem reprovação.' },
            ],
          },
          superficies: [
            { nome: 'registro_de_criacao', descricao: 'o recibo da criação',
              visivel: true, causa: null, detalhe: null },
            { nome: 'espelho_de_leitura', descricao: 'a leitura de volta da conta',
              visivel: false, causa: 'a leitura contínua só enxerga campanhas ativas.',
              detalhe: null },
            { nome: 'identidade_de_campanha', descricao: 'a identidade interna',
              visivel: null, causa: 'a leitura não aconteceu.', detalhe: null },
          ],
          resumo: 'o canário aparece em 1 de 3 superfícies.',
        },
      },
    });
    contratoDosCanais.mockResolvedValue(resposta([search]));
    montar();
    await waitFor(() => screen.getByText(/Campanha canário 24195821946/));
    expect(screen.getByText(/CAMPAIGN_PAUSED/)).toBeTruthy();
    expect(screen.getByText(/MOST_ADS_UNDER_REVIEW/)).toBeTruthy();
  });

  it('MANUAL_CPC aparece como valor, e não como campo vazio', async () => {
    const search = canal({
      canal: 'SEARCH',
      operacional: {
        canario: {
          campaign_id: '24195821946', conta: '547-809-6539',
          conta_label: 'Portal Mundo Mais', canal: 'SEARCH',
          estado_declarado: 'PAUSED',
          leitura_de_campo: {
            observado_em: '2026-09-01',
            estrategia_de_lance: { valor: 'MANUAL_CPC', estado: 'escolhido',
              por_que_importa: 'lance manual não aprende com conversão.' },
            primary_status: 'PAUSED', primary_status_reasons: [],
          },
          superficies: [], resumo: 'x',
        },
      },
    });
    contratoDosCanais.mockResolvedValue(resposta([search]));
    montar();
    await waitFor(() => screen.getByText('MANUAL_CPC'));
    expect(screen.getByText(/lance manual não aprende/)).toBeTruthy();
  });

  it('as três visibilidades de superfície são distinguíveis', async () => {
    const search = canal({
      canal: 'SEARCH',
      operacional: {
        canario: {
          campaign_id: '24195821946', conta: '547-809-6539',
          conta_label: 'Portal Mundo Mais', canal: 'SEARCH',
          estado_declarado: 'PAUSED',
          leitura_de_campo: {
            observado_em: '2026-09-01',
            estrategia_de_lance: { valor: 'MANUAL_CPC', estado: 'escolhido',
              por_que_importa: 'x' },
            primary_status: 'PAUSED', primary_status_reasons: [],
          },
          superficies: [
            { nome: 'a', descricao: 'vista', visivel: true, causa: null, detalhe: null },
            { nome: 'b', descricao: 'ausente', visivel: false, causa: 'porque', detalhe: null },
            { nome: 'c', descricao: 'não lida', visivel: null, causa: 'ninguém leu', detalhe: null },
          ],
          resumo: 'x',
        },
      },
    });
    contratoDosCanais.mockResolvedValue(resposta([search]));
    montar();
    await waitFor(() => screen.getByText(/Campanha canário/));
    // ⚠️ `?` é o desenho de "não deu para perguntar", e ele NÃO pode ser o
    // mesmo de "não está lá": a primeira não autoriza conclusão nenhuma.
    expect(screen.getByText('sim')).toBeTruthy();
    expect(screen.getByText('não')).toBeTruthy();
    expect(screen.getByText('?')).toBeTruthy();
  });
});
