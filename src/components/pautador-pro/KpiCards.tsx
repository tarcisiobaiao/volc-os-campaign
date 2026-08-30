import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Layers, Crown, Medal, Gauge, CheckCircle2 } from 'lucide-react';

interface KpiCardsProps {
  total: number;
  gold: number;
  aTier: number;
  avg: number;
  ready: number;
}

// Stat tiles no idioma VOLC: accent fino no topo, label kicker, número herói
// em font-display tabular, ícone em chip tingido no token do KPI. Cores como
// TOKENS (theme-aware) em vez de hexes frios/quentes misturados.
const kpiConfig = [
  { key: 'total', label: 'Oportunidades', icon: Layers,       accent: 'bg-primary', chip: 'bg-primary/10 text-primary' },
  { key: 'gold',  label: 'Ouro Puro (S)', icon: Crown,        accent: 'bg-warning', chip: 'bg-warning/10 text-warning' },
  { key: 'aTier', label: 'Ouro (A)',      icon: Medal,        accent: 'bg-warning', chip: 'bg-warning/10 text-warning' },
  { key: 'avg',   label: 'Nota média',    icon: Gauge,        accent: 'bg-info',    chip: 'bg-info/10 text-info' },
  { key: 'ready', label: 'Prontos',       icon: CheckCircle2, accent: 'bg-success', chip: 'bg-success/10 text-success' },
] as const;

export const KpiCards: React.FC<KpiCardsProps> = (props) => {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
      {kpiConfig.map((kpi, i) => {
        const Icon = kpi.icon;
        const value = props[kpi.key];
        return (
          <Card
            key={kpi.key}
            className="relative overflow-hidden group reveal hover-lift"
            style={{ ['--i' as never]: i }}
          >
            <span className={`pointer-events-none absolute inset-x-0 top-0 h-0.5 ${kpi.accent}`} />
            <CardContent className="p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="kicker">{kpi.label}</span>
                <span className={`rounded-md p-1.5 ${kpi.chip}`}>
                  <Icon className="h-4 w-4" />
                </span>
              </div>
              <div className="mt-2 font-display text-3xl font-bold tracking-tight tabular">{value}</div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};
