# capi-router — Edge Function multi-tenant do Meta CAPI

## O que é

Uma única Edge Function que recebe os eventos de view de anúncio (GTM → Worker Cloudflare →
esta function) e repassa para a Conversions API da Meta (Graph API **v21.0**).

O que ela faz de diferente do modelo antigo: em vez de ter `PIXEL_ID` e token fixos em secrets
(uma function por site), ela **resolve o site em tempo de request** na tabela `meta_capi_sites`:

1. usa `site_key` do body (as tags geradas pelo wizard sempre mandam);
2. sem `site_key`, casa o host de `event_source_url` com a coluna `domain` — e, se não bater
   exato, tenta o apex do host (cobre `www.` e subdomínios não cadastrados);
3. não achou → `404 {"ok":false,"error":"site_not_found"}`; achou com `is_active=false` →
   `403 {"ok":false,"error":"site_inactive"}`.

Do registro vêm o `pixel_id` e o access token cifrado, que é decifrado em memória com AES-GCM 256.
**Site novo = 1 linha na tabela. Nenhum deploy novo.**

Comportamento preservado do baseline (`capi-apps-technews`): CORS aberto, `GET` → `200 "ok"`,
eventos aceitos `ViewContent` e `RewardedAdView` (ausente = `ViewContent`), montagem de
`user_data`/`custom_data`, `test_event_code` repassado, erro da Meta devolvido no corpo, `204`
com `Cache-Control: no-store` no sucesso.

As functions antigas (`bright-service`, `capi-apps-technews`) continuam no ar, intocadas.

## Deploy pelo painel do Supabase

Projeto: `txvvzpstquqmbhljudfn`.

1. **Edge Functions → Deploy a new function → Via Editor**.
2. Nome: `capi-router` (o nome entra na URL e é o que o wizard usa).
3. Cole o conteúdo de `index.ts` deste diretório e clique em **Deploy**.
4. **Desligue o JWT**: na function, `Details → Function Configuration → Verify JWT` = **OFF**
   (ou `Enforce JWT Verification` desmarcado). Isto é obrigatório — o Worker Cloudflare e o
   navegador não mandam `Authorization`, e com o JWT ligado tudo volta `401`.
5. Cadastre o secret (abaixo) antes do primeiro teste.

URL final: `https://txvvzpstquqmbhljudfn.supabase.co/functions/v1/capi-router`

## Secret — só um

| Secret | O que é |
| --- | --- |
| `CAPI_MASTER_KEY` | Chave AES-256 em **base64** (32 bytes). Gere com `openssl rand -base64 32`. |

Cadastre em **Edge Functions → Secrets** (ou Project Settings → Edge Functions → Secrets).

> Tem que ser **exatamente a mesma chave** usada pelo backend Node (`api/_lib/capiCrypto.js`)
> ao salvar o site. Chave diferente = `500 token_decrypt_failed`. Trocar a master key exige
> re-salvar o token de todos os sites.

`SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` **não** precisam ser criadas: o Supabase já injeta
as duas em toda Edge Function. A leitura da tabela usa o service role, que ignora a RLS (a tabela
tem RLS ligada e zero policies de propósito — ninguém alcança o token cifrado pelo PostgREST).

## Testando com curl

```bash
FN="https://txvvzpstquqmbhljudfn.supabase.co/functions/v1/capi-router"
```

**1. Teste de vida (é o mesmo check do wizard):**

```bash
curl -i "$FN"
# esperado: HTTP/2 200  +  corpo "ok"
```

**2. Evento real (use um `test_event_code` do Gerenciador de Eventos → Testar eventos):**

```bash
curl -i -X POST "$FN" \
  -H "Content-Type: text/plain" \
  -H "x-client-ip: 203.0.113.10" \
  -H "x-client-ua: Mozilla/5.0 (Linux; Android 13)" \
  -d '{
    "site_key": "apps-technews",
    "event_name": "ViewContent",
    "event_id": "teste-curl-1",
    "event_source_url": "https://apps.technewsbrasil.com.br/",
    "slot_id": "google_vignette_interstitial",
    "external_id": "teste-externo-1",
    "test_event_code": "TEST12345"
  }'
# esperado: HTTP/2 204 (sem corpo) e o evento aparecendo em "Testar eventos"
```

**3. Sem `site_key` (resolve pelo domínio da URL):**

```bash
curl -i -X POST "$FN" -H "Content-Type: text/plain" \
  -d '{"event_source_url":"https://apps.technewsbrasil.com.br/post"}'
```

### Lendo a resposta

| Resposta | Significado |
| --- | --- |
| `204` sem corpo | Evento aceito pela Meta. |
| `400 unsupported_event_name` | `event_name` fora de `ViewContent` / `RewardedAdView`. |
| `404 site_not_found` | `site_key`/domínio não está em `meta_capi_sites` (o corpo mostra qual foi procurado). |
| `403 site_inactive` | Site existe com `is_active = false`. |
| `500 master_key_missing` / `master_key_invalid` | Secret `CAPI_MASTER_KEY` ausente ou não é base64 de 32 bytes. |
| `500 token_decrypt_failed` | Master key não é a mesma que cifrou o token daquele site. |
| `500` com `meta_status` e `error` | A Meta recusou — o campo `error` traz o texto original dela. |

## Notas de operação

- **Cache de 60s**: o registro do site fica em memória por 60 segundos, porque a function é
  chamada em todo view de anúncio e não faz sentido um `SELECT` por impressão. Efeito prático:
  editar pixel/token ou desativar um site leva até 60s para valer em todas as instâncias.
  Resultados negativos não são cacheados — site recém-criado pelo wizard funciona na hora.
- O token nunca é logado nem devolvido; mensagens de erro têm o `access_token` redigido.
