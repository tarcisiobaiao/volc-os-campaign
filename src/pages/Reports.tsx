import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Layout } from "@/components/layout/Layout";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { 
  FileText, 
  Download, 
  Calendar as CalendarIcon,
  Filter,
  BarChart3,
  TrendingUp,
  Eye,
  DollarSign
} from "lucide-react";
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
  PieChart,
  Pie,
  Cell
} from "recharts";

// Mock data for reports
const reportTypes = [
  { id: "performance", name: "Performance de Campanhas", description: "Métricas detalhadas de ROAS, CTR e conversões" },
  { id: "cost", name: "Análise de Custos", description: "Breakdown de investimentos e otimizações" },
  { id: "audience", name: "Comportamento de Audiência", description: "Insights sobre engajamento e jornada do usuário" },
  { id: "comparison", name: "Comparativo de Projetos", description: "Análise comparativa entre projetos e campanhas" }
];

const performanceData = [
  { date: "2024-01-15", roas: 3.2, investment: 1200, revenue: 3840, impressions: 15400, clicks: 324 },
  { date: "2024-01-16", roas: 3.8, investment: 1400, revenue: 5320, impressions: 16800, clicks: 386 },
  { date: "2024-01-17", roas: 4.1, investment: 1600, revenue: 6560, impressions: 18200, clicks: 455 },
  { date: "2024-01-18", roas: 3.9, investment: 1500, revenue: 5850, impressions: 17600, clicks: 422 },
  { date: "2024-01-19", roas: 4.3, investment: 1700, revenue: 7310, impressions: 19400, clicks: 485 },
  { date: "2024-01-20", roas: 4.0, investment: 1550, revenue: 6200, impressions: 18800, clicks: 451 },
  { date: "2024-01-21", roas: 4.5, investment: 1800, revenue: 8100, impressions: 20200, clicks: 505 }
];

const projectComparison = [
  { name: "E-commerce", investment: 15200, revenue: 64000, roas: 4.2 },
  { name: "SaaS", investment: 18600, revenue: 70600, roas: 3.8 },
  { name: "Mobile App", investment: 12000, revenue: 34800, roas: 2.9 },
  { name: "Services", investment: 8500, revenue: 17850, roas: 2.1 }
];

const COLORS = ['hsl(var(--success))', 'hsl(var(--info))', 'hsl(var(--warning))', 'hsl(var(--destructive))'];

export default function Reports() {
  const [selectedReportType, setSelectedReportType] = useState("performance");
  const [selectedProject, setSelectedProject] = useState("all");
  const [dateRange, setDateRange] = useState<DateRange | undefined>();
  const [isGenerating, setIsGenerating] = useState(false);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const generateReport = async () => {
    setIsGenerating(true);
    // Simulate report generation
    setTimeout(() => {
      setIsGenerating(false);
      // Here you would trigger the actual report download
      console.log("Report generated for:", { selectedReportType, selectedProject, dateRange });
    }, 2000);
  };

  const exportToPDF = () => {
    console.log("Exporting to PDF...");
  };

  const exportToExcel = () => {
    console.log("Exporting to Excel...");
  };

  return (
    <Layout>
      <div className="p-6 space-y-8 max-w-7xl mx-auto">
        {/* Header */}
        <div className="animate-fade-in">
          <h1 className="text-3xl font-bold bg-gradient-dashboard bg-clip-text text-transparent">
            Relatórios
          </h1>
          <p className="text-muted-foreground mt-2">
            Análises avançadas e insights de performance das campanhas
          </p>
        </div>

        {/* Report Configuration */}
        <Card className="shadow-card animate-scale-in">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Filter className="h-5 w-5 text-primary" />
              Configurar Relatório
            </CardTitle>
            <CardDescription>
              Personalize os dados e período para gerar relatórios detalhados
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
              {/* Report Type */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Tipo de Relatório</label>
                <Select value={selectedReportType} onValueChange={setSelectedReportType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {reportTypes.map((type) => (
                      <SelectItem key={type.id} value={type.id}>
                        {type.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Project Filter */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Projeto</label>
                <Select value={selectedProject} onValueChange={setSelectedProject}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os Projetos</SelectItem>
                    <SelectItem value="ecommerce">E-commerce Store</SelectItem>
                    <SelectItem value="saas">SaaS Platform</SelectItem>
                    <SelectItem value="mobile">Mobile App</SelectItem>
                    <SelectItem value="services">Service Business</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Date Range */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Período</label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="w-full justify-start text-left font-normal">
                      <CalendarIcon className="mr-2 h-4 w-4" />
                      {dateRange?.from ? (
                        dateRange.to ? (
                          <>
                            {format(dateRange.from, "LLL dd, y")} -{" "}
                            {format(dateRange.to, "LLL dd, y")}
                          </>
                        ) : (
                          format(dateRange.from, "LLL dd, y")
                        )
                      ) : (
                        <span>Selecionar período</span>
                      )}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      initialFocus
                      mode="range"
                      defaultMonth={dateRange?.from}
                      selected={dateRange}
                      onSelect={setDateRange}
                      numberOfMonths={2}
                    />
                  </PopoverContent>
                </Popover>
              </div>

              {/* Actions */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Ações</label>
                <div className="flex flex-col gap-2">
                  <Button 
                    onClick={generateReport}
                    disabled={isGenerating}
                    className="w-full"
                  >
                    {isGenerating ? (
                      <>Gerando...</>
                    ) : (
                      <>
                        <FileText className="mr-2 h-4 w-4" />
                        Gerar Relatório
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Report Preview */}
        <div className="space-y-6 animate-fade-in">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">
              {reportTypes.find(t => t.id === selectedReportType)?.name}
            </h2>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={exportToPDF}>
                <Download className="mr-2 h-4 w-4" />
                PDF
              </Button>
              <Button variant="outline" size="sm" onClick={exportToExcel}>
                <Download className="mr-2 h-4 w-4" />
                Excel
              </Button>
            </div>
          </div>

          {/* Performance Report */}
          {selectedReportType === "performance" && (
            <div className="grid gap-6">
              {/* KPI Cards */}
              <div className="grid gap-4 md:grid-cols-4">
                <Card className="shadow-card border-success/20">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">ROAS Médio</CardTitle>
                    <TrendingUp className="h-4 w-4 text-success" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">3.97</div>
                    <p className="text-xs text-muted-foreground">+8.2% vs período anterior</p>
                  </CardContent>
                </Card>

                <Card className="shadow-card border-primary/20">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Investimento</CardTitle>
                    <DollarSign className="h-4 w-4 text-primary" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{formatCurrency(10750)}</div>
                    <p className="text-xs text-muted-foreground">7 dias selecionados</p>
                  </CardContent>
                </Card>

                <Card className="shadow-card border-info/20">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Impressões</CardTitle>
                    <Eye className="h-4 w-4 text-info" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">126.2K</div>
                    <p className="text-xs text-muted-foreground">+15.3% vs período anterior</p>
                  </CardContent>
                </Card>

                <Card className="shadow-card border-warning/20">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">CTR Médio</CardTitle>
                    <BarChart3 className="h-4 w-4 text-warning" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">2.51%</div>
                    <p className="text-xs text-muted-foreground">+0.3% vs período anterior</p>
                  </CardContent>
                </Card>
              </div>

              {/* Performance Charts */}
              <div className="grid gap-6 lg:grid-cols-2">
                <Card className="shadow-card">
                  <CardHeader>
                    <CardTitle>ROAS ao Longo do Tempo</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={performanceData}>
                        <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                        <XAxis 
                          dataKey="date" 
                          tickFormatter={(value) => format(new Date(value), "dd/MM")}
                          className="text-xs"
                        />
                        <YAxis className="text-xs" />
                        <Tooltip 
                          labelFormatter={(value) => format(new Date(value), "dd/MM/yyyy")}
                          contentStyle={{
                            backgroundColor: "hsl(var(--card))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "8px"
                          }}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="roas" 
                          stroke="hsl(var(--success))" 
                          strokeWidth={3}
                          dot={{ fill: "hsl(var(--success))", strokeWidth: 2, r: 4 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                <Card className="shadow-card">
                  <CardHeader>
                    <CardTitle>Investimento vs Receita</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={performanceData}>
                        <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                        <XAxis 
                          dataKey="date" 
                          tickFormatter={(value) => format(new Date(value), "dd/MM")}
                          className="text-xs"
                        />
                        <YAxis className="text-xs" />
                        <Tooltip 
                          formatter={(value: number, name: string) => [
                            formatCurrency(value), 
                            name === "investment" ? "Investimento" : "Receita"
                          ]}
                          contentStyle={{
                            backgroundColor: "hsl(var(--card))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "8px"
                          }}
                        />
                        <Bar dataKey="investment" fill="hsl(var(--primary))" radius={[2, 2, 0, 0]} />
                        <Bar dataKey="revenue" fill="hsl(var(--success))" radius={[2, 2, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {/* Comparison Report */}
          {selectedReportType === "comparison" && (
            <div className="grid gap-6">
              <Card className="shadow-card">
                <CardHeader>
                  <CardTitle>Comparativo de Projetos</CardTitle>
                  <CardDescription>Performance de ROAS por projeto</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={400}>
                    <BarChart data={projectComparison} layout="horizontal">
                      <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                      <XAxis type="number" className="text-xs" />
                      <YAxis dataKey="name" type="category" className="text-xs" />
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
                      <Bar dataKey="roas" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {projectComparison.map((project, index) => (
                  <Card key={project.name} className="shadow-card">
                    <CardHeader>
                      <CardTitle className="text-lg">{project.name}</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div>
                        <p className="text-sm text-muted-foreground">ROAS</p>
                        <p className="text-2xl font-bold text-primary">{project.roas}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Investimento</p>
                        <p className="font-medium">{formatCurrency(project.investment)}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Receita</p>
                        <p className="font-medium">{formatCurrency(project.revenue)}</p>
                      </div>
                      <Badge 
                        variant={project.roas >= 3.5 ? "success" : project.roas >= 2.5 ? "warning" : "danger"} 
                        className="w-full justify-center"
                      >
                        {project.roas >= 3.5 ? "Excelente" : project.roas >= 2.5 ? "Bom" : "Precisa Melhorar"}
                      </Badge>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}