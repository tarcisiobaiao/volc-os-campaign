"""A JORNADA do leitor sai do arquiteto e chega intacta ao `writing_jobs`.

O motor (`funnelforge.adapters.briefing_volc`) lê `writer_briefing.jornada` e
`funnel_strategy.jornada` — este teste prende o lado do backend desse contrato;
o lado do motor está em `funnelforge-migracao/engine/tests/test_jornada_senac.py`,
que carrega uma arquitetura com exatamente esta forma.
"""
from __future__ import annotations

import copy

from app.agents.funnel_pro.page_factory import architect_pages_to_funnel_pages, page_factory
from app.entities.funnel_roles import apply_roles_and_slugs
from app.n8n_prompts import funnel_builder as fb

JORNADA_RENDA = {
    "duvida_id": "renda", "pergunta_principal": "Minha renda se enquadra?",
    "resposta_imediata": "Até dois salários mínimos por pessoa.",
    "ja_resolvido": [], "proxima_duvida": "estado",
    "saida_oficial": {"esperada": False, "classificacao": "nao_aplicavel"},
}

ARQUITETO = {
    "funnel_strategy": {"avatar_summary": "a", "tone_voice": "t", "total_pages": 2,
                        "jornada": {"intencao_principal": "Vaga gratuita",
                                    "checkpoint": "estado", "coortes": []}},
    "pages": [
        {"page_number": 1, "page_type": "LANDING PAGE", "h1_title": "Senac gratuito",
         "slug": "senac-gratuito", "next_page_slug": "renda-senac",
         "editorial": {"reader_question": "q", "useful_delivery": "d", "cta_label": "c",
                       "links": [{"target": "renda-senac", "reason": "r"}]},
         "jornada": {**JORNADA_RENDA, "duvida_id": "senac_gratuito", "proxima_duvida": "renda"}},
        {"page_number": 2, "page_type": "HUB", "h1_title": "Renda", "slug": "renda-senac",
         "editorial": {"reader_question": "q2", "useful_delivery": "d2", "cta_label": "c2",
                       "links": []},
         "jornada": JORNADA_RENDA},
    ],
}


def test_prompt_do_arquiteto_pede_a_jornada_tipada():
    prompt = fb.FUNNEL_ARCHITECT_SYSTEM_MESSAGE + fb.build_funnel_architect_user(
        pais="Brasil", tema="Senac", lingua="pt-BR", data_atual="07/10/2026",
        supporting_data="kw", user_questions="q?")
    assert "<jornada>" in prompt
    for chave in ("duvida_id", "resposta_imediata", "ja_resolvido", "proxima_duvida",
                  "condicao_terminal", "saida_oficial", "monetizacao",
                  "retornos_justificados", "hipotese_de_medicao", "coortes"):
        assert f'"{chave}"' in prompt, chave
    assert "observacao_real" in prompt and "simulacao" in prompt
    assert "Abrir o CadÚnico no site do MDS" in prompt
    assert 'Nunca use rótulo genérico como "canal oficial"' in prompt


def test_page_factory_leva_a_jornada_ao_writer_briefing_e_a_pagina_canonica():
    jobs = page_factory(copy.deepcopy(ARQUITETO))["writingJobs"]
    assert jobs[1]["writer_briefing"]["jornada"] == JORNADA_RENDA
    paginas = architect_pages_to_funnel_pages(copy.deepcopy(ARQUITETO))
    assert paginas[1]["jornada"] == JORNADA_RENDA


def test_sufixo_de_slug_nao_toca_a_jornada():
    arq = copy.deepcopy(ARQUITETO)
    paginas, jobs = apply_roles_and_slugs(architect_pages_to_funnel_pages(arq),
                                          page_factory(arq)["writingJobs"])
    wb = jobs[1]["writer_briefing"]
    assert wb["current_url"] == "renda-senac-pr"
    assert wb["jornada"] == JORNADA_RENDA          # referências por duvida_id
    assert jobs[0]["writer_briefing"]["editorial"]["links"][0]["target"] == "renda-senac-pr"


def test_card_sem_jornada_continua_sem_jornada():
    arq = copy.deepcopy(ARQUITETO)
    for p in arq["pages"]:
        del p["jornada"]
    jobs = page_factory(arq)["writingJobs"]
    assert all(j["writer_briefing"]["jornada"] is None for j in jobs)


# ---------------------------------------------------------------------------
# 2ª rodada (07/10/2026): merge protegido no revisor real, normalização
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

from app.agents.base import AgentContext  # noqa: E402
from app.agents.funnel_pro.jornada_contrato import normalizar_arquitetura  # noqa: E402
from app.agents.funnel_pro.reviewer import FunnelReviewer  # noqa: E402
from app.config import Settings  # noqa: E402
from app.llm.mock import MockEngine  # noqa: E402

JORNADA_COMPLETA = {
    **JORNADA_RENDA,
    "coortes_de_entrada": ["organic_search"],
    "condicao_terminal": "Leitor sabe se se enquadra",
    "monetizacao": {"papel": "secundario", "restricoes": ["nada antes da resposta"]},
    "retornos_justificados": {"senac_gratuito": "quem entrou direto"},
    "hipotese_de_medicao": "quem fez a conta segue",
    "evidencias": [{"natureza": "hipotese", "afirmacao": "x", "fonte": "arquiteto"}],
    "valor": {"problema": "p", "informacao_nova": "i", "capacidade_do_leitor": "c",
              "entregas": ["calculo"]},
}


def test_revisor_real_com_saida_parcial_preserva_a_jornada(monkeypatch):
    arq = copy.deepcopy(ARQUITETO)
    arq["pages"][1]["jornada"] = copy.deepcopy(JORNADA_COMPLETA)
    parcial = copy.deepcopy(arq)
    parcial["pages"][1]["jornada"] = {"duvida_id": "renda", "pergunta_principal": "Minha renda se enquadra?",
                                      "resposta_imediata": "Até dois salários mínimos por pessoa.",
                                      "ja_resolvido": [], "proxima_duvida": "estado",
                                      "condicao_terminal": "",
                                      "saida_oficial": {"esperada": False, "classificacao": "nao_aplicavel"}}
    del parcial["funnel_strategy"]["jornada"]

    class _Cliente:
        ultimo_uso = {"modelo_solicitado": "gemini-3.5-flash", "modelo_servido": "gemini-3.5-flash",
                      "entrada": 100, "saida": 200, "latencia_ms": 900}

        async def complete_json(self, system, user):
            return {**parcial, "changes": [], "achados": []}

    monkeypatch.setattr(FunnelReviewer, "_gemini", lambda self: _Cliente())
    ctx = AgentContext(settings=Settings(gemini_api_key="k", google_api_key=None,
                                         supabase_url=None, supabase_service_role_key=None),
                       engine=MockEngine(), grounding=None)
    res = asyncio.run(FunnelReviewer(ctx).review(arq, entity_facts={}, forced_language="pt-BR"))
    assert res["pages"][1]["jornada"] == JORNADA_COMPLETA
    assert res["funnel_strategy"]["jornada"] == ARQUITETO["funnel_strategy"]["jornada"]
    assert res["jornada_preservada"]
    assert res["telemetria"][0]["etapa"] == "revisor_do_arquiteto"


def test_revisor_substitui_mapa_de_retornos_quando_corrige_id_invalido(monkeypatch):
    arq = copy.deepcopy(ARQUITETO)
    arq["pages"][1]["jornada"] = copy.deepcopy(JORNADA_COMPLETA)
    arq["pages"][1]["jornada"]["retornos_justificados"] = {
        "slug_antigo_invalido": "voltar para conferir"
    }
    revisado = copy.deepcopy(arq)
    revisado["pages"][1]["jornada"]["retornos_justificados"] = {
        "senac_gratuito": "voltar para conferir"
    }

    class _Cliente:
        async def complete_json(self, system, user):
            return {**revisado, "changes": ["ID do retorno corrigido"], "achados": []}

    monkeypatch.setattr(FunnelReviewer, "_gemini", lambda self: _Cliente())
    ctx = AgentContext(settings=Settings(gemini_api_key="k", google_api_key=None,
                                         supabase_url=None, supabase_service_role_key=None),
                       engine=MockEngine(), grounding=None)
    res = asyncio.run(FunnelReviewer(ctx).review(arq, entity_facts={}, forced_language="pt-BR"))

    assert res["pages"][1]["jornada"]["retornos_justificados"] == {
        "senac_gratuito": "voltar para conferir"
    }


def test_normalizacao_logo_apos_o_arquiteto_nomeia_campo_e_motivo():
    arq = copy.deepcopy(ARQUITETO)
    arq["pages"][1]["jornada"]["saida_oficial"]["classificacao"] = "Boa"
    arq["pages"][1]["jornada"]["entrada_direta"] = "talvez"
    normal, rel = normalizar_arquitetura(arq)
    assert normal["pages"][1]["jornada"]["saida_oficial"]["classificacao"] == "boa"
    assert rel["estado"] == "invalida"
    assert {"campo": "pagina[renda-senac].jornada.entrada_direta",
            "motivo": "'talvez' fora do vocabulário (autocontida, depende_de_contexto)"} in rel["erros"]


def test_prompt_pre_redacao_explicita_schema_factual_e_visual():
    p = fb.build_funnel_architect_user(pais='Brasil', tema='Gás', lingua='pt-BR',
        data_atual='08/10/2026', supporting_data='', user_questions='',
        brief_pre_arquitetura={'sha256':'fixture'})
    for chave in ('"id":"entidade.regra"', '"descricao"', '"tipos"', '"critico"',
                  'jornada.screenshot_necessario', 'jornada.imagem_necessaria', 'jornada.schema_tipos'):
        assert chave in p
