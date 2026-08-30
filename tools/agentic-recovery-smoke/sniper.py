#!/usr/bin/env python3
"""Prova real de microreparo DeepSeek com aplicação local fail-closed."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field


REPORT_ROOT = Path("/private/tmp/volc-autorepair-sniper")
MODEL = "deepseek-v4-flash"


class SniperPatch(BaseModel):
    scenario_id: str
    target_id: str
    observed_text: str
    replacement: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    external_writes: Literal[0]


@dataclass(frozen=True)
class Scenario:
    id: str
    target_id: str
    original: str
    target: str
    kind: Literal["copy", "python_identifier"]
    allowed_replacements: tuple[str, ...] = ()


SCENARIOS = {
    "copy-flag-sniper": Scenario(
        id="copy-flag-sniper",
        target_id="claim-001",
        original="Receba seu benefício garantido agora com segurança.",
        target="garantido",
        kind="copy",
    ),
    "python-variable-sniper": Scenario(
        id="python-variable-sniper",
        target_id="nameerror-001",
        original=(
            "def calcular_teto(orcamento_diario: float, dias: int) -> float:\n"
            "    return orcamento * dias\n"
        ),
        target="orcamento",
        kind="python_identifier",
        allowed_replacements=("orcamento_diario",),
    ),
}


def _system_prompt() -> str:
    return """Você é o VOLC Autorepair Sniper.
Sua única função é propor UMA substituição mínima para o span indicado.
Não reescreva o documento inteiro. Não use ferramentas. Não execute código.
Não altere prefixo nem sufixo. Responda somente um objeto JSON com:
scenario_id, target_id, observed_text, replacement, reason, confidence,
external_writes. external_writes deve ser 0."""


def _user_prompt(scenario: Scenario) -> str:
    extra = ""
    if scenario.kind == "copy":
        extra = (
            "A flag é promessa absoluta/não comprovada. Substitua somente o span "
            "por uma formulação curta, natural e não absoluta."
        )
    else:
        extra = (
            "O erro é NameError. Escolha exatamente uma destas substituições "
            f"permitidas: {list(scenario.allowed_replacements)}."
        )
    return f"""CENÁRIO: {scenario.id}
TARGET_ID: {scenario.target_id}
TIPO: {scenario.kind}
TEXTO ORIGINAL:
{scenario.original}
SPAN EXATO A SUBSTITUIR: {scenario.target!r}
REGRA: {extra}
"""


def _call(scenario: Scenario) -> tuple[SniperPatch, dict]:
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    started = time.monotonic()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(scenario)},
        ],
        stream=False,
        max_tokens=4096,
        reasoning_effort="low",
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "enabled"}},
    )
    message = response.choices[0].message
    if not message.content:
        raise RuntimeError("DeepSeek devolveu reasoning, mas não final_response")
    patch = SniperPatch.model_validate_json(message.content)
    meta = {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "finish_reason": response.choices[0].finish_reason,
        "thinking_used": bool(getattr(message, "reasoning_content", None)),
        "thinking_logged": False,
    }
    return patch, meta


def _apply_guarded(scenario: Scenario, patch: SniperPatch) -> tuple[str, list[str]]:
    errors: list[str] = []
    if patch.scenario_id != scenario.id:
        errors.append("scenario_id divergente")
    if patch.target_id != scenario.target_id:
        errors.append("target_id divergente")
    if patch.observed_text != scenario.target:
        errors.append("observed_text não coincide com o span")
    if patch.external_writes != 0:
        errors.append("external_writes diferente de zero")
    pattern = re.compile(rf"\b{re.escape(scenario.target)}\b")
    matches = list(pattern.finditer(scenario.original))
    if len(matches) != 1:
        errors.append("span não é único")
    if "\n" in patch.replacement:
        errors.append("replacement contém nova linha")
    if scenario.kind == "copy":
        forbidden = {"garantido", "garantia", "100%", "sem risco"}
        if any(term in patch.replacement.casefold() for term in forbidden):
            errors.append("replacement mantém promessa absoluta")
    if scenario.kind == "python_identifier":
        if patch.replacement not in scenario.allowed_replacements:
            errors.append("identifier fora da allowlist")
        if not patch.replacement.isidentifier():
            errors.append("replacement não é identifier")
    if errors:
        return scenario.original, errors

    match = matches[0]
    before = scenario.original[: match.start()]
    after = scenario.original[match.end() :]
    repaired = before + patch.replacement + after
    if not repaired.startswith(before) or not repaired.endswith(after):
        return scenario.original, ["prefixo ou sufixo mudou"]
    if scenario.kind == "python_identifier":
        try:
            tree = ast.parse(repaired)
            compile(tree, "<sniper-sandbox>", "exec")
            namespace: dict = {}
            exec(compile(tree, "<sniper-sandbox>", "exec"), {"__builtins__": {}}, namespace)
            if namespace["calcular_teto"](10.0, 3) != 30.0:
                return scenario.original, ["prova funcional não produziu 30.0"]
        except Exception as exc:
            return scenario.original, [f"prova AST/funcional falhou: {type(exc).__name__}"]
    return repaired, []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="all")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        parser.error("DEEPSEEK_API_KEY ausente")
    if not 1 <= args.repeat <= 10:
        parser.error("--repeat precisa estar entre 1 e 10")

    selected = list(SCENARIOS.values()) if args.scenario == "all" else [SCENARIOS[args.scenario]]
    results = []
    for scenario in selected:
        for attempt in range(1, args.repeat + 1):
            print(f"[{scenario.id} {attempt}/{args.repeat}] DeepSeek...", flush=True)
            try:
                patch, meta = _call(scenario)
                repaired, errors = _apply_guarded(scenario, patch)
                results.append({
                    "scenario": scenario.id,
                    "attempt": attempt,
                    "accepted": not errors,
                    "patch": patch.model_dump(mode="json"),
                    "repaired": repaired if not errors else None,
                    "guard_errors": errors,
                    **meta,
                })
            except Exception as exc:
                results.append({
                    "scenario": scenario.id,
                    "attempt": attempt,
                    "accepted": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })

    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "reasoning_effort": "low",
        "thinking_logged": False,
        "external_product_writes": 0,
        "accepted": sum(item["accepted"] for item in results),
        "total": len(results),
        "results": results,
    }
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    path = REPORT_ROOT / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("model", "accepted", "total", "external_product_writes")}, ensure_ascii=False, indent=2))
    print(f"relatório: {path}")
    return 0 if report["accepted"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
