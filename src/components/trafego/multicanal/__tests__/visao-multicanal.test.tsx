// @vitest-environment jsdom
/**
 * T13 — a visão multicanal, e as promessas que ela não pode fazer.
 *
 * ⚠️ Nenhum teste aqui bate na rede: `useCanais` é dublado.
 */
import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ContratoDeCanal } from '@/lib/trafego/canais';

const estado = vi.hoisted(() => ({ resposta: null as unknown }));

vi.mock('@/components/trafego/canais/useCanais', () => ({
  useCanais: () => estado.resposta,
}));

const { VisaoMulticanal, CANAIS_DESTA_TELA } = await import(
  '@/components/trafego/multicanal/VisaoMulticanal'
);

function portao(nome: string, estadoDoPortao: string, bloqueadores: unknown[] = []) {
  return {
    nome,
    estado: estadoDoPortao,
    aberto: estadoDoPortao === 'PERMITIDO',
    bloqueadores,
  };
}

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
      campos_do_pedido: ['copy'],
      capacidades: ['ler', 'propor'],
      provas_obrigatorias: [],
      indisponibilidades: [],
      sabe_criar: false,
      sabe_provar: true,
    },
    portoes: [
      portao('planejavel', 'PERMITIDO'),
      portao('validavel', 'BLOQUEADO', [
        {
          codigo: 'pmax_experimental_desligado',
          causa: 'a conferência de Performance Max está desligada neste servidor.',
          origem: 'servidor',
          observado_em: null,
          revalidacao: null,
        },
      ]),
      portao('criavel_pausada', 'BLOQUEADO', [
        {
          codigo: 'PMAX_FORA_DO_EXECUTOR',
          causa: 'o canal está fora do executor e o canário dele não foi aceito.',
          origem: 'produto',
          observado_em: '2026-09-01',
          revalidacao: null,
        },
      ]),
      portao('ativavel', 'BLOQUEADO', [
        {
          codigo: 'ativacao_fora_de_escopo',
          causa: 'ativar não é ato deste fluxo.',
          origem: 'politica',
          observado_em: null,
          revalidacao: null,
        },
      ]),
    ] as ContratoDeCanal['portoes'],
    assets: {
      estado: 'PERMITIDO',
      recursos: ['imagem_marketing', 'logo'],
      quantidade: 2,
      fonte: 'volc_ads/campanha/pmax.py',
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
      fonte: 'ninguém leu a conta nesta requisição',
      plano: null,
    } as ContratoDeCanal['mensuracao'],
    observabilidade: {
      estado: 'INDETERMINADO',
      coletor: 'varredura do Hub',
      causa: 'ninguém contou',
      campanhas_no_espelho: null,
      contagem_truncada: false,
    },
    operacional: {},
    economia: {
      teto_diario_brl: '20.00',
      cpc_maximo_brl: null,
      lances_permitidos: ['MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE'],
      minimo_diario_medido: null,
      causa: null,
    },
    destino: {
      tabela: 'asset_group',
      campo: 'asset_group.final_urls',
      url_exclusiva: true,
      travas: ['excluded_parent_asset_set_types = [PAGE_FEED]'],
    },
    automacoes_travadas: [
      {
        nome: 'GENERATE_IMAGE_EXTRACTION',
        estado: 'OPTED_OUT',
        campo: 'campaign.asset_automation_settings',
        por_que: 'raspa imagens da landing page para o pool visual da campanha.',
      },
    ],
    prova: {
      estado: 'BLOQUEADO',
      flag: 'porta experimental de Performance Max',
      causa: 'está desligada neste servidor.',
    },
    conta: {
      customer_id: '5478096539',
      customer_id_formatado: '547-809-6539',
      rotulo: 'Portal Mundo Mais',
      login_customer_id: '6016739364',
    },
    proximo_ato: 'para conferir o plano com o Google, resolva primeiro: a porta experimental.',
    ...over,
  };
}

function resposta(canais: ContratoDeCanal[]) {
  return {
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    data: {
      operador: {},
      politica_canario: {},
      canais,
      fontes: {
        espelho_lido: false,
        leitura_viva_do_google: false,
        por_que_sem_leitura_viva: 'nenhuma leitura viva foi feita.',
      },
    },
  };
}

function montar() {
  // ⚠️ O contêiner é DEVOLVIDO e os testes buscam DENTRO dele: sem `cleanup`
  // automático (o ambiente é declarado por arquivo), `screen` enxerga o DOM de
  // todos os `render` anteriores, e um teste que afirma ausência passaria a
  // medir a tela de outro teste.
  return render(
    <MemoryRouter>
      <VisaoMulticanal />
    </MemoryRouter>,
  );
}

// ⚠️ `cleanup` explícito: sem ele, `screen` enxerga o DOM de todos os `render`
// anteriores do arquivo, e um teste que afirma AUSÊNCIA passaria a medir a tela
// de outro teste — o pior tipo de verde.
afterEach(() => {
  cleanup();
});

beforeEach(() => {
  estado.resposta = resposta([
    canal(),
    canal({ canal: 'DISPLAY', rotulo: 'Display' }),
    canal({ canal: 'DEMAND_GEN', rotulo: 'Demand Gen' }),
    canal({ canal: 'SEARCH', rotulo: 'Search' }),
  ]);
});

describe('a visão multicanal', () => {
  it('mostra os TRÊS canais desta tela e deixa Search fora', () => {
    montar();
    const titulos = screen
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent);
    expect(titulos).toEqual(['Performance Max', 'Display', 'Demand Gen']);
    // Search tem cockpit próprio; repeti-lo criaria duas telas para o mesmo
    // canal, e a primeira divergiria da segunda no primeiro ajuste.
    expect(titulos).not.toContain('Search');
    expect(CANAIS_DESTA_TELA).toEqual(['DISPLAY', 'DEMAND_GEN', 'PERFORMANCE_MAX']);
  });

  it('canal bloqueado continua VISÍVEL e explicado', () => {
    montar();
    const secao = screen.getAllByRole('region')[0];
    expect(within(secao).getAllByText(/BLOQUEADO/).length).toBeGreaterThan(0);
    expect(
      within(secao).getByText(/o canal está fora do executor/),
    ).toBeTruthy();
  });

  it('NENHUM botão de ativação existe, em nenhum estado', () => {
    montar();
    for (const b of screen.getAllByRole('button')) {
      const texto = (b.textContent ?? '').toLowerCase();
      expect(texto).not.toContain('ativar');
      expect(texto).not.toContain('despausar');
      expect(texto).not.toContain('publicar');
    }
  });

  it('não oferece criação: a única CTA abre a bancada', () => {
    montar();
    const secao = screen.getAllByRole('region')[0];
    const acoes = within(secao)
      .getAllByRole('button')
      .filter((b) => (b.textContent ?? '').trim().length > 0);
    // UMA CTA dominante por cartão (`design.md`: one primary action per region).
    expect(acoes).toHaveLength(1);
    expect(acoes[0].textContent).toContain('Abrir a bancada');
    expect((acoes[0].textContent ?? '').toLowerCase()).not.toContain('criar');
  });

  it('distingue ausência, nulo e desconhecido — e nunca usa um traço para os três', () => {
    montar();
    const secao = screen.getAllByRole('region')[0];
    // `ausente`: PMax não tem CPC. Não há o que consertar.
    expect(within(secao).getAllByText('não se aplica').length).toBeGreaterThan(0);
    expect(
      within(secao).getByText(/este canal não tem CPC a declarar/),
    ).toBeTruthy();
    // `desconhecido`: ninguém leu a mensuração.
    expect(within(secao).getAllByText('não lido').length).toBeGreaterThan(0);
  });

  it('mostra as automações travadas com nome, estado e consequência', () => {
    montar();
    const secao = screen.getAllByRole('region')[0];
    expect(within(secao).getByText('GENERATE_IMAGE_EXTRACTION')).toBeTruthy();
    expect(within(secao).getByText(/OPTED_OUT/)).toBeTruthy();
    expect(within(secao).getByText(/raspa imagens da landing page/)).toBeTruthy();
  });

  it('mostra o próximo ato do servidor, e um só', () => {
    montar();
    const secao = screen.getAllByRole('region')[0];
    expect(within(secao).getByText('Próximo ato')).toBeTruthy();
    expect(
      within(secao).getByText(/resolva primeiro: a porta experimental/),
    ).toBeTruthy();
  });

  it('a razão de a CTA estar travada aparece INTEIRA, sem "+N"', () => {
    estado.resposta = resposta([
      canal({
        portoes: [
          portao('planejavel', 'BLOQUEADO', [
            {
              codigo: 'sem_leitura',
              causa: 'sua sessão não tem papel ativo agora.',
              origem: 'operador',
              observado_em: null,
              revalidacao: null,
            },
          ]),
          portao('validavel', 'BLOQUEADO', []),
          portao('criavel_pausada', 'BLOQUEADO', []),
          portao('ativavel', 'BLOQUEADO', []),
        ] as ContratoDeCanal['portoes'],
      }),
    ]);
    montar();
    const secao = screen.getAllByRole('region')[0];
    // ⚠️ DUAS aparições, e cada uma responde a uma pergunta diferente: o poço
    // de bloqueadores explica a escada inteira, e o parágrafo ao lado do botão
    // explica o que trava o BOTÃO. Elas coincidem aqui porque o portão fechado
    // é justamente o primeiro.
    const ditas = within(secao).getAllByText(/sua sessão não tem papel ativo agora/);
    expect(ditas.length).toBe(2);
    for (const dita of ditas) {
      expect(dita.textContent).toContain('quem resolve:');
    }
    expect(within(secao).queryByText(/\+\d+ /)).toBeNull();
  });

  it('falha de leitura NÃO vira "nenhum canal disponível"', () => {
    estado.resposta = {
      isLoading: false,
      isError: true,
      isFetching: false,
      error: new Error('502'),
      refetch: vi.fn(),
      data: null,
    };
    montar();
    expect(
      screen.getByText(/Isto é uma falha de leitura, e não uma afirmação/),
    ).toBeTruthy();
  });

  it('carregando NÃO desenha portões fechados', () => {
    estado.resposta = {
      isLoading: true,
      isError: false,
      isFetching: true,
      error: null,
      refetch: vi.fn(),
      data: null,
    };
    const { container } = montar();
    expect(within(container).getByText(/Lendo o que cada canal pode fazer/)).toBeTruthy();
    expect(within(container).queryAllByText(/BLOQUEADO/)).toHaveLength(0);
  });
});
