import React, { useCallback, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useToast } from '@/hooks/use-toast';
import { ArrowLeft, Play, Pause, RefreshCw, Trash2 } from 'lucide-react';

import { useIncubatorDetail } from '@/hooks/incubator/useIncubatorDetail';
import { useIncubatorRealtime } from '@/hooks/incubator/useIncubatorRealtime';
import { useTriggerPipeline } from '@/hooks/incubator/useTriggerPipeline';
import { useSchedule } from '@/hooks/incubator/useSchedule';
import { useScheduleProgress } from '@/hooks/incubator/useScheduleProgress';
import { incubatorService } from '@/services/incubatorService';

import { SiteStatusBadge } from '@/components/incubator/StatusBadge';
import { SiteConfig } from '@/components/incubator/detail/SiteConfig';
import { SiteProgress } from '@/components/incubator/detail/SiteProgress';
import { TitleManager } from '@/components/incubator/TitleManager';
import { ScheduleConfig } from '@/components/incubator/schedule/ScheduleConfig';
import { ScheduleTimeline } from '@/components/incubator/schedule/ScheduleTimeline';
import { ScheduleActions } from '@/components/incubator/schedule/ScheduleActions';

import type { IncubatorSite, IncubatorArticle, ScheduleConfig as ScheduleConfigType } from '@/types/incubator';

const IncubatorDetailPage: React.FC = () => {
  const { siteId } = useParams<{ siteId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const numericId = siteId ? parseInt(siteId, 10) : null;

  const {
    site,
    articles,
    loading,
    error,
    refresh,
    updateArticleLocal,
    addArticleLocal,
    updateSiteLocal,
  } = useIncubatorDetail(numericId);

  const { trigger, triggering } = useTriggerPipeline();
  const { pauseSchedule, resumeSchedule, clearSchedule, pausing: schedulePausing, resuming: scheduleResuming } = useSchedule();
  const { progress: scheduleProgress, refresh: refreshScheduleProgress } = useScheduleProgress(numericId);
  const [showScheduleConfig, setShowScheduleConfig] = useState(false);

  // Realtime
  const realtimeCallbacks = useMemo(() => ({
    onSiteChange: (s: IncubatorSite) => updateSiteLocal(s),
    onArticleChange: (a: IncubatorArticle) => {
      updateArticleLocal(a);
      // Refresh schedule progress when article status changes
      if (['published', 'failed', 'researching'].includes(a.status)) {
        refreshScheduleProgress();
      }
    },
    onArticleInsert: (a: IncubatorArticle) => addArticleLocal(a),
  }), [updateSiteLocal, updateArticleLocal, addArticleLocal, refreshScheduleProgress]);

  useIncubatorRealtime(realtimeCallbacks, numericId || undefined);

  const handleTrigger = useCallback(async () => {
    if (!site) return;
    const result = await trigger(site);
    if (result.success) {
      toast({ title: 'Pipeline iniciado', description: result.message });
      updateSiteLocal({ status: 'content_generating', schedule_active: true, schedule_estimated_completion: result.estimated_completion });
      refresh();
      refreshScheduleProgress();
    } else {
      toast({ title: 'Erro', description: result.message, variant: 'destructive' });
    }
  }, [site, trigger, toast, updateSiteLocal, refresh, refreshScheduleProgress]);

  const handlePause = useCallback(async () => {
    if (!site) return;
    try {
      await incubatorService.updateSiteStatus(site.id, 'paused');
      updateSiteLocal({ status: 'paused' });
      toast({ title: 'Site pausado' });
    } catch {
      toast({ title: 'Erro ao pausar', variant: 'destructive' });
    }
  }, [site, toast, updateSiteLocal]);

  const pendingArticles = useMemo(
    () => articles.filter((a) => a.status === 'pending').length,
    [articles]
  );

  const hasScheduledArticles = useMemo(
    () => articles.some((a) => a.scheduled_at),
    [articles]
  );

  const handleSaveScheduleConfig = useCallback(async (config: ScheduleConfigType) => {
    if (!site) return;
    await incubatorService.updateSite(site.id, {
      schedule_total_days: config.total_days,
      schedule_window_start: config.window_start,
      schedule_window_end: config.window_end,
      schedule_min_gap_minutes: config.min_gap_minutes,
    });
    updateSiteLocal({
      schedule_total_days: config.total_days,
      schedule_window_start: config.window_start,
      schedule_window_end: config.window_end,
      schedule_min_gap_minutes: config.min_gap_minutes,
    });
    toast({ title: 'Configuração salva' });
  }, [site, updateSiteLocal, toast]);

  const handlePauseSchedule = useCallback(async () => {
    if (!site) return;
    try {
      await pauseSchedule(site.id);
      updateSiteLocal({ schedule_active: false });
      toast({ title: 'Schedule pausado' });
    } catch {
      toast({ title: 'Erro ao pausar schedule', variant: 'destructive' });
    }
  }, [site, pauseSchedule, updateSiteLocal, toast]);

  const handleResumeSchedule = useCallback(async () => {
    if (!site) return;
    try {
      await resumeSchedule(site.id);
      updateSiteLocal({ schedule_active: true });
      toast({ title: 'Schedule retomado' });
    } catch {
      toast({ title: 'Erro ao retomar schedule', variant: 'destructive' });
    }
  }, [site, resumeSchedule, updateSiteLocal, toast]);

  const [deleting, setDeleting] = useState(false);

  const handleDeleteSite = useCallback(async () => {
    if (!site) return;
    const confirmed = window.confirm(
      `Excluir "${site.site_name}" e todos os seus artigos? Esta ação não pode ser desfeita.`
    );
    if (!confirmed) return;

    setDeleting(true);
    try {
      await incubatorService.deleteSite(site.id);
      toast({ title: 'Projeto excluído' });
      navigate('/incubator');
    } catch {
      toast({ title: 'Erro ao excluir projeto', variant: 'destructive' });
      setDeleting(false);
    }
  }, [site, toast, navigate]);

  const handleClearSchedule = useCallback(async () => {
    if (!site) return;
    try {
      await clearSchedule(site.id);
      updateSiteLocal({ schedule_active: false, schedule_started_at: null, schedule_estimated_completion: null });
      toast({ title: 'Schedule removido' });
      refresh();
      refreshScheduleProgress();
    } catch {
      toast({ title: 'Erro ao limpar schedule', variant: 'destructive' });
    }
  }, [site, clearSchedule, updateSiteLocal, toast, refresh, refreshScheduleProgress]);

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-[60vh]">
          <LoadingSpinner />
        </div>
      </Layout>
    );
  }

  if (error || !site) {
    return (
      <Layout>
        <div className="p-6">
          <Button variant="ghost" onClick={() => navigate('/incubator')}>
            <ArrowLeft className="h-4 w-4 mr-2" /> Voltar
          </Button>
          <div className="flex flex-col items-center justify-center py-16">
            <p className="text-muted-foreground">{error || 'Site não encontrado'}</p>
          </div>
        </div>
      </Layout>
    );
  }

  const canTrigger = ['draft', 'content_ready', 'review', 'paused'].includes(site.status);
  const canPause = site.status === 'content_generating';
  const canDelete = !['content_generating'].includes(site.status);

  return (
    <Layout>
      <div className="p-4 md:p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3 reveal" style={{ ['--i' as any]: 0 }}>
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={() => navigate('/incubator')}>
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <div className="kicker mb-1">Projeto · Incubadora</div>
              <h1 className="font-display text-xl font-bold tracking-tight flex items-center gap-2">
                {site.site_name}
                <SiteStatusBadge status={site.status} />
              </h1>
              <p className="text-sm text-muted-foreground">{site.site_niche}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={refresh}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Atualizar
            </Button>
            {canPause && (
              <Button variant="outline" size="sm" onClick={handlePause}>
                <Pause className="h-4 w-4 mr-2" />
                Pausar
              </Button>
            )}
            {canTrigger && (
              <Button size="sm" onClick={handleTrigger} disabled={triggering}>
                <Play className="h-4 w-4 mr-2" />
                {triggering ? 'Iniciando...' : 'Iniciar Pipeline'}
              </Button>
            )}
            {canDelete && (
              <Button variant="destructive" size="sm" onClick={handleDeleteSite} disabled={deleting}>
                <Trash2 className="h-4 w-4 mr-2" />
                {deleting ? 'Excluindo...' : 'Excluir'}
              </Button>
            )}
          </div>
        </div>

        {/* Config */}
        <SiteConfig site={site} />

        {/* Progress */}
        <SiteProgress site={site} />

        {/* Schedule Section */}
        {hasScheduledArticles && (
          <>
            <ScheduleActions
              scheduleActive={site.schedule_active}
              onPause={handlePauseSchedule}
              onResume={handleResumeSchedule}
              onReschedule={() => setShowScheduleConfig(true)}
              onClear={handleClearSchedule}
              pausing={schedulePausing}
              resuming={scheduleResuming}
            />
            <ScheduleTimeline articles={articles} progress={scheduleProgress} />
          </>
        )}

        {/* Schedule Config — sempre visivel */}
        {(showScheduleConfig || !hasScheduledArticles) && (
          <ScheduleConfig
            site={site}
            pendingArticles={pendingArticles}
            onSaveConfig={handleSaveScheduleConfig}
          />
        )}

        {/* Title Manager — gestão completa de títulos */}
        <TitleManager siteId={site.id} articles={articles} onRefresh={refresh} />

      </div>
    </Layout>
  );
};

export default IncubatorDetailPage;
