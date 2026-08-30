import React, { useEffect, useState } from 'react';
import { Copy, Loader2 } from 'lucide-react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { EntityCard } from '@/types/pautadorEntity';

interface DuplicateEntityDialogProps {
  card: EntityCard | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (card: EntityCard, displayTitle: string) => Promise<boolean>;
}

/**
 * Duplica um card já minerado para rodar a MESMA entidade em outro site.
 * O nome de exibição é só do CARD: a entidade (canonical_name) fica intacta,
 * porque é ela que alimenta o tema do agente de funil e o briefing.
 */
export const DuplicateEntityDialog: React.FC<DuplicateEntityDialogProps> = ({
  card, open, onOpenChange, onConfirm,
}) => {
  const [displayTitle, setDisplayTitle] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setDisplayTitle('');
  }, [open, card?.id]);

  if (!card) return null;

  const pains = card.pains?.length ?? 0;
  const queries = card.seed_queries?.length ?? 0;

  const submit = async () => {
    setSaving(true);
    const ok = await onConfirm(card, displayTitle.trim());
    setSaving(false);
    if (ok) onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="rounded-md bg-info/10 text-info p-1.5"><Copy className="h-4 w-4" /></span> Duplicar para outro site
          </DialogTitle>
          <DialogDescription>
            Cria um card novo de <strong>{card.entity.canonical_name}</strong> em
            {' '}<strong>Em mineração</strong>, aproveitando a mineração já feita
            ({pains} dor{pains === 1 ? '' : 'es'} · {queries} quer{queries === 1 ? 'y' : 'ies'}).
            A cópia começa sem funil e sem insights.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="duplicate-display-title">Nome de exibição do card</Label>
          <Input
            id="duplicate-display-title"
            value={displayTitle}
            onChange={(e) => setDisplayTitle(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !saving) void submit(); }}
            placeholder="Ex.: Site XPTO"
            autoFocus
          />
          <p className="text-[11px] text-muted-foreground">
            Identifica esta cópia no board e no título da task do ClickUp. A entidade
            em si não muda — o agente de funil continua recebendo
            {' '}“{card.entity.canonical_name}” como tema. Pode deixar em branco e
            nomear depois.
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={submit} disabled={saving}>
            {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Duplicando…</> : 'Duplicar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
