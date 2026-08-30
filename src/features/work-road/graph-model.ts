import type { WorkRoadExecution } from "./live";
import type { FlatTask } from "./selectors";
import { declaredDependencies, isOpenStatus } from "./selectors";

export type OpNodeKind = "initiative" | "task" | "graph" | "execution";
export type OpEdgeKind = "belongs" | "depends" | "graph" | "executes";

export interface OpNode {
  id: string;
  kind: OpNodeKind;
  label: string;
  status?: string;
  taskId?: string;
}

export interface OpEdge {
  from: string;
  to: string;
  kind: OpEdgeKind;
}

export function operationalGraph(
  rows: FlatTask[],
  executions: WorkRoadExecution[],
  options: { openOnly?: boolean; depsOnly?: boolean; focusId?: string } = {},
): { nodes: OpNode[]; edges: OpEdge[] } {
  const visible = options.openOnly === false ? rows : rows.filter((row) => isOpenStatus(row.task.status));
  const nodes = new Map<string, OpNode>();
  const edges: OpEdge[] = [];
  const add = (node: OpNode) => { if (!nodes.has(node.id)) nodes.set(node.id, node); };

  for (const row of visible) {
    add({
      id: `ini:${row.initiative.id}`,
      kind: "initiative",
      label: `${row.initiative.id} · ${row.initiative.title}`,
    });
    add({
      id: `task:${row.task.id}`,
      kind: "task",
      label: `${row.task.id} · ${row.task.title}`,
      status: row.task.status,
      taskId: row.task.id,
    });
    if (!options.depsOnly) {
      edges.push({ from: `ini:${row.initiative.id}`, to: `task:${row.task.id}`, kind: "belongs" });
    }
    for (const dep of declaredDependencies(row.task) ?? []) {
      add({ id: `task:${dep}`, kind: "task", label: dep, taskId: dep });
      edges.push({ from: `task:${dep}`, to: `task:${row.task.id}`, kind: "depends" });
    }
    if (!options.depsOnly) {
      for (const nodeId of row.task.graph_nodes ?? []) {
        add({ id: `graph:${nodeId}`, kind: "graph", label: nodeId });
        edges.push({ from: `task:${row.task.id}`, to: `graph:${nodeId}`, kind: "graph" });
      }
    }
  }

  if (!options.depsOnly) {
    for (const execution of executions) {
      const linked = execution.task_ids ?? [];
      if (linked.length === 0) continue;
      add({ id: `exec:${execution.id}`, kind: "execution", label: execution.mission || execution.name });
      for (const taskId of linked) {
        if (!nodes.has(`task:${taskId}`)) continue;
        edges.push({ from: `exec:${execution.id}`, to: `task:${taskId}`, kind: "executes" });
      }
    }
  }

  if (options.focusId) {
    const focus = `task:${options.focusId}`;
    const keep = new Set<string>([focus]);
    for (const edge of edges) {
      if (edge.from === focus || edge.to === focus) {
        keep.add(edge.from);
        keep.add(edge.to);
      }
    }
    return {
      nodes: [...nodes.values()].filter((node) => keep.has(node.id)),
      edges: edges.filter((edge) => keep.has(edge.from) && keep.has(edge.to)),
    };
  }

  return { nodes: [...nodes.values()], edges };
}

export function pathToDone(rows: FlatTask[], taskId: string): string[] {
  const byId = new Map(rows.map((row) => [row.task.id, row]));
  const start = byId.get(taskId);
  if (!start) return [];
  const seen = new Set<string>();
  const stack = [start];
  while (stack.length) {
    const current = stack.pop()!;
    if (seen.has(current.task.id)) continue;
    seen.add(current.task.id);
    for (const dep of declaredDependencies(current.task) ?? []) {
      const found = byId.get(dep);
      if (found) stack.push(found);
    }
  }
  return [...seen];
}
