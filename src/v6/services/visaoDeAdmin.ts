import { supabase } from '@/lib/supabase';

// Depois da v8_03 (pacote do incidente anon, W4), quem vê todas as linhas de
// public.users é quem tem ADMIN ativo em app_auth.user_roles para o sub do JWT
// — não quem tem role='ADMIN' em public.users. Um admin sem esse papel passa a
// receber só a própria linha, sem erro nenhum do banco. Estas guardas trocam a
// lista silenciosamente incompleta por um erro que diz o que fazer.
export const MENSAGEM_ADMIN_SEM_PAPEL =
  'Seu login é ADMIN no cadastro, mas não tem o papel ADMIN no banco (app_auth). ' +
  'Por isso a lista de usuários veio só com a sua linha. Peça a concessão com ' +
  "public.volc_grant_role('<seu auth.users.id>', 'ADMIN', 'motivo').";

async function papelAdminNoBanco(): Promise<boolean | null> {
  const { data, error } = await supabase.rpc('volc_current_admin');
  if (error || typeof data !== 'boolean') return null; // sem diagnóstico possível
  return data;
}

/**
 * Chame com as linhas de users que a consulta devolveu. Lança erro quando a
 * lista só tem a linha de um ADMIN que o banco não reconhece como ADMIN.
 * Operador (role != ADMIN) vendo só a própria linha é o comportamento esperado.
 */
export async function garantirListaCompletaDeUsuarios(
  linhas: ReadonlyArray<{ role?: string | null }>,
): Promise<void> {
  if (linhas.length !== 1 || linhas[0]?.role !== 'ADMIN') return;
  if ((await papelAdminNoBanco()) === false) throw new Error(MENSAGEM_ADMIN_SEM_PAPEL);
}

/**
 * Para contagens de ADMIN: "só existe 1 admin" pode ser só o que a RLS deixou
 * ver. Lança o erro de papel em vez de um falso "último administrador".
 */
export async function garantirContagemDeAdminsConfiavel(contagem: number): Promise<void> {
  if (contagem > 1) return;
  if ((await papelAdminNoBanco()) === false) throw new Error(MENSAGEM_ADMIN_SEM_PAPEL);
}
