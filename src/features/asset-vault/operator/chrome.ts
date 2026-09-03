/**
 * Tokens locais da experiência do Cofre. Não criam terceira linguagem:
 * só combinam classes já existentes em design.md / index.css.
 *
 * Hallmark · pre-emit critique: P5 H5 E4 S5 R5 V4
 * Macrostructure: mission-control strip + dense inventory table + inspector
 */
export const PRESSIONAR =
  "transition-transform duration-150 ease-out active:scale-[0.96] motion-reduce:transition-none motion-reduce:active:scale-100";

export const FOCO =
  "outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

export const HIT = "min-h-10 min-w-10";

export const ENTRADA =
  `h-10 w-full rounded-md border border-input bg-background px-3 text-sm ${FOCO}`;

export const AREA =
  `min-h-[5.5rem] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ${FOCO}`;

const DESABILITADO = "disabled:cursor-not-allowed disabled:opacity-55";

export const PRIMARIO =
  `inline-flex items-center justify-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground ${HIT} ${FOCO} ${PRESSIONAR} ${DESABILITADO}`;

export const SECUNDARIO =
  `inline-flex items-center justify-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium ${HIT} ${FOCO} ${PRESSIONAR} hover:bg-muted ${DESABILITADO}`;

export const PERIGO =
  `inline-flex items-center justify-center gap-2 rounded-md border border-destructive/35 bg-background px-3 text-sm font-medium text-destructive ${HIT} ${FOCO} ${PRESSIONAR} hover:bg-destructive/10 ${DESABILITADO}`;

export const POCO_ABAS =
  "inline-flex min-h-10 flex-wrap gap-1 rounded-md bg-muted p-1";

export const ABA_ATIVA =
  `inline-flex items-center justify-center gap-2 rounded-md bg-card px-3 text-sm font-medium text-foreground shadow-sm ${HIT} ${FOCO} ${PRESSIONAR}`;

export const ABA_INATIVA =
  `inline-flex items-center justify-center gap-2 rounded-md px-3 text-sm font-medium text-muted-foreground ${HIT} ${FOCO} ${PRESSIONAR} hover:text-foreground`;
