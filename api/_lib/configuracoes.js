/**
 * configuracoes — `/api/settings` e `/api/settings/exchange-rate`.
 *
 * Substitui os usos legítimos de `POST /api/supabase/{query,update,rpc}`, que
 * eram três: ler chaves de `system_settings`, gravar chaves de
 * `system_settings`, e chamar `rpc_set_dollar_exchange_rate`.
 *
 * ---------------------------------------------------------------------------
 * A DIFERENÇA QUE IMPORTA
 * ---------------------------------------------------------------------------
 * Os proxies antigos recebiam o NOME DA TABELA e o NOME DA FUNÇÃO no corpo da
 * requisição. Quem escolhia o que ler, o que escrever e o que executar era
 * quem chamava — com `service_role`, que ignora RLS, e sem autenticação. Na
 * prática era um cliente Postgres aberto na internet: dava para enumerar o
 * esquema tabela por tabela, ler `password_hash`, e chamar qualquer função do
 * catálogo (inclusive `SECURITY DEFINER`, que roda com privilégio de quem a
 * definiu).
 *
 * Aqui NENHUM identificador do banco vem da requisição. A tabela é constante
 * no código. As chaves legíveis e graváveis são listas fechadas. A única RPC
 * chamada tem o nome escrito literalmente abaixo. O que a requisição escolhe é
 * apenas QUAL CHAVE da lista — e nada mais.
 *
 * Isso é uma diferença de CLASSE, não de grau: o pior caso deixa de ser
 * "acesso ao banco" e passa a ser "leu a cotação do dólar".
 */

import { exigirUsuario, exigirAdmin, lerTokenBearer, obterSupabase, falha, ok } from './identidade.js';

/** Tabela constante. Jamais vem da requisição. */
const TABELA = 'system_settings';

/** A única RPC alcançável por esta rota. Nome literal, nunca do corpo. */
const RPC_TAXA = 'rpc_set_dollar_exchange_rate';

/** Chave da taxa — escrita SÓ pela rota dedicada, que dispara o recálculo. */
const CHAVE_TAXA = 'dollar_exchange_rate';
const CHAVE_ATUALIZACAO_MOEDA = 'last_currency_update';

/**
 * Chaves que qualquer usuário autenticado pode LER.
 *
 * Lista fechada: uma chave nova em `system_settings` (um webhook, um token de
 * integração) não passa a ser legível só porque foi criada.
 */
export const CHAVES_LEGIVEIS = Object.freeze([
  CHAVE_TAXA,
  CHAVE_ATUALIZACAO_MOEDA,
  'currency_display',
  'auto_convert_values',
  'gam_last_update',
  'google_ads_last_update',
]);

/**
 * Chaves que um ADMIN pode GRAVAR por `PUT /api/settings`.
 *
 * `dollar_exchange_rate` está de fora DE PROPÓSITO: gravá-la direto pularia o
 * recálculo do mês que a RPC faz na mesma transação, deixando a taxa nova e as
 * receitas convertidas pela taxa velha. Ela só muda por
 * `PUT /api/settings/exchange-rate`.
 */
export const CHAVES_GRAVAVEIS = Object.freeze([
  CHAVE_ATUALIZACAO_MOEDA,
  'currency_display',
  'auto_convert_values',
  'gam_last_update',
  'google_ads_last_update',
]);

const LEGIVEIS = new Set(CHAVES_LEGIVEIS);
const GRAVAVEIS = new Set(CHAVES_GRAVAVEIS);

/**
 * @param {{method:string, query?:object, body?:object, authorization?:string,
 *          recurso?:'settings'|'exchange-rate'}} entrada
 */
export async function despacharConfiguracoes(entrada) {
  const metodo = String(entrada?.method || '').toUpperCase();
  const recurso = entrada?.recurso === 'exchange-rate' ? 'exchange-rate' : 'settings';

  if (recurso === 'exchange-rate') {
    if (metodo !== 'PUT' && metodo !== 'POST') {
      return falha(405, `Método ${metodo || '(vazio)'} não permitido em /api/settings/exchange-rate.`);
    }
    return gravarTaxa(entrada);
  }

  if (metodo === 'GET') return lerChaves(entrada);
  if (metodo === 'PUT' || metodo === 'POST') return gravarChaves(entrada);

  return falha(405, `Método ${metodo || '(vazio)'} não permitido em /api/settings.`);
}

// ---------------------------------------------------------------------------
// GET /api/settings?keys=a,b,c
// ---------------------------------------------------------------------------

async function lerChaves(entrada) {
  const identidade = await exigirUsuario(lerTokenBearer(entrada?.authorization));
  if (identidade.status !== 200) {
    return falha(identidade.status, identidade.error, { codigo: identidade.codigo });
  }

  const pedidas = extrairChaves(entrada?.query?.keys ?? entrada?.body?.keys);
  const alvo = pedidas.length > 0 ? pedidas : CHAVES_LEGIVEIS;

  const recusadas = alvo.filter((chave) => !LEGIVEIS.has(chave));
  if (recusadas.length > 0) {
    // Recusa em vez de ignorar em silêncio: um cliente que pede uma chave
    // inexistente e recebe `{}` conclui que ela está vazia, não que foi barrada.
    return falha(400, `Chave não permitida: ${recusadas.join(', ')}.`, {
      fields: recusadas,
    });
  }

  let supabase;
  try {
    supabase = obterSupabase();
  } catch (erro) {
    return falha(503, erro.message, { codigo: 'CONFIG_AUSENTE' });
  }

  const { data, error } = await supabase
    .from(TABELA)
    .select('key, value, updated_at')
    .in('key', alvo);

  if (error) {
    console.error('[configuracoes] leitura falhou:', error.message);
    return falha(500, 'Não foi possível ler as configurações.');
  }

  return ok(200, { settings: data ?? [] });
}

// ---------------------------------------------------------------------------
// PUT /api/settings  { settings: [{key, value}, ...] }
// ---------------------------------------------------------------------------

async function gravarChaves(entrada) {
  const identidade = await exigirAdmin(lerTokenBearer(entrada?.authorization));
  if (identidade.status !== 200) {
    return falha(identidade.status, identidade.error, { codigo: identidade.codigo });
  }

  const itens = normalizarItens(entrada?.body);
  if (itens.length === 0) {
    return falha(400, 'Envie `settings: [{ key, value }]` com ao menos um item.');
  }

  const recusadas = itens.map((i) => i.key).filter((chave) => !GRAVAVEIS.has(chave));
  if (recusadas.length > 0) {
    const dica = recusadas.includes(CHAVE_TAXA)
      ? ' A cotação muda apenas por PUT /api/settings/exchange-rate, que recalcula o mês na mesma transação.'
      : '';
    return falha(403, `Chave não gravável por esta rota: ${recusadas.join(', ')}.${dica}`, {
      fields: recusadas,
    });
  }

  let supabase;
  try {
    supabase = obterSupabase();
  } catch (erro) {
    return falha(503, erro.message, { codigo: 'CONFIG_AUSENTE' });
  }

  const agora = new Date().toISOString();
  const gravadas = [];

  for (const item of itens) {
    const { error } = await supabase
      .from(TABELA)
      .update({ value: item.value, updated_at: agora })
      .eq('key', item.key);

    if (error) {
      console.error('[configuracoes] escrita falhou:', error.message);
      return falha(500, `Não foi possível gravar a configuração ${item.key}.`);
    }
    gravadas.push(item.key);
  }

  return ok(200, { updated: gravadas, updated_at: agora });
}

// ---------------------------------------------------------------------------
// PUT /api/settings/exchange-rate  { rate: 5.42 }
// ---------------------------------------------------------------------------

async function gravarTaxa(entrada) {
  const identidade = await exigirAdmin(lerTokenBearer(entrada?.authorization));
  if (identidade.status !== 200) {
    return falha(identidade.status, identidade.error, { codigo: identidade.codigo });
  }

  const bruto = entrada?.body?.rate ?? entrada?.body?.taxa;
  const taxa = typeof bruto === 'number' ? bruto : Number(String(bruto ?? '').replace(',', '.'));

  // Mesma faixa que a UI já aplicava. Repetida no servidor porque validação de
  // cliente é conveniência, não controle: quem chama a API não passa pela UI.
  if (!Number.isFinite(taxa) || taxa <= 0 || taxa >= 100) {
    return falha(400, 'Informe `rate` numérico maior que 0 e menor que 100 (ex.: 5.42).');
  }

  let supabase;
  try {
    supabase = obterSupabase();
  } catch (erro) {
    return falha(503, erro.message, { codigo: 'CONFIG_AUSENTE' });
  }

  // Grava a taxa e recalcula o mês inteiro numa transação só (upstream webgov6).
  const { error: erroRpc } = await supabase.rpc(RPC_TAXA, { p_rate: taxa });
  if (erroRpc) {
    console.error('[configuracoes] RPC da taxa falhou:', erroRpc.message);
    return falha(500, 'Não foi possível atualizar a cotação.');
  }

  const agora = new Date().toISOString();
  const { error: erroCarimbo } = await supabase
    .from(TABELA)
    .update({ value: agora, updated_at: agora })
    .eq('key', CHAVE_ATUALIZACAO_MOEDA);

  if (erroCarimbo) {
    // A taxa JÁ mudou e o mês JÁ foi recalculado — o carimbo é metadado. Falhar
    // a requisição inteira aqui faria a UI mostrar erro sobre uma operação que
    // deu certo, e o operador tentaria de novo sem necessidade.
    console.error('[configuracoes] carimbo de atualização falhou:', erroCarimbo.message);
  }

  return ok(200, {
    rate: taxa,
    last_currency_update: erroCarimbo ? null : agora,
    recalculated: true,
  });
}

// ---------------------------------------------------------------------------
// Auxiliares
// ---------------------------------------------------------------------------

function extrairChaves(bruto) {
  if (Array.isArray(bruto)) return bruto.map((k) => String(k).trim()).filter(Boolean);
  if (typeof bruto === 'string') {
    return bruto.split(',').map((k) => k.trim()).filter(Boolean);
  }
  return [];
}

function normalizarItens(corpo) {
  if (!corpo || typeof corpo !== 'object') return [];

  const bruto = Array.isArray(corpo.settings)
    ? corpo.settings
    : corpo.key !== undefined
      ? [corpo]
      : [];

  return bruto
    .filter((i) => i && typeof i === 'object' && typeof i.key === 'string')
    .map((i) => ({ key: i.key.trim(), value: i.value === undefined ? null : String(i.value) }))
    .filter((i) => i.key !== '');
}
