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

export interface ConversaDaBia {
  id: string;
  titulo: string | null;
  criada_em: string;
  atualizada_em: string;
}

export interface ExecucaoDaBia {
  id: string;
  conversa_id: string;
  request_id: string;
  estado: EstadoDaExecucao;
  entrada: string;
  resposta: string | null;
  erro: { codigo: string; mensagem: string | null } | null;
  contexto: ContextoPedido | null;
  criada_em: string;
  terminada_em: string | null;
}

export interface EstadoDaBia {
  modo: 'consulta';
  aviso: string;
  motor_configurado: boolean;
  limites: { max_caracteres: number; envios_por_minuto: number; espera_maxima_s: number };
  capacidades: string[];
}

export interface PedidoDeEnvio {
  request_id: string;
  texto: string;
  contexto?: ContextoPedido;
}
