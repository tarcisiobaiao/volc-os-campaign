import React from 'react';
import { Rocket } from 'lucide-react';
import { SiteCard } from './SiteCard';
import type { IncubatorSite } from '@/types/incubator';

interface SiteGridProps {
  sites: IncubatorSite[];
  onView: (site: IncubatorSite) => void;
  onTrigger: (site: IncubatorSite) => void;
  onPause: (site: IncubatorSite) => void;
}

export const SiteGrid: React.FC<SiteGridProps> = ({ sites, onView, onTrigger, onPause }) => {
  if (sites.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center reveal">
        <span className="h-14 w-14 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-4">
          <Rocket className="h-7 w-7" />
        </span>
        <div className="kicker mb-1">Incubadora vazia</div>
        <h3 className="font-display text-lg font-semibold tracking-tight">Nenhum site na incubadora</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Clique em "Novo Site" para adicionar o primeiro.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {sites.map((site, i) => (
        <SiteCard
          key={site.id}
          site={site}
          index={i}
          onView={onView}
          onTrigger={onTrigger}
          onPause={onPause}
        />
      ))}
    </div>
  );
};
