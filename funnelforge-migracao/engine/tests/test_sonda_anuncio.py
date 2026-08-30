"""Google Analytics não é anúncio — e confundir os dois mata a página.

## O defeito, medido no run #5 (17/08/2026)

A página 3 do funil de "Cartão para Negativado" foi bloqueada com
`official_links_none`: nenhum canal oficial elegível. Mas a pesquisa tinha
achado fontes ÓTIMAS — `serasa.com.br`, `bcb.gov.br` e
`bcb.gov.br/meubc/registrato`. As três respondem HTTP 200, e o verificador de
URL aprovou as três.

Quem as descartou foi a sonda anti-concorrente. Ela devolvia `True` — "vive de
anúncio" — até para o **Banco Central do Brasil**, por causa desta requisição:

    https://stats.g.doubleclick.net/g/collect?v=2&tid=G-TPS4R7DC1S...

Isso é o endpoint de medição do Google Analytics 4. Ele usa o domínio
`doubleclick.net` para sinal entre domínios, e praticamente todo site sério do
mundo o carrega — inclusive os do governo. A lista de marcas continha
`doubleclick.net` inteiro, então bastava ter Analytics para ser classificado
como portal de arbitragem.

Consequência: o canal oficial de QUALQUER página era reprovado, `official_links`
saía vazio, e a página morria no gate de densidade — com as fontes certas na mão.

## O que a sonda tem de continuar pegando

O Serasa carrega `securepubads.g.doubleclick.net/tag/js/gpt.js` (Google
Publisher Tag), `criteo` e `googlesyndication`. Isso é veiculação de display de
verdade: ele monetiza a MESMA sessão que o operador comprou. `True` ali está
certo, e o conserto não pode afrouxar isso.
"""
from __future__ import annotations

from funnelforge.adapters.screenshot_playwright import (
    _MARCAS_DE_ANUNCIO,
    _MEDICAO_NAO_E_ANUNCIO,
)


def _classifica(pedidos: list[str]) -> bool:
    """A mesma decisão do `is_ad_monetized`, sem browser — para o teste ser
    rápido e determinístico. Se a regra mudar lá, este espelho quebra junto."""
    de_anuncio = [p for p in pedidos
                  if not any(ok in p.lower() for ok in _MEDICAO_NAO_E_ANUNCIO)]
    return any(m in p.lower() for p in de_anuncio for m in _MARCAS_DE_ANUNCIO)


GA4_DO_BANCO_CENTRAL = (
    "https://stats.g.doubleclick.net/g/collect?v=2&tid=G-TPS4R7DC1S"
    "&cid=95865887.1787004684&gtm=45je68d0v9103562362"
)
GPT_DO_SERASA = "https://securepubads.g.doubleclick.net/tag/js/gpt.js"


def test_analytics_sozinho_nao_e_anuncio():
    """O caso literal do Banco Central."""
    assert _classifica([GA4_DO_BANCO_CENTRAL]) is False
    assert _classifica([
        "https://www.googletagmanager.com/gtm.js?id=GTM-XXXX",
        "https://www.google-analytics.com/g/collect",
        GA4_DO_BANCO_CENTRAL,
    ]) is False


def test_veiculacao_de_verdade_continua_sendo_pega():
    """O caso literal do Serasa. O conserto não pode afrouxar isto."""
    assert _classifica([GPT_DO_SERASA]) is True
    assert _classifica(["https://static.criteo.net/js/ld/publishertag.ids.js"]) is True
    assert _classifica(["https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"]) is True


def test_analytics_junto_com_anuncio_nao_esconde_o_anuncio():
    """A exclusão é por REQUISIÇÃO, não pela página inteira: um portal que tem
    GA4 E servidor de anúncio continua sendo portal de anúncio."""
    assert _classifica([GA4_DO_BANCO_CENTRAL, GPT_DO_SERASA]) is True


def test_a_medicao_nao_engole_o_dominio_inteiro():
    """`stats.g.doubleclick.net` é medição; `securepubads.g.doubleclick.net` é
    veiculação. Excluir `doubleclick.net` inteiro apagaria a segunda."""
    assert "stats.g.doubleclick.net" in _MEDICAO_NAO_E_ANUNCIO
    assert "doubleclick.net" not in _MEDICAO_NAO_E_ANUNCIO
    assert "securepubads.g.doubleclick.net" in _MARCAS_DE_ANUNCIO
    assert "doubleclick.net" not in _MARCAS_DE_ANUNCIO


def test_sem_requisicao_nenhuma_nao_ha_anuncio():
    assert _classifica([]) is False
