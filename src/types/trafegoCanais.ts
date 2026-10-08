/**
 * A configuração de cada canal Google Ads na criação — o espelho TS do contrato
 * `docs/contracts/GADS-CRIACAO-CANAIS-v1.md` (§6).
 *
 * ## De onde vêm estes tipos
 *
 * O servidor publica o JSON Schema de cada configuração em
 * `GET /api/trafego/canais/esquema`, gerado dos MESMOS dataclasses do motor que
 * julgam o pedido em `/provar` e `/subir` (`volc_ads/campanha/*_config.py`).
 * Os tipos abaixo existem para o compilador; os enums em `as const` existem
 * porque um union TS precisa de uma fonte literal. Na tela, as opções e os
 * limites são lidos do esquema vivo quando ele chegou — ver
 * `src/lib/trafego/canais/esquema.ts` — e estas listas são só o recuo.
 *
 * ⚠️ Ausente (`undefined`/`null`) = o comportamento de antes, byte a byte.
 * Objeto presente entra na impressão aprovável do plano.
 */

// ═══════════════════════════════════════════════════════════════════════════
// Vocabulário comum
// ═══════════════════════════════════════════════════════════════════════════

export const DIAS_DA_SEMANA = [
  'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY',
] as const;
export type DiaDaSemana = typeof DIAS_DA_SEMANA[number];

export const DISPOSITIVOS = ['MOBILE', 'TABLET', 'DESKTOP'] as const;
export type Dispositivo = typeof DISPOSITIVOS[number];

export const CATEGORIAS_DE_CONVERSAO = [
  'DEFAULT', 'PAGE_VIEW', 'PURCHASE', 'SIGNUP', 'DOWNLOAD', 'ADD_TO_CART',
  'BEGIN_CHECKOUT', 'SUBSCRIBE_PAID', 'PHONE_CALL_LEAD', 'IMPORTED_LEAD',
  'SUBMIT_LEAD_FORM', 'BOOK_APPOINTMENT', 'REQUEST_QUOTE', 'GET_DIRECTIONS',
  'OUTBOUND_CLICK', 'CONTACT', 'ENGAGEMENT', 'STORE_VISIT', 'STORE_SALE',
  'QUALIFIED_LEAD', 'CONVERTED_LEAD', 'YOUTUBE_FOLLOW_ON_VIEWS', 'IN_APP_AD_REVENUE',
] as const;
export type CategoriaDeConversao = typeof CATEGORIAS_DE_CONVERSAO[number];

export const ORIGENS_DE_CONVERSAO = [
  'WEBSITE', 'GOOGLE_HOSTED', 'APP', 'CALL_FROM_ADS', 'STORE', 'YOUTUBE_HOSTED',
  'LOCAL_SERVICES_ADS',
] as const;
export type OrigemDeConversao = typeof ORIGENS_DE_CONVERSAO[number];

// ═══════════════════════════════════════════════════════════════════════════
// Search — `configuracao_search`
// ═══════════════════════════════════════════════════════════════════════════

/** `MAXIMIZE_CLICKS` não existe: o nome da API é `TARGET_SPEND`. */
export const ESTRATEGIAS_SEARCH = [
  'MANUAL_CPC', 'TARGET_SPEND', 'MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE',
  'TARGET_IMPRESSION_SHARE',
] as const;
export type EstrategiaSearch = typeof ESTRATEGIAS_SEARCH[number];

export const LOCAIS_DE_IMPRESSAO = [
  'ANYWHERE_ON_PAGE', 'TOP_OF_PAGE', 'ABSOLUTE_TOP_OF_PAGE',
] as const;
export type LocalDeImpressao = typeof LOCAIS_DE_IMPRESSAO[number];

export interface LanceSearch {
  estrategia: EstrategiaSearch;
  target_cpa?: number | null;
  /** Razão (4.0 = 400%). */
  target_roas?: number | null;
  teto_cpc?: number | null;
  local_impressao?: LocalDeImpressao | null;
  /** 0.6 = 60%. */
  fracao_impressao?: number | null;
}

export interface RedeSearch {
  google_search: true;
  parceiros: boolean;
  display_expansion: boolean;
}

export interface AiMaxSearch {
  correspondencia_de_termos: boolean;
  personalizacao_de_texto: boolean;
  expansao_de_url_final: boolean;
  grupos_sem_correspondencia?: string[];
  exclusoes_de_url?: string[];
  listas_de_marca_incluidas?: string[];
  listas_de_marca_excluidas?: string[];
  termos_excluidos?: string[];
  restricoes_de_mensagem?: string[];
}

export const POSICOES_DE_FIXACAO = [
  'HEADLINE_1', 'HEADLINE_2', 'HEADLINE_3', 'DESCRIPTION_1', 'DESCRIPTION_2',
] as const;
export type PosicaoDeFixacao = typeof POSICOES_DE_FIXACAO[number];

export interface Fixacao { texto: string; posicao: PosicaoDeFixacao }

export interface AnuncioSearch {
  path1?: string;
  path2?: string;
  fixacoes?: Fixacao[];
}

export interface FaixaDeHorario {
  dia: DiaDaSemana;
  /** HH:MM, minutos 00/15/30/45. */
  inicio: string;
  /** HH:MM (24:00 = fim do dia). */
  fim: string;
  /** bid_modifier (1.2 = +20%); só em MANUAL_CPC/TARGET_SPEND. */
  ajuste?: number | null;
}

export interface AjusteDeDispositivo {
  dispositivo: Dispositivo;
  /** 0 exclui o dispositivo; senão entre 0.1 e 10.0. */
  fator: number;
}

export const TIPOS_GEO_POSITIVO = ['PRESENCE', 'PRESENCE_OR_INTEREST', 'SEARCH_INTEREST'] as const;
export type TipoGeoPositivo = typeof TIPOS_GEO_POSITIVO[number];
export const TIPOS_GEO_NEGATIVO = ['PRESENCE', 'PRESENCE_OR_INTEREST'] as const;
export type TipoGeoNegativo = typeof TIPOS_GEO_NEGATIVO[number];

export interface SegmentacaoGeo {
  tipo_positivo: TipoGeoPositivo;
  tipo_negativo: TipoGeoNegativo;
  /** ids de geoTargetConstant do país do brief; vazio = o país. */
  locais?: number[];
  locais_excluidos?: number[];
  /** Precisa conter o idioma do brief. */
  idiomas?: string[];
}

export interface MetaDeCategoriaSearch {
  categoria: CategoriaDeConversao;
  origem: OrigemDeConversao;
  lance: boolean;
}

export interface MetaDeConversaoSearch {
  meta_personalizada?: string | null;
  acoes_de_conversao?: string[];
  categorias?: MetaDeCategoriaSearch[];
}

export interface ConfiguracaoSearch {
  lance?: LanceSearch | null;
  rede?: RedeSearch | null;
  ai_max?: AiMaxSearch | null;
  anuncio?: AnuncioSearch | null;
  programacao?: FaixaDeHorario[];
  dispositivos?: AjusteDeDispositivo[];
  geo?: SegmentacaoGeo | null;
  /** AAAA-MM-DD. */
  inicio?: string | null;
  fim?: string | null;
  meta_de_conversao?: MetaDeConversaoSearch | null;
}

/** `{chave(texto): match}` — só troca a correspondência de keyword aprovada. */
export type MatchPorKeyword = Record<string, 'EXACT' | 'PHRASE' | 'BROAD'>;

// ═══════════════════════════════════════════════════════════════════════════
// Display — `configuracao_display`
// ═══════════════════════════════════════════════════════════════════════════

export const ESTRATEGIAS_DISPLAY = [
  'MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE', 'TARGET_SPEND', 'MANUAL_CPC', 'MANUAL_CPM',
] as const;
export type EstrategiaDisplay = typeof ESTRATEGIAS_DISPLAY[number];

export interface LanceDisplay {
  estrategia: EstrategiaDisplay;
  teto_cpc?: number | null;
  cpm_visivel?: number | null;
}

export interface SegmentacaoDisplay {
  listas_de_usuarios?: string[];
  publicos_personalizados?: string[];
  publicos_combinados?: string[];
  interesses?: string[];
  topicos?: string[];
  placements?: string[];
  palavras_chave?: string[];
  publicos_em_observacao?: boolean;
  segmentacao_otimizada?: boolean;
}

export const ROTULOS_DE_CONTEUDO = [
  'SEXUALLY_SUGGESTIVE', 'BELOW_THE_FOLD', 'PARKED_DOMAIN', 'JUVENILE', 'PROFANITY',
  'TRAGEDY', 'VIDEO', 'VIDEO_RATING_DV_G', 'VIDEO_RATING_DV_PG', 'VIDEO_RATING_DV_T',
  'VIDEO_RATING_DV_MA', 'VIDEO_NOT_YET_RATED', 'EMBEDDED_VIDEO', 'LIVE_STREAMING_VIDEO',
  'SOCIAL_ISSUES', 'BRAND_SUITABILITY_CONTENT_FOR_FAMILIES',
] as const;
export type RotuloDeConteudo = typeof ROTULOS_DE_CONTEUDO[number];

/** O padrão de nascimento (`ROTULOS_PADRAO` no motor) — recuo quando o esquema
 *  vivo não chegou. O default real é o que o esquema declara. */
export const ROTULOS_PADRAO_DISPLAY: RotuloDeConteudo[] = [
  'PARKED_DOMAIN', 'SEXUALLY_SUGGESTIVE', 'PROFANITY', 'TRAGEDY', 'SOCIAL_ISSUES', 'JUVENILE',
];

export interface ListaDeExclusaoNova {
  nome: string;
  placements?: string[];
  apps?: string[];
  categorias_de_app?: string[];
}

export interface ExclusoesDisplay {
  placements?: string[];
  apps?: string[];
  categorias_de_app?: string[];
  excluir_todos_os_apps?: boolean;
  rotulos_de_conteudo?: RotuloDeConteudo[];
  topicos?: string[];
  listas_existentes?: string[];
  lista_nova?: ListaDeExclusaoNova | null;
}

export const UNIDADES_DE_FREQUENCIA = ['DAY', 'WEEK', 'MONTH'] as const;
export type UnidadeDeFrequencia = typeof UNIDADES_DE_FREQUENCIA[number];
export const NIVEIS_DE_FREQUENCIA = ['AD_GROUP_AD', 'AD_GROUP', 'CAMPAIGN'] as const;
export type NivelDeFrequencia = typeof NIVEIS_DE_FREQUENCIA[number];

export interface FrequenciaMaxima {
  impressoes: number;
  unidade?: UnidadeDeFrequencia;
  nivel?: NivelDeFrequencia;
}

export interface JanelaDeVeiculacao {
  dia: DiaDaSemana;
  inicio_hora: number;
  fim_hora: number;
  inicio_minuto?: 0 | 15 | 30 | 45;
  fim_minuto?: 0 | 15 | 30 | 45;
}

export const FORMATOS_RDA = ['ALL_FORMATS', 'NATIVE', 'NON_NATIVE'] as const;
export type FormatoRda = typeof FORMATOS_RDA[number];

export interface AnuncioDisplay {
  chamada_para_acao?: string | null;
  cor_principal?: string | null;
  cor_destaque?: string | null;
  cores_flexiveis?: boolean;
  formato?: FormatoRda;
  videos_youtube?: string[];
  melhorias_de_asset?: boolean;
  video_automatico?: boolean;
}

export const PRESENCAS_GEO_DISPLAY = ['PRESENCE', 'PRESENCE_OR_INTEREST'] as const;
export type PresencaGeoDisplay = typeof PRESENCAS_GEO_DISPLAY[number];

export interface ConfiguracaoDisplay {
  lance?: LanceDisplay | null;
  segmentacao?: SegmentacaoDisplay;
  exclusoes?: ExclusoesDisplay;
  frequencia?: FrequenciaMaxima[];
  agenda?: JanelaDeVeiculacao[];
  dispositivos_excluidos?: Dispositivo[];
  presenca_geo?: PresencaGeoDisplay;
  anuncio?: AnuncioDisplay;
}

// ═══════════════════════════════════════════════════════════════════════════
// Demand Gen — `configuracao_demand_gen` (só a parte v25; a base segue em `demand_gen`)
// ═══════════════════════════════════════════════════════════════════════════

export const FORMATOS_DEMAND_GEN = ['MULTI_ASSET', 'VIDEO_RESPONSIVO', 'CARROSSEL'] as const;
export type FormatoDemandGen = typeof FORMATOS_DEMAND_GEN[number];

export const ESTRATEGIAS_DEMAND_GEN = [
  'MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE', 'TARGET_SPEND', 'TARGET_CPC',
] as const;
export type EstrategiaDemandGen = typeof ESTRATEGIAS_DEMAND_GEN[number];

export interface LanceDemandGen {
  estrategia: EstrategiaDemandGen;
  target_cpa?: number | null;
  target_roas?: number | null;
  target_cpc?: number | null;
}

export const CTAS_DEMAND_GEN = [
  'Saiba Mais', 'Inscreva-se', 'Inscrever-se', 'Reservar', 'Fale conosco', 'Visitar site',
  'Comprar agora', 'Ver mais', 'Learn more', 'Learn More', 'Apply now', 'Book now',
  'Contact us', 'Download', 'Visit site', 'Shop now', 'Sign up', 'Get quote', 'Subscribe',
  'See more', 'Get offer', 'Call now',
] as const;

export const CTAS_VIDEO_DEMAND_GEN = [
  'LEARN_MORE', 'GET_QUOTE', 'APPLY_NOW', 'SIGN_UP', 'CONTACT_US', 'SUBSCRIBE', 'DOWNLOAD',
  'BOOK_NOW', 'SHOP_NOW', 'BUY_NOW', 'DONATE_NOW', 'ORDER_NOW', 'PLAY_NOW', 'SEE_MORE',
  'START_NOW', 'VISIT_SITE', 'WATCH_NOW',
] as const;

export interface VideoDemandGen {
  youtube_ids: string[];
  call_to_action?: string | null;
  breadcrumb1?: string | null;
  breadcrumb2?: string | null;
}

export const EXPANSOES_LOOKALIKE = ['NARROW', 'BALANCED', 'BROAD'] as const;
export type ExpansaoLookalike = typeof EXPANSOES_LOOKALIKE[number];

export interface LookalikeDemandGen {
  nome: string;
  sementes: number[];
  expansao: ExpansaoLookalike;
  paises: string[];
}

export const IDADES_DEMAND_GEN = ['18-24', '25-34', '35-44', '45-54', '55-64', '65+'] as const;
export const GENEROS_DEMAND_GEN = ['MALE', 'FEMALE'] as const;
export const RENDAS_DEMAND_GEN = [
  'INCOME_RANGE_0_50', 'INCOME_RANGE_50_60', 'INCOME_RANGE_60_70', 'INCOME_RANGE_70_80',
  'INCOME_RANGE_80_90', 'INCOME_RANGE_90_UP',
] as const;
export const STATUS_PARENTAIS_DEMAND_GEN = ['PARENT', 'NOT_A_PARENT'] as const;

export interface PublicoDemandGen {
  nome: string;
  user_lists?: string[];
  lookalikes?: LookalikeDemandGen[];
  exclusoes_user_list?: string[];
  idades?: string[];
  incluir_idade_indeterminada?: boolean;
  generos?: string[];
  incluir_genero_indeterminado?: boolean;
  rendas?: string[];
  incluir_renda_indeterminada?: boolean;
  status_parentais?: string[];
  incluir_status_parental_indeterminado?: boolean;
}

export const AUTOMACOES_DEMAND_GEN_POR_FORMATO: Record<FormatoDemandGen, readonly string[]> = {
  MULTI_ASSET: [
    'GENERATE_DESIGN_VERSIONS_FOR_IMAGES', 'GENERATE_VIDEOS_FROM_OTHER_ASSETS',
    'GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS',
  ],
  VIDEO_RESPONSIVO: [
    'GENERATE_LANDING_PAGE_PREVIEW', 'GENERATE_LANDING_PAGE_TEXT',
    'GENERATE_SHORTER_YOUTUBE_VIDEOS', 'GENERATE_VERTICAL_YOUTUBE_VIDEOS',
  ],
  CARROSSEL: [],
};

export type StatusDeAutomacao = 'OPTED_IN' | 'OPTED_OUT';

export interface FaixaDeAgendaDemandGen {
  dia: DiaDaSemana;
  inicio: string;
  fim: string;
}

export interface ConfiguracaoDemandGenV25 {
  formato?: FormatoDemandGen;
  lance?: LanceDemandGen | null;
  call_to_action?: string | null;
  video?: VideoDemandGen | null;
  /** Indisponível pela fronteira HTTP (§3 do contrato): a tela nunca o envia. */
  carrossel?: null;
  publico?: PublicoDemandGen | null;
  segmentacao_otimizada?: boolean | null;
  automacoes?: Record<string, StatusDeAutomacao>;
  agenda?: FaixaDeAgendaDemandGen[];
}

// ═══════════════════════════════════════════════════════════════════════════
// Performance Max — `configuracao_pmax` (só a parte v25; a base segue em `pmax`)
// ═══════════════════════════════════════════════════════════════════════════

export interface OpcoesDeUrl {
  sufixo_extra?: [string, string][];
  tracking_url_template?: string;
  parametros_personalizados?: [string, string][];
}

export interface VideoYouTube { video_id: string; nome?: string }

export const TIPOS_DE_SINAL = ['audience', 'search_theme'] as const;
export type TipoDeSinal = typeof TIPOS_DE_SINAL[number];
export interface SinalDeAudiencia { tipo: TipoDeSinal; valor: string }

export interface TextosPMax {
  headlines: string[];
  long_headlines: string[];
  descriptions: string[];
}

export interface AssetGroupPMax {
  nome: string;
  url_final: string;
  textos: TextosPMax;
  /** Envelopes de asset no MESMO formato de `assets_pmax`. */
  imagens: import('./trafego').AssetDemandGen[];
  /** `[]` = sem dica (escolha); `null` = ninguém escolheu (recusado). */
  sinais: SinalDeAudiencia[] | null;
  videos?: VideoYouTube[];
  path1?: string;
  path2?: string;
  opcoes_de_url?: OpcoesDeUrl | null;
}

export const AUTOMACOES_PMAX = [
  'FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION', 'TEXT_ASSET_AUTOMATION',
  'GENERATE_IMAGE_ENHANCEMENT', 'GENERATE_ENHANCED_YOUTUBE_VIDEOS',
  'GENERATE_IMAGE_EXTRACTION', 'AUTOMATED_VIDEO_CRAWL', 'GENERATE_DESIGN_VERSIONS_FOR_IMAGES',
] as const;
export type AutomacaoPMax = typeof AUTOMACOES_PMAX[number];

export const PLATAFORMAS_DE_VIDEO_CRAWL = ['LANDING_PAGE', 'SOCIAL', 'YOUTUBE'] as const;
export type PlataformaDeVideoCrawl = typeof PLATAFORMAS_DE_VIDEO_CRAWL[number];

export interface FonteDeVideoCrawl {
  url: string;
  plataforma: PlataformaDeVideoCrawl;
  habilitada?: boolean;
}

export const OPERANDOS_DE_EXCLUSAO_URL = ['URL', 'PAGE_TITLE', 'PAGE_CONTENT'] as const;
export const OPERADORES_DE_EXCLUSAO_URL = ['CONTAINS', 'EQUALS'] as const;

export interface ExclusaoDeUrl {
  nome: string;
  argumento: string;
  operando?: typeof OPERANDOS_DE_EXCLUSAO_URL[number];
  operador?: typeof OPERADORES_DE_EXCLUSAO_URL[number];
}

export const FONTES_DE_MARCA = [
  '', 'Open Sans', 'Roboto', 'Montserrat', 'Poppins', 'Lato', 'Oswald',
  'Playfair Display', 'Roboto Slab',
] as const;

export interface DiretrizesDeMarca {
  cor_principal?: string;
  cor_destaque?: string;
  fonte?: typeof FONTES_DE_MARCA[number];
}

export const MATCH_TYPES_NEGATIVA_PMAX = ['BROAD', 'PHRASE', 'EXACT'] as const;
export interface NegativaPMax {
  texto: string;
  match_type?: typeof MATCH_TYPES_NEGATIVA_PMAX[number];
}

export interface MarcaExcluida { entity_id: string; nome?: string }

export interface MetaDeConversaoPMax {
  categoria: CategoriaDeConversao;
  origem: OrigemDeConversao;
  biddable: boolean;
}

export const MODOS_CLIENTE_NOVO = ['TARGET_ALL', 'TARGET_SPECIFIC'] as const;
export interface MetaClienteNovo {
  goal: string;
  modo: typeof MODOS_CLIENTE_NOVO[number];
  valor_adicional?: number | null;
  multiplicador_de_valor?: number | null;
}

export interface ConfiguracaoPMaxV25 {
  path1?: string;
  path2?: string;
  opcoes_de_url?: OpcoesDeUrl | null;
  videos?: VideoYouTube[];
  grupos_adicionais?: AssetGroupPMax[];
  automacoes_optadas?: AutomacaoPMax[];
  video_crawl?: FonteDeVideoCrawl[];
  video_crawl_direitos_declarados?: boolean;
  exclusoes_de_url?: ExclusaoDeUrl[];
  termos_excluidos?: string[];
  restricoes_de_mensagem?: string[];
  diretrizes_de_marca?: DiretrizesDeMarca | null;
  negativas_tipadas?: NegativaPMax[];
  listas_de_negativas?: string[];
  marcas_excluidas?: MarcaExcluida[];
  listas_de_marcas_excluidas?: string[];
  metas_de_conversao?: MetaDeConversaoPMax[];
  meta_cliente_novo?: MetaClienteNovo | null;
}

// ═══════════════════════════════════════════════════════════════════════════
// O esquema publicado e o 422
// ═══════════════════════════════════════════════════════════════════════════

/** JSON Schema draft 2020-12, como o servidor o publica. Aberto de propósito. */
export interface EsquemaJson {
  type?: string | string[];
  properties?: Record<string, EsquemaJson>;
  required?: string[];
  additionalProperties?: boolean | EsquemaJson;
  propertyNames?: EsquemaJson;
  items?: EsquemaJson;
  prefixItems?: EsquemaJson[];
  enum?: unknown[];
  const?: unknown;
  anyOf?: EsquemaJson[];
  oneOf?: EsquemaJson[];
  not?: EsquemaJson;
  $ref?: string;
  $defs?: Record<string, EsquemaJson>;
  default?: unknown;
  description?: string;
  title?: string;
  pattern?: string;
  format?: string;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  uniqueItems?: boolean;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  'x-volc-indisponivel-por-http'?: boolean;
  [chave: string]: unknown;
}

export type CanalDeConfiguracao = 'SEARCH' | 'DISPLAY' | 'DEMAND_GEN' | 'PERFORMANCE_MAX';

export interface EsquemaDosCanais {
  versao: string;
  documento: string;
  canais: Record<CanalDeConfiguracao, {
    campo_http: string;
    entra_no_motor_como: string;
    esquema: EsquemaJson;
  }>;
  regras: string[];
}

/** Um item do `detail[]` do 422 do FastAPI — o formato do contrato §2. */
export interface ErroDeCorpo422 {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
  ctx?: { codigo?: string; caminho?: string; [k: string]: unknown };
}
