import React, { useMemo, useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command';
import { Button } from '@/components/ui/button';
import { Check, ChevronsUpDown, Globe2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PAUTADOR_COUNTRIES, searchCountries } from '@/data/pautadorCountries';
import type { PautadorCountryData } from '@/data/pautadorCountries';

const TIER_LABEL: Record<string, string> = {
  high_value: 'Alto valor',
  medium_value: 'Valor médio',
  volume_play: 'Volume',
};

interface CountryComboboxProps {
  /** selected country_name (PT-BR) */
  value: string;
  onChange: (countryName: string, country: PautadorCountryData) => void;
  className?: string;
}

export const CountryCombobox: React.FC<CountryComboboxProps> = ({ value, onChange, className }) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const selected = useMemo(
    () => PAUTADOR_COUNTRIES.find((c) => c.country_name === value),
    [value],
  );
  const results = useMemo(() => searchCountries(query).slice(0, 100), [query]);

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQuery(''); }}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn('w-[260px] justify-between', className)}
        >
          <span className="flex items-center gap-2 truncate">
            <Globe2 className="h-4 w-4 text-muted-foreground shrink-0" />
            {selected ? (
              <span className="truncate">{selected.flag_emoji} {selected.country_name}</span>
            ) : (
              <span className="text-muted-foreground">Selecione um país</span>
            )}
          </span>
          <ChevronsUpDown className="h-4 w-4 opacity-50 shrink-0" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[320px] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Buscar país (nome, ISO, alias)…"
            value={query}
            onValueChange={setQuery}
          />
          <CommandList className="max-h-[320px]">
            <CommandEmpty>Nenhum país encontrado.</CommandEmpty>
            <CommandGroup>
              {results.map((c) => (
                <CommandItem
                  key={c.country_code}
                  value={c.country_code}
                  onSelect={() => { onChange(c.country_name, c); setOpen(false); setQuery(''); }}
                >
                  <Check className={cn('mr-2 h-4 w-4', selected?.country_code === c.country_code ? 'opacity-100' : 'opacity-0')} />
                  <span className="mr-2">{c.flag_emoji}</span>
                  <span className="flex-1 truncate">
                    {c.country_name}
                    <span className="text-[10px] text-muted-foreground ml-1">{c.country_code}</span>
                  </span>
                  <span className="text-[10px] text-muted-foreground ml-2 shrink-0">{TIER_LABEL[c.market_tier]}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
};
