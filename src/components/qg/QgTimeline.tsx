import type { RoadmapInitiative, WorkRoadExecution, WorkRoadLive } from "@/features/work-road/live";
import type { FlatTask } from "@/features/work-road/selectors";
import { declaredDependencies, initiativeProgress, sortBySourceRank, wavesFrom } from "@/features/work-road/selectors";
import { QgTaskCard } from "./QgTaskCard";

export function QgTimeline({
  workRoad,
  rows,
  executions,
}: {
  workRoad: WorkRoadLive;
  rows: FlatTask[];
  executions: WorkRoadExecution[];
}) {
  const ordered = sortBySourceRank(rows);
  const waves = wavesFrom(workRoad);
  const hasDates = rows.some((row) => Boolean(row.task.updated_at));

  return (
    <section aria-labelledby="qg-timeline-heading">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        {hasDates ? "Timeline" : "Sequência operacional"}
      </p>
      <h2 id="qg-timeline-heading" className="mt-1 font-display text-2xl font-semibold tracking-tight text-balance">
        {hasDates ? "Linha do tempo da fonte" : "Sequência operacional"}
      </h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
        Sem datas confiáveis a ordem segue onda, rank, prioridade explícita e ordem editorial persistida.
        Proximidade visual não é dependência.
      </p>
      <div className="mt-8 space-y-10">
        {waves.map((wave) => {
          const inWave = ordered.filter((row) => row.initiative.wave === wave);
          if (inWave.length === 0) return null;
          const seen = new Set<string>();
          const initiatives: RoadmapInitiative[] = [];
          for (const row of inWave) {
            if (seen.has(row.initiative.id)) continue;
            seen.add(row.initiative.id);
            initiatives.push(row.initiative);
          }
          return (
            <section key={wave} aria-labelledby={`wave-${wave}`}>
              <h3 id={`wave-${wave}`} className="font-display text-xl font-semibold tracking-tight">
                {wave}
              </h3>
              {initiatives.map((initiative) => {
                const cards = inWave.filter((row) => row.initiative.id === initiative.id);
                const progress = initiativeProgress(initiative, workRoad.status_weights);
                return (
                  <article key={initiative.id} className="mt-5 border-t border-border pt-4">
                    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_12rem] lg:items-start">
                      <div>
                        <p className="font-mono text-xs font-semibold text-primary">{initiative.id}</p>
                        <h4 className="mt-1 font-display text-lg font-semibold">{initiative.title}</h4>
                        <p className="mt-1 text-sm text-muted-foreground text-pretty">{initiative.why}</p>
                      </div>
                      <ProgressMeter percent={progress.percent} accepted={progress.accepted} />
                    </div>
                    <ul className="mt-3 divide-y divide-border border-y border-border">
                      {cards.map((row) => (
                        <li key={row.task.id} data-task-id={row.task.id}>
                          <QgTaskCard
                            row={row}
                            labels={workRoad.status_labels}
                            executions={executions}
                            reason={
                              declaredDependencies(row.task)
                                ? `Dependência declarada: ${declaredDependencies(row.task)?.join(", ")}`
                                : `Rank ${row.initiative.rank} · ordem editorial ${row.task.order ?? row.indexInInitiative + 1}`
                            }
                          />
                        </li>
                      ))}
                    </ul>
                  </article>
                );
              })}
            </section>
          );
        })}
      </div>
    </section>
  );
}

function ProgressMeter({ percent, accepted }: { percent: number | null; accepted: number }) {
  if (percent == null) {
    return <p className="text-sm text-foreground/80">Progresso ausente: não há tarefas aceitas nesta iniciativa.</p>;
  }
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-xs">
        <span className="font-medium text-foreground">Progresso da fonte</span>
        <span className="tabular-nums text-muted-foreground">{percent}%</span>
      </div>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label={`Progresso ${percent} por cento, ${accepted} tarefas aceitas`}
      >
        <div
          className="h-full rounded-full bg-primary motion-reduce:transition-none"
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
    </div>
  );
}
