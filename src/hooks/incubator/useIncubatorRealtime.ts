import { useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import type { IncubatorSite, IncubatorArticle } from '@/types/incubator';

interface RealtimeCallbacks {
  onSiteChange?: (site: IncubatorSite) => void;
  onSiteInsert?: (site: IncubatorSite) => void;
  onArticleChange?: (article: IncubatorArticle) => void;
  onArticleInsert?: (article: IncubatorArticle) => void;
}

/**
 * Escuta mudanças Realtime nas tabelas incubator_sites e incubator_articles.
 * Se siteId for fornecido, filtra apenas mudanças daquele site.
 */
export function useIncubatorRealtime(callbacks: RealtimeCallbacks, siteId?: number) {
  useEffect(() => {
    const channelName = siteId ? `incubator-${siteId}` : 'incubator-all';

    let channel = supabase.channel(channelName);

    // Sites changes
    const sitesFilter = siteId ? `id=eq.${siteId}` : undefined;

    channel = channel.on(
      'postgres_changes',
      {
        event: 'UPDATE',
        schema: 'public',
        table: 'incubator_sites',
        ...(sitesFilter ? { filter: sitesFilter } : {}),
      },
      (payload) => {
        callbacks.onSiteChange?.(payload.new as IncubatorSite);
      }
    );

    channel = channel.on(
      'postgres_changes',
      {
        event: 'INSERT',
        schema: 'public',
        table: 'incubator_sites',
      },
      (payload) => {
        callbacks.onSiteInsert?.(payload.new as IncubatorSite);
      }
    );

    // Articles changes
    const articlesFilter = siteId ? `site_id=eq.${siteId}` : undefined;

    channel = channel.on(
      'postgres_changes',
      {
        event: 'UPDATE',
        schema: 'public',
        table: 'incubator_articles',
        ...(articlesFilter ? { filter: articlesFilter } : {}),
      },
      (payload) => {
        callbacks.onArticleChange?.(payload.new as IncubatorArticle);
      }
    );

    channel = channel.on(
      'postgres_changes',
      {
        event: 'INSERT',
        schema: 'public',
        table: 'incubator_articles',
        ...(articlesFilter ? { filter: articlesFilter } : {}),
      },
      (payload) => {
        callbacks.onArticleInsert?.(payload.new as IncubatorArticle);
      }
    );

    channel.subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [siteId, callbacks]);
}
