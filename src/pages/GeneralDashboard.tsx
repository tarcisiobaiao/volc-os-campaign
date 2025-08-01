import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, StatusBadge, ROASBadge, PerformanceBadge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { 
  TrendingUp, 
  TrendingDown, 
  DollarSign, 
  Eye, 
  MousePointer, 
  BarChart3,
  Users,
  Zap,
  AlertTriangle,
  CheckCircle,
  Clock,
  RefreshCw,
  Minus,
  User
} from "lucide-react";
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
  PieChart,
  Pie,
  Cell
} from "recharts";
import { Link } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { cn } from "@/lib/utils";
import { useMockData } from "@/services/mockDataService";
import { format } from "date-fns";

const integrationStatus = [
  { name: "Google Ads", status: "online", lastSync: "2 min atrás" },
  { name: "Google Ad Manager", status: "online", lastSync: "5 min atrás" },
  { name: "Analytics", status: "pending", lastSync: "15 min atrás" }
];

const alerts = [
  { type: "warning", message: "Campanha 'Black Friday' com CTR abaixo do esperado", time: "10 min atrás" },
  { type: "success", message: "Meta de ROAS atingida no projeto E-commerce", time: "1 hora atrás" },
  { type: "error", message: "Falha na sincronização com Google Ads", time: "2 horas atrás" }
];

const COLORS = ['hsl(var(--success))', 'hsl(var(--info))', 'hsl(var(--warning))', 'hsl(var(--destructive))'];

export default function GeneralDashboard() {
  const [isLoading, setIsLoading] = useState(true);
  const [selectedPeriod, setSelectedPeriod] = useState("7d");
  const { projects, dailyMetrics, summary, refresh } = useMockData();

  useEffect(() => {
    // Simulate loading
    setTimeout(() => setIsLoading(false), 1000);
  }, []);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const getTrendIcon = (trend: 'up' | 'down' | 'stable') => {
    switch (trend) {
      case 'up': return <TrendingUp className="h-4 w-4 text-success" />;
      case 'down': return <TrendingDown className="h-4 w-4 text-destructive" />;
      default: return <Minus className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getTrendText = (trend: 'up' | 'down' | 'stable') => {
    switch (trend) {
      case 'up': return "Subindo";
      case 'down': return "Caindo";
      default: return "Estável";
    }
  };

  const handleRefresh = () => {
    setIsLoading(true);
    refresh();
    setTimeout(() => setIsLoading(false), 500);
  };


  if (isLoading) {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-screen">
          <LoadingSpinner size="lg" text="Carregando dashboard..." />
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="p-6 space-y-8 max-w-7xl mx-auto">
        {/* Header with User and Controls */}
        <div className="flex items-center justify-between animate-fade-in">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold bg-gradient-dashboard bg-clip-text text-transparent">
                🏠 Dashboard Geral
              </h1>
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10">
                <User className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium text-primary">Felipe</span>
              </div>
            </div>
            <p className="text-muted-foreground">
              Visão geral de todas as campanhas e projetos
            </p>
          </div>
          
          <div className="flex items-center gap-3">
            <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="today">📅 Hoje</SelectItem>
                <SelectItem value="7d">Últimos 7 dias</SelectItem>
                <SelectItem value="30d">Últimos 30 dias</SelectItem>
              </SelectContent>
            </Select>
            <Button onClick={handleRefresh} variant="outline" size="sm">
              <RefreshCw className="h-4 w-4 mr-2" />
              Atualizar
            </Button>
          </div>
        </div>

        {/* Alerts */}
        <Card className="shadow-card animate-scale-in border-warning/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-warning">
              <AlertTriangle className="h-5 w-5" />
              Alertas e Notificações
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {alerts.map((alert, index) => (
                <div key={index} className="flex items-start gap-3 p-3 rounded-lg bg-muted/30">
                  {alert.type === "warning" && <AlertTriangle className="h-4 w-4 text-warning mt-0.5" />}
                  {alert.type === "success" && <CheckCircle className="h-4 w-4 text-success mt-0.5" />}
                  {alert.type === "error" && <AlertTriangle className="h-4 w-4 text-destructive mt-0.5" />}
                  <div className="flex-1">
                    <p className="text-sm font-medium">{alert.message}</p>
                    <p className="text-xs text-muted-foreground">{alert.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* KPI Overview - Cards Resumo */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 animate-fade-in">
          <Card className="shadow-card border-primary/20 bg-gradient-to-br from-primary/5 to-primary/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">💰 Investido</CardTitle>
              <DollarSign className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatCurrency(summary.totalInvestment)}</div>
              <div className="flex items-center text-xs mt-1">
                <TrendingUp className="mr-1 h-3 w-3 text-success" />
                <span className="text-success">↗️ +{summary.trendsPercentage.investment}%</span>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-success/20 bg-gradient-to-br from-success/5 to-success/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">💵 Faturado</CardTitle>
              <TrendingUp className="h-4 w-4 text-success" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatCurrency(summary.totalRevenue)}</div>
              <div className="flex items-center text-xs mt-1">
                <TrendingUp className="mr-1 h-3 w-3 text-success" />
                <span className="text-success">↗️ +{summary.trendsPercentage.revenue}%</span>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-info/20 bg-gradient-to-br from-info/5 to-info/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">📈 ROAS Geral</CardTitle>
              <BarChart3 className="h-4 w-4 text-info" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.generalRoas}%</div>
              <div className="flex items-center text-xs mt-1">
                <TrendingUp className="mr-1 h-3 w-3 text-success" />
                <span className="text-success">↗️ +{summary.trendsPercentage.roas}%</span>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-success/20 bg-gradient-to-br from-success/5 to-success/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">💚 Lucro Líq</CardTitle>
              <DollarSign className="h-4 w-4 text-success" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatCurrency(summary.totalProfit)}</div>
              <div className="flex items-center text-xs mt-1">
                <TrendingUp className="mr-1 h-3 w-3 text-success" />
                <span className="text-success">↗️ +{summary.trendsPercentage.profit}%</span>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-warning/20 bg-gradient-to-br from-warning/5 to-warning/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">👑 ROI Final</CardTitle>
              <TrendingUp className="h-4 w-4 text-warning" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.finalRoi}%</div>
              <div className="flex items-center text-xs mt-1">
                <TrendingUp className="mr-1 h-3 w-3 text-success" />
                <span className="text-success">↗️ +{summary.trendsPercentage.roi}%</span>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-purple-500/20 bg-gradient-to-br from-purple-500/5 to-purple-500/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">🎯 Campanhas</CardTitle>
              <Users className="h-4 w-4 text-purple-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">Ativas: {summary.activeCampaigns}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs">🔴 {summary.campaignStatus.red}</span>
                <span className="text-xs">🟡 {summary.campaignStatus.yellow}</span>
                <span className="text-xs">🟢 {summary.campaignStatus.green}</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Charts Section */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Weekly Performance */}
          <Card className="shadow-card animate-fade-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-primary" />
                Performance Semanal
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={dailyMetrics}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis 
                    dataKey="date" 
                    tickFormatter={(value) => format(new Date(value), "dd/MM")}
                    className="text-xs" 
                  />
                  <YAxis className="text-xs" />
                  <Tooltip 
                    labelFormatter={(value) => format(new Date(value), "dd/MM/yyyy")}
                    formatter={(value: number, name: string) => {
                      if (name === "investment" || name === "revenue") {
                        return [formatCurrency(value), name === "investment" ? "Investimento" : "Receita"];
                      }
                      return [value, name === "roas" ? "ROAS" : name];
                    }}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px"
                    }}
                  />
                  <Bar dataKey="investment" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="revenue" fill="hsl(var(--success))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Projects Overview */}
          <Card className="shadow-card animate-fade-in">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5 text-info" />
                Distribuição por Projeto
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={projects}
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    dataKey="investment"
                    label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(1)}%`}
                  >
                    {projects.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    formatter={(value: number) => [formatCurrency(value), "Investimento"]}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px"
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        {/* Projects Table */}
        <Card className="shadow-card animate-fade-in">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5 text-primary" />
                Resumo por Projeto
              </CardTitle>
              <CardDescription>Performance detalhada de cada projeto</CardDescription>
            </div>
            <Link to="/dashboard/campaigns">
              <Button variant="outline" size="sm">
                Ver Detalhes
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-3 font-medium">Projeto</th>
                    <th className="text-left p-3 font-medium">Investimento</th>
                    <th className="text-left p-3 font-medium">Performance</th>
                    <th className="text-left p-3 font-medium">Campanhas</th>
                    <th className="text-left p-3 font-medium">Tendência</th>
                    <th className="text-left p-3 font-medium">Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((project, index) => (
                    <tr key={index} className="border-b hover:bg-muted/50 transition-colors">
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div className="h-12 w-12 bg-gradient-dashboard rounded-lg flex items-center justify-center text-white font-bold">
                            📂
                          </div>
                          <div>
                            <p className="font-medium text-base">{project.domain}</p>
                            <p className="text-sm text-muted-foreground">{project.name}</p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <div className="text-lg font-bold text-primary">
                          💰 {formatCurrency(project.investment)}
                        </div>
                      </td>
                      <td className="p-4">
                        <div className="space-y-1">
                          <div className="text-sm font-medium">ROAS: {project.roas}% | ROI: {project.roi}%</div>
                          <div className="flex items-center gap-2">
                            {getTrendIcon(project.trend)}
                            <span className="text-sm">{getTrendText(project.trend)}</span>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <span className="text-sm">🟢 {project.campaigns.green}</span>
                          <span className="text-sm">🟡 {project.campaigns.yellow}</span>
                          <span className="text-sm">🔴 {project.campaigns.red}</span>
                        </div>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          {project.trend === 'up' && <span className="text-success">📈 ↗️ Subindo</span>}
                          {project.trend === 'down' && <span className="text-destructive">📉 ↘️ Caindo</span>}
                          {project.trend === 'stable' && <span className="text-muted-foreground">📊 ➡️ Estável</span>}
                        </div>
                      </td>
                      <td className="p-4">
                        <Link to={`/dashboard/campaigns?project=${project.id}`}>
                          <Button variant="outline" size="sm" className="text-xs">
                            [Ver Detalhes]
                          </Button>
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Integration Status */}
        <Card className="shadow-card animate-fade-in">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-warning" />
              Status das Integrações
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-3">
              {integrationStatus.map((integration, index) => (
                <div key={index} className="flex items-center justify-between p-4 rounded-lg bg-muted/30">
                  <div>
                    <p className="font-medium">{integration.name}</p>
                    <p className="text-sm text-muted-foreground flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {integration.lastSync}
                    </p>
                  </div>
                  <StatusBadge status={integration.status as "online" | "offline" | "pending"} />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}