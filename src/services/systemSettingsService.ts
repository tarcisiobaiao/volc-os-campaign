import { secureApi } from '@/lib/secureApi';

export interface SystemSetting {
  id: number;
  key: string;
  value: string;
  description?: string;
  data_type: 'string' | 'number' | 'boolean' | 'json';
  category: string;
  is_editable: boolean;
  created_at: string;
  updated_at: string;
}

export interface CurrencyConfig {
  exchangeRate: number;
  displayCurrency: string;
  autoConvert: boolean;
  lastUpdate: string;
}

class SystemSettingsService {
  private cache: Map<string, any> = new Map();
  private cacheExpiry: Map<string, number> = new Map();
  private readonly CACHE_TTL = 5 * 60 * 1000; // 5 minutes

  // Generic method to get any setting
  async getSetting(key: string): Promise<string | null> {
    try {
      // Check cache first
      const cacheKey = `setting_${key}`;
      const cached = this.cache.get(cacheKey);
      const expiry = this.cacheExpiry.get(cacheKey);

      if (cached && expiry && Date.now() < expiry) {
        return cached;
      }

      const data = await secureApi.query<{ value: string }>({
        table: 'system_settings',
        select: 'value',
        filters: [{ field: 'key', operator: 'eq', value: key }]
      });

      if (!data || data.length === 0) {
        console.error(`Setting ${key} not found`);
        return null;
      }

      // Cache the result
      this.cache.set(cacheKey, data[0].value);
      this.cacheExpiry.set(cacheKey, Date.now() + this.CACHE_TTL);

      return data[0].value;
    } catch (error) {
      console.error(`Error in getSetting for ${key}:`, error);
      return null;
    }
  }

  // Generic method to set any setting
  async setSetting(key: string, value: string): Promise<boolean> {
    try {
      await secureApi.update({
        table: 'system_settings',
        data: {
          value: value,
          updated_at: new Date().toISOString()
        },
        filters: [{ field: 'key', operator: 'eq', value: key }]
      });

      // Clear cache
      this.cache.delete(`setting_${key}`);
      this.cacheExpiry.delete(`setting_${key}`);

      return true;
    } catch (error) {
      console.error(`Error in setSetting for ${key}:`, error);
      return false;
    }
  }

  // Specific methods for currency settings
  async getExchangeRate(): Promise<number> {
    const rate = await this.getSetting('dollar_exchange_rate');
    return rate ? parseFloat(rate) : 5.50; // Default fallback
  }

  async setExchangeRate(rate: number): Promise<boolean> {
    const success = await this.setSetting('dollar_exchange_rate', rate.toString());
    if (success) {
      // Also update the last manual update timestamp
      await this.setSetting('last_currency_update', new Date().toISOString());
    }
    return success;
  }

  async getCurrencyConfig(): Promise<CurrencyConfig> {
    try {
      const [exchangeRate, displayCurrency, autoConvert, lastUpdate] = await Promise.all([
        this.getSetting('dollar_exchange_rate'),
        this.getSetting('currency_display'),
        this.getSetting('auto_convert_values'),
        this.getSetting('last_currency_update'),
      ]);

      return {
        exchangeRate: exchangeRate ? parseFloat(exchangeRate) : 5.50,
        displayCurrency: displayCurrency || 'BRL',
        autoConvert: autoConvert === 'true',
        lastUpdate: lastUpdate || ''
      };
    } catch (error) {
      console.error('Error getting currency config:', error);
      return {
        exchangeRate: 5.50,
        displayCurrency: 'BRL',
        autoConvert: true,
        lastUpdate: ''
      };
    }
  }

  async updateCurrencyConfig(config: Partial<CurrencyConfig>): Promise<boolean> {
    try {
      const promises: Promise<boolean>[] = [];

      if (config.exchangeRate !== undefined) {
        promises.push(this.setSetting('dollar_exchange_rate', config.exchangeRate.toString()));
      }
      if (config.displayCurrency !== undefined) {
        promises.push(this.setSetting('currency_display', config.displayCurrency));
      }
      if (config.autoConvert !== undefined) {
        promises.push(this.setSetting('auto_convert_values', config.autoConvert.toString()));
      }

      const results = await Promise.all(promises);
      return results.every(result => result === true);
    } catch (error) {
      console.error('Error updating currency config:', error);
      return false;
    }
  }

  // Utility method to convert USD to BRL using current exchange rate
  async convertUsdToBrl(usdAmount: number): Promise<number> {
    const rate = await this.getExchangeRate();
    return usdAmount * rate;
  }

  // Utility method to convert BRL to USD using current exchange rate
  async convertBrlToUsd(brlAmount: number): Promise<number> {
    const rate = await this.getExchangeRate();
    return brlAmount / rate;
  }

  // Format currency with proper locale
  formatCurrency(amount: number, currency: string = 'BRL'): string {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: currency
    }).format(amount);
  }

  // Clear all cache
  clearCache(): void {
    this.cache.clear();
    this.cacheExpiry.clear();
  }

  // Check if auto conversion is enabled
  async isAutoConversionEnabled(): Promise<boolean> {
    const autoConvert = await this.getSetting('auto_convert_values');
    return autoConvert === 'true';
  }

  // Get all settings by category
  async getSettingsByCategory(category: string): Promise<SystemSetting[]> {
    try {
      const data = await secureApi.query<SystemSetting>({
        table: 'system_settings',
        select: '*',
        filters: [{ field: 'category', operator: 'eq', value: category }]
      });

      return data || [];
    } catch (error) {
      console.error(`Error in getSettingsByCategory for ${category}:`, error);
      return [];
    }
  }

  // Batch update multiple settings
  async updateMultipleSettings(updates: Array<{ key: string; value: string }>): Promise<boolean> {
    try {
      const updatePromises = updates.map(({ key, value }) =>
        secureApi.update({
          table: 'system_settings',
          data: {
            value: value,
            updated_at: new Date().toISOString()
          },
          filters: [{ field: 'key', operator: 'eq', value: key }]
        })
      );

      await Promise.all(updatePromises);

      // Clear cache for updated keys
      updates.forEach(({ key }) => {
        this.cache.delete(`setting_${key}`);
        this.cacheExpiry.delete(`setting_${key}`);
      });

      return true;
    } catch (error) {
      console.error('Error in updateMultipleSettings:', error);
      return false;
    }
  }

  // Update GAM last sync timestamp
  async updateGamLastUpdate(): Promise<boolean> {
    try {
      const now = new Date();
      // Format in São Paulo timezone in dd/mm/yyyy, hh:mm:ss format
      const timestamp = now.toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZone: 'America/Sao_Paulo'
      });

      console.log('📊 Updating GAM timestamp:', timestamp);
      
      const success = await this.setSetting('gam_last_update', timestamp);
      if (success) {
        // Clear cache to force refresh
        this.clearCache();
      }
      return success;
    } catch (error) {
      console.error('Error updating GAM timestamp:', error);
      return false;
    }
  }

  // Update Google Ads last sync timestamp
  async updateGoogleAdsLastUpdate(): Promise<boolean> {
    try {
      const now = new Date();
      // Format in São Paulo timezone in dd/mm/yyyy, hh:mm:ss format
      const timestamp = now.toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZone: 'America/Sao_Paulo'
      });

      console.log('📊 Updating Google Ads timestamp:', timestamp);
      
      const success = await this.setSetting('google_ads_last_update', timestamp);
      if (success) {
        // Clear cache to force refresh
        this.clearCache();
      }
      return success;
    } catch (error) {
      console.error('Error updating Google Ads timestamp:', error);
      return false;
    }
  }

  // Get system timestamps (GAM and Google Ads)
  async getSystemTimestamps(): Promise<{
    gamLastUpdate: string | null;
    googleAdsLastUpdate: string | null;
    mostRecent: string | null;
  }> {
    try {
      const [gamUpdate, adsUpdate] = await Promise.all([
        this.getSetting('gam_last_update'),
        this.getSetting('google_ads_last_update')
      ]);

      // Determine most recent
      let mostRecent: string | null = null;
      if (gamUpdate && adsUpdate) {
        // Compare timestamps
        const gamDate = this.parseTimestamp(gamUpdate);
        const adsDate = this.parseTimestamp(adsUpdate);
        mostRecent = (gamDate && adsDate && gamDate > adsDate) ? gamUpdate : adsUpdate;
      } else if (gamUpdate) {
        mostRecent = gamUpdate;
      } else if (adsUpdate) {
        mostRecent = adsUpdate;
      }

      return {
        gamLastUpdate: gamUpdate,
        googleAdsLastUpdate: adsUpdate,
        mostRecent
      };
    } catch (error) {
      console.error('Error fetching system timestamps:', error);
      return {
        gamLastUpdate: null,
        googleAdsLastUpdate: null,
        mostRecent: null
      };
    }
  }

  // Helper to parse timestamp from different formats
  private parseTimestamp(timestamp: string): Date | null {
    try {
      if (timestamp.includes('/') && timestamp.includes(',')) {
        // Brazilian format: "10/09/2025, 10:29:04"
        const [datePart, timePart] = timestamp.split(', ');
        const [day, month, year] = datePart.split('/');
        const fullDateString = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${timePart}`;
        return new Date(fullDateString);
      } else {
        return new Date(timestamp);
      }
    } catch {
      return null;
    }
  }
}

// Singleton instance
export const systemSettingsService = new SystemSettingsService();

// React hook for using system settings
import { useState, useEffect } from 'react';

export const useSystemSettings = (keys: string[]) => {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = async () => {
    try {
      setLoading(true);
      setError(null);

      const settingsPromises = keys.map(async (key) => {
        const value = await systemSettingsService.getSetting(key);
        return { key, value: value || '' };
      });

      const results = await Promise.all(settingsPromises);
      const settingsMap = results.reduce((acc, { key, value }) => {
        acc[key] = value;
        return acc;
      }, {} as Record<string, string>);

      setSettings(settingsMap);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (keys.length > 0) {
      loadSettings();
    }
  }, [keys.join(',')]);

  const updateSetting = async (key: string, value: string) => {
    const success = await systemSettingsService.setSetting(key, value);
    if (success) {
      setSettings(prev => ({ ...prev, [key]: value }));
    }
    return success;
  };

  return {
    settings,
    loading,
    error,
    updateSetting,
    reload: loadSettings
  };
};

// React hook specifically for currency settings
export const useCurrencySettings = () => {
  const [currencyConfig, setCurrencyConfig] = useState<CurrencyConfig>({
    exchangeRate: 5.50,
    displayCurrency: 'BRL',
    autoConvert: true,
    lastUpdate: ''
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCurrencyConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      const config = await systemSettingsService.getCurrencyConfig();
      setCurrencyConfig(config);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCurrencyConfig();
  }, []);

  const updateCurrencyConfig = async (updates: Partial<CurrencyConfig>) => {
    const success = await systemSettingsService.updateCurrencyConfig(updates);
    if (success) {
      setCurrencyConfig(prev => ({ ...prev, ...updates }));
    }
    return success;
  };

  return {
    currencyConfig,
    loading,
    error,
    updateCurrencyConfig,
    reload: loadCurrencyConfig
  };
};