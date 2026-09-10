import React from 'react';
import { Check, ChevronsUpDown, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { cn } from '@/lib/utils';

// ISO 3166-1 alpha-2. Names are localized by the browser's CLDR data.
// This list is geographic, not a claim that Meta delivers in every territory.
const ISO2 = 'AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW'.split(' ');
const nomes = new Intl.DisplayNames(['pt-BR'], { type: 'region' });
export const PAISES_META = ISO2.map((codigo) => ({
  codigo,
  nome: nomes.of(codigo) || codigo,
  bandeira: String.fromCodePoint(...[...codigo].map((letra) => letra.charCodeAt(0) + 127397)),
})).sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));

export function SeletorDePaises({ id, selecionados, impedidos = [], onChange }: {
  id: string;
  selecionados: string[];
  impedidos?: string[];
  onChange: (codigos: string[]) => void;
}) {
  const [aberto, setAberto] = React.useState(false);
  const alternar = (codigo: string) => onChange(selecionados.includes(codigo)
    ? selecionados.filter((pais) => pais !== codigo)
    : [...selecionados, codigo]);
  return <div className="space-y-2">
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger asChild>
        <Button id={id} type="button" variant="outline" role="combobox" aria-expanded={aberto}
          className="h-auto min-h-12 w-full justify-between bg-background px-3 py-3 text-left font-normal">
          {selecionados.length ? `${selecionados.length} ${selecionados.length === 1 ? 'país selecionado' : 'países selecionados'}` : 'Buscar países…'}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[var(--radix-popover-trigger-width)] min-w-64 p-0">
        <Command>
          <CommandInput placeholder="Nome do país ou código…" aria-label="Buscar país" />
          <CommandList aria-label="Países disponíveis">
            <CommandEmpty>Nenhum país encontrado.</CommandEmpty>
            {PAISES_META.map(({ codigo, nome, bandeira }) => <CommandItem key={codigo}
              value={`${nome.normalize('NFD').replace(/[\u0300-\u036f]/g, '')} ${nome} ${codigo}`}
              disabled={impedidos.includes(codigo) && !selecionados.includes(codigo)}
              onSelect={() => alternar(codigo)} className="gap-2 py-2.5">
              <span aria-hidden>{bandeira}</span><span className="flex-1">{nome}</span>
              <span className="text-xs text-muted-foreground">{codigo}</span>
              <Check aria-hidden className={cn('h-4 w-4', selecionados.includes(codigo) ? 'opacity-100' : 'opacity-0')} />
            </CommandItem>)}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
    {selecionados.length > 0 && <div className="flex flex-wrap gap-2" aria-label="Países selecionados">
      {selecionados.map((codigo) => {
        const pais = PAISES_META.find((item) => item.codigo === codigo);
        return <button type="button" key={codigo} onClick={() => alternar(codigo)}
          aria-label={`Remover ${pais?.nome || codigo}`}
          className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-sm text-foreground transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <span aria-hidden>{pais?.bandeira}</span>{pais?.nome || codigo}<X className="h-3.5 w-3.5" aria-hidden />
        </button>;
      })}
    </div>}
  </div>;
}
