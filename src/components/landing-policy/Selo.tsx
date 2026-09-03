/**
 * O selo da prontidão de destino: glifo, palavra e descrição. Cor é o terceiro sinal.
 *
 * ## Por que não importa o `Chip` do inventário de Tráfego
 *
 * Pelo mesmo motivo que `components/criativos/comum/Selo.tsx` não importa — as
 * linhas 4 a 11 daquele arquivo são o precedente desta cópia. A política de
 * destino não pertence ao inventário do Google Ads: importar de
 * `components/trafego/inventario/` faria o primeiro consumidor do formato virar
 * dono dele, e o segundo chegaria pedindo para desfazer. O DESENHO é o mesmo de
 * propósito, para o operador ler a mesma língua nas duas áreas; a dependência é
 * que não existe.
 *
 * ⚠️ A cor semântica fica na borda, no fundo e no glifo, NUNCA na palavra:
 * `--warning` no tema claro contra a superfície dá contraste insuficiente para
 * texto de 11px, e colorir a palavra é o jeito mais comum de tornar ilegível
 * justamente o rótulo que precisa ser lido.
 *
 * ⚠️ Nenhum tom usa `aurora-blue`, `aurora-purple` ou `aurora-orange`. A aurora
 * é assinatura de marca; um estado operacional pintado de aurora faz a marca
 * virar cor de alerta.
 *
 * ⚠️ E não existe tom "quase provado". São QUATRO, e só `provado` é positivo —
 * um quinto tom verde-claro para `INDETERMINADO` seria o defeito inteiro desta
 * sprint reintroduzido pela paleta.
 */
import React from 'react';
import { CircleCheck, CircleDashed, CircleOff, CircleSlash } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { TomDaProntidao } from '@/lib/landing-policy/prontidao';

type Glifo = React.ComponentType<{ className?: string }>;

const TINTA: Record<TomDaProntidao, string> = {
  provado: 'border-success/45 bg-success/[0.08] text-foreground',
  negado: 'border-destructive/50 bg-destructive/[0.08] text-foreground',
  ignorado: 'border-border/70 bg-muted/40 text-foreground',
  ausente: 'border-border/50 bg-transparent text-muted-foreground',
};

const TINTA_DO_GLIFO: Record<TomDaProntidao, string> = {
  provado: 'text-success',
  negado: 'text-destructive',
  ignorado: 'text-muted-foreground',
  ausente: 'text-muted-foreground/70',
};

/** O glifo de cada tom. `ignorado` é um traço aberto: ninguém respondeu. */
export const GLIFO_DO_TOM: Record<TomDaProntidao, Glifo> = {
  provado: CircleCheck,
  negado: CircleSlash,
  ignorado: CircleDashed,
  ausente: CircleOff,
};

export const Selo: React.FC<{
  glifo?: Glifo;
  palavra: string;
  /** O que a palavra afirma. Vai para o leitor de tela e para o `title`. */
  descricao: string;
  tom?: TomDaProntidao;
  className?: string;
}> = ({ glifo, palavra, descricao, tom = 'ignorado', className }) => {
  const G = glifo ?? GLIFO_DO_TOM[tom];
  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center gap-1.5 rounded-sm border px-1.5 py-0.5',
        'font-display text-[0.6875rem] font-semibold uppercase leading-none tracking-[0.08em]',
        TINTA[tom],
        className,
      )}
      title={`${palavra}. ${descricao}`}
      data-tom={tom}
    >
      <G className={cn('h-3 w-3 shrink-0', TINTA_DO_GLIFO[tom])} aria-hidden />
      <span className="truncate">{palavra}</span>
      {/* A descrição é o que o selo AFIRMA; sem ela um leitor de tela ouve
          "apto" sem saber apto para quê. */}
      <span className="sr-only">. {descricao}</span>
    </span>
  );
};
