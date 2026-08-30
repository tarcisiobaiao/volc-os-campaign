# Meta CAPI — código de produção (baseline)

Isto é o que **já roda** hoje (technewsbrasil / apps.technewsbrasil). Os geradores do wizard devem
produzir exatamente isto, trocando só os pontos marcados como `⟦variável⟧`. Não reescrever, não
"modernizar", não reordenar: a fidelidade é o que garante que o que funciona continue funcionando.

---

## Tag 1 — MetaPixel Base (GTM: Initialization — All Pages)

`⟦pixelId⟧` = 940750053457681 no exemplo.

```html
<!-- Meta Pixel Code -->
<script>
!function(f,b,e,v,n,t,s)
{if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '⟦pixelId⟧');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id=⟦pixelId⟧&ev=PageView&noscript=1"
/></noscript>
<!-- End Meta Pixel Code -->
```

---

## Tag 2 — Interstitial / ViewContent

`⟦endpointUrl⟧` = `https://ev.technewsbrasil.com.br/capi` · `⟦cookieDomain⟧` = `.technewsbrasil.com.br`

No payload, o gerador ACRESCENTA duas chaves ao que existe hoje: `site_key: '⟦siteKey⟧'` e
`event_name: 'ViewContent'`. O resto é idêntico.

```html
<script>
(function () {
  'use strict';

  window.dataLayer = window.dataLayer || [];

  var ENDPOINT = '⟦endpointUrl⟧';
  var COOKIE_DOMAIN = '⟦cookieDomain⟧'; // compartilha cookies entre subdomínios
  var fired = false;

  function getCookie(name) {
    var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? decodeURIComponent(match.pop()) : '';
  }

  function setCookie(name, value, maxAgeSeconds) {
    document.cookie =
      name + '=' + encodeURIComponent(value) +
      '; path=/' +
      '; domain=' + COOKIE_DOMAIN +
      '; max-age=' + maxAgeSeconds +
      '; SameSite=Lax; Secure';
  }

  function getQueryParam(name) {
    try {
      return new URLSearchParams(window.location.search).get(name) || '';
    } catch (e) {
      return '';
    }
  }

  function ensureFbc() {
    var existingFbc = getCookie('_fbc');
    if (existingFbc) return existingFbc;
    var fbclid = getQueryParam('fbclid');
    if (!fbclid) return '';
    var fbc = 'fb.1.' + Date.now() + '.' + fbclid;
    setCookie('_fbc', fbc, 7776000); // 90 dias
    return fbc;
  }

  function ensureExternalId() {
    var eid = getCookie('_volc_eid');
    if (eid) {
      setCookie('_volc_eid', eid, 31536000); // renova por 365 dias
      return eid;
    }
    if (window.crypto && crypto.randomUUID) {
      eid = crypto.randomUUID();
    } else {
      eid = 'eid_' + Date.now() + '_' +
        Math.random().toString(36).slice(2) +
        Math.random().toString(36).slice(2);
    }
    setCookie('_volc_eid', eid, 31536000); // 365 dias
    return eid;
  }

  function buildEventId() {
    return 'google_vignette_' + Date.now() + '_' + Math.random().toString(36).slice(2);
  }

  function sendCapi(eventId) {
    var fbc = ensureFbc();
    var fbp = getCookie('_fbp');
    var externalId = ensureExternalId();

    var params = new URLSearchParams(window.location.search);

    var payload = {
      site_key: '⟦siteKey⟧',
      event_name: 'ViewContent',
      event_id: eventId,
      event_source_url: location.href.split('#')[0],
      referrer_url: document.referrer || '',
      fbc: fbc,
      fbp: fbp,
      external_id: externalId,
      slot_id: 'google_vignette_interstitial',
      utm_source: params.get('utm_source') || '',
      utm_medium: params.get('utm_medium') || '',
      utm_campaign: params.get('utm_campaign') || '',
      utm_content: params.get('utm_content') || '',
      utm_term: params.get('utm_term') || ''
    };

    try {
      navigator.sendBeacon(
        ENDPOINT,
        new Blob([JSON.stringify(payload)], { type: 'text/plain' })
      );
    } catch (e) {
      try {
        fetch(ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'text/plain' },
          body: JSON.stringify(payload),
          keepalive: true
        });
      } catch (err) {}
    }

    return payload;
  }

  function fireVignetteEvent(method) {
    if (fired) return;

    try {
      var hash = (location.hash || '').toLowerCase();
      if (hash.indexOf('google_vignette') === -1) return;

      fired = true;

      var eventId = buildEventId();
      var payload = sendCapi(eventId);

      window.dataLayer.push({
        event: 'adViewInterstitial',
        source: 'google_vignette',
        method: method || 'hash_google_vignette',
        adUnit: 'google_vignette_interstitial',
        slotId: 'google_vignette_interstitial',
        size: '',
        isEmpty: false,
        adView: true,
        page: location.href.split('#')[0],
        eventId: eventId,
        capiEndpoint: ENDPOINT,
        hasFbc: !!payload.fbc,
        hasFbp: !!payload.fbp,
        hasExternalId: !!payload.external_id
      });

      console.log('[Meta CAPI] google_vignette enviado', payload);
    } catch (e) {
      console.error('[Meta CAPI] erro google_vignette', e);
    }
  }

  ensureFbc();
  ensureExternalId();

  if (document.prerendering) {
    document.addEventListener('prerenderingchange', function () {
      fireVignetteEvent('prerenderingchange');
    }, { once: true });
  } else {
    fireVignetteEvent('initial_check');
  }

  window.addEventListener('hashchange', function () {
    fireVignetteEvent('hashchange');
  }, true);

  var originalPushState = history.pushState;
  history.pushState = function () {
    originalPushState.apply(history, arguments);
    fireVignetteEvent('pushState');
  };

  var originalReplaceState = history.replaceState;
  history.replaceState = function () {
    originalReplaceState.apply(history, arguments);
    fireVignetteEvent('replaceState');
  };
})();
</script>
```

---

## Tag 3 — Rewarded

Mesmas variáveis. Payload de produção já traz `event_name: 'RewardedAdView'` e
`event_type: 'google_rewarded'`; o gerador acrescenta `site_key: '⟦siteKey⟧'`.
Detecta `#goog_rewarded`, dispara `adViewRewarded` no dataLayer, slot `google_rewarded`,
`buildEventId()` com prefixo `google_rewarded_`, e o dataLayer inclui
`rewardedOpened: true, rewardedCompleted: false, rewardGranted: false` e
`metaEventName: 'RewardedAdView'`. Estrutura idêntica à Tag 2 no restante
(getCookie/setCookie/getQueryParam/ensureFbc/ensureExternalId/sendCapi/prerendering/hashchange/
pushState/replaceState, com `fired` próprio).

---

## Worker Cloudflare

`⟦routerFunctionUrl⟧` substitui a URL fixa da function.

```js
const SUPABASE_CAPI_URL = "⟦routerFunctionUrl⟧";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "content-type, authorization, x-client-info, apikey",
};

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    if (request.method === "GET") {
      return new Response("ok", { status: 200, headers: corsHeaders });
    }

    if (request.method !== "POST") {
      return new Response("method not allowed", { status: 405, headers: corsHeaders });
    }

    const clientIp =
      request.headers.get("cf-connecting-ip") ||
      request.headers.get("x-forwarded-for") ||
      "";

    const clientUa = request.headers.get("user-agent") || "";

    const bodyText = await request.text();

    const upstream = await fetch(SUPABASE_CAPI_URL, {
      method: "POST",
      headers: {
        "Content-Type": request.headers.get("content-type") || "text/plain",
        "x-client-ip": clientIp,
        "x-client-ua": clientUa,
      },
      body: bodyText,
    });

    const responseHeaders = new Headers(corsHeaders);

    upstream.headers.forEach((value, key) => {
      if (key.toLowerCase() !== "content-length") {
        responseHeaders.set(key, value);
      }
    });

    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  },
};
```

---

## Edge Function atual (`capi-apps-technews`) — baseline de comportamento

Pontos que a `capi-router` precisa preservar:

- `OPTIONS` → 204 com CORS; `GET` → 200 `"ok"` com CORS.
- `allowedEventNames = new Set(["ViewContent", "RewardedAdView"])`; ausente = `ViewContent`;
  qualquer outro → 400 `unsupported_event_name`.
- `isRewarded` decide `defaultSlotId` (`google_rewarded` / `google_vignette_interstitial`) e
  `contentCategory` (`rewarded` / `interstitial`).
- IP: `x-client-ip` → `cf-connecting-ip` → 1º de `x-forwarded-for`. UA: `x-client-ua` → `user-agent`.
- Evento: `event_time` em segundos, `event_id` (ou `crypto.randomUUID()`), `action_source: "website"`,
  `event_source_url`, `referrer_url` quando houver.
- `user_data`: `client_ip_address`, `client_user_agent`, `fbc`, `fbp`, `external_id: [id]`
  (sem hash — a Meta normaliza e hasheia na recepção).
- `custom_data`: `content_name` (slot), `content_category` (`interstitial`|`rewarded`),
  `content_type: "ad_view"`, `status: "viewable"`, **`ad_format` = a MESMA string de
  `content_category`** (não é o nome do slot), `event_type` e as 5 utms quando presentes.
- `test_event_code` repassado quando vier no body.
- Graph: `https://graph.facebook.com/v21.0/{PIXEL_ID}/events?access_token={TOKEN}` — **manter v21.0**,
  que é a versão validada em produção.
- Erro da Meta → 500 com `{ok:false, meta_status, error, event_name, event_id}`.
- Sucesso → 204 com `Cache-Control: no-store`.
