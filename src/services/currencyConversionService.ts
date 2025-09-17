import { systemSettingsService } from './systemSettingsService';
import { supabase } from '@/lib/supabase';

export class CurrencyConversionService {
  private exchangeRateCache: number | null = null;
  private lastCacheUpdate: number = 0;
  private readonly CACHE_TTL = 5 * 60 * 1000; // 5 minutes

  // Get current exchange rate (with caching)
  private async getExchangeRate(): Promise<number> {
    const now = Date.now();
    
    // Check if cache is still valid
    if (this.exchangeRateCache && (now - this.lastCacheUpdate) < this.CACHE_TTL) {
      return this.exchangeRateCache;
    }

    // Fetch from database
    const rate = await systemSettingsService.getExchangeRate();
    
    // Update cache
    this.exchangeRateCache = rate;
    this.lastCacheUpdate = now;
    
    return rate;
  }

  // Clear cache (call this when exchange rate is manually updated)
  public clearCache(): void {
    this.exchangeRateCache = null;
    this.lastCacheUpdate = 0;
  }

  // Convert USD to BRL
  async convertUsdToBrl(usdAmount: number): Promise<number> {
    const rate = await this.getExchangeRate();
    return usdAmount * rate;
  }

  // Convert BRL to USD
  async convertBrlToUsd(brlAmount: number): Promise<number> {
    const rate = await this.getExchangeRate();
    return brlAmount / rate;
  }

  // Auto-convert values based on system settings
  async autoConvertValue(value: number, fromCurrency: 'USD' | 'BRL', targetCurrency: 'USD' | 'BRL'): Promise<number> {
    // If same currency, no conversion needed
    if (fromCurrency === targetCurrency) {
      return value;
    }

    // Check if auto conversion is enabled
    const isAutoConvertEnabled = await systemSettingsService.isAutoConversionEnabled();
    if (!isAutoConvertEnabled) {
      return value; // Return original value if auto conversion is disabled
    }

    // Perform conversion
    if (fromCurrency === 'USD' && targetCurrency === 'BRL') {
      return await this.convertUsdToBrl(value);
    } else if (fromCurrency === 'BRL' && targetCurrency === 'USD') {
      return await this.convertBrlToUsd(value);
    }

    return value;
  }

  // Convert multiple values in batch
  async batchConvertUsdToBrl(usdAmounts: number[]): Promise<number[]> {
    const rate = await this.getExchangeRate();
    return usdAmounts.map(amount => amount * rate);
  }

  // Format currency with proper locale and symbol
  formatCurrency(amount: number, currency: 'USD' | 'BRL' = 'BRL', includeSymbol: boolean = true): string {
    if (currency === 'BRL') {
      return new Intl.NumberFormat('pt-BR', {
        style: includeSymbol ? 'currency' : 'decimal',
        currency: 'BRL',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      }).format(amount);
    } else {
      return new Intl.NumberFormat('en-US', {
        style: includeSymbol ? 'currency' : 'decimal',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      }).format(amount);
    }
  }

  // Get display value with automatic conversion
  async getDisplayValue(storedValue: number, storedCurrency: 'USD' | 'BRL', displayCurrency: 'USD' | 'BRL' = 'BRL'): Promise<{
    value: number;
    formatted: string;
    originalValue: number;
    originalCurrency: string;
    convertedValue: number;
    convertedCurrency: string;
    exchangeRate: number;
  }> {
    const exchangeRate = await this.getExchangeRate();
    const convertedValue = await this.autoConvertValue(storedValue, storedCurrency, displayCurrency);
    
    return {
      value: convertedValue,
      formatted: this.formatCurrency(convertedValue, displayCurrency),
      originalValue: storedValue,
      originalCurrency: storedCurrency,
      convertedValue: convertedValue,
      convertedCurrency: displayCurrency,
      exchangeRate: exchangeRate
    };
  }

  // Convert and format value in one call (most common use case)
  async convertAndFormat(value: number, fromCurrency: 'USD' | 'BRL', toCurrency: 'USD' | 'BRL' = 'BRL'): Promise<string> {
    const convertedValue = await this.autoConvertValue(value, fromCurrency, toCurrency);
    return this.formatCurrency(convertedValue, toCurrency);
  }

  // Bulk conversion for dashboard data
  async convertDashboardData(data: {
    totalSpend: number;
    totalRevenue: number;
    totalProfit: number;
  }): Promise<{
    totalSpend: { original: number, converted: number, formatted: string };
    totalRevenue: { original: number, converted: number, formatted: string };
    totalProfit: { original: number, converted: number, formatted: string };
    exchangeRate: number;
  }> {
    const exchangeRate = await this.getExchangeRate();
    
    // Assuming stored values are in USD, convert to BRL
    const convertedSpend = await this.autoConvertValue(data.totalSpend, 'USD', 'BRL');
    const convertedRevenue = await this.autoConvertValue(data.totalRevenue, 'USD', 'BRL');
    const convertedProfit = await this.autoConvertValue(data.totalProfit, 'USD', 'BRL');

    return {
      totalSpend: {
        original: data.totalSpend,
        converted: convertedSpend,
        formatted: this.formatCurrency(convertedSpend, 'BRL')
      },
      totalRevenue: {
        original: data.totalRevenue,
        converted: convertedRevenue,
        formatted: this.formatCurrency(convertedRevenue, 'BRL')
      },
      totalProfit: {
        original: data.totalProfit,
        converted: convertedProfit,
        formatted: this.formatCurrency(convertedProfit, 'BRL')
      },
      exchangeRate
    };
  }

  // Helper method to convert campaign data
  async convertCampaignFinancials(campaign: {
    investment: number;
    revenue: number;
  }): Promise<{
    investment: { original: number, converted: number, formatted: string };
    revenue: { original: number, converted: number, formatted: string };
    profit: { original: number, converted: number, formatted: string };
  }> {
    // Assuming stored values are in USD
    const convertedInvestment = await this.autoConvertValue(campaign.investment, 'USD', 'BRL');
    const convertedRevenue = await this.autoConvertValue(campaign.revenue, 'USD', 'BRL');
    const originalProfit = campaign.revenue - campaign.investment;
    const convertedProfit = convertedRevenue - convertedInvestment;

    return {
      investment: {
        original: campaign.investment,
        converted: convertedInvestment,
        formatted: this.formatCurrency(convertedInvestment, 'BRL')
      },
      revenue: {
        original: campaign.revenue,
        converted: convertedRevenue,
        formatted: this.formatCurrency(convertedRevenue, 'BRL')
      },
      profit: {
        original: originalProfit,
        converted: convertedProfit,
        formatted: this.formatCurrency(convertedProfit, 'BRL')
      }
    };
  }

  // Calculate ROAS and ROI with converted values
  calculateMetrics(investment: number, revenue: number): {
    roas: number;
    roi: number;
    roasFormatted: string;
    roiFormatted: string;
  } {
    const roas = investment > 0 ? (revenue / investment) * 100 : 0;
    const profit = revenue - investment;
    const roi = investment > 0 ? (profit / investment) * 100 : 0;

    return {
      roas: roas,
      roi: roi,
      roasFormatted: `${roas.toFixed(1)}%`,
      roiFormatted: `${roi.toFixed(1)}%`
    };
  }

  // Update all revenue_converted values in database when exchange rate changes
  async updateDatabaseConversions(): Promise<void> {
    try {
      const { error } = await supabase.rpc('update_all_revenue_conversions');
      if (error) throw error;
      
      console.log('✅ Successfully updated all revenue_converted values in database');
    } catch (error) {
      console.error('❌ Error updating database revenue conversions:', error);
      throw error;
    }
  }

  // Get revenue value prioritizing converted column
  async getRevenueValue(record: { 
    revenue: number; 
    revenue_converted?: number; 
  }): Promise<{ 
    displayValue: number; 
    isConverted: boolean; 
    originalUsd: number;
    convertedBrl: number;
  }> {
    const originalUsd = record.revenue;
    
    // If we have a pre-calculated converted value, use it
    if (record.revenue_converted && record.revenue_converted > 0) {
      return {
        displayValue: record.revenue_converted,
        isConverted: true,
        originalUsd,
        convertedBrl: record.revenue_converted
      };
    }
    
    // Otherwise, convert on-the-fly
    const convertedBrl = await this.convertUsdToBrl(originalUsd);
    return {
      displayValue: convertedBrl,
      isConverted: false,
      originalUsd,
      convertedBrl
    };
  }

  // Batch get revenue values with converted prioritization
  async batchGetRevenueValues(records: Array<{ 
    revenue: number; 
    revenue_converted?: number; 
  }>): Promise<Array<{ 
    displayValue: number; 
    isConverted: boolean; 
    originalUsd: number;
    convertedBrl: number;
  }>> {
    const exchangeRate = await this.getExchangeRate();
    
    return records.map(record => {
      const originalUsd = record.revenue;
      
      // If we have a pre-calculated converted value, use it
      if (record.revenue_converted && record.revenue_converted > 0) {
        return {
          displayValue: record.revenue_converted,
          isConverted: true,
          originalUsd,
          convertedBrl: record.revenue_converted
        };
      }
      
      // Otherwise, convert using cached rate
      const convertedBrl = originalUsd * exchangeRate;
      return {
        displayValue: convertedBrl,
        isConverted: false,
        originalUsd,
        convertedBrl
      };
    });
  }
}

// Singleton instance
export const currencyConversionService = new CurrencyConversionService();

// React hook for currency conversion
import { useState, useEffect } from 'react';

export const useCurrencyConverter = () => {
  const [exchangeRate, setExchangeRate] = useState<number>(5.50);
  const [loading, setLoading] = useState(true);

  const loadExchangeRate = async () => {
    try {
      setLoading(true);
      const rate = await systemSettingsService.getExchangeRate();
      setExchangeRate(rate);
    } catch (error) {
      console.error('Error loading exchange rate:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadExchangeRate();
  }, []);

  const convertUsdToBrl = (usd: number) => usd * exchangeRate;
  const convertBrlToUsd = (brl: number) => brl / exchangeRate;
  
  const formatBrl = (amount: number) => currencyConversionService.formatCurrency(amount, 'BRL');
  const formatUsd = (amount: number) => currencyConversionService.formatCurrency(amount, 'USD');

  return {
    exchangeRate,
    loading,
    convertUsdToBrl,
    convertBrlToUsd,
    formatBrl,
    formatUsd,
    reload: loadExchangeRate
  };
};