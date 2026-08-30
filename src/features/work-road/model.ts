export type WorkView =
  | "agora"
  | "roadmap"
  | "capacidades"
  | "agentes"
  | "decisoes"
  | "evidencias";

export type WorkState =
  | "ready"
  | "claimed"
  | "in_progress"
  | "review"
  | "blocked"
  | "done";

export type ProductState =
  | "planned"
  | "partial"
  | "implemented"
  | "legacy"
  | "parked";

export type EnvironmentState = "docs" | "code" | "local" | "production";
export type RiskState = "normal" | "external" | "accepted";

export interface AcceptanceItem {
  id: string;
  label: string;
  initiallyDone?: boolean;
}

export interface Initiative {
  id: string;
  title: string;
  objective: string;
  cluster: string;
  whyNow: string;
  owner: string;
  workState: WorkState;
  productState: ProductState;
  risk: RiskState;
  environments: EnvironmentState[];
  branch?: string;
  scope: string[];
  dependencies: string[];
  nextAction: string;
  acceptance: AcceptanceItem[];
  evidenceIds: string[];
}

export interface Wave {
  id: string;
  title: string;
  promise: string;
  initiativeIds: string[];
}

export interface Capability {
  id: string;
  title: string;
  cluster: string;
  state: ProductState;
  explanation: string;
  nextMove: string;
}

export interface AgentAssignment {
  id: string;
  name: string;
  role: string;
  state: "working" | "review" | "standby";
  initiativeId: string;
  branch: string;
  scope: string[];
  handoff: string;
}

export interface OwnerDecision {
  id: string;
  title: string;
  question: string;
  state: "open" | "accepted" | "decided";
  consequence: string;
  relatedInitiatives: string[];
}

export interface WorkEvidence {
  id: string;
  kind: "commit" | "test" | "migration" | "browser" | "document";
  title: string;
  detail: string;
  environment: EnvironmentState;
  verdict: "agent" | "audited" | "owner";
  occurredAt: string;
}

export interface WorkRoadSnapshot {
  generatedAt: string;
  headCommit: string;
  graphCommit: string;
  graphIsStale: boolean;
  initiatives: Initiative[];
  waves: Wave[];
  capabilities: Capability[];
  agents: AgentAssignment[];
  decisions: OwnerDecision[];
  evidence: WorkEvidence[];
}

