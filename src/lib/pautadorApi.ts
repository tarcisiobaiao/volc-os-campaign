// ============================================
// PAUTADOR PRO — cliente HTTP do backend FastAPI
// O backend é um SEGUNDO projeto Vercel (root /backend). A URL base vem de
// VITE_PAUTADOR_API_URL (ex: https://pautador-api.vercel.app). Em dev local:
// http://localhost:8000.
// ============================================

import type {
  DiscoveryResponse,
  FunnelResult,
  KeywordCluster,
  MineResult,
  Opportunity,
  OpportunityStatus,
  PautadorCountry,
} from '@/types/pautador';
import type { ValidacaoRelatorio } from '@/types/pautadorValidacao';
import type { TesesResposta } from '@/types/pautadorOportunidade';
import type {
  ClickupDispatch,
  EntityCard,
  EntityDiscoveryParams,
  EntityDiscoveryResponse,
  EntityFunnelResponse,
  EntityListResponse,
  EntityMeta,
  EntityMineResponse,
  EntityStatusUpdateResult,
  PautadorNiche,
  QuestionChoicePayload,
} from '@/types/pautadorEntity';

import { supabase } from '@/lib/supabase';

const RAW_BASE = (import.meta.env.VITE_PAUTADOR_API_URL || '').trim();
const API_BASE = RAW_BASE.replace(/\/$/, ''); // sem barra final

// ---------------------------------------------------------------------------
// AUTENTICAÇÃO — sessão do Supabase, não chave compartilhada
// ---------------------------------------------------------------------------
// Até 24/08/2026 este arquivo lia `VITE_PAUTADOR_API_KEY` e a enviava como
// `X-API-Key`. Era a MESMA chave que servia de portão para 24 rotas do backend,
// e tudo que começa com `VITE_` é substituído pelo VALOR LITERAL no build:
// "colocar no .env" não escondia nada, publicava. Bastava abrir o DevTools para
// levar o portão inteiro. O próprio comentário que estava aqui admitia o
// problema — "é uma barreira simples, não um segredo forte" — e um segredo que
// se sabe frágil e se publica mesmo assim não é barreira, é adiamento.
//
// Agora vai o access token da sessão do usuário logado. Não é segredo
// compartilhado: identifica UMA pessoa, expira, é renovado pelo `supabase-js` e
// o backend o valida contra o Supabase antes de olhar o papel.
//
// SEM FALLBACK ANÔNIMO. Sem sessão, a chamada falha aqui, antes da rede.

/**
 * Cabeçalho `Authorization` da sessão atual.
 *
 * Seguro chamar `getSession()` aqui: estas funções nascem de interação na tela,
 * nunca de dentro de um callback de `onAuthStateChange` — onde `getSession()`
 * trava o lock do `auth-js` (ver `src/contexts/AuthContext.tsx`).
 */
/**
 * Busca um recurso com credencial e devolve um `blob:` URL.
 *
 * É a ponte entre "o navegador não manda cabeçalho em navegação de topo" e "a
 * rota exige identidade". O `blob:` vale só nesta aba, nesta sessão, e some
 * quando alguém chama `URL.revokeObjectURL`.
 */
async function baixarComoBlobUrl(caminho: string): Promise<string> {
  if (!API_BASE) {
    throw new PautadorApiError('VITE_PAUTADOR_API_URL não configurada.', 0);
  }
  const resp = await fetch(url(caminho), { headers: await autorizacao() });
  if (!resp.ok) {
    throw new PautadorApiError(
      resp.status === 401
        ? 'Sua sessão expirou. Entre novamente para ver este arquivo.'
        : `Não foi possível carregar o arquivo (${resp.status}).`,
      resp.status,
    );
  }
  return URL.createObjectURL(await resp.blob());
}

async function autorizacao(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) {
    throw new PautadorApiError('Sessão expirada. Faça login novamente.', 401);
  }
  return { Authorization: `Bearer ${token}` };
}

import type {
  PerfilPublicacao, PerfilEntrada, ResultadoTesteConexao, ProjetoDestino,
  DisparoDoRedator, ProvaVisual, ReleituraDoWordPress, RunDoRedator,
  PublicacaoDePagina,
} from '@/types/publicacao';
import type { RespostaDosCanais } from '@/lib/trafego/canais';
import type { PlanoVigenteResposta } from '@/lib/trafego/portoes';
import type { MatrizDoRun, RespostaDaMatriz } from '@/types/redator';
import type { FunilEscrito } from '@/types/redatorPaginas';
import type { ConfiguracaoDoRedator, QuadroDoRedator } from '@/types/redatorQuadro';
import type {
  CampanhaCanonica, CapacidadesDoOperador, FiltrosDoInventario, Inventario,
  RevisaoDeCorrespondencia, VocabularioDoInventario,
  Cockpit, EscopoDeContas, EscritaDaCopy, EstadoDaTrava, PedidoDeCopy,
  CopyGerada, CopyPersistida, VereditoDePolitica, VerticalDePolitica,
  PedidoDeProva, PedidoDeProvaSearch, ProjetoComConta, QuadroDeAlertas, QuadroDeTrafego,
  RespostaDaCopy, RespostaDaProva, ReciboDeLancamento,
  PedidoDePlanejamentoPMax, RespostaDoPlanejamentoPMax,
  RevisaoDoConjuntoPago, AprovacaoDoConjuntoPago,
} from '@/types/trafego';
import type { RespostaDoDiagnostico } from '@/types/diagnostico';
import type { RespostaDoDecisionLab } from '@/types/inteligenciaDecisao';
import type { GraphStatusLive, InboxLive, InboxReceipt, InboxTriage, WorkRoadExecutionsLive, WorkRoadLive } from '@/features/work-road/live';

export interface DiscoveryParams {
  country: string;
  country_code?: string;
  native_language?: string;
  count?: number;
  engine?: string;
  model?: string;
  persist?: boolean;
}

export class PautadorApiError extends Error {
  status: number;
  /** O `detail` cru do FastAPI, quando ele é um OBJETO e não uma frase.
   *
   *  `/subir` devolve `{mensagem, preparo}` no 409 para a escada de lançamento
   *  mostrar QUAL juiz reprovou sem repetir `/provar` — que é a chamada mais
   *  lenta do fluxo. Sem este campo, o veredito morreria virando string. */
  corpo?: unknown;
  constructor(message: string, status: number, corpo?: unknown) {
    super(message);
    this.name = 'PautadorApiError';
    this.status = status;
    this.corpo = corpo;
  }
}

export interface EstadoDaConfiguracaoMetaLocal {
  configurado: boolean;
  armazenamento: 'macOS Keychain' | 'Cofre oficial';
  api_version: 'v26.0';
  salvo_em?: string;
}

export interface ResultadoDoTesteMetaLocal {
  ok: true;
  configurado?: boolean;
  api_version: 'v26.0';
  salvo_em?: string;
  ator: { nome: string; id_mascarado: string | null };
  contas: ContaMetaLocal[];
  contas_acessiveis: number;
}

export interface ContaMetaLocal {
  referencia_opaca: string;
  nome: string;
  id_mascarado: string | null;
  status: string | null;
  moeda: string | null;
  fuso: string | null;
  prontidao_leitura: 'READY_FOR_READ';
  business: { id_mascarado: string | null; nome: string | null } | null;
}

export interface ResultadoDasContasMetaLocal {
  ok: true;
  api_version: 'v26.0';
  armazenamento: 'macOS Keychain' | 'Cofre oficial';
  contas: ContaMetaLocal[];
  contas_acessiveis: number;
  proxima_acao: 'preflight_somente_leitura';
}

/** O estado de uma conversão, tal como `trafego/meta/dominio.py` o fecha.
 *
 * ⚠️ `UNKNOWN` NÃO é um quarto sabor de "disponível": é a resposta que a Meta
 * não permitiu concluir. `ESTADOS_DE_CONVERSAO` o lista ao lado de
 * `UNKNOWN_FRESHNESS` (disparou, mas não se sabe quando) e de `INVALID` (o
 * contrato do item quebrou) — e a União anterior OMITIA os três. Omitir na
 * tipagem é como o desconhecido vira "disponível" na tela: o `switch` não tem
 * ramo para ele, o default cai no otimista, e um item que ninguém classificou
 * aparece elegível para otimização. */
export type EstadoDaConversaoMeta =
  /** Disponível, sem eixo de frescor — é o estado dos catálogos de público e
   *  de geolocalização (`ESTADOS_DE_PUBLICO`, `ESTADOS_DE_GEOLOCALIZACAO`). */
  | 'AVAILABLE'
  | 'AVAILABLE_FIRED'
  | 'AVAILABLE_NEVER_FIRED'
  | 'UNKNOWN_FRESHNESS'
  | 'ARCHIVED'
  | 'UNAVAILABLE'
  | 'UNKNOWN'
  | 'INVALID';

export interface ConversaoPersonalizadaMetaLocal {
  referencia_opaca: string;
  id_mascarado: string | null;
  nome: string;
  custom_event_type: string | null;
  event_source_type: string | null;
  event_source_id_mascarado: string | null;
  first_fired_time: string | null;
  last_fired_time: string | null;
  estado: EstadoDaConversaoMeta;
  /** A razão fechada do desconhecimento, quando o estado é `UNKNOWN`. */
  motivo_desconhecido?: string | null;
}

// ⚠️ Quem decide se um estado pode ser OFERECIDO é
// `components/trafego/meta/conversoes.ts`, e é lá de propósito: elegibilidade e
// frescor são dois eixos, com palavra, glifo e descrição próprios. Duplicar a
// regra aqui criaria duas fontes que divergiriam no primeiro estado novo.

/** O mesmo vocabulário serve públicos, lugares e fontes de mensuração:
 *  `ESTADOS_DE_PUBLICO` e `ESTADOS_DE_GEOLOCALIZACAO` são subconjuntos do que
 *  `ESTADOS_DE_CONVERSAO` já lista. Um alias, e não uma segunda união, porque
 *  duas uniões divergiriam no primeiro estado novo do provedor. */
export type EstadoDeItemDeCatalogoMeta = EstadoDaConversaoMeta;

// ═══════════════════════════════════════════════════════════════════════════
// CATÁLOGOS SELECIONÁVEIS — o envelope, e por que ele não pode ser achatado
//
// ⚠️ `A11`: `[]` completo, permissão negada, timeout, página truncada e leitura
// vencida são CINCO respostas diferentes. Um `items: []` sozinho colapsa todas
// em "vazio", e o operador conclui que apagaram o público dele. O envelope
// carrega os cinco separados, e a tela é obrigada a distingui-los.
//
// ⚠️ `estado_do_catalogo` é um eixo ORTOGONAL a `estado`: uma leitura pode ter
// itens E estar vencida. Fundir os dois num selo só esconderia a idade da lista
// exatamente quando ela importa.
// ═══════════════════════════════════════════════════════════════════════════

export type EstadoDoCatalogoMeta =
  | 'COM_ITENS' | 'VAZIO_COMPLETO' | 'PARCIAL' | 'INDISPONIVEL';

export type FrescorDoCatalogoMeta = 'VIGENTE' | 'OBSOLETO';

export interface EnvelopeDeCatalogoMeta<T> {
  ok: boolean;
  catalogo: string;
  api_version: string;
  referencia_opaca_da_conta: string;
  estado: EstadoDoCatalogoMeta;
  /** Código da causa quando `INDISPONIVEL` ou `PARCIAL`. Nunca prosa livre. */
  motivo: string | null;
  /** `true` = tentar de novo pode resolver. `false` = falta acesso. */
  retryable: boolean;
  items: T[];
  total: number;
  /** Itens que vieram malformados. Contados, não escondidos. */
  invalidos: number;
  desconhecidos: number;
  /** `false` = existe mais do que você está vendo. */
  completo: boolean;
  paginas_lidas: number;
  observado_em: string;
  ttl_s: number;
  expira_em: string;
  estado_do_catalogo: FrescorDoCatalogoMeta;
}

export interface PublicoDoCatalogoMeta {
  referencia_opaca: string;
  id_mascarado: string | null;
  nome: string;
  /** CUSTOM, LOOKALIKE, WEBSITE… o que a Meta mandar, sem invenção. */
  subtype: string | null;
  delivery_status_code: number | null;
  operation_status_code: number | null;
  tamanho_aproximado_min: number | null;
  tamanho_aproximado_max: number | null;
  estado: EstadoDeItemDeCatalogoMeta;
  motivo_desconhecido?: string | null;
}

export interface LugarDoCatalogoMeta {
  /** ⚠️ A CHAVE CANÔNICA do compilador. Texto digitado jamais vira uma destas. */
  key: string | null;
  name: string | null;
  type: string | null;
  country_code: string | null;
  region: string | null;
  supports_region: boolean | null;
  supports_city: boolean | null;
  estado: EstadoDeItemDeCatalogoMeta;
  motivo_desconhecido?: string | null;
}

export interface FonteDeMensuracaoMeta {
  referencia_opaca: string;
  id_mascarado: string | null;
  nome: string;
  /** ⚠️ `PIXEL` e `DATASET` são objetos DIFERENTES na Meta. `UNKNOWN` é "a
   *  resposta não disse qual", e não pode virar nenhum dos dois. */
  source_kind: 'PIXEL' | 'DATASET' | 'UNKNOWN';
  last_fired_time: string | null;
  estado: EstadoDeItemDeCatalogoMeta;
  motivo_desconhecido?: string | null;
}

export interface CatalogoDeMensuracaoMeta {
  ok: true;
  /** ⚠️ Dois envelopes, e a separação é o contrato: pixel e conversão
   *  personalizada são objetos distintos, e uma lista só faria o seletor de
   *  otimização oferecer um no lugar do outro. */
  fontes: EnvelopeDeCatalogoMeta<FonteDeMensuracaoMeta>;
  conversoes: EnvelopeDeCatalogoMeta<ConversaoPersonalizadaMetaLocal>;
}

export interface ResultadoDoPreflightMetaLocal {
  ok: true;
  api_version: 'v26.0';
  referencia_opaca: string;
  conta: ContaMetaLocal;
  contagens: Record<string, number | null>;
  estados: { readiness: string; persistencia: 'NAO_PERSISTIDO' };
  capacidades_disponiveis: string[];
  capacidades_ausentes: string[];
  frescor: string;
  paginas_lidas: number;
  erros: Array<{ capability: string; codigo: string; mensagem: string }>;
  mensuracao: {
    pixels_ou_datasets: number | null;
    conversoes_personalizadas: ConversaoPersonalizadaMetaLocal[];
  };
  proxima_acao: string;
}

export interface ReciboMetaReadModel {
  ok: boolean;
  conta_opaca?: string;
  contagens?: Record<string, number | null>;
  paginas_lidas?: number;
  snapshot_hash?: string;
  observado_em?: string;
  escrita?: 'bloqueada' | 'executada';
  repetido?: boolean;
  run_id?: string | null;
  proxima_acao?: string;
}

export interface InventarioMetaPersistido<T = Record<string, unknown>> {
  ok: true;
  has_snapshot: boolean;
  entidade?: string;
  items?: T[];
  item?: T | null;
  contas?: T[];
  recibo?: T | null;
  motivo?: string;
  /** O estado de prontidão do read model. Ver `EstadoDoReadModelMeta`. */
  estado?: string;
}

// ---------------------------------------------------------------------------
// READ MODEL META — o contrato ESCOPADO (backend/app/trafego/meta/read_model.py)
// ---------------------------------------------------------------------------
//
// ⚠️ AUSÊNCIA AQUI TEM SEIS NOMES, E NENHUM DELES É LISTA VAZIA.
//
// `listar()` no servidor devolve SEMPRE `ok: true` — inclusive quando o
// Supabase está fora, quando as tabelas nunca foram criadas e quando a conta
// pedida não existe no snapshot. Um cliente que tipasse a resposta como
// `{ items: T[] }` transformaria as três em "esta conta não tem campanhas", que
// é a única leitura que o servidor NUNCA fez. O estado viaja junto do dado
// justamente para que a tela não possa perdê-lo, e por isso ele é obrigatório
// no tipo — não opcional.

/**
 * Os estados de prontidão que o read model Meta devolve.
 *
 * Os quatro primeiros aparecem em qualquer leitura; `ESCOPO_*` só nas entidades
 * que exigem conta; `NAO_ENCONTRADO_*` só no detalhe de um objeto.
 */
export type EstadoDoReadModelMeta =
  | 'COM_SNAPSHOT'
  | 'SEM_SNAPSHOT'
  | 'SCHEMA_NAO_APLICADO'
  | 'SEM_CONEXAO'
  | 'ESCOPO_OBRIGATORIO'
  | 'ESCOPO_DESCONHECIDO'
  | 'NAO_ENCONTRADO_NO_ESCOPO'
  | 'NAO_ENCONTRADO_ESCOPO_PARCIAL';

/** As sete entidades projetadas. `conjuntos`, `anuncios` e `vinculos` exigem conta. */
export type EntidadeMetaReadModel =
  | 'campanhas'
  | 'conjuntos'
  | 'anuncios'
  | 'criativos'
  | 'vinculos'
  | 'insights'
  | 'mensuracao';

/** As entidades que respondem `ESCOPO_OBRIGATORIO` sem `conta_ref`. */
export const ENTIDADES_META_QUE_EXIGEM_CONTA: ReadonlySet<string> = new Set([
  'conjuntos',
  'anuncios',
  'vinculos',
]);

/**
 * Uma conta no read model.
 *
 * ⚠️ `type` e não `interface`: `MetaReadPreview` guarda esta resposta numa
 * variável tipada como `InventarioMetaPersistido<Record<string, unknown>>`, e o
 * TypeScript só concede a assinatura de índice implícita a apelidos de tipo.
 * Trocar por `interface` quebra aquele arquivo sem que nada aqui mude.
 */
export type ContaMetaReadModel = {
  cofre_ativo_id?: string | null;
  /** Referência opaca da conta — é ela que viaja como `conta_ref`. */
  conta_ref?: string | null;
  id_mascarado?: string | null;
  nome_observado?: string | null;
  moeda?: string | null;
  timezone_name?: string | null;
  account_status?: string | null;
  readiness_state?: string | null;
  observado_em?: string | null;
  ultima_leitura_ok_em?: string | null;
};

/**
 * Uma linha de qualquer das sete entidades.
 *
 * Todos os campos são opcionais porque cada tabela traz os seus; a assinatura de
 * índice existe para que uma coluna nova no servidor não derrube a tela. O
 * identificador cru da Meta NÃO está aqui de propósito: ele é removido no
 * servidor, e `entity_ref` + `id_mascarado` são a única identidade pública.
 */
export type ItemMetaReadModel = {
  entity_ref?: string | null;
  id_mascarado?: string | null;
  meta_campaign_id?: string | null;
  meta_adset_id?: string | null;
  meta_ad_id?: string | null;
  meta_creative_id?: string | null;
  ad_account_ativo_id?: string | null;
  nome?: string | null;
  status?: string | null;
  effective_status?: string | null;
  objetivo?: string | null;
  optimization_goal?: string | null;
  object_story_id?: string | null;
  observado_em?: string | null;
  ultima_vez_visto_em?: string | null;
  /** insights */
  nivel?: string | null;
  periodo_inicio?: string | null;
  periodo_fim?: string | null;
  janela_atribuicao?: string | null;
  currency?: string | null;
  completo?: boolean | null;
  spend?: number | string | null;
  impressions?: number | null;
  reach?: number | null;
  frequency?: number | string | null;
  clicks?: number | null;
  inline_link_clicks?: number | null;
  landing_page_views?: number | null;
  cpm?: number | string | null;
  cpc?: number | string | null;
  ctr?: number | string | null;
  /** mensuração */
  measurement_type?: string | null;
  observed_count?: number | null;
  [campo: string]: unknown;
};

export type ContasDoReadModelMeta = InventarioMetaPersistido<ContaMetaReadModel> & {
  estado: EstadoDoReadModelMeta;
  contas: ContaMetaReadModel[];
};

/**
 * Uma PÁGINA de uma entidade — e a página sabe dizer que é página.
 *
 * `completo` responde "isto é tudo que existe neste escopo?" e `has_more`
 * responde "existe próxima página?". As duas são diferentes: o escopo pode ter
 * sido truncado no servidor (`motivo: ESCOPO_PAI_TRUNCADO`) mesmo quando não há
 * próxima página a pedir.
 */
export type PaginaMetaReadModel<T = ItemMetaReadModel> = {
  ok: true;
  has_snapshot: boolean;
  estado: EstadoDoReadModelMeta;
  entidade: string;
  conta_ref: string | null;
  moeda?: string | null;
  fuso?: string | null;
  /** `ultima_leitura_ok_em` da conta, em ISO 8601 — não uma palavra. */
  frescor?: string | null;
  items: T[];
  completo: boolean;
  has_more: boolean;
  proximo_cursor: string | null;
  motivo: string | null;
};

/** Por que um total é o que é. Um número sozinho não diz se ele é completo. */
export type RazaoDaSomaMeta = {
  conjuntos: number;
  dias: number;
  conjuntos_atribuidos: number;
  /** Contagens por LINHA do grão (conjunto/dia), não por conjunto. */
  linhas: number;
  linhas_atribuidas: number;
  linhas_sem_utm: number;
  linhas_sem_leitura_gam: number;
  linhas_sem_entrega: number;
  spend_completo: boolean;
  revenue_completo: boolean;
};

/** O financeiro de UM conjunto no período. É o grão em que a receita foi medida. */
export type ConjuntoFinanceiroMeta = {
  /** Referência opaca do read model. O id bruto nunca chega ao navegador. */
  adset_ref: string;
  id_mascarado: string | null;
  spend: string | number | null;
  revenue_original: string | number | null;
  revenue_brl: string | number | null;
  impressions: number | null;
  clicks: number | null;
  inline_link_clicks?: number | null;
  landing_page_views?: number | null;
  gam_impressions: number | null;
  gam_clicks: number | null;
  /** Sempre null: alcance não soma entre linhas. */
  reach: null;
  ctr: string | number | null;
  cpc: string | number | null;
  landing_page_load_rate_pct?: string | number | null;
  cost_per_landing_page_view?: string | number | null;
  gam_impressions_per_landing_page_view?: string | number | null;
  roas_ratio: string | number | null;
  profit_gross: string | number | null;
  retorno_excedente_pct: string | number | null;
  currency: string | null;
  timezone: string | null;
  source: string;
  source_freshness: string | null;
  revenue_freshness: string | null;
  razao: RazaoDaSomaMeta;
};

/** Reconciliação com a leitura campaign-level. DIAGNÓSTICO, nunca parcela. */
export type ReconciliacaoMeta = {
  reconciliado: boolean | null;
  motivo: string | null;
  spend_conjuntos: string | number | null;
  spend_campanha: string | number | null;
  diferenca: string | number | null;
};

export type EvidenciaFinanceiraMeta = {
  state: 'INCOMPLETE' | 'PROVISIONAL' | 'UNRECONCILED' | 'OBSERVED_COMPLETE';
  reasons: string[];
  economic_basis: 'gam_revenue_brl_minus_meta_spend';
  other_costs: 'NOT_MODELED';
  informational_only: true;
};

/** Insights do anúncio no mesmo período, sem atribuição de receita GAM. */
export type AnuncioFinanceiroMeta = {
  ad_ref: string;
  adset_ref: string;
  spend: string | number | null;
  impressions: number | null;
  clicks: number | null;
  ctr: string | number | null;
  cpc: string | number | null;
  cpm: string | number | null;
  source_freshness: string | null;
  completo: boolean;
};

export type FinanceiroMeta = {
  ok: boolean;
  estado: string;
  /** O grão em que a receita foi medida. 'adset' desde 08/09/2026. */
  grao?: string;
  contrato?: string;
  currency: string | null;
  timezone: string | null;
  periodo_inicio: string | null;
  periodo_fim: string | null;
  provisorio: boolean;
  frescor: string | null;
  receita_frescor?: string | null;
  /** Decimal do servidor viaja como string; number mantém compatibilidade de projeções. */
  spend: string | number | null;
  revenue: string | number | null;
  revenue_original?: string | number | null;
  profit_gross: string | number | null;
  roas_ratio: string | number | null;
  retorno_excedente_pct: string | number | null;
  /** Já eram calculados no servidor e não tinham onde aparecer. */
  impressions?: number | null;
  clicks?: number | null;
  inline_link_clicks?: number | null;
  landing_page_views?: number | null;
  ctr?: string | number | null;
  cpc?: string | number | null;
  landing_page_load_rate_pct?: string | number | null;
  cost_per_landing_page_view?: string | number | null;
  gam_impressions_per_landing_page_view?: string | number | null;
  gam_impressions?: number | null;
  gam_clicks?: number | null;
  contribution_observed?: string | number | null;
  evidence?: EvidenciaFinanceiraMeta | null;
  spend_completo: boolean;
  revenue_completo: boolean;
  conjuntos_conhecidos?: number;
  /** O drill-down: a campanha é a soma destes. */
  conjuntos?: ConjuntoFinanceiroMeta[];
  anuncios?: AnuncioFinanceiroMeta[];
  anuncios_completo?: boolean;
  anuncios_impedimentos?: string[];
  razao?: RazaoDaSomaMeta | null;
  reconciliacao?: ReconciliacaoMeta | null;
  fontes?: Record<string, string>;
  impedimentos: string[];
};

export type DetalheMetaReadModel<T = ItemMetaReadModel> = {
  ok: true;
  has_snapshot: boolean;
  estado: EstadoDoReadModelMeta;
  entidade: string;
  item: T | null;
  conta_ref?: string | null;
  motivo?: string | null;
};

/** Escopo, cursor e tamanho de uma leitura paginada. */
export interface OpcoesDeLeituraMeta {
  contaRef?: string | null;
  cursor?: string | null;
  tamanho?: number | null;
}

export interface PublicacaoExistenteMeta {
  reuse_supported?: boolean;
  reuse_reason?: string;
  preview_only?: boolean;
  copy_variants?: {messages: string[]; headlines: string[]; descriptions: string[]};
  post_ref: string; asset_ref: string; label: string; creative_name: string;
  source_ad_names: string[]; destination_url: string; call_to_action_type: string;
  message: string; headline: string; description: string; preview_url: string | null;
  /** Flexible ads remain reusable by their immutable post identity. These
   * counts describe the original post; the UI must not imply it picked one
   * of its placement/copy variants to recreate. */
  is_flexible?: boolean; image_variants?: number; text_variants?: number;
}

export interface AtivoCriacaoMeta {
  referencia_opaca: string;
  nome: string;
  tipo: 'page' | 'image_asset' | 'video_asset';
  id_mascarado: string | null;
  largura: number | null;
  altura: number | null;
  preview_disponivel: boolean;
}

export interface InventarioCriacaoMeta {
  ok: true;
  api_version: 'v26.0';
  account_ref: string;
  conta: ContaMetaLocal;
  paginas: AtivoCriacaoMeta[];
  imagens: AtivoCriacaoMeta[];
  /** Vídeos existentes da conta. Leitura apenas: a emissão de criativo de
   *  vídeo continua bloqueada enquanto a miniatura não tiver caminho provado. */
  videos: AtivoCriacaoMeta[];
  receita: string;
}

export interface PlanoMetaPausadoInput {
  account_ref: string;
  page_ref: string;
  asset_ref: string;
  campaign_name: string;
  adset_name: string;
  creative_name: string;
  ad_name: string;
  destination_url: string;
  message: string;
  headline: string;
  description: string;
  daily_budget_minor: number;
  start_time: string;
  special_ad_categories: string[];
  special_categories_confirmed: boolean;
  is_adset_budget_sharing_enabled: boolean;
  /** Desde a v23.0 a Meta assume 1 quando o campo não viaja: a escolha é sempre explícita. */
  advantage_audience: boolean;
  call_to_action_type: string;
  asset_rights_confirmed: boolean;
  third_party_identity_cleared: boolean;
  asset_policy_confirmed_at: string | null;
  variations?: Array<{
    variation_key: string;
    asset_ref: string;
    creative_name: string;
    ad_name: string;
    message: string;
    headline: string;
    description: string;
    call_to_action_type: string;
    asset_rights_confirmed: boolean;
    third_party_identity_cleared: boolean;
    asset_policy_confirmed_at: string | null;
  }>;
}

export interface ResultadoCompilacaoMeta {
  ok: true;
  efeito_externo: 'NENHUM';
  plano: {
    account_ref: string;
    destination_url: string;
    api_version: 'v26.0';
    plano_sha256: string;
    estado_ao_nascer: 'PAUSED';
    tracking?: { revenue_join: string; url_tags: Array<string | null> };
    operacoes: Array<{
      nome: string;
      tipo?: 'campaign' | 'adset' | 'creative' | 'ad';
      endpoint: string;
      depende_de: string[];
      validavel_sem_criar_pai: boolean;
      status: 'PAUSED' | null;
    }>;
  };
}

export interface ResultadoValidacaoPlanoMeta {
  ok: boolean;
  cobertura: 'INDEPENDENT_ROOTS_ONLY';
  operacoes_validadas: string[];
  operacoes_dependentes_pendentes: string[];
  plano_sha256: string;
  objetos_criados: 0;
  /** O recibo durável da validação, gravado pelo SERVIDOR.
   *
   * Sem `validation_id` não existe aprovação: a rota de aprovação recusa uma
   * referência que o banco não conhece. Isso é o que impede o navegador de
   * inventar o próprio recibo verde — e é por isso que `registrada: false`
   * precisa aparecer na tela, e não ser engolido. */
  prova_duravel: {
    registrada: boolean;
    validation_id?: string;
    validated_at?: string;
    motivo?: string;
    codigo?: string;
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// CONTRATO V2 — campanha + N conjuntos + N anúncios
//
// ⚠️ Estes tipos são a TRANSCRIÇÃO literal de `PedidoPlanoMetaV2` e vizinhos em
// `backend/app/routers/trafego_meta_validacao.py`. O DTO é `extra="forbid"`:
// um campo a mais volta 422 nomeando o campo. Por isso nada aqui é opcional
// "por conveniência" — o que o servidor aceita como ausente é `| null`, e o que
// ele exige não tem `?`.
// ═══════════════════════════════════════════════════════════════════════════

export interface OrcamentoMetaV2Input {
  nivel: 'ADSET' | 'CAMPAIGN';
  periodo: 'DAILY' | 'LIFETIME';
  /** Unidade MENOR da moeda — centavos para BRL. Reais aqui fariam R$10,00
   *  virar dez centavos, e o erro só apareceria na fatura. */
  amount_minor: number;
  currency: 'BRL';
}

export interface GeografiaMetaV2Input {
  countries: string[];
  region_keys: string[];
  city_keys: string[];
  zip_keys: string[];
  custom_locations: Array<{
    latitude: number; longitude: number; radius: number;
    distance_unit: 'kilometer' | 'mile';
  }>;
  excluded_countries: string[];
  excluded_region_keys: string[];
  excluded_city_keys: string[];
  excluded_zip_keys: string[];
}

export interface PublicoMetaV2Input {
  mode: 'BROAD' | 'MANUAL' | 'EXISTING_CUSTOM' | 'EXISTING_LOOKALIKE';
  geo: GeografiaMetaV2Input;
  age_min: number;
  age_max: number;
  locale_refs: string[];
  include_custom_refs: string[];
  exclude_custom_refs: string[];
  lookalike_refs: string[];
  interest_refs: string[];
  /** ⚠️ SEM `?`, e isso é o contrato. O DTO não tem default porque a Meta
   *  assume 1 quando o campo não viaja: omitir LIGA a expansão de público. */
  expansion: boolean;
}

export interface TextosFlexiveisMetaV2Input {
  primary_text: string[];
  headline: string[];
  description: string[];
}

export interface ConjuntoMetaV2Input {
  adset_key: string;
  /** Textos independentes das imagens, exclusivos deste conjunto flexível. */
  flexible_texts?: TextosFlexiveisMetaV2Input;
  regulatory_identity_ref?: string | null;
  name: string;
  start_time: string;
  end_time: string | null;
  audience: PublicoMetaV2Input;
  placements: { mode: 'FACEBOOK_ONLY' | 'MANUAL'; values: string[] };
  measurement: {
    purpose: 'REPORT_ONLY' | 'OPTIMIZE';
    source_kind: 'PIXEL' | 'DATASET' | null;
    source_ref: string | null;
    custom_conversion_ref: string | null;
    standard_event: string | null;
  };
  /** Presente só em ABO. Em CBO precisa ser `null`: os dois níveis juntos são
   *  409 META_BUDGET_DUPLICATED. */
  budget: OrcamentoMetaV2Input | null;
}

export interface AnuncioMetaV2Input {
  existing_post_ref?: string;
  variation_key: string;
  /** ⚠️ A ligação explícita com o conjunto. Sem ela o backend recusa com
   *  META_AD_ADSET_UNKNOWN em vez de adivinhar um pai. */
  adset_key: string;
  asset_ref: string;
  creative_name: string;
  ad_name: string;
  message: string;
  headline: string;
  description: string;
  call_to_action_type: string;
  asset_rights_confirmed: boolean;
  third_party_identity_cleared: boolean;
  asset_policy_confirmed_at: string | null;
}

export interface PlanoMetaV2Input {
  creative_mode?: 'STATIC' | 'FLEXIBLE_IMAGES';
  recipe_id: string;
  account_ref: string;
  page_ref: string;
  instagram_actor_ref: string | null;
  campaign_name: string;
  destination_url: string;
  /** Presente só em CBO; em ABO precisa ser `null`. */
  campaign_budget: OrcamentoMetaV2Input | null;
  special_ad_categories: string[];
  special_categories_confirmed: boolean;
  is_adset_budget_sharing_enabled: boolean;
  adsets: ConjuntoMetaV2Input[];
  ads: AnuncioMetaV2Input[];
}

/** Capacidade implementada, não autorização para enviar este plano. */
export interface CapacidadePausadaMeta {
  implementada: boolean;
  fluxo: string;
  estado_ao_nascer: string;
  autoriza_ativacao: boolean;
  exige_recibo_exato_do_plano: boolean;
  cobertura_previa: string;
  dependentes_validados_antes_de_criar: boolean;
  exige_aprovacao_humana: boolean;
  exige_capacidades_do_servidor: boolean;
  exige_prova_de_destino: boolean;
  prova_historica_nao_e_capacidade: boolean;
}

export interface ModoDeOrcamentoMetaV2 {
  id: string;
  nivel: 'ADSET' | 'CAMPAIGN';
  periodo: 'DAILY' | 'LIFETIME';
  prova: string;
  capacidade_pausada?: CapacidadePausadaMeta;
  /** Evidência histórica legada; não substitui a capacidade nem a aprovação. */
  criar_liberado: boolean;
}

export interface ReceitaMetaV2 {
  id: string;
  rotulo: string;
  descricao: string;
  objetivo: string;
  otimizacao: string;
  exige_fonte_de_conversao: boolean;
  propositos_de_mensuracao: Array<'REPORT_ONLY' | 'OPTIMIZE'>;
  prova: string;
  capacidade_pausada?: CapacidadePausadaMeta;
  /** Evidência histórica legada; não substitui a capacidade nem a aprovação. */
  criar_liberado: boolean;
  motivo_sem_prova: string | null;
  modos_de_orcamento: ModoDeOrcamentoMetaV2[];
}

export interface CatalogoDeReceitasMeta {
  ok: true;
  api_version: 'v26.0';
  receita_padrao: string;
  receitas: ReceitaMetaV2[];
  limites: {
    conjuntos: number;
    anuncios_por_conjunto: number;
    anuncios_total: number;
    classificacao: string;
  };
  idade: { min: number; max: number; motivo: string };
}

/** O resumo que a REVISÃO renderiza. Ele é a autoridade: `A33`/`F37` cobram que
 *  rascunho e resumo não possam divergir, e a única forma de garantir isso é a
 *  tela não ter outra fonte além desta. */
export interface ResumoDoPlanoMetaV2 {
  receita: {
    id: string; rotulo: string; objetivo: string; otimizacao: string; prova: string;
  };
  orcamento: {
    nivel: 'ADSET' | 'CAMPAIGN';
    periodo: 'DAILY' | 'LIFETIME';
    modo: string;
    prova: string;
    onde_a_verba_mora: string;
  };
  conjuntos: Array<{
    adset_key: string;
    nome: string;
    orcamento_minor: number | null;
    publico_modo: string;
    publicos_incluidos: number;
    publicos_excluidos: number;
    expansao_advantage: boolean;
    /** ⚠️ A frase de `A16` sai DAQUI. `false` proíbe a tela de dizer que só o
     *  público selecionado será alcançado. */
    promete_alcance_exclusivo: boolean;
    posicionamentos: string[];
    mensuracao_proposito: string;
    mensuracao_altera_entrega: boolean;
    anuncios: string[];
  }>;
  bloqueios_para_criar: string[];
}

export interface ResultadoCompilacaoMetaV2 extends ResultadoCompilacaoMeta {
  contrato: 'V2';
  resumo: ResumoDoPlanoMetaV2;
}

export interface ResultadoValidacaoPlanoMetaV2 extends ResultadoValidacaoPlanoMeta {
  contrato: 'V2';
  cobertura_explicada: string;
  resumo: ResumoDoPlanoMetaV2;
}

/** O que a tela precisa mostrar antes de existir qualquer objeto na conta. */
export interface AprovacaoCriacaoMeta {
  approval_id: string;
  plano_sha256: string;
  expires_at: string;
  operacoes: number;
  manifesto: string[];
  orcamento_diario_minor: number | null;
  budget_manifest?: {
    version: 1; scope: 'ABO' | 'CBO'; currency: 'BRL';
    entries: Array<{step: string; level: 'campaign' | 'adset'; period: 'DAILY' | 'LIFETIME'; amount_minor: number; currency: string}>;
    daily_total_minor: number | null;
  };
  moeda: 'BRL';
  nascimento_pausado_confirmado: true;
}

export interface ResultadoAprovacaoCriacaoMeta {
  ok: true;
  efeito_externo: 'NENHUM';
  aprovacao: AprovacaoCriacaoMeta;
}

/** O read-back SANITIZADO gravado no livro, exatamente como o backend o
 *  produziu: vocabulário fechado, valores curtos, nenhum identificador. A RPC
 *  de gravação RECUSA qualquer chave que pareça id, e é por isso que este
 *  objeto pode atravessar até o navegador. */
export interface EvidenciaDeLeituraMeta {
  /** `true` = a leitura conferiu o objeto contra o aprovado. `false` = existe e
   *  divergiu. Ausente é um terceiro caso: ninguém leu. */
  matched: boolean;
  tipo: string;
  status: string | null;
  effective_status: string | null;
  objective?: string | null;
  optimization_goal?: string | null;
  advantage_audience_lido?: number | null;
}

/** Um passo do recibo durável. NUNCA carrega o id da Meta — só a afirmação
 *  de que ele existe, e agora também o que a leitura de volta encontrou. */
export interface PassoDoReciboMeta {
  name: string;
  state: 'IN_FLIGHT' | 'CREATED' | 'AMBIGUOUS' | 'FAILED';
  has_external_id: boolean;
  error_code: string | null;
  /** Divergência de leitura sobre um objeto que EXISTE. Diferente de erro. */
  readback_error?: string | null;
  prepared_at?: string | null;
  closed_at?: string | null;
  /** ⚠️ QUANDO a leitura foi gravada. `null` não é "não veicula": é "ninguém
   *  conferiu", e a tela precisa das duas palavras diferentes. */
  readback_at?: string | null;
  readback_evidence?: EvidenciaDeLeituraMeta | null;
  /** A mesma conclusão que o banco deriva. A tela a recalcula dos fatos crus;
   *  este campo existe para quem não pode recalcular. */
  readback_confirmed?: boolean;
  /** Quantos ids um trabalhador SEM autoridade viu neste passo. O número
   *  denuncia a ambiguidade; os ids nunca saem do servidor. */
  observed_external_id_count?: number;
}

export interface ReciboCriacaoMeta {
  approval_id: string;
  plan_sha256: string;
  capability: 'META_CREATE_PAUSED';
  state: string;
  expires_at: string;
  /** ⚠️ O MANIFESTO APROVADO, em ordem. É o DENOMINADOR — e a razão de ele
   *  existir aqui é que `steps` só lista o que já apareceu no livro. Contar
   *  sobre `steps` foi o defeito que exibiu "1 de 1" para uma campanha de
   *  quatro objetos. */
  steps_expected?: string[];
  operations_expected?: number;
  daily_budget_minor?: number;
  currency?: string;
  paused_birth_confirmed?: boolean;
  steps: PassoDoReciboMeta[];
}

/** O read-back sanitizado de um objeto recém-criado. Sem id, sem payload. */
export interface LeituraDeVoltaMeta {
  veiculavel: boolean;
  status: string | null;
  effective_status: string | null;
  objective?: string | null;
  optimization_goal?: string | null;
  advantage_audience_lido?: number | null;
}

export interface ResultadoCriacaoPausadaMeta {
  ok: true;
  desfecho: 'CREATED_PAUSED';
  plano_sha256: string;
  /** Referências opacas `metaobj_…`, jamais o identificador da Meta. */
  referencias_opacas: Record<string, string>;
  read_back: Record<string, LeituraDeVoltaMeta>;
  recibo: ReciboCriacaoMeta;
  retry_permitido: false;
}

export interface ConclusaoDaReconciliacaoMeta {
  passo: string;
  tipo: string;
  conclusao: 'FECHADO_COMO_CRIADO' | 'FECHADO_COMO_NAO_ENCONTRADO' | 'PERMANECE_AMBIGUO';
  explicacao: string;
}

export interface ResultadoReconciliacaoMeta {
  ok: true;
  efeito_externo: 'NENHUM';
  passos_ambiguos: number;
  /** Passos ainda em voo: jovens demais para serem promovidos, e que NÃO podem
   *  ser escondidos — silenciá-los devolveria "nada travado" sobre um despacho
   *  sem conclusão. */
  passos_em_voo?: string[];
  /** Órfãos que esta chamada tornou visíveis. Promover não despacha nada. */
  passos_promovidos?: string[];
  conclusoes: ConclusaoDaReconciliacaoMeta[];
  recibo: ReciboCriacaoMeta;
}

export interface ResultadoReciboCriacaoMeta {
  ok: true;
  recibo: ReciboCriacaoMeta;
}

function url(path: string): string {
  return `${API_BASE}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) {
    throw new PautadorApiError(
      'VITE_PAUTADOR_API_URL não configurada. Configure a URL do backend Pautador Pro.',
      0,
    );
  }
  let resp: Response;
  try {
    // ⚠️ `Content-Type` só entra quando o corpo REALMENTE é JSON.
    //
    // Antes ele era injetado sempre. Um corpo `FormData` precisa que o
    // navegador escreva `multipart/form-data; boundary=…` sozinho, e o
    // `boundary` só existe no momento do envio: fixar o cabeçalho aqui produz
    // um multipart sem fronteira, que o servidor recusa como corpo malformado.
    // Sobrescrever também não resolve — passar `undefined` num objeto de
    // cabeçalhos vira a string "undefined". A saída é NÃO declarar, e é o que
    // `baixarComoBlobUrl` já fazia por não ter corpo nenhum.
    // Só o corpo que o navegador precisa rotular sozinho perde o cabeçalho; um
    // GET ou um POST com JSON continua exatamente como estava.
    const corpo = init?.body;
    const oNavegadorRotula = typeof FormData !== 'undefined' && corpo instanceof FormData;
    resp = await fetch(url(path), {
      ...init,
      headers: {
        ...(oNavegadorRotula ? {} : { 'Content-Type': 'application/json' }),
        ...(await autorizacao()),
        ...(init?.headers || {}),
      },
    });
  } catch (err) {
    // fetch() throws on a dropped connection OR a blocked CORS preflight — the
    // browser can't tell them apart, so name both likely causes + the URL.
    throw new PautadorApiError(
      `Não foi possível conectar ao backend Pautador Pro em ${API_BASE}. ` +
        `Verifique: (1) o backend está rodando nessa porta; ` +
        `(2) VITE_PAUTADOR_API_URL aponta para o backend certo; ` +
        `(3) CORS libera a origem do front (PAUTADOR_ALLOWED_ORIGINS).`,
      0,
    );
  }
  if (!resp.ok) {
    let detail = '';
    let corpo: unknown;
    try {
      const body = await resp.json();
      const d = body?.detail;
      if (d && typeof d === 'object') {
        // FastAPI aceita objeto em `detail`, e `/subir` usa isso para mandar o
        // preparo junto do 409. Sem este ramo, o `||` abaixo cairia no
        // `JSON.stringify` e o veredito chegaria à tela como texto colado.
        corpo = d;
        detail = String((d as { mensagem?: string }).mensagem || '') || JSON.stringify(d);
      } else {
        detail = d || JSON.stringify(body);
      }
    } catch {
      /* sem corpo JSON */
    }
    const s = resp.status;
    let msg: string;
    if (s === 401 || (s === 403 && !detail)) {
      // Nada de "confira sua API key": ela não existe mais, e mandar o
      // operador procurar um segredo aposentado é enviá-lo para o lugar errado.
      msg = s === 401
        ? 'Sua sessão expirou ou não foi reconhecida. Entre novamente.'
        : 'Sua conta não tem permissão para esta operação. Fale com um administrador.';
    } else if (s === 403) {
      // ⚠️ 403 COM `detail` não é problema de credencial: é o portão de escopo
      // do Hub de Tráfego dizendo que a conta pedida não é da casa. Traduzir
      // isso para "confira sua API key" manda o operador mexer na chave certa
      // procurando um defeito que está noutro lugar — o mesmo tipo de
      // diagnóstico errado que `_ponte()` documenta no backend.
      msg = detail;
    } else if (s === 404) {
      msg = `Endpoint não encontrado (404) em ${API_BASE}. VITE_PAUTADOR_API_URL pode apontar para outro serviço.`;
    } else if (s === 502 || s === 503 || s === 504) {
      msg = `Backend indisponível (${s}).${detail ? ' ' + detail : ''}`;
    } else if (s >= 500) {
      // 5xx detail carrega a causa real (ex.: "Falha no motor de descoberta: ..." Gemini/Supabase)
      msg = detail || `Erro interno do backend (${s}).`;
    } else {
      msg = detail || `Erro ${s}.`;
    }
    throw new PautadorApiError(msg, s, corpo);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export interface RevisaoMidiaMeta {
  ok: boolean;
  resultados: Array<{master_ref: string; content_sha256: string; aprovacao_humana: boolean;
    utilizavel: boolean; codigo: string | null; politica: {decisao: string; motivos: unknown[];
      achados?: Array<{termo: string}>; detectores?: Array<{nome: string; resultado: string}>}}>;
}
export interface RegistroMidiaMeta {
  ok: boolean;
  resultados: Array<{master_ref: string; estado: string; asset_ref: string | null; motivo: string | null; codigo: string | null}>;
}

export const pautadorApi = {
  revisarMidiaMeta(accountRef: string, masterRefs: string[]): Promise<RevisaoMidiaMeta> {
    return request('/api/trafego/meta/ativos/revisar', { method: 'POST',
      body: JSON.stringify({ account_ref: accountRef, master_refs: masterRefs }) });
  },
  capacidadesMidiaMeta(accountRef: string, draftRef?: string, masterRefs: string[] = []): Promise<{registro_de_imagem: string; motivo: string | null; escopo_do_envio?: string; autorizacao_expira_em?: string; inspecao_de_imagem: {disponivel: boolean; capacidades_ausentes: string[]}}> {
    const query = new URLSearchParams({account_ref: accountRef});
    if (draftRef) { query.set('draft_ref', draftRef); query.set('master_refs', masterRefs.join(',')); }
    return request(`/api/trafego/meta/ativos/capacidades?${query}`);
  },
  registrarMidiaMeta(accountRef: string, revisoes: RevisaoMidiaMeta['resultados'], draftRef?: string): Promise<RegistroMidiaMeta> {
    return request('/api/trafego/meta/ativos/registrar', { method: 'POST', body: JSON.stringify({
      account_ref: accountRef, master_refs: revisoes.map(r => r.master_ref),
      ...(draftRef ? {draft_ref: draftRef} : {}),
      revisoes: revisoes.map(({master_ref, content_sha256}) => ({master_ref, content_sha256})),
      confirmar_registro_na_conta: accountRef, confirmar_quantidade: revisoes.length,
    }) });
  },
  planejarGestaoMeta(pedido: import('@/types/metaOperacao').PedidoGestaoMeta): Promise<import('@/types/metaOperacao').PropostaGestaoMeta> {
    return request('/api/trafego/meta/local/gestao/planejar', { method: 'POST', body: JSON.stringify(pedido) });
  },
  trackingAutomaticoMeta(destinationUrl: string): Promise<import('@/types/metaOperacao').TrackingAutomaticoMeta> {
    return request(`/api/trafego/meta/local/criacao/tracking?${new URLSearchParams({ destination_url: destinationUrl })}`);
  },
  get baseUrl() {
    return API_BASE;
  },
  get configured() {
    return Boolean(API_BASE);
  },

  estadoMetaLocal(): Promise<EstadoDaConfiguracaoMetaLocal> {
    return request('/api/trafego/meta/local/configuracao');
  },

  salvarETestarMetaLocal(token: string): Promise<ResultadoDoTesteMetaLocal> {
    return request('/api/trafego/meta/local/configuracao', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
  },

  testarMetaLocal(): Promise<ResultadoDoTesteMetaLocal> {
    return request('/api/trafego/meta/local/testar', { method: 'POST' });
  },

  postsExistentesMeta(accountRef: string, pageRef: string, q = '', offset = 0): Promise<{
    items: PublicacaoExistenteMeta[]; total: number; offset: number; has_more: boolean; complete: boolean;
  }> {
    return request(`/api/trafego/meta/local/criacao/v2/posts-existentes?${new URLSearchParams({ account_ref: accountRef, page_ref: pageRef, q, offset: String(offset), limit: '24' })}`);
  },

  contasMetaLocal(): Promise<ResultadoDasContasMetaLocal> {
    return request('/api/trafego/meta/local/contas');
  },

  preflightMetaLocal(referenciaOpaca: string): Promise<ResultadoDoPreflightMetaLocal> {
    return request('/api/trafego/meta/local/preflight', {
      method: 'POST',
      body: JSON.stringify({ referencia_opaca: referenciaOpaca }),
    });
  },

  prepararSyncMetaLocal(referenciaOpaca: string): Promise<Record<string, unknown>> {
    return request('/api/trafego/meta/local/sincronizacao/preparar', {
      method: 'POST',
      body: JSON.stringify({ referencia_opaca: referenciaOpaca }),
    });
  },

  persistirSnapshotMetaLocal(referenciaOpaca: string): Promise<ReciboMetaReadModel> {
    return request('/api/trafego/meta/local/sincronizacao/persistir', {
      method: 'POST',
      body: JSON.stringify({ referencia_opaca: referenciaOpaca }),
    });
  },

  contasMetaReadModel(): Promise<ContasDoReadModelMeta> {
    return request('/api/trafego/meta/local/read-model/contas');
  },

  financeiroMeta(referencia: string, contaRef: string, inicio?: string, fim?: string): Promise<FinanceiroMeta> {
    const busca = new URLSearchParams({ conta_ref: contaRef });
    if (inicio) busca.set('inicio', inicio);
    if (fim) busca.set('fim', fim);
    return request(`/api/trafego/meta/local/financeiro/${encodeURIComponent(referencia)}?${busca}`);
  },

  /**
   * Uma página de uma entidade do read model Meta.
   *
   * ⚠️ A ASSINATURA ANTIGA CONTINUA VALENDO. O segundo argumento aceita a
   * referência da conta como string (a forma posicional que existia) ou o
   * objeto de opções. Trocar a forma sem manter a antiga quebraria quem já
   * chamava a função de fora deste milestone, e uma tela de leitura não é lugar
   * para um erro de compilação de outra equipe.
   *
   * O parâmetro na URL passou a ser `conta_ref`; o servidor ainda aceita
   * `conta_opaca` marcado como obsoleto, e mandar os dois só multiplicaria os
   * caminhos que precisam concordar.
   */
  inventarioMetaReadModel<T = ItemMetaReadModel>(
    entidade: EntidadeMetaReadModel | string,
    escopo?: string | OpcoesDeLeituraMeta | null,
  ): Promise<PaginaMetaReadModel<T>> {
    const opcoes: OpcoesDeLeituraMeta =
      typeof escopo === 'string' ? { contaRef: escopo } : (escopo ?? {});
    const busca = new URLSearchParams();
    if (opcoes.contaRef) busca.set('conta_ref', opcoes.contaRef);
    if (opcoes.cursor) busca.set('cursor', opcoes.cursor);
    if (opcoes.tamanho != null) busca.set('tamanho', String(opcoes.tamanho));
    const qs = busca.toString() ? `?${busca.toString()}` : '';
    return request(`/api/trafego/meta/local/read-model/${encodeURIComponent(entidade)}${qs}`);
  },

  /**
   * Um objeto do read model, resolvido DENTRO de uma conta.
   *
   * `referencia` aceita tanto o UUID persistido quanto a referência
   * `metaobj_…` que o recibo de criação entrega — as duas nascem do mesmo par
   * (conta, id externo) e o servidor compara com as duas.
   */
  detalheMetaReadModel<T = ItemMetaReadModel>(
    entidade: EntidadeMetaReadModel | string,
    referencia: string,
    contaRef?: string | null,
  ): Promise<DetalheMetaReadModel<T>> {
    const qs = contaRef ? `?conta_ref=${encodeURIComponent(contaRef)}` : '';
    return request(
      `/api/trafego/meta/local/read-model/${encodeURIComponent(entidade)}/${encodeURIComponent(referencia)}${qs}`,
    );
  },

  ultimoReciboMetaLocal(): Promise<InventarioMetaPersistido> {
    return request('/api/trafego/meta/local/recibo/ultimo');
  },

  removerMetaLocal(): Promise<{ removido: boolean }> {
    return request('/api/trafego/meta/local/configuracao', { method: 'DELETE' });
  },

  capacidadesCriacaoMeta(): Promise<Record<string, string | boolean>> {
    return request('/api/trafego/meta/local/criacao/capacidades');
  },

  ativosCriacaoMeta(accountRef: string): Promise<InventarioCriacaoMeta> {
    return request(
      `/api/trafego/meta/local/criacao/ativos?account_ref=${encodeURIComponent(accountRef)}`,
    );
  },

  previewAtivoMeta(accountRef: string, assetRef: string): Promise<string> {
    return baixarComoBlobUrl(
      `/api/trafego/meta/local/criacao/ativos/preview?account_ref=${encodeURIComponent(accountRef)}&asset_ref=${encodeURIComponent(assetRef)}`,
    );
  },

  compilarPlanoMeta(plano: PlanoMetaPausadoInput): Promise<ResultadoCompilacaoMeta> {
    return request('/api/trafego/meta/local/criacao/compilar', {
      method: 'POST',
      body: JSON.stringify(plano),
    });
  },

  validarPlanoMeta(plano: PlanoMetaPausadoInput): Promise<ResultadoValidacaoPlanoMeta> {
    return request('/api/trafego/meta/local/criacao/validar', {
      method: 'POST',
      body: JSON.stringify({ plano, confirmar_validate_only: true }),
    });
  },

  /** Públicos personalizados e semelhantes que JÁ EXISTEM nesta conta.
   *
   * ⚠️ POST com corpo, e não GET com query, pelo mesmo motivo que `/preflight`:
   * a referência opaca da conta é dado de operação, e uma query string entra em
   * log de proxy, histórico do navegador e `Referer`.
   *
   * ⚠️ Selecionar daqui NUNCA cria público nem semelhante, e nenhuma lista de
   * membros atravessa: o que volta são metadados do objeto.
   *
   * ⚠️ Custa leitura real da conta. Só sai por clique. */
  catalogoDePublicosMeta(
    referenciaOpaca: string,
  ): Promise<EnvelopeDeCatalogoMeta<PublicoDoCatalogoMeta>> {
    return request('/api/trafego/meta/local/catalogos/publicos', {
      method: 'POST',
      body: JSON.stringify({ referencia_opaca: referenciaOpaca }),
    });
  },

  /** Pixels/datasets E conversões personalizadas, em DOIS envelopes. */
  catalogoDeMensuracaoMeta(referenciaOpaca: string): Promise<CatalogoDeMensuracaoMeta> {
    return request('/api/trafego/meta/local/catalogos/mensuracao', {
      method: 'POST',
      body: JSON.stringify({ referencia_opaca: referenciaOpaca }),
    });
  },

  /** Busca de lugares no catálogo da Meta.
   *
   * ⚠️ A `key` devolvida É a chave que o compilador usa. O termo digitado é
   * BUSCA, nunca chave: se o texto livre virasse `region_keys`, uma segmentação
   * inventada teria cara de escolha do operador.
   *
   * `tipos` sai explícito porque o default da rota inclui `country`, e país
   * nesta bancada é código ISO num campo próprio — deixar os dois caminhos
   * abertos criaria duas formas de dizer a mesma coisa, que divergem. */
  catalogoDeGeografiaMeta(entrada: {
    referenciaOpaca: string;
    termo: string;
    tipos?: string[];
    pais?: string | null;
  }): Promise<EnvelopeDeCatalogoMeta<LugarDoCatalogoMeta>> {
    return request('/api/trafego/meta/local/catalogos/geografia', {
      method: 'POST',
      body: JSON.stringify({
        referencia_opaca: entrada.referenciaOpaca,
        termo: entrada.termo,
        tipos: entrada.tipos ?? ['region', 'city', 'zip'],
        pais: entrada.pais ?? null,
      }),
    });
  },

  /** O catálogo de receitas do contrato V2, COM o nível de prova de cada uma.
   *
   * ⚠️ Leitura LOCAL: a rota devolve o registro do servidor e não toca a Meta.
   * Por isso ela pode sair na montagem da página sem violar "nenhuma chamada
   * externa sem clique" — o que a regra proíbe é falar com o provedor. */
  receitasCriacaoMetaV2(): Promise<CatalogoDeReceitasMeta> {
    return request('/api/trafego/meta/local/criacao/v2/receitas');
  },

  identidadesRegulatoriasMeta(accountRef: string): Promise<{items: Array<{
    reference: string; label: string; category: string;
    beneficiary_name: string | null; payer_name: string | null; names_available: boolean;
  }>; complete: boolean}> {
    return request(`/api/trafego/meta/local/criacao/v2/identidades-regulatorias?account_ref=${encodeURIComponent(accountRef)}`);
  },

  /** Compila o plano V2. Efeito externo declarado: NENHUM. */
  compilarPlanoMetaV2(plano: PlanoMetaV2Input): Promise<ResultadoCompilacaoMetaV2> {
    return request('/api/trafego/meta/local/criacao/v2/compilar', {
      method: 'POST',
      body: JSON.stringify(plano),
    });
  },

  /** `validate_only` do plano V2 — por clique, e sem criar nada.
   *
   * ⚠️ Uma receita ou um modo de orçamento sem prova remota CHEGA aqui de
   * propósito: é esta chamada que produz a prova que falta. O que a ausência de
   * prova fecha é criar. */
  validarPlanoMetaV2(plano: PlanoMetaV2Input): Promise<ResultadoValidacaoPlanoMetaV2> {
    return request('/api/trafego/meta/local/criacao/v2/validar', {
      method: 'POST',
      body: JSON.stringify({ plano, confirmar_validate_only: true }),
    });
  },

  /** Aprova o plano. NÃO cria nada: o efeito externo declarado é NENHUM.
   *
   * A frase digitada viaja porque o servidor a compara — literalmente, sem
   * `toLowerCase` e sem sinônimo. Uma tela que só exibisse o campo e mandasse
   * `true` teria trocado um portão por uma decoração. */
  aprovarCriacaoMeta(entrada: {
    plano: PlanoMetaPausadoInput | PlanoMetaV2Input;
    planoSha256: string;
    validationId: string;
    confirmacaoDigitada: string;
  }): Promise<ResultadoAprovacaoCriacaoMeta> {
    return request('/api/trafego/meta/local/criacao/aprovar', {
      method: 'POST',
      body: JSON.stringify({
        plano: entrada.plano,
        plano_sha256_esperado: entrada.planoSha256,
        validation_id: entrada.validationId,
        confirmar_nascimento_pausado: true,
        confirmacao_digitada: entrada.confirmacaoDigitada,
      }),
    });
  },

  /** Cria os objetos PAUSED. Manda DUAS referências e nenhum payload Meta:
   *  o servidor relê o plano aprovado e recompila sozinho. */
  criarCampanhaPausadaMeta(
    approvalId: string, planoSha256: string,
  ): Promise<ResultadoCriacaoPausadaMeta> {
    return request('/api/trafego/meta/local/criacao/criar-pausada', {
      method: 'POST',
      body: JSON.stringify({
        approval_id: approvalId, plano_sha256_esperado: planoSha256,
      }),
    });
  },

  /** O recibo durável de uma operação, por referência opaca.
   *
   *  ⚠️ É o que permite REABRIR uma operação depois de fechar a aba. Sem ele, o
   *  recibo e o `approval_id` viviam só em `useState`: um reload apagava a
   *  única saída segura de um incidente. A rota já existia no backend e não
   *  tinha cliente. Ela depende só da autoridade do LEDGER — a flag de criação
   *  governa o POST que faz nascer objeto, não a leitura do que já nasceu.
   */
  reciboCriacaoMeta(approvalId: string): Promise<ResultadoReciboCriacaoMeta> {
    return request('/api/trafego/meta/local/criacao/recibo', {
      method: 'POST',
      body: JSON.stringify({ approval_id: approvalId }),
    });
  },

  /** Decide um recibo ambíguo POR LEITURA. Nunca reenvia nada. */
  reconciliarCriacaoMeta(approvalId: string): Promise<ResultadoReconciliacaoMeta> {
    return request('/api/trafego/meta/local/criacao/reconciliar', {
      method: 'POST',
      body: JSON.stringify({ approval_id: approvalId }),
    });
  },

  workRoad(): Promise<WorkRoadLive> {
    return request('/api/work-road');
  },

  workRoadExecutions(): Promise<WorkRoadExecutionsLive> {
    return request('/api/work-road/executions');
  },

  workRoadInbox(): Promise<InboxLive> {
    return request('/api/work-road/inbox');
  },

  captureInbox(payload: { title: string; original: string; origin?: string; explanation?: string }): Promise<{ entry: unknown; receipt: InboxReceipt }> {
    return request('/api/work-road/inbox', { method: 'POST', body: JSON.stringify(payload) });
  },

  triageInbox(entryId: string, payload: { triage: InboxTriage; promoted_task_id?: string; possible_duplicate_of?: string; justification?: string }) {
    return request(`/api/work-road/inbox/${encodeURIComponent(entryId)}/triage`, { method: 'POST', body: JSON.stringify(payload) });
  },

  confirmWorkRoadOrder(initiativeId: string, taskIds: string[], expectedSha256: string) {
    return request('/api/work-road/reorder', { method: 'POST', body: JSON.stringify({ initiative_id: initiativeId, task_ids: taskIds, expected_sha256: expectedSha256 }) });
  },

  workRoadGraphStatus(): Promise<GraphStatusLive> {
    return request('/api/work-road/graph-status');
  },

  async workRoadExport(format: string, scope: string, filters: { iniciativa?: string; onda?: string; status?: string; busca?: string }): Promise<Blob> {
    if (!API_BASE) {
      throw new PautadorApiError('VITE_PAUTADOR_API_URL não configurada. Configure a URL do backend Pautador Pro.', 0);
    }
    const params = new URLSearchParams({ format, scope });
    if (filters.iniciativa) params.set('iniciativa', filters.iniciativa);
    if (filters.onda) params.set('onda', filters.onda);
    if (filters.status && filters.status !== 'all') params.set('status', filters.status);
    if (filters.busca) params.set('busca', filters.busca);
    const resp = await fetch(url(`/api/work-road/export?${params}`), { headers: await autorizacao() });
    if (!resp.ok) {
      throw new PautadorApiError(`Falha ao exportar o workbook (${resp.status}).`, resp.status);
    }
    return resp.blob();
  },

  health(): Promise<{
    status: string;
    engine: string;
    supabase: boolean;
    grounding: boolean;
    kw_engine?: string;
    google_ads?: { mode: string; ready: boolean; missing: string[] };
    dataforseo?: boolean;
  }> {
    return request('/api/pautador/health');
  },

  countries(): Promise<{ countries: PautadorCountry[]; source: string }> {
    return request('/api/pautador/countries');
  },

  discovery(params: DiscoveryParams): Promise<DiscoveryResponse> {
    return request('/api/pautador/discovery', {
      method: 'POST',
      body: JSON.stringify({ count: 40, ...params }),
    });
  },

  mine(opportunityId: number, opportunity?: Opportunity): Promise<MineResult> {
    return request(`/api/pautador/opportunities/${opportunityId}/mine`, {
      method: 'POST',
      body: JSON.stringify(opportunity ? { opportunity } : {}),
    });
  },

  funnel(
    opportunityId: number,
    opportunity?: Opportunity,
    cluster?: MineResult | KeywordCluster | null,
  ): Promise<FunnelResult> {
    const payload: Record<string, unknown> = {};
    if (opportunity) payload.opportunity = opportunity;
    if (cluster) payload.cluster = cluster;
    return request(`/api/pautador/opportunities/${opportunityId}/funnel`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  updateStatus(
    opportunityId: number,
    status: OpportunityStatus,
    reviewedBy?: string,
  ): Promise<{ opportunity: Opportunity }> {
    return request(`/api/pautador/opportunities/${opportunityId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, reviewed_by: reviewedBy }),
    });
  },

  addOpportunity(payload: Partial<Opportunity> & { run_id?: number }): Promise<{ opportunity: Opportunity; persisted: boolean }> {
    return request('/api/pautador/opportunities', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // --- ENTITY-FIRST ---
  entityDiscovery(params: EntityDiscoveryParams): Promise<EntityDiscoveryResponse> {
    return request('/api/pautador/entities/discovery', {
      method: 'POST',
      body: JSON.stringify({ count: 20, ...params }),
    });
  },

  niches(): Promise<{ niches: PautadorNiche[]; source: string }> {
    return request('/api/pautador/niches');
  },

  createNiche(payload: {
    slug: string;
    label: string;
    guidance?: string;
    allowed_verticals?: string[];
    sort_order?: number;
  }): Promise<{ niche: PautadorNiche }> {
    return request('/api/pautador/niches', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  listEntityOpportunities(countryCode: string): Promise<EntityListResponse> {
    return request(`/api/pautador/entity-opportunities?country=${encodeURIComponent(countryCode)}`);
  },

  /**
   * O briefing renderizado, como `blob:` URL já autenticada.
   *
   * ---------------------------------------------------------------------------
   * POR QUE NÃO É MAIS UMA URL DIRETA
   * ---------------------------------------------------------------------------
   * Antes isto devolvia a URL da rota, usada em `<a href target="_blank">`. Uma
   * navegação de topo não carrega cabeçalho nenhum — nem `X-API-Key` antes, nem
   * `Authorization` agora. E a justificativa que estava escrita aqui ("por isso
   * a rota é GET aberto no backend") invertia a ordem: a limitação do navegador
   * virava argumento para deixar a rota sem portão. O briefing é a tese
   * comercial de uma oportunidade — dores, consultas semente, hipóteses de
   * funil. Não é material aberto.
   *
   * Agora o conteúdo vem por `fetch` com Bearer e a aba abre um `blob:`, que só
   * existe nesta sessão do navegador. Quem chama deve `URL.revokeObjectURL` ao
   * descartar.
   */
  async entityBriefingBlobUrl(opportunityId: number): Promise<string> {
    return baixarComoBlobUrl(
      `/api/pautador/entity-opportunities/${opportunityId}/briefing.html`,
    );
  },

  /** O mesmo briefing em .docx, para salvar. */
  async entityBriefingDocxBlobUrl(opportunityId: number): Promise<string> {
    return baixarComoBlobUrl(
      `/api/pautador/entity-opportunities/${opportunityId}/briefing.docx`,
    );
  },

  mineEntity(entityId: number, entity?: EntityMeta): Promise<EntityMineResponse> {
    return request(`/api/pautador/entities/${entityId}/mine`, {
      method: 'POST',
      body: JSON.stringify(entity ? { entity } : {}),
    });
  },

  entityFunnel(opportunityId: number, entity?: EntityMeta): Promise<EntityFunnelResponse> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/funnel`, {
      method: 'POST',
      body: JSON.stringify(entity ? { entity } : {}),
    });
  },

  /** Move para "Em validação" E MEDE. É a mesma rota: medir é o que a coluna faz.
   *  Responde só no fim (~30s) — quem quiser acompanhar usa `entityAxes`. */
  validateEntity(opportunityId: number, reviewedBy?: string): Promise<{
    opportunity: EntityCard; validacao?: ValidacaoRelatorio;
  }> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/validate`, {
      method: 'POST',
      body: JSON.stringify({ status: 'validating', reviewed_by: reviewedBy }),
    });
  },

  /** Os eixos já gravados. A escrita é incremental, então isto é progresso REAL
   *  lido do banco — não uma barra que anda sozinha. */
  entityAxes(opportunityId: number): Promise<{
    eixos: { eixo: string; nivel: string | null; proveniencia: string;
             motivo_ausencia: string | null; medido_em: string }[];
    total: number;
  }> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/axes`);
  },

  /** As TESES já deriváveis do que foi medido. Leitura pura: não mede, não
   *  gasta e não chama API externa. Por isso pode ser pedida para a coluna
   *  inteira sempre que a lista muda.
   *
   *  A resposta separa `ranking` de `fora_do_ranking` de propósito: card sem
   *  cobertura mínima não entra na ordenação e também não some da tela. */
  entityTeses(params: {
    opportunity_ids?: number[]; country_code?: string; status?: string;
    limite?: number; aplicar_priors?: boolean;
  }): Promise<TesesResposta> {
    return request('/api/pautador/entity-opportunities/teses', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** A coluna inteira numa passada — o caminho PADRÃO. A base de US$ 0,012 por
   *  chamada domina na cauda curta: um a um paga a base uma vez por card. */
  validateBatch(params: {
    opportunity_ids?: number[]; country_code?: string; status?: string;
    limite?: number; refazer?: boolean;
  }): Promise<{ validacao: ValidacaoRelatorio }> {
    return request('/api/pautador/entity-opportunities/validate-batch', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** v7_17 · registra QUAL PERGUNTA vamos atacar (arraste -> Em validação).
   *  Não move o card e não bloqueia nada: quem move é o arraste. Sem nota,
   *  sem ranking — não há desfecho medido contra o qual validar uma nota. */
  recordQuestionChoice(
    opportunityId: number,
    payload: QuestionChoicePayload,
  ): Promise<{ choice: Record<string, unknown>; candidatas: number }> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/question-choice`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  updateEntityStatus(
    opportunityId: number,
    status: OpportunityStatus,
    reviewedBy?: string,
  ): Promise<EntityStatusUpdateResult> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, reviewed_by: reviewedBy }),
    });
  },

  saveEntityInsights(
    opportunityId: number,
    insights: string,
  ): Promise<{ opportunity: EntityCard }> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/insights`, {
      method: 'PATCH',
      body: JSON.stringify({ insights }),
    });
  },

  /** Descrição da tarefa -> corpo da task no ClickUp. NÃO é o insights. */
  saveEntityTaskDescription(
    opportunityId: number,
    taskDescription: string,
  ): Promise<{ opportunity: EntityCard }> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/task-description`, {
      method: 'PATCH',
      body: JSON.stringify({ task_description: taskDescription }),
    });
  },

  /** Renomeia o CARD (não a entidade). Vazio volta a exibir o canonical_name. */
  saveEntityDisplayTitle(
    opportunityId: number,
    displayTitle: string,
  ): Promise<{ opportunity: EntityCard }> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/display-title`, {
      method: 'PATCH',
      body: JSON.stringify({ display_title: displayTitle }),
    });
  },

  /** Duplica um card já minerado p/ rodar a MESMA entidade em outro site.
   *  A cópia nasce em "Em mineração", com as dores/queries já mineradas. */
  duplicateEntityCard(
    opportunityId: number,
    displayTitle: string,
  ): Promise<{ card: EntityCard; warnings: string[] }> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/duplicate`, {
      method: 'POST',
      body: JSON.stringify({ display_title: displayTitle }),
    });
  },

  setFunnelCompleted(
    opportunityId: number,
    completed: boolean,
  ): Promise<{ opportunity: EntityCard }> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}/complete`, {
      method: 'PATCH',
      body: JSON.stringify({ completed }),
    });
  },

  createManualEntity(payload: {
    country: string;
    country_code: string;
    canonical_name: string;
    full_name?: string;
    entity_type?: string;
    entity_category?: string;
    official_source?: string;
    description?: string;
    aliases?: string[];
    native_language?: string;
    status?: string;
  }): Promise<{ card: EntityCard; already_existed: boolean }> {
    return request('/api/pautador/entities/manual', {
      method: 'POST',
      body: JSON.stringify({ status: 'ready', ...payload }),
    });
  },

  // Input manual em Descobertas -> agente secundário enriquece o card
  enrichEntity(payload: {
    country: string;
    country_code: string;
    canonical_name: string;
    native_language?: string;
  }): Promise<{ card: EntityCard; already_existed: boolean; engine?: string; warnings?: string[] }> {
    return request('/api/pautador/entities/enrich', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  deleteEntityOpportunity(
    opportunityId: number,
  ): Promise<{ deleted: boolean; opportunity_id: number; entity_id: number | null }> {
    return request(`/api/pautador/entity-opportunities/${opportunityId}`, {
      method: 'DELETE',
    });
  },

  // ── publicação: o WordPress de cada projeto ────────────────────────────────
  //
  // O GET NUNCA devolve o Application Password — o backend responde com
  // `senha_mascarada` e mais nada. Por isso `salvarPerfilPublicacao` trata a
  // senha como opcional: campo vazio no formulário significa "não mexi nela".
  // Mandar `wp_app_password: ''` apagaria a credencial de quem já tinha.

  perfilPublicacao(projectId: number): Promise<PerfilPublicacao> {
    return request(`/api/publicacao/projetos/${projectId}/wordpress`);
  },

  salvarPerfilPublicacao(projectId: number, body: PerfilEntrada): Promise<PerfilPublicacao> {
    return request(`/api/publicacao/projetos/${projectId}/wordpress`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  },

  testarPublicacao(projectId: number): Promise<ResultadoTesteConexao> {
    return request(`/api/publicacao/projetos/${projectId}/wordpress/testar`, {
      method: 'POST',
    });
  },

  destinosPublicacao(): Promise<ProjetoDestino[]> {
    return request('/api/publicacao/destinos');
  },

  // Enfileira a escrita do funil. O backend valida ANTES de qualquer gasto:
  // card sem arquitetura, site sem credencial e publicação sem teste verde
  // voltam como 409 com o motivo — cada um deles custaria um run inteiro se
  // ficasse para o motor descobrir.
  dispararRedator(payload: {
    opportunity_id: number;
    project_id: number;
  }): Promise<DisparoDoRedator> {
    return request('/api/publicacao/redator/disparar', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Sem `opportunityId`: as últimas execuções de todos os cards — a porta de
  // entrada da página /redator.
  runsDoRedator(opportunityId?: number): Promise<RunDoRedator[]> {
    return request('/api/publicacao/redator/runs'
      + (opportunityId != null ? `?opportunity_id=${opportunityId}` : ''));
  },

  // O elo que fecha o ciclo PAUTA → FUNIL → CAMPANHA. Lê o WordPress e escreve
  // só na NOSSA tabela — publicar continua sendo clique humano no WP, que é o
  // desenho do motor (`engine/config.yaml: publish_status: draft`).
  relerDoWordPress(runRowId: number): Promise<ReleituraDoWordPress> {
    return request(`/api/publicacao/redator/runs/${runRowId}/reler-wp`, { method: 'POST' });
  },

  // ── HUB DE TRÁFEGO ───────────────────────────────────────────────────────

  /**
   * Campanhas ligadas que não gastaram. Consulta o Google Ads NA HORA.
   *
   * ⚠️ Não há tabela de alertas, e é decisão: alerta guardado envelhece — a
   * campanha volta a gastar às 9h e o aviso das 8h continua dizendo que está
   * parada. Como isso custa cinco consultas por conta, a tela deve chamar com
   * `staleTime` generoso em vez de a cada render.
   */
  // ═══════════════════════════════════════════════════════════════════════
  // INVENTÁRIO OPERACIONAL (Fase 1B)
  // ═══════════════════════════════════════════════════════════════════════

  /**
   * `GET /api/trafego/inventario` — o que existe nas contas, e quão recente é.
   *
   * A paginação é por CURSOR opaco, nunca por offset: entre uma página e a
   * seguinte o inventário muda (uma campanha é pausada, outra é lida pela
   * primeira vez), e offset sob lista instável pula item ou mostra o mesmo
   * duas vezes. O cursor descreve uma posição, não uma contagem.
   *
   * Filtros viajam como query string e são resolvidos NO BANCO. Nenhum filtro
   * dispara leitura nova na conta de anúncios — a tela lê o snapshot.
   */
  inventario(
    filtros?: FiltrosDoInventario,
    cursor?: string | null,
  ): Promise<Inventario> {
    const busca = new URLSearchParams();
    if (cursor) busca.set('cursor', cursor);
    if (filtros) {
      for (const [chave, valor] of Object.entries(filtros)) {
        if (valor === undefined || valor === null) continue;
        // Busca vazia não é filtro: mandá-la faria a assinatura do cursor mudar
        // sem que o recorte mudasse, e a página seguinte seria recusada.
        if (chave === 'busca' && String(valor).trim() === '') continue;
        if (Array.isArray(valor)) {
          if (valor.length > 0) busca.set(chave, valor.join(','));
        } else {
          busca.set(chave, String(valor));
        }
      }
    }
    const qs = busca.toString();
    return request(`/api/trafego/inventario${qs ? `?${qs}` : ''}`);
  },

  /**
   * UMA campanha, pela identidade INTERNA — a rota canônica da ADR-02.
   *
   * ⚠️ **Não aceita `campaign_id` do Google.** O id externo é único dentro de
   * uma conta, não no VOLC O.S., e a identidade externa é uma trinca
   * (plataforma, conta, id). Uma rota que aceitasse o id externo teria de
   * adivinhar as outras duas pontas — e adivinhar errado abre a campanha de
   * outro cliente com a URL certa na barra de endereço.
   *
   * Leitura de snapshot: zero consulta ao Google, zero mutação, e não passa
   * pela listagem paginada. `404` quando o endereço não existe.
   */
  campanhaCanonica(volcCampaignId: string): Promise<CampanhaCanonica> {
    return request(
      `/api/trafego/campanhas/${encodeURIComponent(volcCampaignId)}`,
    );
  },

  /**
   * O diagnóstico de entrega de UMA campanha — por que ela não entrega.
   *
   * Mesma identidade da rota canônica: só o identificador INTERNO. Leitura de
   * projeção: o backend devolve o que a apuração já gravou, e esta chamada não
   * dispara consulta ao Google Ads nem gasta cota da conta do cliente.
   *
   * Diagnóstico e propostas vêm no mesmo envelope porque são a mesma apuração
   * vista de dois lados — separá-los em duas rotas produziria o dia em que a
   * tela mostra a escada de agora ao lado de propostas de meia hora atrás.
   *
   * ⚠️ `404` aqui é ambíguo por natureza: pode ser campanha inexistente OU
   * servidor que ainda não tem esta rota. Quem trata é `useDiagnosticoDeEntrega`,
   * e ele distingue os dois em vez de escolher o mais tranquilizador.
   */
  diagnosticoDeEntrega(volcCampaignId: string): Promise<RespostaDoDiagnostico> {
    return request(
      `/api/trafego/campanhas/${encodeURIComponent(volcCampaignId)}/diagnostico`,
    );
  },

  /**
   * Laboratório isolado por `scenarioId`. O contrato não recebe identidade de
   * campanha real e o endpoint só projeta fixtures sintéticas versionadas.
   */
  decisionIntelligenceLab(scenarioId: string): Promise<RespostaDoDecisionLab> {
    return request(
      `/api/trafego/laboratorio/inteligencia/${encodeURIComponent(scenarioId)}`,
    );
  },

  /**
   * O vocabulário fechado do contrato, e os manifestos de todos os canais.
   *
   * ⚠️ É daqui que o estúdio deriva o que oferecer — nunca de uma lista de
   * canais escrita no cliente. Quatro canais não são quatro botões de "criar":
   * existe construtor para dois, e oferecer os outros por simetria visual faz
   * o operador descobrir a ausência depois de montar o pedido inteiro.
   */
  vocabularioDoInventario(): Promise<VocabularioDoInventario> {
    return request('/api/trafego/inventario/vocabulario');
  },

  /**
   * O que ESTA pessoa pode, neste servidor, agora.
   *
   * ⚠️ A tela pergunta em vez de derivar de `role === 'ADMIN'`. Papel de
   * produto e direito de gastar na conta do cliente são decisões de tamanhos
   * muito diferentes, e derivar uma da outra desenha botão de gasto que o
   * servidor recusa no clique — depois de o operador montar o pedido inteiro.
   *
   * A resposta é um retrato do instante, pedido a cada carregamento, e nunca
   * uma credencial: nada aqui autoriza coisa nenhuma, quem recusa continua
   * sendo o servidor.
   */
  capacidades(): Promise<CapacidadesDoOperador> {
    return request('/api/trafego/capacidades');
  },

  /**
   * Os quatro canais do Google, com veredito e motivo por portão.
   *
   * ⚠️ A resposta é o veredito PRONTO. A tela não recalcula nada: um
   * `capacidades.google_mutate && manifesto.sabe_criar` escrito aqui pareceria
   * correto e estaria errado — a janela do canário recusa Display mesmo com as
   * duas verdadeiras, e a tela ofereceria um botão que o servidor nega no
   * clique, depois de o operador montar o pedido inteiro.
   *
   * Esta rota NÃO consulta o Google: ela desenha um cockpit, e uma leitura viva
   * a cada navegação gastaria quota da conta do cliente. O que ninguém leu
   * chega `INDETERMINADO` com a razão dita, nunca zero.
   */
  contratoDosCanais(): Promise<RespostaDosCanais> {
    return request('/api/trafego/canais');
  },

  /**
   * Que funis internos casam com esta campanha, e com que força cada sinal.
   *
   * ⚠️ Isto SUGERE. A resposta não é vínculo e não vira vínculo por ser única
   * ou por ser forte — quem responde é `confirmarVinculo`, e a resposta leva
   * quem confirmou, quando e com que regra (ADR-09).
   */
  correspondenciasDaCampanha(
    volcCampaignId: string,
  ): Promise<RevisaoDeCorrespondencia> {
    return request(
      `/api/trafego/campanhas/${encodeURIComponent(volcCampaignId)}/correspondencias`,
    );
  },

  /**
   * Confirma o vínculo campanha ↔ funil. É a resposta humana à reconciliação.
   *
   * ⚠️ Quem confirmou NÃO viaja no corpo: o servidor tira do token. Aceitar do
   * corpo deixaria qualquer um assinar a decisão com o nome de outro, numa
   * tabela cujo propósito inteiro é dizer quem decidiu o quê.
   */
  confirmarVinculo(pedido: {
    volc_campaign_id: string;
    opportunity_id?: number;
    project_id?: number;
    funnel_run_id?: number;
    regra: string;
    evidencia?: Record<string, unknown>;
    vinculo_anterior?: string;
  }): Promise<{ vinculo: Record<string, unknown> }> {
    return request('/api/trafego/vinculos', {
      method: 'POST',
      body: JSON.stringify(pedido),
    });
  },

  /**
   * Desfaz um vínculo. Operação de primeira classe, não exceção (ADR-09).
   *
   * A linha NÃO é apagada — ela é o rastro de que houve um vínculo. Apagá-la
   * tornaria a campanha indistinguível de uma que nunca foi vinculada.
   */
  desfazerVinculo(
    vinculoId: string,
    motivo?: string,
  ): Promise<{ vinculo: Record<string, unknown> }> {
    return request(
      `/api/trafego/vinculos/${encodeURIComponent(vinculoId)}/desfazer`,
      { method: 'POST', body: JSON.stringify({ motivo: motivo ?? null }) },
    );
  },

  /**
   * Pede uma leitura nova de UMA conta. Exige ADMIN no servidor.
   *
   * Uma conta por vez de propósito: uma varredura geral sob demanda é o tipo de
   * botão que alguém clica três vezes achando que não funcionou, e cada clique
   * custa cota da API do Google. O servidor aplica limite de frequência e
   * informa o escopo do que vai ler.
   *
   * NÃO abre a trava de escrita: isto lê a conta, não altera nada nela.
   */
  atualizarConta(customerId: string): Promise<{ aceito: boolean; motivo?: string }> {
    return request('/api/trafego/inventario/atualizar', {
      method: 'POST',
      body: JSON.stringify({ customer_id: customerId }),
    });
  },

  /**
   * O quadro de condições que pedem atenção — do SNAPSHOT, não da conta.
   *
   * Passou de `/api/trafego/alertas` para `/api/trafego/inventario/alertas` na
   * Fase 1B. A rota antiga executava consulta ao Google Ads em tempo de render,
   * e o Layout monta o sino em TODA página: abrir o app custava cota da conta
   * de anúncios do cliente. A nova projeta o que a varredura já gravou.
   *
   * Mesma fonte que a aba Atenção usa. Duas superfícies mostrando a mesma
   * condição por caminhos diferentes divergem no dia em que uma atualiza e a
   * outra não.
   */
  alertasDeTrafego(): Promise<QuadroDeAlertas> {
    return request('/api/trafego/inventario/alertas');
  },

  quadroDeTrafego(): Promise<QuadroDeTrafego> {
    return request('/api/trafego/quadro');
  },

  // `com_texto_da_lp` é `false` por padrão: o texto é o artigo inteiro, e a
  // tela pede este payload a cada abertura do cockpit.
  cockpitDeTrafego(opportunityId: number, opts?: { runId?: number; comTextoDaLp?: boolean }): Promise<Cockpit> {
    const q = new URLSearchParams();
    if (opts?.runId != null) q.set('run_id', String(opts.runId));
    if (opts?.comTextoDaLp) q.set('com_texto_da_lp', 'true');
    const s = q.toString();
    return request(`/api/trafego/candidatos/${opportunityId}${s ? `?${s}` : ''}`);
  },

  // ⚠️ LÊ A CONTA E FECHA O MESMO RECIBO. NUNCA REENVIA O MUTATE.
  //
  // É a saída de um desfecho indeterminado — o caso em que a resposta se perdeu
  // e ninguém sabe se a campanha existe. Reenviar ali seria a forma mais fácil
  // de criar a campanha duas vezes no mesmo leilão; por isso a operação é ler,
  // não escrever de novo.
  //
  // `campaign_id` é OPCIONAL de propósito: o item que MAIS precisa de
  // reconciliação é justamente o que não tem id externo, porque a chamada nunca
  // respondeu. Sem id, o servidor busca pela marca `VOLC-CANARY-<impressao>`.
  //
  // ⚠️ Exige ADMIN (`routers/trafego.py:4444`), enquanto o resto do fluxo exige
  // só usuário — logo o operador não fecha o próprio recibo. A tela diz isso em
  // vez de oferecer um botão que voltaria 403.
  reconciliarLancamento(pedido: {
    item_id: string;
    customer_id: string;
    campaign_id?: string | null;
    marca?: string | null;
    /**
     * O canal do item — e sem ele o read-back tipado NÃO RODA.
     *
     * ⚠️ O servidor precisa dele para saber QUE OBJETOS reler: PMax tem asset
     * group e não tem anúncio, e perguntar por um devolveria vazio — que
     * viraria "não existe anúncio", quando o fato é que não existe a entidade.
     * Sem o campo, a rota responde `NAO_SUPORTADO` com a causa dita, e o
     * veredito de sete estados fica desligado em 100% das reconciliações reais.
     */
    canal?: string | null;
  }): Promise<Record<string, unknown>> {
    return request('/api/trafego/reconciliar', {
      method: 'POST', body: JSON.stringify(pedido),
    });
  },

  // O plano de mensuração GRAVADO desta conta, com os sete portões.
  //
  // ⚠️ ZERO REDE ao Google — o backend lê o que já está persistido. É por isso
  // que a parada Economia pode mostrar os portões ANTES da prova: `/provar`
  // gasta até cinco GAQL por clique e é a chamada mais lenta do fluxo, e um
  // operador não deve precisar pagá-la para descobrir que a conta não tem meta.
  //
  // `vigente_da_conta` e `vigente_da_campanha` ficaram sem chamador de produção
  // até 02/09/2026: a v12_02 foi aplicada com backup e onze contraprovas para
  // que alguém pudesse conferir o que ficou gravado, e não havia por onde.
  planoDeMensuracaoVigente(
    customerId: string, loginCustomerId: string, campaignId?: string | null,
  ): Promise<PlanoVigenteResposta> {
    const q = new URLSearchParams({
      customer_id: customerId, login_customer_id: loginCustomerId,
    });
    if (campaignId) q.set('campaign_id', campaignId);
    return request(`/api/trafego/plano-de-mensuracao?${q.toString()}`);
  },

  // ── o conjunto pago: conferir, e depois congelar ──────────────────────────
  //
  // ⚠️ O ATO QUE FALTAVA. `aprovar()` existe no engine desde sempre
  // (`backend/app/agents/mining/paid_eligibility.py:1166`) e não tinha um único
  // chamador de produção: nove call sites, todos de teste. Quem PRODUZ o
  // conjunto (`funnel_factory.py:391`) persiste `conjunto_pago` sem
  // `approved_set_sha256`, e o portão recusa exatamente esse estado
  // (`portao_conjunto_pago.py:158`, `CONJUNTO_PAGO_NAO_APROVADO`). Resultado
  // medido: `/provar` e `/subir` devolviam 409 e a campanha Search não nascia
  // pelo caminho normal. Estas duas rotas são a ponte humana que faltava.
  //
  // A revisão é LEITURA. Não congela nada, e pode ser pedida quantas vezes o
  // operador quiser.
  revisarConjuntoPago(opportunityId: number, runId?: number | null): Promise<RevisaoDoConjuntoPago> {
    const q = runId != null ? `?run_id=${runId}` : '';
    return request(`/api/pautador/opportunities/${opportunityId}/conjunto-pago${q}`);
  },

  // ⚠️ ATO HUMANO, e ele CONGELA. `hash_conferido` é a impressão que apareceu na
  // tela: o servidor a compara com a do conjunto atual e recusa se divergirem
  // (`HashDivergente`). É isso que impede aprovar um conjunto e criar campanha
  // com outro — a mineração pode ter rodado de novo entre a conferência e o
  // clique. O `motivo` nasce VAZIO na tela e é do humano; ele vai ao recibo.
  aprovarConjuntoPago(pedido: {
    opportunity_id: number;
    run_id?: number | null;
    hash_conferido: string;
    motivo: string;
  }): Promise<AprovacaoDoConjuntoPago> {
    return request(`/api/pautador/opportunities/${pedido.opportunity_id}/conjunto-pago/aprovar`, {
      method: 'POST',
      body: JSON.stringify(pedido),
    });
  },

  // O estágio 3. ⚠️ ESTA ROTA GASTA e DEMORA: medido em 18/08/2026 no card 73,
  // 174,19 s em duas rodadas de conjunto (29k tokens de entrada, 34k de saída).
  // A tela precisa mostrar o tempo correndo — um spinner mudo por três minutos
  // é indistinguível de uma tela travada.
  escreverCopy(pedido: PedidoDeCopy): Promise<RespostaDaCopy> {
    return request('/api/trafego/copy', { method: 'POST', body: JSON.stringify(pedido) });
  },

  // O cockpit chama AO ABRIR. É o que faz sair da página e voltar não jogar
  // fora ~174 s de LLM pago — inclusive num browser fechado e reaberto.
  lerCopy(opportunityId: number, runId?: number | null): Promise<RespostaDaCopy> {
    const q = runId != null ? `?run_id=${runId}` : '';
    return request(`/api/trafego/copy/${opportunityId}${q}`);
  },

  // `validate_only` contra a conta real. É LEITURA: a API valida o payload e
  // descarta, sem criar nada. Pode demorar — o backend corta em 120s.
  provarCampanha(pedido: PedidoDeProva): Promise<RespostaDaProva> {
    return request('/api/trafego/provar', { method: 'POST', body: JSON.stringify(pedido) });
  },

  // PMax fica fora de `/provar`: este ato só projeta o contrato local e torna
  // visíveis os bloqueios. Não lê conta Google, não chama validate_only e não
  // cria nada.
  planejarPMax(pedido: PedidoDePlanejamentoPMax): Promise<RespostaDoPlanejamentoPMax> {
    return request('/api/trafego/planejar-pmax', {
      method: 'POST',
      body: JSON.stringify(pedido),
    });
  },

  // O caminho de escrita. Exige `motivo` (vai para o recibo) e só funciona com
  // a trava de dois fatores aberta — ver `estadoDaTrava`.
  subirCampanha(pedido: PedidoDeProvaSearch & {
    motivo: string;
    plano_impressao: string;
    confirmar_criacao_pausada: boolean;
  }): Promise<{ recibo: ReciboDeLancamento }> {
    return request('/api/trafego/subir', { method: 'POST', body: JSON.stringify(pedido) });
  },

  // Consultado ANTES de o operador montar tudo: descobrir no clique final que a
  // trava está fechada desperdiça o trabalho inteiro.
  estadoDaTrava(): Promise<EstadoDaTrava> {
    return request('/api/trafego/trava');
  },

  // Grava a copy corrigida à mão. Não chama LLM e não custa token — existe
  // para consertar um caractere sem refazer 167 s de cascata.
  salvarCopyEditada(pedido: { opportunity_id: number; run_id?: number | null; copy: CopyGerada }):
      Promise<CopyPersistida> {
    return request('/api/trafego/copy', { method: 'PATCH', body: JSON.stringify(pedido) });
  },

  // As verticais e seus portões, do `policy/spec.json`. A tela NÃO tem cópia
  // própria dessa lista: é a mesma fonte que reprova o payload, e duas cópias
  // divergiriam em silêncio.
  verticaisEPortoes(): Promise<{ verticais: VerticalDePolitica[] }> {
    return request('/api/trafego/politica/verticais');
  },

  // O que o Google decidiu sobre os anúncios. Vale para campanha PAUSADA —
  // medido em 19/08/2026: anúncio em campanha pausada é revisado normalmente,
  // o que torna subir pausado o teste de política mais barato que existe.
  vereditoDePolitica(customerId: string, campaignId: string): Promise<VereditoDePolitica> {
    return request(`/api/trafego/veredito/${customerId}/${campaignId}`);
  },

  // ── as contas, na aba Integrações ────────────────────────────────────────

  // A árvore da casa, pronta. A tela NÃO monta essa lista chamando `/contas`
  // id a id: seriam 12 idas e voltas para produzir 39 contas anunciáveis das
  // quais 36 são de cliente e nenhuma pode ser escolhida. ~2,3 s medido em
  // 18/08/2026 — são duas chamadas à API do Google por dentro.
  escopoDeContas(): Promise<EscopoDeContas> {
    return request('/api/trafego/escopo');
  },

  projetosComConta(): Promise<{ projetos: ProjetoComConta[] }> {
    return request('/api/trafego/projetos');
  },

  // ⚠️ O servidor RECUSA conta fora da árvore da casa com 403, e é bom que
  // recuse: esta função é conveniência da tela, não a guarda. `customer_id`
  // viaja no corpo de `/provar` e de `/subir` também.
  vincularConta(projectId: number, customerId: string, managerId: string):
    Promise<{ vinculado: boolean; project_id: number }> {
    return request(`/api/trafego/projetos/${projectId}/conta`, {
      method: 'PUT',
      body: JSON.stringify({
        google_ads_customer_id: customerId,
        google_ads_manager_id: managerId,
      }),
    });
  },

  // Existe porque o PUT não consegue desfazer: o portão recusa id vazio, então
  // "apagar mandando string vazia" deixou de funcionar.
  desvincularConta(projectId: number): Promise<{ vinculado: boolean }> {
    return request(`/api/trafego/projetos/${projectId}/conta`, { method: 'DELETE' });
  },

  // O quadro: onde cada funil está no ciclo. Junta duas fontes que a tela não
  // deveria ter de cruzar sozinha — os cards aprovados do Pautador e os runs.
  quadroDoRedator(): Promise<QuadroDoRedator> {
    return request('/api/publicacao/redator/quadro');
  },

  // Tira uma execução encerrada do quadro. O backend recusa run em andamento e
  // run que publicou — ver a docstring da rota.
  excluirRun(runRowId: number): Promise<{ excluido: boolean; custo_perdido_usd: number }> {
    return request(`/api/publicacao/redator/runs/${runRowId}`, { method: 'DELETE' });
  },

  // A doutrina, os prompts e os modelos do motor. Somente leitura — ver o
  // campo `por_que` na resposta.
  configuracaoDoRedator(): Promise<ConfiguracaoDoRedator> {
    return request('/api/publicacao/redator/configuracao');
  },

  // O funil ESCRITO. Não entra no polling: pesa mais que a matriz, muda pouco,
  // e arrastá-lo 900 vezes por run seria trafegar o texto das cinco páginas para
  // nada.
  paginasDoRun(runRowId: number): Promise<FunilEscrito> {
    return request(`/api/publicacao/redator/runs/${runRowId}/paginas`);
  },

  // Envia ao WordPress UMA página que ficou escrita e parada.
  //
  // ⚠️ Isto ESCREVE num site de verdade, e o clique do operador É a
  // autorização. O backend recusa antes de chamar o motor quando a página já
  // está publicada (evita um SEGUNDO post para a mesma página), quando o run
  // ainda está rodando, quando o portão barrou, ou quando falta credencial.
  publicarPagina(runRowId: number, pageNumber: number): Promise<PublicacaoDePagina> {
    return request(
      `/api/publicacao/redator/runs/${runRowId}/publicar/${pageNumber}`,
      { method: 'POST' },
    );
  },

  // A URL de uma imagem gerada pelo motor. É montada aqui e não no componente
  // porque só este módulo conhece a base do backend — o front e a API são dois
  // projetos Vercel distintos.
  /**
   * Um artefato do motor (imagem, prova visual), como `blob:` URL autenticada.
   *
   * `<img src>` não manda cabeçalho, então a URL direta parava de funcionar
   * quando a rota ganhou portão. O hook `useArtefatoAutenticado` embrulha esta
   * função e cuida do `revokeObjectURL`.
   */
  async artefatoBlobUrl(runRowId: number, nome: string, versao?: string | number): Promise<string> {
    const q = versao != null ? `?v=${encodeURIComponent(String(versao))}` : '';
    return baixarComoBlobUrl(
      `/api/publicacao/redator/runs/${runRowId}/arquivo/${encodeURIComponent(nome)}${q}`,
    );
  },

  /** @deprecated URL crua, sem credencial. A rota exige identidade desde
   *  24/08/2026 — use `artefatoBlobUrl`. Mantida só porque o `versao` documenta
   *  a quebra de cache da prova visual, que continua valendo. */
  urlDoArtefato(runRowId: number, nome: string, versao?: string | number): string {
    // ⚠️ `versao` existe por causa do `Cache-Control: max-age=86400` da rota de
    // artefatos. Ele é correto para imagem do motor — run encerrado nunca
    // reescreve artefato — mas a PROVA VISUAL é sobrescrita a cada clique. Sem
    // quebrar o cache, "tirar print" mostraria a foto de ontem e o operador
    // aprovaria uma página olhando o estado antigo dela.
    const q = versao != null ? `?v=${encodeURIComponent(String(versao))}` : '';
    return url(`/api/publicacao/redator/runs/${runRowId}/arquivo/${encodeURIComponent(nome)}${q}`);
  },

  // Fotografa a página publicada, inteira, rolando. ~20 s medidos na LP do
  // run 7. Não cria nem altera nada — nem aqui, nem no WordPress.
  tirarProvaVisual(runRowId: number, pageNumber: number): Promise<ProvaVisual> {
    return request(`/api/publicacao/redator/runs/${runRowId}/prova-visual/${pageNumber}`,
                   { method: 'POST' });
  },

  // A matriz páginas × etapas de um run.
  //
  // Não passa pelo `request()` genérico porque precisa do ETag e do 304, e
  // `request()` engole a `Response` e trata !ok como erro — um 304 viraria
  // exceção. Aqui, 304 é o caminho FELIZ e o mais comum: durante os ~45 min de
  // um run a tela pergunta a cada 3s (~900 consultas) e só ~30 delas trazem
  // etapa nova. Sem o 304, seriam ~36 MB para mostrar, quase sempre, exatamente
  // o que já estava na tela.
  async matrizDoRun(runRowId: number, etagAnterior?: string | null): Promise<RespostaDaMatriz> {
    if (!API_BASE) {
      throw new PautadorApiError(
        'VITE_PAUTADOR_API_URL não configurada. Configure a URL do backend Pautador Pro.',
        0,
      );
    }
    let resp: Response;
    try {
      resp = await fetch(url(`/api/publicacao/redator/runs/${runRowId}/matriz`), {
        headers: {
          'Content-Type': 'application/json',
          ...(await autorizacao()),
          ...(etagAnterior ? { 'If-None-Match': etagAnterior } : {}),
        },
      });
    } catch {
      throw new PautadorApiError(
        `Não foi possível conectar ao backend Pautador Pro em ${API_BASE}.`, 0);
    }
    if (resp.status === 304) {
      return { matriz: null, etag: etagAnterior ?? null, mudou: false };
    }
    if (!resp.ok) {
      let detail = '';
      try {
        const body = await resp.json();
        detail = body?.detail || '';
      } catch { /* corpo não-JSON: fica o status */ }
      throw new PautadorApiError(detail || `Erro ${resp.status} ao ler a matriz.`, resp.status);
    }
    return {
      matriz: (await resp.json()) as MatrizDoRun,
      etag: resp.headers.get('etag'),
      mudou: true,
    };
  },
};
