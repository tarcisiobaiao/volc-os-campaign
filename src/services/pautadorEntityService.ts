// ============================================
// PAUTADOR PRO — ENTITY-FIRST leituras Supabase (anon + RLS).
// Cards de entidade por país (persistentes). As AÇÕES de IA (discovery/mine/
// funnel/validate/move) vão pelo backend FastAPI (lib/pautadorApi.ts).
// ============================================

import { supabase } from '@/lib/supabase';
import { MigrationPendingError } from '@/services/pautadorService';
import type { OpportunityStatus } from '@/types/pautador';
import type { EntityCard } from '@/types/pautadorEntity';

function isMissingTable(error: { code?: string; message?: string } | null): boolean {
  if (!error) return false;
  return (
    error.code === '42P01' ||
    error.code === 'PGRST205' ||
    /relation .* does not exist|could not find the table/i.test(error.message || '')
  );
}

/** Cards de entidade de um país (entidade + dores + seed queries + funis). */
export async function fetchEntityCards(countryCode: string): Promise<EntityCard[]> {
  const { data: opps, error } = await supabase
    .from('pautador_entity_opportunities')
    .select('*, entity:pautador_entities!entity_id(*)')
    .eq('country_code', countryCode)
    .order('score', { ascending: false, nullsFirst: false });
  if (error) {
    if (isMissingTable(error)) throw new MigrationPendingError();
    throw error;
  }
  const rows = opps || [];
  if (!rows.length) return [];

  const entityIds = Array.from(new Set(rows.map((o: any) => o.entity_id).filter(Boolean)));
  const oppIds = rows.map((o: any) => o.id).filter(Boolean);

  const [{ data: pains }, { data: queries }, { data: funnels }] = await Promise.all([
    supabase.from('pautador_entity_pains').select('*').in('entity_id', entityIds),
    supabase.from('pautador_entity_seed_queries').select('*').in('entity_id', entityIds),
    supabase.from('pautador_entity_funnel_hypotheses').select('*').in('opportunity_id', oppIds),
  ]);

  const group = <T extends Record<string, any>>(arr: T[] | null, key: string) => {
    const m = new Map<any, T[]>();
    for (const r of arr || []) {
      const k = r[key];
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(r);
    }
    return m;
  };
  const painsBy = group(pains, 'entity_id');
  const queriesBy = group(queries, 'entity_id');
  const funnelsBy = group(funnels, 'opportunity_id');

  return rows.map((o: any) => ({
    ...o,
    entity: o.entity || {
      canonical_name: '—',
      slug: '',
      country_code: o.country_code,
      related_systems: [],
      aliases: [],
    },
    pains: painsBy.get(o.entity_id) || [],
    seed_queries: queriesBy.get(o.entity_id) || [],
    funnel_hypotheses: funnelsBy.get(o.id) || [],
  })) as EntityCard[];
}

export async function updateEntityOpportunityStatus(
  id: number,
  status: OpportunityStatus,
): Promise<void> {
  const { error } = await supabase
    .from('pautador_entity_opportunities')
    .update({ status, kanban_stage: status })
    .eq('id', id);
  if (error) throw error;
}

export const pautadorEntityService = {
  fetchEntityCards,
  updateEntityOpportunityStatus,
};
