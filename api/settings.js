/**
 * /api/settings — leitura e escrita de `system_settings` por lista fechada.
 *
 *   GET  /api/settings?keys=a,b   -> usuário autenticado; só chaves legíveis
 *   PUT  /api/settings            -> ADMIN; só chaves graváveis
 *
 * Substitui os usos legítimos de `POST /api/supabase/query` e
 * `POST /api/supabase/update`, que recebiam o NOME DA TABELA no corpo.
 * Ver o cabeçalho de `_lib/configuracoes.js`.
 */

import { criarHandlerVercel } from './_lib/host.js';
import { despacharConfiguracoes } from './_lib/configuracoes.js';

export default criarHandlerVercel(
  (entrada) => despacharConfiguracoes({ ...entrada, recurso: 'settings' }),
  { metodos: 'GET,PUT', nome: 'settings' }
);
