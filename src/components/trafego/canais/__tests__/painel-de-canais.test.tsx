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
      // ⚠️ `null` é "ninguém leu os três recursos que decidem a meta
      // efetiva", e não "não há plano". O servidor sempre emite a chave.
      plano: null,
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

describe('o plano de mensuração na tela (P05-T12 item 8)', () => {
  /** Um plano com tudo lido, e uma coisa faltando — que é o caso real. */
  function plano(over: Record<string, unknown> = {}) {
    return {
      versao: 1,
      customer_id: '5478096539',
      login_customer_id: '6016739364',
      campaign_id: null,
      chave_intencao: null,
      meta_efetiva: {
        nivel: 'CUSTOMER',
        nivel_estado: 'com_dados',
        nivel_decidido: true,
        custom_conversion_goal: null,
        usa_meta_customizada: false,
        campaign_id: null,
        metas_da_conta: [],
        metas_da_conta_estado: 'com_dados',
        metas_da_campanha: [],
        metas_da_campanha_estado: 'inelegivel',
        metas_que_mandam: [],
        metas_biddable: [
          {
            categoria: 'DOWNLOAD',
            origem: 'APP',
            biddable: true,
            campaign: null,
            semantica: 'DOWNLOAD/APP',
          },
        ],
        resolvida: true,
        causa: null,
      },
      acoes: [],
      acoes_estado: 'com_dados',
      acao_alvo: {
        id: '7466919994',
        resource_name: 'customers/5478096539/conversionActions/7466919994',
        owner_customer_id: '5478096539',
        nome: 'Compra no site',
        categoria: 'PURCHASE',
        origem: 'WEBSITE',
        tipo: 'WEBPAGE',
        status: 'ENABLED',
        primaria: true,
        primaria_efetiva: true,
        incluida_em_metricas: true,
        semantica: 'PURCHASE/WEBSITE',
        aceita_como_destino: true,
      },
      acao_alvo_causa: null,
      destino: {
        resolvido: true,
        operating_account_id: '5478096539',
        product_destination_id: '7466919994',
        conversion_action_resource: 'x',
        tipo_da_acao: 'WEBPAGE',
        causa: null,
      },
      frescor: {
        estado: 'vazio_confirmado',
        janela_dias: null,
        ultima_conversao_em: null,
        dias_desde_a_ultima: null,
        conversoes_na_janela: 0,
        conversion_action_id: '7466919994',
        comprovado: false,
        causa: null,
      },
      marcacao: {
        estado: 'com_dados',
        auto_tagging: true,
        conversion_tracking_id: '17862729897',
        conversion_tracking_owner_id: '5478096539',
        cross_account_conversion_tracking_id: null,
        conversion_tracking_status: 'CONVERSION_TRACKING_MANAGED_BY_SELF',
        aceitou_termos_de_dados: true,
        enhanced_conversions_for_leads: false,
        acoes_de_ga4: [],
        acoes_com_tag: ['7466919994'],
        click_ids_suportados: ['gclid', 'gbraid', 'wbraid'],
      },
      proposta_de_acao: null,
      completo: false,
      bloqueadores: [
        'a ação de conversão desta campanha não recebeu NENHUMA conversão na janela consultada.',
      ],
      impressao: 'a'.repeat(64),
    };
  }

  function comPlano(over: Record<string, unknown> = {}) {
    return canal({
      canal: 'SEARCH',
      rotulo: 'Search',
      mensuracao: {
        lida: true,
        conversion_goal_status: 'PRONTO',
        conversion_signal_status: 'PRONTO',
        signal_sources: ['tag do Google no site'],
        measurement_readiness: 'PRONTO',
        data_manager_status: 'NAO_PRONTO',
        observability_status: 'INDETERMINADO',
        smart_bidding_eligible: false,
        plano: plano(over) as never,
        fonte: 'leitura da conta feita ao conferir um pedido',
        notas: {},
      },
    });
  }

  it('mostra a meta efetiva, a fonte do sinal, o frescor e os bloqueadores', async () => {
    contratoDosCanais.mockResolvedValue(resposta([comPlano()]));
    montar();
    await waitFor(() => screen.getByText(/Plano de mensuração/));

    // meta efetiva — o objetivo E o nível de onde ele vem
    expect(screen.getByText('DOWNLOAD/APP (da conta)')).toBeTruthy();
    // fonte do sinal — com o ID NUMÉRICO e a conta DONA, nunca só o nome.
    // ⚠️ `getAllByText`: o id aparece DUAS vezes de propósito — na fonte do
    // sinal e no destino de conversão offline. São dois fatos diferentes sobre
    // a mesma ação, e colapsá-los num só lugar esconderia um deles.
    expect(
      screen.getByText('Compra no site · ação #7466919994 · conta 5478096539'),
    ).toBeTruthy();
    expect(
      screen.getByText('ação #7466919994 na conta 5478096539'),
    ).toBeTruthy();
    // frescor — "nunca recebeu conversão" é conclusão, e não "sem dados"
    expect(screen.getByText('nunca recebeu conversão')).toBeTruthy();
    // bloqueadores — em linguagem operacional, e não em código
    expect(screen.getByText(/não recebeu NENHUMA conversão/)).toBeTruthy();
  });

  it('diz que a campanha ainda não nasceu em vez de esconder o id ausente', async () => {
    // ⚠️ `campaign_id` nulo é o caso NORMAL — o plano existe ANTES do
    // nascimento. Omitir a informação faria o operador ler a ausência do id
    // como defeito.
    contratoDosCanais.mockResolvedValue(resposta([comPlano()]));
    montar();
    await waitFor(() => screen.getByText(/antes do nascimento/));
  });

  it('o estado de mensuração aparece em português E cru', async () => {
    // ⚠️ Quem lê a tela e quem lê o contrato na API precisam ver o mesmo nome.
    contratoDosCanais.mockResolvedValue(resposta([comPlano()]));
    montar();
    await waitFor(() => screen.getByText(/Mensuração — provado \(PRONTO\)/));
  });

  it('sem plano lido, a tela não desenha um plano vazio', async () => {
    // ⚠️ `null` é "ninguém leu"; um plano vazio seria "li e não há nada".
    contratoDosCanais.mockResolvedValue(resposta([canal()]));
    montar();
    await waitFor(() => screen.getByText(/Mensuração/));
    expect(screen.queryByText(/Plano de mensuração/)).toBeNull();
  });
});
