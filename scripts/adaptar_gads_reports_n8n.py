#!/usr/bin/env python3
"""Adapta os coletores D0/D-1 do Google Ads para o contrato VOLC atual.

O script trabalha sobre exports JSON do n8n e produz payloads aceitos pelo
endpoint PUT /api/v1/workflows/{id}. Ele não chama a rede, não ativa e não
executa workflows.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any


API_VERSION = "25"
MERGE_NAME = "Merge - Aguardar duas gravações"
PUBLIC_SETTINGS = {
    "callerPolicy",
    "errorWorkflow",
    "executionOrder",
    "executionTimeout",
    "saveDataErrorExecution",
    "saveDataSuccessExecution",
    "saveExecutionProgress",
    "saveManualExecutions",
    "timezone",
}


def _node(workflow: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [node for node in workflow["nodes"] if node.get("name") == name]
    if len(matches) != 1:
        raise ValueError(f"esperava exatamente um nó {name!r}; encontrei {len(matches)}")
    return matches[0]


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: esperava 1 ocorrência, encontrei {count}")
    return text.replace(old, new, 1)


def _set_api_version(workflow: dict[str, Any]) -> None:
    found = 0
    for node in workflow["nodes"]:
        assignments = (
            node.get("parameters", {})
            .get("assignments", {})
            .get("assignments", [])
        )
        for assignment in assignments:
            if assignment.get("name") == "GOOGLEADS_API_VERSION":
                assignment["value"] = API_VERSION
                found += 1
    if not found:
        raise ValueError("nenhuma configuração GOOGLEADS_API_VERSION encontrada")


def _patch_metrics_query(workflow: dict[str, Any], metrics_node: str) -> None:
    node = _node(workflow, metrics_node)
    parameters = node["parameters"]["bodyParameters"]["parameters"]
    query_item = next((item for item in parameters if item.get("name") == "query"), None)
    if query_item is None:
        raise ValueError(f"{metrics_node}: parâmetro GAQL query ausente")
    query = query_item["value"]
    if "metrics.conversions_value" not in query:
        query = _replace_once(
            query,
            "  metrics.conversions, \n",
            "  metrics.conversions, \n  metrics.conversions_value, \n",
            label=f"{metrics_node}/conversions_value",
        )
    query_item["value"] = query


def _patch_code(workflow: dict[str, Any], code_node: str) -> None:
    node = _node(workflow, code_node)
    code = node["parameters"]["jsCode"]

    if "cost_per_conversion: item.metrics?.costPerConversion" not in code:
        code = _replace_once(
            code,
            "      conversions_value: parseFloat(item.metrics?.conversionsValue || 0),  \n",
            "      conversions_value: parseFloat(item.metrics?.conversionsValue || 0),  \n"
            "      cost_per_conversion: item.metrics?.costPerConversion  \n"
            "        ? Number(item.metrics.costPerConversion) / 1_000_000  \n"
            "        : 0,  \n",
            label=f"{code_node}/cost_per_conversion-map",
        )

    if "      cost_per_conversion: 0,  \n" not in code:
        code = _replace_once(
            code,
            "      conversions_value: 0,  \n",
            "      conversions_value: 0,  \n      cost_per_conversion: 0,  \n",
            label=f"{code_node}/cost_per_conversion-fallback",
        )

    if "    cost_per_conversion: metric.cost_per_conversion,  \n" not in code:
        code = _replace_once(
            code,
            "    conversions_value: metric.conversions_value,  \n",
            "    conversions_value: metric.conversions_value,  \n"
            "    cost_per_conversion: metric.cost_per_conversion,  \n",
            label=f"{code_node}/cost_per_conversion-output",
        )

    old_dedupe = (
        "  if (campaign.campaign_id && !uniqueCampaignsMap.has(campaign.campaign_id)) {  \n"
        "    uniqueCampaignsMap.set(campaign.campaign_id, campaign);  \n"
        "  }  \n"
    )
    new_dedupe = (
        "  const canonicalKey = `${campaign.customer_id}:${campaign.campaign_id}`;  \n"
        "  if (campaign.customer_id && campaign.campaign_id && !uniqueCampaignsMap.has(canonicalKey)) {  \n"
        "    uniqueCampaignsMap.set(canonicalKey, campaign);  \n"
        "  }  \n"
    )
    if "const canonicalKey = `${campaign.customer_id}:${campaign.campaign_id}`" not in code:
        code = _replace_once(code, old_dedupe, new_dedupe, label=f"{code_node}/dedupe")

    node["parameters"]["jsCode"] = code


def _patch_rpc(workflow: dict[str, Any], rpc_node: str) -> None:
    node = _node(workflow, rpc_node)
    body = node["parameters"]["jsonBody"]
    body = _replace_once(
        body,
        '    "p_customer_id": "",',
        '    "p_customer_id": "{{ $json.customer_id }}",',
        label=f"{rpc_node}/customer_id",
    )
    node["parameters"]["jsonBody"] = body


def _patch_daily_write(workflow: dict[str, Any], daily_node: str) -> None:
    node = _node(workflow, daily_node)
    body = node["parameters"]["jsonBody"]
    old = (
        '  "cost_per_conversion": {{ $json.conversions > 0 ? '
        '($json.spend / $json.conversions).toFixed(4) : 0 }},'
    )
    body = _replace_once(
        body,
        old,
        '  "cost_per_conversion": {{ $json.cost_per_conversion }},',
        label=f"{daily_node}/cost_per_conversion",
    )
    node["parameters"]["jsonBody"] = body

    headers = node["parameters"]["headerParameters"]["parameters"]
    prefer = next((item for item in headers if item.get("name") == "Prefer"), None)
    if prefer is None:
        raise ValueError(f"{daily_node}: header Prefer ausente")
    prefer["value"] = "return=representation,resolution=merge-duplicates"


def _synchronize_writes(
    workflow: dict[str, Any],
    *,
    loop_node: str,
    rpc_node: str,
    daily_node: str,
) -> None:
    if any(node.get("name") == MERGE_NAME for node in workflow["nodes"]):
        raise ValueError(f"{MERGE_NAME!r} já existe")

    rpc = _node(workflow, rpc_node)
    daily = _node(workflow, daily_node)
    midpoint_x = max(rpc["position"][0], daily["position"][0]) + 320
    midpoint_y = round((rpc["position"][1] + daily["position"][1]) / 2)
    workflow["nodes"].append(
        {
            "parameters": {
                "mode": "combine",
                "combineBy": "combineByPosition",
                "options": {},
            },
            "type": "n8n-nodes-base.merge",
            "typeVersion": 3.2,
            "position": [midpoint_x, midpoint_y],
            "id": str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"volc:n8n:{workflow.get('id', workflow['name'])}:{MERGE_NAME}",
                )
            ),
            "name": MERGE_NAME,
        }
    )

    workflow["connections"][rpc_node] = {
        "main": [[{"node": MERGE_NAME, "type": "main", "index": 0}]]
    }
    workflow["connections"][daily_node] = {
        "main": [[{"node": MERGE_NAME, "type": "main", "index": 1}]]
    }
    workflow["connections"][MERGE_NAME] = {
        "main": [[{"node": loop_node, "type": "main", "index": 0}]]
    }


def _validate(workflow: dict[str, Any], *, role: str) -> None:
    names = [node["name"] for node in workflow["nodes"]]
    if len(names) != len(set(names)):
        raise ValueError("nomes de nós duplicados")
    ids = [node["id"] for node in workflow["nodes"]]
    if len(ids) != len(set(ids)):
        raise ValueError("IDs de nós duplicados")

    known = set(names)
    for source, groups in workflow["connections"].items():
        if source not in known:
            raise ValueError(f"conexão parte de nó inexistente: {source}")
        for group in groups.get("main", []):
            for connection in group:
                if connection["node"] not in known:
                    raise ValueError(
                        f"conexão {source} aponta para nó inexistente: {connection['node']}"
                    )

    serialized_sources = [
        source
        for source, groups in workflow["connections"].items()
        for group in groups.get("main", [])
        for connection in group
        if connection["node"] == MERGE_NAME
    ]
    if len(serialized_sources) != 2:
        raise ValueError(f"merge deve aguardar duas gravações; recebeu {serialized_sources}")

    payload_text = json.dumps(workflow, ensure_ascii=False)
    if '"p_customer_id": ""' in payload_text:
        raise ValueError("RPC ainda contém customer_id vazio")
    if "($json.spend / $json.conversions)" in payload_text:
        raise ValueError("cost_per_conversion ainda é recalculado")
    if role == "d1" and '"value": "21"' in payload_text:
        raise ValueError("D-1 ainda referencia API v21")


def adapt(workflow: dict[str, Any], *, role: str) -> dict[str, Any]:
    if workflow.get("active"):
        raise ValueError("o workflow de destino está ativo; abortando por segurança")

    # O GET inclui propriedades internas que o contrato público do PUT rejeita.
    workflow["settings"] = {
        key: value
        for key, value in dict(workflow.get("settings") or {}).items()
        if key in PUBLIC_SETTINGS
    }
    workflow["settings"]["executionOrder"] = "v1"
    workflow["settings"]["timezone"] = "America/Sao_Paulo"
    _set_api_version(workflow)

    if role == "d0":
        _patch_metrics_query(workflow, "Google Ads - Get metrics1")
        _patch_code(workflow, "Code")
        _patch_rpc(workflow, "Supabase - Populate gam_reports2")
        _patch_daily_write(workflow, "Supabase - Populate gam_reports3")
        _synchronize_writes(
            workflow,
            loop_node="Loop Over Items3",
            rpc_node="Supabase - Populate gam_reports2",
            daily_node="Supabase - Populate gam_reports3",
        )
    elif role == "d1":
        _patch_metrics_query(workflow, "Google Ads - Get metrics")
        _patch_code(workflow, "Code15")
        _patch_rpc(workflow, "Supabase - Populate gam_reports")
        _patch_daily_write(workflow, "Supabase - Populate gam_reports1")
        _synchronize_writes(
            workflow,
            loop_node="Loop Over Items1",
            rpc_node="Supabase - Populate gam_reports",
            daily_node="Supabase - Populate gam_reports1",
        )
    else:
        raise ValueError(f"papel desconhecido: {role}")

    _validate(workflow, role=role)
    return {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": workflow["settings"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--role", required=True, choices=("d0", "d1"))
    args = parser.parse_args()

    workflow = json.loads(args.input.read_text(encoding="utf-8"))
    payload = adapt(workflow, role=args.role)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
