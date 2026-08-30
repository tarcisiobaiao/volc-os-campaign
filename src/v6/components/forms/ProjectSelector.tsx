/**
 * v6 RBAC — ProjectSelector
 *
 * Combobox de projetos/sites. Mais compacto que o CampaignSelector
 * porque o catálogo é menor (~47 projetos hoje) e cada item carrega
 * menos contexto. Mostra: nome, domínio (quando disponível) e a
 * quantidade de campanhas do projeto.
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
import { Check, ChevronsUpDown } from 'lucide-react';
import type { ProjectLite } from '@/v6/types/v6';

interface ProjectSelectorProps {
  projects: ProjectLite[];
  value: number | null;
  onChange: (value: number | null) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function ProjectSelector({
  projects,
  value,
  onChange,
  placeholder = 'Selecione um projeto',
  disabled,
}: ProjectSelectorProps) {
  const [open, setOpen] = useState(false);

  const selected = useMemo(
    () => projects.find((p) => p.id === value) ?? null,
    [projects, value]
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className="w-full justify-between font-normal"
        >
          {selected ? (
            <span className="flex min-w-0 flex-1 items-center gap-2">
              <span className="truncate">{selected.name}</span>
              {selected.domain && (
                <span className="truncate text-xs text-muted-foreground">
                  · {selected.domain}
                </span>
              )}
            </span>
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
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
            const p = projects.find((x) => String(x.id) === itemValue);
            if (!p) return 0;
            const haystack = `${p.name} ${p.domain ?? ''}`.toLowerCase();
            return haystack.includes(search.toLowerCase()) ? 1 : 0;
          }}
        >
          <CommandInput placeholder="Buscar projeto..." />
          <CommandList className="max-h-72">
            <CommandEmpty>Nenhum projeto encontrado.</CommandEmpty>
            <CommandGroup>
              {projects.map((p) => {
                const isSelected = p.id === value;
                return (
                  <CommandItem
                    key={p.id}
                    value={String(p.id)}
                    onSelect={(v) => {
                      onChange(Number(v));
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
                      <div className="truncate text-sm font-medium">{p.name}</div>
                      {p.domain && (
                        <div className="truncate text-[11px] text-muted-foreground">
                          {p.domain}
                        </div>
                      )}
                    </div>
                    <Badge variant="secondary" className="shrink-0 text-[10px]">
                      {p.campaigns_count} camp.
                    </Badge>
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
