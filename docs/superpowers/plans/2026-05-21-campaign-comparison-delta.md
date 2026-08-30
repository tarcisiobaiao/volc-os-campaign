# Campaign Comparison Delta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-metric delta indicators (vs período anterior) to campaign list cards in `/settings/campaigns` and `/dashboard/project/:id`.

**Architecture:** New hook `useCampaignComparisons` fetches previous-period aggregates from `daily_campaign_metrics` after the main list loads; new `MetricDelta` component renders the delta badge inline inside each metric box. Zero DB changes.

**Tech Stack:** React, TypeScript, Supabase JS client (`@/lib/supabase`), lucide-react, Tailwind CSS.

---

## File Map

| Action | File | Purpose |
|---|---|---|
| Create | `src/hooks/useCampaignComparisons.ts` | Fetches previous-period data for campaigns |
| Create | `src/components/campaign/MetricDelta.tsx` | Renders delta badge (arrow + %) |
| Modify | `src/pages/settings/CampaignsSettings.tsx` | Wire hook + add MetricDelta to 4 metric boxes |
| Modify | `src/pages/ProjectDashboard.tsx` | Wire hook + pass to CampaignCard + add MetricDelta to 3 metric boxes |

---

## Task 1: Hook `useCampaignComparisons`

**Files:**
- Create: `src/hooks/useCampaignComparisons.ts`

- [ ] **Step 1: Create the file with full implementation**

```ts
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
  const d = new Date(dateStr + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return d.toISOString().split('T')[0];
}

function getPreviousPeriod(
  period: string,
  date: string,
  endDate?: string
): { prevStart: string; prevEnd: string; label: string } | null {
  if (!date) return null;

  switch (period) {
    case 'today':
      return { prevStart: addDays(date, -1), prevEnd: addDays(date, -1), label: 'vs ontem' };
    case 'yesterday':
      return { prevStart: addDays(date, -1), prevEnd: addDays(date, -1), label: 'vs anteontem' };
    case 'custom':
      return { prevStart: addDays(date, -1), prevEnd: addDays(date, -1), label: 'vs dia anterior' };
    case '7d':
      return { prevStart: addDays(date, -13), prevEnd: addDays(date, -7), label: 'vs 7d anteriores' };
    case '30d':
      return { prevStart: addDays(date, -59), prevEnd: addDays(date, -30), label: 'vs 30d anteriores' };
    case 'range': {
      if (!endDate) return null;
      const start = new Date(date + 'T00:00:00');
      const end = new Date(endDate + 'T00:00:00');
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
    period: string;
    date: string;
    endDate?: string;
  }
): { comparisons: Map<string, CampaignComparison> | null; loadingComparisons: boolean } {
  const [comparisons, setComparisons] = useState<Map<string, CampaignComparison> | null>(null);
  const [loadingComparisons, setLoadingComparisons] = useState(false);

  useEffect(() => {
    if (!campaigns.length || !filters.date) return;

    const prev = getPreviousPeriod(filters.period, filters.date, filters.endDate);
    if (!prev) return;

    const campaignIds = campaigns.map(c => c.id);

    let cancelled = false;

    const fetch = async () => {
      setLoadingComparisons(true);
      try {
        const { data, error } = await supabase
          .from('daily_campaign_metrics')
          .select('campaign_id, spend, revenue_converted_revshare')
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
      } catch {
        // Silent failure — comparisons stay null, MetricDelta renders nothing
      } finally {
        if (!cancelled) setLoadingComparisons(false);
      }
    };

    fetch();
    return () => { cancelled = true; };
  }, [campaigns.length, filters.period, filters.date, filters.endDate]);

  return { comparisons, loadingComparisons };
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo" && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors relating to `useCampaignComparisons.ts`.

- [ ] **Step 3: Commit**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo"
git add src/hooks/useCampaignComparisons.ts
git commit -m "feat: add useCampaignComparisons hook for previous-period data"
```

---

## Task 2: Component `MetricDelta`

**Files:**
- Create: `src/components/campaign/MetricDelta.tsx`

- [ ] **Step 1: Create the file with full implementation**

```tsx
// src/components/campaign/MetricDelta.tsx
import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface MetricDeltaProps {
  current: number;
  previous: number | undefined;
  label: string;
  isLoading: boolean;
}

export const MetricDelta: React.FC<MetricDeltaProps> = ({ current, previous, label, isLoading }) => {
  if (isLoading) {
    return <div className="animate-pulse h-3 w-16 rounded bg-muted mt-0.5" />;
  }

  if (previous === undefined) return null;

  if (current > 0 && previous === 0) {
    return (
      <div className="flex items-center gap-0.5 mt-0.5">
        <span className="text-[10px] font-medium leading-none text-blue-600">Novo</span>
      </div>
    );
  }

  if (previous === 0) return null;

  const delta = ((current - previous) / Math.abs(previous)) * 100;

  if (delta > 0.5) {
    return (
      <div className="flex items-center gap-0.5 mt-0.5">
        <TrendingUp className="h-3 w-3 text-emerald-600 flex-shrink-0" />
        <span className="text-[10px] font-medium leading-none text-emerald-600">
          +{delta.toFixed(1)}% {label}
        </span>
      </div>
    );
  }

  if (delta < -0.5) {
    return (
      <div className="flex items-center gap-0.5 mt-0.5">
        <TrendingDown className="h-3 w-3 text-red-500 flex-shrink-0" />
        <span className="text-[10px] font-medium leading-none text-red-500">
          {delta.toFixed(1)}% {label}
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-0.5 mt-0.5">
      <Minus className="h-3 w-3 text-muted-foreground flex-shrink-0" />
      <span className="text-[10px] font-medium leading-none text-muted-foreground">
        estável {label}
      </span>
    </div>
  );
};
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo" && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors relating to `MetricDelta.tsx`.

- [ ] **Step 3: Commit**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo"
git add src/components/campaign/MetricDelta.tsx
git commit -m "feat: add MetricDelta component for campaign metric comparison"
```

---

## Task 3: Integrate into `CampaignsSettings.tsx`

**Files:**
- Modify: `src/pages/settings/CampaignsSettings.tsx`

Context: The 4 metric boxes are inside the `filteredCampaigns.map()` at lines ~602–649. Each box is a `<div className="text-center p-3 ... rounded-lg">` with `<p className="text-xs ...">` (label) and `<p className="font-semibold ...">` (value).

- [ ] **Step 1: Add imports at top of file**

Find this block near the top of `CampaignsSettings.tsx`:
```tsx
import { CampaignSortSelect } from "@/components/campaign/CampaignSortSelect";
import { sortCampaigns, type CampaignSortKey } from "@/lib/campaignSort";
```

Add after those two lines:
```tsx
import { MetricDelta } from "@/components/campaign/MetricDelta";
import { useCampaignComparisons } from "@/hooks/useCampaignComparisons";
```

- [ ] **Step 2: Call the hook inside the component**

Find this line inside `CampaignsSettings` (around line 84):
```tsx
const { projects, campaigns, loading, error, refresh } = useSupabaseData(filters);
```

Add immediately after it:
```tsx
const { comparisons, loadingComparisons } = useCampaignComparisons(
  filteredCampaigns,
  { period: selectedPeriod, date: selectedDate, endDate: selectedEndDate || undefined }
);
```

Note: `filteredCampaigns` is defined below via `useMemo`. Because hooks must be called unconditionally and before the memos that depend on them, place this call **after** the `filteredCampaigns` useMemo — near line ~170, right after the `filteredCampaigns` const declaration.

Exact location — after the `filteredCampaigns` useMemo closes (line ~169):
```tsx
  }, [campaigns, searchTerm, projectFilter, statusFilter, hasFilters, allowedProjectIds, allowedCampaignIds, sortKey]);

  // Add here:
  const { comparisons, loadingComparisons } = useCampaignComparisons(
    filteredCampaigns,
    { period: selectedPeriod, date: selectedDate, endDate: selectedEndDate || undefined }
  );
```

- [ ] **Step 3: Add MetricDelta to Gasto box**

Find the Gasto metric box (around line 603):
```tsx
<div className="text-center p-3 bg-blue-50 rounded-lg">
  <p className="text-xs text-muted-foreground mb-1">Gasto</p>
  <p className="font-semibold text-slate-800">{new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format(campaign.investment || 0)}</p>
</div>
```

Replace with:
```tsx
<div className="text-center p-3 bg-blue-50 rounded-lg">
  <p className="text-xs text-muted-foreground mb-1">Gasto</p>
  <p className="font-semibold text-slate-800">{new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format(campaign.investment || 0)}</p>
  <MetricDelta
    current={campaign.investment || 0}
    previous={comparisons?.get(campaign.id)?.prevInvestment}
    label={comparisons?.get(campaign.id)?.comparisonLabel ?? ''}
    isLoading={loadingComparisons}
  />
</div>
```

- [ ] **Step 4: Add MetricDelta to Revenue box**

Find the Revenue metric box (around line 610):
```tsx
<div className="text-center p-3 bg-green-50 rounded-lg">
  <p className="text-xs text-muted-foreground mb-1">Revenue</p>
  <p className="font-semibold text-green-600">{formattedRevenues[campaign.id] || 'R$ 0,00'}</p>
</div>
```

Replace with:
```tsx
<div className="text-center p-3 bg-green-50 rounded-lg">
  <p className="text-xs text-muted-foreground mb-1">Revenue</p>
  <p className="font-semibold text-green-600">{formattedRevenues[campaign.id] || 'R$ 0,00'}</p>
  <MetricDelta
    current={campaign.revenue || 0}
    previous={comparisons?.get(campaign.id)?.prevRevenue}
    label={comparisons?.get(campaign.id)?.comparisonLabel ?? ''}
    isLoading={loadingComparisons}
  />
</div>
```

- [ ] **Step 5: Add MetricDelta to ROAS box**

Find the ROAS metric box (around line 614):
```tsx
<div className={`text-center p-3 rounded-lg border ${(() => {
  const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
  return getROIColor(roasExcess);
})()}`}>
  <p className="text-xs text-muted-foreground mb-1">ROAS</p>
  <p className="font-semibold">{(() => {
    const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
    return roasExcess.toFixed(1);
  })()}%</p>
</div>
```

Replace with:
```tsx
<div className={`text-center p-3 rounded-lg border ${(() => {
  const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
  return getROIColor(roasExcess);
})()}`}>
  <p className="text-xs text-muted-foreground mb-1">ROAS</p>
  <p className="font-semibold">{(() => {
    const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
    return roasExcess.toFixed(1);
  })()}%</p>
  <MetricDelta
    current={calculateROAS(campaign.revenue || 0, campaign.investment || 0)}
    previous={comparisons?.get(campaign.id)?.prevRoas}
    label={comparisons?.get(campaign.id)?.comparisonLabel ?? ''}
    isLoading={loadingComparisons}
  />
</div>
```

- [ ] **Step 6: Add MetricDelta to Lucro Bruto box**

Find the Lucro Bruto metric box (around line 624):
```tsx
<div className={`text-center p-3 rounded-lg ${(() => {
  const grossProfit = (campaign.revenue || 0) - (campaign.investment || 0);
  return grossProfit >= 0 ? 'bg-emerald-50 border border-emerald-200' : 'bg-red-50 border border-red-200';
})()}`}>
  <p className="text-xs text-muted-foreground mb-1">Lucro Bruto</p>
  <p className={`font-semibold ${(() => {
    const grossProfit = (campaign.revenue || 0) - (campaign.investment || 0);
    return grossProfit >= 0 ? 'text-emerald-600' : 'text-red-600';
  })()}`}>{new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format((campaign.revenue || 0) - (campaign.investment || 0))}</p>
</div>
```

Replace with:
```tsx
<div className={`text-center p-3 rounded-lg ${(() => {
  const grossProfit = (campaign.revenue || 0) - (campaign.investment || 0);
  return grossProfit >= 0 ? 'bg-emerald-50 border border-emerald-200' : 'bg-red-50 border border-red-200';
})()}`}>
  <p className="text-xs text-muted-foreground mb-1">Lucro Bruto</p>
  <p className={`font-semibold ${(() => {
    const grossProfit = (campaign.revenue || 0) - (campaign.investment || 0);
    return grossProfit >= 0 ? 'text-emerald-600' : 'text-red-600';
  })()}`}>{new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format((campaign.revenue || 0) - (campaign.investment || 0))}</p>
  <MetricDelta
    current={(campaign.revenue || 0) - (campaign.investment || 0)}
    previous={
      comparisons?.get(campaign.id)
        ? (comparisons.get(campaign.id)!.prevRevenue - comparisons.get(campaign.id)!.prevInvestment)
        : undefined
    }
    label={comparisons?.get(campaign.id)?.comparisonLabel ?? ''}
    isLoading={loadingComparisons}
  />
</div>
```

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo" && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new errors.

- [ ] **Step 8: Commit**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo"
git add src/pages/settings/CampaignsSettings.tsx
git commit -m "feat: add comparison deltas to CampaignsSettings campaign cards"
```

---

## Task 4: Integrate into `ProjectDashboard.tsx` (CampaignCard)

**Files:**
- Modify: `src/pages/ProjectDashboard.tsx`

Context: `CampaignCard` is a component defined at lines ~116–250 inside `ProjectDashboard.tsx`. It receives props and renders 3 metric boxes (Gasto, Revenue, ROAS) at lines ~214–233. The hook call goes in the `ProjectDashboard` function, not inside `CampaignCard`.

- [ ] **Step 1: Add imports at top of `ProjectDashboard.tsx`**

Find this block near the top of the file:
```tsx
import { FunnelUrlsEditor } from "@/components/campaign/FunnelUrlsEditor";
import { useToast } from "@/hooks/use-toast";
```

Add after those two lines:
```tsx
import { MetricDelta } from "@/components/campaign/MetricDelta";
import { useCampaignComparisons, CampaignComparison } from "@/hooks/useCampaignComparisons";
```

- [ ] **Step 2: Extend CampaignCard props to accept comparisons**

Find the `CampaignCard` props destructuring (around line 116):
```tsx
const CampaignCard = ({
  campaign,
  onAction,
  formatRevenue,
  currentProject,
  selectedPeriod,
  selectedDate,
  navigate
}: {
  campaign: any;
  onAction: (action: string, campaignId: string) => void;
  formatRevenue: (brl: number) => string;
  currentProject: any;
  selectedPeriod: string;
  selectedDate: string;
  navigate: (path: string) => void;
}) => {
```

Replace with:
```tsx
const CampaignCard = ({
  campaign,
  onAction,
  formatRevenue,
  currentProject,
  selectedPeriod,
  selectedDate,
  navigate,
  comparison,
  loadingComparisons,
}: {
  campaign: any;
  onAction: (action: string, campaignId: string) => void;
  formatRevenue: (brl: number) => string;
  currentProject: any;
  selectedPeriod: string;
  selectedDate: string;
  navigate: (path: string) => void;
  comparison: CampaignComparison | undefined;
  loadingComparisons: boolean;
}) => {
```

- [ ] **Step 3: Add MetricDelta to Gasto box inside CampaignCard**

Find the Gasto box inside CampaignCard (around line 215):
```tsx
<div className="text-center p-3 bg-red-50 rounded-lg">
  <p className="text-xs text-muted-foreground mb-1">Gasto</p>
  <p className="font-semibold text-red-600">
    {new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(campaign.investment || 0)}
  </p>
</div>
```

Replace with:
```tsx
<div className="text-center p-3 bg-red-50 rounded-lg">
  <p className="text-xs text-muted-foreground mb-1">Gasto</p>
  <p className="font-semibold text-red-600">
    {new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(campaign.investment || 0)}
  </p>
  <MetricDelta
    current={campaign.investment || 0}
    previous={comparison?.prevInvestment}
    label={comparison?.comparisonLabel ?? ''}
    isLoading={loadingComparisons}
  />
</div>
```

- [ ] **Step 4: Add MetricDelta to Revenue box inside CampaignCard**

Find the Revenue box inside CampaignCard (around line 223):
```tsx
<div className="text-center p-3 bg-green-50 rounded-lg">
  <p className="text-xs text-muted-foreground mb-1">Revenue</p>
  <p className="font-semibold text-green-600">{formatRevenue(campaign.revenue || 0)}</p>
</div>
```

Replace with:
```tsx
<div className="text-center p-3 bg-green-50 rounded-lg">
  <p className="text-xs text-muted-foreground mb-1">Revenue</p>
  <p className="font-semibold text-green-600">{formatRevenue(campaign.revenue || 0)}</p>
  <MetricDelta
    current={campaign.revenue || 0}
    previous={comparison?.prevRevenue}
    label={comparison?.comparisonLabel ?? ''}
    isLoading={loadingComparisons}
  />
</div>
```

- [ ] **Step 5: Add MetricDelta to ROAS box inside CampaignCard**

Find the ROAS box inside CampaignCard (around line 228):
```tsx
<div className={`text-center p-3 rounded-lg border ${getROIColor(roasExcess)}`}>
  <p className="text-xs text-muted-foreground mb-1">ROAS</p>
  <p className="font-semibold">{roasExcess.toFixed(1)}%</p>
</div>
```

Replace with:
```tsx
<div className={`text-center p-3 rounded-lg border ${getROIColor(roasExcess)}`}>
  <p className="text-xs text-muted-foreground mb-1">ROAS</p>
  <p className="font-semibold">{roasExcess.toFixed(1)}%</p>
  <MetricDelta
    current={roasExcess}
    previous={comparison?.prevRoas}
    label={comparison?.comparisonLabel ?? ''}
    isLoading={loadingComparisons}
  />
</div>
```

- [ ] **Step 6: Call the hook in `ProjectDashboard` and pass to `CampaignCard`**

Inside the `ProjectDashboard` function, find the `filteredCampaigns` useMemo (around line 831):
```tsx
  }, [projectCampaigns, searchFilter, statusFilter, sortKey]);
```

Add the hook call immediately after:
```tsx
  }, [projectCampaigns, searchFilter, statusFilter, sortKey]);

  const { comparisons: campaignComparisons, loadingComparisons } = useCampaignComparisons(
    filteredCampaigns,
    { period: selectedPeriod, date: selectedDate, endDate: selectedEndDate || undefined }
  );
```

- [ ] **Step 7: Pass comparison props to each CampaignCard render**

Find the CampaignCard render (around line 1427):
```tsx
{filteredCampaigns?.map((campaign: any) => (
  <CampaignCard
    key={campaign.id}
    campaign={campaign}
    onAction={handleCampaignAction}
    formatRevenue={formatRevenue}
    currentProject={currentProject}
    selectedPeriod={selectedPeriod}
    selectedDate={selectedDate}
    navigate={navigate}
  />
))}
```

Replace with:
```tsx
{filteredCampaigns?.map((campaign: any) => (
  <CampaignCard
    key={campaign.id}
    campaign={campaign}
    onAction={handleCampaignAction}
    formatRevenue={formatRevenue}
    currentProject={currentProject}
    selectedPeriod={selectedPeriod}
    selectedDate={selectedDate}
    navigate={navigate}
    comparison={campaignComparisons?.get(campaign.id)}
    loadingComparisons={loadingComparisons}
  />
))}
```

- [ ] **Step 8: Verify TypeScript compiles**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo" && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new errors.

- [ ] **Step 9: Commit**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo"
git add src/pages/ProjectDashboard.tsx
git commit -m "feat: add comparison deltas to ProjectDashboard campaign cards"
```

---

## Task 5: Manual QA

- [ ] **Step 1: Kill any stale processes and start dev server**

```bash
lsof -ti:3001 | xargs kill -9 2>/dev/null; lsof -ti:8080 | xargs kill -9 2>/dev/null
cd "/Users/mac/Desktop/Sistema Webgo/webgo" && npm run dev:all
```

- [ ] **Step 2: QA checklist**

Open http://localhost:8082/settings/campaigns (or whichever port Vite picks):

| Check | Expected |
|---|---|
| Period = "Hoje" | Each campaign card shows shimmer briefly, then delta "vs ontem" below each metric |
| Period = "Ontem" | Delta shows "vs anteontem" |
| Period = "7 dias" | Delta shows "vs 7d anteriores" |
| Campaign with growth | Green ↑ +X.X% label |
| Campaign with decline | Red ↓ −X.X% label |
| Campaign with no previous data | No delta rendered (no error, no empty space) |
| Open http://localhost:8082/dashboard/project/50 | Same deltas visible in campaign list |
| Layout not broken on mobile (< 768px) | Deltas wrap cleanly inside metric boxes |

- [ ] **Step 3: Final commit if any minor visual tweaks were needed**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo"
git add -p  # stage only what changed
git commit -m "fix: adjust MetricDelta visual tweaks from QA"
```

---

## Self-Review

**Spec coverage:**
- ✅ Hook `useCampaignComparisons` — Task 1
- ✅ Component `MetricDelta` — Task 2
- ✅ CampaignsSettings 4 metric boxes — Task 3 (steps 3–6)
- ✅ ProjectDashboard/CampaignCard 3 metric boxes — Task 4 (steps 3–5)
- ✅ Proportional previous period for all period types — Task 1 `getPreviousPeriod`
- ✅ Silent failure / no render when no previous data — Task 1 + Task 2
- ✅ Shimmer loading state — Task 2
- ✅ "Novo" badge for new campaigns — Task 2

**Placeholder scan:** None found.

**Type consistency:** `CampaignComparison` defined in Task 1, imported in Task 4. `comparison` prop (singular, typed as `CampaignComparison | undefined`) consistent across Tasks 4 steps 2, 3, 4, 5, 6, 7.
