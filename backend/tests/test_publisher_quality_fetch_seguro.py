"""O leitor público read-only: SSRF, redirecionamento e teto de bytes.

A leitura pública é a ÚNICA superfície deste trabalho que fala com a rede. Ela
não escreve em lugar nenhum — mas um leitor mal fechado é como um processo
read-only alcança um endereço interno. Estes testes provam a recusa; nenhum
deles abre socket.
"""
from __future__ import annotations

import pytest

from app.publisher_quality import fetch as fetch_mod
from app.publisher_quality.fetch import (
    USER_AGENT_PADRAO,
    _RecordingRedirectHandler,
    fetch_public_https_chain,
    validate_public_https_target,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://exemplo.com.br/x",            # não é https
        "ftp://exemplo.com.br/x",
        "https://127.0.0.1/x",                # loopback
        "https://localhost/x",
        "https://10.0.0.1/x",                 # RFC1918
        "https://192.168.1.1/x",
        "https://169.254.169.254/latest/meta-data/",   # metadata de nuvem
        "https://[::1]/x",
        "https://user:senha@host/x",                   # credencial embutida
        "https:///semhost",
        "",
    ],
)
def test_alvo_inseguro_e_recusado_antes_de_qualquer_leitura(url):
    with pytest.raises(ValueError):
        validate_public_https_target(url)


@pytest.fixture()
def dns_publico(monkeypatch):
    """Resolve qualquer nome para um IP público, sem tocar na rede.

    Sem isto, um host de exemplo que não existe cai no `gaierror` e é recusado
    como privado — que é o comportamento CORRETO do validador (ele fecha por
    ausência de resolução) e por isso mesmo esconderia o caminho feliz.
    """
    monkeypatch.setattr(
        fetch_mod.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )


def test_alvo_publico_e_normalizado_sem_query_nem_fragmento(dns_publico):
    """Query fora do artefato: é por ali que `gclid` e id de campanha entram."""
    assert (
        validate_public_https_target("https://Exemplo.com.BR/r/pagina/?gclid=abc#topo")
        == "https://exemplo.com.br/r/pagina/"
    )


def test_caminho_vazio_vira_barra(dns_publico):
    assert validate_public_https_target("https://exemplo.com.br") == "https://exemplo.com.br/"


def test_nome_que_nao_resolve_e_tratado_como_privado():
    """Fecha por ausência: sem resolução não há como afirmar que o alvo é público."""
    with pytest.raises(ValueError):
        validate_public_https_target("https://host-que-nao-existe.invalid/x")


def test_fetch_com_cadeia_recusa_alvo_privado_sem_abrir_socket():
    with pytest.raises(ValueError):
        fetch_public_https_chain("https://169.254.169.254/latest/meta-data/")


def test_o_handler_valida_o_salto_antes_de_anotar():
    """Anotar antes de validar transformaria a cadeia em registro do que foi
    TENTADO. Ela precisa ser registro do que foi permitido."""
    handler = _RecordingRedirectHandler()

    class _Req:
        full_url = "https://exemplo.com.br/r/pagina/"

    with pytest.raises(ValueError):
        handler.redirect_request(_Req(), None, 302, "Found", {}, "https://127.0.0.1/interno")
    assert handler.saltos == []


def test_user_agent_padrao_e_nomeado_e_read_only():
    """A comparação rastreador × usuário depende de os dois lados pedirem a mesma
    página com user-agents DIFERENTES e conhecidos."""
    assert "read-only" in USER_AGENT_PADRAO
    assert USER_AGENT_PADRAO.startswith("VOLC-")
