import {
  Activity,
  Archive,
  CheckCircle2,
  CircleDashed,
  CircleDotDashed,
  Clock,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { RoadmapTaskStatus } from "@/features/work-road/live";
import type { ExecutionKind } from "@/features/work-road/selectors";
import { executionKindLabel, statusLabel } from "@/features/work-road/selectors";

type Tone = "neutral" | "blue" | "green" | "amber" | "red";

const TONE: Record<Tone, string> = {
  neutral: "border-border bg-muted/70 text-muted-foreground",
  blue: "border-primary/25 bg-primary/[0.07] text-primary",
  green: "border-success/30 bg-success/10 text-success",
  amber: "border-warning/35 bg-warning/10 text-amber-800 dark:text-warning",
  red: "border-destructive/30 bg-destructive/[0.08] text-destructive",
};

const TASK_MARK: Record<RoadmapTaskStatus, { tone: Tone; icon: LucideIcon; glyph: string }> = {
  done: { tone: "green", icon: CheckCircle2, glyph: "✓" },
  partial: { tone: "amber", icon: CircleDotDashed, glyph: "◑" },
  risk: { tone: "red", icon: ShieldAlert, glyph: "!" },
  todo: { tone: "blue", icon: CircleDashed, glyph: "○" },
  reserved: { tone: "neutral", icon: Archive, glyph: "□" },
};

const EXEC_MARK: Record<ExecutionKind, { tone: Tone; icon: LucideIcon; glyph: string }> = {
  ativo: { tone: "blue", icon: Activity, glyph: "●" },
  ocioso: { tone: "amber", icon: Clock, glyph: "◌" },
  concluido: { tone: "green", icon: CheckCircle2, glyph: "✓" },
  falho: { tone: "red", icon: ShieldAlert, glyph: "!" },
  desatualizado: { tone: "neutral", icon: Clock, glyph: "◌" },
  heartbeat_atrasado: { tone: "amber", icon: Clock, glyph: "◌" },
};

export function QgStatusMark({
  status,
  labels,
  className,
}: {
  status: RoadmapTaskStatus;
  labels?: Partial<Record<RoadmapTaskStatus, string>> | null;
  className?: string;
}) {
  const mark = TASK_MARK[status];
  const Icon = mark.icon;
  const label = statusLabel(status, labels);
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-4",
        TONE[mark.tone],
        className,
      )}
    >
      <span aria-hidden="true" className="font-mono text-[10px]">{mark.glyph}</span>
      <Icon aria-hidden="true" className="h-3 w-3" />
      {label}
    </span>
  );
}

export function QgExecutionMark({
  kind,
  className,
}: {
  kind: ExecutionKind;
  className?: string;
}) {
  const mark = EXEC_MARK[kind];
  const Icon = mark.icon;
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-4",
        TONE[mark.tone],
        className,
      )}
    >
      <span aria-hidden="true" className="font-mono text-[10px]">{mark.glyph}</span>
      <Icon aria-hidden="true" className="h-3 w-3" />
      {executionKindLabel(kind)}
    </span>
  );
}

export function QgKindMark({
  label,
  className,
}: {
  label: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center whitespace-nowrap rounded-full border border-border bg-muted/55 px-2 py-0.5 text-[11px] font-semibold leading-4 text-muted-foreground",
        className,
      )}
    >
      {label}
    </span>
  );
}
