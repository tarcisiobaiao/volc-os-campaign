import React, { useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, Plus } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { pautadorApi, PautadorApiError } from '@/lib/pautadorApi';
import type { PautadorNiche } from '@/types/pautadorEntity';

// Modal "+ Nicho" (R1) — espelha AddCountryModal.tsx na estrutura/estilo.
// Diferente do AddCountryModal (que delega o submit ao pai), este componente
// chama pautadorApi.createNiche(...) diretamente e avisa o pai via onCreated
// para que a lista de nichos (dona do estado no hook) seja recarregada.
interface AddNicheModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (niche: PautadorNiche) => void;
}

const EMPTY = { slug: '', label: '', guidance: '', allowed_verticals: '' };

export const AddNicheModal: React.FC<AddNicheModalProps> = ({ open, onOpenChange, onCreated }) => {
  const { toast } = useToast();
  const [f, setF] = useState({ ...EMPTY });
  const [submitting, setSubmitting] = useState(false);

  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setF((prev) => ({ ...prev, [k]: e.target.value }));

  const reset = () => setF({ ...EMPTY });

  const handleSubmit = async () => {
    if (!f.slug.trim() || !f.label.trim() || submitting) return;
    setSubmitting(true);
    try {
      const resp = await pautadorApi.createNiche({
        slug: f.slug.trim(),
        label: f.label.trim(),
        guidance: f.guidance.trim() || undefined,
        allowed_verticals: f.allowed_verticals.split(',').map((v) => v.trim()).filter(Boolean),
      });
      toast({ title: 'Nicho criado ✅', description: `${resp.niche.label} (${resp.niche.slug}) adicionado.` });
      onCreated?.(resp.niche);
      reset();
      onOpenChange(false);
    } catch (err) {
      const message = err instanceof PautadorApiError ? err.message : 'Erro ao criar nicho';
      toast({ title: 'Falha ao criar nicho', description: message, variant: 'destructive' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Adicionar nicho</DialogTitle>
          <DialogDescription>
            Novo nicho selecionável para focar a descoberta (ex.: turismo, saúde, veículos).
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="an-slug" className="text-xs">Slug <span className="text-destructive">*</span></Label>
              <Input id="an-slug" autoFocus value={f.slug} onChange={set('slug')} placeholder="ex: turismo" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="an-label" className="text-xs">Nome <span className="text-destructive">*</span></Label>
              <Input
                id="an-label"
                value={f.label}
                onChange={set('label')}
                placeholder="ex: Turismo"
                onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="an-guidance" className="text-xs">Orientação (guidance)</Label>
            <Textarea
              id="an-guidance"
              value={f.guidance}
              onChange={set('guidance')}
              placeholder="Direcione o foco do nicho: o que trazer, o que evitar…"
              className="min-h-[70px] text-sm"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="an-verticals" className="text-xs">Verticais permitidas (separe por vírgula)</Label>
            <Input id="an-verticals" value={f.allowed_verticals} onChange={set('allowed_verticals')} placeholder="turismo, hospedagem" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>Cancelar</Button>
          <Button onClick={handleSubmit} disabled={!f.slug.trim() || !f.label.trim() || submitting}>
            {submitting ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Plus className="h-3.5 w-3.5 mr-1" />}
            Criar nicho
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
