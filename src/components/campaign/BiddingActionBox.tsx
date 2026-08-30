import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, Minus, Zap, AlertTriangle, LockKeyhole } from 'lucide-react';
import { formatCostCurrency } from '@/utils/currencyUtils';

interface BiddingActionBoxProps {
  campaignId: string;
  currentBid: number;
  suggestedBid: number;
  action: 'AUMENTAR' | 'REDUZIR' | 'MANTER';
  risk: 'BAIXO' | 'MEDIO' | 'ALTO';
  variationPercent: number;
  dataReferencia: string;
}

export function BiddingActionBox({
  campaignId: _campaignId,
  currentBid,
  suggestedBid,
  action,
  risk,
  variationPercent,
  dataReferencia: _dataReferencia,
}: BiddingActionBoxProps) {
  const [editedValue, setEditedValue] = useState<string>(suggestedBid.toFixed(4));

  // Determinar cor e ícone baseado na ação (tokens semânticos VOLC)
  const getActionConfig = () => {
    switch (action) {
      case 'AUMENTAR':
        return {
          icon: <TrendingUp className="h-5 w-5" />,
          color: 'text-success',
          chip: 'bg-success/10 text-success',
          surface: 'bg-success/5',
          border: 'border-success/30',
          accent: 'bg-success'
        };
      case 'REDUZIR':
        return {
          icon: <TrendingDown className="h-5 w-5" />,
          color: 'text-destructive',
          chip: 'bg-destructive/10 text-destructive',
          surface: 'bg-destructive/5',
          border: 'border-destructive/30',
          accent: 'bg-destructive'
        };
      default:
        return {
          icon: <Minus className="h-5 w-5" />,
          color: 'text-info',
          chip: 'bg-info/10 text-info',
          surface: 'bg-info/5',
          border: 'border-info/30',
          accent: 'bg-info'
        };
    }
  };

  const getRiskBadge = () => {
    const map = {
      BAIXO: { cls: 'bg-success/12 text-success', label: 'Baixo risco' },
      MEDIO: { cls: 'bg-warning/12 text-warning', label: 'Médio risco' },
      ALTO: { cls: 'bg-destructive/12 text-destructive', label: 'Alto risco' }
    };
    const r = map[risk];
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${r.cls}`}>
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
        {r.label}
      </span>
    );
  };

  const actionConfig = getActionConfig();
  const valueDiff = parseFloat(editedValue) - currentBid;
  const percentDiff = currentBid > 0 ? ((valueDiff / currentBid) * 100) : 0;

  return (
    <Card className={`relative overflow-hidden shadow-card reveal ${actionConfig.border} ${actionConfig.surface}`} style={{ ['--i' as any]: 0 }}>
      <span className={`pointer-events-none absolute inset-x-0 top-0 h-0.5 ${actionConfig.accent}`} />
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <span className={`rounded-md p-1.5 ${actionConfig.chip}`}><Zap className="h-4 w-4" /></span>
          Ajuste de Bidding Sugerido
          {getRiskBadge()}
        </CardTitle>
        <CardDescription>
          O sistema analisou sua campanha e sugere a seguinte ação
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Ação recomendada */}
        <div className={`flex items-center gap-3 p-4 rounded-lg border ${actionConfig.border} bg-card/60`}>
          <span className={`rounded-md p-1.5 ${actionConfig.chip}`}>
            {actionConfig.icon}
          </span>
          <div className="flex-1">
            <div className="kicker">Ação recomendada</div>
            <div className={`font-display text-lg font-bold ${actionConfig.color}`}>{action}</div>
          </div>
          <div className="text-right">
            <div className="kicker">Variação</div>
            <div className={`font-display text-lg font-bold tabular ${variationPercent >= 0 ? 'text-success' : 'text-destructive'}`}>
              {variationPercent >= 0 ? '+' : ''}{variationPercent.toFixed(1)}%
            </div>
          </div>
        </div>

        {/* Valores */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label className="kicker">Bidding atual</Label>
            <div className="font-display text-2xl font-bold tabular tracking-tight text-foreground">
              {formatCostCurrency(currentBid)}
            </div>
          </div>

          <div className="space-y-1">
            <Label className="kicker">Valor sugerido</Label>
            <div className={`font-display text-2xl font-bold tabular tracking-tight ${actionConfig.color}`}>
              {formatCostCurrency(suggestedBid)}
            </div>
          </div>
        </div>

        {/* Input de edição */}
        <div className="space-y-2">
          <Label htmlFor="bid-value" className="flex items-center gap-2">
            Valor a Aplicar
            {parseFloat(editedValue) !== suggestedBid && (
              <Badge variant="secondary" className="text-xs">Editado</Badge>
            )}
          </Label>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">R$</span>
            <Input
              id="bid-value"
              type="number"
              step="0.0001"
              min="0"
              value={editedValue}
              onChange={(e) => setEditedValue(e.target.value)}
              className="text-lg font-mono tabular"
            />
          </div>
          {valueDiff !== 0 && (
            <div className={`text-sm tabular ${valueDiff > 0 ? 'text-success' : 'text-destructive'}`}>
              {valueDiff > 0 ? '+' : ''}{formatCostCurrency(Math.abs(valueDiff))} ({percentDiff >= 0 ? '+' : ''}{percentDiff.toFixed(1)}%) em relação ao atual
            </div>
          )}
        </div>

        {/* Aviso de risco alto */}
        {risk === 'ALTO' && (
          <div className="flex items-start gap-2 p-3 bg-destructive/5 border border-destructive/30 rounded-lg">
            <AlertTriangle className="h-5 w-5 text-destructive mt-0.5 flex-shrink-0" />
            <div className="text-sm text-destructive">
              <strong>Atenção:</strong> Esta ação tem alto risco. Certifique-se de revisar os dados antes de aplicar.
            </div>
          </div>
        )}

        {/* A rota legada nunca mais escreve do navegador. Aplicação real só
            volta na H0, com aprovação do plano exato, recibo anterior à rede
            e verificação posterior. */}
        <Button
          disabled
          className="w-full gap-2"
          size="lg"
        >
          <LockKeyhole className="h-5 w-5" />
          Aplicação bloqueada nesta página legada
        </Button>

        <p className="text-center text-xs leading-relaxed text-muted-foreground">
          Esta tela mostra a recomendação, mas não envia alterações. A aplicação
          autenticada e auditável será feita pela página canônica da campanha.
        </p>
      </CardContent>
    </Card>
  );
}
