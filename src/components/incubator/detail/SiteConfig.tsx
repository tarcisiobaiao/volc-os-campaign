import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Globe, Settings } from 'lucide-react';
import type { IncubatorSite } from '@/types/incubator';

interface SiteConfigProps {
  site: IncubatorSite;
}

export const SiteConfig: React.FC<SiteConfigProps> = ({ site }) => {
  return (
    <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 0 }}>
      <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="rounded-md bg-info/10 text-info p-1.5"><Settings className="h-4 w-4" /></span>
          Configuração
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="space-y-2">
            <div className="flex items-start gap-2">
              <span className="kicker min-w-[80px] pt-0.5">Nicho</span>
              <span className="font-medium">{site.site_niche}</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="kicker min-w-[80px] pt-0.5">Audiência</span>
              <span className="font-medium">{site.site_audience}</span>
            </div>
            <div className="flex items-center gap-2">
              <Globe className="h-3.5 w-3.5 text-muted-foreground" />
              <a
                href={site.wp_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline truncate"
              >
                {site.wp_url}
              </a>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="kicker">Artigos/lote</span>
              <Badge variant="secondary" className="tabular">{site.articles_per_batch}</Badge>
            </div>
            <div className="flex items-center gap-2">
              <span className="kicker">Auto-publish</span>
              <Badge variant={site.auto_publish ? 'default' : 'secondary'}>
                {site.auto_publish ? 'Sim' : 'Não'}
              </Badge>
            </div>
          </div>
        </div>

        {site.site_context && (
          <div className="pt-3 mt-1">
            <div className="hairline mb-3" />
            <p className="kicker mb-1.5">Contexto do Projeto</p>
            <p className="text-sm">{site.site_context}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
