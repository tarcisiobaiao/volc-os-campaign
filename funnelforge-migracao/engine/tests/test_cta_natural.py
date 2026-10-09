"""CTA natural, curto e honesto (09/10).

Run real da Tarifa Social: todos os botões saíram "Entender…/Ver como…" com
duas orações ("… e evitar uma conclusão pelo NIS ou pela idade"). Causa: o
`copy_rapida.jinja` ensinava "Entender o que muda…"/"Ver como consultar…"/
"Entender como estimar…" e o portão `cta_issues` reprovava todo botão interno
iniciado por consultar/calcular/receber mandando usar "Ver como…". Estes testes
prendem a correção: o portão barra a PROMESSA (o site consulta/paga/aprova/
calcula sem ferramenta), não o verbo, e barra o rótulo longo.
"""
from __future__ import annotations

import pytest

from funnelforge.pipeline.copy_contract import CTA_MAX_CHARS, cta_issues
from funnelforge.pipeline.doctrine import banned_cta_execution_hit
from funnelforge.prompts import render

CTX = {"copy_rapida": True, "domain": "https://portal.test"}
INTERNO = "https://portal.test/rec/quem-tem-direito-p1/"


def _codigos(label: str, href: str = INTERNO, ctx: dict | None = None) -> set[str]:
    return {i.code for i in cta_issues([(label, href)], ctx or CTX)}


def _prompt_rapido() -> str:
    return render("redator_pages_v2", headline="tema", objective="resolver", skeleton=[],
                  keywords=[], editorial={}, escrita_natural=True)


def test_prompt_nao_ensina_mais_a_formula_entender_ver_como():
    texto = _prompt_rapido()
    for formula in ('use "Ver como consultar', 'use "Entender como estimar',
                    '"Entender o que muda na demissão"', '"Ver como estimar o valor anual"',
                    'Use "Ver como…"'):
        assert formula not in texto, formula
    # O que fica: rótulo curto, voz do leitor permitida, promessa limitada.
    assert "Ver se minha família atende aos requisitos" in texto
    assert "não são o formato automático" in texto
    assert "segunda oração" in texto
    assert "nunca diz que o site consulta dados pessoais" in texto


@pytest.mark.parametrize("label", [
    "Ver se minha família atende aos requisitos",
    "Conferir os documentos que preciso",
    "Ver o que fazer se o desconto não aparece",
    "Encontrar o canal de atendimento",
    "Consultar a tabela de descontos por faixa",
    "Ver como consultar meu saldo",
    "Entender por que não há valor único",
])
def test_rotulo_natural_passa_no_portao_interno(label):
    assert _codigos(label) == set()
    assert banned_cta_execution_hit(label) is None


@pytest.mark.parametrize("label", [
    "Consultar meu saldo do PIS",
    "Receber o benefício agora",
    "Ver meu saldo",
    "Conferir meu benefício",
    "Ver se fui aprovado",
    "Saber se o benefício foi liberado",
    "Consultar no app da CAIXA",
])
def test_promessa_que_o_site_nao_cumpre_continua_reprovada(label):
    issues = cta_issues([(label, INTERNO)], CTX)
    assert "cta_editorial_execution" in {i.code for i in issues}
    msg = next(i.message for i in issues if i.code == "cta_editorial_execution")
    assert "Ver como" not in msg  # o feedback não volta a ditar a fórmula


@pytest.mark.parametrize("label", ["Calcular a renda por pessoa", "Estimar meu valor",
                                   "Simular o desconto"])
def test_calculo_so_com_ferramenta_no_destino(label):
    assert "cta_editorial_execution" in _codigos(label)
    com_slug = {**CTX, "destinos_com_ferramenta": ["quem-tem-direito-p1"]}
    com_url = {**CTX, "destinos_com_ferramenta": ["https://portal.test/rec/quem-tem-direito-p1"]}
    assert _codigos(label, ctx=com_slug) == set()
    assert _codigos(label, ctx=com_url) == set()
    outro = {**CTX, "destinos_com_ferramenta": ["outra-pagina-p2"]}
    assert "cta_editorial_execution" in _codigos(label, ctx=outro)


@pytest.mark.parametrize("label", [
    "Entender quem pode ter direito e evitar uma conclusão pelo NIS ou pela idade",
    "Verificar a aplicação na conta e saber onde confirmar a situação",
])
def test_rotulo_longo_de_duas_oracoes_e_apontado(label):
    issues = cta_issues([(label, INTERNO)], CTX)
    longo = [i for i in issues if i.code == "cta_longo"]
    assert longo and str(CTA_MAX_CHARS) in longo[0].message


def test_rotulo_curto_nao_e_apontado_por_tamanho():
    assert "cta_longo" not in _codigos("Corrigir o CadÚnico antes de perder a recarga")


def test_dois_destinos_nunca_dividem_o_mesmo_texto():
    pares = [("Ver o que fazer se o desconto não aparece", "/rec/a"),
             ("Ver o que fazer se o desconto não aparece", "/rec/b")]
    assert "cta_rotulo_repetido" in {i.code for i in cta_issues(pares, CTX)}
    mesmo_destino = [(pares[0][0], "/rec/a"), (pares[0][0], "/rec/a/")]
    assert cta_issues(mesmo_destino, CTX) == []


def test_v1_nao_passa_pelo_portao_novo():
    assert cta_issues([("Consultar meu saldo do PIS", INTERNO)],
                      {**CTX, "copy_rapida": False}) == []


@pytest.mark.parametrize("cta", ["Ver o que pedir à distribuidora",
                                 "Saber quais documentos solicitar"])
def test_doutrina_aceita_enquadramento_alem_de_como(cta):
    assert banned_cta_execution_hit(cta) is None


@pytest.mark.parametrize("cta", ["Solicitar agora", "Cadastre-se", "Pedir o desconto"])
def test_doutrina_continua_barrando_execucao_direta(cta):
    assert banned_cta_execution_hit(cta)
