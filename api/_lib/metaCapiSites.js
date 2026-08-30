/**
 * metaCapiSites — lógica compartilhada do CRUD de `meta_capi_sites`.
 *
 * Consumido por DOIS hosts:
 *   - produção: `api/meta-capi/sites.js` (serverless da Vercel)
 *   - dev:      `server/index.js` (Express)
 * Por isso este arquivo NÃO importa express, NÃO toca em `req`/`res` e NÃO
 * conhece Vercel. Ele recebe dados simples e devolve `{ status, data|error }`.
 * Assim dev e produção não podem divergir de comportamento.
 *
 * Arquivos `_*` dentro de `api/` não viram rota na Vercel — é o mecanismo
 * oficial para colocar código compartilhado ao lado das funções.
 *
 * ---------------------------------------------------------------------------
 * POR QUE AUTENTICAÇÃO PRÓPRIA EM VEZ DO PROXY GENÉRICO /api/supabase/*
 * ---------------------------------------------------------------------------
 * Os endpoints `/api/supabase/{query,insert,update,delete,rpc}` deste sistema
 * aceitam QUALQUER tabela, com a service_role, SEM nenhuma autenticação. Eles
 * são um bypass público de RLS. Passar `meta_capi_sites` por ali significaria
 * expor o cipher do token (e permitir escrita) para qualquer um na internet.
 * Este módulo é o oposto:
 *   1. exige `Authorization: Bearer <access_token do Supabase>`;
 *   2. valida o JWT de verdade em `supabase.auth.getUser(token)`;
 *   3. exige `users.role === 'ADMIN'`;
 *   4. nunca devolve o token — nem cifrado.
 *
 * REGRA DE OURO: nada de token nem de master key em log. Nunca.
 */

import { encryptToken } from './capiCrypto.js';
import {
  exigirAdmin,
  lerTokenBearer,
  obterSupabase,
  resolverOrigemPermitida,
} from './identidade.js';

const TABLE = 'meta_capi_sites';

/**
 * Colunas devolvidas ao cliente. Whitelist explícita e não uma blacklist:
 * se amanhã alguém adicionar `capi_token_backup` na tabela, ela NÃO vaza por
 * omissão. `capi_token_cipher`/`capi_token_iv` jamais entram aqui — o cliente
 * só recebe `has_token: boolean`.
 */
const PUBLIC_COLUMNS = [
  'id',
  'site_key',
  'site_name',
  'domain',
  'cookie_domain',
  'endpoint_url',
  'pixel_id',
  'events',
  'is_active',
  'test_event_code',
  'last_check_at',
  'last_check_result',
  'created_by',
  'created_at',
  'updated_at',
];

/** Colunas lidas do banco = as públicas + as que só servem para derivar has_token. */
const SELECT_COLUMNS = [...PUBLIC_COLUMNS, 'capi_token_cipher', 'capi_token_iv'].join(', ');

const DEFAULT_EVENTS = { interstitial: true, rewarded: true };

// ---------------------------------------------------------------------------
// Infra
// ---------------------------------------------------------------------------

/**
 * Cliente supabase com service_role.
 *
 * Delega para `identidade.obterSupabase()`: o cache lazy, a checagem de env e
 * a mensagem de erro moram lá, numa implementação só. Antes existiam duas
 * cópias desta função no repositório, e duas cópias divergem.
 */
function getSupabase() {
  return obterSupabase();
}

/** Erro tipado, no mesmo formato para os dois hosts. */
function fail(status, error, extra) {
  return { status, error, ...(extra || {}) };
}

function ok(status, data) {
  return { status, data };
}

/**
 * A master key é lida a cada chamada (e não cacheada) para que uma rotação
 * de env var valha na próxima invocação, sem redeploy do dev server.
 */
function getMasterKey() {
  const key = process.env.CAPI_MASTER_KEY;
  return typeof key === 'string' && key.trim() !== '' ? key.trim() : null;
}

/**
 * Guard de configuração. Sem master key NÃO existe fallback: gravar o token
 * em texto puro seria pior do que não gravar. Responde 503 explicando o que
 * fazer, em vez de estourar 500 genérico.
 */
export function requireMasterKey() {
  if (getMasterKey()) return null;
  return fail(
    503,
    'CAPI_MASTER_KEY não configurada no servidor. Gere a chave com `openssl rand -base64 32`, coloque em CAPI_MASTER_KEY (ambiente do backend / variáveis do projeto na Vercel) e use A MESMA chave nos secrets da Edge Function capi-router. O token não é gravado sem cifra.'
  );
}

/** `true` se o backend já consegue cifrar/decifrar. Útil para a UI avisar antes. */
export function isMasterKeyConfigured() {
  return getMasterKey() !== null;
}

// ---------------------------------------------------------------------------
// Autorização — delegada a `_lib/identidade.js`
// ---------------------------------------------------------------------------
//
// Este módulo foi o PRIMEIRO a fazer autenticação direito neste repositório, e
// por isso carregou por um tempo a única implementação correta: Bearer
// obrigatório, JWT validado no GoTrue, papel conferido em `public.users`.
//
// Em 24/08/2026 essa implementação virou `_lib/identidade.js` e passou a ser
// usada também pelas rotas nomeadas (`/api/me`, `/api/users`, `/api/settings`)
// que substituíram os proxies `service_role` sem portão. Aqui ficaram apenas
// os re-exports, para não quebrar quem já importava por este caminho.
//
// A duplicata foi removida DE PROPÓSITO: enquanto existiam duas respostas para
// "quem está pedindo?", corrigir uma delas deixava a outra intacta.

/**
 * Extrai o token de um header `Authorization: Bearer <jwt>`.
 * @param {string|undefined} headerValue
 * @returns {string|null}
 */
export function parseBearerToken(headerValue) {
  return lerTokenBearer(headerValue);
}

/**
 * Valida o access token do Supabase e exige role ADMIN.
 *
 * Mantém a forma de retorno histórica (`{status, user, error}`) porque
 * `dispatch()` abaixo lê `auth.user.id`. `identidade.exigirAdmin` devolve
 * `{status, usuario}` — a adaptação é este objeto, e mais nada.
 *
 * @param {string|null} accessToken JWT do usuário (não a service key)
 * @returns {Promise<{status:number, user?:object, error?:string}>}
 */
export async function requireAdmin(accessToken) {
  const identidade = await exigirAdmin(accessToken);
  if (identidade.status !== 200) {
    return fail(identidade.status, identidade.error);
  }
  const u = identidade.usuario;
  return { status: 200, user: { id: u.id, email: u.email, role: u.role } };
}

// ---------------------------------------------------------------------------
// Validação de payload
// ---------------------------------------------------------------------------

const SITE_KEY_RE = /^[a-z0-9][a-z0-9-]*$/;
const PIXEL_ID_RE = /^\d{5,}$/;

function str(value) {
  return typeof value === 'string' ? value.trim() : '';
}

/**
 * Valida e normaliza o corpo do upsert.
 * @returns {{errors: string[], value: object}}
 */
function validateSitePayload(payload) {
  const errors = [];
  const value = {};

  const siteKey = str(payload.site_key).toLowerCase();
  if (!siteKey) {
    errors.push('`site_key` é obrigatório.');
  } else if (!SITE_KEY_RE.test(siteKey)) {
    errors.push('`site_key` deve conter apenas letras minúsculas, números e hífen (ex.: `apps-technews`).');
  }
  value.site_key = siteKey;

  const siteName = str(payload.site_name);
  if (!siteName) errors.push('`site_name` é obrigatório.');
  value.site_name = siteName;

  // Aceita o domínio com protocolo/barra e normaliza para host puro —
  // o operador cola a URL do navegador com frequência.
  const domain = normalizeHost(payload.domain);
  if (!domain) {
    errors.push('`domain` é obrigatório (ex.: `apps.technewsbrasil.com.br`).');
  } else if (!domain.includes('.')) {
    errors.push('`domain` não parece um host válido (falta o ponto).');
  }
  value.domain = domain;

  const cookieDomain = str(payload.cookie_domain).toLowerCase();
  if (!cookieDomain) {
    errors.push('`cookie_domain` é obrigatório.');
  } else if (!cookieDomain.startsWith('.')) {
    errors.push('`cookie_domain` precisa começar com ponto (o APEX, ex.: `.technewsbrasil.com.br`) — sem isso o cookie não é compartilhado entre subdomínios.');
  }
  value.cookie_domain = cookieDomain;

  const endpointUrl = str(payload.endpoint_url);
  if (!endpointUrl) {
    errors.push('`endpoint_url` é obrigatório (ex.: `https://ev.seudominio.com.br/capi`).');
  } else if (!/^https?:\/\/.+/i.test(endpointUrl)) {
    errors.push('`endpoint_url` precisa ser uma URL http(s) completa.');
  }
  value.endpoint_url = endpointUrl;

  const pixelId = str(payload.pixel_id);
  if (!pixelId) {
    errors.push('`pixel_id` é obrigatório.');
  } else if (!PIXEL_ID_RE.test(pixelId)) {
    errors.push('`pixel_id` deve ser numérico (só os dígitos do ID do Pixel).');
  }
  value.pixel_id = pixelId;

  value.events = normalizeEvents(payload.events);

  if (payload.is_active !== undefined) {
    value.is_active = Boolean(payload.is_active);
  }

  if (payload.test_event_code !== undefined) {
    const code = str(payload.test_event_code);
    value.test_event_code = code === '' ? null : code;
  }

  return { errors, value };
}

function normalizeHost(raw) {
  let host = str(raw).toLowerCase();
  if (!host) return '';
  host = host.replace(/^[a-z]+:\/\//, ''); // tira protocolo
  host = host.split('/')[0];               // tira path
  host = host.split('?')[0];
  host = host.split('#')[0];
  host = host.replace(/:\d+$/, '');        // tira porta
  return host;
}

function normalizeEvents(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { ...DEFAULT_EVENTS };
  }
  return {
    interstitial: raw.interstitial === undefined ? DEFAULT_EVENTS.interstitial : Boolean(raw.interstitial),
    rewarded: raw.rewarded === undefined ? DEFAULT_EVENTS.rewarded : Boolean(raw.rewarded),
  };
}

/** Converte a linha do banco no shape público (sem cipher, com has_token). */
function toPublicSite(row) {
  const out = {};
  for (const column of PUBLIC_COLUMNS) {
    out[column] = row[column] === undefined ? null : row[column];
  }
  out.has_token = Boolean(row.capi_token_cipher && row.capi_token_iv);
  return out;
}

function parseId(raw) {
  if (raw === undefined || raw === null || raw === '') return null;
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

// ---------------------------------------------------------------------------
// Operações
// ---------------------------------------------------------------------------

/**
 * Lista todos os sites. NUNCA devolve `capi_token_cipher`/`capi_token_iv`.
 * @returns {Promise<{status:number, data?:object[], error?:string}>}
 */
export async function listSites() {
  let supabase;
  try {
    supabase = getSupabase();
  } catch (err) {
    return fail(500, err.message);
  }

  const { data, error } = await supabase
    .from(TABLE)
    .select(SELECT_COLUMNS)
    .order('site_name', { ascending: true });

  if (error) {
    console.error('[meta-capi] listSites falhou:', error.message);
    return fail(500, 'Não foi possível listar os sites.');
  }

  return ok(200, (data || []).map(toPublicSite));
}

/**
 * Cria ou atualiza um site.
 *
 * - `capi_token` (texto puro) só existe NESTE ponto do sistema: é cifrado
 *   antes de qualquer ida ao banco e nunca é devolvido nem logado.
 * - Em UPDATE sem `capi_token`, o token existente é PRESERVADO (as colunas
 *   cipher/iv simplesmente não entram no UPDATE).
 * - Em INSERT o token é obrigatório — as colunas são NOT NULL e um site sem
 *   token não serve para nada.
 *
 * @param {object} payload config do site + `capi_token` opcional
 * @param {string|null} userId id do admin (vai para `created_by` no insert)
 */
export async function upsertSite(payload, userId) {
  if (!payload || typeof payload !== 'object') {
    return fail(400, 'Corpo da requisição ausente ou inválido.');
  }

  const missingKey = requireMasterKey();
  if (missingKey) return missingKey;

  let supabase;
  try {
    supabase = getSupabase();
  } catch (err) {
    return fail(500, err.message);
  }

  const { errors, value } = validateSitePayload(payload);
  if (errors.length > 0) {
    return fail(400, `Dados inválidos: ${errors.join(' ')}`, { fields: errors });
  }

  // Qual linha estamos mexendo? Por id explícito, senão pela site_key.
  const explicitId = parseId(payload.id);
  const existing = await findExistingSite(supabase, explicitId, value.site_key);
  if (existing.error) {
    console.error('[meta-capi] upsertSite/lookup falhou:', existing.error.message);
    return fail(500, 'Não foi possível verificar se o site já existe.');
  }
  if (explicitId && !existing.data) {
    return fail(404, `Site id=${explicitId} não encontrado.`);
  }

  const plainToken = str(payload.capi_token);
  const isInsert = !existing.data;

  if (isInsert && !plainToken) {
    return fail(400, '`capi_token` é obrigatório ao cadastrar um site novo.');
  }

  const row = { ...value };

  if (plainToken) {
    try {
      const { cipher, iv } = await encryptToken(plainToken, getMasterKey());
      row.capi_token_cipher = cipher;
      row.capi_token_iv = iv;
    } catch (err) {
      // A mensagem de capiCrypto fala de formato/tamanho, nunca de conteúdo.
      return fail(500, `Falha ao cifrar o token: ${err.message}`);
    }
  }

  if (isInsert) {
    if (row.is_active === undefined) row.is_active = true;
    if (userId) row.created_by = userId;

    const { data, error } = await supabase
      .from(TABLE)
      .insert(row)
      .select(SELECT_COLUMNS)
      .single();

    if (error) return dbError(error, 'cadastrar');
    return ok(201, toPublicSite(data));
  }

  const { data, error } = await supabase
    .from(TABLE)
    .update(row)
    .eq('id', existing.data.id)
    .select(SELECT_COLUMNS)
    .single();

  if (error) return dbError(error, 'atualizar');
  return ok(200, toPublicSite(data));
}

async function findExistingSite(supabase, explicitId, siteKey) {
  if (explicitId) {
    return supabase.from(TABLE).select('id').eq('id', explicitId).limit(1).maybeSingle();
  }
  if (siteKey) {
    return supabase.from(TABLE).select('id').eq('site_key', siteKey).limit(1).maybeSingle();
  }
  return { data: null, error: null };
}

/** Traduz erros do Postgres em mensagens acionáveis em pt-BR. */
function dbError(error, verb) {
  if (error.code === '23505') {
    const details = String(error.message || '');
    if (details.includes('domain')) {
      return fail(409, 'Já existe outro site cadastrado com esse `domain`. Cada domínio pode ter um único cadastro.');
    }
    if (details.includes('site_key')) {
      return fail(409, 'Já existe outro site cadastrado com essa `site_key`. Escolha outra chave.');
    }
    return fail(409, 'Já existe um site com essa `site_key` ou esse `domain`.');
  }
  if (error.code === '42P01') {
    return fail(500, 'Tabela `meta_capi_sites` não existe. Rode a migração `src/sql/v7_13_meta_capi_sites.sql` no Supabase.');
  }
  console.error(`[meta-capi] falha ao ${verb} site:`, error.code, error.message);
  return fail(500, `Não foi possível ${verb} o site.`);
}

/**
 * Grava o resultado do teste ao vivo do wizard.
 * @param {number|string} id
 * @param {object} result resultado por camada (endpoint/function/meta)
 */
export async function recordCheck(id, result) {
  const siteId = parseId(id);
  if (!siteId) return fail(400, '`id` do site é obrigatório e deve ser numérico.');

  let supabase;
  try {
    supabase = getSupabase();
  } catch (err) {
    return fail(500, err.message);
  }

  const { data, error } = await supabase
    .from(TABLE)
    .update({
      last_check_at: new Date().toISOString(),
      last_check_result: sanitizeCheckResult(result),
    })
    .eq('id', siteId)
    .select(SELECT_COLUMNS)
    .single();

  if (error) {
    if (error.code === 'PGRST116') return fail(404, `Site id=${siteId} não encontrado.`);
    console.error('[meta-capi] recordCheck falhou:', error.code, error.message);
    return fail(500, 'Não foi possível gravar o resultado do teste.');
  }

  return ok(200, toPublicSite(data));
}

/**
 * O resultado do check vem do cliente e vai para uma coluna jsonb que é lida
 * na tela. Removemos qualquer campo com cara de segredo antes de persistir —
 * `last_check_result` nunca pode virar um vazamento de token por descuido.
 */
const SECRET_KEY_RE = /(token|secret|password|senha|authorization|api[-_]?key|master[-_]?key)/i;

function sanitizeCheckResult(value, depth = 0) {
  if (value === null || value === undefined) return null;
  if (depth > 6) return '[profundidade máxima]';

  if (Array.isArray(value)) {
    return value.slice(0, 50).map((item) => sanitizeCheckResult(item, depth + 1));
  }

  if (typeof value === 'object') {
    const out = {};
    for (const [key, val] of Object.entries(value)) {
      if (SECRET_KEY_RE.test(key)) {
        out[key] = '[removido]';
        continue;
      }
      out[key] = sanitizeCheckResult(val, depth + 1);
    }
    return out;
  }

  if (typeof value === 'string') {
    return value.length > 4000 ? `${value.slice(0, 4000)}…[truncado]` : value;
  }

  return value;
}

/**
 * Remove o site.
 * @param {number|string} id
 */
export async function deleteSite(id) {
  const siteId = parseId(id);
  if (!siteId) return fail(400, '`id` do site é obrigatório e deve ser numérico.');

  let supabase;
  try {
    supabase = getSupabase();
  } catch (err) {
    return fail(500, err.message);
  }

  const { data, error } = await supabase
    .from(TABLE)
    .delete()
    .eq('id', siteId)
    .select('id');

  if (error) {
    console.error('[meta-capi] deleteSite falhou:', error.code, error.message);
    return fail(500, 'Não foi possível remover o site.');
  }

  if (!data || data.length === 0) {
    return fail(404, `Site id=${siteId} não encontrado.`);
  }

  return ok(200, { id: siteId, deleted: true });
}

// ---------------------------------------------------------------------------
// CORS (compartilhado, para dev e produção concordarem)
// ---------------------------------------------------------------------------

/**
 * Decide qual valor devolver em `Access-Control-Allow-Origin`.
 *
 * Re-export de `_lib/identidade.js`. Nunca `*`: este endpoint usa credenciais
 * (Bearer) e mexe em dados sensíveis. Mantido aqui pelo nome antigo porque
 * `api/meta-capi/sites.js` e `server/index.js` já importavam por este caminho.
 *
 * @param {string|undefined} origin
 * @returns {string|null}
 */
export function resolveAllowedOrigin(origin) {
  return resolverOrigemPermitida(origin);
}

// ---------------------------------------------------------------------------
// Dispatch — o roteamento em si, para dev e produção não divergirem
// ---------------------------------------------------------------------------

/**
 * Roteia uma requisição já normalizada.
 *
 * Os hosts só precisam adaptar entrada/saída (CORS, `res.status().json()`);
 * a decisão de "o que fazer" mora aqui, uma vez só.
 *
 * Rotas (o `check` é identificado por query/body porque a Vercel entrega
 * `/api/meta-capi/sites` como UM arquivo — não há `:id/check` no filesystem):
 *   GET                                        -> lista
 *   POST                                       -> cria/atualiza
 *   POST   { action: 'check', id, result }     -> grava check (fallback p/ clientes sem PATCH)
 *   PATCH  ?id=1  { result }                   -> grava check
 *   DELETE ?id=1                               -> remove
 *
 * @param {{method:string, query?:object, body?:object, authorization?:string, id?:string|number}} input
 * @returns {Promise<{status:number, data?:any, error?:string}>}
 */
export async function dispatch(input) {
  const method = String(input?.method || '').toUpperCase();
  const query = input?.query || {};
  const body = input?.body && typeof input.body === 'object' ? input.body : {};

  // 1. Autorização vale para TODOS os métodos (o preflight OPTIONS é tratado
  //    pelo host antes de chegar aqui — preflight não carrega Authorization).
  const auth = await requireAdmin(parseBearerToken(input?.authorization));
  if (auth.status !== 200) return fail(auth.status, auth.error);

  // id pode vir da rota (dev), da query (produção) ou do corpo.
  const id = input?.id ?? query.id ?? body.id;
  const action = str(query.action) || str(body.action);

  switch (method) {
    case 'GET':
      return listSites();

    case 'POST':
      if (action === 'check') return recordCheck(id, body.result ?? body.check ?? body);
      return upsertSite(body, auth.user.id);

    case 'PUT':
      return upsertSite(body, auth.user.id);

    case 'PATCH':
      return recordCheck(id, body.result ?? body.check ?? body);

    case 'DELETE':
      return deleteSite(id);

    default:
      return fail(405, `Método ${method || '(vazio)'} não permitido em /api/meta-capi/sites.`);
  }
}
