import React, { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CalendarDays, CheckCircle, Clock, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { format, parseISO, isToday, isBefore } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import type { IncubatorArticle, ScheduleDayGroup, ScheduleProgress } from '@/types/incubator';

interface ScheduleTimelineProps {
  articles: IncubatorArticle[];
  progress: ScheduleProgress | null;
}

export const ScheduleTimeline: React.FC<ScheduleTimelineProps> = ({ articles, progress }) => {
  const scheduledArticles = useMemo(
    () => articles.filter((a) => a.scheduled_at),
    [articles]
  );

  const dayGroups = useMemo(() => {
    const groups = new Map<string, ScheduleDayGroup>();

    for (const article of scheduledArticles) {
      const dateKey = format(parseISO(article.scheduled_at!), 'yyyy-MM-dd');
      if (!groups.has(dateKey)) {
        groups.set(dateKey, {
          date: dateKey,
          articles: [],
          published: 0,
          pending: 0,
          failed: 0,
        });
      }
      const group = groups.get(dateKey)!;
      group.articles.push(article);
      if (article.status === 'published') group.published++;
      else if (article.status === 'failed') group.failed++;
      else group.pending++;
    }

    return Array.from(groups.values()).sort((a, b) => a.date.localeCompare(b.date));
  }, [scheduledArticles]);

  if (scheduledArticles.length === 0) {
    return null;
  }

  const now = new Date();

  return (
    <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 0 }}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="rounded-md bg-primary/10 text-primary p-1.5"><CalendarDays className="h-4 w-4" /></span>
          Timeline de Publicação
          {progress && (
            <span className="text-xs font-normal text-muted-foreground ml-auto tabular">
              {progress.published_count}/{progress.total_scheduled} publicados ({progress.progress_pct}%)
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {dayGroups.map((group, gi) => {
            const dateObj = parseISO(group.date);
            const isCurrentDay = isToday(dateObj);
            const isPast = isBefore(dateObj, now) && !isCurrentDay;
            const allDone = group.published === group.articles.length;

            return (
              <div
                key={group.date}
                className={cn(
                  'rounded-lg border border-border p-3 space-y-2 hover-lift reveal',
                  isCurrentDay && 'border-primary/50 bg-primary/5',
                  isPast && allDone && 'opacity-60'
                )}
                style={{ ['--i' as any]: gi + 1 }}
              >
                {/* Day header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      'text-sm font-medium',
                      isCurrentDay && 'text-primary'
                    )}>
                      {format(dateObj, "EEE, dd/MM", { locale: ptBR })}
                    </span>
                    {isCurrentDay && (
                      <span className="kicker text-[10px] bg-primary text-primary-foreground px-1.5 py-0.5 rounded-full">
                        HOJE
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    {group.published > 0 && (
                      <span className="flex items-center gap-1 text-success tabular">
                        <CheckCircle className="h-3 w-3" /> {group.published}
                      </span>
                    )}
                    {group.pending > 0 && (
                      <span className="flex items-center gap-1 text-muted-foreground tabular">
                        <Clock className="h-3 w-3" /> {group.pending}
                      </span>
                    )}
                    {group.failed > 0 && (
                      <span className="flex items-center gap-1 text-destructive tabular">
                        <XCircle className="h-3 w-3" /> {group.failed}
                      </span>
                    )}
                  </div>
                </div>

                {/* Articles for this day */}
                <div className="space-y-1">
                  {group.articles
                    .sort((a, b) => (a.scheduled_at || '').localeCompare(b.scheduled_at || ''))
                    .map((article) => {
                      const time = format(parseISO(article.scheduled_at!), 'HH:mm');
                      const isPublished = article.status === 'published';
                      const isFailed = article.status === 'failed';

                      return (
                        <div
                          key={article.id}
                          className={cn(
                            'flex items-center gap-2 text-xs py-1 px-2 rounded transition-colors',
                            isPublished && 'bg-success/10 text-success',
                            isFailed && 'bg-destructive/10 text-destructive',
                            !isPublished && !isFailed && 'text-muted-foreground hover:bg-muted/40'
                          )}
                        >
                          <span className="font-mono tabular min-w-[40px]">{time}</span>
                          <span className={cn(
                            'h-1.5 w-1.5 rounded-full flex-shrink-0',
                            isPublished ? 'bg-success' : isFailed ? 'bg-destructive' : 'bg-muted-foreground/40'
                          )} />
                          <span className="truncate flex-1">{article.title}</span>
                        </div>
                      );
                    })}
                </div>
              </div>
            );
          })}
        </div>

        {progress?.next_scheduled_at && (
          <div className="mt-3 pt-3">
            <div className="hairline mb-3" />
            <div className="text-xs text-muted-foreground flex items-center gap-2">
              <Clock className="h-3.5 w-3.5" />
              Próximo artigo: <span className="tabular">{format(parseISO(progress.next_scheduled_at), "dd/MM HH:mm", { locale: ptBR })}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
