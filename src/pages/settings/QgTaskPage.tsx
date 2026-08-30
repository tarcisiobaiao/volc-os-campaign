import type { ReactNode } from "react";
import type { WorkRoadExecution } from "@/features/work-road/live";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { QgCopyId } from "@/components/qg/QgCopyId";
import { QgKindMark, QgStatusMark } from "@/components/qg/QgStatusMark";
import { QgError, QgLoading, QgMissingField, QgStaleBanner } from "@/components/qg/QgStates";
import { copyText } from "@/features/work-road/copy-id";
import { formatDate } from "@/features/work-road/format";
import { adkRunCommand, buildAdkManifest, buildMissionPrompt, manifestHasSecrets } from "@/features/work-road/mission";
import {
  classifyTaskKind,
  declaredDependencies,
  editorialPredecessors,
  evidenceText,
  flattenTasks,
  kindLabel,
  executionsForTask,
  openDeclaredDependencies,
  statusLabel,
  textList,
} from "@/features/work-road/selectors";
import { useWorkRoad } from "@/features/work-road/useWorkRoad";
import { useWorkRoadExecutions } from "@/features/work-road/useWorkRoadExecutions";

export function QgTaskPage() {
  const { taskId = "" } = useParams();
  const navigate = useNavigate();
  const reading = useWorkRoad();
  const executions = useWorkRoadExecutions(true);
  const rows = flattenTasks(reading.workRoad);
  const row = rows.find((item) => item.task.id === taskId) ?? null;

  return (
    <Layout>
      <div className="mx-auto w-full max-w-3xl overflow-x-hidden px-4 py-6 sm:px-6 lg:py-8">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          <Link to="/settings/qg-agentico" className="underline-offset-2 hover:underline">QG Operacional</Link>
          {" / "}tarefa
        </p>
        {reading.carregando ? <QgLoading /> : null}
        {reading.falhou ? (
          <QgError title="Não consegui ler o Roadmap Vivo" message={reading.erro} onRetry={reading.recarregar} />
        ) : null}
        {reading.desatualizado ? (
          <QgStaleBanner message="A leitura envelheceu. O detalhe abaixo é a última fotografia válida." onRetry={reading.recarregar} />
        ) : null}
        {reading.workRoad && !row ? (
          <section className="mt-8" role="status" data-testid="qg-task-404">
            <h1 className="font-display text-3xl font-semibold">Tarefa não encontrada</h1>
            <p className="mt-3 text-sm leading-6 text-foreground/80">
              A fonte viva não contém a tarefa {taskId}. Isso é um 404, não uma lista vazia.
            </p>
            <button type="button" className="mt-4 min-h-10 text-sm underline" onClick={() => navigate("/settings/qg-agentico")}>
              Voltar ao QG
            </button>
          </section>
        ) : null}
        {row && reading.workRoad ? <TaskBody row={row} catalog={rows} labels={reading.workRoad.status_labels} source={reading.workRoad.source} head={executions.executions?.main_head ?? null} executions={executions.executions?.executions ?? []} /> : null}
      </div>
    </Layout>
  );
}

function TaskBody({
  row,
  catalog,
  labels,
  source,
  head,
  executions,
}: {
  row: ReturnType<typeof flattenTasks>[number];
  catalog: ReturnType<typeof flattenTasks>;
  labels: Record<string, string>;
  source: { path: string; sha256: string; read_at: string };
  head: string | null;
  executions: WorkRoadExecution[];
}) {
  const task = row.task;
  const deps = declaredDependencies(task);
  const openDeclared = openDeclaredDependencies(row, catalog);
  const acceptance = textList(task.acceptance);
  const prompt = task.prompt_template?.trim() || buildMissionPrompt(row);
  const manifest = buildAdkManifest(row, head);
  const manifestText = JSON.stringify(manifest, null, 2);
  const command = adkRunCommand(`tools/agent-harness/missions/${manifest.mission_id}.json`);
  const prior = editorialPredecessors(row);
  const linked = executionsForTask(task.id, executions);

  return (
    <article className="mt-4 space-y-8">
      <header>
        <p className="font-mono text-xs font-semibold text-primary">{task.id}</p>
        <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-balance">{task.title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <QgStatusMark status={task.status} labels={labels} />
          <QgKindMark label={kindLabel(classifyTaskKind(task.status))} />
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          {row.initiative.id} · {row.initiative.title} · {row.initiative.wave} · rank {row.initiative.rank}
          {task.owner ? ` · owner ${task.owner}` : " · owner não declarado"}
          {task.priority != null ? ` · prioridade ${task.priority}` : " · prioridade não declarada"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Fonte {source.path} · hash {source.sha256.slice(0, 12)} · lida em {formatDate(source.read_at) || "ausente"}
          {task.updated_at ? ` · tarefa ${task.updated_at}` : ""}
        </p>
        <div className="mt-4"><QgCopyId value={task.id} /></div>
      </header>

      <section>
        <h2 className="font-display text-xl font-semibold">Explicação simples</h2>
        <dl className="mt-3 space-y-3 text-sm leading-6">
          <Fact label="O que é">{task.explanation?.trim() || <QgMissingField>A fonte não envia explicação própria desta tarefa.</QgMissingField>}</Fact>
          <Fact label="Por que importa">{row.initiative.why}</Fact>
          <Fact label="Qual problema resolve">{row.initiative.done_when}</Fact>
          <Fact label="O que já existe">{evidenceText(task) || <QgMissingField>Tarefa sem evidência na fonte.</QgMissingField>}</Fact>
          <Fact label="O que falta">{acceptance ? <ul className="list-disc pl-4">{acceptance.map((item) => <li key={item}>{item}</li>)}</ul> : <QgMissingField>Aceite da tarefa não declarado.</QgMissingField>}</Fact>
          <Fact label="O que não faz parte">Conversa, captura no Inbox e ordem editorial não viram aceite sozinhas.</Fact>
        </dl>
      </section>

      <section>
        <h2 className="font-display text-xl font-semibold">Checklist</h2>
        {task.checklist && task.checklist.length > 0 ? (
          <ul className="mt-3 divide-y divide-border border-y border-border">
            {task.checklist.map((item) => (
              <li key={item.id} className="py-3 text-sm">
                <p className="font-medium">{item.done ? "Feito" : "Aberto"} · {item.description}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Prova: {item.proof || "ausente"} · Aceite: {item.acceptance || "ausente"}
                  {item.owner ? ` · ${item.owner}` : ""}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <QgMissingField>Checklist ainda não documentado.</QgMissingField>
        )}
      </section>

      <section>
        <h2 className="font-display text-xl font-semibold">Dependências e riscos</h2>
        {deps ? (
          <ul className="mt-3 text-sm">
            {deps.map((id) => {
              const found = catalog.find((item) => item.task.id === id);
              const blocks = openDeclared.some((item) => item.task.id === id);
              return (
                <li key={id} className="py-2">
                  <Link className="font-mono text-primary underline-offset-2 hover:underline" to={`/settings/qg-agentico/tarefas/${id}`}>{id}</Link>
                  {" · "}
                  {found ? statusLabel(found.task.status, labels) : "fora do catálogo visível"}
                  {blocks ? " · bloqueia porque continua aberta" : " · não bloqueia (concluída, reservada ou ausente)"}
                </li>
              );
            })}
          </ul>
        ) : (
          <QgMissingField>A fonte não declara dependências desta tarefa.</QgMissingField>
        )}
        {prior.length > 0 && !deps ? (
          <p className="mt-2 text-sm text-muted-foreground">
            Anterior na ordem editorial, sem prova de dependência: {prior.map((item) => item.id).join(", ")}.
          </p>
        ) : null}
      </section>

      <section>
        <h2 className="font-display text-xl font-semibold">Evidências e referências</h2>
        {task.links && task.links.length > 0 ? (
          <ul className="mt-3 space-y-2 text-sm">
            {task.links.map((link) => (
              <li key={`${link.kind}:${link.value}`}>
                <span className="text-xs uppercase tracking-wide text-muted-foreground">{link.kind}</span>{" "}
                {link.label}: {link.value}
                {link.kind === "path" ? (
                  <button type="button" className="ml-2 min-h-10 text-xs underline" onClick={() => { void copyText(link.value); }}>
                    Copiar caminho
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <QgMissingField>Nenhum link declarado. Evidência textual: {task.proof || "ausente"}.</QgMissingField>
        )}
      </section>

      <section>
        <h2 className="font-display text-xl font-semibold">Nós do grafo</h2>
        {(task.graph_nodes && task.graph_nodes.length > 0) || row.initiative.graph_nodes.length > 0 ? (
          <p className="mt-2 font-mono text-xs">{(task.graph_nodes && task.graph_nodes.length > 0 ? task.graph_nodes : row.initiative.graph_nodes).join(", ")}</p>
        ) : (
          <QgMissingField>Nenhum nó de grafo veio nesta leitura.</QgMissingField>
        )}
      </section>

      <section>
        <h2 className="font-display text-xl font-semibold">Execuções vinculadas</h2>
        {linked.length > 0 ? (
          <ul className="mt-2 text-sm">
            {linked.map((item) => (
              <li key={item.id} className="py-1">{item.mission || item.name} · {item.task_ids?.join(", ")}</li>
            ))}
          </ul>
        ) : (
          <QgMissingField>Nenhuma execução vinculada a esta task_id.</QgMissingField>
        )}
      </section>

      <section>
        <h2 className="font-display text-xl font-semibold">Prompt pronto</h2>
        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-4 text-xs leading-5">{prompt}</pre>
        <button type="button" className="mt-3 inline-flex min-h-10 items-center rounded-md border border-input px-4 text-sm" onClick={() => { void copyText(prompt); }}>
          Copiar prompt da missão
        </button>
      </section>

      <section>
        <h2 className="font-display text-xl font-semibold">Missão ADK</h2>
        {manifestHasSecrets(manifestText) ? (
          <p className="mt-2 text-sm text-destructive">O manifesto gerado continha padrão de segredo e foi recusado.</p>
        ) : (
          <>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-4 text-xs leading-5">{manifestText}</pre>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="inline-flex min-h-10 items-center rounded-md border border-input px-4 text-sm" onClick={() => { void copyText(manifestText); }}>
                Copiar manifesto
              </button>
              <a
                className="inline-flex min-h-10 items-center rounded-md border border-input px-4 text-sm"
                href={`data:application/json,${encodeURIComponent(manifestText)}`}
                download={`${manifest.mission_id}.json`}
              >
                Baixar manifesto
              </a>
            </div>
            <pre className="mt-4 overflow-x-auto text-xs leading-5">{command}</pre>
            <button type="button" className="mt-2 inline-flex min-h-10 items-center rounded-md border border-input px-4 text-sm" onClick={() => { void copyText(command); }}>
              Copiar comando
            </button>
          </>
        )}
      </section>
    </article>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-1">{children}</dd>
    </div>
  );
}

export default QgTaskPage;
