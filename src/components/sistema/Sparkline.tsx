import React from "react";

import { geometriaDaSparkline } from "@/lib/instrumento";
import { chartColor } from "@/lib/chartTheme";
import { cn } from "@/lib/utils";

type Props = {
  valores: ReadonlyArray<number | null>;
  /** Frase para leitor de tela: "Custo diário, últimos 14 dias". */
  rotulo: string;
  largura?: number;
  altura?: number;
  /** Índice da série categórica (chartTheme). A cor segue a entidade. */
  serie?: number;
  /** Desenha o traço uma vez ao montar (respeita reduced-motion via CSS). */
  desenhar?: boolean;
  className?: string;
};

/**
 * Tendência curta em SVG puro (sem Recharts: ~1 KB, cabe em célula de tabela).
 *
 * ⚠️ `null` é lacuna: a linha QUEBRA. Interpolar por cima de um dia sem
 * leitura, ou descer a zero, desenharia um fato que ninguém mediu.
 */
export function Sparkline({
  valores,
  rotulo,
  largura = 96,
  altura = 28,
  serie = 0,
  desenhar = true,
  className,
}: Props) {
  const { trechos, isolados, final, lacunas } = geometriaDaSparkline(valores, largura, altura, 3);
  const cor = chartColor(serie);
  const descricao =
    trechos.length === 0 && isolados.length === 0
      ? `${rotulo}: sem leituras`
      : `${rotulo}${lacunas > 0 ? `, ${lacunas} ${lacunas === 1 ? "ponto sem leitura" : "pontos sem leitura"}` : ""}`;

  return (
    <svg
      role="img"
      aria-label={descricao}
      width={largura}
      height={altura}
      viewBox={`0 0 ${largura} ${altura}`}
      className={cn("overflow-visible", className)}
      data-lacunas={lacunas}
    >
      {trechos.map((d, i) => (
        <path
          key={i}
          d={d}
          pathLength={1}
          fill="none"
          stroke={cor}
          strokeWidth={1.75}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="sparkline-traco"
          data-desenhar={desenhar ? "true" : "false"}
        />
      ))}
      {isolados.map((p, i) => (
        <circle key={`i${i}`} cx={p.x} cy={p.y} r={1.75} fill={cor} />
      ))}
      {final ? (
        <circle cx={final.x} cy={final.y} r={2.75} fill={cor} stroke="hsl(var(--card))" strokeWidth={1.5} />
      ) : null}
    </svg>
  );
}
