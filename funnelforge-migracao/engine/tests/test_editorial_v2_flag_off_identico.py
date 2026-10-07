"""OURO DO RAMO DESLIGADO: com `run.editorial_v2 = false`, nada muda.

Gerado em 30/09/2026 ANTES de qualquer mudança de prompt da etapa B4, com o
código que estava no worktree. A reforma editorial (briefing, prompts v2,
revisor) fica atrás da flag; este teste é a prova de que, com a flag desligada,
o motor pede ao modelo EXATAMENTE o que pedia antes:

1. todo template renderizado com contextos fixos (várias variantes);
2. o pipeline inteiro (plano injetado, dois funis: legado e contextual) — o
   prompt inicial de cada passo e a ORDEM das chamadas e dos passos;
3. o prompt do adaptador de pesquisa.

⚠️ EXCEÇÃO DECLARADA — o item 3 mudou de propósito na própria B4: a pesquisa
tipada (tipo/escopo/citavel e vigência × data histórica) é CORREÇÃO DE DEFEITO
e vale para todos os runs, com ou sem a flag (contrato entre trilhas, decisão
1). O arquivo de ouro dele foi regenerado uma vez, depois da correção, e a
diferença está registrada no handoff `implementacao-B4.md`. Os itens 1 e 2 não
mudaram.

Regenerar (só quando uma mudança do ramo desligado for DECIDIDA):
    FUNNELFORGE_REGERAR_OURO=1 pytest tests/test_editorial_v2_flag_off_identico.py
"""
from __future__ import annotations

import difflib
import json
import os
from pathlib import Path

import pytest

from funnelforge.domain.models import Page, ResearchFacts, VerifiedFact
from funnelforge.pipeline.base_factual import base_para_o_redator
from funnelforge.pipeline.doctrine import doctrine_context
from funnelforge.prompts import render
from tests.cenario_editorial import (
    FONTE_CADASTRO,
    FONTE_OFICIAL,
    HOJE,
    arquitetura_base,
    congelar_data,
    ordem_do_run,
    prompts_do_run,
    rodar_cenario,
    settings_do_cenario,
)

OURO = Path(__file__).parent / "golden" / "editorial_v1"
REGERAR = os.environ.get("FUNNELFORGE_REGERAR_OURO") == "1"


def _confere(nome: str, texto: str) -> None:
    caminho = OURO / nome
    if REGERAR:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
        return
    assert caminho.exists(), f"ouro ausente: {caminho} (gere com FUNNELFORGE_REGERAR_OURO=1)"
    esperado = caminho.read_text(encoding="utf-8")
    if texto != esperado:
        diff = "\n".join(list(difflib.unified_diff(
            esperado.splitlines(), texto.splitlines(), "ouro", "agora", lineterm=""))[:80])
        pytest.fail(f"{nome} mudou com a flag desligada:\n{diff}")


# ---------------------------------------------------------------------------
# 1. renders diretos
# ---------------------------------------------------------------------------

def _fatos() -> str:
    facts = ResearchFacts(
        resumo="Resumo qualitativo do tema, com 12 numeros podados.",
        dados_validados=[{"fato": "O pedido e feito na distribuidora.", "fonte": FONTE_OFICIAL}],
        fatos_verificados=[VerifiedFact(
            valor="65%", unidade="de desconto na faixa de consumo mais baixa",
            fonte_primaria=FONTE_OFICIAL, dispositivo="Lei de exemplo, art. 1",
            vigente_desde="2010-01-20", verificado_em="2026-09-29")],
        passo_a_passo=["Conferir o cadastro", "Pedir na distribuidora"],
        fontes=[FONTE_OFICIAL, FONTE_CADASTRO],
        fontes_resolvidas=[FONTE_OFICIAL],
    )
    return base_para_o_redator(facts)


_EDITORIAL = {
    "reader_question": "A minha familia pode ter desconto na conta de luz?",
    "useful_delivery": "Explica quem tem direito, onde pedir e como conferir",
    "cta_label": "Ver se a familia tem direito",
    "links": [{"target": "quem-tem-direito-p1", "reason": "Conferir as regras"}],
}
_ROTAS = [
    {"kind": "funnel", "anchor": "Ver o passo a passo do pedido",
     "href": "https://site.exemplo.com.br/rec/como-pedir-p2", "reason": "Depois do direito"},
    {"kind": "external_official", "anchor": "Consultar no canal oficial >>>",
     "href": FONTE_OFICIAL, "reason": ""},
]
_DESTINOS_LP = [
    {"slug": "por-onde-comecar-pr", "h1": "Por onde comecar", "objective": "qualificar",
     "cta_label": "Ver o caminho do seu caso", "delivery": "Escolha do caminho",
     "role": "PRESELL", "role_label": "hub qualificador"},
    {"slug": "quem-tem-direito-p1", "h1": "Quem tem direito", "objective": "regras",
     "cta_label": "Ver quem tem direito", "delivery": "As regras",
     "role": "SOLUTION", "role_label": "pagina de solucao"},
    {"slug": "como-pedir-p2", "h1": "Como pedir", "objective": "passo a passo",
     "cta_label": "Ver o passo a passo", "delivery": "", "role": "SOLUTION",
     "role_label": "pagina de solucao"},
]


def _comum() -> dict:
    return dict(
        headline="Tarifa social de energia: quem tem direito e como pedir",
        objective="Leitor quer saber se a familia pode ter desconto",
        skeleton="- Quem pode ter o desconto\n- Onde pedir",
        keywords="tarifa social, desconto conta de luz",
        cta_text="Ver se a familia tem direito", facts=_fatos(),
        today=HOJE.strftime("%d/%m/%Y"), domain="https://site.exemplo.com.br",
        author_name="Equipe Exemplo", author_credential="Redacao",
        cnpj="42.724.548/0001-24", cta_link="/quem-tem-direito-p1",
        **doctrine_context(),
    )


def _variantes() -> dict[str, tuple[str, dict]]:
    comum = _comum()
    return {
        "extractor__briefing": ("extractor", {"briefing": "Briefing do funil de exemplo."}),
        "redator_p1__com_destinos": ("redator_p1", {
            **comum, "lp_destinations": _DESTINOS_LP, "editorial": _EDITORIAL}),
        "redator_p1__sem_destinos": ("redator_p1", {**comum, "editorial": {}}),
        "redator_pages__meio": ("redator_pages", {
            **comum, "role": "SOLUTION", "page_num": 3, "total_pages": 5,
            "is_terminal": False, "terminal_official": False, "editorial": _EDITORIAL,
            "next_solutions": [{"slug": "como-pedir-p2", "h1": "Como pedir",
                                "objective": "passo a passo"}],
            "routes": _ROTAS, "official_links": [FONTE_OFICIAL],
            "platform_links": [{"url": "https://app.exemplo.com.br/x", "host": "app.exemplo.com.br"}],
            "engajamento": "sequencial", "signature_block": "PULLQUOTE (wp:pullquote)",
            "visual_required_blocks": ["details", "list"]}),
        "redator_pages__terminal": ("redator_pages", {
            **comum, "role": "SOLUTION", "page_num": 5, "total_pages": 5,
            "is_terminal": True, "terminal_official": True, "editorial": {},
            "cross_funnel_label": "Ver outro guia", "routes": _ROTAS[1:],
            "official_links": [FONTE_OFICIAL]}),
        "redator_presell__hub": ("redator_presell", {
            **comum, "role": "PRESELL", "page_num": 2, "total_pages": 5,
            "qualifier_lens": "Qual e a sua situacao?",
            "qualifier_questions": [{"caso": "Nao sei se tenho direito", "solucao": "Quem tem direito"}],
            "routes": _ROTAS[:1], "editorial": {}}),
        "judge__lp_editorial": ("judge", {
            **comum, "content": "{\"hero_title\": \"x\"}", "page_type": "LANDING PAGE",
            "editorial": _EDITORIAL,
            "destination_contracts": [{"slug": "quem-tem-direito-p1", "title": "Quem tem direito",
                                       "delivery": "As regras", "label": "Ver quem tem direito",
                                       "reason": "Conferir"}]}),
        "judge__solution": ("judge", {**comum, "content": "<p>corpo</p>",
                                      "page_type": "SOLUTION"}),
        "seo__conteudo": ("seo", {"content": "<p>corpo do guia</p>",
                                  "today": HOJE.strftime("%d/%m/%Y")}),
        "image_prompt__post": ("image_prompt", {
            "headline": comum["headline"], "objective": comum["objective"],
            "keywords": ["tarifa social"], "page_number": 3,
            "previous_scenes": ["Kitchen table with an unbranded bill."]}),
        "image_prompt_lp__hero": ("image_prompt_lp", {
            "headline": comum["headline"], "objective": comum["objective"],
            "keywords": ["tarifa social"], "page_number": 1, "previous_scenes": []}),
        "image_review__foto": ("image_review", {
            "headline": comum["headline"], "objective": comum["objective"],
            "keywords": ["tarifa social"]}),
        "redator_widget__jornada": ("redator_widget", {
            "country": "Brasil", "year": HOJE.year, "title": comum["headline"],
            "article": "<p>corpo do guia</p>", "arquetipo": "navegador",
            "facts": comum["facts"]}),
        "declarador_engajamento__paginas": ("declarador_engajamento", {
            "country": "Brasil",
            "pages": [Page(page_number=3, page_type="SOLUTION", slug="quem-tem-direito-p1",
                           h1_title="Quem tem direito",
                           main_content_structure=["Quem tem direito", "Documentos"])]}),
    }


@pytest.mark.parametrize("variante", sorted(_variantes()))
def test_ouro_render_direto(variante: str) -> None:
    nome, ctx = _variantes()[variante]
    _confere(f"render__{variante}.txt", render(nome, **ctx))


# ---------------------------------------------------------------------------
# 2. o pipeline inteiro: prompt de cada passo + ordem
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cenario", ["legado", "contextual"])
def test_ouro_pipeline_flag_desligada(cenario: str, tmp_path: Path, monkeypatch) -> None:
    congelar_data(monkeypatch)
    settings = settings_do_cenario(tmp_path)
    assert getattr(settings.run, "editorial_v2", False) is False
    arq = arquitetura_base(editorial=(cenario == "contextual"))
    state, deps, _llm = rodar_cenario(tmp_path, arq, settings)

    prompts = prompts_do_run(deps.runner.runs_dir, state.run_id)
    assert prompts, "o cenário não gerou nenhum prompt"
    for passo, texto in prompts.items():
        _confere(f"pipeline__{cenario}__{passo}.txt", texto)
    # nenhum passo novo pode aparecer escondido: o CONJUNTO de passos com
    # prompt também é ouro.
    _confere(f"pipeline__{cenario}__passos.json",
             json.dumps(sorted(prompts), ensure_ascii=False, indent=1) + "\n")
    _confere(f"pipeline__{cenario}__ordem.json",
             json.dumps(ordem_do_run(deps.runner.runs_dir, state.run_id, state),
                        ensure_ascii=False, indent=1) + "\n")


# ---------------------------------------------------------------------------
# 3. o prompt do adaptador de pesquisa (ver a EXCEÇÃO DECLARADA no topo)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reprovadas", [None, ["https://exemplo.gov.br/pagina-que-nao-existe"]])
def test_ouro_prompt_do_adaptador_de_pesquisa(reprovadas, monkeypatch) -> None:
    congelar_data(monkeypatch)
    from funnelforge.adapters.research_perplexity import _research_prompt

    sufixo = "com_reprovadas" if reprovadas else "simples"
    _confere(f"pesquisa__adaptador__{sufixo}.txt",
             _research_prompt("Tarifa social de energia", "- Quem tem direito\n- Onde pedir",
                              reprovadas))
