import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Loader2, Sparkles, User } from 'lucide-react';
import { TierBadge } from '@/components/pautador-pro/TierBadge';
import { CATEGORY_LABELS } from '@/types/pautador';
import type { Opportunity } from '@/types/pautador';

interface OpportunityCardProps {
  opportunity: Opportunity;
  cardKey: string;
  busy?: boolean;
  onClick: (opp: Opportunity) => void;
}

// Faixas de score mapeadas para tokens semânticos VOLC (ouro=warning, forte=success,
// médio=info, fraco=tinta muda). Sem #hex nem paleta crua do Tailwind.
function scoreColor(score?: number | null): string {
  const s = score || 0;
  if (s >= 100) return 'text-warning';
  if (s >= 70) return 'text-success';
  if (s >= 45) return 'text-info';
  return 'text-muted-foreground';
}

export const OpportunityCard: React.FC<OpportunityCardProps> = ({ opportunity, cardKey, busy, onClick }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: cardKey,
    data: { opportunity },
  });

  const style = { transform: CSS.Transform.toString(transform), transition };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <Card
        className={cn(
          'hover-lift border-border cursor-grab active:cursor-grabbing',
          isDragging && 'opacity-50 shadow-elevated',
        )}
        onClick={() => onClick(opportunity)}
      >
        <CardContent className="p-3 space-y-2">
          <div className="flex items-start justify-between gap-1">
            <h4 className="font-display font-semibold text-xs leading-snug flex-1 line-clamp-2" title={opportunity.keyword}>
              {opportunity.keyword}
            </h4>
            <TierBadge tier={opportunity.tier} />
          </div>

          <div className="flex items-center justify-between gap-1">
            <span className="text-[10px] text-muted-foreground truncate">
              {opportunity.category} · {CATEGORY_LABELS[opportunity.category]}
            </span>
            <span className={cn('font-display text-sm font-bold tabular', scoreColor(opportunity.arbitrage_score))}>
              {opportunity.arbitrage_score ?? '—'}
            </span>
          </div>

          <div className="flex items-center justify-between gap-1 pt-0.5">
            <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground truncate">
              <User className="h-3 w-3" />
              {opportunity.persona || '—'}
            </span>
            <div className="flex items-center gap-1">
              {opportunity._ephemeral && (
                <span className="inline-flex items-center gap-0.5 rounded bg-primary/10 text-primary px-1 py-0.5 text-[9px]" title="Demo (não persistido)">
                  <Sparkles className="h-2.5 w-2.5" /> demo
                </span>
              )}
              {busy && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
              {opportunity.cpc_estimate_local && (
                <span className="text-[9px] text-muted-foreground tabular">{opportunity.cpc_estimate_local}</span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
