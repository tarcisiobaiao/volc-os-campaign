/**
 * O bloco de evidência e a linha de fato — a calha de 24px da Bancada.
 *
 * ## Por que a calha existe
 *
 * `VISUAL-DIRECTION.md §6.1`: cada bloco de decisão tem uma calha esquerda de
 * 24px que carrega só o glifo de estado. O texto começa sempre na mesma coluna,
 * em todos os blocos, em todas as paradas. O efeito é um lugar fixo para o olho
 * conferir "isto foi medido?" sem ler — e um ritmo vertical de instrumento, que
 * é o que separa uma bancada de uma pilha de cartões.
 *
 * ## ⚠️ Isto é um POÇO, não um cartão
 *
 * `design.md:100`: "Nested cards are always wrong". Dentro de uma superfície
 * `bg-card` aninham-se hairlines e poços `bg-muted/20`, nunca outra
 * `shadow-card`. Não há sombra neste arquivo, e a ausência é a especificação.
 *
 * ## ⚠️ O estado entra por hairline de 2px no TOPO
 *
 * `design.md:99` autoriza exatamente isso e proíbe a faixa lateral colorida
 * acima de 1px. A auditoria mediu 12 `border-l-2` coloridas em `trafego/`
 * (`VISUAL-DIRECTION.md §2`, entre elas `PortoesDoCanal.tsx:100`); esta pasta
 * nasce sem nenhuma.
 */
import React from 'react';
import { CircleAlert, CircleCheck, CircleDot, CircleHelp, Info, TriangleAlert } from 'lucide-react';

import { cn } from '@/lib/utils';

import type { TomDoChip } from './ChipDeEstado';

/** O hairline de 2px no topo, por tom. */
const HAIRLINE: Record<TomDoChip, string> = {
  neutro: 'before:bg-border',
  bom: 'before:bg-success',
  verificado: 'before:bg-verified',
  atencao: 'before:bg-warning',
  ruim: 'before:bg-destructive',
  info: 'before:bg-info',
};

/** O glifo da calha. Cor sem forma não sobrevive ao print em preto e branco. */
const GLIFO: Record<TomDoChip, { Icone: React.ComponentType<{ className?: string }>; tinta: string }> = {
  neutro: { Icone: CircleDot, tinta: 'text-muted-foreground' },
  bom: { Icone: CircleCheck, tinta: 'text-success' },
  verificado: { Icone: CircleDot, tinta: 'text-verified' },
  atencao: { Icone: TriangleAlert, tinta: 'text-warning' },
  ruim: { Icone: CircleAlert, tinta: 'text-destructive' },
  info: { Icone: Info, tinta: 'text-info' },
};

export const BlocoDeEvidencia: React.FC<{
  titulo: string;
  children: React.ReactNode;
  /** Pinta o hairline de 2px no topo e acende o glifo da calha. */
  tom?: TomDoChip;
  /** Um controle secundário, no canto. Nunca a ação dominante da região. */
  acao?: React.ReactNode;
}> = ({ titulo, children, tom, acao }) => {
  const desenho = tom ? (GLIFO[tom] ?? GLIFO.neutro) : null;
  return (
    <section
      className={cn(
        'relative overflow-hidden rounded-md border border-border/60 bg-muted/20 p-3',
        tom && "before:absolute before:inset-x-0 before:top-0 before:h-[2px] before:content-['']",
        tom && (HAIRLINE[tom] ?? HAIRLINE.neutro),
      )}
    >
      <div className="grid grid-cols-[24px_minmax(0,1fr)] gap-x-2 gap-y-3">
        <div className="flex h-5 items-center justify-center">
          {desenho ? (
            <desenho.Icone className={cn('h-4 w-4', desenho.tinta)} aria-hidden />
          ) : null}
        </div>
        <div className="flex items-start justify-between gap-3">
          {/* 15px/600 é o H3 de bloco de `VISUAL-DIRECTION.md §3`. Inter, não
              display: o display carrega identidade, e um bloco de evidência é
              trabalho. */}
          <h3 className="min-w-0 text-[0.9375rem] font-semibold leading-5 text-balance text-foreground">
            {titulo}
          </h3>
          {acao ? <div className="shrink-0">{acao}</div> : null}
        </div>
        <div className="col-start-2 min-w-0">{children}</div>
      </div>
    </section>
  );
};

/**
 * Uma linha de fato: rótulo, valor, fonte e — quando é medida — frescor.
 *
 * ## ⚠️ ESTA É A LINHA QUE NÃO PODE MENTIR
 *
 * `valor === null` e `valor === undefined` são AUSÊNCIA e escrevem a palavra de
 * ausência em `text-muted-foreground`. Nunca `0`, nunca célula vazia. A regra é
 * de `design.md:148` ("Absence, failure, stale data and measured zero are
 * different states") e de `:247`, e o tipo já a carrega em
 * `src/types/trafego.ts:289` ("`null` = ausência. A tela escreve '—' e diz quem
 * não leu. Nunca `0`").
 *
 * O defeito que isto impede tem forma conhecida: `{valor || ausencia}` parece
 * certo e transforma um zero MEDIDO em "não medido" — e `{valor ?? 0}`
 * transforma "não perguntei" em "perguntei e deu zero". As duas leituras levam
 * a decisões de gasto opostas. Por isso o teste do módulo é literal: passar
 * `null` não pode produzir `0` no DOM
 * (`__tests__/linha-de-fato.test.tsx`).
 *
 * Zero MEDIDO continua sendo zero e aparece como zero: `0` é um `ReactNode`
 * válido e não cai no ramo de ausência.
 */
export const LinhaDeFato: React.FC<{
  rotulo: string;
  /** `null`/`undefined` = ausência. Qualquer outra coisa é o valor, inclusive `0`. */
  valor: React.ReactNode | null;
  /** De onde veio. "você, agora", "a conta", "a mineração". */
  fonte?: string;
  /** Só quando o valor é MEDIDA. Ausente = não se carimba nada. */
  frescor?: string | null;
  ausencia?: string;
}> = ({ rotulo, valor, fonte, frescor, ausencia = 'não medido' }) => {
  const ausente = valor === null || valor === undefined;
  // "—" sozinho não é conteúdo para leitor de tela (`RESPONSIVE-AND-A11Y.md §5.5`).
  // Quando a palavra de ausência é um símbolo, quem ouve recebe a palavra.
  const simbolica = ausente && !/\p{L}/u.test(ausencia);

  return (
    // ⚠️ `<span>`, e NÃO `<dt>`/`<dd>`. A dupla de definição só é válida dentro
    // de um `<dl>`, e este componente não pode garantir o ancestral: ele entra
    // no `children` livre de `BlocoDeEvidencia`. Um `<dl>` por linha resolveria
    // a validade e criaria outro problema — o leitor de tela anunciaria "lista
    // com 1 item" a cada fato, dez vezes por parada.
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 py-1">
      <span className="text-sm text-pretty text-muted-foreground">{rotulo}</span>
      <span
        className={cn(
          // `tabular` força numerais tabulares (`src/index.css:369-372`): sem
          // eles um valor que atualiza muda de largura e a coluna dança.
          'tabular text-right text-sm',
          ausente ? 'text-muted-foreground' : 'font-medium text-foreground',
        )}
      >
        {ausente ? (
          <>
            <span aria-hidden={simbolica || undefined}>{ausencia}</span>
            {simbolica && <span className="sr-only">ausente</span>}
          </>
        ) : (
          valor
        )}
      </span>
      {(fonte || frescor) && (
        <p className="col-span-2 text-[0.8125rem] leading-5 text-muted-foreground">
          {fonte ? `fonte: ${fonte}` : null}
          {/* ⚠️ Frescor só quando VEIO. Carimbar "agora" numa linha sem leitura
              seria inventar frescor, que `design.md:247` proíbe por nome. */}
          {fonte && frescor ? ' · ' : null}
          {frescor ?? null}
        </p>
      )}
    </div>
  );
};
