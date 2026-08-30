import React, { useEffect, useState } from 'react';
import { pautadorService } from '@/services/pautadorService';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, Pickaxe, Workflow, Check, X, Landmark, RotateCw, Trash2, Lightbulb, Save, Target, KeyRound, ExternalLink, ClipboardList } from 'lucide-react';
import { TierBadge } from '@/components/pautador-pro/TierBadge';
import { STATUS_LABELS } from '@/types/pautador';
import type { OpportunityStatus, Tier } from '@/types/pautador';
import { entitySubtitle, funnelRoleLabel, funnelSummary, funnelTitle } from '@/types/pautadorEntity';
import type { EntityCard, EntityFunnelResponse, EntityMineResponse } from '@/types/pautadorEntity';
import { BriefingAcoes } from './BriefingAcoes';
import { ValidacaoPainel } from './ValidacaoPainel';
import type { EixoEmProgresso } from '@/types/pautadorValidacao';

interface EntityDrawerProps {
  card: EntityCard | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mineResult?: EntityMineResponse | null;
  funnelResult?: EntityFunnelResponse | null;
  busy?: boolean;
  onMove: (c: EntityCard, status: OpportunityStatus) => void;
  onMine: (c: EntityCard) => void;
  onFunnel: (c: EntityCard) => void;
  onValidate: (c: EntityCard) => void;
  onRerun: (c: EntityCard) => void;
  onDelete: (c: EntityCard) => void;
  onSaveInsights: (c: EntityCard, text: string) => Promise<boolean> | void;
  /** Descrição da tarefa -> corpo da task no ClickUp (≠ insights). */
  onSaveTaskDescription?: (c: EntityCard, text: string) => Promise<boolean> | void;
  /** Renomeia só o CARD (diferencia cópias da mesma entidade). */
  onSaveDisplayTitle?: (c: EntityCard, text: string) => Promise<boolean> | void;
}

const VALID_TIERS: Tier[] = ['S', 'A', 'B', 'EXPERIMENTAL'];

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <p className="kicker">{label}</p>
    <p className="text-sm font-medium">{children}</p>
  </div>
);

const sev = (s?: string | null) => {
  const m: Record<string, string> = { high: 'text-destructive', medium: 'text-warning', low: 'text-muted-foreground' };
  return m[(s || '').toLowerCase()] || 'text-muted-foreground';
};

type ClusterRow = { production_ads_queue?: Array<{ keyword: string; volume?: number; cpc?: number; competition?: string }>; keywords?: Array<{ keyword: string }>; currency?: string | null };

export const EntityDrawer: React.FC<EntityDrawerProps & {
  onMedir?: (card: EntityCard) => void;
  medindo?: Set<string>;
  progresso?: Record<string, EixoEmProgresso[]>;
}> = ({
  card, open, onOpenChange, mineResult, funnelResult, busy, onMove, onMine, onFunnel, onValidate,
  onRerun, onDelete, onSaveInsights, onSaveTaskDescription, onSaveDisplayTitle,
  onMedir, medindo, progresso,
}) => {
  // keywords mineradas (n8n ou interno) vivem em pautador_keyword_clusters
  const [cluster, setCluster] = useState<ClusterRow | null>(null);
  // texto livre da aba Insights (sincroniza com o card ao abrir/trocar)
  const [insightsText, setInsightsText] = useState('');
  const [savingInsights, setSavingInsights] = useState(false);
  // descrição da tarefa: o texto que a PESSOA lê no ClickUp
  const [taskDescText, setTaskDescText] = useState('');
  const [savingTaskDesc, setSavingTaskDesc] = useState(false);
  // nome de exibição do CARD (não da entidade) — diferencia cópias por site
  const [titleText, setTitleText] = useState('');
  const [savingTitle, setSavingTitle] = useState(false);
  useEffect(() => {
    let cancelled = false;
    if (open && card?.id && !card?.ephemeral) {
      pautadorService.fetchClusters(card.id)
        .then((cs) => { if (!cancelled) setCluster((cs[0] as unknown as ClusterRow) || null); })
        .catch(() => {});
    } else {
      setCluster(null);
    }
    return () => { cancelled = true; };
  }, [open, card?.id, card?.ephemeral]);
  useEffect(() => { setInsightsText(card?.insights || ''); }, [card?.id, card?.insights]);
  useEffect(() => { setTaskDescText(card?.task_description || ''); }, [card?.id, card?.task_description]);
  useEffect(() => { setTitleText(card?.display_title || ''); }, [card?.id, card?.display_title]);

  if (!card) return null;
  const canRerun = card.status === 'mining' || card.status === 'funnel';
  const isRejected = card.status === 'rejected';
  const handleDelete = () => {
    if (window.confirm(`Excluir "${card.entity.canonical_name}"? Esta ação remove o card e seus dados. Não pode ser desfeita.`)) {
      onDelete(card);
      onOpenChange(false);
    }
  };
  const handleSaveInsights = async () => {
    setSavingInsights(true);
    try { await onSaveInsights(card, insightsText); }
    finally { setSavingInsights(false); }
  };
  const handleSaveTaskDesc = async () => {
    if (!onSaveTaskDescription) return;
    setSavingTaskDesc(true);
    try { await onSaveTaskDescription(card, taskDescText); }
    finally { setSavingTaskDesc(false); }
  };
  const handleSaveTitle = async () => {
    if (!onSaveDisplayTitle) return;
    setSavingTitle(true);
    try { await onSaveDisplayTitle(card, titleText); }
    finally { setSavingTitle(false); }
  };
  const e = card.entity;
  const tier = (card.gold_tier && VALID_TIERS.includes(card.gold_tier as Tier) ? card.gold_tier : 'B') as Tier;
  const pains = card.pains || [];
  const queries = card.seed_queries || [];
  const funnels = card.funnel_hypotheses || [];
  const cpc = card.cpc_min != null ? `${card.cpc_min}${card.cpc_max != null ? `–${card.cpc_max}` : ''} ${card.cpc_currency || ''}`.trim() : null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {/* `overflow-x-hidden` é trava, não estilo: o corpo do drawer NUNCA rola
          na horizontal. Conteúdo largo (a fita de abas, uma tabela) rola dentro
          do próprio container. Sem isso, um filho que estoure a largura arrasta
          o painel inteiro e o título sai da tela — foi o que aconteceu quando a
          sétima aba entrou. */}
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto overflow-x-hidden">
        <SheetHeader className="space-y-2">
          <div className="flex items-center gap-2">
            <TierBadge tier={tier} showLabel />
            {card.strategic_stage && <span className="text-xs text-muted-foreground">{card.strategic_stage}</span>}
            {card.ephemeral && <span className="text-[10px] text-primary bg-primary/10 rounded px-1 py-0.5">demo</span>}
          </div>
          <SheetTitle className="font-display text-xl font-bold tracking-tight">
            {(card.display_title || '').trim() || e.canonical_name}
          </SheetTitle>
          <SheetDescription className="text-xs flex items-center gap-1">
            <Landmark className="h-3 w-3" />
            {(card.display_title || '').trim()
              ? `${e.canonical_name} · ${entitySubtitle(e)}`
              : entitySubtitle(e)}
          </SheetDescription>
        </SheetHeader>

        <div className="relative mt-4 flex items-center justify-between overflow-hidden rounded-lg border border-border bg-card p-3 shadow-card">
          <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-warning" />
          <div>
            <p className="kicker">Nota de arbitragem</p>
            <p className="font-display text-3xl font-bold text-warning tabular">{card.score ?? '—'}</p>
          </div>
          <div className="text-right text-xs text-muted-foreground">
            <p>Status: <span className="font-medium text-foreground">{STATUS_LABELS[card.status] || card.status}</span></p>
            {card.roi_signal != null && <p>Sinal ROI: <span className="tabular">{card.roi_signal}</span></p>}
            {cpc && <p>CPC: <span className="tabular">{cpc}</span></p>}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => onValidate(card)}>
            <Check className="h-3.5 w-3.5 mr-1" /> Validar
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onMine(card)}>
            {busy ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Pickaxe className="h-3.5 w-3.5 mr-1" />} Minerar
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onFunnel(card)}>
            {busy ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Workflow className="h-3.5 w-3.5 mr-1" />} Funil
          </Button>
          {canRerun && (
            <Button size="sm" variant="outline" className="border-warning/40 text-warning hover:bg-warning/10" disabled={busy} onClick={() => onRerun(card)}>
              {busy ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <RotateCw className="h-3.5 w-3.5 mr-1" />} Rodar novamente
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => onMove(card, 'ready')}>Pronto</Button>
          {/* O briefing vive AQUI, e é o único lugar. O ClickUp saiu do VOLC
              O.S. — herança do webgo — porque documentação em dois lugares vira
              duas verdades sem ninguém saber qual vale. */}
          <BriefingAcoes card={card} />
          {isRejected ? (
            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive hover:bg-destructive/10" onClick={handleDelete}>
              <Trash2 className="h-3.5 w-3.5 mr-1" /> Excluir
            </Button>
          ) : (
            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => onMove(card, 'rejected')}>
              <X className="h-3.5 w-3.5 mr-1" /> Rejeitar
            </Button>
          )}
        </div>

        <Separator className="my-4" />

        {/* Card já medido abre em Validação. Abrir em `Detalhe` obrigava a
            achar a aba certa para ver a única coisa que o card tem de novo — e
            a aba de Validação é justamente a que fica no meio da fita. */}
        <Tabs defaultValue={card.validacao ? 'validacao' : 'detalhe'}>
          {/* A FITA DE ABAS ROLA DENTRO DE SI MESMA.
              Sete abas passam da largura do drawer, e a `TabsList` do shadcn é
              `inline-flex` sem quebra — ela empurrava o painel inteiro. Aqui a
              rolagem fica presa neste container, e a máscara à direita avisa
              que há mais aba sem precisar de seta nem de legenda.
              As abas encolhem de `text-sm/px-3` para `text-xs/px-2.5`: com isso
              as sete cabem em telas de 640px para cima, e a rolagem vira rede
              de segurança para quando as contagens crescerem (`Keywords (12)`)
              em vez de ser o comportamento normal. */}
          <div className="overflow-x-auto pb-0.5
                          [scrollbar-width:none] [&::-webkit-scrollbar]:hidden
                          [mask-image:linear-gradient(to_right,#000_0,#000_calc(100%_-_18px),transparent_100%)]">
            <TabsList className="w-max">
              <TabsTrigger value="detalhe" className="shrink-0 px-2.5 text-xs">Detalhe</TabsTrigger>
              <TabsTrigger value="validacao" className="shrink-0 px-2.5 text-xs">
                Validação {card.validacao?.portao?.veredito === 'portao' ? '⛔'
                  : card.validacao?.portao?.veredito === 'limitrofe' ? '◑'
                  : card.validacao ? '•' : ''}
              </TabsTrigger>
              <TabsTrigger value="entidade" className="shrink-0 px-2.5 text-xs">Entidade</TabsTrigger>
              <TabsTrigger value="dores" className="shrink-0 px-2.5 text-xs">Dores {pains.length ? `(${pains.length})` : ''}</TabsTrigger>
              <TabsTrigger value="keywords" className="shrink-0 px-2.5 text-xs">Keywords {queries.length ? `(${queries.length})` : ''}</TabsTrigger>
              <TabsTrigger value="funil" className="shrink-0 px-2.5 text-xs">Funil {funnels.length ? `(${funnels.length})` : ''}</TabsTrigger>
              <TabsTrigger value="insights" className="shrink-0 px-2.5 text-xs">Notas {card.insights || card.task_description ? '•' : ''}</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="validacao" className="pt-3">
            <ValidacaoPainel
              validacao={card.validacao}
              medindo={!!card.id && medindo?.has(String(card.id))}
              progresso={card.id ? progresso?.[String(card.id)] : undefined}
              onMedir={onMedir ? () => onMedir(card) : undefined}
            />
          </TabsContent>

          {/* DETALHE */}
          <TabsContent value="detalhe" className="mt-4 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Volume">{card.volume_level || '—'}</Field>
              <Field label="RPM">{card.rpm_level || '—'}</Field>
              <Field label="Concorrência">{card.competition_level || '—'}</Field>
              <Field label="Confiança">{card.confidence_level || '—'}</Field>
              <Field label="Janela temporal">{card.temporal_window || '—'}</Field>
              <Field label="CPC estimado">{cpc || '—'}</Field>
            </div>
            {card.concrete_pain && (
              <div>
                <p className="kicker">Dor concreta</p>
                <p className="text-sm">{card.concrete_pain}</p>
              </div>
            )}
            {card.gold_reason && (
              <div>
                <p className="kicker">Razão de ser ouro</p>
                <p className="text-sm">{card.gold_reason}</p>
              </div>
            )}
          </TabsContent>

          {/* ENTIDADE */}
          <TabsContent value="entidade" className="mt-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Nome canônico">{e.canonical_name}</Field>
              <Field label="Nome completo">{e.full_name || '—'}</Field>
              <Field label="País">{e.country || e.country_code}</Field>
              <Field label="Tipo">{e.entity_type || '—'}</Field>
              <Field label="Categoria">{e.entity_category || '—'}</Field>
              <Field label="Órgão / fonte oficial">{e.official_source || '—'}</Field>
            </div>
            {!!e.related_systems?.length && (
              <div>
                <p className="kicker mb-1">Sistemas relacionados</p>
                <div className="flex flex-wrap gap-1">
                  {e.related_systems.map((s, i) => <span key={i} className="text-[11px] bg-info/10 text-info border border-info/20 rounded px-1.5 py-0.5">{s}</span>)}
                </div>
              </div>
            )}
            {!!e.aliases?.length && (
              <div>
                <p className="kicker mb-1">Aliases</p>
                <div className="flex flex-wrap gap-1">
                  {e.aliases.map((a, i) => <span key={i} className="text-[11px] bg-muted rounded px-1.5 py-0.5">{a}</span>)}
                </div>
              </div>
            )}
            {e.description && (
              <div>
                <p className="kicker">Descrição</p>
                <p className="text-sm">{e.description}</p>
              </div>
            )}
          </TabsContent>

          {/* DORES */}
          <TabsContent value="dores" className="mt-4">
            {pains.length ? (
              <div className="space-y-2">
                {pains.map((p, i) => (
                  <div key={i} className="rounded-lg border p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium">{p.pain_name}</p>
                      <div className="flex items-center gap-1 shrink-0">
                        {p.intent && <span className="text-[10px] bg-muted rounded px-1.5 py-0.5">{p.intent}</span>}
                        {p.severity && <span className={`text-[10px] font-semibold ${sev(p.severity)}`}>{p.severity}</span>}
                      </div>
                    </div>
                    {p.pain_description && <p className="text-xs text-muted-foreground mt-1">{p.pain_description}</p>}
                    {p.user_goal && <p className="text-[11px] mt-1 inline-flex items-center gap-1"><Target className="h-3 w-3 text-primary shrink-0" /> {p.user_goal}</p>}
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-muted-foreground">Sem dores. Clique em <b>Minerar</b> para aprofundar a entidade.</div>
            )}
          </TabsContent>

          {/* KEYWORDS */}
          <TabsContent value="keywords" className="mt-4 space-y-3">
            {!!cluster?.production_ads_queue?.length && (
              <div>
                <p className="kicker mb-1">
                  Fila de ADS — minerada ({cluster.production_ads_queue.length})
                </p>
                <div className="rounded-lg border divide-y max-h-64 overflow-y-auto">
                  {cluster.production_ads_queue.slice(0, 40).map((k, i) => (
                    <div key={i} className="flex items-center justify-between p-2 text-xs gap-2">
                      <span className="truncate flex-1">{k.keyword}</span>
                      <span className="text-muted-foreground shrink-0 tabular-nums">
                        vol {typeof k.volume === 'number' ? k.volume.toLocaleString('pt-BR') : '—'} · CPC {typeof k.cpc === 'number' ? k.cpc.toFixed(2) : '—'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {queries.length > 0 && (
              <div>
                <p className="kicker mb-1">Seed queries ({queries.length})</p>
                <div className="rounded-lg border divide-y">
                  {queries.map((q, i) => (
                    <div key={i} className="flex items-center justify-between p-2 text-xs gap-2">
                      <span className="truncate flex-1">{q.query}</span>
                      <div className="flex items-center gap-1 shrink-0">
                        {q.query_type && <span className="text-[10px] text-muted-foreground bg-muted rounded px-1 py-0.5">{q.query_type}</span>}
                        {q.intent && <span className="text-[10px] text-info">{q.intent}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {!cluster?.production_ads_queue?.length && queries.length === 0 && (
              <div className="py-8 text-center text-xs text-muted-foreground">Sem keywords. <b>Minerar</b> gera as evidências da entidade.</div>
            )}
          </TabsContent>

          {/* FUNIL */}
          <TabsContent value="funil" className="mt-4 space-y-3">
            {!!funnelResult?.pages?.length && (() => {
              const strat = (funnelResult.funnel_strategy || {}) as Record<string, unknown>;
              const wjByPage = new Map<number, Record<string, unknown>>();
              (funnelResult.writing_jobs || []).forEach((j) => {
                const wb = (j.writer_briefing || {}) as Record<string, unknown>;
                const pn = Number(wb.page_num);
                if (!Number.isNaN(pn)) wjByPage.set(pn, wb);
              });
              return (
                <div className="rounded-lg border bg-muted/30 p-3 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold">Esqueleto do funil ({funnelResult.pages.length} páginas)</p>
                    <span className="text-[10px] rounded px-1.5 py-0.5 border border-info/20 bg-info/10 text-info">
                      {funnelResult.writing_jobs?.length ?? 0} briefings
                    </span>
                  </div>
                  {(strat.avatar_summary || strat.tone_voice) && (
                    <div className="text-[11px] text-muted-foreground space-y-0.5">
                      {!!strat.avatar_summary && <p><span className="font-medium text-foreground">Avatar:</span> {String(strat.avatar_summary)}</p>}
                      {!!strat.tone_voice && <p><span className="font-medium text-foreground">Tom:</span> {String(strat.tone_voice)}</p>}
                    </div>
                  )}
                  <div className="space-y-2">
                    {funnelResult.pages.map((p, i) => {
                      const wb = wjByPage.get(p.position) || {};
                      const kws = wb.keywords ? String(wb.keywords) : '';
                      const cta = wb.cta_text ? String(wb.cta_text) : '';
                      const ctaLink = wb.cta_link ? String(wb.cta_link) : '';
                      const slug = wb.current_url ? String(wb.current_url) : '';
                      return (
                        <div key={i} className="rounded-md border bg-background p-2.5 space-y-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-xs font-semibold">P{p.position}. {p.page_title}</p>
                            <span className={`text-[9px] rounded px-1.5 py-0.5 shrink-0 border ${
                              p.position === 1 ? 'border-info/20 bg-info/10 text-info'
                                : p.position === 2 ? 'border-warning/30 bg-warning/10 text-warning'
                                  : 'border-success/30 bg-success/10 text-success'
                            }`}>{funnelRoleLabel(p)}</span>
                          </div>
                          {slug && <p className="text-[10px] text-info">/{slug}</p>}
                          {p.emotional_goal && <p className="text-[11px] inline-flex items-center gap-1"><Target className="h-3 w-3 text-primary shrink-0" /> {p.emotional_goal}</p>}
                          {!!p.subtitles?.length && (
                            <div>
                              <p className="kicker">Estrutura (H2s)</p>
                              <ul className="list-disc list-inside text-[11px] space-y-0.5">
                                {p.subtitles.map((s, j) => <li key={j}>{s}</li>)}
                              </ul>
                            </div>
                          )}
                          {!!p.internal_links?.length && (
                            <div className="flex flex-wrap gap-1">
                              {p.internal_links.map((l, j) => (
                                <span key={j} className="inline-flex items-center gap-0.5 text-[10px] text-info">
                                  <ExternalLink className="h-2.5 w-2.5" />{l}
                                </span>
                              ))}
                            </div>
                          )}
                          {(kws || cta) && (
                            <div className="text-[10px] text-muted-foreground border-t border-border pt-1 space-y-0.5">
                              {kws && <p className="inline-flex items-center gap-1"><KeyRound className="h-2.5 w-2.5 text-info shrink-0" /> {kws}</p>}
                              {cta && <p>CTA: <span className="font-medium text-foreground">{cta}</span>{ctaLink ? ` → ${ctaLink}` : ''}</p>}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}
            {funnels.length ? (
              <div className="space-y-3">
                {funnels.map((f, i) => (
                  <div key={i} className="rounded-lg border p-3">
                    <p className="text-sm font-semibold">{funnelTitle(f)}</p>
                    {funnelSummary(f) && <p className="text-xs text-muted-foreground mt-1">{funnelSummary(f)}</p>}
                    {!!f.pages?.length && (
                      <ol className="list-decimal list-inside text-xs mt-2 space-y-0.5">
                        {f.pages.map((pg, j) => <li key={j}>{pg}</li>)}
                      </ol>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-muted-foreground">Sem funil. Clique em <b>Funil</b> para gerar hipóteses centradas na entidade.</div>
            )}
          </TabsContent>

          {/* INSIGHTS — direcionamento do admin (entra no prompt do funil) */}
          <TabsContent value="insights" className="mt-4 space-y-3">
            {onSaveDisplayTitle && !card.ephemeral && card.id && (
              <div className="space-y-1.5 pb-3 border-b">
                <p className="kicker">
                  Nome de exibição do card
                </p>
                <div className="flex items-center gap-2">
                  <input
                    value={titleText}
                    onChange={(ev) => setTitleText(ev.target.value)}
                    onKeyDown={(ev) => { if (ev.key === 'Enter' && !savingTitle) void handleSaveTitle(); }}
                    placeholder={e.canonical_name}
                    className="flex-1 h-8 rounded-md border border-input bg-background px-2 text-sm"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={savingTitle || titleText === (card.display_title || '')}
                    onClick={handleSaveTitle}
                  >
                    {savingTitle ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Renomear'}
                  </Button>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  Só o rótulo do card (e o título da task no ClickUp). A entidade continua
                  sendo <b>{e.canonical_name}</b> para o agente de funil. Vazio = usa o nome da entidade.
                </p>
              </div>
            )}

            <p className="kicker">
              Direcionamento do agente
            </p>
            <div className="flex items-start gap-1.5 text-xs text-warning bg-warning/10 border border-warning/20 rounded-md p-2">
              <Lightbulb className="h-3.5 w-3.5 text-warning mt-0.5 shrink-0" />
              <span>
                <b>Este texto vira direcionamento do agente de funil.</b> Ao arrastar o card
                para <b>Em funil</b>, o que estiver aqui entra no prompt do arquiteto como
                instrução prioritária (sem revogar a estrutura do funil). Não aparece no
                briefing nem na task — é bastidor. Deixe vazio para o comportamento padrão.
              </span>
            </div>
            <Textarea
              value={insightsText}
              onChange={(ev) => setInsightsText(ev.target.value)}
              placeholder="Ex.: recortar para quem perdeu o prazo e vai pagar multa; evitar tom alarmista; a página 3 deve cobrir o passo a passo pelo app…"
              className="min-h-[200px] text-sm"
            />
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-muted-foreground">{insightsText.length} caracteres{card.ephemeral ? ' · card demo (não persiste)' : ''}</span>
              <Button
                size="sm"
                disabled={savingInsights || insightsText === (card.insights || '')}
                onClick={handleSaveInsights}
              >
                {savingInsights ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
                Salvar direcionamento
              </Button>
            </div>

            {/* Segundo campo: o que a PESSOA lê no ClickUp. Separado do de cima
                de propósito — um é prompt de máquina, o outro é instrução humana. */}
            {onSaveTaskDescription && (
              <div className="pt-4 mt-2 border-t space-y-2">
                <p className="kicker">
                  Descrição da tarefa
                </p>
                <div className="flex items-start gap-1.5 text-xs text-info bg-info/10 border border-info/20 rounded-md p-2">
                  <ClipboardList className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <span>
                    Anotação livre para quem vai executar. Fica <b>só aqui no sistema</b>,
                    junto do card. Não entra no briefing nem na arquitetura do funil.
                  </span>
                </div>
                <Textarea
                  value={taskDescText}
                  onChange={(ev) => setTaskDescText(ev.target.value)}
                  placeholder="Ex.: publicar no site B; usar o template novo de landing; prazo até sexta; falar com o Design antes de subir…"
                  className="min-h-[140px] text-sm"
                />
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-muted-foreground">
                    {taskDescText.length} caracteres
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={savingTaskDesc || taskDescText === (card.task_description || '')}
                    onClick={handleSaveTaskDesc}
                  >
                    {savingTaskDesc ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
                    Salvar descrição
                  </Button>
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
};
