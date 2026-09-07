import { useState, useEffect, useRef } from "react";
import {
  BrainCircuit,
  Sparkles,
  Palette,
  Package,
  CheckCircle2,
  XCircle,
} from "lucide-react";

export type LoadPhase =
  | "research"
  | "blueprints"
  | "images"
  | "packaging"
  | "done";

export type SlotStatus = "pending" | "active" | "done" | "failed";

export interface SlotState {
  status: SlotStatus;
  url?: string; // object URL of the completed thumbnail
}

interface LoadingScreenProps {
  total: number;
  phase: LoadPhase;
  slots: SlotState[]; // length === total; slots[0] = image 1
}

// Real progress is discrete (one bump per backend event). We map phase + resolved
// count to a target %, then ease a displayed value toward it with a gentle creep so
// the bar never freezes during a 20–30s render — but it can never overtake the phase.
const PHASE_RANGE: Record<LoadPhase, [number, number]> = {
  research: [4, 12],
  blueprints: [12, 25],
  images: [25, 90],
  packaging: [90, 99],
  done: [100, 100],
};

const PHASE_META: Record<LoadPhase, { Icon: typeof BrainCircuit }> = {
  research: { Icon: BrainCircuit },
  blueprints: { Icon: Sparkles },
  images: { Icon: Palette },
  packaging: { Icon: Package },
  done: { Icon: CheckCircle2 },
};

export default function LoadingScreen({ total, phase, slots }: LoadingScreenProps) {
  const doneCount = slots.filter((s) => s.status === "done").length;
  const resolvedCount = slots.filter(
    (s) => s.status === "done" || s.status === "failed"
  ).length;

  // ── Real target % ──────────────────────────────────────────────
  let target = PHASE_RANGE[phase][0];
  if (phase === "images" && total > 0) {
    target = 25 + (resolvedCount / total) * 65;
  } else if (phase === "packaging") {
    target = 95;
  } else if (phase === "done") {
    target = 100;
  }

  // ── Eased display value with bounded creep ─────────────────────
  const [display, setDisplay] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    const id = setInterval(() => {
      setDisplay((d) => {
        const [, upper] = PHASE_RANGE[phase];
        const ceil = phase === "done" ? 100 : upper - 1;
        const aim = Math.min(ceil, Math.max(target, d + 0.25)); // slow creep
        const next = d + (aim - d) * 0.12; // ease
        return Math.max(d, Math.min(100, next));
      });
    }, 120);
    return () => clearInterval(id);
  }, [phase, target]);

  const progress = Math.round(display);

  // ── Phase label ────────────────────────────────────────────────
  const phaseLabel =
    phase === "research"
      ? "Analisando briefing..."
      : phase === "blueprints"
        ? "Gerando blueprints criativos..."
        : phase === "images"
          ? `Criando imagens — ${doneCount} de ${total} prontas`
          : phase === "packaging"
            ? "Empacotando criativos..."
            : "Finalizando...";

  const { Icon } = PHASE_META[phase];

  // ── Rough ETA from real progress ───────────────────────────────
  const elapsedSec = (Date.now() - startRef.current) / 1000;
  const remainingSec =
    display > 6 && display < 99 ? (elapsedSec * (100 - display)) / display : 0;
  const remainingMin = Math.ceil(remainingSec / 60);

  // ── Circular progress geometry ─────────────────────────────────
  const R = 72;
  const C = 2 * Math.PI * R;
  const offset = C - (display / 100) * C;

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] space-y-10 animate-float-up">
      <img
        src="/aprova-logo.png"
        alt="Aprova Concursos"
        className="h-10 object-contain opacity-50"
      />

      {/* Circular progress */}
      <div className="relative">
        <div className="absolute inset-[-24px] rounded-full bg-primary/10 blur-3xl animate-pulse-glow" />

        <svg width="184" height="184" className="relative -rotate-90">
          <circle cx="92" cy="92" r={R} fill="none" stroke="hsl(var(--muted))" strokeWidth="5" />
          <circle
            cx="92"
            cy="92"
            r={R}
            fill="none"
            stroke="url(#grad)"
            strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={offset}
            className="transition-all duration-200 ease-out"
          />
          <defs>
            <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="hsl(var(--primary))" />
              <stop offset="100%" stopColor="hsl(var(--accent))" />
            </linearGradient>
          </defs>
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-4xl font-black text-foreground tabular-nums tracking-tight">
            {progress}
          </span>
          <span className="text-xs font-semibold text-muted-foreground -mt-0.5">%</span>
        </div>
      </div>

      {/* Phase label */}
      <div className="text-center space-y-2 min-h-[52px]">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-card/80 border border-border/50 shadow-sm">
          <Icon className="w-4 h-4 text-primary animate-pulse" />
          <p className="text-sm font-semibold text-foreground">{phaseLabel}</p>
        </div>

        {phase !== "done" && remainingSec > 15 && (
          <p className="text-xs text-muted-foreground/60 tabular-nums">
            ~{remainingMin > 1 ? `${remainingMin} min` : "menos de 1 min"} restante
            {remainingMin > 1 ? "s" : ""}
          </p>
        )}
      </div>

      {/* Thin progress bar */}
      <div className="w-72 max-w-full">
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-200 ease-out animate-stripe"
            style={{
              width: `${display}%`,
              background:
                "linear-gradient(90deg, hsl(var(--primary)), hsl(var(--accent)))",
            }}
          />
        </div>
      </div>

      {/* Mini slots grid — synced to REAL backend state */}
      <div className="flex gap-2 flex-wrap justify-center max-w-sm">
        {Array.from({ length: total }).map((_, i) => {
          const slot = slots[i] ?? { status: "pending" as SlotStatus };
          return (
            <div
              key={i}
              className={`
                relative w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold
                overflow-hidden transition-all duration-500
                ${
                  slot.status === "done"
                    ? "bg-primary/10 border border-primary/25 text-primary scale-100"
                    : slot.status === "failed"
                      ? "bg-destructive/10 border border-destructive/30 text-destructive"
                      : slot.status === "active"
                        ? "border-2 border-primary/40 bg-primary/5 text-primary/50 animate-pulse"
                        : "animate-shimmer border border-transparent text-transparent"
                }
              `}
            >
              {slot.status === "done" && slot.url ? (
                <>
                  <img
                    src={slot.url}
                    alt={`Criativo ${i + 1}`}
                    className="absolute inset-0 w-full h-full object-cover"
                  />
                  <span className="absolute inset-0 bg-black/30" />
                  <CheckCircle2 className="relative w-4 h-4 text-white drop-shadow" />
                </>
              ) : slot.status === "done" ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : slot.status === "failed" ? (
                <XCircle className="w-4 h-4" />
              ) : slot.status === "active" ? (
                <span className="w-3.5 h-3.5 border-2 border-primary/40 border-t-primary rounded-full animate-spin" />
              ) : (
                <span>{i + 1}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
