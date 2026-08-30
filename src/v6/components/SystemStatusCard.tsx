/**
 * v6 RBAC — SystemStatusCard
 *
 * Bloco 7: status técnico do que está ligado, do que está sendo
 * mostrado e quem é o admin logado. Útil pra debugging e como
 * lembrete visual de que estamos em "modo paralelo".
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Settings2 } from 'lucide-react';

interface SystemStatusCardProps {
  flagEnabled: boolean;
  userEmail: string | null | undefined;
  userRole: string | null | undefined;
  userName: string | null | undefined;
}

export function SystemStatusCard({
  flagEnabled,
  userEmail,
  userRole,
  userName,
}: SystemStatusCardProps) {
  const rows: { label: string; value: React.ReactNode }[] = [
    {
      label: 'Feature flag',
      value: flagEnabled ? (
        <Badge variant="success">VITE_USE_V6_ADMIN = true</Badge>
      ) : (
        <Badge variant="warning">desligada</Badge>
      ),
    },
    {
      label: 'Modo de operação',
      value: <Badge variant="secondary">read-only</Badge>,
    },
    {
      label: 'Mutações',
      value: <Badge variant="outline">não disponíveis (Etapa 3.C)</Badge>,
    },
    {
      label: 'Cutover do legado',
      value: <Badge variant="outline">não realizado</Badge>,
    },
    {
      label: 'Usuário atual',
      value: (
        <span className="text-sm">
          {userName || '—'}{' '}
          <span className="text-muted-foreground">
            ({userEmail || 'sem email'})
          </span>
        </span>
      ),
    },
    {
      label: 'Role global',
      value: userRole ? (
        <Badge variant={userRole === 'ADMIN' ? 'success' : 'secondary'}>
          {userRole}
        </Badge>
      ) : (
        <Badge variant="outline">desconhecido</Badge>
      ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-display text-base">
          <span className="rounded-md bg-primary/10 p-1.5 text-primary">
            <Settings2 className="h-4 w-4" />
          </span>
          Status técnico
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-1 gap-y-3 sm:grid-cols-2 sm:gap-x-8">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex items-center justify-between gap-3 border-b border-dashed pb-2 sm:border-b-0 sm:pb-0"
            >
              <dt className="text-sm text-muted-foreground">{row.label}</dt>
              <dd className="text-right">{row.value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
