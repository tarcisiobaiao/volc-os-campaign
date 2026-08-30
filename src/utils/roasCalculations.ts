/**
 * Utility functions for ROAS calculations
 *
 * ROAS (Return on Ad Spend) is calculated as excess return over investment
 * Example: If investment = 100 and revenue = 167, ROAS = 67% (not 167%)
 */

/**
 * Calculate ROAS as excess percentage over investment
 * @param revenue - Total revenue generated
 * @param investment - Total investment/spend
 * @returns ROAS as excess percentage (e.g., 67% for 167% traditional ROAS)
 */
export const calculateROAS = (revenue: number, investment: number): number => {
  // Caso especial: Se há faturamento mas sem gasto, retorna +100% simbólico
  if (investment <= 0 && revenue > 0) return 100;

  // Caso normal: Sem faturamento ou sem dados válidos
  if (investment <= 0) return 0;

  return ((revenue / investment) - 1) * 100;
};

/**
 * Calculate traditional ROAS (revenue/investment * 100)
 * Used internally for compatibility with existing logic
 * @param revenue - Total revenue generated
 * @param investment - Total investment/spend
 * @returns Traditional ROAS percentage
 */
export const calculateTraditionalROAS = (revenue: number, investment: number): number => {
  if (investment <= 0) return 0;
  return (revenue / investment) * 100;
};

/**
 * Get ROAS color classification based on excess percentage
 * @param roasExcess - ROAS as excess percentage
 * @returns Color category for UI styling
 */
export const getROASColorCategory = (roasExcess: number): "green" | "yellow" | "orange" | "red" => {
  if (roasExcess >= 80) return "green";    // ≥80% excess (≥180% traditional)
  if (roasExcess >= 40) return "yellow";   // 40-79% excess (140-179% traditional)
  if (roasExcess >= 0) return "orange";    // 0-39% excess (100-139% traditional)
  return "red";                            // <0% excess (negative)
};

/**
 * As quatro faixas de ROAS, no vocabulário semântico do produto.
 *
 * ---------------------------------------------------------------------------
 * POR QUE ISTO DEIXOU DE SER PALETA CRUA
 * ---------------------------------------------------------------------------
 *
 * Estas duas tabelas são a fonte de cor de ROAS de CINCO páginas
 * (`/`, `/reports`, `/dashboard/project/:id`, `/settings/projects`,
 * `/settings/campaigns`). Elas devolviam `text-orange-600 bg-orange-50`,
 * `bg-green-500`, `text-yellow-600` — paleta crua do Tailwind. Três problemas,
 * todos multiplicados por cinco páginas:
 *
 *   1. CONTRASTE. Medido no navegador: `text-orange-600` sobre `bg-orange-50`
 *      dá 3,35:1, abaixo do piso de 4,5:1 da WCAG 1.4.3.
 *   2. TEMA ESCURO. A paleta crua não tem variante escura, então o cartão de
 *      ROI ficava com fundo creme dentro do tema escuro, e a tinta clara do
 *      tema por cima: 2,25:1. Um cartão inteiro que não virava.
 *   3. VOCABULÁRIO. `design.md`: "Semantic vocabulary is closed: primary,
 *      verified, success, warning, destructive, info". Verde, amarelo, laranja
 *      e vermelho crus ensinam quatro significados que o resto do produto não
 *      reconhece.
 *
 * As QUATRO faixas continuam existindo — `getROASColorCategory` não mudou, e é
 * ela que alimenta os filtros. O que mudou é que amarelo e laranja passaram a
 * dividir `warning`: as duas sempre significaram a mesma coisa para o operador
 * ("está abaixo do que devia"), e o número exato, que está sempre na tela ao
 * lado, é quem carrega a gradação fina. Cor é o sinal grosso; o número é o
 * fino. `design.md`: "Color is never the sole carrier of meaning."
 */
const ROAS_ESTILO: Record<ReturnType<typeof getROASColorCategory>, string> = {
  green:  "text-success bg-success/10 border-success/25",
  yellow: "text-warning bg-warning/10 border-warning/25",
  // Tinte igual ao das outras faixas: sobre `/[0.16]` o texto secundário do
  // cartão media 3,99:1. A distinção entre "amarelo" e "laranja" fica na borda
  // e, sobretudo, no número — que está sempre na tela ao lado.
  orange: "text-warning bg-warning/10 border-warning/40",
  red:    "text-destructive bg-destructive/10 border-destructive/25",
};

/** Preenchimento sólido, para a barra/selo. O par com `-foreground` já passa. */
const ROAS_PREENCHIMENTO: Record<ReturnType<typeof getROASColorCategory>, string> = {
  green:  "bg-success",
  yellow: "bg-warning",
  orange: "bg-warning",
  red:    "bg-destructive",
};

/**
 * Get detailed ROAS color styling for components
 * @param roasExcess - ROAS as excess percentage
 * @returns CSS classes for styling
 */
export const getROASColorStyles = (roasExcess: number): string => {
  return ROAS_ESTILO[getROASColorCategory(roasExcess)];
};

/**
 * Get ROAS badge color for backgrounds
 * @param roasExcess - ROAS as excess percentage
 * @returns Background color class
 */
export const getROASBadgeColor = (roasExcess: number): string => {
  return ROAS_PREENCHIMENTO[getROASColorCategory(roasExcess)];
};