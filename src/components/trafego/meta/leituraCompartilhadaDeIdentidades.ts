/** One reader per authenticated owner/epoch. Never keep this factory in a module singleton.
 * Coalesces only concurrent reads; fulfillment and rejection both evict the entry.
 * No identities, tokens or catalogs are persisted, and no selection is inferred.
 */
export function criarLeitorDeIdentidadesCompartilhado<T>(ler: (accountRef: string) => Promise<T>) {
  const emVoo = new Map<string, Promise<T>>();
  let epoch = 0;
  const erroDeSessao = () => new Error('A sessão mudou durante a consulta. Consulte novamente os responsáveis.');
  const consultar = (accountRef: string): Promise<T> => {
    const existente = emVoo.get(accountRef);
    if (existente) return existente;
    const inicio = epoch;
    const pedido = Promise.resolve().then(() => {
      if (inicio !== epoch) throw erroDeSessao();
      return ler(accountRef);
    }).then(result => {
      if (inicio !== epoch) throw erroDeSessao();
      return result;
    });
    emVoo.set(accountRef, pedido);
    const limpar = () => { if (emVoo.get(accountRef) === pedido) emVoo.delete(accountRef); };
    // Both handlers resolve: avoid creating an unhandled rejected `finally` promise.
    void pedido.then(limpar, limpar);
    return pedido;
  };
  return Object.assign(consultar, { clear() { epoch++; emVoo.clear(); } });
}
