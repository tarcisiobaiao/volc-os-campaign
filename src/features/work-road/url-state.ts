import type { RoadmapTaskStatus } from "./live";
import { ROADMAP_TASK_STATUSES } from "./live";

export type QgView = "agora" | "timeline" | "kanban" | "lista" | "grafo" | "execucoes" | "inbox";

export const QG_VIEWS: QgView[] = ["agora", "timeline", "kanban", "lista", "grafo", "execucoes", "inbox"];

const VIEW_ALIASES: Record<string, QgView> = {
  roadmap: "timeline",
  tarefas: "lista",
};

export type QgSort = "fonte" | "id" | "titulo" | "estado";
export type QgExecucaoFilter = "all" | "ativa" | "orfa";

export interface QgUrlState {
  visao: QgView;
  busca: string;
  status: RoadmapTaskStatus | "all";
  iniciativa: string;
  onda: string;
  tarefa: string;
  owner: string;
  execucao: QgExecucaoFilter;
  ordem: QgSort;
  grafoModo: "aberto" | "dependencias" | "caminho";
}

const VALID_VIEWS = new Set<string>(QG_VIEWS);
const VALID_STATUS = new Set<string>(["all", ...ROADMAP_TASK_STATUSES]);
const VALID_SORT = new Set<string>(["fonte", "id", "titulo", "estado"]);
const VALID_EXEC = new Set<string>(["all", "ativa", "orfa"]);
const VALID_GRAFO = new Set<string>(["aberto", "dependencias", "caminho"]);

export function parseQgSearch(params: URLSearchParams): QgUrlState {
  const visaoRaw = params.get("visao") ?? "agora";
  const aliased = VIEW_ALIASES[visaoRaw] ?? visaoRaw;
  const statusRaw = params.get("status") ?? "all";
  const ordemRaw = params.get("ordem") ?? "fonte";
  const execRaw = params.get("execucao") ?? "all";
  const grafoRaw = params.get("grafo") ?? "aberto";
  return {
    visao: VALID_VIEWS.has(aliased) ? (aliased as QgView) : "agora",
    busca: params.get("busca") ?? "",
    status: VALID_STATUS.has(statusRaw) ? (statusRaw as RoadmapTaskStatus | "all") : "all",
    iniciativa: params.get("iniciativa") ?? "",
    onda: params.get("onda") ?? "",
    tarefa: params.get("tarefa") ?? "",
    owner: params.get("owner") ?? "",
    execucao: VALID_EXEC.has(execRaw) ? (execRaw as QgExecucaoFilter) : "all",
    ordem: VALID_SORT.has(ordemRaw) ? (ordemRaw as QgSort) : "fonte",
    grafoModo: VALID_GRAFO.has(grafoRaw) ? (grafoRaw as QgUrlState["grafoModo"]) : "aberto",
  };
}

export function writeQgSearch(
  current: URLSearchParams,
  patch: Partial<QgUrlState>,
): URLSearchParams {
  const next = new URLSearchParams(current);
  const merged: QgUrlState = { ...parseQgSearch(current), ...patch };

  setOrDelete(next, "visao", merged.visao === "agora" ? "" : merged.visao);
  setOrDelete(next, "busca", merged.busca.trim());
  setOrDelete(next, "status", merged.status === "all" ? "" : merged.status);
  setOrDelete(next, "iniciativa", merged.iniciativa);
  setOrDelete(next, "onda", merged.onda);
  setOrDelete(next, "tarefa", merged.tarefa);
  setOrDelete(next, "owner", merged.owner);
  setOrDelete(next, "execucao", merged.execucao === "all" ? "" : merged.execucao);
  setOrDelete(next, "ordem", merged.ordem === "fonte" ? "" : merged.ordem);
  setOrDelete(next, "grafo", merged.grafoModo === "aberto" ? "" : merged.grafoModo);
  return next;
}

function setOrDelete(params: URLSearchParams, key: string, value: string) {
  if (!value) params.delete(key);
  else params.set(key, value);
}

export function taskPath(taskId: string): string {
  return `/settings/qg-agentico/tarefas/${encodeURIComponent(taskId)}`;
}
