# Placement Negation Suggestions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Sugestões de Negativação" card to Display campaign pages that analyzes the last 14 days of placement data and lists placements to block in Google Ads, with a one-click copy button.

**Architecture:** A Supabase SQL function computes per-placement windowed ROAS averages and trend, returning only placements that pass the two-crivo gate (3+ negative windows + ≥10% ROAS decline). A React hook calls the function via RPC. A collapsible card component renders two tables (NEGATIVAR / OBSERVAR) following the same pattern as the existing `DisplayROITable`. The card is always fixed to the last 14 days regardless of the page's date filter.

**Tech Stack:** PostgreSQL (Supabase RPC), React, TypeScript, Tailwind CSS, lucide-react, shadcn/ui (Card, Table, Badge, Collapsible)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/sql/get_placement_negation_suggestions.sql` | Create | SQL reference copy |
| `src/hooks/usePlacementNegation.ts` | Create | RPC call, split NEGATIVAR / OBSERVAR |
| `src/components/campaign/PlacementNegationCard.tsx` | Create | Card UI, copy button |
| `src/pages/CampaignDetailDashboard.tsx` | Modify | Add import + render card after DisplayROITable |

---

## Task 1: SQL function in Supabase

**Files:**
- Create: `src/sql/get_placement_negation_suggestions.sql` (reference copy)
- Execute: via Supabase MCP `execute_sql` tool

- [ ] **Step 1: Create the SQL reference file**

Create `src/sql/get_placement_negation_suggestions.sql` with this exact content:

```sql
-- Placement Negation Suggestions
-- Returns placements with consistently negative ROI across time windows.
-- Two-crivo gate: 3+ negative windows AND ROAS declined ≥10% vs start of period.
-- Minimum: 3 days of data, R$ 15 total spend.

CREATE OR REPLACE FUNCTION get_placement_negation_suggestions(p_campaign_id TEXT)
RETURNS TABLE (
  canal          TEXT,
  categoria      TEXT,
  roas_1d        NUMERIC,
  roas_3d        NUMERIC,
  roas_7d        NUMERIC,
  roas_14d       NUMERIC,
  var_roas_pct   NUMERIC,
  motivo         TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH base AS (
    SELECT
      v.canal,
      v.date,
      v.roas_pct,
      v.investido_brl
    FROM vw_display_roi v
    WHERE v.campaign_id = p_campaign_id
      AND v.date >= CURRENT_DATE - INTERVAL '14 days'
      AND v.date < CURRENT_DATE  -- exclude today (partial day)
  ),

  eligible AS (
    -- Minimum data gate: 3+ days, R$15+ spend
    SELECT canal
    FROM base
    GROUP BY canal
    HAVING COUNT(DISTINCT date) >= 3
       AND SUM(investido_brl) > 15
  ),

  windowed AS (
    SELECT
      b.canal,
      AVG(CASE WHEN b.date = CURRENT_DATE - 1                                      THEN b.roas_pct END) AS roas_1d,
      AVG(CASE WHEN b.date >= CURRENT_DATE - 3                                     THEN b.roas_pct END) AS roas_3d,
      AVG(CASE WHEN b.date >= CURRENT_DATE - 7                                     THEN b.roas_pct END) AS roas_7d,
      AVG(b.roas_pct)                                                                                    AS roas_14d,
      -- Trend: first 3 days in window vs last 3 days
      AVG(CASE WHEN b.date BETWEEN CURRENT_DATE - 14 AND CURRENT_DATE - 12        THEN b.roas_pct END) AS roas_inicio,
      AVG(CASE WHEN b.date >= CURRENT_DATE - 3                                     THEN b.roas_pct END) AS roas_fim
    FROM base b
    JOIN eligible e USING (canal)
    GROUP BY b.canal
  ),

  scored AS (
    SELECT
      w.*,
      CASE
        WHEN w.roas_inicio IS NOT NULL AND w.roas_inicio != 0
        THEN (w.roas_fim - w.roas_inicio) / ABS(w.roas_inicio)
        ELSE NULL
      END AS var_roas,
      (CASE WHEN w.roas_1d  < 0 THEN 1 ELSE 0 END +
       CASE WHEN w.roas_3d  < 0 THEN 1 ELSE 0 END +
       CASE WHEN w.roas_7d  < 0 THEN 1 ELSE 0 END +
       CASE WHEN w.roas_14d < 0 THEN 1 ELSE 0 END) AS windows_neg
    FROM windowed w
  ),

  classified AS (
    SELECT
      s.*,
      CASE
        WHEN s.windows_neg >= 3 AND COALESCE(s.var_roas, 0) <= -0.10 THEN 'NEGATIVAR'
        WHEN s.windows_neg = 4                                         THEN 'NEGATIVAR'
        WHEN s.windows_neg >= 2 AND COALESCE(s.var_roas, 0) <= -0.10  THEN 'OBSERVAR'
        WHEN s.windows_neg = 3                                         THEN 'OBSERVAR'
        ELSE NULL
      END AS categoria
    FROM scored s
  )

  SELECT
    c.canal::TEXT,
    c.categoria::TEXT,
    ROUND(c.roas_1d::NUMERIC,  1),
    ROUND(c.roas_3d::NUMERIC,  1),
    ROUND(c.roas_7d::NUMERIC,  1),
    ROUND(c.roas_14d::NUMERIC, 1),
    ROUND(c.var_roas::NUMERIC, 3),
    CASE
      WHEN c.categoria = 'NEGATIVAR' THEN
        'Negativo em ' || c.windows_neg || ' de 4 janelas' ||
        CASE WHEN c.var_roas IS NOT NULL
             THEN ', ROAS caiu ' || ROUND((ABS(c.var_roas) * 100)::NUMERIC, 1) || '% no período'
             ELSE '' END
      WHEN c.categoria = 'OBSERVAR' THEN
        'Negativo em ' || c.windows_neg || ' de 4 janelas' ||
        CASE WHEN c.var_roas IS NOT NULL
             THEN ', queda de ' || ROUND((ABS(c.var_roas) * 100)::NUMERIC, 1) || '% — aguardar mais dados'
             ELSE ' — aguardar mais dados' END
    END::TEXT
  FROM classified c
  WHERE c.categoria IS NOT NULL
  ORDER BY
    CASE c.categoria WHEN 'NEGATIVAR' THEN 0 ELSE 1 END,
    COALESCE(c.var_roas, 0) ASC;
END;
$$;
```

- [ ] **Step 2: Execute the SQL in Supabase**

Use the Supabase MCP `execute_sql` tool to run the full SQL from Step 1 against the project.

Expected result: `CREATE FUNCTION` with no errors.

- [ ] **Step 3: Verify the function exists and returns data**

Run this test query via Supabase MCP `execute_sql`:

```sql
SELECT * FROM get_placement_negation_suggestions('23749513086') LIMIT 10;
```

Expected: either rows with `canal`, `categoria`, `roas_1d` etc., or an empty result set (both are valid — no error is what matters).

- [ ] **Step 4: Commit the SQL reference file**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo"
git add src/sql/get_placement_negation_suggestions.sql
git commit -m "feat: add get_placement_negation_suggestions SQL function"
```

---

## Task 2: TypeScript hook — `usePlacementNegation`

**Files:**
- Create: `src/hooks/usePlacementNegation.ts`

- [ ] **Step 1: Create the hook file**

Create `src/hooks/usePlacementNegation.ts` with this exact content:

```typescript
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
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo" && npx tsc --noEmit 2>&1 | head -20
```

Expected: no output (zero errors).

- [ ] **Step 3: Commit**

```bash
git add src/hooks/usePlacementNegation.ts
git commit -m "feat: add usePlacementNegation hook"
```

---

## Task 3: UI Component — `PlacementNegationCard`

**Files:**
- Create: `src/components/campaign/PlacementNegationCard.tsx`

- [ ] **Step 1: Create the component**

Create `src/components/campaign/PlacementNegationCard.tsx` with this exact content:

```tsx
import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { AlertTriangle, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePlacementNegation, PlacementSuggestion } from '@/hooks/usePlacementNegation';

interface PlacementNegationCardProps {
  campaignId: string;
}

function formatRoas(value: number | null): { text: string; className: string } {
  if (value === null) return { text: '—', className: 'text-muted-foreground' };
  return {
    text: `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`,
    className: value >= 0 ? 'text-green-600' : 'text-red-600',
  };
}

function formatVar(value: number | null): { text: string; className: string } {
  if (value === null) return { text: '—', className: 'text-muted-foreground' };
  const pct = value * 100;
  return {
    text: `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`,
    className: pct >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium',
  };
}

function PlacementTable({ rows }: { rows: PlacementSuggestion[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Placement</TableHead>
          <TableHead className="text-right">ROI 1d</TableHead>
          <TableHead className="text-right">ROI 3d</TableHead>
          <TableHead className="text-right">ROI 7d</TableHead>
          <TableHead className="text-right">ROI 14d</TableHead>
          <TableHead className="text-right">Variação</TableHead>
          <TableHead>Diagnóstico</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(row => {
          const r1 = formatRoas(row.roas_1d);
          const r3 = formatRoas(row.roas_3d);
          const r7 = formatRoas(row.roas_7d);
          const r14 = formatRoas(row.roas_14d);
          const v = formatVar(row.var_roas_pct);
          return (
            <TableRow key={row.canal}>
              <TableCell className="font-mono text-xs max-w-[200px] truncate" title={row.canal}>
                {row.canal}
              </TableCell>
              <TableCell className={`text-right text-xs ${r1.className}`}>{r1.text}</TableCell>
              <TableCell className={`text-right text-xs ${r3.className}`}>{r3.text}</TableCell>
              <TableCell className={`text-right text-xs ${r7.className}`}>{r7.text}</TableCell>
              <TableCell className={`text-right text-xs ${r14.className}`}>{r14.text}</TableCell>
              <TableCell className={`text-right text-xs ${v.className}`}>{v.text}</TableCell>
              <TableCell className="text-xs text-muted-foreground max-w-[220px]">{row.motivo}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export function PlacementNegationCard({ campaignId }: PlacementNegationCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const { negativar, observar, loading, error } = usePlacementNegation(campaignId);

  const totalCount = negativar.length + observar.length;

  const handleCopy = () => {
    const list = negativar.map(p => p.canal).join('\n');
    navigator.clipboard.writeText(list).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <Card className="mt-6">
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer hover:bg-muted/30 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 flex-wrap">
                <CardTitle className="text-lg flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-yellow-500" />
                  Sugestões de Negativação
                </CardTitle>
                {!loading && totalCount > 0 && (
                  <Badge variant="secondary">{totalCount} placement{totalCount !== 1 ? 's' : ''}</Badge>
                )}
                <span className="text-xs text-muted-foreground font-normal">
                  Análise dos últimos 14 dias
                </span>
              </div>
              {isOpen ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
            </div>
          </CardHeader>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <CardContent>
            {loading && (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                <span className="ml-3 text-muted-foreground">Analisando placements...</span>
              </div>
            )}

            {error && (
              <div className="text-center py-8 text-red-500 text-sm">
                Erro ao carregar sugestões: {error}
              </div>
            )}

            {!loading && !error && totalCount === 0 && (
              <p className="text-center py-8 text-muted-foreground text-sm">
                Nenhum placement com histórico negativo consistente nos últimos 14 dias.
              </p>
            )}

            {!loading && !error && negativar.length > 0 && (
              <div className="mb-6">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-red-500 inline-block" />
                    <span className="text-sm font-semibold text-red-600">
                      Negativar ({negativar.length})
                    </span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopy}
                    className="h-7 gap-1 text-xs"
                  >
                    {copied ? (
                      <><Check className="h-3 w-3" /> Copiado</>
                    ) : (
                      <><Copy className="h-3 w-3" /> Copiar lista</>
                    )}
                  </Button>
                </div>
                <PlacementTable rows={negativar} />
              </div>
            )}

            {!loading && !error && observar.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="h-2 w-2 rounded-full bg-yellow-500 inline-block" />
                  <span className="text-sm font-semibold text-yellow-600">
                    Observar ({observar.length})
                  </span>
                </div>
                <PlacementTable rows={observar} />
              </div>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo" && npx tsc --noEmit 2>&1 | head -20
```

Expected: no output (zero errors).

- [ ] **Step 3: Commit**

```bash
git add src/components/campaign/PlacementNegationCard.tsx
git commit -m "feat: add PlacementNegationCard component"
```

---

## Task 4: Integration into CampaignDetailDashboard

**Files:**
- Modify: `src/pages/CampaignDetailDashboard.tsx`

The file is at `/Users/mac/Desktop/Sistema Webgo/webgo/src/pages/CampaignDetailDashboard.tsx`.

Current state at the integration point (around line 1344):
```tsx
      {/* ROI Display por Placement */}
        {campaignId && selectedDate && (
          <DisplayROITable
            campaignId={campaignId}
            startDate={selectedDate}
            endDate={selectedEndDate || selectedDate}
          />
        )}
```

- [ ] **Step 1: Add import**

Add this import at line 23 of `CampaignDetailDashboard.tsx`, after the existing `DisplayROITable` import:

```tsx
import { PlacementNegationCard } from "@/components/campaign/PlacementNegationCard";
```

- [ ] **Step 2: Add the card after DisplayROITable**

Replace the `{/* ROI Display por Placement */}` block with:

```tsx
      {/* ROI Display por Placement */}
        {campaignId && selectedDate && (
          <DisplayROITable
            campaignId={campaignId}
            startDate={selectedDate}
            endDate={selectedEndDate || selectedDate}
          />
        )}

      {/* Sugestões de Negativação */}
        {campaignId && (
          <PlacementNegationCard campaignId={campaignId} />
        )}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd "/Users/mac/Desktop/Sistema Webgo/webgo" && npx tsc --noEmit 2>&1 | head -20
```

Expected: no output.

- [ ] **Step 4: Verify in browser**

Open `http://localhost:8080/dashboard/campaign/23749513086` and confirm:
- "Sugestões de Negativação" card appears below "ROI Display por Placement"
- Card is collapsible
- Badge shows placement count (or no badge if empty)
- "Análise dos últimos 14 dias" sub-label is visible
- Expanding the card shows either placements or the empty-state message

- [ ] **Step 5: Test the copy button**

If NEGATIVAR placements appear:
- Click "Copiar lista"
- Button changes to "Copiado ✓" for 2 seconds
- Paste into a text editor and confirm each placement name is on its own line

- [ ] **Step 6: Commit**

```bash
git add src/pages/CampaignDetailDashboard.tsx
git commit -m "feat: integrate PlacementNegationCard into campaign detail page"
```

---

## Self-Review

**Spec coverage:**
- ✅ SQL function with 4 windows (1d, 3d, 7d, 14d) — Task 1
- ✅ Minimum gate: 3 days + R$15 spend — Task 1 `eligible` CTE
- ✅ NEGATIVAR: 3+ negative windows + var_roas ≤ -10% — Task 1 `classified` CTE
- ✅ OBSERVAR: 2+ windows + -10% OR 3 windows alone — Task 1 `classified` CTE
- ✅ Hook splits results into `negativar` / `observar` arrays — Task 2
- ✅ Fixed 14-day window (not page date filter) — SQL + hook have no date params from page
- ✅ Collapsible card with same pattern as DisplayROITable — Task 3
- ✅ NEGATIVAR block with copy button — Task 3 `handleCopy`
- ✅ OBSERVAR block without copy button — Task 3
- ✅ ROI values colored green/red, null shown as `—` — Task 3 `formatRoas`
- ✅ Empty state message — Task 3
- ✅ Error state — Task 3
- ✅ Card appears only when `campaignId` exists — Task 4
- ✅ Copy: one placement per line — `join('\n')` in Task 3

**Placeholder scan:** None found.

**Type consistency:** `PlacementSuggestion` defined in hook (Task 2) and imported in component (Task 3). `var_roas_pct` field name consistent across SQL output column, interface, and `formatVar` call.
