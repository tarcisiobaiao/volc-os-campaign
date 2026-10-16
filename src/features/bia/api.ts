/**
 * Cliente de `/api/agent/*` — o `secureApi` existente, apontado para o FastAPI.
 *
 * Mesma porta de todas as rotas nomeadas: access token da sessão Supabase do
 * usuário logado, falha fechada sem sessão, `ErroDeApi` com status e código.
 * A base é `VITE_PAUTADOR_API_URL`, a MESMA do resto do FastAPI
 * (`src/lib/pautadorApi.ts`). O navegador nunca fala com o Hermes: não existe
 * URL, chave ou sessão do Hermes neste bundle.
 *
 * Duas exceções ao `secureApi`, ambas pelo mesmo token da sessão:
 * - upload por XMLHttpRequest, porque só ele informa progresso de envio;
 * - progresso da execução por `fetch` em streaming (SSE), porque EventSource
 *   não envia cabeçalho de autorização.
 */
import { ErroDeApi, SecureApiClient } from '@/lib/secureApi';
import { supabase } from '@/lib/supabase';

import type {
  AnexoDaBia,
  CapturaGravada,
  ComandoDoCatalogo,
  ConversaDaBia,
  EstadoDaBia,
  EventoDeFluxo,
  ExecucaoDaBia,
  PedidoDeCaptura,
  PedidoDeEnvio,
  ResultadoDoStatus,
  StatusDoCerebro,
} from './tipos';

const BASE = (import.meta.env.VITE_PAUTADOR_API_URL || '').trim().replace(/\/$/, '');
const cliente = new SecureApiClient(BASE);

const corpo = (dados: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(dados) });
const id = (valor: string) => encodeURIComponent(valor);

async function tokenDaSessao(): Promise<string> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ErroDeApi('Sessão expirada. Faça login novamente.', 401, 'SEM_SESSAO');
  return token;
}

function erroDoCorpo(status: number, texto: string): ErroDeApi {
  try {
    const json = JSON.parse(texto);
    const d = json.detail;
    const mensagem = (typeof d === 'string' ? d : d?.mensagem) || `Falha (${status})`;
    return new ErroDeApi(mensagem, status, typeof d === 'object' ? d?.codigo : undefined);
  } catch {
    return new ErroDeApi(`Falha (${status})`, status);
  }
}

export interface EnvioDeAnexo {
  promessa: Promise<AnexoDaBia>;
  cancelar: () => void;
}

export const biaApi = {
  estado: () => cliente.requisitar<EstadoDaBia>('/api/agent/estado'),

  novaConversa: () =>
    cliente.requisitar<{ conversa: ConversaDaBia }>('/api/agent/conversations', corpo({})),

  conversas: () => cliente.requisitar<{ conversas: ConversaDaBia[] }>('/api/agent/conversations'),

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

  comandos: () => cliente.requisitar<{ comandos: ComandoDoCatalogo[] }>('/api/agent/comandos'),

  executarComando: (nome: string, conversaId: string | null) =>
    cliente.requisitar<{ comando: string; resultado: ResultadoDoStatus; recibo: Record<string, unknown> }>(
      `/api/agent/comandos/${id(nome)}`,
      corpo(conversaId ? { conversa_id: conversaId } : {}),
    ),

  /** Status git dos três cérebros, só leitura (executor tipado no VPS). */
  cerebroStatus: () => cliente.requisitar<StatusDoCerebro>('/api/agent/cerebro/status'),

  /** Grava UMA captura nova na estação `inbox/bia-web/`. Mesmo request_id = mesmo arquivo. */
  gravarCaptura: (pedido: PedidoDeCaptura) =>
    cliente.requisitar<{ captura: CapturaGravada }>('/api/agent/cerebro/capturas', corpo(pedido)),

  removerAnexo: (anexoId: string) =>
    cliente.requisitar<{ removido: boolean }>(`/api/agent/anexos/${id(anexoId)}/remover`, corpo({})),

  /** Envia UM arquivo, com progresso (0–1). Corpo bruto; o nome vai no cabeçalho. */
  enviarAnexo(arquivo: File, aoProgresso: (fracao: number) => void): EnvioDeAnexo {
    const xhr = new XMLHttpRequest();
    const promessa = (async () => {
      const token = await tokenDaSessao();
      return new Promise<AnexoDaBia>((resolver, rejeitar) => {
        xhr.open('POST', `${BASE}/api/agent/anexos`);
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        xhr.setRequestHeader('X-Bia-Nome', encodeURIComponent(arquivo.name));
        if (arquivo.type) xhr.setRequestHeader('Content-Type', arquivo.type);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) aoProgresso(e.loaded / e.total);
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolver((JSON.parse(xhr.responseText) as { anexo: AnexoDaBia }).anexo);
          } else {
            rejeitar(erroDoCorpo(xhr.status, xhr.responseText));
          }
        };
        xhr.onerror = () => rejeitar(new ErroDeApi('A rede falhou durante o envio.', 0, 'REDE'));
        xhr.onabort = () => rejeitar(new ErroDeApi('Envio cancelado.', 0, 'CANCELADO'));
        xhr.send(arquivo);
      });
    })();
    return { promessa, cancelar: () => xhr.abort() };
  },

  /** Miniatura/arquivo do PRÓPRIO anexo como `blob:` (o servidor exige o token). */
  async urlDoAnexo(anexoId: string): Promise<string> {
    const token = await tokenDaSessao();
    const r = await fetch(`${BASE}/api/agent/anexos/${id(anexoId)}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!r.ok) throw erroDoCorpo(r.status, await r.text());
    return URL.createObjectURL(await r.blob());
  },

  /**
   * Assina o progresso de UMA execução. Só leitura: cair e assinar de novo nunca
   * reenvia nada. Resolve quando o servidor encerra o fluxo; rejeita na falha.
   */
  async acompanhar(execucaoId: string, aoEvento: (e: EventoDeFluxo) => void, sinal: AbortSignal): Promise<void> {
    const token = await tokenDaSessao();
    const r = await fetch(`${BASE}/api/agent/runs/${id(execucaoId)}/fluxo`, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
      signal: sinal,
    });
    if (!r.ok || !r.body) throw erroDoCorpo(r.status, await r.text());
    const leitor = r.body.getReader();
    const decodificador = new TextDecoder();
    let pendente = '';
    for (;;) {
      const { value, done } = await leitor.read();
      if (done) break;
      pendente += decodificador.decode(value, { stream: true });
      let fim: number;
      while ((fim = pendente.indexOf('\n\n')) >= 0) {
        const bloco = pendente.slice(0, fim);
        pendente = pendente.slice(fim + 2);
        let nome = '';
        let dados = '';
        for (const linha of bloco.split('\n')) {
          if (linha.startsWith('event:')) nome = linha.slice(6).trim();
          else if (linha.startsWith('data:')) dados += linha.slice(5).trim();
        }
        if (!nome || !dados) continue;
        const json = JSON.parse(dados);
        if (nome === 'estado') aoEvento({ tipo: 'estado', execucao: json.execucao });
        else if (nome === 'parcial') aoEvento({ tipo: 'parcial', texto: json.texto });
        else if (nome === 'aviso') aoEvento({ tipo: 'aviso', codigo: json.codigo });
      }
    }
  },
};

export type BiaApi = typeof biaApi;
