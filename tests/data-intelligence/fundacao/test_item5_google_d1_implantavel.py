"""Item 5 (17/10/2026): o JSON EXATO que vai para o Google D-1 (Code15 e nomes de nó do D-1), não o template.

Lê o workflow construído em experiments/.../artifacts/item5-20261017/novos/google_d1.json (fora do Git, 0600;
o teste é pulado quando o artefato não existe) e roda o Code node dele em Node com os nomes de nó do D-1.
Confere: zero medido × ausência de linha × moeda só da origem, GAQL com customer.currency_code nos dois nós de
consulta e corpo de ingestão sem moeda fixa, com metric_row_status e collector_version 2.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
COD = RAIZ / "docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/codigo"
NOVO = RAIZ / "experiments/data-intelligence-lab/artifacts/item5-20261017/novos/google_d1.json"
NODE = shutil.which("node")
pytestmark = [pytest.mark.skipif(NODE is None, reason="node ausente"),
              pytest.mark.skipif(not NOVO.exists(), reason="artefato do D-1 ausente (fora do Git)")]


def _wf():
    return {n["name"]: n for n in json.loads(NOVO.read_text())["nodes"]}


def _rodar(tmp_path, campanhas, metricas):
    n = _wf()
    c, f = tmp_path / "code.js", tmp_path / "fx.json"
    c.write_text(n["Code15"]["parameters"]["jsCode"])
    f.write_text(json.dumps({"nodes": {
        "Google Ads - Get Campaigns": [{"json": {"results": campanhas}}],
        "Google Ads - Get Conversion Goals1": [{"json": {"results": []}}],
        "Google Ads - Get Campaign Budget2": [{"json": {"results": []}}],
        "Google Ads - Get metrics": [{"json": {"results": metricas}}],
        "Split Out": [{"json": {"customerClient": {"id": "1111111111"}}}],
        "Edit Fields": [{"json": {"Start date": "2026-10-16"}}]}}))
    r = subprocess.run([NODE, str(COD / "executar_code_node.mjs"), str(c), str(f)], capture_output=True, text=True, check=True)
    return {d["campaign_id"]: d for d in json.loads(r.stdout)[0]["json"]["data"]}


def test_d1_zero_medido_ausencia_e_moeda(tmp_path):
    d = _rodar(tmp_path,
               [{"campaign": {"id": "101", "status": "ENABLED"}, "customer": {"currencyCode": "BRL"}},
                {"campaign": {"id": "102", "status": "ENABLED"}, "customer": {"currencyCode": "BRL"}},
                {"campaign": {"id": "103", "status": "PAUSED"}}],
               [{"campaign": {"id": "101"}, "metrics": {"costMicros": "1230000", "impressions": "10"}},
                {"campaign": {"id": "102"}, "metrics": {}}])
    assert d["101"]["metric_row_status"] == "present" and d["101"]["metrics"]["cost_micros"] == 1230000
    assert d["102"]["metric_row_status"] == "present" and d["102"]["metrics"]["cost_micros"] == 0
    assert d["103"]["metric_row_status"] == "metric_row_absent" and d["103"]["metrics"] == {}
    assert (d["101"]["currency_code"], d["101"]["currency_status"], d["101"]["currency_source"]) == ("BRL", "observed", "gaql:customer.currency_code")
    assert d["103"]["currency_code"] is None and d["103"]["currency_status"] == "unproven"


def test_d1_gaql_e_ingestao():
    n = _wf()
    for g in ("Google Ads - Get Campaigns", "Google Ads - Get metrics"):
        assert "customer.currency_code" in n[g]["parameters"]["bodyParameters"]["parameters"][0]["value"]
    ing = n["Supabase | Ingestão canônica shadow"]["parameters"]["jsonBody"]
    assert "currency_code: $json.currency_code," in ing and "'BRL'" not in ing
    assert "metric_row_status: $json.metric_row_status" in ing and "collector_version: 2," in ing
    assert "collector_version: 2," in n["Supabase | Finalizar run"]["parameters"]["jsonBody"]
