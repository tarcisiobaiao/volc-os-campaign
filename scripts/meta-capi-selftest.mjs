#!/usr/bin/env node
/**
 * Autoteste da API de Conversões (Meta) — prova a cadeia sem tocar no pixel real.
 *
 * O que ele responde, em ordem:
 *   1. a tabela meta_capi_sites existe?
 *   2. a Edge Function capi-router está publicada e sem Verify JWT?
 *   3. a CAPI_MASTER_KEY do servidor é A MESMA do secret da function?
 *
 * O passo 3 é o que não dá para verificar "no olho": ele cifra um token aqui,
 * grava numa linha temporária e pede para a function decifrar. Como o pixel e o
 * token são falsos, o sucesso aparece como um erro da META (token inválido) —
 * e é justamente esse erro que prova que a decifragem funcionou. A linha é
 * removida no fim, sempre.
 *
 * Uso:  node scripts/meta-capi-selftest.mjs
 */
import { readFileSync } from 'node:fs';
import { encryptToken } from '../api/_lib/capiCrypto.js';

const ENV_FILE = new URL('../.env.server', import.meta.url);
const SELFTEST_KEY = '__selftest__';

// Por padrão testa a function direto. Com `--endpoint=<url>` o POST vai pelo
// caminho REAL do evento (Worker -> function), que é o que o navegador faz.
const ENDPOINT_ARG = (process.argv.find((a) => a.startsWith('--endpoint=')) || '').split('=')[1];

function loadEnv() {
  const out = {};
  let raw = '';
  try {
    raw = readFileSync(ENV_FILE, 'utf8');
  } catch {
    return out;
  }
  for (const line of raw.split('\n')) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (m) out[m[1]] = m[2].trim().replace(/^["']|["']$/g, '');
  }
  return out;
}

const env = { ...loadEnv(), ...process.env };
const SUPABASE_URL = env.SUPABASE_URL;
const SERVICE_KEY = env.SUPABASE_SERVICE_ROLE_KEY;
const MASTER_KEY = env.CAPI_MASTER_KEY;
const FUNCTION_URL = `${(SUPABASE_URL || '').replace(/\/$/, '')}/functions/v1/capi-router`;

const pass = (m) => console.log(`  \x1b[32m✔\x1b[0m ${m}`);
const fail = (m) => console.log(`  \x1b[31m✖\x1b[0m ${m}`);
const info = (m) => console.log(`  \x1b[2m${m}\x1b[0m`);

const rest = (path, init = {}) =>
  fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: SERVICE_KEY,
      Authorization: `Bearer ${SERVICE_KEY}`,
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  });

async function cleanup() {
  try {
    await rest(`meta_capi_sites?site_key=eq.${SELFTEST_KEY}`, { method: 'DELETE' });
  } catch {
    /* melhor esforço */
  }
}

async function main() {
  let failures = 0;

  console.log('\nAutoteste da API de Conversões\n');

  // ---- pré-requisitos ------------------------------------------------------
  console.log('Configuração');
  if (!SUPABASE_URL || !SERVICE_KEY) {
    fail('SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ausentes no .env.server');
    process.exit(1);
  }
  pass('Supabase configurado');

  if (!MASTER_KEY) {
    fail('CAPI_MASTER_KEY ausente no .env.server');
    process.exit(1);
  }
  const keyBytes = Buffer.from(MASTER_KEY, 'base64').length;
  if (keyBytes !== 32) {
    fail(`CAPI_MASTER_KEY decodifica para ${keyBytes} bytes; AES-256 exige 32`);
    process.exit(1);
  }
  pass('CAPI_MASTER_KEY presente e com 32 bytes');

  // ---- 1. tabela -----------------------------------------------------------
  console.log('\n1. Tabela meta_capi_sites');
  const tableResp = await rest('meta_capi_sites?select=id&limit=1');
  if (tableResp.ok) {
    pass('tabela existe e responde');
  } else {
    failures++;
    fail(`tabela indisponível (HTTP ${tableResp.status})`);
    info((await tableResp.text()).slice(0, 200));
    info('→ rode src/sql/v7_13_meta_capi_sites.sql no SQL Editor do Supabase');
    process.exit(1);
  }

  // ---- 2. function ---------------------------------------------------------
  console.log('\n2. Edge Function capi-router');
  const ping = await fetch(FUNCTION_URL, { method: 'GET' });
  if (ping.ok) {
    pass(`publicada e respondendo (HTTP ${ping.status})`);
  } else {
    failures++;
    fail(`respondeu HTTP ${ping.status}`);
    if (ping.status === 401) {
      info('→ 401 = Verify JWT ligado. Desligue: o Worker chama sem Authorization.');
    }
    process.exit(1);
  }

  // ---- 3. a chave do servidor é a mesma do secret da function? -------------
  console.log('\n3. Chave mestra (servidor ↔ function)');
  await cleanup();

  const { cipher, iv } = await encryptToken('TOKEN_FALSO_DO_AUTOTESTE', MASTER_KEY);
  const insert = await rest('meta_capi_sites', {
    method: 'POST',
    headers: { Prefer: 'return=representation' },
    body: JSON.stringify([
      {
        site_key: SELFTEST_KEY,
        site_name: 'Autoteste (temporário)',
        domain: 'selftest.invalid',
        cookie_domain: '.selftest.invalid',
        endpoint_url: 'https://selftest.invalid/capi',
        pixel_id: '000000000000000',
        capi_token_cipher: cipher,
        capi_token_iv: iv,
        events: { interstitial: true, rewarded: false },
      },
    ]),
  });

  if (!insert.ok) {
    failures++;
    fail(`não consegui gravar a linha temporária (HTTP ${insert.status})`);
    info((await insert.text()).slice(0, 300));
    process.exit(1);
  }
  info('linha temporária criada com um token falso cifrado aqui');

  const postUrl = ENDPOINT_ARG || FUNCTION_URL;
  if (ENDPOINT_ARG) info(`enviando pelo endpoint real: ${ENDPOINT_ARG}`);
  const resp = await fetch(postUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: JSON.stringify({
      site_key: SELFTEST_KEY,
      event_name: 'ViewContent',
      event_id: `selftest_${Date.now()}`,
      event_source_url: 'https://selftest.invalid/',
      slot_id: 'google_vignette_interstitial',
    }),
  });

  const bodyText = await resp.text();
  let parsed = {};
  try {
    parsed = JSON.parse(bodyText);
  } catch {
    /* corpo não-JSON */
  }

  await cleanup();
  info('linha temporária removida');

  const err = String(parsed.error || '');

  if (err === 'master_key_missing') {
    failures++;
    fail('a function não tem o secret CAPI_MASTER_KEY');
    info('→ Supabase → Project Settings → Edge Functions → Secrets');
  } else if (err === 'master_key_invalid') {
    failures++;
    fail('o secret CAPI_MASTER_KEY da function não é base64 de 32 bytes');
  } else if (err === 'token_decrypt_failed') {
    failures++;
    fail('a chave da function é DIFERENTE da chave do servidor');
    info('→ cole exatamente o mesmo valor nos dois lugares (sem espaços/quebras)');
  } else if (err === 'site_not_found') {
    failures++;
    fail('a function não enxergou a linha — confira se ela lê o mesmo projeto');
  } else if (resp.status === 204) {
    // Só aconteceria se a Meta aceitasse um token falso: não deveria ocorrer.
    fail('a Meta aceitou um token FALSO — verifique qual pixel/token está em uso');
    failures++;
  } else if (parsed.meta_status || /OAuth|access token|Unsupported|Invalid/i.test(bodyText)) {
    pass('a function decifrou o token com a chave do servidor');
    pass('a chamada chegou até a Meta (que recusou o token falso, como esperado)');
    info(`resposta da Meta: HTTP ${parsed.meta_status || resp.status}`);
  } else {
    failures++;
    fail(`resposta inesperada (HTTP ${resp.status})`);
    info(bodyText.slice(0, 400));
  }

  console.log(
    failures === 0
      ? '\n\x1b[32mTudo certo.\x1b[0m Falta só replicar a CAPI_MASTER_KEY nas variáveis da Vercel.\n'
      : `\n\x1b[31m${failures} problema(s).\x1b[0m Veja as dicas acima.\n`,
  );
  process.exit(failures === 0 ? 0 : 1);
}

main().catch(async (err) => {
  await cleanup();
  console.error('\nerro inesperado:', err?.message || err);
  process.exit(1);
});
