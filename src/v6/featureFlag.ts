/**
 * v6 RBAC — feature flag
 *
 * Controla a visibilidade da nova área administrativa /admin/v6
 * (sistema novo de roles, memberships, comissões versionadas e
 * payouts), introduzida pela Etapa 3.A.
 *
 * Como ativar (somente em ambiente local ou staging):
 *   1. Crie/edite `webgo/.env.local`
 *   2. Adicione a linha:
 *
 *        VITE_USE_V6_ADMIN=true
 *
 *   3. **Reinicie o dev server** (Vite só lê variáveis de ambiente
 *      no boot — mudar `.env.local` em tempo de execução não tem
 *      efeito até o restart).
 *
 * Default: desligado. Em produção fica off por padrão. Mesmo com a
 * flag ligada, o acesso continua restrito a usuários com
 * `userProfile.role === 'ADMIN'` (defesa em camadas via
 * ProtectedRoute + filtro `adminOnly` no menu + check interno na
 * página).
 *
 * Esta função NÃO deve ter side effects e NÃO deve importar nada
 * fora deste arquivo. Ela é importada de fora de `src/v6/` por
 * exatamente dois arquivos:
 *   - `webgo/src/App.tsx` (registro condicional da rota)
 *   - `webgo/src/components/layout/Navigation.tsx` (item de menu)
 */
export const isV6Enabled = (): boolean => {
  return import.meta.env.VITE_USE_V6_ADMIN === 'true';
};
