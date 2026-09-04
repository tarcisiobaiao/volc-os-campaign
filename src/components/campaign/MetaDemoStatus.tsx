/**
 * Estado de frescor e período para telas Meta em modo demonstrativo.
 *
 * Google usa `DateFilter` (Select interativo) e `DataStatus` (badge com
 * timestamp real de `system_settings`). Nenhum dos dois se aplica aqui: os
 * dados Meta são fixos e nenhuma leitura real aconteceu, então oferecer um
 * seletor de período que não muda nada, ou um selo "Dados atualizados" ligado
 * a um timestamp de outra integração, seria fingir uma capacidade que não
 * existe (`design.md`: "State capability honestly").
 *
 * O que se preserva é a GEOMETRIA: mesmo slot, mesma altura, mesmo tipo de
 * controle — só o conteúdo muda para o que é verdade neste cenário.
 */
import React from 'react';
import { Calendar as CalendarIcon, Info } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

export const MetaPeriodoChip: React.FC<{ label: string; className?: string }> = ({ label, className }) => (
  <button
    type="button"
    disabled
    title="Período fixo no cenário demonstrativo Meta — ainda não há sincronização real para filtrar por data."
    className={cn(
      'flex h-10 items-center gap-2 rounded-md border border-border bg-card px-3 text-left text-sm text-muted-foreground',
      'disabled:cursor-not-allowed disabled:opacity-80',
      className,
    )}
  >
    <CalendarIcon className="h-4 w-4 flex-shrink-0" aria-hidden />
    <span className="truncate">{label}</span>
  </button>
);

export const MetaFrescorBadge: React.FC<{ className?: string }> = ({ className }) => (
  <Badge
    variant="outline"
    className={cn('flex items-center gap-1.5 whitespace-nowrap border-warning/25 bg-warning/12 text-warning', className)}
    title="Pré-visualização Meta: dados fictícios para validar a experiência. Nenhuma leitura real da Marketing API ou escrita no Supabase aconteceu."
  >
    <Info className="h-3 w-3 flex-shrink-0" aria-hidden />
    <span className="whitespace-nowrap">Dados demonstrativos</span>
  </Badge>
);
