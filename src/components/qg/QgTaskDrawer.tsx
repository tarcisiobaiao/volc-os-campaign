import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { WorkRoadLive } from "@/features/work-road/live";
import type { FlatTask } from "@/features/work-road/selectors";
import {
  classifyTaskKind,
  declaredDependencies,
  editorialPredecessors,
  evidenceText,
  kindLabel,
  statusLabel,
  textList,
} from "@/features/work-road/selectors";
import { QgCopyId } from "./QgCopyId";
import { QgKindMark, QgStatusMark } from "./QgStatusMark";
import { taskPath } from "@/features/work-road/url-state";
import { QgMissingField } from "./QgStates";

export function QgTaskDrawer({
  row,
  labels,
  open,
  onClose,
}: {
  row: FlatTask | null;
  labels: WorkRoadLive["status_labels"] | null | undefined;
  open: boolean;
  onClose: () => void;
}) {
  const task = row?.task;
  const initiative = row?.initiative;
  const evidence = task ? evidenceText(task) : null;
  const deps = task ? declaredDependencies(task) : null;
  const prior = row ? editorialPredecessors(row) : [];
  const acceptance = task ? textList(task.acceptance) : null;
  const graph = task?.graph_nodes?.length ? task.graph_nodes : initiative?.graph_nodes ?? [];

  return (
    <Sheet open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 overflow-y-auto p-0 sm:max-w-lg"
        aria-describedby="qg-task-drawer-desc"
      >
        {row && task && initiative ? (
          <>
            <SheetHeader className="space-y-3 border-b border-border px-6 py-5 text-left">
              <p className="font-mono text-xs font-semibold text-primary">{task.id}</p>
              <SheetTitle className="font-display text-xl font-semibold leading-7 text-balance">
                {task.title}
              </SheetTitle>
              <SheetDescription id="qg-task-drawer-desc" className="text-pretty">
                Detalhe somente leitura da tarefa no Roadmap Vivo.
              </SheetDescription>
              <div className="flex flex-wrap items-center gap-2">
                <QgStatusMark status={task.status} labels={labels} />
                <QgKindMark label={kindLabel(classifyTaskKind(task.status))} />
              </div>
            </SheetHeader>

            <dl className="grid gap-5 px-6 py-5 text-sm">
              <Fact label="Iniciativa">
                {initiative.id} · {initiative.title}
              </Fact>
              <Fact label="Onda">{initiative.wave}</Fact>
              <Fact label="Prioridade / rank">
                Rank {initiative.rank} na fonte viva.
              </Fact>
              <Fact label="Estado">
                {statusLabel(task.status, labels)}
              </Fact>
              <Fact label="Explicação">
                {task.explanation?.trim() ? (
                  task.explanation
                ) : (
                  <QgMissingField>
                    A fonte não envia explicação própria desta tarefa. O motivo da iniciativa: {initiative.why}
                  </QgMissingField>
                )}
              </Fact>
              <Fact label="Aceite">
                {acceptance ? (
                  <ul className="list-disc space-y-1 pl-4">
                    {acceptance.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                ) : (
                  <QgMissingField>
                    Aceite da tarefa não declarado. Pronto da iniciativa: {initiative.done_when}
                  </QgMissingField>
                )}
              </Fact>
              <Fact label="Dependências">
                {deps && deps.length > 0 ? (
                  <ul className="list-disc space-y-1 pl-4">
                    {deps.map((item) => <li key={item} className="font-mono text-xs">{item}</li>)}
                  </ul>
                ) : (
                  <QgMissingField>A fonte não declara dependências desta tarefa.</QgMissingField>
                )}
              </Fact>
              {prior.length > 0 && !deps ? (
                <Fact label="Ordem editorial">
                  Anterior na ordem editorial, sem prova de dependência: {prior.map((item) => item.id).join(", ")}.
                </Fact>
              ) : null}
              <Fact label="Evidência">
                {evidence ? (
                  evidence
                ) : (
                  <QgMissingField>Tarefa sem evidência na fonte.</QgMissingField>
                )}
              </Fact>
              <Fact label="Grafo">
                {graph.length > 0 ? (
                  <ul className="flex flex-wrap gap-1.5">
                    {graph.map((node) => (
                      <li key={node} className="rounded-full border border-border px-2 py-0.5 font-mono text-[11px]">
                        {node}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <QgMissingField>Nenhum nó de grafo veio nesta leitura.</QgMissingField>
                )}
              </Fact>
            </dl>

            <div className="mt-auto flex flex-wrap items-center gap-3 border-t border-border px-6 py-4">
              <QgCopyId value={task.id} />
              <Link
                to={taskPath(task.id)}
                className="inline-flex min-h-10 items-center text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Página completa {task.id}
              </Link>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</dt>
      <dd className="mt-1 leading-6 text-foreground/90">{children}</dd>
    </div>
  );
}
