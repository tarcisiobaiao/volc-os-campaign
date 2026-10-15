/**
 * O código da Edge Function `capi-router`, para o wizard exibir no dev.
 *
 * ## Por que um módulo só para isso
 *
 * O `?raw` garante que o wizard mostra o MESMO arquivo versionado que se publica.
 * Mas, importado direto no `WizardSteps.tsx`, ele levava as 500 linhas de
 * `supabase/functions/capi-router/index.ts` (código de servidor, desenho da
 * cifra dos tokens, nomes de secret) para o bundle de produção servido a
 * qualquer navegador.
 *
 * `vite.config.ts` troca este módulo por `capiRouterSource.producao.ts` quando
 * `mode === 'production'` — o mesmo mecanismo da bancada visual, porque um `if
 * (import.meta.env.DEV)` em volta de um `import()` elimina o ramo e não o
 * chunk. Quem cobra é `src/__tests__/bundle-sem-codigo-de-servidor.test.ts`
 * sob `VOLC_PROVA_DE_BUNDLE=1`.
 */
import fonte from '../../../../supabase/functions/capi-router/index.ts?raw';

/** Caminho do arquivo no repositório: é o que se publica, em qualquer modo. */
export const CAPI_ROUTER_CAMINHO = 'supabase/functions/capi-router/index.ts';

/** O código, ou `null` quando o build não o embarca (produção). */
export const CAPI_ROUTER_SOURCE: string | null = fonte;
