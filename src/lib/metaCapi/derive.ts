/**
 * Meta CAPI — derivações puras (sem I/O, sem estado).
 *
 * Fonte da verdade: docs/superpowers/specs/2026-07-30-meta-capi-wizard-contrato.md
 */
import type {
  DeriveConfigInput,
  MetaCapiSiteConfig,
  ValidationResult,
} from './types';

/**
 * Sufixos públicos compostos (precisam de 3 rótulos para chegar no apex).
 * Lista fechada do contrato — não inventar entradas novas sem atualizar o contrato.
 */
export const COMPOSITE_PUBLIC_SUFFIXES: readonly string[] = [
  'com.br',
  'net.br',
  'org.br',
  'gov.br',
  'edu.br',
  'co.uk',
  'com.ar',
  'com.mx',
  'com.co',
  'com.pe',
  'com.uy',
  'com.py',
  'com.ve',
  'com.ec',
  'com.gt',
  'com.do',
  'co.jp',
  'com.au',
];

/** Subdomínio padrão do endpoint quando o wizard não recebe outro. */
export const DEFAULT_ENDPOINT_SUBDOMAIN = 'ev';

/** Normaliza um domínio para comparação: minúsculo, sem espaços, sem ponto final. */
function normalizeDomain(domain: string): string {
  return String(domain ?? '')
    .trim()
    .toLowerCase()
    .replace(/\.+$/, '');
}

/**
 * Devolve o sufixo público do domínio (`com.br`, `co.uk`, `com`, ...).
 * Usado por `publicSuffixApex` e por `deriveSiteKey`.
 */
export function publicSuffixOf(domain: string): string {
  const labels = normalizeDomain(domain).split('.').filter(Boolean);
  if (labels.length < 2) return labels[labels.length - 1] || '';

  const lastTwo = labels.slice(-2).join('.');
  if (COMPOSITE_PUBLIC_SUFFIXES.indexOf(lastTwo) !== -1) return lastTwo;

  return labels[labels.length - 1];
}

/**
 * Apex do domínio (registrable domain), SEM ponto na frente.
 *
 *   apps.technewsbrasil.com.br -> technewsbrasil.com.br
 *   a.b.site.co.uk             -> site.co.uk
 *   site.com                   -> site.com
 */
export function publicSuffixApex(domain: string): string {
  const normalized = normalizeDomain(domain);
  const labels = normalized.split('.').filter(Boolean);
  if (labels.length <= 2) return labels.join('.');

  const lastTwo = labels.slice(-2).join('.');
  const take = COMPOSITE_PUBLIC_SUFFIXES.indexOf(lastTwo) !== -1 ? 3 : 2;

  return labels.slice(-take).join('.');
}

/**
 * Domínio do cookie: apex COM ponto na frente, para compartilhar entre subdomínios.
 * `apps.technewsbrasil.com.br` -> `.technewsbrasil.com.br`
 */
export function deriveCookieDomain(domain: string): string {
  const apex = publicSuffixApex(domain);
  return apex ? '.' + apex : '';
}

/**
 * Chave multi-tenant derivada do domínio: domínio sem o sufixo público,
 * pontos viram hífen, minúsculo, só `[a-z0-9-]`.
 * `apps.technewsbrasil.com.br` -> `apps-technewsbrasil`
 */
export function deriveSiteKey(domain: string): string {
  const normalized = normalizeDomain(domain);
  const suffix = publicSuffixOf(normalized);

  let base = normalized;
  if (suffix && base.endsWith('.' + suffix)) {
    base = base.slice(0, -(suffix.length + 1));
  } else if (suffix && base === suffix) {
    base = '';
  }

  return sanitizeSiteKey(base);
}

/** Sanitiza uma siteKey digitada pelo usuário para o formato aceito. */
export function sanitizeSiteKey(value: string): string {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[._\s]+/g, '-')
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Endpoint do Worker. Montado a partir do APEX, nunca do host:
 * domínio `apps.technewsbrasil.com.br` + subdomínio `ev` -> `https://ev.technewsbrasil.com.br/capi`
 */
export function deriveEndpointUrl(domain: string, subdomain?: string): string {
  const apex = publicSuffixApex(domain);
  if (!apex) return '';

  const sub = String(subdomain ?? '')
    .trim()
    .toLowerCase()
    .replace(/^\.+|\.+$/g, '') || DEFAULT_ENDPOINT_SUBDOMAIN;

  return 'https://' + sub + '.' + apex + '/capi';
}

/**
 * URL da Edge Function multi-tenant do Supabase.
 *
 * Aceita as duas formas de instalação:
 *  - Supabase hosted: recebe o project ref puro (`txvvzpstquqmbhljudfn`) e
 *    monta `https://<ref>.supabase.co/functions/v1/capi-router`.
 *  - Supabase self-hosted (caso do VOLC O.S., database.agenciavolc.com.br):
 *    recebe a URL base ou o host e monta `<base>/functions/v1/capi-router`.
 *
 * A distinção é feita pela presença de ponto ou de esquema: um project ref do
 * Supabase hosted é sempre um único label, sem ponto.
 */
export function deriveRouterFunctionUrl(projectRefOrBaseUrl: string): string {
  const raw = String(projectRefOrBaseUrl ?? '').trim().replace(/\/+$/, '');
  if (!raw) return '';

  const isSelfHosted = raw.includes('.') || raw.includes('://');
  if (!isSelfHosted) {
    return 'https://' + raw + '.supabase.co/functions/v1/capi-router';
  }

  const base = /^https?:\/\//i.test(raw) ? raw : 'https://' + raw;
  try {
    return new URL('/functions/v1/capi-router', base).toString();
  } catch {
    return '';
  }
}

/** Monta a config completa do site a partir da entrada do formulário. */
export function deriveConfig(input: DeriveConfigInput): MetaCapiSiteConfig {
  const domain = normalizeDomain(input.domain);
  const endpointSubdomain =
    String(input.endpointSubdomain ?? '')
      .trim()
      .toLowerCase()
      .replace(/^\.+|\.+$/g, '') || DEFAULT_ENDPOINT_SUBDOMAIN;

  const siteKey = input.siteKey
    ? sanitizeSiteKey(input.siteKey)
    : deriveSiteKey(domain);

  return {
    siteName: String(input.siteName ?? '').trim(),
    siteKey,
    domain,
    cookieDomain: deriveCookieDomain(domain),
    endpointSubdomain,
    endpointUrl: deriveEndpointUrl(domain, endpointSubdomain),
    pixelId: String(input.pixelId ?? '').trim(),
    events: {
      interstitial: !!(input.events && input.events.interstitial),
      rewarded: !!(input.events && input.events.rewarded),
    },
    routerFunctionUrl: deriveRouterFunctionUrl(input.projectRef),
  };
}

const OK: ValidationResult = { valid: true, error: null };

function fail(error: string): ValidationResult {
  return { valid: false, error };
}

/**
 * Valida o domínio digitado no wizard.
 *
 * ATENÇÃO: devolve `{ valid, error }`, não um boolean — use `isValidDomain(d).valid`.
 * As mensagens já estão em pt-BR, prontas para o formulário.
 */
export function isValidDomain(domain: string): ValidationResult {
  const raw = String(domain ?? '').trim();

  if (!raw) return fail('Informe o domínio do site.');
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(raw) || raw.startsWith('//')) {
    return fail('Informe apenas o domínio, sem http:// ou https://.');
  }
  if (/\s/.test(raw)) return fail('O domínio não pode conter espaços.');
  if (raw.indexOf('/') !== -1) {
    return fail('Informe apenas o domínio, sem caminho — ex.: apps.seusite.com.br.');
  }
  if (raw.indexOf('@') !== -1) {
    return fail('Informe apenas o domínio, sem e-mail ou usuário.');
  }
  if (raw.indexOf(':') !== -1) {
    return fail('Informe apenas o domínio, sem porta (ex.: remova o ":8080").');
  }
  if (raw.indexOf('?') !== -1 || raw.indexOf('#') !== -1) {
    return fail('Informe apenas o domínio, sem parâmetros de URL.');
  }

  const normalized = normalizeDomain(raw);
  if (normalized.length > 253) {
    return fail('O domínio é longo demais (máximo de 253 caracteres).');
  }

  const labels = normalized.split('.');
  if (labels.length < 2) {
    return fail('O domínio precisa ter ao menos um ponto — ex.: seusite.com.br.');
  }

  for (const label of labels) {
    if (!label) {
      return fail('O domínio tem pontos seguidos ou sobrando — ex.: apps.seusite.com.br.');
    }
    if (label.length > 63) {
      return fail('Cada parte do domínio pode ter no máximo 63 caracteres.');
    }
    if (!/^[a-z0-9-]+$/.test(label)) {
      return fail('O domínio só aceita letras, números, hífen e ponto.');
    }
    if (label.startsWith('-') || label.endsWith('-')) {
      return fail('Nenhuma parte do domínio pode começar ou terminar com hífen.');
    }
  }

  const tld = labels[labels.length - 1];
  if (!/^[a-z]{2,}$/.test(tld)) {
    return fail('A terminação do domínio parece inválida — ex.: .com, .com.br.');
  }

  return OK;
}

/**
 * Valida o Pixel ID: só dígitos, entre 10 e 20 caracteres.
 *
 * ATENÇÃO: devolve `{ valid, error }`, não um boolean — use `isValidPixelId(p).valid`.
 */
export function isValidPixelId(pixelId: string): ValidationResult {
  const raw = String(pixelId ?? '').trim();

  if (!raw) return fail('Informe o Pixel ID da Meta.');
  if (!/^[0-9]+$/.test(raw)) {
    return fail('O Pixel ID deve conter apenas números (sem letras, espaços ou pontuação).');
  }
  if (raw.length < 10 || raw.length > 20) {
    return fail('O Pixel ID deve ter entre 10 e 20 dígitos.');
  }

  return OK;
}
