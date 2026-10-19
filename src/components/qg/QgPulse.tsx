import { cn } from "@/lib/utils";
import type { WorkRoadSummary } from "@/features/work-road/live";
import { ROADMAP_TASK_STATUSES } from "@/features/work-road/live";
import { plainStatusLabel } from "@/features/work-road/selectors";
import type { WorkRoadLive } from "@/features/work-road/live";
import { QgAbsentSummary } from "./QgStates";

export function QgPulse({
  summary,
  labels: _labels,
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
          label="do trabalho documentado já avançou"
        />
        <PulseCell value={summary.initiatives} label="frentes organizadas" />
        <PulseCell value={summary.tasks} label="entregas acompanhadas" />
      </div>
      <ul className="grid gap-px border-t border-border bg-border sm:grid-cols-2 lg:grid-cols-5">
        {ROADMAP_TASK_STATUSES.map((status) => (
          <li key={status} className="flex items-baseline gap-2 bg-card px-4 py-3">
            <span className="text-lg font-semibold tabular-nums text-foreground">
              {summary.counts[status]}
            </span>
            <span className="text-xs leading-4 text-muted-foreground">
              {plainStatusLabel(status).toLocaleLowerCase("pt-BR")}
            </span>
          </li>
        ))}
      </ul>
      <p className="border-t border-border bg-card px-4 py-3 text-xs leading-5 text-muted-foreground">
        Este percentual mede organização e evidência do roadmap. Não significa que o sistema inteiro está pronto nem que a operação já gera lucro.
      </p>
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
