import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RoadmapTaskStatus, WorkRoadLive } from "@/features/work-road/live";
import { ROADMAP_TASK_STATUSES } from "@/features/work-road/live";
import type { FlatTask } from "@/features/work-road/selectors";
import {
  classifyTaskKind,
  kindLabel,
  listedTextCount,
  statusLabel,
  wavesFrom,
} from "@/features/work-road/selectors";
import type { QgUrlState } from "@/features/work-road/url-state";
import { QgKindMark, QgStatusMark } from "./QgStatusMark";
import { QgFilterEmpty } from "./QgStates";

export function QgTarefas({
  workRoad,
  rows,
  filtered,
  filters,
  onFilters,
  onOpenTask,
}: {
  workRoad: WorkRoadLive;
  rows: FlatTask[];
  filtered: FlatTask[];
  filters: QgUrlState;
  onFilters: (patch: Partial<QgUrlState>) => void;
  onOpenTask: (id: string) => void;
}) {
  const total = workRoad.summary?.tasks ?? null;
  const countLabel = listedTextCount(filtered.length, total);
  const initiatives = [...workRoad.initiatives].sort((a, b) => a.rank - b.rank);
  const waves = wavesFrom(workRoad);

  return (
    <section aria-labelledby="qg-tasks-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Catálogo completo</p>
          <h2 id="qg-tasks-heading" className="mt-1 font-display text-2xl font-semibold tracking-tight">
            Tarefas da operação
          </h2>
        </div>
        {countLabel ? (
          <p className="text-sm tabular-nums text-foreground" aria-live="polite">
            {countLabel}
          </p>
        ) : (
          <p className="text-sm text-foreground" aria-live="polite">
            {filtered.length} neste recorte. O total da fonte não veio nesta leitura.
          </p>
        )}
      </div>

      <div className="mt-5 grid gap-3 border-y border-border py-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <label className="relative block w-full max-w-xl" htmlFor="qg-task-search">
          <span className="sr-only">Buscar por título ou ID</span>
          <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            id="qg-task-search"
            value={filters.busca}
            onChange={(event) => onFilters({ busca: event.target.value })}
            placeholder="ID, título ou explicação"
            className="h-10 min-h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <FilterSelect
            label="Estado"
            value={filters.status}
            onChange={(value) => onFilters({ status: value as RoadmapTaskStatus | "all" })}
            options={[
              { value: "all", label: "Todos os estados" },
              ...ROADMAP_TASK_STATUSES.map((status) => ({
                value: status,
                label: `${statusLabel(status, workRoad.status_labels)}${
                  workRoad.summary ? ` (${workRoad.summary.counts[status]})` : ""
                }`,
              })),
            ]}
          />
          <FilterSelect
            label="Iniciativa"
            value={filters.iniciativa || "all"}
            onChange={(value) => onFilters({ iniciativa: value === "all" ? "" : value })}
            options={[
              { value: "all", label: "Todas as iniciativas" },
              ...initiatives.map((initiative) => ({
                value: initiative.id,
                label: `${initiative.id} · ${initiative.title}`,
              })),
            ]}
          />
          <FilterSelect
            label="Owner"
            value={filters.owner || "all"}
            onChange={(value) => onFilters({ owner: value === "all" ? "" : value })}
            options={[
              { value: "all", label: "Todos os owners" },
              ...[...new Set(rows.map((row) => row.task.owner).filter((item): item is string => Boolean(item)))].map((owner) => ({
                value: owner,
                label: owner,
              })),
            ]}
          />
          <FilterSelect
            label="Execução"
            value={filters.execucao}
            onChange={(value) => onFilters({ execucao: value as QgUrlState["execucao"] })}
            options={[
              { value: "all", label: "Todas as execuções" },
              { value: "ativa", label: "Com execução ativa" },
            ]}
          />
          <FilterSelect
            label="Ordenação"
            value={filters.ordem}
            onChange={(value) => onFilters({ ordem: value as QgUrlState["ordem"] })}
            options={[
              { value: "fonte", label: "Ordem da fonte" },
              { value: "id", label: "ID" },
              { value: "titulo", label: "Título" },
              { value: "estado", label: "Estado" },
            ]}
          />
          <FilterSelect
            label="Onda"
            value={filters.onda || "all"}
            onChange={(value) => onFilters({ onda: value === "all" ? "" : value })}
            options={[
              { value: "all", label: "Todas as ondas" },
              ...waves.map((wave) => ({ value: wave, label: wave })),
            ]}
          />
        </div>
      </div>

      <div className="mt-2 flex max-w-full gap-1 overflow-x-auto pb-1 lg:hidden" aria-label="Atalhos de estado">
        <Button
          size="sm"
          variant={filters.status === "all" ? "default" : "ghost"}
          onClick={() => onFilters({ status: "all" })}
        >
          Todas
        </Button>
        {ROADMAP_TASK_STATUSES.map((status) => (
          <Button
            key={status}
            size="sm"
            variant={filters.status === status ? "default" : "ghost"}
            onClick={() => onFilters({ status })}
          >
            {statusLabel(status, workRoad.status_labels)}
          </Button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <QgFilterEmpty
          onClear={() => onFilters({ busca: "", status: "all", iniciativa: "", onda: "", owner: "", execucao: "all", ordem: "fonte" })}
        />
      ) : (
        <ul className="mt-2 divide-y divide-border border-y border-border">
          {filtered.map((row) => (
            <li key={row.task.id}>
              <button
                type="button"
                onClick={() => onOpenTask(row.task.id)}
                aria-label={`Abrir tarefa ${row.task.id}: ${row.task.title}`}
                className={cn(
                  "grid w-full gap-2 py-3 text-left outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:grid-cols-[7.5rem_minmax(0,1fr)_auto] sm:items-start",
                  row.task.status === "done" && "opacity-65",
                )}
              >
                <span className="font-mono text-xs font-semibold text-primary">{row.task.id}</span>
                <span className="min-w-0">
                  <span className={cn("block text-sm font-medium", row.task.status === "done" && "text-muted-foreground")}>
                    {row.task.title}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {row.initiative.id} · rank {row.initiative.rank} · {row.initiative.wave}
                  </span>
                  <span className="mt-1 inline-flex">
                    <QgKindMark label={kindLabel(classifyTaskKind(row.task.status))} />
                  </span>
                </span>
                <QgStatusMark status={row.task.status} labels={workRoad.status_labels} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="sr-only">{rows.length} tarefas na fonte antes dos filtros.</p>
    </section>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  const id = `qg-filter-${label.toLocaleLowerCase("pt-BR").replace(/\s+/g, "-")}`;
  return (
    <label className="block min-w-[12rem] text-xs font-medium text-muted-foreground" htmlFor={id}>
      {label}
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 block h-10 min-h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}
