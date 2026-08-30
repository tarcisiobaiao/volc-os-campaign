import type {
  AssetDemandGen,
  ConfiguracaoDemandGen,
  PedidoDeProva,
  PedidoDeProvaDemandGen,
  PedidoDeProvaSearch,
} from '../../../types/trafego';

const configuracaoDemandGen: ConfiguracaoDemandGen = {
  upgraded_targeting: true,
  controles_de_canal: {
    estrategia: 'ALL_CHANNELS',
    selected_channels: null,
  },
  audiencias: [],
  intencoes: [],
  exclusoes_de_audiencia: [],
};

const assetDemandGen: AssetDemandGen = {
  tipo: 'imagem_marketing',
  nome: 'paisagem-aprovada',
  dados_base64: 'aW1hZ2Vt',
  conteudo_hash: 'sha256:abc123',
  origem: 'gerado',
  procedencia: {
    motor: 'fixture-hermetica',
    versao_do_motor: '1',
    insumo: 'paisagem para prova tipada',
    quando: '2026-08-29T12:00:00+00:00',
    pedido: 'pedido hermetico',
    custo_usd: null,
  },
};

const pedidoSearch: PedidoDeProvaSearch = {
  opportunity_id: 73,
  customer_id: '8017851692',
  login_customer_id: '6016739364',
  run_id: 6,
  grupos: [{ tipo: 'ACESSO', keywords: ['saque anual fgts'] }],
  copy: {
    headlines: ['Saque Anual 2026'],
    descriptions: ['Veja regras, prazos e limites.'],
    sitelinks: [],
    callouts: [],
    snippet: null,
  },
  budget_diario: 10,
  cpc_inicial: 0.12,
  match_type: 'PHRASE',
  canal: 'SEARCH',
  estrategia_lance: 'MANUAL_CPC',
  graduacao_em_conversoes: 30,
  criterios: [],
  vertical: 'informativo',
  certificacoes: [],
  url_final: 'https://creditoup.com.br/r/saque-anual/',
};

const pedidoSearchLegado: PedidoDeProva = {
  opportunity_id: 65,
  customer_id: '5478096539',
  login_customer_id: '6016739364',
  grupos: [{ tipo: 'SAQUE', keywords: ['consultar fgts'] }],
  budget_diario: 20,
  cpc_inicial: 1,
  match_type: 'PHRASE',
};

const pedidoDemandGen: PedidoDeProvaDemandGen = {
  opportunity_id: 88,
  customer_id: '8017851692',
  login_customer_id: '6016739364',
  run_id: null,
  copy: {
    headlines: ['Entenda o beneficio'],
    descriptions: ['Veja regras, prazos e condicoes.'],
    business_name: 'VOLC',
    sitelinks: [],
    callouts: [],
    snippet: null,
  },
  budget_diario: 10,
  canal: 'DEMAND_GEN',
  estrategia_lance: 'MAXIMIZE_CONVERSIONS',
  demand_gen: configuracaoDemandGen,
  assets_demand_gen: [assetDemandGen],
  vertical: 'informativo',
  certificacoes: [],
  url_final: 'https://creditoup.com.br/r/saque-anual/',
};

const pedidos: PedidoDeProva[] = [
  pedidoSearch,
  pedidoSearchLegado,
  pedidoDemandGen,
];

function resumoTipado(pedido: PedidoDeProva): string {
  if (pedido.canal === 'DEMAND_GEN') {
    const estrategia: 'MAXIMIZE_CONVERSIONS' = pedido.estrategia_lance;
    return [
      estrategia,
      pedido.demand_gen.upgraded_targeting,
      pedido.assets_demand_gen.length,
    ].join(':');
  }
  const cpc: number = pedido.cpc_inicial;
  const matchType: string = pedido.match_type;
  return `${matchType}:${cpc}`;
}

pedidos.map(resumoTipado);

const searchComCampoDemandGen: PedidoDeProvaSearch = {
  ...pedidoSearch,
  // @ts-expect-error Search nao aceita o envelope vertical Demand Gen.
  demand_gen: configuracaoDemandGen,
};

const searchComAssetsDemandGen: PedidoDeProvaSearch = {
  ...pedidoSearch,
  // @ts-expect-error assets_demand_gen vazio ou cheio pertence a Demand Gen.
  assets_demand_gen: [assetDemandGen],
};

const demandGenComCpcSearch: PedidoDeProvaDemandGen = {
  ...pedidoDemandGen,
  // @ts-expect-error Demand Gen nao aceita CPC inicial Search.
  cpc_inicial: 0.12,
};

const demandGenComMatchTypeSearch: PedidoDeProvaDemandGen = {
  ...pedidoDemandGen,
  // @ts-expect-error Demand Gen nao aceita match_type Search.
  match_type: 'PHRASE',
};

const demandGenComEstrategiaSearch: PedidoDeProvaDemandGen = {
  ...pedidoDemandGen,
  // @ts-expect-error Demand Gen nasce apenas em MAXIMIZE_CONVERSIONS.
  estrategia_lance: 'MANUAL_CPC',
};

void searchComCampoDemandGen;
void searchComAssetsDemandGen;
void demandGenComCpcSearch;
void demandGenComMatchTypeSearch;
void demandGenComEstrategiaSearch;
