/**
 * O cliente HTTP do Estúdio Criativo.
 *
 * ## Mesma porta, mesma credencial, vocabulário próprio
 *
 * O backend é o mesmo FastAPI do Pautador Pro (`VITE_PAUTADOR_API_URL`) e a
 * credencial é a mesma sessão do Supabase. O que muda é o vocabulário: o
 * Estúdio devolve `{ detail: { codigo, mensagem } }` com a `mensagem` JÁ
 * sanitizada no servidor, então aqui não existe o tradutor de status que
 * `pautadorApi` precisa manter. A regra é curta: mostrar `mensagem`, guardar
 * `codigo` para quem for investigar, e NUNCA deixar status, stack, nome de
 * tabela ou caminho de arquivo chegarem à tela.
 *
 * ## Por que o fluxo de eventos não usa `EventSource`
 *
 * Porque `EventSource` não manda cabeçalho. A rota de eventos exige
 * `Authorization: Bearer …` como todas as outras, e a alternativa seria pôr o
 * token na query string, onde ele entra em log de proxy e em histórico de
 * navegação. Então o fluxo é `fetch` com corpo em streaming e um
 * `AbortController` para o desmonte: mesma semântica de SSE, mesma credencial
 * das demais chamadas, e o token continua só no cabeçalho.
 *
 * ⚠️ Nenhum caminho de storage é montado aqui. `previewUrl`, `posterUrl` e
 * `videoUrl` chegam prontos e assinados. Se algum dia esta camada precisar
 * concatenar bucket com chave, o defeito está no backend, não aqui.
 */
import { supabase } from '@/lib/supabase';
import { lerQuadro, repartirQuadros } from '@/components/criativos/stream/sse';
import type {
  MotorDaBancada,
  Parque,
  TrabalhoDaBancada,
} from '@/types/parqueCriativo';
import type {
  Aprovacao,
  AssetMaster,
  BrandPack,
  CreativeJob,
  EstadoDoJob,
  EventoDoJob,
  FormatoDisponivel,
  KindDeMaster,
  PedidoDeAprovacao,
  PedidoDeJobDeImagem,
  VideoObservado,
} from '@/types/criativos';

const RAW_BASE = (import.meta.env.VITE_PAUTADOR_API_URL || '').trim();
const API_BASE = RAW_BASE.replace(/\/$/, '');
const PREFIXO = '/api/criativos';

/**
 * A falha como a tela pode falar dela.
 *
 * `codigo` existe para o log, não para a frase: quem opera lê `mensagem`, quem
 * investiga cola o `codigo`. Nunca há um terceiro campo com o corpo cru.
 */
export class ErroDoEstudio extends Error {
  readonly codigo: string;
  constructor(mensagem: string, codigo: string) {
    super(mensagem);
    this.name = 'ErroDoEstudio';
    this.codigo = codigo;
  }
}

/** Frases do cliente. Fechadas, porque erro imprevisto também precisa de frase. */
const FRASE = {
  semBase: 'O endereço do Estúdio não está configurado neste ambiente.',
  semSessao: 'Sua sessão expirou. Entre novamente para continuar.',
  semRede: 'Não foi possível falar com o Estúdio agora.',
  semForma: 'O Estúdio respondeu em um formato que esta tela não reconhece.',
  generica: 'O Estúdio não conseguiu concluir esta operação.',
} as const;

export function estudioConfigurado(): boolean {
  return Boolean(API_BASE);
}

async function autorizacao(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ErroDoEstudio(FRASE.semSessao, 'sessao_ausente');
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
 * `detail` que é string. Nenhum desses ramos pode devolver o texto cru: um
 * proxy que responde com a própria página de erro entregaria à tela nome de
 * servidor e versão de software.
 */
async function falhaDaResposta(resp: Response): Promise<ErroDoEstudio> {
  if (resp.status === 401) return new ErroDoEstudio(FRASE.semSessao, 'sessao_expirada');
  try {
    const corpo: unknown = await resp.json();
    const detail = (corpo as { detail?: unknown })?.detail;
    if (detail && typeof detail === 'object') {
      const d = detail as { codigo?: unknown; mensagem?: unknown };
      const mensagem = typeof d.mensagem === 'string' && d.mensagem.trim() ? d.mensagem : FRASE.generica;
      const codigo = typeof d.codigo === 'string' && d.codigo.trim() ? d.codigo : 'sem_codigo';
      return new ErroDoEstudio(mensagem, codigo);
    }
  } catch {
    /* corpo ausente ou não é JSON: cai na frase fechada */
  }
  return new ErroDoEstudio(FRASE.generica, 'resposta_sem_detalhe');
}

interface RespostaCrua<T> {
  dados: T;
  status: number;
  cabecalho: Headers;
}

async function chamar<T>(url: string, init?: RequestInit): Promise<RespostaCrua<T>> {
  if (!API_BASE) throw new ErroDoEstudio(FRASE.semBase, 'base_ausente');
  let resp: Response;
  try {
    resp = await fetch(url, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(await autorizacao()),
        ...(init?.headers ?? {}),
      },
    });
  } catch (err) {
    if (err instanceof ErroDoEstudio) throw err;
    throw new ErroDoEstudio(FRASE.semRede, 'sem_resposta');
  }
  if (!resp.ok) throw await falhaDaResposta(resp);
  if (resp.status === 204) {
    return { dados: undefined as T, status: resp.status, cabecalho: resp.headers };
  }
  try {
    return { dados: (await resp.json()) as T, status: resp.status, cabecalho: resp.headers };
  } catch {
    throw new ErroDoEstudio(FRASE.semForma, 'resposta_ilegivel');
  }
}

/**
 * As URLs de arquivo sao resolvidas contra a API, nunca contra a pagina.
 *
 * ⚠️ Conserto de um defeito achado no navegador, e ele quebraria em producao do
 * mesmo jeito. O backend devolve `previewUrl` como caminho relativo
 * (`/api/criativos/arquivo/<token>`), e uma tag `<img src="/api/...">` resolve
 * isso contra a ORIGEM DA PAGINA. Como o FastAPI mora noutra origem
 * (`VITE_PAUTADOR_API_URL`), o pedido ia parar no servidor Express, que nao tem
 * essa rota: toda miniatura, poster e video davam 404 enquanto o JSON dizia que
 * o arquivo existia.
 *
 * Normalizar aqui, na fronteira, e o unico ponto onde isso cabe uma vez so.
 * Fazer no componente exigiria lembrar em cada `src`, `href` e `poster`, e o
 * primeiro esquecimento voltaria a mostrar imagem quebrada sem erro nenhum.
 */
const CAMPOS_DE_ARQUIVO = new Set(['previewUrl', 'posterUrl', 'videoUrl']);

function absolutizarArquivos<T>(valor: T): T {
  if (!API_BASE || valor === null || typeof valor !== 'object') return valor;
  if (Array.isArray(valor)) return valor.map((v) => absolutizarArquivos(v)) as unknown as T;

  const saida: Record<string, unknown> = {};
  for (const [chave, v] of Object.entries(valor as Record<string, unknown>)) {
    if (CAMPOS_DE_ARQUIVO.has(chave) && typeof v === 'string' && v.startsWith('/')) {
      saida[chave] = `${API_BASE}${v}`;
    } else {
      saida[chave] = absolutizarArquivos(v);
    }
  }
  return saida as T;
}

async function ler<T>(url: string, init?: RequestInit): Promise<T> {
  return absolutizarArquivos((await chamar<T>(url, init)).dados);
}

// ─────────────────────────────────────────────────────────────────────────────
// Formas de resposta declaradas pelo backend
// ─────────────────────────────────────────────────────────────────────────────

export interface ResumoDoEstudio {
  emAndamento: CreativeJob[];
  aguardandoRevisao: AssetMaster[];
  falhas: CreativeJob[];
  aprovadosRecentes: AssetMaster[];
  contagemPorEstado: Record<EstadoDoJob, number>;
  totalAssets: number;
  brandPacks: number;
  /**
   * O servidor tem credencial de provedor? `false` significa que pedir peça
   * vai falhar, e a tela precisa dizer isso ANTES do formulário, não depois.
   */
  motorConfigurado: boolean;
  /** Há leitura de vídeo observado neste ambiente. */
  videoDisponivel: boolean;
}

export interface CatalogoDeFormatos {
  formatos: FormatoDisponivel[];
  motorConfigurado: boolean;
}

/**
 * Os builds de vídeo que existem para LER.
 *
 * `disponivel: false` é indisponibilidade declarada, não erro: a fábrica
 * externa pode simplesmente não ter build publicado neste ambiente, e mostrar
 * uma tela de erro para isso manda alguém procurar defeito onde não há.
 */
export interface CatalogoDeVideos {
  builds: string[];
  disponivel: boolean;
}

export interface PaginaDeAssets {
  assets: AssetMaster[];
  /** Quantos casam com o filtro. */
  total: number;
  /** Quantos existem no total, filtro nenhum. */
  universo: number;
}

export interface DetalheDoAsset {
  asset: AssetMaster;
  versoes: AssetMaster[];
  aprovacoes: Aprovacao[];
  job: CreativeJob;
}

export interface ConsultaDeAssets {
  busca?: string;
  kind?: KindDeMaster | '';
  estado?: string;
  brandPack?: string;
  destino?: string;
  desde?: string;
  ate?: string;
  limite?: number;
  offset?: number;
}

/**
 * O resultado de pedir um job. `replay` é o 200 com
 * `X-Criativo-Idempotente: replay`: o mesmo formulário reenviado não gerou
 * chamada nova ao motor, e a tela precisa dizer isso em vez de fingir que
 * acabou de criar algo.
 */
export interface JobCriado {
  job: CreativeJob;
  replay: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Operações
// ─────────────────────────────────────────────────────────────────────────────

export const criativosApi = {
  get configurado() {
    return estudioConfigurado();
  },

  resumo(): Promise<ResumoDoEstudio> {
    return ler<ResumoDoEstudio>(endereco('/resumo'));
  },

  /**
   * O parque: motores, modos, formatos, skins, vozes, gates e exigências de canal,
   * lidos das tabelas `criativo_*` que a v11_02 pôs em produção.
   *
   * ⚠️ NÃO substitui `formatos()`. Aquela rota serve os quatro slots que o motor
   * sabe executar; esta serve os sete que o banco declara. A diferença sai em
   * `divergencias`, com dimensão dos dois lados — não em silêncio.
   */
  parque(): Promise<Parque> {
    return ler<Parque>(endereco('/parque'));
  },

  /** Quais motores ESTA máquina roda agora. Diferente do que existe no parque. */
  motoresDaBancada(): Promise<{ motores: MotorDaBancada[] }> {
    return ler<{ motores: MotorDaBancada[] }>(endereco('/bancada/motores'));
  },

  /**
   * Produz uma peça localmente. Não publica, não entrega, não sai da máquina.
   *
   * ⚠️ `seed` é obrigatório no tipo. Um render sem semente não pode ser repetido,
   * e a promessa central do recibo é reprodutibilidade.
   */
  produzirNaBancada(pedido: {
    receitaId: string;
    motorSlug: string;
    modoSlug: string;
    finalidadeSlug: string;
    seed: number;
    slots: string[];
    titulo: string;
    apoio?: string | null;
  }): Promise<TrabalhoDaBancada> {
    return ler<TrabalhoDaBancada>(endereco('/bancada/trabalhos'), {
      method: 'POST',
      body: JSON.stringify(pedido),
    });
  },

  /**
   * Baixa o artefato COM credencial e devolve os bytes.
   *
   * ⚠️ Existe porque `<img src="/api/...">` estava errado por dois motivos que
   * este arquivo já documenta no topo: a tag resolve o caminho contra a ORIGEM DA
   * PÁGINA (e o FastAPI mora noutra), e `<img>` não manda `Authorization`. A rota
   * irmã `/arquivo/{token}` resolveu isso com link assinado; esta resolve
   * buscando os bytes pelo mesmo cliente autenticado das outras chamadas.
   */
  async bytesDaBancada(id: string, slot: string): Promise<Blob> {
    const resp = await fetch(
      endereco(`/bancada/arquivo/${encodeURIComponent(id)}/${encodeURIComponent(slot)}`),
      { headers: await autorizacao() },
    );
    if (!resp.ok) throw await falhaDaResposta(resp);
    return resp.blob();
  },

  trabalhoDaBancada(id: string): Promise<TrabalhoDaBancada> {
    return ler<TrabalhoDaBancada>(endereco(`/bancada/trabalhos/${encodeURIComponent(id)}`));
  },

  trabalhosDaBancada(limite = 30): Promise<{ trabalhos: TrabalhoDaBancada[] }> {
    return ler<{ trabalhos: TrabalhoDaBancada[] }>(
      endereco(`/bancada/trabalhos?limite=${limite}`),
    );
  },

  linhagemDaBancada(id: string): Promise<{ linhagem: TrabalhoDaBancada[] }> {
    return ler<{ linhagem: TrabalhoDaBancada[] }>(
      endereco(`/bancada/trabalhos/${encodeURIComponent(id)}/linhagem`),
    );
  },

  /** Cancela. O estado só muda quando o servidor confirma. */
  cancelarNaBancada(id: string, motivo: string): Promise<TrabalhoDaBancada> {
    return ler<TrabalhoDaBancada>(
      endereco(`/bancada/trabalhos/${encodeURIComponent(id)}/cancelar`),
      { method: 'POST', body: JSON.stringify({ motivo }) },
    );
  },

  /**
   * Retoma um trabalho terminal. Devolve o trabalho NOVO, não o antigo.
   *
   * ⚠️ Não reabre o que falhou: um `failed` guarda o motivo, e reabrir apagaria
   * essa história. Dois cliques convergem para a mesma retomada.
   */
  retomarNaBancada(id: string): Promise<TrabalhoDaBancada> {
    return ler<TrabalhoDaBancada>(
      endereco(`/bancada/trabalhos/${encodeURIComponent(id)}/retomar`),
      { method: 'POST' },
    );
  },

  async criarJobDeImagem(pedido: PedidoDeJobDeImagem): Promise<JobCriado> {
    const resposta = await chamar<CreativeJob>(endereco('/jobs'), {
      method: 'POST',
      body: JSON.stringify(pedido),
    });
    const marca = resposta.cabecalho.get('X-Criativo-Idempotente');
    return {
      // `chamar` cru nao passa por `ler`, entao a normalizacao de URL de
      // arquivo precisa ser explicita aqui. Sem ela, as miniaturas do job
      // recem-criado dariam 404 enquanto as da biblioteca funcionariam — o
      // tipo de inconsistencia que ninguem relaciona com a causa.
      job: absolutizarArquivos(resposta.dados),
      replay: resposta.status === 200 || marca === 'replay',
    };
  },

  jobs(filtro?: { estado?: EstadoDoJob; limite?: number }): Promise<{ jobs: CreativeJob[] }> {
    return ler(endereco('/jobs', { estado: filtro?.estado, limite: filtro?.limite }));
  },

  job(id: string): Promise<CreativeJob> {
    return ler<CreativeJob>(endereco(`/jobs/${encodeURIComponent(id)}`));
  },

  retentarJob(id: string): Promise<CreativeJob> {
    return ler<CreativeJob>(endereco(`/jobs/${encodeURIComponent(id)}/retry`), { method: 'POST' });
  },

  cancelarJob(id: string): Promise<CreativeJob> {
    return ler<CreativeJob>(endereco(`/jobs/${encodeURIComponent(id)}/cancel`), { method: 'POST' });
  },

  assets(consulta: ConsultaDeAssets = {}): Promise<PaginaDeAssets> {
    return ler<PaginaDeAssets>(
      endereco('/assets', {
        busca: consulta.busca,
        kind: consulta.kind,
        estado: consulta.estado,
        brandPack: consulta.brandPack,
        destino: consulta.destino,
        desde: consulta.desde,
        ate: consulta.ate,
        limite: consulta.limite,
        offset: consulta.offset,
      }),
    );
  },

  asset(id: string): Promise<DetalheDoAsset> {
    return ler<DetalheDoAsset>(endereco(`/assets/${encodeURIComponent(id)}`));
  },

  decidir(assetId: string, pedido: PedidoDeAprovacao): Promise<Aprovacao> {
    return ler<Aprovacao>(endereco(`/assets/${encodeURIComponent(assetId)}/aprovacoes`), {
      method: 'POST',
      body: JSON.stringify(pedido),
    });
  },

  brandPacks(): Promise<{ brandPacks: BrandPack[] }> {
    return ler(endereco('/brand-packs'));
  },

  formatos(): Promise<CatalogoDeFormatos> {
    return ler<CatalogoDeFormatos>(endereco('/formatos'));
  },

  videos(): Promise<CatalogoDeVideos> {
    return ler<CatalogoDeVideos>(endereco('/videos'));
  },

  /**
   * ⚠️ A chave é o SLUG do build (`short_odete`), não o id do job. O job
   * observado carrega esse slug em `origemExterna.identificadorDoBuild`, que é
   * de onde a página do job o tira.
   */
  video(buildSlug: string): Promise<VideoObservado> {
    return ler<VideoObservado>(endereco(`/video/${encodeURIComponent(buildSlug)}`));
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Fluxo de eventos (SSE por `fetch`)
// ─────────────────────────────────────────────────────────────────────────────

export interface EscutaDoFluxo {
  aoEvento(evento: EventoDoJob): void;
  aoJob(job: CreativeJob): void;
  aoFim(estado: EstadoDoJob): void;
}

/**
 * Abre o fluxo de eventos de um job a partir de `desde`.
 *
 * Resolve quando o servidor fecha o fluxo (fim natural ou queda). Quem chama
 * decide se reabre, e com qual cursor: a política de reconexão mora no hook,
 * não aqui, porque só o hook sabe qual foi a última `seq` ENTREGUE à tela.
 */
export async function abrirFluxoDeEventos(
  jobId: string,
  desde: number,
  escuta: EscutaDoFluxo,
  sinal: AbortSignal,
): Promise<void> {
  if (!API_BASE) throw new ErroDoEstudio(FRASE.semBase, 'base_ausente');
  const url = endereco(`/jobs/${encodeURIComponent(jobId)}/eventos`, { desde });
  let resp: Response;
  try {
    resp = await fetch(url, {
      method: 'GET',
      signal: sinal,
      headers: { Accept: 'text/event-stream', ...(await autorizacao()) },
    });
  } catch (err) {
    if (sinal.aborted) return;
    if (err instanceof ErroDoEstudio) throw err;
    throw new ErroDoEstudio(FRASE.semRede, 'sem_resposta');
  }
  if (!resp.ok) throw await falhaDaResposta(resp);
  if (!resp.body) throw new ErroDoEstudio(FRASE.semForma, 'fluxo_sem_corpo');

  const leitor = resp.body.getReader();
  const decodificador = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      buffer += decodificador.decode(value, { stream: true });
      const { quadros, resto } = repartirQuadros(buffer);
      buffer = resto;
      for (const bruto of quadros) {
        const quadro = lerQuadro(bruto);
        if (!quadro) continue;
        let carga: unknown;
        try {
          carga = JSON.parse(quadro.dados);
        } catch {
          continue; // quadro ilegível não derruba o fluxo inteiro
        }
        if (quadro.evento === 'evento') escuta.aoEvento(carga as EventoDoJob);
        // O quadro `job` do stream carrega as renditions com `previewUrl`, e
        // ele nao passa por `ler`. Normalizar aqui tambem.
        else if (quadro.evento === 'job') escuta.aoJob(absolutizarArquivos(carga as CreativeJob));
        else if (quadro.evento === 'fim') {
          escuta.aoFim((carga as { estado: EstadoDoJob }).estado);
        }
      }
    }
  } catch (err) {
    if (sinal.aborted) return;
    throw new ErroDoEstudio(FRASE.semRede, 'fluxo_interrompido');
  } finally {
    try {
      leitor.releaseLock();
    } catch {
      /* já liberado pelo abort */
    }
  }
}

export function mensagemDaFalha(err: unknown): string {
  if (err instanceof ErroDoEstudio) return err.message;
  return FRASE.generica;
}

export function codigoDaFalha(err: unknown): string | null {
  return err instanceof ErroDoEstudio ? err.codigo : null;
}

/**
 * Os códigos do Estúdio que mudam o COMPORTAMENTO da tela, não só a frase.
 *
 * O resto dos códigos vira texto e ponto. Estes cinco decidem se um botão
 * existe, se um formulário pode ser enviado ou se a tela deve reler em vez de
 * acusar defeito.
 */
export const CODIGO = {
  motorSemCredencial: 'ESTUDIO.motor_sem_credencial',
  modoIndisponivel: 'ESTUDIO.modo_indisponivel',
  ativoNaoAprovavel: 'ESTUDIO.ativo_nao_aprovavel',
  decisaoDuplicada: 'ESTUDIO.decisao_duplicada',
  linkInvalido: 'ESTUDIO.link_invalido',
} as const;

export function ehCodigo(err: unknown, codigo: string): boolean {
  return err instanceof ErroDoEstudio && err.codigo === codigo;
}
