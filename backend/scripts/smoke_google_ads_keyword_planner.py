"""
Smoke test — REAL, minimal, non-destructive call to Google Ads
generateKeywordIdeas (read-only: it does NOT create/modify/delete anything).

Run:  cd backend && python scripts/smoke_google_ads_keyword_planner.py

It NEVER prints secrets. If Google Ads auth is not ready it stops and reports
only the missing key NAMES (no values). Seed = "tax refund", geo = Reino Unido.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.mining.geo import GeoLanguageMapper
from app.config import get_settings
from app.services.google_ads import GoogleAdsKeywordPlannerClient

SEED = "tax refund"
COUNTRY = "Reino Unido"
COUNTRY_CODE = "GB"
PAGE_SIZE = 10


def _mask(kw: str) -> str:
    """Keywords sao publicas, mas mascaramos por precaucao (regra do smoke)."""
    kw = kw or ""
    if len(kw) <= 4:
        return (kw[:1] or "") + "***"
    return kw[:3] + "***" + kw[-2:]


def _classify_http_error(status: int, text: str) -> str:
    t = (text or "").upper()
    hints = []
    # --- OAuth token-endpoint errors (falha ANTES de chegar na Ads API) ---
    if "UNAUTHORIZED_CLIENT" in t:
        hints.append(
            "OAuth 'unauthorized_client' -> o REFRESH_TOKEN nao pertence a este CLIENT_ID/CLIENT_SECRET "
            "(token gerado para outro OAuth client) OU o client nao esta autorizado para esse grant. "
            "Acao: gere o refresh token usando EXATAMENTE o mesmo client_id+secret do .env, escopo "
            "https://www.googleapis.com/auth/adwords."
        )
    elif "INVALID_CLIENT" in t:
        hints.append("OAuth 'invalid_client' -> CLIENT_ID/CLIENT_SECRET incorretos ou rotacionados.")
    elif "INVALID_GRANT" in t:
        hints.append("OAuth 'invalid_grant' -> refresh token expirado/revogado/malformado (espaco/quebra de linha?).")
    elif status == 401 or "UNAUTHENTICATED" in t:
        hints.append("401 / UNAUTHENTICATED -> credencial invalida (reautorize o OAuth, ou cheque a service account).")
    if "USER_PERMISSION_DENIED" in t:
        hints.append("USER_PERMISSION_DENIED -> o usuario/SA nao tem acesso ao customer_id (adicione no Google Ads/MCC).")
    if "DEVELOPER_TOKEN_NOT_APPROVED" in t or "DEVELOPER_TOKEN_PROHIBITED" in t:
        hints.append("DEVELOPER_TOKEN_NOT_APPROVED -> developer token sem acesso de producao (use conta de teste ou peca aprovacao).")
    if "CUSTOMER_NOT_ENABLED" in t:
        hints.append("CUSTOMER_NOT_ENABLED -> a conta Google Ads nao esta ativa/habilitada para API.")
    if "LOGIN_CUSTOMER_ID" in t or "AUTHORIZATION_ERROR" in t:
        hints.append("login-customer-id incorreto -> confira GOOGLE_ADS_LOGIN_CUSTOMER_ID (deve ser o MCC).")
    if "CUSTOMER_NOT_FOUND" in t or ("CUSTOMER_ID" in t and "NOT" in t):
        hints.append("customer_id sem acesso -> confira GOOGLE_ADS_CUSTOMER_ID e o vinculo MCC<->conta.")
    if not hints:
        hints.append(f"HTTP {status} — verifique a resposta da API (detalhe nao classificado).")
    return " | ".join(hints)


def _sanitize(body: str, settings) -> str:
    """Trunca e remove identificadores de conta do trecho exibido."""
    snippet = (body or "")[:400]
    for ident in (settings.google_ads_customer_id, settings.google_ads_login_customer_id):
        if ident:
            snippet = snippet.replace(ident, "<account_id>")
            snippet = snippet.replace(ident.replace("-", ""), "<account_id>")
    return snippet


async def main() -> int:
    settings = get_settings()
    status = settings.google_ads_auth_status()

    print("=== Google Ads — smoke (read-only) ===")
    print(f"auth_mode (resolvido): {status['mode']}")
    print(f"ready                : {status['ready']}")
    print(f"missing (so nomes)   : {status['missing']}")

    if not status["ready"]:
        print("\n[STOP] Google Ads nao esta pronto — NAO vou chamar a API.")
        print("Preencha em backend/.env (sem commitar) UM dos modos:")
        print("  - oauth_refresh_token: GOOGLE_ADS_CLIENT_ID + CLIENT_SECRET + REFRESH_TOKEN")
        print("  - service_account    : GOOGLE_ADS_SERVICE_ACCOUNT_JSON ou GOOGLE_ADS_JSON_KEY_FILE_PATH")
        print("  + comuns: DEVELOPER_TOKEN, LOGIN_CUSTOMER_ID, CUSTOMER_ID")
        return 2

    geo = GeoLanguageMapper.map(COUNTRY, COUNTRY_CODE)
    print(f"\nGeo: {geo['Pais_Geo'] if 'Pais_Geo' in geo else geo['País_Geo']} | geo_target={geo['Criteria_ID']} | lang_const={geo['language_constant']}")

    client = GoogleAdsKeywordPlannerClient(settings)
    print(f"client.enabled={client.enabled} | client.auth_mode={client.auth_mode}")
    print(f"\nChamando generateKeywordIdeas(seed='{SEED}', pageSize={PAGE_SIZE}) ...")

    try:
        results = await client.generate_keyword_ideas(
            seed_keyword=SEED,
            geo_target=geo["Criteria_ID"] or 2826,
            language_constant=geo["language_constant"] or 1000,
            page_size=PAGE_SIZE,
        )
    except Exception as exc:  # noqa: BLE001
        status_code = getattr(getattr(exc, "response", None), "status_code", 0)
        body = getattr(getattr(exc, "response", None), "text", "") or str(exc)
        print("\n[FALHA] A chamada Keyword Planner NAO funcionou.")
        print(f"  tipo: {type(exc).__name__}  http={status_code}")
        print(f"  causa provavel: {_classify_http_error(status_code, body)}")
        print(f"  resposta (trecho sanitizado): {_sanitize(body, settings)}")
        return 1

    print("\n[OK] Keyword Planner respondeu.")
    print(f"  auth mode usado : {client.auth_mode}")
    print(f"  total de ideias : {len(results)}")
    for item in results[:3]:
        m = item.get("keywordIdeaMetrics") or {}
        vol = m.get("avgMonthlySearches")
        cpc_micros = m.get("averageCpcMicros")
        cpc = round((int(cpc_micros) / 1_000_000), 2) if cpc_micros else None
        comp = m.get("competition")
        print(f"   - {_mask(item.get('text', ''))} | vol={vol} | cpc={cpc} | comp={comp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
