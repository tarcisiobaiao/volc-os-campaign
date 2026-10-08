/**
 * POST /api/atualizar?alvo=google-ads|gam — dispara a coleta no n8n (produção/Vercel).
 *
 * A regra mora em `_lib/atualizacoes.js`, que o `server/index.js` importa igual no dev.
 */

import { criarHandlerVercel } from './_lib/host.js';
import { despacharAtualizacao } from './_lib/atualizacoes.js';

export default criarHandlerVercel(despacharAtualizacao, { metodos: 'POST', nome: 'atualizar' });
