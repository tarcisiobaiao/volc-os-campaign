import React from 'react';
import { AlertCircle, Check, Cloud, Loader2, Radio, Server, Tag } from 'lucide-react';
import { cn } from '@/lib/utils';

export type LinkState = 'idle' | 'checking' | 'ok' | 'fail';

export interface ChainState {
  gtm: LinkState;
  endpoint: LinkState;
  function: LinkState;
  meta: LinkState;
}

const NODES = [
  { key: 'gtm', label: 'GTM', sub: 'tags no site', icon: Tag },
  { key: 'endpoint', label: 'Endpoint', sub: 'worker + DNS', icon: Cloud },
  { key: 'function', label: 'Function', sub: 'capi-router', icon: Server },
  { key: 'meta', label: 'Meta', sub: 'evento recebido', icon: Radio },
] as const;

const TONE: Record<LinkState, { ring: string; bg: string; text: string; label: string }> = {
  idle: {
    ring: 'border-muted-foreground/25',
    bg: 'bg-muted/40',
    text: 'text-muted-foreground',
    label: 'não testado',
  },
  checking: {
    ring: 'border-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-950/40',
    text: 'text-primary',
    label: 'testando…',
  },
  ok: {
    ring: 'border-emerald-400',
    bg: 'bg-emerald-50 dark:bg-emerald-950/40',
    text: 'text-emerald-600',
    label: 'no ar',
  },
  fail: {
    ring: 'border-destructive/60',
    bg: 'bg-destructive/10',
    text: 'text-destructive',
    label: 'falhou',
  },
};

/**
 * O caminho real de um evento, desenhado. Cada elo acende conforme o teste passa.
 *
 * Não é enfeite: é a superfície de diagnóstico. Quando a conversão não chega na
 * Meta, o que o operador precisa saber é ONDE parou — e é exatamente isso que o
 * elo apagado mostra, sem ler log nenhum.
 */
export const ChainDiagram: React.FC<{ state: ChainState; className?: string }> = ({
  state,
  className,
}) => (
  <div
    className={cn(
      'flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-0 rounded-xl border bg-card p-4',
      className,
    )}
    role="group"
    aria-label="Estado da cadeia de conversões"
  >
    {NODES.map((node, i) => {
      const s = state[node.key];
      const tone = TONE[s];
      const Icon = node.icon;
      const prev = i > 0 ? state[NODES[i - 1].key] : 'ok';

      return (
        <React.Fragment key={node.key}>
          {i > 0 && (
            <div
              className="hidden sm:block flex-1 h-px mx-2 relative overflow-hidden"
              aria-hidden
            >
              <div className="absolute inset-0 bg-border" />
              <div
                className={cn(
                  'absolute inset-y-0 left-0 bg-success transition-[width] duration-200 ease-out',
                  prev === 'ok' ? 'w-full' : 'w-0',
                )}
              />
            </div>
          )}
          {i > 0 && <div className="sm:hidden h-3 w-px bg-border ml-5" aria-hidden />}

          <div className="flex sm:flex-col items-center sm:items-center gap-2 sm:gap-1.5 sm:min-w-[92px]">
            <div
              className={cn(
                'relative h-10 w-10 rounded-full border-2 flex items-center justify-center transition-colors',
                tone.ring,
                tone.bg,
              )}
            >
              {s === 'checking' ? (
                <Loader2 className={cn('h-4 w-4 animate-spin', tone.text)} />
              ) : s === 'ok' ? (
                <Check className={cn('h-4 w-4', tone.text)} />
              ) : s === 'fail' ? (
                <AlertCircle className={cn('h-4 w-4', tone.text)} />
              ) : (
                <Icon className={cn('h-4 w-4', tone.text)} />
              )}
            </div>
            <div className="text-center leading-tight">
              <p className="text-xs font-semibold">{node.label}</p>
              <p className={cn('text-[10px]', s === 'idle' ? 'text-muted-foreground' : tone.text)}>
                {s === 'idle' ? node.sub : tone.label}
              </p>
            </div>
          </div>
        </React.Fragment>
      );
    })}
  </div>
);
