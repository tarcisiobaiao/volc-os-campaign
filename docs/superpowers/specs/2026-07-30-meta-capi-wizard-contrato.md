# Meta CAPI — contrato compartilhado (wizard multi-tenant)

Fonte da verdade para as peças implementadas em paralelo. **Não divergir daqui.**
Projeto Supabase: `txvvzpstquqmbhljudfn`.

## Arquitetura

```
GTM (3 tags por site)  ->  Worker Cloudflare (1 só, N rotas)  ->  Edge Function capi-router (1 só)  ->  Meta CAPI
                                                                          |
                                                              meta_capi_sites (pixel + token cifrado)
```

Antes: 1 Edge Function + 2 secrets **por site**. Agora: site novo = 1 linha na tabela.
As functions atuais (`bright-service`, `capi-apps-technews`) **continuam no ar, intocadas**.

## 1. Config do site (TypeScript)

```ts
// src/lib/metaCapi/types.ts
export interface MetaCapiSiteConfig {
  siteName: string;           // "Apps TechNews"
  siteKey: string;            // "apps-technews"  (chave multi-tenant; derivada, editável)
  domain: string;             // "apps.technewsbrasil.com.br"
  cookieDomain: string;       // ".technewsbrasil.com.br"  (APEX — ver regra abaixo)
  endpointSubdomain: string;  // "ev"
  endpointUrl: string;        // "https://ev.technewsbrasil.com.br/capi"
  pixelId: string;            // "940750053457681"
  events: { interstitial: boolean; rewarded: boolean };
  routerFunctionUrl: string;  // "https://txvvzpstquqmbhljudfn.supabase.co/functions/v1/capi-router"
}
```

### Regra do cookie domain (crítica)

O cookie precisa ser compartilhado entre subdomínios, então usa-se o **apex**, não o host:

| domain | cookieDomain correto |
| --- | --- |
| `apps.technewsbrasil.com.br` | `.technewsbrasil.com.br` |
| `technewsbrasil.com.br` | `.technewsbrasil.com.br` |
| `blog.loja.com.br` | `.loja.com.br` |
| `site.com` | `.site.com` |
| `a.b.site.co.uk` | `.site.co.uk` |

Sufixos compostos que precisam de 3 rótulos: `com.br, net.br, org.br, gov.br, edu.br, co.uk, com.ar, com.mx, com.co, com.pe, com.uy, com.py, com.ve, com.ec, com.gt, com.do, co.jp, com.au`.
Fora dessa lista, apex = últimos 2 rótulos.

### Derivações

- `siteKey` = domain sem o sufixo público, pontos → hífen, minúsculo, só `[a-z0-9-]`.
  `apps.technewsbrasil.com.br` → `apps-technewsbrasil` (o usuário pode editar para `apps-technews`).
- `endpointUrl` = `https://{endpointSubdomain}.{apex sem ponto inicial}/capi`
- `routerFunctionUrl` = `https://{ref}.supabase.co/functions/v1/capi-router`

## 2. Payload (tag → worker → function)

```jsonc
{
  "site_key": "apps-technews",          // NOVO: é o que torna multi-tenant
  "event_name": "ViewContent",          // ou "RewardedAdView"; ausente = ViewContent
  "event_type": "google_vignette",      // opcional
  "event_id": "...", "event_source_url": "...", "referrer_url": "...",
  "fbc": "", "fbp": "", "external_id": "",
  "slot_id": "google_vignette_interstitial",
  "utm_source": "", "utm_medium": "", "utm_campaign": "", "utm_content": "", "utm_term": "",
  "test_event_code": ""                 // só no teste do wizard
}
```

O Worker acrescenta os headers `x-client-ip` e `x-client-ua` (IP/UA reais do usuário).

## 3. Tabela `meta_capi_sites` (migração v7_13)

| coluna | tipo | nota |
| --- | --- | --- |
| `id` | bigserial PK | |
| `site_key` | text UNIQUE NOT NULL | casa com `site_key` do payload |
| `site_name` | text NOT NULL | |
| `domain` | text UNIQUE NOT NULL | usado no fallback por host |
| `cookie_domain` | text NOT NULL | |
| `endpoint_url` | text NOT NULL | |
| `pixel_id` | text NOT NULL | |
| `capi_token_cipher` | text NOT NULL | base64, AES-GCM |
| `capi_token_iv` | text NOT NULL | base64, 12 bytes |
| `events` | jsonb NOT NULL default `{"interstitial":true,"rewarded":true}` | |
| `is_active` | boolean NOT NULL default true | |
| `test_event_code` | text | |
| `last_check_at` | timestamptz | |
| `last_check_result` | jsonb | |
| `created_by` | uuid REFERENCES users(id) ON DELETE SET NULL | |
| `created_at` / `updated_at` | timestamptz default now() | trigger de updated_at |

**RLS ligada e ZERO policies** → anon/authenticated não leem nada pelo PostgREST.
Só `service_role` (que ignora RLS) enxerga: a Edge Function e o backend.

## 4. Criptografia do token (idêntica nos dois lados)

- Algoritmo: **AES-GCM 256**, WebCrypto (existe em Node 18+ e em Deno).
- Chave: env `CAPI_MASTER_KEY` = 32 bytes em **base64** (gerar com `openssl rand -base64 32`).
- IV: 12 bytes aleatórios por gravação, guardado em `capi_token_iv` (base64).
- Saída: ciphertext em base64 (inclui o auth tag, como o WebCrypto devolve).

```js
// cifra
const key = await crypto.subtle.importKey('raw', b64ToBytes(MASTER), 'AES-GCM', false, ['encrypt']);
const iv = crypto.getRandomValues(new Uint8Array(12));
const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(token));
// decifra: mesma chave, iv do banco, ['decrypt'] -> TextDecoder
```

Motivo: os endpoints `/api/supabase/*` do sistema aceitam qualquer tabela com service role **sem
autenticação**. Enquanto isso não for tratado, o token não pode existir em texto puro no banco.

## 5. Endpoint autenticado (dev Express + prod Vercel)

Lógica **compartilhada** em `api/_lib/metaCapiSites.js` (arquivos `_*` não viram rota na Vercel),
importada por `api/meta-capi/sites.js` (prod) e por `server/index.js` (dev).

Contrato:

- `POST /api/meta-capi/sites` — cria/atualiza. Body = config + `capi_token` (texto puro, só aqui).
- `GET  /api/meta-capi/sites` — lista. **Nunca** devolve o token; devolve `has_token: true`.
- `PATCH /api/meta-capi/sites/:id/check` — grava `last_check_at`/`last_check_result`.
- `DELETE /api/meta-capi/sites/:id`

Autorização, **diferente do proxy genérico**:
1. `Authorization: Bearer <access_token do Supabase>` obrigatório;
2. `supabase.auth.getUser(token)` para obter o email;
3. `users.role === 'ADMIN'`, senão 403.

## 6. Templates a gerar (fiéis à produção)

Os arquivos abaixo são **cópia do que já roda**, com os pontos de variação marcados.
Não "melhorar" o código: só parametrizar.

### 6.1 Tag base do Pixel (GTM: Initialization — All Pages)

Idêntica ao padrão da Meta, com `{{pixelId}}` em `fbq('init', ...)` e na `<img>` do `<noscript>`.

### 6.2 Tag interstitial (GTM: Initialization — All Pages)

Base: a tag `Meta - Adviewinterstitial – ViewContent` de produção. Variações:
`ENDPOINT` = `{{endpointUrl}}`, `COOKIE_DOMAIN` = `{{cookieDomain}}`.
**Acrescentar ao payload**: `site_key: '{{siteKey}}'` e `event_name: 'ViewContent'`.
Detecta `#google_vignette` no hash; dispara `dataLayer` `adViewInterstitial`; slot
`google_vignette_interstitial`; guarda `_fbc` (90d) e `_volc_eid` (365d).

### 6.3 Tag rewarded (GTM: Initialization — All Pages)

Base: a tag `Meta - Rewarded`. Mesmas variações + `site_key`.
Detecta `#goog_rewarded`; `event_name: 'RewardedAdView'`; `event_type: 'google_rewarded'`;
slot `google_rewarded`; dataLayer `adViewRewarded`.

### 6.4 Worker Cloudflare (um só, N rotas)

Base: o worker de produção. Única mudança: `SUPABASE_CAPI_URL` = `{{routerFunctionUrl}}`.
Repassa `cf-connecting-ip` → `x-client-ip` e `user-agent` → `x-client-ua`.

### 6.5 Edge Function `capi-router` (multi-tenant)

Comportamento a preservar de `capi-apps-technews`, com a resolução por site:

1. `OPTIONS` → 204 + CORS; `GET` → 200 `"ok"` + CORS. **Obrigatório**: o wizard usa o GET como
   teste de vida, e o CORS aberto é o que permite testar do browser.
2. Resolve o site: `body.site_key`; se ausente, casa `host(body.event_source_url)` com `domain`
   (e com o apex, para cobrir subdomínio). Não achou → 404 JSON `{ok:false, error:"site_not_found"}`.
3. Site inativo → 403 `{ok:false, error:"site_inactive"}`.
4. Decifra `capi_token_cipher` com `CAPI_MASTER_KEY`.
5. `event_name` permitido: `ViewContent` | `RewardedAdView` (ausente = ViewContent). Outro → 400.
6. Monta o evento igual ao de hoje: `custom_data` com `content_name` (slot), `content_category`
   (`interstitial`|`rewarded`), `content_type: "ad_view"`, `status: "viewable"`, `ad_format`, utms.
7. `user_data`: `client_ip_address` (x-client-ip), `client_user_agent` (x-client-ua), fbc, fbp,
   `external_id: [id]`.
8. Erro da Meta → **devolver o texto do erro** no corpo (o wizard mostra ao operador).
9. Sucesso → 204.

Secrets da function: **só** `CAPI_MASTER_KEY`. `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` já são
injetadas por padrão pelo Supabase.

## 7. Checks ao vivo do wizard

| Check | Como | Verde quando |
| --- | --- | --- |
| Endpoint (Worker + DNS) | `GET {endpointUrl}` | 200 |
| Function | `GET {routerFunctionUrl}` | 200 |
| Cadeia até a Meta | `POST {endpointUrl}` com payload real + `test_event_code` | 204 |

Falha: dizer **em qual camada** (endpoint mudo = Worker/DNS; 5xx = function; corpo com erro = Meta)
e mostrar a mensagem da Meta na íntegra.
