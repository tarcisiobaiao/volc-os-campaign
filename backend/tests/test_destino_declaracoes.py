"""Declarações de adtech/chrome do projeto chegam ao portão de campanha, e a
ausência é explícita (09/10/2026). Dica de conexão ≠ recurso carregado."""
from __future__ import annotations

import time

from app.routers import trafego

URL = "https://creditoup.com.br/r/guia-cursos-senac/"
HTML = ("<html><head>"
        "<link rel='dns-prefetch' href='https://office.joinads.me'>"
        "<link rel='preload' as='script' href='https://script.joinads.me/x.js'>"
        "</head><body class='single postid-2306'><main><p>Guia.</p></main>"
        "<footer><a href='https://www.fabiolobo.com.br'>Fabio Lobo</a></footer></body></html>")


def _destino(monkeypatch, wordpress):
    monkeypatch.setattr(trafego.pqf, "fetch_public_https_chain",
                        lambda url, **k: {"status": 200, "html": HTML, "hops": [], "headers": {},
                                          "sha256": "x", "url": url, "final_url": url})
    return trafego._avaliar_destino(URL, recibo=None, promessa="", papel_declarado="paid_destination",
                                    agora=time.time(),
                                    declaracoes=trafego._declaracoes_do_projeto(wordpress))


def _achados(d):
    return [(a.codigo, a.evidencia) for a in d.avaliacao.bloqueios + d.avaliacao.riscos]


def test_sem_declaracao_a_ausencia_vai_escrita_no_destino(monkeypatch):
    d = _destino(monkeypatch, {"project_id": 2, "wp_url": "https://creditoup.com.br"})
    assert d.declaracoes_do_projeto["fonte"].startswith("ausente")
    assert d.para_json()["declaracoes_do_projeto"]["adtech"] == ()
    codigos = [c for c, _ in _achados(d)]
    assert "SCRIPT_TERCEIRO_NAO_DECLARADO" in codigos and "LINK_EXTERNO_NO_CHROME" in codigos


def test_dica_de_conexao_e_recurso_carregado_sao_distinguidos(monkeypatch):
    d = _destino(monkeypatch, None)
    tipos = {e["host"]: e["tipo"] for c, e in _achados(d) if c == "SCRIPT_TERCEIRO_NAO_DECLARADO"}
    assert tipos["office.joinads.me"] == "dica_de_conexao"
    assert tipos["script.joinads.me"] == "recurso_carregado"


def test_declaracao_do_projeto_chega_ao_portao(monkeypatch):
    d = _destino(monkeypatch, {"project_id": 2, "adtech_declarada": ["joinads.me"],
                               "chrome_declarado_pelo_site": "fabiolobo.com.br"})
    assert d.declaracoes_do_projeto["fonte"].startswith("project_wordpress")
    codigos = [c for c, _ in _achados(d)]
    assert "SCRIPT_TERCEIRO_NAO_DECLARADO" not in codigos
    assert "LINK_EXTERNO_NO_CHROME" not in codigos


def test_declarar_adtech_nao_libera_link_de_navegacao(monkeypatch):
    """Adtech autoriza RECURSO técnico, não navegação: o link do rodapé segue."""
    d = _destino(monkeypatch, {"project_id": 2, "adtech_declarada": ["joinads.me", "fabiolobo.com.br"]})
    assert "LINK_EXTERNO_NO_CHROME" in [c for c, _ in _achados(d)]
