import React from "react";

import { cn } from "@/lib/utils";

export type Verdade =
  | "real"
  | "demo"
  | "parcial"
  | "bloqueado"
  | "indisponivel"
  | "erro"
  | "desconhecido"
  | "zero";

const ROTULO: Record<Verdade, { palavra: string; glifo: string; classe: string }> = {
  real: { palavra: "Dado real", glifo: "◆", classe: "border-verified/30 bg-verified/10 text-foreground" },
  demo: { palavra: "Demonstração", glifo: "◌", classe: "border-demo/35 bg-demo/10 text-foreground" },
  parcial: { palavra: "Leitura parcial", glifo: "▲", classe: "border-warning/30 bg-warning/10 text-foreground" },
  bloqueado: { palavra: "Bloqueado", glifo: "✕", classe: "border-destructive/30 bg-destructive/10 text-foreground" },
  indisponivel: { palavra: "Fonte indisponível", glifo: "■", classe: "border-warning/30 bg-warning/10 text-foreground" },
  erro: { palavra: "Erro de leitura", glifo: "✕", classe: "border-destructive/30 bg-destructive/10 text-foreground" },
  desconhecido: { palavra: "Desconhecido", glifo: "?", classe: "border-border bg-muted text-foreground" },
  zero: { palavra: "Zero medido", glifo: "●", classe: "border-border bg-card text-foreground" },
};

type Props = {
  verdade: Verdade;
  detalhe?: string;
  className?: string;
};

export function VerdadeDoDado({ verdade, detalhe, className }: Props) {
  const item = ROTULO[verdade];
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 rounded-full border px-2.5 text-[13px] font-semibold",
        item.classe,
        className,
      )}
    >
      <span aria-hidden>{item.glifo}</span>
      {item.palavra}
      {detalhe ? <span className="sr-only">. {detalhe}</span> : null}
    </span>
  );
}
