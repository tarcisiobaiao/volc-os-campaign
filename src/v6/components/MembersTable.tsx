/**
 * v6 RBAC — MembersTable
 *
 * Bloco 3 da página: lista de members enriquecida com user, role e
 * campaign. Tabela read-only. Inclui loading, empty e error states.
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
import { AlertCircle, Users as UsersIcon, Search, Pencil, Trash2 } from 'lucide-react';
import type { CampaignMemberEnriched } from '@/v6/types/v6';

interface MembersTableProps {
  members: CampaignMemberEnriched[];
  isLoading: boolean;
  error: Error | null;
  /** Opcional: se fornecido, mostra botão de editar role na linha. */
  onEdit?: (member: CampaignMemberEnriched) => void;
  /** Opcional: se fornecido, mostra botão de remover na linha. */
  onRemove?: (member: CampaignMemberEnriched) => void;
}

const fmtDate = (iso: string): string => {
  try {
    return new Date(iso).toLocaleDateString('pt-BR');
  } catch {
    return iso;
  }
};

/** Pílula de role tingida (soft), no idioma VOLC. */
const rolePill = (code: string | undefined): string => {
  switch (code) {
    case 'OWNER':
      return 'bg-success/12 text-success';
    case 'OPERATOR':
      return 'bg-primary/12 text-primary';
    case 'REVIEWER':
      return 'bg-info/12 text-info';
    case 'VIEWER':
      return 'bg-muted text-muted-foreground';
    default:
      return 'bg-muted text-muted-foreground';
  }
};

export function MembersTable({ members, isLoading, error, onEdit, onRemove }: MembersTableProps) {
  const showActions = Boolean(onEdit || onRemove);
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return members;
    const q = search.toLowerCase();
    return members.filter((m) => {
      return (
        m.user?.email?.toLowerCase().includes(q) ||
        m.user?.name?.toLowerCase().includes(q) ||
        m.campaign?.campaign_name?.toLowerCase().includes(q) ||
        m.campaign_id.toLowerCase().includes(q) ||
        m.role?.code?.toLowerCase().includes(q)
      );
    });
  }, [members, search]);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 font-display">
              <span className="rounded-md bg-info/10 p-1.5 text-info">
                <UsersIcon className="h-4 w-4" />
              </span>
              Members por campanha
            </CardTitle>
            <CardDescription>
              Vínculo entre usuários e campanhas no novo modelo. Apenas
              acesso — comissão é tabela separada.
            </CardDescription>
          </div>
          <div className="relative w-full max-w-xs">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar por usuário, campanha ou role"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
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
            <span>Erro ao carregar members: {error.message}</span>
          </div>
        )}

        {!isLoading && !error && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed py-12 text-center">
            <span className="rounded-full bg-muted p-3 text-muted-foreground">
              {members.length === 0 ? (
                <UsersIcon className="h-5 w-5" />
              ) : (
                <Search className="h-5 w-5" />
              )}
            </span>
            <div className="kicker">
              {members.length === 0 ? 'Sem members' : 'Sem resultados'}
            </div>
            <p className="max-w-sm text-sm text-muted-foreground">
              {members.length === 0
                ? 'Nenhum member cadastrado em campaign_members.'
                : 'Nenhum member corresponde ao filtro de busca.'}
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
                  <TableHead className="kicker">Role</TableHead>
                  <TableHead className="kicker text-right">Vínculo criado</TableHead>
                  {showActions && <TableHead className="kicker text-right">Ações</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.slice(0, 200).map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>
                      <div className="font-medium">
                        {m.user?.name || '(nome desconhecido)'}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {m.user?.email || m.user_id}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-xs truncate font-medium">
                        {m.campaign?.campaign_name || m.campaign_id}
                      </div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {m.campaign_id}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span
                        className={
                          'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ' +
                          rolePill(m.role?.code)
                        }
                      >
                        {m.role?.label || `role #${m.role_id}`}
                      </span>
                    </TableCell>
                    <TableCell className="text-right text-sm tabular text-muted-foreground">
                      {fmtDate(m.created_at)}
                    </TableCell>
                    {showActions && (
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          {onEdit && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => onEdit(m)}
                              title="Editar role"
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          )}
                          {onRemove && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => onRemove(m)}
                              title="Remover membership"
                              className="text-destructive hover:text-destructive"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
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
