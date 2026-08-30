/**
 * v6 RBAC — CampaignSelector
 *
 * Combobox de campanhas com contexto enxuto (membros + comissões
 * vigentes). Pode ser filtrado por projeto via prop `projectId`.
 *
 * Princípio: campanha pode ter múltiplos membros simultaneamente.
 * Esta UI nunca bloqueia — só dá contexto para o admin.
 */
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import { Check, ChevronsUpDown, Info } from 'lucide-react';
import type { CampaignWithContext } from '@/v6/types/v6';

interface CampaignSelectorProps {
  campaigns: CampaignWithContext[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Filtra apenas campanhas deste projeto. Se null/undefined, mostra todas. */
  projectId?: number | null;
  /**
   * Se fornecido, destaca quais campanhas já têm vínculo deste
   * usuário (badge "você"), apenas como informação. Não bloqueia.
   */
  highlightUserId?: string;
}

export function CampaignSelector({
  campaigns,
  value,
  onChange,
  placeholder = 'Selecione uma campanha',
  disabled,
  projectId,
  highlightUserId,
}: CampaignSelectorProps) {
  const [open, setOpen] = useState(false);

  const visible = useMemo(() => {
    if (projectId == null) return campaigns;
    return campaigns.filter((c) => c.project_id === projectId);
  }, [campaigns, projectId]);

  const selected = useMemo(
    () => visible.find((c) => c.campaign_id === value) ?? null,
    [visible, value]
  );

  const triggerDisabled = disabled || (projectId != null && visible.length === 0);

  return (
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
          {selected ? (
            <span className="flex min-w-0 flex-1 items-center gap-2">
              <span className="truncate">
                {selected.campaign_name || '(sem nome)'}
              </span>
              {selected.members.length > 0 && (
                <Badge
                  variant="secondary"
                  className="shrink-0 px-1.5 py-0 text-[10px] font-normal"
                >
                  {selected.members.length}
                </Badge>
              )}
            </span>
          ) : (
            <span className="text-muted-foreground">
              {projectId != null && visible.length === 0
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
        <Command
          filter={(itemValue, search) => {
            const c = visible.find((x) => x.campaign_id === itemValue);
            if (!c) return 0;
            const haystack = `${c.campaign_name ?? ''} ${c.campaign_id}`.toLowerCase();
            return haystack.includes(search.toLowerCase()) ? 1 : 0;
          }}
        >
          <CommandInput placeholder="Buscar campanha..." />
          <CommandList className="max-h-72">
            <CommandEmpty>Nenhuma campanha encontrada.</CommandEmpty>
            <CommandGroup>
              {visible.map((c) => {
                const isSelected = c.campaign_id === value;
                const userAlreadyMember = highlightUserId
                  ? c.members.some((m) => m.user_id === highlightUserId)
                  : false;
                return (
                  <CommandItem
                    key={c.campaign_id}
                    value={c.campaign_id}
                    onSelect={(v) => {
                      onChange(v);
                      setOpen(false);
                    }}
                    className="gap-2"
                  >
                    <Check
                      className={cn(
                        'h-4 w-4 shrink-0',
                        isSelected ? 'opacity-100' : 'opacity-0'
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-sm">
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
                      <div className="font-mono text-[10px] text-muted-foreground">
                        {c.campaign_id}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {c.members.length > 0 && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Badge
                              variant="secondary"
                              className="px-1.5 py-0 text-[10px] font-normal"
                            >
                              {c.members.length} membro{c.members.length > 1 ? 's' : ''}
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
                      {c.active_commissions.length > 0 && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-success/15 text-success">
                              <Info className="h-2.5 w-2.5" />
                            </span>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">
                            <div className="space-y-1 text-xs">
                              <div className="font-medium">Comissões vigentes</div>
                              {c.active_commissions.slice(0, 6).map((cc) => (
                                <div key={cc.user_id}>
                                  {cc.user_email.split('@')[0]} · {cc.percentage}%
                                </div>
                              ))}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
