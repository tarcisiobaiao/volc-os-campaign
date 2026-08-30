"""
Prompts extracted VERBATIM from the two production n8n workflows:

  - n8n-peneirador-kw.json   -> Seed Optimizer + VOLC Funnel Prospector
  - n8n-funnel-builder.json  -> Funnel Architect (AI Agent1)

The system messages and JSON schemas are preserved ipsis litteris. Only the
n8n templating expressions ({{ $json.* }}, {{ $('Config Global1')... }}) were
replaced by safe Python placeholder tokens (__TOKEN__) injected by the
build_* helpers — the semantic text is unchanged.

This package is intentionally SEPARATE from app/prompts.py (the discovery
GOD MODE prompt) so the working Phase-1 discovery is never touched.
"""
from __future__ import annotations

from app.n8n_prompts.kw_seed_optimizer import (
    SEED_OPTIMIZER_SYSTEM_MESSAGE,
    SEED_OPTIMIZER_JSON_SCHEMA_EXAMPLE,
    build_seed_optimizer_user,
)
from app.n8n_prompts.kw_funnel_prospector import (
    FUNNEL_PROSPECTOR_SYSTEM_MESSAGE,
    build_funnel_prospector_user,
)
from app.n8n_prompts.funnel_builder import (
    FUNNEL_ARCHITECT_SYSTEM_MESSAGE,
    build_funnel_architect_user,
)

__all__ = [
    "SEED_OPTIMIZER_SYSTEM_MESSAGE",
    "SEED_OPTIMIZER_JSON_SCHEMA_EXAMPLE",
    "build_seed_optimizer_user",
    "FUNNEL_PROSPECTOR_SYSTEM_MESSAGE",
    "build_funnel_prospector_user",
    "FUNNEL_ARCHITECT_SYSTEM_MESSAGE",
    "build_funnel_architect_user",
]
