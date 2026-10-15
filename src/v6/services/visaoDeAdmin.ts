import { supabase } from '@/lib/supabase';

// Depois da v8_03 (pacote do incidente anon, W4), quem vê todas as linhas de
// public.users é quem tem ADMIN ativo em app_auth.user_roles para o sub do JWT
// — não quem tem role='ADMIN' em public.users. Um admin sem esse papel passa a
// receber só a própria linha (ou nenhuma, se o e-mail do login não casar), sem
// erro nenhum do banco. Estas guardas trocam a lista silenciosamente incompleta
// por um erro que diz o que fazer.
export const MENSAGEM_ADMIN_SEM_PAPEL =
  'Seu login é ADMIN no cadastro, mas não tem o papel ADMIN no banco (app_auth). ' +
  'Por isso a lista de usuários veio incompleta. Peça a concessão com ' +
  "public.volc_grant_role('<seu auth.users.id>', 'ADMIN', 'motivo').";

export const MENSAGEM_SEM_PERFIL =
  'A lista de usuários veio vazia: seu login não casa com nenhuma linha do cadastro ' +
  '(public.users, por e-mail) e o banco não o reconhece como ADMIN. Avise o administrador.';

export const MENSAGEM_PAPEL_INDETERMINADO =
  'A lista de usuários veio incompleta e não foi possível confirmar seu papel no ' +
  'banco (volc_current_admin falhou). A lista não é confiável; avise o administrador.';

// true/false = resposta do banco; Error = a pergunta falhou (não é "não é admin").
async function papelAdminNoBanco(): Promise<boolean | Error> {
  const { data, error } = await supabase.rpc('volc_current_admin');
  if (error || typeof data !== 'boolean') return new Error(error?.message ?? 'resposta inesperada');
  return data;
}

async function exigirPapelAdmin(mensagemSeNaoAdmin: string): Promise<void> {
  const papel = await papelAdminNoBanco();
  if (papel instanceof Error) throw new Error(MENSAGEM_PAPEL_INDETERMINADO);
  if (!papel) throw new Error(mensagemSeNaoAdmin);
}

/**
 * Chame com as linhas de users que a consulta devolveu. Lista com 2+ linhas não
 * é suspeita. Com 1 linha de OPERATOR/VIEWER é o esperado (só a própria). Com 1
 * linha de ADMIN, ou 0 linhas, confere o papel no banco e lança se ele não
 * confirmar ADMIN — inclusive quando a própria pergunta falha.
 */
export async function garantirListaCompletaDeUsuarios(
  linhas: ReadonlyArray<{ role?: string | null }>,
): Promise<void> {
  if (linhas.length > 1) return;
  if (linhas.length === 1 && linhas[0]?.role !== 'ADMIN') return;
  await exigirPapelAdmin(linhas.length === 0 ? MENSAGEM_SEM_PERFIL : MENSAGEM_ADMIN_SEM_PAPEL);
}

/**
 * Para contagens de ADMIN: "só existe 1 admin" pode ser só o que a RLS deixou
 * ver. Lança o erro de papel em vez de um falso "último administrador".
 */
export async function garantirContagemDeAdminsConfiavel(contagem: number): Promise<void> {
  if (contagem > 1) return;
  await exigirPapelAdmin(MENSAGEM_ADMIN_SEM_PAPEL);
}
