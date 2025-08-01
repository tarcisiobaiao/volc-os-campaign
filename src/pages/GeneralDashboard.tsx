import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, StatusBadge, ROASBadge, PerformanceBadge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
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
  Clock
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

// Mock data
const generalMetrics = {
  totalInvestment: 45800,
  totalRevenue: 156400, 
  totalCampaigns: 12,
  activeCampaigns: 8,
  avgRoas: 3.4,
  totalImpressions: 2840000,
  totalClicks: 68500,
  avgCtr: 2.4
};

const projectsOverview = [
  { name: "E-commerce Store", investment: 15200, roas: 4.2, status: "excellent", campaigns: 4 },
  { name: "SaaS Platform", investment: 18600, roas: 3.8, status: "good", campaigns: 3 },
  { name: "Mobile App", investment: 12000, roas: 2.9, status: "average", campaigns: 3 },
  { name: "Service Business", investment: 8500, roas: 2.1, status: "poor", campaigns: 2 }
];

const weeklyData = [
  { day: "Dom", investment: 5200, revenue: 18400, roas: 3.5 },
  { day: "Seg", investment: 6800, revenue: 22100, roas: 3.3 },
  { day: "Ter", investment: 7200, revenue: 25600, roas: 3.6 },
  { day: "Qua", investment: 6500, revenue: 23800, roas: 3.7 },
  { day: "Qui", investment: 7800, revenue: 28200, roas: 3.6 },
  { day: "Sex", investment: 8100, revenue: 29800, roas: 3.7 },
  { day: "Sáb", investment: 4200, revenue: 16500, roas: 3.9 }
];

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
        {/* Header */}
        <div className="animate-fade-in">
          <h1 className="text-3xl font-bold bg-gradient-dashboard bg-clip-text text-transparent">
            Dashboard Geral
          </h1>
          <p className="text-muted-foreground mt-2">
            Visão geral de todas as campanhas e projetos
          </p>
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

        {/* KPI Overview */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4 animate-fade-in">
          <Card className="shadow-card border-primary/20 bg-gradient-to-br from-primary/5 to-primary/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Investimento Total</CardTitle>
              <DollarSign className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatCurrency(generalMetrics.totalInvestment)}</div>
              <div className="flex items-center text-xs mt-1">
                <TrendingUp className="mr-1 h-3 w-3 text-success" />
                <span className="text-success">+12.5%</span>
                <span className="text-muted-foreground ml-1">vs semana anterior</span>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-success/20 bg-gradient-to-br from-success/5 to-success/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Receita Total</CardTitle>
              <TrendingUp className="h-4 w-4 text-success" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatCurrency(generalMetrics.totalRevenue)}</div>
              <div className="flex items-center gap-2 mt-1">
                <ROASBadge roas={generalMetrics.avgRoas} />
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-info/20 bg-gradient-to-br from-info/5 to-info/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Campanhas</CardTitle>
              <BarChart3 className="h-4 w-4 text-info" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{generalMetrics.activeCampaigns}/{generalMetrics.totalCampaigns}</div>
              <div className="flex items-center text-xs mt-1">
                <span className="text-muted-foreground">Ativas / Total</span>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-warning/20 bg-gradient-to-br from-warning/5 to-warning/10">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">CTR Médio</CardTitle>
              <MousePointer className="h-4 w-4 text-warning" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{generalMetrics.avgCtr}%</div>
              <div className="flex items-center text-xs mt-1">
                <TrendingUp className="mr-1 h-3 w-3 text-success" />
                <span className="text-success">+0.3%</span>
                <span className="text-muted-foreground ml-1">vs semana anterior</span>
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
                <BarChart data={weeklyData}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis dataKey="day" className="text-xs" />
                  <YAxis className="text-xs" />
                  <Tooltip 
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
                    data={projectsOverview}
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    dataKey="investment"
                    label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(1)}%`}
                  >
                    {projectsOverview.map((entry, index) => (
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
                    <th className="text-left p-3 font-medium">ROAS</th>
                    <th className="text-left p-3 font-medium">Campanhas</th>
                    <th className="text-left p-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {projectsOverview.map((project, index) => (
                    <tr key={index} className="border-b hover:bg-muted/50 transition-colors">
                      <td className="p-3 font-medium">{project.name}</td>
                      <td className="p-3">{formatCurrency(project.investment)}</td>
                      <td className="p-3">
                        <ROASBadge roas={project.roas} />
                      </td>
                      <td className="p-3">{project.campaigns} ativas</td>
                      <td className="p-3">
                        <PerformanceBadge 
                          value={project.roas * 25} 
                          thresholds={{ excellent: 100, good: 75, average: 50 }}
                        />
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