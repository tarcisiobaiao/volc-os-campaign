import React, { useMemo, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { calcArbitrageScore } from '@/lib/pautadorScore';
import {
  CATEGORY_LABELS, COMPETITION_LABELS, INTENT_LABELS, QUAL_LABELS, TIER_META, TIMING_LABELS,
} from '@/types/pautador';
import type {
  Category, Competition, Intent, Opportunity, Qual4, Tier, Timing,
} from '@/types/pautador';

interface AddOpportunityModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  country: string;
  nativeLanguage?: string;
  onSubmit: (opp: Opportunity) => void;
}

const CATEGORIES: Category[] = ['S1','S2','S3','S4','S5','S6','A1','A2','A3','A4','B1','B2','B3','EXP'];
const QUALS: Qual4[] = ['low','medium','high','very_high'];
const COMPS: Competition[] = ['low','medium','high'];
const INTENTS: Intent[] = ['informational','navigational','calculator','comparison'];
const TIMINGS: Timing[] = ['evergreen','seasonal','event_driven','trending'];

export const AddOpportunityModal: React.FC<AddOpportunityModalProps> = ({
  open, onOpenChange, country, nativeLanguage, onSubmit,
}) => {
  const [keyword, setKeyword] = useState('');
  const [mainKeyword, setMainKeyword] = useState('');
  const [tier, setTier] = useState<Tier>('S');
  const [category, setCategory] = useState<Category>('S1');
  const [volume, setVolume] = useState<Qual4>('high');
  const [rpm, setRpm] = useState<Qual4>('high');
  const [competition, setCompetition] = useState<Competition>('low');
  const [confidence, setConfidence] = useState<Qual4>('high');
  const [intent, setIntent] = useState<Intent>('informational');
  const [timing, setTiming] = useState<Timing>('evergreen');
  const [cpc, setCpc] = useState('');
  const [persona, setPersona] = useState('');
  const [painPoint, setPainPoint] = useState('');
  const [reasoning, setReasoning] = useState('');

  const previewScore = useMemo(
    () => calcArbitrageScore(volume, rpm, competition, confidence, tier),
    [volume, rpm, competition, confidence, tier],
  );

  const reset = () => {
    setKeyword(''); setMainKeyword(''); setCpc(''); setPersona(''); setPainPoint(''); setReasoning('');
  };

  const handleSubmit = () => {
    if (!keyword.trim() || !mainKeyword.trim()) return;
    const opp: Opportunity = {
      country,
      native_language: nativeLanguage,
      keyword: keyword.trim(),
      main_keyword: mainKeyword.trim(),
      tier,
      category,
      volume_estimate: volume,
      rpm_potential: rpm,
      competition_estimate: competition,
      confidence,
      intent,
      timing,
      cpc_estimate_local: cpc.trim() || undefined,
      persona: persona.trim() || undefined,
      pain_point: painPoint.trim() || undefined,
      reasoning: reasoning.trim() || undefined,
      arbitrage_score: previewScore,
      variations: [],
      expansion_hooks: [],
      status: 'discovered',
      source: 'manual',
    };
    onSubmit(opp);
    reset();
    onOpenChange(false);
  };

  const SelectField = <T extends string>({ label, value, onChange, options, labels }: {
    label: string; value: T; onChange: (v: T) => void; options: T[]; labels?: Record<string, string>;
  }) => (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Select value={value} onValueChange={(v) => onChange(v as T)}>
        <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
        <SelectContent>
          {options.map((o) => <SelectItem key={o} value={o}>{labels?.[o] || o}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Adicionar oportunidade — {country}</DialogTitle>
          <DialogDescription>
            Preencha o cartão canônico. A nota de arbitragem é calculada automaticamente.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1">
            <Label className="text-xs">Palavra-chave de busca (idioma nativo) *</Label>
            <Input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="ex: how to recover government gateway id" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Núcleo da dor (main keyword) *</Label>
            <Input value={mainKeyword} onChange={(e) => setMainKeyword(e.target.value)} placeholder="ex: gateway authenticator app" />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <SelectField label="Nível" value={tier} onChange={setTier} options={Object.keys(TIER_META) as Tier[]} labels={Object.fromEntries(Object.entries(TIER_META).map(([k, v]) => [k, `${v.short} · ${v.label}`]))} />
            <SelectField label="Categoria" value={category} onChange={setCategory} options={CATEGORIES} labels={Object.fromEntries(CATEGORIES.map((c) => [c, `${c} · ${CATEGORY_LABELS[c]}`]))} />
            <SelectField label="Volume" value={volume} onChange={setVolume} options={QUALS} labels={QUAL_LABELS} />
            <SelectField label="RPM" value={rpm} onChange={setRpm} options={QUALS} labels={QUAL_LABELS} />
            <SelectField label="Concorrência" value={competition} onChange={setCompetition} options={COMPS} labels={COMPETITION_LABELS} />
            <SelectField label="Confiança" value={confidence} onChange={setConfidence} options={QUALS} labels={QUAL_LABELS} />
            <SelectField label="Intenção" value={intent} onChange={setIntent} options={INTENTS} labels={INTENT_LABELS} />
            <SelectField label="Janela" value={timing} onChange={setTiming} options={TIMINGS} labels={TIMING_LABELS} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">CPC local (ex: 1.20-3.50 GBP)</Label>
              <Input value={cpc} onChange={(e) => setCpc(e.target.value)} placeholder="0.30-0.60 EUR" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Persona alvo</Label>
              <Input value={persona} onChange={(e) => setPersona(e.target.value)} placeholder="ex: João, 26 anos" />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Dor concreta</Label>
            <Textarea value={painPoint} onChange={(e) => setPainPoint(e.target.value)} rows={2} />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Razão de ser ouro</Label>
            <Textarea value={reasoning} onChange={(e) => setReasoning(e.target.value)} rows={2} />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-warning/30 bg-warning/10 p-3">
            <span className="kicker">Nota de arbitragem (preview)</span>
            <span className="font-display text-2xl font-bold text-warning tabular">{previewScore}</span>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button onClick={handleSubmit} disabled={!keyword.trim() || !mainKeyword.trim()}>Adicionar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
