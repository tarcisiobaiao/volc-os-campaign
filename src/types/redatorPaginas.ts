// ============================================
// O FUNIL ESCRITO — o que o motor produziu
//
// Separado de `redator.ts` (a matriz) de propósito: aquilo é telemetria, muda a
// cada 3s e some de interesse quando o run acaba. Isto é conteúdo — pesa mais,
// muda pouco e continua valendo depois.
// ============================================

export interface SeoDaPagina {
  titulo: string;
  descricao: string;
  foco: string;
  slug: string;
}

export interface TextoDaPagina {
  /** `gutenberg` para prosa; `lp_json` para a LP, que é um JSON de slots que o
   *  tema monta — hero, seções, FAQ, CTAs. A tela escolhe como renderizar por
   *  este campo, nunca adivinhando pelo conteúdo. */
  formato: string;
  conteudo: string;
  palavras: number;
}

/** Uma aresta do grafo do funil.
 *
 * `placement` não é metadado: um link no `hero` é lido por quase todo mundo e
 * um no `footer` por quase ninguém — é o peso real daquele caminho.
 *
 * `kind` diz se o leitor continua no funil (`funnel`), sai para cumprir a
 * promessa da página (`external_official`) ou é reciclado para outro funil do
 * mesmo domínio (`cross_funnel`). Cada salto interno é mais um pageview na
 * mesma sessão comprada — é assim que a arbitragem fecha. */
export interface RotaDaPagina {
  placement: 'hero' | 'inline' | 'footer' | string;
  kind: 'funnel' | 'external_official' | 'cross_funnel' | string;
  /** Slug (quando `funnel`) ou URL absoluta (quando é saída). */
  target: string;
  anchor: string;
}

export interface PrintOficial {
  url: string;
  arquivo: string;
}

export interface SlotDeAnuncio {
  slot_id: string;
  page_role: string;
  placement: string;
  sizes: string[];
  min_height_px: number;
  refresh_eligible: boolean;
}

export interface PaginaEscrita {
  page_number: number;
  papel: 'LP' | 'PRESELL' | 'SOLUTION' | string;
  slug: string;
  h1: string;
  engajamento: string;
  /** Por que esta página existe no funil, e para onde ela empurra. É a única
   *  informação que explica a ORDEM — sem ela, 5 páginas parecem 5 artigos. */
  objetivo: string;
  gancho: string;
  proxima: string;
  estrutura: string[];
  palavras_alvo: string[];
  /** ⚠️ É uma LISTA de arestas, não um objeto. O motor grava
   *  `[{placement, kind, target, anchor}]` — e é daqui que sai o grafo do
   *  funil, porque uma página aponta para várias ao mesmo tempo. */
  rotas: RotaDaPagina[];
  seo: SeoDaPagina;
  links_oficiais: string[];
  prints: PrintOficial[];
  texto: TextoDaPagina;
  publicada: {
    post_id: number; slug: string; url_wp: string; status_wp: string;
  } | null;
  bloqueada: boolean;
  custo_usd: number;
  issues: { etapa: string; code: string; message: string }[];
  /** Nome do arquivo, não caminho: a tela pede pela rota de artefato, que
   *  valida contra lista branca antes de servir. */
  imagem: string | null;
  meta: { robots?: string; canonical?: string } | null;
  anuncios: { slots?: SlotDeAnuncio[]; vignette?: Record<string, unknown> } | null;
  arquivos: string[];
}

export interface FunilEscrito {
  paginas: PaginaEscrita[];
  /** A pasta do run sumiu do disco (run antigo, ou backend noutra máquina).
   *  Dizer isso é melhor que devolver vazio e parecer um funil sem páginas. */
  sem_artefatos: boolean;
  motivo?: string;
  avatar?: string;
  tom?: string;
}
