import React from 'react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type RedeDeCampanhas = 'google' | 'meta';

interface Props {
  rede: RedeDeCampanhas;
  onChange: (rede: RedeDeCampanhas) => void;
  className?: string;
}

export const SeletorRedeCampanhas: React.FC<Props> = ({ rede, onChange, className }) => (
  <div className={cn('inline-flex rounded-md border border-border bg-muted p-1', className)} aria-label="Rede de anúncios">
    <Button
      type="button"
      size="sm"
      variant="ghost"
      aria-pressed={rede === 'google'}
      className={cn('min-h-9 rounded-sm', rede === 'google' && 'bg-card text-foreground shadow-card')}
      onClick={() => onChange('google')}
    >
      Google Ads
    </Button>
    <Button
      type="button"
      size="sm"
      variant="ghost"
      aria-pressed={rede === 'meta'}
      className={cn('min-h-9 rounded-sm', rede === 'meta' && 'bg-card text-foreground shadow-card')}
      onClick={() => onChange('meta')}
    >
      Meta Ads
    </Button>
  </div>
);

export default SeletorRedeCampanhas;
