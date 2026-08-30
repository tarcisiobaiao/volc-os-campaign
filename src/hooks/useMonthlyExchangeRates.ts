import { useState, useEffect, useCallback } from 'react';
import { supabase } from '@/lib/supabase';

export interface MonthlyRate {
  id: number;
  year_month: string;
  rate: number;
  source: string;
  recalculated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecalculateResult {
  month: string;
  rate: number;
  affected: {
    daily_campaign_metrics: number;
    daily_project_metrics: number;
    gam_metrics: number;
    adsense_metrics: number;
  };
  total_rows: number;
}

export function useMonthlyExchangeRates() {
  const [rates, setRates] = useState<MonthlyRate[]>([]);
  const [loading, setLoading] = useState(true);
  const [recalculating, setRecalculating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchRates = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const { data, error: fetchError } = await supabase
        .from('monthly_exchange_rates')
        .select('*')
        .order('year_month', { ascending: false })
        .limit(12);

      if (fetchError) throw fetchError;
      setRates(data || []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro ao carregar taxas mensais';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRates();
  }, [fetchRates]);

  const recalculateMonth = useCallback(async (yearMonth: string, rate: number): Promise<RecalculateResult> => {
    try {
      setRecalculating(yearMonth);
      setError(null);

      console.log('[MonthlyRates] Calling rpc_recalculate_month:', { yearMonth, rate });

      const { data, error: rpcError } = await supabase.rpc('rpc_recalculate_month', {
        p_year_month: yearMonth,
        p_rate: rate,
      });

      console.log('[MonthlyRates] RPC response:', { data, error: rpcError });

      if (rpcError) throw rpcError;

      // Refresh list after recalculation (don't let this fail the whole operation)
      try { await fetchRates(); } catch (e) { console.warn('[MonthlyRates] fetchRates after recalc failed:', e); }

      return (data ?? { month: yearMonth, rate, affected: {}, total_rows: 0 }) as RecalculateResult;
    } catch (err) {
      console.error('[MonthlyRates] RPC error:', err);
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      throw err;
    } finally {
      setRecalculating(null);
    }
  }, [fetchRates]);

  const updateRate = useCallback(async (yearMonth: string, newRate: number) => {
    try {
      setError(null);

      const { error: upsertError } = await supabase
        .from('monthly_exchange_rates')
        .upsert(
          { year_month: yearMonth, rate: newRate, source: 'manual', updated_at: new Date().toISOString() },
          { onConflict: 'year_month' }
        );

      if (upsertError) throw upsertError;
      await fetchRates();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro ao salvar taxa';
      setError(msg);
      throw err;
    }
  }, [fetchRates]);

  return {
    rates,
    loading,
    recalculating,
    error,
    fetchRates,
    recalculateMonth,
    updateRate,
  };
}
