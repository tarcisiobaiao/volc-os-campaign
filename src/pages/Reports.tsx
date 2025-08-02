import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ArrowLeft, BarChart3, FileDown, Mail } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from '@/hooks/use-toast';

interface ProjectSummary {
  name: string;
  invested: number;
  revenue: number;
  roas: number;
  roi: number;
  campaigns: number;
}

export default function Reports() {
  const navigate = useNavigate();
  const [reportType, setReportType] = useState('consolidado');
  const [period, setPeriod] = useState('30-dias');
  const [selectedProjects, setSelectedProjects] = useState('todos');
  const [format, setFormat] = useState('visualizar');

  // Mock data for the consolidated report
  const reportData = {
    period: '01/07/2025 a 31/07/2025',
    summary: {
      totalInvested: 45623.89,
      totalRevenue: 72105.34,
      grossProfit: 26481.45,
      taxes: 5844.53,
      operationalCosts: 6788.00,
      netProfit: 13848.92,
      averageRoas: 158,
      finalRoi: 30.3
    },
    projects: [
      {
        name: 'direito2.com.br',
        invested: 28450.00,
        revenue: 45230.00,
        roas: 159,
        roi: 34.2,
        campaigns: 23
      },
      {
        name: 'folhadosul.com.br',
        invested: 12890.00,
        revenue: 19234.00,
        roas: 149,
        roi: 28.1,
        campaigns: 9
      },
      {
        name: 'cartaoecredito.com.br',
        invested: 4284.00,
        revenue: 7641.00,
        roas: 178,
        roi: 41.3,
        campaigns: 3
      }
    ] as ProjectSummary[]
  };

  const formatCurrency = (value: number) => {
    return `R$ ${value.toFixed(2).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.')}`;
  };

  const handleExportCSV = () => {
    toast({ title: "Relatório exportado com sucesso!" });
  };

  const handleSendEmail = () => {
    toast({ title: "Relatório enviado por email!" });
  };

  const handleViewCharts = () => {
    toast({ title: "Abrindo visualização de gráficos..." });
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-2xl font-bold">📈 Relatórios</h1>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="text-sm font-medium">📊 Tipo:</label>
          <Select value={reportType} onValueChange={setReportType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="consolidado">Consolidado</SelectItem>
              <SelectItem value="por-projeto">Por Projeto</SelectItem>
              <SelectItem value="por-campanha">Por Campanha</SelectItem>
            </SelectContent>
          </Select>
        </div>
        
        <div>
          <label className="text-sm font-medium">📅 Período:</label>
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7-dias">Últimos 7 dias</SelectItem>
              <SelectItem value="30-dias">Últimos 30 dias</SelectItem>
              <SelectItem value="90-dias">Últimos 90 dias</SelectItem>
              <SelectItem value="personalizado">Personalizado</SelectItem>
            </SelectContent>
          </Select>
        </div>
        
        <div>
          <label className="text-sm font-medium">📂 Projetos:</label>
          <Select value={selectedProjects} onValueChange={setSelectedProjects}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todos</SelectItem>
              <SelectItem value="direito2">direito2.com.br</SelectItem>
              <SelectItem value="folhadosul">folhadosul.com.br</SelectItem>
              <SelectItem value="cartaoecredito">cartaoecredito.com.br</SelectItem>
            </SelectContent>
          </Select>
        </div>
        
        <div>
          <label className="text-sm font-medium">📄 Formato:</label>
          <Select value={format} onValueChange={setFormat}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="visualizar">Visualizar</SelectItem>
              <SelectItem value="csv">CSV</SelectItem>
              <SelectItem value="pdf">PDF</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Report Content */}
      <Card>
        <CardHeader>
          <CardTitle>📋 RELATÓRIO CONSOLIDADO - JULHO 2025</CardTitle>
          <p className="text-muted-foreground">Período: {reportData.period}</p>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* General Summary */}
          <div>
            <h3 className="text-lg font-semibold mb-4">💰 RESUMO GERAL:</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Total Investido:</p>
                <p className="font-semibold">{formatCurrency(reportData.summary.totalInvested)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Faturado:</p>
                <p className="font-semibold">{formatCurrency(reportData.summary.totalRevenue)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Lucro Bruto:</p>
                <p className="font-semibold">{formatCurrency(reportData.summary.grossProfit)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Impostos (8.1%):</p>
                <p className="font-semibold">{formatCurrency(reportData.summary.taxes)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Custos Operacionais:</p>
                <p className="font-semibold">{formatCurrency(reportData.summary.operationalCosts)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Lucro Líquido:</p>
                <p className="font-semibold text-green-600">{formatCurrency(reportData.summary.netProfit)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">ROAS Médio:</p>
                <p className="font-semibold">{reportData.summary.averageRoas}%</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">ROI Final:</p>
                <p className="font-semibold text-green-600">{reportData.summary.finalRoi}%</p>
              </div>
            </div>
          </div>

          {/* Projects Breakdown */}
          <div>
            <h3 className="text-lg font-semibold mb-4">📊 POR PROJETO:</h3>
            <div className="space-y-4">
              {reportData.projects.map((project, index) => (
                <Card key={index} className="p-4">
                  <div className="space-y-2">
                    <h4 className="font-semibold">{project.name}</h4>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">Investido: </span>
                        <span className="font-medium">{formatCurrency(project.invested)}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Faturado: </span>
                        <span className="font-medium">{formatCurrency(project.revenue)}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">ROAS: </span>
                        <span className="font-medium">{project.roas}%</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">ROI: </span>
                        <span className="font-medium">{project.roi}%</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Campanhas: </span>
                        <span className="font-medium">{project.campaigns}</span>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-4 pt-4">
            <Button onClick={handleViewCharts}>
              <BarChart3 className="h-4 w-4 mr-2" />
              📊 Ver Gráficos
            </Button>
            <Button variant="outline" onClick={handleExportCSV}>
              <FileDown className="h-4 w-4 mr-2" />
              📋 Exportar CSV
            </Button>
            <Button variant="outline" onClick={handleSendEmail}>
              <Mail className="h-4 w-4 mr-2" />
              📧 Email
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}