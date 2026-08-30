// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import QGAgenticoPage from "@/pages/settings/QGAgenticoPage";
import QgTaskPage from "@/pages/settings/QgTaskPage";
import { pautadorApi } from "@/lib/pautadorApi";
import type { GraphStatusLive, InboxLive, RoadmapTask, WorkRoadExecutionsLive, WorkRoadLive } from "@/features/work-road/live";

vi.mock("@/lib/supabase", () => ({
  supabase: {},
}));

vi.mock("@/components/layout/Layout", () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const ROADMAP: WorkRoadLive = {
  schema_version: 1,
  updated_at: "2026-08-26",
  purpose: "teste",
  status_weights: { done: 1, partial: 0, risk: 0.25, todo: 0, reserved: null },
  status_labels: { done: "Concluído", partial: "Parcial", risk: "Risco", todo: "A fazer", reserved: "Reservado" },
  initiatives: [
    {
      id: "P01",
      rank: 1,
      title: "Fechar a fonte do trabalho",
      wave: "A · Clareza",
      why: "Uma verdade para todos.",
      done_when: "QG e livro leem a mesma fonte.",
      graph_nodes: ["cap_work_road"],
      tasks: [
        { id: "T1", title: "Criar o Roadmap Vivo", status: "done", proof: "arquivo versionado" },
        { id: "T2", title: "Ligar o QG", status: "partial", proof: "integração em validação" },
        { id: "T-risk", title: "Fechar grants", status: "risk", proof: "risco aceito temporariamente" },
        { id: "T-res", title: "Reservar low ticket", status: "reserved", proof: "pedido do dono" },
        { id: "T-empty", title: "Sem prova registrada", status: "todo", proof: "" },
      ],
    },
    {
      id: "P04",
      rank: 4,
      title: "Google Ads além de Search",
      wave: "B · Operação",
      why: "Destravar novos canais.",
      done_when: "Primeiro canal nasce com recibo.",
      graph_nodes: ["cap_google_multichannel"],
      tasks: [
        { id: "T3", title: "Implementar Display", status: "todo", proof: "perfil ausente" },
      ],
    },
  ],
  summary: {
    initiatives: 2,
    tasks: 6,
    accepted_tasks: 5,
    progress_percent: 25,
    counts: { done: 1, partial: 1, risk: 1, todo: 2, reserved: 1 },
  },
  source: {
    path: "volc-os-workbook/ROADMAP-VIVO.json",
    sha256: "abc",
    read_at: "2026-08-26T18:00:00Z",
  },
};

const EXECUTIONS: WorkRoadExecutionsLive = {
  schema_version: 1,
  available: true,
  read_at: "2026-08-27T12:00:00Z",
  main_head: "ca96353",
  reason: null,
  executions: [
    {
      id: "p04-display-finalizacao",
      name: "p04 display finalizacao",
      branch: "worktree-p04-display-finalizacao",
      head: "d12c28b",
      session_active: true,
      worktree_locked: true,
      dirty_files: 0,
      commits_ahead: 12,
      commits: [
        { sha: "d12c28b", subject: "suite deixa de tocar a conta real", committed_at: "2026-08-27T11:50:00Z" },
      ],
      roadmap_changes: [
        {
          task_id: "P04-T05",
          title: "Conectar motores criativos",
          before_status: "partial",
          after_status: "partial",
          proof_changed: true,
        },
      ],
    },
    {
      id: "old-idle",
      name: "missao antiga",
      branch: "agent/old",
      head: "deadbee",
      session_active: false,
      worktree_locked: false,
      dirty_files: 0,
      commits_ahead: 0,
      commits: [],
      roadmap_changes: [],
    },
  ],
};


const INBOX: InboxLive = {
  schema_version: 1,
  updated_at: "2026-08-28T12:00:00Z",
  purpose: "fila",
  entries: [],
  disclaimer: "Conversa não vira tarefa sozinha. Capturada não pertence ao percentual.",
  summary: {
    total: 0, capturadas: 0, em_triagem: 0, promovidas: 0, duplicadas: 0,
    descartadas: 0, aguardando_triagem: 0, possiveis_duplicatas: 0,
  },
  coverage: { themes: [], note: "Auditoria pontual." },
  source: { path: "volc-os-workbook/INBOX-ROADMAP.json", sha256: "def", read_at: "2026-08-28T12:00:00Z" },
};

const GRAPH: GraphStatusLive = {
  available: false,
  stale: true,
  head: "afa0917",
  head_short: "afa0917",
  graph_commit: null,
  generated_at: null,
  reason: "O grafo técnico não está neste worktree. Não é verdade operacional atual.",
  authority: "docs/volc-os-graph/curadoria-operacional.json",
};

function LocationProbe() {
  const [params] = useSearchParams();
  return <div data-testid="qg-qs">{params.toString()}</div>;
}

beforeEach(() => {
  vi.spyOn(pautadorApi, "workRoad").mockResolvedValue(ROADMAP);
  vi.spyOn(pautadorApi, "workRoadExecutions").mockResolvedValue(EXECUTIONS);
  vi.spyOn(pautadorApi, "workRoadInbox").mockResolvedValue(INBOX);
  vi.spyOn(pautadorApi, "workRoadGraphStatus").mockResolvedValue(GRAPH);
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mount(entry = "/settings/qg-agentico", client?: QueryClient) {
  const queryClient = client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/settings/qg-agentico" element={<QGAgenticoPage />} />
          <Route path="/settings/qg-agentico/tarefas/:taskId" element={<QgTaskPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeCatalog(taskCount: number): WorkRoadLive {
  const tasks: RoadmapTask[] = Array.from({ length: taskCount }, (_, index) => ({
    id: `TX-${String(index + 1).padStart(3, "0")}`,
    title: `Tarefa catalogada ${index + 1}`,
    status: index % 5 === 0 ? "done" : "todo",
    proof: `prova ${index + 1}`,
  }));
  return {
    ...ROADMAP,
    initiatives: [{
      ...ROADMAP.initiatives[0],
      tasks,
    }],
    summary: {
      initiatives: 1,
      tasks: taskCount,
      accepted_tasks: taskCount,
      progress_percent: 20,
      counts: {
        done: tasks.filter((item) => item.status === "done").length,
        partial: 0,
        risk: 0,
        todo: tasks.filter((item) => item.status === "todo").length,
        reserved: 0,
      },
    },
  };
}

describe("QG Operacional", () => {
  it("lê a fonte viva e não apresenta o snapshot local antigo", async () => {
    mount();
    expect(await screen.findByRole("heading", { name: "QG Operacional" })).toBeTruthy();
    expect(await screen.findByText(/volc-os-workbook\/ROADMAP-VIVO\.json/)).toBeTruthy();
    expect(screen.getByText("25%")).toBeTruthy();
    expect(screen.getByText(/Fechar a fonte do trabalho/)).toBeTruthy();
    expect(screen.queryByText("Protótipo local, sem falsa sincronização")).toBeNull();
  });

  it("não hardcoda os números principais: outro resumo muda a tela", async () => {
    vi.mocked(pautadorApi.workRoad).mockResolvedValue({
      ...ROADMAP,
      summary: { initiatives: 9, tasks: 40, accepted_tasks: 37, progress_percent: 12.5, counts: { done: 4, partial: 3, risk: 0, todo: 30, reserved: 3 } },
    });
    mount();
    expect(await screen.findByText("12.5%")).toBeTruthy();
    expect(screen.getByText("9")).toBeTruthy();
    expect(screen.getByText("40")).toBeTruthy();
    expect(screen.queryByText("25%")).toBeNull();
  });

  it("mostra as 95 tarefas e o recorte N de 95", async () => {
    vi.mocked(pautadorApi.workRoad).mockResolvedValue(makeCatalog(95));
    mount("/settings/qg-agentico?visao=tarefas");
    expect(await screen.findByText("95 de 95")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /Abrir tarefa TX-/ })).toHaveLength(95);
    expect(screen.getByText("Tarefa catalogada 95")).toBeTruthy();
  });

  it("deriva progresso da iniciativa pelos pesos da fonte", async () => {
    mount("/settings/qg-agentico?visao=roadmap");
    expect(await screen.findByRole("heading", { name: "Sequência operacional" })).toBeTruthy();
    // P01: done=1, partial=0, risk=0.25, todo=0, reserved fora → (1+0+0.25+0)/4 = 31.3
    expect(screen.getByLabelText(/Progresso 31\.3 por cento/)).toBeTruthy();
    expect(screen.queryByLabelText(/Progresso 75 por cento/)).toBeNull();
  });

  it("preserva filtros na URL e combina busca com estado", async () => {
    mount("/settings/qg-agentico?visao=tarefas&busca=Display&status=todo&iniciativa=P04&onda=B+%C2%B7+Opera%C3%A7%C3%A3o");
    expect(await screen.findByText("1 de 6")).toBeTruthy();
    expect(screen.getByText("Implementar Display")).toBeTruthy();
    expect(screen.queryByText("Criar o Roadmap Vivo")).toBeNull();
    expect(screen.getByTestId("qg-qs").textContent).toContain("visao=tarefas");
    expect(screen.getByTestId("qg-qs").textContent).toContain("status=todo");
    expect(screen.getByTestId("qg-qs").textContent).toContain("iniciativa=P04");
  });

  it("atualiza a URL ao filtrar e buscar", async () => {
    mount("/settings/qg-agentico?visao=tarefas");
    expect(await screen.findByText("6 de 6")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "done" } });
    expect(screen.getByText("Criar o Roadmap Vivo")).toBeTruthy();
    expect(screen.queryByText("Implementar Display")).toBeNull();
    expect(screen.getByText("1 de 6")).toBeTruthy();
    expect(screen.getByTestId("qg-qs").textContent).toContain("status=done");
    fireEvent.change(screen.getByLabelText("Buscar por título ou ID"), { target: { value: "Display" } });
    expect(screen.getByText(/Nenhuma tarefa neste recorte/)).toBeTruthy();
    expect(screen.getByTestId("qg-qs").textContent).toContain("busca=Display");
  });

  it("falha fechado quando a fonte não pode ser lida e não vira lista vazia", async () => {
    vi.mocked(pautadorApi.workRoad).mockRejectedValue(new Error("arquivo indisponível"));
    mount();
    expect(await screen.findByRole("heading", { name: "Não consegui ler o Roadmap Vivo" }, { timeout: 3000 })).toBeTruthy();
    expect(screen.getByText(/não substitui a fonte por dados antigos/i)).toBeTruthy();
    expect(screen.queryByText("Nenhuma tarefa neste recorte")).toBeNull();
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("mostra dados desatualizados em vez de apagar o último recorte válido", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
    vi.mocked(pautadorApi.workRoad).mockResolvedValueOnce(ROADMAP);
    mount("/settings/qg-agentico", client);
    expect(await screen.findByText(/Fechar a fonte do trabalho/)).toBeTruthy();
    vi.mocked(pautadorApi.workRoad).mockRejectedValue(new Error("timeout"));
    await client.invalidateQueries({ queryKey: ["work-road", "live"] });
    expect(await screen.findByText(/Dados desatualizados/, {}, { timeout: 4000 })).toBeTruthy();
    expect(screen.getByText(/Fechar a fonte do trabalho/)).toBeTruthy();
  });

  it("ausência de resumo não vira zero", async () => {
    vi.mocked(pautadorApi.workRoad).mockResolvedValue({ ...ROADMAP, summary: null });
    mount();
    expect(await screen.findByText(/resumo quantitativo não veio/i)).toBeTruthy();
    expect(screen.queryByText("25%")).toBeNull();
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("roadmap vazio é ausência de catálogo, não uma fila zerada", async () => {
    vi.mocked(pautadorApi.workRoad).mockResolvedValue({ ...ROADMAP, initiatives: [] });
    mount();
    expect(await screen.findByRole("heading", { name: "O Roadmap Vivo chegou vazio" })).toBeTruthy();
  });

  it("execução antiga sem processo não aparece como ativa", async () => {
    mount("/settings/qg-agentico?visao=execucoes");
    expect(await screen.findByRole("heading", { name: "O que os agentes estão registrando" })).toBeTruthy();
    expect(screen.getByText("Heartbeat atrasado")).toBeTruthy();
    const old = screen.getByText("missao antiga").closest("article");
    expect(old).toBeTruthy();
    expect(within(old as HTMLElement).getByText("Desatualizada")).toBeTruthy();
    expect(within(old as HTMLElement).queryByText("Ativa")).toBeNull();
    expect(within(old as HTMLElement).getByText(/sem heartbeat/i)).toBeTruthy();
  });

  it("não oferece escrita nem encerramento de processo", async () => {
    mount("/settings/qg-agentico?visao=execucoes");
    expect(await screen.findByRole("heading", { name: "O que os agentes estão registrando" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /encerrar|concluir|matar|kill|salvar/i })).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    const called = (pautadorApi.workRoad as ReturnType<typeof vi.fn>).mock.calls.length
      + (pautadorApi.workRoadExecutions as ReturnType<typeof vi.fn>).mock.calls.length;
    expect(called).toBeGreaterThan(0);
    expect("updateWorkRoad" in pautadorApi).toBe(false);
  });

  it("abre o drawer com evidência, reserva, risco, parcial e copiar ID", async () => {
    mount("/settings/qg-agentico?visao=tarefas&tarefa=T-empty");
    expect(await screen.findByText("Tarefa sem evidência na fonte.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copiar ID T-empty" })).toBeTruthy();
    cleanup();
    mount("/settings/qg-agentico?visao=tarefas&tarefa=T-res");
    expect(await screen.findAllByText("Capacidade reservada")).toHaveLength(2);
    cleanup();
    mount("/settings/qg-agentico?visao=tarefas&tarefa=T-risk");
    expect((await screen.findAllByText("Existe com risco")).length).toBeGreaterThan(0);
    cleanup();
    mount("/settings/qg-agentico?visao=tarefas&tarefa=T2");
    expect((await screen.findAllByText("Parcial")).length).toBeGreaterThan(0);
  });

  it("expõe nomes acessíveis e navegação por teclado nas visões", async () => {
    mount();
    const agora = await screen.findByRole("tab", { name: "Agora" });
    expect(agora.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(agora, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Timeline" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: "Lista" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Kanban" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Inbox" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Execuções" })).toBeTruthy();
  });

  it("claro, escuro e viewport estreita não escondem as ações", async () => {
    const view = mount("/settings/qg-agentico?visao=tarefas");
    expect(await screen.findByRole("button", { name: /Abrir tarefa T1/ })).toBeTruthy();
    expect(screen.getByLabelText("Buscar por título ou ID")).toBeTruthy();
    expect(screen.getByLabelText("Estado")).toBeTruthy();
    view.container.querySelector(".dark") ?? view.container.classList.add("dark");
    expect(screen.getByRole("tab", { name: "Agora" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Lista" })).toBeTruthy();
    expect(screen.getByLabelText("Iniciativa")).toBeTruthy();
    expect(screen.getByLabelText("Onda")).toBeTruthy();
  });

  it("acompanha uma worktree sem transformar commits em percentual", async () => {
    mount("/settings/qg-agentico?visao=execucoes");
    expect(await screen.findByRole("heading", { name: "O que os agentes estão registrando" })).toBeTruthy();
    expect(screen.getByText("suite deixa de tocar a conta real")).toBeTruthy();
    expect(screen.getByText("Evidência atualizada, sem promover o estado.")).toBeTruthy();
    expect(screen.getAllByText(/Não é percentual de conclusão/i).length).toBeGreaterThan(0);
    expect(pautadorApi.workRoadExecutions).toHaveBeenCalled();
  });

  it("consulta novamente quando recebe foco lógico por uma nova montagem", async () => {
    mount();
    await waitFor(() => expect(pautadorApi.workRoad).toHaveBeenCalledTimes(1));
  });

  it("nenhuma execução ativa é um estado explícito", async () => {
    vi.mocked(pautadorApi.workRoadExecutions).mockResolvedValue({
      ...EXECUTIONS,
      executions: EXECUTIONS.executions.map((item) => ({ ...item, session_active: false })),
    });
    mount("/settings/qg-agentico?visao=execucoes");
    expect(await screen.findByText(/Nenhuma execução ativa neste instante/)).toBeTruthy();
  });

  it("não infere bloqueio pela ordem editorial e não repete task.id nas filas de Agora", async () => {
    mount("/settings/qg-agentico");
    expect(await screen.findByTestId("qg-agora-proxima")).toBeTruthy();
    expect(screen.queryByTestId("qg-agora-fila-bloqueio")).toBeNull();
    expect(screen.queryByText(/impede avanço/i)).toBeNull();
    const nextId = screen.getByTestId("qg-agora-proxima").querySelector(".font-mono")?.textContent;
    const secondaryIds = ["qg-agora-fila-risco", "qg-agora-fila-bloqueio", "qg-agora-fila-parcial", "qg-agora-fila-prioridade"]
      .flatMap((id) => Array.from(screen.queryByTestId(id)?.querySelectorAll("[data-task-id]") ?? []))
      .map((node) => node.getAttribute("data-task-id"));
    expect(new Set(secondaryIds).size).toBe(secondaryIds.length);
    if (nextId) expect(secondaryIds).not.toContain(nextId);
  });

  it("mostra bloqueio somente quando a fonte declara dependência aberta", async () => {
    vi.mocked(pautadorApi.workRoad).mockResolvedValue({
      ...ROADMAP,
      initiatives: [
        {
          ...ROADMAP.initiatives[0],
          tasks: [
            { id: "T1", title: "Criar o Roadmap Vivo", status: "done", proof: "arquivo versionado" },
            { id: "T2", title: "Ligar o QG", status: "partial", proof: "integração em validação" },
            { id: "T-wait", title: "Espera Display", status: "todo", proof: "aguardando", depends_on: ["T3"] },
          ],
        },
        {
          ...ROADMAP.initiatives[1],
          tasks: [
            { id: "T3", title: "Implementar Display", status: "todo", proof: "perfil ausente" },
          ],
        },
      ],
    });
    mount("/settings/qg-agentico");
    const blocked = await screen.findByTestId("qg-agora-fila-bloqueio");
    expect(blocked.querySelector("[data-task-id='T-wait']")).toBeTruthy();
    expect(blocked.querySelector("[data-task-id='T3']")).toBeNull();
  });

  it("execução sem agent e sem provider não é identificada como Claude", async () => {
    mount("/settings/qg-agentico?visao=execucoes");
    expect(await screen.findByRole("heading", { name: "O que os agentes estão registrando" })).toBeTruthy();
    expect(screen.getAllByText("agente local não identificado").length).toBeGreaterThan(0);
    expect(screen.queryByText(/claude/i)).toBeNull();
    expect(screen.queryByText(/codex/i)).toBeNull();
    expect(screen.queryByText(/grok/i)).toBeNull();
  });

  it("mantém a rota antiga apenas como redirecionamento para o QG", () => {
    const app = readFileSync(resolve(process.cwd(), "src/App.tsx"), "utf-8");
    expect(app).toContain('path="/settings/qg-agentico"');
    expect(app).toContain('<Navigate to="/settings/qg-agentico" replace />');
  });

  it("arquivos do QG não hardcodam 15/95/25/21/44 como verdade operacional", () => {
    const roots = [
      resolve(process.cwd(), "src/pages/settings/QGAgenticoPage.tsx"),
      resolve(process.cwd(), "src/components/qg"),
      resolve(process.cwd(), "src/features/work-road"),
    ];
    const files = [
      roots[0],
      ...["QgAgora", "QgRoadmap", "QgTarefas", "QgExecucoes", "QgPulse"].map((name) =>
        resolve(process.cwd(), `src/components/qg/${name}.tsx`),
      ),
    ];
    for (const file of files) {
      const text = readFileSync(file, "utf-8");
      expect(text).not.toMatch(/\b95 tarefas\b/);
      expect(text).not.toMatch(/\b15 iniciativas\b/);
      expect(text).not.toMatch(/const TOTAL_TASKS/);
    }
  });

  it("Inbox não afirma captura automática e não conta no percentual", async () => {
    mount("/settings/qg-agentico?visao=inbox");
    expect(await screen.findByRole("heading", { name: "Inbox do Roadmap" })).toBeTruthy();
    expect(screen.getAllByText(/não vira tarefa sozinha/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/adicionada ao roadmap/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Capturar ideia" })).toBeTruthy();
    expect(screen.getByText("25%")).toBeTruthy();
  });

  it("página de tarefa inexistente é 404", async () => {
    mount("/settings/qg-agentico/tarefas/T-FALSA");
    expect(await screen.findByTestId("qg-task-404")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Tarefa não encontrada" })).toBeTruthy();
  });

  it("página de tarefa declara campos ausentes", async () => {
    mount("/settings/qg-agentico/tarefas/T-empty");
    expect(await screen.findByRole("heading", { name: "Sem prova registrada" })).toBeTruthy();
    expect(screen.getByText("Checklist ainda não documentado.")).toBeTruthy();
    expect(screen.getByText("A fonte não declara dependências desta tarefa.")).toBeTruthy();
  });

  it("Kanban é um board genuíno: colunas nomeadas, ids únicos e rolagem acessível", async () => {
    mount("/settings/qg-agentico?visao=kanban");
    expect(await screen.findByRole("heading", { name: "Kanban da fonte" })).toBeTruthy();
    // O board é uma região nomeada e rolável; nenhuma coluna é escondida atrás de tabs.
    const board = screen.getByRole("region", { name: /board do kanban/i });
    expect(board.className).toContain("overflow-x-auto");
    // As cinco colunas existem como regiões nomeadas com as contagens da fonte.
    const todoColumn = screen.getByRole("region", { name: /A fazer/ });
    expect(within(todoColumn).getByText("2")).toBeTruthy();
    expect(screen.getByRole("region", { name: /Parcial \/ em desenvolvimento/ })).toBeTruthy();
    expect(screen.getByRole("region", { name: /Com risco/ })).toBeTruthy();
    expect(screen.getByRole("region", { name: /Concluída e provada/ })).toBeTruthy();
    expect(screen.getByRole("region", { name: /Reservada/ })).toBeTruthy();
    // Cada task.id aparece uma única vez no board inteiro.
    const ids = Array.from(document.querySelectorAll("[data-task-id]")).map((node) => node.getAttribute("data-task-id"));
    expect(ids.length).toBe(6);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("Kanban usa card compacto legível: ID e estado no topo, hairline semântica e subordinação visual", async () => {
    mount("/settings/qg-agentico?visao=kanban");
    await screen.findByRole("heading", { name: "Kanban da fonte" });
    const card = screen.getByRole("button", { name: "Abrir tarefa T1: Criar o Roadmap Vivo" }).closest("article");
    expect(card).toBeTruthy();
    expect(card?.className).toContain("rounded-lg");
    expect(card?.className).toContain("bg-card");
    // Concluída fica subordinada, mas continua acessível (mesmo botão, ainda presente).
    expect(card?.className).toContain("opacity-70");
    // Hairline semântica de 2px no topo, na cor do estado (T1 é done).
    const hairline = card?.querySelector("[data-testid='qg-card-hairline']");
    expect(hairline).toBeTruthy();
    expect(hairline?.className).toContain("h-0.5");
    expect(hairline?.className).toContain("bg-success");
    const partialCard = screen.getByRole("button", { name: "Abrir tarefa T2: Ligar o QG" }).closest("article");
    const partialHairline = partialCard?.querySelector("[data-testid='qg-card-hairline']");
    expect(partialHairline?.className).toContain("bg-warning");
    expect(partialCard?.className).not.toContain("opacity-70");
  });

  it("Kanban expõe subir/descer compactos com disabled correto e anuncia a reordenação", async () => {
    mount("/settings/qg-agentico?visao=kanban");
    expect(await screen.findByRole("heading", { name: "Kanban da fonte" })).toBeTruthy();
    const upT1 = screen.getByRole("button", { name: "Subir T1" });
    const downT1 = screen.getByRole("button", { name: "Descer T1" });
    // T1 é o primeiro da iniciativa P01: sobe desabilitado, desce habilitado.
    expect((upT1 as HTMLButtonElement).disabled).toBe(true);
    expect((downT1 as HTMLButtonElement).disabled).toBe(false);
    // Alvos móveis de pelo menos 44px.
    expect(upT1.className).toContain("h-11");
    expect(upT1.className).toContain("w-11");
    // Iniciativa com uma única tarefa (P04) desabilita os dois lados.
    expect((screen.getByRole("button", { name: "Subir T3" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Descer T3" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(downT1);
    // O anúncio de reordenação chega por aria-live e a proposta mostra a nova sequência.
    expect(screen.getByText(/T1 desceu na proposta da iniciativa P01/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Proposta de nova ordem" })).toBeTruthy();
    expect(screen.getByText("T2 → T1 → T-risk → T-res → T-empty")).toBeTruthy();
  });

  it("coluna sem tarefas declara ausência, não vira lista vazia silenciosa", async () => {
    vi.mocked(pautadorApi.workRoad).mockResolvedValue({
      ...ROADMAP,
      initiatives: [
        {
          ...ROADMAP.initiatives[0],
          tasks: ROADMAP.initiatives[0].tasks.filter((task) => task.status !== "risk"),
        },
        ROADMAP.initiatives[1],
      ],
    });
    mount("/settings/qg-agentico?visao=kanban");
    expect(await screen.findByRole("heading", { name: "Kanban da fonte" })).toBeTruthy();
    const riskColumn = screen.getByRole("region", { name: /Com risco/ });
    expect(within(riskColumn).getByText("Nenhuma tarefa neste estado.")).toBeTruthy();
    const ids = Array.from(document.querySelectorAll("[data-task-id]")).map((node) => node.getAttribute("data-task-id"));
    expect(ids.length).toBe(5);
    expect(new Set(ids).size).toBe(5);
  });

  it("grafo defasado avisa e o nó abre a tarefa", async () => {
    mount("/settings/qg-agentico?visao=grafo");
    expect(await screen.findByRole("heading", { name: "Grafo operacional" })).toBeTruthy();
    expect(screen.getByText(/Não é verdade operacional atual/)).toBeTruthy();
    expect(screen.getByText(/docs\/volc-os-graph\/curadoria-operacional\.json/)).toBeTruthy();
    const node = await screen.findByTestId("qg-graph-node-T2");
    expect(node.getAttribute("href")).toBe("/settings/qg-agentico/tarefas/T2");
    fireEvent.click(node);
    expect(await screen.findByRole("heading", { name: "Ligar o QG" })).toBeTruthy();
  });

  it("execução órfã aparece na visão Execuções", async () => {
    mount("/settings/qg-agentico?visao=execucoes");
    expect(await screen.findByText(/Execuções órfãs \(sem task_ids\): 2/)).toBeTruthy();
  });

});
