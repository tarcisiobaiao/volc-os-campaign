import { useState, useCallback } from 'react';
import { incubatorService } from '@/services/incubatorService';
import type { StartPipelineResult } from '@/services/incubatorService';
import type { IncubatorSite, ScheduleConfig } from '@/types/incubator';

export function useTriggerPipeline() {
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trigger = useCallback(async (
    site: IncubatorSite,
    scheduleConfig?: ScheduleConfig
  ): Promise<StartPipelineResult> => {
    setTriggering(true);
    setError(null);
    try {
      const result = await incubatorService.startPipeline(site, scheduleConfig);
      if (!result.success) {
        setError(result.message);
      }
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao iniciar pipeline';
      setError(message);
      return { success: false, message };
    } finally {
      setTriggering(false);
    }
  }, []);

  return { trigger, triggering, error };
}
