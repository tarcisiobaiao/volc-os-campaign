/**
 * Tokens de movimento para framer-motion, espelhando as vars de `src/index.css`.
 *
 * O CSS é a autoridade (design.md §Motion e §V3). Este arquivo existe porque o
 * framer-motion recebe número e array, não `var(--motion-dado)`. Se um valor
 * mudar lá, muda aqui no mesmo commit — `instrumento.test.ts` confere.
 */

/** Segundos, como o framer-motion espera. */
export const DURACAO = {
  press: 0.14,
  menu: 0.2,
  sheet: 0.28,
  /** Chegada de dado: tick de número, desenho de sparkline. Uma vez por valor. */
  dado: 0.64,
} as const;

export const CURVA = {
  enter: [0.22, 1, 0.36, 1],
  move: [0.25, 1, 0.5, 1],
  /** Expo-out: o número chega rápido e assenta devagar. */
  dado: [0.16, 1, 0.3, 1],
} as const satisfies Record<string, readonly [number, number, number, number]>;

export const MOLA = {
  /** Painéis e seleção: sem quique perceptível. */
  firme: { type: 'spring', stiffness: 420, damping: 34, mass: 1 },
  /** Elementos maiores (sheet, painel expandido). */
  suave: { type: 'spring', stiffness: 260, damping: 30, mass: 1 },
} as const;

/** Passo de escalonamento e teto de itens escalonados (30ms × 6 = 180ms). */
export const ESCALONAR = { passo: 0.03, teto: 6 } as const;

/** Atraso de stagger do i-ésimo item, respeitando o teto. */
export const atrasoEscalonado = (i: number): number => Math.min(Math.max(0, i), ESCALONAR.teto) * ESCALONAR.passo;
