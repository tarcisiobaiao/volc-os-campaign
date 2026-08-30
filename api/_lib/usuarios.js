/**
 * usuarios — `POST /api/users`, o substituto de `POST /api/users/create`.
 *
 * ---------------------------------------------------------------------------
 * O QUE MUDOU, E POR QUE
 * ---------------------------------------------------------------------------
 * A rota antiga chamava `supabase.auth.admin.createUser()` com a `service_role`
 * e o `role` vindo do corpo, SEM nenhuma autenticação. Ou seja: um estranho
 * criava o próprio ADMIN e o sistema passava a ter dois donos — sem login, sem
 * rastro, sem nada a auditar depois.
 *
 * Agora exige papel ADMIN comprovado no servidor. O resto do fluxo é o mesmo,
 * de propósito: esta fatia fecha a superfície, não reescreve o cadastro.
 *
 * ---------------------------------------------------------------------------
 * POR QUE O ENDPOINT EXISTE (não remover achando que é redundante)
 * ---------------------------------------------------------------------------
 * `supabase.auth.signUp()` chamado do React SUBSTITUI a sessão do admin logado
 * pela do usuário recém-criado — o admin é deslogado ao criar um operador.
 * É comportamento padrão do auth client. A Admin API server-side não toca em
 * sessão nenhuma. Por isso a criação vive no servidor.
 */

import { exigirAdmin, lerTokenBearer, obterSupabase, COLUNAS_PERFIL, falha, ok } from './identidade.js';

const PAPEIS_ACEITOS = new Set(['ADMIN', 'OPERATOR']);
const SELECT_CRIADO = 'id, name, email, role, commission_percentage, created_at';

/**
 * @param {{method:string, body?:object, authorization?:string}} entrada
 */
export async function despacharUsuarios(entrada) {
  const metodo = String(entrada?.method || '').toUpperCase();

  if (metodo !== 'POST') {
    return falha(405, `Método ${metodo || '(vazio)'} não permitido em /api/users.`);
  }

  // Portão ANTES de qualquer validação de corpo: uma resposta 400 diferente da
  // 401 já conta como oráculo — diz ao anônimo que o corpo estava certo.
  const identidade = await exigirAdmin(lerTokenBearer(entrada?.authorization));
  if (identidade.status !== 200) {
    return falha(identidade.status, identidade.error, { codigo: identidade.codigo });
  }

  const corpo = entrada?.body || {};
  const nome = typeof corpo.name === 'string' ? corpo.name.trim() : '';
  const email = typeof corpo.email === 'string' ? corpo.email.trim() : '';
  const senha = typeof corpo.password === 'string' ? corpo.password : '';
  const papel = typeof corpo.role === 'string' ? corpo.role.trim().toUpperCase() : '';

  if (!email || !senha || !papel) {
    return falha(400, 'name, email, password e role são obrigatórios.');
  }
  if (!PAPEIS_ACEITOS.has(papel)) {
    return falha(400, 'role inválido (use ADMIN ou OPERATOR).');
  }

  let supabase;
  try {
    supabase = obterSupabase();
  } catch (erro) {
    return falha(503, erro.message, { codigo: 'CONFIG_AUSENTE' });
  }

  // 1. Cria em auth.users (sem mexer em sessão de ninguém).
  //
  //    `role` NÃO vai para `user_metadata`. O usuário edita o próprio
  //    `user_metadata` pelo GoTrue; guardar o papel lá seria deixar um campo
  //    com cara de autorização ao alcance de quem ele deveria limitar. O papel
  //    mora em `public.users.role` e, depois de v8_01, é defendido pelo
  //    trigger `app_auth.tg_users_guard_privileged_columns`.
  const { data: criado, error: erroCriacao } = await supabase.auth.admin.createUser({
    email,
    password: senha,
    email_confirm: true,
    user_metadata: { name: nome },
  });

  if (erroCriacao) {
    console.error('[usuarios] admin.createUser falhou:', erroCriacao.message);
    return falha(500, erroCriacao.message);
  }
  if (!criado?.user) {
    return falha(500, 'auth.users sem retorno do user.');
  }

  const authUserId = criado.user.id;

  // 2. Insere em public.users com o mesmo id.
  const { data: perfil, error: erroInsercao } = await supabase
    .from('users')
    .insert([
      {
        id: authUserId,
        email,
        name: nome,
        role: papel,
        commission_percentage: 0,
        // OBRIGA troca de senha no primeiro login. `ProtectedRoute` redireciona
        // para /change-password enquanto isso for true. Sem isso o operador
        // entra com a senha provisória escolhida pelo admin — que a conhece.
        needs_password_change: true,
        first_login: true,
      },
    ])
    .select(SELECT_CRIADO)
    .single();

  if (erroInsercao) {
    // Rollback do auth.users (best-effort). Sem ele sobraria um usuário capaz
    // de autenticar mas sem perfil — que o portão recusa com 403 e ninguém
    // consegue explicar.
    console.error('[usuarios] insert em public.users falhou — rollback:', erroInsercao.message);
    try {
      await supabase.auth.admin.deleteUser(authUserId);
    } catch (erroRollback) {
      console.error('[usuarios] rollback do auth falhou:', erroRollback?.message);
    }
    return falha(500, erroInsercao.message);
  }

  return ok(200, perfil);
}

/** Exportado só para o teste conferir que a whitelist não regrediu. */
export const COLUNAS_RESPOSTA = COLUNAS_PERFIL;
