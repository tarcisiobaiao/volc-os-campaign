import { describe, expect, it } from "vitest";
import { classifyExecution, filterTasks, flattenTasks, listedTextCount, progressFromWeights, agoraQueues, isBlockedByDeclaredDependency, executionAgentLabel, recommendNext, sortBySourceRank, declaredDependencies, isOrphanExecution } from "../selectors";
import { parseQgSearch, writeQgSearch } from "../url-state";
import { readingFreshness } from "../freshness";
import { buildAdkManifest, buildMissionPrompt, manifestHasSecrets } from "../mission";
import type { FlatTask } from "../selectors";
import type { RoadmapInitiative, RoadmapTask, WorkRoadExecution, WorkRoadLive } from "../live";
import roadmapVivo from "../../../../volc-os-workbook/ROADMAP-VIVO.json";

const weights = { done: 1, partial: 0.5, risk: 0.25, todo: 0, reserved: null };

function task(partial: Partial<RoadmapTask> & Pick<RoadmapTask, "id" | "status">): RoadmapTask {
  return { title: partial.title ?? partial.id, proof: partial.proof ?? "prova", ...partial };
}

describe("progressFromWeights", () => {
  it("usa os pesos da fonte, não uma fórmula local inventada", () => {
    const tasks = [task({ id: "A", status: "done" }), task({ id: "B", status: "partial" })];
    expect(progressFromWeights(tasks, weights).percent).toBe(75);
    expect(progressFromWeights(tasks, { ...weights, partial: 0 }).percent).toBe(50);
  });

  it("trata reserva e falta de aceitas como ausência, não como zero", () => {
    const reserved = [task({ id: "R", status: "reserved" })];
    expect(progressFromWeights(reserved, weights).percent).toBeNull();
    expect(progressFromWeights([], weights).percent).toBeNull();
    expect(progressFromWeights(reserved, null).percent).toBeNull();
  });
});

describe("prioridade operacional da fonte viva", () => {
  it("recomenda fechar o canário Search antes das pendências editoriais sem prioridade explícita", () => {
    const roadmap = roadmapVivo as unknown as WorkRoadLive;
    const recomendacao = recommendNext(flattenTasks(roadmap));

    expect(recomendacao.next?.task.id).toBe("P05-T11");
    expect(recomendacao.authority).toBe("prioridade explícita");
  });
});

describe("filterTasks", () => {
  const initiative: RoadmapInitiative = {
    id: "P04",
    rank: 4,
    title: "Google Ads",
    wave: "B · Operação",
    why: "why",
    done_when: "done",
    graph_nodes: [],
    tasks: [],
  };
  const rows: FlatTask[] = [
    { initiative, indexInInitiative: 0, task: task({ id: "P04-T01", title: "Display", status: "todo" }) },
    { initiative, indexInInitiative: 1, task: task({ id: "P04-T02", title: "Demand Gen", status: "partial" }) },
  ];

  it("combina busca, estado, iniciativa e onda", () => {
    expect(filterTasks(rows, { busca: "display", status: "todo", iniciativa: "P04", onda: "B · Operação" })).toHaveLength(1);
    expect(filterTasks(rows, { busca: "display", status: "partial", iniciativa: "P04", onda: "B · Operação" })).toHaveLength(0);
    expect(filterTasks(rows, { busca: "P04-T02", status: "all", iniciativa: "", onda: "" })[0].task.id).toBe("P04-T02");
  });
});

describe("listedTextCount", () => {
  it("não inventa o total quando a fonte omite", () => {
    expect(listedTextCount(3, 95)).toBe("3 de 95");
    expect(listedTextCount(0, null)).toBeNull();
  });
});

describe("classifyExecution", () => {
  const base: WorkRoadExecution = {
    id: "wt",
    name: "missao",
    branch: "feat/x",
    head: "abc1234",
    session_active: false,
    worktree_locked: false,
    dirty_files: 0,
    commits_ahead: 0,
    commits: [],
    roadmap_changes: [],
  };

  it("não classifica como ativa só porque o diretório existe", () => {
    const result = classifyExecution(base);
    expect(result.kind).toBe("desatualizado");
    expect(result.kind).not.toBe("ativo");
    expect(result.missingHeartbeat).toBe(true);
  });

  it("sessão viva sem heartbeat é atraso, não execução normal", () => {
    expect(classifyExecution({ ...base, session_active: true }).kind).toBe("heartbeat_atrasado");
  });

  it("só marca ativa com processo vivo e heartbeat", () => {
    expect(classifyExecution({ ...base, session_active: true, heartbeat_at: "2026-08-28T12:00:00Z" }).kind).toBe("ativo");
  });

  it("marca falha somente quando a fonte diz", () => {
    expect(classifyExecution({ ...base, failed: true }).kind).toBe("falho");
  });
});

describe("url-state", () => {
  it("roundtrip de visao, busca, status, iniciativa e onda", () => {
    const written = writeQgSearch(new URLSearchParams(), {
      visao: "lista",
      busca: "display",
      status: "todo",
      iniciativa: "P04",
      onda: "B",
    });
    expect(written.get("visao")).toBe("lista");
    expect(written.get("busca")).toBe("display");
    expect(written.get("status")).toBe("todo");
    expect(written.get("iniciativa")).toBe("P04");
    expect(written.get("onda")).toBe("B");
    const parsed = parseQgSearch(written);
    expect(parsed).toMatchObject({
      visao: "lista",
      busca: "display",
      status: "todo",
      iniciativa: "P04",
      onda: "B",
    });
  });

  it("aliases visao=tarefas e visao=roadmap", () => {
    expect(parseQgSearch(new URLSearchParams("visao=tarefas")).visao).toBe("lista");
    expect(parseQgSearch(new URLSearchParams("visao=roadmap")).visao).toBe("timeline");
  });
});

describe("readingFreshness", () => {
  it("distingue erro sem dados de dados desatualizados", () => {
    expect(readingFreshness({ dataUpdatedAt: 0, isError: true, isPending: false, hasData: false })).toBe("erro");
    expect(readingFreshness({ dataUpdatedAt: 1, isError: true, isPending: false, hasData: true })).toBe("desatualizado");
    expect(readingFreshness({ dataUpdatedAt: Date.now() - 120_000, isError: false, isPending: false, hasData: true })).toBe("desatualizado");
  });
});

function initiativeWith(tasks: RoadmapTask[]): RoadmapInitiative {
  return {
    id: "P01",
    rank: 1,
    title: "Ini",
    wave: "A",
    why: "why",
    done_when: "done",
    graph_nodes: [],
    tasks,
  };
}

function rowsFrom(tasks: RoadmapTask[]): FlatTask[] {
  const initiative = initiativeWith(tasks);
  return tasks.map((item, indexInInitiative) => ({ task: item, initiative, indexInInitiative }));
}

describe("bloqueio só com dependência declarada", () => {
  it("tarefa anterior sem dependencies não vira bloqueador", () => {
    const rows = rowsFrom([
      task({ id: "T1", status: "todo" }),
      task({ id: "T2", status: "todo" }),
    ]);
    expect(isBlockedByDeclaredDependency(rows[1], rows)).toBe(false);
    expect(agoraQueues(rows).blocked).toHaveLength(0);
    expect(recommendNext(rows).reason).toMatch(/não em dependência comprovada/);
  });

  it("dependência declarada e aberta vira bloqueio", () => {
    const rows = rowsFrom([
      task({ id: "T1", status: "todo" }),
      task({ id: "T2", status: "todo", depends_on: ["T1"] }),
    ]);
    expect(isBlockedByDeclaredDependency(rows[1], rows)).toBe(true);
    expect(agoraQueues(rows).blocked.map((row) => row.task.id)).toEqual(["T2"]);
  });

  it("dependência declarada e concluída não bloqueia", () => {
    const rows = rowsFrom([
      task({ id: "T1", status: "done" }),
      task({ id: "T2", status: "todo", dependencies: ["T1"] }),
    ]);
    expect(isBlockedByDeclaredDependency(rows[1], rows)).toBe(false);
    expect(agoraQueues(rows).blocked).toHaveLength(0);
  });

  it("nenhum task.id se repete nas filas secundárias de Agora", () => {
    const rows = rowsFrom([
      task({ id: "A", status: "risk" }),
      task({ id: "B", status: "partial" }),
      task({ id: "C", status: "todo", depends_on: ["A"] }),
      task({ id: "D", status: "todo" }),
    ]);
    const queues = agoraQueues(rows);
    expect(queues.next?.task.id).toBe("B");
    const secondary = [
      ...queues.risks,
      ...queues.blocked,
      ...queues.partials,
      ...queues.ranked,
    ].map((row) => row.task.id);
    expect(secondary).toEqual(["A", "C", "D"]);
    expect(new Set(secondary).size).toBe(secondary.length);
    expect(secondary).not.toContain("B");
  });
});

describe("executionAgentLabel", () => {
  const base: WorkRoadExecution = {
    id: "wt",
    name: "missao",
    branch: "feat/x",
    head: "abc1234",
    session_active: false,
    worktree_locked: false,
    dirty_files: 0,
    commits_ahead: 0,
    commits: [],
    roadmap_changes: [],
  };

  it("não identifica Claude, Codex ou Grok sem evidência da API", () => {
    const label = executionAgentLabel(base);
    expect(label).toBe("agente local não identificado");
    expect(label.toLocaleLowerCase("pt-BR")).not.toMatch(/claude|codex|grok/);
  });

  it("usa agent ou provider quando a fonte envia", () => {
    expect(executionAgentLabel({ ...base, agent: "codex" })).toBe("codex");
    expect(executionAgentLabel({ ...base, provider: "grok" })).toBe("grok");
  });
});


describe("ordenação da fonte e inbox", () => {
  it("sortBySourceRank usa prioridade explícita antes de rank e ordem editorial", () => {
    const later = initiativeWith([
      task({ id: "T-b", status: "todo", order: 2, priority: 2 }),
      task({ id: "T-a", status: "todo", order: 1, priority: 1 }),
    ]);
    const rows = later.tasks.map((item, indexInInitiative) => ({
      task: item,
      initiative: later,
      indexInInitiative,
    }));
    expect(sortBySourceRank(rows).map((row) => row.task.id)).toEqual(["T-a", "T-b"]);
  });

  it("prioridade explícita atravessa iniciativas e vence o rank editorial", () => {
    const editorial = initiativeWith([task({ id: "T-editorial", status: "todo" })]);
    const operacional: RoadmapInitiative = {
      ...initiativeWith([task({ id: "T-operacional", status: "partial", priority: 1 })]),
      id: "P05",
      rank: 5,
    };
    const rows: FlatTask[] = [
      { task: editorial.tasks[0], initiative: editorial, indexInInitiative: 0 },
      { task: operacional.tasks[0], initiative: operacional, indexInInitiative: 0 },
    ];

    expect(sortBySourceRank(rows).map((row) => row.task.id)).toEqual(["T-operacional", "T-editorial"]);
    expect(recommendNext(rows)).toMatchObject({
      next: { task: { id: "T-operacional" } },
      authority: "prioridade explícita",
    });
  });

  it("dependência só existe quando a fonte declara", () => {
    const rows = rowsFrom([
      task({ id: "T1", status: "todo" }),
      task({ id: "T2", status: "todo" }),
    ]);
    expect(declaredDependencies(rows[1].task)).toBeNull();
    expect(isBlockedByDeclaredDependency(rows[1], rows)).toBe(false);
  });
});

describe("execução órfã e manifesto", () => {
  it("execução sem task_ids é órfã", () => {
    expect(isOrphanExecution({
      id: "wt", name: "x", branch: "b", head: "h", session_active: false,
      worktree_locked: false, dirty_files: 0, commits_ahead: 0, commits: [], roadmap_changes: [],
    })).toBe(true);
  });
});

describe("manifesto ADK", () => {
  it("marca campos ausentes e recusa padrão de segredo", () => {
    const rows = rowsFrom([task({ id: "T1", status: "todo", proof: "arquivo" })]);
    const manifest = buildAdkManifest(rows[0], "abc1234");
    expect(manifest.task_ids).toEqual(["T1"]);
    expect(manifest.acceptance[0]).toMatch(/AUSENTE/);
    expect(manifestHasSecrets(manifest)).toBe(false);
    expect(manifestHasSecrets("token=super-secret")).toBe(true);
    const prompt = buildMissionPrompt(rows[0]);
    expect(prompt).toContain("T1");
    expect(prompt).toMatch(/AUSENTE: explanation/);
  });
});
