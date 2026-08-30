#!/usr/bin/env python3
"""Gera formatos derivados do grafo VOLC sem alterar suas fontes oficiais.

Saídas:
- GraphML e Cypher do grafo híbrido completo;
- vault Obsidian do mapa operacional curado;
- ZIP pronto para abrir/importar no Obsidian.

Execute com o Python do ambiente Graphify.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import networkx as nx
from graphify.export import to_cypher, to_obsidian
from graphify.paths import load_node_link_graph


ROOT = Path(__file__).resolve().parents[1]
HYBRID_JSON = ROOT / "graphify-out" / "graph.json"
ANALYSIS_JSON = ROOT / "graphify-out" / ".graphify_analysis.json"
LABELS_JSON = ROOT / "graphify-out" / ".graphify_labels.json"
BUSINESS_JSON = ROOT / "docs" / "volc-os-graph" / "volc-os-graph.json"
VAULT = ROOT / "graphify-out" / "obsidian-volc-os"
ZIP_BASE = ROOT / "entregaveis" / "VOLC_OS_Obsidian_Vault"


def scalar(value: object) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def write_graphml(graph: nx.Graph, communities: dict[int, list[str]], path: Path) -> None:
    """Exporta MultiGraph preservando relações paralelas e atributos escalares."""
    node_community = {
        node_id: community_id
        for community_id, members in communities.items()
        for node_id in members
    }
    exported = graph.copy()
    for node_id, attrs in exported.nodes(data=True):
        attrs["community"] = node_community.get(node_id, -1)
        for key in list(attrs):
            if key.startswith("_"):
                del attrs[key]
            else:
                attrs[key] = scalar(attrs[key])
    if exported.is_multigraph():
        edge_iter = exported.edges(keys=True, data=True)
        for _source, _target, _key, attrs in edge_iter:
            for name in list(attrs):
                if name.startswith("_"):
                    del attrs[name]
                else:
                    attrs[name] = scalar(attrs[name])
    else:
        for _source, _target, attrs in exported.edges(data=True):
            for name in list(attrs):
                if name.startswith("_"):
                    del attrs[name]
                else:
                    attrs[name] = scalar(attrs[name])
    for key in list(exported.graph):
        exported.graph[key] = scalar(exported.graph[key])
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(exported, path)


def write_hybrid_csv(graph: nx.Graph, communities: dict[int, list[str]], output: Path) -> None:
    """Gera dois CSVs simples, apropriados ao Data Importer do Neo4j Aura."""
    node_community = {
        node_id: community_id
        for community_id, members in communities.items()
        for node_id in members
    }
    output.mkdir(parents=True, exist_ok=True)
    node_fields = [
        "id", "label", "file_type", "community", "community_name",
        "source_file", "source_location", "state", "cluster_label", "summary",
    ]
    with (output / "hybrid-nodes.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=node_fields)
        writer.writeheader()
        for node_id, data in graph.nodes(data=True):
            writer.writerow({
                "id": node_id,
                "label": data.get("label", node_id),
                "file_type": data.get("file_type", "unknown"),
                "community": node_community.get(node_id, -1),
                "community_name": data.get("community_name", ""),
                "source_file": data.get("source_file", ""),
                "source_location": data.get("source_location", ""),
                "state": data.get("state", ""),
                "cluster_label": data.get("cluster_label", ""),
                "summary": data.get("summary", ""),
            })
    edge_fields = ["source", "target", "relation", "confidence", "context", "evidence"]
    with (output / "hybrid-edges.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=edge_fields)
        writer.writeheader()
        for source, target, data in graph.edges(data=True):
            writer.writerow({
                "source": source,
                "target": target,
                "relation": data.get("relation", "related_to"),
                "confidence": data.get("confidence", "EXTRACTED"),
                "context": data.get("context", ""),
                "evidence": data.get("evidence", ""),
            })


def business_graph(payload: dict) -> tuple[nx.MultiDiGraph, dict[int, list[str]], dict[int, str]]:
    graph = nx.MultiDiGraph()
    cluster_ids = {key: index for index, key in enumerate(payload["clusters"])}
    communities = {community_id: [] for community_id in cluster_ids.values()}
    labels = {cluster_ids[key]: label for key, label in payload["clusters"].items()}

    for node in payload["nodes"]:
        attrs = dict(node)
        node_id = attrs.pop("id")
        attrs.update({
            "file_type": "business",
            "source_file": attrs.get("source", ""),
            "source_location": "",
        })
        graph.add_node(node_id, **attrs)
        communities[cluster_ids[node["cluster"]]].append(node_id)

    confidence = {
        "measured": "EXTRACTED",
        "documented": "EXTRACTED",
        "modeled": "INFERRED",
        "inferred": "INFERRED",
        "ambiguous": "AMBIGUOUS",
    }
    for edge in payload["edges"]:
        graph.add_edge(
            edge["source"], edge["target"],
            relation=edge.get("relation", "related_to"),
            confidence=confidence.get(edge.get("confidence", ""), "AMBIGUOUS"),
            evidence=edge.get("evidence", ""),
        )
    return graph, communities, labels


def write_vault_intro(vault: Path, payload: dict) -> None:
    community_notes = sorted(vault.glob("_COMMUNITY_*.md"))
    links = "\n".join(f"- [[{note.stem}]]" for note in community_notes)
    intro = f"""---
type: inicio
tags:
  - volc-os/mapa-vivo
---

# VOLC O.S. · Mapa Vivo

Este vault é uma **visualização gerada**. A fonte oficial continua no projeto;
não edite estas notas esperando que o JSON seja atualizado na volta.

## Como navegar

1. Abra **Graph view** para ver a operação como rede.
2. Comece pelas comunidades abaixo.
3. Abra o **Local graph** de uma capacidade para investigar apenas seus vizinhos.
4. Use as propriedades `state`, `type`, `community` e as tags para filtrar.

## Comunidades

{links}

## Tamanho

- {len(payload['nodes'])} nós operacionais curados;
- {len(payload['edges'])} relações;
- o grafo técnico completo permanece em `graphify-out/graph.json`.
"""
    (vault / "_INICIO.md").write_text(intro, encoding="utf-8")
    (vault / "_ATUALIZACAO.md").write_text(
        "# Atualização\n\nExecute `scripts/atualizar_grafo_volc_os.py` na raiz do projeto. "
        "Esta pasta e o ZIP serão recriados a partir das fontes oficiais.\n",
        encoding="utf-8",
    )


def main() -> None:
    hybrid_raw = json.loads(HYBRID_JSON.read_text(encoding="utf-8"))
    hybrid = load_node_link_graph(hybrid_raw)
    analysis = json.loads(ANALYSIS_JSON.read_text(encoding="utf-8"))
    communities = {
        int(key): members for key, members in analysis["communities"].items()
    }
    write_graphml(hybrid, communities, ROOT / "graphify-out" / "graph.graphml")
    write_hybrid_csv(hybrid, communities, ROOT / "graphify-out")
    to_cypher(hybrid, str(ROOT / "graphify-out" / "cypher.txt"))

    business_payload = json.loads(BUSINESS_JSON.read_text(encoding="utf-8"))
    business, business_communities, business_labels = business_graph(business_payload)
    VAULT.mkdir(parents=True, exist_ok=True)
    notes = to_obsidian(
        business,
        business_communities,
        str(VAULT),
        community_labels=business_labels,
    )
    write_vault_intro(VAULT, business_payload)
    ZIP_BASE.parent.mkdir(parents=True, exist_ok=True)
    zip_path = Path(shutil.make_archive(str(ZIP_BASE), "zip", root_dir=VAULT))
    print(json.dumps({
        "graphml": str(ROOT / "graphify-out" / "graph.graphml"),
        "neo4j_nodes_csv": str(ROOT / "graphify-out" / "hybrid-nodes.csv"),
        "neo4j_edges_csv": str(ROOT / "graphify-out" / "hybrid-edges.csv"),
        "cypher": str(ROOT / "graphify-out" / "cypher.txt"),
        "obsidian_vault": str(VAULT),
        "obsidian_notes": notes + 2,
        "obsidian_zip": str(zip_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
