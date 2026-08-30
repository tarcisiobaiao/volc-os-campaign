/**
 * Tema de gráficos VOLC — base compartilhada para todos os Recharts do sistema.
 *
 * Regras (validadas com o skill dataviz):
 *  - Paleta categórica em ORDEM FIXA, nunca ciclada por rank. A cor segue a
 *    ENTIDADE, não a posição. (validador: CVD ΔE 10.7 / normal 23.0 — passa)
 *  - Um eixo só (nunca dual-axis).
 *  - Grid/eixos recessivos; texto em tokens de tinta (nunca na cor da série).
 *  - Cores de status (positivo/negativo/atenção) são RESERVADAS — não viram série.
 *  - Linhas >= 2.5px e tooltip sempre presente (alívio do WARN de contraste do
 *    neon-blue/verde sobre o branco).
 *
 * Uso típico:
 *   <LineChart ...>
 *     <CartesianGrid {...volcGrid} />
 *     <XAxis dataKey="date" {...volcAxis} />
 *     <YAxis {...volcAxis} />
 *     <Tooltip content={<VolcTooltip />} cursor={volcCursor} />
 *     <Line dataKey="roas" stroke={chartColor(0)} {...volcLine} />
 *   </LineChart>
 */
import * as React from "react";

/** Série categórica VOLC (aurora), em ordem fixa. */
export const CHART_SERIES = [
  "hsl(var(--chart-1))", // deep-blue
  "hsl(var(--chart-2))", // neon-blue
  "hsl(var(--chart-3))", // purple
  "hsl(var(--chart-4))", // orange
  "hsl(var(--chart-5))", // green
] as const;

/** Pega a cor da i-ésima série (por identidade, sempre a mesma ordem). */
export const chartColor = (i: number): string => CHART_SERIES[((i % CHART_SERIES.length) + CHART_SERIES.length) % CHART_SERIES.length];

/** Status RESERVADO — nunca use como cor de série. */
export const CHART_STATUS = {
  positive: "hsl(var(--success))",
  negative: "hsl(var(--destructive))",
  warning: "hsl(var(--warning))",
  neutral: "hsl(var(--muted-foreground))",
} as const;

/** Grid recessivo: sem linhas verticais, sutil. */
export const volcGrid = {
  stroke: "hsl(var(--border))",
  strokeOpacity: 0.55,
  vertical: false,
} as const;

/** Eixos: tinta muda, fonte pequena, números tabulares, sem tickLine dura. */
export const volcAxis = {
  stroke: "hsl(var(--border))",
  tickLine: false,
  axisLine: { stroke: "hsl(var(--border))", strokeOpacity: 0.6 },
  tick: {
    fill: "hsl(var(--muted-foreground))",
    fontSize: 11,
    fontVariantNumeric: "tabular-nums",
  },
} as const;

/** Linha/área: traço grosso o suficiente pra ler no claro. */
export const volcLine = {
  strokeWidth: 2.5,
  dot: false,
  activeDot: { r: 4, strokeWidth: 0 },
} as const;

/** Cursor do tooltip (a régua vertical), discreto. */
export const volcCursor = { stroke: "hsl(var(--primary))", strokeOpacity: 0.35, strokeWidth: 1 } as const;

/**
 * <defs> com gradientes aurora para preenchimento de área (fade vertical).
 * Renderize dentro do chart e referencie por url(#volc-fill-N).
 */
export function VolcAuroraDefs() {
  return (
    <defs>
      {CHART_SERIES.map((c, i) => (
        <linearGradient key={i} id={`volc-fill-${i}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity={0.32} />
          <stop offset="100%" stopColor={c} stopOpacity={0.02} />
        </linearGradient>
      ))}
    </defs>
  );
}
export const chartFill = (i: number) => `url(#volc-fill-${((i % CHART_SERIES.length) + CHART_SERIES.length) % CHART_SERIES.length})`;

type TooltipEntry = { name?: string; value?: number | string; color?: string; dataKey?: string | number };
interface VolcTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: React.ReactNode;
  /** Formatação opcional do valor (ex.: moeda, %). */
  valueFormatter?: (value: number | string, name?: string) => React.ReactNode;
  labelFormatter?: (label: React.ReactNode) => React.ReactNode;
}

/** Tooltip VOLC: cartão de vidro, rótulo kicker, valores tabulares, ponto de cor por série. */
export function VolcTooltip({ active, payload, label, valueFormatter, labelFormatter }: VolcTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="glass rounded-lg px-3 py-2.5 min-w-[9rem] shadow-elevated">
      {label !== undefined && label !== "" && (
        <div className="kicker mb-1.5">{labelFormatter ? labelFormatter(label) : label}</div>
      )}
      <div className="space-y-1">
        {payload.map((entry, i) => (
          <div key={i} className="flex items-center justify-between gap-4 text-xs">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span className="h-2 w-2 rounded-[2px]" style={{ background: entry.color }} />
              {entry.name}
            </span>
            <span className="font-medium tabular text-foreground">
              {valueFormatter && entry.value !== undefined ? valueFormatter(entry.value, entry.name) : entry.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
