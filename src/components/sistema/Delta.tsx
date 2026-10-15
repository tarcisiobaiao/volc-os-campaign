import React from "react";

import { avaliarDelta, formatarNumero, type Sentido } from "@/lib/instrumento";
import { cn } from "@/lib/utils";

type Props = {
  atual: number | null;
  base: number | null;
  /** Obrigatório: o componente não adivinha se subir é bom. */
  sentido: Sentido;
  /** "vs. 7 dias anteriores" */
  rotuloBase?: string;
  className?: string;
};

const GLIFO = { sobe: "▲", desce: "▼", igual: "=", desconhecida: "—" } as const;
const TOM = {
  bom: "text-delta-bom",
  ruim: "text-delta-ruim",
  neutro: "text-muted-foreground",
} as const;
const LEITURA = {
  bom: "o que é favorável",
  ruim: "o que é desfavorável",
  neutro: "sem juízo de valor",
} as const;

/**
 * Variação contra uma base, com glifo + sinal + palavra (cor é o terceiro sinal).
 *
 * Custo que sobe não é verde: o tom depende de `sentido`, e `neutro` nunca pinta.
 * Base zero mostra a direção sem inventar percentual.
 */
export function Delta({ atual, base, sentido, rotuloBase, className }: Props) {
  const { direcao, fracao, tom } = avaliarDelta(atual, base, sentido);

  if (direcao === "desconhecida") {
    return (
      <span className={cn("inline-flex items-center gap-1 text-micro text-muted-foreground", className)}>
        <span aria-hidden>{GLIFO.desconhecida}</span>
        sem base de comparação
      </span>
    );
  }

  const magnitude =
    fracao == null
      ? "sem % (base zero)"
      : `${fracao > 0 ? "+" : fracao < 0 ? "−" : ""}${formatarNumero(Math.abs(fracao), { tipo: "percentual" })}`;
  const verbo = direcao === "sobe" ? "Subiu" : direcao === "desce" ? "Caiu" : "Ficou igual";

  return (
    <span className={cn("inline-flex items-center gap-1 text-micro", className)}>
      <span aria-hidden className={cn("numero font-semibold", TOM[tom])}>
        {GLIFO[direcao]} {magnitude}
      </span>
      {rotuloBase ? (
        <span aria-hidden className="text-muted-foreground">
          {rotuloBase}
        </span>
      ) : null}
      <span className="sr-only">
        {verbo}
        {fracao != null && direcao !== "igual" ? ` ${formatarNumero(Math.abs(fracao), { tipo: "percentual" })}` : ""}
        {rotuloBase ? ` ${rotuloBase}` : ""}, {LEITURA[tom]}.
      </span>
    </span>
  );
}
