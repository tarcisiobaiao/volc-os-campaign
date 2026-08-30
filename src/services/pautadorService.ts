// ============================================
// PAUTADOR PRO — leituras Supabase (anon + RLS) e atualizações de status.
// Segue o padrão de incubatorService.ts: client direto, named fns + bundle.
// As AÇÕES de IA (descoberta/mineração/funil) vão pelo backend FastAPI
// (lib/pautadorApi.ts); aqui ficam as leituras e moves simples de Kanban.
// ============================================

import { supabase } from '@/lib/supabase';
import type {
  AgentLog,
  FunnelPage,
  KeywordCluster,
  Opportunity,
  OpportunityStatus,
  PautadorCountry,
  PautadorRun,
} from '@/types/pautador';

/** Erro indicando que a migração v7 ainda não foi aplicada no Supabase. */
export class MigrationPendingError extends Error {
  constructor() {
    super('As tabelas pautador_* não existem. Rode src/sql/v7_01_create_pautador_tables.sql no Supabase.');
    this.name = 'MigrationPendingError';
  }
}

function isMissingTable(error: { code?: string; message?: string } | null): boolean {
  if (!error) return false;
  // 42P01 = undefined_table; PostgREST also returns PGRST205 for unknown table
  return error.code === '42P01' || error.code === 'PGRST205' ||
    /relation .* does not exist|could not find the table/i.test(error.message || '');
}

export async function fetchCountries(): Promise<PautadorCountry[]> {
  const { data, error } = await supabase
    .from('pautador_countries')
    .select('*')
    .eq('is_active', true)
    .order('country_name', { ascending: true });
  if (error) {
    if (isMissingTable(error)) throw new MigrationPendingError();
    throw error;
  }
  return data || [];
}

export async function createCountry(
  row: Omit<PautadorCountry, 'id'>,
): Promise<PautadorCountry> {
  const { data, error } = await supabase
    .from('pautador_countries')
    .insert(row)
    .select()
    .single();
  if (error) {
    if (isMissingTable(error)) throw new MigrationPendingError();
    throw error; // includes 23505 (unique_violation) for duplicate country_code
  }
  return data;
}

export async function fetchRuns(limit = 50): Promise<PautadorRun[]> {
  const { data, error } = await supabase
    .from('pautador_runs')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) {
    if (isMissingTable(error)) throw new MigrationPendingError();
    throw error;
  }
  return data || [];
}

export async function fetchLatestRun(country?: string): Promise<PautadorRun | null> {
  let query = supabase
    .from('pautador_runs')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(1);
  if (country) query = query.eq('country', country);
  const { data, error } = await query;
  if (error) {
    if (isMissingTable(error)) throw new MigrationPendingError();
    throw error;
  }
  return (data && data[0]) || null;
}

export async function fetchOpportunities(runId?: number, country?: string): Promise<Opportunity[]> {
  let query = supabase
    .from('pautador_opportunities')
    .select('*')
    .order('arbitrage_score', { ascending: false });
  if (runId) query = query.eq('run_id', runId);
  if (country) query = query.eq('country', country);
  const { data, error } = await query;
  if (error) {
    if (isMissingTable(error)) throw new MigrationPendingError();
    throw error;
  }
  return data || [];
}

export async function updateOpportunityStatus(
  id: number,
  status: OpportunityStatus,
): Promise<Opportunity> {
  const { data, error } = await supabase
    .from('pautador_opportunities')
    .update({ status })
    .eq('id', id)
    .select()
    .single();
  if (error) throw error;
  return data;
}

export async function fetchClusters(opportunityId: number): Promise<KeywordCluster[]> {
  const { data, error } = await supabase
    .from('pautador_keyword_clusters')
    .select('*')
    .eq('opportunity_id', opportunityId)
    .order('created_at', { ascending: false });
  if (error) {
    if (isMissingTable(error)) return [];
    throw error;
  }
  return data || [];
}

export async function fetchFunnelPages(opportunityId: number): Promise<FunnelPage[]> {
  const { data, error } = await supabase
    .from('pautador_funnels')
    .select('*')
    .eq('opportunity_id', opportunityId)
    .order('position', { ascending: true });
  if (error) {
    if (isMissingTable(error)) return [];
    throw error;
  }
  return data || [];
}

export async function fetchLogs(runId: number, limit = 100): Promise<AgentLog[]> {
  const { data, error } = await supabase
    .from('pautador_agent_logs')
    .select('*')
    .eq('run_id', runId)
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) {
    if (isMissingTable(error)) return [];
    throw error;
  }
  return data || [];
}

export const pautadorService = {
  fetchCountries,
  createCountry,
  fetchRuns,
  fetchLatestRun,
  fetchOpportunities,
  updateOpportunityStatus,
  fetchClusters,
  fetchFunnelPages,
  fetchLogs,
};
