import { useNavigate } from "react-router-dom";
import type { RoadmapTaskStatus, WorkRoadExecution, WorkRoadLive } from "@/features/work-road/live";
import type { FlatTask } from "@/features/work-road/selectors";
import {
  checklistProgress,
  classifyExecution,
  declaredDependencies,
  evidenceText,
  executionsForTask,
} from "@/features/work-road/selectors";
import { taskPath } from "@/features/work-road/url-state";
import { cn } from "@/lib/utils";
import { QgExecutionMark, QgStatusMark } from "./QgStatusMark";

/**
 * Hairline semântica de 2px no topo do card compacto (DESIGN.md: status on a
 * card usa hairline de 2px na cor do estado). Nunca é a única portadora de
 * significado: o chip mantém glifo + palavra.
 */
const HAIRLINE: Record<RoadmapTaskStatus, string> = {
  done: "bg-success",
  partial: "bg-warning",
  risk: "bg-destructive",
  todo: "bg-primary",
  reserved: "bg-muted-foreground/50",
};

/** Concluídas e reservadas ficam visualmente subordinadas, mas continuam acessíveis. */
const SUBORDINATE: ReadonlySet<RoadmapTaskStatus> = new Set(["done", "reserved"]);

export function QgTaskCard({
  row,
  labels,
  executions = [],
  reason,
  compact = false,
}: {
  row: FlatTask;
  labels: WorkRoadLive["status_labels"];
  executions?: WorkRoadExecution[];
  reason?: string;
  compact?: boolean;
}) {
  const navigate = useNavigate();
  const progress = checklistProgress(row.task);
  const deps = declaredDependencies(row.task);
  const evidence = evidenceText(row.task);
  const live = executionsForTask(row.task.id, executions).filter((item) => {
    const kind = classifyExecution(item).kind;
    return kind === "ativo" || kind === "heartbeat_atrasado";
  });

  const open = () => navigate(taskPath(row.task.id));

  if (compact) {
    return (
      <article
        className={cn(
          "relative overflow-hidden rounded-lg border border-border bg-card",
          SUBORDINATE.has(row.task.status) && "opacity-70",
        )}
      >
        <span
          aria-hidden="true"
          data-testid="qg-card-hairline"
          className={cn("absolute inset-x-0 top-0 h-0.5", HAIRLINE[row.task.status])}
        />
        <button
          type="button"
          onClick={open}
          aria-label={`Abrir tarefa ${row.task.id}: ${row.task.title}`}
          className="block w-full p-3 text-left outline-none transition-colors duration-150 hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring motion-reduce:transition-none"
        >
          <span className="flex flex-wrap items-start justify-between gap-2">
            <span className="font-mono text-xs font-semibold text-primary">{row.task.id}</span>
            <QgStatusMark status={row.task.status} labels={labels} />
          </span>
          <span className="mt-2 block text-sm font-medium leading-5 text-foreground text-pretty break-words">
            {row.task.title}
          </span>
          <span className="mt-1.5 block text-xs leading-5 text-muted-foreground break-words">
            {row.initiative.id} · {row.initiative.title}
          </span>
          {reason ? (
            <span className="mt-1 block text-xs leading-5 text-foreground/75 break-words">{reason}</span>
          ) : null}
          {evidence ? (
            <span className="mt-1.5 line-clamp-2 block text-xs leading-5 text-muted-foreground break-words">
              {evidence}
            </span>
          ) : null}
          {deps ? (
            <span className="mt-1.5 block text-xs leading-5 text-foreground/80 break-words">
              Dependência declarada: {deps.join(", ")}
            </span>
          ) : null}
          {live.length > 0 ? (
            <span className="mt-2 flex flex-wrap gap-1.5">
              {live.map((item) => (
                <QgExecutionMark key={item.id} kind={classifyExecution(item).kind} />
              ))}
            </span>
          ) : null}
        </button>
      </article>
    );
  }

  return (
    <article className="border-b border-border py-3 last:border-b-0">
      <button
        type="button"
        onClick={open}
        aria-label={`Abrir tarefa ${row.task.id}: ${row.task.title}`}
        className="grid w-full gap-2 text-left outline-none transition-colors duration-150 hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring motion-reduce:transition-none sm:grid-cols-[7.5rem_minmax(0,1fr)_auto] sm:items-start"
      >
        <span className="font-mono text-xs font-semibold text-primary">{row.task.id}</span>
        <span className="min-w-0">
          <span className="block text-sm font-medium text-foreground text-pretty">{row.task.title}</span>
          <span className="mt-1 block text-xs leading-5 text-muted-foreground">
            {row.initiative.id} · {row.initiative.title}
          </span>
          {reason ? <span className="mt-1 block text-xs leading-5 text-foreground/75">{reason}</span> : null}
          {!compact && progress ? (
            <span className="mt-1 block text-xs tabular-nums text-muted-foreground">
              Checklist {progress.done}/{progress.total}
            </span>
          ) : null}
          {!compact && !progress ? (
            <span className="mt-1 block text-xs italic text-muted-foreground">Checklist ainda não documentado</span>
          ) : null}
          {deps ? (
            <span className="mt-1 block text-xs text-foreground/80">
              Dependência declarada: {deps.join(", ")}
            </span>
          ) : null}
          {live.map((item) => (
            <span key={item.id} className="mt-1 inline-flex">
              <QgExecutionMark kind={classifyExecution(item).kind} />
            </span>
          ))}
        </span>
        <QgStatusMark status={row.task.status} labels={labels} />
      </button>
    </article>
  );
}
