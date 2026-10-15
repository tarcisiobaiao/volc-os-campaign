"""Hermetismo de credencial Google para sessões de teste (backend/tests e raiz).

Chamado no import do conftest, antes de qualquer cliente: aponta o google-ads.yaml e
o google-oauth.json do Freedom Lab para caminhos que não existem e faz qualquer
refresh de OAuth recusar sem rede. Só `restaurar()` — usado pela fixture
`ambiente_real` com VOLC_TESTES_AMBIENTE_REAL=1 — devolve o real, e só para o seu teste.
"""
from __future__ import annotations

import os

CAMINHO_INEXISTENTE = "/nonexistent/volc-testes-hermeticos/google-ads.yaml"
VARIAVEIS = {
    "GOOGLE_ADS_CONFIGURATION_FILE_PATH": CAMINHO_INEXISTENTE,
    "VOLC_GOOGLE_OAUTH_FILE": "/nonexistent/volc-testes-hermeticos/google-oauth.json",
}
_original_refresh = None


class RefreshBloqueado(RuntimeError):
    pass


def _recusa_refresh(self, request):  # noqa: ARG001 — assinatura de Credentials.refresh
    raise RefreshBloqueado("refresh de OAuth bloqueado na sessão de testes "
                           "(VOLC_TESTES_AMBIENTE_REAL=1 + fixture ambiente_real para o real)")


def aplicar() -> None:
    global _original_refresh
    for k, v in VARIAVEIS.items():
        os.environ[k] = v
    try:
        from google.oauth2 import credentials as _cred
    except ImportError:
        return
    if _original_refresh is None:
        _original_refresh = _cred.Credentials.refresh
    _cred.Credentials.refresh = _recusa_refresh


def restaurar(monkeypatch, ambiente_intacto: dict) -> None:
    """Desfaz o bloqueio só dentro de um teste (monkeypatch devolve no teardown)."""
    for k in VARIAVEIS:
        if ambiente_intacto.get(k):
            monkeypatch.setenv(k, ambiente_intacto[k])
        else:
            monkeypatch.delenv(k, raising=False)
    if _original_refresh is not None:
        from google.oauth2 import credentials as _cred
        monkeypatch.setattr(_cred.Credentials, "refresh", _original_refresh)
