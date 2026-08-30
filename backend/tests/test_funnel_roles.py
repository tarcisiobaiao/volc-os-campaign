"""Papéis (LP/Pre-sell/Solução) + sufixos de slug do funil, com refs reescritas."""
from app.entities.funnel_roles import apply_roles_and_slugs, role_for_position


def _sample():
    pages = [
        {"position": 1, "page_title": "Guía SOAT", "subtitles": ["H2: qué es"],
         "internal_links": ["Gatillo → /consultar-soat-runt-placa"]},
        {"position": 2, "page_title": "Consultas", "subtitles": ["1. Vigente (Ir a /consultar-soat-vigente-placa-gratis)"],
         "internal_links": ["Gatillo → /consultar-soat-vigente-placa-gratis"]},
        {"position": 3, "page_title": "Vigente", "subtitles": [],
         "internal_links": ["Volver → /guia-soat-colombia-2026"]},
    ]
    writing_jobs = [
        {"writer_briefing": {"page_num": 1, "current_url": "guia-soat-colombia-2026", "cta_link": "/consultar-soat-runt-placa"}},
        {"writer_briefing": {"page_num": 2, "current_url": "consultar-soat-runt-placa", "cta_link": "/consultar-soat-vigente-placa-gratis"}},
        {"writer_briefing": {"page_num": 3, "current_url": "consultar-soat-vigente-placa-gratis", "cta_link": "/guia-soat-colombia-2026"}},
    ]
    return pages, writing_jobs


def test_role_for_position():
    assert role_for_position(1) == ("landing", "Landing Page (Pouso)", "")
    assert role_for_position(2) == ("presell", "Pre-sell", "-pr")
    assert role_for_position(3) == ("solution", "Página Solução 1", "-p1")
    assert role_for_position(5) == ("solution", "Página Solução 3", "-p3")


def test_roles_labels_and_slugs():
    pages, wjs = apply_roles_and_slugs(*_sample())

    assert [p["role_label"] for p in pages] == ["Landing Page (Pouso)", "Pre-sell", "Página Solução 1"]

    # slug própria: P1 intacta; P2 -pr; P3 -p1
    urls = [j["writer_briefing"]["current_url"] for j in wjs]
    assert urls == ["guia-soat-colombia-2026", "consultar-soat-runt-placa-pr", "consultar-soat-vigente-placa-gratis-p1"]

    # referências cruzadas reescritas p/ a slug nova
    assert pages[0]["internal_links"][0] == "Gatillo → /consultar-soat-runt-placa-pr"
    assert wjs[0]["writer_briefing"]["cta_link"] == "/consultar-soat-runt-placa-pr"
    assert "(Ir a /consultar-soat-vigente-placa-gratis-p1)" in pages[1]["subtitles"][0]
    assert wjs[1]["writer_briefing"]["cta_link"] == "/consultar-soat-vigente-placa-gratis-p1"

    # link/CTA que aponta pra P1 (Landing) permanece intacto
    assert pages[2]["internal_links"][0] == "Volver → /guia-soat-colombia-2026"
    assert wjs[2]["writer_briefing"]["cta_link"] == "/guia-soat-colombia-2026"


def test_idempotent():
    pages, wjs = apply_roles_and_slugs(*_sample())
    pages2, wjs2 = apply_roles_and_slugs(pages, wjs)  # roda de novo
    assert [j["writer_briefing"]["current_url"] for j in wjs2] == [j["writer_briefing"]["current_url"] for j in wjs]
    assert wjs2[1]["writer_briefing"]["cta_link"] == "/consultar-soat-vigente-placa-gratis-p1"  # sem duplo sufixo
