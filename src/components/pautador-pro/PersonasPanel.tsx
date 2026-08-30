import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { User, Users } from 'lucide-react';
import type { Persona } from '@/types/pautador';

const LITERACY_LABEL: Record<string, string> = { high: 'Alto', medium: 'Médio', low: 'Baixo' };

export const PersonasPanel: React.FC<{ personas: Persona[] }> = ({ personas }) => {
  if (!personas?.length) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Users className="h-5 w-5" />
        </span>
        <div className="kicker">Sem personas</div>
        <p className="max-w-xs text-sm text-muted-foreground">
          Dispare uma descoberta para mapear as 8 personas do país.
        </p>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {personas.map((p, i) => (
        <Card key={i} className="reveal hover-lift" style={{ ['--i' as never]: i }}>
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
                <User className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold truncate">{p.name}</p>
                <p className="text-[10px] text-muted-foreground truncate">{p.demographics}</p>
              </div>
            </div>
            {p.core_pain && <p className="text-xs">{p.core_pain}</p>}
            <div className="flex flex-wrap gap-1 text-[10px]">
              <span className="bg-muted rounded-full px-2 py-0.5">Letramento: {LITERACY_LABEL[p.digital_literacy || 'medium']}</span>
              {(p.main_systems || []).slice(0, 2).map((s, j) => (
                <span key={j} className="bg-info/10 text-info rounded-full px-2 py-0.5">{s}</span>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};
