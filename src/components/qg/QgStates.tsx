import type { ReactNode } from "react";
import { CloudOff, Inbox, SearchX, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const SECONDARY = "text-foreground/75";

export function QgLoading({ label = "Carregando o Roadmap Vivo" }: { label?: string }) {
  return (
    <div className="space-y-3 py-6" role="status" aria-label={label}>
      <Skeleton className="h-24 w-full rounded-lg motion-reduce:animate-none" />
      <Skeleton className="h-16 w-full rounded-lg motion-reduce:animate-none" />
      <Skeleton className="h-40 w-full rounded-lg motion-reduce:animate-none" />
    </div>
  );
}

export function QgError({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string | null;
  onRetry: () => void;
}) {
  return (
    <section className="my-6 rounded-lg border border-destructive/30 bg-destructive/[0.06] p-5" role="alert">
      <div className="flex items-start gap-3">
        <CloudOff aria-hidden="true" className="mt-0.5 h-5 w-5 text-destructive" />
        <div>
          <h2 className="font-display text-lg font-semibold text-foreground text-balance">{title}</h2>
          <p className={cn("mt-1 max-w-3xl text-sm leading-6 text-pretty", SECONDARY)}>
            {message || "A leitura falhou sem detalhe. O QG não substitui a fonte por uma lista vazia."}
          </p>
          <Button className="mt-4 min-h-10" size="sm" variant="outline" onClick={onRetry}>
            Tentar novamente
          </Button>
        </div>
      </div>
    </section>
  );
}

export function QgStaleBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      className="mb-5 flex flex-col gap-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
      role="status"
    >
      <div className="flex items-start gap-2">
        <TriangleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 text-amber-800 dark:text-warning" />
        <p className="text-sm text-foreground">
          <span className="font-semibold">Dados desatualizados.</span>{" "}
          <span className={SECONDARY}>{message}</span>
        </p>
      </div>
      <Button size="sm" variant="outline" className="min-h-10 shrink-0" onClick={onRetry}>
        Relê agora
      </Button>
    </div>
  );
}

export function QgEmptyRoadmap() {
  return (
    <section className="my-8 border-y border-border py-10" aria-labelledby="qg-empty-roadmap">
      <Inbox aria-hidden="true" className="h-5 w-5 text-muted-foreground" />
      <h2 id="qg-empty-roadmap" className="mt-3 font-display text-xl font-semibold text-balance">
        O Roadmap Vivo chegou vazio
      </h2>
      <p className={cn("mt-2 max-w-2xl text-sm leading-6 text-pretty", SECONDARY)}>
        A leitura funcionou, mas a fonte não trouxe iniciativas. Isso não é zero de progresso: é ausência de catálogo.
      </p>
    </section>
  );
}

export function QgFilterEmpty({ onClear }: { onClear: () => void }) {
  return (
    <div className="py-12 text-center" role="status">
      <SearchX aria-hidden="true" className="mx-auto h-5 w-5 text-muted-foreground" />
      <p className="mt-3 text-sm font-medium text-foreground">Nenhuma tarefa neste recorte</p>
      <p className={cn("mt-1 text-sm", SECONDARY)}>
        A busca e os filtros combinados não encontram item na fonte. O catálogo continua existindo fora deste recorte.
      </p>
      <Button className="mt-4 min-h-10" size="sm" variant="outline" onClick={onClear}>
        Limpar filtros
      </Button>
    </div>
  );
}

export function QgAbsentSummary() {
  return (
    <p className="mt-4 text-sm text-foreground" role="status">
      O resumo quantitativo não veio nesta leitura. Ausência não é zero.
    </p>
  );
}

export function QgNoActiveExecutions() {
  return (
    <p className="text-sm text-foreground" role="status">
      Nenhuma execução ativa neste instante. Diretórios ociosos não contam como sessão viva.
    </p>
  );
}

export function QgMissingField({ children }: { children: ReactNode }) {
  return (
    <p className="text-sm italic text-foreground/80">{children}</p>
  );
}
