/**
 * v6 RBAC — _pagination
 *
 * Helper para escapar do cap silencioso de 1000 linhas que o
 * PostgREST/Supabase impõe via `db-max-rows` em SELECTs (mesmo
 * quando o client passa `.limit(100000)` — o servidor ignora além
 * do cap configurado).
 *
 * Estratégia: paginação manual via `.range(from, to)` em loop até
 * que uma página devolva menos linhas que `PAGE_SIZE` (sinal de
 * fim de dados).
 *
 * Importante:
 *   - O `fetchPage` callback DEVE incluir uma cláusula de ordenação
 *     ESTÁVEL (composta — pelo menos com `id` como tiebreaker), caso
 *     contrário páginas podem repetir/perder linhas quando há rows
 *     com chaves de ordenação iguais.
 *   - `HARD_CAP_PAGES` é um cinto de segurança contra loops
 *     infinitos. Para 500 páginas × 1000 = até 500k linhas. Se isso
 *     for atingido, há provavelmente algo errado.
 */

const PAGE_SIZE = 1000;
const HARD_CAP_PAGES = 500;

export interface PageResult<T> {
  data: T[] | null;
  error: { message?: string } | null;
}

/**
 * Executa um fetch paginado contra o Supabase, juntando todas as
 * páginas em um único array.
 *
 * @param fetchPage callback que recebe `from`/`to` (inclusivos) e
 *                  retorna o resultado bruto do supabase-js (com
 *                  `.range(from, to)` aplicado dentro).
 */
export async function fetchAllPaginated<T>(
  fetchPage: (from: number, to: number) => Promise<PageResult<T>>
): Promise<T[]> {
  const all: T[] = [];

  for (let page = 0; page < HARD_CAP_PAGES; page++) {
    const from = page * PAGE_SIZE;
    const to = from + PAGE_SIZE - 1;

    const { data, error } = await fetchPage(from, to);
    if (error) throw error;
    if (!data || data.length === 0) break;

    all.push(...data);

    // Última página: o servidor devolveu menos do que pedimos.
    if (data.length < PAGE_SIZE) break;
  }

  return all;
}
