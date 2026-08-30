import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CheckCircle, XCircle, Clock, CalendarClock } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import type { IncubatorSite } from '@/types/incubator';

interface SiteProgressProps {
  site: IncubatorSite;
}

export const SiteProgress: React.FC<SiteProgressProps> = ({ site }) => {
  const { total_articles_planned, total_articles_published, total_articles_failed } = site;
  const pending = Math.max(0, total_articles_planned - total_articles_published - total_articles_failed);
  const progress = total_articles_planned > 0
    ? Math.round((total_articles_published / total_articles_planned) * 100)
    : 0;

  return (
    <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 1 }}>
      <CardHeader className="pb-3">
        <CardTitle className="kicker">Progresso de Conteúdo</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Progress Bar */}
        <div>
          <div className="flex items-baseline justify-between mb-2">
            <span className="font-display text-2xl font-bold tabular tracking-tight">{progress}%</span>
            <span className="text-sm text-muted-foreground tabular">
              {total_articles_published}/{total_articles_planned} artigos
            </span>
          </div>
          <div className="h-3 w-full bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-[width] duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Counters */}
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1.5 text-success">
            <CheckCircle className="h-4 w-4" />
            <span className="tabular">{total_articles_published} publicados</span>
          </div>
          {total_articles_failed > 0 && (
            <div className="flex items-center gap-1.5 text-destructive">
              <XCircle className="h-4 w-4" />
              <span className="tabular">{total_articles_failed} falhou</span>
            </div>
          )}
          {pending > 0 && (
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Clock className="h-4 w-4" />
              <span className="tabular">{pending} pendentes</span>
            </div>
          )}
        </div>

        {/* Schedule info */}
        {site.schedule_active && (
          <div className="pt-3">
            <div className="hairline mb-3" />
            <div className="flex items-center gap-3 text-sm">
              <div className="flex items-center gap-1.5 text-info">
                <CalendarClock className="h-4 w-4 animate-pulse" />
                <span>Schedule ativo</span>
              </div>
              {site.schedule_window_start && site.schedule_window_end && (
                <span className="text-xs text-muted-foreground tabular">
                  Janela: {site.schedule_window_start}–{site.schedule_window_end}
                </span>
              )}
              {site.schedule_estimated_completion && (
                <span className="text-xs text-muted-foreground tabular ml-auto">
                  Conclusão prevista: {format(parseISO(site.schedule_estimated_completion), 'dd/MM/yyyy', { locale: ptBR })}
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
