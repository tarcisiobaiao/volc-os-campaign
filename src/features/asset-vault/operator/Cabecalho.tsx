import { Vault } from "lucide-react";
import { cn } from "@/lib/utils";
import { HIT, PRESSIONAR, FOCO, PRIMARIO } from "./chrome";

export function CabecalhoDoCofre({
  acaoPrimaria,
}: {
  acaoPrimaria?: { rotulo: string; aoClicar: () => void } | null;
}) {
  return (
    <header className="flex flex-col items-stretch gap-4 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
      <div className="min-w-0 w-full max-w-3xl">
        <div className="kicker mb-2 flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Vault aria-hidden="true" className="h-3.5 w-3.5" />
          </span>
          Patrimônio e acesso
        </div>
        <h1 className="font-display text-[32px] font-bold tracking-tight leading-[1.05] text-foreground sm:text-[40px] text-balance">
          Cofre de Ativos
        </h1>
        <div className="mt-3 aurora-rule w-16" />
        <p className="mt-3 max-w-2xl min-w-0 break-words text-sm leading-6 text-muted-foreground text-pretty">
          O que existe, o que está pronto, o que está sem acesso e qual é o próximo ato seguro.
          O valor da credencial mora no 1Password; aqui mora a referência, o dono e o estado.
        </p>
      </div>
      {acaoPrimaria ? (
        <button type="button" onClick={acaoPrimaria.aoClicar} className={cn(PRIMARIO, "w-full sm:w-auto sm:shrink-0")}>
          {acaoPrimaria.rotulo}
        </button>
      ) : null}
    </header>
  );
}

export function AbasDoCofre({
  atual,
  aoTrocar,
}: {
  atual: string;
  aoTrocar: (view: "inventory" | "reviews" | "relations" | "contract") => void;
}) {
  const itens = [
    { id: "inventory" as const, label: "Inventário" },
    { id: "reviews" as const, label: "Revisões" },
    { id: "relations" as const, label: "Relações" },
    { id: "contract" as const, label: "Contrato" },
  ];
  return (
    <nav aria-label="Modos do Cofre" className="mt-5 flex min-h-10 w-full flex-wrap gap-1 rounded-md bg-muted p-1">
      {itens.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => aoTrocar(item.id)}
          aria-pressed={atual === item.id}
          className={cn(
            "inline-flex flex-1 basis-[calc(50%-0.25rem)] items-center justify-center rounded-md px-2 text-sm font-medium sm:flex-none sm:basis-auto sm:px-3",
            HIT, FOCO, PRESSIONAR,
            atual === item.id
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
