import { useState, useCallback } from 'react';
import { incubatorService } from '@/services/incubatorService';
import type { ScheduleConfig, GenerateScheduleResponse } from '@/types/incubator';

export function useSchedule() {
  const [generating, setGenerating] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generateSchedule = useCallback(async (
    siteId: number,
    config: ScheduleConfig
  ): Promise<GenerateScheduleResponse> => {
    setGenerating(true);
    setError(null);
    try {
      const result = await incubatorService.generateSchedule(siteId, config);
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao gerar schedule';
      setError(message);
      throw err;
    } finally {
      setGenerating(false);
    }
  }, []);

  const pauseSchedule = useCallback(async (siteId: number) => {
    setPausing(true);
    setError(null);
    try {
      await incubatorService.pauseSchedule(siteId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao pausar schedule';
      setError(message);
      throw err;
    } finally {
      setPausing(false);
    }
  }, []);

  const resumeSchedule = useCallback(async (siteId: number) => {
    setResuming(true);
    setError(null);
    try {
      await incubatorService.resumeSchedule(siteId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao retomar schedule';
      setError(message);
      throw err;
    } finally {
      setResuming(false);
    }
  }, []);

  const clearSchedule = useCallback(async (siteId: number) => {
    setError(null);
    try {
      await incubatorService.clearSchedule(siteId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao limpar schedule';
      setError(message);
      throw err;
    }
  }, []);

  return {
    generateSchedule,
    pauseSchedule,
    resumeSchedule,
    clearSchedule,
    generating,
    pausing,
    resuming,
    error,
  };
}
