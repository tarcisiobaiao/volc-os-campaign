import { useState, useEffect, useCallback } from 'react';
import { incubatorService } from '@/services/incubatorService';
import type { IncubatorSite, NewSiteFormData, SiteStatus } from '@/types/incubator';

export function useIncubatorSites() {
  const [sites, setSites] = useState<IncubatorSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await incubatorService.fetchSites();
      setSites(data);
    } catch (err) {
      console.error('Error loading incubator sites:', err);
      setError('Erro ao carregar sites');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = useCallback(async (formData: NewSiteFormData) => {
    const newSite = await incubatorService.createSite(formData);
    setSites(prev => [newSite, ...prev]);
    return newSite;
  }, []);

  const update = useCallback(async (id: number, updates: Partial<IncubatorSite>) => {
    const updated = await incubatorService.updateSite(id, updates);
    setSites(prev => prev.map(s => s.id === id ? updated : s));
    return updated;
  }, []);

  const updateStatus = useCallback(async (id: number, status: SiteStatus) => {
    const updated = await incubatorService.updateSiteStatus(id, status);
    setSites(prev => prev.map(s => s.id === id ? updated : s));
    return updated;
  }, []);

  const remove = useCallback(async (id: number) => {
    await incubatorService.deleteSite(id);
    setSites(prev => prev.filter(s => s.id !== id));
  }, []);

  // Atualizar um site localmente (para Realtime)
  const updateLocal = useCallback((updated: Partial<IncubatorSite> & { id: number }) => {
    setSites(prev => prev.map(s => s.id === updated.id ? { ...s, ...updated } : s));
  }, []);

  const addLocal = useCallback((site: IncubatorSite) => {
    setSites(prev => {
      if (prev.some(s => s.id === site.id)) {
        return prev.map(s => s.id === site.id ? site : s);
      }
      return [site, ...prev];
    });
  }, []);

  // KPIs derivados
  const kpis = {
    total: sites.length,
    generating: sites.filter(s => s.status === 'content_generating').length,
    submitted: sites.filter(s => s.status === 'submitted' || s.status === 'submitting').length,
    approved: sites.filter(s => s.status === 'approved').length,
    rejected: sites.filter(s => s.status === 'rejected').length,
  };

  return {
    sites,
    loading,
    error,
    kpis,
    refresh: load,
    create,
    update,
    updateStatus,
    remove,
    updateLocal,
    addLocal,
  };
}
