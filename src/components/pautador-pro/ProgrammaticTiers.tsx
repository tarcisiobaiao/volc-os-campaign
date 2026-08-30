// ============================================================================
// PAUTADOR PRO — Benchmarks de PROGRAMÁTICA por tier de mercado do país.
// Mostra volume, valor e eCPM/RPM estimados para display + vídeo, destacando
// o tier do país selecionado. Referência para arbitragem de atenção (a receita
// vem do RevShare/AdSense/programática nas páginas do funil).
//
// ⚠ São FAIXAS de referência de mercado (ordem de grandeza), não cotação em
// tempo real — variam por vertical, formato, sazonalidade e qualidade do tráfego.
// ============================================================================
import React from 'react';
import type { MarketTier } from '@/data/pautadorCountries';
import { TrendingUp, DollarSign, BarChart3, Gauge, Info } from 'lucide-react';

interface TierBenchmark {
  tier: MarketTier;
  label: string;
  accent: string;        // classes tailwind do card
  ecpm_display: string;  // USD
  ecpm_video: string;    // USD
  rpm_page: string;      // USD por 1k pageviews (conteúdo)
  volume: string;
  value: string;
  note: string;
}

const BENCHMARKS: Record<MarketTier, TierBenchmark> = {
  high_value: {
    tier: 'high_value',
    label: 'Alto valor (Tier 1)',
    accent: 'border-success/40 bg-success/10',
    ecpm_display: 'US$ 4 – 15',
    ecpm_video: 'US$ 10 – 30',
    rpm_page: 'US$ 8 – 25',
    volume: 'Médio-alto',
    value: 'Altíssimo — poder de compra elevado; verticais finanças/seguros/jurídico chegam a US$ 20+ de eCPM.',
    note: 'CPM premium compensa o CPC de tráfego mais caro. Ideal para funis de intenção alta (restituição, benefícios, seguros).',
  },
  medium_value: {
    tier: 'medium_value',
    label: 'Valor médio (Tier 2)',
    accent: 'border-warning/40 bg-warning/10',
    ecpm_display: 'US$ 1 – 4',
    ecpm_video: 'US$ 3 – 10',
    rpm_page: 'US$ 1.5 – 6',
    volume: 'Alto',
    value: 'Médio — bom equilíbrio entre custo de aquisição e receita programática. LatAm premium, Leste Europeu.',
    note: 'A margem sai do volume qualificado + CPC de aquisição baixo. Escale keywords com intenção clara.',
  },
  volume_play: {
    tier: 'volume_play',
    label: 'Jogo de volume (Tier 3)',
    accent: 'border-info/40 bg-info/10',
    ecpm_display: 'US$ 0.10 – 1',
    ecpm_video: 'US$ 0.50 – 2.5',
    rpm_page: 'US$ 0.20 – 1.5',
    volume: 'Muito alto',
    value: 'Baixo por usuário — o volume massivo de tráfego compensa o eCPM baixo.',
    note: 'Estratégia: escala e custo de aquisição mínimo. Só fecha a conta com CPC de tráfego muito baixo.',
  },
};

const Metric: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({ icon, label, value }) => (
  <div className="flex items-start gap-2">
    <span className="mt-0.5 text-muted-foreground">{icon}</span>
    <div>
      <p className="kicker">{label}</p>
      <p className="text-sm font-semibold tabular">{value}</p>
    </div>
  </div>
);

interface Props {
  countryName: string;
  countryTier?: MarketTier | null;
  currency?: string | null;
}

export const ProgrammaticTiers: React.FC<Props> = ({ countryName, countryTier, currency }) => {
  const order: MarketTier[] = ['high_value', 'medium_value', 'volume_play'];
  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-4 shadow-card">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-primary/10 text-primary p-1.5"><BarChart3 className="h-4 w-4" /></span>
          <span className="kicker">Programática · volume, valor e eCPM por tier</span>
        </div>
        {countryTier && (
          <span className="text-[11px] rounded-full border border-primary/30 bg-primary/5 px-2.5 py-0.5 text-primary">
            {countryName}: {BENCHMARKS[countryTier].label}{currency ? ` · ${currency}` : ''}
          </span>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
        {order.map((t, idx) => {
          const b = BENCHMARKS[t];
          const active = countryTier === t;
          return (
            <div
              key={t}
              className={`rounded-lg border p-3 space-y-3 reveal hover-lift ${active ? `${b.accent} ring-2 ring-primary/40` : 'border-border bg-muted/20'}`}
              style={{ ['--i' as never]: idx }}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-bold">{b.label}</p>
                {active && <span className="kicker text-primary">país atual</span>}
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <Metric icon={<DollarSign className="h-3.5 w-3.5" />} label="eCPM display" value={b.ecpm_display} />
                <Metric icon={<DollarSign className="h-3.5 w-3.5" />} label="eCPM vídeo" value={b.ecpm_video} />
                <Metric icon={<Gauge className="h-3.5 w-3.5" />} label="RPM página" value={b.rpm_page} />
                <Metric icon={<TrendingUp className="h-3.5 w-3.5" />} label="Volume" value={b.volume} />
              </div>
              <div>
                <p className="kicker">Valor</p>
                <p className="text-[11px]">{b.value}</p>
              </div>
              <p className="text-[10px] text-muted-foreground border-t border-border pt-1.5">{b.note}</p>
            </div>
          );
        })}
      </div>

      <p className="flex items-start gap-1.5 text-[10px] text-muted-foreground">
        <Info className="h-3 w-3 shrink-0 mt-0.5" />
        Faixas de referência de mercado (USD, ordem de grandeza) para display/vídeo programático. Variam por vertical,
        formato, sazonalidade e qualidade do tráfego — use como bússola, não como cotação.
      </p>
    </div>
  );
};
