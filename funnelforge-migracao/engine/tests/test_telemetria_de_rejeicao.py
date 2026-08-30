"""Trabalho REJEITADO também foi pago — e o ledger tem que dizer isso.

## O defeito

Dois passos chamavam o modelo, recebiam a telemetria de volta e a jogavam fora
ao montar o `StepResult`:

- `_widget_skip`: quando o sanitizador reprova o widget, a página publica sem
  ele. O gasto da geração aconteceu. Ia para o ledger como zero.
- `declarar_engajamento`: sempre gravava custo, tokens, modelo e tentativas
  zerados, inclusive no caminho de sucesso.

Medido no run de referência (`referencia/run-fgts-producao/state.json`):
`widget_p5` está gravado com `cost_usd: 0.0`, `attempts: 0`, `model_used: ''` e
duas issues — `widget_rejected` e `ampersand_in_script`. O relatório declarou
US$ 2,547234 e a fatura foi maior.

## Por que importa mais do que parece

Este número é a régua de decisão do operador: ele olha quanto já saiu para
decidir se vale cancelar um run. Um custo subestimado é pior que custo nenhum,
porque parece confiável. E rejeição não é ausência de gasto — é gasto que não
virou entrega, que é justamente o que ele mais precisa enxergar.
"""
from __future__ import annotations

from funnelforge.domain.models import Issue, Page, StepResult, StepStatus
from funnelforge.pipeline.steps import _widget_skip


def _pagina() -> Page:
    return Page(page_number=5, page_type="SOLUTION", h1_title="Como pedir",
                slug="como-pedir-p1")


def test_widget_rejeitado_preserva_o_que_foi_pago():
    """O caso real: o sanitizador reprovou por um único `&&` no script."""
    pago = StepResult(step="widget_p5", status=StepStatus.OK,
                      model_used="gemini/gemini-3.5-flash", attempts=1,
                      prompt_tokens=5829, completion_tokens=14508,
                      cost_usd=0.139316, latency_ms=59388)

    r = _widget_skip(_pagina(), Issue(code="ampersand_in_script", message="&& no script"),
                     pago=pago)

    assert r.status is StepStatus.SKIPPED          # a página publica sem widget
    assert r.cost_usd == 0.139316                  # mas o dinheiro saiu
    assert r.prompt_tokens == 5829
    assert r.completion_tokens == 14508
    assert r.latency_ms == 59388
    assert r.attempts == 1
    assert r.model_used == "gemini/gemini-3.5-flash"
    # e o motivo continua legível, que é o outro metade da informação
    assert [i.code for i in r.issues] == ["widget_rejected", "ampersand_in_script"]


def test_sem_chamada_paga_o_zero_e_verdade():
    """Nem toda rejeição custou: `widget_no_config` acontece ANTES do modelo.
    Aqui zero é medição correta, não omissão — e o teste trava a diferença."""
    r = _widget_skip(_pagina(), Issue(code="widget_no_config", message="sem config"))

    assert r.cost_usd == 0.0
    assert r.attempts == 0
    assert r.model_used == ""


def test_o_ledger_soma_a_rejeicao():
    """A prova de ponta: o custo do run passa a incluir o widget rejeitado."""
    from funnelforge.domain.models import FunnelPlan, RunState
    from funnelforge.pipeline.pipeline import _profit_ledger

    estado = RunState(run_id="r")
    estado.plan = FunnelPlan(pages=[_pagina()])
    estado.step_status["write_p5"] = StepResult(
        step="write_p5", status=StepStatus.OK, cost_usd=0.20)
    estado.step_status["widget_p5"] = _widget_skip(
        _pagina(), Issue(code="ampersand_in_script", message="&&"),
        pago=StepResult(step="widget_p5", status=StepStatus.OK, cost_usd=0.139316))

    led = _profit_ledger(estado)

    # 0.20 + 0.139316 — antes do conserto seria 0.20, e o operador decidiria
    # cancelar (ou não) com 41% do gasto invisível
    assert led["cost_usd"] == 0.339316
