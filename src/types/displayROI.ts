export interface DisplayROIRow {
  campaign_id: string;
  canal: string;
  date: string;
  investido_brl: number;
  conversions: number;
  receita_brl: number;
  receita_usd: number;
  impressions: number;
  clicks: number;
  lucro_bruto: number;
  roas_pct: number;
  status_roi: string;
}

export interface DisplayROISummary {
  totalInvestido: number;
  totalReceita: number;
  lucroBruto: number;
  roasMedia: number;
  totalImpressoes: number;
  totalClicks: number;
}

export type SortField = keyof Pick<
  DisplayROIRow,
  'canal' | 'investido_brl' | 'receita_brl' | 'lucro_bruto' | 'roas_pct' | 'impressions' | 'clicks' | 'status_roi'
>;

export type SortDirection = 'asc' | 'desc';
