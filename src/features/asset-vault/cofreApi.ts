/**
 * Cliente HTTP do Cofre de Ativos.
 *
 * ## Mesma porta, mesma credencial, vocabulário próprio
 *
 * O backend é o mesmo FastAPI do Pautador Pro (`VITE_PAUTADOR_API_URL`) e a
 * credencial é a mesma sessão do Supabase. O Cofre devolve
 * `{ detail: { codigo, mensagem } }` com a `mensagem` **já sanitizada no
 * servidor**, então aqui não existe tradutor de status: mostrar `mensagem`,
 * guardar `codigo` para quem for investigar.
 *
 * ## O que este arquivo nunca faz
 *
 * **Não cai para a fixture.** `fixtures.ts` continua existindo para teste
 * hermético e para o Storybook, e é só isso. Um cliente que responde com o
 * retrato editorial quando a API falha inventa um inventário: a pessoa vê oito
 * ativos plausíveis e conclui que o Cofre está no ar. Aqui a falha é uma falha,
 * e a tela tem um estado próprio para ela — diferente do estado vazio, que
 * também é um fato legítimo.
 *
 * **Não monta o localizador de nada.** O endereço do item no 1Password não
 * chega neste arquivo porque não sai do banco: `cofre_postura_credencial`
 * projeta provider, nome lógico, finalidade, estado e frescor, e omite o
 * endereço. Se algum dia um `localizador` aparecer numa resposta, o defeito
 * está no backend, não aqui — e há teste dos dois lados.
 */
import { supabase } from '@/lib/supabase';

const RAW_BASE = (import.meta.env.VITE_PAUTADOR_API_URL || '').trim();
const API_BASE = RAW_BASE.replace(/\/$/, '');
const PREFIXO = '/api/cofre';

/** A falha como a tela pode falar dela. `codigo` é para o log, `message` para a frase. */
export class ErroDoCofre extends Error {
  readonly codigo: string;
  readonly status: number;
  constructor(mensagem: string, codigo: string, status: number) {
    super(mensagem);
    this.name = 'ErroDoCofre';
    this.codigo = codigo;
    this.status = status;
  }
  /** Indisponibilidade é diferente de recusa: a tela mostra telas diferentes. */
  get indisponivel(): boolean {
    return this.status === 503 || this.codigo === 'cofre_indisponivel';
  }
  get semPermissao(): boolean {
    return this.status === 403;
  }
  get semSessao(): boolean {
    return this.status === 401;
  }
}

const FRASE = {
  semBase: 'O endereço do Cofre não está configurado neste ambiente.',
  semSessao: 'Sua sessão expirou. Entre novamente para continuar.',
  semPermissao: 'O Cofre é exclusivo para administradores.',
  semRede: 'Não foi possível falar com o Cofre agora.',
  semForma: 'O Cofre respondeu em um formato que esta tela não reconhece.',
  generica: 'O Cofre não conseguiu concluir esta operação.',
} as const;

export function cofreConfigurado(): boolean {
  return Boolean(API_BASE);
}

async function autorizacao(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ErroDoCofre(FRASE.semSessao, 'sessao_ausente', 401);
  return { Authorization: `Bearer ${token}` };
}

function endereco(caminho: string, busca?: Record<string, string | boolean | undefined>): string {
  const query = new URLSearchParams();
  for (const [chave, valor] of Object.entries(busca ?? {})) {
    if (valor === undefined || valor === '' || valor === false) continue;
    query.set(chave, String(valor));
  }
  const cauda = query.toString();
  return `${API_BASE}${PREFIXO}${caminho}${cauda ? `?${cauda}` : ''}`;
}

/**
 * Lê `{ detail: { codigo, mensagem } }` sem confiar na forma.
 *
 * O corpo pode vir em HTML (proxy no meio), vazio (504 de gateway) ou com um
 * `detail` que é string. Nenhum desses ramos devolve o texto cru: um proxy que
 * responde com a própria página de erro entregaria nome de servidor e versão.
 */
async function falhaDaResposta(resp: Response): Promise<ErroDoCofre> {
  if (resp.status === 401) return new ErroDoCofre(FRASE.semSessao, 'sessao_expirada', 401);
  if (resp.status === 403) return new ErroDoCofre(FRASE.semPermissao, 'sem_permissao', 403);
  try {
    const corpo: unknown = await resp.json();
    const detail = (corpo as { detail?: unknown })?.detail;
    if (detail && typeof detail === 'object') {
      const d = detail as { codigo?: unknown; mensagem?: unknown };
      const mensagem = typeof d.mensagem === 'string' && d.mensagem.trim() ? d.mensagem : FRASE.generica;
      const codigo = typeof d.codigo === 'string' && d.codigo.trim() ? d.codigo : 'sem_codigo';
      return new ErroDoCofre(mensagem, codigo, resp.status);
    }
  } catch {
    /* corpo ausente ou não é JSON: cai na frase fechada */
  }
  if (resp.status >= 500) return new ErroDoCofre(FRASE.semRede, 'cofre_indisponivel', resp.status);
  return new ErroDoCofre(FRASE.generica, 'resposta_sem_detalhe', resp.status);
}

async function pedir<T>(caminho: string, init: RequestInit = {},
                        busca?: Record<string, string | boolean | undefined>): Promise<T> {
  if (!API_BASE) throw new ErroDoCofre(FRASE.semBase, 'sem_base', 503);
  let resp: Response;
  try {
    resp = await fetch(endereco(caminho, busca), {
      ...init,
      headers: { ...(await autorizacao()), 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    });
  } catch (erro) {
    if (erro instanceof ErroDoCofre) throw erro;
    // Rede caída é INDISPONIBILIDADE, não inventário vazio.
    throw new ErroDoCofre(FRASE.semRede, 'cofre_indisponivel', 503);
  }
  if (!resp.ok) throw await falhaDaResposta(resp);
  try {
    return (await resp.json()) as T;
  } catch {
    throw new ErroDoCofre(FRASE.semForma, 'resposta_ilegivel', resp.status);
  }
}

// ── o que a API devolve ─────────────────────────────────────────────────────

export interface GavetaDoCofre {
  cluster: string;
  rotulo: string;
  descricao: string;
  ordem: number;
  total: number;
}

export interface AtivoDaLista {
  ativo_id: string;
  nome: string;
  kind: string;
  tipo_rotulo: string;
  cluster: string;
  plataforma: string;
  estado: string;
  criticidade: string;
  resumo: string;
  dono_nome: string;
  dono_custodia: string;
  projeto?: string | null;
  vertical?: string | null;
  display_id?: string | null;
  url_publica?: string | null;
  tags: string[];
  proxima_acao: string;
  revisao_atual: number;
  aposentado_em?: string | null;
  /**
   * As arestas viajam na listagem, não só no detalhe: a visão de Relações
   * precisa delas para todos os ativos ao mesmo tempo, e buscar o detalhe de
   * cada um só para desenhar o mapa seria um N+1.
   */
  relacoes: RelacaoDeclarada[];
  /** Booleano, não endereço. A tela precisa saber SE existe referência. */
  credencial_registrada: boolean;
  verificacao_estado: string;
  verificado_em?: string | null;
}

export interface Inventario {
  gavetas: GavetaDoCofre[];
  ativos: AtivoDaLista[];
}

export interface PosturaDeCredencial {
  referencia_id: number;
  provider: string;
  nome_logico: string;
  finalidade: string;
  owner_nome: string;
  estado: string;
  valido_ate?: string | null;
  verificacao_estado: string;
  verificado_em?: string | null;
  referencia_registrada: boolean;
}

export interface VerificacaoRegistrada {
  verificacao_id: number;
  alvo: string;
  resultado: string;
  metodo: string;
  procedencia: string;
  evidencia: string;
  observado_em: string;
  proximo_ato?: string | null;
  revisar_em?: string | null;
}

export interface RevisaoRegistrada {
  revisao: number;
  operacao: string;
  motivo: string;
  autor_email: string;
  ocorrido_em: string;
}

export interface RelacaoDeclarada {
  relacao_id?: number;
  tipo: string;
  destino: string;
  rotulo: string;
  estado: string;
}

export interface PerfilDeEngine {
  modalidade: string;
  estado_operacional: string;
  versao_contrato?: string | null;
  formatos?: number | null;
  skins?: number | null;
  nichos?: number | null;
  vozes?: number | null;
  manifesto_fonte: string;
  manifesto_sha256?: string | null;
  fonte_fingerprint?: string | null;
  capacidades_observadas: string[];
  limitacoes: string[];
  requisitos: string[];
  destinos_compativeis: string[];
  verificado_em?: string | null;
}

export interface DetalheDoAtivo {
  ativo_id: string;
  nome: string;
  kind: string;
  cluster: string;
  gaveta_rotulo: string;
  tipo_rotulo: string;
  plataforma: string;
  estado: string;
  criticidade: string;
  resumo: string;
  dono_nome: string;
  dono_custodia: string;
  projeto?: string | null;
  vertical?: string | null;
  display_id?: string | null;
  url_publica?: string | null;
  localizacao_rotulo?: string | null;
  capacidades: string[];
  tags: string[];
  proxima_acao: string;
  revisao_atual: number;
  aposentado_em?: string | null;
  aposentado_motivo?: string | null;
  criado_em: string;
  atualizado_em: string;
  engine?: PerfilDeEngine | null;
  relacoes: RelacaoDeclarada[];
  credencial: PosturaDeCredencial[];
  verificacao: VerificacaoRegistrada[];
  historico: RevisaoRegistrada[];
}

export interface EngineDisponivel extends PerfilDeEngine {
  ativo_id: string;
  nome: string;
  estado: string;
  localizacao_rotulo?: string | null;
}

export interface Recibo {
  operacao: string;
  ativo_id?: string;
  revisao?: number;
  relacao_id?: number;
  referencia_id?: number;
  verificacao_id?: number;
  idempotente: boolean;
}

// ── leitura ─────────────────────────────────────────────────────────────────

export function inventario(filtros: {
  cluster?: string; kind?: string; estado?: string; busca?: string; incluirAposentados?: boolean;
} = {}): Promise<Inventario> {
  return pedir<Inventario>('/ativos', {}, {
    cluster: filtros.cluster,
    kind: filtros.kind,
    estado: filtros.estado,
    busca: filtros.busca,
    incluir_aposentados: filtros.incluirAposentados,
  });
}

export function detalhe(ativoId: string): Promise<DetalheDoAtivo> {
  return pedir<DetalheDoAtivo>(`/ativos/${encodeURIComponent(ativoId)}`);
}

export function posturaDeCredencial(ativoId: string): Promise<{ credenciais: PosturaDeCredencial[] }> {
  return pedir(`/ativos/${encodeURIComponent(ativoId)}/credencial`);
}

export function engines(): Promise<{ engines: EngineDisponivel[] }> {
  return pedir('/engines');
}

// ── escrita ─────────────────────────────────────────────────────────────────

/**
 * Chave de idempotência derivada do ATO, não sorteada.
 *
 * Sorteá-la faria cada clique no botão "Cadastrar" valer como operação nova —
 * inclusive o segundo clique de quem achou que o primeiro não pegou. Derivada
 * do ativo e do tipo de ato, o retry devolve o recibo guardado e o servidor
 * responde 200 com `X-Cofre-Idempotente: replay`.
 *
 * ⚠️ O sufixo de janela é DELIBERADO e tem custo: dois atos iguais sobre o
 * mesmo ativo dentro do mesmo minuto compartilham chave. É o que se quer para
 * um duplo-clique; não é o que se quer para duas edições distintas em sequência
 * rápida — e por isso as revisões incluem um resumo das mudanças na chave.
 */
export function chaveDoAto(ato: string, ativoId: string, discriminante = ''): string {
  const janela = Math.floor(Date.now() / 60_000);
  const bruto = `${ato}:${ativoId}:${discriminante}:${janela}`;
  let hash = 0;
  for (let i = 0; i < bruto.length; i += 1) {
    hash = (hash * 31 + bruto.charCodeAt(i)) | 0;
  }
  return `${ato}-${Math.abs(hash).toString(36)}-${janela}`.slice(0, 120);
}

export function cadastrarAtivo(corpo: Record<string, unknown>): Promise<Recibo> {
  return pedir<Recibo>('/ativos', { method: 'POST', body: JSON.stringify(corpo) });
}

export function revisarAtivo(ativoId: string, corpo: Record<string, unknown>): Promise<Recibo> {
  return pedir<Recibo>(`/ativos/${encodeURIComponent(ativoId)}`, {
    method: 'PATCH', body: JSON.stringify(corpo),
  });
}

export function relacionar(ativoId: string, corpo: Record<string, unknown>): Promise<Recibo> {
  return pedir<Recibo>(`/ativos/${encodeURIComponent(ativoId)}/relacoes`, {
    method: 'POST', body: JSON.stringify(corpo),
  });
}

export function aposentar(ativoId: string, corpo: Record<string, unknown>): Promise<Recibo> {
  return pedir<Recibo>(`/ativos/${encodeURIComponent(ativoId)}/aposentadoria`, {
    method: 'POST', body: JSON.stringify(corpo),
  });
}

export function reativar(ativoId: string, corpo: Record<string, unknown>): Promise<Recibo> {
  return pedir<Recibo>(`/ativos/${encodeURIComponent(ativoId)}/reativacao`, {
    method: 'POST', body: JSON.stringify(corpo),
  });
}

export function registrarVerificacao(ativoId: string, corpo: Record<string, unknown>): Promise<Recibo> {
  return pedir<Recibo>(`/ativos/${encodeURIComponent(ativoId)}/verificacoes`, {
    method: 'POST', body: JSON.stringify(corpo),
  });
}

/**
 * Registra ONDE a credencial mora. O valor nunca passa por aqui — e o campo
 * `localizador` do formulário é o único do sistema inteiro que aceita uma
 * secret reference, com a gramática validada no servidor.
 */
export function referenciarCredencial(ativoId: string, corpo: Record<string, unknown>): Promise<Recibo> {
  return pedir<Recibo>(`/ativos/${encodeURIComponent(ativoId)}/credencial`, {
    method: 'POST', body: JSON.stringify(corpo),
  });
}
