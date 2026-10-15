import React from "react";

import { ESTADO_DE_PROPOSTA, type EstadoDeProposta } from "@/lib/instrumento";
import { cn } from "@/lib/utils";

/**
 * Tratamento visual de cada estado do ciclo P09 (design.md §V3, mapa fechado).
 * A palavra carrega o estado; o glifo dá a forma; a cor vem por último.
 * `sombra` e `proposta` são hipótese: hachura, não tinta.
 */
const CLASSE: Record<EstadoDeProposta, { selo: string; glifo: string }> = {
  sombra: { selo: "hachura-hipotese border-dashed border-foreground/35 bg-card", glifo: "text-foreground" },
  proposta: { selo: "hachura-hipotese border-solid border-primary/40 bg-card", glifo: "text-primary" },
  aguardando: { selo: "border-warning/35 bg-warning/10", glifo: "text-warning" },
  aprovada: { selo: "border-primary/35 bg-primary/10", glifo: "text-primary" },
  aplicada: { selo: "border-verified/35 bg-verified/10", glifo: "text-verified" },
  recusada: { selo: "border-border bg-muted", glifo: "text-muted-foreground" },
  vencida: { selo: "border-dashed border-border bg-muted", glifo: "text-muted-foreground" },
  revertida: { selo: "border-info/35 bg-info/10", glifo: "text-info" },
};

type Props = {
  estado: EstadoDeProposta;
  className?: string;
};

export function SeloDeProposta({ estado, className }: Props) {
  const item = ESTADO_DE_PROPOSTA[estado];
  const classe = CLASSE[estado];
  return (
    <span
      data-estado={estado}
      title={item.descricao}
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 rounded-full border px-2.5 text-[13px] font-semibold text-foreground",
        classe.selo,
        className,
      )}
    >
      <span aria-hidden className={classe.glifo}>
        {item.glifo}
      </span>
      {item.palavra}
      <span className="sr-only">. {item.descricao}</span>
    </span>
  );
}
