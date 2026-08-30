import React from 'react';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { Inbox } from 'lucide-react';
import { KanbanSiteCard } from './KanbanSiteCard';
import { cn } from '@/lib/utils';
import type { IncubatorSite, KanbanColumn as KanbanColumnType } from '@/types/incubator';

interface KanbanColumnProps {
  column: KanbanColumnType;
  sites: IncubatorSite[];
  onSiteClick: (site: IncubatorSite) => void;
}

// Dot da coluna mapeado aos tokens semânticos VOLC (frio consistente).
const COLUMN_DOT: Record<string, string> = {
  gray:   'bg-muted-foreground',
  blue:   'bg-info',
  yellow: 'bg-warning',
  purple: 'bg-primary',
  green:  'bg-success',
  red:    'bg-destructive',
};

export const KanbanColumn: React.FC<KanbanColumnProps> = ({ column, sites, onSiteClick }) => {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  const siteIds = sites.map(s => s.id);

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex flex-col rounded-xl border border-border bg-card/40 min-w-[260px] max-w-[300px] w-full transition-colors',
        isOver && 'ring-2 ring-primary/30 border-primary/40'
      )}
    >
      {/* Header */}
      <div className="p-3 border-b border-border flex items-center gap-2">
        <span className={cn('h-2 w-2 rounded-full', COLUMN_DOT[column.color] || 'bg-muted-foreground')} />
        <h3 className="kicker flex-1 truncate">{column.title}</h3>
        <span className="tabular text-xs font-medium text-muted-foreground bg-muted rounded-full px-2 py-0.5">
          {sites.length}
        </span>
      </div>

      {/* Cards */}
      <div className="p-2 flex-1 overflow-y-auto max-h-[calc(100vh-340px)] space-y-2">
        <SortableContext items={siteIds} strategy={verticalListSortingStrategy}>
          {sites.map((site) => (
            <KanbanSiteCard key={site.id} site={site} onClick={onSiteClick} />
          ))}
        </SortableContext>

        {sites.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-1.5 py-8 text-center">
            <Inbox className="h-5 w-5 text-muted-foreground/60" />
            <span className="kicker">Nenhum site</span>
          </div>
        )}
      </div>
    </div>
  );
};
