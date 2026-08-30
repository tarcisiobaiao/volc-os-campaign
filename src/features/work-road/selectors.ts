import type {
  RoadmapInitiative,
  RoadmapTask,
  RoadmapTaskStatus,
  WorkRoadExecution,
  WorkRoadLive,
  WorkRoadSummary,
} from "./live";
import { ROADMAP_TASK_STATUSES } from "./live";

export interface FlatTask {
  task: RoadmapTask;
  initiative: RoadmapInitiative;
  indexInInitiative: number;
}

export function emptyStatusCounts(): Record<RoadmapTaskStatus, number> {
  return { done: 0, partial: 0, risk: 0, todo: 0, reserved: 0 };
}

export function countByStatus(tasks: RoadmapTask[]): Record<RoadmapTaskStatus, number> {
  const counts = emptyStatusCounts();
  for (const task of tasks) {
    if (task.status in counts) counts[task.status] += 1;
  }
  return counts;
}

/**
 * Progresso pelo contrato oficial de pesos. Tarefas `reserved` (peso null)
 * ficam de fora. Se não houver tarefas aceitas, o percentual é ausência, não zero.
 */
export function progressFromWeights(
  tasks: RoadmapTask[],
  weights: Record<RoadmapTaskStatus, number | null> | null | undefined,
): { percent: number | null; accepted: number; weighted: number } {
  if (!weights) return { percent: null, accepted: 0, weighted: 0 };
  const accepted = tasks.filter((task) => weights[task.status] != null);
  if (accepted.length === 0) return { percent: null, accepted: 0, weighted: 0 };
  const weighted = accepted.reduce((sum, task) => sum + Number(weights[task.status]), 0);
  const percent = Math.round((weighted / accepted.length) * 1000) / 10;
  return {
    percent,
    accepted: accepted.length,
    weighted,
  };
}

export function initiativeProgress(
  initiative: RoadmapInitiative,
  weights: Record<RoadmapTaskStatus, number | null> | null | undefined,
) {
  return {
    ...progressFromWeights(initiative.tasks, weights),
    counts: countByStatus(initiative.tasks),
  };
}

export function flattenTasks(road: WorkRoadLive | null | undefined): FlatTask[] {
  if (!road?.initiatives) return [];
  return road.initiatives.flatMap((initiative) =>
    (initiative.tasks ?? []).map((task, indexInInitiative) => ({
      task,
      initiative,
      indexInInitiative,
    })),
  );
}

export function sourceOrder(row: FlatTask): number {
  return row.task.order ?? row.indexInInitiative;
}

export function sortBySourceRank(rows: FlatTask[]): FlatTask[] {
  return [...rows].sort((a, b) => {
    const priorityA = a.task.priority ?? Number.POSITIVE_INFINITY;
    const priorityB = b.task.priority ?? Number.POSITIVE_INFINITY;
    if (priorityA !== priorityB) return priorityA - priorityB;
    if (a.initiative.rank !== b.initiative.rank) return a.initiative.rank - b.initiative.rank;
    if (sourceOrder(a) !== sourceOrder(b)) return sourceOrder(a) - sourceOrder(b);
    return a.indexInInitiative - b.indexInInitiative;
  });
}

export type TaskSort = "fonte" | "id" | "titulo" | "estado";

export function sortTasks(rows: FlatTask[], ordem: TaskSort = "fonte"): FlatTask[] {
  if (ordem === "fonte") return sortBySourceRank(rows);
  const copy = [...rows];
  if (ordem === "id") {
    copy.sort((a, b) => a.task.id.localeCompare(b.task.id, "pt-BR"));
  } else if (ordem === "titulo") {
    copy.sort((a, b) => a.task.title.localeCompare(b.task.title, "pt-BR"));
  } else if (ordem === "estado") {
    copy.sort((a, b) => a.task.status.localeCompare(b.task.status, "pt-BR") || a.task.id.localeCompare(b.task.id, "pt-BR"));
  }
  return copy;
}

export interface TaskFilters {
  busca: string;
  status: RoadmapTaskStatus | "all";
  iniciativa: string;
  onda: string;
  owner?: string;
}

export function filterTasks(rows: FlatTask[], filters: TaskFilters): FlatTask[] {
  const query = filters.busca.trim().toLocaleLowerCase("pt-BR");
  const owner = (filters.owner ?? "").trim().toLocaleLowerCase("pt-BR");
  return rows.filter(({ task, initiative }) => {
    if (filters.status !== "all" && task.status !== filters.status) return false;
    if (filters.iniciativa && initiative.id !== filters.iniciativa) return false;
    if (filters.onda && initiative.wave !== filters.onda) return false;
    if (owner && (task.owner ?? "").toLocaleLowerCase("pt-BR") !== owner) return false;
    if (!query) return true;
    const haystack = [
      task.id,
      task.title,
      task.proof,
      task.explanation,
      task.owner,
      initiative.id,
      initiative.title,
    ]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase("pt-BR");
    return haystack.includes(query);
  });
}

export function listedTextCount(visible: number, total: number | null | undefined): string | null {
  if (total == null) return null;
  return `${visible} de ${total}`;
}

export function isOpenStatus(status: RoadmapTaskStatus): boolean {
  return status !== "done" && status !== "reserved";
}

/** Ordem editorial da iniciativa. Nunca prova bloqueio operacional. */
export function editorialPredecessors(row: FlatTask): RoadmapTask[] {
  return row.initiative.tasks.slice(0, row.indexInInitiative);
}

export function declaredDependencies(task: RoadmapTask): string[] | null {
  const values = task.dependencies ?? task.depends_on;
  if (!values) return null;
  const ids = values.map((item) => item.trim()).filter(Boolean);
  return ids.length > 0 ? ids : null;
}

export function openDeclaredDependencies(row: FlatTask, catalog: FlatTask[]): FlatTask[] {
  const ids = declaredDependencies(row.task);
  if (!ids) return [];
  const byId = new Map(catalog.map((item) => [item.task.id, item]));
  return ids.flatMap((id) => {
    const found = byId.get(id);
    if (!found || !isOpenStatus(found.task.status)) return [];
    return [found];
  });
}

export function isBlockedByDeclaredDependency(row: FlatTask, catalog: FlatTask[]): boolean {
  return openDeclaredDependencies(row, catalog).length > 0;
}

export function evidenceText(task: RoadmapTask): string | null {
  const proof = task.proof?.trim() ?? "";
  return proof ? proof : null;
}

export type TaskKind = "produto" | "parcial" | "risco" | "a_fazer" | "reservada";

export function classifyTaskKind(status: RoadmapTaskStatus): TaskKind {
  if (status === "done") return "produto";
  if (status === "partial") return "parcial";
  if (status === "risk") return "risco";
  if (status === "reserved") return "reservada";
  return "a_fazer";
}

export function kindLabel(kind: TaskKind): string {
  switch (kind) {
    case "produto":
      return "Produto comprovado";
    case "parcial":
      return "Parcial";
    case "risco":
      return "Existe com risco";
    case "reservada":
      return "Capacidade reservada";
    default:
      return "A fazer";
  }
}

export type PriorityAuthority = "prioridade explícita" | "ordem editorial" | "dependência declarada" | "risco" | "execução ativa";

function priorityReason(row: FlatTask, lead: string, authority: PriorityAuthority): { next: FlatTask; reason: string; authority: PriorityAuthority } {
  const base = row.task.priority != null
    ? `${lead} Autoridade: prioridade explícita ${row.task.priority} na fonte (${row.initiative.id}).`
    : `${lead} Autoridade: ${authority} da fonte (${row.initiative.id}, rank ${row.initiative.rank}). Ordem editorial não prova dependência; não em dependência comprovada.`;
  return { next: row, reason: base, authority: row.task.priority != null ? "prioridade explícita" : authority };
}

export function recommendNext(rows: FlatTask[]): { next: FlatTask | null; reason: string; authority: PriorityAuthority | null } {
  const ranked = sortBySourceRank(rows);
  const open = ranked.filter((row) => isOpenStatus(row.task.status));
  if (open.length === 0) {
    return { next: null, reason: "A fonte não aponta tarefa aberta.", authority: null };
  }
  const actionable = open.filter((row) => row.task.status !== "risk");
  const next = actionable[0] ?? open[0];
  if (next.task.status === "risk") {
    return priorityReason(next, "Única frente aberta de maior rank ainda carrega risco.", "risco");
  }
  if (isBlockedByDeclaredDependency(next, rows)) {
    return priorityReason(next, "Há dependência declarada ainda aberta nesta frente.", "dependência declarada");
  }
  if (next.task.status === "partial") {
    return priorityReason(next, "Parcial na iniciativa de maior prioridade ainda aberta.", "ordem editorial");
  }
  return priorityReason(next, "Próxima tarefa aberta na ordem editorial da fonte.", "ordem editorial");
}

export type AgoraQueueRole = "risco" | "bloqueio" | "parcial" | "prioridade";

export interface AgoraQueues {
  next: FlatTask | null;
  reason: string;
  authority: PriorityAuthority | null;
  risks: FlatTask[];
  blocked: FlatTask[];
  partials: FlatTask[];
  ranked: FlatTask[];
  upcoming: FlatTask[];
}

/**
 * Filas da visão Agora. Cada task.id entra no máximo uma vez nas filas
 * secundárias. A tarefa dominante do topo sai dessas filas.
 */
export function agoraQueues(rows: FlatTask[]): AgoraQueues {
  const { next, reason, authority } = recommendNext(rows);
  const seen = new Set<string>();
  if (next) seen.add(next.task.id);

  const take = (candidates: FlatTask[]) => {
    const picked: FlatTask[] = [];
    for (const row of candidates) {
      if (seen.has(row.task.id)) continue;
      seen.add(row.task.id);
      picked.push(row);
    }
    return picked;
  };

  const rankedAll = sortBySourceRank(rows);
  const risks = take(rankedAll.filter((row) => row.task.status === "risk")).slice(0, 3);
  const blocked = take(rankedAll.filter((row) => isBlockedByDeclaredDependency(row, rows))).slice(0, 3);
  const partials = take(rankedAll.filter((row) => row.task.status === "partial")).slice(0, 3);
  const upcoming = take(rankedAll.filter((row) => isOpenStatus(row.task.status))).slice(0, 5);
  const ranked = upcoming;

  return { next, reason, authority, risks, blocked, partials, ranked, upcoming };
}

export function reasonForNow(row: FlatTask, role: AgoraQueueRole): string {
  if (role === "risco") {
    return `A fonte marca ${row.task.id} como risco. Não é alerta decorativo: o estado veio do Roadmap Vivo.`;
  }
  if (role === "bloqueio") {
    return `A fonte declara dependência ainda aberta para ${row.task.id}. Ordem editorial sozinha não prova este bloqueio.`;
  }
  if (role === "parcial") {
    return `Parcial na iniciativa ${row.initiative.id}. Já existe trabalho; falta o aceite de pronto.`;
  }
  return `Prioridade editorial ${row.initiative.rank} na onda ${row.initiative.wave}.`;
}

export function wavesFrom(road: WorkRoadLive): string[] {
  const seen: string[] = [];
  for (const initiative of road.initiatives) {
    if (!seen.includes(initiative.wave)) seen.push(initiative.wave);
  }
  return seen;
}

export function summaryOrAbsent(road: WorkRoadLive | null | undefined): WorkRoadSummary | null {
  if (!road?.summary) return null;
  const { initiatives, tasks, accepted_tasks, progress_percent, counts } = road.summary;
  if (
    initiatives == null
    || tasks == null
    || accepted_tasks == null
    || progress_percent == null
    || !counts
  ) {
    return null;
  }
  return road.summary;
}

export function statusLabel(
  status: RoadmapTaskStatus,
  labels: Partial<Record<RoadmapTaskStatus, string>> | null | undefined,
): string {
  return labels?.[status] || fallbackStatusLabel(status);
}

export function fallbackStatusLabel(status: RoadmapTaskStatus): string {
  switch (status) {
    case "done":
      return "Concluída";
    case "partial":
      return "Parcial";
    case "risk":
      return "Com risco";
    case "todo":
      return "A fazer";
    case "reserved":
      return "Reservada";
  }
}

export type ExecutionKind = "ativo" | "ocioso" | "concluido" | "falho" | "desatualizado" | "heartbeat_atrasado";

export function classifyExecution(execution: WorkRoadExecution): {
  kind: ExecutionKind;
  why: string;
  missingHeartbeat: boolean;
} {
  const missingHeartbeat = !execution.heartbeat_at;
  if (execution.failed === true) {
    return {
      kind: "falho",
      why: "A fonte marcou esta execução como falha.",
      missingHeartbeat,
    };
  }
  if (execution.session_active === true && missingHeartbeat) {
    return {
      kind: "heartbeat_atrasado",
      why: "Há processo vivo, mas a fonte não enviou heartbeat. Ausência de heartbeat não é execução normal.",
      missingHeartbeat,
    };
  }
  if (execution.session_active === true) {
    return {
      kind: "ativo",
      why: "Há processo vivo e heartbeat na fonte. A existência do diretório sozinha não ativa este estado.",
      missingHeartbeat,
    };
  }
  if (execution.commits_ahead > 0 && execution.dirty_files === 0) {
    return {
      kind: "concluido",
      why: "Sessão sem processo vivo, árvore limpa e commits registrados desde a base.",
      missingHeartbeat,
    };
  }
  if (execution.dirty_files > 0) {
    return {
      kind: "ocioso",
      why: "A worktree tem arquivos em edição, mas não há processo vivo.",
      missingHeartbeat,
    };
  }
  return {
    kind: "desatualizado",
    why: "Há um diretório de worktree, porém sem processo vivo nem evidência recente de sessão.",
    missingHeartbeat,
  };
}

export function executionKindLabel(kind: ExecutionKind): string {
  switch (kind) {
    case "ativo":
      return "Ativa";
    case "ocioso":
      return "Ociosa";
    case "concluido":
      return "Concluída";
    case "falho":
      return "Falhou";
    case "desatualizado":
      return "Desatualizada";
    case "heartbeat_atrasado":
      return "Heartbeat atrasado";
  }
}

export function textList(value: string | string[] | null | undefined): string[] | null {
  if (value == null) return null;
  if (Array.isArray(value)) {
    const items = value.map((item) => item.trim()).filter(Boolean);
    return items.length > 0 ? items : null;
  }
  const trimmed = value.trim();
  return trimmed ? [trimmed] : null;
}

export function executionAgentLabel(execution: WorkRoadExecution): string {
  const named = execution.agent?.trim() || execution.provider?.trim();
  return named || "agente local não identificado";
}

export function checklistProgress(task: RoadmapTask): { done: number; total: number } | null {
  const items = task.checklist;
  if (!items || items.length === 0) return null;
  return {
    done: items.filter((item) => item.done === true).length,
    total: items.length,
  };
}

export function isOrphanExecution(execution: WorkRoadExecution): boolean {
  return !execution.task_ids || execution.task_ids.length === 0;
}

export function executionsForTask(taskId: string, executions: WorkRoadExecution[]): WorkRoadExecution[] {
  return executions.filter((item) => (item.task_ids ?? []).includes(taskId));
}

export const KANBAN_COLUMNS: Array<{ id: RoadmapTaskStatus; title: string }> = [
  { id: "todo", title: "A fazer" },
  { id: "partial", title: "Parcial / em desenvolvimento" },
  { id: "risk", title: "Com risco" },
  { id: "done", title: "Concluída e provada" },
  { id: "reserved", title: "Reservada" },
];

export function uniqueTaskIds(rows: FlatTask[]): string[] {
  return [...new Set(rows.map((row) => row.task.id))];
}

export { ROADMAP_TASK_STATUSES };
