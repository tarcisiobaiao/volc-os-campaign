import React from 'react';
import {
  ArrowLeft,
  BarChart3,
  CirclePause,
  CirclePlay,
  FileClock,
  GitBranch,
  History,
  Info,
  LockKeyhole,
  Megaphone,
  Settings2,
} from 'lucide-react';
import { Link, Navigate, useParams } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { MetaConfiguracaoLocal } from '@/components/trafego/meta/MetaConfiguracaoLocal';
import {
  META_DEMO,
  ROTULOS_META,
  objetoMetaDemo,
  type ObjetoMetaDemo,
  type TipoMeta,
} from '@/components/trafego/meta/modelo';

const TIPOS: TipoMeta[] = ['campanhas', 'conjuntos', 'anuncios', 'criativos'];

const Estado: React.FC<{ valor: ObjetoMetaDemo['status'] }> = ({ valor }) => {
  const config = valor === 'ATIVO'
    ? { variante: 'success' as const, icone: CirclePlay, texto: 'Ativo' }
    : valor === 'PAUSADO'
      ? { variante: 'outline' as const, icone: CirclePause, texto: 'Pausado' }
      : { variante: 'warning' as const, icone: FileClock, texto: 'Rascunho' };
  const Icone = config.icone;
  return <Badge variant={config.variante}><Icone className="h-3.5 w-3.5" aria-hidden />{config.texto}</Badge>;
};

function descendentes(objeto: ObjetoMetaDemo): ObjetoMetaDemo[] {
  const indice = TIPOS.indexOf(objeto.tipo);
  if (indice < 0 || indice === TIPOS.length - 1) return [];
  return META_DEMO[TIPOS[indice + 1]].filter((filho) => filho.paiId === objeto.id);
}

const Campo: React.FC<{ rotulo: string; valor: React.ReactNode; ajuda?: string }> = ({ rotulo, valor, ajuda }) => (
  <div className="min-w-0 border-b border-border py-3 last:border-0">
    <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{rotulo}</dt>
    <dd className="mt-1 text-sm font-medium text-foreground">{valor}</dd>
    {ajuda && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{ajuda}</p>}
  </div>
);

const Estrutura: React.FC<{ objeto: ObjetoMetaDemo }> = ({ objeto }) => {
  const filhos = descendentes(objeto);
  const proximoTipo = TIPOS[TIPOS.indexOf(objeto.tipo) + 1];
  return (
    <section aria-labelledby="estrutura-meta">
      <div className="mb-3 flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-primary" aria-hidden />
        <h2 id="estrutura-meta" className="font-display text-lg font-semibold">Estrutura subordinada</h2>
      </div>
      {filhos.length ? (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/60 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
              <tr><th className="px-4 py-2.5">Estado</th><th className="px-4 py-2.5">Nome</th><th className="px-4 py-2.5">Entrega</th><th className="px-4 py-2.5 text-right">Resultado</th></tr>
            </thead>
            <tbody>
              {filhos.map((filho) => (
                <tr key={filho.id} className="border-t border-border hover:bg-muted/20">
                  <td className="px-4 py-3"><Estado valor={filho.status} /></td>
                  <td className="px-4 py-3 font-medium">
                    <Link className="text-primary hover:underline" to={`/trafego/meta/${proximoTipo}/${filho.id}?modo=demo`}>{filho.nome}</Link>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{filho.entrega}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{filho.resultado}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
          Este cenário não possui um nível subordinado para exibir.
        </div>
      )}
    </section>
  );
};

const MetaObjetoPage: React.FC = () => {
  const params = useParams<{ tipo: string; objetoId: string }>();
  if (!TIPOS.includes(params.tipo as TipoMeta)) return <Navigate to="/trafego?rede=meta" replace />;
  const tipo = params.tipo as TipoMeta;
  const objeto = objetoMetaDemo(tipo, params.objetoId ?? '');
  if (!objeto) return <Navigate to={`/trafego?rede=meta&nivel=${tipo}`} replace />;
  const rotulo = ROTULOS_META[tipo];

  return (
    <Layout>
      <main className="p-4 md:p-8">
        <header className="mb-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <Link to={`/trafego?rede=meta&nivel=${tipo}`} className="inline-flex min-h-9 items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
                <ArrowLeft className="h-4 w-4" aria-hidden /> Meta Ads · {rotulo.plural}
              </Link>
              <div className="mt-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary"><Megaphone className="h-3.5 w-3.5" aria-hidden /></span>
                {rotulo.singular} · demonstração
              </div>
              <h1 className="mt-2 max-w-4xl text-balance font-display text-[2rem] font-bold leading-[1.05] tracking-tight md:text-[2.4rem]">{objeto.nome}</h1>
              <div className="aurora-rule mt-3 w-16" aria-hidden />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Estado valor={objeto.status} />
                <span className="text-sm text-muted-foreground">{objeto.objetivo ?? objeto.detalhe}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <MetaConfiguracaoLocal />
              <Button type="button" disabled title="Ações reais bloqueadas no modo demonstrativo">Editar {rotulo.singular}</Button>
            </div>
          </div>
          <div className="mt-5 flex items-start gap-2 rounded-md border border-verified/25 bg-verified/5 px-3 py-2.5 text-xs">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-verified" aria-hidden />
            <p><strong>Cenário demonstrativo.</strong> A arquitetura desta página é real; identidade, entrega e métricas são fictícias e não vieram de uma conta Meta.</p>
          </div>
        </header>

        <Tabs defaultValue="visao">
          <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-lg border border-border bg-muted p-1">
            <TabsTrigger value="visao">Visão geral</TabsTrigger>
            <TabsTrigger value="estrutura">Estrutura</TabsTrigger>
            <TabsTrigger value="configuracao">Configuração</TabsTrigger>
            <TabsTrigger value="historico">Histórico</TabsTrigger>
          </TabsList>

          <TabsContent value="visao" className="mt-5">
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
              <div className="rounded-md border border-border bg-card p-5 shadow-card">
                <div className="flex items-center gap-2 border-b border-border pb-4">
                  <BarChart3 className="h-4 w-4 text-primary" aria-hidden />
                  <h2 className="font-display text-lg font-semibold">Leitura operacional</h2>
                </div>
                <dl className="grid gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
                  <Campo rotulo="Entrega" valor={objeto.entrega ?? 'Não aplicável'} ajuda="effective_status no read model real" />
                  <Campo rotulo="Orçamento" valor={objeto.orcamento ?? 'Não definido'} ajuda="ausência não é convertida em zero" />
                  <Campo rotulo="Resultado" valor={objeto.resultado ?? 'Não medido'} ajuda="cenário fictício" />
                  <Campo rotulo="Custo" valor={objeto.custo ?? 'Não medido'} ajuda="cenário fictício" />
                  <Campo rotulo="Origem" valor="Meta Marketing API v26.0" ajuda="read model previsto; sem leitura nesta tela" />
                  <Campo rotulo="Frescor" valor="Demonstração" ajuda="nenhuma data externa foi observada" />
                </dl>
                <div className="mt-6"><Estrutura objeto={objeto} /></div>
              </div>

              <aside className="rounded-md border border-border bg-card p-5 shadow-card" aria-label="Ações da entidade Meta">
                <div className="flex items-center gap-2">
                  <LockKeyhole className="h-4 w-4 text-warning" aria-hidden />
                  <h2 className="font-display text-lg font-semibold">Ações</h2>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                  A interface antecipa os atos, mas nenhum deles é emitido no modo demonstrativo.
                </p>
                <div className="mt-4 space-y-2">
                  <Button type="button" variant="outline" className="w-full justify-start" disabled><CirclePause className="mr-2 h-4 w-4" aria-hidden /> Pausar</Button>
                  <Button type="button" variant="outline" className="w-full justify-start" disabled><Settings2 className="mr-2 h-4 w-4" aria-hidden /> Alterar configuração</Button>
                </div>
                <div className="mt-5 border-t border-border pt-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Para habilitar</p>
                  <ol className="mt-2 space-y-2 text-xs leading-relaxed text-muted-foreground">
                    <li>1. provar token e conta em somente leitura</li>
                    <li>2. sincronizar este objeto no read model</li>
                    <li>3. aprovar contrato de escrita e recibo</li>
                  </ol>
                </div>
              </aside>
            </div>
          </TabsContent>

          <TabsContent value="estrutura" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card"><Estrutura objeto={objeto} /></TabsContent>
          <TabsContent value="configuracao" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card">
            <h2 className="font-display text-lg font-semibold">Contrato da configuração</h2>
            <dl className="mt-3 grid gap-x-8 sm:grid-cols-2">
              <Campo rotulo="Status configurado" valor={objeto.status} />
              <Campo rotulo="Status efetivo" valor={objeto.entrega ?? 'Não lido'} />
              <Campo rotulo="Objeto pai" valor={objeto.pai ?? 'Conta de anúncios'} />
              <Campo rotulo="Identidade externa" valor="oculta na demonstração" />
            </dl>
          </TabsContent>
          <TabsContent value="historico" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card">
            <div className="flex items-center gap-2"><History className="h-4 w-4 text-primary" aria-hidden /><h2 className="font-display text-lg font-semibold">Histórico e recibos</h2></div>
            <p className="mt-3 text-sm text-muted-foreground">Nenhum evento real existe neste cenário demonstrativo. A linha do tempo não inventa alterações.</p>
          </TabsContent>
        </Tabs>
      </main>
    </Layout>
  );
};

export default MetaObjetoPage;
