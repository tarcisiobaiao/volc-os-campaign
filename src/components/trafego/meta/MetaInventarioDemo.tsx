import React from 'react';
import { ArrowRight, CirclePause, CirclePlay, FileClock, Info, Plus, Search } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { NivelMeta } from '@/components/trafego/hub/contrato';
import { cn } from '@/lib/utils';

import { META_DEMO, ROTULOS_META, type ObjetoMetaDemo, type TipoMeta } from './modelo';

const estado = {
  ATIVO: { icone: CirclePlay, classe: 'border-success/25 bg-success/10 text-success', rotulo: 'Ativo' },
  PAUSADO: { icone: CirclePause, classe: 'border-border bg-muted/50 text-foreground', rotulo: 'Pausado' },
  RASCUNHO: { icone: FileClock, classe: 'border-warning/25 bg-warning/10 text-warning', rotulo: 'Rascunho' },
};

const Estado: React.FC<{ valor: ObjetoMetaDemo['status'] }> = ({ valor }) => {
  const config = estado[valor];
  const Icone = config.icone;
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs font-medium', config.classe)}>
      <Icone className="h-3.5 w-3.5" aria-hidden /> {config.rotulo}
    </span>
  );
};

const Linha: React.FC<{ objeto: ObjetoMetaDemo; tipo: TipoMeta }> = ({ objeto, tipo }) => (
  <tr className="border-b border-border last:border-0 hover:bg-muted/25">
    <td className="px-4 py-3 align-top"><Estado valor={objeto.status} /></td>
    <td className="min-w-[280px] px-4 py-3 align-top">
      <Link
        to={`/trafego/meta/${tipo}/${objeto.id}?modo=demo`}
        className="group inline-flex max-w-full items-start gap-2 font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="truncate">{objeto.nome}</span>
        <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-150 group-hover:translate-x-0.5" aria-hidden />
      </Link>
      <p className="mt-1 truncate text-xs text-muted-foreground">
        {objeto.pai ? `${objeto.pai} · ` : ''}{objeto.detalhe ?? 'Meta Ads'}
      </p>
    </td>
    <td className="px-4 py-3 align-top text-sm text-foreground">{objeto.objetivo ?? objeto.entrega ?? '—'}</td>
    <td className="px-4 py-3 text-right align-top text-sm font-medium tabular-nums text-foreground">{objeto.orcamento ?? '—'}</td>
    <td className="px-4 py-3 text-right align-top text-sm tabular-nums text-foreground">{objeto.resultado ?? '—'}</td>
    <td className="px-4 py-3 text-right align-top text-sm tabular-nums text-foreground">{objeto.custo ?? '—'}</td>
  </tr>
);

export const MetaInventarioDemo: React.FC<{ nivel: NivelMeta }> = ({ nivel }) => {
  const tipo = nivel as TipoMeta;
  const [busca, setBusca] = React.useState('');
  const objetos = META_DEMO[tipo].filter((objeto) =>
    objeto.nome.toLocaleLowerCase('pt-BR').includes(busca.trim().toLocaleLowerCase('pt-BR')),
  );
  const rotulo = ROTULOS_META[tipo];

  return (
    <section aria-label={`Inventário demonstrativo de ${rotulo.plural}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">Modelo navegável de {rotulo.plural}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Estrutura v26 pronta para receber o read model; valores abaixo são fictícios.
          </p>
        </div>
        <Button asChild variant="outline" className="min-h-10 bg-card">
          <Link to="/trafego/meta/nova?modo=demo">
            <Plus className="mr-2 h-4 w-4" aria-hidden /> Explorar criação
          </Link>
        </Button>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-3 rounded-md border border-verified/25 bg-verified/5 px-3 py-2.5 text-xs text-foreground">
        <Info className="h-4 w-4 shrink-0 text-verified" aria-hidden />
        <strong>Demonstração inequívoca.</strong>
        <span className="text-muted-foreground">
          Nenhum nome, status, orçamento ou desempenho desta tabela veio da Meta.
        </span>
      </div>

      <div className="mb-3 max-w-sm">
        <label htmlFor="busca-meta-demo" className="sr-only">Buscar {rotulo.plural}</label>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            id="busca-meta-demo"
            value={busca}
            onChange={(evento) => setBusca(evento.target.value)}
            className="pl-9"
            placeholder={`Buscar ${rotulo.singular}`}
          />
        </div>
      </div>

      <div className="overflow-hidden rounded-md border border-border bg-card shadow-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] border-collapse text-left">
            <thead className="bg-muted/60 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Estado</th>
                <th className="px-4 py-3">{rotulo.singular}</th>
                <th className="px-4 py-3">{tipo === 'campanhas' ? 'Objetivo' : 'Entrega'}</th>
                <th className="px-4 py-3 text-right">Orçamento</th>
                <th className="px-4 py-3 text-right">Resultado</th>
                <th className="px-4 py-3 text-right">Custo</th>
              </tr>
            </thead>
            <tbody>
              {objetos.map((objeto) => <Linha key={objeto.id} objeto={objeto} tipo={tipo} />)}
            </tbody>
          </table>
        </div>
        {!objetos.length && (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">
            Nenhum {rotulo.singular} deste cenário corresponde à busca.
          </div>
        )}
      </div>
      <p className="mt-2 text-right text-[11px] text-muted-foreground">
        cenário demonstrativo · sem leitura externa · atualizado ao carregar esta interface
      </p>
    </section>
  );
};

export default MetaInventarioDemo;
