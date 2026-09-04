import React from 'react';
import { ArrowLeft, BarChart3, CirclePause, GitBranch, History, Info, LockKeyhole, MousePointerClick, Radio } from 'lucide-react';
import { Link, Navigate, useParams } from 'react-router-dom';

import { IdentidadeDeCanal } from '@/components/trafego/hub/IdentidadeDeCanal';
import { META_DEMO, META_INSIGHTS_DEMO } from '@/components/trafego/meta/modelo';
import { Layout } from '@/components/layout/Layout';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const moeda = (valor: number | null) => valor === null ? 'Não medido' : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(valor);
const inteiro = (valor: number | null) => valor === null ? 'Não medido' : new Intl.NumberFormat('pt-BR').format(valor);
const decimal = (valor: number | null, sufixo = '') => valor === null ? 'Não medido' : `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(valor)}${sufixo}`;

const Metrica: React.FC<{ rotulo: string; valor: string; detalhe: string; destaque?: boolean }> = ({ rotulo, valor, detalhe, destaque }) => (
  <div className="min-w-0 border-t border-border pt-3">
    <p className="kicker">{rotulo}</p>
    <p className={`mt-1 font-display text-xl font-bold tabular-nums ${destaque ? 'text-success' : 'text-foreground'}`}>{valor}</p>
    <p className="mt-1 text-xs text-muted-foreground">{detalhe}</p>
  </div>
);

export const MetaCampaignInsightPage: React.FC = () => {
  const { campaignId = '' } = useParams<{ campaignId: string }>();
  const campanha = META_DEMO.campanhas.find((item) => item.id === campaignId);
  const leitura = META_INSIGHTS_DEMO[campaignId];
  if (!campanha || !leitura) return <Navigate to="/settings/campaigns?rede=meta" replace />;

  const lucro = leitura.gasto !== null && leitura.receitaGam !== null ? leitura.receitaGam - leitura.gasto : null;
  const roasExcedente = leitura.gasto !== null && leitura.receitaGam !== null && leitura.gasto > 0 ? ((leitura.receitaGam / leitura.gasto) - 1) * 100 : null;
  const ctr = leitura.impressoes !== null && leitura.cliquesNoLink !== null && leitura.impressoes > 0 ? (leitura.cliquesNoLink / leitura.impressoes) * 100 : null;
  const cpc = leitura.gasto !== null && leitura.cliquesNoLink !== null && leitura.cliquesNoLink > 0 ? leitura.gasto / leitura.cliquesNoLink : null;
  const cpm = leitura.gasto !== null && leitura.impressoes !== null && leitura.impressoes > 0 ? (leitura.gasto / leitura.impressoes) * 1000 : null;
  const frequencia = leitura.impressoes !== null && leitura.alcance !== null && leitura.alcance > 0 ? leitura.impressoes / leitura.alcance : null;
  const conjuntos = META_DEMO.conjuntos.filter((item) => item.paiId === campanha.id);

  return (
    <Layout>
      <main className="mx-auto max-w-[1500px] p-4 md:p-8">
        <header className="mb-6">
          <Link to="/settings/campaigns?rede=meta" className="inline-flex min-h-9 items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" aria-hidden />Campanhas · Meta Ads</Link>
          <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="kicker">Visão da campanha</p>
              <h1 className="mt-2 max-w-4xl text-balance font-display text-[2rem] font-bold leading-[1.05] tracking-tight md:text-[2.5rem]">{campanha.nome}</h1>
              <div className="aurora-rule mt-3 w-16" aria-hidden />
              <div className="mt-3 flex flex-wrap items-center gap-2"><IdentidadeDeCanal rede="meta" canal="Tráfego" /><Badge variant={campanha.status === 'ATIVO' ? 'success' : campanha.status === 'PAUSADO' ? 'outline' : 'warning'}>{campanha.status}</Badge><span className="text-sm text-muted-foreground">{leitura.periodo}</span></div>
            </div>
            <Button type="button" disabled title="Mutação bloqueada no cenário demonstrativo"><CirclePause className="mr-2 h-4 w-4" aria-hidden />Pausar campanha</Button>
          </div>
          <div className="mt-5 flex items-start gap-2 rounded-md border border-verified/25 bg-verified/5 px-3 py-2.5 text-xs">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-verified" aria-hidden />
            <p><strong>Dados fictícios para inspeção da interface.</strong> A hierarquia e os campos seguem o contrato Meta planejado; nenhuma leitura da Marketing API ou do Supabase oficial aconteceu.</p>
          </div>
        </header>

        <Tabs defaultValue="visao">
          <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-lg border border-border bg-muted p-1">
            <TabsTrigger value="visao">Visão geral</TabsTrigger><TabsTrigger value="estrutura">Conjuntos e anúncios</TabsTrigger><TabsTrigger value="atribuicao">Atribuição</TabsTrigger><TabsTrigger value="historico">Histórico</TabsTrigger>
          </TabsList>

          <TabsContent value="visao" className="mt-5">
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
              <div className="space-y-5">
                <section className="rounded-md border border-border bg-card p-5 shadow-card" aria-labelledby="economia-meta">
                  <div className="flex items-center gap-2"><BarChart3 className="h-4 w-4 text-primary" aria-hidden /><h2 id="economia-meta" className="font-display text-lg font-semibold">Economia da campanha</h2></div>
                  <p className="mt-1 text-xs text-muted-foreground">Espinha comum VOLC: investimento da plataforma × receita atribuída no GAM.</p>
                  <div className="mt-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
                    <Metrica rotulo="Gasto Meta" valor={moeda(leitura.gasto)} detalhe="Meta Insights · demo" />
                    <Metrica rotulo="Revenue GAM" valor={moeda(leitura.receitaGam)} detalhe="atribuição por campanha · demo" destaque />
                    <Metrica rotulo="Lucro bruto" valor={moeda(lucro)} detalhe="revenue − mídia" destaque={lucro !== null && lucro >= 0} />
                    <Metrica rotulo="ROAS excedente" valor={roasExcedente === null ? 'Não medido' : decimal(roasExcedente, '%')} detalhe="(revenue ÷ gasto − 1) × 100" />
                  </div>
                </section>

                <section className="rounded-md border border-border bg-card p-5 shadow-card" aria-labelledby="entrega-meta">
                  <div className="flex items-center gap-2"><Radio className="h-4 w-4 text-primary" aria-hidden /><h2 id="entrega-meta" className="font-display text-lg font-semibold">Entrega Meta</h2></div>
                  <div className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
                    <Metrica rotulo="Impressões" valor={inteiro(leitura.impressoes)} detalhe="impressions" />
                    <Metrica rotulo="Alcance" valor={inteiro(leitura.alcance)} detalhe="reach" />
                    <Metrica rotulo="Frequência" valor={decimal(frequencia)} detalhe="impressões ÷ alcance" />
                    <Metrica rotulo="Cliques no link" valor={inteiro(leitura.cliquesNoLink)} detalhe="inline_link_clicks" />
                    <Metrica rotulo="Landing page views" valor={inteiro(leitura.visualizacoesDaPagina)} detalhe="action metric" />
                    <Metrica rotulo="CTR de link" valor={decimal(ctr, '%')} detalhe="cliques ÷ impressões" />
                    <Metrica rotulo="CPC de link" valor={moeda(cpc)} detalhe="gasto ÷ cliques" />
                    <Metrica rotulo="CPM" valor={moeda(cpm)} detalhe="gasto por mil impressões" />
                  </div>
                </section>

                <section className="rounded-md border border-border bg-card p-5 shadow-card" aria-labelledby="serie-meta">
                  <h2 id="serie-meta" className="font-display text-lg font-semibold">Leitura diária</h2>
                  {leitura.serie.length ? (
                    <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead className="border-b border-border text-[11px] uppercase tracking-[0.08em] text-muted-foreground"><tr><th className="py-2">Dia</th><th className="py-2 text-right">Gasto</th><th className="py-2 text-right">Revenue</th><th className="py-2 text-right">Impressões</th><th className="py-2 text-right">Alcance</th><th className="py-2 text-right">LP views</th></tr></thead><tbody>{leitura.serie.map((dia) => <tr key={dia.data} className="border-b border-border last:border-0"><td className="py-3 font-medium">{dia.data}</td><td className="py-3 text-right tabular-nums">{moeda(dia.gasto)}</td><td className="py-3 text-right tabular-nums text-success">{moeda(dia.receitaGam)}</td><td className="py-3 text-right tabular-nums">{inteiro(dia.impressoes)}</td><td className="py-3 text-right tabular-nums">{inteiro(dia.alcance)}</td><td className="py-3 text-right tabular-nums">{inteiro(dia.visualizacoesDaPagina)}</td></tr>)}</tbody></table></div>
                  ) : <p className="mt-4 text-sm text-muted-foreground">Este cenário não possui série observada. Ausência não foi convertida em zero.</p>}
                </section>
              </div>

              <aside className="h-fit rounded-md border border-border bg-card p-5 shadow-card" aria-label="Resumo e próximos atos">
                <div className="flex items-center gap-2"><LockKeyhole className="h-4 w-4 text-warning" aria-hidden /><h2 className="font-display text-lg font-semibold">Controle</h2></div>
                <dl className="mt-4 space-y-3 text-sm"><div className="border-b border-border pb-3"><dt className="text-xs text-muted-foreground">Objetivo</dt><dd className="mt-1 font-medium">{campanha.objetivo}</dd></div><div className="border-b border-border pb-3"><dt className="text-xs text-muted-foreground">Resultado otimizado</dt><dd className="mt-1 font-medium">{leitura.eventoDeResultado}</dd></div><div className="border-b border-border pb-3"><dt className="text-xs text-muted-foreground">Janela de atribuição</dt><dd className="mt-1 font-medium">{leitura.atribuicao}</dd></div><div><dt className="text-xs text-muted-foreground">Frescor</dt><dd className="mt-1 font-medium">Demonstração · não sincronizada</dd></div></dl>
                <div className="mt-5 border-t border-border pt-4"><p className="kicker">Próximo ato real</p><p className="mt-2 text-sm text-muted-foreground">Conectar uma conta em somente leitura e preencher o read model antes de habilitar qualquer edição.</p></div>
              </aside>
            </div>
          </TabsContent>

          <TabsContent value="estrutura" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card">
            <div className="flex items-center gap-2"><GitBranch className="h-4 w-4 text-primary" aria-hidden /><h2 className="font-display text-lg font-semibold">Campanha → conjuntos → anúncios → criativos</h2></div>
            <div className="mt-4 space-y-3">{conjuntos.map((conjunto) => { const anuncios = META_DEMO.anuncios.filter((item) => item.paiId === conjunto.id); return <div key={conjunto.id} className="border-l-2 border-primary/30 pl-4"><Link to={`/trafego/meta/conjuntos/${conjunto.id}?modo=demo`} className="font-semibold text-primary hover:underline">{conjunto.nome}</Link><p className="mt-1 text-xs text-muted-foreground">{conjunto.entrega} · {conjunto.resultado}</p><div className="mt-2 space-y-2">{anuncios.map((anuncio) => <div key={anuncio.id} className="flex items-center justify-between gap-3 border-t border-border py-2 text-sm"><Link to={`/trafego/meta/anuncios/${anuncio.id}?modo=demo`} className="hover:text-primary">{anuncio.nome}</Link><span className="text-xs text-muted-foreground">{anuncio.entrega}</span></div>)}</div></div>; })}</div>
          </TabsContent>

          <TabsContent value="atribuicao" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card">
            <div className="flex items-center gap-2"><MousePointerClick className="h-4 w-4 text-primary" aria-hidden /><h2 className="font-display text-lg font-semibold">Atribuição e ação</h2></div><dl className="mt-4 grid gap-5 sm:grid-cols-2"><Metrica rotulo="Janela Meta" valor={leitura.atribuicao} detalhe="deve acompanhar cada leitura real" /><Metrica rotulo="Ação primária" valor={leitura.eventoDeResultado} detalhe="action_type preservado, não achatado" /><Metrica rotulo="Receita" valor="GAM por campanha" detalhe="fonte econômica comum do VOLC" /><Metrica rotulo="Identidade" valor="provider + conta + objeto" detalhe="ID externo sozinho não é chave canônica" /></dl>
          </TabsContent>

          <TabsContent value="historico" className="mt-5 rounded-md border border-border bg-card p-5 shadow-card">
            <div className="flex items-center gap-2"><History className="h-4 w-4 text-primary" aria-hidden /><h2 className="font-display text-lg font-semibold">Histórico e recibos</h2></div><p className="mt-3 text-sm text-muted-foreground">Nenhum evento real existe neste cenário. A tela não fabrica mudanças, leituras ou recibos.</p>
          </TabsContent>
        </Tabs>
      </main>
    </Layout>
  );
};

export default MetaCampaignInsightPage;
