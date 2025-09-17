import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Eye, Calendar, TrendingUp, BarChart3, Target, DollarSign } from "lucide-react";
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

// Metrics configuration matching the image colors
const metricsConfig = [
  { key: 'revenue', name: 'Revenue', color: '#22c55e', type: 'bar', format: '$' },
  { key: 'ecpm', name: 'eCPM', color: '#06b6d4', type: 'line', format: '$' },
  { key: 'cpc', name: 'CPC', color: '#f97316', type: 'line', format: '$' },
  { key: 'viewability', name: 'Viewability', color: '#ec4899', type: 'line', format: '%' },
  { key: 'pmr', name: 'PMR', color: '#8b5cf6', type: 'line', format: '%' },
  { key: 'ctr', name: 'CTR', color: '#ef4444', type: 'line', format: '%' },
  { key: 'rps', name: 'RPS', color: '#84cc16', type: 'line', format: '$' }
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

  // Custom tooltip to match the image style
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-card p-4 border border-border rounded-lg shadow-xl backdrop-blur-sm">
          <p className="font-semibold mb-2 text-foreground">{label}</p>
          {payload.map((entry: any, index: number) => (
            <p key={index} style={{ color: entry.color }} className="text-sm">
              {entry.name}: {entry.name.includes('Revenue') || entry.name.includes('eCPM') || entry.name.includes('CPC') || entry.name.includes('RPS') ? '$' : ''}{entry.value}{entry.name.includes('Viewability') || entry.name.includes('PMR') || entry.name.includes('CTR') ? '%' : ''}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  if (loading || utmLoading) {
    return (
      <Card className="col-span-full shadow-lg bg-gradient-to-br from-background to-muted/30">
        <CardHeader>
          <CardTitle className="text-xl font-semibold flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            📈 Performance de Campanhas UTM
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
    <Card className="col-span-full shadow-lg bg-gradient-to-br from-background to-muted/30">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 bg-gradient-to-r from-red-500 via-green-500 to-blue-600 rounded-lg flex items-center justify-center shadow-lg">
                <Target className="h-4 w-4 text-white" />
              </div>
              <CardTitle className="text-xl font-semibold bg-gradient-to-r from-red-500 to-green-600 bg-clip-text text-transparent">
                📊 Performance de Campanhas UTM
              </CardTitle>
            </div>
            <span className="text-sm text-muted-foreground flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {format(new Date(), 'dd/MM/yyyy')}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2">
              <Label className="text-xs">Projeto:</Label>
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
              <Label className="text-xs">Período:</Label>
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
            <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p className="text-sm text-yellow-800">
                <strong>💡 Dica:</strong> Este gráfico mostra a performance agregada das campanhas UTM. 
                O gráfico de barras representa <span className="text-red-600 font-medium">Gasto</span> vs <span className="text-green-600 font-medium">Revenue</span>, 
                enquanto as linhas mostram <span className="text-blue-600 font-medium">Lucro</span>, <span className="text-purple-600 font-medium">ROAS</span> e <span className="text-yellow-600 font-medium">CTR</span>.
              </p>
            </div>
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                <XAxis 
                  dataKey="dateShort" 
                  axisLine={false}
                  tickLine={false}
                  className="text-xs text-muted-foreground"
                />
                <YAxis 
                  yAxisId="currency"
                  orientation="left"
                  axisLine={false}
                  tickLine={false}
                  className="text-xs text-muted-foreground"
                  domain={[0, 'dataMax + 20']}
                  tickFormatter={(value) => `R$${value}`}
                />
                <YAxis 
                  yAxisId="percentage"
                  orientation="right"
                  axisLine={false}
                  tickLine={false}
                  className="text-xs text-muted-foreground"
                  domain={[0, 100]}
                  tickFormatter={(value) => `${value}%`}
                />
                
                {/* Spend bars - red */}
                <Bar 
                  yAxisId="currency"
                  dataKey="spend" 
                  fill="url(#spendGradient)"
                  radius={[4, 4, 0, 0]}
                  name="Gasto"
                />
                
                {/* Revenue bars - green */}
                <Bar 
                  yAxisId="currency"
                  dataKey="revenue" 
                  fill="url(#revenueGradient)"
                  radius={[4, 4, 0, 0]}
                  name="Revenue"
                  fillOpacity={0.8}
                />

                {/* Performance lines */}
                <Line 
                  yAxisId="currency"
                  type="monotone" 
                  dataKey="profit" 
                  stroke="#3b82f6" 
                  strokeWidth={2}
                  dot={{ fill: "#3b82f6", strokeWidth: 2, r: 4 }}
                  name="Lucro"
                />
                <Line 
                  yAxisId="percentage"
                  type="monotone" 
                  dataKey="roas" 
                  stroke="#8b5cf6" 
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={{ fill: "#8b5cf6", strokeWidth: 2, r: 4 }}
                  name="ROAS"
                />
                <Line 
                  yAxisId="percentage"
                  type="monotone" 
                  dataKey="ctr" 
                  stroke="#f59e0b" 
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={{ fill: "#f59e0b", strokeWidth: 2, r: 4 }}
                  name="CTR"
                />

                <Tooltip content={<CustomTooltip />} />

                <defs>
                  <linearGradient id="spendGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#ef4444" stopOpacity={1} />
                    <stop offset="50%" stopColor="#dc2626" stopOpacity={0.8} />
                    <stop offset="100%" stopColor="#b91c1c" stopOpacity={0.6} />
                  </linearGradient>
                  <linearGradient id="revenueGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22c55e" stopOpacity={1} />
                    <stop offset="50%" stopColor="#16a34a" stopOpacity={0.8} />
                    <stop offset="100%" stopColor="#15803d" stopOpacity={0.6} />
                  </linearGradient>
                </defs>
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Metrics Panel - like in the image */}
          <div className="lg:col-span-1">
            <div className="bg-gradient-to-br from-muted/30 to-muted/50 rounded-lg p-4 h-[400px] overflow-y-auto border border-border shadow-inner">
              <h3 className="font-semibold mb-4 text-center text-foreground">
                📅 {format(new Date(selectedDate.date), 'dd/MM/yyyy')}
              </h3>
              
              <div className="space-y-4">
                {metricsConfig.map((metric) => (
                  <div key={metric.key} className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/30 transition-colors">
                    <div className="flex items-center gap-2">
                      <div 
                        className="w-3 h-3 rounded-full shadow-sm"
                        style={{ backgroundColor: metric.color }}
                      />
                      <span className="text-sm font-medium text-foreground">{metric.name}</span>
                    </div>
                    <span className="text-sm font-semibold text-foreground">
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
                <div className="text-center space-y-3">
                  <div className="p-3 rounded-lg bg-gradient-to-r from-red-500/10 to-rose-500/10 border border-red-500/20">
                    <div className="text-xs text-muted-foreground">💸 Total Gasto</div>
                    <div className="text-lg font-bold text-red-600">
                      R$ {data.reduce((sum, item) => sum + item.spend, 0).toFixed(2)}
                    </div>
                  </div>
                  
                  <div className="p-3 rounded-lg bg-gradient-to-r from-green-500/10 to-emerald-500/10 border border-green-500/20">
                    <div className="text-xs text-muted-foreground">💰 Total Revenue</div>
                    <div className="text-lg font-bold text-green-600">
                      {formatBrlCurrency(data.reduce((sum, item) => sum + item.revenue, 0))}
                    </div>
                  </div>

                  <div className="p-3 rounded-lg bg-gradient-to-r from-blue-500/10 to-indigo-500/10 border border-blue-500/20">
                    <div className="text-xs text-muted-foreground">📈 ROAS Médio</div>
                    <div className="text-sm font-semibold text-blue-600">
                      {(data.reduce((sum, item) => sum + item.roas, 0) / data.length).toFixed(1)}%
                    </div>
                  </div>

                  <div className="p-3 rounded-lg bg-gradient-to-r from-purple-500/10 to-violet-500/10 border border-purple-500/20">
                    <div className="text-xs text-muted-foreground">👆 CTR Médio</div>
                    <div className="text-sm font-semibold text-purple-600">
                      {(data.reduce((sum, item) => sum + item.ctr, 0) / data.length).toFixed(2)}%
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap justify-center gap-6 mt-6 pt-4 border-t border-border">
          {metricsConfig.map((metric) => (
            <div key={metric.key} className="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/30 transition-colors">
              <div 
                className={cn(
                  "w-3 h-3 rounded-full shadow-sm",
                  metric.type === 'line' && "border-2 bg-white"
                )}
                style={{ 
                  backgroundColor: metric.type === 'bar' ? metric.color : 'white',
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