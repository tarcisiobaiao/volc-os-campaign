import React from "react";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleOff,
  Filter,
  Inbox,
  ShieldAlert,
  WifiOff,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type TomOperacional =
  | "vazio"
  | "filtro"
  | "erro"
  | "bloqueado"
  | "demo"
  | "parcial"
  | "indisponivel"
  | "sucesso";

const TOM: Record<
  TomOperacional,
  { Icone: typeof Inbox; moldura: string; glifo: string }
> = {
  vazio: {
    Icone: Inbox,
    moldura: "border-dashed border-border bg-card",
    glifo: "text-muted-foreground",
  },
  filtro: {
    Icone: Filter,
    moldura: "border-solid border-border bg-muted/50",
    glifo: "text-muted-foreground",
  },
  erro: {
    Icone: WifiOff,
    moldura: "border-solid border-destructive/40 bg-destructive/8",
    glifo: "text-destructive",
  },
  bloqueado: {
    Icone: ShieldAlert,
    moldura: "border-solid border-destructive/40 bg-destructive/8",
    glifo: "text-destructive",
  },
  demo: {
    Icone: Ban,
    moldura: "border-solid border-demo/40 bg-demo/8",
    glifo: "text-demo",
  },
  parcial: {
    Icone: AlertTriangle,
    moldura: "border-solid border-warning/40 bg-warning/8",
    glifo: "text-warning",
  },
  indisponivel: {
    Icone: CircleOff,
    moldura: "border-solid border-warning/40 bg-warning/8",
    glifo: "text-warning",
  },
  sucesso: {
    Icone: CheckCircle2,
    moldura: "border-solid border-success/40 bg-success/8",
    glifo: "text-success",
  },
};

type Props = {
  tom: TomOperacional;
  titulo: string;
  explicacao: string;
  acao?: { rotulo: string; onClick: () => void };
  className?: string;
};

export function EstadoOperacional({ tom, titulo, explicacao, acao, className }: Props) {
  const { Icone, moldura, glifo } = TOM[tom];
  const alerta = tom === "erro" || tom === "bloqueado";

  return (
    <div
      role={alerta ? "alert" : undefined}
      className={cn("rounded-lg border px-5 py-8 text-center", moldura, className)}
    >
      <Icone className={cn("mx-auto h-6 w-6", glifo)} aria-hidden />
      <p className="mt-3 font-display text-sm font-semibold text-foreground">{titulo}</p>
      <p className="mx-auto mt-1 max-w-[52ch] text-pretty text-sm leading-relaxed text-muted-foreground">
        {explicacao}
      </p>
      {acao ? (
        <div className="mt-4 flex justify-center">
          <Button type="button" variant={tom === "erro" ? "default" : "secondary"} onClick={acao.onClick}>
            {acao.rotulo}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
