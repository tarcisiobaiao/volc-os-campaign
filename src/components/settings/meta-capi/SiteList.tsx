import React from 'react';
import { Activity, ArrowRight, Globe, MoreVertical, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { MetaCapiSite } from '@/hooks/useMetaCapiSites';

/** "há 3 dias", "agora mesmo" — o operador quer saber se o teste é recente, não a data. */
function relativeTime(iso: string | null): string {
  if (!iso) return 'nunca testado';
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.round(diff / 60000);
  if (min < 1) return 'testado agora mesmo';
  if (min < 60) return `testado há ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `testado há ${h}h`;
  const d = Math.round(h / 24);
  return `testado há ${d} ${d === 1 ? 'dia' : 'dias'}`;
}

function healthOf(site: MetaCapiSite): { variant: 'success' | 'warning' | 'danger'; label: string } {
  const passed = (site.last_check_result as { ok?: boolean } | null)?.ok;
  if (!site.last_check_at) return { variant: 'warning', label: 'aguardando teste' };
  if (passed) return { variant: 'success', label: 'enviando' };
  return { variant: 'danger', label: 'último teste falhou' };
}

interface SiteListProps {
  sites: MetaCapiSite[];
  onCreate: () => void;
  onOpen: (site: MetaCapiSite) => void;
  onRemove: (site: MetaCapiSite) => void;
}

export const SiteList: React.FC<SiteListProps> = ({ sites, onCreate, onOpen, onRemove }) => {
  if (!sites.length) {
    return (
      <Card className="shadow-card border-dashed">
        <CardContent className="py-14 text-center space-y-4">
          <div className="mx-auto h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
            <Activity className="h-6 w-6 text-primary" />
          </div>
          <div className="space-y-1">
            <h3 className="font-semibold">Nenhum site enviando conversões ainda</h3>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              O assistente monta as tags do GTM, o Worker e a configuração da API de Conversões
              para um site seu, e testa a cadeia inteira antes de você sair da tela.
            </p>
          </div>
          <Button onClick={onCreate} className="gap-2">
            <Plus className="h-4 w-4" /> Configurar primeiro site
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {sites.length} {sites.length === 1 ? 'site configurado' : 'sites configurados'}
        </p>
        <Button onClick={onCreate} size="sm" className="gap-2">
          <Plus className="h-4 w-4" /> Novo site
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {sites.map((site) => {
          const health = healthOf(site);
          return (
            <Card key={site.id} className="shadow-card hover:shadow-md transition-shadow">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold truncate">{site.site_name}</h3>
                      {!site.is_active && <Badge variant="outline">pausado</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                      <Globe className="h-3 w-3 shrink-0" />
                      <span className="truncate">{site.domain}</span>
                    </p>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0">
                        <MoreVertical className="h-4 w-4" />
                        <span className="sr-only">Ações do site</span>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => onOpen(site)}>
                        Abrir códigos e testes
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onSelect={() => onRemove(site)}
                        className="text-destructive gap-2"
                      >
                        <Trash2 className="h-3.5 w-3.5" /> Remover
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                <div className="flex items-center gap-2 flex-wrap text-[11px]">
                  <Badge variant={health.variant}>{health.label}</Badge>
                  <span className="text-muted-foreground">{relativeTime(site.last_check_at)}</span>
                </div>

                <div className="flex items-center justify-between gap-2 pt-1 border-t">
                  <div className="text-[11px] text-muted-foreground space-y-0.5 min-w-0">
                    <p className="truncate">Pixel {site.pixel_id}</p>
                    <p className="flex items-center gap-1">
                      <ShieldCheck className="h-3 w-3 text-emerald-600 shrink-0" />
                      token guardado cifrado
                    </p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => onOpen(site)} className="gap-1 shrink-0">
                    Abrir <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
};
