export type RoadmapTaskStatus = "done" | "partial" | "risk" | "todo" | "reserved";

export const ROADMAP_TASK_STATUSES: RoadmapTaskStatus[] = [
  "done",
  "partial",
  "risk",
  "todo",
  "reserved",
];

export interface RoadmapChecklistItem {
  id: string;
  description: string;
  done?: boolean;
  proof?: string | null;
  acceptance?: string | null;
  owner?: string | null;
}

export interface RoadmapLink {
  kind: "path" | "doc" | "url" | "route" | "commit" | "graph" | "execution";
  label: string;
  value: string;
}

/**
 * Campos opcionais existem para o QG mostrar ausência com honestidade.
 * Se a fonte não envia o campo, a interface declara que não veio: nunca inventa.
 */
export interface RoadmapTask {
  id: string;
  title: string;
  status: RoadmapTaskStatus;
  proof: string;
  priority?: number | null;
  order?: number | null;
  owner?: string | null;
  explanation?: string | null;
  acceptance?: string | string[] | null;
  checklist?: RoadmapChecklistItem[] | null;
  dependencies?: string[] | null;
  depends_on?: string[] | null;
  links?: RoadmapLink[] | null;
  graph_nodes?: string[] | null;
  prompt_template?: string | null;
  mission_template?: string | null;
  updated_at?: string | null;
}

export interface RoadmapInitiative {
  id: string;
  rank: number;
  title: string;
  wave: string;
  why: string;
  done_when: string;
  graph_nodes: string[];
  tasks: RoadmapTask[];
  explanation?: string | null;
  dependencies?: string[] | null;
}

export interface WorkRoadSummary {
  initiatives: number;
  tasks: number;
  accepted_tasks: number;
  progress_percent: number;
  counts: Record<RoadmapTaskStatus, number>;
}

export interface WorkRoadLive {
  schema_version: number;
  updated_at: string;
  purpose: string;
  status_weights: Record<RoadmapTaskStatus, number | null>;
  status_labels: Record<RoadmapTaskStatus, string>;
  initiatives: RoadmapInitiative[];
  summary?: WorkRoadSummary | null;
  source: {
    path: string;
    sha256: string;
    read_at: string;
  };
}

export interface WorkRoadExecutionCommit {
  sha: string;
  subject: string;
  committed_at: string;
}

export interface WorkRoadRoadmapChange {
  task_id: string;
  title: string;
  before_status: RoadmapTaskStatus | null;
  after_status: RoadmapTaskStatus | null;
  proof_changed: boolean;
}

export interface WorkRoadExecution {
  id: string;
  name: string;
  branch: string;
  head: string;
  session_active: boolean;
  worktree_locked: boolean;
  dirty_files: number;
  commits_ahead: number;
  commits: WorkRoadExecutionCommit[];
  roadmap_changes: WorkRoadRoadmapChange[];
  task_ids?: string[] | null;
  worktree?: string | null;
  agent?: string | null;
  provider?: string | null;
  mission?: string | null;
  heartbeat_at?: string | null;
  failed?: boolean | null;
}

export interface WorkRoadExecutionsLive {
  schema_version: number;
  available: boolean;
  read_at: string;
  main_head: string | null;
  executions: WorkRoadExecution[];
  reason: string | null;
}

export type InboxOrigin = "usuario" | "claude" | "codex" | "grok" | "adk" | "documento" | "grafo" | "sistema";
export type InboxTriage = "capturada" | "em_triagem" | "promovida" | "duplicada" | "descartada";

export interface InboxAudit {
  at: string;
  actor: string;
  action: string;
  detail: string;
}

export interface InboxEntry {
  id: string;
  title: string;
  original: string;
  explanation?: string | null;
  origin: InboxOrigin;
  origin_ref?: string | null;
  author: string;
  captured_at: string;
  suggested_cluster?: string | null;
  suggested_urgency?: "baixa" | "media" | "alta" | null;
  triage: InboxTriage;
  promoted_task_id?: string | null;
  possible_duplicate_of?: string | null;
  decision?: string | null;
  justification?: string | null;
  audit: InboxAudit[];
}

export interface InboxCoverageTheme {
  id: string;
  title: string;
  related_task_ids: string[];
  inbox_id: string | null;
}

export interface InboxLive {
  schema_version: number;
  updated_at: string;
  purpose: string;
  entries: InboxEntry[];
  summary?: {
    total: number;
    capturadas: number;
    em_triagem: number;
    promovidas: number;
    duplicadas: number;
    descartadas: number;
    aguardando_triagem: number;
    possiveis_duplicatas: number;
  } | null;
  coverage?: { themes: InboxCoverageTheme[]; note?: string } | null;
  source: {
    path: string;
    sha256: string;
    read_at: string;
  };
  disclaimer: string;
}

export interface InboxReceipt {
  id: string;
  captured_at: string;
  origin: string;
  triage: InboxTriage;
  source_path: string;
  sha256: string;
}

export interface GraphStatusLive {
  available: boolean;
  stale: boolean;
  head: string | null;
  head_short: string | null;
  graph_commit: string | null;
  generated_at: string | null;
  reason: string | null;
  authority: string;
}

export interface ReorderReceipt {
  at: string;
  actor: string;
  initiative_id: string;
  before: string[];
  after: string[];
  before_sha256: string;
  after_sha256: string;
}
