#!/usr/bin/env python3
"""Bounded proof: one operation JSONB roundtrip, then archive that exact row.

Dry-run by default. Does not create a run, approval, image, campaign or paid call.
Use the same backend venv and --source-project of the operator's existing work.
Credentials stay in backend settings; neither keys nor owner IDs are printed.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def prove(args: argparse.Namespace) -> dict:
    from app.config import Settings
    from app.criativo.agente.contrato import EntradaNovaOperacao
    from app.criativo.agente.persistencia import NaoEncontrado, RepositorioAgenteCriativo
    from app.criativo.contexto_pagina import analisar_pagina
    from app.services.supabase_service import SupabaseService

    settings = Settings(_env_file=(ROOT / ".env.server", ROOT / "backend/.env", ROOT / "backend/.env.local"))
    if (settings.supabase_url or "").rstrip("/") != "https://database.agenciavolc.com.br":
        raise RuntimeError("O destino não é o Supabase operacional autorizado.")
    db = SupabaseService(settings)
    repo = RepositorioAgenteCriativo(db)
    source = await db.select("criativo_agente_operacao", {
        "project_ref": f"eq.{args.source_project}", "select": "project_ref,owner_id", "limit": 1,
    })
    if len(source) != 1 or not source[0].get("owner_id"):
        raise RuntimeError("A operação de origem não existe; nenhuma identidade foi inferida.")
    snapshot = await analisar_pagina(args.url, modelo=None)
    entrada = EntradaNovaOperacao(
        nome_da_operacao="QA técnico · persistência contexto LP · sem geração",
        url_destino=snapshot.url_solicitada, contexto_da_pagina=snapshot,
        contexto_do_publico="Teste técnico de retomada, sem aprovação de campanha ou estratégia.",
        fatos_da_oferta=[{
            "ref": "fact_qa_context_roundtrip",
            "declaracao": "Teste técnico de persistência; nenhuma peça será criada.",
            "origem": "OPERADOR",
        }], quantidade_de_pecas=1, formatos_permitidos=["4x5"],
    ).model_dump(mode="json")
    result = {"executed": False, "target": "database.agenciavolc.com.br",
              "snapshot_version": snapshot.schema_version, "excerpts": len(snapshot.fatos),
              "input_sha256": hashlib.sha256(json.dumps(entrada, sort_keys=True).encode()).hexdigest(),
              "paid_calls": 0, "runs_created": 0, "approvals_created": 0}
    if not args.execute:
        result["next"] = "Repita com --execute para criar e arquivar uma única operação QA."
        return result
    owner = source[0]["owner_id"]
    project = "crproj_" + secrets.token_hex(12)
    print(json.dumps({"phase": "write_intent", "project_ref": project, "cleanup": "archive_only"}), flush=True)
    try:
        await repo.criar_operacao({"project_ref": project, "owner_id": owner, "status": "RUNNING", "input": entrada})
        readback = await repo.obter_operacao(project, owner)
        if readback["input"] != entrada:
            raise RuntimeError("O input JSONB não voltou literalmente igual.")
        try:
            await repo.obter_operacao(project, str(uuid4()))
        except NaoEncontrado:
            result["owner_filter_verified"] = True
        else:
            raise RuntimeError("A consulta por outro owner devolveu a operação.")
        result.update({"executed": True, "roundtrip_equal": True, "project_ref": project})
    finally:
        archived = await db.patch("criativo_agente_operacao", {
            "project_ref": f"eq.{project}", "owner_id": f"eq.{owner}", "status": "eq.RUNNING",
        }, {"status": "ARCHIVED"})
        if archived:
            final = await repo.obter_operacao(project, owner)
            if final["status"] != "ARCHIVED":
                raise RuntimeError(f"Conferir arquivamento manual da operação QA {project}.")
            result["archived"] = True
        else:
            # Also catches ambiguous writes instead of claiming cleanup.
            try:
                final = await repo.obter_operacao(project, owner)
            except NaoEncontrado:
                result["archived"] = False
            else:
                if final["status"] != "ARCHIVED":
                    raise RuntimeError(f"Não foi possível arquivar a operação QA {project}.")
                result["archived"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-project", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"crproj_[a-f0-9]{24}", args.source_project):
        parser.error("--source-project deve ser uma referência de operação existente.")
    check = subprocess.run([sys.executable, str(ROOT / "scripts/verificar_autoridade_supabase.py")], cwd=ROOT,
                           capture_output=True, text=True)
    if check.returncode:
        print(json.dumps({"ok": False, "error": "Verificador da autoridade Supabase recusou o ambiente."}))
        return 1
    try:
        result = asyncio.run(prove(args))
    except Exception as exc:
        # httpx exceptions may carry URLs/query params; no raw exception output.
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "message": "Prova interrompida; confira os logs seguros do backend."}))
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
