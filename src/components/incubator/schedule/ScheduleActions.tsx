import React from 'react';
import { Button } from '@/components/ui/button';
import { Pause, Play, RefreshCw, Trash2 } from 'lucide-react';

interface ScheduleActionsProps {
  scheduleActive: boolean;
  onPause: () => Promise<void>;
  onResume: () => Promise<void>;
  onReschedule: () => void;
  onClear: () => Promise<void>;
  pausing: boolean;
  resuming: boolean;
}

export const ScheduleActions: React.FC<ScheduleActionsProps> = ({
  scheduleActive,
  onPause,
  onResume,
  onReschedule,
  onClear,
  pausing,
  resuming,
}) => {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="kicker">Agendamento</span>
        <span className="hairline-aurora w-8" />
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {scheduleActive ? (
          <Button variant="outline" size="sm" onClick={onPause} disabled={pausing}>
            <Pause className="h-4 w-4 mr-2" />
            {pausing ? 'Pausando...' : 'Pausar Schedule'}
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={onResume} disabled={resuming}>
            <Play className="h-4 w-4 mr-2" />
            {resuming ? 'Retomando...' : 'Retomar Schedule'}
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={onReschedule}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Reagendar
        </Button>
        <Button variant="ghost" size="sm" onClick={onClear} className="text-destructive hover:text-destructive hover:bg-destructive/10">
          <Trash2 className="h-4 w-4 mr-2" />
          Limpar Schedule
        </Button>
      </div>
    </div>
  );
};
