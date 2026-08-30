import React from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface StepDef {
  id: string;
  title: string;
  hint: string;
  /** Passo que só se faz uma vez por conta, não a cada site. */
  onceOnly?: boolean;
}

interface StepRailProps {
  steps: StepDef[];
  currentId: string;
  done: Set<string>;
  onSelect: (id: string) => void;
}

/**
 * Trilha dos passos, endereçada por ID e não por índice.
 *
 * O número de passos MUDA: quando a Edge Function já está publicada, ela sai da
 * trilha. Com índice, encolher a lista deslocaria silenciosamente o passo atual
 * e o conjunto de concluídos.
 */
export const StepRail: React.FC<StepRailProps> = ({ steps, currentId, done, onSelect }) => (
  <ol className="space-y-1" aria-label="Etapas da configuração">
    {steps.map((step, i) => {
      const isDone = done.has(step.id);
      const isCurrent = step.id === currentId;

      return (
        <li key={step.id}>
          <button
            onClick={() => onSelect(step.id)}
            aria-current={isCurrent ? 'step' : undefined}
            className={cn(
              'w-full text-left flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors',
              isCurrent ? 'bg-primary/10' : 'hover:bg-muted/60',
            )}
          >
            <span
              className={cn(
                'mt-0.5 h-6 w-6 shrink-0 rounded-full border flex items-center justify-center text-[11px] font-semibold transition-colors',
                isDone
                  ? 'border-emerald-500 bg-emerald-500 text-white'
                  : isCurrent
                    ? 'border-primary text-primary'
                    : 'border-muted-foreground/30 text-muted-foreground',
              )}
            >
              {isDone ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </span>
            <span className="min-w-0">
              <span
                className={cn(
                  'block text-sm font-medium leading-tight',
                  isCurrent ? 'text-foreground' : 'text-muted-foreground',
                )}
              >
                {step.title}
              </span>
              <span className="block text-[11px] text-muted-foreground leading-tight mt-0.5">
                {step.onceOnly && <span className="text-primary font-medium">uma vez só · </span>}
                {step.hint}
              </span>
            </span>
          </button>
        </li>
      );
    })}
  </ol>
);
