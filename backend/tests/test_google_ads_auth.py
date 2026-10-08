"""
Dual Google Ads auth: config readiness + service-account JWT (RS256) signing.
Fully offline (a throwaway RSA key is generated in-test). No secrets printed.

Run:  cd backend && pytest -q
"""
from __future__ import annotations

import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings
from app.services.google_ads import GoogleAdsKeywordPlannerClient

# Pin EVERY Google Ads field so tests are isolated from the local .env
# (the operator may have some of these configured for real).
_BASE = dict(
    google_ads_auth_mode="auto",
    google_ads_developer_token="dev-token",
    google_ads_login_customer_id="111-222-3333",
    google_ads_customer_id="444-555-6666",
    google_ads_client_id="",
    google_ads_client_secret="",
    google_ads_refresh_token="",
    google_ads_service_account_json="",
    google_ads_json_key_file_path="",
    google_ads_impersonated_email="",
)


def _settings(**over) -> Settings:
    # init kwargs override .env / os.environ in pydantic-settings
    return Settings(**{**_BASE, **over})


# --- readiness / mode resolution ---------------------------------------------
def test_status_none_when_no_auth():
    s = _settings(google_ads_developer_token="", google_ads_login_customer_id="", google_ads_customer_id="")
    st = s.google_ads_auth_status()
    assert st["mode"] == "none" and st["ready"] is False
    assert any("CUSTOMER_ID" in m for m in st["missing"])


def test_status_oauth_ready_auto():
    s = _settings(
        google_ads_client_id="cid", google_ads_client_secret="sec", google_ads_refresh_token="rt"
    )
    st = s.google_ads_auth_status()
    assert st["mode"] == "oauth_refresh_token" and st["ready"] is True and st["missing"] == []
    assert s.has_google_ads is True


def test_status_service_account_ready_auto_no_refresh_needed():
    # SA present, NO refresh token -> still ready (requirement #5)
    s = _settings(google_ads_service_account_json='{"client_email":"x","private_key":"y"}')
    st = s.google_ads_auth_status()
    assert st["mode"] == "service_account" and st["ready"] is True
    assert "GOOGLE_ADS_REFRESH_TOKEN" not in st["missing"]


def test_status_service_account_via_file_path():
    s = _settings(google_ads_json_key_file_path="/tmp/whatever.json")
    assert s.google_ads_auth_status()["mode"] == "service_account"


def test_explicit_mode_oauth_reports_missing():
    s = _settings(google_ads_auth_mode="oauth_refresh_token")  # no oauth creds
    st = s.google_ads_auth_status()
    assert st["mode"] == "oauth_refresh_token" and st["ready"] is False
    assert "GOOGLE_ADS_CLIENT_ID" in st["missing"]


def test_explicit_mode_service_account_reports_missing():
    s = _settings(google_ads_auth_mode="service_account")  # no SA
    st = s.google_ads_auth_status()
    assert st["mode"] == "service_account" and st["ready"] is False
    assert any("SERVICE_ACCOUNT_JSON" in m for m in st["missing"])


def test_missing_common_fields_block_ready():
    s = _settings(
        google_ads_customer_id="",
        google_ads_client_id="c", google_ads_client_secret="s", google_ads_refresh_token="r",
    )
    st = s.google_ads_auth_status()
    assert st["ready"] is False and "GOOGLE_ADS_CUSTOMER_ID" in st["missing"]


def test_developer_token_is_optional():
    """O developer token saiu de uso em 09/09/2026: o nível de acesso agora é do
    projeto Google Cloud. Medido em 08/10/2026: v25 sem o header devolve 200.
    Exigi-lo deixaria a mineração em mock numa máquina que só tem OAuth."""
    s = _settings(
        google_ads_developer_token="",
        google_ads_client_id="c", google_ads_client_secret="s", google_ads_refresh_token="r",
    )
    st = s.google_ads_auth_status()
    assert st["ready"] is True and st["missing"] == []


# --- service-account JWT signing (real RS256, throwaway key) ------------------
def test_service_account_jwt_signs_and_verifies():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    info = {
        "type": "service_account",
        "client_email": "pautador@proj.iam.gserviceaccount.com",
        "private_key_id": "kid-123",
        "private_key": private_pem,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    s = _settings(
        google_ads_service_account_json=json.dumps(info),
        google_ads_impersonated_email="owner@empresa.com",
    )
    client = GoogleAdsKeywordPlannerClient(s)
    assert client.enabled is True and client.auth_mode == "service_account"

    jwt, token_uri = client._sign_sa_jwt(info)
    assert token_uri == "https://oauth2.googleapis.com/token"
    parts = jwt.split(".")
    assert len(parts) == 3

    def _b64d(seg: str) -> bytes:
        return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))

    header = json.loads(_b64d(parts[0]))
    claims = json.loads(_b64d(parts[1]))
    assert header["alg"] == "RS256" and header["kid"] == "kid-123"
    assert claims["iss"] == info["client_email"]
    assert claims["scope"] == "https://www.googleapis.com/auth/adwords"
    assert claims["aud"] == info["token_uri"]
    assert claims["sub"] == "owner@empresa.com"  # impersonation subject

    # signature must verify with the public key
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    key.public_key().verify(_b64d(parts[2]), signing_input, padding.PKCS1v15(), hashes.SHA256())


# --- request: versão e headers -------------------------------------------------
import httpx as _httpx

_ASYNC_CLIENT_REAL = _httpx.AsyncClient


class _Captura:
    """Substitui httpx.AsyncClient e guarda as requisições, sem rede.

    Guarda a classe real ANTES do monkeypatch: o patch troca o atributo do
    próprio módulo httpx, e instanciar `httpx.AsyncClient` aqui dentro seria
    instanciar a si mesma.
    """

    pedidos: list = []

    def __init__(self, *a, **k):
        httpx = _httpx

        def responder(req):
            _Captura.pedidos.append(req)
            if req.url.host == "oauth2.googleapis.com":
                return httpx.Response(200, json={"access_token": "tok"})
            return httpx.Response(200, json={"results": [{"text": "x"}]})

        self._c = _ASYNC_CLIENT_REAL(transport=httpx.MockTransport(responder))

    async def __aenter__(self):
        return self._c

    async def __aexit__(self, *exc):
        await self._c.aclose()


def _rodar_ideias(monkeypatch, **over):
    import asyncio

    import app.services.google_ads as mod

    _Captura.pedidos = []
    monkeypatch.setattr(mod.httpx, "AsyncClient", _Captura)
    s = _settings(google_ads_client_id="c", google_ads_client_secret="s",
                  google_ads_refresh_token="r", **over)
    cli = GoogleAdsKeywordPlannerClient(s)
    out = asyncio.run(cli.generate_keyword_ideas(
        seed_keyword="fgts", geo_target=2076, language_constant=1014))
    return out, [p for p in _Captura.pedidos if p.url.host == "googleads.googleapis.com"]


def test_keyword_ideas_usa_v25_e_nao_v21(monkeypatch):
    """v21 devolve 404 desde set/2026 (medido em 08/10/2026)."""
    out, pedidos = _rodar_ideias(monkeypatch)
    assert out == [{"text": "x"}]
    assert len(pedidos) == 1
    assert pedidos[0].url.path == "/v25/customers/4445556666:generateKeywordIdeas"


def test_keyword_ideas_sem_token_nao_manda_header(monkeypatch):
    _, pedidos = _rodar_ideias(monkeypatch, google_ads_developer_token="")
    assert "developer-token" not in pedidos[0].headers
    assert pedidos[0].headers["login-customer-id"] == "1112223333"
