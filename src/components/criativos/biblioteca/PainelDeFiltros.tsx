/**
 * Os filtros da biblioteca, com todo filtro ativo visível e removível.
 *
 * ## Por que `<select>` nativo
 *
 * Porque ele já traz teclado, busca por letra, leitura de rótulo, comportamento
 * de toque do sistema e formulário. Um menu caseiro acerta a aparência e erra
 * pelo menos um desses quatro, e o que se perde é sempre para quem menos pode
 * perder.
 *
 * ## Por que os filtros ativos aparecem como fichas removíveis
 *
 * Porque um filtro que a tela aplica e não mostra é a forma mais barata de
 * fazer alguém concluir que um ativo sumiu do sistema.
 */
import React from 'react';
import { Search, X } from 'lucide-react';

import { cn } from '@/lib/utils';
import {
  ROTULO_DO_ESTADO_FILTRAVEL,
  filtrosAtivos,
  removerFiltro,
  type FiltrosDaBiblioteca,
} from '@/components/criativos/biblioteca/filtros';
import { DESTINOS } from '@/components/criativos/briefing/contrato';
import type { BrandPack, KindDeMaster } from '@/types/criativos';

const CONTROLE = cn(
  'h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground',
  'transition-colors duration-150 ease-out',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
);

const KINDS: { valor: KindDeMaster; rotulo: string }[] = [
  { valor: 'imagem', rotulo: 'Imagem' },
  { valor: 'video', rotulo: 'Vídeo' },
  { valor: 'audio', rotulo: 'Áudio' },
  { valor: 'texto', rotulo: 'Texto' },
  { valor: 'logo', rotulo: 'Logo' },
  { valor: 'auxiliar', rotulo: 'Auxiliar' },
];

export const PainelDeFiltros: React.FC<{
  filtros: FiltrosDaBiblioteca;
  aoMudar: (f: FiltrosDaBiblioteca) => void;
  brandPacks: BrandPack[];
  nomeDoPack: (id: string) => string;
  /** A contagem em uma frase: subconjunto visível e universo. */
  contagem: string;
}> = ({ filtros, aoMudar, brandPacks, nomeDoPack, contagem }) => {
  const ativos = filtrosAtivos(filtros, nomeDoPack);
  const mudar = <K extends keyof FiltrosDaBiblioteca>(
    chave: K,
    valor: FiltrosDaBiblioteca[K],
  ) => aoMudar({ ...filtros, [chave]: valor });

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="lg:col-span-2">
          <label htmlFor="biblioteca-busca" className="block text-[13px] font-medium text-foreground">
            Buscar
          </label>
          <div className="relative mt-1.5">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <input
              id="biblioteca-busca"
              type="search"
              className={cn(CONTROLE, 'pl-9')}
              value={filtros.busca}
              onChange={(e) => mudar('busca', e.target.value)}
            />
          </div>
        </div>

        <div>
          <label htmlFor="biblioteca-kind" className="block text-[13px] font-medium text-foreground">
            Tipo
          </label>
          <select
            id="biblioteca-kind"
            className={cn(CONTROLE, 'mt-1.5')}
            value={filtros.kind}
            onChange={(e) => mudar('kind', e.target.value as FiltrosDaBiblioteca['kind'])}
          >
            <option value="">Todos os tipos</option>
            {KINDS.map((k) => (
              <option key={k.valor} value={k.valor}>
                {k.rotulo}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="biblioteca-estado" className="block text-[13px] font-medium text-foreground">
            Estado da revisão
          </label>
          <select
            id="biblioteca-estado"
            className={cn(CONTROLE, 'mt-1.5')}
            value={filtros.estado}
            onChange={(e) => mudar('estado', e.target.value as FiltrosDaBiblioteca['estado'])}
          >
            <option value="">Todos os estados</option>
            {(Object.keys(ROTULO_DO_ESTADO_FILTRAVEL) as (keyof typeof ROTULO_DO_ESTADO_FILTRAVEL)[]).map(
              (chave) => (
                <option key={chave} value={chave}>
                  {ROTULO_DO_ESTADO_FILTRAVEL[chave]}
                </option>
              ),
            )}
          </select>
        </div>

        <div>
          <label htmlFor="biblioteca-pack" className="block text-[13px] font-medium text-foreground">
            Brand pack
          </label>
          <select
            id="biblioteca-pack"
            className={cn(CONTROLE, 'mt-1.5')}
            value={filtros.brandPack}
            onChange={(e) => mudar('brandPack', e.target.value)}
          >
            <option value="">Todos os packs</option>
            {brandPacks.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}, versão {p.versao}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="biblioteca-destino" className="block text-[13px] font-medium text-foreground">
            Destino pretendido
          </label>
          <select
            id="biblioteca-destino"
            className={cn(CONTROLE, 'mt-1.5')}
            value={filtros.destino}
            onChange={(e) => mudar('destino', e.target.value)}
          >
            <option value="">Todos os destinos</option>
            {DESTINOS.map((d) => (
              <option key={d.destino} value={d.destino}>
                {d.rotulo}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="biblioteca-desde" className="block text-[13px] font-medium text-foreground">
            Criado a partir de
          </label>
          <input
            id="biblioteca-desde"
            type="date"
            className={cn(CONTROLE, 'mt-1.5')}
            value={filtros.desde}
            onChange={(e) => mudar('desde', e.target.value)}
          />
        </div>

        <div>
          <label htmlFor="biblioteca-ate" className="block text-[13px] font-medium text-foreground">
            Criado até
          </label>
          <input
            id="biblioteca-ate"
            type="date"
            className={cn(CONTROLE, 'mt-1.5')}
            value={filtros.ate}
            onChange={(e) => mudar('ate', e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[13px] text-foreground" role="status">
          {contagem}
        </p>
        {ativos.map((f) => (
          <button
            key={f.chave}
            type="button"
            onClick={() => aoMudar(removerFiltro(filtros, f.chave))}
            className={cn(
              'inline-flex min-h-7 items-center gap-1.5 rounded-full border border-border bg-muted/60 px-2.5 text-[12px] text-foreground',
              'transition-colors duration-150 ease-out hover:border-destructive/50 hover:bg-destructive/[0.08]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            )}
          >
            <span className="truncate">
              {f.rotulo}: {f.valor}
            </span>
            <X className="h-3 w-3 shrink-0" aria-hidden />
            <span className="sr-only">Remover o filtro {f.rotulo}</span>
          </button>
        ))}
      </div>
    </div>
  );
};
