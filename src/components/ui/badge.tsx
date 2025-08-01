import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary: "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive: "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground",
        // Semáforo variants
        success: "border-transparent bg-success text-success-foreground",
        warning: "border-transparent bg-warning text-warning-foreground", 
        danger: "border-transparent bg-destructive text-destructive-foreground",
        // Performance variants
        excellent: "border-transparent bg-success text-success-foreground animate-pulse",
        good: "border-transparent bg-info text-info-foreground",
        average: "border-transparent bg-warning text-warning-foreground",
        poor: "border-transparent bg-destructive text-destructive-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  value?: number; // Para badges de performance automática
  thresholds?: {
    excellent: number;
    good: number;
    average: number;
  };
}

// Função para determinar variant baseado em valor e thresholds
function getPerformanceVariant(
  value: number,
  thresholds: BadgeProps["thresholds"] = {
    excellent: 80,
    good: 60,
    average: 40
  }
): "excellent" | "good" | "average" | "poor" {
  if (value >= thresholds.excellent) return "excellent";
  if (value >= thresholds.good) return "good";
  if (value >= thresholds.average) return "average";
  return "poor";
}

function Badge({ 
  className, 
  variant, 
  value, 
  thresholds,
  children,
  ...props 
}: BadgeProps) {
  // Se valor foi fornecido, determinar variant automaticamente
  const finalVariant = value !== undefined 
    ? getPerformanceVariant(value, thresholds)
    : variant;

  return (
    <div className={cn(badgeVariants({ variant: finalVariant }), className)} {...props}>
      {children || (value !== undefined && `${value}%`)}
    </div>
  );
}

// Componentes específicos para facilitar uso
export const StatusBadge: React.FC<{ status: "online" | "offline" | "pending" }> = ({ status }) => {
  const variants = {
    online: "success" as const,
    offline: "danger" as const, 
    pending: "warning" as const
  };

  const labels = {
    online: "Online",
    offline: "Offline",
    pending: "Pendente"
  };

  return <Badge variant={variants[status]}>{labels[status]}</Badge>;
};

export const PerformanceBadge: React.FC<{ 
  value: number; 
  label?: string;
  thresholds?: BadgeProps["thresholds"];
}> = ({ value, label, thresholds }) => {
  return (
    <Badge value={value} thresholds={thresholds}>
      {label ? `${label}: ${value}%` : `${value}%`}
    </Badge>
  );
};

export const ROASBadge: React.FC<{ roas: number }> = ({ roas }) => {
  // Thresholds específicos para ROAS
  const roasThresholds = {
    excellent: 4.0,
    good: 3.0,
    average: 2.0
  };

  const getROASVariant = (value: number): "excellent" | "good" | "average" | "poor" => {
    if (value >= roasThresholds.excellent) return "excellent";
    if (value >= roasThresholds.good) return "good"; 
    if (value >= roasThresholds.average) return "average";
    return "poor";
  };

  return (
    <Badge variant={getROASVariant(roas)}>
      ROAS: {roas.toFixed(2)}
    </Badge>
  );
};

export { Badge, badgeVariants }
