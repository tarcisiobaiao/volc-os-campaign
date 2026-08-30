import React from 'react';
import { cn } from '@/lib/utils';
import { STATUS_COLORS, STATUS_LABELS, ARTICLE_STATUS_COLORS, ARTICLE_STATUS_LABELS } from '@/types/incubator';
import type { SiteStatus, ArticleStatus } from '@/types/incubator';

interface SiteStatusBadgeProps {
  status: SiteStatus;
  size?: 'sm' | 'md';
}

export const SiteStatusBadge: React.FC<SiteStatusBadgeProps> = ({ status, size = 'md' }) => {
  const colors = STATUS_COLORS[status];
  const label = STATUS_LABELS[status];

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        colors.bg,
        colors.text,
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs'
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', colors.dot)} />
      {label}
    </span>
  );
};

interface ArticleStatusBadgeProps {
  status: ArticleStatus;
}

export const ArticleStatusBadge: React.FC<ArticleStatusBadgeProps> = ({ status }) => {
  const colors = ARTICLE_STATUS_COLORS[status];
  const label = ARTICLE_STATUS_LABELS[status];

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
        colors.bg,
        colors.text,
      )}
    >
      {label}
    </span>
  );
};
