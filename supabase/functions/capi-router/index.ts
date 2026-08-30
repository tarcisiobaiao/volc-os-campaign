/**
 * capi-router — Edge Function multi-tenant do Meta Conversions API.
 *
 * Substitui o modelo antigo (1 function + 2 secrets POR SITE) por uma única function
 * que resolve o site em tempo de request lendo a tabela `meta_capi_sites`.
 * Site novo = 1 linha na tabela (nenhum deploy novo).
 *
 * Cadeia: GTM -> Worker Cloudflare -> ESTA function -> Graph API da Meta.
 *
 * O comportamento de envio é cópia fiel do baseline de produção (`capi-apps-technews`):
 * mesmos eventos aceitos, mesmo user_data/custom_data, Graph API v21.0, test_event_code
 * repassado, erro da Meta devolvido no corpo, 204 no sucesso.
 * A ÚNICA diferença é de onde vêm `pixel_id` e o access token: antes, secrets; agora, banco.
 *
 * Secrets necessários: apenas CAPI_MASTER_KEY.
 * SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY são injetadas pelo Supabase por padrão.
 */

// ---------------------------------------------------------------------------
// CORS — idêntico ao do Worker/baseline.
// Obrigatório: o wizard usa o GET desta function como teste de vida direto do
// browser; sem CORS aberto o check nunca ficaria verde.
// ---------------------------------------------------------------------------
const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "content-type, authorization, x-client-info, apikey",
};

// v21.0 é a versão validada em produção. NÃO subir de versão sem re-testar a cadeia
// inteira no Gerenciador de Eventos — foi o que o baseline fixou.
const GRAPH_API_VERSION = "v21.0";

// Mesmo Set do baseline. Ausente = ViewContent; qualquer outro nome = 400.
const ALLOWED_EVENT_NAMES = new Set(["ViewContent", "RewardedAdView"]);

const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"] as const;

// Colunas lidas do banco. `test_event_code` da tabela é DE PROPÓSITO ignorado aqui:
// evento enviado com test_event_code não entra no relatório normal da Meta, então
// uma linha com o campo preenchido por engano derrubaria silenciosamente o tracking
// de produção do site inteiro. O test_event_code só vale quando vem no body (wizard).
const SITE_COLUMNS = "site_key,domain,pixel_id,capi_token_cipher,capi_token_iv,is_active";

// Sufixos públicos com 3 rótulos (mesma lista do contrato, seção "Regra do cookie domain").
// Serve para achar o apex de um host e cobrir subdomínios no fallback por domínio.
const MULTI_LABEL_SUFFIXES = new Set([
  "com.br", "net.br", "org.br", "gov.br", "edu.br", "co.uk", "com.ar", "com.mx",
  "com.co", "com.pe", "com.uy", "com.py", "com.ve", "com.ec", "com.gt", "com.do",
  "co.jp", "com.au",
]);

// ---------------------------------------------------------------------------
// Acesso ao banco: fetch direto no PostgREST, sem @supabase/supabase-js.
//
// Por quê: esta function é chamada em TODO view de anúncio. Importar o SDK via
// esm.sh acrescenta um download remoto no cold start e uma dependência de terceiro
// no caminho crítico, para fazer exatamente um SELECT com filtro. Com service role
// o PostgREST é uma chamada HTTP de duas linhas — menos dependência, cold start menor
// e nada quebra se o esm.sh ficar fora do ar.
// ---------------------------------------------------------------------------
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";

interface SiteRow {
  site_key: string;
  domain: string;
  pixel_id: string;
  capi_token_cipher: string;
  capi_token_iv: string;
  is_active: boolean;
}

// ---------------------------------------------------------------------------
// Cache em memória do registro do site.
//
// Por quê: 1 request = 1 view de anúncio. Sem cache, cada impressão vira também um
// SELECT no Postgres — em pico de tráfego isso é o gargalo (e custo) mais bobo possível.
// O registro muda raríssimo, então 60s de TTL derruba o tráfego ao banco em ~99% sem
// atrasar nada perceptível: trocar token/pixel ou desativar um site leva no máximo 60s
// para valer em todas as instâncias.
//
// Só cacheamos ACERTO. Negativo (site_not_found) não entra no cache de propósito:
// o wizard cria o site e dispara o teste da cadeia em seguida, e um negative cache
// faria esse primeiro teste falhar sem motivo.
//
// O cache é por isolate; um cache miss (isolate novo, TTL vencido) apenas custa um
// SELECT — nunca muda o resultado.
// ---------------------------------------------------------------------------
const SITE_CACHE_TTL_MS = 60_000;
const SITE_CACHE_MAX_ENTRIES = 500;
const siteCache = new Map<string, { row: SiteRow; expiresAt: number }>();

function cacheRead(key: string): SiteRow | null {
  const hit = siteCache.get(key);
  if (!hit) return null;
  if (hit.expiresAt <= Date.now()) {
    siteCache.delete(key);
    return null;
  }
  return hit.row;
}

function cacheWrite(key: string, row: SiteRow): void {
  // Poda burra e barata: o número de chaves é limitado pela quantidade de sites reais
  // (não cacheamos negativos), então isto praticamente nunca dispara.
  if (siteCache.size >= SITE_CACHE_MAX_ENTRIES) siteCache.clear();
  siteCache.set(key, { row, expiresAt: Date.now() + SITE_CACHE_TTL_MS });
}

// ---------------------------------------------------------------------------
// Helpers gerais
// ---------------------------------------------------------------------------
function str(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Remove o access_token de qualquer texto antes de sair no corpo da resposta ou no log.
 * Necessário porque o token viaja na query string da Graph API (formato do baseline) e
 * mensagens de erro de rede do fetch costumam embutir a URL inteira.
 */
function redact(text: string): string {
  return text
    .replace(/access_token=[^&\s"'<>]+/gi, "access_token=***")
    .replace(/"access_token"\s*:\s*"[^"]*"/gi, '"access_token":"***"');
}

function errMessage(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  return redact(raw).slice(0, 400);
}

function jsonResponse(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

/** Erro de configuração da própria function (secret ausente/ruim). Vira 500 explicativo. */
class ConfigError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

// ---------------------------------------------------------------------------
// Resolução do site
// ---------------------------------------------------------------------------
function hostFromUrl(raw: unknown): string {
  const value = str(raw);
  if (!value) return "";
  try {
    return new URL(value).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function apexOf(host: string): string {
  const parts = host.split(".").filter(Boolean);
  if (parts.length <= 2) return host;
  const lastTwo = parts.slice(-2).join(".");
  const labels = MULTI_LABEL_SUFFIXES.has(lastTwo) ? 3 : 2;
  if (parts.length <= labels) return host;
  return parts.slice(-labels).join(".");
}

async function querySites(query: string): Promise<SiteRow[]> {
  if (!SUPABASE_URL || !SERVICE_ROLE_KEY) {
    throw new ConfigError(
      "supabase_env_missing",
      "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY não disponíveis no ambiente da function.",
    );
  }
  const res = await fetch(`${SUPABASE_URL}/rest/v1/meta_capi_sites?${query}`, {
    method: "GET",
    headers: {
      apikey: SERVICE_ROLE_KEY,
      // service_role ignora RLS — a tabela tem RLS ligada e ZERO policies de propósito,
      // então ninguém alcança o token cifrado pelo PostgREST público.
      Authorization: `Bearer ${SERVICE_ROLE_KEY}`,
      Accept: "application/json",
    },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`postgrest_${res.status}: ${detail.slice(0, 300)}`);
  }
  return (await res.json()) as SiteRow[];
}

interface ResolveResult {
  row: SiteRow | null;
  siteKey: string;
  host: string;
}

/**
 * 1) `site_key` do body (caminho normal — as tags geradas pelo wizard sempre mandam).
 * 2) Sem site_key: host de `event_source_url` casado com `domain`; se não bater exato,
 *    tenta o apex do host (cobre www. e subdomínios não cadastrados).
 * Devolve row=null quando não encontra (o handler transforma em 404).
 */
async function resolveSite(body: Record<string, unknown>): Promise<ResolveResult> {
  const siteKey = str(body.site_key).toLowerCase();
  const host = hostFromUrl(body.event_source_url);

  if (siteKey) {
    const cacheKey = `key:${siteKey}`;
    const cached = cacheRead(cacheKey);
    if (cached) return { row: cached, siteKey, host };

    // Valida antes de interpolar no filtro do PostgREST (o site_key derivado é
    // [a-z0-9-]; aceitamos _ e . por tolerância, e nada além disso).
    if (!/^[a-z0-9._-]{1,120}$/.test(siteKey)) return { row: null, siteKey, host };

    const rows = await querySites(
      `site_key=eq.${encodeURIComponent(siteKey)}&select=${SITE_COLUMNS}&limit=1`,
    );
    const row = rows[0] ?? null;
    if (row) cacheWrite(cacheKey, row);
    return { row, siteKey, host };
  }

  if (!host) return { row: null, siteKey, host };

  const cacheKey = `host:${host}`;
  const cached = cacheRead(cacheKey);
  if (cached) return { row: cached, siteKey, host };

  if (!/^[a-z0-9.-]{1,253}$/.test(host)) return { row: null, siteKey, host };

  const apex = apexOf(host);
  const candidates = apex && apex !== host ? [host, apex] : [host];

  // Host e apex numa consulta só: menos uma ida ao banco no caminho quente.
  const filter = `or=(${candidates.map((c) => `domain.eq.${c}`).join(",")})`;
  const rows = await querySites(`${filter}&select=${SITE_COLUMNS}&limit=5`);

  // Match exato do host tem precedência sobre o apex.
  const row = rows.find((r) => str(r.domain).toLowerCase() === host) ??
    rows.find((r) => str(r.domain).toLowerCase() === apex) ??
    null;

  if (row) {
    cacheWrite(cacheKey, row);
    // Indexa também por site_key: se o mesmo site depois mandar site_key, já é hit.
    if (row.site_key) cacheWrite(`key:${row.site_key.toLowerCase()}`, row);
  }
  return { row, siteKey, host };
}

// ---------------------------------------------------------------------------
// Cripto — AES-GCM 256, exatamente o formato da seção 4 do contrato.
// Precisa ser compatível byte a byte com api/_lib/capiCrypto.js (lado Node):
//   - chave: CAPI_MASTER_KEY em base64, 32 bytes crus;
//   - IV: 12 bytes, base64, vindo de capi_token_iv;
//   - ciphertext: base64, JÁ COM o auth tag de 128 bits no fim (é o que o WebCrypto
//     devolve por padrão nos dois runtimes — por isso não passamos tagLength).
// ---------------------------------------------------------------------------
// Sem anotação de retorno de propósito: deixando o TS inferir, o tipo sai como
// Uint8Array<ArrayBuffer> (TS >= 5.7) e casa com BufferSource do WebCrypto; anotar
// `: Uint8Array` degradaria para ArrayBufferLike e o type-check falharia.
function b64ToBytes(b64: string) {
  const bin = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function decodeMasterKeyBytes(raw: string) {
  try {
    return b64ToBytes(raw);
  } catch {
    throw new ConfigError("master_key_invalid", "CAPI_MASTER_KEY não é base64 válido.");
  }
}

let masterKeyPromise: Promise<CryptoKey> | null = null;

function getMasterKey(): Promise<CryptoKey> {
  if (!masterKeyPromise) {
    masterKeyPromise = (async () => {
      const raw = str(Deno.env.get("CAPI_MASTER_KEY"));
      if (!raw) {
        throw new ConfigError(
          "master_key_missing",
          "Secret CAPI_MASTER_KEY não configurado na Edge Function.",
        );
      }
      const bytes = decodeMasterKeyBytes(raw);
      if (bytes.length !== 32) {
        throw new ConfigError(
          "master_key_invalid",
          `CAPI_MASTER_KEY precisa ter 32 bytes (AES-256); veio com ${bytes.length}.`,
        );
      }
      // extractable=false: a chave não sai da WebCrypto nem por acidente.
      return await crypto.subtle.importKey("raw", bytes, { name: "AES-GCM" }, false, ["decrypt"]);
    })();
    // Não memoiza o erro para sempre: se o secret for corrigido e a function reusar o
    // mesmo isolate, a próxima tentativa lê o env de novo.
    masterKeyPromise.catch(() => {
      masterKeyPromise = null;
    });
  }
  return masterKeyPromise;
}

async function decryptToken(cipherB64: string, ivB64: string): Promise<string> {
  const key = await getMasterKey();
  const iv = b64ToBytes(ivB64);
  const cipher = b64ToBytes(cipherB64);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, cipher);
  return new TextDecoder().decode(plain);
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------
Deno.serve(async (req: Request): Promise<Response> => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  // Teste de vida do wizard: precisa continuar 200 "ok".
  if (req.method === "GET") {
    return new Response("ok", {
      status: 200,
      headers: { ...CORS_HEADERS, "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  if (req.method !== "POST") {
    return jsonResponse(405, { ok: false, error: "method_not_allowed" });
  }

  // O sendBeacon das tags manda Blob com type "text/plain"; o fetch de fallback também.
  // Por isso NUNCA usar req.json(): lê como texto e faz o parse na mão, igual ao baseline.
  let body: Record<string, unknown>;
  try {
    const rawBody = await req.text();
    const parsed = JSON.parse(rawBody || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return jsonResponse(400, { ok: false, error: "invalid_body" });
    }
    body = parsed as Record<string, unknown>;
  } catch {
    return jsonResponse(400, { ok: false, error: "invalid_json" });
  }

  // Valida o nome do evento ANTES de ir ao banco: payload inválido não merece um SELECT.
  const eventName = str(body.event_name) || "ViewContent";
  if (!ALLOWED_EVENT_NAMES.has(eventName)) {
    return jsonResponse(400, { ok: false, error: "unsupported_event_name", event_name: eventName });
  }
  const isRewarded = eventName === "RewardedAdView";

  // --- resolve o site --------------------------------------------------------
  let resolved: ResolveResult;
  try {
    resolved = await resolveSite(body);
  } catch (err) {
    console.error("[capi-router] falha ao resolver site:", errMessage(err));
    const code = err instanceof ConfigError ? err.code : "site_lookup_failed";
    return jsonResponse(500, { ok: false, error: code, detail: errMessage(err) });
  }

  if (!resolved.row) {
    return jsonResponse(404, {
      ok: false,
      error: "site_not_found",
      site_key: resolved.siteKey || null,
      host: resolved.host || null,
    });
  }

  const site = resolved.row;

  if (!site.is_active) {
    return jsonResponse(403, { ok: false, error: "site_inactive", site_key: site.site_key });
  }

  // --- decifra o token -------------------------------------------------------
  let accessToken = "";
  try {
    accessToken = await decryptToken(site.capi_token_cipher, site.capi_token_iv);
  } catch (err) {
    // Nunca logar nem devolver o token ou a master key — só o código do erro.
    const code = err instanceof ConfigError ? err.code : "token_decrypt_failed";
    const detail = err instanceof ConfigError
      ? err.message
      : "Não foi possível decifrar capi_token_cipher. Confira se CAPI_MASTER_KEY é a mesma chave usada ao salvar o site.";
    console.error(`[capi-router] ${code} site_key=${site.site_key}`);
    return jsonResponse(500, { ok: false, error: code, detail, site_key: site.site_key });
  }
  if (!accessToken) {
    console.error(`[capi-router] token_empty site_key=${site.site_key}`);
    return jsonResponse(500, { ok: false, error: "token_empty", site_key: site.site_key });
  }

  // --- monta o evento (idêntico ao baseline) ---------------------------------
  // O Worker repassa o IP/UA reais nesses headers; os fallbacks cobrem chamada direta.
  const clientIp = str(req.headers.get("x-client-ip")) ||
    str(req.headers.get("cf-connecting-ip")) ||
    str((req.headers.get("x-forwarded-for") ?? "").split(",")[0]);
  const clientUa = str(req.headers.get("x-client-ua")) || str(req.headers.get("user-agent"));

  const eventId = str(body.event_id) || crypto.randomUUID();
  const slotId = str(body.slot_id) ||
    (isRewarded ? "google_rewarded" : "google_vignette_interstitial");
  const contentCategory = isRewarded ? "rewarded" : "interstitial";
  const eventType = str(body.event_type);
  // Fiel à function de produção: `ad_format` recebe a MESMA string de
  // `content_category` ("interstitial" | "rewarded"). Não é o nome do slot —
  // trocar isso mudaria o valor que a Meta já recebe hoje e quebraria qualquer
  // segmentação montada em cima do campo.
  const adFormat = contentCategory;

  const userData: Record<string, unknown> = {};
  if (clientIp) userData.client_ip_address = clientIp;
  if (clientUa) userData.client_user_agent = clientUa;
  const fbc = str(body.fbc);
  if (fbc) userData.fbc = fbc;
  const fbp = str(body.fbp);
  if (fbp) userData.fbp = fbp;
  const externalId = str(body.external_id);
  // Sem hash de propósito: a Meta normaliza e hasheia o external_id na recepção.
  if (externalId) userData.external_id = [externalId];

  const customData: Record<string, unknown> = {
    content_name: slotId,
    content_category: contentCategory,
    content_type: "ad_view",
    status: "viewable",
    ad_format: adFormat,
  };
  if (eventType) customData.event_type = eventType;
  for (const key of UTM_KEYS) {
    const value = str(body[key]);
    if (value) customData[key] = value;
  }

  const event: Record<string, unknown> = {
    event_name: eventName,
    event_time: Math.floor(Date.now() / 1000), // segundos, como a Meta exige
    event_id: eventId, // deduplica com o Pixel do browser
    action_source: "website",
    user_data: userData,
    custom_data: customData,
  };
  const eventSourceUrl = str(body.event_source_url);
  if (eventSourceUrl) event.event_source_url = eventSourceUrl;
  const referrerUrl = str(body.referrer_url);
  if (referrerUrl) event.referrer_url = referrerUrl;

  const metaPayload: Record<string, unknown> = { data: [event] };
  // Só repassa o test_event_code que veio no body (wizard). Ver comentário em SITE_COLUMNS.
  const testEventCode = str(body.test_event_code);
  if (testEventCode) metaPayload.test_event_code = testEventCode;

  // --- envia para a Meta -----------------------------------------------------
  const endpoint =
    `https://graph.facebook.com/${GRAPH_API_VERSION}/${encodeURIComponent(site.pixel_id)}/events` +
    `?access_token=${encodeURIComponent(accessToken)}`;

  let metaStatus = 0;
  let metaText = "";
  try {
    const metaRes = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(metaPayload),
    });
    metaStatus = metaRes.status;
    // Sempre drena o corpo (mesmo no sucesso) para não vazar conexão no isolate.
    metaText = await metaRes.text().catch(() => "");
    if (!metaRes.ok) {
      const errorText = redact(metaText) || `HTTP ${metaStatus}`;
      console.error(`[capi-router] meta_error site_key=${site.site_key} status=${metaStatus}`);
      // O wizard mostra este texto na íntegra ao operador.
      return jsonResponse(500, {
        ok: false,
        meta_status: metaStatus,
        error: errorText,
        event_name: eventName,
        event_id: eventId,
      });
    }
  } catch (err) {
    // Falha de rede até a Meta: errMessage já remove o access_token da URL na mensagem.
    console.error(`[capi-router] meta_unreachable site_key=${site.site_key}`);
    return jsonResponse(500, {
      ok: false,
      meta_status: metaStatus,
      error: errMessage(err),
      event_name: eventName,
      event_id: eventId,
    });
  }

  // Sucesso: 204 sem corpo. no-store porque a resposta é por-request e não pode
  // ser cacheada por nenhum intermediário (Worker/CDN).
  return new Response(null, {
    status: 204,
    headers: { ...CORS_HEADERS, "Cache-Control": "no-store" },
  });
});
