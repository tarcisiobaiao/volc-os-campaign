import React from "react";

import { cn } from "@/lib/utils";

type Props = {
  titulo?: string;
  /** Frescor, filtro de período ou uma ação secundária, à direita do título. */
  lateral?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
} & Omit<React.HTMLAttributes<HTMLElement>, "title">;

/**
 * Superfície de instrumento (design.md §V3): card + fio de luz no topo +
 * sombra tingida. Não aninhe um dentro do outro nem dentro de `shadow-card`.
 */
export function PainelInstrumento({ titulo, lateral, className, children, ...resto }: Props) {
  const id = React.useId();
  return (
    <section
      aria-labelledby={titulo ? id : undefined}
      className={cn("instrumento p-4 md:p-5", className)}
      {...resto}
    >
      {titulo || lateral ? (
        <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {titulo ? (
            <h2 id={id} className="font-display text-base font-semibold text-foreground">
              {titulo}
            </h2>
          ) : (
            <span />
          )}
          {lateral ? <div className="flex items-center gap-2">{lateral}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

/**
 * Faixa de métricas: uma `Metrica` hero e de 3 a 5 de faixa, separadas por
 * hairline — nunca uma grade de cartões idênticos (PRODUCT §9).
 * No telefone, empilha com hairline horizontal.
 */
export function FaixaDeMetricas({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 divide-y divide-border/70 sm:grid-cols-2 sm:divide-y-0 lg:flex lg:divide-x",
        "[&>*]:py-3 sm:[&>*]:px-4 lg:[&>*]:py-0 lg:[&>*:first-child]:pl-0 lg:[&>*]:flex-1 lg:[&>*:first-child]:flex-[1.6]",
        className,
      )}
    >
      {children}
    </div>
  );
}
