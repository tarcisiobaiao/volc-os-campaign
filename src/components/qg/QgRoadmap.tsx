import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RoadmapInitiative, WorkRoadLive } from "@/features/work-road/live";
import { initiativeProgress, kindLabel, classifyTaskKind, wavesFrom } from "@/features/work-road/selectors";
import { QgKindMark, QgStatusMark } from "./QgStatusMark";
import { QgMissingField } from "./QgStates";

export function QgRoadmap({
  workRoad,
  onOpenTask,
}: {
  workRoad: WorkRoadLive;
  onOpenTask: (id: string) => void;
}) {
  const waves = wavesFrom(workRoad);
  return (
    <section aria-labelledby="qg-roadmap-heading">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Frentes na ordem da fonte</p>
      <h2 id="qg-roadmap-heading" className="mt-1 font-display text-2xl font-semibold tracking-tight text-balance">
        Iniciativas e ondas
      </h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
        O progresso de cada iniciativa usa os pesos oficiais da fonte. Reservadas ficam visíveis e fora do percentual.
      </p>
      <div className="mt-8 space-y-10">
        {waves.map((wave) => (
          <section key={wave} aria-label={wave}>
            <h3 className="border-b border-border pb-3 font-display text-lg font-semibold">{wave}</h3>
            <div>
              {workRoad.initiatives
                .filter((initiative) => initiative.wave === wave)
                .sort((a, b) => a.rank - b.rank)
                .map((initiative) => (
                  <InitiativeBlock
                    key={initiative.id}
                    initiative={initiative}
                    workRoad={workRoad}
                    onOpenTask={onOpenTask}
                  />
                ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

function InitiativeBlock({
  initiative,
  workRoad,
  onOpenTask,
}: {
  initiative: RoadmapInitiative;
  workRoad: WorkRoadLive;
  onOpenTask: (id: string) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const progress = initiativeProgress(initiative, workRoad.status_weights);
  const explanation = initiative.explanation?.trim() || initiative.why;
  const deps = initiative.dependencies;

  return (
    <article className="border-b border-border py-5">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_12rem] lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-2">
            <p className="font-mono text-xs font-semibold text-primary">{initiative.id}</p>
            <p className="text-xs tabular-nums text-muted-foreground">rank {initiative.rank}</p>
          </div>
          <h4 className="mt-1 font-display text-lg font-semibold leading-6 text-balance">{initiative.title}</h4>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-foreground/85 text-pretty">{explanation}</p>
        </div>
        <ProgressMeter percent={progress.percent} accepted={progress.accepted} />
      </div>

      <dl className="mt-4 grid gap-4 text-sm md:grid-cols-2">
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Contagem por estado</dt>
          <dd className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs tabular-nums text-foreground/85">
            {Object.entries(progress.counts).map(([status, count]) => (
              <span key={status}>{count} {status}</span>
            ))}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Por que existe</dt>
          <dd className="mt-1 leading-6 text-foreground/85">{initiative.why}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Pronto quando</dt>
          <dd className="mt-1 leading-6 text-foreground/85">{initiative.done_when}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Dependências</dt>
          <dd className="mt-1 leading-6">
            {deps && deps.length > 0 ? deps.join(", ") : (
              <QgMissingField>A fonte não declara dependências desta iniciativa.</QgMissingField>
            )}
          </dd>
        </div>
        <div className="md:col-span-2">
          <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Nós do grafo</dt>
          <dd className="mt-2 flex flex-wrap gap-1.5">
            {initiative.graph_nodes.length > 0 ? initiative.graph_nodes.map((node) => (
              <span key={node} className="rounded-full border border-border px-2 py-0.5 font-mono text-[11px]">{node}</span>
            )) : (
              <QgMissingField>Nenhum nó veio nesta leitura.</QgMissingField>
            )}
          </dd>
        </div>
      </dl>

      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="mt-4 inline-flex min-h-10 items-center gap-2 text-sm font-medium text-primary outline-none transition-transform duration-150 ease-out active:scale-[0.96] focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 motion-reduce:transition-none motion-reduce:active:scale-100"
      >
        <ChevronDown aria-hidden="true" className={cn("h-4 w-4 transition-transform duration-150", open && "rotate-180")} />
        {open ? "Recolher tarefas" : `Mostrar ${initiative.tasks.length} tarefas`}
      </button>

      {open ? (
        <ul className="mt-2 divide-y divide-border border-t border-border" aria-label={`Tarefas de ${initiative.title}`}>
          {initiative.tasks.map((task) => (
            <li key={task.id}>
              <button
                type="button"
                onClick={() => onOpenTask(task.id)}
                aria-label={`Abrir tarefa ${task.id}: ${task.title}`}
                className={cn(
                  "grid w-full gap-2 py-3 text-left outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:grid-cols-[7.5rem_minmax(0,1fr)_auto] sm:items-start",
                  task.status === "done" && "opacity-70",
                )}
              >
                <span className="font-mono text-xs font-semibold text-primary">{task.id}</span>
                <span className="min-w-0">
                  <span className={cn("block text-sm font-medium", task.status === "done" && "text-muted-foreground")}>
                    {task.title}
                  </span>
                  <span className="mt-1 inline-flex">
                    <QgKindMark label={kindLabel(classifyTaskKind(task.status))} />
                  </span>
                </span>
                <QgStatusMark status={task.status} labels={workRoad.status_labels} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
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
