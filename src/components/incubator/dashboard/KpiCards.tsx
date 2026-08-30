import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Globe, Loader2, Clock, CheckCircle, XCircle } from 'lucide-react';

interface KpiCardsProps {
  total: number;
  generating: number;
  submitted: number;
  approved: number;
  rejected: number;
}

const kpiConfig = [
  // Os outros quatro KPIs já usam token semântico no `accent`; só este trazia
  // a aurora, que o contrato proíbe como cor de métrica. `primary` casa com o
  // `chip` que ele já usava e devolve a coerência da fileira.
  { key: 'total',      label: 'Total Sites',       icon: Globe,       accent: 'bg-primary',         chip: 'bg-primary/10 text-primary',         spin: false },
  { key: 'generating', label: 'Gerando Conteúdo',  icon: Loader2,     accent: 'bg-info',            chip: 'bg-info/10 text-info',               spin: true  },
  { key: 'submitted',  label: 'Aguardando AdSense', icon: Clock,      accent: 'bg-warning',         chip: 'bg-warning/10 text-warning',         spin: false },
  { key: 'approved',   label: 'Aprovados',          icon: CheckCircle, accent: 'bg-success',        chip: 'bg-success/10 text-success',         spin: false },
  { key: 'rejected',   label: 'Rejeitados',         icon: XCircle,     accent: 'bg-destructive',    chip: 'bg-destructive/10 text-destructive', spin: false },
] as const;

export const KpiCards: React.FC<KpiCardsProps> = (props) => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {kpiConfig.map((kpi, i) => {
        const Icon = kpi.icon;
        const value = props[kpi.key];
        return (
          <Card
            key={kpi.key}
            className="relative overflow-hidden group reveal hover-lift"
            style={{ ['--i' as any]: i }}
          >
            <span className={`pointer-events-none absolute inset-x-0 top-0 h-0.5 ${kpi.accent}`} />
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-2">
                <span className="kicker">{kpi.label}</span>
                <span className={`rounded-md p-1.5 ${kpi.chip}`}>
                  <Icon className={`h-4 w-4 ${kpi.spin ? 'animate-spin' : ''}`} />
                </span>
              </div>
              <div className="mt-2 font-display text-2xl font-bold tabular tracking-tight">{value}</div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};
