// ============================================
// REDATOR — a matriz páginas × etapas
//
// Projeção do `step_status` do motor. O backend (`app/redator/matriz.py`) já
// resolveu as duas coisas que o front não teria como resolver sozinho:
//
// 1. o parse das chaves (`write_p3`, e a exceção `page_5`, que quebra a
//    convenção por não ter o `p` do meio);
// 2. a máscara `aplicaveis` por página — porque a AUSÊNCIA de uma chave é
//    ambígua por construção: significa ao mesmo tempo "não se aplica", "a flag
//    está desligada", "ainda não chegou" e "a página morreu antes".
//
// O front não recalcula nada disso. Ele desenha.
// ============================================

/** Uma das 11 etapas do laço do pipeline, na ordem em que rodam. */
export interface ColunaDaMatriz {
  chave: string;
  rotulo: string;
  /** `false` = a etapa é local e nunca custa. A célula NUNCA escreve "US$ 0,00":
   *  sugeriria medição onde não há. */
  paga: boolean;
}

export interface CelulaDaMatriz {
  status: 'OK' | 'RETRIED' | 'FALLBACK' | 'FAILED' | 'SKIPPED' | string;
  tentativas: number | null;
  modelo: string;
  custo_usd: number;
  latencia_ms: number;
  issues: { code: string; message: string }[];
}

export interface PaginaDaMatriz {
  page_number: number;
  /** O PAPEL, nunca o `page_type` — este diz "HUB" onde o papel é PRESELL. */
  papel: 'LP' | 'PRESELL' | 'SOLUTION' | string;
  slug: string;
  h1: string;
  engajamento: string;
  /** Quais das 11 colunas fazem sentido nesta página. Calculada no servidor. */
  aplicaveis: string[];
  /** `screenshot OK` não significa que existe print — o motor grava o OK fora
   *  do `if shots`. Esta é a contagem real. */
  prints: number;
  publicada: PaginaPublicada | null;
  bloqueada: boolean;
  /** A coluna em que a página morreu. À DIREITA dela, o que falta é
   *  "cancelado", não "pendente" — nunca vai chegar. */
  bloqueada_em: string | null;
}

/** O que o WordPress devolveu, VERBATIM. É o elo com a campanha: a receita do
 *  AdSense é atribuída ao clique comprado por igualdade de string com
 *  `campaign_funnel_urls`. Remontar a URL a partir do slug quebraria a
 *  atribuição em silêncio quando o WP acrescenta `-2`. */
export interface PaginaPublicada {
  page_number: number;
  role: string;
  post_type: string;
  post_id: number;
  slug: string;
  /** ⚠️ De um RASCUNHO o WP devolve `?post_type=r&p=2146`, não o permalink. */
  url_wp: string;
  status_wp: string;
  publicado_em?: string;
}

export interface MatrizDoRun {
  /** O nome que o operador reconhece — `canonical_name` da entidade.
   *  A manchete escrevia `card #74`: o número da linha do banco como nome
   *  de um funil de seis páginas. O recuo para `card #N` continua, mas
   *  agora é o último caso, não o primeiro. */
  titulo?: string;
  run: {
    id: number;
    opportunity_id: number;
    project_id: number;
    run_id: string | null;
    // ⚠️ Sem `| string` no fim: em TypeScript, `'a' | 'b' | string` colapsa em
    // `string` e a união deixa de checar coisa nenhuma — o oposto do que a
    // escrita sugere. A mesma união estrita de `RunDoRedator`.
    status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
    modo: 'rascunho' | 'publicado';
    custo_usd: number | null;
    paginas_planejadas: number | null;
    paginas_geradas: number | null;
    erro: string | null;
    criado_em: string | null;
  };
  colunas: ColunaDaMatriz[];
  paginas: PaginaDaMatriz[];
  /** Indexadas por `<etapa>_p<N>`. */
  celulas: Record<string, CelulaDaMatriz>;
  /** Passos do RUN, não de uma página (`extract`, `funnel_graph`, `blocked_pN`…). */
  faixa: Record<string, CelulaDaMatriz>;
  custo_total: number;
  /** A escala da grade: a altura de cada célula é proporcional a este teto. */
  custo_maior_celula: number;
  /** O total pode estar ABAIXO da fatura — ver `matriz.py`. A tela avisa e NÃO
   *  compensa sozinha. */
  subestimado: boolean;
  publicadas: PaginaPublicada[];
  lp_url: string | null;
  teto_usd: number | null;
  teto_pagina_usd: number | null;
  artefatos: { pasta?: string; arquivos?: string[]; pid?: number; carimbo?: string };
}

/** `304` = nada mudou desde o último ETag. O polling é de 3s por ~45 min: ~900
 *  consultas, das quais ~93% não trazem nada. */
export interface RespostaDaMatriz {
  matriz: MatrizDoRun | null;
  etag: string | null;
  mudou: boolean;
}
