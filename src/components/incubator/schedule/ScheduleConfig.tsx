import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { CalendarClock, Clock, Timer, Layers, Save, Loader2 } from 'lucide-react';
import type { ScheduleConfig as ScheduleConfigType, IncubatorSite } from '@/types/incubator';

interface ScheduleConfigProps {
  site: IncubatorSite;
  pendingArticles: number;
  onSaveConfig: (config: ScheduleConfigType) => Promise<void>;
}

export const ScheduleConfig: React.FC<ScheduleConfigProps> = ({
  site,
  pendingArticles,
  onSaveConfig,
}) => {
  const [totalDays, setTotalDays] = useState(site.schedule_total_days || 7);
  const [windowStart, setWindowStart] = useState(site.schedule_window_start || '06:00');
  const [windowEnd, setWindowEnd] = useState(site.schedule_window_end || '22:00');
  const [minGap, setMinGap] = useState(site.schedule_min_gap_minutes || 60);
  const [saving, setSaving] = useState(false);

  const articlesPerDay = pendingArticles > 0 ? Math.ceil(pendingArticles / totalDays) : 0;

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSaveConfig({
        total_days: totalDays,
        window_start: windowStart,
        window_end: windowEnd,
        min_gap_minutes: minGap,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 0 }}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="rounded-md bg-primary/10 text-primary p-1.5"><CalendarClock className="h-4 w-4" /></span>
          Configurar Agendamento
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="totalDays" className="text-xs flex items-center gap-1">
              <Layers className="h-3 w-3" />
              Dias totais
            </Label>
            <Input
              id="totalDays"
              type="number"
              min={1}
              max={90}
              value={totalDays}
              onChange={(e) => setTotalDays(parseInt(e.target.value) || 1)}
              className="h-8 tabular"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="windowStart" className="text-xs flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Início janela
            </Label>
            <Input
              id="windowStart"
              type="time"
              value={windowStart}
              onChange={(e) => setWindowStart(e.target.value)}
              className="h-8 tabular"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="windowEnd" className="text-xs flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Fim janela
            </Label>
            <Input
              id="windowEnd"
              type="time"
              value={windowEnd}
              onChange={(e) => setWindowEnd(e.target.value)}
              className="h-8 tabular"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="minGap" className="text-xs flex items-center gap-1">
              <Timer className="h-3 w-3" />
              Gap mínimo (min)
            </Label>
            <Input
              id="minGap"
              type="number"
              min={15}
              max={480}
              value={minGap}
              onChange={(e) => setMinGap(parseInt(e.target.value) || 60)}
              className="h-8 tabular"
            />
          </div>
        </div>

        {/* Preview */}
        <div className="bg-muted/40 border border-border rounded-lg p-3 text-sm space-y-1">
          <p className="kicker">Preview</p>
          {pendingArticles > 0 ? (
            <>
              <p className="text-muted-foreground tabular">
                {pendingArticles} artigos pendentes distribuídos em {Math.min(totalDays, pendingArticles)} dias
                {articlesPerDay > 0 && ` (~${articlesPerDay} artigos/dia)`}
              </p>
              <p className="text-muted-foreground tabular">
                Publicação entre {windowStart} e {windowEnd} (horário de Brasília)
              </p>
            </>
          ) : (
            <p className="text-muted-foreground">
              Nenhum artigo pendente. Adicione títulos primeiro.
            </p>
          )}
        </div>

        <Button
          onClick={handleSave}
          disabled={saving}
          className="w-full"
          size="sm"
        >
          {saving ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Save className="h-4 w-4 mr-2" />
          )}
          {saving ? 'Salvando...' : 'Salvar Agendamento'}
        </Button>
      </CardContent>
    </Card>
  );
};
