"""Leitura do destino de campanha: URL real na requisição, sanitização só nos
registros, e prova de QUE página veio.

Card 106, 09/10/2026: a leitura descartava a query e `?post_type=r&p=2477` foi
lida como a home (200, "home blog"); os bloqueios da home viraram bloqueios da
LP. A contenção do mesmo dia (recusar qualquer query) foi trocada por isto.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.publisher_quality import fetch as pqf
from app.routers import trafego

LP = "https://creditoup.com.br/?post_type=r&p=2477"
SEGREDO = "abc123segredo"


# ── segurança × requisição × recibo ─────────────────────────────────────────

def test_permalink_publico_e_requisitado_como_e():
    url = "https://creditoup.com.br/r/guia-gas-do-povo/"
    assert pqf.alvo_de_requisicao(url) == url
    assert pqf.url_para_recibo(url) == url


def test_query_que_identifica_conteudo_vai_na_requisicao_e_aparece_no_recibo():
    assert pqf.alvo_de_requisicao(LP) == LP
    assert "p=2477" in pqf.url_para_recibo(LP) and "post_type=r" in pqf.url_para_recibo(LP)


def test_tracking_vai_na_requisicao_e_vira_fingerprint_no_recibo():
    url = "https://creditoup.com.br/r/x/?utm_source=google&gclid=Cj0KCQ-segredo"
    assert pqf.alvo_de_requisicao(url) == url
    recibo = pqf.url_para_recibo(url)
    assert "Cj0KCQ-segredo" not in recibo and "google" not in recibo
    assert "gclid=~" in recibo and "utm_source=~" in recibo
    # mesmo valor → mesmo fingerprint (comparável sem expor)
    assert recibo == pqf.url_para_recibo(url)


def test_query_sensivel_nao_vaza_no_recibo():
    url = f"https://creditoup.com.br/?p=2477&preview=true&preview_nonce={SEGREDO}"
    assert SEGREDO not in pqf.url_para_recibo(url)
    assert "p=2477" in pqf.url_para_recibo(url)


def test_fragmento_e_credencial_nao_sao_requisitados():
    assert pqf.alvo_de_requisicao("https://creditoup.com.br/r/x/?p=1#topo").endswith("?p=1")
    with pytest.raises(ValueError):
        pqf.alvo_de_requisicao("https://usuario:senha@creditoup.com.br/")


@pytest.mark.parametrize("url", ["https://127.0.0.1/x", "https://localhost/", "http://creditoup.com.br/",
                                 "https://10.0.0.5/?p=1"])
def test_destino_privado_ou_proibido_e_recusado(url):
    with pytest.raises(ValueError):
        pqf.alvo_de_requisicao(url)


def test_redirecionamento_legitimo_e_anotado_sanitizado_e_revalidado(monkeypatch):
    monkeypatch.setattr(pqf, "_host_is_private", lambda h: h == "interno.local")
    h = pqf._RecordingRedirectHandler(preservar_query=True)
    req = SimpleNamespace(full_url=f"https://creditoup.com.br/?p=2477&preview_nonce={SEGREDO}",
                          get_method=lambda: "GET", headers={}, data=None,
                          unredirected_hdrs={}, origin_req_host="creditoup.com.br",
                          get_full_url=lambda: "", timeout=10)
    monkeypatch.setattr(pqf.HTTPRedirectHandler, "redirect_request",
                        lambda self, *a, **k: "pedido-seguinte")
    h.redirect_request(req, None, 301, "Moved", {}, "https://creditoup.com.br/r/guia-gas-do-povo/")
    (salto,) = h.saltos
    assert salto["to"] == "https://creditoup.com.br/r/guia-gas-do-povo/" and salto["status"] == 301
    assert SEGREDO not in salto["from"]
    # salto para host privado levanta antes de virar linha
    with pytest.raises(ValueError):
        pqf._SafeRedirectHandler.redirect_request(h, req, None, 302, "x", {}, "https://interno.local/")


def test_leitura_com_query_devolve_so_a_forma_sanitizada(monkeypatch):
    class Resp:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def geturl(self):
            return f"https://creditoup.com.br/?p=2477&preview_nonce={SEGREDO}"

        def read(self, n):
            return b"<html><body class='postid-2477'>ok</body></html>"

    pedidos = []

    class Abridor:
        def open(self, request, timeout):
            pedidos.append(request.full_url)
            return Resp()

    monkeypatch.setattr(pqf, "build_opener", lambda *a: Abridor())
    monkeypatch.setattr(pqf, "_host_is_private", lambda h: False)
    r = pqf.fetch_public_https_chain(f"https://creditoup.com.br/?p=2477&preview_nonce={SEGREDO}",
                                     preservar_query=True)
    assert pedidos == [f"https://creditoup.com.br/?p=2477&preview_nonce={SEGREDO}"]  # a URL REAL foi pedida
    assert SEGREDO not in r["url"] and SEGREDO not in r["final_url"]
    assert "p=2477" in r["final_url"]


# ── o portão prova QUE página veio ───────────────────────────────────────────

def _leitor(status=200, html="<html><body class='single postid-2477'>LP</body></html>"):
    chamadas = []

    def ler(url, **k):
        chamadas.append((url, k.get("preservar_query")))
        return {"status": status, "html": html, "url": pqf.url_para_recibo(url),
                "final_url": pqf.url_para_recibo(url)}
    return ler, chamadas


def test_lp_por_query_e_lida_com_a_query_e_aceita_quando_e_ela(monkeypatch):
    ler, chamadas = _leitor()
    monkeypatch.setattr(trafego.pqf, "fetch_public_https_chain", ler)
    leituras = trafego._ler_destino_ao_vivo(LP)
    assert leituras and all(u == LP and pq is True for u, pq in chamadas)


@pytest.mark.parametrize("status, html, trecho", [
    (404, "<html><body class='error404'></body></html>", "HTTP 404"),
    (200, "<html><head><title>Página não encontrada - X</title></head><body class='error404'></body></html>",
     "soft-404"),
    (200, "<html><body class='home blog'>home</body></html>", "não declara esse id"),
    (200, "<html><body class='single postid-1741'>outro post</body></html>", "não declara esse id"),
])
def test_rascunho_soft404_e_outra_pagina_sao_destino_publico_nao_validado(monkeypatch, status, html, trecho):
    ler, _ = _leitor(status=status, html=html)
    monkeypatch.setattr(trafego.pqf, "fetch_public_https_chain", ler)
    with pytest.raises(trafego.DestinoIlegivel) as e:
        trafego._ler_destino_ao_vivo(LP)
    assert "destino público não validado" in str(e.value) and trecho in str(e.value)


def test_home_servida_no_lugar_de_permalink_e_recusada(monkeypatch):
    ler, _ = _leitor(html="<html><body class='home blog'>home</body></html>")
    monkeypatch.setattr(trafego.pqf, "fetch_public_https_chain", ler)
    with pytest.raises(trafego.DestinoIlegivel, match="home foi servida"):
        trafego._ler_destino_ao_vivo("https://creditoup.com.br/r/guia-gas-do-povo/")


def test_rascunho_vira_avaliacao_sem_evidencia_e_nao_achado_de_conteudo(monkeypatch):
    ler, _ = _leitor(status=404, html="<html><body class='error404'></body></html>")
    monkeypatch.setattr(trafego.pqf, "fetch_public_https_chain", ler)
    d = trafego._avaliar_destino(LP, recibo=None, promessa="", papel_declarado="paid_destination",
                                 agora=time.time())
    assert "destino público não validado" in d.detalhe_da_leitura
    assert d.avaliacao.paid_destination_ready is False
    codigos = {a.codigo for a in d.avaliacao.bloqueios}
    assert not codigos & {"CONTEUDO_ORIGINAL_INSUFICIENTE", "MARCA_GOVERNAMENTAL_COM_DESTINO_DIVERGENTE",
                          "LINK_EXTERNO_NO_CHROME"}
