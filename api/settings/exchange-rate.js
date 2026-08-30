/**
 * PUT /api/settings/exchange-rate — cotação do dólar, restrita a ADMIN.
 *
 * Rota própria porque a operação não é "gravar uma chave": ela dispara
 * `rpc_set_dollar_exchange_rate`, que grava a taxa e recalcula o mês inteiro
 * na mesma transação. Gravar `dollar_exchange_rate` por `PUT /api/settings`
 * deixaria a taxa nova com as receitas convertidas pela taxa velha — por isso
 * aquela rota recusa esta chave.
 *
 * Substitui o único uso legítimo de `POST /api/supabase/rpc`, que aceitava o
 * NOME DA FUNÇÃO no corpo. Ver o cabeçalho de `_lib/configuracoes.js`.
 */

import { criarHandlerVercel } from '../_lib/host.js';
import { despacharConfiguracoes } from '../_lib/configuracoes.js';

export default criarHandlerVercel(
  (entrada) => despacharConfiguracoes({ ...entrada, recurso: 'exchange-rate' }),
  { metodos: 'PUT', nome: 'settings/exchange-rate' }
);
