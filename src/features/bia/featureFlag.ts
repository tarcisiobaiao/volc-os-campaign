/**
 * Bia — feature flag do front.
 *
 * Mesmo padrão de `src/v6/featureFlag.ts`: `VITE_BIA_ENABLED=true` no
 * `.env.local` e restart do Vite. Desligada por padrão.
 *
 * ⚠️ É só VISIBILIDADE. A autorização mora no servidor: `BIA_ENABLED=1` e
 * `exigir_admin` em `/api/agent/*`. Com a flag ligada e o backend desligado, o
 * widget aparece e recebe 404 — nunca contorna nada.
 */
export const isBiaEnabled = (): boolean => import.meta.env.VITE_BIA_ENABLED === 'true';
