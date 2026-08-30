import type { FlatTask } from "./selectors";
import { declaredDependencies, evidenceText, textList } from "./selectors";

const SECRET_MARK = /(api[_-]?key\s*[:=]|secret\s*[:=]|token\s*[:=]|password\s*[:=]|authorization:\s*bearer|BEGIN [A-Z ]+PRIVATE KEY|\.env\s*=)/i;

export function absent(label: string): string {
  return `[AUSENTE: ${label}]`;
}

export function buildMissionPrompt(row: FlatTask): string {
  const task = row.task;
  const acceptance = textList(task.acceptance);
  const deps = declaredDependencies(task);
  const links = task.links?.map((item) => `${item.kind}: ${item.value}`) ?? null;
  const lines = [
    `# Missão ${task.id}`,
    "",
    "## Objetivo",
    task.title,
    "",
    "## Contexto",
    task.explanation?.trim() || absent("explanation"),
    `Iniciativa ${row.initiative.id} · ${row.initiative.title}`,
    `Onda ${row.initiative.wave} · rank ${row.initiative.rank}`,
    `Por que a iniciativa existe: ${row.initiative.why}`,
    "",
    "## O que já existe",
    evidenceText(task) || absent("proof"),
    "",
    "## Fontes",
    "volc-os-workbook/ROADMAP-VIVO.json",
    ...(links ?? [absent("links")]),
    "",
    "## Caminhos permitidos",
    "src/pages/settings/QGAgenticoPage.tsx",
    "src/pages/settings/QgTaskPage.tsx",
    "src/features/work-road/**",
    "src/components/qg/**",
    "backend/app/routers/work_road.py",
    "backend/app/work_road/**",
    "volc-os-workbook/**",
    "",
    "## Aceite",
    ...(acceptance ?? [absent("acceptance")]),
    `Pronto da iniciativa: ${row.initiative.done_when}`,
    "",
    "## Gates",
    "Testes do QG e do Work Road",
    "TypeScript nos arquivos de ownership",
    "build Vite",
    "",
    "## Limites",
    "Não inventar dependências, progresso ou identidade de agente.",
    "Não tocar Tráfego, Criativos, migrations ou o grafo gerado.",
    "Não incluir segredo, token ou conteúdo de .env.",
    "Não executar shell pelo navegador.",
    "",
    `## Task ID`,
    task.id,
    "",
    "## Dependências declaradas",
    deps ? deps.join(", ") : "Nenhuma dependência declarada pela fonte.",
  ];
  return lines.join("\n");
}

export interface AdkManifest {
  mission_id: string;
  task_ids: string[];
  objective: string;
  base_commit: string | null;
  worktree: string;
  agents: string[];
  ownership: string[];
  acceptance: string[];
  gates: string[];
  restrictions: string[];
  heartbeat: {
    required: true;
    note: string;
  };
}

export function buildAdkManifest(row: FlatTask, baseCommit: string | null): AdkManifest {
  const acceptance = textList(row.task.acceptance) ?? [absent("acceptance")];
  return {
    mission_id: `qg-${row.task.id.toLowerCase()}`,
    task_ids: [row.task.id],
    objective: row.task.title,
    base_commit: baseCommit,
    worktree: `.claude/worktrees/${row.task.id.toLowerCase()}`,
    agents: row.task.owner ? [row.task.owner] : [absent("owner/agents")],
    ownership: [
      "src/pages/settings/QGAgenticoPage.tsx",
      "src/pages/settings/QgTaskPage.tsx",
      "src/features/work-road/**",
      "src/components/qg/**",
    ],
    acceptance,
    gates: ["testes do QG", "testes do Work Road", "tsc nos arquivos de ownership", "vite build"],
    restrictions: [
      "Sem segredo, token ou conteúdo de .env",
      "Sem push, merge ou deploy",
      "Sem inventar dependência por ordem editorial",
      "Sem reconstruir o grafo nesta branch",
    ],
    heartbeat: {
      required: true,
      note: "Diretório de worktree não prova processo ativo. Ausência de heartbeat não é execução normal.",
    },
  };
}

export function adkRunCommand(manifestPath: string): string {
  return [
    "/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/.venv-adk/bin/volc-agent-run \\",
    "  --repo /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign \\",
    `  --mission ${manifestPath}`,
  ].join("\n");
}

export function manifestHasSecrets(manifest: AdkManifest | string): boolean {
  const text = typeof manifest === "string" ? manifest : JSON.stringify(manifest);
  return SECRET_MARK.test(text);
}
