import React from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Calendar,
  Circle,
  Clock,
  Coins,
  DollarSign,
  Eye,
  FileText,
  GitBranch,
  History,
  Layers,
  MousePointer,
  MousePointerClick,
  Radio,
  Settings,
  Target,
  TrendingUp,
  Users,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Bar, ComposedChart } from 'recharts';

import { Layout } from '@/components/layout/Layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { chartColor, volcGrid, volcAxis, volcLine, volcCursor, VolcTooltip } from '@/lib/chartTheme';
import { IdentidadeDeCanal } from '@/components/trafego/hub/IdentidadeDeCanal';
import { MetaFrescorBadge, MetaPeriodoChip } from '@/components/campaign/MetaDemoStatus';
import { calculateROAS } from '@/utils/roasCalculations';
import { META_DEMO, META_INSIGHTS_DEMO, type MetaInsightDiarioDemo } from '@/components/trafego/meta/modelo';

const moeda = (valor: number | null) => valor === null ? 'Não medido' : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(valor);
const inteiro = (valor: number | null) => valor === null ? 'Não medido' : new Intl.NumberFormat('pt-BR').format(valor);
const decimal = (valor: number | null, sufixo = '') => valor === null ? 'Não medido' : `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(valor)}${sufixo}`;
const dataBr = (iso?: string | null) => iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('pt-BR') : 'Não medido';

function pontoDoGrafico(dia: MetaInsightDiarioDemo) {
  const lucro = dia.receitaGam - dia.gasto;
  const roas = calculateROAS(dia.receitaGam, dia.gasto);
  const ctr = dia.impressoes > 0 ? (dia.cliquesNoLink / dia.impressoes) * 100 : 0;
  const cpc = dia.cliquesNoLink > 0 ? dia.gasto / dia.cliquesNoLink : 0;
  const cpm = dia.impressoes > 0 ? (dia.gasto / dia.impressoes) * 1000 : 0;
  const frequencia = dia.alcance > 0 ? dia.impressoes / dia.alcance : 0;
  return { ...dia, lucro, roas, ctr, cpc, cpm, frequencia };
}

export const MetaCampaignInsightPage: React.FC = () => {
  const { campaignId = '' } = useParams<{ campaignId: string }>();
  const navigate = useNavigate();
  const campanha = META_DEMO.campanhas.find((item) => item.id === campaignId);
  const leitura = META_INSIGHTS_DEMO[campaignId];
  if (!campanha || !leitura) return <Navigate to="/settings/campaigns?rede=meta" replace />;

  const lucro = leitura.gasto !== null && leitura.receitaGam !== null ? leitura.receitaGam - leitura.gasto : null;
  const roasExcedente = leitura.gasto !== null && leitura.receitaGam !== null && leitura.gasto > 0 ? calculateROAS(leitura.receitaGam, leitura.gasto) : null;
  const ctr = leitura.impressoes !== null && leitura.cliquesNoLink !== null && leitura.impressoes > 0 ? (leitura.cliquesNoLink / leitura.impressoes) * 100 : null;
  const cpc = leitura.gasto !== null && leitura.cliquesNoLink !== null && leitura.cliquesNoLink > 0 ? leitura.gasto / leitura.cliquesNoLink : null;
  const cpm = leitura.gasto !== null && leitura.impressoes !== null && leitura.impressoes > 0 ? (leitura.gasto / leitura.impressoes) * 1000 : null;
  const frequencia = leitura.impressoes !== null && leitura.alcance !== null && leitura.alcance > 0 ? leitura.impressoes / leitura.alcance : null;
  const diasAtivos = campanha.status === 'RASCUNHO' || !campanha.criadoEm
    ? null
    : Math.floor((new Date().getTime() - new Date(`${campanha.criadoEm}T00:00:00`).getTime()) / (1000 * 3600 * 24));

  const conjuntos = META_DEMO.conjuntos.filter((item) => item.paiId === campanha.id);
  const serieGrafico = leitura.serie.map(pontoDoGrafico);

  const getStatusBadge = (status: typeof campanha.status) => {
    if (status === 'ATIVO') {
      return (
        <Badge className="bg-success text-success-foreground flex items-center gap-1">
          <Circle className="h-2 w-2 fill-current" aria-hidden />Ativa
        </Badge>
      );
    }
    if (status === 'PAUSADO') {
      return (
        <Badge variant="secondary" className="bg-destructive text-destructive-foreground flex items-center gap-1">
          <Circle className="h-2 w-2 fill-current" aria-hidden />Pausada
        </Badge>
      );
    }
    return (
      <Badge variant="secondary" className="bg-muted text-foreground flex items-center gap-1">
        <Circle className="h-2 w-2 fill-current" aria-hidden />Rascunho
      </Badge>
    );
  };

  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;

  return (
    <Layout>
      <div className={`${isMobile ? 'p-4' : 'p-6'} space-y-4 md:space-y-6`}>
        {/* Header */}
        <div className="space-y-4">
          <div className="flex items-start gap-4 reveal" style={{ ['--i' as any]: 0 }}>
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="flex-shrink-0 gap-2 touch-target">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Voltar
            </Button>
            <div className="flex-1 min-w-0">
              <div className="kicker mb-2 flex items-center gap-2">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-success animate-pulse" aria-hidden />
                Detalhe da campanha
              </div>
              <h1 className={`font-display font-bold tracking-tight leading-[1.05] ${isMobile ? 'text-2xl' : 'text-4xl'}`}>
                Dashboard da <span className="text-foreground">Campanha</span>
              </h1>
              <div className="mt-3 aurora-rule w-16" />
              <p className={`${isMobile ? 'text-xs' : 'text-sm'} text-muted-foreground mt-3`}>
                ID: {campanha.id} • Projeto: {campanha.projeto ?? 'Sem projeto vinculado'}
              </p>
            </div>
          </div>

          {/* Filters and Actions Section */}
          <div className={`flex ${isMobile ? 'flex-col' : 'items-center flex-wrap'} gap-3`}>
            <MetaPeriodoChip label={leitura.periodo} className={isMobile ? 'w-full' : undefined} />

            <div className="flex items-center gap-2 flex-wrap">
              <MetaFrescorBadge />

              <Button
                variant="outline"
                size="sm"
                className="gap-2 flex-shrink-0"
                disabled
                title="Configuração indisponível no cenário demonstrativo Meta."
              >
                <Settings className="h-4 w-4" aria-hidden />
                Configurar
              </Button>
              <div className="flex-shrink-0">
                {getStatusBadge(campanha.status)}
              </div>
            </div>
          </div>
        </div>

        {/* Campaign Info */}
        <Card className="reveal hover-lift" style={{ ['--i' as any]: 1 }}>
          <CardHeader>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="flex items-center gap-2 font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><Target className="h-4 w-4" aria-hidden /></span>
                {campanha.nome}
              </CardTitle>
              <IdentidadeDeCanal rede="meta" canal="Tráfego" />
            </div>
            <CardDescription className="text-sm">
              <div className="space-y-1">
                <p className="flex items-center gap-2">
                  <FileText className="h-4 w-4" aria-hidden />
                  <strong>Nome completo:</strong> {campanha.nome} / {campanha.projeto ?? 'Sem projeto'} / {campanha.site ?? 'sem site vinculado'}
                </p>
                <p className="flex items-center gap-2">
                  <Radio className="h-4 w-4" aria-hidden />
                  <strong>Canal:</strong> Meta Ads · Tráfego | <strong>Estratégia:</strong> {campanha.detalhe ?? 'Não declarada'}
                </p>
                <p className="flex items-center gap-2">
                  <Calendar className="h-4 w-4" aria-hidden />
                  <strong>Período:</strong> {dataBr(campanha.criadoEm)} - {campanha.terminaEm ? dataBr(campanha.terminaEm) : campanha.criadoEm ? 'Contínua' : 'Não iniciada'}
                </p>
              </div>
            </CardDescription>
          </CardHeader>
        </Card>

        {/* Métricas Principais */}
        <div className="flex items-center gap-3">
          <span className="kicker whitespace-nowrap">Métricas principais</span>
          <span className="hairline-aurora flex-1" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          {/* Gasto */}
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 2 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Investimento Total</span>
              <span className="rounded-md bg-info/10 text-info p-1.5"><DollarSign className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight">{moeda(leitura.gasto)}</div>
              <div className="mt-2 text-xs text-muted-foreground">
                Orçamento: <span className="tabular">{campanha.orcamento ?? 'Não medido'}</span>
              </div>
            </CardContent>
          </Card>

          {/* Revenue */}
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 3 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Revenue</span>
              <span className="rounded-md bg-success/10 text-success p-1.5"><TrendingUp className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight text-success">{moeda(leitura.receitaGam)}</div>
              <div className="mt-2 text-xs text-success font-medium tabular">
                ROAS: {roasExcedente === null ? 'Não medido' : `${roasExcedente.toFixed(1)}%`}
              </div>
            </CardContent>
          </Card>

          {/* ROAS */}
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 4 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">ROAS</span>
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><Target className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight">{roasExcedente === null ? 'Não medido' : `${roasExcedente.toFixed(1)}%`}</div>
              <div className="mt-2 text-xs text-muted-foreground">
                {leitura.eventoDeResultado}: <span className="tabular">{inteiro(leitura.visualizacoesDaPagina)}</span>
              </div>
            </CardContent>
          </Card>

          {/* Lucro Bruto */}
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 5 }}>
            <span className={`pointer-events-none absolute inset-x-0 top-0 h-0.5 ${lucro === null ? 'bg-muted-foreground/30' : lucro >= 0 ? 'bg-success' : 'bg-destructive'}`} />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Lucro Bruto</span>
              <span className={`rounded-md p-1.5 ${lucro === null ? 'bg-muted text-muted-foreground' : lucro >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}><TrendingUp className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className={`font-display text-2xl md:text-3xl font-bold tabular tracking-tight ${lucro === null ? '' : lucro >= 0 ? 'text-success' : 'text-destructive'}`}>
                {moeda(lucro)}
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                revenue − mídia
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Métricas Secundárias */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 6 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">CTR de Link</span>
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><MousePointer className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl font-bold tabular tracking-tight">{ctr === null ? 'Não medido' : `${ctr.toFixed(2)}%`}</div>
              <div className="mt-2 text-xs text-muted-foreground">
                <span className="tabular">{inteiro(leitura.cliquesNoLink)}</span> cliques • <span className="tabular">{inteiro(leitura.impressoes)}</span> impressões
              </div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 7 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">CPC de Link</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><DollarSign className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl font-bold tabular tracking-tight">{moeda(cpc)}</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 8 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Custo/LP View</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Target className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl font-bold tabular tracking-tight">
                {leitura.gasto !== null && leitura.visualizacoesDaPagina !== null && leitura.visualizacoesDaPagina > 0
                  ? moeda(leitura.gasto / leitura.visualizacoesDaPagina)
                  : 'Não medido'}
              </div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 9 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Dias Ativos</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Calendar className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl font-bold tabular tracking-tight">
                {diasAtivos === null ? 'Não iniciada' : diasAtivos}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Métricas Meta */}
        <div className="flex items-center gap-3">
          <span className="kicker whitespace-nowrap">Métricas Meta</span>
          <span className="hairline-aurora flex-1" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <Card className="relative overflow-hidden hover-lift">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Impressões</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Eye className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-xl font-bold tabular tracking-tight">{inteiro(leitura.impressoes)}</div>
              <div className="mt-1 text-xs text-muted-foreground">impressions</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden hover-lift">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Alcance</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Users className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-xl font-bold tabular tracking-tight">{inteiro(leitura.alcance)}</div>
              <div className="mt-1 text-xs text-muted-foreground">reach</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden hover-lift">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Frequência</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Radio className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-xl font-bold tabular tracking-tight">{decimal(frequencia)}</div>
              <div className="mt-1 text-xs text-muted-foreground">impressões ÷ alcance</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden hover-lift">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Cliques no Link</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><MousePointerClick className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-xl font-bold tabular tracking-tight">{inteiro(leitura.cliquesNoLink)}</div>
              <div className="mt-1 text-xs text-muted-foreground">inline_link_clicks</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden hover-lift">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Landing Page Views</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Layers className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-xl font-bold tabular tracking-tight">{inteiro(leitura.visualizacoesDaPagina)}</div>
              <div className="mt-1 text-xs text-muted-foreground">action metric</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden hover-lift">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">CPM</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Coins className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-xl font-bold tabular tracking-tight">{moeda(cpm)}</div>
              <div className="mt-1 text-xs text-muted-foreground">gasto por mil impressões</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden hover-lift">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Janela de Atribuição</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Clock className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-base font-bold tracking-tight text-pretty">{leitura.atribuicao}</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden hover-lift">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Evento de Resultado</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Target className="h-4 w-4" aria-hidden /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-base font-bold tracking-tight text-pretty">{leitura.eventoDeResultado}</div>
            </CardContent>
          </Card>
        </div>

        {/* Gráficos */}
        <div className="flex items-center gap-3">
          <span className="kicker whitespace-nowrap">Análise de desempenho</span>
          <span className="hairline-aurora flex-1" />
        </div>

        {serieGrafico.length === 0 ? (
          <Card className="p-6 text-center shadow-card">
            <p className="text-muted-foreground text-sm">Este cenário não possui série diária observada. Ausência não foi convertida em zero.</p>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
            {/* Gasto vs Revenue */}
            <Card className="hover-lift">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base font-display">
                  <span className="rounded-md bg-primary/10 text-primary p-1.5"><Coins className="h-4 w-4" aria-hidden /></span>
                  Gasto vs Revenue ({leitura.periodo})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={serieGrafico}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="data" {...volcAxis} />
                    <YAxis {...volcAxis} />
                    <Tooltip cursor={volcCursor} content={<VolcTooltip valueFormatter={(value) => `R$ ${Number(value).toFixed(2)}`} />} />
                    <Line type="monotone" dataKey="gasto" stroke={chartColor(3)} name="Gasto" {...volcLine} />
                    <Line type="monotone" dataKey="receitaGam" stroke={chartColor(4)} name="Revenue" {...volcLine} />
                    <Line type="monotone" dataKey="lucro" stroke={chartColor(0)} name="Lucro Bruto" {...volcLine} />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Impressões vs Cliques no Link */}
            <Card className="hover-lift">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base font-display">
                  <span className="rounded-md bg-primary/10 text-primary p-1.5"><MousePointer className="h-4 w-4" aria-hidden /></span>
                  Impressões vs Cliques no Link ({leitura.periodo})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart data={serieGrafico}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="data" {...volcAxis} />
                    <YAxis yAxisId="left" {...volcAxis} />
                    <YAxis yAxisId="right" orientation="right" domain={[0, 'auto']} {...volcAxis} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip valueFormatter={(value, name) => name === 'CTR' ? `${Number(value).toFixed(2)}%` : Number(value).toLocaleString()} />
                    } />
                    <Bar yAxisId="left" dataKey="impressoes" fill={chartColor(0)} name="Impressões" radius={[4, 4, 0, 0]} />
                    <Bar yAxisId="left" dataKey="cliquesNoLink" fill={chartColor(1)} name="Cliques no link" radius={[4, 4, 0, 0]} />
                    <Line yAxisId="right" type="monotone" dataKey="ctr" stroke={chartColor(3)} name="CTR" {...volcLine} />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Alcance vs Frequência */}
            <Card className="hover-lift">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base font-display">
                  <span className="rounded-md bg-primary/10 text-primary p-1.5"><Users className="h-4 w-4" aria-hidden /></span>
                  Alcance vs Frequência ({leitura.periodo})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart data={serieGrafico}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="data" {...volcAxis} />
                    <YAxis yAxisId="left" {...volcAxis} />
                    <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => value.toFixed(1)} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip valueFormatter={(value, name) => name === 'Frequência' ? Number(value).toFixed(2) : Number(value).toLocaleString()} />
                    } />
                    <Bar yAxisId="left" dataKey="alcance" fill={chartColor(2)} name="Alcance" radius={[4, 4, 0, 0]} />
                    <Line yAxisId="right" type="monotone" dataKey="frequencia" stroke={chartColor(4)} name="Frequência" {...volcLine} />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* CPC de link vs CPM */}
            <Card className="hover-lift">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base font-display">
                  <span className="rounded-md bg-primary/10 text-primary p-1.5"><DollarSign className="h-4 w-4" aria-hidden /></span>
                  CPC de Link vs CPM ({leitura.periodo})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={serieGrafico}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="data" {...volcAxis} />
                    <YAxis {...volcAxis} tickFormatter={(value) => `R$ ${value.toFixed(2)}`} />
                    <Tooltip cursor={volcCursor} content={<VolcTooltip valueFormatter={(value) => `R$ ${Number(value).toFixed(2)}`} />} />
                    <Line type="monotone" dataKey="cpc" stroke={chartColor(3)} name="CPC de link" {...volcLine} />
                    <Line type="monotone" dataKey="cpm" stroke={chartColor(1)} name="CPM" {...volcLine} />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Estrutura, atribuição e histórico — contrato Meta sem equivalente Google nesta página */}
        <div className="flex items-center gap-3">
          <span className="kicker whitespace-nowrap">Estrutura e histórico</span>
          <span className="hairline-aurora flex-1" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
          <Card className="hover-lift">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><GitBranch className="h-4 w-4" aria-hidden /></span>
                Campanha → conjuntos → anúncios
              </CardTitle>
              <CardDescription className="text-xs">Hierarquia preservada, não achatada em uma linha só.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {conjuntos.map((conjunto) => {
                const anuncios = META_DEMO.anuncios.filter((item) => item.paiId === conjunto.id);
                return (
                  <div key={conjunto.id} className="border-l-2 border-primary/30 pl-4">
                    <p className="font-semibold text-foreground">{conjunto.nome}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{conjunto.entrega} · {conjunto.resultado}</p>
                    <div className="mt-2 space-y-2">
                      {anuncios.map((anuncio) => (
                        <div key={anuncio.id} className="flex items-center justify-between gap-3 border-t border-border py-2 text-sm">
                          <span>{anuncio.nome}</span>
                          <span className="text-xs text-muted-foreground">{anuncio.entrega}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
              {conjuntos.length === 0 && <p className="text-sm text-muted-foreground">Nenhum conjunto vinculado neste cenário.</p>}
            </CardContent>
          </Card>

          <Card className="hover-lift">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><History className="h-4 w-4" aria-hidden /></span>
                Histórico e próximo ato real
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>Nenhum evento real existe neste cenário. A tela não fabrica mudanças, leituras ou recibos.</p>
              <div className="border-t border-border pt-3">
                <p className="kicker">Próximo ato real</p>
                <p className="mt-2">Conectar uma conta Meta em somente leitura e preencher o read model antes de habilitar qualquer edição.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
};

export default MetaCampaignInsightPage;
