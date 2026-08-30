import React, { useEffect, useState } from 'react';
import { pautadorService } from '@/services/pautadorService';
import { cn } from '@/lib/utils';
import { ScrollText, Loader2, FileClock } from 'lucide-react';
import type { AgentLog } from '@/types/pautador';

// Cores de nível em TOKENS (theme-aware): warn/error usam status reservados,
// debug/info ficam na tinta muda para não competir com a mensagem.
const LEVEL_COLOR: Record<string, string> = {
  debug: 'text-muted-foreground/70',
  info: 'text-muted-foreground',
  warn: 'text-warning',
  error: 'text-destructive',
};

const EmptyState: React.FC<{ icon: React.ElementType; label: string; text: string; spin?: boolean }> = ({
  icon: Icon, label, text, spin,
}) => (
  <div className="flex flex-col items-center gap-3 py-12 text-center">
    <span className="flex h-11 w-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
      <Icon className={cn('h-5 w-5', spin && 'animate-spin')} />
    </span>
    <div className="kicker">{label}</div>
    <p className="max-w-xs text-sm text-muted-foreground">{text}</p>
  </div>
);

export const LogsPanel: React.FC<{ runId?: number }> = ({ runId }) => {
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!runId) { setLogs([]); return; }
    setLoading(true);
    pautadorService.fetchLogs(runId)
      .then((l) => !cancelled && setLogs(l))
      .catch(() => !cancelled && setLogs([]))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [runId]);

  if (!runId) {
    return <EmptyState icon={FileClock} label="Sem execução" text="Sem execução persistida para exibir logs." />;
  }
  if (loading) {
    return <EmptyState icon={Loader2} label="Carregando" text="Buscando logs desta execução…" spin />;
  }
  if (!logs.length) {
    return <EmptyState icon={ScrollText} label="Sem logs" text="Nenhum log para esta execução." />;
  }

  return (
    <div className="rounded-lg border border-border divide-y divide-border font-mono text-xs shadow-card">
      {logs.map((log, i) => (
        <div key={log.id ?? `${log.created_at ?? 'log'}-${i}`} className="flex items-start gap-2 p-2 transition-colors hover:bg-muted/40">
          <span className={cn('uppercase font-semibold w-12 shrink-0', LEVEL_COLOR[log.level])}>{log.level}</span>
          <span className="text-muted-foreground w-40 shrink-0 truncate">{log.agent}{log.step ? ` · ${log.step}` : ''}</span>
          <span className="flex-1">{log.message}</span>
          {log.duration_ms != null && <span className="text-muted-foreground shrink-0 tabular">{log.duration_ms}ms</span>}
        </div>
      ))}
    </div>
  );
};
