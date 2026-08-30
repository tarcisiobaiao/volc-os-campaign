# Placement Negation Suggestions — Design Spec
Date: 2026-05-21

## Goal
Add a "Sugestões de Negativação" card to Display campaign detail pages. The card analyzes the last 14 days of placement performance and surfaces placements to negate (block) in Google Ads, with a one-click copy-to-clipboard list.

## Scope
- SQL function `get_placement_negation_suggestions(p_campaign_id TEXT)` in Supabase
- `src/hooks/usePlacementNegation.ts` — new hook (calls RPC, returns typed data)
- `src/components/campaign/PlacementNegationCard.tsx` — new UI card component
- `src/pages/CampaignDetail.tsx` — integrate card below `DisplayROITable`

**Out of scope:** changes to `vw_display_roi`, `DisplayROITable`, other campaign types, automated negation via Google Ads API.

---

## Data Layer — SQL Function

### Function signature
```sql
get_placement_negation_suggestions(p_campaign_id TEXT)
RETURNS TABLE (
  canal           TEXT,
  categoria       TEXT,   -- 'NEGATIVAR' | 'OBSERVAR'
  roas_1d         NUMERIC,
  roas_3d         NUMERIC,
  roas_7d         NUMERIC,
  roas_14d        NUMERIC,
  var_roas_pct    NUMERIC, -- (roas_fim - roas_inicio) / ABS(roas_inicio)
  motivo          TEXT
)
```

### Data source
`vw_display_roi` filtered by `campaign_id = p_campaign_id` and `date >= CURRENT_DATE - 14`.

### Per-placement calculations
| Metric | Calculation |
|---|---|
| `roas_1d` | AVG(roas_pct) WHERE date = CURRENT_DATE - 1 |
| `roas_3d` | AVG(roas_pct) WHERE date >= CURRENT_DATE - 3 |
| `roas_7d` | AVG(roas_pct) WHERE date >= CURRENT_DATE - 7 |
| `roas_14d` | AVG(roas_pct) over full 14-day window |
| `roas_inicio` | AVG(roas_pct) of first 3 days in window |
| `roas_fim` | AVG(roas_pct) of last 3 days in window |
| `var_roas_pct` | `(roas_fim - roas_inicio) / ABS(roas_inicio)` |
| `windows_negative` | Count of {1d, 3d, 7d, 14d} windows where avg ROAS < 0 |

### Minimum data filter
- At least 3 days with data in the 14-day window
- Total spend (`investido_brl`) > R$ 15 over the 14-day window

### Classification rules
- **NEGATIVAR**: `windows_negative >= 3` AND `var_roas_pct <= -0.10`
- **OBSERVAR**: `windows_negative >= 3` AND `var_roas_pct > -0.10`  
  OR `windows_negative == 2` AND `var_roas_pct <= -0.10`

### motivo field (human-readable)
- NEGATIVAR: `"Negativo em X de 4 janelas, ROAS caiu Y% no período"`
- OBSERVAR: `"Negativo em X de 4 janelas, queda de Y% — aguardar mais dados"`

### Edge cases
- `roas_inicio = 0`: skip var_roas calculation, treat var as 0 (no trend signal)
- Placement with data only in 1 or 2 days: excluded by minimum filter
- All windows positive: placement not returned at all

---

## Frontend Hook — `usePlacementNegation`

### Location
`src/hooks/usePlacementNegation.ts`

### Input
```ts
usePlacementNegation(campaignId: string)
```

### Behavior
- Calls `supabase.rpc('get_placement_negation_suggestions', { p_campaign_id: campaignId })`
- Fires once on mount; re-fires if `campaignId` changes
- Always queries 14 days (period filter on the page is irrelevant — the SQL function uses fixed `CURRENT_DATE - 14`)

### Output
```ts
{
  negativar: PlacementSuggestion[];
  observar:  PlacementSuggestion[];
  loading:   boolean;
  error:     string | null;
}
```

### Type
```ts
interface PlacementSuggestion {
  canal:        string;
  categoria:    'NEGATIVAR' | 'OBSERVAR';
  roas_1d:      number | null;
  roas_3d:      number | null;
  roas_7d:      number | null;
  roas_14d:     number | null;
  var_roas_pct: number | null;
  motivo:       string;
}
```

### Error handling
- On RPC error: `error` set, both arrays empty, `loading` false
- Never blocks the main campaign page render

---

## UI Component — `PlacementNegationCard`

### Location
`src/components/campaign/PlacementNegationCard.tsx`

### Props
```ts
interface PlacementNegationCardProps {
  campaignId: string;
}
```
(Hook is called internally — no data props needed)

### Structure

**Card wrapper:** collapsible (same `<Collapsible>` + `<Card>` pattern as `DisplayROITable`)

**Header:**
- Icon: `AlertTriangle` (lucide-react)
- Title: `"Sugestões de Negativação"`
- Badge: total count of NEGATIVAR + OBSERVAR placements
- Sub-label: `"Análise dos últimos 14 dias"` (always fixed, never reflects page date filter)
- Collapse chevron

**Loading state:** spinner centered, same as `DisplayROITable`

**Empty state:** `"Nenhum placement com histórico negativo consistente nos últimos 14 dias."` — muted text, centered

**NEGATIVAR block** (shown first, only if `negativar.length > 0`):
- Section label: red dot + `"Negativar"` in `text-red-600 font-semibold text-sm`
- Copy button top-right: `"Copiar lista"` with `Copy` icon — copies `negativar.map(p => p.canal).join('\n')` to clipboard; changes to `"Copiado ✓"` for 2 seconds
- Table columns: Placement | ROI 1d | ROI 3d | ROI 7d | ROI 14d | Variação | Motivo
- ROI values colored: green if ≥ 0, red if < 0; `—` if null
- Variação: `var_roas_pct` formatted as `"-X.X%"` in red, `"+X.X%"` in green
- Rows sorted by `var_roas_pct` ascending (worst first)

**OBSERVAR block** (shown second, only if `observar.length > 0`):
- Section label: yellow dot + `"Observar"` in `text-yellow-600 font-semibold text-sm`
- No copy button (not ready to negate)
- Same table columns, same formatting
- Rows sorted by `var_roas_pct` ascending

### Visual style
Follows existing `DisplayROITable` conventions: same card, same table, same badge and collapsible pattern. No new design system components introduced.

---

## Integration — `CampaignDetail.tsx`

- Import `PlacementNegationCard`
- Render it immediately after `<DisplayROITable ... />`, passing `campaignId`
- Only rendered when campaign type is Display (condition already exists in the page for `DisplayROITable` — reuse same gate)

---

## Self-review

- No TBDs or placeholders remain
- `roas_inicio = 0` edge case explicitly handled in SQL
- Minimum filter (3 days + R$15) matches client-approved criteria
- Two-crivo gate (windows_negative + var_roas_pct) validated by client
- Period filter on page does NOT affect this card — stated explicitly in header and hook
- Scope is focused: 1 SQL function + 1 hook + 1 component + 1 integration point
- Copy button copies NEGATIVAR only (OBSERVAR is not ready to act on)
- Empty state and error state both handled
