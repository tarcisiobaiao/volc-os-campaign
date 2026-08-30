// ============================================
// PAUTADOR PRO — normalização determinística de países (client-side, sem LLM)
// Permite o admin digitar um país novo e obter o cartão canônico:
// name_pt, name_native, iso2, iso3, emoji_flag, primary_language, market_tier.
// Mapa local para países comuns + fallback conservador para desconhecidos.
// ============================================

import type { MarketTier, PautadorCountry } from '@/types/pautador';

export interface CanonicalCountry {
  name_pt: string;
  name_native: string;
  iso2: string | null;
  iso3: string | null;
  emoji_flag: string | null;
  primary_language: string | null; // locale BCP-47, ex: es-MX
  market_tier: MarketTier;
  matched: boolean; // true = país conhecido no mapa
}

interface Entry {
  name_pt: string;
  name_native: string;
  iso2: string;
  iso3: string;
  emoji_flag: string;
  primary_language: string;
  market_tier: MarketTier;
  aliases?: string[];
}

const COUNTRIES: Entry[] = [
  { name_pt: 'Reino Unido', name_native: 'United Kingdom', iso2: 'GB', iso3: 'GBR', emoji_flag: '🇬🇧', primary_language: 'en-GB', market_tier: 'high_value', aliases: ['uk', 'inglaterra', 'gra bretanha', 'great britain', 'england'] },
  { name_pt: 'Estados Unidos', name_native: 'United States', iso2: 'US', iso3: 'USA', emoji_flag: '🇺🇸', primary_language: 'en-US', market_tier: 'high_value', aliases: ['eua', 'usa', 'america'] },
  { name_pt: 'Canadá', name_native: 'Canada', iso2: 'CA', iso3: 'CAN', emoji_flag: '🇨🇦', primary_language: 'en-CA', market_tier: 'high_value' },
  { name_pt: 'Alemanha', name_native: 'Deutschland', iso2: 'DE', iso3: 'DEU', emoji_flag: '🇩🇪', primary_language: 'de-DE', market_tier: 'high_value', aliases: ['germany'] },
  { name_pt: 'França', name_native: 'France', iso2: 'FR', iso3: 'FRA', emoji_flag: '🇫🇷', primary_language: 'fr-FR', market_tier: 'high_value' },
  { name_pt: 'Suíça', name_native: 'Schweiz', iso2: 'CH', iso3: 'CHE', emoji_flag: '🇨🇭', primary_language: 'de-CH', market_tier: 'high_value', aliases: ['switzerland', 'suica'] },
  { name_pt: 'Áustria', name_native: 'Österreich', iso2: 'AT', iso3: 'AUT', emoji_flag: '🇦🇹', primary_language: 'de-AT', market_tier: 'high_value', aliases: ['austria'] },
  { name_pt: 'Países Baixos', name_native: 'Nederland', iso2: 'NL', iso3: 'NLD', emoji_flag: '🇳🇱', primary_language: 'nl-NL', market_tier: 'high_value', aliases: ['holanda', 'netherlands'] },
  { name_pt: 'Bélgica', name_native: 'België', iso2: 'BE', iso3: 'BEL', emoji_flag: '🇧🇪', primary_language: 'nl-BE', market_tier: 'high_value', aliases: ['belgium'] },
  { name_pt: 'Irlanda', name_native: 'Ireland', iso2: 'IE', iso3: 'IRL', emoji_flag: '🇮🇪', primary_language: 'en-IE', market_tier: 'high_value', aliases: ['ireland'] },
  { name_pt: 'Suécia', name_native: 'Sverige', iso2: 'SE', iso3: 'SWE', emoji_flag: '🇸🇪', primary_language: 'sv-SE', market_tier: 'high_value', aliases: ['sweden', 'suecia'] },
  { name_pt: 'Noruega', name_native: 'Norge', iso2: 'NO', iso3: 'NOR', emoji_flag: '🇳🇴', primary_language: 'nb-NO', market_tier: 'high_value', aliases: ['norway'] },
  { name_pt: 'Dinamarca', name_native: 'Danmark', iso2: 'DK', iso3: 'DNK', emoji_flag: '🇩🇰', primary_language: 'da-DK', market_tier: 'high_value', aliases: ['denmark'] },
  { name_pt: 'Finlândia', name_native: 'Suomi', iso2: 'FI', iso3: 'FIN', emoji_flag: '🇫🇮', primary_language: 'fi-FI', market_tier: 'high_value', aliases: ['finland'] },
  { name_pt: 'Austrália', name_native: 'Australia', iso2: 'AU', iso3: 'AUS', emoji_flag: '🇦🇺', primary_language: 'en-AU', market_tier: 'high_value', aliases: ['australia'] },
  { name_pt: 'Nova Zelândia', name_native: 'New Zealand', iso2: 'NZ', iso3: 'NZL', emoji_flag: '🇳🇿', primary_language: 'en-NZ', market_tier: 'high_value', aliases: ['new zealand'] },
  { name_pt: 'Japão', name_native: '日本', iso2: 'JP', iso3: 'JPN', emoji_flag: '🇯🇵', primary_language: 'ja-JP', market_tier: 'high_value', aliases: ['japan', 'japao'] },
  { name_pt: 'Coreia do Sul', name_native: '대한민국', iso2: 'KR', iso3: 'KOR', emoji_flag: '🇰🇷', primary_language: 'ko-KR', market_tier: 'high_value', aliases: ['south korea', 'coreia'] },
  { name_pt: 'Cingapura', name_native: 'Singapore', iso2: 'SG', iso3: 'SGP', emoji_flag: '🇸🇬', primary_language: 'en-SG', market_tier: 'high_value', aliases: ['singapura', 'singapore'] },
  { name_pt: 'Portugal', name_native: 'Portugal', iso2: 'PT', iso3: 'PRT', emoji_flag: '🇵🇹', primary_language: 'pt-PT', market_tier: 'medium_value' },
  { name_pt: 'Espanha', name_native: 'España', iso2: 'ES', iso3: 'ESP', emoji_flag: '🇪🇸', primary_language: 'es-ES', market_tier: 'medium_value', aliases: ['spain', 'espanha'] },
  { name_pt: 'Itália', name_native: 'Italia', iso2: 'IT', iso3: 'ITA', emoji_flag: '🇮🇹', primary_language: 'it-IT', market_tier: 'medium_value', aliases: ['italy', 'italia'] },
  { name_pt: 'Polônia', name_native: 'Polska', iso2: 'PL', iso3: 'POL', emoji_flag: '🇵🇱', primary_language: 'pl-PL', market_tier: 'medium_value', aliases: ['poland', 'polonia'] },
  { name_pt: 'Brasil', name_native: 'Brasil', iso2: 'BR', iso3: 'BRA', emoji_flag: '🇧🇷', primary_language: 'pt-BR', market_tier: 'medium_value', aliases: ['brazil'] },
  { name_pt: 'México', name_native: 'México', iso2: 'MX', iso3: 'MEX', emoji_flag: '🇲🇽', primary_language: 'es-MX', market_tier: 'medium_value', aliases: ['mexico'] },
  { name_pt: 'Argentina', name_native: 'Argentina', iso2: 'AR', iso3: 'ARG', emoji_flag: '🇦🇷', primary_language: 'es-AR', market_tier: 'medium_value' },
  { name_pt: 'Chile', name_native: 'Chile', iso2: 'CL', iso3: 'CHL', emoji_flag: '🇨🇱', primary_language: 'es-CL', market_tier: 'medium_value' },
  { name_pt: 'Uruguai', name_native: 'Uruguay', iso2: 'UY', iso3: 'URY', emoji_flag: '🇺🇾', primary_language: 'es-UY', market_tier: 'medium_value', aliases: ['uruguay'] },
  { name_pt: 'Colômbia', name_native: 'Colombia', iso2: 'CO', iso3: 'COL', emoji_flag: '🇨🇴', primary_language: 'es-CO', market_tier: 'volume_play', aliases: ['colombia'] },
  { name_pt: 'Peru', name_native: 'Perú', iso2: 'PE', iso3: 'PER', emoji_flag: '🇵🇪', primary_language: 'es-PE', market_tier: 'volume_play' },
  { name_pt: 'Equador', name_native: 'Ecuador', iso2: 'EC', iso3: 'ECU', emoji_flag: '🇪🇨', primary_language: 'es-EC', market_tier: 'volume_play', aliases: ['ecuador'] },
  { name_pt: 'Bolívia', name_native: 'Bolivia', iso2: 'BO', iso3: 'BOL', emoji_flag: '🇧🇴', primary_language: 'es-BO', market_tier: 'volume_play', aliases: ['bolivia'] },
  { name_pt: 'Paraguai', name_native: 'Paraguay', iso2: 'PY', iso3: 'PRY', emoji_flag: '🇵🇾', primary_language: 'es-PY', market_tier: 'volume_play', aliases: ['paraguay'] },
  { name_pt: 'Venezuela', name_native: 'Venezuela', iso2: 'VE', iso3: 'VEN', emoji_flag: '🇻🇪', primary_language: 'es-VE', market_tier: 'volume_play' },
  { name_pt: 'Guatemala', name_native: 'Guatemala', iso2: 'GT', iso3: 'GTM', emoji_flag: '🇬🇹', primary_language: 'es-GT', market_tier: 'volume_play' },
  { name_pt: 'Índia', name_native: 'भारत', iso2: 'IN', iso3: 'IND', emoji_flag: '🇮🇳', primary_language: 'hi-IN', market_tier: 'volume_play', aliases: ['india'] },
  { name_pt: 'Indonésia', name_native: 'Indonesia', iso2: 'ID', iso3: 'IDN', emoji_flag: '🇮🇩', primary_language: 'id-ID', market_tier: 'volume_play', aliases: ['indonesia'] },
  { name_pt: 'Filipinas', name_native: 'Pilipinas', iso2: 'PH', iso3: 'PHL', emoji_flag: '🇵🇭', primary_language: 'fil-PH', market_tier: 'volume_play', aliases: ['philippines'] },
];

/** Remove acentos + lowercase + colapsa espaços, para comparação tolerante. */
export function normKey(s: string): string {
  return (s || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '') // remove combining diacritics
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

const LOOKUP = new Map<string, Entry>();
for (const e of COUNTRIES) {
  for (const k of [e.name_pt, e.name_native, e.iso2, e.iso3, ...(e.aliases || [])]) {
    LOOKUP.set(normKey(k), e);
  }
}

function slugCode(name: string): string {
  const base = normKey(name).replace(/[^a-z]/g, '').toUpperCase();
  return (base || 'XX').slice(0, 3);
}

/** Normaliza um país digitado livremente em um cartão canônico determinístico. */
export function normalizeCountryInput(raw: string): CanonicalCountry {
  const entry = LOOKUP.get(normKey(raw));
  if (entry) {
    return { ...entry, matched: true, aliases: undefined } as CanonicalCountry;
  }
  const name = raw.trim().replace(/\s+/g, ' ');
  const titled = name.replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    name_pt: titled,
    name_native: titled,
    iso2: null,
    iso3: null,
    emoji_flag: null,
    primary_language: null,
    market_tier: 'volume_play', // default conservador
    matched: false,
  };
}

/** Mapeia o cartão canônico para uma linha da tabela pautador_countries. */
export function toCountryRow(c: CanonicalCountry): Omit<PautadorCountry, 'id'> {
  return {
    country_code: (c.iso2 || slugCode(c.name_pt)).toUpperCase().slice(0, 8),
    country_name: c.name_pt,
    native_language: c.primary_language || 'und',
    market_tier: c.market_tier,
    flag_emoji: c.emoji_flag,
    is_active: true,
  };
}

/** True se `name`/`code` já existir na lista (comparação tolerante a acento/case). */
export function countryExists(
  list: PautadorCountry[],
  candidate: { country_code?: string; country_name: string },
): PautadorCountry | undefined {
  const ck = candidate.country_code ? candidate.country_code.toUpperCase() : '';
  const nk = normKey(candidate.country_name);
  return list.find(
    (c) => (ck && c.country_code?.toUpperCase() === ck) || normKey(c.country_name) === nk,
  );
}
