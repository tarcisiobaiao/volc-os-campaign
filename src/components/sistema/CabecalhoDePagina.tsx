import React from "react";

import { cn } from "@/lib/utils";

type Props = {
  kicker: string;
  titulo: React.ReactNode;
  proposito?: string;
  icone?: React.ReactNode;
  acao?: React.ReactNode;
  className?: string;
};

/**
 * Identidade de página do Design System V2.
 * Kicker, H1, aurora-rule, propósito, no máximo uma ação primária.
 */
export function CabecalhoDePagina({
  kicker,
  titulo,
  proposito,
  icone,
  acao,
  className,
}: Props) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-4", className)}>
      <div className="min-w-0 max-w-3xl">
        <p className="kicker mb-2 flex items-center gap-2">
          {icone ? (
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
              {icone}
            </span>
          ) : null}
          {kicker}
        </p>
        <h1 className="font-display text-[1.75rem] font-bold leading-[1.1] tracking-tight text-foreground md:text-4xl">
          {titulo}
        </h1>
        <div className="aurora-rule mt-3 w-16" aria-hidden />
        {proposito ? (
          <p className="mt-3 max-w-[70ch] text-pretty text-sm text-muted-foreground">{proposito}</p>
        ) : null}
      </div>
      {acao ? <div className="flex shrink-0 items-center gap-2">{acao}</div> : null}
    </header>
  );
}
