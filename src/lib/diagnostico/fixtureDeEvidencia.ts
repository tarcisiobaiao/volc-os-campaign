/**
 * Fixture com a FORMA REAL do `evidencia.json`.
 *
 * Ela não é ilustração: reproduz o que
 * `docs/growth-engine/diagnostico/consultas/rodar.py` emite — `_meta` +
 * `consultas`, cada consulta com `gaql`, `por_que`, `lido_em_utc` e ou
 * (`ok: true`, `n`, `linhas`) ou (`ok: false`, `erro`). As linhas são o que
 * `MessageToDict(preserving_proto_field_name=True)` devolve: snake_case
 * aninhado, int64 como STRING, e campo de valor padrão OMITIDO.
 *
 * Os dois casos vêm das duas campanhas Search reais da conta Crédito Up, com os
 * identificadores que aparecem nos recibos de `volc_ads/dados/recibos/`. Nenhum
 * segredo entra aqui: id de conta e de campanha não são credencial, e nenhuma
 * chave, token ou cabeçalho de autorização é reproduzido.
 *
 * ⚠️ Quando o `evidencia.json` do Agente B existir, ele substitui esta fixture
 * nos testes sem tocar em nenhum componente — é o mesmo tipo.
 */
import type {
  ConsultaFalhada,
  ConsultaRespondida,
  EvidenciaDeDiagnostico,
  LinhaDaConsulta,
} from './evidencia';

export const CONTA = '8017851692';
export const ID_MAQUININHA = '24155028398';
export const ID_FGTS = '24160871402';

const LIDO_EM = '2026-08-26T18:04:11.000Z';

function ok(linhas: LinhaDaConsulta[], porQue = 'consulta do runner'): ConsultaRespondida {
  return {
    gaql: 'SELECT ... FROM ...',
    por_que: porQue,
    lido_em_utc: LIDO_EM,
    ok: true,
    n: linhas.length,
    linhas,
  };
}

function falhou(erro: string): ConsultaFalhada {
  return {
    gaql: 'SELECT ... FROM ...',
    por_que: 'consulta do runner',
    lido_em_utc: LIDO_EM,
    ok: false,
    erro,
  };
}

export interface OpcoesDaFixture {
  /** Consultas a derrubar, para provar `nao_apurado`. */
  derrubar?: string[];
  /** Sobrescreve o estado da campanha da Maquininha. */
  estadoDaMaquininha?: string;
  /** Fração de leilões perdidos por verba na FGTS. */
  perdaPorVerba?: number;
  /** Impressões da FGTS na janela. `0` é medida, não ausência. */
  impressoesDoFgts?: number;
}

/**
 * A evidência de prova.
 *
 * Padrão: Maquininha PAUSED (o recibo criou pausada e ninguém ligou) e FGTS
 * ligada, entregando, perdendo 38% dos leilões por verba.
 */
export function evidenciaDeProva(opcoes: OpcoesDaFixture = {}): EvidenciaDeDiagnostico {
  const {
    derrubar = [],
    estadoDaMaquininha = 'PAUSED',
    perdaPorVerba = 0.38,
    impressoesDoFgts = 4820,
  } = opcoes;

  const consultas: Record<string, ConsultaRespondida | ConsultaFalhada> = {
    conta: ok([
      {
        customer: {
          id: CONTA,
          descriptive_name: 'Crédito Up',
          currency_code: 'BRL',
          time_zone: 'America/Sao_Paulo',
          status: 'ENABLED',
          // `manager` e `test_account` são `false` e o serializador os OMITE.
          auto_tagging_enabled: true,
          optimization_score: 0.71,
        },
      },
    ]),

    faturamento: ok([
      {
        billing_setup: {
          id: '9182736450',
          status: 'APPROVED',
          payments_account: 'customers/8017851692/paymentsAccounts/1',
          start_date_time: '2026-02-11 00:00:00',
        },
      },
    ]),

    campanhas: ok([
      {
        campaign: {
          id: ID_MAQUININHA,
          name: 'BR - 20260819_131546 / Maquininha de Cartão / https://creditoup.com.br/r/maquininha-de-cartao-menor-taxa/',
          status: estadoDaMaquininha,
          serving_status: estadoDaMaquininha === 'ENABLED' ? 'SERVING' : 'NOT_SERVING',
          primary_status: estadoDaMaquininha === 'ENABLED' ? 'ELIGIBLE' : 'PAUSED',
          primary_status_reasons:
            estadoDaMaquininha === 'ENABLED' ? [] : ['CAMPAIGN_PAUSED'],
          advertising_channel_type: 'SEARCH',
          bidding_strategy_type: 'MANUAL_CPC',
        },
        campaign_budget: {
          id: '15800018633',
          amount_micros: '15000000',
          delivery_method: 'STANDARD',
          status: 'ENABLED',
          period: 'DAILY',
        },
      },
      {
        campaign: {
          id: ID_FGTS,
          name: 'BR - 20260819_200614 / FGTS Saque-Aniversário / https://creditoup.com.br/r/fgts-saque-aniversario/',
          status: 'ENABLED',
          serving_status: 'SERVING',
          primary_status: 'ELIGIBLE',
          primary_status_reasons: [],
          advertising_channel_type: 'SEARCH',
          bidding_strategy_type: 'MANUAL_CPC',
        },
        campaign_budget: {
          id: '15811123159',
          amount_micros: '20000000',
          delivery_method: 'STANDARD',
          status: 'ENABLED',
          period: 'DAILY',
        },
      },
    ]),

    grupos: ok([
      grupo(ID_MAQUININHA, '199296802053', 'Maquininha — taxa'),
      grupo(ID_FGTS, '199310445071', 'FGTS — saque aniversário'),
      grupo(ID_FGTS, '199310445072', 'FGTS — antecipação'),
    ]),

    anuncios: ok([
      anuncio(ID_MAQUININHA, '199296802053', '741852963'),
      anuncio(ID_FGTS, '199310445071', '741852964'),
      anuncio(ID_FGTS, '199310445072', '741852965'),
    ]),

    keywords: ok([
      keyword(ID_MAQUININHA, '199296802053', '320734835278', 'maquininha de cartão'),
      keyword(ID_FGTS, '199310445071', '923327950987', 'saque aniversário fgts'),
      keyword(ID_FGTS, '199310445071', '918180464554', 'antecipar saque aniversário'),
      keyword(ID_FGTS, '199310445072', '298034418894', 'fgts antecipação'),
    ]),

    criterios_campanha: ok([
      {
        campaign: { id: ID_MAQUININHA },
        campaign_criterion: {
          criterion_id: '2076',
          type: 'LOCATION',
          status: 'ENABLED',
          location: { geo_target_constant: 'geoTargetConstants/2076' },
        },
      },
      {
        campaign: { id: ID_MAQUININHA },
        campaign_criterion: {
          criterion_id: '1014',
          type: 'LANGUAGE',
          status: 'ENABLED',
          language: { language_constant: 'languageConstants/1014' },
        },
      },
      {
        campaign: { id: ID_FGTS },
        campaign_criterion: {
          criterion_id: '2076',
          type: 'LOCATION',
          status: 'ENABLED',
          location: { geo_target_constant: 'geoTargetConstants/2076' },
        },
      },
      {
        campaign: { id: ID_FGTS },
        campaign_criterion: {
          criterion_id: '1014',
          type: 'LANGUAGE',
          status: 'ENABLED',
          language: { language_constant: 'languageConstants/1014' },
        },
      },
    ]),

    conversoes: ok([
      {
        conversion_action: {
          id: '6620001',
          name: 'Lead — formulário Crédito Up',
          status: 'ENABLED',
          type: 'WEBPAGE',
          category: 'SUBMIT_LEAD_FORM',
          primary_for_goal: true,
          counting_type: 'ONE_PER_CLICK',
          include_in_conversions_metric: true,
        },
      },
    ]),

    metricas_campanha: ok([
      {
        campaign: { id: ID_MAQUININHA, name: 'Maquininha de Cartão' },
        // Campanha pausada: todas as métricas são zero e o serializador as OMITE.
        // A linha existe, e é isso que faz "zero medido" ser diferente de
        // "não apurado".
      },
      {
        campaign: { id: ID_FGTS, name: 'FGTS Saque-Aniversário' },
        metrics: {
          impressions: String(impressoesDoFgts),
          clicks: '311',
          cost_micros: '487230000',
          average_cpc: '1566655',
          ctr: 0.0645,
          conversions: 12,
          search_impression_share: 0.44,
          search_budget_lost_impression_share: perdaPorVerba,
          search_rank_lost_impression_share: 0.18,
        },
      },
    ]),

    termos_de_busca: ok([
      {
        campaign: { id: ID_FGTS },
        search_term_view: { search_term: 'saque aniversário fgts como antecipar', status: 'ADDED' },
        metrics: { impressions: '820', clicks: '61', cost_micros: '96140000' },
      },
    ]),
  };

  for (const nome of derrubar) {
    consultas[nome] = falhou(
      'GoogleAdsException: PERMISSION_DENIED — a credencial não alcança este recurso nesta conta',
    );
  }

  return {
    _meta: {
      lido_em_utc: LIDO_EM,
      customer_id: CONTA,
      login_customer_id: '6016739364',
      versao_api: 'v25',
      janela_das_metricas: 'LAST_30_DAYS',
      modo_de_escrita: 'travado',
      somente_leitura: true,
    },
    consultas,
  };
}

function grupo(campanha: string, id: string, nome: string): LinhaDaConsulta {
  return {
    campaign: { id: campanha },
    ad_group: {
      id,
      name: nome,
      status: 'ENABLED',
      primary_status: 'ELIGIBLE',
      primary_status_reasons: [],
      type: 'SEARCH_STANDARD',
      cpc_bid_micros: '2500000',
    },
  };
}

function anuncio(campanha: string, grupoId: string, adId: string): LinhaDaConsulta {
  return {
    campaign: { id: campanha },
    ad_group: { id: grupoId },
    ad_group_ad: {
      status: 'ENABLED',
      primary_status: 'ELIGIBLE',
      ad_strength: 'GOOD',
      policy_summary: { approval_status: 'APPROVED', review_status: 'REVIEWED' },
      ad: {
        id: adId,
        type: 'RESPONSIVE_SEARCH_AD',
        final_urls: ['https://creditoup.com.br/r/fgts-saque-aniversario/'],
      },
    },
  };
}

function keyword(
  campanha: string,
  grupoId: string,
  criterio: string,
  texto: string,
): LinhaDaConsulta {
  return {
    campaign: { id: campanha },
    ad_group: { id: grupoId },
    ad_group_criterion: {
      criterion_id: criterio,
      keyword: { text: texto, match_type: 'PHRASE' },
      status: 'ENABLED',
      primary_status: 'ELIGIBLE',
      approval_status: 'APPROVED',
      system_serving_status: 'ELIGIBLE',
      effective_cpc_bid_micros: '2500000',
      quality_info: { quality_score: 6 },
    },
  };
}
