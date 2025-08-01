import { useState, useEffect, useMemo, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { 
  ArrowLeft, 
  RefreshCw, 
  Search, 
  Download, 
  Plus, 
  Edit, 
  Pause, 
  Play,
  Eye,
  DollarSign,
  TrendingUp,
  TrendingDown,
  AlertTriangle
} from "lucide-react";
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Legend
} from "recharts";
import { cn } from "@/lib/utils";
import { Layout } from "@/components/layout/Layout";
import { useProjectData } from "@/services/mockDataService";

// Types
interface ProjectFilters {
  period: "today" | "yesterday" | "7d" | "30d" | "custom";
  comparison: "yesterday" | "lastWeek" | "lastMonth";
  search: string;
  status: "all" | "active" | "paused" | "critical";
}

interface MetricCardProps {
  title: string;
  value: string;
  comparison: string;
  change: number;
  icon: React.ReactNode;
  color: "success" | "warning" | "danger" | "info";
}

// Metric Card with Comparison
const MetricCard = ({ title, value, comparison, change, icon, color }: MetricCardProps) => {
  const isPositive = change > 0;
  const colorClasses = {
    success: "border-success/20 bg-gradient-to-br from-success/5 to-success/10",
    warning: "border-warning/20 bg-gradient-to-br from-warning/5 to-warning/10",
    danger: "border-destructive/20 bg-gradient-to-br from-destructive/5 to-destructive/10",
    info: "border-info/20 bg-gradient-to-br from-info/5 to-info/10"
  };

  return (
    <Card className={cn("animate-fade-in shadow-card", colorClasses[color])}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <div className="h-4 w-4 text-primary">{icon}</div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold mb-1">{value}</div>
        <div className="text-xs text-muted-foreground mb-2">{comparison}</div>
        <div className="flex items-center text-xs">
          {isPositive ? (
            <TrendingUp className="mr-1 h-3 w-3 text-success" />
          ) : (
            <TrendingDown className="mr-1 h-3 w-3 text-destructive" />
          )}
          <span className={isPositive ? "text-success" : "text-destructive"}>
            {isPositive ? "+" : ""}{change.toFixed(1)}%
          </span>
        </div>
      </CardContent>
    </Card>
  );
};

// Campaign Card Component
const CampaignCard = ({ campaign, onAction }: { campaign: any; onAction: (action: string, campaignId: string) => void }) => {
  const getStatusColor = (roas: number) => {
    if (roas >= 150) return "success";
    if (roas >= 100) return "warning";
    return "danger";
  };

  const getStatusIcon = (roas: number) => {
    if (roas >= 150) return "🟢";
    if (roas >= 100) return "🟡";
    return "🔴";
  };

  const isCritical = campaign.roas < 100;

  return (
    <Card className={cn(
      "animate-fade-in hover:shadow-lg transition-all duration-300",
      isCritical && "border-destructive/40 bg-destructive/5"
    )}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{getStatusIcon(campaign.roas)}</span>
            <div>
              <h3 className="font-semibold text-sm">{campaign.name}</h3>
              <p className="text-xs text-muted-foreground">{campaign.description}</p>
            </div>
          </div>
          {isCritical && (
            <AlertTriangle className="h-4 w-4 text-destructive" />
          )}
        </div>

        <div className="grid grid-cols-3 gap-4 mb-3">
          <div>
            <p className="text-xs text-muted-foreground">Investido</p>
            <p className="font-semibold">R$ {campaign.investment.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Faturado</p>
            <p className="font-semibold">R$ {campaign.revenue.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">ROAS</p>
            <Badge variant={getStatusColor(campaign.roas)}>
              {campaign.roas.toFixed(0)}%
            </Badge>
          </div>
        </div>

        <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
          <span>📊 Funil: {campaign.funnelUrls || 2} URLs</span>
          <span>👁️ {campaign.views || Math.floor(Math.random() * 1000 + 100)} views</span>
        </div>

        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => onAction("edit", campaign.id)}
            className="flex-1"
          >
            <Edit className="h-3 w-3 mr-1" />
            Editar
          </Button>
          {isCritical ? (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => onAction("pause", campaign.id)}
            >
              <Pause className="h-3 w-3 mr-1" />
              Pausar
            </Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onAction("pause", campaign.id)}
            >
              <Pause className="h-3 w-3" />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default function ProjectDashboard() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { projectData, isLoading } = useProjectData(projectId || "");
  
  const [filters, setFilters] = useState<ProjectFilters>({
    period: "today",
    comparison: "yesterday",
    search: "",
    status: "all"
  });

  const [autoRefresh, setAutoRefresh] = useState(false);

  // Auto-refresh every 30 minutes
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      window.location.reload();
    }, 30 * 60 * 1000); // 30 minutes

    return () => clearInterval(interval);
  }, [autoRefresh]);

  // Format currency
  const formatCurrency = useCallback((value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  }, []);

  // Calculate metrics with comparison
  const metrics = useMemo(() => {
    if (!projectData?.project || !projectData?.yesterdayData) return null;

    const today = projectData.project;
    const yesterday = projectData.yesterdayData;

    return {
      investment: {
        value: today.investment,
        comparison: yesterday.investment,
        change: ((today.investment - yesterday.investment) / yesterday.investment) * 100
      },
      revenue: {
        value: today.revenue,
        comparison: yesterday.revenue,
        change: ((today.revenue - yesterday.revenue) / yesterday.revenue) * 100
      },
      roas: {
        value: today.roas,
        comparison: yesterday.roas,
        change: ((today.roas - yesterday.roas) / yesterday.roas) * 100
      },
      grossProfit: {
        value: today.grossProfit,
        comparison: yesterday.grossProfit,
        change: ((today.grossProfit - yesterday.grossProfit) / yesterday.grossProfit) * 100
      },
      netProfit: {
        value: today.netProfit,
        comparison: yesterday.netProfit,
        change: ((today.netProfit - yesterday.netProfit) / yesterday.netProfit) * 100
      },
      roi: {
        value: today.roi,
        comparison: yesterday.roi,
        change: ((today.roi - yesterday.roi) / yesterday.roi) * 100
      }
    };
  }, [projectData]);

  // Filter campaigns
  const filteredCampaigns = useMemo(() => {
    if (!projectData?.campaigns) return [];

    return projectData.campaigns.filter((campaign: any) => {
      const matchesSearch = campaign.name.toLowerCase().includes(filters.search.toLowerCase()) ||
                           campaign.description.toLowerCase().includes(filters.search.toLowerCase());

      const matchesStatus = filters.status === "all" || 
                           (filters.status === "critical" && campaign.roas < 100) ||
                           (filters.status === "active" && campaign.status === "active") ||
                           (filters.status === "paused" && campaign.status === "paused");

      return matchesSearch && matchesStatus;
    });
  }, [projectData?.campaigns, filters.search, filters.status]);

  // Handle campaign actions
  const handleCampaignAction = useCallback((action: string, campaignId: string) => {
    console.log(`Action: ${action} on campaign: ${campaignId}`);
    // TODO: Implement actual actions
  }, []);

  if (isLoading) {
    return (
      <Layout>
        <div className="p-6">
          <div className="animate-pulse space-y-6">
            <div className="h-8 bg-muted rounded w-64"></div>
            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
              {[1,2,3,4,5,6].map(i => (
                <div key={i} className="h-24 bg-muted rounded"></div>
              ))}
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  if (!projectData?.project) {
    return (
      <Layout>
        <div className="p-6">
          <div className="text-center py-12">
            <h2 className="text-xl font-semibold mb-2">Projeto não encontrado</h2>
            <Button onClick={() => navigate("/dashboard")} variant="outline">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Voltar ao Dashboard
            </Button>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between animate-fade-in">
          <div className="flex items-center gap-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate("/dashboard")}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Voltar
            </Button>
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-2">
                📂 {projectData.project.name}
              </h1>
              <p className="text-muted-foreground">
                Dashboard detalhado do projeto
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant={autoRefresh ? "default" : "outline"}
              size="sm"
              onClick={() => setAutoRefresh(!autoRefresh)}
            >
              <RefreshCw className={cn("h-4 w-4 mr-2", autoRefresh && "animate-spin")} />
              Auto-refresh
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.location.reload()}
            >
              Atualizar
            </Button>
          </div>
        </div>

        {/* Filters */}
        <Card className="shadow-card animate-scale-in">
          <CardHeader>
            <CardTitle>Filtros e Período</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Período</label>
                <Select 
                  value={filters.period} 
                  onValueChange={(value: any) => setFilters(prev => ({ ...prev, period: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="today">Hoje</SelectItem>
                    <SelectItem value="yesterday">Ontem</SelectItem>
                    <SelectItem value="7d">Últimos 7 dias</SelectItem>
                    <SelectItem value="30d">Últimos 30 dias</SelectItem>
                    <SelectItem value="custom">Personalizado</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Comparar com</label>
                <Select 
                  value={filters.comparison} 
                  onValueChange={(value: any) => setFilters(prev => ({ ...prev, comparison: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="yesterday">Ontem</SelectItem>
                    <SelectItem value="lastWeek">Semana anterior</SelectItem>
                    <SelectItem value="lastMonth">Mês anterior</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Status</label>
                <Select 
                  value={filters.status} 
                  onValueChange={(value: any) => setFilters(prev => ({ ...prev, status: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="active">Ativas</SelectItem>
                    <SelectItem value="paused">Pausadas</SelectItem>
                    <SelectItem value="critical">Críticas</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Buscar</label>
                <div className="relative">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Buscar campanhas..."
                    value={filters.search}
                    onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
                    className="pl-9"
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Metrics Cards */}
        {metrics && (
          <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
            <MetricCard
              title="💰 Investido"
              value={formatCurrency(metrics.investment.value)}
              comparison={`Ontem: ${formatCurrency(metrics.investment.comparison)}`}
              change={metrics.investment.change}
              icon={<DollarSign />}
              color="info"
            />
            <MetricCard
              title="💵 Faturado"
              value={formatCurrency(metrics.revenue.value)}
              comparison={`Ontem: ${formatCurrency(metrics.revenue.comparison)}`}
              change={metrics.revenue.change}
              icon={<DollarSign />}
              color="success"
            />
            <MetricCard
              title="📈 ROAS"
              value={`${metrics.roas.value.toFixed(0)}%`}
              comparison={`Ontem: ${metrics.roas.comparison.toFixed(0)}%`}
              change={metrics.roas.change}
              icon={<TrendingUp />}
              color="success"
            />
            <MetricCard
              title="💚 L. Bruto"
              value={formatCurrency(metrics.grossProfit.value)}
              comparison={`Ontem: ${formatCurrency(metrics.grossProfit.comparison)}`}
              change={metrics.grossProfit.change}
              icon={<DollarSign />}
              color="success"
            />
            <MetricCard
              title="💎 L. Líquido"
              value={formatCurrency(metrics.netProfit.value)}
              comparison={`Ontem: ${formatCurrency(metrics.netProfit.comparison)}`}
              change={metrics.netProfit.change}
              icon={<DollarSign />}
              color="warning"
            />
            <MetricCard
              title="👑 ROI"
              value={`${metrics.roi.value.toFixed(0)}%`}
              comparison={`Ontem: ${metrics.roi.comparison.toFixed(0)}%`}
              change={metrics.roi.change}
              icon={<TrendingUp />}
              color="info"
            />
          </div>
        )}

        {/* Campaigns List */}
        <Card className="shadow-card animate-fade-in">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Lista de Campanhas</CardTitle>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline">
                  <Download className="h-4 w-4 mr-2" />
                  Exportar
                </Button>
                <Button size="sm">
                  <Plus className="h-4 w-4 mr-2" />
                  Nova Campanha
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-1">
              {filteredCampaigns.map((campaign: any) => (
                <CampaignCard
                  key={campaign.id}
                  campaign={campaign}
                  onAction={handleCampaignAction}
                />
              ))}
            </div>

            {filteredCampaigns.length === 0 && (
              <div className="text-center py-12">
                <p className="text-muted-foreground">Nenhuma campanha encontrada com os filtros aplicados</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Historical Chart */}
        {projectData?.historicalData && (
          <Card className="shadow-card animate-fade-in">
            <CardHeader>
              <CardTitle>📈 Histórico - Últimos 30 dias</CardTitle>
              <div className="flex gap-2">
                <Badge variant="outline">Receita</Badge>
                <Badge variant="outline">Investimento</Badge>
                <Badge variant="outline">ROAS</Badge>
                <Badge variant="outline">ROI</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={projectData.historicalData}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis 
                    dataKey="dateFormatted" 
                    className="text-xs"
                  />
                  <YAxis className="text-xs" />
                  <Tooltip 
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px"
                    }}
                  />
                  <Legend />
                  <Line 
                    type="monotone" 
                    dataKey="revenue" 
                    stroke="hsl(var(--success))" 
                    strokeWidth={2}
                    name="Receita"
                  />
                  <Line 
                    type="monotone" 
                    dataKey="investment" 
                    stroke="hsl(var(--warning))" 
                    strokeWidth={2}
                    name="Investimento"
                  />
                  <Line 
                    type="monotone" 
                    dataKey="roas" 
                    stroke="hsl(var(--primary))" 
                    strokeWidth={2}
                    name="ROAS"
                  />
                  <Line 
                    type="monotone" 
                    dataKey="roi" 
                    stroke="hsl(var(--info))" 
                    strokeWidth={2}
                    name="ROI"
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}