/**
 * Leitura paginada da RPC `get_campaigns_aggregated`.
 *
 * Produção só tem a assinatura de 3 parâmetros (project, início, fim) — a
 * versão com `p_limit/p_offset` de `src/sql/fix_campaigns_aggregated_pagination.sql`
 * nunca foi aplicada, e chamá-la dava 404 e jogava o dashboard no fallback.
 * Aquele arquivo também está defasado (devolve menos colunas que a função viva,
 * sem `aggregated_commission`), então não deve ser aplicado.
 *
 * A paginação fica no PostgREST: `order` + `range` sobre o resultado da função.
 * Cada página fica abaixo do cap de 1000 linhas, e a ordem por `campaign_id`
 * (chave única do resultado) mantém as páginas estáveis. Quem consome reordena
 * por receita depois.
 */

type ErroRpc = { message: string; code?: string };
type RespostaRpc = { data: unknown[] | null; error: ErroRpc | null };

interface ConstrutorRpc {
  order(coluna: string, opcoes?: { ascending?: boolean }): ConstrutorRpc;
  range(de: number, ate: number): PromiseLike<RespostaRpc>;
}

export interface ClienteRpc {
  rpc(fn: string, params: Record<string, unknown>): ConstrutorRpc;
}

export type ParametrosCampanhasAgregadas = {
  p_project_id: number | null;
  p_start_date: string;
  p_end_date: string;
};

export async function lerCampanhasAgregadas<T = any>(
  cliente: ClienteRpc,
  params: ParametrosCampanhasAgregadas,
  { tamanhoPagina = 500, tetoPaginas = 200 }: { tamanhoPagina?: number; tetoPaginas?: number } = {},
): Promise<{ linhas: T[]; erro: ErroRpc | null }> {
  const linhas: T[] = [];
  for (let pagina = 0; pagina < tetoPaginas; pagina++) {
    const de = pagina * tamanhoPagina;
    const { data, error } = await cliente
      .rpc('get_campaigns_aggregated', params)
      .order('campaign_id', { ascending: true })
      .range(de, de + tamanhoPagina - 1);

    if (error) return { linhas: [], erro: error };
    if (!data || data.length === 0) return { linhas, erro: null };
    linhas.push(...(data as T[]));
    if (data.length < tamanhoPagina) return { linhas, erro: null };
  }
  // Todas as páginas vieram cheias: a lista estaria cortada sem aviso.
  return {
    linhas: [],
    erro: { code: 'teto_de_paginas', message: `get_campaigns_aggregated passou de ${tetoPaginas * tamanhoPagina} linhas` },
  };
}
