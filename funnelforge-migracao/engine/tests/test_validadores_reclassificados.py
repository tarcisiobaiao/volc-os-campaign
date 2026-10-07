"""VALIDADORES RECLASSIFICADOS pela régua da Frente A (etapa B5, diretriz 8).

No ramo editorial novo, julgamento semântico por palavra/regex deixa de
reprovar e de forçar reescrita integral: vira LOCALIZADOR entregue ao revisor
(classe `patchavel`). O que é objetivamente verificável continua bloqueando
(schema, HTML, URLs, same_domain, external_cta_authorized, raw_html_contract,
ad_interaction na zona de anúncio, identidade estrutural, grounding numérico,
limites). Com a flag desligada, nada muda (o ouro prova).
"""
from __future__ import annotations

import json

from funnelforge.config.settings import StepConfig
from funnelforge.domain.models import Issue, StepStatus
from funnelforge.pipeline.retry_policy import (
    CODIGOS_PATCHAVEIS,
    CODIGOS_REMOVIDOS_NO_V2,
    classe_da_issue,
    classificar_issues,
    separar_para_o_revisor,
)
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM

FEAR = Issue(code="fear_language", message="Gatilho de medo/escassez proibido (tom calmo obrigatório).")
OFICIAL = Issue(code="official_impersonation", message="Linguagem de falsa oficialidade proibida.")
EXECUCAO = Issue(code="cta_execution", message="CTA com verbo de execução de serviço (proibido).")
PRIMEIRA = Issue(code="cta_first_person", message="CTA em 1ª pessoa emocional na LP (proibido).")
VISUAL = Issue(code="missing_semantic_block", message="Engajamento 'sequencial' exige bloco wp:list.")
LEGAL = Issue(code="ungrounded_legal_claim", message="Afirmação de força legal sem dispositivo.")
LEGAL_CIT = Issue(code="critical_claim_without_citation",
                  message="Afirmação legal não cita sua fonte primária: 'x'.")
NUM_CIT = Issue(code="critical_claim_without_citation",
                message="Afirmação crítica não cita sua fonte primária: 'R$ 500'.")
DIRECAO_FORA = Issue(code="directional_copy_outside_widget",
                     message="Parágrafo editorial 7 orienta por posição; a instrução deve viver dentro do componente interativo.")
DIRECAO_ZONA = Issue(code="directional_copy_outside_widget",
                     message="Parágrafo editorial 3 (na zona de anúncio) orienta por posição; a instrução deve viver dentro do componente interativo.")
DOMINIO = Issue(code="cross_domain", message="Link para host não autorizado.")
SCHEMA = Issue(code="lp_schema", message="sections deve ser lista.")
NUMERO = Issue(code="ungrounded_critical_claim", message="Número sem fato verificado.")


def test_classes_da_regua():
    for issue in (FEAR, OFICIAL, EXECUCAO, LEGAL, LEGAL_CIT, DIRECAO_FORA):
        assert classe_da_issue(issue) == "patchavel", issue.code
    for issue in (PRIMEIRA, VISUAL):
        assert classe_da_issue(issue) == "removido", issue.code
    for issue in (DOMINIO, SCHEMA, NUMERO, NUM_CIT, DIRECAO_ZONA):
        assert classe_da_issue(issue) == "estrutural", issue.code
    assert {"fear_language", "official_impersonation", "cta_execution", "language_pt",
            "no_compliance", "anchor_incongruent"} <= CODIGOS_PATCHAVEIS
    assert {"cta_first_person", "missing_semantic_block"} == CODIGOS_REMOVIDOS_NO_V2


def test_separar_para_o_revisor():
    bloqueantes, localizadores = separar_para_o_revisor([FEAR, DOMINIO, PRIMEIRA, LEGAL])
    assert bloqueantes == [DOMINIO]
    assert [i.code for i in localizadores] == ["fear_language", "ungrounded_legal_claim"]


def test_classificar_no_v2_patchavel_nao_retenta_e_no_v1_retenta():
    v2 = classificar_issues([FEAR], {"editorial_v2": True})
    assert v2.retentar is False and v2.classe == "patchavel"
    assert classificar_issues([FEAR], {}).retentar is True        # ramo antigo intocado
    assert classificar_issues([FEAR, DOMINIO], {"editorial_v2": True}).retentar is True


def _runner(tmp_path, respostas):
    llm = FakeLLM(responses=respostas)
    return Runner(llm=llm, max_retries=2, runs_dir=tmp_path / "runs"), llm


CFG = StepConfig(model="m", fallbacks=[], temperature=0.7,
                 validators=["calm_utility", "gutenberg_blocks"])
TEXTO_COM_VAGAS = ("<!-- wp:paragraph --><p>Cada turma tem vagas limitadas conforme o "
                   "edital.</p><!-- /wp:paragraph -->")


def test_runner_v2_nao_reescreve_a_pagina_por_palavra(tmp_path):
    runner, llm = _runner(tmp_path, [TEXTO_COM_VAGAS])
    texto, res = runner.run_llm_step("write_p3", CFG, [{"role": "user", "content": "x"}],
                                     ctx={"editorial_v2": True}, run_id="r-1-2")
    assert len(llm.calls) == 1 and texto == TEXTO_COM_VAGAS
    assert res.status is StepStatus.OK
    assert [i.code for i in res.issues] == ["localizador:fear_language"]


def test_runner_v2_ainda_reescreve_por_falha_estrutural_sem_mandato_de_tom(tmp_path):
    quebrado = TEXTO_COM_VAGAS.replace("<!-- /wp:paragraph -->", "")
    runner, llm = _runner(tmp_path, [quebrado, TEXTO_COM_VAGAS])
    _texto, res = runner.run_llm_step("write_p3", CFG, [{"role": "user", "content": "x"}],
                                      ctx={"editorial_v2": True}, run_id="r-1-2")
    assert len(llm.calls) == 2 and res.status is StepStatus.RETRIED
    feedback = llm.calls[1]["messages"][-1]["content"]
    assert "[unbalanced]" in feedback
    assert "fear_language" not in feedback and "tom calmo" not in feedback


def test_runner_sem_a_flag_continua_como_antes(tmp_path):
    runner, llm = _runner(tmp_path, [TEXTO_COM_VAGAS, TEXTO_COM_VAGAS, TEXTO_COM_VAGAS])
    _texto, res = runner.run_llm_step("write_p3", CFG, [{"role": "user", "content": "x"}],
                                      ctx={}, run_id="r-1-2")
    assert len(llm.calls) == 3 and res.status is StepStatus.FAILED
    assert res.issues[0].code == "fear_language"


def test_lp_v2_primeira_pessoa_sai_e_schema_continua_bloqueando(tmp_path):
    lp = {"hero_title": "T", "hero_subtitle": "S", "article_title": "A",
          "intro": "<p>i</p>", "sections": [{"title": "t", "body": "<p>b</p>"}] * 4,
          "faq": [{"q": "q?", "a": "a"}], "transition": "<p>t</p>",
          "cta_texts": ["Quero ver quem tem direito", "Ver regras", "Ver passo a passo"]}
    cfg = StepConfig(model="m", fallbacks=[], temperature=0.7, validators=["lp_json_contract"])
    runner, llm = _runner(tmp_path, [json.dumps(lp)])
    _t, res = runner.run_llm_step("write_p1", cfg, [{"role": "user", "content": "x"}],
                                  ctx={"editorial_v2": True}, run_id="r-1-2")
    assert res.status is StepStatus.OK and len(llm.calls) == 1
    quebrado = dict(lp, sections=lp["sections"][:3])
    runner, llm = _runner(tmp_path / "b", [json.dumps(quebrado)] * 3)
    _t, res = runner.run_llm_step("write_p1", cfg, [{"role": "user", "content": "x"}],
                                  ctx={"editorial_v2": True}, run_id="r-1-2")
    assert res.status is StepStatus.FAILED and {i.code for i in res.issues} == {"lp_sections"}
