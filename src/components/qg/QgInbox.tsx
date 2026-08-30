import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { InboxEntry, InboxLive, WorkRoadExecution } from "@/features/work-road/live";
import { isOrphanExecution } from "@/features/work-road/selectors";
import { pautadorApi } from "@/lib/pautadorApi";
import { QgError, QgLoading, QgMissingField, QgStaleBanner } from "./QgStates";

export function QgInbox({
  inbox,
  carregando,
  falhou,
  desatualizado,
  erro,
  recarregar,
  executions,
}: {
  inbox: InboxLive | null;
  carregando: boolean;
  falhou: boolean;
  desatualizado: boolean;
  erro: string | null;
  recarregar: () => void;
  executions: WorkRoadExecution[];
}) {
  const [title, setTitle] = React.useState("");
  const [original, setOriginal] = React.useState("");
  const [receipt, setReceipt] = React.useState<string | null>(null);
  const [fail, setFail] = React.useState<string | null>(null);
  const client = useQueryClient();
  const orphans = executions.filter(isOrphanExecution);

  if (carregando) return <QgLoading label="Carregando o Inbox do Roadmap" />;
  if (falhou) {
    return <QgError title="Não consegui ler o Inbox" message={erro} onRetry={recarregar} />;
  }

  const onCapture = async (event: React.FormEvent) => {
    event.preventDefault();
    setFail(null);
    try {
      const result = await pautadorApi.captureInbox({ title, original, origin: "usuario" });
      setReceipt(
        `Entrada ${result.receipt.id} capturada em ${result.receipt.captured_at}. Origem ${result.receipt.origin}. Estado capturada. Hash ${result.receipt.sha256}. Ainda não foi adicionada ao roadmap.`,
      );
      setTitle("");
      setOriginal("");
      await client.invalidateQueries({ queryKey: ["work-road", "inbox"] });
    } catch (err) {
      setFail(err instanceof Error ? err.message : "Falha ao capturar.");
    }
  };

  return (
    <section aria-labelledby="qg-inbox-heading" className="space-y-8">
      {desatualizado ? (
        <QgStaleBanner message="A leitura do Inbox envelheceu. O que está na tela é a última fotografia válida." onRetry={recarregar} />
      ) : null}
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Fila anterior ao roadmap</p>
        <h2 id="qg-inbox-heading" className="mt-1 font-display text-2xl font-semibold tracking-tight">
          Inbox do Roadmap
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground text-pretty">
          {inbox?.disclaimer || "Conversa não vira tarefa sozinha. Capturada não pertence ao percentual."}
        </p>
      </div>

      <section aria-labelledby="qg-coverage" className="border-y border-border py-5">
        <h3 id="qg-coverage" className="font-display text-lg font-semibold">Cobertura</h3>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <CoverageStat label="Capturadas" value={inbox?.summary?.capturadas} />
          <CoverageStat label="Aguardando triagem" value={inbox?.summary?.aguardando_triagem} />
          <CoverageStat label="Promovidas" value={inbox?.summary?.promovidas} />
          <CoverageStat label="Possíveis duplicatas" value={inbox?.summary?.possiveis_duplicatas ?? inbox?.summary?.duplicadas} />
          <CoverageStat label="Execuções sem tarefa" value={orphans.length} />
        </dl>
        <p className="mt-3 text-xs text-muted-foreground">Esta conversa não foi capturada retroativamente.</p>
        <ul className="mt-4 divide-y divide-border border-y border-border">
          {(inbox?.coverage?.themes ?? []).map((theme) => (
            <li key={theme.id} className="py-2 text-sm">
              <span className="font-medium">{theme.title}</span>
              <span className="mt-1 block text-xs text-muted-foreground">
                {theme.related_task_ids.length > 0
                  ? `Relacionada a ${theme.related_task_ids.join(", ")}`
                  : theme.inbox_id
                    ? `Lacuna no Inbox: ${theme.inbox_id}`
                    : "Sem relação verificável"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <form onSubmit={(event) => { void onCapture(event); }} className="max-w-xl space-y-3">
        <h3 className="font-display text-lg font-semibold">Capturar nova ideia</h3>
        <p className="text-sm text-muted-foreground">Não é preciso decidir a arquitetura agora. Depois de gravar, o estado será capturada, não tarefa.</p>
        <label className="block text-sm font-medium" htmlFor="inbox-title">Título</label>
        <input id="inbox-title" value={title} onChange={(event) => setTitle(event.target.value)} required minLength={3} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <label className="block text-sm font-medium" htmlFor="inbox-original">Descrição original</label>
        <textarea id="inbox-original" value={original} onChange={(event) => setOriginal(event.target.value)} required rows={4} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <button type="submit" className="inline-flex min-h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-transform duration-150 ease-out active:scale-[0.96] motion-reduce:transition-none">
          Capturar ideia
        </button>
        {receipt ? <p className="text-sm text-foreground" role="status">{receipt}</p> : null}
        {fail ? <p className="text-sm text-destructive" role="alert">{fail}</p> : null}
      </form>

      <ul className="divide-y divide-border border-y border-border">
        {(inbox?.entries ?? []).map((entry) => (
          <InboxRow key={entry.id} entry={entry} />
        ))}
      </ul>
      {(inbox?.entries ?? []).length === 0 ? <QgMissingField>O Inbox está vazio. Isso é ausência de captura, não zero do roadmap.</QgMissingField> : null}
    </section>
  );
}

function CoverageStat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums">{value == null ? "ausente" : value}</dd>
    </div>
  );
}

function InboxRow({ entry }: { entry: InboxEntry }) {
  return (
    <li className="py-3">
      <p className="font-mono text-xs text-primary">{entry.id}</p>
      <p className="mt-1 text-sm font-medium">{entry.title}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {entry.triage} · {entry.origin} · {entry.captured_at}
        {entry.promoted_task_id ? ` · promovida para ${entry.promoted_task_id}` : ""}
      </p>
    </li>
  );
}
