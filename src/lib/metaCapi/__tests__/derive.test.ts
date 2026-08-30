import { describe, it, expect } from 'vitest';
import {
  COMPOSITE_PUBLIC_SUFFIXES,
  DEFAULT_ENDPOINT_SUBDOMAIN,
  deriveConfig,
  deriveCookieDomain,
  deriveEndpointUrl,
  deriveRouterFunctionUrl,
  deriveSiteKey,
  isValidDomain,
  isValidPixelId,
  publicSuffixApex,
  sanitizeSiteKey,
} from '../derive';

const PROJECT_REF = 'txvvzpstquqmbhljudfn';

describe('publicSuffixApex / deriveCookieDomain — tabela do contrato', () => {
  const table: Array<{ domain: string; apex: string; cookieDomain: string }> = [
    {
      domain: 'apps.technewsbrasil.com.br',
      apex: 'technewsbrasil.com.br',
      cookieDomain: '.technewsbrasil.com.br',
    },
    {
      domain: 'technewsbrasil.com.br',
      apex: 'technewsbrasil.com.br',
      cookieDomain: '.technewsbrasil.com.br',
    },
    { domain: 'blog.loja.com.br', apex: 'loja.com.br', cookieDomain: '.loja.com.br' },
    { domain: 'site.com', apex: 'site.com', cookieDomain: '.site.com' },
    { domain: 'a.b.site.co.uk', apex: 'site.co.uk', cookieDomain: '.site.co.uk' },
  ];

  for (const row of table) {
    it(`${row.domain} -> apex ${row.apex} / cookie ${row.cookieDomain}`, () => {
      expect(publicSuffixApex(row.domain)).toBe(row.apex);
      expect(deriveCookieDomain(row.domain)).toBe(row.cookieDomain);
    });
  }

  it('cookieDomain sempre começa com ponto (compartilhamento entre subdomínios)', () => {
    for (const row of table) {
      expect(deriveCookieDomain(row.domain).startsWith('.')).toBe(true);
    }
  });

  it('todos os sufixos compostos da lista usam 3 rótulos', () => {
    for (const suffix of COMPOSITE_PUBLIC_SUFFIXES) {
      expect(publicSuffixApex(`www.marca.${suffix}`)).toBe(`marca.${suffix}`);
      expect(deriveCookieDomain(`www.marca.${suffix}`)).toBe(`.marca.${suffix}`);
    }
  });

  it('sufixo simples fora da lista usa 2 rótulos', () => {
    expect(publicSuffixApex('news.exemplo.io')).toBe('exemplo.io');
    expect(publicSuffixApex('a.b.c.exemplo.dev')).toBe('exemplo.dev');
    // "co.br" NÃO está na lista do contrato
    expect(publicSuffixApex('sub.marca.co.br')).toBe('co.br');
  });

  it('normaliza caixa alta, espaços e ponto final', () => {
    expect(publicSuffixApex('  APPS.TechNewsBrasil.COM.BR.  ')).toBe('technewsbrasil.com.br');
    expect(deriveCookieDomain('  APPS.TechNewsBrasil.COM.BR.  ')).toBe('.technewsbrasil.com.br');
  });

  it('entrada vazia não gera um ponto solto', () => {
    expect(publicSuffixApex('')).toBe('');
    expect(deriveCookieDomain('')).toBe('');
  });
});

describe('deriveSiteKey / sanitizeSiteKey', () => {
  it('tira o sufixo público e troca ponto por hífen', () => {
    expect(deriveSiteKey('apps.technewsbrasil.com.br')).toBe('apps-technewsbrasil');
    expect(deriveSiteKey('technewsbrasil.com.br')).toBe('technewsbrasil');
    expect(deriveSiteKey('blog.loja.com.br')).toBe('blog-loja');
    expect(deriveSiteKey('site.com')).toBe('site');
    expect(deriveSiteKey('a.b.site.co.uk')).toBe('a-b-site');
  });

  it('sempre minúsculo e só [a-z0-9-]', () => {
    const key = deriveSiteKey('Apps.TechNews_Brasil.COM.BR');
    expect(key).toBe('apps-technews-brasil');
    expect(key).toMatch(/^[a-z0-9-]+$/);
  });

  it('sanitiza a chave editada pelo usuário', () => {
    expect(sanitizeSiteKey('  Apps TechNews  ')).toBe('apps-technews');
    expect(sanitizeSiteKey('apps..technews')).toBe('apps-technews');
    expect(sanitizeSiteKey('--apps--technews--')).toBe('apps-technews');
    expect(sanitizeSiteKey('Apps@TechNews!')).toBe('apps-technews');
    expect(sanitizeSiteKey('Notícias BR')).toBe('not-cias-br');
    expect(sanitizeSiteKey('')).toBe('');
  });
});

describe('deriveEndpointUrl — sempre a partir do APEX, nunca do host', () => {
  it('apps.technewsbrasil.com.br + ev -> https://ev.technewsbrasil.com.br/capi', () => {
    expect(deriveEndpointUrl('apps.technewsbrasil.com.br', 'ev')).toBe(
      'https://ev.technewsbrasil.com.br/capi',
    );
  });

  it('não repete o subdomínio do site no endpoint', () => {
    const url = deriveEndpointUrl('apps.technewsbrasil.com.br', 'ev');
    expect(url).not.toContain('apps.');
    expect(url).not.toContain('ev.apps.');
  });

  it('funciona com apex, subdomínio profundo e sufixo composto', () => {
    expect(deriveEndpointUrl('technewsbrasil.com.br', 'ev')).toBe(
      'https://ev.technewsbrasil.com.br/capi',
    );
    expect(deriveEndpointUrl('a.b.site.co.uk', 'capi')).toBe('https://capi.site.co.uk/capi');
    expect(deriveEndpointUrl('site.com', 'ev')).toBe('https://ev.site.com/capi');
  });

  it('subdomínio ausente/vazio cai no padrão "ev"', () => {
    expect(DEFAULT_ENDPOINT_SUBDOMAIN).toBe('ev');
    expect(deriveEndpointUrl('site.com')).toBe('https://ev.site.com/capi');
    expect(deriveEndpointUrl('site.com', '   ')).toBe('https://ev.site.com/capi');
  });

  it('tolera o subdomínio digitado com pontos nas pontas', () => {
    expect(deriveEndpointUrl('site.com', '.EV.')).toBe('https://ev.site.com/capi');
  });
});

describe('deriveRouterFunctionUrl', () => {
  it('monta a URL da Edge Function do projeto', () => {
    expect(deriveRouterFunctionUrl(PROJECT_REF)).toBe(
      'https://txvvzpstquqmbhljudfn.supabase.co/functions/v1/capi-router',
    );
  });

  it('ref vazio devolve string vazia (em vez de URL quebrada)', () => {
    expect(deriveRouterFunctionUrl('')).toBe('');
    expect(deriveRouterFunctionUrl('   ')).toBe('');
  });

  // Delta VOLC: o fork roda Supabase self-hosted, onde não existe project ref.
  // Antes desta correção a derivação devolvia '' para qualquer host próprio, e
  // checkFunction('') acabava fazendo fetch contra a própria página do app.
  describe('Supabase self-hosted', () => {
    const expected = 'https://database.agenciavolc.com.br/functions/v1/capi-router';

    it('aceita a URL base completa', () => {
      expect(deriveRouterFunctionUrl('https://database.agenciavolc.com.br')).toBe(expected);
    });

    it('aceita host sem esquema e assume https', () => {
      expect(deriveRouterFunctionUrl('database.agenciavolc.com.br')).toBe(expected);
    });

    it('ignora barra final', () => {
      expect(deriveRouterFunctionUrl('https://database.agenciavolc.com.br/')).toBe(expected);
    });

    it('não confunde host self-hosted com project ref hosted', () => {
      expect(deriveRouterFunctionUrl('database.agenciavolc.com.br')).not.toContain('.supabase.co');
    });

    it('preserva porta não padrão do self-hosted', () => {
      expect(deriveRouterFunctionUrl('http://localhost:8000')).toBe(
        'http://localhost:8000/functions/v1/capi-router',
      );
    });
  });
});

describe('deriveConfig', () => {
  it('monta a config completa do exemplo do contrato', () => {
    const cfg = deriveConfig({
      siteName: 'Apps TechNews',
      domain: 'apps.technewsbrasil.com.br',
      pixelId: '940750053457681',
      endpointSubdomain: 'ev',
      projectRef: PROJECT_REF,
      events: { interstitial: true, rewarded: true },
    });

    expect(cfg).toEqual({
      siteName: 'Apps TechNews',
      siteKey: 'apps-technewsbrasil',
      domain: 'apps.technewsbrasil.com.br',
      cookieDomain: '.technewsbrasil.com.br',
      endpointSubdomain: 'ev',
      endpointUrl: 'https://ev.technewsbrasil.com.br/capi',
      pixelId: '940750053457681',
      events: { interstitial: true, rewarded: true },
      routerFunctionUrl: 'https://txvvzpstquqmbhljudfn.supabase.co/functions/v1/capi-router',
    });
  });

  it('respeita a siteKey editada pelo usuário (sanitizada)', () => {
    const cfg = deriveConfig({
      siteName: 'Apps TechNews',
      domain: 'apps.technewsbrasil.com.br',
      pixelId: '940750053457681',
      projectRef: PROJECT_REF,
      events: { interstitial: true, rewarded: false },
      siteKey: 'Apps TechNews',
    });

    expect(cfg.siteKey).toBe('apps-technews');
    expect(cfg.events).toEqual({ interstitial: true, rewarded: false });
  });

  it('normaliza domínio e aplica o subdomínio padrão quando ausente', () => {
    const cfg = deriveConfig({
      siteName: '  Loja  ',
      domain: '  BLOG.Loja.COM.BR  ',
      pixelId: ' 1234567890 ',
      projectRef: PROJECT_REF,
      events: { interstitial: true, rewarded: true },
    });

    expect(cfg.domain).toBe('blog.loja.com.br');
    expect(cfg.siteName).toBe('Loja');
    expect(cfg.pixelId).toBe('1234567890');
    expect(cfg.endpointSubdomain).toBe('ev');
    expect(cfg.endpointUrl).toBe('https://ev.loja.com.br/capi');
    expect(cfg.cookieDomain).toBe('.loja.com.br');
  });

  it('é pura: mesma entrada, mesma saída, sem mutar o input', () => {
    const input = {
      siteName: 'Site',
      domain: 'site.com',
      pixelId: '1234567890',
      projectRef: PROJECT_REF,
      events: { interstitial: true, rewarded: true },
    };
    const snapshot = JSON.stringify(input);

    expect(deriveConfig(input)).toEqual(deriveConfig(input));
    expect(JSON.stringify(input)).toBe(snapshot);
  });
});

describe('isValidDomain', () => {
  it('aceita domínios válidos', () => {
    for (const domain of [
      'site.com',
      'apps.technewsbrasil.com.br',
      'a.b.site.co.uk',
      'meu-site-1.com.br',
    ]) {
      expect(isValidDomain(domain)).toEqual({ valid: true, error: null });
    }
  });

  it('rejeita vazio', () => {
    const r = isValidDomain('');
    expect(r.valid).toBe(false);
    expect(r.error).toBe('Informe o domínio do site.');
  });

  it('rejeita protocolo', () => {
    for (const bad of ['http://site.com', 'https://site.com', 'HTTPS://SITE.COM', '//site.com']) {
      const r = isValidDomain(bad);
      expect(r.valid).toBe(false);
      expect(r.error).toContain('http://');
    }
  });

  it('rejeita caminho, porta, querystring e e-mail', () => {
    expect(isValidDomain('site.com/capi').error).toContain('caminho');
    expect(isValidDomain('site.com:8080').error).toContain('porta');
    expect(isValidDomain('site.com?x=1').error).toContain('parâmetros');
    expect(isValidDomain('user@site.com').error).toContain('e-mail');
  });

  it('rejeita espaços, domínio sem ponto e pontos duplicados', () => {
    expect(isValidDomain('meu site.com').error).toContain('espaços');
    expect(isValidDomain('localhost').error).toContain('ponto');
    expect(isValidDomain('site..com').error).toContain('pontos');
  });

  it('rejeita caracteres inválidos, hífen nas pontas e TLD numérico', () => {
    expect(isValidDomain('site_novo.com').valid).toBe(false);
    expect(isValidDomain('-site.com').error).toContain('hífen');
    expect(isValidDomain('site-.com').error).toContain('hífen');
    expect(isValidDomain('192.168.0.1').error).toContain('terminação');
  });

  it('toda mensagem de erro é uma frase em pt-BR utilizável no formulário', () => {
    for (const bad of ['', 'http://site.com', 'site.com/capi', 'localhost', '-site.com']) {
      const r = isValidDomain(bad);
      expect(r.valid).toBe(false);
      expect(typeof r.error).toBe('string');
      expect((r.error as string).length).toBeGreaterThan(10);
      expect(r.error).toMatch(/\.$/);
    }
  });
});

describe('isValidPixelId', () => {
  it('aceita IDs só com dígitos entre 10 e 20 caracteres', () => {
    expect(isValidPixelId('940750053457681')).toEqual({ valid: true, error: null });
    expect(isValidPixelId('1234567890').valid).toBe(true);
    expect(isValidPixelId('12345678901234567890').valid).toBe(true);
    expect(isValidPixelId('  940750053457681  ').valid).toBe(true);
  });

  it('rejeita vazio', () => {
    expect(isValidPixelId('').error).toBe('Informe o Pixel ID da Meta.');
  });

  it('rejeita letras e pontuação', () => {
    for (const bad of ['94075005345768a', 'pixel-940750053457681', '940 750 053 457', '9407.50053']) {
      const r = isValidPixelId(bad);
      expect(r.valid).toBe(false);
      expect(r.error).toContain('apenas números');
    }
  });

  it('rejeita curto demais e longo demais', () => {
    expect(isValidPixelId('123456789').error).toContain('entre 10 e 20');
    expect(isValidPixelId('123456789012345678901').error).toContain('entre 10 e 20');
  });
});
