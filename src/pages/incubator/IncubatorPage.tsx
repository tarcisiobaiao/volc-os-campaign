import React, { useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useToast } from '@/hooks/use-toast';
import { Plus, LayoutDashboard, Columns3, RefreshCw } from 'lucide-react';

import { useIncubatorSites } from '@/hooks/incubator/useIncubatorSites';
import { useIncubatorRealtime } from '@/hooks/incubator/useIncubatorRealtime';
import { useTriggerPipeline } from '@/hooks/incubator/useTriggerPipeline';

import { KpiCards } from '@/components/incubator/dashboard/KpiCards';
import { SiteGrid } from '@/components/incubator/dashboard/SiteGrid';
import { KanbanBoard } from '@/components/incubator/kanban/KanbanBoard';
import { NewSiteModal } from '@/components/incubator/NewSiteModal';

import type { IncubatorSite, NewSiteFormData, SiteStatus } from '@/types/incubator';

const IncubatorPage: React.FC = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [isNewModalOpen, setIsNewModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('dashboard');

  const {
    sites,
    loading,
    kpis,
    refresh,
    create,
    updateStatus,
    updateLocal,
    addLocal,
  } = useIncubatorSites();

  const { trigger, triggering } = useTriggerPipeline();

  // Realtime callbacks — memoizados para evitar re-subscribe
  const realtimeCallbacks = useMemo(() => ({
    onSiteChange: (site: IncubatorSite) => updateLocal(site),
    onSiteInsert: (site: IncubatorSite) => addLocal(site),
  }), [updateLocal, addLocal]);

  useIncubatorRealtime(realtimeCallbacks);

  // --- Handlers ---

  const handleView = useCallback((site: IncubatorSite) => {
    navigate(`/incubator/${site.id}`);
  }, [navigate]);

  const handleTrigger = useCallback(async (site: IncubatorSite) => {
    const result = await trigger(site);
    if (result.success) {
      toast({ title: 'Pipeline iniciado', description: result.message });
      updateLocal({ id: site.id, status: 'content_generating' as SiteStatus, schedule_active: true });
    } else {
      toast({ title: 'Erro ao iniciar pipeline', description: result.message, variant: 'destructive' });
    }
  }, [trigger, toast, updateLocal]);

  const handlePause = useCallback(async (site: IncubatorSite) => {
    try {
      await updateStatus(site.id, 'paused');
      toast({ title: 'Site pausado', description: `${site.site_name} foi pausado` });
    } catch {
      toast({ title: 'Erro ao pausar', variant: 'destructive' });
    }
  }, [updateStatus, toast]);

  const handleCreate = useCallback(async (data: NewSiteFormData) => {
    try {
      const newSite = await create(data);
      toast({ title: 'Site criado', description: `${newSite.site_name} adicionado à incubadora` });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao criar site';
      toast({ title: 'Erro ao criar site', description: message, variant: 'destructive' });
      throw err;
    }
  }, [create, toast]);

  const handleKanbanStatusChange = useCallback(async (siteId: number, newStatus: SiteStatus) => {
    if (newStatus === 'content_generating') {
      // Caso especial: iniciar pipeline (gera schedule + muda status)
      const site = sites.find(s => s.id === siteId);
      if (site) {
        await handleTrigger(site);
      }
      return;
    }
    try {
      await updateStatus(siteId, newStatus);
    } catch {
      toast({ title: 'Erro ao mover site', variant: 'destructive' });
      refresh();
    }
  }, [sites, handleTrigger, updateStatus, toast, refresh]);

  // --- Render ---

  return (
    <Layout>
      <div className="p-4 md:p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between flex-wrap gap-3 reveal" style={{ ['--i' as any]: 0 }}>
          <div>
            <div className="kicker mb-2 flex items-center gap-2">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
              Pipeline · AdSense
            </div>
            <h1 className="font-display font-bold tracking-tight leading-[1.05] text-3xl md:text-4xl">
              Incubadora de <span className="text-foreground">Sites</span>
            </h1>
            <div className="mt-3 aurora-rule w-16" />
            <p className="text-sm text-muted-foreground mt-3">
              Pipeline de criação e aprovação de sites no Google AdSense
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
            <Button size="sm" onClick={() => setIsNewModalOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Novo Site
            </Button>
          </div>
        </div>

        {/* KPIs */}
        <KpiCards {...kpis} />

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="dashboard" className="gap-2">
              <LayoutDashboard className="h-4 w-4" />
              Dashboard
            </TabsTrigger>
            <TabsTrigger value="kanban" className="gap-2">
              <Columns3 className="h-4 w-4" />
              Kanban
            </TabsTrigger>
          </TabsList>

          <TabsContent value="dashboard" className="mt-4">
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <LoadingSpinner />
              </div>
            ) : (
              <SiteGrid
                sites={sites}
                onView={handleView}
                onTrigger={handleTrigger}
                onPause={handlePause}
              />
            )}
          </TabsContent>

          <TabsContent value="kanban" className="mt-4">
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <LoadingSpinner />
              </div>
            ) : (
              <KanbanBoard
                sites={sites}
                onSiteClick={handleView}
                onStatusChange={handleKanbanStatusChange}
              />
            )}
          </TabsContent>
        </Tabs>

        {/* New Site Modal */}
        <NewSiteModal
          open={isNewModalOpen}
          onOpenChange={setIsNewModalOpen}
          onSubmit={handleCreate}
        />
      </div>
    </Layout>
  );
};

export default IncubatorPage;
