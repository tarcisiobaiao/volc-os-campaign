import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { ArrowLeft, TrendingUp, DollarSign, MousePointer, Eye, Target, Calendar, Settings, AlertTriangle } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, ComposedChart } from 'recharts';
import { supabaseDataService } from "@/services/supabaseDataService";
import { formatBrlCurrency, formatCostCurrency, preloadExchangeRate } from "@/utils/currencyUtils";
import { DateFilter } from "@/components/dashboard/DateFilter";
import { DataStatus } from "@/components/dashboard/DataStatus";
import { format } from "date-fns";
import { calculateROAS } from "@/utils/roasCalculations";
import { FunnelUrlsEditor } from "@/components/campaign/FunnelUrlsEditor";
import { taxHistoryService } from "@/services/taxHistoryService";

export default function CampaignDetailDashboard() {

  const { campaignId } = useParams();
  const navigate = useNavigate();


  // All hooks must be declared before any conditional returns
  const [campaignData, setCampaignData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exchangeRate, setExchangeRate] = useState<number>(5.50);
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | '7d' | '30d' | 'custom' | 'range'>('today');
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedEndDate, setSelectedEndDate] = useState<string>("");
  const [showFunnelEditor, setShowFunnelEditor] = useState(false);
  const [taxRate, setTaxRate] = useState<number>(8.1);

  // Initialize with current server date
  useEffect(() => {
    const initialize = async () => {
      try {
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);
      } catch (error) {
        console.error('❌ Error getting server date:', error);
        const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(new Date());
        setSelectedDate(saoPauloDate);
      }
    };

    initialize();
  }, []);

  // Load campaign data
  useEffect(() => {
    const loadCampaignData = async () => {
      if (!campaignId || !selectedDate) {
        return;
      }

      try {
        setLoading(true);
        setError(null);

        // Load exchange rate and tax rate
        const [rate, currentTaxRate] = await Promise.all([
          preloadExchangeRate(),
          taxHistoryService.getLatestTaxRate()
        ]);
        setExchangeRate(rate);
        setTaxRate(currentTaxRate);

        // Load campaign data
        
        // Load both today's metrics and 7-day chart data when period is "today"
        let data;

        if (selectedPeriod === 'today') {
          // For "today", get both today's metrics and 7-day chart data
          const [todayData, chartData] = await Promise.all([
            supabaseDataService.getCampaignDashboardDataFiltered(campaignId, {
              period: 'today',
              date: selectedDate,
              endDate: selectedEndDate || undefined
            }),
            supabaseDataService.getCampaignDashboardDataFiltered(campaignId, {
              period: '7d',
              date: selectedDate,
              endDate: selectedEndDate || undefined
            })
          ]);

          // Use today's metrics for main stats, but 7-day data for charts
          data = {
            ...todayData,
            dailyMetrics: chartData.dailyMetrics // Use 7-day chart data
          };
        } else {
          // For other periods, use normal logic
          data = await supabaseDataService.getCampaignDashboardDataFiltered(campaignId, {
            period: selectedPeriod,
            date: selectedDate,
            endDate: selectedEndDate || undefined
          });
        }

        setCampaignData(data);
      } catch (err) {
        console.error('❌ Error loading campaign data:', err);
        setError(err instanceof Error ? err.message : 'Erro ao carregar dados da campanha');
      } finally {
        setLoading(false);
      }
    };

    loadCampaignData();
  }, [campaignId, selectedPeriod, selectedDate, selectedEndDate]);

  // Helper function to parse date ensuring São Paulo timezone
  const parseDateToSaoPaulo = (dateStr: string): Date => {
    try {
      if (!dateStr || typeof dateStr !== 'string') {
        return new Date();
      }
      
      const [year, month, day] = dateStr.split('-').map(Number);
      
      if (!year || !month || !day || isNaN(year) || isNaN(month) || isNaN(day)) {
        return new Date();
      }
      
      return new Date(`${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T12:00:00-03:00`);
    } catch (error) {
      console.error('Error parsing date:', error, dateStr);
      return new Date();
    }
  };

  // Handlers for date filters
  const handlePeriodChange = async (period: 'today' | '7d' | '30d' | 'custom' | 'range') => {
    setSelectedPeriod(period);
    if (period === 'today') {
      try {
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);
        setSelectedEndDate("");
      } catch (error) {
        console.error('Error getting server date:', error);
        const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(new Date());
        setSelectedDate(saoPauloDate);
        setSelectedEndDate("");
      }
    }
  };

  const handleDateChange = (date: string) => {
    setSelectedDate(date);
    if (selectedPeriod === 'custom') {
      setSelectedEndDate("");
    }
  };

  const handleDateRangeChange = (startDate: string, endDate: string) => {
    setSelectedDate(startDate);
    setSelectedEndDate(endDate);
    setSelectedPeriod('range');
  };

  const handleConfigureClick = () => {
    const projectType = campaign?.project_type;

    if (projectType === 'ADSENSE') {
      setShowFunnelEditor(true);
    } else {
      // Para projetos GAM ou outros, mostrar alerta
      alert('Configuração não disponível para este tipo de projeto.');
    }
  };

  // Check campaignId first
  if (!campaignId) {
    return (
      <Layout>
        <div className="p-6">
          <h1 className="text-2xl font-bold">Erro: ID da campanha não fornecido</h1>
          <Button onClick={() => navigate("/dashboard/campaigns")} className="mt-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Voltar às Campanhas
          </Button>
        </div>
      </Layout>
    );
  }

  // Show loading state
  if (loading) {
    return (
      <Layout>
        <div className="flex justify-center items-center min-h-[400px]">
          <LoadingSpinner />
          <span className="ml-2">Carregando dados da campanha...</span>
        </div>
      </Layout>
    );
  }

  // Show error state
  if (error) {
    return (
      <Layout>
        <div className="p-6 text-center">
          <h1 className="text-2xl font-bold text-red-600">Erro ao carregar dados</h1>
          <p className="text-muted-foreground mb-4">{error}</p>
          <Button onClick={() => window.location.reload()} className="mt-4">
            Tentar novamente
          </Button>
        </div>
      </Layout>
    );
  }

  // Check if we have campaign data
  if (!campaignData || !campaignData.campaignMetrics) {
    return (
      <Layout>
        <div className="p-6 text-center">
          <h1 className="text-2xl font-bold text-gray-600">Campanha não encontrada</h1>
          <p className="text-muted-foreground mb-4">
            A campanha com ID {campaignId} não foi encontrada no banco de dados.
          </p>
          <Button onClick={() => navigate("/dashboard/campaigns")} className="mt-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Voltar às Campanhas
          </Button>
        </div>
      </Layout>
    );
  }

  // Extract campaign metrics from loaded data
  const campaign = campaignData.campaignMetrics;
  const historicalData = campaignData.historicalData || [];

  const getStatusBadge = (status: string) => {
    return status === 'Active' || status === 'ENABLED' ? (
      <Badge className="bg-green-500">🟢 Ativa</Badge>
    ) : (
      <Badge variant="secondary" className="bg-red-500">🔴 Pausada</Badge>
    );
  };

  // Função para formatar valores de REVENUE (já convertidos pelo database em revenue_conversao)
  const formatRevenue = (brlValue: number) => {
    return formatBrlCurrency(brlValue);
  };

  // Função para formatar valores de CUSTOS/GASTOS (já em BRL)
  const formatCurrency = (brlValue: number) => {
    return formatCostCurrency(brlValue);
  };

  const formatPercentage = (value: number) => `${value.toFixed(2)}%`;

  // Calculate derived metrics
  const revenue = campaign.revenue || 0;
  const spend = campaign.spend || 0;
  const profit = revenue - spend;

  // Calculate ROI with tax deduction: (revenue * (1 - tax/100) - spend) / spend * 100
  const revenueAfterTax = revenue * (1 - taxRate / 100);
  const profitAfterTax = revenueAfterTax - spend;
  const roi = spend > 0 ? ((profitAfterTax / spend) * 100).toFixed(1) : 0;

  const roas = spend > 0 ? calculateROAS(revenue, spend).toFixed(1) : 0;

  // Function to generate dynamic chart title based on selected period
  const getChartPeriodTitle = () => {
    if (selectedPeriod === 'today') {
      return 'Hoje';
    } else if (selectedPeriod === '7d') {
      return '7 dias';
    } else if (selectedPeriod === '30d') {
      return '30 dias';
    } else if (selectedPeriod === 'range' && selectedDate && selectedEndDate) {
      const start = new Date(selectedDate + 'T00:00:00');
      const end = new Date(selectedEndDate + 'T00:00:00');
      const diffDays = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
      const startFormatted = format(start, 'dd/MM');
      const endFormatted = format(end, 'dd/MM');
      return `${diffDays} dias (${startFormatted} até ${endFormatted})`;
    } else if (selectedPeriod === 'custom' && selectedDate) {
      return `Data: ${format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy')}`;
    }
    return 'Período selecionado';
  };

  return (
    <Layout>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-2">
              <ArrowLeft className="h-4 w-4" />
              Voltar
            </Button>
            <div>
              <h1 className="text-2xl font-bold">📊 Dashboard da Campanha</h1>
              <p className="text-sm text-muted-foreground mt-1">
                ID: {campaign.campaignId} • Projeto: {campaign.projectName}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <DateFilter
              selectedPeriod={selectedPeriod}
              selectedDate={selectedDate}
              selectedEndDate={selectedEndDate}
              onPeriodChange={handlePeriodChange}
              onDateChange={handleDateChange}
              onDateRangeChange={handleDateRangeChange}
            />
            
            <DataStatus 
              loading={loading} 
              error={error} 
              lastUpdate={new Date().toLocaleTimeString('pt-BR')}
            />
            
            <Button variant="outline" size="sm" className="gap-2" onClick={handleConfigureClick}>
              <Settings className="h-4 w-4" />
              Configurar
            </Button>
            {getStatusBadge(campaign.status)}
          </div>
        </div>

        {/* Campaign Info */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              🎯 {campaign.custom_goal}
            </CardTitle>
            <CardDescription className="text-sm">
              <div className="space-y-1">
                <p>📝 <strong>Nome completo:</strong> {campaign.campaign_name}</p>
                <p>🔍 <strong>Canal:</strong> {campaign.advertising_channel} | <strong>Estratégia:</strong> {campaign.bidding_strategy}</p>
                <p>📅 <strong>Período:</strong> {new Date(campaign.start_date).toLocaleDateString('pt-BR')} - {new Date(campaign.end_date).toLocaleDateString('pt-BR')}</p>
              </div>
            </CardDescription>
          </CardHeader>
        </Card>

        {/* Métricas Principais */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Gasto */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">Gasto Total</p>
                  <p className="text-xl font-bold text-red-600">{formatCurrency(campaign.spend)}</p>
                </div>
                <DollarSign className="h-8 w-8 text-red-500" />
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                Orçamento: {formatCurrency(campaign.budget_amount)}/dia
              </div>
            </CardContent>
          </Card>

          {/* Revenue */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">Revenue</p>
                  <p className="text-xl font-bold text-green-600">{formatRevenue(revenue)}</p>
                </div>
                <TrendingUp className="h-8 w-8 text-green-500" />
              </div>
              <div className="mt-2 text-xs text-green-600">
                ROAS: {roas}%
              </div>
            </CardContent>
          </Card>

          {/* ROAS */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">ROAS</p>
                  <p className="text-xl font-bold text-blue-600">{roas}%</p>
                </div>
                <Target className="h-8 w-8 text-blue-500" />
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                Conversões: {campaign.conversions.toFixed(0)}
              </div>
            </CardContent>
          </Card>

          {/* Lucro Bruto */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">Lucro Bruto</p>
                  <p className={`text-xl font-bold ${profit >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {formatCurrency(profit)}
                  </p>
                </div>
                <TrendingUp className={`h-8 w-8 ${profit >= 0 ? 'text-green-500' : 'text-red-500'}`} />
              </div>
              <div className={`mt-2 text-xs ${Number(roi) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                ROI: {roi}% (imposto: {taxRate}%)
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Métricas Secundárias */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">CTR</p>
                  <p className="text-xl font-bold text-purple-600">{formatPercentage(campaign.ctr)}</p>
                </div>
                <MousePointer className="h-8 w-8 text-purple-500" />
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                {campaign.clicks.toLocaleString()} cliques • {campaign.impressions.toLocaleString()} impressões
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 text-center">
              <DollarSign className="h-6 w-6 mx-auto mb-2 text-gray-500" />
              <p className="text-sm text-muted-foreground">CPC</p>
              <p className="text-lg font-semibold">{formatCurrency(campaign.cpc)}</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 text-center">
              <Target className="h-6 w-6 mx-auto mb-2 text-gray-500" />
              <p className="text-sm text-muted-foreground">Custo/Conversão</p>
              <p className="text-lg font-semibold">{formatCurrency(campaign.cost_per_conversion)}</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 text-center">
              <Calendar className="h-6 w-6 mx-auto mb-2 text-gray-500" />
              <p className="text-sm text-muted-foreground">Dias Ativos</p>
              <p className="text-lg font-semibold">
                {Math.floor((new Date().getTime() - new Date(campaign.start_date).getTime()) / (1000 * 3600 * 24))}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Gráficos */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Gráfico Gasto vs Revenue */}
          <Card>
            <CardHeader>
              <CardTitle>💰 Gasto vs Revenue ({getChartPeriodTitle()})</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                {historicalData.length <= 1 ? (
                  // Gráfico de barras para 1 dia
                  <BarChart data={[
                    { name: 'Gasto', value: campaign.spend, fill: '#ef4444' },
                    { name: 'Revenue', value: revenue, fill: '#22c55e' },
                    { name: 'Lucro Bruto', value: profit, fill: profit >= 0 ? '#3b82f6' : '#f97316' }
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip
                      formatter={(value) => [`R$ ${Number(value).toFixed(2)}`, '']}
                      labelStyle={{ color: '#000' }}
                    />
                    <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                      {[
                        { name: 'Gasto', value: campaign.spend, fill: '#ef4444' },
                        { name: 'Revenue', value: revenue, fill: '#22c55e' },
                        { name: 'Lucro Bruto', value: profit, fill: profit >= 0 ? '#3b82f6' : '#f97316' }
                      ].map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                ) : (
                  // Gráfico de linhas para múltiplos dias
                  <LineChart data={historicalData.map(item => ({
                    ...item,
                    profit: (item.revenue || 0) - (item.spend || 0)
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tickFormatter={(date) => {
                      return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                    }} />
                    <YAxis />
                    <Tooltip
                      labelFormatter={(date) => {
                        return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR');
                      }}
                      formatter={(value, name) => {
                        const labels: Record<string, string> = {
                          spend: 'Gasto',
                          revenue: 'Revenue',
                          profit: 'Lucro Bruto'
                        };
                        return [`R$ ${Number(value).toFixed(2)}`, labels[name] || name];
                      }}
                    />
                    <Line type="monotone" dataKey="spend" stroke="#ef4444" strokeWidth={2} name="spend" />
                    <Line type="monotone" dataKey="revenue" stroke="#22c55e" strokeWidth={2} name="revenue" />
                    <Line type="monotone" dataKey="profit" stroke="#3b82f6" strokeWidth={2} name="profit" />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico Clicks vs Impressions */}
          <Card>
            <CardHeader>
              <CardTitle>👆 Clicks vs Impressões ({getChartPeriodTitle()})</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={historicalData.map(item => ({
                  ...item,
                  ctr: item.impressions > 0 ? (item.clicks / item.impressions) * 100 : 0
                }))}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickFormatter={(date) => {
                    return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                  }} />
                  <YAxis yAxisId="left" />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 'auto']} />
                  <Tooltip
                    labelFormatter={(date) => {
                      return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR');
                    }}
                    formatter={(value, name) => {
                      if (name === 'ctr') {
                        return [`${Number(value).toFixed(2)}%`, 'CTR'];
                      }
                      return [
                        Number(value).toLocaleString(),
                        name === 'clicks' ? 'Clicks' : 'Impressões'
                      ];
                    }}
                  />
                  <Bar yAxisId="left" dataKey="impressions" fill="#3b82f6" name="impressions" />
                  <Bar yAxisId="left" dataKey="clicks" fill="#8b5cf6" name="clicks" />
                  <Line yAxisId="right" type="monotone" dataKey="ctr" stroke="#f59e0b" strokeWidth={2} name="ctr" dot={{ r: 4 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Popup de configuração de funis */}
      {showFunnelEditor && (
        <FunnelUrlsEditor
          isOpen={showFunnelEditor}
          onClose={() => setShowFunnelEditor(false)}
          campaignId={campaignId}
          campaignName={campaign?.campaign_name || 'Campanha'}
          onSave={() => {
            // Opcional: recarregar dados após salvar
          }}
        />
      )}
    </Layout>
  );
}