from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import work_road
from app.seguranca.identidade import exigir_usuario


def _documento() -> dict:
    return {
        "schema_version": 1,
        "updated_at": "2026-08-26",
        "purpose": "teste",
        "status_weights": {
            "done": 1.0,
            "partial": 0.5,
            "risk": 0.25,
            "todo": 0.0,
            "reserved": None,
        },
        "status_labels": {},
        "initiatives": [
            {
                "id": "P01",
                "rank": 1,
                "title": "Fonte viva",
                "wave": "A",
                "why": "uma verdade",
                "done_when": "prova",
                "graph_nodes": ["cap_work_road"],
                "tasks": [
                    {"id": "T1", "title": "Feita", "status": "done", "proof": "teste"},
                    {"id": "T2", "title": "Parcial", "status": "partial", "proof": "teste"},
                    {"id": "T3", "title": "Futura", "status": "reserved", "proof": "reserva"},
                ],
            }
        ],
    }


def test_leitura_calcula_resumo_sem_contar_reservadas(tmp_path):
    caminho = tmp_path / "ROADMAP-VIVO.json"
    caminho.write_text(json.dumps(_documento()), encoding="utf-8")

    documento, etag = work_road.ler_roadmap(caminho)

    assert len(etag) == 64
    assert documento["summary"] == {
        "initiatives": 1,
        "tasks": 3,
        "accepted_tasks": 2,
        "progress_percent": 75.0,
        "counts": {"done": 1, "partial": 1, "reserved": 1, "risk": 0, "todo": 0},
    }
    assert documento["source"]["path"] == "volc-os-workbook/ROADMAP-VIVO.json"


def test_leitura_falha_fechado_para_estado_desconhecido(tmp_path):
    documento = _documento()
    documento["initiatives"][0]["tasks"][0]["status"] = "quase"
    caminho = tmp_path / "ROADMAP-VIVO.json"
    caminho.write_text(json.dumps(documento), encoding="utf-8")

    try:
        work_road.ler_roadmap(caminho)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        assert "estado desconhecido" in getattr(exc, "detail", "")
    else:
        raise AssertionError("a fonte inválida deveria falhar fechada")


def test_endpoint_e_autenticado_e_nao_faz_cache(tmp_path, monkeypatch):
    caminho = tmp_path / "ROADMAP-VIVO.json"
    caminho.write_text(json.dumps(_documento()), encoding="utf-8")
    monkeypatch.setattr(work_road, "_ROADMAP", caminho)

    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: object()
    resposta = TestClient(app).get("/api/work-road")

    assert resposta.status_code == 200
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.headers["etag"].startswith('"')
    assert resposta.json()["summary"]["progress_percent"] == 75.0


def test_parser_de_worktrees_preserva_trava_e_separa_blocos():
    bruto = """worktree /repo
HEAD abc123
branch refs/heads/main

worktree /repo/.claude/worktrees/p04
HEAD def456
branch refs/heads/worktree-p04
locked claude session p04 (pid 123 start hoje)

"""

    blocos = work_road._parse_worktrees(bruto)

    assert blocos == [
        {"worktree": "/repo", "HEAD": "abc123", "branch": "refs/heads/main"},
        {
            "worktree": "/repo/.claude/worktrees/p04",
            "HEAD": "def456",
            "branch": "refs/heads/worktree-p04",
            "locked": "claude session p04 (pid 123 start hoje)",
        },
    ]


def test_endpoint_de_execucoes_e_somente_leitura_e_sem_cache(monkeypatch):
    fotografia = {
        "schema_version": 1,
        "available": True,
        "read_at": "2026-08-27T12:00:00Z",
        "main_head": "ca96353",
        "executions": [],
        "reason": None,
    }
    monkeypatch.setattr(work_road, "ler_execucoes", lambda: fotografia)

    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: object()
    resposta = TestClient(app).get("/api/work-road/executions")

    assert resposta.status_code == 200
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.json() == fotografia
