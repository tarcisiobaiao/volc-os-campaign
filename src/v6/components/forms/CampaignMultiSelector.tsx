/**
 * v6 RBAC — CampaignMultiSelector
 *
 * Versão multi-seleção do CampaignSelector. Permite selecionar
 * múltiplas campanhas de uma vez ao vincular um usuário, com
 * atalhos premium para "selecionar todas" e "desmarcar todas"
 * (respeitando o filtro de busca ativo).
 *
 * Regras de UX:
 *   - O select-all opera sobre o conjunto **visível** (após busca),
 *     não sobre o catálogo todo — evita "ops, selecionei tudo".
 *   - Campanhas em que o usuário já está vinculado aparecem com
 *     badge "já vinculado" e, por padrão, são desabilitadas (não
 *     marcáveis) para evitar duplicatas silenciosas — a lógica de
 *     skip fica no submit.
 *   - Counter no trigger (N selecionadas) + chips removíveis abaixo.
 */
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { ChevronsUpDown, X, CheckSquare, Square } from 'lucide-react';
import type { CampaignWithContext } from '@/v6/types/v6';

interface CampaignMultiSelectorProps {
  campaigns: CampaignWithContext[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Filtra apenas campanhas deste projeto. Se null/undefined, mostra todas. */
  projectId?: number | null;
  /**
   * Se fornecido, destaca campanhas em que este usuário já tem
   * vínculo. Essas campanhas ficam desabilitadas (não marcáveis).
   */
  highlightUserId?: string;
}

export function CampaignMultiSelector({
  campaigns,
  value,
  onChange,
  placeholder = 'Selecione campanhas',
  disabled,
  projectId,
  highlightUserId,
}: CampaignMultiSelectorProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  // Campanhas filtradas por projeto
  const scoped = useMemo(() => {
    if (projectId == null) return campaigns;
    return campaigns.filter((c) => c.project_id === projectId);
  }, [campaigns, projectId]);

  // Flag "já vinculado" por campanha
  const alreadyLinkedIds = useMemo(() => {
    if (!highlightUserId) return new Set<string>();
    return new Set(
      scoped
        .filter((c) => c.members.some((m) => m.user_id === highlightUserId))
        .map((c) => c.campaign_id)
    );
  }, [scoped, highlightUserId]);

  // Campanhas visíveis (após o filtro de busca textual)
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return scoped;
    return scoped.filter((c) => {
      const hay = `${c.campaign_name ?? ''} ${c.campaign_id}`.toLowerCase();
      return hay.includes(q);
    });
  }, [scoped, search]);

  // IDs selecionáveis entre os visíveis (ignora "já vinculados")
  const selectableVisibleIds = useMemo(
    () =>
      visible
        .filter((c) => !alreadyLinkedIds.has(c.campaign_id))
        .map((c) => c.campaign_id),
    [visible, alreadyLinkedIds]
  );

  const selectedSet = useMemo(() => new Set(value), [value]);

  const visibleSelectedCount = useMemo(
    () => selectableVisibleIds.filter((id) => selectedSet.has(id)).length,
    [selectableVisibleIds, selectedSet]
  );

  const allVisibleSelected =
    selectableVisibleIds.length > 0 &&
    visibleSelectedCount === selectableVisibleIds.length;
  const someVisibleSelected =
    visibleSelectedCount > 0 && !allVisibleSelected;

  const toggleOne = (id: string) => {
    if (selectedSet.has(id)) {
      onChange(value.filter((v) => v !== id));
    } else {
      onChange([...value, id]);
    }
  };

  const selectAllVisible = () => {
    const merged = new Set(value);
    selectableVisibleIds.forEach((id) => merged.add(id));
    onChange(Array.from(merged));
  };

  const clearVisible = () => {
    if (selectableVisibleIds.length === 0) return;
    const toRemove = new Set(selectableVisibleIds);
    onChange(value.filter((id) => !toRemove.has(id)));
  };

  const clearAll = () => onChange([]);

  const triggerDisabled = disabled || (projectId != null && scoped.length === 0);

  // Chips (badges) das selecionadas — mostra até 6 e colapsa o resto
  const selectedCampaigns = useMemo(() => {
    const map = new Map(scoped.map((c) => [c.campaign_id, c]));
    return value
      .map((id) => map.get(id))
      .filter((c): c is CampaignWithContext => Boolean(c));
  }, [scoped, value]);

  const MAX_CHIPS = 6;
  const visibleChips = selectedCampaigns.slice(0, MAX_CHIPS);
  const hiddenChipCount = Math.max(0, selectedCampaigns.length - MAX_CHIPS);

  return (
    <div className="space-y-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={triggerDisabled}
            className="w-full justify-between font-normal"
          >
            {value.length > 0 ? (
              <span className="flex min-w-0 flex-1 items-center gap-2">
                <Badge
                  variant="default"
                  className="shrink-0 px-1.5 py-0 text-[10px] font-medium"
                >
                  {value.length}
                </Badge>
                <span className="truncate text-sm">
                  {value.length === 1
                    ? '1 campanha selecionada'
                    : `${value.length} campanhas selecionadas`}
                </span>
              </span>
            ) : (
              <span className="text-muted-foreground">
                {projectId != null && scoped.length === 0
                  ? 'Nenhuma campanha neste projeto'
                  : placeholder}
              </span>
            )}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-[var(--radix-popover-trigger-width)] p-0"
          align="start"
        >
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Buscar campanha..."
              value={search}
              onValueChange={setSearch}
            />

            {/* Header premium: select-all / clear sobre os visíveis */}
            <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-2 py-1.5">
              <button
                type="button"
                onClick={
                  allVisibleSelected ? clearVisible : selectAllVisible
                }
                disabled={selectableVisibleIds.length === 0}
                className={cn(
                  'flex items-center gap-1.5 rounded px-1.5 py-1 text-xs font-medium transition-colors',
                  'hover:bg-background disabled:cursor-not-allowed disabled:opacity-50'
                )}
              >
                {allVisibleSelected ? (
                  <CheckSquare className="h-3.5 w-3.5 text-primary" />
                ) : someVisibleSelected ? (
                  <div className="flex h-3.5 w-3.5 items-center justify-center rounded-[2px] border border-primary bg-primary/20">
                    <div className="h-1.5 w-1.5 rounded-[1px] bg-primary" />
                  </div>
                ) : (
                  <Square className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <span>
                  {allVisibleSelected
                    ? 'Desmarcar todas'
                    : search.trim()
                    ? `Selecionar todas (${selectableVisibleIds.length})`
                    : `Selecionar todas (${selectableVisibleIds.length})`}
                </span>
              </button>
              {value.length > 0 && (
                <button
                  type="button"
                  onClick={clearAll}
                  className="flex items-center gap-1 rounded px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-background hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                  Limpar tudo ({value.length})
                </button>
              )}
            </div>

            <CommandList className="max-h-72">
              <CommandEmpty>Nenhuma campanha encontrada.</CommandEmpty>
              <CommandGroup>
                {visible.map((c) => {
                  const isSelected = selectedSet.has(c.campaign_id);
                  const isAlready = alreadyLinkedIds.has(c.campaign_id);
                  return (
                    <CommandItem
                      key={c.campaign_id}
                      value={c.campaign_id}
                      onSelect={() => {
                        if (isAlready) return;
                        toggleOne(c.campaign_id);
                      }}
                      className={cn(
                        'gap-2',
                        isAlready && 'cursor-not-allowed opacity-60'
                      )}
                    >
                      <Checkbox
                        checked={isSelected}
                        disabled={isAlready}
                        className="pointer-events-none shrink-0"
                        aria-label={`Selecionar ${c.campaign_name ?? c.campaign_id}`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate text-sm">
                            {c.campaign_name || '(sem nome)'}
                          </span>
                          {isAlready && (
                            <Badge
                              variant="success"
                              className="shrink-0 px-1.5 py-0 text-[10px] font-normal"
                            >
                              já vinculado
                            </Badge>
                          )}
                        </div>
                        <div className="font-mono text-[10px] text-muted-foreground">
                          {c.campaign_id}
                        </div>
                      </div>
                      {c.members.length > 0 && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Badge
                              variant="secondary"
                              className="shrink-0 px-1.5 py-0 text-[10px] font-normal"
                            >
                              {c.members.length}
                            </Badge>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">
                            <div className="space-y-1 text-xs">
                              {c.members.slice(0, 8).map((m) => (
                                <div key={`${m.user_id}-${m.role_id}`}>
                                  {m.user_name || m.user_email.split('@')[0]}
                                  <span className="ml-1 text-muted-foreground">
                                    {m.role_code}
                                  </span>
                                </div>
                              ))}
                              {c.members.length > 8 && (
                                <div className="text-muted-foreground">
                                  +{c.members.length - 8}
                                </div>
                              )}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {/* Chips das selecionadas */}
      {selectedCampaigns.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {visibleChips.map((c) => (
            <Badge
              key={c.campaign_id}
              variant="secondary"
              className="group gap-1 pl-2 pr-1 font-normal"
            >
              <span className="max-w-[180px] truncate">
                {c.campaign_name || c.campaign_id}
              </span>
              <button
                type="button"
                onClick={() => toggleOne(c.campaign_id)}
                className="rounded-sm p-0.5 opacity-60 transition-opacity hover:bg-background hover:opacity-100"
                aria-label={`Remover ${c.campaign_name ?? c.campaign_id}`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {hiddenChipCount > 0 && (
            <Badge variant="outline" className="font-normal">
              +{hiddenChipCount}
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}
