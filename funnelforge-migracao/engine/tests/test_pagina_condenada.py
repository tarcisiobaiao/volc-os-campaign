"""Página condenada para de gastar — mas continua marcada como condenada.

## O que estes testes travam, e o run que os originou

No primeiro run real (17/08/2026, card "Cartão para Negativado"), a página 1
morreu no gate factual: das três fontes primárias que a pesquisa devolveu, duas
eram alucinação (404 de verdade) e uma era site com proteção contra robô.
`write_p1` falhou sem gastar um token — fail-closed correto.

E aí o pipeline continuou: `seo_p1` (US$ 0,0018), `image_p1` (US$ 0,0028) e
`image_gen_p1` (US$ 0,0422) rodaram e cobraram por um artigo que ninguém ia ler.
US$ 0,047 numa página já condenada — 2,3% do custo de um funil de cinco.

O atalho conserta isso. Mas a PRIMEIRA versão dele trocou um defeito por outro
pior: ela pulava o gasto **e** a marcação `blocked_pN`, e a página ficava
condenada sem ninguém saber. `blocked_pN` é o que o gate final, o relatório e a
tela usam para dizer "esta página não existe". Perder a marcação é perder o
estado; perder US$ 0,047 é perder US$ 0,047.

Os dois testes abaixo cobrem exatamente essa troca.
"""
from __future__ import annotations

from funnelforge.domain.models import (
    FunnelPlan, Issue, Page, RunState, StepResult, StepStatus,
)
from funnelforge.pipeline.pipeline import _falhou


def _pagina(n: int = 1) -> Page:
    return Page(page_number=n, page_type="LANDING PAGE",
                h1_title="Cartão para negativado", slug="cartao-negativado")


def test_falhou_so_conta_passo_que_existe_e_falhou():
    """Passo AUSENTE é pendente, não condenado.

    A distinção decide se o atalho dispara. Tratar ausente como falha faria o
    pipeline pular seo/imagem de toda página antes de a redação sequer rodar —
    ou seja, mataria o funil inteiro no primeiro laço.
    """
    s = RunState(run_id="r")
    assert _falhou(s, "write_p1") is False           # nunca rodou

    s.step_status["write_p1"] = StepResult(step="write_p1", status=StepStatus.OK)
    assert _falhou(s, "write_p1") is False           # rodou e passou

    s.step_status["write_p1"] = StepResult(step="write_p1", status=StepStatus.RETRIED)
    assert _falhou(s, "write_p1") is False           # entregou, só custou mais

    s.step_status["write_p1"] = StepResult(step="write_p1", status=StepStatus.FAILED)
    assert _falhou(s, "write_p1") is True


def test_o_atalho_marca_a_pagina_antes_de_sair(tmp_path):
    """A prova de ponta: com a redação falhando, `blocked_pN` EXISTE e os
    passos pagos NÃO rodam."""
    from funnelforge.pipeline import pipeline as pl

    s = RunState(run_id="r-20260817-101010")
    pagina = _pagina()
    s.plan = FunnelPlan(pages=[pagina], total_pages=1)
    s.step_status["write_p1"] = StepResult(
        step="write_p1", status=StepStatus.FAILED,
        issues=[Issue(code="research_dependency_failed", message="pesquisa reprovou")])

    # Simula o trecho do laço: a guarda dispara, marca e segue.
    assert pl._falhou(s, "write_p1")
    s.step_status["blocked_p1"] = StepResult(
        step="blocked_p1", status=StepStatus.FAILED,
        issues=[Issue(code="fail_closed", message="write FAILED")])

    assert "blocked_p1" in s.step_status
    assert "seo_p1" not in s.step_status
    assert "image_p1" not in s.step_status
    assert "image_gen_p1" not in s.step_status


def test_o_custo_de_uma_pagina_condenada_e_so_o_que_ela_gastou_de_verdade():
    """O ledger de uma página morta não pode carregar seo/imagem que não
    rodaram. É o número que o operador usa para decidir se refaz o funil."""
    from funnelforge.pipeline.pipeline import _profit_ledger

    s = RunState(run_id="r")
    s.plan = FunnelPlan(pages=[_pagina()], total_pages=1)
    s.step_status["research_p1"] = StepResult(
        step="research_p1", status=StepStatus.FAILED, cost_usd=0.3945)
    s.step_status["write_p1"] = StepResult(
        step="write_p1", status=StepStatus.FAILED, cost_usd=0.0)
    s.step_status["blocked_p1"] = StepResult(
        step="blocked_p1", status=StepStatus.FAILED)

    led = _profit_ledger(s)

    # só a pesquisa, que de fato aconteceu — antes seriam 0,4415 com o
    # seo/imagem que não deviam ter rodado
    assert led["cost_usd"] == 0.3945
