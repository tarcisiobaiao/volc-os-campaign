"""PROMPTS V2 SEM ACHATAMENTO (etapa B4, item 6).

Saem, no ramo novo: "verbo brando", o molde de "transição calma", "SEMPRE no
ANO CORRENTE", "curiosidade sem revelar tudo", "focada em conversão", os
exemplos do caso Senac em prompt genérico, a proibição de 1ª pessoa por
palavra e as cotas de FAQ/blocos além do que o template exige.

Entram: redigir A PARTIR DO BRIEFING — especificidade, desejo real, razão
concreta para começar, dúvidas bem escolhidas, benefício demonstrável com
qualificador, transição que diz o ganho do próximo passo, CTA com a intenção do
leitor e identidade do publisher onde é material.

Os templates antigos não mudam (ver o ouro em
`test_editorial_v2_flag_off_identico.py`): o ramo novo é outro arquivo.
"""
from __future__ import annotations

import pytest

from funnelforge.pipeline.doctrine import BANNED_CTA_FIRST_PERSON, doctrine_context
from funnelforge.prompts import nome_do_prompt, render

BRIEFING = ("BRIEFING DESTA PÁGINA (briefing-v1) — escreva a partir dele.\n"
            "TOM: registro servico; intensidade direta; por quê: leitor com pressa\n"
            "BRIEFING DO ARQUITETO DO FUNIL: tom e voz pedidos: direto e acolhedor")

_COMUM = dict(
    headline="Quem tem direito a tarifa social", objective="Confirmar se a familia se encaixa",
    skeleton="- Quem tem direito\n- Casos que ficam de fora", keywords="tarifa social",
    cta_text="Ver quem tem direito", facts="FATOS VERIFICADOS: NENHUM.",
    today="30/09/2026", domain="https://site.exemplo.com.br", briefing_texto=BRIEFING,
    author_name="Equipe", author_credential="Redacao", cnpj="42.724.548/0001-24",
)
_ROTAS = [{"kind": "funnel", "anchor": "Como pedir", "href": "https://site.exemplo.com.br/rec/pedir-p2",
           "reason": "depois do direito",
           "passo": {"rotulo": "Ver como pedir o desconto", "intencao": "pedir o desconto",
                     "o_que_encontra": "o passo a passo do pedido"}}]
_DESTINOS = [{"slug": "pedir-p2", "h1": "Como pedir", "objective": "passo a passo",
              "role_label": "página de solução", "delivery": "Passo a passo do pedido",
              "passo": {"rotulo": "Ver como pedir o desconto", "intencao": "pedir o desconto",
                        "o_que_encontra": "o passo a passo do pedido"}}]

REDATORES_V2 = {
    "redator_p1_v2": dict(_COMUM, lp_destinations=_DESTINOS),
    "redator_pages_v2": dict(_COMUM, role="SOLUTION", routes=_ROTAS,
                             official_links=["https://oficial.exemplo.gov.br/consulta"],
                             exigencia_visual=["details", "list"]),
    "redator_presell_v2": dict(_COMUM, role="PRESELL", routes=_ROTAS,
                               qualifier_lens="Qual e o seu caso?"),
}
OUTROS_V2 = {
    "seo_v2": dict(content="<p>corpo</p>", papel="SOLUTION", h1="Quem tem direito",
                   promessa="Mostrar quem tem direito", entrega="checklist: condicoes",
                   intencao="confirmar o direito", termos="", facts="FATOS VERIFICADOS: NENHUM."),
    "image_prompt_v2": dict(headline="Tarifa social", objective="entender o desconto"),
    "image_prompt_lp_v2": dict(headline="Tarifa social", objective="entender o desconto"),
    "briefing": dict(pagina={"numero": 3, "slug": "x-p1", "papel": "SOLUTION",
                             "papel_rotulo": "guia de solução", "h1": "X", "objetivo": "o",
                             "estrutura": ["a"], "keywords": "k"},
                     editorial={}, arquiteto={"tone_voice": "t", "avatar_summary": "a"},
                     inventario_texto="FATOS: nenhum", destinos=[], refs_arquiteto=[]),
}

ACHATAMENTO = (
    "verbo brando", "transição calma", "agora que você entende", "ano corrente",
    "curiosidade sem revelar", "focada em conversão", "engajador e atrativo",
    "classe mundial", "abre loop", "abre curiosidade", "provoca a próxima dúvida",
    "use muitos", "4 a 6 perguntas", "sim./não./depende.", '5 objetos em "faq"',
    "sensacionalismo (que fere a política do google)", "high-conversion",
)
CASO_SENAC = (
    "ver requisitos", "escolher um curso", "guia de inscrição",
    "regional, modalidade e edital", "vaga, aprovação, certificado", "vocational",
    "hospitality", "textile", "culinary", "senac", "course availability",
)
PROIBICAO_POR_PALAVRA = ("1ª pessoa", "primeira pessoa", "2ª/3ª pessoa", "imperativo",
                         *BANNED_CTA_FIRST_PERSON)


def _render(nome: str, ctx: dict) -> str:
    return render(nome, **ctx)


@pytest.mark.parametrize("nome", sorted({**REDATORES_V2, **OUTROS_V2}))
def test_prompt_v2_sem_achatamento_sem_caso_senac_sem_proibicao_por_palavra(nome):
    ctx = {**REDATORES_V2, **OUTROS_V2}[nome]
    low = _render(nome, ctx).lower()
    for trecho in ACHATAMENTO + CASO_SENAC + PROIBICAO_POR_PALAVRA:
        assert trecho not in low, f"{nome}: '{trecho}'"


@pytest.mark.parametrize("nome", sorted(REDATORES_V2))
def test_redator_v2_escreve_a_partir_do_briefing(nome):
    texto = _render(nome, REDATORES_V2[nome])
    low = texto.lower()
    assert BRIEFING in texto
    for trecho in ("escreva a partir do briefing", "especificidade", "desejo real",
                   "razão concreta para começar", "dúvidas bem escolhidas",
                   "benefício demonstrável", "qualificador", "hipótese é hipótese",
                   "não retenha informação básica", "não existe tom padrão",
                   "intenção ou o avanço do leitor", "ganho", "independente"):
        assert trecho in low, f"{nome}: falta '{trecho}'"
    # o que o briefing planejou para cada destino chega ao redator
    assert "Ver como pedir o desconto" in texto
    # nenhum tom padrão: sem "calmo"/"calma" que não venha do briefing
    assert "calm" not in low


def test_redator_v2_da_lp_mantem_o_contrato_do_template():
    low = _render("redator_p1_v2", REDATORES_V2["redator_p1_v2"]).lower()
    assert 'exatamente 4 objetos em "sections"' in low
    assert 'exatamente 3 strings em "cta_texts"' in low
    assert "pelo menos 1" in low                     # faq: sem cota, mas não vazia
    assert "exatamente 1 <p>" in low                 # intro de um parágrafo
    assert "página de pouso" in low


def test_redator_v2_das_internas_declara_so_a_exigencia_tecnica():
    texto = _render("redator_pages_v2", REDATORES_V2["redator_pages_v2"])
    assert "wp:details, wp:list" in texto            # portão visual declarado
    assert "O plano visual do briefing pede estes blocos" in texto  # D2
    assert "pelo menos 3 blocos wp:paragraph substantivos no fluxo principal" in texto
    assert "slots configurados do Ad Inserter" in texto
    assert "nada fora deles" in texto
    assert doctrine_context()["compliance_notice_text"] in texto  # aviso uma vez
    assert "Tema/headline: Quem tem direito a tarifa social" in texto
    sem = _render("redator_pages_v2", {**REDATORES_V2["redator_pages_v2"],
                                       "exigencia_visual": []})
    assert "O plano visual do briefing pede estes blocos" not in sem


def test_seo_v2_nomeia_a_entrega_real_sem_ano():
    texto = _render("seo_v2", OUTROS_V2["seo_v2"])
    low = texto.lower()
    assert "h1 visível" in low and "entrega real" in low
    assert "sem ano" in low
    for chave in ('"seotitle"', '"metadescription"', '"keywordfocus"', '"slug"'):
        assert chave in texto
    assert texto.startswith("<contrato_editorial_independente>")


def test_nome_do_prompt_so_troca_quem_tem_versao_v2():
    assert nome_do_prompt("redator_pages", v2=True) == "redator_pages_v2"
    assert nome_do_prompt("seo", v2=True) == "seo_v2"
    assert nome_do_prompt("redator_pages", v2=False) == "redator_pages"
    for sem_v2 in ("judge", "redator_widget", "image_review", "declarador_engajamento"):
        assert nome_do_prompt(sem_v2, v2=True) == sem_v2
