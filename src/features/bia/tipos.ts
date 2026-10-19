/**
 * Contrato de `/api/agent/*` (backend/app/agente_bia/rotas.py), do lado do front.
 *
 * Não há aqui nenhum campo de modelo, provider, profile, instrução, sessão do
 * Hermes, ferramenta, URL, SQL, tabela, tenant ou usuário: o servidor recusa
 * todos, e o tipo não deixa nem escrevê-los.
 */

export type EstadoDaExecucao =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'uncertain'
  | 'cancelled';

export const TERMINAIS: ReadonlySet<EstadoDaExecucao> = new Set(['succeeded', 'failed', 'cancelled']);

export type JanelaDeContexto = 'ultimos_7_dias' | 'ultimos_14_dias' | 'ultimos_30_dias';

export interface ContextoPedido {
  campaign_ref: string;
  janela: JanelaDeContexto;
}

export interface AnexoReferencia {
  id: string;
  nome: string;
  tipo: string;
  familia: 'imagem' | 'documento';
  tamanho: number;
}

export interface AnexoDaBia extends AnexoReferencia {
  mime: string;
  sha256: string;
  criado_em: string;
  expira_em: string;
  paginas: number | null;
  largura: number | null;
  altura: number | null;
  caracteres: number | null;
  truncado: boolean;
}

export interface ConversaDaBia {
  id: string;
  titulo: string | null;
  criada_em: string;
  atualizada_em: string;
  mensagens?: number;
}

export interface ExecucaoDaBia {
  id: string;
  conversa_id: string;
  request_id: string;
  estado: EstadoDaExecucao;
  entrada: string;
  resposta: string | null;
  erro: { codigo: string; mensagem: string | null } | null;
  contexto: { campanha: ContextoPedido | null; anexos: AnexoReferencia[]; intencao?: IntencaoDeEnvio } | null;
  criada_em: string;
  terminada_em: string | null;
}

export interface EstadoDaBia {
  modo: 'consulta';
  aviso: string;
  memoria: { compartilhada_com: 'telegram'; aviso: string };
  motor_configurado: boolean;
  limites: { max_caracteres: number; envios_por_minuto: number; espera_maxima_s: number };
  capacidades: string[];
}

/** Intenção tipada: o servidor monta o pedido à Bia. */
export type IntencaoDeEnvio = 'rascunho_cerebro';

export interface PedidoDeEnvio {
  request_id: string;
  texto: string;
  contexto?: ContextoPedido;
  anexos?: string[];
  intencao?: IntencaoDeEnvio;
}

export type DestinoDoCerebro = 'volc' | 'arbitragem' | 'pessoal';
export type TipoDeCaptura = 'decisao' | 'captura' | 'pendencia' | 'referencia' | 'nota';

/** O que a Bia devolve no rascunho (JSON pedido pelo servidor). */
export interface RascunhoDoCerebro {
  destino: DestinoDoCerebro;
  titulo: string;
  tipo: TipoDeCaptura;
  resumo: string;
  decisoes: string[];
  aprendizados: string[];
  pendencias: string[];
  hipoteses: string[];
  tags: string[];
}

export interface PedidoDeCaptura {
  request_id: string;
  destino: DestinoDoCerebro;
  titulo: string;
  tipo: TipoDeCaptura;
  conteudo: string;
  tags: string[];
  execucao_id?: string;
}

export interface CapturaGravada {
  cerebro: DestinoDoCerebro;
  repo: string;
  caminho: string;
  sidecar: string;
  sha256: string;
  bytes: number;
  salvo_no_servidor: boolean;
  sincronizado_github: boolean;
  git: { estado: string; commitado: boolean };
  ja_existia: boolean;
}

export interface StatusDoCerebro {
  repos: {
    cerebro: DestinoDoCerebro;
    branch: string | null;
    commit: string | null;
    commit_em: string | null;
    alteracoes: number | null;
    capturas_web_pendentes: number | null;
    a_frente: number | null;
    atras: number | null;
    ultima_busca: string | null;
    estacao_web: boolean | null;
    ok: boolean;
  }[];
  verificado_em: string | null;
  somente_leitura: true;
}

export type ClasseDeComando =
  | 'local_ui'
  | 'hermes_safe'
  | 'requires_tool'
  | 'external_mutation'
  | 'telegram_only';

export interface ComandoDoCatalogo {
  nome: string;
  descricao: string;
  args: string;
  origem: 'volc' | 'hermes_registro' | 'hermes_skill';
  classe: ClasseDeComando;
  disponivel: boolean;
  execucao: 'local' | 'backend' | null;
  motivo: string;
  equivalente_web: string | null;
  aliases: string[];
}

export interface ResultadoDoStatus {
  conversa: { mensagens: number; por_estado: Record<string, number> } | null;
  hermes: { versao: string | null; gateway: string | null } | null;
  sessao_web: {
    mensagens: number | null;
    ferramentas_usadas: number | null;
    tokens_entrada: number | null;
    tokens_saida: number | null;
    custo_estimado_usd: number | null;
  } | null;
  avisos: string[];
}

/** Evento do SSE de progresso (`GET /api/agent/runs/{id}/fluxo`). */
export type EventoDeFluxo =
  | { tipo: 'estado'; execucao: ExecucaoDaBia }
  | { tipo: 'parcial'; texto: string }
  | { tipo: 'aviso'; codigo: string };
