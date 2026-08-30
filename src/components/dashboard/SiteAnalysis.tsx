import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Eye, Calendar, TrendingUp, BarChart3, Target, DollarSign, Lightbulb } from "lucide-react";
import { useSupabaseData, useUtmCampaignData } from "@/services/supabaseDataService";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  Legend
} from "recharts";
import { format, subDays } from "date-fns";
import { cn } from "@/lib/utils";
import { formatBrlCurrency } from "@/utils/currencyUtils";
import { chartColor, volcGrid, volcAxis, volcLine, volcCursor } from "@/lib/chartTheme";

// Sample data similar to the image
const generateSiteAnalysisData = () => {
  const data = [];
  for (let i = 6; i >= 0; i--) {
    const date = subDays(new Date(), i);
    const baseRevenue = 1800 + Math.random() * 400; // $1800-$2200 range like image

    data.push({
      date: format(date, 'yyyy-MM-dd'),
      dateShort: format(date, 'MM-dd'),
      revenue: Number(baseRevenue.toFixed(2)),
      ecpm: Number((12.00 + Math.random() * 2).toFixed(2)), // $12-14 range
      cpc: Number((0.05 + Math.random() * 0.05).toFixed(2)), // $0.05-0.10 range
      viewability: Number((80 + Math.random() * 10).toFixed(2)), // 80-90% range
      pmr: Number((82 + Math.random() * 6).toFixed(2)), // 82-88% range
      ctr: Number((14 + Math.random() * 4).toFixed(2)), // 14-18% range
      rps: Number((20 + Math.random() * 4).toFixed(2)) // $20-24 range
    });
  }
  return data;
};

// Métricas do painel/legenda — cor por identidade fixa do tema VOLC.
const metricsConfig = [
  { key: 'revenue', name: 'Revenue', color: chartColor(1), type: 'bar', format: '$' },
  { key: 'ecpm', name: 'eCPM', color: chartColor(2), type: 'line', format: '$' },
  { key: 'cpc', name: 'CPC', color: chartColor(3), type: 'line', format: '$' },
  { key: 'viewability', name: 'Viewability', color: chartColor(4), type: 'line', format: '%' },
  { key: 'pmr', name: 'PMR', color: chartColor(0), type: 'line', format: '%' },
  { key: 'ctr', name: 'CTR', color: chartColor(2), type: 'line', format: '%' },
  { key: 'rps', name: 'RPS', color: chartColor(4), type: 'line', format: '$' }
];

export const SiteAnalysis = () => {
  const { campaigns, projects, loading } = useSupabaseData();
  const [selectedProject, setSelectedProject] = useState("all");
  const [selectedPeriod, setSelectedPeriod] = useState("7");

  // Use real UTM campaign data
  const { utmData, loading: utmLoading } = useUtmCampaignData(
    selectedProject === "all" ? undefined : selectedProject,
    parseInt(selectedPeriod)
  );

  const [data, setData] = useState(generateCampaignAnalysisData());
  const [selectedDate, setSelectedDate] = useState(data[data.length - 1]);

  // Use real UTM campaign data when available, fallback to generated data
  useEffect(() => {
    if (utmData && utmData.length > 0) {
      // Convert UTM data to chart format
      const chartData = utmData.map(dayData => ({
        date: dayData.date,
        dateShort: format(new Date(dayData.date), 'MM/dd'),
        spend: dayData.investment,
        revenue: dayData.revenue,
        profit: dayData.profit,
        roas: dayData.roas,
        clicks: dayData.clicks,
        impressions: dayData.impressions,
        ctr: dayData.ctr,
        conversions: dayData.conversions,
        cpc: dayData.cpc
      })).reverse(); // Reverse to show chronological order

      setData(chartData);
      if (chartData.length > 0) {
        setSelectedDate(chartData[chartData.length - 1]);
      }
    } else {
      // Fallback to generated data
      const generatedData = generateCampaignAnalysisData();
      setData(generatedData);
      setSelectedDate(generatedData[generatedData.length - 1]);
    }
  }, [utmData]);

  // Tooltip VOLC: cartão de vidro, rótulo kicker, valores tabulares, ponto de cor por série.
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="glass rounded-lg px-3 py-2.5 min-w-[9rem] shadow-elevated">
          <div className="kicker mb-1.5">{label}</div>
          <div className="space-y-1">
            {payload.map((entry: any, index: number) => (
              <div key={index} className="flex items-center justify-between gap-4 text-xs">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <span className="h-2 w-2 rounded-[2px]" style={{ background: entry.color }} />
                  {entry.name}
                </span>
                <span className="font-medium tabular text-foreground">
                  {entry.name.includes('Revenue') || entry.name.includes('eCPM') || entry.name.includes('CPC') || entry.name.includes('RPS') ? '$' : ''}{entry.value}{entry.name.includes('Viewability') || entry.name.includes('PMR') || entry.name.includes('CTR') ? '%' : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      );
    }
    return null;
  };

  if (loading || utmLoading) {
    return (
      <Card className="col-span-full relative overflow-hidden shadow-card">
        <CardHeader>
          <CardTitle className="text-xl font-display font-semibold flex items-center gap-2">
            <span className="rounded-md bg-primary/10 text-primary p-1.5"><Target className="h-4 w-4" /></span>
            Performance de Campanhas UTM
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[400px]">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
              <p className="text-muted-foreground">Carregando dados das campanhas...</p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="col-span-full relative overflow-hidden shadow-card">
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-primary/10 text-primary p-1.5">
                <Target className="h-4 w-4" />
              </span>
              <div>
                <div className="kicker mb-0.5">Campanhas UTM</div>
                <CardTitle className="text-xl font-display font-semibold">
                  Performance de <span className="text-foreground">Campanhas</span>
                </CardTitle>
              </div>
            </div>
            <span className="text-sm text-muted-foreground flex items-center gap-1 tabular">
              <Calendar className="h-3 w-3" />
              {format(new Date(), 'dd/MM/yyyy')}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2">
              <Label className="kicker">Projeto</Label>
              <Select value={selectedProject} onValueChange={setSelectedProject}>
                <SelectTrigger className="w-32 h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  {projects.map(project => (
                    <SelectItem key={project.id} value={project.id}>
                      {project.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Label className="kicker">Período</Label>
              <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
                <SelectTrigger className="w-20 h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7">7d</SelectItem>
                  <SelectItem value="30">30d</SelectItem>
                  <SelectItem value="90">90d</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Main Chart */}
          <div className="lg:col-span-3">
            <div className="mb-4 flex items-start gap-2.5 p-3 rounded-lg border border-border bg-muted/40">
              <span className="rounded-md bg-warning/10 text-warning p-1.5 flex-shrink-0">
                <Lightbulb className="h-4 w-4" />
              </span>
              <p className="text-sm text-muted-foreground">
                Este gráfico mostra a performance agregada das campanhas UTM.
                O gráfico de barras representa <span className="font-medium" style={{ color: chartColor(0) }}>Gasto</span> vs <span className="font-medium" style={{ color: chartColor(1) }}>Revenue</span>,
                enquanto as linhas mostram <span className="font-medium" style={{ color: chartColor(2) }}>Lucro</span>, <span className="font-medium" style={{ color: chartColor(3) }}>ROAS</span> e <span className="font-medium" style={{ color: chartColor(4) }}>CTR</span>.
              </p>
            </div>
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid {...volcGrid} />
                <XAxis
                  dataKey="dateShort"
                  {...volcAxis}
                />
                <YAxis
                  yAxisId="currency"
                  orientation="left"
                  {...volcAxis}
                  domain={[0, 'dataMax + 20']}
                  tickFormatter={(value) => `R$${value}`}
                />
                <YAxis
                  yAxisId="percentage"
                  orientation="right"
                  {...volcAxis}
                  domain={[0, 100]}
                  tickFormatter={(value) => `${value}%`}
                />

                {/* Gasto (série 0) */}
                <Bar
                  yAxisId="currency"
                  dataKey="spend"
                  fill={chartColor(0)}
                  radius={[4, 4, 0, 0]}
                  name="Gasto"
                />

                {/* Revenue (série 1) */}
                <Bar
                  yAxisId="currency"
                  dataKey="revenue"
                  fill={chartColor(1)}
                  radius={[4, 4, 0, 0]}
                  name="Revenue"
                  fillOpacity={0.85}
                />

                {/* Performance lines */}
                <Line
                  yAxisId="currency"
                  type="monotone"
                  dataKey="profit"
                  stroke={chartColor(2)}
                  name="Lucro"
                  {...volcLine}
                />
                <Line
                  yAxisId="percentage"
                  type="monotone"
                  dataKey="roas"
                  stroke={chartColor(3)}
                  strokeDasharray="5 5"
                  name="ROAS"
                  {...volcLine}
                />
                <Line
                  yAxisId="percentage"
                  type="monotone"
                  dataKey="ctr"
                  stroke={chartColor(4)}
                  strokeDasharray="5 5"
                  name="CTR"
                  {...volcLine}
                />

                <Tooltip content={<CustomTooltip />} cursor={volcCursor} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Metrics Panel - like in the image */}
          <div className="lg:col-span-1">
            <div className="glass rounded-lg p-4 h-[400px] overflow-y-auto">
              <div className="flex items-center justify-center gap-1.5 mb-4">
                <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="kicker tabular">
                  {format(new Date(selectedDate.date), 'dd/MM/yyyy')}
                </span>
              </div>

              <div className="space-y-2">
                {metricsConfig.map((metric) => (
                  <div key={metric.key} className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/40 transition-colors">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2.5 h-2.5 rounded-[3px]"
                        style={{ backgroundColor: metric.color }}
                      />
                      <span className="text-sm font-medium text-foreground">{metric.name}</span>
                    </div>
                    <span className="text-sm font-semibold tabular text-foreground">
                      {metric.format === 'R$' ? 'R$ ' : ''}
                      {typeof selectedDate[metric.key as keyof typeof selectedDate] === 'number'
                        ? selectedDate[metric.key as keyof typeof selectedDate].toFixed(2)
                        : selectedDate[metric.key as keyof typeof selectedDate]}
                      {metric.format === '%' ? '%' : ''}
                    </span>
                  </div>
                ))}
              </div>

              {/* Summary stats for UTM campaigns */}
              <div className="mt-6 pt-4 border-t border-border">
                <div className="space-y-3">
                  <div className="relative overflow-hidden rounded-lg border border-border bg-card p-3">
                    <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
                    <div className="flex items-center justify-between">
                      <span className="kicker">Total Gasto</span>
                      <span className="rounded-md bg-info/10 text-info p-1"><DollarSign className="h-3.5 w-3.5" /></span>
                    </div>
                    <div className="font-display text-lg font-bold tabular mt-1">
                      R$ {data.reduce((sum, item) => sum + item.spend, 0).toFixed(2)}
                    </div>
                  </div>

                  <div className="relative overflow-hidden rounded-lg border border-border bg-card p-3">
                    <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
                    <div className="flex items-center justify-between">
                      <span className="kicker">Total Revenue</span>
                      <span className="rounded-md bg-success/10 text-success p-1"><TrendingUp className="h-3.5 w-3.5" /></span>
                    </div>
                    <div className="font-display text-lg font-bold tabular text-success mt-1">
                      {formatBrlCurrency(data.reduce((sum, item) => sum + item.revenue, 0))}
                    </div>
                  </div>

                  <div className="relative overflow-hidden rounded-lg border border-border bg-card p-3">
                    <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-primary" />
                    <div className="flex items-center justify-between">
                      <span className="kicker">ROAS Médio</span>
                      <span className="rounded-md bg-primary/10 text-primary p-1"><BarChart3 className="h-3.5 w-3.5" /></span>
                    </div>
                    <div className="font-display text-base font-semibold tabular text-primary mt-1">
                      {(data.reduce((sum, item) => sum + item.roas, 0) / data.length).toFixed(1)}%
                    </div>
                  </div>

                  <div className="relative overflow-hidden rounded-lg border border-border bg-card p-3">
                    <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
                    <div className="flex items-center justify-between">
                      <span className="kicker">CTR Médio</span>
                      <span className="rounded-md bg-info/10 text-info p-1"><Target className="h-3.5 w-3.5" /></span>
                    </div>
                    <div className="font-display text-base font-semibold tabular text-info mt-1">
                      {(data.reduce((sum, item) => sum + item.ctr, 0) / data.length).toFixed(2)}%
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap justify-center gap-4 mt-6 pt-4 border-t border-border">
          {metricsConfig.map((metric) => (
            <div key={metric.key} className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-muted/40 transition-colors">
              <div
                className={cn(
                  "w-2.5 h-2.5 rounded-[3px]",
                  metric.type === 'line' && "border-2 bg-transparent"
                )}
                style={{
                  backgroundColor: metric.type === 'bar' ? metric.color : 'transparent',
                  borderColor: metric.type === 'line' ? metric.color : 'transparent'
                }}
              />
              <span className="text-sm text-muted-foreground">{metric.name}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};
