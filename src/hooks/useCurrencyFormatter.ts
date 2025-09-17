import { useState, useEffect, useCallback } from 'react';
import { currencyConversionService } from '@/services/currencyConversionService';

export const useCurrencyFormatter = () => {
  const [loading, setLoading] = useState(false);

  // Format currency with automatic conversion from USD to BRL
  // Now supports both plain USD values and records with revenue_converted
  const formatCurrency = useCallback(async (
    input: number | { revenue: number; revenue_converted?: number }
  ): Promise<string> => {
    try {
      setLoading(true);
      
      if (typeof input === 'number') {
        // Legacy usage: plain USD amount
        return await currencyConversionService.convertAndFormat(input, 'USD', 'BRL');
      } else {
        // New usage: revenue record with optional converted value
        const revenueData = await currencyConversionService.getRevenueValue(input);
        return currencyConversionService.formatCurrency(revenueData.displayValue, 'BRL');
      }
    } catch (error) {
      console.error('Error formatting currency:', error);
      // Fallback to standard BRL formatting with default rate
      const amount = typeof input === 'number' ? input : input.revenue;
      return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
      }).format(amount * 5.50);
    } finally {
      setLoading(false);
    }
  }, []);

  // Synchronous version for when you already have the conversion rate
  const formatCurrencySync = useCallback((amount: number, currency: 'USD' | 'BRL' = 'BRL'): string => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: currency
    }).format(amount);
  }, []);

  // Batch format multiple values - supports both number arrays and revenue records
  const batchFormatCurrency = useCallback(async (
    values: number[] | Array<{ revenue: number; revenue_converted?: number }>
  ): Promise<string[]> => {
    try {
      setLoading(true);
      
      if (values.length === 0) return [];
      
      // Check if we're dealing with numbers or revenue records
      if (typeof values[0] === 'number') {
        // Legacy: array of USD numbers
        const formatted = await Promise.all(
          (values as number[]).map(value => currencyConversionService.convertAndFormat(value, 'USD', 'BRL'))
        );
        return formatted;
      } else {
        // New: array of revenue records
        const revenueData = await currencyConversionService.batchGetRevenueValues(
          values as Array<{ revenue: number; revenue_converted?: number }>
        );
        return revenueData.map(data => 
          currencyConversionService.formatCurrency(data.displayValue, 'BRL')
        );
      }
    } catch (error) {
      console.error('Error in batch format:', error);
      // Fallback formatting
      return values.map(value => {
        const amount = typeof value === 'number' ? value : value.revenue;
        return formatCurrencySync(amount * 5.50, 'BRL');
      });
    } finally {
      setLoading(false);
    }
  }, [formatCurrencySync]);

  // Format with detailed conversion info
  const formatWithConversion = useCallback(async (usdAmount: number): Promise<{
    formatted: string;
    originalUsd: number;
    convertedBrl: number;
    exchangeRate: number;
  }> => {
    try {
      const displayData = await currencyConversionService.getDisplayValue(usdAmount, 'USD', 'BRL');
      return {
        formatted: displayData.formatted,
        originalUsd: displayData.originalValue,
        convertedBrl: displayData.convertedValue,
        exchangeRate: displayData.exchangeRate
      };
    } catch (error) {
      console.error('Error in formatWithConversion:', error);
      const fallbackRate = 5.50;
      const convertedBrl = usdAmount * fallbackRate;
      return {
        formatted: formatCurrencySync(convertedBrl, 'BRL'),
        originalUsd: usdAmount,
        convertedBrl: convertedBrl,
        exchangeRate: fallbackRate
      };
    }
  }, [formatCurrencySync]);

  return {
    formatCurrency,
    formatCurrencySync,
    batchFormatCurrency,
    formatWithConversion,
    loading
  };
};

// Hook specifically for dashboard values
export const useDashboardCurrency = () => {
  const { formatCurrency, formatWithConversion, loading } = useCurrencyFormatter();
  const [exchangeRate, setExchangeRate] = useState<number>(5.50);

  // Load current exchange rate
  useEffect(() => {
    const loadRate = async () => {
      try {
        const rate = await currencyConversionService['getExchangeRate']?.() || 5.50;
        setExchangeRate(rate);
      } catch (error) {
        console.error('Error loading exchange rate:', error);
      }
    };
    loadRate();
  }, []);

  // Format dashboard financial values
  const formatDashboardValue = useCallback(async (value: number) => {
    const result = await formatWithConversion(value);
    return {
      ...result,
      displayText: result.formatted,
      tooltip: `USD $${result.originalUsd.toFixed(2)} × R$${result.exchangeRate.toFixed(2)} = ${result.formatted}`
    };
  }, [formatWithConversion]);

  // Format multiple dashboard values
  const formatDashboardValues = useCallback(async (values: {
    totalSpend: number;
    totalRevenue: number;
    totalProfit: number;
  }) => {
    try {
      const [spend, revenue, profit] = await Promise.all([
        formatDashboardValue(values.totalSpend),
        formatDashboardValue(values.totalRevenue),
        formatDashboardValue(values.totalProfit)
      ]);

      return { spend, revenue, profit };
    } catch (error) {
      console.error('Error formatting dashboard values:', error);
      // Fallback formatting
      return {
        spend: {
          formatted: `R$ ${(values.totalSpend * exchangeRate).toFixed(2)}`,
          displayText: `R$ ${(values.totalSpend * exchangeRate).toFixed(2)}`,
          originalUsd: values.totalSpend,
          convertedBrl: values.totalSpend * exchangeRate,
          exchangeRate: exchangeRate,
          tooltip: `USD $${values.totalSpend.toFixed(2)} × R$${exchangeRate.toFixed(2)}`
        },
        revenue: {
          formatted: `R$ ${(values.totalRevenue * exchangeRate).toFixed(2)}`,
          displayText: `R$ ${(values.totalRevenue * exchangeRate).toFixed(2)}`,
          originalUsd: values.totalRevenue,
          convertedBrl: values.totalRevenue * exchangeRate,
          exchangeRate: exchangeRate,
          tooltip: `USD $${values.totalRevenue.toFixed(2)} × R$${exchangeRate.toFixed(2)}`
        },
        profit: {
          formatted: `R$ ${(values.totalProfit * exchangeRate).toFixed(2)}`,
          displayText: `R$ ${(values.totalProfit * exchangeRate).toFixed(2)}`,
          originalUsd: values.totalProfit,
          convertedBrl: values.totalProfit * exchangeRate,
          exchangeRate: exchangeRate,
          tooltip: `USD $${values.totalProfit.toFixed(2)} × R$${exchangeRate.toFixed(2)}`
        }
      };
    }
  }, [formatDashboardValue, exchangeRate]);

  return {
    formatCurrency,
    formatDashboardValue,
    formatDashboardValues,
    exchangeRate,
    loading
  };
};

// New hook specifically for revenue data with converted values
export const useRevenueFormatter = () => {
  const [loading, setLoading] = useState(false);

  // Format revenue value prioritizing converted column
  const formatRevenue = useCallback(async (
    revenue: number, 
    revenueConverted?: number
  ): Promise<{
    formatted: string;
    displayValue: number;
    isFromDatabase: boolean;
    originalUsd: number;
  }> => {
    try {
      setLoading(true);
      const revenueData = await currencyConversionService.getRevenueValue({
        revenue,
        revenue_converted: revenueConverted
      });
      
      return {
        formatted: currencyConversionService.formatCurrency(revenueData.displayValue, 'BRL'),
        displayValue: revenueData.displayValue,
        isFromDatabase: revenueData.isConverted,
        originalUsd: revenueData.originalUsd
      };
    } catch (error) {
      console.error('Error formatting revenue:', error);
      const fallbackValue = revenueConverted || revenue * 5.50;
      return {
        formatted: new Intl.NumberFormat('pt-BR', {
          style: 'currency',
          currency: 'BRL'
        }).format(fallbackValue),
        displayValue: fallbackValue,
        isFromDatabase: !!revenueConverted,
        originalUsd: revenue
      };
    } finally {
      setLoading(false);
    }
  }, []);

  // Batch format revenue records
  const batchFormatRevenue = useCallback(async (
    records: Array<{ revenue: number; revenue_converted?: number }>
  ): Promise<Array<{
    formatted: string;
    displayValue: number;
    isFromDatabase: boolean;
    originalUsd: number;
  }>> => {
    try {
      setLoading(true);
      const revenueData = await currencyConversionService.batchGetRevenueValues(records);
      
      return revenueData.map((data, index) => ({
        formatted: currencyConversionService.formatCurrency(data.displayValue, 'BRL'),
        displayValue: data.displayValue,
        isFromDatabase: data.isConverted,
        originalUsd: data.originalUsd
      }));
    } catch (error) {
      console.error('Error in batch format revenue:', error);
      return records.map(record => {
        const fallbackValue = record.revenue_converted || record.revenue * 5.50;
        return {
          formatted: new Intl.NumberFormat('pt-BR', {
            style: 'currency',
            currency: 'BRL'
          }).format(fallbackValue),
          displayValue: fallbackValue,
          isFromDatabase: !!record.revenue_converted,
          originalUsd: record.revenue
        };
      });
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    formatRevenue,
    batchFormatRevenue,
    loading
  };
};