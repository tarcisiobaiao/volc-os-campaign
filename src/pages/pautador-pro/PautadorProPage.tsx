import React, { useState } from 'react';
import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { CountryCombobox } from '@/components/pautador-pro/CountryCombobox';
import { NicheMultiSelect } from '@/components/pautador-pro/NicheMultiSelect';
import { AddNicheModal } from '@/components/pautador-pro/AddNicheModal';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { RefreshCw, Radar, Columns3, Globe2, ShieldAlert, Loader2, Database, AlertTriangle, Plus } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

import { useEntityPautador } from '@/hooks/pautador/useEntityPautador';
import { KpiCards } from '@/components/pautador-pro/KpiCards';
import { EntityKanbanBoard } from '@/components/pautador-pro/entity/EntityKanbanBoard';
import { EntityDrawer } from '@/components/pautador-pro/entity/EntityDrawer';
import { ComparadorDeOportunidades } from '@/components/pautador-pro/entity/ComparadorDeOportunidades';
import { ManualEntityDialog } from '@/components/pautador-pro/entity/ManualEntityDialog';
import { DuplicateEntityDialog } from '@/components/pautador-pro/entity/DuplicateEntityDialog';
import { DispararRedatorDialog } from '@/components/pautador-pro/entity/DispararRedatorDialog';
import { EnrichEntityDialog } from '@/components/pautador-pro/entity/EnrichEntityDialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { IntelligencePanel } from '@/components/pautador-pro/IntelligencePanel';
import { ProgrammaticTiers } from '@/components/pautador-pro/ProgrammaticTiers';
import { entityKey } from '@/types/pautadorEntity';
import type { EntityCard } from '@/types/pautadorEntity';
import type { CulturalIntelligence, Insights } from '@/types/pautador';
import { PAUTADOR_COUNTRIES } from '@/data/pautadorCountries';

const ForbiddenView: React.FC = () => (
  <Layout>
    <div className="p-4 md:p-6">
      <Card className="border-destructive/30 bg-destructive/5 max-w-lg mx-auto mt-16 reveal">
        <CardContent className="p-8 text-center space-y-3">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <ShieldAlert className="h-6 w-6" />
          </span>
          <div className="kicker">Acesso restrito</div>
          <h2 className="font-display text-lg font-bold tracking-tight">Pautador Pro</h2>
          <p className="text-sm text-muted-foreground">O Pautador Pro é exclusivo para administradores.</p>
        </CardContent>
      </Card>
    </div>
  </Layout>
);

// Faixa animada persistente: indica que há uma descoberta ON no país (a run vive
// em pautador_runs.status='running', então sobrevive à navegação — sair e voltar).
const DiscoveryBanner: React.FC<{ country: string }> = ({ country }) => (
  <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 animate-fade-in shadow-card">
    <div className="flex items-center gap-2 text-sm text-primary">
      <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary">
        <Radar className="h-4 w-4 animate-spin" />
      </span>
      <span>
        Descoberta em andamento para <b>{country}</b>… as novas entidades aparecem aqui automaticamente.
      </span>
    </div>
    <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-primary/15">
      <div className="h-full w-1/3 rounded-full bg-primary animate-progress-indeterminate" />
    </div>
  </div>
);

// Esqueleto shimmer enquanto não há cards e a descoberta roda (primeiro run do país).
const DiscoverySkeleton: React.FC = () => (
  <div className="grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-6">
    {Array.from({ length: 6 }).map((_, col) => (
      <div key={col} className="space-y-3">
        <div className="h-6 w-24 skeleton" />
        {Array.from({ length: 2 + (col % 2) }).map((__, i) => (
          <div key={i} className="h-24 skeleton" />
        ))}
      </div>
    ))}
  </div>
);

const PautadorProContent: React.FC = () => {
  const {
    selectedCountry, setSelectedCountry,
    cards, source, migrationPending, cultural, insights, mineResults, funnelResults, kpis,
    loading, discovering, discoveryRunning, busyKeys, miningKeys, buildingKeys, doneKeys, apiConfigured,
    niches, selectedNiches, setSelectedNiches, seasonality, setSeasonality, reloadNiches,
    refresh, runDiscovery, moveEntity, mineEntity, buildFunnel, validateEntity,
    rerunEntity, deleteEntity, saveInsights, saveTaskDescription, saveDisplayTitle, duplicateCard,
    toggleFunnelCompleted, createManualEntity,
    enrichEntity,
    medirCard, medirColuna, medindo, medindoLote, ultimoLote, progresso,
    teses, tesesCarregando, tesesErro,
  } = useEntityPautador();

  const [activeTab, setActiveTab] = useState('kanban');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [duplicateTarget, setDuplicateTarget] = useState<EntityCard | null>(null);
  // O card cujo funil vai ser escrito. O popup pergunta em QUAL site.
  const [alvoDoRedator, setAlvoDoRedator] = useState<EntityCard | null>(null);
  const [enrichOpen, setEnrichOpen] = useState(false);
  const [addNicheOpen, setAddNicheOpen] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string>('');

  const selected = selectedKey ? cards.find((c) => entityKey(c) === selectedKey) ?? null : null;
  const openCard = (c: EntityCard) => { setSelectedKey(entityKey(c)); setDrawerOpen(true); };

  const countryData = PAUTADOR_COUNTRIES.find((c) => c.country_name === selectedCountry);

  return (
    <Layout>
      <div className="p-4 md:p-6 space-y-6">
        <div className="flex items-start justify-between flex-wrap gap-3 reveal" style={{ ['--i' as never]: 0 }}>
          <div className="min-w-0">
            <div className="kicker mb-2 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Radar className="h-3.5 w-3.5" />
              </span>
              Descoberta entity-first
            </div>
            <h1 className="font-display text-3xl font-bold tracking-tight leading-[1.05]">
              Pautador <span className="text-aurora">Pro</span>
            </h1>
            <div className="mt-3 aurora-rule w-16" />
            <p className="text-sm text-muted-foreground mt-3">
              Entidades por país · dores · keywords · funis
            </p>
          </div>
          <Button variant="outline" size="sm" className="hover-lift" onClick={refresh} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} /> Atualizar
          </Button>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <CountryCombobox value={selectedCountry} onChange={(name) => setSelectedCountry(name)} />

          <NicheMultiSelect niches={niches} value={selectedNiches} onChange={setSelectedNiches} />
          <Button variant="ghost" size="sm" className="gap-1 text-muted-foreground" onClick={() => setAddNicheOpen(true)}>
            <Plus className="h-3.5 w-3.5" /> Nicho
          </Button>

          <ToggleGroup
            type="single"
            size="sm"
            variant="outline"
            value={seasonality ?? ''}
            onValueChange={(v) => setSeasonality(v === '' ? null : (v as 'evergreen' | 'seasonal'))}
          >
            <ToggleGroupItem value="" aria-label="Sem filtro de sazonalidade">Todos</ToggleGroupItem>
            <ToggleGroupItem value="evergreen" aria-label="Evergreen">Evergreen</ToggleGroupItem>
            <ToggleGroupItem value="seasonal" aria-label="Sazonal">Sazonal</ToggleGroupItem>
          </ToggleGroup>

          <Button onClick={runDiscovery} disabled={discovering}>
            {discovering ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Radar className="h-4 w-4 mr-2" />}
            Disparar descoberta
          </Button>

          {source === 'ephemeral' && (
            <span className="inline-flex items-center gap-1.5 text-xs text-warning border border-warning/30 bg-warning/10 rounded-full px-2.5 py-1">
              <Database className="h-3 w-3" /> modo demo (não persistido)
            </span>
          )}
          {source === 'supabase' && (
            <span className="text-xs text-muted-foreground">{cards.length} entidades persistidas</span>
          )}
        </div>

        {migrationPending && (
          <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>Tabelas <code>pautador_entit*</code> não encontradas. Rode <code>src/sql/v7_03_pautador_entities.sql</code> no Supabase para persistir as entidades.</span>
          </div>
        )}
        {!apiConfigured && (
          <div className="flex items-start gap-2 rounded-lg border border-info/30 bg-info/10 p-3 text-xs text-info">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>Backend não configurado. Defina <code>VITE_PAUTADOR_API_URL</code> para disparar descobertas.</span>
          </div>
        )}

        <KpiCards {...kpis} />

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="kanban" className="gap-2"><Columns3 className="h-4 w-4" /> Entidades</TabsTrigger>
            <TabsTrigger value="cultural" className="gap-2"><Globe2 className="h-4 w-4" /> Inteligência cultural</TabsTrigger>
          </TabsList>

          <TabsContent value="kanban" className="mt-4 space-y-3">
            {discoveryRunning && <DiscoveryBanner country={selectedCountry} />}
            {loading ? (
              <div className="flex items-center justify-center py-16"><LoadingSpinner /></div>
            ) : cards.length === 0 ? (
              discoveryRunning ? (
                <DiscoverySkeleton />
              ) : (
                <div className="flex flex-col items-center gap-3 py-16 text-center">
                  <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <Radar className="h-6 w-6" />
                  </span>
                  <div className="kicker">Sem entidades</div>
                  <p className="max-w-sm text-sm text-muted-foreground">
                    Nenhuma entidade ainda para <b className="text-foreground">{selectedCountry}</b>. Clique em <b className="text-foreground">Disparar descoberta</b>.
                  </p>
                </div>
              )
            ) : (
              <>
                <EntityKanbanBoard cards={cards} busyKeys={busyKeys} miningKeys={miningKeys} buildingKeys={buildingKeys} doneKeys={doneKeys} onCardClick={openCard} onStatusChange={moveEntity} onToggleComplete={toggleFunnelCompleted} onEscreverFunil={setAlvoDoRedator} onAddManual={() => setManualOpen(true)} onAddEnrich={() => setEnrichOpen(true)} onDuplicate={setDuplicateTarget} onMedirColuna={medirColuna} medindoLote={medindoLote} ultimoLote={ultimoLote} medindo={medindo} progresso={progresso} />
                {/* A comparação só aparece quando há coluna de validação. Ela
                    não mede e não gasta: lê o que já foi gravado. */}
                {(teses?.ranking.length || teses?.fora_do_ranking.length || tesesCarregando) ? (
                  <ComparadorDeOportunidades
                    dados={teses}
                    carregando={tesesCarregando}
                    erro={tesesErro}
                    selecionadaId={selected?.id ?? null}
                    onSelecionar={(t) => {
                      const alvo = cards.find((c) => c.id === t.opportunity_id);
                      if (alvo) openCard(alvo);
                    }}
                  />
                ) : null}
              </>
            )}
          </TabsContent>

          <TabsContent value="cultural" className="mt-4 space-y-4">
            <ProgrammaticTiers
              countryName={selectedCountry}
              countryTier={countryData?.market_tier ?? null}
              currency={countryData?.currency_code ?? null}
            />
            <IntelligencePanel cultural={(cultural as unknown as CulturalIntelligence) || null} insights={(insights as unknown as Insights) || null} />
          </TabsContent>
        </Tabs>

        <EntityDrawer
          tese={selected?.id ? (teses?.teses.find((t) => t.opportunity_id === selected.id) ?? null) : null}
          onMedir={medirCard}
          medindo={medindo}
          progresso={progresso}
          card={selected}
          open={drawerOpen}
          onOpenChange={setDrawerOpen}
          mineResult={selected ? mineResults[selectedKey] : null}
          funnelResult={selected ? funnelResults[selectedKey] : null}
          busy={busyKeys.has(selectedKey)}
          onMove={moveEntity}
          onMine={mineEntity}
          onFunnel={buildFunnel}
          onValidate={validateEntity}
          onRerun={rerunEntity}
          onDelete={deleteEntity}
          onSaveInsights={saveInsights}
          onSaveTaskDescription={saveTaskDescription}
          onSaveDisplayTitle={saveDisplayTitle}
        />

        <DispararRedatorDialog
          card={alvoDoRedator}
          aberto={!!alvoDoRedator}
          aoFechar={() => setAlvoDoRedator(null)}
        />

        <DuplicateEntityDialog
          card={duplicateTarget}
          open={!!duplicateTarget}
          onOpenChange={(open) => { if (!open) setDuplicateTarget(null); }}
          onConfirm={duplicateCard}
        />

        <ManualEntityDialog
          open={manualOpen}
          onOpenChange={setManualOpen}
          country={selectedCountry}
          onCreate={createManualEntity}
        />

        <EnrichEntityDialog
          open={enrichOpen}
          onOpenChange={setEnrichOpen}
          country={selectedCountry}
          onEnrich={enrichEntity}
        />

        <AddNicheModal
          open={addNicheOpen}
          onOpenChange={setAddNicheOpen}
          onCreated={() => reloadNiches()}
        />
      </div>
    </Layout>
  );
};

const PautadorProPage: React.FC = () => {
  const { userProfile } = useAuth();
  if (userProfile?.role !== 'ADMIN') return <ForbiddenView />;
  return <PautadorProContent />;
};

export default PautadorProPage;
