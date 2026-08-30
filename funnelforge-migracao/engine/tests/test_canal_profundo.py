"""Domínio-raiz → a página que o leitor precisa abrir.

## O caso real que originou o módulo

Medido em 19/08/2026 no funil FGTS publicado: **22 de 23 links externos eram
domínio-raiz**. "página de download na Google Play Store" apontava para
`play.google.com`; "tabela de limites da Caixa", para `caixa.gov.br`.

A causa era a pesquisa, não a escolha do canal: nas três páginas de solução,
`fonte_primaria` e `fontes` só continham raízes. E o prompt da pesquisa JÁ
pedia o contrário, com exemplo — "URL EXATA (nunca o portal generico)". O
modelo ignorou nas três.

⚠️ Nenhum teste aqui abre rede. `escolher_profundo` é puro de propósito: é onde
mora a decisão, e decisão que só dá para provar com internet não se prova.
"""
from __future__ import annotations

import pytest

from funnelforge.pipeline import canal_profundo as cp

# Os links REAIS colhidos de `caixa.gov.br/beneficios-trabalhador/fgts/` em
# 19/08/2026, com navegador. É a amostra que importa: a resposta certa está
# entre eles, cercada do menu institucional inteiro.
LINKS_CAIXA = [
    ("Para você", "https://www.caixa.gov.br/voce/Paginas/default.aspx"),
    ("Para sua empresa", "https://www.caixa.gov.br/empresa/Paginas/default.aspx"),
    ("Fale conosco", "https://www.caixa.gov.br/atendimento/fale-conosco/Paginas/default.aspx"),
    ("Aplicativos", "https://www.caixa.gov.br/atendimento/aplicativos/Paginas/default.aspx"),
    ("Saque-aniversário",
     "https://www.caixa.gov.br/beneficios-trabalhador/fgts/saque-FGTS/Paginas/default.aspx#saque-aniversario"),
    ("Mapa do site", "https://www.caixa.gov.br/site/paginas/mapa-do-site.aspx"),
    ("Privacidade", "https://www.caixa.gov.br/site/paginas/privacidade.aspx"),
    ("Outro banco", "https://www.bb.com.br/fgts/saque-aniversario"),
]


def test_acha_a_pagina_do_saque_aniversario():
    """A resposta que eu levei três chutes errados para achar à mão — e um
    deles, `.../fgts/saque-aniversario/Paginas/default.aspx`, devolvia 404."""
    termos = cp.termos_uteis("Como ativar o Saque-Aniversário do FGTS",
                             "adesão saque aniversário aplicativo")
    achado = cp.escolher_profundo("https://www.caixa.gov.br", LINKS_CAIXA, termos)
    assert achado and "saque-FGTS" in achado and "#saque-aniversario" in achado


def test_nao_atravessa_para_outro_host():
    """`bb.com.br/fgts/saque-aniversario` casa PERFEITAMENTE com os termos — e
    é outro banco. Trocar o canal oficial por um concorrente seria pior que a
    raiz."""
    termos = cp.termos_uteis("saque aniversário FGTS")
    achado = cp.escolher_profundo("https://www.caixa.gov.br", LINKS_CAIXA, termos)
    assert achado is None or "bb.com.br" not in achado


@pytest.mark.parametrize("lixo", [
    ("Mapa do site", "https://www.caixa.gov.br/site/paginas/mapa-do-site.aspx"),
    ("Buscar", "https://www.caixa.gov.br/busca?q=saque+aniversario+fgts"),
    ("Fale conosco", "https://www.caixa.gov.br/atendimento/fale-conosco/x.aspx"),
])
def test_navegacao_institucional_nunca_vence(lixo):
    termos = cp.termos_uteis("saque aniversário FGTS")
    assert cp.pontuar(lixo[0], lixo[1], termos) <= 0


def test_sem_casamento_suficiente_devolve_nada():
    """Um termo casado é o menu de qualquer site. O piso é dois."""
    termos = cp.termos_uteis("consignado para aposentado do INSS")
    assert cp.escolher_profundo("https://www.caixa.gov.br", LINKS_CAIXA, termos) is None


# ── e_raiz: o que conta como "é só a marca" ────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://www.caixa.gov.br", "https://www.caixa.gov.br/",
    "https://play.google.com", "https://apps.apple.com",
])
def test_reconhece_raiz(url):
    assert cp.e_raiz(url)


@pytest.mark.parametrize("url", [
    "https://play.google.com/store/apps/details?id=br.gov.caixa.fgts.trabalhador",
    "https://www.caixa.gov.br/beneficios-trabalhador/fgts/Paginas/default.aspx",
    "https://www.caixa.gov.br/x/y#z",
])
def test_reconhece_pagina_especifica(url):
    assert not cp.e_raiz(url)


# ── aprofundar: fail-safe em toda parte ────────────────────────────────────
#
# Um canal oficial pior nunca vale uma página perdida. Toda falha devolve a
# raiz, que é exatamente o comportamento de antes deste módulo.

def test_url_ja_especifica_nao_e_tocada():
    u = "https://www.caixa.gov.br/beneficios-trabalhador/fgts/Paginas/default.aspx"
    assert cp.aprofundar(u, {"fgts"}, colher=lambda _: []) == u


def test_colheita_vazia_devolve_a_raiz():
    assert cp.aprofundar("https://www.caixa.gov.br", {"fgts", "saque"},
                         colher=lambda _: []) == "https://www.caixa.gov.br"


def test_colheita_que_explode_devolve_a_raiz():
    def explode(_):
        raise RuntimeError("rede caiu")
    assert cp.aprofundar("https://www.caixa.gov.br", {"fgts", "saque"},
                         colher=explode) == "https://www.caixa.gov.br"


def test_link_achado_mas_morto_nao_sobe():
    """⚠️ Fail-closed. Uma URL plausível e morta é PIOR que a raiz: a raiz pelo
    menos abre. Foi o que aconteceu com o meu palpite
    `.../fgts/saque-aniversario/Paginas/default.aspx` — 404."""
    achado = cp.aprofundar(
        "https://www.caixa.gov.br",
        cp.termos_uteis("saque aniversário FGTS aplicativo"),
        verificar=lambda _: False, colher=lambda _: LINKS_CAIXA)
    assert achado == "https://www.caixa.gov.br"


def test_link_achado_e_vivo_sobe():
    achado = cp.aprofundar(
        "https://www.caixa.gov.br",
        cp.termos_uteis("saque aniversário FGTS aplicativo"),
        verificar=lambda _: True, colher=lambda _: LINKS_CAIXA)
    assert "saque-FGTS" in achado


def test_verificador_que_explode_devolve_a_raiz():
    def explode(_):
        raise RuntimeError("timeout")
    assert cp.aprofundar("https://www.caixa.gov.br",
                         cp.termos_uteis("saque aniversário FGTS"),
                         verificar=explode,
                         colher=lambda _: LINKS_CAIXA) == "https://www.caixa.gov.br"


# ── a fronteira com o pipeline ─────────────────────────────────────────────

def test_o_pipeline_aprofunda_os_canais_oficiais():
    import inspect

    from funnelforge.pipeline.steps import registrar_canais_oficiais

    fonte = inspect.getsource(registrar_canais_oficiais)
    assert "canal_profundo.aprofundar" in fonte
    assert "canal_profundo.e_raiz" in fonte, (
        "só raiz deve ser aprofundada — URL específica da pesquisa é para manter")


# ── dois termos distintos antes de qualquer bônus ──────────────────────────
#
# ⚠️ Medido em 19/08/2026 contra o site ao vivo: com o tema "antecipação do
# saque-aniversário", `habilitacao-saque-calamidade-fgts` vencia casando UM
# termo — `saque` — porque os bônus de profundidade (+3) e de página-de-serviço
# (+1) somavam mais que o casamento real. Saque de CALAMIDADE num artigo sobre
# antecipação.
#
# Link específico ERRADO é pior que a raiz: a raiz é honesta sobre ser a
# instituição; o link errado promete a resposta e entrega outra.

CALAMIDADE = ("Habilitação Saque Calamidade FGTS",
              "https://www.caixa.gov.br/poder-publico/"
              "habilitacao-saque-calamidade-fgts/Paginas/default.aspx")


def test_um_termo_so_nao_ganha_por_bonus():
    termos = cp.termos_uteis("Antecipação do saque-aniversário empréstimo antecipar")
    assert cp.pontuar(*CALAMIDADE, termos) == 0


def test_calamidade_nao_vence_artigo_de_antecipacao():
    termos = cp.termos_uteis("Antecipação do saque-aniversário empréstimo antecipar")
    escolhido = cp.escolher_profundo("https://www.caixa.gov.br",
                                     [CALAMIDADE] + LINKS_CAIXA, termos)
    assert escolhido is None or "calamidade" not in escolhido


def test_dois_termos_continuam_bastando_quando_sao_reais():
    termos = cp.termos_uteis("saque aniversário FGTS")
    achado = cp.escolher_profundo("https://www.caixa.gov.br", LINKS_CAIXA, termos)
    assert achado and "#saque-aniversario" in achado


# ── segundo salto: a página certa não fica pendurada na home ───────────────

def test_o_segundo_salto_encontra_o_que_a_home_nao_mostra():
    """Foi o que aconteceu de verdade: um salto só a partir da home escolhia
    saque-calamidade; a página do saque-aniversário está DENTRO da seção
    `/beneficios-trabalhador/fgts/`, que é o caminho que o leitor faz."""
    home = [("Benefícios ao trabalhador FGTS",
             "https://www.caixa.gov.br/beneficios-trabalhador/fgts/Paginas/default.aspx"),
            CALAMIDADE]

    def colher(url):
        return LINKS_CAIXA if "beneficios-trabalhador" in url else home

    achado = cp.aprofundar("https://www.caixa.gov.br",
                           cp.termos_uteis("saque aniversário FGTS"),
                           verificar=lambda _: True, colher=colher)
    assert "#saque-aniversario" in achado


def test_um_salto_so_nao_acha_e_devolve_a_raiz():
    """A prova de que o segundo salto é o que faz a diferença — e não um
    detalhe de implementação."""
    home = [("Benefícios ao trabalhador FGTS",
             "https://www.caixa.gov.br/beneficios-trabalhador/fgts/Paginas/default.aspx")]
    achado = cp.aprofundar("https://www.caixa.gov.br",
                           cp.termos_uteis("saque aniversário adesão"),
                           verificar=lambda _: True,
                           colher=lambda _: home, saltos=1)
    assert achado == "https://www.caixa.gov.br"
