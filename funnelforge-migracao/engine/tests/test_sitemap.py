import pytest

from funnelforge.adapters.sitemap_http import HttpSitemapProvider
from funnelforge.domain.models import Route, resolve_route

_D = "https://creditoup.com.br"


def test_sitemap_descarta_redundante_e_respeita_o_mesmo_dominio():
    """O que a regra SEM LÉXICO garante — e o que ela deixou de garantir.

    GARANTE: página que repete 3+ termos do tema é a mesma pauta e sai; página
    de outro domínio sai; página do próprio funil sai. Isso vale para FGTS,
    para cartão de negativado e para entregador de aplicativo, sem ninguém
    escrever vocabulário.

    NÃO GARANTE MAIS: qual das candidatas SOBREVIVENTES vem primeiro. A ordem
    antiga vinha de uma lista `_BRIDGE` escrita à mão ("sacar, dinheiro, parado,
    esquecido") que sabia que PIS/Pasep era a vizinha certa de um funil de FGTS.
    Aquilo era conhecimento semântico de UM tema, e reprovava todos os outros.

    ⚠️ A fonte certa para esse desempate não é o sitemap: é a tabela
    `pautador_funnel_runs`, que agora sabe QUAIS cards já viraram funil NAQUELE
    site. Recircular para um funil que o próprio sistema publicou é melhor que
    adivinhar por slug — e é dado, não léxico. Fica registrado como o próximo
    passo; até lá, entre as sobreviventes a ordem é arbitrária.
    """
    p = HttpSitemapProvider(_D)
    urls = [
        f"{_D}/como-consultar-fgts-pelo-cpf-p1/",                # página do funil -> sai
        f"{_D}/saque-aniversario-do-fgts-completo/",             # 3 termos do tema -> sai
        f"{_D}/como-sacar-pis-pasep-esquecido-dinheiro-parado/", # vizinha -> fica
        "https://outrosite.com/qualquer/",                       # outro domínio -> sai
    ]
    ranked = p._rank(urls, theme="antecipar FGTS saque aniversario",
                     exclude_slugs=["como-consultar-fgts-pelo-cpf-p1"])

    assert ranked, "esperava ao menos uma candidata"
    assert any("pis-pasep" in u for u in ranked)
    assert not any("saque-aniversario-do-fgts-completo" in u for u in ranked)
    assert not any("outrosite.com" in u for u in ranked)
    assert not any("consultar-fgts-pelo-cpf" in u for u in ranked)


def test_sitemap_serve_a_qualquer_vertical_nao_so_a_governamental():
    """O defeito que a regra nova conserta: com o léxico de FGTS, um funil de
    entregador de aplicativo não pontuava NADA e a saída caía no fallback."""
    p = HttpSitemapProvider(_D)
    urls = [
        f"{_D}/entregador-ifood-quanto-ganha-p1/",       # página do funil -> sai
        f"{_D}/entregador-ifood-cadastro-taxas/",        # mesma pauta -> sai
        f"{_D}/motoboy-seguro-para-moto-de-trabalho/",   # vizinha -> fica
    ]
    ranked = p._rank(urls, theme="entregador iFood cadastro",
                     exclude_slugs=["entregador-ifood-quanto-ganha-p1"])
    assert any("motoboy-seguro" in u for u in ranked)
    assert not any("entregador-ifood-cadastro" in u for u in ranked)


def test_resolve_route_cross_funnel_is_real_absolute_same_domain():
    # O ramo cross_funnel não depende de autorização externa nenhuma: ele é, por
    # definição, uma URL do PRÓPRIO domínio vinda do sitemap. Por isso a chamada
    # não passa `authorized_external` (o antigo `allowed_external` deixou de
    # existir) -- a lei aqui é a do mesmo domínio, não a da pesquisa.
    # a real absolute same-domain URL -> returned as-is (never reconstructed)
    ok = Route(placement="footer", kind="cross_funnel", target=f"{_D}/pis-pasep-esquecido/")
    assert resolve_route(ok, domain=_D, post_type="rec") == f"{_D}/pis-pasep-esquecido/"
    # a BARE SLUG (invented page) is rejected -> fabrication is impossible now
    with pytest.raises(ValueError):
        bare = Route(placement="footer", kind="cross_funnel", target="emprestimo-consignado")
        resolve_route(bare, domain=_D, post_type="rec")
    # cross-domain is rejected
    with pytest.raises(ValueError):
        resolve_route(Route(placement="footer", kind="cross_funnel", target="https://evil.com/x"),
                      domain=_D, post_type="rec")
