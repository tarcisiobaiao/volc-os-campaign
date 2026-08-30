import { cn } from "@/lib/utils";
import type { WorkRoadSummary } from "@/features/work-road/live";
import { ROADMAP_TASK_STATUSES } from "@/features/work-road/live";
import { statusLabel } from "@/features/work-road/selectors";
import type { WorkRoadLive } from "@/features/work-road/live";
import { QgAbsentSummary } from "./QgStates";

export function QgPulse({
  summary,
  labels,
  className,
}: {
  summary: WorkRoadSummary | null;
  labels: WorkRoadLive["status_labels"] | null | undefined;
  className?: string;
}) {
  if (!summary) return <QgAbsentSummary />;

  return (
    <section
      aria-label="Pulso do Roadmap Vivo"
      className={cn("mt-5 overflow-hidden rounded-lg border border-border bg-card shadow-card", className)}
    >
      <div className="grid gap-px bg-border sm:grid-cols-2 lg:grid-cols-3">
        <PulseCell
          value={`${summary.progress_percent}%`}
          label="índice editorial da fonte"
        />
        <PulseCell value={summary.initiatives} label="iniciativas" />
        <PulseCell value={summary.tasks} label="tarefas na fonte" />
      </div>
      <ul className="grid gap-px border-t border-border bg-border sm:grid-cols-2 lg:grid-cols-5">
        {ROADMAP_TASK_STATUSES.map((status) => (
          <li key={status} className="flex items-baseline gap-2 bg-card px-4 py-3">
            <span className="text-lg font-semibold tabular-nums text-foreground">
              {summary.counts[status]}
            </span>
            <span className="text-xs leading-4 text-muted-foreground">
              {statusLabel(status, labels).toLocaleLowerCase("pt-BR")}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PulseCell({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="flex items-baseline gap-2 bg-card px-4 py-3">
      <span className="text-lg font-semibold tabular-nums text-foreground">{value}</span>
      <span className="text-xs leading-4 text-muted-foreground">{label}</span>
    </div>
  );
}
