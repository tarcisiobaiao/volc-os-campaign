import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card, CardContent } from '@/components/ui/card';
import { SiteStatusBadge } from '@/components/incubator/StatusBadge';
import { Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { IncubatorSite } from '@/types/incubator';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';

interface KanbanSiteCardProps {
  site: IncubatorSite;
  onClick: (site: IncubatorSite) => void;
}

export const KanbanSiteCard: React.FC<KanbanSiteCardProps> = ({ site, onClick }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: site.id, data: { site }, disabled: site.schedule_active });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const progress = site.total_articles_planned > 0
    ? Math.round((site.total_articles_published / site.total_articles_planned) * 100)
    : 0;

  const updatedAgo = formatDistanceToNow(new Date(site.updated_at), { addSuffix: true, locale: ptBR });

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <Card
        className={cn(
          'border-border hover-lift',
          site.schedule_active ? 'cursor-pointer' : 'cursor-grab active:cursor-grabbing',
          isDragging && 'opacity-50 shadow-elevated'
        )}
        onClick={() => onClick(site)}
      >
        <CardContent className="p-3 space-y-2">
          <div className="flex items-start justify-between gap-1">
            <h4 className="font-semibold text-xs truncate flex-1">{site.site_name}</h4>
            <SiteStatusBadge status={site.status} size="sm" />
          </div>

          <div className="flex items-center gap-1">
            <p className="text-xs text-muted-foreground truncate flex-1">{site.site_niche}</p>
            {site.schedule_active && (
              <Clock className="h-3 w-3 text-info animate-pulse flex-shrink-0" />
            )}
          </div>

          {/* Mini progress bar */}
          <div>
            <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-volc"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-[10px] text-muted-foreground tabular">
                {site.total_articles_published}/{site.total_articles_planned} artigos
              </span>
              <span className="text-[10px] text-muted-foreground">{updatedAgo}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
