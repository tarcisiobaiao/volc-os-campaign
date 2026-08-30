"""
Google Ads Keyword Planner client — generateKeywordIdeas, with DUAL auth.

Ported from n8n-peneirador-kw.json node "🔍 Keyword Planner API1":
  POST https://googleads.googleapis.com/v21/customers/{customer_id}:generateKeywordIdeas
  headers: developer-token, login-customer-id (MCC)
  body: geoTargetConstants, language, keywordSeed, historicalMetricsOptions

Auth modes (GOOGLE_ADS_AUTH_MODE, resolved by Settings.google_ads_auth_status):
  - service_account     : sign a RS256 JWT with the SA private key, exchange it
                          for an access token (urn:...:jwt-bearer). Supports an
                          optional impersonated subject (domain-wide delegation).
  - oauth_refresh_token : exchange a refresh token for an access token.

Both modes require GOOGLE_ADS_DEVELOPER_TOKEN + LOGIN_CUSTOMER_ID + CUSTOMER_ID.
The n8n node had a hardcoded developer_token / mcc_id / customer_id; those are
MIGRATED to env and never copied into code. When unconfigured, `enabled` is
False and the mining pipeline uses a mock. Secrets are never logged.
"""
from __future__ import annotations

import base64
import calendar
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings

_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DEFAULT_SA_TOKEN_URL = "https://oauth2.googleapis.com/token"
_ADWORDS_SCOPE = "https://www.googleapis.com/auth/adwords"
_JWT_BEARER_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
_API_VERSION = "v21"
_MICROS = 1_000_000


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class GoogleAdsKeywordPlannerClient:
    name = "google_ads"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.developer_token = settings.google_ads_developer_token or ""
        self.customer_id = (settings.google_ads_customer_id or "").replace("-", "")
        self.login_customer_id = (settings.google_ads_login_customer_id or "").replace("-", "")
        status = settings.google_ads_auth_status()
        self.auth_mode = status["mode"]
        self._ready = status["ready"]

    @property
    def enabled(self) -> bool:
        return self._ready

    # ---- auth ---------------------------------------------------------------
    def _service_account_info(self) -> Dict[str, Any]:
        raw = self.settings.google_ads_service_account_json
        if raw:
            return json.loads(raw)
        path = self.settings.google_ads_json_key_file_path
        if path:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        raise RuntimeError(
            "Service account não configurada (GOOGLE_ADS_SERVICE_ACCOUNT_JSON ou GOOGLE_ADS_JSON_KEY_FILE_PATH)."
        )

    def _sign_sa_jwt(self, info: Dict[str, Any]) -> tuple[str, str]:
        """Return (signed_jwt, token_uri). Requires `cryptography` (RS256)."""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "Modo service_account requer o pacote 'cryptography' instalado."
            ) from exc

        token_uri = info.get("token_uri") or _DEFAULT_SA_TOKEN_URL
        now = int(time.time())
        header: Dict[str, Any] = {"alg": "RS256", "typ": "JWT"}
        if info.get("private_key_id"):
            header["kid"] = info["private_key_id"]
        claims: Dict[str, Any] = {
            "iss": info["client_email"],
            "scope": _ADWORDS_SCOPE,
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
        }
        subject = self.settings.google_ads_impersonated_email
        if subject:
            claims["sub"] = subject

        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(claims, separators=(",", ":")).encode())
        )
        private_key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
        signature = private_key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
        return f"{signing_input}.{_b64url(signature)}", token_uri

    async def _sa_access_token(self, client: httpx.AsyncClient) -> str:
        info = self._service_account_info()
        assertion, token_uri = self._sign_sa_jwt(info)
        resp = await client.post(
            token_uri, data={"grant_type": _JWT_BEARER_GRANT, "assertion": assertion}
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("Google Ads service-account token exchange returned no access_token.")
        return token

    async def _oauth_access_token(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            _OAUTH_TOKEN_URL,
            data={
                "client_id": self.settings.google_ads_client_id,
                "client_secret": self.settings.google_ads_client_secret,
                "refresh_token": self.settings.google_ads_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("Google Ads OAuth returned no access_token.")
        return token

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if self.auth_mode == "service_account":
            return await self._sa_access_token(client)
        return await self._oauth_access_token(client)

    # ---- request ------------------------------------------------------------
    @staticmethod
    def _year_month_range() -> Dict[str, Any]:
        """Last-12-months window, matching the n8n $now.minus(12,'months') body."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=365)
        return {
            "start": {"month": calendar.month_name[start.month].upper(), "year": start.year},
            "end": {"month": calendar.month_name[now.month].upper(), "year": now.year},
        }

    async def generate_keyword_ideas(
        self,
        *,
        seed_keyword: str,
        geo_target: int,
        language_constant: int,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return the raw `results` array from generateKeywordIdeas (read-only)."""
        if not self.enabled:
            raise RuntimeError("Google Ads not configured (GOOGLE_ADS_*).")

        url = f"https://googleads.googleapis.com/{_API_VERSION}/customers/{self.customer_id}:generateKeywordIdeas"
        body = {
            "customerId": self.customer_id,
            "geoTargetConstants": [f"geoTargetConstants/{geo_target}"],
            "language": f"languageConstants/{language_constant}",
            "includeAdultKeywords": False,
            "keywordPlanNetwork": "GOOGLE_SEARCH_AND_PARTNERS",
            "pageSize": page_size,
            "historicalMetricsOptions": {
                "includeAverageCpc": True,
                "yearMonthRange": self._year_month_range(),
            },
            "keywordSeed": {"keywords": [seed_keyword]},
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            access = await self._access_token(client)
            headers = {
                "Authorization": f"Bearer {access}",
                "developer-token": self.developer_token,
                "Content-Type": "application/json",
            }
            if self.login_customer_id:
                headers["login-customer-id"] = self.login_customer_id
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        return data.get("results") or []
