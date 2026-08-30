/**
 * Histórico removido: acessível, e visualmente subordinado.
 *
 * Medido na primeira varredura real: 79 das 84 campanhas estavam removidas.
 * Misturá-las com as 5 operacionais faz o olho tratar história como operação.
 * Por isso o padrão esconde, e a abertura é uma ação explícita com a
 * quantidade vinda do servidor — nunca um 79 escrito na tela.
 */
import React from 'react';
import { History } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export const BotaoDoHistorico: React.FC<{
  quantidade: number | null;
  aberto: boolean;
  aoAbrir: () => void;
  aoFechar: () => void;
}> = ({ quantidade, aberto, aoAbrir, aoFechar }) => {
  if (aberto) {
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-11 px-3 text-xs md:h-9"
        onClick={aoFechar}
      >
        ocultar histórico removido
      </Button>
    );
  }

  const trecho =
    quantidade == null
      ? 'Mostrar histórico removido'
      : quantidade === 1
        ? 'Mostrar histórico removido: 1'
        : `Mostrar histórico removido: ${quantidade}`;

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="h-11 gap-2 px-3 text-xs font-normal text-muted-foreground md:h-9"
      onClick={aoAbrir}
    >
      <History className="h-3.5 w-3.5" aria-hidden />
      {trecho}
    </Button>
  );
};

export const FaixaDoHistorico: React.FC<{
  quantidade: number | null;
  children?: React.ReactNode;
}> = ({ quantidade, children }) => (
  <section
    aria-label="histórico removido"
    className={cn(
      'mt-8 border-t border-dashed border-border pt-5',
      'opacity-80',
    )}
  >
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h3 className="font-display text-sm font-semibold text-muted-foreground">
        Histórico removido
      </h3>
      {quantidade != null && (
        <span className="tabular text-[11px] text-muted-foreground">
          {quantidade === 1 ? '1 campanha' : `${quantidade} campanhas`}
        </span>
      )}
    </div>
    <p className="mb-4 max-w-[70ch] text-[12px] leading-relaxed text-muted-foreground">
      Campanhas que a conta declara como removidas. Não competem com as operacionais:
      não gastam, não pedem lance, e não entram na fila de atenção.
    </p>
    {children}
  </section>
);

export default BotaoDoHistorico;
