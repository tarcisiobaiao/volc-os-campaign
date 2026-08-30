import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Building2, HandCoins, HeartCrack, CalendarClock, Smartphone, Lightbulb, Eye, Compass, AlertTriangle, Globe2 } from 'lucide-react';
import type { CulturalIntelligence, Insights } from '@/types/pautador';

interface IntelligencePanelProps {
  cultural: CulturalIntelligence | null;
  insights: Insights | null;
}

const ListCard: React.FC<{ title: string; icon: React.ElementType; items: string[]; i?: number }> = ({ title, icon: Icon, items, i = 0 }) => (
  <Card className="reveal hover-lift" style={{ ['--i' as never]: i }}>
    <CardHeader className="pb-2">
      <CardTitle className="flex items-center gap-2">
        <span className="rounded-md bg-primary/10 text-primary p-1.5"><Icon className="h-4 w-4" /></span>
        <span className="kicker">{title}</span>
      </CardTitle>
    </CardHeader>
    <CardContent>
      {items?.length ? (
        <ul className="space-y-1 text-sm">
          {items.map((it, idx) => (
            <li key={idx} className="flex gap-2"><span className="text-primary/60">•</span><span>{it}</span></li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">—</p>
      )}
    </CardContent>
  </Card>
);

const InsightRow: React.FC<{ title: string; icon: React.ElementType; text: string; tone?: 'primary' | 'warning' }> = ({ title, icon: Icon, text, tone = 'primary' }) =>
  text ? (
    <div className="flex gap-3">
      <span className={`shrink-0 rounded-md p-1.5 ${tone === 'warning' ? 'bg-warning/10 text-warning' : 'bg-primary/10 text-primary'}`}>
        <Icon className="h-4 w-4" />
      </span>
      <div>
        <p className="kicker mb-0.5">{title}</p>
        <p className="text-sm text-muted-foreground">{text}</p>
      </div>
    </div>
  ) : null;

export const IntelligencePanel: React.FC<IntelligencePanelProps> = ({ cultural, insights }) => {
  if (!cultural && !insights) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Globe2 className="h-5 w-5" />
        </span>
        <div className="kicker">Sem inteligência cultural</div>
        <p className="max-w-xs text-sm text-muted-foreground">
          Dispare uma descoberta para ver a inteligência cultural do país.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-6">
      {cultural && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <ListCard title="Órgãos e portais" icon={Building2} items={cultural.key_institutions} i={0} />
          <ListCard title="Programas e benefícios" icon={HandCoins} items={cultural.main_benefits_programs} i={1} />
          <ListCard title="Dores culturais únicas" icon={HeartCrack} items={cultural.unique_cultural_pains} i={2} />
          <ListCard title="Eventos e mudanças" icon={CalendarClock} items={cultural.upcoming_events} i={3} />
          <ListCard title="Atrito digital (apps)" icon={Smartphone} items={cultural.digital_friction_apps} i={4} />
        </div>
      )}
      {insights && (
        <Card className="relative overflow-hidden reveal" style={{ ['--i' as never]: 5 }}>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <span className="kicker">Insights estratégicos</span>
              <span className="hairline-aurora flex-1" />
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <InsightRow title="Observação de mercado" icon={Eye} text={insights.market_observation} />
            <InsightRow title="Ângulo subexplorado" icon={Lightbulb} text={insights.untapped_angle} />
            <InsightRow title="Aprofundamento recomendado" icon={Compass} text={insights.recommended_deep_dive} />
            <InsightRow title="Aviso cultural" icon={AlertTriangle} text={insights.cultural_warning} tone="warning" />
          </CardContent>
        </Card>
      )}
    </div>
  );
};
