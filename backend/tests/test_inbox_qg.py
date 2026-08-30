from __future__ import annotations

import json
import hashlib
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import work_road
from app.seguranca.identidade import exigir_admin, exigir_usuario
from app.work_road import export_doc, inbox_store


class _Admin:
    email = "admin@volc.test"
    sub = "admin-1"
    e_admin = True


def test_captura_nao_entra_no_percentual_do_roadmap(tmp_path):
    snapshot = tmp_path / "INBOX-ROADMAP.json"
    recibos = tmp_path / "INBOX-ROADMAP.receipts.jsonl"
    resultado = inbox_store.capturar(
        snapshot,
        recibos,
        titulo="Ideia nova",
        original="Nasceu no QG, ainda não é tarefa.",
        actor="operador",
    )
    assert resultado["receipt"]["triage"] == "capturada"
    assert "adicionada ao roadmap" not in json.dumps(resultado).lower()
    assert recibos.read_text(encoding="utf-8").count("\n") == 1

    caminho = tmp_path / "ROADMAP-VIVO.json"
    caminho.write_text(json.dumps({
        "schema_version": 1,
        "updated_at": "2026-08-28",
        "purpose": "teste",
        "status_weights": {"done": 1.0, "partial": 0.5, "risk": 0.25, "todo": 0.0, "reserved": None},
        "status_labels": {},
        "initiatives": [{
            "id": "P01",
            "rank": 1,
            "title": "Ini",
            "wave": "A",
            "why": "why",
            "done_when": "done",
            "graph_nodes": [],
            "tasks": [
                {"id": "T1", "title": "Feita", "status": "done", "proof": "ok"},
                {"id": "T2", "title": "Futura", "status": "todo", "proof": "ainda"},
            ],
        }],
    }), encoding="utf-8")
    documento, _ = work_road.ler_roadmap(caminho)
    assert documento["summary"]["progress_percent"] == 50.0
    assert documento["summary"]["tasks"] == 2


def test_promocao_vincula_entrada_a_tarefa_existente(tmp_path):
    snapshot = tmp_path / "INBOX-ROADMAP.json"
    recibos = tmp_path / "INBOX-ROADMAP.receipts.jsonl"
    capturada = inbox_store.capturar(
        snapshot, recibos, titulo="Promover", original="texto", actor="op",
    )
    entrada_id = capturada["entry"]["id"]
    resultado = inbox_store.triar(
        snapshot,
        recibos,
        entry_id=entrada_id,
        actor="admin",
        triage="promovida",
        promoted_task_id="P01-T07",
        task_ids={"P01-T07"},
    )
    assert resultado["entry"]["triage"] == "promovida"
    assert resultado["entry"]["promoted_task_id"] == "P01-T07"


def test_promocao_recusa_tarefa_inexistente(tmp_path):
    snapshot = tmp_path / "INBOX-ROADMAP.json"
    recibos = tmp_path / "INBOX-ROADMAP.receipts.jsonl"
    capturada = inbox_store.capturar(
        snapshot, recibos, titulo="Promover", original="texto", actor="op",
    )
    try:
        inbox_store.triar(
            snapshot,
            recibos,
            entry_id=capturada["entry"]["id"],
            actor="admin",
            triage="promovida",
            promoted_task_id="T-FALSA",
            task_ids={"P01-T07"},
        )
    except ValueError as exc:
        assert "não existe" in str(exc)
    else:
        raise AssertionError("promoção para tarefa inexistente deveria falhar")


def test_capturas_concorrentes_nao_perdem_entrada_nem_repetem_id(tmp_path):
    snapshot = tmp_path / "INBOX-ROADMAP.json"
    recibos = tmp_path / "INBOX-ROADMAP.receipts.jsonl"

    def capturar(indice: int):
        return inbox_store.capturar(
            snapshot,
            recibos,
            titulo=f"Ideia {indice}",
            original=f"Descrição {indice}",
            actor="agente",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(capturar, range(24)))

    ids = [resultado["entry"]["id"] for resultado in resultados]
    documento, _ = inbox_store.ler_ou_criar(snapshot)
    assert len(ids) == len(set(ids)) == 24
    assert len(documento["entries"]) == 24
    assert recibos.read_text(encoding="utf-8").count("\n") == 24


def test_nova_triagem_limpa_campos_da_decisao_anterior(tmp_path):
    snapshot = tmp_path / "INBOX-ROADMAP.json"
    recibos = tmp_path / "INBOX-ROADMAP.receipts.jsonl"
    entrada_id = inbox_store.capturar(
        snapshot, recibos, titulo="Reavaliar", original="texto", actor="op",
    )["entry"]["id"]
    inbox_store.triar(
        snapshot,
        recibos,
        entry_id=entrada_id,
        actor="admin",
        triage="promovida",
        promoted_task_id="P01-T07",
        task_ids={"P01-T07"},
    )
    resultado = inbox_store.triar(
        snapshot,
        recibos,
        entry_id=entrada_id,
        actor="admin",
        triage="em_triagem",
    )
    assert resultado["entry"]["promoted_task_id"] is None
    assert resultado["entry"]["possible_duplicate_of"] is None
    assert resultado["entry"]["justification"] is None


def test_inbox_endpoint_autenticado(tmp_path, monkeypatch):
    monkeypatch.setattr(work_road, "_INBOX", tmp_path / "INBOX-ROADMAP.json")
    monkeypatch.setattr(work_road, "_INBOX_RECIBOS", tmp_path / "INBOX-ROADMAP.receipts.jsonl")
    monkeypatch.setattr(work_road, "_COBERTURA", tmp_path / "INBOX-COVERAGE.json")
    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: _Admin()
    cliente = TestClient(app)
    criada = cliente.post("/api/work-road/inbox", json={"title": "Capturar", "original": "ideia crua"})
    assert criada.status_code == 201
    assert criada.json()["receipt"]["triage"] == "capturada"
    lida = cliente.get("/api/work-road/inbox")
    assert lida.status_code == 200
    assert lida.json()["summary"]["capturadas"] >= 1
    assert "não vira tarefa sozinha" in lida.json()["disclaimer"].lower()


def test_tarefa_inexistente_404(tmp_path, monkeypatch):
    caminho = tmp_path / "ROADMAP-VIVO.json"
    caminho.write_text(json.dumps({
        "schema_version": 1,
        "updated_at": "2026-08-28",
        "purpose": "teste",
        "status_weights": {"done": 1.0, "partial": 0.5, "risk": 0.25, "todo": 0.0, "reserved": None},
        "status_labels": {},
        "initiatives": [{
            "id": "P01", "rank": 1, "title": "Ini", "wave": "A", "why": "w", "done_when": "d",
            "graph_nodes": [],
            "tasks": [{"id": "T1", "title": "Uma", "status": "todo", "proof": "p"}],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(work_road, "_ROADMAP", caminho)
    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: _Admin()
    cliente = TestClient(app)
    assert cliente.get("/api/work-road/tasks/T1").status_code == 200
    assert cliente.get("/api/work-road/tasks/T-FALSA").status_code == 404


def test_reordenacao_admin_permuta_e_gera_recibo(tmp_path, monkeypatch):
    caminho = tmp_path / "ROADMAP-VIVO.json"
    caminho.write_text(json.dumps({
        "schema_version": 1,
        "updated_at": "2026-08-28",
        "purpose": "teste",
        "status_weights": {"done": 1.0, "partial": 0.5, "risk": 0.25, "todo": 0.0, "reserved": None},
        "status_labels": {},
        "initiatives": [{
            "id": "P01", "rank": 1, "title": "Ini", "wave": "A", "why": "w", "done_when": "d",
            "graph_nodes": [],
            "tasks": [
                {"id": "T1", "title": "Uma", "status": "todo", "proof": "p"},
                {"id": "T2", "title": "Duas", "status": "todo", "proof": "p"},
            ],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(work_road, "_ROADMAP", caminho)
    monkeypatch.setattr(work_road, "_INBOX_RECIBOS", tmp_path / "recibos.jsonl")
    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: _Admin()
    app.dependency_overrides[exigir_admin] = lambda: _Admin()
    cliente = TestClient(app)
    esperado = hashlib.sha256(caminho.read_bytes()).hexdigest()
    resposta = cliente.post("/api/work-road/reorder", json={
        "initiative_id": "P01",
        "task_ids": ["T2", "T1"],
        "expected_sha256": esperado,
    })
    assert resposta.status_code == 200
    ids = [tarefa["id"] for tarefa in resposta.json()["roadmap"]["initiatives"][0]["tasks"]]
    assert ids == ["T2", "T1"]
    assert resposta.json()["receipt"]["before"] == ["T1", "T2"]
    assert resposta.json()["receipt"]["after"] == ["T2", "T1"]
    relido = json.loads(caminho.read_text(encoding="utf-8"))
    assert [tarefa["id"] for tarefa in relido["initiatives"][0]["tasks"]] == ["T2", "T1"]


def test_reordenacao_recusa_fonte_que_mudou(tmp_path, monkeypatch):
    caminho = tmp_path / "ROADMAP-VIVO.json"
    caminho.write_text(json.dumps({
        "schema_version": 1,
        "updated_at": "2026-08-28",
        "purpose": "teste",
        "status_weights": {"done": 1.0, "partial": 0.5, "risk": 0.25, "todo": 0.0, "reserved": None},
        "status_labels": {},
        "initiatives": [{
            "id": "P01", "rank": 1, "title": "Ini", "wave": "A", "why": "w", "done_when": "d",
            "graph_nodes": [],
            "tasks": [
                {"id": "T1", "title": "Uma", "status": "todo", "proof": "p"},
                {"id": "T2", "title": "Duas", "status": "todo", "proof": "p"},
            ],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(work_road, "_ROADMAP", caminho)
    monkeypatch.setattr(work_road, "_INBOX_RECIBOS", tmp_path / "recibos.jsonl")
    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: _Admin()
    app.dependency_overrides[exigir_admin] = lambda: _Admin()
    cliente = TestClient(app)
    resposta = cliente.post("/api/work-road/reorder", json={
        "initiative_id": "P01",
        "task_ids": ["T2", "T1"],
        "expected_sha256": "0" * 64,
    })
    assert resposta.status_code == 409
    assert "mudou" in resposta.json()["detail"]


def test_exportacao_pdf_e_arquivo_real():
    documento = {
        "updated_at": "2026-08-28",
        "source": {"path": "volc-os-workbook/ROADMAP-VIVO.json", "sha256": "abc"},
        "initiatives": [{
            "id": "P01", "title": "Ini", "wave": "A", "why": "porque",
            "tasks": [{"id": "T1", "title": "Uma", "status": "todo", "proof": "p"}],
        }],
    }
    texto = export_doc.texto(documento, gerado_em="2026-08-28T12:00:00+00:00")
    pdf = export_doc.pdf_bytes(texto)
    assert pdf.startswith(b"%PDF-1.4")
    assert b"Workbook" in pdf or b"VOLC" in pdf
    assert b"pagina 1" in pdf
    html = export_doc.html_documento(documento, gerado_em="2026-08-28T12:00:00+00:00")
    assert "T1" in html and "A4" in html


def test_reordenacao_nao_admin_403(tmp_path, monkeypatch):
    class _User:
        email = "op@volc.test"
        sub = "user-1"
        e_admin = False

    caminho = tmp_path / "ROADMAP-VIVO.json"
    caminho.write_text(json.dumps({
        "schema_version": 1,
        "updated_at": "2026-08-28",
        "purpose": "teste",
        "status_weights": {"done": 1.0, "partial": 0.5, "risk": 0.25, "todo": 0.0, "reserved": None},
        "status_labels": {},
        "initiatives": [{
            "id": "P01", "rank": 1, "title": "Ini", "wave": "A", "why": "w", "done_when": "d",
            "graph_nodes": [],
            "tasks": [
                {"id": "T1", "title": "Uma", "status": "todo", "proof": "p"},
                {"id": "T2", "title": "Duas", "status": "todo", "proof": "p"},
            ],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(work_road, "_ROADMAP", caminho)
    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: _User()
    cliente = TestClient(app)
    resposta = cliente.post("/api/work-road/reorder", json={"initiative_id": "P01", "task_ids": ["T2", "T1"]})
    assert resposta.status_code == 403


def test_graph_status_stale_sem_update_status(tmp_path, monkeypatch):
    monkeypatch.setattr(work_road, "_GRAFO_STATUS", tmp_path / "UPDATE_STATUS.json")
    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: _Admin()
    cliente = TestClient(app)
    resposta = cliente.get("/api/work-road/graph-status")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["stale"] is True
    assert corpo["available"] is False
    assert "curadoria-operacional.json" in corpo["authority"]


def test_graph_status_le_built_at_commit(tmp_path, monkeypatch):
    status = tmp_path / "UPDATE_STATUS.json"
    status.write_text(json.dumps({
        "built_at_commit": "commit-de-geracao",
        "generated_at": "2026-08-29T10:00:00Z",
    }), encoding="utf-8")
    monkeypatch.setattr(work_road, "_GRAFO_STATUS", status)
    monkeypatch.setattr(work_road, "_git", lambda args, cwd=work_road._RAIZ: "head-atual\n" if args[-1] == "HEAD" else "head-at\n")
    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: _Admin()
    corpo = TestClient(app).get("/api/work-road/graph-status").json()
    assert corpo["graph_commit"] == "commit-de-geracao"
    assert corpo["stale"] is True
    assert "outro commit" in corpo["reason"]


def test_export_docx_ausente_e_honesto(tmp_path, monkeypatch):
    caminho = tmp_path / "ROADMAP-VIVO.json"
    caminho.write_text(json.dumps({
        "schema_version": 1,
        "updated_at": "2026-08-28",
        "purpose": "teste",
        "status_weights": {"done": 1.0, "partial": 0.5, "risk": 0.25, "todo": 0.0, "reserved": None},
        "status_labels": {},
        "initiatives": [{
            "id": "P01", "rank": 1, "title": "Ini", "wave": "A", "why": "w", "done_when": "d",
            "graph_nodes": [],
            "tasks": [{"id": "T1", "title": "Uma", "status": "todo", "proof": "p"}],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(work_road, "_ROADMAP", caminho)
    monkeypatch.setattr(work_road, "_RAIZ", tmp_path)
    app = FastAPI()
    app.include_router(work_road.router)
    app.dependency_overrides[exigir_usuario] = lambda: _Admin()
    cliente = TestClient(app)
    resposta = cliente.get("/api/work-road/export?format=docx&scope=full")
    assert resposta.status_code == 404
