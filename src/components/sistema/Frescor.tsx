import React from "react";

import { idade } from "@/components/trafego/inventario/formato";
import { LIMITES_PADRAO, nivelDeFrescor, type LimitesDeFrescor, type NivelDeFrescor } from "@/lib/instrumento";
import { cn } from "@/lib/utils";

type Props = {
  lidoEm: string | Date | null | undefined;
  limites?: LimitesDeFrescor;
  /** Injetável para teste e para a bancada; padrão é o relógio local. */
  agora?: Date;
  /** "Google Ads", "JoinAds" — de onde veio a leitura. */
  fonte?: string;
  className?: string;
};

const NIVEL: Record<NivelDeFrescor, { glifo: string; palavra: string | null; tom: string }> = {
  fresco: { glifo: "●", palavra: null, tom: "text-verified" },
  envelhecido: { glifo: "◐", palavra: "Envelhecido", tom: "text-warning" },
  vencido: { glifo: "▲", palavra: "Vencido para decidir", tom: "text-warning" },
  futuro: { glifo: "▲", palavra: "Relógio fora de sincronia", tom: "text-warning" },
  nunca: { glifo: "?", palavra: "Nunca lido", tom: "text-muted-foreground" },
};

const hora = (d: Date) =>
  d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }).replace(/\u00a0/g, " ");

/**
 * Carimbo de frescor colado ao número: "● lido há 12 min · 14:32 · Google Ads".
 *
 * Reaproveita `idade()` do inventário (mesma lei: data futura nunca vira
 * "agora"). Um número sem este carimbo não é número operacional (PRODUCT §4).
 */
export function Frescor({ lidoEm, limites = LIMITES_PADRAO, agora, fonte, className }: Props) {
  const relogio = agora ?? new Date();
  const { nivel, segundos } = nivelDeFrescor(lidoEm, relogio, limites);
  const item = NIVEL[nivel];
  const instante = lidoEm == null ? null : lidoEm instanceof Date ? lidoEm : new Date(lidoEm);
  const partes: string[] = [];
  if (nivel !== "nunca" && nivel !== "futuro") partes.push(`lido ${idade(segundos)}`);
  if (instante && !Number.isNaN(instante.getTime()) && nivel !== "nunca") partes.push(hora(instante));
  if (fonte) partes.push(fonte);

  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1 text-micro text-muted-foreground", className)} data-frescor={nivel}>
      <span aria-hidden className={item.tom}>
        {item.glifo}
      </span>
      {item.palavra ? <span className="font-semibold text-foreground">{item.palavra}</span> : null}
      {item.palavra && partes.length ? <span aria-hidden>·</span> : null}
      <span className="numero">{partes.join(" · ")}</span>
    </span>
  );
}
