/**
 * v6 RBAC — TopCampaigns
 *
 * Bloco 6: top 10 campanhas que mais geraram comissão (v6).
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
import { AlertCircle, Trophy } from 'lucide-react';
import type { TopCampaignResult } from '@/v6/types/v6';

interface TopCampaignsProps {
  data: TopCampaignResult[];
  isLoading: boolean;
  error: Error | null;
}

const fmtBRL = (value: number): string =>
  new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);

export function TopCampaigns({ data, isLoading, error }: TopCampaignsProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-display">
          <span className="rounded-md bg-warning/10 p-1.5 text-warning">
            <Trophy className="h-4 w-4" />
          </span>
          Top campanhas geradoras de comissão
        </CardTitle>
        <CardDescription>
          Dez campanhas com maior soma de <code>amount</code> em
          <code> daily_campaign_member_payouts</code>.
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
            <span>Erro ao carregar top campanhas: {error.message}</span>
          </div>
        )}

        {!isLoading && !error && data.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed py-12 text-center">
            <span className="rounded-full bg-muted p-3 text-muted-foreground">
              <Trophy className="h-5 w-5" />
            </span>
            <div className="kicker">Sem ranking</div>
            <p className="max-w-sm text-sm text-muted-foreground">
              Nenhuma campanha com payout calculado ainda.
            </p>
          </div>
        )}

        {!isLoading && !error && data.length > 0 && (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="kicker w-10 text-center">#</TableHead>
                  <TableHead className="kicker">Campanha</TableHead>
                  <TableHead className="kicker text-right">Dias</TableHead>
                  <TableHead className="kicker text-right">Revenue</TableHead>
                  <TableHead className="kicker text-right">Spend</TableHead>
                  <TableHead className="kicker text-right">Comissão</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((c, idx) => (
                  <TableRow key={c.campaign_id}>
                    <TableCell className="text-center">
                      <span
                        className={
                          'inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold tabular ' +
                          (idx === 0
                            ? 'bg-warning/15 text-warning'
                            : idx < 3
                            ? 'bg-primary/10 text-primary'
                            : 'bg-muted text-muted-foreground')
                        }
                      >
                        {idx + 1}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-md truncate font-medium">
                        {c.campaign_name || '(sem nome)'}
                      </div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {c.campaign_id}
                      </div>
                    </TableCell>
                    <TableCell className="text-right text-sm tabular text-muted-foreground">
                      {c.dias_calculados.toLocaleString('pt-BR')}
                    </TableCell>
                    <TableCell className="text-right tabular text-sm">
                      {fmtBRL(c.revenue_total)}
                    </TableCell>
                    <TableCell className="text-right tabular text-sm">
                      {fmtBRL(c.spend_total)}
                    </TableCell>
                    <TableCell className="text-right tabular text-sm font-semibold text-primary">
                      {fmtBRL(c.comissao_total)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
