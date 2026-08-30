import React from 'react';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { Inbox } from 'lucide-react';
import { OpportunityCard } from './OpportunityCard';
import { cn } from '@/lib/utils';
import { oppKey } from '@/hooks/pautador/usePautadorPro';
import type { Opportunity, PautadorKanbanColumn } from '@/types/pautador';

interface KanbanColumnProps {
  column: PautadorKanbanColumn;
  opportunities: Opportunity[];
  busyKeys: Set<string>;
  onCardClick: (opp: Opportunity) => void;
  index?: number;
}

// Identidade da coluna traduzida para o vocabulário VOLC (tokens semânticos,
// nunca a paleta crua do Tailwind — cinza frio consistente, sem warm/cool misturado).
const COLUMN_ACCENT: Record<string, { bar: string; dot: string; pill: string }> = {
  gray:   { bar: 'bg-muted-foreground/40', dot: 'bg-muted-foreground', pill: 'bg-muted text-muted-foreground' },
  blue:   { bar: 'bg-info',                dot: 'bg-info',             pill: 'bg-info/10 text-info' },
  yellow: { bar: 'bg-warning',             dot: 'bg-warning',          pill: 'bg-warning/10 text-warning' },
  purple: { bar: 'bg-primary',             dot: 'bg-primary',          pill: 'bg-primary/10 text-primary' },
  green:  { bar: 'bg-success',             dot: 'bg-success',          pill: 'bg-success/10 text-success' },
  red:    { bar: 'bg-destructive',         dot: 'bg-destructive',      pill: 'bg-destructive/10 text-destructive' },
};
const accentOf = (color: string) => COLUMN_ACCENT[color] || COLUMN_ACCENT.gray;

export const KanbanColumn: React.FC<KanbanColumnProps> = ({ column, opportunities, busyKeys, onCardClick, index = 0 }) => {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  const ids = opportunities.map(oppKey);
  const accent = accentOf(column.color);

  return (
    <div
      ref={setNodeRef}
      style={{ ['--i' as any]: index }}
      className={cn(
        'reveal flex flex-col rounded-xl border border-border bg-muted/20 min-w-[250px] max-w-[290px] w-full overflow-hidden transition-shadow duration-200',
        isOver && 'ring-2 ring-primary/30 shadow-elevated',
      )}
    >
      <span className={cn('h-0.5 w-full', accent.bar)} />
      <div className="p-3 border-b border-border flex items-center gap-2">
        <span className={cn('h-2 w-2 rounded-full', accent.dot)} />
        <h3 className="kicker flex-1 truncate">{column.title}</h3>
        <span className={cn('text-xs tabular rounded-full px-2 py-0.5 font-medium', accent.pill)}>
          {opportunities.length}
        </span>
      </div>

      <div className="p-2 flex-1 overflow-y-auto max-h-[calc(100vh-360px)] space-y-2">
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {opportunities.map((opp) => {
            const key = oppKey(opp);
            return (
              <OpportunityCard
                key={key}
                cardKey={key}
                opportunity={opp}
                busy={busyKeys.has(key)}
                onClick={onCardClick}
              />
            );
          })}
        </SortableContext>

        {opportunities.length === 0 && (
          <div className="flex flex-col items-center gap-1.5 py-10 text-center">
            <span className="rounded-md bg-muted p-1.5 text-muted-foreground">
              <Inbox className="h-4 w-4" />
            </span>
            <span className="kicker">Vazio</span>
          </div>
        )}
      </div>
    </div>
  );
};
