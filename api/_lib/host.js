/**
 * host — o adaptador que faz a Vercel e o Express responderem igual.
 *
 * ---------------------------------------------------------------------------
 * POR QUE UM ADAPTADOR EM VEZ DE DOIS HANDLERS
 * ---------------------------------------------------------------------------
 * Este repositório tem dois hosts para as mesmas rotas: as funções serverless
 * da Vercel (`api/*.js`) e o Express do dev (`server/index.js`). Quando cada
 * um implementa a própria versão da rota, eles divergem — e a divergência
 * aparece exatamente onde dói: o dev testa com um portão e a produção roda com
 * outro. Foi assim que `/api/supabase/delete` passou a existir só no Express,
 * sem par na Vercel e sem ninguém notar.
 *
 * Aqui a regra mora numa função `despachar()` pura, e os dois hosts são
 * fabricados a partir dela. Equivalência por construção, não por disciplina:
 * não há como adicionar um `if` na produção sem que o dev o receba junto.
 *
 * O CORS e o `Cache-Control: no-store` também moram aqui, pelo mesmo motivo.
 */

import { resolverOrigemPermitida } from './identidade.js';

/**
 * Monta os cabeçalhos comuns e decide se a requisição para aqui.
 *
 * @returns {{parar:true, status:number, corpo?:object}|{parar:false}}
 */
function prepararCabecalhos({ metodo, origem, metodosPermitidos, definirHeader }) {
  const origemPermitida = resolverOrigemPermitida(origem);

  // `Vary: Origin` evita que um CDN sirva a resposta de uma origem para outra.
  definirHeader('Vary', 'Origin');
  if (origemPermitida) {
    definirHeader('Access-Control-Allow-Origin', origemPermitida);
    definirHeader('Access-Control-Allow-Credentials', 'true');
  }
  definirHeader('Access-Control-Allow-Methods', `${metodosPermitidos},OPTIONS`);
  definirHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept');
  definirHeader('Access-Control-Max-Age', '600');
  // Resposta com dado de usuário não pode ficar em cache de CDN nem de browser.
  definirHeader('Cache-Control', 'no-store');

  if (metodo === 'OPTIONS') {
    // Preflight não carrega Authorization — responder antes de qualquer auth.
    // Se a origem não foi liberada, o navegador barra sozinho (não mandamos o
    // header Allow-Origin), então 204 aqui é seguro.
    return { parar: true, status: 204 };
  }

  if (origem && !origemPermitida) {
    return { parar: true, status: 403, corpo: { error: 'Origin não autorizada.' } };
  }

  return { parar: false };
}

/**
 * Fabrica o handler da Vercel.
 *
 * @param {(entrada:object) => Promise<{status:number,data?:any,error?:string}>} despachar
 * @param {{metodos:string, nome:string}} opcoes
 */
export function criarHandlerVercel(despachar, { metodos, nome }) {
  return async function handler(req, res) {
    const decisao = prepararCabecalhos({
      metodo: req.method,
      origem: req.headers?.origin,
      metodosPermitidos: metodos,
      definirHeader: (k, v) => res.setHeader(k, v),
    });

    if (decisao.parar) {
      if (decisao.corpo) return res.status(decisao.status).json(decisao.corpo);
      return res.status(decisao.status).end();
    }

    try {
      const resultado = await despachar({
        method: req.method,
        query: req.query || {},
        body: normalizarCorpo(req.body),
        authorization: req.headers?.authorization,
      });

      if (resultado.error) {
        const carga = { error: resultado.error };
        if (resultado.codigo) carga.codigo = resultado.codigo;
        if (resultado.fields) carga.fields = resultado.fields;
        return res.status(resultado.status).json(carga);
      }

      return res.status(resultado.status).json(resultado.data);
    } catch (erro) {
      // Nunca logar o corpo: ele pode carregar senha (POST /api/users).
      console.error(`[${nome}] erro não tratado:`, erro?.message);
      return res.status(500).json({ error: 'Erro interno ao processar a requisição.' });
    }
  };
}

/**
 * Fabrica o handler do Express a partir da MESMA `despachar()`.
 *
 * O CORS global do `server/index.js` já roda antes; repetimos os cabeçalhos
 * aqui de propósito, para que a resposta seja byte-a-byte comparável com a da
 * Vercel num teste de equivalência.
 */
export function criarHandlerExpress(despachar, { metodos, nome }) {
  return async function handler(req, res) {
    const decisao = prepararCabecalhos({
      metodo: req.method,
      origem: req.headers?.origin,
      metodosPermitidos: metodos,
      definirHeader: (k, v) => res.set(k, v),
    });

    if (decisao.parar) {
      if (decisao.corpo) return res.status(decisao.status).json(decisao.corpo);
      return res.status(decisao.status).end();
    }

    try {
      const resultado = await despachar({
        method: req.method,
        query: req.query || {},
        body: normalizarCorpo(req.body),
        authorization: req.headers?.authorization,
      });

      if (resultado.error) {
        const carga = { error: resultado.error };
        if (resultado.codigo) carga.codigo = resultado.codigo;
        if (resultado.fields) carga.fields = resultado.fields;
        return res.status(resultado.status).json(carga);
      }

      return res.status(resultado.status).json(resultado.data);
    } catch (erro) {
      console.error(`[${nome}] erro não tratado:`, erro?.message);
      return res.status(500).json({ error: 'Erro interno ao processar a requisição.' });
    }
  };
}

/**
 * A Vercel entrega `req.body` já parseado quando o Content-Type é JSON, mas em
 * DELETE/PATCH sem content-type ele pode vir string ou undefined.
 */
function normalizarCorpo(corpo) {
  if (!corpo) return {};
  if (typeof corpo === 'object') return corpo;
  if (typeof corpo === 'string') {
    try {
      return JSON.parse(corpo);
    } catch {
      return {};
    }
  }
  return {};
}
