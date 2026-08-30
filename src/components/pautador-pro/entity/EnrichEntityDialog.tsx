import React, { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Plus, Sparkles } from 'lucide-react';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  country: string;
  onEnrich: (name: string) => Promise<boolean> | boolean;
}

export const EnrichEntityDialog: React.FC<Props> = ({ open, onOpenChange, country, onEnrich }) => {
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      const ok = await onEnrich(name.trim());
      if (ok) { setName(''); onOpenChange(false); }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><span className="rounded-md bg-primary/10 text-primary p-1.5"><Sparkles className="h-4 w-4" /></span> Adicionar entidade em Descobertas</DialogTitle>
          <DialogDescription className="text-xs">
            Informe só o <b>nome da entidade</b> em <b>{country}</b>. Um agente secundário roda na hora e preenche o card com os mesmos dados da descoberta (dores, keywords, volume estimado…).
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1 py-1">
          <Label htmlFor="enrich-name" className="text-xs">Entidade <span className="text-destructive">*</span></Label>
          <Input
            id="enrich-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
            placeholder="Ex.: SOAT, RUNT, Sisbén…"
            autoFocus
          />
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>Cancelar</Button>
          <Button onClick={submit} disabled={saving || !name.trim()}>
            {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Plus className="h-3.5 w-3.5 mr-1" />}
            Enriquecer e adicionar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
