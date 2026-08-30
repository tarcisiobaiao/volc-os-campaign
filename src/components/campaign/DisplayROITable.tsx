import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableFooter } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { ChevronDown, ChevronUp, DollarSign, TrendingUp, BarChart3, Eye, MousePointer, ArrowUpDown, CalendarDays } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { formatBrlCurrency } from '@/utils/currencyUtils';
import { useDisplayROI } from '@/hooks/useDisplayROI';
import type { SortField } from '@/types/displayROI';

interface DisplayROITableProps {
  campaignId: string;
  startDate: string;
  endDate: string;
}

export function DisplayROITable({ campaignId, startDate, endDate }: DisplayROITableProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { data, loading, error, summary, totals, sortField, sortDirection, handleSort, hasData } = useDisplayROI({
    campaignId,
    startDate,
    endDate,
  });

  const formatNumber = (value: number) =>
    new Intl.NumberFormat('pt-BR').format(Math.round(value));

  const formatPercent = (value: number) =>
    `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;

  const profitColor = (value: number) =>
    value > 0 ? 'text-success' : value < 0 ? 'text-destructive' : 'text-muted-foreground';

  const roasColor = (value: number) => {
    if (value >= 20) return 'text-success';
    if (value >= 0) return 'text-warning';
    return 'text-destructive';
  };

  const statusPill = (status: string) => {
    const map: Record<string, string> = {
      LUCRATIVO: 'bg-success/12 text-success',
      NEUTRO: 'bg-warning/12 text-warning',
      PREJUIZO: 'bg-destructive/12 text-destructive',
    };
    const cls = map[status] ?? 'bg-muted text-muted-foreground';
    return (
      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
        {status}
      </span>
    );
  };

  const SortableHeader = ({ field, children }: { field: SortField; children: React.ReactNode }) => (
    <TableHead
      className="cursor-pointer select-none hover:bg-muted/50 transition-colors"
      onClick={() => handleSort(field)}
    >
      <div className="flex items-center gap-1 kicker">
        {children}
        {sortField === field ? (
          sortDirection === 'asc' ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-30" />
        )}
      </div>
    </TableHead>
  );

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <Card className="mt-6 relative overflow-hidden shadow-card">
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer hover:bg-muted/30 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 flex-wrap">
                <CardTitle className="text-lg flex items-center gap-2">
                  <span className="rounded-md bg-primary/10 text-primary p-1.5"><BarChart3 className="h-4 w-4" /></span>
                  ROI Display por Placement
                </CardTitle>
                {hasData && (
                  <Badge variant="secondary" className="tabular">
                    {data.length} placements
                  </Badge>
                )}
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground font-normal tabular">
                  <CalendarDays className="h-3 w-3" />
                  {startDate === endDate
                    ? format(parseISO(startDate), "dd MMM yyyy", { locale: ptBR })
                    : `${format(parseISO(startDate), "dd MMM", { locale: ptBR })} - ${format(parseISO(endDate), "dd MMM yyyy", { locale: ptBR })}`
                  }
                </span>
              </div>
              {isOpen ? <ChevronUp className="h-5 w-5 text-muted-foreground" /> : <ChevronDown className="h-5 w-5 text-muted-foreground" />}
            </div>
          </CardHeader>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <CardContent>
            {loading && (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="skeleton h-16 w-full" />
                ))}
              </div>
            )}

            {error && (
              <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
                <span className="rounded-md bg-destructive/10 p-2 text-destructive"><BarChart3 className="h-5 w-5" /></span>
                <div className="kicker text-destructive">Erro</div>
                <p className="text-sm text-muted-foreground">Erro ao carregar dados: {error}</p>
              </div>
            )}

            {!loading && !error && !hasData && (
              <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
                <span className="rounded-md bg-muted p-2 text-muted-foreground"><BarChart3 className="h-5 w-5" /></span>
                <div className="kicker">Sem dados</div>
                <p className="text-sm text-muted-foreground">Nenhum dado de ROI Display encontrado para este período.</p>
              </div>
            )}

            {!loading && !error && hasData && (
              <>
                {/* Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
                  <Card className="relative overflow-hidden border hover-lift">
                    <CardContent className="p-3">
                      <div className="kicker mb-1 flex items-center gap-1">
                        <DollarSign className="h-3 w-3" />
                        Total investido
                      </div>
                      <p className="font-display text-sm font-bold tabular">{formatBrlCurrency(summary.totalInvestido)}</p>
                    </CardContent>
                  </Card>

                  <Card className="relative overflow-hidden border hover-lift">
                    <CardContent className="p-3">
                      <div className="kicker mb-1 flex items-center gap-1">
                        <DollarSign className="h-3 w-3" />
                        Total receita
                      </div>
                      <p className="font-display text-sm font-bold tabular">{formatBrlCurrency(summary.totalReceita)}</p>
                    </CardContent>
                  </Card>

                  <Card className="relative overflow-hidden border hover-lift">
                    <CardContent className="p-3">
                      <div className="kicker mb-1 flex items-center gap-1">
                        <TrendingUp className="h-3 w-3" />
                        Lucro bruto
                      </div>
                      <p className={`font-display text-sm font-bold tabular ${profitColor(summary.lucroBruto)}`}>
                        {formatBrlCurrency(summary.lucroBruto)}
                      </p>
                    </CardContent>
                  </Card>

                  <Card className="relative overflow-hidden border hover-lift">
                    <CardContent className="p-3">
                      <div className="kicker mb-1 flex items-center gap-1">
                        <TrendingUp className="h-3 w-3" />
                        ROAS
                      </div>
                      <p className={`font-display text-sm font-bold tabular ${roasColor(summary.roasMedia)}`}>
                        {formatPercent(summary.roasMedia)}
                      </p>
                    </CardContent>
                  </Card>

                  <Card className="relative overflow-hidden border hover-lift">
                    <CardContent className="p-3">
                      <div className="kicker mb-1 flex items-center gap-1">
                        <Eye className="h-3 w-3" />
                        Impressões
                      </div>
                      <p className="font-display text-sm font-bold tabular">{formatNumber(summary.totalImpressoes)}</p>
                    </CardContent>
                  </Card>

                  <Card className="relative overflow-hidden border hover-lift">
                    <CardContent className="p-3">
                      <div className="kicker mb-1 flex items-center gap-1">
                        <MousePointer className="h-3 w-3" />
                        Clicks
                      </div>
                      <p className="font-display text-sm font-bold tabular">{formatNumber(summary.totalClicks)}</p>
                    </CardContent>
                  </Card>
                </div>

                {/* Placements Table */}
                <div className="rounded-md border overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <SortableHeader field="canal">Canal</SortableHeader>
                        <SortableHeader field="investido_brl">Investido (R$)</SortableHeader>
                        <SortableHeader field="receita_brl">Receita (R$)</SortableHeader>
                        <SortableHeader field="lucro_bruto">Lucro Bruto (R$)</SortableHeader>
                        <SortableHeader field="roas_pct">ROAS (%)</SortableHeader>
                        <SortableHeader field="impressions">Impressoes</SortableHeader>
                        <SortableHeader field="clicks">Clicks</SortableHeader>
                        <SortableHeader field="status_roi">Status</SortableHeader>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.map((row, index) => (
                        <TableRow key={`${row.canal}-${index}`} className="border-border hover:bg-muted/40 transition-colors">
                          <TableCell className="max-w-[280px]">
                            <a
                              href={row.canal.startsWith('http') ? row.canal : `https://${row.canal}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-primary hover:underline truncate block"
                              title={row.canal}
                            >
                              {row.canal.length > 45 ? row.canal.substring(0, 45) + '...' : row.canal}
                            </a>
                          </TableCell>
                          <TableCell className="tabular">{formatBrlCurrency(row.investido_brl)}</TableCell>
                          <TableCell className="tabular">{formatBrlCurrency(row.receita_brl)}</TableCell>
                          <TableCell className={`tabular ${profitColor(row.lucro_bruto)}`}>
                            {formatBrlCurrency(row.lucro_bruto)}
                          </TableCell>
                          <TableCell className={`tabular ${roasColor(row.roas_pct)}`}>
                            {formatPercent(row.roas_pct)}
                          </TableCell>
                          <TableCell className="tabular">{formatNumber(row.impressions)}</TableCell>
                          <TableCell className="tabular">{formatNumber(row.clicks)}</TableCell>
                          <TableCell>{statusPill(row.status_roi)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                    <TableFooter>
                      <TableRow className="bg-muted/50 font-bold">
                        <TableCell className="kicker">Total</TableCell>
                        <TableCell className="tabular">{formatBrlCurrency(totals.investido_brl)}</TableCell>
                        <TableCell className="tabular">{formatBrlCurrency(totals.receita_brl)}</TableCell>
                        <TableCell className={`tabular ${profitColor(totals.lucro_bruto)}`}>
                          {formatBrlCurrency(totals.lucro_bruto)}
                        </TableCell>
                        <TableCell className={`tabular ${roasColor(totals.roas_pct)}`}>
                          {formatPercent(totals.roas_pct)}
                        </TableCell>
                        <TableCell className="tabular">{formatNumber(totals.impressions)}</TableCell>
                        <TableCell className="tabular">{formatNumber(totals.clicks)}</TableCell>
                        <TableCell />
                      </TableRow>
                    </TableFooter>
                  </Table>
                </div>
              </>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
