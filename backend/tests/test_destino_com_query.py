"""O portão de destino não avalia OUTRA página quando a URL é a query.

Card 106, 09/10/2026: `?post_type=r&p=2477` foi lida como a home (a leitura
pública descarta a query), e os bloqueios da home viraram bloqueios da LP.
"""
from __future__ import annotations

import pytest

from app.routers import trafego


def test_url_identificada_pela_query_e_recusada_sem_ler(monkeypatch):
    monkeypatch.setattr(trafego.pqf, "fetch_public_https_chain",
                        lambda *a, **k: pytest.fail("leu outra página"))
    with pytest.raises(trafego.DestinoIlegivel, match="query string"):
        trafego._ler_destino_ao_vivo("https://creditoup.com.br/?post_type=r&p=2477")


def test_permalink_sem_query_continua_sendo_lido(monkeypatch):
    lidas = []

    def fake(url, **k):
        lidas.append(url)
        return {"status": 200, "html": "<html><body>ok</body></html>", "final_url": url}

    monkeypatch.setattr(trafego.pqf, "fetch_public_https_chain", fake)
    try:
        trafego._ler_destino_ao_vivo("https://creditoup.com.br/r/guia-gas-do-povo/")
    except trafego.DestinoIlegivel:
        pass  # outras checagens do leitor podem recusar o HTML falso; a leitura aconteceu
    assert lidas and all(u == "https://creditoup.com.br/r/guia-gas-do-povo/" for u in lidas)


def test_o_avaliador_transforma_a_recusa_em_destino_sem_evidencia(monkeypatch):
    import time

    monkeypatch.setattr(trafego.pqf, "fetch_public_https_chain",
                        lambda *a, **k: pytest.fail("leu outra página"))
    d = trafego._avaliar_destino("https://creditoup.com.br/?post_type=r&p=2477", recibo=None,
                                 promessa="", papel_declarado="paid_destination", agora=time.time())
    assert "query string" in d.detalhe_da_leitura
    assert d.avaliacao.paid_destination_ready is False
