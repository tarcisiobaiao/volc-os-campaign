import React, { useMemo, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Check, HelpCircle } from 'lucide-react';
import { normalizeCountryInput } from '@/lib/pautadorCountries';

const MARKET_TIER_LABELS: Record<string, string> = {
  high_value: 'Alto valor (CPC/RPM altos)',
  medium_value: 'Valor médio',
  volume_play: 'Jogo de volume (CPC/RPM baixos)',
};

interface AddCountryModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  submitting?: boolean;
  onSubmit: (input: string) => void | Promise<void>;
}

export const AddCountryModal: React.FC<AddCountryModalProps> = ({ open, onOpenChange, submitting, onSubmit }) => {
  const [input, setInput] = useState('');
  const preview = useMemo(() => (input.trim() ? normalizeCountryInput(input) : null), [input]);

  const handleSubmit = async () => {
    if (!input.trim()) return;
    await onSubmit(input.trim());
    setInput('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setInput(''); onOpenChange(o); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Adicionar país</DialogTitle>
          <DialogDescription>
            Digite o país (ex: México, Argentina, Suíça, Japão). A normalização é automática.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs">País</Label>
            <Input
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="ex: México"
              onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
            />
          </div>

          {preview && (
            <div className="rounded-lg border p-3 space-y-2 bg-muted/30">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">
                  {preview.emoji_flag ? `${preview.emoji_flag} ` : ''}{preview.name_pt}
                </span>
                {preview.matched ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[10px] text-success">
                    <Check className="h-3 w-3" /> país conhecido
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-[10px] text-warning">
                    <HelpCircle className="h-3 w-3" /> novo (preenchimento parcial)
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>Nome nativo: <b className="text-foreground">{preview.name_native}</b></span>
                <span>ISO: <b className="text-foreground">{preview.iso2 || '—'}{preview.iso3 ? ` / ${preview.iso3}` : ''}</b></span>
                <span>Idioma: <b className="text-foreground">{preview.primary_language || '—'}</b></span>
                <span>Faixa: <b className="text-foreground">{MARKET_TIER_LABELS[preview.market_tier]}</b></span>
              </div>
              {!preview.matched && (
                <p className="text-[11px] text-warning">
                  País não está no mapa — ISO/idioma podem ficar vazios. Você pode ajustar depois no Supabase.
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button onClick={handleSubmit} disabled={!input.trim() || submitting}>
            {submitting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
            Adicionar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
