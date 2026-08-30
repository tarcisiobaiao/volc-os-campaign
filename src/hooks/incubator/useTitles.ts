import { useState, useCallback } from 'react';
import { supabase } from '@/lib/supabase';
import type { BulkInsertResult } from '@/types/incubator';

export function useTitles(siteId: number | null) {
  const [inserting, setInserting] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const insertBatch = useCallback(async (titles: string[]): Promise<BulkInsertResult> => {
    if (!siteId) throw new Error('Site ID não definido');
    try {
      setInserting(true);
      const { data, error } = await supabase.rpc('insert_incubator_articles_batch', {
        p_site_id: siteId,
        p_titles: titles,
      });
      if (error) throw error;
      return data as BulkInsertResult;
    } finally {
      setInserting(false);
    }
  }, [siteId]);

  const removeTitles = useCallback(async (ids: number[]): Promise<number> => {
    if (!siteId || ids.length === 0) return 0;
    try {
      setRemoving(true);
      const { data, error } = await supabase
        .from('incubator_articles')
        .delete()
        .in('id', ids)
        .eq('site_id', siteId)
        .in('status', ['pending', 'failed'])
        .select('id');

      if (error) throw error;
      const count = data?.length ?? 0;

      // Atualizar contador do site
      const { count: remaining } = await supabase
        .from('incubator_articles')
        .select('id', { count: 'exact', head: true })
        .eq('site_id', siteId);

      await supabase
        .from('incubator_sites')
        .update({
          total_articles_planned: remaining ?? 0,
          updated_at: new Date().toISOString(),
        })
        .eq('id', siteId);

      return count;
    } finally {
      setRemoving(false);
    }
  }, [siteId]);

  const retryFailed = useCallback(async (ids: number[]): Promise<number> => {
    if (!siteId || ids.length === 0) return 0;
    try {
      setRetrying(true);
      const { data, error } = await supabase
        .from('incubator_articles')
        .update({
          status: 'pending',
          error_message: null,
          failed_at_step: null,
          scheduled_at: new Date(Date.now() + 60_000).toISOString(),
          updated_at: new Date().toISOString(),
        })
        .in('id', ids)
        .eq('site_id', siteId)
        .eq('status', 'failed')
        .select('id');

      if (error) throw error;
      return data?.length ?? 0;
    } finally {
      setRetrying(false);
    }
  }, [siteId]);

  const fetchExistingTitles = useCallback(async (): Promise<string[]> => {
    if (!siteId) return [];
    const { data, error } = await supabase
      .from('incubator_articles')
      .select('title')
      .eq('site_id', siteId);
    if (error) throw error;
    return (data || []).map(d => d.title);
  }, [siteId]);

  return {
    insertBatch,
    removeTitles,
    retryFailed,
    fetchExistingTitles,
    inserting,
    removing,
    retrying,
  };
}
