"""backend/tests: a sessão não lê o google-ads.yaml real nem refresca OAuth (conftest do backend)."""
import builtins
import os

import pytest

from volc_ads import hermetico_testes as h


def _abertos(monkeypatch):
    vistos = []
    original = builtins.open

    def espia(arquivo, *a, **k):
        vistos.append(os.path.abspath(os.fspath(arquivo)) if isinstance(arquivo, (str, os.PathLike)) else arquivo)
        return original(arquivo, *a, **k)
    monkeypatch.setattr(builtins, "open", espia)
    return vistos


def test_cliente_ads_nao_le_o_yaml_real(monkeypatch):
    from volc_ads.gads import client
    vistos = _abertos(monkeypatch)
    assert os.environ["GOOGLE_ADS_CONFIGURATION_FILE_PATH"] == h.CAMINHO_INEXISTENTE
    with pytest.raises(Exception) as erro:
        client.cliente.__wrapped__("1234567890")
    assert not isinstance(erro.value, AssertionError)
    real = os.path.expanduser("~/google-ads.yaml")
    assert real not in vistos, "o google-ads.yaml real foi aberto"


def test_refresh_de_oauth_recusa_sem_rede():
    from google.oauth2.credentials import Credentials
    c = Credentials(token=None, refresh_token="falso", client_id="falso", client_secret="falso",
                    token_uri="https://oauth2.googleapis.com/token")
    with pytest.raises(h.RefreshBloqueado):
        c.refresh(None)


def test_broker_do_lab_aponta_para_caminho_inexistente():
    assert os.environ["VOLC_GOOGLE_OAUTH_FILE"].startswith("/nonexistent/")
