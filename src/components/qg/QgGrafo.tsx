import * as React from "react";
import { useNavigate } from "react-router-dom";
import type { GraphStatusLive, WorkRoadExecution } from "@/features/work-road/live";
import type { FlatTask } from "@/features/work-road/selectors";
import { operationalGraph, pathToDone } from "@/features/work-road/graph-model";
import { taskPath } from "@/features/work-road/url-state";
import { QgMissingField, QgStaleBanner } from "./QgStates";

export function QgGrafo({
  rows,
  executions,
  graphStatus,
  modo,
  onModo,
  busca,
  onBusca,
  onRetry,
}: {
  rows: FlatTask[];
  executions: WorkRoadExecution[];
  graphStatus: GraphStatusLive | null;
  modo: "aberto" | "dependencias" | "caminho";
  onModo: (modo: "aberto" | "dependencias" | "caminho") => void;
  busca: string;
  onBusca?: (busca: string) => void;
  onRetry?: () => void;
}) {
  const navigate = useNavigate();
  const [zoom, setZoom] = React.useState(1);
  const query = busca.trim().toLocaleLowerCase("pt-BR");
  const focus = rows.find((row) => {
    if (!query) return false;
    return row.task.id.toLocaleLowerCase("pt-BR").includes(query)
      || row.task.title.toLocaleLowerCase("pt-BR").includes(query);
  });
  const graph = operationalGraph(rows, executions, {
    openOnly: true,
    depsOnly: modo === "dependencias",
    focusId: modo === "caminho" ? focus?.task.id : undefined,
  });
  const width = 960;
  const layout = layoutGraph(graph);
  const pathIds = focus ? pathToDone(rows, focus.task.id) : [];

  return (
    <section aria-labelledby="qg-graph-heading">
      <h2 id="qg-graph-heading" className="font-display text-2xl font-semibold tracking-tight">
        Grafo operacional
      </h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
        Subgrafo de iniciativas, tarefas, dependências declaradas, nós do grafo e execuções vinculadas.
        Centralidade não é prioridade. Aresta sem tipo não existe. Este grafo técnico não é a verdade operacional atual quando está defasado.
      </p>
      {graphStatus?.stale || graphStatus?.available === false ? (
        <QgStaleBanner
          message={`${graphStatus.reason || "Grafo técnico defasado."} HEAD ${graphStatus.head_short || "ausente"} · geração ${graphStatus.generated_at || "ausente"}. Autoridade humana: ${graphStatus.authority}`}
          onRetry={onRetry ?? (() => undefined)}
        />
      ) : null}

      <div className="mt-4 flex flex-wrap items-end gap-2">
        {onBusca ? (
          <label className="block min-w-[16rem] text-xs font-medium text-muted-foreground" htmlFor="qg-graph-search">
            Buscar no grafo
            <input
              id="qg-graph-search"
              value={busca}
              onChange={(event) => onBusca(event.target.value)}
              className="mt-1 block h-10 min-h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
        ) : null}
        {([
          ["aberto", "Tarefas abertas"],
          ["dependencias", "Somente dependências"],
          ["caminho", "Caminho até concluir"],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            aria-pressed={modo === id}
            onClick={() => onModo(id)}
            className="inline-flex min-h-10 items-center rounded-md border border-input px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {label}
          </button>
        ))}
        <button type="button" className="inline-flex min-h-10 items-center px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => setZoom((value) => Math.min(2, value + 0.1))}>Zoom +</button>
        <button type="button" className="inline-flex min-h-10 items-center px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => setZoom((value) => Math.max(0.6, value - 0.1))}>Zoom −</button>
        <button type="button" className="inline-flex min-h-10 items-center px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => setZoom(1)}>Centralizar</button>
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        Legenda: belongs = iniciativa, depends = dependência declarada, graph = relação com nó técnico, executes = execução vinculada.
      </p>
      {modo === "caminho" && pathIds.length > 0 ? (
        <p className="mt-2 text-sm">Caminho declarado até {focus?.task.id}: {pathIds.join(" → ")}</p>
      ) : null}

      {graph.nodes.length === 0 ? (
        <QgMissingField>Não há relações operacionais visíveis neste recorte.</QgMissingField>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <svg
            role="img"
            aria-label="Grafo operacional de tarefas"
            viewBox={`0 0 ${width} ${layout.height}`}
            width={width * zoom}
            height={layout.height * zoom}
            className="max-w-none text-foreground"
          >
            {graph.edges.map((edge, index) => {
              const from = layout.positions.get(edge.from);
              const to = layout.positions.get(edge.to);
              if (!from || !to) return null;
              const dash = edge.kind === "depends" ? undefined : "4 4";
              return (
                <line
                  key={`${edge.from}-${edge.to}-${index}`}
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke="currentColor"
                  strokeOpacity={0.45}
                  strokeDasharray={dash}
                >
                  <title>{edge.kind}</title>
                </line>
              );
            })}
            {graph.nodes.map((node) => {
              const point = layout.positions.get(node.id);
              if (!point) return null;
              const clickable = node.kind === "task" && node.taskId;
              return (
                <g key={node.id} transform={`translate(${point.x}, ${point.y})`}>
                  {clickable ? (
                    <a
                      href={taskPath(node.taskId!)}
                      data-testid={`qg-graph-node-${node.taskId}`}
                      onClick={(event) => {
                        event.preventDefault();
                        navigate(taskPath(node.taskId!));
                      }}
                    >
                      <circle r={8} fill="currentColor" />
                      <text x={14} y={4} fontSize={11}>{node.label}</text>
                    </a>
                  ) : (
                    <>
                      <circle r={5} fill="currentColor" opacity={0.7} />
                      <text x={12} y={4} fontSize={11}>{node.label}</text>
                    </>
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </section>
  );
}

function layoutGraph(graph: ReturnType<typeof operationalGraph>) {
  const positions = new Map<string, { x: number; y: number }>();
  const initiatives = graph.nodes.filter((node) => node.kind === "initiative");
  const extras = graph.nodes.filter((node) => node.kind === "graph" || node.kind === "execution");
  const children = new Map<string, string[]>();
  for (const edge of graph.edges) {
    if (edge.kind !== "belongs") continue;
    const list = children.get(edge.from) ?? [];
    list.push(edge.to);
    children.set(edge.from, list);
  }
  let y = 40;
  const placed = new Set<string>();
  for (const initiative of initiatives) {
    positions.set(initiative.id, { x: 72, y });
    const childIds = children.get(initiative.id) ?? [];
    childIds.forEach((id, index) => {
      positions.set(id, { x: 300, y: y + index * 28 });
      placed.add(id);
    });
    y += Math.max(36, childIds.length * 28) + 20;
  }
  for (const node of graph.nodes) {
    if (node.kind === "task" && !positions.has(node.id)) {
      positions.set(node.id, { x: 300, y });
      y += 28;
    }
  }
  extras.forEach((node, index) => {
    positions.set(node.id, { x: 680, y: 40 + index * 32 });
  });
  return { positions, height: Math.max(420, y + 48, 48 + extras.length * 32) };
}
