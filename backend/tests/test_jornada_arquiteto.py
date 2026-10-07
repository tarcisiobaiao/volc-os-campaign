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
