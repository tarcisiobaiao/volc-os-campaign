/**
 * /api/meta-capi/sites — endpoint AUTENTICADO do wizard Meta CAPI (produção/Vercel).
 *
 * Este handler é fino de propósito: ele só faz CORS e adapta `req`/`res`.
 * Toda a regra (auth, validação, cifra, banco) mora em `../_lib/metaCapiSites.js`,
 * que o `server/index.js` importa igualzinho no dev. Um comportamento só.
 *
 * ATENÇÃO ao ler este arquivo junto com `api/supabase/query.js`:
 * aquele proxy aceita qualquer tabela, com service_role, SEM autenticação e
 * com `Access-Control-Allow-Origin: *`. Aqui é o CONTRÁRIO em tudo — Bearer
 * obrigatório, role ADMIN obrigatória, CORS por lista. Não "padronize" este
 * arquivo com os outros.
 *
 * Rotas (a Vercel entrega tudo neste único arquivo, então o `check` é
 * roteado por query/body, não por path):
 *   GET    /api/meta-capi/sites                 -> lista (sem token, com has_token)
 *   POST   /api/meta-capi/sites                 -> cria/atualiza
 *   PATCH  /api/meta-capi/sites?id=1            -> grava last_check_at/result
 *   POST   /api/meta-capi/sites  {action:'check', id, result}  -> idem (fallback)
 *   DELETE /api/meta-capi/sites?id=1            -> remove
 */

import { dispatch, resolveAllowedOrigin } from '../_lib/metaCapiSites.js';

const ALLOWED_METHODS = 'GET,POST,PUT,PATCH,DELETE,OPTIONS';

export default async function handler(req, res) {
  // ---------------------------------------------------------------------
  // CORS restrito. Nada de '*': o endpoint trafega credenciais (Bearer) e
  // mexe no cadastro que guarda o token da Meta. Ecoamos a origin só quando
  // ela está na lista permitida; `Vary: Origin` evita que um CDN sirva a
  // resposta de uma origin para outra.
  // ---------------------------------------------------------------------
  const origin = req.headers?.origin;
  const allowedOrigin = resolveAllowedOrigin(origin);

  res.setHeader('Vary', 'Origin');
  if (allowedOrigin) {
    res.setHeader('Access-Control-Allow-Origin', allowedOrigin);
    res.setHeader('Access-Control-Allow-Credentials', 'true');
  }
  res.setHeader('Access-Control-Allow-Methods', ALLOWED_METHODS);
  res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept');
  res.setHeader('Access-Control-Max-Age', '600');
  // Resposta com dado sensível não pode ficar em cache de CDN/browser.
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') {
    // Preflight não carrega Authorization — responder antes de qualquer auth.
    // Se a origin não foi liberada, o browser barra sozinho (não mandamos o
    // header Allow-Origin), então 204 aqui é seguro.
    res.status(204).end();
    return;
  }

  if (origin && !allowedOrigin) {
    return res.status(403).json({ error: 'Origin não autorizada.' });
  }

  try {
    const result = await dispatch({
      method: req.method,
      query: req.query || {},
      body: parseBody(req),
      authorization: req.headers?.authorization,
    });

    if (result.error) {
      const payload = { error: result.error };
      if (result.fields) payload.fields = result.fields;
      return res.status(result.status).json(payload);
    }

    return res.status(result.status).json(result.data);
  } catch (error) {
    // Log sem corpo da requisição: o body do POST carrega `capi_token`.
    console.error('[meta-capi] erro não tratado:', error?.message);
    return res.status(500).json({ error: 'Erro interno ao processar a requisição.' });
  }
}

/**
 * A Vercel já entrega `req.body` parseado quando o Content-Type é JSON, mas em
 * DELETE/PATCH sem content-type ele pode vir como string ou undefined.
 */
function parseBody(req) {
  const body = req.body;
  if (!body) return {};
  if (typeof body === 'object') return body;
  if (typeof body === 'string') {
    try {
      return JSON.parse(body);
    } catch {
      return {};
    }
  }
  return {};
}
