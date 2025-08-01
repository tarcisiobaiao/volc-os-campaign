import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { CalendarIcon, TrendingUp, TrendingDown, DollarSign, Eye, MousePointer, Zap } from "lucide-react";
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
  Legend
} from "recharts";
import { cn } from "@/lib/utils";

// Types
interface CampaignMetrics {
  date: string;
  roas: number;
  investment: number;
  pageViews: number;
  ctr: number;
  ecpm: number;
  campaign: string;
  project: string;
}

interface Project {
  id: string;
  name: string;
}

interface Campaign {
  id: string;
  name: string;
  projectId: string;
}

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

// Mock data - replace with real API calls
const mockProjects: Project[] = [
  { id: "1", name: "E-commerce Store" },
  { id: "2", name: "SaaS Platform" },
  { id: "3", name: "Mobile App" },
];

const mockCampaigns: Campaign[] = [
  { id: "1", name: "Black Friday Sale", projectId: "1" },
  { id: "2", name: "Summer Campaign", projectId: "1" },
  { id: "3", name: "Product Launch", projectId: "2" },
  { id: "4", name: "User Acquisition", projectId: "3" },
];

const mockMetrics: CampaignMetrics[] = [
  { date: "2024-01-15", roas: 3.2, investment: 1200, pageViews: 15400, ctr: 2.1, ecpm: 4.5, campaign: "Black Friday Sale", project: "E-commerce Store" },
  { date: "2024-01-16", roas: 3.8, investment: 1400, pageViews: 16800, ctr: 2.3, ecpm: 4.8, campaign: "Black Friday Sale", project: "E-commerce Store" },
  { date: "2024-01-17", roas: 4.1, investment: 1600, pageViews: 18200, ctr: 2.5, ecpm: 5.1, campaign: "Black Friday Sale", project: "E-commerce Store" },
  { date: "2024-01-18", roas: 3.9, investment: 1500, pageViews: 17600, ctr: 2.4, ecpm: 4.9, campaign: "Black Friday Sale", project: "E-commerce Store" },
  { date: "2024-01-19", roas: 4.3, investment: 1700, pageViews: 19400, ctr: 2.7, ecpm: 5.3, campaign: "Black Friday Sale", project: "E-commerce Store" },
  { date: "2024-01-20", roas: 4.0, investment: 1550, pageViews: 18800, ctr: 2.6, ecpm: 5.0, campaign: "Black Friday Sale", project: "E-commerce Store" },
  { date: "2024-01-21", roas: 4.5, investment: 1800, pageViews: 20200, ctr: 2.8, ecpm: 5.5, campaign: "Black Friday Sale", project: "E-commerce Store" },
];

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
  const [metrics, setMetrics] = useState<CampaignMetrics[]>([]);
  const [availableCampaigns, setAvailableCampaigns] = useState<Campaign[]>([]);

  // Filter campaigns based on selected project
  useEffect(() => {
    if (filters.projectId) {
      const filteredCampaigns = mockCampaigns.filter(c => c.projectId === filters.projectId);
      setAvailableCampaigns(filteredCampaigns);
      setFilters(prev => ({ ...prev, campaignId: "all" }));
    } else {
      setAvailableCampaigns([]);
    }
  }, [filters.projectId]);

  // Fetch metrics data
  useEffect(() => {
    console.log('[CampaignDashboard]', filters);
    
    if (!filters.projectId) {
      setMetrics([]);
      return;
    }

    setIsLoading(true);
    
    // Simulate API call
    setTimeout(() => {
      let filteredMetrics = mockMetrics;
      
      // Filter by project/campaign
      const selectedProject = mockProjects.find(p => p.id === filters.projectId);
      if (selectedProject) {
        filteredMetrics = filteredMetrics.filter(m => m.project === selectedProject.name);
      }
      
      if (filters.campaignId && filters.campaignId !== "all") {
        const selectedCampaign = availableCampaigns.find(c => c.id === filters.campaignId);
        if (selectedCampaign) {
          filteredMetrics = filteredMetrics.filter(m => m.campaign === selectedCampaign.name);
        }
      }
      
      setMetrics(filteredMetrics);
      setIsLoading(false);
    }, 800);
  }, [filters, availableCampaigns]);

  // Calculate aggregated KPIs
  const calculateKPIs = () => {
    if (metrics.length === 0) {
      return {
        totalInvestment: 0,
        avgRoas: 0,
        totalPageViews: 0,
        avgCtr: 0,
      };
    }

    const total = metrics.reduce((acc, curr) => ({
      investment: acc.investment + curr.investment,
      roas: acc.roas + curr.roas,
      pageViews: acc.pageViews + curr.pageViews,
      ctr: acc.ctr + curr.ctr,
    }), { investment: 0, roas: 0, pageViews: 0, ctr: 0 });

    return {
      totalInvestment: total.investment,
      avgRoas: total.roas / metrics.length,
      totalPageViews: total.pageViews,
      avgCtr: total.ctr / metrics.length,
    };
  };

  const kpis = calculateKPIs();

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  return (
    <div className="min-h-screen bg-background p-4 lg:p-8">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="animate-fade-in">
          <h1 className="text-3xl font-bold bg-gradient-dashboard bg-clip-text text-transparent">
            Dashboard de Campanhas
          </h1>
          <p className="text-muted-foreground mt-2">
            Monitore KPIs e performance das suas campanhas em tempo real
          </p>
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
                    {mockProjects.map((project) => (
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

        {/* Content */}
        {isLoading ? (
          <LoadingSkeleton />
        ) : !filters.projectId ? (
          <EmptyState />
        ) : (
          <div className="space-y-6">
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
                title="Page Views"
                value={formatNumber(kpis.totalPageViews)}
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

            {/* Charts */}
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
                    <LineChart data={metrics}>
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
                    <BarChart data={metrics}>
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
    </div>
  );
}