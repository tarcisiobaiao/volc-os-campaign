#!/usr/bin/env python3
"""Smoke isolado do runtime agêntico; nunca executa ação externa de produto."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    ROOT / "docs/architecture/contracts/agentic-recovery-smoke-v1.json"
)
REPORT_ROOT = Path("/private/tmp/volc-agentic-recovery-smoke")
COMPROMISED_LITELLM = {"1.82.7", "1.82.8"}


class RecoveryResult(BaseModel):
    verdict: Literal["repaired", "recommendation", "needs_human", "blocked"]
    summary: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str]
    missing_information: list[str]
    proposed_recipe: str | None
    external_writes: int = Field(ge=0, le=0)
    confidence: float = Field(ge=0, le=1)


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def preflight() -> dict:
    contract = _load_contract()
    adk = _version("google-adk")
    litellm = _version("litellm")
    allowed = set(contract["allowed_tools"])
    forbidden = set(contract["forbidden_tools"])
    errors: list[str] = []

    if adk != "2.8.0":
        errors.append(f"google-adk esperado 2.8.0; observado {adk or 'ausente'}")
    if litellm is None:
        errors.append("litellm ausente; instalar versão >=1.84")
    elif litellm in COMPROMISED_LITELLM:
        errors.append(f"litellm {litellm} é versão proibida pelo advisory")
    else:
        major_minor = tuple(int(part) for part in litellm.split(".")[:2])
        if major_minor < (1, 84):
            errors.append(f"litellm {litellm} abaixo do mínimo 1.84")
    overlap = sorted(allowed & forbidden)
    if overlap:
        errors.append(f"ferramentas simultaneamente permitidas/proibidas: {overlap}")
    if contract["limits"]["external_writes"] != 0:
        errors.append("smoke precisa declarar external_writes=0")

    return {
        "ok": not errors,
        "google_adk": adk,
        "litellm": litellm,
        "contract": str(CONTRACT_PATH.relative_to(ROOT)),
        "deepseek_key_present": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "errors": errors,
    }


def _scenario(contract: dict, scenario_id: str) -> dict:
    for item in contract["scenarios"]:
        if item["id"] == scenario_id:
            return item
    ids = ", ".join(item["id"] for item in contract["scenarios"])
    raise ValueError(f"cenário desconhecido {scenario_id!r}; use: {ids}")


def _prompt(contract: dict, scenario: dict) -> str:
    return f"""Você é um microagente de diagnóstico do VOLC O.S.

Analise SOMENTE o cenário sanitizado abaixo. Não use rede, não peça segredos,
não invente fatos e não execute ferramenta ou ação externa. Diferencie fato,
hipótese e informação ausente. Respeite os limites e devolva exatamente o
contrato estruturado solicitado pelo runtime.

LIMITES
{json.dumps(contract['limits'], ensure_ascii=False, indent=2)}

FERRAMENTAS PROIBIDAS
{json.dumps(contract['forbidden_tools'], ensure_ascii=False, indent=2)}

CENÁRIO
{json.dumps(scenario, ensure_ascii=False, indent=2)}

Regras finais:
- external_writes deve ser 0;
- evidence_ids deve citar somente IDs presentes no cenário;
- se os dados não fecharem a causa, use needs_human ou recommendation;
- nunca transforme a hipótese de CPC baixo numa causa comprovada;
- proposed_recipe é uma proposta local, não uma autorização.
"""


def _final_text(events: list) -> str:
    for event in reversed(events):
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            continue
        texts = [
            getattr(part, "text", None)
            for part in parts
            if not getattr(part, "thought", False)
        ]
        joined = "".join(text for text in texts if text)
        if joined.strip():
            return joined.strip()
    raise RuntimeError("ADK terminou sem resposta final; havia somente raciocínio")


def _structured_result(raw: str) -> RecoveryResult:
    """Aceita JSON puro ou um único objeto JSON cercado por explicação/fence.

    Alguns modelos entregam raciocínio textual antes do objeto mesmo quando o
    ADK declara ``output_schema``. A fronteira local continua estrita: somente
    o objeto é aceito e ele ainda precisa validar integralmente em Pydantic.
    """

    candidates = [raw.strip()]
    candidates.extend(
        match.strip()
        for match in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    )
    first = raw.find("{")
    last = raw.rfind("}")
    if first >= 0 and last > first:
        candidates.append(raw[first : last + 1])

    errors: list[str] = []
    for candidate in dict.fromkeys(candidates):
        try:
            return RecoveryResult.model_validate_json(candidate)
        except ValidationError as exc:
            errors.append(str(exc))
    raise RuntimeError(
        "saída não continha objeto compatível com RecoveryResult: "
        + (errors[-1] if errors else "nenhum JSON encontrado")
    )


async def _one_live(contract: dict, scenario: dict, index: int) -> dict:
    from google.adk.agents import LlmAgent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = LlmAgent(
        name="volc_agentic_recovery_smoke",
        description="Microagente sem ferramentas e sem escrita externa.",
        model=LiteLlm(model="deepseek/deepseek-v4-flash"),
        instruction=_prompt(contract, scenario),
        output_schema=RecoveryResult,
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=8192,
            temperature=0,
        ),
        mode="task",
    )
    runner = InMemoryRunner(agent=agent, app_name="volc_agentic_recovery_smoke")
    started = time.monotonic()
    events = await asyncio.wait_for(
        runner.run_debug(
            "Produza o veredito estruturado para este cenário.",
            user_id=f"smoke_user_{index}",
            session_id=f"{scenario['id']}_{index}",
            quiet=True,
        ),
        timeout=contract["limits"]["timeout_seconds"],
    )
    raw = _final_text(events)
    result = _structured_result(raw)
    return {
        "index": index,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "result": result.model_dump(mode="json"),
    }


async def _run_live(scenario_id: str, repeat: int) -> dict:
    contract = _load_contract()
    scenario = _scenario(contract, scenario_id)
    results = []
    failures = []
    for index in range(1, repeat + 1):
        print(f"[{index}/{repeat}] executando {scenario_id}...", flush=True)
        try:
            results.append(await _one_live(contract, scenario, index))
        except Exception as exc:  # relatório da prova, sem mascarar falha
            failures.append({"index": index, "error": f"{type(exc).__name__}: {exc}"})
    verdicts = [item["result"]["verdict"] for item in results]
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario_id,
        "model": "deepseek/deepseek-v4-flash",
        "repeat": repeat,
        "succeeded": len(results),
        "failed": len(failures),
        "all_external_writes_zero": all(
            item["result"]["external_writes"] == 0 for item in results
        ),
        "verdicts": verdicts,
        "results": results,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--scenario", default="redator-invalid-json-loop")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    status = preflight()
    if args.preflight:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["ok"] else 1

    if not status["ok"]:
        print(json.dumps(status, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    if not status["deepseek_key_present"]:
        print(
            "DEEPSEEK_API_KEY ausente. Injete-a somente na sessão/1Password; "
            "nenhuma chamada foi feita.",
            file=sys.stderr,
        )
        return 2
    if not 1 <= args.repeat <= 10:
        parser.error("--repeat precisa estar entre 1 e 10")

    report = asyncio.run(_run_live(args.scenario, args.repeat))
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = REPORT_ROOT / f"{stamp}-{args.scenario}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in (
        "scenario", "repeat", "succeeded", "failed", "verdicts"
    )}, ensure_ascii=False, indent=2))
    print(f"relatório: {report_path}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
