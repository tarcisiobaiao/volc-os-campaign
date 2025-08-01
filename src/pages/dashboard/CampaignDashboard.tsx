import { useState, useEffect, useMemo, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { CalendarIcon, TrendingUp, TrendingDown, DollarSign, Eye, MousePointer, Zap, RefreshCw, User } from "lucide-react";
import { format } from "date-fns";
import { DateRange } from "react-day-picker";
import { 
  LineChart, 
  Line, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Legend,
  ComposedChart
} from "recharts";
import { cn } from "@/lib/utils";
import { Layout } from "@/components/layout/Layout";
import { useMockData } from "@/services/mockDataService";

// Types
interface DashboardFilters {
  projectId: string;
  campaignId: string;
  dateRange: DateRange | undefined;
  period: "7d" | "30d" | "custom";
}

interface KPICardProps {
  title: string;
  value: string;
  change: number;
  icon: React.ReactNode;
  color: "success" | "warning" | "info" | "primary";
}

// KPI Card Component
const KPICard = ({ title, value, change, icon, color }: KPICardProps) => {
  const isPositive = change > 0;
  const colorClasses = {
    success: "border-success/20 bg-gradient-to-br from-success/5 to-success/10",
    warning: "border-warning/20 bg-gradient-to-br from-warning/5 to-warning/10", 
    info: "border-info/20 bg-gradient-to-br from-info/5 to-info/10",
    primary: "border-primary/20 bg-gradient-to-br from-primary/5 to-primary/10"
  };

  const iconColorClasses = {
    success: "text-success",
    warning: "text-warning",
    info: "text-info", 
    primary: "text-primary"
  };

  return (
    <Card className={cn("animate-fade-in shadow-card", colorClasses[color])}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <div className={cn("h-4 w-4", iconColorClasses[color])}>
          {icon}
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold mb-1">{value}</div>
        <div className="flex items-center text-xs">
          {isPositive ? (
            <TrendingUp className="mr-1 h-3 w-3 text-success" />
          ) : (
            <TrendingDown className="mr-1 h-3 w-3 text-destructive" />
          )}
          <span className={isPositive ? "text-success" : "text-destructive"}>
            {isPositive ? "+" : ""}{change.toFixed(1)}%
          </span>
          <span className="text-muted-foreground ml-1">vs last period</span>
        </div>
      </CardContent>
    </Card>
  );
};

// Loading Skeleton Component
const LoadingSkeleton = () => (
  <div className="space-y-6 animate-fade-in">
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {[1, 2, 3, 4].map((i) => (
        <Card key={i} className="animate-pulse">
          <CardHeader className="space-y-0 pb-2">
            <div className="h-4 bg-muted rounded w-20"></div>
          </CardHeader>
          <CardContent>
            <div className="h-8 bg-muted rounded w-16 mb-2"></div>
            <div className="h-4 bg-muted rounded w-24"></div>
          </CardContent>
        </Card>
      ))}
    </div>
    <div className="grid gap-6 md:grid-cols-2">
      {[1, 2].map((i) => (
        <Card key={i} className="animate-pulse">
          <CardHeader>
            <div className="h-6 bg-muted rounded w-32"></div>
          </CardHeader>
          <CardContent>
            <div className="h-64 bg-muted rounded"></div>
          </CardContent>
        </Card>
      ))}
    </div>
  </div>
);

// Empty State Component
const EmptyState = () => (
  <div className="flex flex-col items-center justify-center py-12 animate-fade-in">
    <div className="h-16 w-16 bg-muted rounded-full flex items-center justify-center mb-4">
      <TrendingUp className="h-8 w-8 text-muted-foreground" />
    </div>
    <h3 className="text-lg font-semibold mb-2">Nenhum dado encontrado</h3>
    <p className="text-muted-foreground text-center max-w-md">
      Selecione um projeto e campanha para visualizar as métricas do dashboard.
    </p>
  </div>
);

export default function CampaignDashboard() {
  const [filters, setFilters] = useState<DashboardFilters>({
    projectId: "",
    campaignId: "all", 
    dateRange: undefined,
    period: "7d"
  });
  
  const [isLoading, setIsLoading] = useState(false);
  const { projects, campaigns, dailyMetrics, refresh } = useMockData();
  const [selectedProject, setSelectedProject] = useState<any>(null);
  const [filteredMetrics, setFilteredMetrics] = useState<typeof dailyMetrics>([]);

  // Filter campaigns based on selected project
  const availableCampaigns = selectedProject 
    ? campaigns.filter(c => c.projectId === selectedProject.id)
    : [];

  // Fix: Memoize project selection to prevent loops
  useEffect(() => {
    if (filters.projectId && projects.length > 0) {
      const project = projects.find(p => p.id === filters.projectId);
      if (project && (!selectedProject || selectedProject.id !== project.id)) {
        setSelectedProject(project);
        setFilters(prev => ({ ...prev, campaignId: "all" }));
      }
    } else if (!filters.projectId) {
      setSelectedProject(null);
      setFilteredMetrics([]);
    }
  }, [filters.projectId, projects.length]); // Remove selectedProject from deps

  // Fix: Optimize metrics filtering to prevent loops
  useEffect(() => {
    console.log('[CampaignDashboard] Filters changed:', {
      projectId: filters.projectId,
      campaignId: filters.campaignId,
      hasProject: !!selectedProject
    });
    
    if (!filters.projectId || !selectedProject) {
      setFilteredMetrics([]);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    
    // Use setTimeout to simulate API call and prevent blocking
    const timeoutId = setTimeout(() => {
      try {
        // For now, return all dailyMetrics since they're general data
        // In real implementation, you'd filter by project/campaign
        setFilteredMetrics(dailyMetrics);
      } catch (error) {
        console.error('Error filtering metrics:', error);
        setFilteredMetrics([]);
      } finally {
        setIsLoading(false);
      }
    }, 300); // Reduced timeout for better UX

    return () => clearTimeout(timeoutId);
  }, [filters.projectId, filters.campaignId, selectedProject?.id, dailyMetrics.length]); // Stable dependencies

  // Fix: Memoize KPI calculations to prevent unnecessary recalculations
  const kpis = useMemo(() => {
    if (filteredMetrics.length === 0) {
      return {
        totalInvestment: 0,
        totalRevenue: 0,
        avgRoas: 0,
        avgCtr: 0,
        avgEcpm: 0,
        avgViewability: 0,
        totalImpressions: 0,
      };
    }

    const total = filteredMetrics.reduce((acc, curr) => ({
      investment: acc.investment + curr.investment,
      revenue: acc.revenue + curr.revenue,
      roas: acc.roas + curr.roas,
      ctr: acc.ctr + curr.ctr,
      ecpm: acc.ecpm + curr.ecpm,
      viewability: acc.viewability + curr.viewability,
      impressions: acc.impressions + curr.impressions,
    }), { investment: 0, revenue: 0, roas: 0, ctr: 0, ecpm: 0, viewability: 0, impressions: 0 });

    return {
      totalInvestment: total.investment,
      totalRevenue: total.revenue,
      avgRoas: total.roas / filteredMetrics.length,
      avgCtr: total.ctr / filteredMetrics.length,
      avgEcpm: total.ecpm / filteredMetrics.length,
      avgViewability: total.viewability / filteredMetrics.length,
      totalImpressions: total.impressions,
    };
  }, [filteredMetrics]);

  // Fix: Memoize format functions to prevent recreations
  const formatCurrency = useCallback((value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  }, []);

  const formatNumber = useCallback((value: number) => {
    return new Intl.NumberFormat('pt-BR').format(value);
  }, []);

  const handleRefresh = useCallback(() => {
    setIsLoading(true);
    refresh();
    setTimeout(() => setIsLoading(false), 500);
  }, [refresh]);

  return (
    <Layout>
      <div className="p-6 space-y-8 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between animate-fade-in">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold bg-gradient-dashboard bg-clip-text text-transparent">
                📊 Dashboard de Campanhas
              </h1>
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10">
                <User className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium text-primary">Felipe</span>
              </div>
            </div>
            <p className="text-muted-foreground">
              Monitore KPIs e performance das suas campanhas em tempo real
            </p>
          </div>
          
          <Button onClick={handleRefresh} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Atualizar
          </Button>
        </div>

        {/* Filters */}
        <Card className="shadow-card animate-scale-in">
          <CardHeader>
            <CardTitle className="text-lg">Filtros</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {/* Project Filter */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Projeto</label>
                <Select 
                  value={filters.projectId} 
                  onValueChange={(value) => setFilters(prev => ({ ...prev, projectId: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione um projeto" />
                  </SelectTrigger>
                  <SelectContent>
                    {projects.map((project) => (
                      <SelectItem key={project.id} value={project.id}>
                        {project.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Campaign Filter */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Campanha</label>
                <Select 
                  value={filters.campaignId} 
                  onValueChange={(value) => setFilters(prev => ({ ...prev, campaignId: value }))}
                  disabled={!filters.projectId}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Todas as campanhas" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas as campanhas</SelectItem>
                    {availableCampaigns.map((campaign) => (
                      <SelectItem key={campaign.id} value={campaign.id}>
                        {campaign.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Period Filter */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Período</label>
                <Select 
                  value={filters.period} 
                  onValueChange={(value: "7d" | "30d" | "custom") => setFilters(prev => ({ ...prev, period: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="7d">Últimos 7 dias</SelectItem>
                    <SelectItem value="30d">Últimos 30 dias</SelectItem>
                    <SelectItem value="custom">Período customizado</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Custom Date Range */}
              {filters.period === "custom" && (
                <div className="space-y-2">
                  <label className="text-sm font-medium">Datas</label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" className="w-full justify-start text-left font-normal">
                        <CalendarIcon className="mr-2 h-4 w-4" />
                        {filters.dateRange?.from ? (
                          filters.dateRange.to ? (
                            <>
                              {format(filters.dateRange.from, "LLL dd, y")} -{" "}
                              {format(filters.dateRange.to, "LLL dd, y")}
                            </>
                          ) : (
                            format(filters.dateRange.from, "LLL dd, y")
                          )
                        ) : (
                          <span>Selecione as datas</span>
                        )}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        initialFocus
                        mode="range"
                        defaultMonth={filters.dateRange?.from}
                        selected={filters.dateRange}
                        onSelect={(range) => setFilters(prev => ({ ...prev, dateRange: range }))}
                        numberOfMonths={2}
                      />
                    </PopoverContent>
                  </Popover>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Content - Add key to force proper animations */}
        {isLoading ? (
          <div key="loading">
            <LoadingSkeleton />
          </div>
        ) : !filters.projectId ? (
          <div key="empty">
            <EmptyState />
          </div>
        ) : (
          <div key="content" className="space-y-6">
            {/* KPI Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <KPICard
                title="Investimento Total"
                value={formatCurrency(kpis.totalInvestment)}
                change={12.5}
                icon={<DollarSign />}
                color="primary"
              />
              <KPICard
                title="ROAS Médio"
                value={kpis.avgRoas.toFixed(2)}
                change={8.2}
                icon={<TrendingUp />}
                color="success"
              />
              <KPICard
                title="Impressões"
                value={formatNumber(kpis.totalImpressions)}
                change={-2.1}
                icon={<Eye />}
                color="info"
              />
              <KPICard
                title="CTR Médio"
                value={`${kpis.avgCtr.toFixed(2)}%`}
                change={5.3}
                icon={<MousePointer />}
                color="warning"
              />
            </div>

            {/* Advanced Analytics Chart - Similar to uploaded image */}
            <Card className="shadow-card animate-fade-in col-span-full">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      📈 Site Analysis
                    </CardTitle>
                    <p className="text-sm text-muted-foreground mt-1">
                      {format(new Date(), "MMM dd, yyyy")}
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">• Revenue</span>
                        <p className="font-bold">{formatCurrency(kpis.totalRevenue)}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">• eCPM</span>
                        <p className="font-bold">${kpis.avgEcpm.toFixed(2)}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">• CPC</span>
                        <p className="font-bold">${(kpis.totalInvestment / kpis.totalImpressions * 1000).toFixed(2)}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">• Viewability</span>
                        <p className="font-bold">{kpis.avgViewability.toFixed(2)}%</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">• PMR</span>
                        <p className="font-bold">84.87%</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">• CTR</span>
                        <p className="font-bold">{kpis.avgCtr.toFixed(2)}%</p>
                      </div>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <ComposedChart data={filteredMetrics}>
                    <CartesianGrid strokeDasharray="3 3" className="opacity-20" />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={(value) => format(new Date(value), "yyyy-MM-dd")}
                      className="text-xs"
                    />
                    <YAxis yAxisId="left" className="text-xs" />
                    <YAxis yAxisId="right" orientation="right" className="text-xs" />
                    <Tooltip 
                      labelFormatter={(value) => format(new Date(value), "yyyy-MM-dd")}
                      formatter={(value: number, name: string) => {
                        if (name === "revenue") return [formatCurrency(value), "Revenue"];
                        if (name === "ecpm") return [`$${value}`, "eCPM"];
                        if (name === "ctr") return [`${value}%`, "CTR"];
                        if (name === "viewability") return [`${value}%`, "Viewability"];
                        return [value, name];
                      }}
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px"
                      }}
                    />
                    <Legend />
                    
                    {/* Revenue Bars - Green gradient like in the image */}
                    <Bar 
                      yAxisId="left"
                      dataKey="revenue" 
                      fill="url(#revenueGradient)"
                      radius={[4, 4, 0, 0]}
                      name="Revenue"
                    />
                    
                    {/* Performance Lines - Dotted like in the image */}
                    <Line 
                      yAxisId="right"
                      type="monotone" 
                      dataKey="ecpm" 
                      stroke="#00bcd4" 
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      name="eCPM"
                      dot={{ fill: "#00bcd4", strokeWidth: 2, r: 3 }}
                    />
                    <Line 
                      yAxisId="right"
                      type="monotone" 
                      dataKey="viewability" 
                      stroke="#e91e63" 
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      name="Viewability"
                      dot={{ fill: "#e91e63", strokeWidth: 2, r: 3 }}
                    />
                    <Line 
                      yAxisId="right"
                      type="monotone" 
                      dataKey="ctr" 
                      stroke="#ff5722" 
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      name="CTR"
                      dot={{ fill: "#ff5722", strokeWidth: 2, r: 3 }}
                    />
                    <Line 
                      yAxisId="right"
                      type="monotone" 
                      dataKey="pmr" 
                      stroke="#9c27b0" 
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      name="PMR"
                      dot={{ fill: "#9c27b0", strokeWidth: 2, r: 3 }}
                    />
                    
                    <defs>
                      <linearGradient id="revenueGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#4caf50" stopOpacity={0.9} />
                        <stop offset="50%" stopColor="#4caf50" stopOpacity={0.7} />
                        <stop offset="100%" stopColor="#4caf50" stopOpacity={0.3} />
                      </linearGradient>
                    </defs>
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Secondary Charts */}
            <div className="grid gap-6 lg:grid-cols-2">
              {/* ROAS and CTR Line Chart */}
              <Card className="shadow-card animate-fade-in">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Zap className="h-5 w-5 text-primary" />
                    ROAS e CTR ao Longo do Tempo
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={filteredMetrics}>
                      <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                      <XAxis 
                        dataKey="date" 
                        tickFormatter={(value) => format(new Date(value), "dd/MM")}
                        className="text-xs"
                      />
                      <YAxis yAxisId="left" className="text-xs" />
                      <YAxis yAxisId="right" orientation="right" className="text-xs" />
                      <Tooltip 
                        labelFormatter={(value) => format(new Date(value), "dd/MM/yyyy")}
                        contentStyle={{
                          backgroundColor: "hsl(var(--card))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: "8px"
                        }}
                      />
                      <Legend />
                      <Line 
                        yAxisId="left"
                        type="monotone" 
                        dataKey="roas" 
                        stroke="hsl(var(--primary))" 
                        strokeWidth={3}
                        name="ROAS"
                        dot={{ fill: "hsl(var(--primary))", strokeWidth: 2, r: 4 }}
                      />
                      <Line 
                        yAxisId="right"
                        type="monotone" 
                        dataKey="ctr" 
                        stroke="hsl(var(--info))" 
                        strokeWidth={3}
                        name="CTR (%)"
                        dot={{ fill: "hsl(var(--info))", strokeWidth: 2, r: 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              {/* Investment Bar Chart */}
              <Card className="shadow-card animate-fade-in">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <DollarSign className="h-5 w-5 text-success" />
                    Investimento Diário
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={filteredMetrics}>
                      <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                      <XAxis 
                        dataKey="date" 
                        tickFormatter={(value) => format(new Date(value), "dd/MM")}
                        className="text-xs"
                      />
                      <YAxis className="text-xs" />
                      <Tooltip 
                        labelFormatter={(value) => format(new Date(value), "dd/MM/yyyy")}
                        formatter={(value: number) => [formatCurrency(value), "Investimento"]}
                        contentStyle={{
                          backgroundColor: "hsl(var(--card))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: "8px"
                        }}
                      />
                      <Bar 
                        dataKey="investment" 
                        fill="url(#investmentGradient)"
                        radius={[4, 4, 0, 0]}
                        className="animate-chart-bar"
                      />
                      <defs>
                        <linearGradient id="investmentGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="hsl(var(--success))" stopOpacity={0.8} />
                          <stop offset="100%" stopColor="hsl(var(--success))" stopOpacity={0.2} />
                        </linearGradient>
                      </defs>
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}