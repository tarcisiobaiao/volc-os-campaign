#!/usr/bin/env python3
"""Gera um explorador neural standalone para o grafo híbrido do VOLC O.S."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graphify-out" / "graph.json"
OUTPUT = ROOT / "entregaveis" / "Explorador_Neural_VOLC_OS.html"


BUSINESS_COLORS = {
    "strategy": "#70B7FF",
    "discovery": "#00D4FF",
    "production": "#9A7BFF",
    "acquisition": "#FF8A4C",
    "measurement": "#43D19E",
    "decision": "#F4C95D",
    "publisher_quality": "#FF6B9A",
    "governance": "#AAB7CF",
    "platform": "#6CC7C2",
    "data": "#D781FF",
}

TECH_COLORS = {
    "src": "#5B789B",
    "backend": "#7F6C9B",
    "volc_ads": "#A06D4C",
    "funnelforge-migracao": "#6E8F81",
    "api": "#5F8C94",
    "supabase": "#7A8799",
    "tests": "#6B7180",
    "other": "#596274",
}

SECTOR_ANGLES = {
    "src": -95,
    "backend": -30,
    "volc_ads": 28,
    "api": 72,
    "supabase": 118,
    "funnelforge-migracao": 185,
    "tests": 245,
    "other": 300,
}


def stable_fraction(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8", "replace")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def tech_root(node: dict) -> str:
    source = str(node.get("source_file") or "")
    root = source.split("/", 1)[0] if source else "other"
    return root if root in TECH_COLORS else "other"


def prepare_graph(data: dict) -> dict:
    degree: Counter[str] = Counter()
    adjacency: dict[str, list[int]] = defaultdict(list)
    for index, edge in enumerate(data["links"]):
        degree[str(edge["source"])] += 1
        degree[str(edge["target"])] += 1
        adjacency[str(edge["source"])].append(index)
        adjacency[str(edge["target"])].append(index)

    community_groups: dict[int, list[dict]] = defaultdict(list)
    for node in data["nodes"]:
        if node.get("file_type") != "business":
            community_groups[int(node.get("community") or 0)].append(node)

    community_centers: dict[int, tuple[float, float]] = {}
    grouped_communities: dict[str, list[tuple[int, list[dict]]]] = defaultdict(list)
    for community, members in community_groups.items():
        root_counts = Counter(tech_root(node) for node in members)
        grouped_communities[root_counts.most_common(1)[0][0]].append((community, members))

    for root, groups in grouped_communities.items():
        groups.sort(key=lambda pair: (-len(pair[1]), pair[0]))
        base = math.radians(SECTOR_ANGLES[root])
        for index, (community, members) in enumerate(groups):
            lane = index % 9
            ring = index // 9
            angle = base + math.radians((lane - 4) * 5.5)
            radius = 1680 + ring * 125 + lane * 22
            jitter = (stable_fraction(f"community:{community}") - 0.5) * 80
            community_centers[community] = (
                math.cos(angle) * (radius + jitter),
                math.sin(angle) * (radius + jitter),
            )

    business_clusters = [
        "strategy", "discovery", "production", "acquisition", "measurement",
        "decision", "publisher_quality", "governance", "platform", "data",
    ]
    business_centers = {
        cluster: (
            math.cos(math.radians(-90 + index * 36)) * 720,
            math.sin(math.radians(-90 + index * 36)) * 720,
        )
        for index, cluster in enumerate(business_clusters)
    }

    nodes = []
    for node in data["nodes"]:
        node_id = str(node["id"])
        is_business = node.get("file_type") == "business"
        if is_business:
            cluster = str(node.get("cluster") or "data")
            cx, cy = business_centers.get(cluster, (0.0, 0.0))
            siblings = [
                item for item in data["nodes"]
                if item.get("file_type") == "business" and item.get("cluster") == cluster
            ]
            position = next(i for i, item in enumerate(siblings) if str(item["id"]) == node_id)
            count = len(siblings)
            ring = 70 + 34 * math.sqrt(position + 1)
            angle = 2 * math.pi * (position / max(count, 1) + stable_fraction(node_id) * 0.08)
            x, y = cx + math.cos(angle) * ring, cy + math.sin(angle) * ring
            color = BUSINESS_COLORS.get(cluster, "#00D4FF")
        else:
            community = int(node.get("community") or 0)
            cx, cy = community_centers.get(community, (0.0, 0.0))
            members = community_groups[community]
            position = next(i for i, item in enumerate(members) if str(item["id"]) == node_id)
            angle = position * 2.399963229728653 + stable_fraction(node_id) * 0.35
            ring = 9.5 * math.sqrt(position + 1)
            x, y = cx + math.cos(angle) * ring, cy + math.sin(angle) * ring
            color = TECH_COLORS[tech_root(node)]

        nodes.append({
            "id": node_id,
            "label": node.get("label") or node_id,
            "x": round(x, 2),
            "y": round(y, 2),
            "r": round(2.1 + min(9, math.sqrt(degree[node_id])) * (0.65 if is_business else 0.42), 2),
            "color": color,
            "business": is_business,
            "community": node.get("community"),
            "community_name": node.get("community_name") or "Sem comunidade",
            "cluster": node.get("cluster") or "",
            "cluster_label": node.get("cluster_label") or "",
            "type": node.get("type") or node.get("file_type") or "unknown",
            "state": node.get("state") or "",
            "state_label": node.get("state_label") or "",
            "summary": node.get("summary") or "",
            "evidence": node.get("evidence") or "",
            "source": node.get("source") or node.get("source_file") or "",
            "source_location": node.get("source_location") or "",
            "degree": degree[node_id],
        })

    edges = []
    for edge in data["links"]:
        edges.append({
            "source": str(edge["source"]),
            "target": str(edge["target"]),
            "relation": edge.get("relation") or "related_to",
            "confidence": edge.get("confidence") or "EXTRACTED",
            "context": edge.get("context") or "code",
        })

    return {
        "meta": {
            "nodes": len(nodes),
            "edges": len(edges),
            "business_nodes": sum(node["business"] for node in nodes),
            "bridges": sum(edge["context"] == "business_to_code" for edge in edges),
            "communities": len({node["community"] for node in nodes}),
        },
        "nodes": nodes,
        "edges": edges,
    }


HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VOLC O.S. · Explorador Neural</title>
<style>
:root {
  color-scheme: dark;
  --bg: oklch(13% .018 274);
  --surface: oklch(17% .022 274);
  --surface-2: oklch(20% .024 274);
  --line: oklch(32% .026 274 / .68);
  --text: oklch(93% .01 250);
  --muted: oklch(69% .022 255);
  --quiet: oklch(52% .022 255);
  --cyan: oklch(78% .14 210);
  --orange: oklch(72% .17 48);
  --focus: oklch(86% .13 205);
  --danger: oklch(66% .2 28);
}
* { box-sizing: border-box; }
html, body { width: 100%; height: 100%; margin: 0; overflow: hidden; }
body { background: var(--bg); color: var(--text); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
button, input { font: inherit; }
button { color: inherit; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.app { height: 100%; display: grid; grid-template-rows: 64px 1fr 30px; }
.topbar { display: grid; grid-template-columns: minmax(260px, 1fr) minmax(300px, 620px) minmax(260px, 1fr); align-items: center; gap: 24px; padding: 0 20px; background: var(--surface); border-bottom: 1px solid var(--line); z-index: 4; }
.brand { display: flex; align-items: baseline; gap: 12px; min-width: 0; }
.brand strong { font-size: 15px; letter-spacing: .08em; white-space: nowrap; }
.brand span { color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.search { position: relative; }
.search input { width: 100%; height: 38px; padding: 0 42px 0 14px; color: var(--text); background: var(--bg); border: 1px solid var(--line); border-radius: 7px; }
.search input::placeholder { color: var(--quiet); }
.search kbd { position: absolute; right: 12px; top: 10px; color: var(--quiet); font-size: 11px; }
.results { display: none; position: absolute; top: 44px; left: 0; right: 0; max-height: 360px; overflow: auto; background: var(--surface); border: 1px solid var(--line); z-index: 8; }
.results.open { display: block; }
.result { width: 100%; display: grid; grid-template-columns: 9px 1fr auto; align-items: center; gap: 10px; padding: 10px 12px; text-align: left; background: transparent; border: 0; border-bottom: 1px solid var(--line); cursor: pointer; }
.result:hover { background: var(--surface-2); }
.result-dot { width: 7px; height: 7px; border-radius: 50%; }
.result-main { min-width: 0; }
.result-main b, .result-main small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-main b { font-size: 12px; }
.result-main small, .result-type { color: var(--muted); font-size: 10px; }
.top-actions { justify-self: end; display: flex; gap: 8px; }
.icon-button { min-width: 36px; height: 36px; padding: 0 10px; border: 1px solid var(--line); border-radius: 7px; background: transparent; cursor: pointer; }
.icon-button:hover { background: var(--surface-2); }
.workspace { min-height: 0; display: grid; grid-template-columns: 208px 1fr 340px; }
.rail, .inspector { min-height: 0; background: var(--surface); z-index: 3; }
.rail { border-right: 1px solid var(--line); overflow-y: auto; }
.inspector { border-left: 1px solid var(--line); overflow-y: auto; }
.section { padding: 18px 16px; border-bottom: 1px solid var(--line); }
.section h2 { margin: 0 0 12px; color: var(--muted); font-size: 10px; letter-spacing: .12em; text-transform: uppercase; }
.mode { width: 100%; display: grid; grid-template-columns: 26px 1fr; gap: 8px; padding: 9px 8px; text-align: left; background: transparent; border: 0; border-radius: 6px; cursor: pointer; }
.mode:hover { background: var(--surface-2); }
.mode[aria-pressed="true"] { background: oklch(27% .045 230); color: var(--focus); }
.mode-key { color: var(--quiet); font-size: 10px; padding-top: 2px; }
.mode b, .mode small { display: block; }
.mode b { font-size: 12px; font-weight: 600; }
.mode small { margin-top: 2px; color: var(--muted); font-size: 10px; line-height: 1.35; }
.toggle { display: flex; align-items: center; gap: 9px; padding: 7px 0; color: var(--muted); font-size: 11px; cursor: pointer; }
.toggle input { accent-color: var(--cyan); }
.legend { display: grid; gap: 7px; }
.legend-row { display: grid; grid-template-columns: 10px 1fr auto; align-items: center; gap: 8px; color: var(--muted); font-size: 10px; }
.dot { width: 7px; height: 7px; border-radius: 50%; }
.canvas-wrap { position: relative; min-width: 0; min-height: 0; overflow: hidden; background: radial-gradient(circle at 50% 48%, oklch(20% .032 255) 0, var(--bg) 54%); }
.canvas-wrap::after { content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .15; background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.12'/%3E%3C/svg%3E"); mix-blend-mode: soft-light; }
#graph { width: 100%; height: 100%; display: block; cursor: grab; }
#graph.dragging { cursor: grabbing; }
.hint { position: absolute; left: 18px; bottom: 18px; max-width: 350px; padding: 10px 12px; background: oklch(16% .02 274 / .92); border: 1px solid var(--line); color: var(--muted); font-size: 11px; line-height: 1.45; pointer-events: none; }
.selection-title { margin: 0; font-size: 17px; line-height: 1.25; }
.selection-meta { margin: 6px 0 0; color: var(--muted); font-size: 11px; line-height: 1.5; }
.selection-color { width: 28px; height: 3px; margin: 14px 0; }
.property { margin: 14px 0 0; }
.property dt { color: var(--quiet); font-size: 9px; letter-spacing: .1em; text-transform: uppercase; }
.property dd { margin: 4px 0 0; color: var(--muted); font-size: 11px; line-height: 1.5; overflow-wrap: anywhere; }
.property dd strong { color: var(--text); }
.inspector-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 16px; }
.action { min-height: 34px; padding: 7px 8px; background: transparent; border: 1px solid var(--line); border-radius: 6px; font-size: 10px; cursor: pointer; }
.action:hover { background: var(--surface-2); }
.connections { display: grid; }
.connection { display: grid; grid-template-columns: 8px 1fr; gap: 9px; padding: 9px 0; text-align: left; color: var(--muted); background: transparent; border: 0; border-bottom: 1px solid var(--line); cursor: pointer; }
.connection:hover { color: var(--text); }
.connection b, .connection small { display: block; }
.connection b { font-size: 11px; font-weight: 550; }
.connection small { margin-top: 3px; color: var(--quiet); font-size: 9px; }
.empty { color: var(--muted); font-size: 12px; line-height: 1.6; }
.statusbar { display: flex; align-items: center; justify-content: space-between; padding: 0 14px; background: var(--surface); border-top: 1px solid var(--line); color: var(--quiet); font-size: 10px; }
.statusbar strong { color: var(--muted); font-weight: 550; }
.mobile-panel { display: none; }
@media (max-width: 980px) {
  .topbar { grid-template-columns: 1fr minmax(220px, 1.2fr) auto; gap: 10px; }
  .brand span { display: none; }
  .workspace { grid-template-columns: 54px 1fr 300px; }
  .rail .section { padding: 12px 8px; }
  .rail h2, .mode b, .mode small, .toggle span, .legend { display: none; }
  .mode { grid-template-columns: 1fr; text-align: center; }
  .mode-key { font-size: 12px; }
}
@media (max-width: 720px) {
  .app { grid-template-rows: 54px 1fr 28px; }
  .topbar { grid-template-columns: auto 1fr auto; padding: 0 10px; }
  .brand strong { font-size: 12px; }
  .top-actions .export-label { display: none; }
  .workspace { grid-template-columns: 48px 1fr; }
  .inspector { display: none; }
  .hint { left: 10px; right: 10px; bottom: 10px; max-width: none; }
}
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
</style>
</head>
<body>
<main class="app">
  <header class="topbar">
    <div class="brand"><strong>VOLC O.S.</strong><span>Explorador Neural</span></div>
    <div class="search">
      <label for="search-input" class="sr-only" hidden>Buscar nó</label>
      <input id="search-input" type="search" autocomplete="off" placeholder="Buscar capacidade, tela, tabela, workflow ou arquivo">
      <kbd>/</kbd>
      <div id="search-results" class="results" role="listbox" aria-label="Resultados da busca"></div>
    </div>
    <div class="top-actions">
      <button id="fit-button" class="icon-button" type="button" title="Enquadrar grafo" aria-label="Enquadrar grafo">⌖</button>
      <button id="export-button" class="icon-button" type="button" title="Salvar imagem PNG"><span class="export-label">Salvar PNG</span></button>
    </div>
  </header>

  <div class="workspace">
    <nav class="rail" aria-label="Lentes do grafo">
      <section class="section">
        <h2>Lente</h2>
        <button class="mode" data-mode="map" aria-pressed="true"><span class="mode-key">1</span><span><b>Mapa</b><small>Operação curada</small></span></button>
        <button class="mode" data-mode="bridges" aria-pressed="false"><span class="mode-key">2</span><span><b>Pontes</b><small>Negócio e implementação</small></span></button>
        <button class="mode" data-mode="full" aria-pressed="false"><span class="mode-key">3</span><span><b>Rede completa</b><small>Todo o sistema</small></span></button>
        <button class="mode" data-mode="neighborhood" aria-pressed="false"><span class="mode-key">4</span><span><b>Vizinhança</b><small>Até dois saltos</small></span></button>
      </section>
      <section class="section">
        <h2>Relações</h2>
        <label class="toggle"><input id="show-extracted" type="checkbox" checked><span>Extraídas</span></label>
        <label class="toggle"><input id="show-inferred" type="checkbox" checked><span>Inferidas</span></label>
        <label class="toggle"><input id="show-labels" type="checkbox" checked><span>Rótulos</span></label>
      </section>
      <section class="section">
        <h2>Leitura</h2>
        <div class="legend">
          <div class="legend-row"><span class="dot" style="background:#00D4FF"></span><span>Negócio</span><span>269</span></div>
          <div class="legend-row"><span class="dot" style="background:#718096"></span><span>Código</span><span>8.892</span></div>
          <div class="legend-row"><span class="dot" style="background:#FF8A4C"></span><span>Ponte</span><span>98</span></div>
        </div>
      </section>
    </nav>

    <section class="canvas-wrap" aria-label="Área do grafo">
      <canvas id="graph" role="img" aria-label="Grafo dinâmico do VOLC O.S. Use busca ou clique em um nó para explorar."></canvas>
      <div id="hint" class="hint">Arraste para mover, use a roda para ampliar. Clique em um nó para ver evidências. Teclas 1 a 4 alternam a lente.</div>
    </section>

    <aside class="inspector" aria-label="Detalhes do nó selecionado">
      <section id="selection" class="section" aria-live="polite">
        <h2>Seleção</h2>
        <p class="empty">Selecione um nó ou use a busca. Aqui aparecem estado, evidência, origem e relações próximas.</p>
      </section>
      <section class="section">
        <h2>Conexões</h2>
        <div id="connections" class="connections"><p class="empty">Nenhum nó selecionado.</p></div>
      </section>
    </aside>
  </div>

  <footer class="statusbar">
    <span id="status-left"><strong>Mapa</strong> · preparando</span>
    <span id="status-right">Snapshot 22/08/2026 · local e standalone</span>
  </footer>
</main>

<script id="graph-data" type="application/json">__GRAPH_DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('graph-data').textContent);
const canvas = document.getElementById('graph');
const ctx = canvas.getContext('2d', { alpha: false });
const wrap = canvas.parentElement;
const nodeById = new Map(DATA.nodes.map(n => [n.id, n]));
const edgeIndexesByNode = new Map(DATA.nodes.map(n => [n.id, []]));
DATA.edges.forEach((e, i) => { edgeIndexesByNode.get(e.source)?.push(i); edgeIndexesByNode.get(e.target)?.push(i); });

let mode = 'map';
let selected = null;
let hovered = null;
let visibleNodes = [];
let visibleEdges = [];
let visibleIds = new Set();
let view = { x: 0, y: 0, scale: .22 };
let dragging = false;
let moved = false;
let lastPointer = { x: 0, y: 0 };
let frameRequested = false;
let pulseStart = performance.now();

const modeNames = { map: 'Mapa', bridges: 'Pontes', full: 'Rede completa', neighborhood: 'Vizinhança' };

function resize() {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const rect = wrap.getBoundingClientRect();
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  canvas.style.width = rect.width + 'px';
  canvas.style.height = rect.height + 'px';
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  canvas._ratio = ratio;
  requestDraw();
}

function worldToScreen(n) {
  const rect = canvas.getBoundingClientRect();
  return { x: rect.width / 2 + view.x + n.x * view.scale, y: rect.height / 2 + view.y + n.y * view.scale };
}

function neighborSet(rootId, depth) {
  const found = new Set([rootId]);
  let frontier = new Set([rootId]);
  for (let hop = 0; hop < depth; hop++) {
    const next = new Set();
    frontier.forEach(id => {
      (edgeIndexesByNode.get(id) || []).forEach(index => {
        const edge = DATA.edges[index];
        const other = edge.source === id ? edge.target : edge.source;
        if (!found.has(other)) { found.add(other); next.add(other); }
      });
    });
    frontier = next;
  }
  return found;
}

function relationAllowed(edge) {
  if (edge.confidence === 'INFERRED' && !document.getElementById('show-inferred').checked) return false;
  if (edge.confidence !== 'INFERRED' && !document.getElementById('show-extracted').checked) return false;
  return true;
}

function computeVisible() {
  if (mode === 'map') {
    visibleIds = new Set(DATA.nodes.filter(n => n.business).map(n => n.id));
  } else if (mode === 'bridges') {
    visibleIds = new Set(DATA.nodes.filter(n => n.business).map(n => n.id));
    DATA.edges.filter(e => e.context === 'business_to_code').forEach(e => { visibleIds.add(e.source); visibleIds.add(e.target); });
  } else if (mode === 'neighborhood') {
    visibleIds = selected ? neighborSet(selected, 2) : new Set(DATA.nodes.filter(n => n.business).map(n => n.id));
  } else {
    visibleIds = new Set(DATA.nodes.map(n => n.id));
  }
  visibleNodes = DATA.nodes.filter(n => visibleIds.has(n.id));
  visibleEdges = DATA.edges.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target) && relationAllowed(e));
  document.getElementById('status-left').innerHTML = `<strong>${modeNames[mode]}</strong> · ${visibleNodes.length.toLocaleString('pt-BR')} nós · ${visibleEdges.length.toLocaleString('pt-BR')} relações`;
  requestDraw();
}

function setMode(nextMode, fit = true) {
  mode = nextMode;
  document.querySelectorAll('.mode').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mode === mode)));
  computeVisible();
  if (fit) fitVisible();
}

function fitVisible() {
  if (!visibleNodes.length) return;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  visibleNodes.forEach(n => { minX = Math.min(minX, n.x); minY = Math.min(minY, n.y); maxX = Math.max(maxX, n.x); maxY = Math.max(maxY, n.y); });
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(200, maxX - minX);
  const height = Math.max(200, maxY - minY);
  view.scale = Math.min(rect.width * .84 / width, rect.height * .84 / height);
  view.scale = Math.max(.025, Math.min(2.4, view.scale));
  view.x = -(minX + maxX) / 2 * view.scale;
  view.y = -(minY + maxY) / 2 * view.scale;
  requestDraw();
}

function focusNode(id, openNeighborhood = false) {
  const node = nodeById.get(id);
  if (!node) return;
  selected = id;
  if (!visibleIds.has(id)) setMode(node.business ? 'map' : 'full', false);
  if (openNeighborhood) setMode('neighborhood', false);
  const rect = canvas.getBoundingClientRect();
  view.scale = Math.max(view.scale, openNeighborhood ? .8 : .55);
  view.x = -node.x * view.scale;
  view.y = -node.y * view.scale;
  renderInspector(node);
  requestDraw(true);
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

function renderInspector(node) {
  const selection = document.getElementById('selection');
  selection.innerHTML = `
    <h2>Seleção</h2>
    <h3 class="selection-title">${esc(node.label)}</h3>
    <p class="selection-meta">${esc(node.type)}${node.state_label ? ' · ' + esc(node.state_label) : ''}<br>${esc(node.cluster_label || node.community_name)}</p>
    <div class="selection-color" style="background:${esc(node.color)}"></div>
    ${node.summary ? `<dl class="property"><dt>O que é</dt><dd>${esc(node.summary)}</dd></dl>` : ''}
    ${node.evidence ? `<dl class="property"><dt>Evidência</dt><dd>${esc(node.evidence)}</dd></dl>` : ''}
    <dl class="property"><dt>Origem</dt><dd>${esc(node.source || 'Origem não registrada')}${node.source_location ? ' · ' + esc(node.source_location) : ''}</dd></dl>
    <dl class="property"><dt>Conectividade</dt><dd><strong>${node.degree}</strong> relações no grafo integral</dd></dl>
    <div class="inspector-actions">
      <button class="action" type="button" data-action="focus1">Focar 1 salto</button>
      <button class="action" type="button" data-action="focus2">Focar 2 saltos</button>
    </div>`;
  selection.querySelector('[data-action="focus1"]').addEventListener('click', () => showNeighborhood(node.id, 1));
  selection.querySelector('[data-action="focus2"]').addEventListener('click', () => showNeighborhood(node.id, 2));

  const connections = (edgeIndexesByNode.get(node.id) || []).map(index => {
    const edge = DATA.edges[index];
    const otherId = edge.source === node.id ? edge.target : edge.source;
    return { edge, other: nodeById.get(otherId) };
  }).filter(item => item.other).sort((a, b) => (b.other.business - a.other.business) || (b.other.degree - a.other.degree)).slice(0, 80);
  document.getElementById('connections').innerHTML = connections.length ? connections.map(({edge, other}) => `
    <button class="connection" type="button" data-node="${esc(other.id)}">
      <span class="dot" style="background:${esc(other.color)}"></span>
      <span><b>${esc(other.label)}</b><small>${esc(edge.relation)} · ${esc(edge.confidence)}</small></span>
    </button>`).join('') : '<p class="empty">Este nó não possui relações registradas.</p>';
  document.querySelectorAll('.connection').forEach(button => button.addEventListener('click', () => focusNode(button.dataset.node)));
}

function showNeighborhood(id, depth) {
  selected = id;
  mode = 'neighborhood';
  document.querySelectorAll('.mode').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mode === mode)));
  visibleIds = neighborSet(id, depth);
  visibleNodes = DATA.nodes.filter(n => visibleIds.has(n.id));
  visibleEdges = DATA.edges.filter(e => visibleIds.has(e.source) && visibleIds.has(e.target) && relationAllowed(e));
  document.getElementById('status-left').innerHTML = `<strong>Vizinhança</strong> · ${depth} salto${depth > 1 ? 's' : ''} · ${visibleNodes.length.toLocaleString('pt-BR')} nós · ${visibleEdges.length.toLocaleString('pt-BR')} relações`;
  fitVisible();
}

function draw(forcePulse = false) {
  frameRequested = false;
  const rect = canvas.getBoundingClientRect();
  ctx.save();
  ctx.fillStyle = '#11131c';
  ctx.fillRect(0, 0, rect.width, rect.height);
  ctx.translate(rect.width / 2 + view.x, rect.height / 2 + view.y);
  ctx.scale(view.scale, view.scale);

  const selectedNeighbors = selected ? neighborSet(selected, 1) : new Set();
  ctx.lineCap = 'round';
  visibleEdges.forEach(edge => {
    const source = nodeById.get(edge.source), target = nodeById.get(edge.target);
    if (!source || !target) return;
    const active = selected && (edge.source === selected || edge.target === selected);
    const bridge = edge.context === 'business_to_code';
    ctx.beginPath(); ctx.moveTo(source.x, source.y); ctx.lineTo(target.x, target.y);
    ctx.strokeStyle = active ? 'rgba(219,247,255,.88)' : bridge ? 'rgba(255,138,76,.46)' : edge.confidence === 'INFERRED' ? 'rgba(154,123,255,.16)' : 'rgba(126,150,181,.13)';
    ctx.lineWidth = (active ? 2.5 : bridge ? 1.4 : .65) / Math.max(view.scale, .18);
    if (edge.confidence === 'INFERRED') ctx.setLineDash([4 / view.scale, 5 / view.scale]); else ctx.setLineDash([]);
    ctx.stroke();
  });
  ctx.setLineDash([]);

  const labelsEnabled = document.getElementById('show-labels').checked;
  const labelCandidates = [];
  visibleNodes.forEach(node => {
    const dimmed = selected && !selectedNeighbors.has(node.id);
    const isSelected = node.id === selected;
    const isHovered = node.id === hovered;
    const radius = node.r / Math.max(Math.sqrt(view.scale), .52);
    ctx.beginPath(); ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = dimmed ? node.color + '36' : node.color + (node.business ? 'E8' : 'B8');
    ctx.fill();
    if (isSelected || isHovered) {
      ctx.strokeStyle = isSelected ? '#E8FAFF' : '#A9DDEE';
      ctx.lineWidth = 2.2 / view.scale; ctx.stroke();
    }
    if (isSelected) {
      const pulse = 1 + Math.sin((performance.now() - pulseStart) / 260) * .12;
      ctx.beginPath(); ctx.arc(node.x, node.y, radius * (1.8 + pulse), 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(0,212,255,.35)'; ctx.lineWidth = 1.5 / view.scale; ctx.stroke();
    }
    if (labelsEnabled && (isSelected || isHovered || (node.business && ((view.scale > .58 && node.degree > 2) || node.degree > 18)) || (view.scale > .9 && node.degree > 14))) labelCandidates.push(node);
  });

  labelCandidates.slice(0, 90).forEach(node => {
    const fontSize = (node.id === selected ? 13 : node.business ? 10.5 : 9) / view.scale;
    ctx.font = `${node.id === selected ? 650 : 520} ${fontSize}px Inter, system-ui, sans-serif`;
    ctx.fillStyle = node.id === selected ? '#EEF9FC' : node.business ? '#D8E5EA' : '#AAB7C4';
    ctx.fillText(node.label.length > 58 ? node.label.slice(0, 56) + '…' : node.label, node.x + (node.r + 5) / view.scale, node.y - 3 / view.scale);
  });
  ctx.restore();
  if (selected && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) requestAnimationFrame(() => requestDraw());
}

function requestDraw() { if (!frameRequested) { frameRequested = true; requestAnimationFrame(draw); } }

function nearestNode(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const x = (clientX - rect.left - rect.width / 2 - view.x) / view.scale;
  const y = (clientY - rect.top - rect.height / 2 - view.y) / view.scale;
  let best = null, bestDistance = Infinity;
  const maxDistance = 15 / Math.max(view.scale, .08);
  visibleNodes.forEach(node => {
    const distance = Math.hypot(node.x - x, node.y - y);
    if (distance < bestDistance && distance < maxDistance) { best = node; bestDistance = distance; }
  });
  return best;
}

canvas.addEventListener('pointerdown', event => { dragging = true; moved = false; lastPointer = { x: event.clientX, y: event.clientY }; canvas.setPointerCapture(event.pointerId); canvas.classList.add('dragging'); });
canvas.addEventListener('pointermove', event => {
  if (dragging) {
    const dx = event.clientX - lastPointer.x, dy = event.clientY - lastPointer.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
    view.x += dx; view.y += dy; lastPointer = { x: event.clientX, y: event.clientY }; requestDraw();
  } else {
    const node = nearestNode(event.clientX, event.clientY);
    const next = node?.id || null;
    if (next !== hovered) { hovered = next; canvas.style.cursor = hovered ? 'pointer' : 'grab'; requestDraw(); }
  }
});
canvas.addEventListener('pointerup', event => {
  dragging = false; canvas.classList.remove('dragging');
  if (!moved) { const node = nearestNode(event.clientX, event.clientY); if (node) focusNode(node.id); }
});
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = event.clientX - rect.left - rect.width / 2 - view.x;
  const my = event.clientY - rect.top - rect.height / 2 - view.y;
  const old = view.scale;
  const factor = Math.exp(-event.deltaY * .0013);
  view.scale = Math.max(.018, Math.min(4.5, view.scale * factor));
  view.x -= mx * (view.scale / old - 1);
  view.y -= my * (view.scale / old - 1);
  requestDraw();
}, { passive: false });

const searchInput = document.getElementById('search-input');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {
  const query = searchInput.value.trim().toLocaleLowerCase('pt-BR');
  if (!query) { searchResults.classList.remove('open'); searchResults.innerHTML = ''; return; }
  const matches = DATA.nodes.filter(n => n.label.toLocaleLowerCase('pt-BR').includes(query) || n.source.toLocaleLowerCase('pt-BR').includes(query))
    .sort((a, b) => (b.business - a.business) || (b.degree - a.degree)).slice(0, 18);
  searchResults.innerHTML = matches.length ? matches.map(n => `
    <button class="result" type="button" role="option" data-node="${esc(n.id)}">
      <span class="result-dot" style="background:${esc(n.color)}"></span>
      <span class="result-main"><b>${esc(n.label)}</b><small>${esc(n.cluster_label || n.community_name)}</small></span>
      <span class="result-type">${esc(n.type)}</span>
    </button>`).join('') : '<p class="empty" style="padding:14px">Nenhum nó encontrado.</p>';
  searchResults.classList.add('open');
  searchResults.querySelectorAll('.result').forEach(button => button.addEventListener('click', () => {
    focusNode(button.dataset.node); searchResults.classList.remove('open'); searchInput.blur();
  }));
});
searchInput.addEventListener('keydown', event => {
  if (event.key === 'Escape') { searchInput.value = ''; searchResults.classList.remove('open'); searchInput.blur(); }
  if (event.key === 'Enter') searchResults.querySelector('.result')?.click();
});
document.addEventListener('click', event => { if (!event.target.closest('.search')) searchResults.classList.remove('open'); });

document.querySelectorAll('.mode').forEach(button => button.addEventListener('click', () => setMode(button.dataset.mode)));
['show-extracted','show-inferred','show-labels'].forEach(id => document.getElementById(id).addEventListener('change', () => { computeVisible(); }));
document.getElementById('fit-button').addEventListener('click', fitVisible);
document.getElementById('export-button').addEventListener('click', () => {
  requestDraw();
  const link = document.createElement('a'); link.download = `volc-os-${mode}.png`; link.href = canvas.toDataURL('image/png'); link.click();
});
document.addEventListener('keydown', event => {
  if (event.target.matches('input')) return;
  if (event.key === '/') { event.preventDefault(); searchInput.focus(); }
  if (['1','2','3','4'].includes(event.key)) setMode(['map','bridges','full','neighborhood'][Number(event.key)-1]);
  if (event.key.toLowerCase() === 'f') fitVisible();
  if (event.key === 'Escape') { selected = null; hovered = null; setMode('map'); document.getElementById('selection').innerHTML = '<h2>Seleção</h2><p class="empty">Selecione um nó ou use a busca.</p>'; document.getElementById('connections').innerHTML = '<p class="empty">Nenhum nó selecionado.</p>'; }
});

new ResizeObserver(resize).observe(wrap);
computeVisible();
setTimeout(fitVisible, 20);
</script>
</body>
</html>'''


def main() -> None:
    data = json.loads(GRAPH.read_text(encoding="utf-8"))
    prepared = prepare_graph(data)
    payload = json.dumps(prepared, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(HTML.replace("__GRAPH_DATA__", payload), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), **prepared["meta"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
