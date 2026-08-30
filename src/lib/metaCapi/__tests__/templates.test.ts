import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';

import { deriveConfig } from '../derive';
import {
  TEMPLATE_META,
  buildAllTemplates,
  buildInterstitialTag,
  buildPixelBaseTag,
  buildRewardedTag,
  buildWorkerScript,
} from '../templates';
import type { MetaCapiSiteConfig, TemplateId } from '../types';

/** Config do exemplo de produção — a mesma do arquivo de fontes. */
const cfg: MetaCapiSiteConfig = {
  siteName: 'Apps TechNews',
  siteKey: 'apps-technews',
  domain: 'apps.technewsbrasil.com.br',
  cookieDomain: '.technewsbrasil.com.br',
  endpointSubdomain: 'ev',
  endpointUrl: 'https://ev.technewsbrasil.com.br/capi',
  pixelId: '940750053457681',
  events: { interstitial: true, rewarded: true },
  routerFunctionUrl: 'https://txvvzpstquqmbhljudfn.supabase.co/functions/v1/capi-router',
};

const SPEC_PATH = fileURLToPath(
  new URL(
    '../../../../docs/superpowers/specs/2026-07-30-meta-capi-fontes-producao.md',
    import.meta.url,
  ),
);

/** Blocos de código do arquivo de fontes, na ordem: pixel base, interstitial, worker. */
function specBlocks(): string[] {
  const spec = readFileSync(SPEC_PATH, 'utf8');
  const blocks = spec.match(/```(?:html|js)\n[\s\S]*?\n```/g) || [];
  return blocks.map((b) => b.replace(/^```(?:html|js)\n/, '').replace(/\n```$/, ''));
}

/** Reaplica os ⟦placeholders⟧ do arquivo de fontes com os valores da config. */
function fillPlaceholders(block: string): string {
  return block
    .replace(/⟦pixelId⟧/g, cfg.pixelId)
    .replace(/⟦endpointUrl⟧/g, cfg.endpointUrl)
    .replace(/⟦cookieDomain⟧/g, cfg.cookieDomain)
    .replace(/⟦siteKey⟧/g, cfg.siteKey)
    .replace(/⟦routerFunctionUrl⟧/g, cfg.routerFunctionUrl);
}

describe('fidelidade byte-a-byte com o código de produção', () => {
  it('o arquivo de fontes ainda traz os 3 blocos esperados', () => {
    expect(specBlocks()).toHaveLength(3);
  });

  it('tag base do Pixel é idêntica à de produção', () => {
    expect(buildPixelBaseTag(cfg)).toBe(fillPlaceholders(specBlocks()[0]));
  });

  it('tag interstitial é idêntica à de produção', () => {
    expect(buildInterstitialTag(cfg)).toBe(fillPlaceholders(specBlocks()[1]));
  });

  it('worker é idêntico ao de produção', () => {
    expect(buildWorkerScript(cfg)).toBe(fillPlaceholders(specBlocks()[2]));
  });

  it('a tag rewarded espelha a interstitial (só as diferenças previstas)', () => {
    const interstitial = buildInterstitialTag(cfg).split('\n');
    const rewarded = buildRewardedTag(cfg).split('\n');

    // mesmas funções utilitárias, byte a byte
    for (const helper of [
      "    var match = document.cookie.match('(^|;)\\\\s*' + name + '\\\\s*=\\\\s*([^;]+)');",
      "      '; SameSite=Lax; Secure';",
      "    setCookie('_fbc', fbc, 7776000); // 90 dias",
      "    setCookie('_volc_eid', eid, 31536000); // 365 dias",
      '        new Blob([JSON.stringify(payload)], { type: \'text/plain\' })',
      '          keepalive: true',
    ]) {
      expect(interstitial).toContain(helper);
      expect(rewarded).toContain(helper);
    }

    // mesma "moldura": prerendering, hashchange, pushState, replaceState e o guard `fired`
    for (const frame of [
      '  var fired = false;',
      '  if (document.prerendering) {',
      "  window.addEventListener('hashchange', function () {",
      '  var originalPushState = history.pushState;',
      '  var originalReplaceState = history.replaceState;',
    ]) {
      expect(interstitial).toContain(frame);
      expect(rewarded).toContain(frame);
    }

    // e o mesmo tamanho de arquivo a menos das linhas realmente novas
    expect(rewarded.length).toBe(interstitial.length + 5);
  });
});

describe('tag base do Pixel', () => {
  it('usa o pixelId nos DOIS lugares (fbq init e <img> do noscript)', () => {
    const out = buildPixelBaseTag(cfg);

    expect(out).toContain(`fbq('init', '${cfg.pixelId}');`);
    expect(out).toContain(
      `src="https://www.facebook.com/tr?id=${cfg.pixelId}&ev=PageView&noscript=1"`,
    );
    expect(out.split(cfg.pixelId).length - 1).toBe(2);
  });

  it('mantém o PageView e os comentários de marcação da Meta', () => {
    const out = buildPixelBaseTag(cfg);
    expect(out).toContain("fbq('track', 'PageView');");
    expect(out.startsWith('<!-- Meta Pixel Code -->')).toBe(true);
    expect(out.endsWith('<!-- End Meta Pixel Code -->')).toBe(true);
  });

  it('reflete outro pixelId sem sobrar resíduo do exemplo', () => {
    const out = buildPixelBaseTag({ ...cfg, pixelId: '1111111111' });
    expect(out.split('1111111111').length - 1).toBe(2);
    expect(out).not.toContain('940750053457681');
  });
});

describe('tag interstitial', () => {
  const out = buildInterstitialTag(cfg);

  it('injeta endpoint e cookieDomain nas constantes', () => {
    expect(out).toContain(`var ENDPOINT = '${cfg.endpointUrl}';`);
    expect(out).toContain(`var COOKIE_DOMAIN = '${cfg.cookieDomain}';`);
  });

  it('manda site_key e event_name ViewContent no payload', () => {
    expect(out).toContain(`      site_key: '${cfg.siteKey}',`);
    expect(out).toContain("      event_name: 'ViewContent',");
    expect(out).not.toContain('RewardedAdView');
  });

  it('detecta google_vignette (e não goog_rewarded)', () => {
    expect(out).toContain("      if (hash.indexOf('google_vignette') === -1) return;");
    expect(out).not.toContain('goog_rewarded');
  });

  it('usa o slot e o evento de dataLayer do interstitial', () => {
    expect(out).toContain("      slot_id: 'google_vignette_interstitial',");
    expect(out).toContain("        event: 'adViewInterstitial',");
    expect(out).toContain("    return 'google_vignette_' + Date.now()");
  });

  it('mantém sendBeacon com fallback de fetch keepalive', () => {
    expect(out).toContain('navigator.sendBeacon(');
    expect(out).toContain('keepalive: true');
    expect(out.indexOf('navigator.sendBeacon(')).toBeLessThan(out.indexOf('fetch(ENDPOINT'));
  });

  it('grava _fbc por 90 dias e _volc_eid por 365 dias', () => {
    expect(out).toContain("setCookie('_fbc', fbc, 7776000); // 90 dias");
    expect(out).toContain("setCookie('_volc_eid', eid, 31536000); // 365 dias");
  });

  it('reflete outra config sem resíduo do exemplo', () => {
    const other = buildInterstitialTag({
      ...cfg,
      siteKey: 'blog-loja',
      cookieDomain: '.loja.com.br',
      endpointUrl: 'https://ev.loja.com.br/capi',
    });
    expect(other).toContain("var ENDPOINT = 'https://ev.loja.com.br/capi';");
    expect(other).toContain("      site_key: 'blog-loja',");
    expect(other).not.toContain('technewsbrasil');
  });
});

describe('tag rewarded', () => {
  const out = buildRewardedTag(cfg);

  it('injeta endpoint e cookieDomain nas constantes', () => {
    expect(out).toContain(`var ENDPOINT = '${cfg.endpointUrl}';`);
    expect(out).toContain(`var COOKIE_DOMAIN = '${cfg.cookieDomain}';`);
  });

  it('manda site_key, event_name RewardedAdView e event_type google_rewarded', () => {
    expect(out).toContain(`      site_key: '${cfg.siteKey}',`);
    expect(out).toContain("      event_name: 'RewardedAdView',");
    expect(out).toContain("      event_type: 'google_rewarded',");
    expect(out).not.toContain("event_name: 'ViewContent'");
  });

  it('detecta goog_rewarded (e não google_vignette)', () => {
    expect(out).toContain("      if (hash.indexOf('goog_rewarded') === -1) return;");
    expect(out).not.toContain('google_vignette');
  });

  it('usa slot, eventId e dataLayer do rewarded', () => {
    expect(out).toContain("      slot_id: 'google_rewarded',");
    expect(out).toContain("    return 'google_rewarded_' + Date.now()");
    expect(out).toContain("        event: 'adViewRewarded',");
    expect(out).toContain('        rewardedOpened: true,');
    expect(out).toContain('        rewardedCompleted: false,');
    expect(out).toContain('        rewardGranted: false,');
    expect(out).toContain("        metaEventName: 'RewardedAdView',");
  });
});

describe('worker Cloudflare', () => {
  const out = buildWorkerScript(cfg);

  it('aponta para a routerFunctionUrl da config', () => {
    expect(out).toContain(`const SUPABASE_CAPI_URL = "${cfg.routerFunctionUrl}";`);
    expect(out.startsWith('const SUPABASE_CAPI_URL = "https://')).toBe(true);
  });

  it('mantém os headers x-client-ip e x-client-ua no repasse', () => {
    expect(out).toContain('"x-client-ip": clientIp,');
    expect(out).toContain('"x-client-ua": clientUa,');
    expect(out).toContain('request.headers.get("cf-connecting-ip")');
    expect(out).toContain('request.headers.get("user-agent")');
  });

  it('mantém OPTIONS 204, GET "ok" 200 e CORS aberto (teste de vida do wizard)', () => {
    expect(out).toContain('return new Response(null, { status: 204, headers: corsHeaders });');
    expect(out).toContain('return new Response("ok", { status: 200, headers: corsHeaders });');
    expect(out).toContain('"Access-Control-Allow-Origin": "*",');
  });

  it('reflete outro projectRef', () => {
    const other = buildWorkerScript({
      ...cfg,
      routerFunctionUrl: 'https://outroref.supabase.co/functions/v1/capi-router',
    });
    expect(other).toContain('const SUPABASE_CAPI_URL = "https://outroref.supabase.co/functions/v1/capi-router";');
    expect(other).not.toContain('txvvzpstquqmbhljudfn');
  });
});

describe('anti-placeholder', () => {
  /**
   * Únicas ocorrências legítimas de `null`/`undefined` no código de produção.
   * Qualquer outra é vazamento de variável não resolvida.
   */
  const ALLOWED: Record<TemplateId, string[]> = {
    pixelBase: [],
    interstitial: [],
    rewarded: [],
    worker: ['return new Response(null, { status: 204, headers: corsHeaders });'],
  };

  function scrub(id: TemplateId, code: string): string {
    let out = code;
    for (const allowed of ALLOWED[id]) out = out.split(allowed).join('');
    return out;
  }

  const configs: Array<[string, MetaCapiSiteConfig]> = [
    ['config do exemplo', cfg],
    [
      'config derivada com campos opcionais ausentes',
      deriveConfig({
        siteName: 'Blog Loja',
        domain: 'blog.loja.com.br',
        pixelId: '1234567890',
        projectRef: 'abcdefghijklmnop',
        events: { interstitial: true, rewarded: true },
      }),
    ],
  ];

  for (const [label, config] of configs) {
    for (const id of Object.keys(TEMPLATE_META) as TemplateId[]) {
      it(`${id} — ${label}: sem ⟦, {{, undefined ou null`, () => {
        const code = buildAllTemplates(config)[id];
        const clean = scrub(id, code);

        expect(code).not.toContain('⟦');
        expect(code).not.toContain('⟧');
        expect(code).not.toContain('{{');
        expect(code).not.toContain('}}');
        expect(clean).not.toContain('undefined');
        expect(clean).not.toContain('null');
        expect(code).not.toContain('[object Object]');
        expect(code.trim().length).toBeGreaterThan(0);
      });
    }
  }
});

describe('TEMPLATE_META', () => {
  it('descreve os quatro artefatos com id coerente', () => {
    const ids = Object.keys(TEMPLATE_META) as TemplateId[];
    expect(ids.sort()).toEqual(['interstitial', 'pixelBase', 'rewarded', 'worker']);
    for (const id of ids) {
      expect(TEMPLATE_META[id].id).toBe(id);
    }
  });

  it('as três tags do GTM são HTML personalizado em Initialization — All Pages', () => {
    for (const id of ['pixelBase', 'interstitial', 'rewarded'] as TemplateId[]) {
      expect(TEMPLATE_META[id].gtmTagType).toBe('HTML personalizado');
      expect(TEMPLATE_META[id].gtmTrigger).toBe('Initialization — All Pages');
    }
  });

  it('o worker deixa claro que não é tag do GTM', () => {
    expect(TEMPLATE_META.worker.gtmTagType).toContain('Não se aplica');
    expect(TEMPLATE_META.worker.gtmTrigger).toContain('Não se aplica');
  });

  it('todo metadado tem título e descrição preenchidos', () => {
    for (const meta of Object.values(TEMPLATE_META)) {
      expect(meta.title.length).toBeGreaterThan(5);
      expect(meta.description.length).toBeGreaterThan(40);
    }
  });
});

describe('buildAllTemplates', () => {
  it('devolve os quatro artefatos de uma vez', () => {
    const all = buildAllTemplates(cfg);
    expect(all.pixelBase).toBe(buildPixelBaseTag(cfg));
    expect(all.interstitial).toBe(buildInterstitialTag(cfg));
    expect(all.rewarded).toBe(buildRewardedTag(cfg));
    expect(all.worker).toBe(buildWorkerScript(cfg));
  });
});
