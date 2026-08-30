/**
 * GET /api/me — o perfil de QUEM ESTÁ PEDINDO (produção/Vercel).
 *
 * Handler fino de propósito: CORS e adaptação de `req`/`res` moram em
 * `_lib/host.js`; a regra mora em `_lib/perfil.js`, que o `server/index.js`
 * importa igualzinho no dev. Um comportamento só, nos dois ambientes.
 *
 * Substitui `POST /api/users/query`, que aceitava um e-mail arbitrário no
 * corpo, sem autenticação, e respondia `select('*')` — inclusive
 * `password_hash`. Ver o cabeçalho de `_lib/perfil.js`.
 */

import { criarHandlerVercel } from './_lib/host.js';
import { despacharPerfil } from './_lib/perfil.js';

export default criarHandlerVercel(despacharPerfil, { metodos: 'GET', nome: 'me' });
