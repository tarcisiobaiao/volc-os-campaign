"""A PONTE DO BRIEFING: `funnel_architecture` (VOLC O.S.) -> `FunnelPlan`.

Cobre os quatro pontos em que a conversão pode calar um defeito:
1. o slug certo é `writer_briefing.current_url` (o `pages[]` canônico não tem);
2. `keywords` vem como STRING com vírgulas (o funil de produção saiu com 0 de
   7 páginas com `target_keywords` justamente por isso);
3. `page_type` do VOLC vem acentuado ("SOLUÇÃO") e não bate com "SOLUTION";
4. um plano injetado PRECISA passar pelos quatro passos de normalização —
   sem `_populate_routes` toda página fica com `routes=[]`.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from funnelforge.adapters.briefing_docx import DocxBriefingLoader
from funnelforge.adapters.briefing_volc import (
    carregar_arquitetura,
    plano_do_funnel_architecture,
)
from funnelforge.config.settings import load_settings
from funnelforge.domain.models import PageRole, StepStatus, effective_role
from funnelforge.pipeline.pipeline import Deps, run_pipeline
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM

_TITULOS = {
    1: "Saque FGTS Aniversário: Como Funciona",
    2: "Guia Completo do FGTS",
    3: "Como Consultar o Saldo do FGTS",
    4: "Como Sacar o FGTS Aniversário",
    5: "Prazos de Pagamento do FGTS Aniversário",
}
_SLUGS = {
    1: "saque-fgts",
    2: "quem-tem-direito-pr",
    3: "como-consultar-saldo-p1",
    4: "como-sacar-p2",
    5: "prazos-pagamento-p3",
}
# `page_type` como o arquiteto do VOLC devolve: acentuado, em português.
_TIPOS = {1: "LANDING PAGE", 2: "PRÉ-SELL", 3: "SOLUÇÃO", 4: "SOLUÇÃO", 5: "SOLUÇÃO"}
_KEYWORDS = {
    1: "fgts, saque aniversario",
    2: "fgts guia",
    3: "consultar saldo fgts",
    4: "sacar fgts",
    5: "prazo fgts",
}


def arquitetura_volc() -> dict:
    """Um `funnel_architecture` fiel ao que o VOLC grava: `pages[]` canônico
    (sem slug, sem page_type, sem keywords) + `writing_jobs[]` com o
    `writer_briefing` completo."""
    paginas, jobs = [], []
    for pos in range(1, 6):
        proximo = _SLUGS.get(pos + 1)
        paginas.append({
            "position": pos,
            "page_title": _TITULOS[pos],
            "avatar": "Trabalhador CLT buscando antecipar o FGTS.",
            "stage": "tofu" if pos == 1 else ("mofu" if pos <= 3 else "bofu"),
            "emotional_goal": f"objetivo emocional da página {pos}",
            "subtitles": [f"H2: Seção {pos}.1", f"H2: Seção {pos}.2"],
            "internal_links": [],
            "intro_section": ["Abertura escrita pelo arquiteto."],
            "closing_section": ["Fechamento escrito pelo arquiteto."],
        })
        jobs.append({
            "job_id": f"write_p{pos}",
            "page_type": _TIPOS[pos],
            "writer_briefing": {
                "avatar_context": "Trabalhador CLT buscando antecipar o FGTS.",
                "tone": "calmo, editorial, factual",
                "page_num": pos,
                "total_pages": 5,
                "headline": _TITULOS[pos],
                "objective": f"objetivo emocional da página {pos}",
                "current_url": _SLUGS[pos],
                "cta_text": "Ver o próximo passo",
                # a `page_factory` do VOLC põe "/inicio" na última página
                "cta_link": f"/{proximo}" if proximo else "/inicio",
                "skeleton": f"- H2: Seção {pos}.1\n- H2: Seção {pos}.2",
                "keywords": _KEYWORDS[pos],
                "intro_section": ["Abertura escrita pelo arquiteto."],
                "closing_section": ["Fechamento escrito pelo arquiteto."],
            },
        })
    return {
        "funnel_strategy": {
            "avatar_summary": "Trabalhador CLT buscando antecipar o FGTS.",
            "tone_voice": "calmo, editorial, factual",
            "total_pages": 5,
        },
        "pages": paginas,
        "writing_jobs": jobs,
    }


# ---------------------------------------------------------------------------
# conversão
# ---------------------------------------------------------------------------


def test_slug_vem_do_writer_briefing_e_o_papel_sai_dele():
    plano = plano_do_funnel_architecture(arquitetura_volc())
    assert [p.slug for p in plano.pages] == [_SLUGS[i] for i in range(1, 6)]
    assert [effective_role(p) for p in plano.pages] == [
        PageRole.LP, PageRole.PRESELL,
        PageRole.SOLUTION, PageRole.SOLUTION, PageRole.SOLUTION,
    ]


def test_page_type_acentuado_do_volc_vira_o_vocabulario_do_engine():
    """"SOLUÇÃO"/"PRÉ-SELL" nunca chegam ao engine: `step_write`/`step_build`
    comparam `page_type == "LANDING PAGE"` e uma string acentuada faria a LP
    entrar pelo redator de página interna."""
    plano = plano_do_funnel_architecture(arquitetura_volc())
    assert [p.page_type for p in plano.pages] == [
        "LANDING PAGE", "HUB", "SOLUTION", "SOLUTION", "SOLUTION"]


def test_keywords_string_com_virgula_vira_lista():
    plano = plano_do_funnel_architecture(arquitetura_volc())
    assert plano.pages[0].target_keywords == ["fgts", "saque aniversario"]
    assert all(p.target_keywords for p in plano.pages), "nenhuma página pode ficar sem keyword"


def test_keywords_sentinela_da_page_factory_nao_vira_keyword():
    arq = arquitetura_volc()
    arq["writing_jobs"][2]["writer_briefing"]["keywords"] = "Keywords do tema principal"
    plano = plano_do_funnel_architecture(arq)
    assert plano.pages[2].target_keywords == []


def test_next_page_slug_sai_do_cta_link_sem_a_barra():
    plano = plano_do_funnel_architecture(arquitetura_volc())
    assert plano.pages[0].next_page_slug == "quem-tem-direito-pr"
    assert plano.pages[3].next_page_slug == "prazos-pagamento-p3"


def test_cta_link_para_fora_do_funil_nao_vira_next_page_slug():
    """A `page_factory` do VOLC preenche "/inicio" na última página e
    "/pagina-N" quando o arquiteto não declarou destino. São páginas que não
    existem: melhor vazio que um href morto."""
    plano = plano_do_funnel_architecture(arquitetura_volc())
    assert plano.pages[4].next_page_slug == ""


def test_estrutura_e_estrategia_sao_preservadas():
    plano = plano_do_funnel_architecture(arquitetura_volc())
    assert plano.pages[0].main_content_structure == ["H2: Seção 1.1", "H2: Seção 1.2"]
    assert plano.avatar_summary.startswith("Trabalhador CLT")
    assert plano.tone_voice == "calmo, editorial, factual"
    assert plano.total_pages == 5


def test_estrutura_cai_para_o_skeleton_quando_pages_nao_veio():
    arq = arquitetura_volc()
    arq["pages"] = []
    plano = plano_do_funnel_architecture(arq)
    assert plano.pages[0].main_content_structure == ["H2: Seção 1.1", "H2: Seção 1.2"]
    assert plano.pages[0].h1_title == _TITULOS[1]


def test_slug_sem_sufixo_recebe_o_sufixo_da_posicao():
    """Arquitetura gravada antes de `apply_roles_and_slugs`: sem sufixo,
    `derive_role` leria as 5 páginas como LP."""
    arq = arquitetura_volc()
    for pos, job in enumerate(arq["writing_jobs"], start=1):
        job["writer_briefing"]["current_url"] = f"tema-{pos}"
    plano = plano_do_funnel_architecture(arq)
    assert [p.slug for p in plano.pages] == [
        "tema-1", "tema-2-pr", "tema-3-p1", "tema-4-p2", "tema-5-p3"]


def test_arquitetura_sem_writing_jobs_falha_com_mensagem_util():
    arq = arquitetura_volc()
    arq["writing_jobs"] = []
    with pytest.raises(ValueError, match="writing_jobs"):
        plano_do_funnel_architecture(arq)


def test_pagina_sem_current_url_falha_em_portugues():
    arq = arquitetura_volc()
    arq["writing_jobs"][2]["writer_briefing"]["current_url"] = ""
    with pytest.raises(ValueError, match="sem slug"):
        plano_do_funnel_architecture(arq)


def test_aceita_a_linha_do_banco_com_o_envelope():
    plano = plano_do_funnel_architecture({"id": 73, "funnel_architecture": arquitetura_volc()})
    assert len(plano.pages) == 5


def test_carregar_arquitetura_le_o_json(tmp_path: Path):
    caminho = tmp_path / "card-73.json"
    caminho.write_text(json.dumps(arquitetura_volc(), ensure_ascii=False), encoding="utf-8")
    assert plano_do_funnel_architecture(carregar_arquitetura(caminho)).total_pages == 5


# ---------------------------------------------------------------------------
# a armadilha do `_fresh_extract` + o run inteiro pela ponte
# ---------------------------------------------------------------------------


def _deps(tmp_path: Path, config_files: Path):
    from tests.test_smoke_e2e import _responder

    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    llm = FakeLLM(responses=_responder)
    runner = Runner(llm=llm, max_retries=settings.run.max_retries, runs_dir=tmp_path / "runs")
    return llm, Deps(llm=llm, research=None, image_gen=None, image_proc=None,
                     publisher=None, loader=DocxBriefingLoader(), settings=settings,
                     runner=runner)


def test_plano_injetado_passa_pelos_quatro_passos_de_normalizacao(
    tmp_path: Path, config_files: Path
):
    """A armadilha: `_fresh_extract` é avaliado ANTES de `step_extract`, e um
    plano pré-populado caía no ramo do resume — pulando expand/dedupe/
    engajamento/rotas. Sem rotas, `pagespec` reprova toda escrita."""
    llm, deps = _deps(tmp_path, config_files)
    plano = plano_do_funnel_architecture(arquitetura_volc())

    state = run_pipeline(None, deps, only=None, publish=False,
                         plan=plano, timestamp="20260815-120000")

    assert state.plan is not None
    # rotas povoadas em TODAS as páginas (era o sintoma: routes=[] -> cta_too_few)
    sem_rota = [p.slug for p in state.plan.pages if not p.routes]
    assert not sem_rota, f"páginas sem rota: {sem_rota}"
    # ordinais atribuídos (`assign_solution_ordinals`, dentro de expand_presell_hubs)
    solucoes = sorted((p for p in state.plan.pages if effective_role(p) is PageRole.SOLUTION),
                      key=lambda p: p.ordinal)
    assert [s.ordinal for s in solucoes] == [1, 2, 3]
    # o grafo foi validado — e passou
    assert "funnel_graph" not in state.step_status, state.step_status.get("funnel_graph")
    # nenhum passo falhou e as 5 páginas foram escritas
    for chave, res in state.step_status.items():
        assert res.status != StepStatus.FAILED, f"{chave} falhou: {res.issues}"
    assert len(state.drafts) == 5


def test_ponte_nao_gasta_a_chamada_do_extractor(tmp_path: Path, config_files: Path):
    """O ponto econômico da frente: o `step_extract` não roda."""
    llm, deps = _deps(tmp_path, config_files)
    plano = plano_do_funnel_architecture(arquitetura_volc())

    state = run_pipeline(None, deps, only="p1", publish=False,
                         plan=plano, timestamp="20260815-120000")

    assert "extract" not in state.step_status
    assert not (tmp_path / "runs" / state.run_id / "prompts" / "extract.txt").exists()


def test_run_id_sai_do_slug_da_lp(tmp_path: Path, config_files: Path):
    llm, deps = _deps(tmp_path, config_files)
    plano = plano_do_funnel_architecture(arquitetura_volc())
    state = run_pipeline(None, deps, only="p1", publish=False,
                         plan=plano, timestamp="20260815-120000")
    assert state.run_id == "saque-fgts-20260815-120000"


def test_plano_injetado_nunca_sobrescreve_um_resume(tmp_path: Path, config_files: Path):
    """Cinto de segurança: `plan` só entra num state SEM plano. Um `resume`
    continua sendo um resume — sem re-expandir, sem re-rotear."""
    from funnelforge.domain.models import RunState

    llm, deps = _deps(tmp_path, config_files)
    original = plano_do_funnel_architecture(arquitetura_volc())
    retomado = RunState(run_id="retomado", plan=copy.deepcopy(original))
    outro = plano_do_funnel_architecture(arquitetura_volc())
    outro.pages[0].slug = "nao-deveria-entrar"

    state = run_pipeline(None, deps, only="p1", publish=False,
                         resume_state=retomado, plan=outro)

    assert state.plan.pages[0].slug == "saque-fgts"
    # e o ramo de normalização não rodou: as rotas continuam vazias
    assert all(not p.routes for p in state.plan.pages)
