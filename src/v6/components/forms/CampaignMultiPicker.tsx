/**
 * v6 RBAC — CampaignMultiPicker
 *
 * Lista de checkboxes para seleção de **múltiplas campanhas** dentro
 * de um projeto, com:
 *
 *   - busca por nome/id
 *   - botão "Selecionar todas" / "Limpar"
 *   - contador de selecionadas
 *   - badges com #membros e indicador de comissão vigente
 *
 * É a UX correta para o fluxo de onboarding admin: não é um
 * combobox de "uma por vez", é um picker de lote, que é exatamente
 * como o admin pensa o trabalho ("dá acesso a todas as campanhas
 * desse projeto pra esse operador").
 *
 * Não bloqueia seleção: campanha pode ter múltiplos membros.
 */
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Search, ListChecks, Eraser, Users } from 'lucide-react';
import type { CampaignWithContext } from '@/v6/types/v6';

interface CampaignMultiPickerProps {
  campaigns: CampaignWithContext[];
  /** Filtra apenas campanhas deste projeto. Obrigatório aqui. */
  projectId: number | null;
  /** Lista controlada de campaign_ids selecionados. */
  value: string[];
  onChange: (value: string[]) => void;
  /** Marca uma campanha como "já vinculada" (para edição). */
  highlightUserId?: string;
  /** Texto custom para empty state. */
  emptyText?: string;
}

export function CampaignMultiPicker({
  campaigns,
  projectId,
  value,
  onChange,
  highlightUserId,
  emptyText,
}: CampaignMultiPickerProps) {
  const [search, setSearch] = useState('');

  const visible = useMemo(() => {
    if (projectId == null) return [];
    const list = campaigns.filter((c) => c.project_id === projectId);
    if (!search.trim()) return list;
    const q = search.toLowerCase();
    return list.filter(
      (c) =>
        (c.campaign_name ?? '').toLowerCase().includes(q) ||
        c.campaign_id.toLowerCase().includes(q)
    );
  }, [campaigns, projectId, search]);

  const totalInProject = useMemo(() => {
    if (projectId == null) return 0;
    return campaigns.filter((c) => c.project_id === projectId).length;
  }, [campaigns, projectId]);

  const selectedSet = useMemo(() => new Set(value), [value]);

  const allVisibleSelected =
    visible.length > 0 && visible.every((c) => selectedSet.has(c.campaign_id));

  const toggle = (id: string) => {
    if (selectedSet.has(id)) {
      onChange(value.filter((x) => x !== id));
    } else {
      onChange([...value, id]);
    }
  };

  const selectAllVisible = () => {
    const merged = new Set(value);
    for (const c of visible) merged.add(c.campaign_id);
    onChange(Array.from(merged));
  };

  const clearAll = () => onChange([]);

  if (projectId == null) {
    return (
      <div className="rounded-md border border-dashed bg-muted/20 p-6 text-center text-xs text-muted-foreground">
        Escolha um projeto para listar suas campanhas.
      </div>
    );
  }

  if (totalInProject === 0) {
    return (
      <div className="rounded-md border border-dashed bg-muted/20 p-6 text-center text-xs text-muted-foreground">
        {emptyText ?? 'Nenhuma campanha cadastrada neste projeto.'}
      </div>
    );
  }

  return (
    <div className="min-w-0 overflow-hidden rounded-md border bg-background">
      {/* Toolbar */}
      <div className="flex flex-col gap-2 border-b p-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar campanha…"
            className="h-8 pl-7 text-xs"
          />
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 px-2 text-[11px]"
            onClick={selectAllVisible}
            disabled={allVisibleSelected || visible.length === 0}
          >
            <ListChecks className="mr-1 h-3.5 w-3.5" />
            Selecionar {search.trim() ? 'visíveis' : 'todas'}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-[11px]"
            onClick={clearAll}
            disabled={value.length === 0}
          >
            <Eraser className="mr-1 h-3.5 w-3.5" />
            Limpar
          </Button>
        </div>
      </div>

      {/* Counter */}
      <div className="flex items-center justify-between border-b bg-muted/30 px-3 py-1.5 text-[11px] text-muted-foreground">
        <span>
          <strong className="text-foreground">{value.length}</strong> de{' '}
          {totalInProject} selecionada{value.length !== 1 ? 's' : ''}
          {search.trim() && (
            <>
              {' '}
              · mostrando {visible.length} resultado
              {visible.length !== 1 ? 's' : ''}
            </>
          )}
        </span>
      </div>

      {/* List */}
      <ScrollArea className="h-64">
        {visible.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted-foreground">
            Nenhuma campanha corresponde à busca.
          </div>
        ) : (
          <ul className="divide-y">
            {visible.map((c) => {
              const checked = selectedSet.has(c.campaign_id);
              const userAlreadyMember = highlightUserId
                ? c.members.some((m) => m.user_id === highlightUserId)
                : false;
              return (
                <li
                  key={c.campaign_id}
                  className={
                    'flex cursor-pointer items-center gap-3 px-3 py-2 text-sm transition-colors hover:bg-muted/40 ' +
                    (checked ? 'bg-primary/5' : '')
                  }
                  onClick={() => toggle(c.campaign_id)}
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() => toggle(c.campaign_id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate font-medium">
                        {c.campaign_name || '(sem nome)'}
                      </span>
                      {userAlreadyMember && (
                        <Badge
                          variant="success"
                          className="shrink-0 px-1.5 py-0 text-[10px] font-normal"
                        >
                          já vinculado
                        </Badge>
                      )}
                    </div>
                    <div className="truncate font-mono text-[10px] text-muted-foreground">
                      {c.campaign_id}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {c.members.length > 0 && (
                      <Badge
                        variant="secondary"
                        className="px-1.5 py-0 text-[10px] font-normal"
                      >
                        <Users className="mr-1 h-2.5 w-2.5" />
                        {c.members.length}
                      </Badge>
                    )}
                    {c.active_commissions.length > 0 && (
                      <Badge
                        variant="outline"
                        className="border-success/30 px-1.5 py-0 text-[10px] font-normal text-success"
                      >
                        %
                      </Badge>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </ScrollArea>
    </div>
  );
}
