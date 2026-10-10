"""A direção do operador chega à revisão global como dado, abaixo das regras."""
from types import SimpleNamespace as NS

from funnelforge.domain.models import StepResult, StepStatus
from funnelforge.pipeline import inteligencia
from funnelforge.pipeline import revisao as rv
from funnelforge.pipeline import steps as st


def _rodar(monkeypatch, **kw):
    enviadas = []

    class Runner:
        def run_llm_step(self, nome, cfg, mensagens, ctx, run_id):
            enviadas.append(mensagens[0]["content"])
            return '{"paginas": []}', StepResult(step=nome, status=StepStatus.OK)

    monkeypatch.setattr(st, "step_seo", lambda *a: None)
    monkeypatch.setattr(st, "_contexto_da_revisao", lambda *a: None)
    monkeypatch.setattr(st, "_revisar_pagina", lambda *a, **k: None)
    monkeypatch.setattr(rv, "documento_de", lambda *a: None)
    monkeypatch.setattr(rv, "montar_prompt_do_revisor", lambda *a: "PROMPT")
    monkeypatch.setattr(inteligencia, "_inventario_de_midia", lambda *a: {})
    state = NS(drafts={1: None}, seo={}, run_id="r", step_status={},
               brief_pre_arquitetura=NS(model_dump=lambda: {}))
    deps = NS(runner=Runner(), settings=NS(steps={"revisor": None}))
    inteligencia.revisar_lote(state, [NS(page_number=1)], deps, **kw)
    return enviadas[0]


def test_direcao_entra_na_mensagem_da_revisao_global(monkeypatch):
    texto = _rodar(monkeypatch, direcao="Subtítulo com o benefício comprovado.")
    assert "DIREÇÃO DO OPERADOR" in texto and "benefício comprovado" in texto
    assert "só com fatos do inventário" in texto


def test_sem_direcao_a_mensagem_nao_muda(monkeypatch):
    assert "DIREÇÃO DO OPERADOR" not in _rodar(monkeypatch)
