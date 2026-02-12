import { systemSettingsService } from '@/services/systemSettingsService';

/**
 * Global utility functions for currency formatting with automatic conversion
 * Use these instead of manual Intl.NumberFormat to ensure consistent USD->BRL conversion
 */

let cachedExchangeRate: number | null = null;
let cacheTimestamp: number = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

// Get exchange rate with caching
const getExchangeRate = async (): Promise<number> => {
  const now = Date.now();
  
  if (cachedExchangeRate && (now - cacheTimestamp) < CACHE_TTL) {
    return cachedExchangeRate;
  }
  
  try {
    const rate = await systemSettingsService.getExchangeRate();
    cachedExchangeRate = rate;
    cacheTimestamp = now;
    return rate;
  } catch (error) {
    console.error('Error getting exchange rate:', error);
    return 5.50; // Fallback
  }
};

// Clear cache (call when exchange rate is updated)
export const clearExchangeRateCache = (): void => {
  cachedExchangeRate = null;
  cacheTimestamp = 0;
};

// Convert USD to BRL and format as currency
export const formatCurrency = async (usdValue: number): Promise<string> => {
  try {
    const rate = await getExchangeRate();
    const brlValue = usdValue * rate;
    
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(brlValue);
  } catch (error) {
    console.error('Error formatting currency:', error);
    // Fallback formatting
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(usdValue * 5.50);
  }
};

// Synchronous version using cached rate (for performance in loops/renders)
export const formatCurrencySync = (usdValue: number, exchangeRate?: number): string => {
  const rate = exchangeRate || cachedExchangeRate || 5.50;
  const brlValue = usdValue * rate;
  
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(brlValue);
};

// Get current cached exchange rate
export const getCachedExchangeRate = (): number => {
  return cachedExchangeRate || 5.50;
};

// Pre-load exchange rate (call this on app startup or page load)
export const preloadExchangeRate = async (): Promise<number> => {
  return await getExchangeRate();
};

// Batch format multiple values efficiently
export const batchFormatCurrency = async (usdValues: number[]): Promise<string[]> => {
  const rate = await getExchangeRate();
  return usdValues.map(usd => formatCurrencySync(usd, rate));
};

// Convert and get both original and converted values
export const convertWithDetails = async (usdValue: number): Promise<{
  originalUsd: number;
  convertedBrl: number;
  exchangeRate: number;
  formattedBrl: string;
}> => {
  const rate = await getExchangeRate();
  const brlValue = usdValue * rate;
  
  return {
    originalUsd: usdValue,
    convertedBrl: brlValue,
    exchangeRate: rate,
    formattedBrl: formatCurrencySync(usdValue, rate)
  };
};

// Format BRL values that are already converted (from revenue_converted column)
// Use this when you have BRL values from the database that don't need conversion
export const formatBrlCurrency = (brlValue: number): string => {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(brlValue);
};

// Format cost/investment values (already in BRL, no conversion needed)
export const formatCostCurrency = (brlValue: number): string => {
  return formatBrlCurrency(brlValue);
};

// NEW: Format revenue values prioritizing converted column
export const formatRevenueCurrency = async (
  revenue: number,
  revenueConverted?: number
): Promise<string> => {
  // If we have a pre-calculated converted value, use it directly
  if (revenueConverted && revenueConverted > 0) {
    return formatBrlCurrency(revenueConverted);
  }
  
  // Otherwise, convert USD to BRL
  return await formatCurrency(revenue);
};

// NEW: Get revenue display value (prioritizes converted column)
export const getRevenueDisplayValue = async (
  revenue: number,
  revenueConverted?: number
): Promise<{
  value: number;
  formatted: string;
  isFromDatabase: boolean;
  exchangeRate?: number;
}> => {
  // If we have a pre-calculated converted value, use it
  if (revenueConverted && revenueConverted > 0) {
    return {
      value: revenueConverted,
      formatted: formatBrlCurrency(revenueConverted),
      isFromDatabase: true
    };
  }
  
  // Otherwise, convert on-the-fly
  const conversionDetails = await convertWithDetails(revenue);
  return {
    value: conversionDetails.convertedBrl,
    formatted: conversionDetails.formattedBrl,
    isFromDatabase: false,
    exchangeRate: conversionDetails.exchangeRate
  };
};

// NEW: Batch format revenue values
export const batchFormatRevenueCurrency = async (
  records: Array<{ revenue: number; revenue_converted?: number }>
): Promise<string[]> => {
  // Separate records that need conversion vs. those that don't
  const needConversion: number[] = [];
  const needConversionIndexes: number[] = [];
  const results: string[] = new Array(records.length);
  
  records.forEach((record, index) => {
    if (record.revenue_converted && record.revenue_converted > 0) {
      // Use pre-calculated value
      results[index] = formatBrlCurrency(record.revenue_converted);
    } else {
      // Needs conversion
      needConversion.push(record.revenue);
      needConversionIndexes.push(index);
    }
  });
  
  // Convert the ones that need it
  if (needConversion.length > 0) {
    const converted = await batchFormatCurrency(needConversion);
    needConversionIndexes.forEach((originalIndex, convertedIndex) => {
      results[originalIndex] = converted[convertedIndex];
    });
  }
  
  return results;
};