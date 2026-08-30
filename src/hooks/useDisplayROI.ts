import { useState, useEffect, useMemo } from 'react';
import { supabase } from '@/lib/supabase';
import type { DisplayROIRow, DisplayROISummary, SortField, SortDirection } from '@/types/displayROI';

interface UseDisplayROIParams {
  campaignId: string;
  startDate: string;
  endDate: string;
}

export function useDisplayROI({ campaignId, startDate, endDate }: UseDisplayROIParams) {
  const [data, setData] = useState<DisplayROIRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>('lucro_bruto');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  useEffect(() => {
    if (!campaignId || !startDate) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const effectiveEndDate = endDate || startDate;

        const { data: rows, error: queryError } = await supabase
          .from('vw_display_roi')
          .select('*')
          .eq('campaign_id', campaignId)
          .gte('date', startDate)
          .lte('date', effectiveEndDate)
          .order('lucro_bruto', { ascending: false });

        if (queryError) throw queryError;

        // Aggregate by canal (sum all dates for the same placement)
        const aggregated = new Map<string, DisplayROIRow>();

        (rows || []).forEach((row: DisplayROIRow) => {
          const key = row.canal;
          const existing = aggregated.get(key);

          if (existing) {
            existing.investido_brl += row.investido_brl || 0;
            existing.conversions += row.conversions || 0;
            existing.receita_brl += row.receita_brl || 0;
            existing.receita_usd += row.receita_usd || 0;
            existing.impressions += row.impressions || 0;
            existing.clicks += row.clicks || 0;
            existing.lucro_bruto += row.lucro_bruto || 0;
          } else {
            aggregated.set(key, {
              ...row,
              investido_brl: row.investido_brl || 0,
              conversions: row.conversions || 0,
              receita_brl: row.receita_brl || 0,
              receita_usd: row.receita_usd || 0,
              impressions: row.impressions || 0,
              clicks: row.clicks || 0,
              lucro_bruto: row.lucro_bruto || 0,
              roas_pct: 0,
              status_roi: '',
            });
          }
        });

        // Recalculate ROAS and status for aggregated rows
        const result = Array.from(aggregated.values()).map((row) => {
          const roas = row.investido_brl > 0
            ? ((row.receita_brl - row.investido_brl) / row.investido_brl) * 100
            : 0;

          let status: string;
          if (roas >= 20) status = 'LUCRATIVO';
          else if (roas >= 0) status = 'NEUTRO';
          else status = 'PREJUIZO';

          return { ...row, roas_pct: roas, status_roi: status };
        });

        setData(result);
      } catch (err) {
        console.error('Error fetching display ROI:', err);
        setError(err instanceof Error ? err.message : 'Erro ao buscar dados de ROI Display');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [campaignId, startDate, endDate]);

  const sortedData = useMemo(() => {
    return [...data].sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc'
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }

      const aNum = Number(aVal) || 0;
      const bNum = Number(bVal) || 0;
      return sortDirection === 'asc' ? aNum - bNum : bNum - aNum;
    });
  }, [data, sortField, sortDirection]);

  const summary: DisplayROISummary = useMemo(() => {
    const totalInvestido = data.reduce((sum, r) => sum + r.investido_brl, 0);
    const totalReceita = data.reduce((sum, r) => sum + r.receita_brl, 0);
    const lucroBruto = totalReceita - totalInvestido;
    const roasMedia = totalInvestido > 0
      ? ((totalReceita - totalInvestido) / totalInvestido) * 100
      : 0;
    const totalImpressoes = data.reduce((sum, r) => sum + r.impressions, 0);
    const totalClicks = data.reduce((sum, r) => sum + r.clicks, 0);

    return { totalInvestido, totalReceita, lucroBruto, roasMedia, totalImpressoes, totalClicks };
  }, [data]);

  const totals = useMemo(() => ({
    investido_brl: data.reduce((s, r) => s + r.investido_brl, 0),
    receita_brl: data.reduce((s, r) => s + r.receita_brl, 0),
    lucro_bruto: data.reduce((s, r) => s + r.lucro_bruto, 0),
    roas_pct: summary.roasMedia,
    impressions: data.reduce((s, r) => s + r.impressions, 0),
    clicks: data.reduce((s, r) => s + r.clicks, 0),
  }), [data, summary.roasMedia]);

  const handleSort = (field: SortField) => {
    if (field === sortField) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  return {
    data: sortedData,
    loading,
    error,
    summary,
    totals,
    sortField,
    sortDirection,
    handleSort,
    hasData: data.length > 0,
  };
}
