import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { WorkRoadExecution, WorkRoadLive } from "@/features/work-road/live";
import type { FlatTask } from "@/features/work-road/selectors";
import { KANBAN_COLUMNS, sortBySourceRank, uniqueTaskIds } from "@/features/work-road/selectors";
import { copyText } from "@/features/work-road/copy-id";
import { pautadorApi } from "@/lib/pautadorApi";
import { QgTaskCard } from "./QgTaskCard";

/**
 * Controles compactos de reordenação. Alvo móvel de 44px (WCAG 2.5.8),
 * nome acessível claro, disabled correto nos limites da iniciativa.
 */
function ReorderControl({
  taskId,
  initiativeId,
  direction,
  disabled,
  onMove,
}: {
  taskId: string;
  initiativeId: string;
  direction: "up" | "down";
  disabled: boolean;
  onMove: () => void;
}) {
  const label = direction === "up" ? `Subir ${taskId}` : `Descer ${taskId}`;
  const Icon = direction === "up" ? ChevronUp : ChevronDown;
  return (
    <button
      type="button"
      aria-label={label}
      title={`${label} na ordem da iniciativa ${initiativeId}`}
      disabled={disabled}
      onClick={onMove}
      className="inline-flex h-11 w-11 items-center justify-center text-muted-foreground outline-none transition-colors duration-150 hover:bg-muted/60 hover:text-foreground focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-40 motion-reduce:transition-none"
    >
      <Icon aria-hidden="true" className="h-4 w-4" />
    </button>
  );
}

export function QgKanban({
  workRoad,
  rows,
  executions,
}: {
  workRoad: WorkRoadLive;
  rows: FlatTask[];
  executions: WorkRoadExecution[];
}) {
  const ordered = sortBySourceRank(rows);
  const ids = uniqueTaskIds(ordered);
  const [draft, setDraft] = React.useState<Record<string, string[]>>({});
  const [receipt, setReceipt] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);
  const [announcement, setAnnouncement] = React.useState<string | null>(null);
  const client = useQueryClient();

  const columns = KANBAN_COLUMNS.map((item) => ({
    ...item,
    cards: ordered.filter((row) => row.task.status === item.id),
  }));

  const proposal = Object.entries(draft).map(([initiativeId, taskIds]) => ({ initiativeId, taskIds }));

  const currentOrderFor = (initiativeId: string): string[] =>
    draft[initiativeId]
      ?? ordered.filter((row) => row.initiative.id === initiativeId).map((row) => row.task.id);

  const moveInInitiative = (initiativeId: string, taskId: string, delta: number) => {
    const current = currentOrderFor(initiativeId);
    const index = current.indexOf(taskId);
    const nextIndex = index + delta;
    if (index < 0 || nextIndex < 0 || nextIndex >= current.length) return;
    const next = [...current];
    const [removed] = next.splice(index, 1);
    next.splice(nextIndex, 0, removed);
    setDraft((prev) => ({ ...prev, [initiativeId]: next }));
    setAnnouncement(
      `Tarefa ${taskId} ${delta < 0 ? "subiu" : "desceu"} na proposta da iniciativa ${initiativeId}.`,
    );
  };

  const confirm = async () => {
    setPending(true);
    setError(null);
    try {
      let expectedSha256 = workRoad.source.sha256;
      for (const item of proposal) {
        const result = await pautadorApi.confirmWorkRoadOrder(
          item.initiativeId,
          item.taskIds,
          expectedSha256,
        ) as { receipt?: { after_sha256?: string } };
        expectedSha256 = result.receipt?.after_sha256 || expectedSha256;
      }
      setDraft({});
      setReceipt("Nova ordem gravada na fonte. As visões vão reler o Roadmap Vivo.");
      await client.invalidateQueries({ queryKey: ["work-road", "live"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível gravar a ordem.");
    } finally {
      setPending(false);
    }
  };

  return (
    <section aria-labelledby="qg-kanban-heading">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Estados da fonte</p>
      <h2 id="qg-kanban-heading" className="mt-1 font-display text-2xl font-semibold tracking-tight">
        Kanban da fonte
      </h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
        As colunas são o estado editorial. Execução de agente é um indicador no card, não uma coluna.
        Arrastar no navegador não altera a autoridade. Use subir/descer e confirme.
        Em telas estreitas o board rola horizontalmente; nenhuma coluna é comprimida abaixo do legível.
      </p>
      <p className="sr-only" role="status">{announcement}</p>
      {ids.length !== ordered.length ? (
        <p className="mt-3 text-sm text-destructive" role="alert">A fonte devolveu IDs repetidos. O Kanban recusou duplicar cards.</p>
      ) : null}

      <div
        role="region"
        aria-label="Board do Kanban: colunas por estado editorial. Role horizontalmente para ver todas as colunas."
        tabIndex={0}
        className="mt-5 overflow-x-auto pb-1 outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <div className="flex items-start gap-4">
          {columns.map((item) => (
            <section
              key={item.id}
              data-testid={`qg-kanban-${item.id}`}
              aria-labelledby={`kanban-${item.id}`}
              className="w-72 shrink-0 rounded-lg border border-border bg-muted/50"
            >
              <header className="flex items-center justify-between gap-2 border-b border-border px-3 py-2.5">
                <h3 id={`kanban-${item.id}`} className="text-sm font-semibold text-foreground">
                  {item.title}
                </h3>
                <span className="rounded-full bg-card px-2 py-0.5 text-xs font-semibold tabular-nums text-muted-foreground">
                  {item.cards.length}
                </span>
              </header>
              {item.cards.length === 0 ? (
                <p className="px-3 py-4 text-sm text-muted-foreground">Nenhuma tarefa neste estado.</p>
              ) : (
                <ul className="space-y-3 p-3">
                  {item.cards.map((row) => {
                    const current = currentOrderFor(row.initiative.id);
                    const index = current.indexOf(row.task.id);
                    const canUp = index > 0;
                    const canDown = index >= 0 && index < current.length - 1;
                    return (
                      <li key={row.task.id} data-task-id={row.task.id} className="space-y-2">
                        <QgTaskCard row={row} labels={workRoad.status_labels} executions={executions} compact />
                        <div className="flex justify-end px-1">
                          <div className="inline-flex overflow-hidden rounded-md border border-input">
                            <ReorderControl
                              taskId={row.task.id}
                              initiativeId={row.initiative.id}
                              direction="up"
                              disabled={!canUp}
                              onMove={() => moveInInitiative(row.initiative.id, row.task.id, -1)}
                            />
                            <span aria-hidden="true" className="w-px self-stretch bg-border" />
                            <ReorderControl
                              taskId={row.task.id}
                              initiativeId={row.initiative.id}
                              direction="down"
                              disabled={!canDown}
                              onMove={() => moveInInitiative(row.initiative.id, row.task.id, 1)}
                            />
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          ))}
        </div>
      </div>

      {proposal.length > 0 ? (
        <div className="mt-6 border-t border-border pt-4">
          <h3 className="font-display text-lg font-semibold">Proposta de nova ordem</h3>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
            A confirmação grava a sequência das iniciativas tocadas na fonte, com conflito protegido pelo sha256 da leitura.
          </p>
          <ul className="mt-3 divide-y divide-border overflow-hidden rounded-lg border border-border bg-card">
            {proposal.map((item) => (
              <li key={item.initiativeId} className="flex flex-col gap-1 px-3 py-2.5 text-sm sm:flex-row sm:items-center sm:gap-3">
                <span className="font-mono text-xs font-semibold text-primary">{item.initiativeId}</span>
                <span className="min-w-0 text-foreground/80 break-words">{item.taskIds.join(" → ")}</span>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => { void confirm(); }}
              disabled={pending}
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-transform duration-150 ease-out active:scale-[0.96] hover:bg-primary/90 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 motion-reduce:transition-none motion-reduce:active:scale-100"
            >
              {pending ? "Gravando" : "Confirmar nova ordem"}
            </button>
            <button
              type="button"
              onClick={() => { void copyText(JSON.stringify(proposal, null, 2)); }}
              className="inline-flex min-h-11 items-center rounded-md border border-input px-4 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Copiar proposta
            </button>
          </div>
          {error ? <p className="mt-2 text-sm text-destructive" role="alert">{error} Em modo leitura, copie a proposta.</p> : null}
          {receipt ? <p className="mt-2 text-sm text-foreground" role="status">{receipt}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
