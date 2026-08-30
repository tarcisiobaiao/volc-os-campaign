// ============================================
// INCUBADORA DE SITES — Types & Constants
// ============================================

// --- Status Types ---

export type SiteStatus =
  | 'draft'
  | 'content_generating'
  | 'content_ready'
  | 'review'
  | 'submitting'
  | 'submitted'
  | 'approved'
  | 'rejected'
  | 'paused';

export type ArticleStatus =
  | 'pending'
  | 'researching'
  | 'writing'
  | 'seo_optimizing'
  | 'image_generating'
  | 'publishing'
  | 'published'
  | 'failed';

export type ExecutionType =
  | 'content_batch'
  | 'single_article'
  | 'adsense_submit'
  | 'status_check';

export type ExecutionStatus =
  | 'running'
  | 'success'
  | 'partial_success'
  | 'error';

// --- Data Interfaces ---

export interface IncubatorSite {
  id: number;
  site_name: string;
  site_niche: string;
  site_audience: string;
  country: string;
  wp_url: string;
  wp_username: string | null;
  wp_app_password: string | null;
  sheets_url: string | null;
  sheet_tab_name: string | null;
  status: SiteStatus;
  total_articles_planned: number;
  total_articles_published: number;
  total_articles_failed: number;
  adsense_submission_date: string | null;
  adsense_response_date: string | null;
  adsense_rejection_reason: string | null;
  adsense_pub_id: string | null;
  n8n_workflow_id: string | null;
  n8n_last_execution_id: string | null;
  n8n_last_execution_status: string | null;
  auto_publish: boolean;
  articles_per_batch: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  site_context: string | null;
  notes: string | null;
  // Schedule fields
  schedule_total_days: number | null;
  schedule_window_start: string | null;
  schedule_window_end: string | null;
  schedule_min_gap_minutes: number | null;
  schedule_active: boolean;
  schedule_started_at: string | null;
  schedule_estimated_completion: string | null;
}

export interface IncubatorArticle {
  id: number;
  site_id: number;
  title: string;
  slug: string | null;
  wp_post_id: number | null;
  wp_post_url: string | null;
  status: ArticleStatus;
  seo_title: string | null;
  meta_description: string | null;
  focus_keyword: string | null;
  excerpt: string | null;
  featured_image_url: string | null;
  image_alt_text: string | null;
  failed_at_step: string | null;
  error_message: string | null;
  retry_count: number;
  created_at: string;
  published_at: string | null;
  updated_at: string;
  // Schedule fields
  scheduled_at: string | null;
  schedule_batch_id: string | null;
}

export interface PipelineLog {
  id: number;
  site_id: number;
  execution_type: ExecutionType;
  status: ExecutionStatus;
  articles_attempted: number;
  articles_succeeded: number;
  articles_failed: number;
  error_message: string | null;
  n8n_execution_id: string | null;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
}

export interface NewSiteFormData {
  site_name: string;
  site_niche: string;
  site_audience: string;
  country: string;
  wp_url: string;
  wp_username: string;
  wp_app_password: string;
  articles_per_batch: number;
  auto_publish: boolean;
  site_context: string;
  titles?: string[];
}

export interface BulkInsertResult {
  inserted: number;
  skipped_duplicates: number;
  total_articles: number;
}

export interface TitleValidation {
  title: string;
  isValid: boolean;
  isDuplicate: boolean;
  warning?: string;
}

// --- Kanban ---

export interface KanbanColumn {
  id: string;
  title: string;
  statuses: SiteStatus[];
  color: string;
}

export const KANBAN_COLUMNS: KanbanColumn[] = [
  { id: 'draft',    title: 'Draft',             statuses: ['draft'],                      color: 'gray'   },
  { id: 'content',  title: 'Gerando Conteúdo',  statuses: ['content_generating'],         color: 'blue'   },
  { id: 'review',   title: 'Review',            statuses: ['content_ready', 'review'],    color: 'yellow' },
  { id: 'adsense',  title: 'AdSense',           statuses: ['submitting', 'submitted'],    color: 'purple' },
  { id: 'approved', title: 'Aprovado',          statuses: ['approved'],                   color: 'green'  },
  { id: 'rejected', title: 'Rejeitado',         statuses: ['rejected'],                   color: 'red'    },
];

// --- Status Colors & Labels ---

export const STATUS_COLORS: Record<SiteStatus, { bg: string; text: string; dot: string }> = {
  draft:              { bg: 'bg-gray-100',    text: 'text-gray-600',    dot: 'bg-gray-400'    },
  content_generating: { bg: 'bg-blue-50',     text: 'text-blue-600',    dot: 'bg-blue-500'    },
  content_ready:      { bg: 'bg-indigo-50',   text: 'text-indigo-600',  dot: 'bg-indigo-500'  },
  review:             { bg: 'bg-yellow-50',   text: 'text-yellow-700',  dot: 'bg-yellow-500'  },
  submitting:         { bg: 'bg-orange-50',   text: 'text-orange-600',  dot: 'bg-orange-500'  },
  submitted:          { bg: 'bg-purple-50',   text: 'text-purple-600',  dot: 'bg-purple-500'  },
  approved:           { bg: 'bg-green-50',    text: 'text-green-600',   dot: 'bg-green-500'   },
  rejected:           { bg: 'bg-red-50',      text: 'text-red-600',     dot: 'bg-red-500'     },
  paused:             { bg: 'bg-slate-100',   text: 'text-slate-500',   dot: 'bg-slate-400'   },
};

export const STATUS_LABELS: Record<SiteStatus, string> = {
  draft:              'Rascunho',
  content_generating: 'Gerando Conteúdo',
  content_ready:      'Conteúdo Pronto',
  review:             'Em Revisão',
  submitting:         'Submetendo',
  submitted:          'Aguardando AdSense',
  approved:           'Aprovado',
  rejected:           'Rejeitado',
  paused:             'Pausado',
};

export const ARTICLE_STATUS_LABELS: Record<ArticleStatus, string> = {
  pending:          'Na Fila',
  researching:      'Pesquisando',
  writing:          'Escrevendo',
  seo_optimizing:   'Otimizando SEO',
  image_generating: 'Gerando Imagem',
  publishing:       'Publicando',
  published:        'Publicado',
  failed:           'Falhou',
};

export const ARTICLE_STATUS_COLORS: Record<ArticleStatus, { bg: string; text: string }> = {
  pending:          { bg: 'bg-gray-100',   text: 'text-gray-600'   },
  researching:      { bg: 'bg-cyan-50',    text: 'text-cyan-600'   },
  writing:          { bg: 'bg-blue-50',    text: 'text-blue-600'   },
  seo_optimizing:   { bg: 'bg-indigo-50',  text: 'text-indigo-600' },
  image_generating: { bg: 'bg-violet-50',  text: 'text-violet-600' },
  publishing:       { bg: 'bg-orange-50',  text: 'text-orange-600' },
  published:        { bg: 'bg-green-50',   text: 'text-green-600'  },
  failed:           { bg: 'bg-red-50',     text: 'text-red-600'    },
};

// --- Schedule Types ---

export interface ScheduleConfig {
  total_days: number;
  window_start: string; // "06:00"
  window_end: string;   // "22:00"
  min_gap_minutes: number;
}

export interface ScheduleProgress {
  site_id: number;
  total_scheduled: number;
  published_count: number;
  pending_count: number;
  failed_count: number;
  progress_pct: number;
  next_scheduled_at: string | null;
  last_published_at: string | null;
  estimated_completion: string | null;
}

export interface ScheduleDayGroup {
  date: string;
  articles: IncubatorArticle[];
  published: number;
  pending: number;
  failed: number;
}

export interface GenerateScheduleResponse {
  success: boolean;
  scheduled: number;
  batch_id: string;
  effective_days: number;
  articles_per_day: number;
  estimated_completion: string | null;
  errors?: string[];
  error?: string;
}
