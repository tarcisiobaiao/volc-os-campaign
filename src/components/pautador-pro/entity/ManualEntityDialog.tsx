import React, { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, Plus } from 'lucide-react';

interface ManualEntityFields {
  canonical_name: string;
  full_name?: string;
  official_source?: string;
  entity_category?: string;
  description?: string;
  aliases?: string[];
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  country: string;
  onCreate: (fields: ManualEntityFields) => Promise<boolean> | boolean;
}

const EMPTY = { canonical_name: '', full_name: '', official_source: '', entity_category: '', description: '', aliases: '' };

export const ManualEntityDialog: React.FC<Props> = ({ open, onOpenChange, country, onCreate }) => {
  const [f, setF] = useState({ ...EMPTY });
  const [saving, setSaving] = useState(false);
  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setF((prev) => ({ ...prev, [k]: e.target.value }));

  const submit = async () => {
    if (!f.canonical_name.trim() || saving) return;
    setSaving(true);
    try {
      const ok = await onCreate({
        canonical_name: f.canonical_name,
        full_name: f.full_name,
        official_source: f.official_source,
        entity_category: f.entity_category,
        description: f.description,
        aliases: f.aliases ? f.aliases.split(',').map((a) => a.trim()).filter(Boolean) : [],
      });
      if (ok) { setF({ ...EMPTY }); onOpenChange(false); }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><span className="rounded-md bg-success/10 text-success p-1.5"><Plus className="h-4 w-4" /></span> Adicionar entidade em Pronto</DialogTitle>
          <DialogDescription className="text-xs">
            Cadastro manual para sincronizar um funil que já existe em <b>{country}</b>. Entra direto na coluna <b>Pronto</b> e <b>não</b> dispara task no ClickUp.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-1">
          <div className="space-y-1">
            <Label htmlFor="me-name" className="text-xs">Nome canônico <span className="text-destructive">*</span></Label>
            <Input id="me-name" value={f.canonical_name} onChange={set('canonical_name')} placeholder="Ex.: SOAT" autoFocus />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="me-full" className="text-xs">Nome completo</Label>
              <Input id="me-full" value={f.full_name} onChange={set('full_name')} placeholder="Seguro Obligatorio…" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="me-src" className="text-xs">Órgão / fonte oficial</Label>
              <Input id="me-src" value={f.official_source} onChange={set('official_source')} placeholder="RUNT, DIAN…" />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="me-cat" className="text-xs">Categoria</Label>
            <Input id="me-cat" value={f.entity_category} onChange={set('entity_category')} placeholder="transito, tributos, saude…" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="me-alias" className="text-xs">Aliases (separe por vírgula)</Label>
            <Input id="me-alias" value={f.aliases} onChange={set('aliases')} placeholder="soat digital, soat en línea" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="me-desc" className="text-xs">Descrição</Label>
            <Textarea id="me-desc" value={f.description} onChange={set('description')} placeholder="O que é a entidade / por que já tem funil." className="min-h-[70px] text-sm" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>Cancelar</Button>
          <Button onClick={submit} disabled={saving || !f.canonical_name.trim()}>
            {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Plus className="h-3.5 w-3.5 mr-1" />}
            Criar em Pronto
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
