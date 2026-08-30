import { CloudOff, GitCommitHorizontal } from "lucide-react";
import type { WorkRoadExecution, WorkRoadExecutionsLive } from "@/features/work-road/live";
import { classifyExecution, executionAgentLabel, isOrphanExecution } from "@/features/work-road/selectors";
import { formatDate, formatTime } from "@/features/work-road/format";
import { QgExecutionMark } from "./QgStatusMark";
import { QgError, QgLoading, QgMissingField, QgNoActiveExecutions, QgStaleBanner } from "./QgStates";

export function QgExecucoes({
  reading,
}: {
  reading: {
    executions: WorkRoadExecutionsLive | null;
    carregando: boolean;
    falhou: boolean;
    desatualizado: boolean;
    erro: string | null;
    recarregar: () => void;
  };
}) {
  if (reading.carregando) return <QgLoading label="Carregando execuções dos agentes" />;
  if (reading.falhou) {
    return (
      <QgError
        title="Não consegui ler as execuções"
        message={reading.erro}
        onRetry={reading.recarregar}
      />
    );
  }
  if (!reading.executions?.available) {
    return (
      <section className="border-y border-border py-8" aria-labelledby="execution-unavailable">
        <CloudOff aria-hidden="true" className="h-5 w-5 text-muted-foreground" />
        <h2 id="execution-unavailable" className="mt-3 font-display text-xl font-semibold">
          Monitor local indisponível
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-foreground/75">
          {reading.executions?.reason || "Este ambiente não expõe as worktrees locais dos agentes."}
        </p>
      </section>
    );
  }

  const live = reading.executions.executions.filter((item) => {
    const kind = classifyExecution(item).kind;
    return kind === "ativo" || kind === "heartbeat_atrasado";
  });
  const orphans = reading.executions.executions.filter(isOrphanExecution);

  return (
    <section aria-labelledby="executions-heading">
      {reading.desatualizado ? (
        <QgStaleBanner
          message="A última leitura de execuções falhou ou envelheceu. O que aparece abaixo pode não ser o instante atual."
          onRetry={reading.recarregar}
        />
      ) : null}
      <div className="flex flex-col gap-4 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Observação local e somente leitura
          </p>
          <h2 id="executions-heading" className="mt-1 font-display text-2xl font-semibold tracking-tight">
            O que os agentes estão registrando
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground text-pretty">
            Um diretório não torna a sessão ativa. Sem processo vivo, a execução é ociosa, concluída ou desatualizada.
          </p>
        </div>
        <div className="text-xs text-muted-foreground lg:text-right">
          <p className="font-medium text-foreground">main · {reading.executions.main_head || "HEAD indisponível"}</p>
          <p className="mt-1">Lido em {formatDate(reading.executions.read_at) || "horário ausente"}</p>
        </div>
      </div>

      <div className="mt-4">
        {live.length === 0 ? <QgNoActiveExecutions /> : null}
        {orphans.length > 0 ? <p className="mt-2 text-sm">Execuções órfãs (sem task_ids): {orphans.length}.</p> : null}
      </div>

      {reading.executions.executions.length === 0 ? (
        <div className="py-12 text-center">
          <p className="text-sm font-medium">Nenhuma worktree agêntica encontrada</p>
          <p className="mt-1 text-xs text-muted-foreground">Quando uma missão isolada nascer, ela aparecerá aqui.</p>
        </div>
      ) : (
        <div className="mt-2">
          {reading.executions.executions.map((execution) => (
            <ExecutionRow key={execution.id} execution={execution} />
          ))}
        </div>
      )}
    </section>
  );
}

function ExecutionRow({ execution }: { execution: WorkRoadExecution }) {
  const classified = classifyExecution(execution);
  const latest = execution.commits[0] ?? null;
  const agent = executionAgentLabel(execution);
  const mission = execution.mission || execution.name;
  const worktree = execution.worktree || execution.id;

  return (
    <article className="border-b border-border py-5 last:border-b-0">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_14rem]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-display text-lg font-semibold capitalize tracking-tight">{mission}</h3>
            <QgExecutionMark kind={classified.kind} />
            <span className="inline-flex min-h-6 items-center rounded-full border border-border px-2 text-[11px] font-semibold">
              {execution.dirty_files > 0 ? `Árvore suja (${execution.dirty_files})` : "Árvore limpa"}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-foreground/80">{classified.why}</p>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <Meta label="Agente / provedor" value={agent} />
            <Meta label="Branch" value={execution.branch || null} />
            <Meta label="Worktree" value={worktree} />
            <Meta label="HEAD" value={execution.head || null} />
            <Meta label="Tarefas" value={(execution.task_ids && execution.task_ids.length > 0) ? execution.task_ids.join(", ") : null} missing="Execução órfã: nenhuma task_id vinculada." />
            <Meta
              label="Heartbeat"
              value={classified.missingHeartbeat ? null : formatTime(execution.heartbeat_at)}
              missing="Execução sem heartbeat na fonte."
            />
          </dl>
        </div>
        <div className="text-sm xl:text-right">
          <p className="text-lg font-semibold tabular-nums">{execution.commits_ahead}</p>
          <p className="mt-1 text-xs text-muted-foreground">commits desde a base. Não é percentual de conclusão.</p>
          {latest ? (
            <p className="mt-3 text-xs text-muted-foreground">
              Último commit em {formatDate(latest.committed_at)}
            </p>
          ) : (
            <p className="mt-3 text-xs text-muted-foreground">Nenhum commit novo desde a separação desta worktree.</p>
          )}
        </div>
      </div>

      <div className="mt-5 grid gap-6 border-t border-border pt-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(16rem,0.7fr)]">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Commits produzidos</p>
          <ol className="mt-2 divide-y divide-border">
            {execution.commits.map((commit) => (
              <li key={commit.sha} className="grid gap-1 py-2.5 sm:grid-cols-[4.5rem_minmax(0,1fr)_auto] sm:items-baseline sm:gap-3">
                <span className="inline-flex items-center gap-1.5 font-mono text-xs text-primary">
                  <GitCommitHorizontal aria-hidden="true" className="h-3.5 w-3.5" />
                  {commit.sha}
                </span>
                <span className="text-sm text-foreground/85">{commit.subject}</span>
                <time className="text-[11px] text-muted-foreground" dateTime={commit.committed_at}>
                  {formatDate(commit.committed_at)}
                </time>
              </li>
            ))}
            {execution.commits.length === 0 ? (
              <li className="py-3 text-sm text-muted-foreground">Sem registros novos.</li>
            ) : null}
          </ol>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Propostas para o Roadmap Vivo
          </p>
          <ul className="mt-2 divide-y divide-border">
            {execution.roadmap_changes.map((change) => (
              <li key={change.task_id} className="py-2.5">
                <p className="font-mono text-xs font-semibold text-primary">{change.task_id}</p>
                <p className="mt-1 text-sm leading-5">{change.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {change.before_status !== change.after_status
                    ? `Estado proposto: ${change.before_status || "novo"} → ${change.after_status || "removido"}`
                    : change.proof_changed
                      ? "Evidência atualizada, sem promover o estado."
                      : "Conteúdo editorial alterado."}
                </p>
              </li>
            ))}
            {execution.roadmap_changes.length === 0 ? (
              <li className="py-3 text-sm text-muted-foreground">Nenhuma mudança proposta na fonte oficial.</li>
            ) : null}
          </ul>
        </div>
      </div>
    </article>
  );
}

function Meta({
  label,
  value,
  missing,
}: {
  label: string;
  value: string | null | undefined;
  missing?: string;
}) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 font-mono text-xs text-foreground/85">
        {value || <QgMissingField>{missing || "Não informado pela fonte."}</QgMissingField>}
      </dd>
    </div>
  );
}
