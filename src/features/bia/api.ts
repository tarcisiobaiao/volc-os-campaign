/**
 * Cliente de `/api/agent/*` — o `secureApi` existente, apontado para o FastAPI.
 *
 * Mesma porta de todas as rotas nomeadas: access token da sessão Supabase do
 * usuário logado, falha fechada sem sessão, `ErroDeApi` com status e código.
 * A base é `VITE_PAUTADOR_API_URL`, a MESMA do resto do FastAPI
 * (`src/lib/pautadorApi.ts`). O navegador nunca fala com o Hermes: não existe
 * URL, chave ou sessão do Hermes neste bundle.
 */
import { SecureApiClient } from '@/lib/secureApi';

import type {
  ConversaDaBia,
  EstadoDaBia,
  ExecucaoDaBia,
  PedidoDeEnvio,
} from './tipos';

const BASE = (import.meta.env.VITE_PAUTADOR_API_URL || '').trim().replace(/\/$/, '');
const cliente = new SecureApiClient(BASE);

const corpo = (dados: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(dados) });
const id = (valor: string) => encodeURIComponent(valor);

export const biaApi = {
  estado: () => cliente.requisitar<EstadoDaBia>('/api/agent/estado'),

  novaConversa: () =>
    cliente.requisitar<{ conversa: ConversaDaBia }>('/api/agent/conversations', corpo({})),

  historico: (conversaId: string) =>
    cliente.requisitar<{ conversa: ConversaDaBia; execucoes: ExecucaoDaBia[]; aviso: string }>(
      `/api/agent/conversations/${id(conversaId)}/messages`,
    ),

  enviar: (conversaId: string, pedido: PedidoDeEnvio) =>
    cliente.requisitar<{ execucao: ExecucaoDaBia; aviso: string }>(
      `/api/agent/conversations/${id(conversaId)}/messages`,
      corpo(pedido),
    ),

  execucao: (execucaoId: string) =>
    cliente.requisitar<{ execucao: ExecucaoDaBia }>(`/api/agent/runs/${id(execucaoId)}`),

  reconciliar: (execucaoId: string) =>
    cliente.requisitar<{ execucao: ExecucaoDaBia }>(
      `/api/agent/runs/${id(execucaoId)}/reconcile`,
      corpo({}),
    ),
};

export type BiaApi = typeof biaApi;
