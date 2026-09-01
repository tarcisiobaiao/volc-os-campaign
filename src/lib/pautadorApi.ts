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
    resp = await fetch(url(path), {
      ...init,
      headers: {
        'Content-Type': 'application/json',
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

export const pautadorApi = {
  get baseUrl() {
    return API_BASE;
  },
  get configured() {
    return Boolean(API_BASE);
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
