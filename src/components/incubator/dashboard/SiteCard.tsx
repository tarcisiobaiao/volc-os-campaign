import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { SiteStatusBadge } from '@/components/incubator/StatusBadge';
import { Play, Pause, Eye, Globe, CalendarClock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { STATUS_COLORS } from '@/types/incubator';
import type { IncubatorSite } from '@/types/incubator';
import { formatDistanceToNow, format, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';

interface SiteCardProps {
  site: IncubatorSite;
  onView: (site: IncubatorSite) => void;
  onTrigger: (site: IncubatorSite) => void;
  onPause: (site: IncubatorSite) => void;
  index?: number;
}

export const SiteCard: React.FC<SiteCardProps> = ({ site, onView, onTrigger, onPause, index = 0 }) => {
  const progress = site.total_articles_planned > 0
    ? Math.round((site.total_articles_published / site.total_articles_planned) * 100)
    : 0;

  const borderColor = STATUS_COLORS[site.status]?.dot?.replace('bg-', 'border-') || 'border-border';
  const updatedAgo = formatDistanceToNow(new Date(site.updated_at), { addSuffix: true, locale: ptBR });

  const canTrigger = ['draft', 'content_ready', 'review', 'paused'].includes(site.status);
  const canPause = ['content_generating'].includes(site.status);

  return (
    <Card
      className={cn(
        'border-l-4 hover-lift reveal cursor-pointer group',
        borderColor
      )}
      style={{ ['--i' as any]: index }}
      onClick={() => onView(site)}
    >
      <CardContent className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <Globe className="h-4 w-4 text-muted-foreground flex-shrink-0" />
              <h3 className="font-semibold text-sm truncate">{site.site_name}</h3>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 truncate">{site.site_niche}</p>
          </div>
          <SiteStatusBadge status={site.status} size="sm" />
        </div>

        {/* Progress Bar */}
        <div>
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
            <span className="tabular">{site.total_articles_published}/{site.total_articles_planned} artigos</span>
            <span className="tabular">{progress}%</span>
          </div>
          <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-volc duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
          {site.total_articles_failed > 0 && (
            <p className="text-xs text-destructive mt-1 tabular">{site.total_articles_failed} falha(s)</p>
          )}
        </div>

        {/* Schedule Badge */}
        {site.schedule_active && site.schedule_estimated_completion && (
          <div className="flex items-center gap-1.5 text-xs text-info bg-info/10 rounded-full px-2 py-1">
            <CalendarClock className="h-3 w-3 animate-pulse" />
            <span>
              Agendado até {format(parseISO(site.schedule_estimated_completion), 'dd/MM', { locale: ptBR })}
            </span>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-1">
          <span className="text-xs text-muted-foreground">{updatedAgo}</span>
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
            {canTrigger && (
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onTrigger(site)} title="Executar pipeline">
                <Play className="h-3.5 w-3.5 text-success" />
              </Button>
            )}
            {canPause && (
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onPause(site)} title="Pausar">
                <Pause className="h-3.5 w-3.5 text-warning" />
              </Button>
            )}
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onView(site)} title="Ver detalhes">
              <Eye className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
