"""Similaridade lexical entre páginas do mesmo tema não bloqueia (10/10/2026).

Os guardas de estado anotavam `duplicate_content`/`hub_not_distinct` e
reprovavam o `write_pN`: a página virava `blocked_pN`, saía da revisão e do
build e, numa retomada, era redigida de novo. Agora a métrica é observação
(`similaridade_lexical`) levada ao revisor contextual; o status não muda.
"""
from types import SimpleNamespace as NS

from funnelforge.domain.models import (
    FunnelPlan, Page, PageDraft, RunState, StepResult, StepStatus,
)
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.pipeline import _done, _falhou
from funnelforge.pipeline.retry_policy import classe_da_issue, classificar_issues
from funnelforge.pipeline.uniqueness import jaccard

_TEMA = ("saque aniversario fgts saldo demissao multa rescisoria retirada anual "
         "modalidade aplicativo caixa calendario parcela antecipacao")


def _estado(conteudos: dict[int, str]) -> tuple[RunState, FunnelPlan]:
    plan = FunnelPlan(total_pages=3, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="LP", slug="fgts"),
        Page(page_number=2, page_type="PRESELL", h1_title="Hub", slug="fgts-pr"),
        Page(page_number=3, page_type="SOLUTION", h1_title="Vale a pena", slug="fgts-p1"),
    ])
    state = RunState(run_id="sim", plan=plan)
    for n, texto in conteudos.items():
        state.drafts[n] = PageDraft(page_number=n, page_type="SOLUTION", format="gutenberg",
                                    content=f"<!-- wp:paragraph --><p>{texto}</p><!-- /wp:paragraph -->",
                                    word_count=len(texto.split()))
        state.step_status[f"write_p{n}"] = StepResult(step=f"write_p{n}",
                                                      status=StepStatus.OK, attempts=1)
    return state, plan


def _deps(limiar=0.35, hub=0.6):
    return NS(settings=NS(uniqueness=NS(jaccard_threshold=limiar,
                                        hub_distinction_threshold=hub)))


def test_vocabulario_do_tema_vira_observacao_e_nao_reprova_a_redacao():
    state, plan = _estado({1: _TEMA + " resposta da lp", 2: _TEMA + " escolha do hub",
                           3: _TEMA + " troca e consequencia"})
    assert jaccard(state.drafts[3].content, state.drafts[2].content) >= 0.35
    for page in plan.pages:
        st.uniqueness_state_guard(state, page, _deps())
        st.presell_hub_distinction_guard(state, page, _deps())
        st.uniqueness_state_guard(state, page, _deps())          # idempotente
    for n in (1, 2, 3):
        res = state.step_status[f"write_p{n}"]
        assert res.status is StepStatus.OK
        assert [i.code for i in res.issues] == ["similaridade_lexical"]
        assert "Observação, não defeito" in res.issues[0].message
        # A página continua "feita": o laço não a redige de novo nem a condena.
        assert _done(state, f"write_p{n}") and not _falhou(state, f"write_p{n}")


def test_paginas_distintas_nao_ganham_observacao():
    state, plan = _estado({1: "alfa beta gama delta", 3: "epsilon zeta eta theta"})
    st.uniqueness_state_guard(state, plan.pages[2], _deps())
    assert not state.step_status["write_p3"].issues


def test_observacao_e_codigos_antigos_sao_pista_para_o_revisor_nao_retentativa():
    for code in ("similaridade_lexical", "duplicate_content", "hub_not_distinct"):
        assert classe_da_issue(NS(code=code, message="")) == "patchavel"
        veredito = classificar_issues([NS(code=code, message="")], {"editorial_v2": True})
        assert veredito.retentar is False


def test_contrato_tecnico_de_gutenberg_continua_reprovando():
    quebrado = "<!-- wp:paragraph --><p>Sem fechamento</p>"
    codigos = {i.code for i in st.html_issues(quebrado)} if hasattr(st, "html_issues") else set()
    from funnelforge.pipeline.validators.checks import run_validators
    codigos |= {i.code for i in run_validators(["gutenberg_blocks"], quebrado, {"editorial_v2": True})}
    assert codigos, "o portão técnico de Gutenberg deixou de acusar bloco sem fechamento"
    assert all(classe_da_issue(NS(code=c, message="")) == "estrutural" for c in codigos)
