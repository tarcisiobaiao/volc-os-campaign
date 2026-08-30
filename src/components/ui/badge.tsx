import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * Chip de estado — a receita do `design.md`, não a do template.
 *
 * ---------------------------------------------------------------------------
 * O QUE ESTAVA ERRADO
 * ---------------------------------------------------------------------------
 *
 * 1. PALETA CRUA FORA DO VOCABULÁRIO FECHADO.
 *
 *    `success` era `bg-green-500 text-white` e `warning` era `bg-orange-500
 *    text-white`. Medido no navegador: "Online" dava **2,28:1** e "Pendente"
 *    **2,80:1** — abaixo do piso de 4,5:1 da WCAG 1.4.3. E `green-500` /
 *    `orange-500` / `blue-500` não existem no vocabulário do produto, que o
 *    `design.md` declara FECHADO: primary, verified, success, warning,
 *    destructive, info. Um chip fora dele ensina um significado que o resto
 *    do sistema não reconhece.
 *
 *    Como a paleta crua não tem variante escura, esses chips também
 *    atravessavam o tema escuro sem mudar — verde-500 sobre canvas #0C111B.
 *
 * 2. `animate-pulse` NA VARIANTE `excellent`.
 *
 *    `design.md` §Motion: "Live metrics, warning color and spend actions must
 *    not pulse or bounce." Uma métrica boa piscando na cara do operador é
 *    exatamente a decoração que o contrato proíbe — e, com `prefers-reduced-
 *    motion`, era movimento que nada desligava.
 *
 * 3. COR COMO ÚNICO PORTADOR DO SIGNIFICADO.
 *
 *    `<Badge value={82} />` renderizava "82%" e escolhia a cor sozinho. Quem
 *    não distingue verde de laranja recebia só um número. O PRODUCT.md é
 *    explícito: "Estados nunca dependem só de cor: combinam glifo, palavra e
 *    descrição." Agora cada variante semântica carrega um glifo, e ele vem com
 *    `aria-hidden` porque quem lê a palavra não precisa ouvir o símbolo.
 *
 * As variantes de performance não sumiram — foram MAPEADAS para o vocabulário
 * fechado. `excellent` continua existindo na API; ele só deixou de inventar uma
 * sétima cor para dizer o que `success` já dizia.
 */

const badgeVariants = cva(
  // `transition-colors` e não `transition-all`: o contrato manda nomear a
  // propriedade. Só a cor muda no hover de um chip.
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive: "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border-border text-foreground",

        // Vocabulário semântico fechado. Tinta sobre tinte, com borda de
        // baixa opacidade — a receita de chip do design.md, não um preenchimento
        // saturado. A tinta foi resolvida por medição contra este leito exato.
        success: "border-success/25 bg-success/10 text-success",
        warning: "border-warning/25 bg-warning/10 text-warning",
        verified: "border-verified/25 bg-verified/10 text-verified",
        info: "border-info/25 bg-info/10 text-info",
        danger: "border-destructive/25 bg-destructive/10 text-destructive",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

/** Glifo por variante — o segundo portador do estado, ao lado da palavra. */
const VARIANT_GLYPH: Partial<Record<NonNullable<BadgeProps["variant"]>, string>> = {
  success: "●",
  warning: "▲",
  verified: "◆",
  info: "■",
  danger: "✕",
  destructive: "✕",
}

/**
 * As quatro faixas de performance, mapeadas para o vocabulário fechado.
 * A PALAVRA acompanha a cor: sem ela o chip seria só um tom.
 */
const PERFORMANCE_TIER = {
  excellent: { variant: "success" as const, label: "ótimo" },
  good: { variant: "verified" as const, label: "bom" },
  average: { variant: "warning" as const, label: "médio" },
  poor: { variant: "danger" as const, label: "baixo" },
}

type PerformanceTier = keyof typeof PERFORMANCE_TIER

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  value?: number
  thresholds?: {
    excellent: number
    good: number
    average: number
  }
}

function getPerformanceTier(
  value: number,
  thresholds: BadgeProps["thresholds"] = { excellent: 80, good: 60, average: 40 }
): PerformanceTier {
  if (value >= thresholds.excellent) return "excellent"
  if (value >= thresholds.good) return "good"
  if (value >= thresholds.average) return "average"
  return "poor"
}

function Badge({ className, variant, value, thresholds, children, ...props }: BadgeProps) {
  const tier = value !== undefined ? getPerformanceTier(value, thresholds) : null
  const finalVariant = tier ? PERFORMANCE_TIER[tier].variant : variant
  const glyph = finalVariant ? VARIANT_GLYPH[finalVariant] : undefined

  return (
    <div className={cn(badgeVariants({ variant: finalVariant }), className)} {...props}>
      {glyph && (
        <span aria-hidden="true" className="text-[0.85em] leading-none">
          {glyph}
        </span>
      )}
      {children ?? (value !== undefined && `${value}%`)}
    </div>
  )
}

export const StatusBadge: React.FC<{ status: "online" | "offline" | "pending" }> = ({ status }) => {
  const variants = {
    online: "success" as const,
    offline: "danger" as const,
    pending: "warning" as const,
  }
  const labels = { online: "Online", offline: "Offline", pending: "Pendente" }

  return <Badge variant={variants[status]}>{labels[status]}</Badge>
}

export const PerformanceBadge: React.FC<{
  value: number
  label?: string
  thresholds?: BadgeProps["thresholds"]
}> = ({ value, label, thresholds }) => (
  <Badge value={value} thresholds={thresholds}>
    {label ? `${label}: ${value}%` : `${value}%`}
  </Badge>
)

export const ROASBadge: React.FC<{ roas: number }> = ({ roas }) => {
  // ROAS aqui é EXCEDENTE, não o múltiplo tradicional: 300 significa 300% de
  // excedente, ou seja 400% no jeito clássico de contar.
  const roasThresholds = { excellent: 300.0, good: 200.0, average: 100.0 }
  const tier = getPerformanceTier(roas, roasThresholds)

  // A palavra da faixa acompanha o número. Sem ela, "ROAS: 82,0%" verde e
  // "ROAS: 82,0%" laranja são o mesmo texto para quem não distingue as cores.
  return (
    <Badge variant={PERFORMANCE_TIER[tier].variant}>
      ROAS {roas.toFixed(1)}% · {PERFORMANCE_TIER[tier].label}
    </Badge>
  )
}

export { Badge, badgeVariants }
