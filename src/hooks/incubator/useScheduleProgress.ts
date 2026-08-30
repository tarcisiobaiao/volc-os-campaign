import { useState, useEffect, useCallback } from 'react';
import { incubatorService } from '@/services/incubatorService';
import type { ScheduleProgress } from '@/types/incubator';

export function useScheduleProgress(siteId: number | null) {
  const [progress, setProgress] = useState<ScheduleProgress | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!siteId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await incubatorService.fetchScheduleProgress(siteId);
      setProgress(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao buscar progresso';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return {
    progress,
    loading,
    error,
    refresh: fetch,
  };
}
