/**
 * capiCrypto — cifra/decifra do access token da Meta CAPI.
 *
 * Contrato (docs/superpowers/specs/2026-07-30-meta-capi-wizard-contrato.md §4):
 *   - AES-GCM 256 via WebCrypto (`globalThis.crypto.subtle`).
 *   - Chave: env CAPI_MASTER_KEY = 32 bytes em base64 (`openssl rand -base64 32`).
 *   - IV: 12 bytes aleatórios POR GRAVAÇÃO, guardado em base64 junto do cipher.
 *   - Saída: ciphertext em base64 (o WebCrypto já concatena o auth tag no fim).
 *
 * POR QUE ESTE ARQUIVO EXISTE (e não um `crypto.createCipheriv` do Node):
 *   o MESMO formato precisa ser lido pela Edge Function `capi-router`, que roda
 *   em Deno. WebCrypto existe nos dois runtimes; o módulo `node:crypto` não.
 *   Por isso: zero import de Node aqui, nada além de APIs globais. Este arquivo
 *   é copiável para o Deno sem alterar uma linha.
 *
 * REGRA DE OURO: nada aqui pode ir para log. Nem o token, nem a master key,
 * nem pedaços delas. As mensagens de erro falam de TAMANHO e FORMATO, jamais
 * de conteúdo.
 */

/** AES-256 exige exatamente 32 bytes de chave. */
const MASTER_KEY_BYTES = 32;

/** GCM: 12 bytes é o tamanho de nonce recomendado (NIST SP 800-38D). */
const IV_BYTES = 12;

const ALGORITHM = 'AES-GCM';

/**
 * Acesso ao WebCrypto. Node 18+ e Deno expõem em `globalThis.crypto`.
 * Falhar cedo e com mensagem clara é melhor do que um TypeError obscuro
 * de "cannot read property subtle of undefined" no meio de um request.
 */
function getCrypto() {
  const c = globalThis.crypto;
  if (!c || !c.subtle || typeof c.getRandomValues !== 'function') {
    throw new Error(
      'WebCrypto indisponível neste runtime. É preciso Node 18+ (ou Deno) para a cifra AES-GCM do token da Meta CAPI.'
    );
  }
  return c;
}

// ---------------------------------------------------------------------------
// base64 <-> bytes
// Buffer (Node) quando existir, atob/btoa (padrão web, também em Deno) senão.
// Mantém o arquivo portátil sem `import` nenhum.
// ---------------------------------------------------------------------------

function bytesToB64(bytes) {
  if (typeof globalThis.Buffer !== 'undefined') {
    return globalThis.Buffer.from(bytes).toString('base64');
  }
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return globalThis.btoa(binary);
}

function b64ToBytes(b64, label) {
  if (typeof b64 !== 'string' || b64.length === 0) {
    throw new Error(`${label} ausente ou vazio (esperado uma string base64).`);
  }

  let bytes;
  try {
    if (typeof globalThis.Buffer !== 'undefined') {
      bytes = new Uint8Array(globalThis.Buffer.from(b64, 'base64'));
    } else {
      const binary = globalThis.atob(b64);
      bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
      }
    }
  } catch {
    throw new Error(`${label} não é base64 válido.`);
  }

  // `Buffer.from(x, 'base64')` não lança em lixo — ele ignora os caracteres
  // inválidos e devolve menos bytes. Então validamos o resultado, não a entrada.
  if (bytes.length === 0) {
    throw new Error(`${label} não é base64 válido (decodificou para 0 bytes).`);
  }
  return bytes;
}

// ---------------------------------------------------------------------------
// Chave
// ---------------------------------------------------------------------------

/**
 * Valida e importa a master key.
 * @param {string} masterKeyB64 chave em base64 (32 bytes)
 * @param {string[]} usages ['encrypt'] ou ['decrypt']
 */
async function importMasterKey(masterKeyB64, usages) {
  if (typeof masterKeyB64 !== 'string' || masterKeyB64.trim() === '') {
    throw new Error(
      'CAPI_MASTER_KEY não configurada. Gere uma com `openssl rand -base64 32` e coloque no ambiente do backend E nos secrets da Edge Function.'
    );
  }

  const raw = b64ToBytes(masterKeyB64.trim(), 'CAPI_MASTER_KEY');

  if (raw.length !== MASTER_KEY_BYTES) {
    // Mensagem fala do TAMANHO, nunca do conteúdo.
    throw new Error(
      `CAPI_MASTER_KEY inválida: AES-256 exige ${MASTER_KEY_BYTES} bytes, a chave fornecida tem ${raw.length}. Gere uma nova com \`openssl rand -base64 32\`.`
    );
  }

  return getCrypto().subtle.importKey('raw', raw, ALGORITHM, false, usages);
}

/**
 * Gera uma master key nova (32 bytes aleatórios em base64).
 * Usada pelo wizard para SUGERIR a chave ao operador — o valor gerado nunca
 * é persistido nem logado aqui; quem decide o que fazer com ele é a UI.
 * @returns {string} base64 de 32 bytes
 */
export function generateMasterKey() {
  const bytes = new Uint8Array(MASTER_KEY_BYTES);
  getCrypto().getRandomValues(bytes);
  return bytesToB64(bytes);
}

// ---------------------------------------------------------------------------
// Cifra / decifra
// ---------------------------------------------------------------------------

/**
 * Cifra o access token.
 * @param {string} plain token em texto puro
 * @param {string} masterKeyB64 CAPI_MASTER_KEY (base64, 32 bytes)
 * @returns {Promise<{cipher: string, iv: string}>} ambos em base64
 */
export async function encryptToken(plain, masterKeyB64) {
  if (typeof plain !== 'string' || plain.length === 0) {
    throw new Error('Token vazio: não há o que cifrar.');
  }

  const key = await importMasterKey(masterKeyB64, ['encrypt']);

  // IV novo a cada gravação. Reusar IV com a mesma chave em GCM permite
  // recuperar o plaintext — é o erro clássico do modo.
  const iv = new Uint8Array(IV_BYTES);
  getCrypto().getRandomValues(iv);

  const encoded = new TextEncoder().encode(plain);
  const cipherBuffer = await getCrypto().subtle.encrypt(
    { name: ALGORITHM, iv },
    key,
    encoded
  );

  return {
    cipher: bytesToB64(new Uint8Array(cipherBuffer)),
    iv: bytesToB64(iv),
  };
}

/**
 * Decifra o access token.
 * @param {string} cipher ciphertext em base64 (com o auth tag no fim)
 * @param {string} iv IV em base64 (12 bytes)
 * @param {string} masterKeyB64 CAPI_MASTER_KEY (base64, 32 bytes)
 * @returns {Promise<string>} token em texto puro
 */
export async function decryptToken(cipher, iv, masterKeyB64) {
  const key = await importMasterKey(masterKeyB64, ['decrypt']);
  const cipherBytes = b64ToBytes(cipher, 'capi_token_cipher');
  const ivBytes = b64ToBytes(iv, 'capi_token_iv');

  if (ivBytes.length !== IV_BYTES) {
    throw new Error(
      `capi_token_iv inválido: AES-GCM espera ${IV_BYTES} bytes, recebeu ${ivBytes.length}.`
    );
  }

  let plainBuffer;
  try {
    plainBuffer = await getCrypto().subtle.decrypt(
      { name: ALGORITHM, iv: ivBytes },
      key,
      cipherBytes
    );
  } catch {
    // O WebCrypto joga um OperationError genérico quando o auth tag não bate.
    // Traduzimos para algo acionável — sem vazar nada do conteúdo.
    throw new Error(
      'Falha ao decifrar o token da Meta CAPI: a CAPI_MASTER_KEY não corresponde à que cifrou este registro, ou o dado está corrompido. Se a chave foi rotacionada, recadastre o token do site.'
    );
  }

  return new TextDecoder().decode(plainBuffer);
}

export const CAPI_CRYPTO_CONSTANTS = Object.freeze({
  MASTER_KEY_BYTES,
  IV_BYTES,
  ALGORITHM,
});
