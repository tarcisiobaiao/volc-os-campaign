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
import { Calendar as CalendarIcon, FlaskConical, Info } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

/**
 * A faixa que diz, sem depender de cor, que NADA abaixo dela veio de uma conta.
 *
 * ⚠️ Ela é conteúdo fixo (`role="note"`), e não um `toast`.
 *
 * O selo `MetaFrescorBadge` já existia e continua útil, mas ele é um chip de
 * 11 px ao lado de um filtro: numa tela cheia de cartões financeiros com aspecto
 * de produção, quem chega no meio da rolagem — ou olha um print — não o
 * encontra. Um aviso que some sozinho é pior ainda: a tela fica idêntica a uma
 * tela real assim que ele expira.
 *
 * A frase diz três coisas em ordem: que é demonstração, que nenhuma conta foi
 * consultada, e onde está a leitura real. A última importa tanto quanto as
 * outras — sem ela, o operador que percebeu o aviso ainda não sabe para onde ir.
 */
export const FaixaDeDemonstracao: React.FC<{ oQue: string; className?: string }> = ({
  oQue,
  className,
}) => (
  <div
    role="note"
    aria-label="cenário demonstrativo"
    className={cn('rounded-md border border-warning/40 bg-warning/[0.08] px-4 py-3', className)}
  >
    <div className="flex items-start gap-2">
      <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
      <p className="max-w-[80ch] text-[13px] leading-relaxed">
        <strong className="font-semibold">Cenário demonstrativo — nada aqui é real.</strong>{' '}
        {oQue} Nenhuma conta Meta foi consultada, nenhum número foi medido e nenhuma decisão de
        gasto deve sair desta tela. A leitura real vive na mesma rota sem{' '}
        <code className="rounded-sm bg-muted px-1 py-0.5 text-[12px]">?modo=demo</code>.
      </p>
    </div>
  </div>
);

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
