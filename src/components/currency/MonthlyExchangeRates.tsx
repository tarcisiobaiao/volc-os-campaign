import React, { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { CalendarDays, RefreshCw, CheckCircle } from 'lucide-react';
import { useMonthlyExchangeRates, type MonthlyRate } from '@/hooks/useMonthlyExchangeRates';
import { useToast } from '@/hooks/use-toast';

const MONTH_LABELS: Record<string, string> = {
  '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril',
  '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto',
  '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro',
};

function formatYearMonth(ym: string): string {
  const [year, month] = ym.split('-');
  return `${MONTH_LABELS[month] || month} ${year}`;
}

function formatYearMonthShort(ym: string): string {
  const [year, month] = ym.split('-');
  const short = (MONTH_LABELS[month] || month).slice(0, 3);
  return `${short}/${year}`;
}

/** Generate last N months as YYYY-MM strings (excluding current month) */
function getPastMonths(count: number): string[] {
  const months: string[] = [];
  const now = new Date();
  for (let i = 1; i <= count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  }
  return months;
}

export const MonthlyExchangeRates: React.FC = () => {
  const { rates, loading, recalculating, recalculateMonth } = useMonthlyExchangeRates();
  const { toast } = useToast();

  const pastMonths = useMemo(() => getPastMonths(11), []);

  const [selectedMonth, setSelectedMonth] = useState(pastMonths[0]);
  const [rateValue, setRateValue] = useState('');
  const [initialized, setInitialized] = useState(false);

  // Build lookup map from DB
  const rateMap = useMemo(() => {
    const map = new Map<string, MonthlyRate>();
    for (const r of rates) map.set(r.year_month, r);
    return map;
  }, [rates]);

  // When selected month changes or rates load, sync the input value
  const selectedRate = rateMap.get(selectedMonth);

  // Initialize rate input when data loads or month changes
  if (!initialized && !loading) {
    setRateValue(selectedRate ? selectedRate.rate.toFixed(4) : '');
    setInitialized(true);
  }

  const handleMonthChange = (ym: string) => {
    setSelectedMonth(ym);
    const existing = rateMap.get(ym);
    setRateValue(existing ? existing.rate.toFixed(4) : '');
  };

  const handleRecalculate = async () => {
    const rate = parseFloat(rateValue);
    if (isNaN(rate) || rate <= 0 || rate >= 100) {
      toast({ title: 'Taxa inválida (deve ser > 0 e < 100)', variant: 'destructive' });
      return;
    }

    try {
      const result = await recalculateMonth(selectedMonth, rate);
      toast({
        title: `${formatYearMonthShort(selectedMonth)} recalculado`,
        description: `Taxa R$ ${rate.toFixed(4)} — ${result.total_rows} registros atualizados`,
      });
    } catch {
      toast({ title: 'Erro ao recalcular', variant: 'destructive' });
    }
  };

  const isRecalculating = recalculating === selectedMonth;

  if (loading) {
    return (
      <Card className="relative overflow-hidden shadow-card">
        <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
        <CardHeader className="pb-2 pt-3 px-4">
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-info/10 text-info p-1.5"><CalendarDays className="h-4 w-4" /></span>
            <div className="space-y-1.5">
              <div className="skeleton h-3 w-40 rounded" />
              <div className="skeleton h-2.5 w-28 rounded" />
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-3 pt-1 space-y-2">
          <div className="skeleton h-8 w-full rounded-md" />
          <div className="skeleton h-8 w-full rounded-md" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="relative overflow-hidden shadow-card hover-lift reveal" style={{ ['--i' as any]: 0 }}>
      <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
      <CardHeader className="pb-2 pt-3 px-4">
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-info/10 text-info p-1.5">
            <CalendarDays className="h-4 w-4" />
          </span>
          <div>
            <span className="kicker block">Recalcular Mês Anterior</span>
            <p className="text-xs text-muted-foreground">Alterar taxa e recalcular conversões</p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-3 pt-1 space-y-2">
        {/* Month selector */}
        <Select value={selectedMonth} onValueChange={handleMonthChange}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {pastMonths.map((ym) => {
              const existing = rateMap.get(ym);
              return (
                <SelectItem key={ym} value={ym}>
                  <span className="flex items-center gap-2">
                    {formatYearMonth(ym)}
                    {existing && (
                      <span className="text-muted-foreground text-xs tabular">
                        — R$ {existing.rate.toFixed(2)}
                      </span>
                    )}
                  </span>
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>

        {/* Rate input + recalculate button */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <span className="absolute left-2 top-1/2 transform -translate-y-1/2 text-xs text-muted-foreground">
              R$
            </span>
            <Input
              type="number"
              aria-label="Nova taxa de câmbio, em reais por dólar"
              step="0.0001"
              min="0.01"
              max="99"
              value={rateValue}
              onChange={(e) => setRateValue(e.target.value)}
              placeholder="5.5000"
              className="pl-6 h-8 text-sm tabular"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRecalculate();
              }}
            />
          </div>
          <Button
            onClick={handleRecalculate}
            disabled={isRecalculating || !rateValue}
            size="sm"
            className="h-8 px-3 text-xs"
          >
            {isRecalculating ? (
              <>
                <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                Calculando
              </>
            ) : (
              <>
                <CheckCircle className="h-3 w-3 mr-1" />
                Recalcular
              </>
            )}
          </Button>
        </div>

        {/* Info about selected month */}
        {selectedRate?.recalculated_at && (
          <p className="text-[11px] text-muted-foreground flex items-center gap-1">
            <CheckCircle className="h-3 w-3 text-success" />
            Último recálculo: <span className="tabular">{new Date(selectedRate.recalculated_at).toLocaleString('pt-BR')}</span>
          </p>
        )}
        {!selectedRate && (
          <div className="flex items-center gap-2 rounded-md bg-muted/40 px-2 py-1.5">
            <span className="rounded-md bg-info/10 text-info p-1"><CalendarDays className="h-3 w-3" /></span>
            <p className="text-[11px] text-muted-foreground">
              Sem taxa definida — insira o valor e recalcule
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
