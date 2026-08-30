/**
 * POST /api/users — criação de usuário, restrita a ADMIN (produção/Vercel).
 *
 * Substitui `POST /api/users/create`, que chamava `auth.admin.createUser` com
 * a `service_role` e o `role` vindo do corpo, sem nenhuma autenticação.
 * Ver o cabeçalho de `_lib/usuarios.js`.
 */

import { criarHandlerVercel } from './_lib/host.js';
import { despacharUsuarios } from './_lib/usuarios.js';

export default criarHandlerVercel(despacharUsuarios, { metodos: 'POST', nome: 'users' });
