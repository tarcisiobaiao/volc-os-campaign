import type { LucideIcon } from "lucide-react";
import {
  BookOpenCheck,
  Boxes,
  CircleDashed,
  CircleDot,
  CirclePause,
  Code2,
  FileText,
  FlaskConical,
  History,
  LockKeyhole,
  Rocket,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  EnvironmentState,
  ProductState,
  RiskState,
  WorkState,
} from "./model";

type Tone = "neutral" | "blue" | "green" | "amber" | "red" | "purple";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "border-border bg-muted/55 text-muted-foreground",
  blue: "border-primary/25 bg-primary/[0.07] text-primary",
  green: "border-success/30 bg-success/10 text-success",
  amber: "border-warning/35 bg-warning/10 text-amber-700 dark:text-warning",
  red: "border-destructive/30 bg-destructive/[0.08] text-destructive",
  purple: "border-violet-500/25 bg-violet-500/[0.08] text-violet-700 dark:text-violet-300",
};

export function Pill({
  children,
  tone = "neutral",
  icon: Icon,
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-4",
        TONE_CLASS[tone],
        className,
      )}
    >
      {Icon ? <Icon aria-hidden="true" className="h-3 w-3" /> : null}
      {children}
    </span>
  );
}

const WORK: Record<WorkState, { label: string; tone: Tone; icon: LucideIcon }> = {
  ready: { label: "Pronta", tone: "neutral", icon: CircleDashed },
  claimed: { label: "Assumida", tone: "purple", icon: LockKeyhole },
  in_progress: { label: "Em execução", tone: "blue", icon: CircleDot },
  review: { label: "Em revisão", tone: "amber", icon: BookOpenCheck },
  blocked: { label: "Aguardando", tone: "amber", icon: CirclePause },
  done: { label: "Concluída", tone: "green", icon: BookOpenCheck },
};

const PRODUCT: Record<ProductState, { label: string; tone: Tone }> = {
  planned: { label: "Planejado", tone: "neutral" },
  partial: { label: "Parcial", tone: "amber" },
  implemented: { label: "Implementado", tone: "green" },
  legacy: { label: "Legado aproveitável", tone: "purple" },
  parked: { label: "Estacionado", tone: "neutral" },
};

const ENVIRONMENT: Record<EnvironmentState, { label: string; icon: LucideIcon }> = {
  docs: { label: "Documentação", icon: FileText },
  code: { label: "Código", icon: Code2 },
  local: { label: "Localhost", icon: FlaskConical },
  production: { label: "Produção", icon: Rocket },
};

export function WorkStatePill({ state }: { state: WorkState }) {
  const item = WORK[state];
  return <Pill tone={item.tone} icon={item.icon}>{item.label}</Pill>;
}

export function ProductStatePill({ state }: { state: ProductState }) {
  const item = PRODUCT[state];
  return <Pill tone={item.tone}>{item.label}</Pill>;
}

export function RiskPill({ state }: { state: RiskState }) {
  if (state === "normal") return null;
  return state === "accepted" ? (
    <Pill tone="red" icon={ShieldAlert}>Risco aceito</Pill>
  ) : (
    <Pill tone="amber" icon={History}>Dependência externa</Pill>
  );
}

export function EnvironmentPills({ environments }: { environments: EnvironmentState[] }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      {environments.map((environment) => {
        const item = ENVIRONMENT[environment];
        return <Pill key={environment} icon={item.icon}>{item.label}</Pill>;
      })}
    </span>
  );
}

export function ClusterMark({ children }: { children: React.ReactNode }) {
  return <Pill tone="blue" icon={Boxes}>{children}</Pill>;
}

