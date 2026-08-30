/**
 * perfil — `GET /api/me`, o substituto de `POST /api/users/query`.
 *
 * ---------------------------------------------------------------------------
 * O QUE MUDOU, E POR QUE
 * ---------------------------------------------------------------------------
 * `POST /api/users/query` recebia um e-mail NO CORPO da requisição, sem
 * autenticação, e respondia `select('*')` de `public.users`. Duas falhas
 * distintas na mesma rota:
 *
 *   1. era um oráculo de enumeração — testava-se e-mail por e-mail para
 *      descobrir quem tem conta;
 *   2. `select('*')` numa tabela que guarda `password_hash`,
 *      `token_primeiro_acesso` e `token_expiracao` entregava o hash da senha
 *      do ADMIN para quem pedisse. Material para quebra offline, sem nenhuma
 *      tentativa de login registrada em lugar nenhum.
 *
 * `GET /api/me` corrige a classe do problema, não o sintoma: não existe
 * parâmetro de entrada. Quem a requisição descreve é decidido pelo JWT, então
 * não há e-mail a escolher. E as colunas vêm da whitelist `COLUNAS_PERFIL` —
 * uma coluna nova na tabela não vaza por omissão.
 */

import { exigirUsuario, lerTokenBearer, falha, ok } from './identidade.js';

/**
 * @param {{method:string, authorization?:string}} entrada
 * @returns {Promise<{status:number, data?:object, error?:string, codigo?:string}>}
 */
export async function despacharPerfil(entrada) {
  const metodo = String(entrada?.method || '').toUpperCase();

  if (metodo !== 'GET') {
    return falha(405, `Método ${metodo || '(vazio)'} não permitido em /api/me.`);
  }

  const identidade = await exigirUsuario(lerTokenBearer(entrada?.authorization));
  if (identidade.status !== 200) {
    return falha(identidade.status, identidade.error, { codigo: identidade.codigo });
  }

  // `identidade.usuario` já vem restrito a COLUNAS_PERFIL pelo próprio guarda.
  return ok(200, identidade.usuario);
}
