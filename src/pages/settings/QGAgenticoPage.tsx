import { Target } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { QgAgora } from "@/components/qg/QgAgora";
import { QgExecucoes } from "@/components/qg/QgExecucoes";
import { QgExport } from "@/components/qg/QgExport";
import { QgGrafo } from "@/components/qg/QgGrafo";
import { QgInbox } from "@/components/qg/QgInbox";
import { QgKanban } from "@/components/qg/QgKanban";
import { QgPulse } from "@/components/qg/QgPulse";
import { QgTarefas } from "@/components/qg/QgTarefas";
import { QgTaskDrawer } from "@/components/qg/QgTaskDrawer";
import { QgTimeline } from "@/components/qg/QgTimeline";
import { QgEmptyRoadmap, QgError, QgFilterEmpty, QgLoading, QgStaleBanner } from "@/components/qg/QgStates";
import { QgViewNav } from "@/components/qg/QgViewNav";
import { formatDate } from "@/features/work-road/format";
import {
  filterTasks,
  flattenTasks,
  sortBySourceRank,
  sortTasks,
  summaryOrAbsent,
} from "@/features/work-road/selectors";
import { parseQgSearch, writeQgSearch, type QgUrlState, type QgView } from "@/features/work-road/url-state";
import { useGraphStatus, useWorkRoadInbox } from "@/features/work-road/useInbox";
import { useWorkRoad } from "@/features/work-road/useWorkRoad";
import { useWorkRoadExecutions } from "@/features/work-road/useWorkRoadExecutions";

export function QGAgenticoContent() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = parseQgSearch(searchParams);
  const reading = useWorkRoad();
  const executionsReading = useWorkRoadExecutions(true);
  const inboxReading = useWorkRoadInbox();
  const graphReading = useGraphStatus();
  const workRoad = reading.workRoad;
  const rows = sortBySourceRank(flattenTasks(workRoad));
  const executions = executionsReading.executions?.executions ?? [];
  const matched = filterTasks(rows, filters).filter((row) => {
    if (filters.execucao === "ativa") {
      return executions.some((item) => (item.task_ids ?? []).includes(row.task.id) && item.session_active);
    }
    return true;
  });
  const sourced = sortBySourceRank(matched);
  const listed = sortTasks(matched, filters.ordem);
  const selected = rows.find((row) => row.task.id === filters.tarefa) ?? null;
  const summary = summaryOrAbsent(workRoad);
  const emptyCatalog = Boolean(workRoad && workRoad.initiatives.length === 0);
  const emptySlice = sourced.length === 0;

  const patchUrl = (patch: Partial<QgUrlState>) => {
    setSearchParams(writeQgSearch(searchParams, patch), { replace: true });
  };
  const clearFilters = () => patchUrl({
    busca: "",
    status: "all",
    iniciativa: "",
    onda: "",
    owner: "",
    execucao: "all",
    ordem: "fonte",
  });
  const setView = (visao: QgView) => patchUrl({ visao, tarefa: "" });
  const openTask = (id: string) => patchUrl({ tarefa: id });
  const openPage = (id: string) => navigate(`/settings/qg-agentico/tarefas/${encodeURIComponent(id)}`);

  return (
    <div className="mx-auto w-full max-w-[1540px] overflow-x-hidden px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <header className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div>
          <div className="kicker mb-2 flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Target className="h-3.5 w-3.5" aria-hidden />
            </span>
            sala de comando
          </div>
          <h1 className="font-display text-3xl font-bold tracking-tight leading-[1.05] text-foreground sm:text-4xl">
            QG <span className="text-aurora">Operacional</span>
          </h1>
          <div className="mt-3 aurora-rule w-16" />
          <p className="mt-3 max-w-3xl text-pretty text-sm text-muted-foreground">
            Uma tarefa dominante, a sequência da fonte, e um Inbox que não finge captura automática.
          </p>
        </div>
        <div className="space-y-3">
          {workRoad ? (
            <div className="text-xs text-muted-foreground lg:text-right">
              <p className="font-medium text-foreground">Fonte viva · {workRoad.source.path}</p>
              <p className="mt-1">Atualizada em {formatDate(workRoad.updated_at)}</p>
              <p className="mt-1">
                {reading.atualizando ? "Conferindo atualização" : `Lida em ${formatDate(workRoad.source.read_at)}`}
              </p>
            </div>
          ) : null}
          <QgExport filters={filters} />
        </div>
      </header>

      {reading.desatualizado ? (
        <QgStaleBanner
          message="A leitura mais recente falhou ou envelheceu. O que está na tela é a última fotografia válida, não o instante atual."
          onRetry={reading.recarregar}
        />
      ) : null}

      {workRoad ? <QgPulse summary={summary} labels={workRoad.status_labels} /> : null}

      <QgViewNav view={filters.visao} onChange={setView} />

      <div
        role="tabpanel"
        id={`qg-panel-${filters.visao}`}
        aria-labelledby={`qg-tab-${filters.visao}`}
        className="py-7"
      >
        {reading.carregando ? <QgLoading /> : null}
        {reading.falhou ? (
          <QgError
            title="Não consegui ler o Roadmap Vivo"
            message={reading.erro ? `O QG não substitui a fonte por dados antigos. ${reading.erro}` : "O QG não substitui a fonte por dados antigos."}
            onRetry={reading.recarregar}
          />
        ) : null}
        {emptyCatalog ? <QgEmptyRoadmap /> : null}
        {workRoad && !emptyCatalog && filters.visao === "agora" ? (
          <QgAgora
            workRoad={workRoad}
            rows={rows}
            executions={executionsReading.executions}
            onOpenTask={openTask}
            onOpenPage={openPage}
          />
        ) : null}
        {workRoad && !emptyCatalog && filters.visao === "timeline" ? (
          emptySlice ? <QgFilterEmpty onClear={clearFilters} /> : (
            <QgTimeline workRoad={workRoad} rows={sourced} executions={executions} />
          )
        ) : null}
        {workRoad && !emptyCatalog && filters.visao === "kanban" ? (
          emptySlice ? <QgFilterEmpty onClear={clearFilters} /> : (
            <QgKanban workRoad={workRoad} rows={sourced} executions={executions} />
          )
        ) : null}
        {workRoad && !emptyCatalog && filters.visao === "lista" ? (
          <QgTarefas
            workRoad={workRoad}
            rows={rows}
            filtered={listed}
            filters={filters}
            onFilters={patchUrl}
            onOpenTask={openTask}
          />
        ) : null}
        {workRoad && !emptyCatalog && filters.visao === "grafo" ? (
          emptySlice ? <QgFilterEmpty onClear={clearFilters} /> : (
            <QgGrafo
              rows={sourced}
              executions={executions}
              graphStatus={graphReading.status}
              modo={filters.grafoModo}
              onModo={(grafoModo) => patchUrl({ grafoModo })}
              busca={filters.busca}
              onBusca={(busca) => patchUrl({ busca })}
              onRetry={graphReading.recarregar}
            />
          )
        ) : null}
        {workRoad && filters.visao === "execucoes" ? (
          <QgExecucoes reading={executionsReading} />
        ) : null}
        {filters.visao === "inbox" ? (
          <QgInbox
            inbox={inboxReading.inbox}
            carregando={inboxReading.carregando}
            falhou={inboxReading.falhou}
            desatualizado={inboxReading.desatualizado}
            erro={inboxReading.erro}
            recarregar={inboxReading.recarregar}
            executions={executions}
          />
        ) : null}
      </div>

      <QgTaskDrawer
        row={selected}
        labels={workRoad?.status_labels}
        open={Boolean(selected)}
        onClose={() => patchUrl({ tarefa: "" })}
      />

      <footer className="flex flex-col gap-2 border-t border-border py-5 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <span>O agente atualiza a fonte; o QG reflete a mudança em até 15 segundos.</span>
        <span>Inbox e reordenação ADMIN deixam recibo. Conversa não vira tarefa sozinha.</span>
      </footer>
    </div>
  );
}

export default function QGAgenticoPage() {
  return (
    <Layout>
      <QGAgenticoContent />
    </Layout>
  );
}
