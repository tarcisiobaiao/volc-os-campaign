import React, { useMemo, useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { ChevronsUpDown, Tags } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { PautadorNiche } from '@/types/pautadorEntity';

// Multiselect de nichos (R1) — mesma linguagem visual do CountryCombobox
// (popover + command). Seleção VAZIA é válida e significa "sem filtro de
// nicho" (comportamento diversificado de hoje) — nunca force uma seleção.
interface NicheMultiSelectProps {
  niches: PautadorNiche[];
  /** slugs selecionados; [] = sem filtro */
  value: string[];
  onChange: (slugs: string[]) => void;
  className?: string;
}

export const NicheMultiSelect: React.FC<NicheMultiSelectProps> = ({ niches, value, onChange, className }) => {
  const [open, setOpen] = useState(false);

  // só nichos ativos são selecionáveis (is_active pode vir ausente em seeds — trata como ativo)
  const active = useMemo(() => niches.filter((n) => n.is_active !== false), [niches]);
  const selectedSet = useMemo(() => new Set(value), [value]);

  const toggle = (slug: string) => {
    onChange(selectedSet.has(slug) ? value.filter((s) => s !== slug) : [...value, slug]);
  };

  const label = useMemo(() => {
    if (value.length === 0) return 'Nichos';
    if (value.length === 1) return active.find((n) => n.slug === value[0])?.label ?? value[0];
    return `${value.length} nichos`;
  }, [value, active]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn('w-[200px] justify-between font-normal', className)}
        >
          <span className="flex items-center gap-2 truncate">
            <Tags className="h-4 w-4 text-muted-foreground shrink-0" />
            <span className={cn('truncate', value.length === 0 && 'text-muted-foreground')}>{label}</span>
          </span>
          <ChevronsUpDown className="h-4 w-4 opacity-50 shrink-0" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Buscar nicho…" />
          <CommandList className="max-h-[280px]">
            <CommandEmpty>Nenhum nicho encontrado.</CommandEmpty>
            <CommandGroup>
              {active.map((n) => {
                const checked = selectedSet.has(n.slug);
                return (
                  <CommandItem key={n.slug} value={n.label} onSelect={() => toggle(n.slug)} className="gap-2">
                    <Checkbox checked={checked} className="pointer-events-none shrink-0" aria-label={`Selecionar ${n.label}`} />
                    <span className="flex-1 truncate">{n.label}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
          {value.length > 0 && (
            <div className="border-t p-1.5">
              <button
                type="button"
                onClick={() => onChange([])}
                className="w-full rounded px-2 py-1 text-left text-xs text-muted-foreground hover:bg-muted"
              >
                Limpar seleção ({value.length})
              </button>
            </div>
          )}
        </Command>
      </PopoverContent>
    </Popover>
  );
};
