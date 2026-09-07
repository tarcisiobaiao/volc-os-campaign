/**
 * Vocabulário de retorno: três medidas, três unidades, três nomes.
 *
 * ---------------------------------------------------------------------------
 * O PROBLEMA QUE ESTE ARQUIVO CARREGAVA
 * ---------------------------------------------------------------------------
 *
 * `calculateROAS` NÃO devolve ROAS. Devolve o EXCEDENTE sobre o gasto:
 * `((receita / gasto) - 1) * 100`. Para receita 200 e gasto 100 ela responde
 * `100`, enquanto ROAS — a medida que a Meta e o Google Ads chamam de ROAS —
 * vale `2`. Três fórmulas diferentes convivem na base com alguma variação do
 * mesmo nome (excedente %, tradicional %, ROI %), e a coluna da tela diz
 * "ROAS" para todas.
 *
 * O risco concreto não é estético: `target_roas` do Google Ads é uma RAZÃO
 * enviada à plataforma. Um dia alguém "unifica" os nomes, o `100` do excedente
 * viaja para o campo de meta, e a conta passa a perseguir um alvo 50× maior do
 * que o pretendido.
 *
 * ---------------------------------------------------------------------------
 * A DECISÃO (adjudicação O02)
 * ---------------------------------------------------------------------------
 *
 * `calculateROAS` fica EXATAMENTE como estava e passa a ser explicitamente
 * legado. Dez arquivos a consomem, cinco deles painéis do Google alimentados
 * por `daily_campaign_metrics`, e as quatro faixas de cor logo abaixo estão
 * calibradas na escala do excedente (>=80 verde, >=40 amarelo, >=0 laranja).
 * Trocar a fórmula global recoloriria cinco páginas e reescreveria relatórios
 * históricos em silêncio — exatamente o que não se deve fazer para arrumar um
 * nome.
 *
 * O que muda é que passam a existir os nomes certos, com unidade no nome, e
 * ausência que continua ausência:
 *
 *   | função                  | fórmula              | unidade   | 200/100 |
 *   |-------------------------|----------------------|-----------|---------|
 *   | `roasRatio`             | receita / gasto      | razão     | `2`     |
 *   | `retornoExcedentePct`   | (receita/gasto - 1)  | %         | `100`   |
 *   | `roiLiquidoPct`         | lucro líq. / invest. | %         | depende |
 *
 * As três devolvem `null` quando a resposta não é conhecida. `calculateROAS`
 * devolve `0` para gasto ausente e um `100` simbólico para receita sem gasto —
 * dois valores inventados que o vocabulário novo não reproduz.
 *
 * NUNCA envie nenhuma destas a um campo de meta de plataforma. `target_roas`
 * do Google Ads é montado em `src/pages/trafego/NovaCampanhaPage.tsx` a partir
 * do que o operador digita, e deve continuar assim.
 */

/** Valor financeiro que pode não ter sido medido. `null` nunca é zero. */
export type ValorMedido = number | null | undefined;

const medido = (valor: ValorMedido): number | null =>
  typeof valor === 'number' && Number.isFinite(valor) ? valor : null;

/**
 * ROAS de verdade: receita dividida por gasto, adimensional.
 *
 * É a medida que a Meta e o Google Ads chamam de ROAS. Devolve `null` — e não
 * zero — quando o gasto não foi medido ou é zero: dividir por zero não produz
 * "retorno nulo", produz uma pergunta sem resposta, e um zero aqui viraria
 * "campanha ruim" num painel onde a verdade é "ainda não dá para dizer".
 */
export const roasRatio = (receita: ValorMedido, gasto: ValorMedido): number | null => {
  const r = medido(receita);
  const g = medido(gasto);
  if (r === null || g === null || g <= 0) return null;
  return r / g;
};

/**
 * Retorno EXCEDENTE sobre o gasto, em pontos percentuais.
 *
 * Mesma aritmética de `calculateROAS`, com o nome que descreve o que ela faz e
 * sem os dois valores inventados. 200/100 => `100` (cem por cento acima do
 * gasto), não `200`.
 */
export const retornoExcedentePct = (receita: ValorMedido, gasto: ValorMedido): number | null => {
  const razao = roasRatio(receita, gasto);
  return razao === null ? null : (razao - 1) * 100;
};

/** Lucro bruto: receita menos gasto de mídia. `null` se qualquer parcela falta. */
export const lucroBruto = (receita: ValorMedido, gasto: ValorMedido): number | null => {
  const r = medido(receita);
  const g = medido(gasto);
  return r === null || g === null ? null : r - g;
};

/**
 * ROI líquido em pontos percentuais, depois de deduções explícitas.
 *
 * `deducoes` são impostos, taxas e custos operacionais que a REGRA VERSIONADA
 * daquele projeto e daquele mês produziu. Não há alíquota padrão aqui de
 * propósito: as planilhas de referência trazem percentuais históricos, e
 * transformar um deles em constante universal aplicaria a taxa de um cliente à
 * conta de outro. Sem regra resolvida, `deducoes` é `null` e o ROI líquido é
 * `null` — o gasto e a receita continuam úteis mesmo assim.
 */
export const roiLiquidoPct = (
  receita: ValorMedido,
  gasto: ValorMedido,
  deducoes: ValorMedido,
): number | null => {
  const r = medido(receita);
  const g = medido(gasto);
  const d = medido(deducoes);
  if (r === null || g === null || d === null) return null;
  const investimento = g + d;
  if (investimento <= 0) return null;
  return ((r - investimento) / investimento) * 100;
};

/**
 * @deprecated Nome errado para o que calcula: devolve EXCEDENTE em %, não ROAS.
 *
 * Preservada byte a byte porque cinco painéis do Google e as faixas de cor
 * abaixo dependem desta escala. Para código novo use `roasRatio` (razão) ou
 * `retornoExcedentePct` (%), que distinguem ausência de zero.
 *
 * @param revenue - Total revenue generated
 * @param investment - Total investment/spend
 * @returns Excedente em % (ex.: 67 para uma razão de 1,67)
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