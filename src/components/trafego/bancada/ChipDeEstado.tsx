/**
 * O chip de estado da Bancada Guiada.
 *
 * ## Por que este chip existe se `inventario/Selos.tsx` já tem um
 *
 * O `Chip` do inventário (`src/components/trafego/inventario/Selos.tsx:99-121`)
 * é 11px, caixa alta e `rounded-sm`. Ele foi desenhado para uma TABELA, onde
 * dezenas de selos disputam a mesma coluna e o operador varre a coluna inteira
 * de olho. A Bancada é o oposto: um estado por decisão, lido uma vez, e o
 * estado é justamente o texto que sustenta a decisão.
 *
 * Duas regras da casa colidiam com o selo de tabela quando ele vinha para cá:
 * `design.md:172` ("essential actions and explanatory text never drop below
 * 14px" e o piso de 13px em metadado denso) e `VISUAL-DIRECTION.md §8`, que
 * proíbe caixa alta fora do `.kicker`. O front-matter de `design.md:56-58`
 * fixa a geometria deste chip — raio 999px, altura 24px — e é ela que está
 * implementada aqui: `rounded-full h-6`, 13px, caixa de sentença.
 *
 * ## A gramática herdada sem uma vírgula de mudança: glifo + palavra + descrição
 *
 * `PRODUCT.md:36` e `design.md:166` dizem a mesma coisa por caminhos
 * diferentes: cor nunca é o único portador de significado. Então a cor
 * semântica vive na BORDA, no LEITO e no GLIFO — nunca na palavra.
 *
 * ⚠️ A palavra é sempre `text-foreground`. `--warning` no claro é
 * `36 90% 28%` (`src/index.css:68`): escrever a palavra do estado com a cor do
 * estado é o jeito mais eficiente de tornar ilegível exatamente o rótulo que
 * decide. O mesmo raciocínio já está registrado em `Selos.tsx:70-78`.
 */
import React from 'react';

import { cn } from '@/lib/utils';

/**
 * ⚠️ `verificado` NÃO é `bom`, e `info` não é nenhum dos dois.
 *
 * A separação vem de `design.md:162`: `verified` afirma que a fonte foi
 * OBSERVADA ou reconciliada, e "does not mean success". A união é copiada de
 * `Selos.tsx:56` de propósito — dois vocabulários de tom no mesmo produto
 * divergiriam na primeira cor nova.
 */
export type TomDoChip = 'neutro' | 'bom' | 'verificado' | 'atencao' | 'ruim' | 'info';

/** O leito: borda e fundo. A cor mora aqui, nunca no texto. */
const LEITO: Record<TomDoChip, string> = {
  neutro: 'border-border bg-muted/50',
  bom: 'border-success/40 bg-success/[0.08]',
  verificado: 'border-verified/45 bg-verified/[0.08]',
  atencao: 'border-warning/50 bg-warning/[0.10]',
  ruim: 'border-destructive/45 bg-destructive/[0.08]',
  info: 'border-info/40 bg-info/[0.08]',
};

/** O glifo: o segundo portador. Sobrevive ao print em preto e branco pela FORMA. */
const TINTA_DO_GLIFO: Record<TomDoChip, string> = {
  neutro: 'text-muted-foreground',
  bom: 'text-success',
  verificado: 'text-verified',
  atencao: 'text-warning',
  ruim: 'text-destructive',
  info: 'text-info',
};

export const ChipDeEstado: React.FC<{
  glifo: React.ComponentType<{ className?: string }>;
  palavra: string;
  /** O que a palavra AFIRMA. Vai para o leitor de tela e para o `title`. */
  descricao: string;
  tom?: TomDoChip;
  className?: string;
}> = ({ glifo: Glifo, palavra, descricao, tom = 'neutro', className }) => (
  <span
    className={cn(
      'inline-flex h-6 max-w-full items-center gap-1.5 rounded-full border px-2.5',
      // 13px é o piso de metadado de `VISUAL-DIRECTION.md §3`. Caixa de
      // sentença: caixa alta é auxílio de navegação, não textura (`design.md:174`).
      'text-[0.8125rem] font-medium leading-none text-foreground',
      LEITO[tom],
      className,
    )}
    title={`${palavra} — ${descricao}`}
  >
    <Glifo className={cn('h-3.5 w-3.5 shrink-0', TINTA_DO_GLIFO[tom])} aria-hidden />
    <span className="truncate">{palavra}</span>
    {/* ⚠️ Não é redundância. `title` não é lido por leitor de tela em toque nem
        por teclado; sem esta linha o chip afirma "bloqueado" e some com o
        motivo justamente para quem mais depende dele. */}
    <span className="sr-only"> — {descricao}</span>
  </span>
);
