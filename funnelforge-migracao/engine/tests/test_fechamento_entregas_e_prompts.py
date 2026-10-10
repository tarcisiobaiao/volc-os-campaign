"""Fechamento de 10/10: redator e revisor leem as mesmas entregas dos destinos,
e os prompts V2 não proíbem palavras nem pedem meta de palavras."""
import re

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.domain.models import RunState
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.inteligencia import congelar_pacotes, prompt_do_pacote
from funnelforge.pipeline.pipeline import _populate_routes
from funnelforge.pipeline.revisao import Documento, montar_prompt_do_revisor
from funnelforge.prompts import render
from tests.cenario_editorial import montar_deps, responder_v2, settings_do_cenario
from tests.test_dossie_factual import FATOS_COMPLETOS, _compilar, _Pesquisa, arquitetura
from tests.test_inteligencia_pre_redacao import brief
from tests.test_prompts_v2 import REDATORES_V2


def _com_pacotes(tmp_path):
    s = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=True)
    _, deps = montar_deps(tmp_path, s, responder_v2)
    state = RunState(run_id="pacotes", plan=plano_do_funnel_architecture(arquitetura()),
                     brief_pre_arquitetura=brief())
    state.dossie = _compilar(state, _Pesquisa(FATOS_COMPLETOS)).model_dump(mode="json")
    _populate_routes(state, deps)
    congelar_pacotes(state, deps)
    state.editorial_v2 = True
    return state, deps


def _entregas(prompt: str) -> str:
    m = re.search(r"<entregas_dos_destinos>([\s\S]*?)</entregas_dos_destinos>", prompt)
    return m.group(1) if m else ""


def test_presell_e_solucoes_recebem_a_entrega_confirmada_de_cada_destino(tmp_path):
    state, _ = _com_pacotes(tmp_path)
    conferidas = 0
    for page in state.plan.pages:
        if page.page_type == "LANDING PAGE":
            continue
        funil = [d for d in state.pacotes[page.page_number]["destinos"] if d["tipo"] == "funnel"]
        bloco = _entregas(prompt_do_pacote(state, page))
        for d in funil:
            assert d["entrega"] and d["entrega"] in bloco, (page.slug, d["destino"])
            conferidas += 1
    assert conferidas, "o cenário precisa ter ao menos uma aresta interna fora da LP"


def test_revisor_confere_os_botoes_contra_a_entrega_do_pacote_nao_a_do_plano(tmp_path):
    state, deps = _com_pacotes(tmp_path)
    page = next(p for p in state.plan.pages if p.page_type != "LANDING PAGE" and any(
        d["tipo"] == "funnel" for d in state.pacotes[p.page_number]["destinos"]))
    destino = next(d for d in state.pacotes[page.page_number]["destinos"]
                   if d["tipo"] == "funnel")
    # O que o redator leu: a ferramenta do destino não ficou pronta e a entrega
    # virou o fallback. O plano continua prometendo a ferramenta.
    destino["entrega"] = "Explica a regra em texto, sem calculadora."
    doc = Documento(formato="gutenberg",
                    corpo="<!-- wp:paragraph --><p>Resposta.</p><!-- /wp:paragraph -->",
                    seotitle="Título", metadescription="Descrição.")

    ctx = st._contexto_da_revisao(state, page, deps, doc)

    alvo = next(d for d in ctx.destinos if d["id"] == destino["id"])
    assert alvo["entrega"] == "Explica a regra em texto, sem calculadora."
    assert "Explica a regra em texto, sem calculadora." in montar_prompt_do_revisor(doc, ctx)


def test_lp_v2_sem_meta_de_palavras_e_sem_lista_de_frases_proibidas():
    prompt = render("redator_p1_v2", **{
        **REDATORES_V2["redator_p1_v2"],
        "banned_fear": ["não perca o prazo"], "banned_official": ["sistema oficial"],
        "banned_cta_execution": ["agendar"]})
    assert "650" not in prompt and "sem meta de palavras" in prompt
    for frase in ("não perca o prazo", "sistema oficial", '"agendar"'):
        assert frase not in prompt
    assert "Não há lista de palavras ou verbos proibidos" in prompt


def test_escrita_natural_julga_oficialidade_pelo_sentido_sem_lista():
    texto = render("escrita_natural", banned_official=["canal oficial do governo"])
    assert "canal oficial do governo" not in texto
    assert "Oficialidade pelo sentido" in texto and "no site da ANEEL" in texto


# Canário de 10/10: o revisor citou o fato da ANEEL ("renda total de até três
# salários-mínimos") e o patch foi recusado como número novo, levando a p2 à
# decisão humana sem necessidade.
def test_numero_por_extenso_do_fato_citavel_passa_no_patch_e_o_inventado_nao():
    from types import SimpleNamespace

    from funnelforge.pipeline.steps import numeros_permitidos_no_patch
    from tests.test_revisor_patches import _achado, _aplicar, _doc_gutenberg, _patch

    fatos = [SimpleNamespace(tipo="condicao", citavel=True, dispositivo="", vigente_desde=None,
                             texto="renda total de até três salários-mínimos"),
             SimpleNamespace(tipo="contexto", citavel=True, dispositivo="", vigente_desde=None,
                             texto="cinco distribuidoras citadas")]
    permitidos = frozenset(numeros_permitidos_no_patch(fatos))
    assert "tres" in permitidos and "cinco" not in permitidos

    antes = "um trecho comum sobre a conta"
    achado = [_achado(trecho=antes, severidade="ajuste", categoria="erro_factual",
                      tipo="fato", ref="n1")]
    _n, aplicados, _r = _aplicar(
        _doc_gutenberg(), [_patch(antes, "um limite de até três salários-mínimos")],
        achado, numeros=permitidos)
    assert aplicados
    _n, aplicados, recusados = _aplicar(
        _doc_gutenberg(), [_patch(antes, "um limite de até cinco salários-mínimos")],
        achado, numeros=permitidos)
    assert not aplicados and recusados[0]["motivo"] == "numero_novo"


def test_canonica_tira_token_de_sessao_e_mantem_query_funcional():
    from funnelforge.adapters.pesquisa_plano import canonica

    faq = ("https://www.gov.br/mme/pt-br/luzdopovo/perguntas-frequentes-faq/"
           "perguntas-frequentes/?_authenticator=269a6d6e911145fef46e6dd9d78bcdf5b88a9459")
    assert canonica(faq) == ("https://www.gov.br/mme/pt-br/luzdopovo/perguntas-frequentes-faq/"
                             "perguntas-frequentes/")
    assert canonica("https://www.neoenergia.com/en/tarifa-social?doAsUserId=6205") == \
        "https://www.neoenergia.com/en/tarifa-social"
    servico = ("https://www.gov.br/pt-br/servicos/consultar-dados-do-cadastro-unico-cadunico"
               "?id=53&origem=servico")
    assert canonica(servico) == servico


def test_sniper_mostra_contraste_resposta_tema_sem_proibir_verbo():
    from importlib import resources
    fonte = resources.files("funnelforge.prompts").joinpath("ctas_do_funil.jinja").read_text("utf-8")
    assert "só repete o tema" in fonte and "Nenhum verbo é proibido" in fonte
    assert "o sistema recusa" not in fonte
