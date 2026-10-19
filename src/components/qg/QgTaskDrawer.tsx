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
  plainStatusLabels,
  statusLabel,
  taskPlainExplanation,
  taskRemaining,
} from "@/features/work-road/selectors";
import { QgKindMark, QgStatusMark } from "./QgStatusMark";
import { taskPath } from "@/features/work-road/url-state";
import { QgMissingField } from "./QgStates";

export function QgTaskDrawer({
  row,
  labels: _labels,
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
  const acceptance = task ? taskRemaining(task) : null;
  const graph = task?.graph_nodes?.length ? task.graph_nodes : initiative?.graph_nodes ?? [];

  return (
    <Sheet open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 overflow-y-auto p-0 sm:max-w-lg"
        aria-describedby="qg-task-drawer-desc"
      >
        <SheetDescription id="qg-task-drawer-desc" className="sr-only">
          O que esta entrega resolve, o que já existe e o que ainda falta.
        </SheetDescription>
        {row && task && initiative ? (
          <>
            <SheetHeader className="space-y-3 border-b border-border px-6 py-5 text-left">
              <SheetTitle className="font-display text-xl font-semibold leading-7 text-balance">
                {task.title}
              </SheetTitle>
              <p className="text-sm text-muted-foreground text-pretty">
                O que esta entrega resolve, o que já existe e o que ainda falta.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <QgStatusMark status={task.status} labels={plainStatusLabels()} />
                <QgKindMark label={kindLabel(classifyTaskKind(task.status))} />
              </div>
            </SheetHeader>

            <dl className="grid gap-5 px-6 py-5 text-sm">
              <Fact label="Iniciativa">
                {initiative.title}
              </Fact>
              <Fact label="Estado">
                {statusLabel(task.status, plainStatusLabels())}
              </Fact>
              <Fact label="O que é">
                {taskPlainExplanation(row)}
              </Fact>
              <Fact label="O que falta para considerar pronto">
                {acceptance ? (
                  <ul className="list-disc space-y-1 pl-4">
                    {acceptance.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                ) : (
                  <QgMissingField>
                    O critério final desta entrega ainda não foi descrito em linguagem simples. Pronto da frente: {initiative.done_when}
                  </QgMissingField>
                )}
              </Fact>
              <Fact label="O que pode impedir o avanço">
                {deps && deps.length > 0 ? (
                  <ul className="list-disc space-y-1 pl-4">
                    {deps.map((item) => <li key={item}>Existe uma entrega anterior ainda aberta. A referência técnica é {item}.</li>)}
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
              <Fact label="O que já existe">
                {evidence ? (
                  evidence
                ) : (
                  <QgMissingField>Tarefa sem evidência na fonte.</QgMissingField>
                )}
              </Fact>
            </dl>

            <details className="mx-6 mb-5 border-y border-border py-3 text-xs text-muted-foreground">
              <summary className="cursor-pointer font-medium text-foreground">Detalhes técnicos e rastreabilidade</summary>
              <dl className="mt-3 space-y-2">
                <div><dt className="inline font-medium">Referência: </dt><dd className="inline font-mono">{task.id}</dd></div>
                <div><dt className="inline font-medium">Frente: </dt><dd className="inline font-mono">{initiative.id} · posição {initiative.rank} · {initiative.wave}</dd></div>
                <div><dt className="inline font-medium">Nós do grafo: </dt><dd className="inline font-mono">{graph.length > 0 ? graph.join(", ") : "não declarados"}</dd></div>
              </dl>
            </details>

            <div className="mt-auto flex flex-wrap items-center gap-3 border-t border-border px-6 py-4">
              <Link
                to={taskPath(task.id)}
                className="inline-flex min-h-10 items-center text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Abrir histórico completo
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
