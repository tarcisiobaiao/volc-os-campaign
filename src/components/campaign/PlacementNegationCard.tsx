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
    className: value >= 0 ? 'text-success' : 'text-destructive',
  };
}

function formatVar(value: number | null): { text: string; className: string } {
  if (value === null) return { text: '—', className: 'text-muted-foreground' };
  const pct = value * 100;
  return {
    text: `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`,
    className: pct >= 0 ? 'text-success font-medium' : 'text-destructive font-medium',
  };
}

function PlacementTable({ rows }: { rows: PlacementSuggestion[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="kicker">Placement</TableHead>
          <TableHead className="text-right kicker">ROI 1d</TableHead>
          <TableHead className="text-right kicker">ROI 3d</TableHead>
          <TableHead className="text-right kicker">ROI 7d</TableHead>
          <TableHead className="text-right kicker">ROI 14d</TableHead>
          <TableHead className="text-right kicker">Variação</TableHead>
          <TableHead className="kicker">Diagnóstico</TableHead>
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
            <TableRow key={row.canal} className="border-border hover:bg-muted/40 transition-colors">
              <TableCell className="font-mono text-xs max-w-[200px] truncate" title={row.canal}>
                {row.canal}
              </TableCell>
              <TableCell className={`text-right text-xs tabular ${r1.className}`}>{r1.text}</TableCell>
              <TableCell className={`text-right text-xs tabular ${r3.className}`}>{r3.text}</TableCell>
              <TableCell className={`text-right text-xs tabular ${r7.className}`}>{r7.text}</TableCell>
              <TableCell className={`text-right text-xs tabular ${r14.className}`}>{r14.text}</TableCell>
              <TableCell className={`text-right text-xs tabular ${v.className}`}>{v.text}</TableCell>
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
    }).catch(() => {
      console.error('[PlacementNegationCard] Clipboard write failed');
    });
  };

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <Card className="mt-6 relative overflow-hidden shadow-card">
        <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-warning" />
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer hover:bg-muted/30 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 flex-wrap">
                <CardTitle className="text-lg flex items-center gap-2">
                  <span className="rounded-md bg-warning/10 text-warning p-1.5"><AlertTriangle className="h-4 w-4" /></span>
                  Sugestões de Negativação
                </CardTitle>
                {!loading && totalCount > 0 && (
                  <Badge variant="secondary" className="tabular">{totalCount} placement{totalCount !== 1 ? 's' : ''}</Badge>
                )}
                <span className="text-xs text-muted-foreground font-normal">
                  Análise dos últimos 14 dias
                </span>
              </div>
              {isOpen ? <ChevronUp className="h-5 w-5 text-muted-foreground" /> : <ChevronDown className="h-5 w-5 text-muted-foreground" />}
            </div>
          </CardHeader>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <CardContent>
            {loading && (
              <div className="space-y-2 py-2">
                <div className="skeleton h-8 w-full" />
                <div className="skeleton h-8 w-full" />
                <div className="skeleton h-8 w-5/6" />
              </div>
            )}

            {error && (
              <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
                <span className="rounded-md bg-destructive/10 p-2 text-destructive"><AlertTriangle className="h-5 w-5" /></span>
                <div className="kicker text-destructive">Erro</div>
                <p className="text-sm text-muted-foreground">Erro ao carregar sugestões: {error}</p>
              </div>
            )}

            {!loading && !error && totalCount === 0 && (
              <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
                <span className="rounded-md bg-success/10 p-2 text-success"><Check className="h-5 w-5" /></span>
                <div className="kicker">Tudo certo</div>
                <p className="text-sm text-muted-foreground">
                  Nenhum placement com histórico negativo consistente nos últimos 14 dias.
                </p>
              </div>
            )}

            {!loading && !error && negativar.length > 0 && (
              <div className="mb-6">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-destructive inline-block" />
                    <span className="kicker text-destructive">
                      Negativar ({negativar.length})
                    </span>
                    <span className="hairline-aurora flex-1" />
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopy}
                    className="h-7 gap-1 text-xs ml-3 flex-shrink-0"
                  >
                    {copied ? (
                      <><Check className="h-3 w-3" /> Copiado</>
                    ) : (
                      <><Copy className="h-3 w-3" /> Copiar lista</>
                    )}
                  </Button>
                </div>
                <div className="rounded-md border overflow-x-auto">
                  <PlacementTable rows={negativar} />
                </div>
              </div>
            )}

            {!loading && !error && observar.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="h-2 w-2 rounded-full bg-warning inline-block" />
                  <span className="kicker text-warning">
                    Observar ({observar.length})
                  </span>
                  <span className="hairline-aurora flex-1" />
                </div>
                <div className="rounded-md border overflow-x-auto">
                  <PlacementTable rows={observar} />
                </div>
              </div>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
