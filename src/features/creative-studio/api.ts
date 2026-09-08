/**
 * O cliente HTTP do Assistente Criativo.
 *
 * ## A porta certa, que não é a que `/api` sugere
 *
 * O Vite proxeia `/api` para a **3001**, que é o servidor Node — e o
 * Assistente vive no FastAPI da **8010**. Uma chamada relativa a `/api/...`
 * daqui responde 404 e parece "rota inexistente" quando o problema é ter
 * batido em outro processo. Por isso a base é absoluta, montada de
 * `VITE_PAUTADOR_API_URL`, exatamente como `src/lib/criativosApi.ts` faz.
 *
 * ## Uma credencial só
 *
 * A sessão do Supabase, no cabeçalho `Authorization`. Não existe segundo login,
 * não existe chave no bundle e não existe token na query string. Se não há
 * sessão, a chamada falha ANTES da rede, com a frase que a tela mostra.
 *
 * ## As frases são fechadas
 *
 * O servidor devolve `{ detail: { codigo, mensagem } }` com a `mensagem` já
 * sanitizada. Quando não devolve — proxy no meio, 504 de gateway, corpo em
 * HTML — a tela recebe uma frase da lista abaixo, nunca o corpo cru: uma
 * página de erro de proxy entregaria nome de servidor e versão de software.
 */
import { supabase } from '@/lib/supabase';

import type {
  Anexo,
  AutorizacaoDeGasto,
  Capacidades,
  DecisaoRegistrada,
  EntradaNovaOperacao,
  GeracaoRegistrada,
  OperacaoCompleta,
  OperacaoEnfileirada,
  PedidoDeContinuacao,
  PedidoDeDecisao,
  PlanoDeGeracao,
  ResumoDaOperacao,
  RunEnfileirada,
  RunExecutada,
} from './tipos';

const RAW_BASE = (import.meta.env.VITE_PAUTADOR_API_URL || '').trim();
const API_BASE = RAW_BASE.replace(/\/$/, '');
const PREFIXO = '/api/criativos/meta/agente';

export class ErroDoAssistente extends Error {
  readonly codigo: string;
  constructor(mensagem: string, codigo: string) {
    super(mensagem);
    this.name = 'ErroDoAssistente';
    this.codigo = codigo;
  }
}

const FRASE = {
  semBase: 'O endereço do Assistente não está configurado neste ambiente.',
  semSessao: 'Sua sessão expirou. Entre novamente para continuar.',
  semRede: 'Não foi possível falar com o Assistente agora.',
  semForma: 'O Assistente respondeu em um formato que esta tela não reconhece.',
  generica: 'O Assistente não conseguiu concluir esta operação.',
} as const;

export function assistenteConfigurado(): boolean {
  return Boolean(API_BASE);
}

async function autorizacao(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ErroDoAssistente(FRASE.semSessao, 'sessao_ausente');
  return { Authorization: `Bearer ${token}` };
}

function endereco(
  caminho: string,
  busca?: Record<string, string | number | undefined>,
): string {
  const query = new URLSearchParams();
  for (const [chave, valor] of Object.entries(busca ?? {})) {
    if (valor === undefined || valor === '') continue;
    query.set(chave, String(valor));
  }
  const cauda = query.toString();
  return `${API_BASE}${PREFIXO}${caminho}${cauda ? `?${cauda}` : ''}`;
}

async function falhaDaResposta(resp: Response): Promise<ErroDoAssistente> {
  if (resp.status === 401) return new ErroDoAssistente(FRASE.semSessao, 'sessao_expirada');
  try {
    const corpo: unknown = await resp.json();
    const detail = (corpo as { detail?: unknown })?.detail;
    if (detail && typeof detail === 'object') {
      const d = detail as { codigo?: unknown; mensagem?: unknown };
      const mensagem =
        typeof d.mensagem === 'string' && d.mensagem.trim() ? d.mensagem : FRASE.generica;
      const codigo = typeof d.codigo === 'string' && d.codigo.trim() ? d.codigo : 'sem_codigo';
      return new ErroDoAssistente(mensagem, codigo);
    }
  } catch {
    /* corpo ausente ou não-JSON: cai na frase fechada */
  }
  return new ErroDoAssistente(FRASE.generica, 'resposta_sem_detalhe');
}

async function chamar<T>(url: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) throw new ErroDoAssistente(FRASE.semBase, 'base_ausente');
  let resp: Response;
  try {
    resp = await fetch(url, {
      ...init,
      headers: {
        // ⚠️ `FormData` NÃO recebe `Content-Type`. O browser precisa escrever o
        // cabeçalho inteiro, com o `boundary` que ele sorteia; declarar
        // `application/json` — ou mesmo `multipart/form-data` sem boundary —
        // produz um corpo que o servidor não consegue separar em partes.
        ...(init?.body && !(init.body instanceof FormData)
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...(await autorizacao()),
        ...(init?.headers ?? {}),
      },
    });
  } catch (erro) {
    if (erro instanceof ErroDoAssistente) throw erro;
    // AbortController no desmonte não é falha de rede: quem cancelou fomos nós.
    if (erro instanceof DOMException && erro.name === 'AbortError') throw erro;
    throw new ErroDoAssistente(FRASE.semRede, 'rede_indisponivel');
  }
  if (!resp.ok) throw await falhaDaResposta(resp);
  if (resp.status === 204) return undefined as T;
  try {
    return (await resp.json()) as T;
  } catch {
    throw new ErroDoAssistente(FRASE.semForma, 'corpo_ilegivel');
  }
}

// ── Histórico ────────────────────────────────────────────────────────────────

export async function listarOperacoes(
  opcoes: { limite?: number; offset?: number; signal?: AbortSignal } = {},
): Promise<{ operacoes: ResumoDaOperacao[]; limite: number; offset: number }> {
  const { limite = 20, offset = 0, signal } = opcoes;
  return chamar(endereco('/operacoes', { limite, offset }), { signal });
}

export async function lerOperacao(
  projectRef: string,
  signal?: AbortSignal,
): Promise<OperacaoCompleta> {
  return chamar(endereco(`/operacoes/${projectRef}`), { signal });
}

// ── Estratégia ───────────────────────────────────────────────────────────────

/**
 * Cria a operação e ENFILEIRA a primeira run. Não gera nada.
 *
 * Devolve `project_ref` e `run_ref` na hora: se a aba fechar no segundo
 * seguinte, a operação está no histórico e a run está retomável.
 */
export async function criarOperacao(
  entrada: EntradaNovaOperacao,
  signal?: AbortSignal,
): Promise<OperacaoEnfileirada> {
  return chamar(endereco('/operacoes'), {
    method: 'POST',
    body: JSON.stringify(entrada),
    signal,
  });
}

export async function enfileirarRun(
  projectRef: string,
  pedido: PedidoDeContinuacao,
  signal?: AbortSignal,
): Promise<RunEnfileirada> {
  return chamar(endereco(`/operacoes/${projectRef}/runs`), {
    method: 'POST',
    body: JSON.stringify(pedido),
    signal,
  });
}

/**
 * Executa uma run enfileirada. É a ÚNICA chamada que faz o modelo rodar, e ela
 * só acontece por clique explícito — nunca ao montar a página, listar ou
 * reconectar.
 */
export async function executarRun(
  projectRef: string,
  runRef: string,
  signal?: AbortSignal,
): Promise<RunExecutada> {
  return chamar(endereco(`/operacoes/${projectRef}/runs/${runRef}/executar`), {
    method: 'POST',
    signal,
  });
}

// ── Decisão ──────────────────────────────────────────────────────────────────

export async function registrarDecisao(
  projectRef: string,
  pedido: PedidoDeDecisao,
  signal?: AbortSignal,
): Promise<DecisaoRegistrada> {
  return chamar(endereco(`/operacoes/${projectRef}/decisoes`), {
    method: 'POST',
    body: JSON.stringify(pedido),
    signal,
  });
}

/**
 * O caminho estável de um elemento do lote.
 *
 * Existe aqui, e não espalhado pelos componentes, porque a regra é uma só e é
 * fácil de errar: dentro de lista o segmento é o `ref`, nunca a posição. O
 * servidor recusa índice — e recusa DEPOIS de o operador ter clicado em
 * aprovar, que é o pior momento para descobrir.
 */
export function caminhoDe(colecao: string, ref: string, campo?: string): string {
  return `/${colecao}/${ref}${campo ? `/${campo}` : ''}`;
}

// ── Capacidades ──────────────────────────────────────────────────────────────

/**
 * O que este servidor sabe produzir: formatos, motor e modos de composição.
 *
 * ⚠️ Aqui morava `FORMATOS_DO_MOTOR`, uma terceira cópia do catálogo escrita à
 * mão. Ela tinha TRÊS slots enquanto `backend/app/criativo/dominio.py:FORMATOS`
 * produzia quatro: o `1.91x1` nunca apareceu no Assistente, e nenhum teste
 * falhou, porque uma constante desatualizada não quebra nada — ela só some da
 * tela.
 *
 * A cópia foi apagada em vez de corrigida. Um catálogo buscado do servidor não
 * pode divergir dele, porque não existe segunda lista para divergir.
 */
export async function lerCapacidades(signal?: AbortSignal): Promise<Capacidades> {
  return chamar(endereco('/capacidades'), { signal });
}

/** Teto estratégico do agente. Espelha `MAX_VARIACOES` do contrato. */
export const MAX_PECAS = 15;

// ── Fotografia real ──────────────────────────────────────────────────────────

/**
 * Envia a fotografia. O arquivo NUNCA vira base64 no estado da tela.
 *
 * Um base64 no estado atravessa o `localStorage`, aparece em todo log que
 * registre corpo, e reaparece num projeto novo se alguém esquecer de limpar. O
 * que volta daqui é uma referência opaca e um hash — e é contra o hash que a
 * autorização de gasto é assinada, de modo que trocar a foto depois de conferir
 * o plano invalida a autorização em vez de passar despercebido.
 *
 * A validação inteira é do servidor: MIME por assinatura de bytes, teto de
 * pixels contra decompression bomb, EXIF removido. Um `accept=".png"` no input
 * é conveniência, nunca garantia.
 */
export async function enviarFotografia(
  projectRef: string,
  arquivo: File,
  signal?: AbortSignal,
): Promise<Anexo> {
  const formulario = new FormData();
  formulario.append('arquivo', arquivo, arquivo.name);
  formulario.append('consentimento', 'true');
  // Sem `Content-Type` explícito: o browser precisa escrever o `boundary`, e
  // declará-lo à mão produz um corpo que o servidor não consegue separar.
  return chamar(endereco(`/operacoes/${projectRef}/anexos`), {
    method: 'POST',
    body: formulario,
    signal,
  });
}

export async function listarFotografias(
  projectRef: string,
  signal?: AbortSignal,
): Promise<{ anexos: Anexo[] }> {
  return chamar(endereco(`/operacoes/${projectRef}/anexos`), { signal });
}

export async function removerFotografia(
  projectRef: string,
  anexoRef: string,
  signal?: AbortSignal,
): Promise<{ anexo_ref: string; removido: boolean }> {
  return chamar(endereco(`/operacoes/${projectRef}/anexos/${anexoRef}`), {
    method: 'DELETE',
    signal,
  });
}

// ── Produção ─────────────────────────────────────────────────────────────────

/**
 * Confere o pedido sem produzir nada.
 *
 * Existe separada de `gerarImagens` porque o operador tem direito de ver o
 * total, o teto e o custo — e as recusas — sem arriscar um clique que gasta.
 */
export async function planejarGeracao(
  projectRef: string,
  pedido: {
    run_ref: string;
    selected_creative_refs: string[];
    format_ids: string[];
    anexo_ref?: string | null;
    modo_de_composicao?: string;
  },
  signal?: AbortSignal,
): Promise<PlanoDeGeracao> {
  return chamar(endereco(`/operacoes/${projectRef}/geracoes/plano`), {
    method: 'POST',
    body: JSON.stringify(pedido),
    signal,
  });
}

/**
 * O ato que gasta. Só por clique explícito, nunca ao montar ou reconectar.
 *
 * O servidor RECALCULA o plano e ignora qualquer total que esta tela tenha
 * mostrado: um teto conferido no browser não é um teto.
 */
export async function gerarImagens(
  projectRef: string,
  pedido: {
    run_ref: string;
    selected_creative_refs: string[];
    format_ids: string[];
    anexo_ref?: string | null;
    modo_de_composicao?: string;
    /**
     * Obrigatória. O servidor recusa com 409 sem ela, e a recusa carrega o
     * modelo e o total que precisam ser confirmados.
     */
    autorizacao: AutorizacaoDeGasto;
  },
  signal?: AbortSignal,
): Promise<{
  geracoes: GeracaoRegistrada[];
  total_de_renders: number;
  custo_estimado_usd: number | null;
}> {
  return chamar(endereco(`/operacoes/${projectRef}/geracoes`), {
    method: 'POST',
    body: JSON.stringify(pedido),
    signal,
  });
}

export async function listarGeracoes(
  projectRef: string,
  signal?: AbortSignal,
): Promise<{ geracoes: GeracaoRegistrada[] }> {
  return chamar(endereco(`/operacoes/${projectRef}/geracoes`), { signal });
}
