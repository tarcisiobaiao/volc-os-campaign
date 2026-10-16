/** Conversas recentes do PRÓPRIO usuário (o servidor filtra pelo dono). */
import React from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

import type { ConversaDaBia } from '../tipos';

function quando(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const hoje = new Date();
  const ontem = new Date(hoje);
  ontem.setDate(hoje.getDate() - 1);
  const mesmoDia = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (mesmoDia(d, hoje)) return `hoje, ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
  if (mesmoDia(d, ontem)) return 'ontem';
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
}

interface Props {
  conversas: ConversaDaBia[] | null;
  atual: string | null;
  onAbrir: (id: string) => void;
}

export const ListaDeConversas: React.FC<Props> = ({ conversas, atual, onAbrir }) => {
  if (!conversas) {
    return (
      <div role="status" aria-label="Carregando conversas" className="space-y-2 p-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full rounded-md" />)}
      </div>
    );
  }
  if (!conversas.length) {
    return <p className="p-4 text-sm text-muted-foreground">Você ainda não tem conversas com a Bia nesta interface.</p>;
  }
  return (
    <ul aria-label="Conversas recentes" className="space-y-0.5 p-2">
      {conversas.map((c) => {
        const corrente = c.id === atual;
        return (
          <li key={c.id}>
            <button
              type="button"
              onClick={() => onAbrir(c.id)}
              aria-current={corrente ? 'true' : undefined}
              className={cn(
                'flex min-h-12 w-full flex-col items-start justify-center gap-0.5 rounded-md px-3 py-2 text-left transition-volc duration-[140ms] ease-enter hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70',
                corrente && 'bg-muted',
              )}
            >
              <span className="line-clamp-1 w-full text-sm font-medium text-foreground">
                {c.titulo?.trim() || 'Conversa sem mensagens'}
              </span>
              <span className="text-micro font-normal tracking-normal text-muted-foreground">
                {quando(c.atualizada_em)}
                {typeof c.mensagens === 'number' ? ` · ${c.mensagens} ${c.mensagens === 1 ? 'mensagem' : 'mensagens'}` : ''}
                {corrente ? ' · aberta' : ''}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
};
