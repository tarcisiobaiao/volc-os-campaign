# Campaign Comparison Delta — Design Spec
Date: 2026-05-21

## Goal
Add per-metric comparison indicators to campaign list cards in both `/settings/campaigns` and `/dashboard/project/:id`. Each metric (Gasto, Revenue, ROAS, Lucro Bruto) shows the delta vs the equivalent prior period so users can assess trend at a glance without entering each campaign.

## Scope
- `src/hooks/useCampaignComparisons.ts` — new hook (data fetching)
- `src/components/campaign/MetricDelta.tsx` — new UI component (delta display)
- `src/pages/settings/CampaignsSettings.tsx` — integrate delta into 4 metric boxes
- `src/pages/ProjectDashboard.tsx` (CampaignCard) — integrate delta into 3 metric boxes

**Out of scope:** campaign detail page, summary metric cards at top of ProjectDashboard, any DB changes.

---

## Data Layer — `useCampaignComparisons`

### Input
```ts
useCampaignComparisons(
  campaigns: Campaign[],
  filters: {
    period: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
    date: string;       // YYYY-MM-DD
    endDate?: string;   // YYYY-MM-DD, only for range
  }
)
```

### Previous period calculation
| Current period | Previous period |
|---|---|
| today (D) | D-1 to D-1 |
| yesterday (D-1) | D-2 to D-2 |
| custom (date X) | X-1 to X-1 |
| 7d (D-6 to D) | D-13 to D-7 |
| 30d (D-29 to D) | D-59 to D-30 |
| range (start → end, N days) | start-N to start-1 |

### Query
Single query to `daily_campaign_metrics`:
```sql
SELECT campaign_id, SUM(spend), SUM(revenue_converted_revshare)
FROM daily_campaign_metrics
WHERE campaign_id IN (...currentCampaignIds)
  AND date >= prevStartDate
  AND date <= prevEndDate
GROUP BY campaign_id
```

### Output
```ts
{
  comparisons: Map<string, {
    prevInvestment: number;
    prevRevenue: number;
    prevRoas: number;       // calculated from prevRevenue/prevInvestment
    comparisonLabel: string; // "vs ontem", "vs 7d anteriores", etc.
  }> | null;
  loadingComparisons: boolean;
}
```

### Comparison labels
| Period | Label |
|---|---|
| today | "vs ontem" |
| yesterday | "vs anteontem" |
| 7d | "vs 7d anteriores" |
| 30d | "vs 30d anteriores" |
| custom | "vs dia anterior" |
| range | "vs período anterior" |

### Edge cases
- No previous data for a campaign → entry absent from Map → MetricDelta renders nothing
- `prevInvestment === 0` and `prevRevenue === 0` → absent from Map (treat as no data)
- `previous === 0` and `current > 0` → show "Novo" badge in blue
- Hook fires only when `campaigns.length > 0` and `date` is set

---

## UI Component — `MetricDelta`

### Props
```ts
interface MetricDeltaProps {
  current: number;
  previous: number | undefined;
  label: string;          // "vs ontem"
  isLoading: boolean;
}
```

### Rendering logic
```
if isLoading → skeleton: animate-pulse h-3 w-16 rounded bg-muted
if previous === undefined → render nothing
if current > 0 and previous === 0 → "Novo" badge (blue, text-xs)
else:
  delta = ((current - previous) / Math.abs(previous)) * 100
  if delta > 0.5  → TrendingUp green  + "+X.X% {label}"
  if delta < -0.5 → TrendingDown red  + "−X.X% {label}"
  else            → Minus icon gray   + "estável {label}"
```

### Visual style
- Container: `flex items-center gap-0.5 mt-0.5`
- Icon: `h-3 w-3` (TrendingUp / TrendingDown / Minus from lucide-react)
- Text: `text-[10px] font-medium leading-none`
- Green: `text-emerald-600`, Red: `text-red-500`, Gray: `text-muted-foreground`

---

## Integration

### CampaignsSettings.tsx
- Call `useCampaignComparisons(filteredCampaigns, { period: selectedPeriod, date: selectedDate, endDate: selectedEndDate })` near top of component
- In each campaign card metric box, below the value `<p>`, add:
  ```tsx
  <MetricDelta
    current={campaign.investment}
    previous={comparisons?.get(campaign.id)?.prevInvestment}
    label={comparisons?.get(campaign.id)?.comparisonLabel ?? ''}
    isLoading={loadingComparisons}
  />
  ```
- Same pattern for Revenue, ROAS, Lucro Bruto

### ProjectDashboard.tsx — CampaignCard
- Pass `comparisons` and `loadingComparisons` as props to `CampaignCard`
- Same `<MetricDelta>` pattern for the 3 boxes (Gasto, Revenue, ROAS)

---

## Error handling
- If the previous-period query fails → `comparisons` stays `null`, `loadingComparisons` false → MetricDelta renders nothing silently
- Never blocks or delays the main campaign list render

---

## Self-review
- No placeholders or TBDs remain
- Architecture matches feature description: hook feeds component, component inserted inline
- Scope is focused: 4 files touched, 2 new files created
- All edge cases explicitly handled
