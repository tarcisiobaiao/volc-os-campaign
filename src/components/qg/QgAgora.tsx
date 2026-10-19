import * as React from "react";
import { ChevronDown } from "lucide-react";
import type { RoadmapInitiative, WorkRoadExecutionsLive, WorkRoadLive } from "@/features/work-road/live";
import type { AgoraQueueRole, FlatTask } from "@/features/work-road/selectors";
import {
  agoraQueues,
  classifyExecution,
  initiativeProgress,
  isOpenStatus,
  plainStatusLabels,
  sortBySourceRank,
  taskPlainExplanation,
  taskRemaining,
  wavesFrom,
} from "@/features/work-road/selectors";
import { cn } from "@/lib/utils";
import { QgExecutionMark, QgStatusMark } from "./QgStatusMark";
import { QgNoActiveExecutions } from "./QgStates";

const SIMPLE_LABELS = plainStatusLabels();

export function QgAgora({
  workRoad,
  rows,
  executions,
  onOpenTask,
  onOpenPage,
}: {
  workRoad: WorkRoadLive;
  rows: FlatTask[];
  executions: WorkRoadExecutionsLive | null;
  onOpenTask: (id: string) => void;
  onOpenPage?: (id: string) => void;
}) {
  const queues = agoraQueues(rows);
  const ordered = sortBySourceRank(rows);
  const liveExecutions = (executions?.executions ?? []).filter((item) => {
    const kind = classifyExecution(item).kind;
    return kind === "ativo" || kind === "heartbeat_atrasado";
  });

  return (
    <div className="space-y-12">
      <section aria-labelledby="qg-next">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          Seu ponto de partida
        </p>
        <h2 id="qg-next" className="mt-1 font-display text-2xl font-semibold tracking-tight text-balance">
          O primeiro item aberto na ordem aprovada
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
          Esta não é uma sugestão inventada pela tela. É a primeira entrega ainda aberta na sequência do Roadmap Vivo.
          Se ela não deve vir primeiro, precisamos corrigir a ordem na fonte.
        </p>
        {queues.next ? (
          <FocusTask row={queues.next} onOpenTask={onOpenTask} onOpenPage={onOpenPage} />
        ) : (
          <p className="mt-5 border-y border-border py-5 text-sm text-foreground">
            O roadmap não possui entrega aberta neste momento.
          </p>
        )}
      </section>

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)]">
        <section aria-labelledby="qg-attention">
          <h2 id="qg-attention" className="font-display text-xl font-semibold tracking-tight">
            O que pede atenção
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            Risco e bloqueio só aparecem aqui quando estão registrados na fonte. A tela não transforma ordem editorial em bloqueio.
          </p>
          <div className="mt-4 space-y-7">
            <SimpleQueue
              title="Riscos registrados"
              empty="Nenhum risco marcado na fonte."
              testId="qg-agora-fila-risco"
              rows={queues.risks}
              role="risco"
              onOpenTask={onOpenTask}
            />
            <SimpleQueue
              title="Dependências que impedem avanço"
              empty={null}
              testId="qg-agora-fila-bloqueio"
              rows={queues.blocked}
              role="bloqueio"
              onOpenTask={onOpenTask}
            />
          </div>
        </section>

        <section aria-labelledby="qg-now-exec">
          <h2 id="qg-now-exec" className="font-display text-xl font-semibold tracking-tight">
            Agentes trabalhando agora
          </h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Processo ativo não significa tarefa concluída. O roadmap só muda quando existe prova e a fonte é atualizada.
          </p>
          <div className="mt-4 divide-y divide-border border-y border-border">
            {liveExecutions.length === 0 ? <QgNoActiveExecutions /> : null}
            {liveExecutions.map((execution) => {
              const classified = classifyExecution(execution);
              return (
                <article key={execution.id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="font-medium capitalize">{execution.mission || execution.name}</h3>
                    <QgExecutionMark kind={classified.kind} />
                  </div>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">{classified.why}</p>
                </article>
              );
            })}
          </div>
        </section>
      </div>

      <section aria-labelledby="qg-full-plan">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          Plano completo
        </p>
        <h2 id="qg-full-plan" className="mt-1 font-display text-2xl font-semibold tracking-tight text-balance">
          Tudo o que ainda falta, separado por frente
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
          Cada frente explica por que existe, o que significa terminá-la e quais entregas continuam abertas. Códigos, hashes e caminhos ficam recolhidos nos detalhes técnicos.
        </p>
        <RoadmapByWave workRoad={workRoad} rows={ordered} onOpenTask={onOpenTask} />
      </section>

      <section aria-labelledby="qg-following" className="grid gap-8 lg:grid-cols-2">
        <h2 id="qg-following" className="sr-only">Filas complementares</h2>
        <SimpleQueue
          title="Próximos itens na sequência"
          empty="Não há outros itens abertos na sequência."
          testId="qg-agora-fila-prioridade"
          rows={queues.upcoming}
          role="prioridade"
          onOpenTask={onOpenTask}
        />
        <SimpleQueue
          title="Já começaram, mas ainda não fecharam"
          empty="Nenhuma entrega parcial próxima na sequência."
          testId="qg-agora-fila-parcial"
          rows={queues.partials}
          role="parcial"
          onOpenTask={onOpenTask}
        />
      </section>
    </div>
  );
}

function FocusTask({ row, onOpenTask, onOpenPage }: {
  row: FlatTask;
  onOpenTask: (id: string) => void;
  onOpenPage?: (id: string) => void;
}) {
  const remaining = taskRemaining(row.task);
  return (
    <article data-testid="qg-agora-proxima" className="mt-5 rounded-lg border border-border bg-card p-5 shadow-card sm:p-6">
      <span className="sr-only font-mono">{row.task.id}</span>
      <div className="flex flex-wrap items-center gap-2">
        <QgStatusMark status={row.task.status} labels={SIMPLE_LABELS} />
        <span className="text-xs text-muted-foreground">Frente: {row.initiative.title}</span>
      </div>
      <h3 className="mt-4 max-w-3xl font-display text-2xl font-semibold leading-8 text-balance">{row.task.title}</h3>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-foreground/85 text-pretty">{taskPlainExplanation(row)}</p>
      <div className="mt-5 border-t border-border pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          O que falta para considerar pronto
        </p>
        {remaining ? (
          <ul className="mt-2 max-w-3xl list-disc space-y-1 pl-5 text-sm leading-6 text-foreground/85">
            {remaining.map((item) => <li key={item}>{item}</li>)}
          </ul>
        ) : (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-warning">
            O roadmap ainda não registra um critério final em linguagem simples. Precisamos completar esse campo antes de chamar a entrega de pronta.
          </p>
        )}
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onOpenTask(row.task.id)}
          className="inline-flex min-h-10 items-center rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground transition-transform duration-150 ease-out active:scale-[0.97] hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 motion-reduce:transition-none motion-reduce:active:scale-100"
        >
          Ver o que já existe e o que falta
        </button>
        {onOpenPage ? (
          <button
            type="button"
            onClick={() => onOpenPage(row.task.id)}
            className="inline-flex min-h-10 items-center rounded-md bg-muted px-4 text-sm font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Abrir histórico completo
          </button>
        ) : null}
      </div>
      <details className="mt-4 text-xs text-muted-foreground">
        <summary className="cursor-pointer py-1 font-medium text-foreground">Referência técnica</summary>
        <p className="mt-1 font-mono">{row.task.id} · {row.initiative.id}</p>
      </details>
    </article>
  );
}

function RoadmapByWave({ workRoad, rows, onOpenTask }: {
  workRoad: WorkRoadLive;
  rows: FlatTask[];
  onOpenTask: (id: string) => void;
}) {
  const [expanded, setExpanded] = React.useState<Set<string>>(() => new Set());
  const toggle = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="mt-8 space-y-10">
      {wavesFrom(workRoad).map((wave) => (
        <section key={wave} aria-label={wave}>
          <h3 className="border-b border-border pb-3 font-display text-xl font-semibold">{wave}</h3>
          <div className="divide-y divide-border">
            {workRoad.initiatives
              .filter((initiative) => initiative.wave === wave)
              .sort((a, b) => a.rank - b.rank)
              .map((initiative) => (
                <ExecutiveInitiative
                  key={initiative.id}
                  initiative={initiative}
                  workRoad={workRoad}
                  rows={rows.filter((row) => row.initiative.id === initiative.id)}
                  expanded={expanded.has(initiative.id)}
                  onToggle={() => toggle(initiative.id)}
                  onOpenTask={onOpenTask}
                />
              ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function ExecutiveInitiative({ initiative, workRoad, rows, expanded, onToggle, onOpenTask }: {
  initiative: RoadmapInitiative;
  workRoad: WorkRoadLive;
  rows: FlatTask[];
  expanded: boolean;
  onToggle: () => void;
  onOpenTask: (id: string) => void;
}) {
  const progress = initiativeProgress(initiative, workRoad.status_weights);
  const open = rows.filter((row) => isOpenStatus(row.task.status));
  const visible = expanded ? open : open.slice(0, 3);
  const hidden = open.length - visible.length;

  return (
    <article className="py-6">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_15rem] lg:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <QgStatusMark
              status={open.length === 0 ? "done" : progress.counts.risk > 0 ? "risk" : progress.counts.partial > 0 ? "partial" : "todo"}
              labels={SIMPLE_LABELS}
            />
            <span className="text-xs text-muted-foreground">
              {open.length === 0 ? "nenhuma entrega aberta" : `${open.length} ${open.length === 1 ? "entrega aberta" : "entregas abertas"}`}
            </span>
          </div>
          <h4 className="mt-3 font-display text-xl font-semibold leading-7 text-balance">{initiative.title}</h4>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-foreground/85 text-pretty">{initiative.why}</p>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
            <span className="font-medium text-foreground">Consideramos esta frente pronta quando: </span>
            {initiative.done_when}
          </p>
        </div>
        <div>
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="font-medium text-foreground">Avanço documentado</span>
            <span className="tabular-nums text-muted-foreground">{progress.percent == null ? "desconhecido" : `${progress.percent}%`}</span>
          </div>
          {progress.percent != null ? (
            <div
              className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress.percent}
              aria-label={`${initiative.title}: ${progress.percent} por cento de avanço documentado`}
            >
              <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, Math.max(0, progress.percent))}%` }} />
            </div>
          ) : null}
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {progress.counts.done} prontas · {progress.counts.partial} incompletas · {progress.counts.todo} não iniciadas · {progress.counts.risk} com risco
          </p>
        </div>
      </div>

      {open.length > 0 ? (
        <div className="mt-5">
          <ul className="divide-y divide-border border-y border-border">
            {visible.map((row) => (
              <li key={row.task.id} data-task-id={row.task.id}>
                <button
                  type="button"
                  onClick={() => onOpenTask(row.task.id)}
                  aria-label={`Abrir entrega: ${row.task.title}`}
                  className="grid w-full gap-2 py-3 text-left outline-none transition-colors duration-150 hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring motion-reduce:transition-none sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-foreground">{row.task.title}</span>
                    <span className="mt-1 block max-w-3xl text-xs leading-5 text-muted-foreground">{taskPlainExplanation(row)}</span>
                  </span>
                  <QgStatusMark status={row.task.status} labels={SIMPLE_LABELS} />
                </button>
              </li>
            ))}
          </ul>
          {open.length > 3 ? (
            <button
              type="button"
              aria-expanded={expanded}
              onClick={onToggle}
              className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-md bg-muted px-3 text-sm font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ChevronDown className={cn("h-4 w-4 transition-transform duration-150 motion-reduce:transition-none", expanded && "rotate-180")} aria-hidden />
              {expanded ? "Mostrar menos" : `Mostrar mais ${hidden}`}
            </button>
          ) : null}
        </div>
      ) : (
        <p className="mt-4 text-sm text-success">Todas as entregas desta frente estão concluídas ou foram guardadas para depois.</p>
      )}

      <details className="mt-4 text-xs text-muted-foreground">
        <summary className="cursor-pointer py-1 font-medium text-foreground">Referência técnica da frente</summary>
        <p className="mt-1 font-mono">{initiative.id} · posição {initiative.rank}</p>
      </details>
    </article>
  );
}

function SimpleQueue({ title, empty, testId, rows, role, onOpenTask }: {
  title: string;
  empty: string | null;
  testId: string;
  rows: FlatTask[];
  role: AgoraQueueRole;
  onOpenTask: (id: string) => void;
}) {
  if (rows.length === 0 && empty == null) return null;
  return (
    <section data-testid={rows.length > 0 ? testId : undefined} aria-label={title}>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {rows.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">{empty}</p> : (
        <ul className="mt-2 divide-y divide-border border-y border-border">
          {rows.map((row) => (
            <li key={row.task.id} data-task-id={row.task.id}>
              <button
                type="button"
                onClick={() => onOpenTask(row.task.id)}
                aria-label={`Abrir entrega: ${row.task.title}`}
                className="grid w-full gap-2 py-3 text-left outline-none transition-colors duration-150 hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring motion-reduce:transition-none sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
              >
                <span>
                  <span className="block text-sm font-medium text-foreground">{row.task.title}</span>
                  <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                    {role === "risco"
                      ? "O roadmap registra um risco que precisa ser resolvido ou aceito conscientemente."
                      : role === "bloqueio"
                        ? "Esta entrega depende de outra que ainda está aberta."
                        : taskPlainExplanation(row)}
                  </span>
                </span>
                <QgStatusMark status={row.task.status} labels={SIMPLE_LABELS} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
