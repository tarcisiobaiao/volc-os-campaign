/**
 * Meta CAPI — geradores dos artefatos que o operador cola no GTM / Cloudflare.
 *
 * Fontes da verdade:
 *   docs/superpowers/specs/2026-07-30-meta-capi-fontes-producao.md  (código que já roda)
 *   docs/superpowers/specs/2026-07-30-meta-capi-wizard-contrato.md  (pontos de variação)
 *
 * REGRA: o código gerado é cópia do de produção, trocando SÓ os pontos de variação.
 * Não reescrever, não reformatar, não "modernizar", não trocar `var` por `const`.
 * A fidelidade é o que garante que o que funciona continue funcionando.
 *
 * Os literais usam String.raw para que as contrabarras (`\\s` no getCookie)
 * cheguem intactas na saída.
 */
import type { MetaCapiSiteConfig, TemplateId, TemplateMeta } from './types';

/** Tag 1 — MetaPixel Base (GTM: Initialization — All Pages). */
export function buildPixelBaseTag(cfg: MetaCapiSiteConfig): string {
  const pixelId = cfg.pixelId;

  return String.raw`<!-- Meta Pixel Code -->
<script>
!function(f,b,e,v,n,t,s)
{if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '${pixelId}');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id=${pixelId}&ev=PageView&noscript=1"
/></noscript>
<!-- End Meta Pixel Code -->`;
}

/** Tag 2 — Interstitial / ViewContent (GTM: Initialization — All Pages). */
export function buildInterstitialTag(cfg: MetaCapiSiteConfig): string {
  const endpointUrl = cfg.endpointUrl;
  const cookieDomain = cfg.cookieDomain;
  const siteKey = cfg.siteKey;

  return String.raw`<script>
(function () {
  'use strict';

  window.dataLayer = window.dataLayer || [];

  var ENDPOINT = '${endpointUrl}';
  var COOKIE_DOMAIN = '${cookieDomain}'; // compartilha cookies entre subdomínios
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
      site_key: '${siteKey}',
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
</script>`;
}

/**
 * Tag 3 — Rewarded (GTM: Initialization — All Pages).
 *
 * Estrutura idêntica à Tag 2; diferenças (conforme o arquivo de fontes):
 * detecta `goog_rewarded`, `event_name: 'RewardedAdView'`, `event_type: 'google_rewarded'`,
 * slot `google_rewarded`, `buildEventId()` com prefixo `google_rewarded_`,
 * dataLayer `adViewRewarded` com rewardedOpened/rewardedCompleted/rewardGranted e metaEventName.
 */
export function buildRewardedTag(cfg: MetaCapiSiteConfig): string {
  const endpointUrl = cfg.endpointUrl;
  const cookieDomain = cfg.cookieDomain;
  const siteKey = cfg.siteKey;

  return String.raw`<script>
(function () {
  'use strict';

  window.dataLayer = window.dataLayer || [];

  var ENDPOINT = '${endpointUrl}';
  var COOKIE_DOMAIN = '${cookieDomain}'; // compartilha cookies entre subdomínios
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
    return 'google_rewarded_' + Date.now() + '_' + Math.random().toString(36).slice(2);
  }

  function sendCapi(eventId) {
    var fbc = ensureFbc();
    var fbp = getCookie('_fbp');
    var externalId = ensureExternalId();

    var params = new URLSearchParams(window.location.search);

    var payload = {
      site_key: '${siteKey}',
      event_name: 'RewardedAdView',
      event_type: 'google_rewarded',
      event_id: eventId,
      event_source_url: location.href.split('#')[0],
      referrer_url: document.referrer || '',
      fbc: fbc,
      fbp: fbp,
      external_id: externalId,
      slot_id: 'google_rewarded',
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

  function fireRewardedEvent(method) {
    if (fired) return;

    try {
      var hash = (location.hash || '').toLowerCase();
      if (hash.indexOf('goog_rewarded') === -1) return;

      fired = true;

      var eventId = buildEventId();
      var payload = sendCapi(eventId);

      window.dataLayer.push({
        event: 'adViewRewarded',
        source: 'goog_rewarded',
        method: method || 'hash_goog_rewarded',
        adUnit: 'google_rewarded',
        slotId: 'google_rewarded',
        size: '',
        isEmpty: false,
        adView: true,
        rewardedOpened: true,
        rewardedCompleted: false,
        rewardGranted: false,
        metaEventName: 'RewardedAdView',
        page: location.href.split('#')[0],
        eventId: eventId,
        capiEndpoint: ENDPOINT,
        hasFbc: !!payload.fbc,
        hasFbp: !!payload.fbp,
        hasExternalId: !!payload.external_id
      });

      console.log('[Meta CAPI] goog_rewarded enviado', payload);
    } catch (e) {
      console.error('[Meta CAPI] erro goog_rewarded', e);
    }
  }

  ensureFbc();
  ensureExternalId();

  if (document.prerendering) {
    document.addEventListener('prerenderingchange', function () {
      fireRewardedEvent('prerenderingchange');
    }, { once: true });
  } else {
    fireRewardedEvent('initial_check');
  }

  window.addEventListener('hashchange', function () {
    fireRewardedEvent('hashchange');
  }, true);

  var originalPushState = history.pushState;
  history.pushState = function () {
    originalPushState.apply(history, arguments);
    fireRewardedEvent('pushState');
  };

  var originalReplaceState = history.replaceState;
  history.replaceState = function () {
    originalReplaceState.apply(history, arguments);
    fireRewardedEvent('replaceState');
  };
})();
</script>`;
}

/** Worker Cloudflare — um só, N rotas. Única variação: a URL da Edge Function. */
export function buildWorkerScript(cfg: MetaCapiSiteConfig): string {
  const routerFunctionUrl = cfg.routerFunctionUrl;

  return String.raw`const SUPABASE_CAPI_URL = "${routerFunctionUrl}";

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
};`;
}

/** Metadados para a UI: título, onde colar no GTM e o que a peça faz. */
export const TEMPLATE_META: Record<TemplateId, TemplateMeta> = {
  pixelBase: {
    id: 'pixelBase',
    title: 'Tag 1 — Pixel base da Meta',
    gtmTagType: 'HTML personalizado',
    gtmTrigger: 'Initialization — All Pages',
    description:
      'Carrega o fbevents.js, faz o fbq(\'init\') com o Pixel ID do site e dispara o PageView. ' +
      'É a base: sem ela, as tags de interstitial e rewarded não têm pixel para complementar.',
  },
  interstitial: {
    id: 'interstitial',
    title: 'Tag 2 — Interstitial (ViewContent)',
    gtmTagType: 'HTML personalizado',
    gtmTrigger: 'Initialization — All Pages',
    description:
      'Detecta o hash #google_vignette do anúncio interstitial do Google, envia o evento ViewContent ' +
      'para o endpoint da CAPI via sendBeacon (com fetch keepalive como fallback) e empurra ' +
      'adViewInterstitial no dataLayer. Cuida também dos cookies _fbc (90 dias) e _volc_eid (365 dias).',
  },
  rewarded: {
    id: 'rewarded',
    title: 'Tag 3 — Rewarded (RewardedAdView)',
    gtmTagType: 'HTML personalizado',
    gtmTrigger: 'Initialization — All Pages',
    description:
      'Mesma estrutura da tag de interstitial, mas detecta o hash #goog_rewarded, envia o evento ' +
      'RewardedAdView com event_type google_rewarded e empurra adViewRewarded no dataLayer.',
  },
  worker: {
    id: 'worker',
    title: 'Worker Cloudflare — endpoint do site',
    gtmTagType: 'Não se aplica (Cloudflare Worker)',
    gtmTrigger: 'Não se aplica (publique numa rota do Cloudflare apontando para o endpoint)',
    description:
      'Recebe os eventos das tags no seu próprio domínio (first-party), acrescenta os headers ' +
      'x-client-ip e x-client-ua com o IP e o User-Agent reais e repassa para a Edge Function ' +
      'capi-router. Um único Worker atende todos os sites — basta adicionar a rota.',
  },
};

/** Conveniência para a UI: gera os quatro artefatos de uma vez. */
export function buildAllTemplates(cfg: MetaCapiSiteConfig): Record<TemplateId, string> {
  return {
    pixelBase: buildPixelBaseTag(cfg),
    interstitial: buildInterstitialTag(cfg),
    rewarded: buildRewardedTag(cfg),
    worker: buildWorkerScript(cfg),
  };
}
