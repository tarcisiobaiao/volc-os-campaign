import { useState } from 'react';
import { Search, ChevronsUpDown, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Command, CommandInput, CommandItem, CommandList, CommandEmpty } from '@/components/ui/command';
import type { AtivoCriacaoMeta } from '@/lib/pautadorApi';

export function SelecionarAtivoMeta({ id, items, value, onChange, disabled }: {
  id: string; items: AtivoCriacaoMeta[]; value: string; onChange: (ref: string) => void; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const normalizar = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const encontrados = items.filter(item => normalizar(item.nome || '').includes(normalizar(q)));
  const selected = items.find(item => item.referencia_opaca === value);
  return <Popover open={open} onOpenChange={setOpen}><PopoverTrigger asChild>
    <Button type="button" id={id} variant="outline" role="combobox" aria-expanded={open} disabled={disabled}
      className="min-h-11 w-full justify-between text-left font-normal"><Search className="mr-2 h-4 w-4 shrink-0" aria-hidden /><span className="truncate">{selected?.nome || (value ? 'Peça selecionada · atualize o catálogo' : 'Buscar imagem pelo nome')}</span><ChevronsUpDown className="ml-2 h-4 w-4 shrink-0" aria-hidden /></Button>
    </PopoverTrigger><PopoverContent align="start" className="w-[var(--radix-popover-trigger-width)] min-w-64 p-0">
      <Command shouldFilter={false} label="Buscar criativo pelo nome"><CommandInput value={q} onValueChange={setQ} placeholder="Nome do criativo…" aria-label="Buscar criativo pelo nome" />
        <CommandList><CommandEmpty>Nenhuma peça encontrada nesta consulta.</CommandEmpty>
          {encontrados.slice(0, 60).map(item => <CommandItem key={item.referencia_opaca} value={item.referencia_opaca} disabled={disabled} onSelect={() => { if (disabled) return; onChange(item.referencia_opaca); setOpen(false); }}>
            <span className="min-w-0 flex-1 truncate">{item.nome}{item.largura && item.altura ? ` · ${item.largura}×${item.altura}` : ''}</span>
            {value === item.referencia_opaca && <Check className="ml-2 h-4 w-4" aria-hidden />}
          </CommandItem>)}
        </CommandList>
        {encontrados.length > 60 && <p className="border-t border-border p-3 text-xs text-muted-foreground">{encontrados.length} resultados. Refine o nome para localizar a peça.</p>}
      </Command>
    </PopoverContent></Popover>;
}
