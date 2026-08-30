import { useState, useEffect, useCallback } from 'react';
import { incubatorService } from '@/services/incubatorService';
import type { IncubatorSite, IncubatorArticle } from '@/types/incubator';

export function useIncubatorDetail(siteId: number | null) {
  const [site, setSite] = useState<IncubatorSite | null>(null);
  const [articles, setArticles] = useState<IncubatorArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!siteId) return;
    try {
      setLoading(true);
      setError(null);
      const [siteData, articlesData] = await Promise.all([
        incubatorService.fetchSiteById(siteId),
        incubatorService.fetchArticles(siteId),
      ]);
      setSite(siteData);
      setArticles(articlesData);
    } catch (err) {
      console.error('Error loading incubator detail:', err);
      setError('Erro ao carregar detalhes do site');
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => { load(); }, [load]);

  // Atualizar artigo localmente (para Realtime)
  const updateArticleLocal = useCallback((updated: Partial<IncubatorArticle> & { id: number }) => {
    setArticles(prev => prev.map(a => a.id === updated.id ? { ...a, ...updated } : a));
  }, []);

  const addArticleLocal = useCallback((article: IncubatorArticle) => {
    setArticles(prev => {
      if (prev.some(a => a.id === article.id)) {
        return prev.map(a => a.id === article.id ? article : a);
      }
      return [article, ...prev];
    });
  }, []);

  const updateSiteLocal = useCallback((updated: Partial<IncubatorSite>) => {
    setSite(prev => prev ? { ...prev, ...updated } : prev);
  }, []);

  return {
    site,
    articles,
    loading,
    error,
    refresh: load,
    updateArticleLocal,
    addArticleLocal,
    updateSiteLocal,
  };
}
