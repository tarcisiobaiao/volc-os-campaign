#!/usr/bin/env python3
"""Une o grafo técnico do Graphify ao Mapa Mestre de negócio do VOLC O.S.

O script não extrai código e não acessa rede. Ele recebe:

1. ``graphify-out/graph.json`` produzido pelo Graphify em modo local/AST;
2. ``docs/volc-os-graph/volc-os-graph.json`` produzido pelo inventário VOLC.

O resultado preserva a trilha de confiança do Graphify e adiciona pontes
determinísticas entre capacidades, telas, serviços, APIs, tabelas e o código que
as implementa. Para executá-lo, use um Python que tenha ``graphifyy`` instalado.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.cluster import score_all
from graphify.export import to_html, to_json
from graphify.paths import load_node_link_graph
from graphify.report import generate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUSINESS = ROOT / "docs" / "volc-os-graph" / "volc-os-graph.json"
DEFAULT_OUTPUT = ROOT / "graphify-out"

CONFIDENCE = {
    "measured": ("EXTRACTED", 1.0),
    "documented": ("EXTRACTED", 1.0),
    "modeled": ("INFERRED", 0.82),
    "inferred": ("INFERRED", 0.72),
    "ambiguous": ("AMBIGUOUS", 0.45),
}

TECH_LABELS = {
    "api": "Código · APIs e integrações",
    "backend": "Código · Backend e motores",
    "src": "Código · Produto e interface",
    "supabase": "Código · Supabase e banco",
    "n8n": "Código · Automações n8n",
    "tests": "Código · Qualidade e testes",
    "volc_ads": "Código · Motor Google Ads",
    "funnelforge-migracao": "Código · FunnelForge",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-graph", type=Path, required=True,
                        help="graph.json gerado pelo Graphify para o código")
    parser.add_argument("--business-graph", type=Path, default=DEFAULT_BUSINESS,
                        help="Mapa Mestre de negócio em JSON")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="diretório graphify-out de destino")
    parser.add_argument("--no-html", action="store_true",
                        help="não gerar a visualização HTML agregada")
    return parser.parse_args()


def normalized(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\(\)$", "", text)
    text = text.lstrip(".")
    return re.sub(r"[^a-z0-9à-ÿ]+", "", text)


def local_source(value: object) -> str:
    source = str(value or "").strip().replace("\\", "/")
    if not source or source.startswith(("http://", "https://")):
        return ""
    if "," in source or source.startswith("Fontes oficiais"):
        return ""
    candidate = ROOT / source
    return source if candidate.exists() else ""


def as_multigraph(graph: nx.Graph) -> nx.MultiGraph:
    result = nx.MultiGraph()
    result.graph.update(graph.graph)
    result.add_nodes_from((node_id, dict(data)) for node_id, data in graph.nodes(data=True))
    for source, target, data in graph.edges(data=True):
        result.add_edge(source, target, **dict(data))
    return result


def build_indexes(graph: nx.Graph) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    by_file: dict[str, list[str]] = defaultdict(list)
    by_label: dict[str, list[str]] = defaultdict(list)
    for node_id, data in graph.nodes(data=True):
        source_file = str(data.get("source_file") or "").replace("\\", "/")
        if source_file:
            by_file[source_file].append(node_id)
        label = normalized(data.get("label"))
        if label:
            by_label[label].append(node_id)
    return by_file, by_label


def candidate_score(graph: nx.Graph, node_id: str, business: dict, source: str) -> int:
    data = graph.nodes[node_id]
    label = normalized(data.get("label"))
    wanted = {
        normalized(business.get("component")),
        normalized(business.get("label")),
        normalized(Path(source).stem if source else ""),
        normalized(Path(source).name if source else ""),
    }
    wanted.discard("")
    score = 0
    if label in wanted:
        score += 100
    if source and str(data.get("source_file") or "") == source:
        score += 40
    if source and data.get("label") == Path(source).name:
        score += 30
    if data.get("_callable"):
        score += 5
    return score


def resolve_bridge(graph: nx.Graph, business: dict,
                   by_file: dict[str, list[str]],
                   by_label: dict[str, list[str]]) -> tuple[str | None, str, str, float]:
    source = local_source(business.get("source"))
    if source and by_file.get(source):
        candidates = by_file[source]
        chosen = max(candidates, key=lambda node_id: candidate_score(graph, node_id, business, source))
        return chosen, "implemented_by", "EXTRACTED", 1.0

    node_type = business.get("type")
    if node_type in {"table_or_view", "database_function"}:
        candidates = by_label.get(normalized(business.get("label")), [])
        if candidates:
            chosen = max(
                candidates,
                key=lambda node_id: (
                    graph.nodes[node_id].get("file_type") == "code",
                    bool(graph.nodes[node_id].get("source_file")),
                ),
            )
            return chosen, "represented_in_code_as", "INFERRED", 0.78

    return None, "", "", 0.0


def add_business_layer(graph: nx.MultiGraph, business_data: dict) -> dict[str, int]:
    by_file, by_label = build_indexes(graph)
    business_ids: dict[str, str] = {}

    for item in business_data["nodes"]:
        node_id = f"volc::{item['id']}"
        business_ids[item["id"]] = node_id
        source_file = local_source(item.get("source"))
        attributes = dict(item)
        attributes.update({
            "id": node_id,
            "local_id": item["id"],
            "repo": "volc-business",
            "file_type": "business",
            "_origin": "volc_inventory",
            "norm_label": normalized(item.get("label")),
            "source_file": source_file,
            "source_location": "",
        })
        graph.add_node(node_id, **attributes)

    business_edges = 0
    for edge in business_data["edges"]:
        source = business_ids.get(edge["source"])
        target = business_ids.get(edge["target"])
        if not source or not target:
            continue
        evidence_source = (
            graph.nodes[source].get("source_file")
            or "docs/volc-os-graph/volc-os-graph.json"
        )
        confidence, score = CONFIDENCE.get(
            str(edge.get("confidence") or "").lower(), ("AMBIGUOUS", 0.45)
        )
        graph.add_edge(
            source,
            target,
            relation=edge.get("relation") or "related_to",
            confidence=confidence,
            confidence_score=score,
            context="business",
            evidence=edge.get("evidence") or "",
            _origin="volc_inventory",
            _src=source,
            _tgt=target,
            source_file=evidence_source,
            source_location="",
            weight=1.0,
        )
        business_edges += 1

    bridges = 0
    bridge_types: Counter[str] = Counter()
    for item in business_data["nodes"]:
        target, relation, confidence, score = resolve_bridge(graph, item, by_file, by_label)
        if not target:
            continue
        source = business_ids[item["id"]]
        evidence_source = (
            graph.nodes[source].get("source_file")
            or "docs/volc-os-graph/volc-os-graph.json"
        )
        graph.add_edge(
            source,
            target,
            relation=relation,
            confidence=confidence,
            confidence_score=score,
            context="business_to_code",
            evidence=(
                f"Correspondência determinística entre {item.get('type')} "
                f"e {graph.nodes[target].get('source_file') or graph.nodes[target].get('label')}."
            ),
            _origin="volc_adapter",
            _src=source,
            _tgt=target,
            source_file=evidence_source,
            source_location="",
            weight=1.0,
        )
        bridges += 1
        bridge_types[relation] += 1

    return {
        "business_nodes": len(business_ids),
        "business_edges": business_edges,
        "bridges": bridges,
        **{f"bridge_{key}": value for key, value in bridge_types.items()},
    }


def technical_label(graph: nx.Graph, members: list[str]) -> str:
    roots: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    for node_id in members:
        data = graph.nodes[node_id]
        source = str(data.get("source_file") or "")
        if source:
            roots[source.split("/", 1)[0]] += 1
        if data.get("label"):
            labels[str(data["label"])] += graph.degree(node_id) + 1
    if roots:
        root, _ = roots.most_common(1)[0]
        if root in TECH_LABELS:
            return TECH_LABELS[root]
        return f"Código · {root.replace('-', ' ').replace('_', ' ').title()}"
    if labels:
        return f"Núcleo · {labels.most_common(1)[0][0][:54]}"
    return "Núcleo técnico"


def label_communities(graph: nx.Graph,
                      communities: dict[int, list[str]]) -> dict[int, str]:
    labels: dict[int, str] = {}
    used: Counter[str] = Counter()
    for community_id, members in communities.items():
        business_clusters = Counter(
            graph.nodes[node_id].get("cluster_label")
            for node_id in members
            if graph.nodes[node_id].get("file_type") == "business"
            and graph.nodes[node_id].get("cluster_label")
        )
        base = (
            f"VOLC · {business_clusters.most_common(1)[0][0]}"
            if business_clusters
            else technical_label(graph, members)
        )
        used[base] += 1
        labels[community_id] = base if used[base] == 1 else f"{base} · {used[base]}"
    return labels


def hybrid_communities(graph: nx.Graph, business_data: dict) -> dict[int, list[str]]:
    """Preserva comunidades técnicas do Graphify e os 10 domínios do Mapa Mestre.

    Reagrupar os nove mil nós depois de adicionar poucas pontes de negócio torna
    o resultado sensível a empates internos do Louvain. As comunidades técnicas
    já foram detectadas pelo Graphify; os clusters operacionais já foram curados
    pelo Mapa Mestre. Preservar ambos é mais fiel e reprodutível.
    """
    communities: dict[int, list[str]] = defaultdict(list)
    code_ids: list[int] = []
    for node_id, data in graph.nodes(data=True):
        if data.get("file_type") == "business":
            continue
        community_id = data.get("community")
        if community_id is None:
            continue
        community_id = int(community_id)
        communities[community_id].append(node_id)
        code_ids.append(community_id)

    next_id = max(code_ids, default=-1) + 1
    business_cluster_ids = {
        cluster_id: next_id + index
        for index, cluster_id in enumerate(business_data.get("clusters", {}))
    }
    fallback_id = next_id + len(business_cluster_ids)

    for node_id, data in graph.nodes(data=True):
        if data.get("file_type") == "business":
            community_id = business_cluster_ids.get(data.get("cluster"), fallback_id)
            communities[community_id].append(node_id)
        elif data.get("community") is None:
            communities[fallback_id].append(node_id)

    return {
        community_id: sorted(members)
        for community_id, members in sorted(communities.items())
        if members
    }


def git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def write_readme(output: Path, stats: dict[str, int], graph: nx.Graph,
                 communities: dict[int, list[str]]) -> None:
    confidence = Counter(
        data.get("confidence", "EXTRACTED") for _, _, data in graph.edges(data=True)
    )
    content = f"""# VOLC O.S. · Knowledge Graph híbrido

Este diretório é a fonte consultável que une duas lentes complementares:

- **Graphify local/AST:** estrutura real do código, SQL, chamadas e imports;
- **Mapa Mestre VOLC:** operação, capacidades, Supabase vivo, n8n, ClickUp,
  documentos, estados e prioridades.

## Snapshot atual

- {graph.number_of_nodes():,} nós e {graph.number_of_edges():,} relações;
- {len(communities):,} comunidades detectadas automaticamente;
- {stats['business_nodes']:,} nós e {stats['business_edges']:,} relações de negócio;
- {stats['bridges']:,} pontes negócio → implementação;
- confiança: {confidence['EXTRACTED']:,} extraídas, {confidence['INFERRED']:,}
  inferidas e {confidence['AMBIGUOUS']:,} ambíguas.

## Arquivos

- `graph.json` — fonte integral para consulta e travessia;
- `UPDATE_STATUS.json` — carimbo de atualização e hash dos insumos;
- `graph.html` — visão agregada das comunidades;
- `graph.graphml` — intercâmbio com Gephi, yEd e ferramentas GraphML;
- `hybrid-nodes.csv` / `hybrid-edges.csv` — importação visual no Neo4j Aura;
- `cypher.txt` — importação por Cypher em bancos Neo4j compatíveis;
- `obsidian-volc-os/` — vault curado para o Graph view do Obsidian;
- `GRAPH_REPORT.md` — hubs, ligações inesperadas e perguntas sugeridas;
- `.graphify_analysis.json` — análises estruturadas;
- `.graphify_labels.json` — nomes determinísticos das comunidades.

O mapa executivo continua em `../entregaveis/Mapa_Mestre_VOLC_OS.html`; ele é a
melhor porta de entrada humana. Este grafo híbrido é a camada profunda, usada
para responder perguntas como “qual código implementa esta capacidade?”, “o que
é impactado por esta tabela?” e “qual caminho liga tráfego a monetização?”.

Para navegar visualmente como em uma rede neural ou no grafo do Obsidian, abra
`../entregaveis/Explorador_Neural_VOLC_OS.html`. Ele funciona por duplo clique,
sem servidor, login ou internet, e oferece quatro lentes: Mapa, Pontes, Rede
completa e Vizinhança.

## Consultar

Com o pacote oficial `graphifyy` instalado:

```bash
graphify query "o que conecta o Hub de Tráfego ao cockpit de campanha?"
graphify path "Hub de Tráfego" "Cockpit de campanha"
graphify explain "Loop de conversão offline"
graphify affected "campaign_funnel_urls" --relation represented_in_code_as --depth 2
graphify god-nodes --top 20
```

## Atualizar

Execute o pipeline único na raiz do projeto:

```bash
python3 scripts/atualizar_grafo_volc_os.py
```

Ele atualiza o Mapa Mestre, regenera o AST local de código/SQL, refaz o híbrido,
exporta Obsidian/GraphML/CSV/Cypher e reconstrói o Explorador Neural. Para conferir
se algo mudou desde a última execução:

```bash
python3 scripts/atualizar_grafo_volc_os.py --check
```

Use `--refresh-live` quando quiser refazer antes o inventário somente-leitura do
Supabase. Use `--reuse-technical` somente quando código e SQL não mudaram.

As relações do inventário medidas no código/banco são convertidas em
`EXTRACTED`; relações de negócio modeladas viram `INFERRED`; pontes por nome sem
arquivo inequívoco também permanecem `INFERRED`. Assim, hipótese nunca se
disfarça de fato.
"""
    (output / "README.md").write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    raw_code = json.loads(args.code_graph.read_text(encoding="utf-8"))
    graph = as_multigraph(load_node_link_graph(raw_code))
    business_data = json.loads(args.business_graph.read_text(encoding="utf-8"))
    stats = add_business_layer(graph, business_data)

    communities = hybrid_communities(graph, business_data)
    labels = label_communities(graph, communities)
    cohesion = score_all(graph, communities)
    gods = god_nodes(graph, top_n=20)
    surprises = surprising_connections(graph, communities, top_n=12)
    questions = suggest_questions(graph, communities, labels, top_n=10)
    commit = git_head()

    if not to_json(
        graph,
        communities,
        str(output / "graph.json"),
        force=True,
        built_at_commit=commit,
        community_labels=labels,
    ):
        raise RuntimeError("Graphify recusou gravar graph.json")

    report = generate(
        graph,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        {
            "warning": (
                "Grafo híbrido: AST local do código + inventário operacional "
                "VOLC; documentos extensos permanecem na camada curada."
            )
        },
        {"input": 0, "output": 0},
        str(ROOT),
        suggested_questions=questions,
        built_at_commit=commit,
    )
    (output / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")

    analysis = {
        "methodology": "Graphify local AST + curated VOLC operational graph",
        "stats": stats,
        "communities": {str(key): value for key, value in communities.items()},
        "cohesion": {str(key): value for key, value in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
        "questions": questions,
    }
    (output / ".graphify_analysis.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / ".graphify_labels.json").write_text(
        json.dumps({str(key): value for key, value in labels.items()},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if not args.no_html:
        to_html(
            graph,
            communities,
            str(output / "graph.html"),
            community_labels=labels,
            node_limit=5000,
        )

    write_readme(output, stats, graph, communities)
    print(json.dumps({
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "communities": len(communities),
        **stats,
        "output": str(output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
