/**
 * v6 RBAC — PayoutsMonthly
 *
 * Bloco 5: payouts agregados por mês. Tabela read-only nesta etapa.
 * O gráfico (Recharts) entra na 3.B junto com filtros mais ricos.
 */
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { AlertCircle, Calendar } from 'lucide-react';
import type { PayoutsByMonth } from '@/v6/types/v6';

interface PayoutsMonthlyProps {
  data: PayoutsByMonth[];
  isLoading: boolean;
  error: Error | null;
}

const fmtBRL = (value: number): string =>
  new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);

const fmtMonth = (yyyymm01: string): string => {
  // 'YYYY-MM-01' → 'mmm/yyyy'
  try {
    const d = new Date(yyyymm01 + 'T00:00:00');
    return d.toLocaleDateString('pt-BR', {
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return yyyymm01;
  }
};

export function PayoutsMonthly({ data, isLoading, error }: PayoutsMonthlyProps) {
  const totals = data.reduce(
    (acc, m) => ({
      revenue: acc.revenue + m.revenue_total,
      spend: acc.spend + m.spend_total,
      net: acc.net + m.net_profit_total,
      comissao: acc.comissao + m.comissao_total,
    }),
    { revenue: 0, spend: 0, net: 0, comissao: 0 }
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-display">
          <span className="rounded-md bg-info/10 p-1.5 text-info">
            <Calendar className="h-4 w-4" />
          </span>
          Payouts mensais
        </CardTitle>
        <CardDescription>
          Agregado de <code>daily_campaign_member_payouts</code> por mês
          (consolidando todos os usuários e campanhas). Gráfico será
          adicionado na 3.B.
        </CardDescription>
      </CardHeader>

      <CardContent>
        {isLoading && (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        )}

        {!isLoading && error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span>Erro ao carregar payouts: {error.message}</span>
          </div>
        )}

        {!isLoading && !error && data.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed py-12 text-center">
            <span className="rounded-full bg-muted p-3 text-muted-foreground">
              <Calendar className="h-5 w-5" />
            </span>
            <div className="kicker">Sem payouts</div>
            <p className="max-w-sm text-sm text-muted-foreground">
              Nenhum payout calculado ainda. Rode o backfill da Etapa 2
              (v6_10) se essa for a primeira vez.
            </p>
          </div>
        )}

        {!isLoading && !error && data.length > 0 && (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="kicker">Mês</TableHead>
                  <TableHead className="kicker text-right">Linhas</TableHead>
                  <TableHead className="kicker text-right">Campanhas</TableHead>
                  <TableHead className="kicker text-right">Revenue</TableHead>
                  <TableHead className="kicker text-right">Spend</TableHead>
                  <TableHead className="kicker text-right">Lucro líquido</TableHead>
                  <TableHead className="kicker text-right">Comissão</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((m) => (
                  <TableRow key={m.month}>
                    <TableCell className="font-medium capitalize">
                      {fmtMonth(m.month)}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular text-muted-foreground">
                      {m.linhas.toLocaleString('pt-BR')}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular text-muted-foreground">
                      {m.campanhas_distintas.toLocaleString('pt-BR')}
                    </TableCell>
                    <TableCell className="text-right tabular text-sm">
                      {fmtBRL(m.revenue_total)}
                    </TableCell>
                    <TableCell className="text-right tabular text-sm">
                      {fmtBRL(m.spend_total)}
                    </TableCell>
                    <TableCell className="text-right tabular text-sm">
                      {fmtBRL(m.net_profit_total)}
                    </TableCell>
                    <TableCell className="text-right tabular text-sm font-semibold text-primary">
                      {fmtBRL(m.comissao_total)}
                    </TableCell>
                  </TableRow>
                ))}
                <TableRow className="bg-muted/40 font-semibold">
                  <TableCell>Total</TableCell>
                  <TableCell />
                  <TableCell />
                  <TableCell className="text-right tabular">
                    {fmtBRL(totals.revenue)}
                  </TableCell>
                  <TableCell className="text-right tabular">
                    {fmtBRL(totals.spend)}
                  </TableCell>
                  <TableCell className="text-right tabular">
                    {fmtBRL(totals.net)}
                  </TableCell>
                  <TableCell className="text-right tabular text-primary">
                    {fmtBRL(totals.comissao)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
