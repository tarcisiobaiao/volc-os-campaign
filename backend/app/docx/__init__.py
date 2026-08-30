"""VOLC DOCX generation (padrão institucional VOLC) para o Pautador Pro.

O briefing tem duas saídas do MESMO modelo (`briefing_model`): o `.docx` anexado
na task do ClickUp e a página HTML que o operador abre em nova aba.
"""
from .briefing_html import render_briefing_html
from .briefing_model import BriefingModel, briefing_filename, build_briefing_model
from .funnel_briefing import build_funnel_briefing

__all__ = [
    "build_funnel_briefing",
    "briefing_filename",
    "build_briefing_model",
    "render_briefing_html",
    "BriefingModel",
]
