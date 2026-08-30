import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';

export interface PlacementSuggestion {
  canal: string;
  categoria: 'NEGATIVAR' | 'OBSERVAR';
  roas_1d: number | null;
  roas_3d: number | null;
  roas_7d: number | null;
  roas_14d: number | null;
  var_roas_pct: number | null;
  motivo: string;
}

export function usePlacementNegation(campaignId: string) {
  const [negativar, setNegativar] = useState<PlacementSuggestion[]>([]);
  const [observar, setObservar] = useState<PlacementSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNegativar([]);
    setObservar([]);
    if (!campaignId) return;

    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const { data, error: rpcError } = await supabase.rpc(
          'get_placement_negation_suggestions',
          { p_campaign_id: campaignId }
        );

        if (cancelled) return;
        if (rpcError) throw rpcError;

        const rows = (data ?? []) as PlacementSuggestion[];
        setNegativar(rows.filter(r => r.categoria === 'NEGATIVAR'));
        setObservar(rows.filter(r => r.categoria === 'OBSERVAR'));
      } catch (err) {
        if (!cancelled) {
          console.error('[usePlacementNegation]', err);
          setError(err instanceof Error ? err.message : 'Erro ao buscar sugestões de negativação');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchData();
    return () => { cancelled = true; };
  }, [campaignId]);

  return { negativar, observar, loading, error };
}
