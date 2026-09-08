import React from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type Props = {
  id: string;
  label: string;
  obrigatorio?: boolean;
  ajuda?: string;
  erro?: string;
  className?: string;
  children: React.ReactNode;
};

export function Campo({ id, label, obrigatorio, ajuda, erro, className, children }: Props) {
  const ajudaId = ajuda ? `${id}-ajuda` : undefined;
  const erroId = erro ? `${id}-erro` : undefined;

  return (
    <div className={cn("grid gap-2", className)}>
      <Label htmlFor={id}>
        {label}
        {obrigatorio ? (
          <span className="ml-1 text-destructive" aria-hidden>
            *
          </span>
        ) : null}
      </Label>
      {children}
      {ajuda && !erro ? (
        <p id={ajudaId} className="text-sm text-muted-foreground">
          {ajuda}
        </p>
      ) : null}
      {erro ? (
        <p id={erroId} role="alert" className="text-sm text-destructive">
          {erro}
        </p>
      ) : null}
    </div>
  );
}
