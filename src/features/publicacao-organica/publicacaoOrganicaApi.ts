/**
 * Cliente HTTP da publicação orgânica.
 *
 * ## Mesma porta e mesma credencial do Cofre, vocabulário próprio
 *
 * O backend é o mesmo FastAPI (`VITE_PAUTADOR_API_URL`) que serve `/api/cofre`,
 * e a credencial é a mesma sessão do Supabase. As rotas respondem
 * `{ detail: { codigo, mensagem } }` com a `mensagem` **já sanitizada no
 * servidor** por `infraestrutura._mensagem_segura` — que descarta `details` e
 * `hint` do PostgREST porque são eles que carregam a linha recusada. Aqui não
 * existe tradutor de status: mostrar `mensagem`, guardar `codigo`.
 *
 * ## O que este arquivo nunca faz
 *
 * **Não inventa idempotência.** A chave é derivada NO BACKEND
 * (`dominio.chave_de_idempotencia`), a partir de peça, versão, destino, modo,
 * horário e corpo. Mandar uma daqui não é só redundante: `JobEntrada` é
 * `extra="forbid"`, então um campo `chave` faria o pedido inteiro voltar 400.
 * O efeito prático é o que importa — reenviar o MESMO conteúdo produz a mesma
 * chave e devolve o recibo que já existe, com `idempotente: true` NO CORPO — e
 * também no header `X-Publicacao-Idempotente: replay`, que esta tela lê apenas
 * como reforço porque ele não atravessa o CORS (ver `marcarIdempotencia`).
 *
 * **Não cai para fixture nenhuma.** Não existe fixture neste módulo, e é de
 * propósito: uma tela que mostra jobs plausíveis quando a API cai afirma que a
 * publicação está no ar. Falha é falha, vazio é vazio, e a tela tem estados
 * diferentes para os dois.
 *
 * **Não manda `confirmo_publicacao_imediata` por conta própria.** O campo só
 * entra no corpo quando o humano marcou a confirmação, e só no modo `now` — o
 * backend recusa a combinação contrária com `consentimento_sem_now`. Um default
 * `true` em qualquer lugar deste arquivo seria o defeito que a missão existe
 * para não repetir.
 */
import { supabase } from '@/lib/supabase';
import { versaoDaPeca } from './contract';
import type {
  DestinoOrganico,
  DetalheDoJob,
  JobOrganico,
  ModoDePublicacao,
  ProntidaoDaPublicacao,
  RascunhoDoFormulario,
  ReciboDeOperacao,
} from './contract';

const RAW_BASE = (import.meta.env.VITE_PAUTADOR_API_URL || '').trim();
const API_BASE = RAW_BASE.replace(/\/$/, '');
const PREFIXO = '/api/publicacao-organica';

/** A falha como a tela pode falar dela. `codigo` para o log, `message` para a frase. */
export class ErroDaPublicacao extends Error {
  readonly codigo: string;
  readonly status: number;

  constructor(mensagem: string, codigo: string, status: number) {
    super(mensagem);
    this.name = 'ErroDaPublicacao';
    this.codigo = codigo;
    this.status = status;
  }

  /** Indisponibilidade é diferente de recusa: a tela mostra telas diferentes. */
  get indisponivel(): boolean {
    return this.status === 503
      || this.codigo === 'publicacao_indisponivel'
      || this.codigo === 'sem_control_plane';
  }

  get semPermissao(): boolean {
    return this.status === 403;
  }

  get semSessao(): boolean {
    return this.status === 401;
  }

  /**
   * 409 é conflito de ESTADO, não defeito: o job mudou entre a leitura e o
   * clique, ou outro consumidor assumiu. A tela pede releitura, não retry cego.
   */
  get conflito(): boolean {
    return this.status === 409;
  }
}

const FRASE = {
  semBase: 'O endereço da publicação não está configurado neste ambiente.',
  semSessao: 'Sua sessão expirou. Entre novamente para continuar.',
  semPermissao: 'A publicação orgânica é exclusiva para administradores.',
  semRede: 'Não foi possível falar com a publicação agora.',
  semForma: 'A publicação respondeu em um formato que esta tela não reconhece.',
  generica: 'A publicação não conseguiu concluir esta operação.',
} as const;

export function publicacaoConfigurada(): boolean {
  return Boolean(API_BASE);
}

async function autorizacao(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  // Sem fallback anônimo. Toda rota deste router tem `Depends(exigir_admin)`, e
  // uma chamada sem Bearer voltaria 401 — mandar assim mesmo só trocaria uma
  // frase clara ("entre de novo") por um erro de rede genérico.
  if (!token) throw new ErroDaPublicacao(FRASE.semSessao, 'sessao_ausente', 401);
  return { Authorization: `Bearer ${token}` };
}

function endereco(caminho: string, busca?: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [chave, valor] of Object.entries(busca ?? {})) {
    if (valor === undefined || valor === '') continue;
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
async function falhaDaResposta(resp: Response): Promise<ErroDaPublicacao> {
  if (resp.status === 401) return new ErroDaPublicacao(FRASE.semSessao, 'sessao_expirada', 401);
  if (resp.status === 403) return new ErroDaPublicacao(FRASE.semPermissao, 'sem_permissao', 403);
  try {
    const corpo: unknown = await resp.json();
    const detail = (corpo as { detail?: unknown })?.detail;
    if (detail && typeof detail === 'object') {
      const d = detail as { codigo?: unknown; mensagem?: unknown };
      const mensagem = typeof d.mensagem === 'string' && d.mensagem.trim() ? d.mensagem : FRASE.generica;
      const codigo = typeof d.codigo === 'string' && d.codigo.trim() ? d.codigo : 'sem_codigo';
      return new ErroDaPublicacao(mensagem, codigo, resp.status);
    }
  } catch {
    /* corpo ausente ou não é JSON: cai na frase fechada */
  }
  if (resp.status >= 500) {
    return new ErroDaPublicacao(FRASE.semRede, 'publicacao_indisponivel', resp.status);
  }
  return new ErroDaPublicacao(FRASE.generica, 'resposta_sem_detalhe', resp.status);
}

/**
 * Diz se este 200 foi REPLAY — e o CORPO é a fonte, não o header.
 *
 * ⚠️ CORREÇÃO DE UM COMENTÁRIO FALSO (02/09/2026). Este trecho afirmava que "o
 * header é a única forma de saber que um 200 foi replay". Ele não é, por dois
 * fatos medidos no repositório:
 *
 *   1. o CORPO já traz `idempotente`. `rotas._responder` lê exatamente esse
 *      campo do recibo para escolher entre 200 e 201, e o recibo inteiro vai
 *      para o cliente — é o mesmo campo que `ReciboDeOperacao` declara e que a
 *      v14_01 produz;
 *   2. o header quase nunca é legível. `backend/app/main.py` monta o
 *      `CORSMiddleware` sem `expose_headers`, e sem essa lista o navegador só
 *      entrega ao JavaScript os seis headers seguros do CORS. Numa chamada
 *      cross-origin — que é o caso do operador, front e API em domínios
 *      diferentes — `resp.headers.get('X-Publicacao-Idempotente')` devolve
 *      `null`. Confiar nele seria dizer "job criado" para todo replay.
 *
 * Então: corpo primeiro; header só como REFORÇO, para quando o campo não veio
 * no corpo (backend antigo, proxy que reescreve o JSON) e a resposta é
 * same-origin, onde o header chega.
 */
function marcarIdempotencia<T>(lido: T, resp: Response): T {
  if (!lido || typeof lido !== 'object') return lido;
  const recibo = lido as Record<string, unknown>;
  if (typeof recibo.idempotente === 'boolean') return lido;
  const marca = resp.headers?.get?.('X-Publicacao-Idempotente');
  if (marca) recibo.idempotente = marca === 'replay';
  return lido;
}

async function pedir<T>(
  caminho: string,
  init: RequestInit = {},
  busca?: Record<string, string | number | undefined>,
): Promise<T> {
  if (!API_BASE) throw new ErroDaPublicacao(FRASE.semBase, 'sem_base', 503);
  let resp: Response;
  try {
    resp = await fetch(endereco(caminho, busca), {
      ...init,
      headers: {
        ...(await autorizacao()),
        'Content-Type': 'application/json',
        ...(init.headers ?? {}),
      },
    });
  } catch (erro) {
    if (erro instanceof ErroDaPublicacao) throw erro;
    // Rede caída é INDISPONIBILIDADE, não "nenhum job".
    throw new ErroDaPublicacao(FRASE.semRede, 'publicacao_indisponivel', 503);
  }
  if (!resp.ok) throw await falhaDaResposta(resp);
  try {
    return marcarIdempotencia((await resp.json()) as T, resp);
  } catch {
    throw new ErroDaPublicacao(FRASE.semForma, 'resposta_ilegivel', resp.status);
  }
}

// ── leitura ─────────────────────────────────────────────────────────────────

export function listarDestinos(): Promise<{ destinos: DestinoOrganico[] }> {
  return pedir<{ destinos: DestinoOrganico[] }>('/destinos');
}

export function listarJobs(filtros: { estado?: string; limite?: number } = {}):
Promise<{ jobs: JobOrganico[] }> {
  return pedir<{ jobs: JobOrganico[] }>('/jobs', {}, {
    estado: filtros.estado,
    limite: filtros.limite,
  });
}

export function detalharJob(jobId: string): Promise<DetalheDoJob> {
  return pedir<DetalheDoJob>(`/jobs/${encodeURIComponent(jobId)}`);
}

/**
 * A sonda do control plane.
 *
 * ⚠️ Ela NÃO levanta no servidor — indisponível é uma RESPOSTA (`pronto: false`
 * com `fonte` e `detalhe`), não um 500. Aqui ela ainda pode falhar por rede ou
 * sessão, e nesse caso a tela mostra o mesmo que mostraria para `pronto: false`:
 * "não sei se o control plane está de pé" nunca vira "está".
 */
export function prontidao(): Promise<ProntidaoDaPublicacao> {
  return pedir<ProntidaoDaPublicacao>('/prontidao');
}

// ── escrita ─────────────────────────────────────────────────────────────────

/** O que a tela monta para criar um job. Espelha `JobEntrada` do backend. */
export interface PedidoDeJob {
  peca_id: string;
  peca_versao: number;
  autorizacao_id: string;
  destino_id: string;
  modo: ModoDePublicacao;
  timezone: string;
  /** Só em `schedule`. Em qualquer outro modo o backend recusa. */
  horario_local?: string | null;
  texto: string;
  /**
   * ⚠️ Sempre vazio nesta v1. `POST /upload` e `POST /upload-from-url` existem
   * na API oficial do Postiz e NÃO foram exercitados
   * (`portas.CAPACIDADES_NAO_EXERCITADAS`): mandar imagem exigiria decidir onde
   * o arquivo do Cofre é servido, e essa decisão é de infraestrutura. O campo
   * viaja para não mentir sobre o contrato, não porque a tela o preencha.
   */
  imagens?: string[];
  /**
   * O SIM EXPLÍCITO, e só ele.
   *
   * ⚠️ Este parâmetro é `boolean` sem default. Quem chama decide, e a decisão
   * vem de uma caixa que o humano marcou num diálogo que diz o que vai
   * acontecer. `criarJob` só o coloca no corpo quando é `true`.
   */
  confirmo_publicacao_imediata?: boolean;
}

/**
 * O corpo exato que sai para `POST /jobs`.
 *
 * Exportado por causa do teste: as duas regras que decidem o que ENTRA no corpo
 * — horário só em `schedule`, consentimento só em `now` e só quando marcado —
 * são as que um refactor futuro pode quebrar sem quebrar mais nada. Provadas
 * aqui, elas não dependem de rede, de `import.meta.env` nem de sessão.
 */
export function corpoDoPedido(pedido: PedidoDeJob): Record<string, unknown> {
  const corpo: Record<string, unknown> = {
    peca_id: pedido.peca_id,
    peca_versao: pedido.peca_versao,
    autorizacao_id: pedido.autorizacao_id,
    destino_id: pedido.destino_id,
    modo: pedido.modo,
    timezone: pedido.timezone,
    texto: pedido.texto,
    imagens: pedido.imagens ?? [],
  };
  // `horario_local` só existe em `schedule`. Mandá-lo em `draft` ou `now` faz o
  // domínio recusar com `horario_inesperado` — e recusar está certo: horário
  // num modo que o ignora é uma promessa que ninguém cumpre.
  if (pedido.modo === 'schedule' && pedido.horario_local) {
    corpo.horario_local = pedido.horario_local;
  }
  // O campo aparece SOMENTE quando o humano marcou. Fora de `now` o backend
  // recusa com `consentimento_sem_now`, e a ausência aqui é o que garante que
  // um `draft` nunca carregue consentimento de publicação imediata por herança
  // de estado esquecido no formulário.
  if (pedido.modo === 'now' && pedido.confirmo_publicacao_imediata === true) {
    corpo.confirmo_publicacao_imediata = true;
  }
  return corpo;
}

/**
 * Converte o rascunho do formulário no pedido da API.
 *
 * ⚠️ `confirmo_publicacao_imediata` recebe o valor da CAIXA, e só. Não há
 * default, não há `|| true`, e o cliente só o coloca no corpo quando é `true` e
 * o modo é `now`. Um `true` implícito em qualquer ponto desta função seria o
 * defeito que a missão existe para não repetir.
 */
export function paraPedido(rascunho: RascunhoDoFormulario, marcado: boolean): PedidoDeJob {
  const versao = versaoDaPeca(rascunho.peca_versao);
  // ⚠️ Aqui NÃO existe normalização silenciosa. Era `Math.max(1, parseInt(…) ||
  // 1)`, e essa linha transformava campo vazio em v1 sem que ninguém visse: o
  // diálogo dizia "versão " e o corpo dizia `1`. O formulário já bloqueia este
  // caso (`versaoDaPeca === null` é bloqueador), então chegar aqui com versão
  // inválida significa que alguém contornou o formulário — e a resposta certa é
  // levantar, não escolher uma revisão no lugar do humano.
  if (versao === null) {
    throw new Error('versão da peça inválida: só um inteiro a partir de 1 pode ser publicado, '
      + 'porque a aprovação cobre uma revisão exata.');
  }
  return {
    peca_id: rascunho.peca_id.trim(),
    peca_versao: versao,
    autorizacao_id: rascunho.autorizacao_id.trim(),
    destino_id: rascunho.destino_id,
    modo: rascunho.modo,
    timezone: rascunho.timezone.trim(),
    horario_local: rascunho.modo === 'schedule' ? rascunho.horario_local.trim() : null,
    texto: rascunho.texto,
    confirmo_publicacao_imediata: rascunho.modo === 'now' ? marcado : false,
  };
}

/**
 * Cria a INTENÇÃO. Nada sai daqui para o control plane.
 *
 * ⚠️ Criar não despacha, e a separação é o contrato: `gerar != aprovar !=
 * publicar`. O job nasce em `rascunho`; `liberar` e depois `despachar` são atos
 * distintos, cada um com o seu clique.
 */
export function criarJob(pedido: PedidoDeJob): Promise<ReciboDeOperacao> {
  return pedir<ReciboDeOperacao>('/jobs', {
    method: 'POST',
    body: JSON.stringify(corpoDoPedido(pedido)),
  });
}

/** Rascunho → pronto. O único caminho, e ele reconfere a aprovação. */
export function liberar(jobId: string): Promise<ReciboDeOperacao> {
  return pedir<ReciboDeOperacao>(`/jobs/${encodeURIComponent(jobId)}/liberar`, { method: 'POST' });
}

/** O único passo que fala com o control plane. Uma chamada por job. */
export function despachar(jobId: string): Promise<ReciboDeOperacao> {
  return pedir<ReciboDeOperacao>(`/jobs/${encodeURIComponent(jobId)}/despachar`, { method: 'POST' });
}

/**
 * Pergunta ao control plane o que aconteceu e fecha (ou não) o estado.
 *
 * ⚠️ A consulta é por JANELA DE DATA: a API oficial do Postiz não tem
 * `GET /posts/{id}` (medido em 02/09/2026). Não encontrar não reprova e não
 * apaga — o job continua onde está e a observação registra que não achamos.
 */
export function reconciliar(jobId: string): Promise<ReciboDeOperacao> {
  return pedir<ReciboDeOperacao>(`/jobs/${encodeURIComponent(jobId)}/reconciliar`, { method: 'POST' });
}

/**
 * Cancela um job. Exige motivo — e o motivo vira transição, não comentário.
 *
 * ⚠️ Um job `em_voo` NÃO é cancelável: o pedido pode já ter chegado ao destino,
 * e marcar cancelado esconderia um post que existe. O backend recusa, e a tela
 * nem oferece o botão nesse estado.
 */
export function cancelar(jobId: string, motivo: string): Promise<ReciboDeOperacao> {
  return pedir<ReciboDeOperacao>(`/jobs/${encodeURIComponent(jobId)}/cancelar`, {
    method: 'POST',
    body: JSON.stringify({ motivo }),
  });
}
