"""
Generate the frontend dataset + SQL seed from the canonical country dataset
(backend/app/data/countries.py) — ONE source of truth, zero drift.

Emits:
  - src/data/pautadorCountries.ts            (typed array + search/resolve helpers)
  - src/sql/v7_04_seed_all_pautador_countries.sql  (idempotent: add cols + upsert 195)

Run:  cd backend && python scripts/gen_country_artifacts.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.countries import COUNTRIES  # noqa: E402

WEBGO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS_PATH = os.path.join(WEBGO, "src", "data", "pautadorCountries.ts")
SQL_PATH = os.path.join(WEBGO, "src", "sql", "v7_04_seed_all_pautador_countries.sql")


def _validate() -> None:
    n = len(COUNTRIES)
    assert n == 195, f"esperado 195 países, obtido {n}"
    iso2 = [c["country_code"] for c in COUNTRIES]
    iso3 = [c["iso3"] for c in COUNTRIES]
    assert len(set(iso2)) == n, "ISO2 duplicado"
    assert len(set(iso3)) == n, "ISO3 duplicado"
    for c in COUNTRIES:
        assert c["country_name"] and c["native_language"] and c["flag_emoji"] and c["market_tier"], c
        assert c["market_tier"] in ("high_value", "medium_value", "volume_play"), c


def _sql_str(v) -> str:
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def _sql_int(v) -> str:
    return "NULL" if v is None else str(int(v))


def _sql_jsonb(arr) -> str:
    return "'" + json.dumps(arr, ensure_ascii=False).replace("'", "''") + "'::jsonb"


def gen_ts() -> str:
    rows = json.dumps(COUNTRIES, ensure_ascii=False, indent=2)
    return f"""// ============================================================================
// AUTO-GERADO por backend/scripts/gen_country_artifacts.py — NÃO EDITAR À MÃO.
// Fonte canônica: backend/app/data/countries.py (195 países soberanos).
// ============================================================================

export type MarketTier = 'high_value' | 'medium_value' | 'volume_play';

export interface PautadorCountryData {{
  country_code: string;        // ISO2
  iso3: string;
  country_name: string;        // PT-BR
  name_en: string;
  name_native: string;
  native_language: string;     // locale (ex: pt-BR)
  language_code: string;
  language_short: string;
  language_constant: number | null;   // Google Ads languageConstants (null = desconhecido)
  google_ads_geo_target: number | null; // Google Ads geoTargetConstants (null = desconhecido)
  currency_code: string;
  market_tier: MarketTier;
  flag_emoji: string;
  aliases: string[];
  is_active: boolean;
  is_sovereign: boolean;
}}

export const PAUTADOR_COUNTRIES: PautadorCountryData[] = {rows};

export const norm = (s: string): string =>
  (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').trim().toLowerCase().replace(/\\s+/g, ' ');

const KEY_INDEX = new Map<string, PautadorCountryData>();
for (const c of PAUTADOR_COUNTRIES) {{
  for (const k of [c.country_code, c.iso3, c.country_name, c.name_en, c.name_native, ...c.aliases]) {{
    const nk = norm(k);
    if (!KEY_INDEX.has(nk)) KEY_INDEX.set(nk, c);
  }}
}}

/** Resolve por ISO2/ISO3/nome PT/EN/nativo/alias (sem acento, case-insensitive). */
export function resolveCountry(input: string): PautadorCountryData | undefined {{
  return KEY_INDEX.get(norm(input));
}}

/** Busca tolerante (substring) por nome PT/EN/nativo, ISO2/ISO3 e aliases. */
export function searchCountries(query: string): PautadorCountryData[] {{
  const q = norm(query);
  if (!q) return PAUTADOR_COUNTRIES;
  return PAUTADOR_COUNTRIES.filter((c) => {{
    const hay = [c.country_name, c.name_en, c.name_native, c.country_code, c.iso3, ...c.aliases].map(norm);
    return hay.some((h) => h.includes(q));
  }});
}}
"""


def gen_sql() -> str:
    head = """-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 4 / SEED dos 195 PAÍSES SOBERANOS (ADITIVO, idempotente)
-- 193 Estados-membros da ONU + Santa Sé (Vaticano) + Estado da Palestina.
-- AUTO-GERADO por backend/scripts/gen_country_artifacts.py — NÃO editar à mão.
--
-- NÃO destrutivo: ON CONFLICT (country_code) DO UPDATE (não apaga países).
-- Preserva RLS/policies de v7_01. Roda DEPOIS de v7_01.
-- >>> Rodar manualmente no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

-- 1) Colunas faltantes (idempotente)
ALTER TABLE public.pautador_countries
    ADD COLUMN IF NOT EXISTS iso3                  text,
    ADD COLUMN IF NOT EXISTS name_en               text,
    ADD COLUMN IF NOT EXISTS name_native           text,
    ADD COLUMN IF NOT EXISTS language_code         text,
    ADD COLUMN IF NOT EXISTS language_short        text,
    ADD COLUMN IF NOT EXISTS language_constant     integer,
    ADD COLUMN IF NOT EXISTS google_ads_geo_target integer,
    ADD COLUMN IF NOT EXISTS currency_code         text,
    ADD COLUMN IF NOT EXISTS aliases               jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS is_sovereign          boolean NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS idx_pautador_countries_iso3      ON public.pautador_countries (iso3);
CREATE INDEX IF NOT EXISTS idx_pautador_countries_sovereign ON public.pautador_countries (is_sovereign);

-- 2) Upsert dos 195 países soberanos
INSERT INTO public.pautador_countries
    (country_code, country_name, native_language, market_tier, rpm_index, flag_emoji, is_active,
     iso3, name_en, name_native, language_code, language_short, language_constant,
     google_ads_geo_target, currency_code, aliases, is_sovereign)
VALUES
"""
    rpm = {"high_value": 90, "medium_value": 50, "volume_play": 20}
    values = []
    for c in COUNTRIES:
        values.append(
            "    ("
            + ", ".join(
                [
                    _sql_str(c["country_code"]),
                    _sql_str(c["country_name"]),
                    _sql_str(c["native_language"]),
                    _sql_str(c["market_tier"]),
                    str(rpm[c["market_tier"]]),
                    _sql_str(c["flag_emoji"]),
                    "true",
                    _sql_str(c["iso3"]),
                    _sql_str(c["name_en"]),
                    _sql_str(c["name_native"]),
                    _sql_str(c["language_code"]),
                    _sql_str(c["language_short"]),
                    _sql_int(c["language_constant"]),
                    _sql_int(c["google_ads_geo_target"]),
                    _sql_str(c["currency_code"]),
                    _sql_jsonb(c["aliases"]),
                    "true",
                ]
            )
            + ")"
        )
    body = ",\n".join(values)
    tail = """
ON CONFLICT (country_code) DO UPDATE SET
    country_name          = EXCLUDED.country_name,
    native_language       = EXCLUDED.native_language,
    market_tier           = EXCLUDED.market_tier,
    flag_emoji            = EXCLUDED.flag_emoji,
    is_active             = true,
    iso3                  = EXCLUDED.iso3,
    name_en               = EXCLUDED.name_en,
    name_native           = EXCLUDED.name_native,
    language_code         = EXCLUDED.language_code,
    language_short        = EXCLUDED.language_short,
    language_constant     = EXCLUDED.language_constant,
    google_ads_geo_target = EXCLUDED.google_ads_geo_target,
    currency_code         = EXCLUDED.currency_code,
    aliases               = EXCLUDED.aliases,
    is_sovereign          = true,
    updated_at            = now();

-- =====================================================================
-- Verificação (opcional) — deve retornar 195:
-- SELECT count(*) FROM public.pautador_countries WHERE is_active = true AND is_sovereign = true;
-- SELECT country_code, country_name, market_tier FROM public.pautador_countries ORDER BY country_name;
-- =====================================================================
"""
    return head + body + tail


def main() -> int:
    _validate()
    os.makedirs(os.path.dirname(TS_PATH), exist_ok=True)
    with open(TS_PATH, "w", encoding="utf-8") as fh:
        fh.write(gen_ts())
    with open(SQL_PATH, "w", encoding="utf-8") as fh:
        fh.write(gen_sql())
    print(f"OK — {len(COUNTRIES)} países")
    print(f"  TS : {TS_PATH}")
    print(f"  SQL: {SQL_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
