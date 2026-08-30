import React from 'react';
import { cn } from '@/lib/utils';
import { TIER_META } from '@/types/pautador';
import type { Tier } from '@/types/pautador';

interface TierBadgeProps {
  tier: Tier;
  className?: string;
  showLabel?: boolean;
}

export const TierBadge: React.FC<TierBadgeProps> = ({ tier, className, showLabel = false }) => {
  // Fallback prevents a white-screen crash if data carries an unexpected tier
  // (runtime data from the API/Supabase is only TS-typed, not validated).
  const meta = TIER_META[tier] ?? TIER_META.B;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold',
        meta.bg,
        meta.text,
        meta.border,
        className,
      )}
      title={meta.label}
    >
      {meta.short}
      {showLabel && <span className="font-normal">· {meta.label}</span>}
    </span>
  );
};
