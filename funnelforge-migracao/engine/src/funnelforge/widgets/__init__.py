"""Motor de widgets: a LLM descreve o conteúdo, o motor imprime o HTML.

Porta de entrada única — `pipeline/steps.py::step_widget` só precisa destes três.
"""
from funnelforge.widgets.contrato import (
    ARQUETIPOS, Widget, WidgetInvalido, chave_por_nome, ler,
)
from funnelforge.widgets.render import renderizar, texto_visivel

__all__ = ["ARQUETIPOS", "Widget", "WidgetInvalido", "chave_por_nome", "ler",
           "renderizar", "texto_visivel"]
