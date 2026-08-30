/**
 * v6 RBAC — CommissionsTimeline
 *
 * Bloco 4: comissões versionadas. Mostra todas as vigências
 * (passadas e atuais) numa tabela ordenada por valid_from desc.
 * Usa um Badge "Vigente" para destacar quem está ativo agora.
 */
import { useMemo, useState } from 'react';
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
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { AlertCircle, Receipt, Search, CalendarX, Check } from 'lucide-react';
import type { CampaignCommissionEnriched } from '@/v6/types/v6';

interface CommissionsTimelineProps {
  data: CampaignCommissionEnriched[];
  isLoading: boolean;
  error: Error | null;
  /** Opcional: dispara fluxo de "encerrar vigência" para a comissão. */
  onEnd?: (commission: CampaignCommissionEnriched) => void;
}

const fmtDate = (iso: string | null): string => {
  if (!iso) return '—';
  try {
    return new Date(iso + 'T00:00:00').toLocaleDateString('pt-BR');
  } catch {
    return iso;
  }
};

const fmtPct = (value: number): string =>
  new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value) + '%';

export function CommissionsTimeline({
  data,
  isLoading,
  error,
  onEnd,
}: CommissionsTimelineProps) {
  const [search, setSearch] = useState('');
  const [onlyActive, setOnlyActive] = useState(false);

  const filtered = useMemo(() => {
    let result = data;
    if (onlyActive) result = result.filter((c) => c.is_active);
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (c) =>
          c.user?.email?.toLowerCase().includes(q) ||
          c.user?.name?.toLowerCase().includes(q) ||
          c.campaign?.campaign_name?.toLowerCase().includes(q) ||
          c.campaign_id.toLowerCase().includes(q)
      );
    }
    return result;
  }, [data, search, onlyActive]);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 font-display">
              <span className="rounded-md bg-success/10 p-1.5 text-success">
                <Receipt className="h-4 w-4" />
              </span>
              Comissões versionadas
            </CardTitle>
            <CardDescription>
              Cada linha é uma vigência (user × campanha × período).
              Existência da linha = direito à comissão. Ausência = sem
              comissão, mesmo se for member.
            </CardDescription>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => setOnlyActive((v) => !v)}
              className={
                'inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ' +
                (onlyActive
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-input bg-background hover:bg-accent')
              }
            >
              {onlyActive && <Check className="h-3.5 w-3.5" />}
              Só vigentes
            </button>
            <div className="relative w-full max-w-xs">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar usuário/campanha"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8"
              />
            </div>
          </div>
        </div>
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
            <span>Erro ao carregar comissões: {error.message}</span>
          </div>
        )}

        {!isLoading && !error && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed py-12 text-center">
            <span className="rounded-full bg-muted p-3 text-muted-foreground">
              {data.length === 0 ? (
                <Receipt className="h-5 w-5" />
              ) : (
                <Search className="h-5 w-5" />
              )}
            </span>
            <div className="kicker">
              {data.length === 0 ? 'Sem comissões' : 'Sem resultados'}
            </div>
            <p className="max-w-sm text-sm text-muted-foreground">
              {data.length === 0
                ? 'Nenhuma comissão cadastrada em campaign_commissions.'
                : 'Nenhuma comissão corresponde ao filtro.'}
            </p>
          </div>
        )}

        {!isLoading && !error && filtered.length > 0 && (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="kicker">Usuário</TableHead>
                  <TableHead className="kicker">Campanha</TableHead>
                  <TableHead className="kicker text-right">Taxa</TableHead>
                  <TableHead className="kicker">Vigência</TableHead>
                  <TableHead className="kicker">Status</TableHead>
                  {onEnd && <TableHead className="kicker text-right">Ações</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.slice(0, 200).map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>
                      <div className="font-medium">
                        {c.user?.name || '(usuário desconhecido)'}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {c.user?.email || c.user_id}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-xs truncate font-medium">
                        {c.campaign?.campaign_name || c.campaign_id}
                      </div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {c.campaign_id}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-display font-semibold tabular">
                      {fmtPct(c.percentage)}
                    </TableCell>
                    <TableCell className="text-sm tabular">
                      <div>
                        <span className="text-muted-foreground">de</span>{' '}
                        {fmtDate(c.valid_from)}
                      </div>
                      <div>
                        <span className="text-muted-foreground">até</span>{' '}
                        {c.valid_to ? fmtDate(c.valid_to) : '—'}
                      </div>
                    </TableCell>
                    <TableCell>
                      {c.is_active ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-success/12 px-2 py-0.5 text-xs font-medium text-success">
                          <span className="h-1.5 w-1.5 rounded-full bg-success" />
                          Vigente
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                          <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
                          Encerrada
                        </span>
                      )}
                    </TableCell>
                    {onEnd && (
                      <TableCell className="text-right">
                        {c.is_active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onEnd(c)}
                            title="Encerrar vigência"
                          >
                            <CalendarX className="mr-1 h-3.5 w-3.5" /> Encerrar
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {filtered.length > 200 && (
              <div className="border-t bg-muted/30 px-3 py-2 text-center text-xs tabular text-muted-foreground">
                Mostrando 200 de {filtered.length.toLocaleString('pt-BR')}{' '}
                resultados — refine a busca para ver mais.
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
