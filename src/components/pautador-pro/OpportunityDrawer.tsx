import React, { useEffect, useState } from 'react';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, Pickaxe, Workflow, Check, X, ExternalLink, AlertTriangle, Target } from 'lucide-react';
import { TierBadge } from '@/components/pautador-pro/TierBadge';
import { pautadorService } from '@/services/pautadorService';
import {
  CATEGORY_LABELS, COMPETITION_LABELS, INTENT_LABELS, QUAL_LABELS, STATUS_LABELS, TIMING_LABELS,
} from '@/types/pautador';
import type {
  FunnelPage, FunnelResult, KeywordCluster, MineResult, Opportunity, OpportunityStatus,
} from '@/types/pautador';

interface OpportunityDrawerProps {
  opportunity: Opportunity | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cluster?: KeywordCluster | null;
  funnelPages?: FunnelPage[] | null;
  mineResult?: MineResult | null;
  funnelResult?: FunnelResult | null;
  busy?: boolean;
  onMove: (opp: Opportunity, status: OpportunityStatus) => void;
  onMine: (opp: Opportunity) => void;
  onFunnel: (opp: Opportunity) => void;
}

const fmtNum = (n?: number | null) =>
  typeof n === 'number' ? n.toLocaleString('pt-BR') : '—';

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <p className="kicker">{label}</p>
    <p className="text-sm font-medium">{children}</p>
  </div>
);

export const OpportunityDrawer: React.FC<OpportunityDrawerProps> = ({
  opportunity, open, onOpenChange, cluster, funnelPages, mineResult, funnelResult, busy, onMove, onMine, onFunnel,
}) => {
  const [dbCluster, setDbCluster] = useState<KeywordCluster | null>(null);
  const [dbFunnel, setDbFunnel] = useState<FunnelPage[]>([]);

  useEffect(() => {
    let cancelled = false;
    if (open && opportunity?.id && !opportunity._ephemeral) {
      pautadorService.fetchClusters(opportunity.id).then((cs) => !cancelled && setDbCluster(cs[0] || null)).catch(() => {});
      pautadorService.fetchFunnelPages(opportunity.id).then((ps) => !cancelled && setDbFunnel(ps)).catch(() => {});
    } else {
      setDbCluster(null);
      setDbFunnel([]);
    }
    return () => { cancelled = true; };
  }, [open, opportunity?.id, opportunity?._ephemeral]);

  if (!opportunity) return null;

  const effectiveCluster = cluster || dbCluster;
  const clusterKeywords = effectiveCluster?.keywords ?? [];
  const richFunnelPages = funnelResult?.funnel?.pages;
  const effectiveFunnel =
    (funnelPages && funnelPages.length ? funnelPages : richFunnelPages && richFunnelPages.length ? richFunnelPages : dbFunnel) || [];
  const ads = mineResult?.production_ads_queue ?? [];
  const seo = mineResult?.content_seo_queue ?? [];
  const funis = mineResult?.funis_sugeridos ?? [];
  const hasRichMine = ads.length > 0 || seo.length > 0 || funis.length > 0;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader className="space-y-2">
          <div className="flex items-center gap-2">
            <TierBadge tier={opportunity.tier} showLabel />
            <span className="text-xs text-muted-foreground">
              {opportunity.category} · {CATEGORY_LABELS[opportunity.category]}
            </span>
            {opportunity._ephemeral && (
              <span className="text-[10px] text-warning border border-warning/30 bg-warning/10 rounded-full px-1.5 py-0.5">demo</span>
            )}
          </div>
          <SheetTitle className="text-base leading-snug">{opportunity.keyword}</SheetTitle>
          <SheetDescription className="text-xs">
            {opportunity.keyword_pt_translation || opportunity.main_keyword} · {opportunity.country}
          </SheetDescription>
        </SheetHeader>

        {/* Score banner */}
        <div className="mt-4 flex items-center justify-between rounded-lg border border-warning/30 bg-warning/10 p-3">
          <div>
            <p className="kicker">Nota de arbitragem</p>
            <p className="font-display text-3xl font-bold text-warning tabular">{opportunity.arbitrage_score ?? '—'}</p>
          </div>
          <div className="text-right text-xs text-muted-foreground">
            <p>Status: <span className="font-medium text-foreground">{STATUS_LABELS[opportunity.status]}</span></p>
            {opportunity.estimated_roi_signal != null && <p>Sinal ROI: {opportunity.estimated_roi_signal}</p>}
            {opportunity.cpc_estimate_local && <p>CPC: {opportunity.cpc_estimate_local}</p>}
          </div>
        </div>

        {/* Actions */}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => onMove(opportunity, 'validating')}>
            <Check className="h-3.5 w-3.5 mr-1" /> Validar
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onMine(opportunity)}>
            {busy ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Pickaxe className="h-3.5 w-3.5 mr-1" />} Minerar
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onFunnel(opportunity)}>
            {busy ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Workflow className="h-3.5 w-3.5 mr-1" />} Funil
          </Button>
          <Button size="sm" variant="outline" onClick={() => onMove(opportunity, 'ready')}>Pronto</Button>
          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => onMove(opportunity, 'rejected')}>
            <X className="h-3.5 w-3.5 mr-1" /> Rejeitar
          </Button>
        </div>

        <Separator className="my-4" />

        <Tabs defaultValue="detalhe">
          <TabsList>
            <TabsTrigger value="detalhe">Detalhe</TabsTrigger>
            <TabsTrigger value="keywords">
              Keywords {hasRichMine ? `(${ads.length + seo.length})` : effectiveCluster ? `(${clusterKeywords.length})` : ''}
            </TabsTrigger>
            <TabsTrigger value="funil">Funil {effectiveFunnel.length ? `(${effectiveFunnel.length})` : ''}</TabsTrigger>
          </TabsList>

          <TabsContent value="detalhe" className="mt-4 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Núcleo da dor">{opportunity.main_keyword}</Field>
              <Field label="Persona">{opportunity.persona || '—'}</Field>
              <Field label="Volume">{opportunity.volume_estimate ? QUAL_LABELS[opportunity.volume_estimate] : '—'}</Field>
              <Field label="RPM">{opportunity.rpm_potential ? QUAL_LABELS[opportunity.rpm_potential] : '—'}</Field>
              <Field label="Concorrência">{opportunity.competition_estimate ? COMPETITION_LABELS[opportunity.competition_estimate] : '—'}</Field>
              <Field label="Confiança">{opportunity.confidence ? QUAL_LABELS[opportunity.confidence] : '—'}</Field>
              <Field label="Intenção">{opportunity.intent ? INTENT_LABELS[opportunity.intent] : '—'}</Field>
              <Field label="Janela temporal">{opportunity.timing ? TIMING_LABELS[opportunity.timing] : '—'}</Field>
            </div>

            {opportunity.pain_point && (
              <div>
                <p className="kicker">Dor concreta</p>
                <p className="text-sm">{opportunity.pain_point}</p>
              </div>
            )}
            {opportunity.reasoning && (
              <div>
                <p className="kicker">Razão de ser ouro</p>
                <p className="text-sm">{opportunity.reasoning}</p>
              </div>
            )}
            {!!opportunity.variations?.length && (
              <div>
                <p className="kicker mb-1">Variações</p>
                <div className="flex flex-wrap gap-1">
                  {opportunity.variations.map((v, i) => (
                    <span key={i} className="text-[11px] bg-muted rounded px-1.5 py-0.5">{v}</span>
                  ))}
                </div>
              </div>
            )}
            {!!opportunity.expansion_hooks?.length && (
              <div>
                <p className="kicker mb-1">Ganchos de conteúdo</p>
                <ul className="list-disc list-inside text-sm space-y-0.5">
                  {opportunity.expansion_hooks.map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              </div>
            )}
          </TabsContent>

          <TabsContent value="keywords" className="mt-4">
            {hasRichMine ? (
              <div className="space-y-4">
                {/* services / engine badges */}
                {!!mineResult?.services_used?.length && (
                  <div className="flex flex-wrap gap-1">
                    {mineResult.services_used.map((s, i) => (
                      <span
                        key={i}
                        className={`text-[10px] rounded-full px-2 py-0.5 border ${
                          s.endsWith(':live') ? 'border-success/30 bg-success/10 text-success' : 'border-border bg-muted text-muted-foreground'
                        }`}
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                )}
                {!!mineResult?.warnings?.length && (
                  <div className="rounded-lg border border-warning/30 bg-warning/10 p-2 text-[11px] text-warning space-y-0.5">
                    {mineResult.warnings.map((w, i) => (
                      <p key={i} className="flex items-start gap-1.5">
                        <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" /> <span>{w}</span>
                      </p>
                    ))}
                  </div>
                )}

                {/* ADS queue */}
                {ads.length > 0 && (
                  <div>
                    <p className="kicker mb-1">Fila de ADS ({ads.length})</p>
                    <div className="rounded-lg border divide-y max-h-64 overflow-y-auto">
                      {ads.slice(0, 30).map((k, i) => (
                        <div key={i} className="flex items-center justify-between p-2 text-xs gap-2">
                          <span className="truncate flex-1">{k.keyword}</span>
                          <span className="text-muted-foreground shrink-0 tabular-nums">
                            vol {fmtNum(k.volume)} · CPC {typeof k.cpc === 'number' ? k.cpc.toFixed(2) : '—'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Content/SEO queue */}
                {seo.length > 0 && (
                  <div>
                    <p className="kicker mb-1">Conteúdo / SEO ({seo.length})</p>
                    <div className="flex flex-wrap gap-1">
                      {seo.slice(0, 20).map((k, i) => (
                        <span key={i} className="text-[11px] bg-muted rounded px-1.5 py-0.5">{k.keyword}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Funis sugeridos */}
                {funis.length > 0 && (
                  <div>
                    <p className="kicker mb-1">Funis sugeridos ({funis.length})</p>
                    <div className="space-y-1">
                      {funis.map((f, i) => (
                        <div key={i} className="rounded border p-2 text-xs">
                          <p className="font-medium">{f.rank ? `#${f.rank} ` : ''}{f.nome_funil}</p>
                          <p className="text-muted-foreground">
                            âncora: {f.keyword_ancora} · vol agregado {fmtNum(f.metricas?.volume_agregado)} · {f.sub_intencoes?.length ?? 0} sub-intenções
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : effectiveCluster ? (
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground">
                  {effectiveCluster.cluster_name}
                  {effectiveCluster.avg_cpc_local != null && ` · CPC médio ${effectiveCluster.avg_cpc_local} ${effectiveCluster.currency || ''}`}
                </p>
                <div className="rounded-lg border divide-y">
                  {clusterKeywords.map((k, i) => (
                    <div key={i} className="flex items-center justify-between p-2 text-xs">
                      <span className="truncate flex-1">{k.keyword}</span>
                      <span className="text-muted-foreground ml-2 shrink-0">
                        {k.volume ? QUAL_LABELS[k.volume] : '—'} · {k.cpc_local || '—'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-muted-foreground">
                Sem cluster. Clique em <b>Minerar</b> para gerar a árvore de keywords.
              </div>
            )}
          </TabsContent>

          <TabsContent value="funil" className="mt-4">
            {effectiveFunnel.length ? (
              <div className="space-y-3">
                {funnelResult?.funnel_strategy && (
                  <div className="rounded-lg border bg-muted/40 p-3 text-xs space-y-1">
                    {!!(funnelResult.funnel_strategy as Record<string, unknown>).avatar_summary && (
                      <p><span className="font-medium">Avatar:</span> {String((funnelResult.funnel_strategy as Record<string, unknown>).avatar_summary)}</p>
                    )}
                    {!!(funnelResult.funnel_strategy as Record<string, unknown>).tone_voice && (
                      <p><span className="font-medium">Tom:</span> {String((funnelResult.funnel_strategy as Record<string, unknown>).tone_voice)}</p>
                    )}
                    <div className="flex flex-wrap gap-1 pt-1">
                      {(funnelResult.writing_jobs?.length ?? 0) > 0 && (
                        <span className="text-[10px] rounded-full px-2 py-0.5 border border-info/30 bg-info/10 text-info">
                          {funnelResult.writing_jobs.length} briefings de redação
                        </span>
                      )}
                      {(funnelResult.services_used || []).map((s, i) => (
                        <span key={i} className={`text-[10px] rounded-full px-2 py-0.5 border ${s.startsWith('gemini') ? 'border-success/30 bg-success/10 text-success' : 'border-border bg-muted text-muted-foreground'}`}>{s}</span>
                      ))}
                    </div>
                  </div>
                )}
                {effectiveFunnel.map((p) => (
                  <div key={p.position} className="rounded-lg border border-border p-3 hover-lift">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">Pág. {p.position} · {p.page_title}</p>
                      <span className="kicker rounded-full bg-muted px-2 py-0.5">{p.stage}</span>
                    </div>
                    {p.avatar && <p className="text-xs text-muted-foreground mt-1">Avatar: {p.avatar}</p>}
                    {p.emotional_goal && (
                      <p className="text-xs mt-1 flex items-start gap-1.5">
                        <Target className="h-3 w-3 shrink-0 mt-0.5 text-primary" /> <span>{p.emotional_goal}</span>
                      </p>
                    )}
                    {!!p.subtitles?.length && (
                      <ul className="list-disc list-inside text-xs mt-2 space-y-0.5">
                        {p.subtitles.map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    )}
                    {!!p.internal_links?.length && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {p.internal_links.map((l, i) => (
                          <span key={i} className="inline-flex items-center gap-0.5 text-[10px] text-info">
                            <ExternalLink className="h-2.5 w-2.5" />{l}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-muted-foreground">
                Sem funil. Clique em <b>Funil</b> para gerar as 5 páginas.
              </div>
            )}
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
};
