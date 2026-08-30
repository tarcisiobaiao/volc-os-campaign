/**
 * identidade — o portão de identidade compartilhado das rotas Node.
 *
 * Consumido por DOIS hosts, como todo `api/_lib/`:
 *   - produção: as funções serverless da Vercel em `api/*.js`
 *   - dev:      `server/index.js` (Express)
 * Por isso este módulo não importa express, não toca em `req`/`res` e não
 * conhece Vercel. Recebe dados simples e devolve `{ status, ... }`.
 *
 * ---------------------------------------------------------------------------
 * POR QUE ESTE ARQUIVO EXISTE
 * ---------------------------------------------------------------------------
 * Até 24/08/2026 existiam DUAS respostas diferentes para "quem está pedindo?"
 * dentro do mesmo repositório: `api/_lib/metaCapiSites.js` fazia a coisa certa
 * (Bearer + papel conferido no servidor), e `api/supabase/*` não fazia nada —
 * aceitava qualquer tabela, com `service_role`, sem autenticação, com
 * `Access-Control-Allow-Origin: *`. Duas respostas para a mesma pergunta é
 * como um portão vira decorativo: basta usar a outra porta.
 *
 * Agora existe UMA. `metaCapiSites.js` delega para cá; as rotas nomeadas
 * (`/api/me`, `/api/users`, `/api/settings`) nasceram usando este módulo. Se
 * amanhã alguém escrever uma rota nova em `api/`, o caminho de menor esforço
 * é importar daqui — e não reimplementar um portão ligeiramente diferente.
 *
 * ---------------------------------------------------------------------------
 * DE ONDE VEM O PAPEL, E POR QUE NÃO É O MESMO DO FastAPI
 * ---------------------------------------------------------------------------
 * Aqui o papel vem de `public.users.role`. No Hub (FastAPI,
 * `backend/app/seguranca/identidade.py`) o papel vem da RPC
 * `public.volc_role_of()`, que lê `app_auth.user_roles`. A divergência é
 * DELIBERADA e tem prazo:
 *
 *   - este host serve o app legado, que já está em produção e cujos usuários
 *     existem em `public.users` hoje. Amarrar o fechamento da superfície à
 *     aplicação de uma migration em produção significaria deixar os proxies
 *     abertos até lá — inaceitável;
 *   - `app_auth.user_roles` é SEMEADA a partir de `public.users`
 *     (`supabase/migrations/v8_01_app_auth_schema_and_roles.sql:641`), casando
 *     por `lower(email)`. As duas fontes começam iguais por construção;
 *   - depois de v8_01, `public.users.role` deixa de ser livremente gravável: o
 *     trigger `app_auth.tg_users_guard_privileged_columns` bloqueia escalação
 *     de papel e registra a tentativa em `app_auth.user_role_audit`.
 *
 * CONDIÇÃO DE APOSENTADORIA: quando v8_01 estiver aplicada em produção e o
 * inventário confirmar que todo usuário de `public.users` tem linha
 * correspondente em `app_auth.user_roles`, este módulo passa a chamar
 * `volc_role_of` e `public.users.role` vira apenas dado de perfil (nome,
 * e-mail), não fonte de autorização. Até lá, NÃO existe fallback entre as
 * duas: cada host tem uma fonte só. Fallback silencioso entre fontes de
 * autorização é como um portão passa a aceitar a resposta mais permissiva.
 *
 * REGRA DE OURO: nada de token, JWT ou hash em log. Nunca.
 */

import { createClient } from '@supabase/supabase-js';

/** Papéis que o sistema reconhece. Qualquer outro valor não autoriza nada. */
export const PAPEIS = Object.freeze(['ADMIN', 'OPERATOR']);

/**
 * Colunas de `public.users` que podem sair do servidor.
 *
 * Whitelist explícita, nunca blacklist: se amanhã alguém adicionar
 * `token_recuperacao` à tabela, ela NÃO vaza por omissão. `password_hash`,
 * `token_primeiro_acesso` e `token_expiracao` jamais entram aqui.
 */
export const COLUNAS_PERFIL = Object.freeze([
  'id',
  'name',
  'email',
  'role',
  'needs_password_change',
  'first_login',
  'commission_percentage',
  'created_at',
  'updated_at',
]);

const SELECT_PERFIL = COLUNAS_PERFIL.join(', ');

// ---------------------------------------------------------------------------
// Infra
// ---------------------------------------------------------------------------

let clienteCache = null;

/**
 * Cliente supabase com `service_role`, criado SOB DEMANDA.
 *
 * Lazy de propósito: no dev, `server/index.js` chama `dotenv.config()` no corpo
 * do módulo, mas em ESM todos os imports são avaliados ANTES desse corpo rodar.
 * Instanciar no topo (como faziam os proxies antigos) deixaria as env vars
 * vazias no Express.
 */
export function obterSupabase() {
  if (clienteCache) return clienteCache;

  const url = process.env.SUPABASE_URL;
  const chave = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!url || !chave) {
    throw new Error(
      'SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY precisam estar configuradas no ambiente do backend.'
    );
  }

  clienteCache = createClient(url, chave, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return clienteCache;
}

/** Só para teste: força a próxima chamada a recriar o cliente. */
export function _resetarClienteParaTeste() {
  clienteCache = null;
}

/** Erro tipado, no mesmo formato para os dois hosts. */
export function falha(status, error, extra) {
  return { status, error, ...(extra || {}) };
}

/** Sucesso tipado. */
export function ok(status, data) {
  return { status, data };
}

// ---------------------------------------------------------------------------
// Autorização
// ---------------------------------------------------------------------------

/**
 * Extrai o token de um header `Authorization: Bearer <jwt>`.
 * @param {string|undefined} valorDoHeader
 * @returns {string|null}
 */
export function lerTokenBearer(valorDoHeader) {
  if (typeof valorDoHeader !== 'string') return null;
  const casamento = valorDoHeader.match(/^Bearer\s+(.+)$/i);
  if (!casamento) return null;
  const token = casamento[1].trim();
  return token.length > 0 ? token : null;
}

/**
 * Exige um usuário autenticado E cadastrado.
 *
 * FALHA FECHADA em todos os caminhos: sem token, token inválido, erro de
 * configuração, erro do banco — nenhum deles resulta em "segue em frente".
 * Um portão que abre quando não consegue decidir não é um portão.
 *
 * @param {string|null} token access token do Supabase (nunca a service key)
 * @returns {Promise<{status:number, usuario?:object, error?:string, codigo?:string}>}
 */
export async function exigirUsuario(token) {
  if (!token) {
    return falha(
      401,
      'Autenticação obrigatória: envie o header `Authorization: Bearer <access_token>`.',
      { codigo: 'SEM_TOKEN' }
    );
  }

  let supabase;
  try {
    supabase = obterSupabase();
  } catch (erro) {
    // Configuração ausente é 503, não 500: o serviço não está pronto, e o
    // operador precisa saber que a causa é ambiente, não código.
    console.error('[identidade] backend mal configurado:', erro.message);
    return falha(503, 'Serviço de identidade indisponível: backend mal configurado.', {
      codigo: 'CONFIG_AUSENTE',
    });
  }

  // 1. O JWT é válido? Quem é? Chamada real ao GoTrue — o payload do token
  //    nunca é lido diretamente, porque qualquer um escreve um payload.
  const { data: dadosAuth, error: erroAuth } = await supabase.auth.getUser(token);

  if (erroAuth || !dadosAuth?.user) {
    // Não logamos o token nem a mensagem crua do auth (pode ecoar o JWT).
    return falha(401, 'Sessão inválida ou expirada. Faça login novamente.', {
      codigo: 'SESSAO_INVALIDA',
    });
  }

  const usuarioAuth = dadosAuth.user;
  const email = typeof usuarioAuth.email === 'string' ? usuarioAuth.email : '';

  if (!email) {
    return falha(403, 'Usuário sem e-mail associado — não é possível verificar a permissão.', {
      codigo: 'SEM_EMAIL',
    });
  }

  // 2. Existe perfil em `public.users`? O papel vem de lá, NUNCA de
  //    `user_metadata`: aquele campo é editável pelo próprio usuário via
  //    GoTrue, então confiar nele seria deixar o visitante assinar o crachá.
  const perfil = await procurarPerfil(supabase, email, usuarioAuth.id);

  if (perfil.error) {
    console.error('[identidade] falha ao carregar perfil:', perfil.error.message);
    return falha(500, 'Não foi possível verificar as permissões do usuário.', {
      codigo: 'PERFIL_INDISPONIVEL',
    });
  }

  if (!perfil.data) {
    return falha(
      403,
      'Usuário autenticado, mas sem cadastro em `users`. Peça a um admin para liberar o acesso.',
      { codigo: 'SEM_CADASTRO' }
    );
  }

  return { status: 200, usuario: perfil.data };
}

/**
 * Exige papel ADMIN. Encadeia `exigirUsuario` — não existe caminho que chegue
 * a ADMIN sem antes provar identidade.
 *
 * @param {string|null} token
 * @returns {Promise<{status:number, usuario?:object, error?:string, codigo?:string}>}
 */
export async function exigirAdmin(token) {
  const identidade = await exigirUsuario(token);
  if (identidade.status !== 200) return identidade;

  if (String(identidade.usuario.role || '').toUpperCase() !== 'ADMIN') {
    return falha(403, 'Acesso restrito a administradores.', { codigo: 'NAO_ADMIN' });
  }

  return identidade;
}

/**
 * Acha o perfil por e-mail exato, depois em minúsculas, depois pelo id
 * (`public.users.id = auth.users.id` no fluxo de criação deste sistema).
 *
 * Evita `ilike`, que trataria `_` do e-mail como coringa — e um coringa numa
 * busca de identidade é como um e-mail casar com o de outra pessoa.
 */
async function procurarPerfil(supabase, email, authUserId) {
  const tentativas = [
    ['email', email],
    ['email', email.toLowerCase()],
    ['id', authUserId],
  ];

  for (const [coluna, valor] of tentativas) {
    if (!valor) continue;
    const { data, error } = await supabase
      .from('users')
      .select(SELECT_PERFIL)
      .eq(coluna, valor)
      .limit(1)
      .maybeSingle();

    if (error) return { data: null, error };
    if (data) return { data, error: null };
  }

  return { data: null, error: null };
}

// ---------------------------------------------------------------------------
// CORS
// ---------------------------------------------------------------------------

const ORIGEM_DEV_RE = /^https?:\/\/(localhost|127\.0\.0\.1|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/;

/**
 * Decide qual valor devolver em `Access-Control-Allow-Origin`.
 *
 * Nunca `*`. Estas rotas trafegam credencial (Bearer) e mexem em dado
 * sensível; `*` numa rota credenciada é contradição declarada — o navegador
 * só manda credencial para origem permitida nominalmente.
 *
 * E que fique registrado: CORS **não é autenticação**. `curl` não lê
 * `Access-Control-Allow-Origin`. O que protege estas rotas é o Bearer; o CORS
 * só evita que uma página de terceiro use a sessão do usuário logado.
 *
 * @param {string|undefined} origem header Origin da requisição
 * @returns {string|null} a origem a ecoar, ou null se não permitida
 */
export function resolverOrigemPermitida(origem) {
  if (!origem) return null;

  const lista = new Set(
    String(process.env.ALLOWED_ORIGINS || '')
      .split(',')
      .map((o) => o.trim())
      .filter(Boolean)
  );

  if (process.env.VITE_SITE_URL) lista.add(process.env.VITE_SITE_URL.trim());
  if (process.env.VERCEL_URL) lista.add(`https://${process.env.VERCEL_URL}`);
  if (process.env.VERCEL_PROJECT_PRODUCTION_URL) {
    lista.add(`https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`);
  }

  if (lista.has(origem)) return origem;

  const producao =
    process.env.NODE_ENV === 'production' || process.env.VERCEL_ENV === 'production';
  if (!producao && ORIGEM_DEV_RE.test(origem)) return origem;

  return null;
}
