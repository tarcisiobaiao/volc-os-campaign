/**
 * Cliente HTTP de `/api/trafego/gestao` (contrato GADS-GESTAO v1).
 *
 * ## Autenticação
 *
 * O mesmo mecanismo de `pautadorApi.ts`: o access token da sessão do Supabase
 * vai como `Authorization: Bearer`, e a base é `VITE_PAUTADOR_API_URL`. A
 * função de lá (`autorizacao`) não é exportada e aquele arquivo não é desta
 * frente, então o mecanismo é refeito aqui com a MESMA fonte (`supabase.auth.
 * getSession()`), sem fallback anônimo: sem sessão, falha antes da rede.
 *
 * ⚠️ `@/lib/supabase` é importado tarde (na chamada). O módulo dele lança no
 * import quando falta configuração, e esta página é montada em testes que
 * dublam só o `pautadorApi`; um import no topo derrubaria a página inteira por
 * causa de um painel que nem chegou a ser usado.
 *
 * ## Erros
 *
 * Toda recusa da gestão chega como `{"detail": {codigo, mensagem, detalhe?}}`
 * e vira `ErroDaGestao` com `status`, `codigo` e `corpo` — a tela decide pela
 * `codigo` (ver `gestao/erros.ts`), nunca pela mensagem.
 */
import type {
  CorpoDeErroDaGestao,
  PedidoDeAprovacao,
  PedidoDeImportacao,
  PedidoDeProposta,
  PedidoDeRecusa,
  PedidoDeReversao,
  RespostaDaAplicacao,
  RespostaDaDecisao,
  RespostaDaImportacao,
  RespostaDaProposta,
  RespostaDaReversao,
  RespostaDaVerificacao,
  RespostaDeRecomendacoes,
  RespostaDoPainel,
} from '@/types/gestao';

const BASE = '/api/trafego/gestao';

function apiBase(): string {
  return String(import.meta.env.VITE_PAUTADOR_API_URL || '').trim().replace(/\/$/, '');
}

export class ErroDaGestao extends Error {
  status: number;
  /** `codigo` estável do contrato; `null` quando o servidor não mandou um. */
  codigo: string | null;
  detalhe: unknown;
  /** O `detail` cru, quando objeto — mesmo nome que `PautadorApiError.corpo`. */
  corpo?: unknown;
  constructor(mensagem: string, status: number, corpo?: unknown) {
    super(mensagem);
    this.name = 'ErroDaGestao';
    this.status = status;
    this.corpo = corpo;
    const c = corpo as Partial<CorpoDeErroDaGestao> | undefined;
    this.codigo = c && typeof c === 'object' && typeof c.codigo === 'string' ? c.codigo : null;
    this.detalhe = c && typeof c === 'object' ? c.detalhe : undefined;
  }
}

type FonteDeToken = () => Promise<string | null>;

async function tokenDaSessao(): Promise<string | null> {
  const { supabase } = await import('@/lib/supabase');
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

let fonteDeToken: FonteDeToken = tokenDaSessao;

/** Só para teste: troca a origem do token. Devolve a função que restaura. */
export function trocarFonteDeToken(fonte: FonteDeToken): () => void {
  const anterior = fonteDeToken;
  fonteDeToken = fonte;
  return () => {
    fonteDeToken = anterior;
  };
}

async function chamar<T>(caminho: string, init: RequestInit = {}): Promise<T> {
  const base = apiBase();
  if (!base) {
    throw new ErroDaGestao('VITE_PAUTADOR_API_URL não configurada.', 0);
  }
  let token: string | null;
  try {
    token = await fonteDeToken();
  } catch {
    token = null;
  }
  if (!token) {
    throw new ErroDaGestao('Sessão expirada. Faça login novamente.', 401);
  }
  let resp: Response;
  try {
    resp = await fetch(`${base}${BASE}${caminho}`, {
      ...init,
      headers: {
        ...(init.body != null ? { 'Content-Type': 'application/json' } : {}),
        Authorization: `Bearer ${token}`,
        ...(init.headers || {}),
      },
    });
  } catch {
    throw new ErroDaGestao(
      `Não foi possível conectar ao backend em ${base}. Confira se ele está no ar.`,
      0,
    );
  }
  if (!resp.ok) {
    let corpo: unknown;
    let mensagem = '';
    try {
      const body = await resp.json();
      const d = body?.detail;
      if (d && typeof d === 'object') {
        corpo = d;
        mensagem = String((d as { mensagem?: string }).mensagem || '');
      } else if (typeof d === 'string') {
        mensagem = d;
      }
    } catch {
      /* sem corpo JSON */
    }
    throw new ErroDaGestao(mensagem || `Erro ${resp.status}.`, resp.status, corpo);
  }
  return resp.json() as Promise<T>;
}

function json(corpo: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(corpo) };
}

const seg = encodeURIComponent;

export const gestaoApi = {
  /** §3.1 — `trafego_proposta_painel` da conta, mais recentes primeiro. */
  propostas(customerId: string, opcoes: { estado?: string; limite?: number } = {}) {
    const q = new URLSearchParams({ customer_id: customerId });
    if (opcoes.estado) q.set('estado', opcoes.estado);
    if (opcoes.limite) q.set('limite', String(opcoes.limite));
    return chamar<RespostaDoPainel>(`/propostas?${q}`);
  },

  /** §3.2 — 201 nova, 200 já existia. Não escreve no Google. */
  propor(pedido: PedidoDeProposta) {
    return chamar<RespostaDaProposta>('/propostas', json(pedido));
  },

  /** §3.3 (admin) — `diff_apresentado` é o que a tela MOSTROU. */
  aprovar(propostaId: string, pedido: PedidoDeAprovacao) {
    return chamar<RespostaDaDecisao>(`/propostas/${seg(propostaId)}/aprovar`, json(pedido));
  },

  /** §3.4 (admin) — motivo obrigatório. */
  recusar(propostaId: string, pedido: PedidoDeRecusa) {
    return chamar<RespostaDaDecisao>(`/propostas/${seg(propostaId)}/recusar`, json(pedido));
  },

  /** §3.5 (admin) — sem corpo. Escreve no Google. */
  aplicar(propostaId: string) {
    return chamar<RespostaDaAplicacao>(`/propostas/${seg(propostaId)}/aplicar`, {
      method: 'POST',
    });
  },

  /** §3.6 — relê a conta e compara com o proposto. */
  verificar(aplicacaoId: string) {
    return chamar<RespostaDaVerificacao>(`/aplicacoes/${seg(aplicacaoId)}/verificar`, {
      method: 'POST',
    });
  },

  /** §3.7 (admin) — motivo obrigatório. */
  reverter(aplicacaoId: string, pedido: PedidoDeReversao) {
    return chamar<RespostaDaReversao>(`/aplicacoes/${seg(aplicacaoId)}/reverter`, json(pedido));
  },

  /** §3.8 — identidade para campanha que não nasceu pelo VOLC. */
  importarCampanha(pedido: PedidoDeImportacao) {
    return chamar<RespostaDaImportacao>('/campanhas/importar', json(pedido));
  },

  /** §3.9 — recomendações não dispensadas (lê o Google). */
  recomendacoes(customerId: string) {
    const q = new URLSearchParams({ customer_id: customerId });
    return chamar<RespostaDeRecomendacoes>(`/recomendacoes?${q}`);
  },
};

export type GestaoApi = typeof gestaoApi;
