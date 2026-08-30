// src/hooks/useCampaignComparisons.ts
import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabase';
import { Campaign } from '@/services/supabaseDataService';
import { calculateROAS } from '@/utils/roasCalculations';

export interface CampaignComparison {
  prevInvestment: number;
  prevRevenue: number;
  prevRoas: number;
  comparisonLabel: string;
}

function addDays(dateStr: string, n: number): string {
  const d = new Date(dateStr + 'T12:00:00');
  d.setDate(d.getDate() + n);
  return d.toISOString().split('T')[0];
}

function getPreviousPeriod(
  period: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range',
  date: string,
  endDate?: string
): { prevStart: string; prevEnd: string; label: string } | null {
  if (!date) return null;

  switch (period) {
    case 'today':
      return null; // partial day — comparison would be misleading
    case 'yesterday':
      return { prevStart: addDays(date, -1), prevEnd: addDays(date, -1), label: 'vs dia anterior' };
    case 'custom':
      return { prevStart: addDays(date, -1), prevEnd: addDays(date, -1), label: 'vs dia anterior' };
    case '7d':
      return { prevStart: addDays(date, -13), prevEnd: addDays(date, -7), label: 'vs 7d anteriores' };
    case '30d':
      return { prevStart: addDays(date, -59), prevEnd: addDays(date, -30), label: 'vs 30d anteriores' };
    case 'range': {
      if (!endDate) return null;
      const start = new Date(date + 'T12:00:00');
      const end = new Date(endDate + 'T12:00:00');
      const n = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
      return { prevStart: addDays(date, -n), prevEnd: addDays(date, -1), label: 'vs período anterior' };
    }
    default:
      return null;
  }
}

export function useCampaignComparisons(
  campaigns: Campaign[],
  filters: {
    period: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
    date: string;
    endDate?: string;
  }
): { comparisons: Map<string, CampaignComparison> | null; loadingComparisons: boolean } {
  const [comparisons, setComparisons] = useState<Map<string, CampaignComparison> | null>(null);
  const [loadingComparisons, setLoadingComparisons] = useState(false);

  const campaignIdKey = campaigns.map(c => c.id).join(',');

  useEffect(() => {
    setComparisons(null);  // Clear stale data immediately when deps change

    if (!campaigns.length || !filters.date) return;

    const prev = getPreviousPeriod(filters.period, filters.date, filters.endDate);
    if (!prev) return;

    // Campaign.id maps to campaign_id in daily_campaign_metrics (Google Ads campaign ID)
    const campaignIds = campaigns.map(c => c.id).filter(Boolean);

    if (!campaignIds.length) {
      setLoadingComparisons(false);
      return;
    }

    let cancelled = false;

    const fetch = async () => {
      setLoadingComparisons(true);
      try {
        const { data, error } = await supabase
          .from('daily_campaign_metrics')
          .select('campaign_id, spend, revenue_converted_revshare')
          .limit(50000)
          .in('campaign_id', campaignIds)
          .gte('date', prev.prevStart)
          .lte('date', prev.prevEnd);

        if (cancelled) return;
        if (error) throw error;

        const aggregated = new Map<string, { spend: number; revenue: number }>();
        for (const row of data ?? []) {
          const existing = aggregated.get(row.campaign_id) ?? { spend: 0, revenue: 0 };
          aggregated.set(row.campaign_id, {
            spend: existing.spend + (Number(row.spend) || 0),
            revenue: existing.revenue + (Number(row.revenue_converted_revshare) || 0),
          });
        }

        const map = new Map<string, CampaignComparison>();
        for (const [id, agg] of aggregated.entries()) {
          if (agg.spend === 0 && agg.revenue === 0) continue;
          map.set(id, {
            prevInvestment: agg.spend,
            prevRevenue: agg.revenue,
            prevRoas: calculateROAS(agg.revenue, agg.spend),
            comparisonLabel: prev.label,
          });
        }

        setComparisons(map);
      } catch (err) {
        console.error('[useCampaignComparisons] Failed to fetch previous-period data:', err);
      } finally {
        if (!cancelled) setLoadingComparisons(false);
      }
    };

    fetch();
    return () => {
      cancelled = true;
      setLoadingComparisons(false);
    };
  }, [campaignIdKey, filters.period, filters.date, filters.endDate]);

  return { comparisons, loadingComparisons };
}
