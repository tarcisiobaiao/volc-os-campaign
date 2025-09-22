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
 * Get detailed ROAS color styling for components
 * @param roasExcess - ROAS as excess percentage
 * @returns CSS classes for styling
 */
export const getROASColorStyles = (roasExcess: number): string => {
  if (roasExcess >= 150) return "text-green-800 bg-green-100 border-green-200";   // ≥150% excess (excellent)
  if (roasExcess >= 80) return "text-green-600 bg-green-50 border-green-100";     // ≥80% excess (good/green)
  if (roasExcess >= 40) return "text-yellow-600 bg-yellow-50 border-yellow-200";  // 40-79% excess (yellow)
  if (roasExcess >= 0) return "text-orange-600 bg-orange-50 border-orange-200";   // 0-39% excess (orange)
  return "text-red-600 bg-red-50 border-red-200";                                // <0% excess (red/negative)
};

/**
 * Get ROAS badge color for backgrounds
 * @param roasExcess - ROAS as excess percentage
 * @returns Background color class
 */
export const getROASBadgeColor = (roasExcess: number): string => {
  if (roasExcess >= 150) return "bg-green-700";   // ≥150% excess (excellent)
  if (roasExcess >= 80) return "bg-green-500";    // ≥80% excess (good/green)
  if (roasExcess >= 40) return "bg-yellow-500";   // 40-79% excess (yellow)
  if (roasExcess >= 0) return "bg-orange-500";    // 0-39% excess (orange)
  return "bg-red-500";                            // <0% excess (red/negative)
};