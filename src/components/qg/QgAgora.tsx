import type { WorkRoadExecutionsLive, WorkRoadLive } from "@/features/work-road/live";
import type { AgoraQueueRole, FlatTask } from "@/features/work-road/selectors";
import {
  agoraQueues,
  classifyExecution,
  classifyTaskKind,
  evidenceText,
  executionAgentLabel,
  kindLabel,
  reasonForNow,
} from "@/features/work-road/selectors";
import { QgCopyId } from "./QgCopyId";
import { QgExecutionMark, QgKindMark, QgStatusMark } from "./QgStatusMark";
import { QgMissingField, QgNoActiveExecutions } from "./QgStates";

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
  const { next, reason, authority, risks, blocked, partials, upcoming } = agoraQueues(rows);
  const liveExecutions = (executions?.executions ?? []).filter((item) => {
    const kind = classifyExecution(item).kind;
    return kind === "ativo" || kind === "heartbeat_atrasado";
  });

  return (
    <div className="space-y-10">
      <section aria-labelledby="qg-next">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">O que fazer agora</p>
        <h2 id="qg-next" className="mt-1 font-display text-2xl font-semibold tracking-tight text-balance">
          Próxima tarefa recomendada
        </h2>
        {next ? (
          <article data-testid="qg-agora-proxima" className="mt-5 border-y border-border py-5">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-mono text-xs font-semibold text-primary">{next.task.id}</p>
              <QgStatusMark status={next.task.status} labels={workRoad.status_labels} />
              <QgKindMark label={kindLabel(classifyTaskKind(next.task.status))} />
            </div>
            <h3 className="mt-3 font-display text-xl font-semibold leading-7 text-balance">{next.task.title}</h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-foreground/80 text-pretty">{reason}</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Autoridade usada: {authority ?? "ausente"}. Proximidade editorial não é dependência.
            </p>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
              Terminar significa: {next.task.acceptance ? (Array.isArray(next.task.acceptance) ? next.task.acceptance.join("; ") : next.task.acceptance) : next.initiative.done_when}
              {next.task.acceptance ? "" : " (aceite da tarefa ausente; vale o pronto da iniciativa)."}
            </p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              {next.initiative.title} · {next.initiative.id} · rank {next.initiative.rank} · {next.initiative.wave}
            </p>
            <div className="mt-4 max-w-3xl text-sm leading-6">
              {evidenceText(next.task) ? (
                <p><span className="font-medium text-foreground">Evidência: </span>{next.task.proof}</p>
              ) : (
                <QgMissingField>Tarefa sem evidência na fonte.</QgMissingField>
              )}
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onOpenTask(next.task.id)}
                className="inline-flex min-h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-transform duration-150 ease-out active:scale-[0.96] hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 motion-reduce:transition-none motion-reduce:active:scale-100"
              >
                Abrir tarefa {next.task.id}
              </button>
              <QgCopyId value={next.task.id} />
              {onOpenPage ? (
                <button
                  type="button"
                  onClick={() => onOpenPage(next.task.id)}
                  className="inline-flex min-h-10 items-center rounded-md border border-input px-4 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Página completa {next.task.id}
                </button>
              ) : null}
            </div>
          </article>
        ) : (
          <p className="mt-4 text-sm text-foreground">{reason}</p>
        )}
      </section>

      <section aria-labelledby="qg-now-exec">
        <h2 id="qg-now-exec" className="font-display text-xl font-semibold tracking-tight">
          Em execução por agentes
        </h2>
        <div className="mt-4 space-y-3">
          {liveExecutions.length === 0 ? <QgNoActiveExecutions /> : null}
          {liveExecutions.map((execution) => {
            const classified = classifyExecution(execution);
            return (
              <article key={execution.id} className="border-b border-border py-3 last:border-b-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-medium capitalize">{execution.mission || execution.name}</h3>
                  <QgExecutionMark kind={classified.kind} />
                </div>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  {executionAgentLabel(execution)} · {execution.branch || "branch ausente"}
                </p>
              </article>
            );
          })}
        </div>
      </section>

      <NowList
        title="Riscos e bloqueadores"
        description="Só o que a fonte marcou com risco. O restante da sala permanece calmo."
        testId="qg-agora-fila-risco"
        rows={risks}
        labels={workRoad.status_labels}
        role="risco"
        onOpenTask={onOpenTask}
      />

      <NowList
        title="O que impede avanço"
        description="Só tarefas com dependência declarada ainda aberta. Ordem editorial não prova bloqueio."
        testId="qg-agora-fila-bloqueio"
        rows={blocked}
        labels={workRoad.status_labels}
        role="bloqueio"
        onOpenTask={onOpenTask}
      />

      <NowList
        title="Próximas 3 a 5 tarefas"
        description="Ordem da fonte, sem repetir a tarefa dominante."
        testId="qg-agora-fila-prioridade"
        rows={upcoming}
        labels={workRoad.status_labels}
        role="prioridade"
        onOpenTask={onOpenTask}
      />

      <NowList
        title="Parciais próximas de conclusão"
        description="Já há trabalho; falta o aceite. Não são concluídas. Não repetem a tarefa dominante."
        testId="qg-agora-fila-parcial"
        rows={partials}
        labels={workRoad.status_labels}
        role="parcial"
        onOpenTask={onOpenTask}
      />
    </div>
  );
}

function NowList({
  title,
  description,
  testId,
  rows,
  labels,
  role,
  onOpenTask,
}: {
  title: string;
  description: string;
  testId: string;
  rows: FlatTask[];
  labels: WorkRoadLive["status_labels"];
  role: AgoraQueueRole;
  onOpenTask: (id: string) => void;
}) {
  if (rows.length === 0) return null;
  const headingId = `qg-now-${testId}`;
  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId} className="font-display text-xl font-semibold tracking-tight text-balance">
        {title}
      </h2>
      <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">{description}</p>
      <ul data-testid={testId} className="mt-4 divide-y divide-border border-y border-border">
        {rows.map((row) => (
          <li key={row.task.id} data-task-id={row.task.id}>
            <button
              type="button"
              onClick={() => onOpenTask(row.task.id)}
              aria-label={`Abrir tarefa ${row.task.id}: ${row.task.title}`}
              className="grid w-full gap-2 py-3 text-left outline-none transition-colors duration-150 hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring motion-reduce:transition-none sm:grid-cols-[7.5rem_minmax(0,1fr)_auto] sm:items-start"
            >
              <span className="font-mono text-xs font-semibold text-primary">{row.task.id}</span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">{row.task.title}</span>
                <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                  {reasonForNow(row, role)}
                </span>
              </span>
              <QgStatusMark status={row.task.status} labels={labels} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
