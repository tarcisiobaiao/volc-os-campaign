/**
 * Publicação — o perfil de WordPress de cada projeto.
 *
 * A regra que atravessa este arquivo: **não existe tipo para a senha vinda do
 * servidor.** `PerfilPublicacao` (o que chega) não tem campo de token; só
 * `PerfilEntrada` (o que vai) tem, e opcional. Não é descuido de tipagem — é a
 * regra do backend expressa no tipo, para que um `perfil.wp_app_password`
 * escrito por engano não compile.
 *
 * E repare no que também não existe: CNPJ, autor e lista de cross-funnel. O
 * CNPJ e a assinatura saem do TEMA do site; a saída cross-funnel o engine
 * resolve lendo o sitemap real. Cadastrar de novo aqui seria manter à mão um
 * dado que o site já publica sozinho.
 */

export interface ConexaoTestada {
  ok?: boolean | null;
  em?: string | null;
  detalhe?: string | null;
}

/** O que o backend DEVOLVE. Repare: nenhuma senha. */
export interface PerfilPublicacao {
  project_id: number;
  /** Tem Application Password cadastrado? */
  configurado: boolean;
  /** O backend tem VOLC_SEGREDO_KEY? Sem isso não dá para cifrar nada. */
  cofre_pronto: boolean;
  wp_url?: string | null;
  wp_username?: string | null;
  /** Só para reconhecer QUAL credencial está lá. Nunca reconstruível. */
  senha_mascarada: string;
  post_type: string;
  lp_post_type: string;
  conexao: ConexaoTestada;
}

/** O que a tela ENVIA. Senha ausente = mantém a atual (não apaga). */
export interface PerfilEntrada {
  wp_url: string;
  wp_username: string;
  wp_app_password?: string;
  post_type: string;
  lp_post_type: string;
}

export interface ResultadoTesteConexao {
  ok: boolean;
  detalhe: string;
  usuario?: string | null;
  pode_publicar?: boolean | null;
  post_types_ok?: Record<string, boolean> | null;
}

/** Um site candidato a receber o funil, com o motivo de estar apto ou não. */
export interface ProjetoDestino {
  project_id: number;
  nome: string;
  dominio?: string | null;
  apto: boolean;
  motivo: string;
}

export const PERFIL_VAZIO: PerfilEntrada = {
  wp_url: '',
  wp_username: '',
  post_type: 'rec',
  lp_post_type: 'r',
};

/** O perfil que chegou, no formato do formulário — sem a senha, que nunca vem. */
export function paraFormulario(p: PerfilPublicacao): PerfilEntrada {
  return {
    wp_url: p.wp_url || '',
    wp_username: p.wp_username || '',
    post_type: p.post_type || 'rec',
    lp_post_type: p.lp_post_type || 'r',
  };
}

/** Uma execução do redator: qual card, para qual site, o que saiu. */
export interface RunDoRedator {
  id: number;
  opportunity_id: number;
  project_id: number;
  run_id?: string | null;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  /**
   * Hoje todo disparo grava `publicado` (sobe como rascunho do WordPress). O
   * valor `rascunho` — o antigo "só gerar", que não tocava no site — não é mais
   * emitido, mas continua no tipo porque a coluna aceita e um run é registro
   * histórico do que ELE fez, não do que hoje se pode pedir.
   */
  modo: 'rascunho' | 'publicado';
  custo_usd?: number | null;
  paginas_planejadas?: number | null;
  paginas_geradas?: number | null;
  erro?: string | null;
  criado_em?: string | null;
}

export interface DisparoDoRedator {
  run: RunDoRedator;
  /** Hoje `false`: a fila existe, o motor ainda não consome dela. */
  motor_conectado: boolean;
  aviso?: string | null;
}

export const ROTULO_STATUS_RUN: Record<RunDoRedator['status'], string> = {
  queued: 'na fila',
  running: 'escrevendo',
  done: 'concluído',
  failed: 'falhou',
  cancelled: 'cancelado',
};

// ── a releitura do WordPress ────────────────────────────────────────────────
//
// `status_wp` e `lp_url` são gravados UMA VEZ, pelo worker, no instante da
// escrita — e o motor sobe tudo como rascunho de propósito
// (`engine/config.yaml: publish_status: draft`). Sem reler, o operador publica
// a LP no WP e o run continua dizendo `draft` com `?post_type=r&p=2152`: o Hub
// de Tráfego barra LP em rascunho, corretamente e para sempre.

export interface PaginaRelida {
  post_id: number;
  post_type: string;
  role: string;
  status_antes: string;
  status_agora: string;
  url_antes: string;
  /** O permalink de verdade. Rascunho devolve `?post_type=x&p=123`; publicado,
   *  o endereço final — e é essa troca que destrava o Tráfego. */
  url_agora: string;
  mudou: boolean;
  /** Página apagada no WP volta 404 e é RELATADA, nunca removida da linha:
   *  `paginas_publicadas` é o único registro de qual rascunho veio de qual run. */
  erro?: string | null;
}

export interface ReleituraDoWordPress {
  run_row_id: number;
  paginas: PaginaRelida[];
  mudaram: number;
  lp_url_antes?: string | null;
  lp_url_agora?: string | null;
  no_ar: number;
  resumo: string;
}

/** A foto da página publicada — inteira, com a rolagem já acionada.
 *
 *  Os portões provam FATO e FORMA; nenhum deles vê o tema montar a página. Um
 *  bloco que o tema não conhece ou uma imagem que não carregou não reprovam em
 *  validador nenhum, e são a primeira coisa que o leitor pago enxerga. */
export interface ProvaVisual {
  page_number: number;
  /** Nome do arquivo no run. Servido pela rota de artefatos, que tem lista
   *  branca `^p\d+...\.png$` — o nome foi escolhido para caber nela. */
  arquivo: string;
  url: string;
  status_http: number | null;
  /** ⚠️ Título ou corpo de 404. A foto sozinha não distingue "página feia" de
   *  "erro com tema bonito". */
  parece_erro: boolean;
  bytes: number;
  resumo: string;
}

/** O desfecho de enviar UMA página ao WordPress.
 *
 *  ⚠️ `ok: false` com `erro` NÃO é o mesmo que uma exceção HTTP. As recusas
 *  previsíveis (já publicada, run rodando, portão barrou, credencial ausente)
 *  voltam como 409 e viram exceção; este `ok: false` é o caso em que o motor
 *  RODOU e a página não apareceu publicada — que é justamente o desfecho que
 *  passava despercebido, porque o motor sai com código 0 e não imprime nada. */
export interface PublicacaoDePagina {
  ok: boolean;
  publicada?: {
    post_id: number; slug: string; url_wp: string; status_wp: string;
    page_number?: number; role?: string;
  } | null;
  erro?: string | null;
  aviso?: string | null;
}
