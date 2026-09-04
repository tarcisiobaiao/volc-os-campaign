import React, { useMemo, useState } from 'react';
import { ArrowLeft, BarChart3, Circle, FolderOpen, Info, Search, Settings } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { SeletorRedeCampanhas, type RedeDeCampanhas } from '@/components/campaign/SeletorRedeCampanhas';
import { IdentidadeDeCanal } from '@/components/trafego/hub/IdentidadeDeCanal';
import { META_DEMO, META_INSIGHTS_DEMO, type ObjetoMetaDemo } from '@/components/trafego/meta/modelo';
import { Layout } from '@/components/layout/Layout';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

interface Props {
  onNetworkChange: (rede: RedeDeCampanhas) => void;
}

const moeda = (valor: number | null) => valor === null
  ? 'Não medido'
  : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(valor);

const Estado: React.FC<{ valor: ObjetoMetaDemo['status'] }> = ({ valor }) => {
  if (valor === 'ATIVO') return <Badge variant="success"><Circle className="h-2 w-2 fill-current" aria-hidden />Ativa</Badge>;
  if (valor === 'PAUSADO') return <Badge variant="outline"><Circle className="h-2 w-2 fill-current" aria-hidden />Pausada</Badge>;
  return <Badge variant="warning"><Circle className="h-2 w-2 fill-current" aria-hidden />Rascunho</Badge>;
};

export const MetaCampaignsSettingsDemo: React.FC<Props> = ({ onNetworkChange }) => {
  const navigate = useNavigate();
  const [busca, setBusca] = useState('');
  const campanhas = useMemo(() => META_DEMO.campanhas.filter((campanha) =>
    campanha.nome.toLocaleLowerCase('pt-BR').includes(busca.toLocaleLowerCase('pt-BR')),
  ), [busca]);

  return (
    <Layout>
      <main className="mx-auto max-w-7xl space-y-6 p-4 md:space-y-8 md:p-6">
        <header className="space-y-4">
          <div className="flex items-start gap-3">
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="shrink-0 gap-2">
              <ArrowLeft className="h-4 w-4" aria-hidden />Voltar
            </Button>
            <div className="min-w-0 flex-1">
              <div className="kicker mb-2 flex items-center gap-2">
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary"><Settings className="h-3 w-3" aria-hidden /></span>
                Configurações · Campanhas
              </div>
              <h1 className="font-display text-[1.7rem] font-bold leading-[1.05] tracking-tight md:text-4xl">Campanhas</h1>
              <div className="aurora-rule mt-3 w-16" aria-hidden />
              <p className="mt-3 text-sm text-muted-foreground md:text-base">A mesma visão financeira, separada pela origem da mídia.</p>
            </div>
          </div>
          <SeletorRedeCampanhas rede="meta" onChange={onNetworkChange} />
        </header>

        <div className="flex items-start gap-2 rounded-md border border-verified/25 bg-verified/5 px-3 py-2.5 text-xs">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-verified" aria-hidden />
          <p><strong>Pré-visualização Meta.</strong> Estes três blocos são fictícios e servem para validar a experiência. Nenhum gasto, desempenho ou objeto veio de uma conta real.</p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="w-full max-w-md">
            <label htmlFor="busca-campanhas-meta" className="kicker mb-2 block">Buscar campanha Meta</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input id="busca-campanhas-meta" value={busca} onChange={(event) => setBusca(event.target.value)} className="pl-10" placeholder="Nome da campanha" />
            </div>
          </div>
          <Badge variant="outline"><span className="tabular-nums">{campanhas.length}</span> campanhas demonstrativas</Badge>
        </div>

        <section className="space-y-4" aria-label="Campanhas Meta demonstrativas">
          {campanhas.map((campanha, index) => {
            const leitura = META_INSIGHTS_DEMO[campanha.id];
            const lucro = leitura.gasto !== null && leitura.receitaGam !== null ? leitura.receitaGam - leitura.gasto : null;
            const retorno = leitura.gasto !== null && leitura.receitaGam !== null && leitura.gasto > 0
              ? ((leitura.receitaGam / leitura.gasto) - 1) * 100
              : null;
            return (
              <Link
                key={campanha.id}
                to={`/dashboard/campaign/${campanha.id}?rede=meta&modo=demo`}
                className="block text-inherit no-underline reveal"
                style={{ ['--i' as any]: Math.min(index, 8) }}
              >
                <Card className="relative cursor-pointer overflow-hidden p-6 shadow-card hover-lift">
                  <CardContent className="p-0">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h2 className="flex flex-wrap items-center gap-2 font-display text-lg font-semibold"><Estado valor={campanha.status} /><span>{campanha.nome}</span></h2>
                        <IdentidadeDeCanal rede="meta" canal="Tráfego" className="mt-2" />
                        <p className="mt-1 flex items-center gap-1 text-sm text-muted-foreground"><FolderOpen className="h-3 w-3" aria-hidden />Foco Genial · demonstração</p>
                      </div>
                      <span className="text-xs text-muted-foreground">abrir visão da campanha →</span>
                    </div>

                    <div className="mt-5 flex items-center gap-2">
                      <span className="rounded-md bg-primary/10 p-1.5 text-primary"><BarChart3 className="h-3.5 w-3.5" aria-hidden /></span>
                      <span className="kicker">Performance financeira · demonstração</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
                      <div className="border-t border-border pt-3"><p className="kicker">Gasto Meta</p><p className="mt-1 font-display text-lg font-bold tabular-nums">{moeda(leitura.gasto)}</p></div>
                      <div className="border-t border-border pt-3"><p className="kicker">Revenue GAM</p><p className="mt-1 font-display text-lg font-bold tabular-nums text-success">{moeda(leitura.receitaGam)}</p></div>
                      <div className="border-t border-border pt-3"><p className="kicker">ROAS excedente</p><p className="mt-1 font-display text-lg font-bold tabular-nums">{retorno === null ? 'Não medido' : `${retorno.toFixed(1)}%`}</p></div>
                      <div className="border-t border-border pt-3"><p className="kicker">Lucro bruto</p><p className="mt-1 font-display text-lg font-bold tabular-nums">{moeda(lucro)}</p></div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </section>
      </main>
    </Layout>
  );
};

export default MetaCampaignsSettingsDemo;
