"""Captura pública + keywords já existentes: preparação somente leitura.

Não minera, não aprova novo conjunto pago e não representa o fluxo HTTP.
É o input real e reproduzível da prova técnica do harness de Search.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from volc_ads import ponte  # noqa: F401 — import canônico do backend
from app.publisher_quality.fetch import fetch_public_https_chain
from volc_ads.gads.client import buscar, PoliticaRetry
from volc_ads.harness.search import Entrada, _gravar, sha


class _TextoVisivel(HTMLParser):
    ignorar = {"head", "script", "style", "nav", "footer", "header", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ocultos = []
        self.partes = []

    def handle_starttag(self, tag, attrs):
        if tag in self.ignorar:
            self.ocultos.append(tag)

    def handle_endtag(self, tag):
        if tag in self.ocultos:
            del self.ocultos[self.ocultos.index(tag):]

    def handle_data(self, data):
        if not self.ocultos and data.strip():
            self.partes.append(data.strip())


def snapshot(customer_id: str, login_customer_id: str) -> dict:
    def ler(query):
        return buscar(customer_id, query, login_customer_id=login_customer_id,
                      politica=PoliticaRetry(tentativas=1))

    campanhas = [{
        "id": str(r.campaign.id), "status": r.campaign.status.name,
        "channel": r.campaign.advertising_channel_type.name,
        "budget_micros": r.campaign_budget.amount_micros,
        "bidding_strategy": r.campaign.bidding_strategy_type.name,
    } for r in ler("SELECT campaign.id, campaign.status, campaign.advertising_channel_type, "
                   "campaign_budget.amount_micros, campaign.bidding_strategy_type FROM campaign "
                   "WHERE campaign.status != 'REMOVED' ORDER BY campaign.id")]
    anuncios = [{"group_id": str(r.ad_group.id), "id": str(r.ad_group_ad.ad.id),
                 "status": r.ad_group_ad.status.name}
                for r in ler("SELECT ad_group.id, ad_group_ad.ad.id, ad_group_ad.status "
                             "FROM ad_group_ad WHERE ad_group_ad.status != 'REMOVED' "
                             "ORDER BY ad_group_ad.ad.id")]
    return {"campaigns": campanhas, "ads": anuncios}


def capturar(pasta: Path, *, customer_id: str, login_customer_id: str,
             url: str, tema: str, slug: str, budget: float, cpc: float) -> Entrada:
    pasta.mkdir(parents=True, exist_ok=True)
    if (pasta / "input.json").exists():
        raise ValueError("captura já existe; não sobrescreva o run")
    antes = snapshot(customer_id, login_customer_id)
    _gravar(pasta / "snapshot-before.json", antes)
    rows = buscar(customer_id,
        "SELECT campaign.id, campaign.status, ad_group.id, ad_group.status, "
        "ad_group_criterion.criterion_id, ad_group_criterion.keyword.text, "
        "ad_group_criterion.keyword.match_type FROM ad_group_criterion "
        "WHERE campaign.status = 'ENABLED' AND ad_group.status = 'ENABLED' "
        "AND ad_group_criterion.status = 'ENABLED' AND ad_group_criterion.negative = FALSE "
        "AND ad_group_criterion.type = 'KEYWORD' ORDER BY ad_group_criterion.criterion_id",
        login_customer_id=login_customer_id, politica=PoliticaRetry(tentativas=1))
    kws, vistos, origem = [], set(), []
    for r in rows:
        text = r.ad_group_criterion.keyword.text
        origem.append({"campaign_id": str(r.campaign.id), "ad_group_id": str(r.ad_group.id),
                       "text": text, "match_type": r.ad_group_criterion.keyword.match_type.name})
        if text.strip().casefold() not in vistos:
            kws.append(text)
            vistos.add(text.strip().casefold())
    if not kws or len(kws) > 100:
        raise ValueError("snapshot deve conter 1..100 keywords; selecione outro recorte explicitamente")
    pagina = fetch_public_https_chain(url)
    if pagina["status"] != 200:
        raise ValueError("LP não respondeu HTTP 200")
    leitor = _TextoVisivel()
    leitor.feed(pagina["html"])
    texto = " ".join(leitor.partes)
    if len(texto) > 20000:
        raise ValueError("LP muito grande; forneça recorte explícito sem truncamento silencioso")
    e = Entrada(customer_id=customer_id, login_customer_id=login_customer_id,
                tema=tema, slug=slug, url_final=pagina["final_url"], pagina_texto=texto,
                keywords=kws, origem_keywords="snapshot SELECT Google: keywords já ENABLED; "
                "prova técnica, não aprovação de novo conjunto pago; source_sha256=" + sha(origem),
                budget_diario=budget, cpc_inicial=cpc,
                carimbo=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    _gravar(pasta / "keywords-source.json", origem)
    _gravar(pasta / "landing-source.json", {
        "url": pagina["url"], "final_url": pagina["final_url"], "http_status": pagina["status"],
        "document_sha256": pagina["sha256"], "extracted_text_sha256": sha(texto),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    })
    _gravar(pasta / "input.json", e.model_dump())
    return e


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pasta", type=Path)
    p.add_argument("--customer-id", required=True)
    p.add_argument("--login-customer-id", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--tema", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--budget", required=True, type=float)
    p.add_argument("--cpc", required=True, type=float)
    a = p.parse_args()
    e = capturar(a.pasta, customer_id=a.customer_id, login_customer_id=a.login_customer_id,
                 url=a.url, tema=a.tema, slug=a.slug, budget=a.budget, cpc=a.cpc)
    print("captura OK:", len(e.keywords), "keywords,", len(e.pagina_texto), "caracteres de LP")


if __name__ == "__main__":
    main()
