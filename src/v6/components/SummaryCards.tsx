/**
 * v6 RBAC — SummaryCards
 *
 * Bloco 2 da página: KPIs do sistema novo. Mostra também o "gap"
 * vs o legado (sum_amount_v6 - sum_commission_legacy), que sabemos
 * que será praticamente igual ao próprio sum_amount_v6 enquanto o
 * bug do trigger legado não for corrigido.
 */
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Users as UsersIcon,
  Receipt,
  Calculator,
  Megaphone,
  Banknote,
  AlertTriangle,
} from 'lucide-react';
import type { MembersCountByRole, SummaryStats } from '@/v6/types/v6';

const fmtBRL = (value: number): string =>
  new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);

const fmtInt = (value: number): string =>
  new Intl.NumberFormat('pt-BR').format(value);

interface SummaryCardsProps {
  summary: SummaryStats | null;
  membersCount: number;
  activeCommissionsCount: number;
  countByRole: MembersCountByRole[];
  isLoading: boolean;
}

/** Acentos VOLC estáticos (Tailwind precisa das classes literais). */
const ACCENTS = {
  primary: { bar: 'bg-primary', chip: 'bg-primary/10 text-primary', value: '' },
  info: { bar: 'bg-info', chip: 'bg-info/10 text-info', value: '' },
  success: { bar: 'bg-success', chip: 'bg-success/10 text-success', value: 'text-success' },
  warning: { bar: 'bg-warning', chip: 'bg-warning/10 text-warning', value: 'text-warning' },
} as const;

type AccentKey = keyof typeof ACCENTS;

export function SummaryCards({
  summary,
  membersCount,
  activeCommissionsCount,
  countByRole,
  isLoading,
}: SummaryCardsProps) {
  const cards: Array<{
    title: string;
    icon: typeof UsersIcon;
    value: string;
    caption: string;
    accent: AccentKey;
    warning?: boolean;
  }> = [
    {
      title: 'Membros (acesso)',
      icon: UsersIcon,
      accent: 'info',
      value: isLoading ? '—' : fmtInt(membersCount),
      caption: isLoading
        ? 'Carregando…'
        : countByRole
            .filter((r) => r.total > 0)
            .map((r) => `${r.role_label}: ${r.total}`)
            .join(' · ') || 'Nenhum role atribuído',
    },
    {
      title: 'Comissões vigentes',
      icon: Receipt,
      accent: 'primary',
      value: isLoading ? '—' : fmtInt(activeCommissionsCount),
      caption: 'Linhas em campaign_commissions com valid_to NULL',
    },
    {
      title: 'Linhas de payout',
      icon: Calculator,
      accent: 'info',
      value: isLoading || !summary ? '—' : fmtInt(summary.total_payouts),
      caption: !summary
        ? '—'
        : `${fmtInt(summary.total_payouts_with_commission)} com comissão > 0`,
    },
    {
      title: 'Campanhas com payout',
      icon: Megaphone,
      accent: 'primary',
      value: isLoading || !summary ? '—' : fmtInt(summary.distinct_campaigns),
      caption: !summary
        ? '—'
        : `${fmtInt(summary.distinct_users)} ${
            summary.distinct_users === 1 ? 'usuário' : 'usuários'
          } envolvidos`,
    },
    {
      title: 'Comissão v6 (total)',
      icon: Banknote,
      accent: 'success',
      value: isLoading || !summary ? '—' : fmtBRL(summary.sum_amount),
      caption: !summary
        ? '—'
        : summary.date_min && summary.date_max
        ? `Cobertura: ${summary.date_min} → ${summary.date_max}`
        : 'Sem dados de cobertura',
    },
    {
      title: 'Gap vs legado',
      icon: AlertTriangle,
      accent: 'warning',
      value: isLoading || !summary ? '—' : fmtBRL(summary.sum_amount),
      caption:
        'Legado paga 0 (bug do trigger). Gap = comissão v6 calculada que o legado deixou de registrar.',
      warning: true,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((card, i) => {
        const Icon = card.icon;
        const accent = ACCENTS[card.accent];
        return (
          <Card
            key={card.title}
            className="reveal hover-lift group relative overflow-hidden"
            style={{ ['--i' as any]: i + 1 }}
          >
            <span className={'pointer-events-none absolute inset-x-0 top-0 h-0.5 ' + accent.bar} />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">{card.title}</span>
              <span className={'rounded-md p-1.5 ' + accent.chip}>
                <Icon className="h-4 w-4" />
              </span>
            </CardHeader>
            <CardContent>
              <div
                className={
                  'font-display text-2xl font-bold tabular tracking-tight ' + accent.value
                }
              >
                {card.value}
              </div>
              <CardDescription className="mt-1 text-xs leading-snug">
                {card.caption}
              </CardDescription>
              {card.warning && !isLoading && (
                <Badge variant="warning" className="mt-2">
                  Bug legado conhecido
                </Badge>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
