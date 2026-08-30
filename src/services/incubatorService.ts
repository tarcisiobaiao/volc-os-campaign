import { supabase } from '@/lib/supabase';
import type {
  IncubatorSite,
  IncubatorArticle,
  PipelineLog,
  NewSiteFormData,
  SiteStatus,
  ScheduleConfig,
  ScheduleProgress,
  GenerateScheduleResponse,
} from '@/types/incubator';

// --- Sites CRUD ---

export async function fetchSites(): Promise<IncubatorSite[]> {
  const { data, error } = await supabase
    .from('incubator_sites')
    .select('*')
    .order('updated_at', { ascending: false });

  if (error) throw error;
  return data || [];
}

export async function fetchSiteById(id: number): Promise<IncubatorSite | null> {
  const { data, error } = await supabase
    .from('incubator_sites')
    .select('*')
    .eq('id', id)
    .single();

  if (error) throw error;
  return data;
}

export async function createSite(formData: NewSiteFormData): Promise<IncubatorSite> {
  const { data: userData } = await supabase.auth.getUser();

  // Buscar o UUID do usuário na tabela users pelo email
  let createdBy: string | null = null;
  if (userData?.user?.email) {
    const { data: userRow } = await supabase
      .from('users')
      .select('id')
      .eq('email', userData.user.email)
      .single();
    if (userRow) createdBy = userRow.id;
  }

  // Separar títulos do resto dos dados do formulário
  const { titles, ...siteData } = formData;

  const { data, error } = await supabase
    .from('incubator_sites')
    .insert({
      ...siteData,
      status: 'draft' as SiteStatus,
      created_by: createdBy,
    })
    .select()
    .single();

  if (error) throw error;

  // Inserir títulos via RPC se fornecidos
  if (titles && titles.length > 0) {
    await supabase.rpc('insert_incubator_articles_batch', {
      p_site_id: data.id,
      p_titles: titles,
    });
  }

  return data;
}

export async function updateSite(id: number, updates: Partial<IncubatorSite>): Promise<IncubatorSite> {
  const { data, error } = await supabase
    .from('incubator_sites')
    .update(updates)
    .eq('id', id)
    .select()
    .single();

  if (error) throw error;
  return data;
}

export async function updateSiteStatus(id: number, status: SiteStatus): Promise<IncubatorSite> {
  return updateSite(id, { status });
}

export async function deleteSite(id: number): Promise<void> {
  const { error } = await supabase
    .from('incubator_sites')
    .delete()
    .eq('id', id);

  if (error) throw error;
}

// --- Articles ---

export async function fetchArticles(siteId: number): Promise<IncubatorArticle[]> {
  const { data, error } = await supabase
    .from('incubator_articles')
    .select('*')
    .eq('site_id', siteId)
    .order('created_at', { ascending: false });

  if (error) throw error;
  return data || [];
}

// --- Pipeline Logs ---

export async function fetchPipelineLogs(siteId: number): Promise<PipelineLog[]> {
  const { data, error } = await supabase
    .from('incubator_pipeline_logs')
    .select('*')
    .eq('site_id', siteId)
    .order('started_at', { ascending: false })
    .limit(20);

  if (error) throw error;
  return data || [];
}

// --- Start Pipeline (orchestrated flow) ---

export interface StartPipelineResult {
  success: boolean;
  message: string;
  scheduled?: number;
  effective_days?: number;
  estimated_completion?: string | null;
}

export async function startPipeline(
  site: IncubatorSite,
  scheduleConfig?: ScheduleConfig
): Promise<StartPipelineResult> {
  // 1. Verificar se o site tem artigos pendentes
  const { count, error: countError } = await supabase
    .from('incubator_articles')
    .select('*', { count: 'exact', head: true })
    .eq('site_id', site.id)
    .eq('status', 'pending');

  if (countError) throw countError;
  if (!count || count === 0) {
    return { success: false, message: 'Adicione títulos antes de iniciar o pipeline' };
  }

  // 2. Gerar schedule com config do site ou config fornecida
  const toTimeStr = (v: string | number | null | undefined, fallback: string): string => {
    if (!v) return fallback;
    const s = String(v);
    return s.includes(':') ? s : s.padStart(2, '0') + ':00';
  };

  const config: ScheduleConfig = scheduleConfig || {
    total_days: site.schedule_total_days || 7,
    window_start: toTimeStr(site.schedule_window_start, '07:00'),
    window_end: toTimeStr(site.schedule_window_end, '21:00'),
    min_gap_minutes: site.schedule_min_gap_minutes || 45,
  };

  try {
    const scheduleResult = await generateSchedule(site.id, config);

    // 3. Atualizar status para content_generating
    await updateSite(site.id, {
      status: 'content_generating' as SiteStatus,
      schedule_active: true,
      schedule_estimated_completion: scheduleResult.estimated_completion,
    });

    return {
      success: true,
      message: `Schedule criado: ${scheduleResult.scheduled} artigos em ${scheduleResult.effective_days} dias`,
      scheduled: scheduleResult.scheduled,
      effective_days: scheduleResult.effective_days,
      estimated_completion: scheduleResult.estimated_completion,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Erro ao gerar schedule';
    return { success: false, message };
  }
}

// --- Schedule ---

export async function generateSchedule(
  siteId: number,
  config: ScheduleConfig
): Promise<GenerateScheduleResponse> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session?.access_token) throw new Error('Não autenticado');

  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
  const response = await fetch(`${supabaseUrl}/functions/v1/generate-schedule`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({
      site_id: siteId,
      total_days: config.total_days,
      window_start: config.window_start,
      window_end: config.window_end,
      min_gap_minutes: config.min_gap_minutes,
    }),
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || `Erro ${response.status}`);
  }
  return result;
}

export async function pauseSchedule(siteId: number): Promise<void> {
  const { error } = await supabase
    .from('incubator_sites')
    .update({ schedule_active: false })
    .eq('id', siteId);

  if (error) throw error;
}

export async function resumeSchedule(siteId: number): Promise<void> {
  const { error } = await supabase
    .from('incubator_sites')
    .update({ schedule_active: true })
    .eq('id', siteId);

  if (error) throw error;
}

export async function fetchScheduleProgress(siteId: number): Promise<ScheduleProgress | null> {
  const { data, error } = await supabase
    .from('v_incubator_schedule_progress')
    .select('*')
    .eq('site_id', siteId)
    .single();

  if (error) {
    // View may return no rows, that's ok
    if (error.code === 'PGRST116') return null;
    throw error;
  }
  return data;
}

export async function clearSchedule(siteId: number): Promise<void> {
  // Remove schedule from all pending articles
  const { error: articlesError } = await supabase
    .from('incubator_articles')
    .update({ scheduled_at: null, schedule_batch_id: null })
    .eq('site_id', siteId)
    .eq('status', 'pending');

  if (articlesError) throw articlesError;

  // Reset site schedule fields
  const { error: siteError } = await supabase
    .from('incubator_sites')
    .update({
      schedule_active: false,
      schedule_started_at: null,
      schedule_estimated_completion: null,
    })
    .eq('id', siteId);

  if (siteError) throw siteError;
}

// --- Retry Failed Articles ---

export async function retryArticle(articleId: number): Promise<void> {
  const { error } = await supabase
    .from('incubator_articles')
    .update({
      status: 'pending',
      error_message: null,
      failed_at_step: null,
      scheduled_at: new Date(Date.now() + 60_000).toISOString(), // schedule 1min from now
    })
    .eq('id', articleId)
    .eq('status', 'failed');

  if (error) throw error;
}

export async function retryAllFailed(siteId: number): Promise<number> {
  const { data, error } = await supabase
    .from('incubator_articles')
    .update({
      status: 'pending',
      error_message: null,
      failed_at_step: null,
      scheduled_at: new Date(Date.now() + 60_000).toISOString(),
    })
    .eq('site_id', siteId)
    .eq('status', 'failed')
    .select('id');

  if (error) throw error;
  return data?.length || 0;
}

export const incubatorService = {
  fetchSites,
  fetchSiteById,
  createSite,
  updateSite,
  updateSiteStatus,
  deleteSite,
  fetchArticles,
  fetchPipelineLogs,
  startPipeline,
  generateSchedule,
  pauseSchedule,
  resumeSchedule,
  fetchScheduleProgress,
  clearSchedule,
  retryArticle,
  retryAllFailed,
};
