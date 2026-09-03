/**
 * A ação dominante de uma região — e a razão pela qual ela não pode agir.
 *
 * ## ⚠️ A razão é VISÍVEL, em todos os breakpoints
 *
 * O contra-modelo está medido: `NovaCampanhaPage.tsx:461-479` desabilita
 * "Lançar outra" em silêncio e mostra o motivo de "Lançar campanha" apenas de
 * `sm:` para cima (`hidden … sm:block`) — some justamente no telefone, onde a
 * tela é menor e o operador tem menos contexto. `VISUAL-DIRECTION.md §2` marca
 * isso como `major`, e `MOTION-AND-INTERACTION.md §3` nomeia o modelo correto,
 * que já existe em `lote/QuadroDoLote.tsx:305-335`: `disabled` + `aria-disabled`
 * + parágrafo adjacente ligado por `aria-describedby`.
 *
 * ## ⚠️ TODAS as faltas, sem "+N"
 *
 * Cortar a lista em duas e escrever "+3" devolve ao operador o trabalho de
 * descobrir o que falta — que é exatamente o trabalho que este parágrafo
 * existe para poupar. Se são cinco faltas, são cinco linhas.
 *
 * ## Movimento
 *
 * Só `background-color` e `transform`, nomeados (`design.md:116,122`). Press
 * `scale(0.96)` exato — nunca abaixo de 0,95. O lift de hover mora dentro de
 * `@media (hover:hover) and (pointer:fine)` porque em tela de toque o "hover"
 * fica grudado depois do toque e o botão sobe e não desce. O anel de foco NÃO
 * entra na transição (`MOTION-AND-INTERACTION.md §8.11`): foco atrasado é foco
 * perdido.
 */
import React, { useId } from 'react';
import { Loader2 } from 'lucide-react';

import { cn } from '@/lib/utils';

export const AcaoDominante: React.FC<{
  children: React.ReactNode;
  onClick?: () => void;
  pode: boolean;
  /** Por que não pode. Vem do servidor e aparece INTEIRA, sempre. */
  faltas: string[];
  enviando?: boolean;
  type?: 'button' | 'submit';
  className?: string;
}> = ({ children, onClick, pode, faltas, enviando = false, type = 'button', className }) => {
  const semente = useId();
  const idFaltas = `faltas-${semente}`;
  const lista = faltas ?? [];
  const temFaltas = lista.length > 0;
  const travado = !pode || enviando;

  return (
    <div className="space-y-2">
      <button
        type={type}
        onClick={onClick}
        disabled={travado}
        // `disabled` tira o botão da ordem de foco e leva o `aria-describedby`
        // junto; `aria-disabled` mantém a afirmação para quem inspeciona a
        // árvore. A razão não depende de nenhum dos dois: ela está na tela.
        aria-disabled={travado}
        aria-busy={enviando}
        aria-describedby={temFaltas ? idFaltas : undefined}
        className={cn(
          // 44px no toque, 40px no desktop — a altura de controle de
          // `design.md:43` e o alvo mínimo de `RESPONSIVE-AND-A11Y.md`.
          'inline-flex h-11 items-center justify-center gap-2 rounded-md px-4 md:h-10',
          'text-sm font-semibold',
          'bg-primary text-primary-foreground',
          'transition-[background-color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)]',
          'hover:bg-[hsl(var(--primary-hover))]',
          '[@media(hover:hover)and(pointer:fine)]:hover:-translate-y-px',
          'active:scale-[0.96]',
          'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
          'disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0',
          className,
        )}
      >
        {/* O rótulo NÃO é substituído: trocá-lo por "Enviando…" apaga o que o
            operador autorizou no exato momento em que ele quer conferir. O
            spinner entra ao lado e a largura do botão só cresce uma vez.
            `animate-spin` sobrevive a `prefers-reduced-motion` de propósito
            (`src/index.css:592`): um spinner parado lê como tela travada. */}
        {enviando ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden /> : null}
        {children}
      </button>

      {temFaltas && (
        <div id={idFaltas} className="max-w-[70ch]">
          <p className="text-sm text-muted-foreground">
            {lista.length === 1 ? 'Falta para liberar:' : `Faltam ${lista.length} coisas para liberar:`}
          </p>
          {/* 14px: é texto que decide (`design.md:172`). Nada de 11px aqui — a
              auditoria mediu 235 ocorrências desse piso rompido em `trafego/`. */}
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm leading-relaxed text-pretty text-muted-foreground">
            {lista.map((f, i) => (
              <li key={`${f}-${i}`}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
