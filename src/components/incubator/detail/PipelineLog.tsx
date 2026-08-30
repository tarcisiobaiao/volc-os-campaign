import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Activity } from 'lucide-react';
import type { PipelineLog as PipelineLogType } from '@/types/incubator';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';

interface PipelineLogProps {
  logs: PipelineLogType[];
}

const STATUS_INDICATOR: Record<string, { color: string }> = {
  running:         { color: 'bg-info animate-pulse' },
  success:         { color: 'bg-success'            },
  partial_success: { color: 'bg-warning'            },
  error:           { color: 'bg-destructive'        },
};

export const PipelineLog: React.FC<PipelineLogProps> = ({ logs }) => {
  return (
    <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 0 }}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="rounded-md bg-info/10 text-info p-1.5"><Activity className="h-4 w-4" /></span>
          Pipeline Log
        </CardTitle>
      </CardHeader>
      <CardContent>
        {logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <span className="rounded-lg bg-muted text-muted-foreground p-2.5"><Activity className="h-5 w-5" /></span>
            <p className="kicker">Sem execuções</p>
            <p className="text-sm text-muted-foreground">Nenhuma execução registrada</p>
          </div>
        ) : (
          <div className="space-y-1">
            {logs.map((log, i) => {
              const indicator = STATUS_INDICATOR[log.status] || STATUS_INDICATOR.error;
              const dateStr = format(new Date(log.started_at), "dd/MM HH:mm", { locale: ptBR });
              const duration = log.duration_seconds
                ? log.duration_seconds >= 60
                  ? `${Math.floor(log.duration_seconds / 60)}min`
                  : `${log.duration_seconds}s`
                : '...';

              return (
                <div
                  key={log.id}
                  className="flex items-center gap-3 text-sm py-1.5 px-2 -mx-2 rounded-md hover:bg-muted/40 transition-colors reveal"
                  style={{ ['--i' as any]: i + 1 }}
                >
                  <span className={cn('h-2.5 w-2.5 rounded-full flex-shrink-0', indicator.color)} />
                  <span className="text-muted-foreground min-w-[80px] tabular">{dateStr}</span>
                  <span className="font-medium flex-1 truncate">
                    {log.execution_type === 'content_batch' ? `Lote` : log.execution_type}
                  </span>
                  <span className="text-muted-foreground tabular">
                    {log.articles_succeeded}/{log.articles_attempted} artigos
                  </span>
                  <span className="text-xs text-muted-foreground min-w-[40px] text-right tabular">
                    {duration}
                  </span>
                  {log.articles_failed > 0 && (
                    <span className="text-xs text-destructive tabular">{log.articles_failed} erro(s)</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
