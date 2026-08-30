import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { ArrowLeft, TrendingUp, DollarSign, MousePointer, Eye, Target, Calendar, Settings, AlertTriangle, BarChart3, FileText, Circle, Coins, Crown } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, ComposedChart } from 'recharts';
import { chartColor, volcGrid, volcAxis, volcLine, volcCursor, VolcTooltip } from "@/lib/chartTheme";
import { supabaseDataService } from "@/services/supabaseDataService";
import { supabase } from "@/lib/supabase";
import { formatBrlCurrency, formatCostCurrency, preloadExchangeRate } from "@/utils/currencyUtils";
import { DateFilter } from "@/components/dashboard/DateFilter";
import { DataStatus } from "@/components/dashboard/DataStatus";
import { format } from "date-fns";
import { calculateROAS } from "@/utils/roasCalculations";
import { FunnelUrlsEditor } from "@/components/campaign/FunnelUrlsEditor";
import { taxHistoryService } from "@/services/taxHistoryService";
import { OrientacaoBox } from "@/components/campaign/OrientacaoBox";
import { BiddingActionBox } from "@/components/campaign/BiddingActionBox";
import { OtimizacaoBox } from "@/components/campaign/OtimizacaoBox";
import { DisplayROITable } from "@/components/campaign/DisplayROITable";
import { PlacementNegationCard } from "@/components/campaign/PlacementNegationCard";

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
  const [orientacaoData, setOrientacaoData] = useState<{
    orientacao_texto: string | null;
    orientacao_resumo: string | null;
    orientacao_json: any | null;
    date: string | null;
  } | null>(null);
  const [otimizacaoData, setOtimizacaoData] = useState<{
    otimizacao_resumo: string | null;
    otimizacao_json: any | null;
    otimizacao_realizada_em: string | null;
  } | null>(null);

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

        // Load exchange rate
        const rate = await preloadExchangeRate();
        setExchangeRate(rate);

        // Load tax rate based on selected period
        let currentTaxRate: number;
        if (selectedPeriod === 'range' && selectedDate && selectedEndDate &&
            selectedDate.substring(0, 7) !== selectedEndDate.substring(0, 7)) {
          // Multiple months: use weighted average tax rate
          currentTaxRate = await taxHistoryService.getTaxRateForDateRange(selectedDate, selectedEndDate);
        } else {
          // Single month: use that month's tax rate
          const monthToUse = selectedDate ? selectedDate.substring(0, 7) : new Date().toISOString().slice(0, 7);
          currentTaxRate = await taxHistoryService.getCurrentTaxRate(monthToUse);
        }
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

  // Load orientação data for today only
  useEffect(() => {
    const loadOrientacaoData = async () => {
      if (!campaignId || !selectedDate) {
        return;
      }

      try {
        // Get today's date from server
        const serverDate = await supabaseDataService.getServerDate();

        // Only fetch orientação if we're viewing today's data
        if (selectedDate !== serverDate) {
          setOrientacaoData(null);
          return;
        }

        // Fetch orientação data from daily_campaign_metrics for today
        const { data, error } = await supabase
          .from('daily_campaign_metrics')
          .select('orientacao_texto, orientacao_resumo, orientacao_json, date')
          .eq('campaign_id', campaignId)
          .eq('date', serverDate)
          .maybeSingle();

        if (error) {
          console.error('❌ Error loading orientação data:', error);
          setOrientacaoData(null);
          return;
        }

        // Only set data if at least one field is filled
        if (data && (data.orientacao_texto || data.orientacao_resumo)) {
          setOrientacaoData(data);
        } else {
          setOrientacaoData(null);
        }
      } catch (err) {
        console.error('❌ Error in loadOrientacaoData:', err);
        setOrientacaoData(null);
      }
    };

    loadOrientacaoData();
  }, [campaignId, selectedDate]);

  // Load otimização (auto adjust) data for today only
  useEffect(() => {
    const loadOtimizacaoData = async () => {
      if (!campaignId || !selectedDate) {
        return;
      }

      try {
        // Get today's date from server
        const serverDate = await supabaseDataService.getServerDate();

        // Only fetch otimização if we're viewing today's data
        if (selectedDate !== serverDate) {
          setOtimizacaoData(null);
          return;
        }

        // Fetch otimização data from daily_campaign_metrics for today
        const { data, error } = await supabase
          .from('daily_campaign_metrics')
          .select('otimizacao_resumo, otimizacao_json, otimizacao_realizada_em')
          .eq('campaign_id', campaignId)
          .eq('date', serverDate)
          .maybeSingle();

        if (error) {
          console.error('❌ Error loading otimização data:', error);
          setOtimizacaoData(null);
          return;
        }

        // Only set data if otimizacao_realizada_em is filled (meaning auto adjust was done)
        if (data && data.otimizacao_realizada_em) {
          setOtimizacaoData(data);
        } else {
          setOtimizacaoData(null);
        }
      } catch (err) {
        console.error('❌ Error in loadOtimizacaoData:', err);
        setOtimizacaoData(null);
      }
    };

    loadOtimizacaoData();
  }, [campaignId, selectedDate]);

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
          <h1 className="text-2xl font-bold text-destructive">Erro ao carregar dados</h1>
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
          <h1 className="text-2xl font-bold text-muted-foreground">Campanha não encontrada</h1>
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
      <Badge className="bg-success text-success-foreground flex items-center gap-1">
        <Circle className="h-2 w-2 fill-current" />
        Ativa
      </Badge>
    ) : (
      <Badge variant="secondary" className="bg-destructive text-destructive-foreground flex items-center gap-1">
        <Circle className="h-2 w-2 fill-current" />
        Pausada
      </Badge>
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

  const isMobile = window.innerWidth < 768;
  
  return (
    <Layout>
      <div className={`${isMobile ? 'p-4' : 'p-6'} space-y-4 md:space-y-6`}>
        {/* Header */}
        <div className="space-y-4">
          {/* Title Section */}
          <div className="flex items-start gap-4 reveal" style={{ ['--i' as any]: 0 }}>
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="flex-shrink-0 gap-2 touch-target">
              <ArrowLeft className="h-4 w-4" />
              Voltar
            </Button>
            <div className="flex-1 min-w-0">
              <div className="kicker mb-2 flex items-center gap-2">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
                Detalhe da campanha
              </div>
              <h1 className={`font-display font-bold tracking-tight leading-[1.05] ${isMobile ? 'text-2xl' : 'text-4xl'}`}>
                Dashboard da <span className="text-foreground">Campanha</span>
              </h1>
              <div className="mt-3 aurora-rule w-16" />
              <p className={`${isMobile ? 'text-xs' : 'text-sm'} text-muted-foreground mt-3`}>
                ID: {campaign.campaignId} • Projeto: {campaign.projectName}
              </p>
            </div>
          </div>
          
          {/* Filters and Actions Section */}
          <div className={`flex ${isMobile ? 'flex-col' : 'items-center flex-wrap'} gap-3`}>
            <DateFilter
              selectedPeriod={selectedPeriod}
              selectedDate={selectedDate}
              selectedEndDate={selectedEndDate}
              onPeriodChange={handlePeriodChange}
              onDateChange={handleDateChange}
              onDateRangeChange={handleDateRangeChange}
            />
            
            <div className="flex items-center gap-2 flex-wrap">
              <DataStatus 
                loading={loading} 
                error={error} 
                lastUpdate={new Date().toLocaleTimeString('pt-BR')}
              />
              
              <Button variant="outline" size="sm" className="gap-2 flex-shrink-0" onClick={handleConfigureClick}>
                <Settings className="h-4 w-4" />
                Configurar
              </Button>
              <div className="flex-shrink-0">
                {getStatusBadge(campaign.status)}
              </div>
            </div>
          </div>
        </div>

        {/* Campaign Info */}
        <Card className="reveal hover-lift" style={{ ['--i' as any]: 1 }}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 font-display">
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><Target className="h-4 w-4" /></span>
              {campaign.custom_goal}
            </CardTitle>
            <CardDescription className="text-sm">
              <div className="space-y-1">
                <p className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  <strong>Nome completo:</strong> {campaign.campaign_name}
                </p>
                <p className="flex items-center gap-2">
                  <Target className="h-4 w-4" />
                  <strong>Canal:</strong> {campaign.advertising_channel} | <strong>Estratégia:</strong> {campaign.bidding_strategy}
                </p>
                <p className="flex items-center gap-2">
                  <Calendar className="h-4 w-4" />
                  <strong>Período:</strong> {new Date(campaign.start_date).toLocaleDateString('pt-BR')} - {new Date(campaign.end_date).toLocaleDateString('pt-BR')}
                </p>
              </div>
            </CardDescription>
          </CardHeader>
        </Card>

        {/* Métricas Principais */}
        <div className="flex items-center gap-3">
          <span className="kicker whitespace-nowrap">Métricas principais</span>
          <span className="hairline-aurora flex-1" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          {/* Gasto */}
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 2 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Investimento Total</span>
              <span className="rounded-md bg-info/10 text-info p-1.5"><DollarSign className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight">{formatCurrency(campaign.spend)}</div>
              <div className="mt-2 text-xs text-muted-foreground">
                Orçamento: <span className="tabular">{formatCurrency(campaign.budget_amount)}</span>/dia
              </div>
            </CardContent>
          </Card>

          {/* Revenue */}
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 3 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Revenue</span>
              <span className="rounded-md bg-success/10 text-success p-1.5"><TrendingUp className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight text-success">{formatRevenue(revenue)}</div>
              <div className="mt-2 text-xs text-success font-medium tabular">
                ROAS: {roas}%
              </div>
            </CardContent>
          </Card>

          {/* ROAS */}
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 4 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">ROAS</span>
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><Target className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight">{roas}%</div>
              <div className="mt-2 text-xs text-muted-foreground">
                Conversões: <span className="tabular">{campaign.conversions.toFixed(0)}</span>
              </div>
            </CardContent>
          </Card>

          {/* Lucro Bruto */}
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 5 }}>
            <span className={`pointer-events-none absolute inset-x-0 top-0 h-0.5 ${profit >= 0 ? 'bg-success' : 'bg-destructive'}`} />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Lucro Bruto</span>
              <span className={`rounded-md p-1.5 ${profit >= 0 ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}><TrendingUp className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent>
              <div className={`font-display text-2xl md:text-3xl font-bold tabular tracking-tight ${profit >= 0 ? 'text-success' : 'text-destructive'}`}>
                {formatCurrency(profit)}
              </div>
              <div className={`mt-2 text-xs font-medium tabular ${Number(roi) >= 0 ? 'text-success' : 'text-destructive'}`}>
                ROI: {roi}% (imposto: {taxRate}%)
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Métricas Secundárias */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 6 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">CTR</span>
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><MousePointer className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl font-bold tabular tracking-tight">{formatPercentage(campaign.ctr)}</div>
              <div className="mt-2 text-xs text-muted-foreground">
                <span className="tabular">{campaign.clicks.toLocaleString()}</span> cliques • <span className="tabular">{campaign.impressions.toLocaleString()}</span> impressões
              </div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 7 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">CPC</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><DollarSign className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl font-bold tabular tracking-tight">{formatCurrency(campaign.cpc)}</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 8 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Custo/Conversão</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Target className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl font-bold tabular tracking-tight">{formatCurrency(campaign.cost_per_conversion)}</div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden reveal hover-lift" style={{ ['--i' as any]: 9 }}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <span className="kicker">Dias Ativos</span>
              <span className="rounded-md bg-muted text-muted-foreground p-1.5"><Calendar className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent>
              <div className="font-display text-2xl font-bold tabular tracking-tight">
                {Math.floor((new Date().getTime() - new Date(campaign.start_date).getTime()) / (1000 * 3600 * 24))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Gráficos */}
        <div className="flex items-center gap-3">
          <span className="kicker whitespace-nowrap">Análise de desempenho</span>
          <span className="hairline-aurora flex-1" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
          {/* Gráfico Clicks vs Impressions */}
          <Card className="hover-lift">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><MousePointer className="h-4 w-4" /></span>
                Clicks vs Impressões ({getChartPeriodTitle()})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={historicalData.map(item => ({
                  ...item,
                  ctr: item.impressions > 0 ? (item.clicks / item.impressions) * 100 : 0
                }))}>
                  <CartesianGrid {...volcGrid} />
                  <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                    return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                  }} />
                  <YAxis yAxisId="left" {...volcAxis} />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 'auto']} {...volcAxis} />
                  <Tooltip cursor={volcCursor} content={
                    <VolcTooltip
                      labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                      valueFormatter={(value, name) =>
                        name === 'CTR' ? `${Number(value).toFixed(2)}%` : Number(value).toLocaleString()
                      }
                    />
                  } />
                  <Bar yAxisId="left" dataKey="impressions" fill={chartColor(0)} name="Impressões" radius={[4, 4, 0, 0]} />
                  <Bar yAxisId="left" dataKey="clicks" fill={chartColor(1)} name="Clicks" radius={[4, 4, 0, 0]} />
                  <Line yAxisId="right" type="monotone" dataKey="ctr" stroke={chartColor(3)} name="CTR" {...volcLine} />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico Taxa de Conversão, CPC e Custo por Conversão */}
          <Card className="hover-lift">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><Target className="h-4 w-4" /></span>
                Taxa de Conversão, CPC e Custo/Conversão ({getChartPeriodTitle()})
              </CardTitle>
              <CardDescription className="text-xs">
                Taxa de Conversão: {campaign.clicks > 0 ? ((campaign.conversions / campaign.clicks) * 100).toFixed(2) : 0}% • CPC: {formatCurrency(campaign.cpc)} • Custo/Conversão: {formatCurrency(campaign.cost_per_conversion)}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={historicalData.map(item => {
                  const itemClicks = item.clicks || 0;
                  const itemConversions = item.conversions || 0;
                  const conversionRate = itemClicks > 0 ? ((itemConversions / itemClicks) * 100) : 0;

                  return {
                    ...item,
                    conversion_rate: conversionRate,
                    cpc: item.cpc || 0,
                    cost_per_conversion: item.cost_per_conversion || 0
                  };
                })}>
                  <CartesianGrid {...volcGrid} />
                  <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                    return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                  }} />
                  <YAxis yAxisId="left" {...volcAxis} tickFormatter={(value) => `${value.toFixed(1)}%`} />
                  <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => `R$ ${value.toFixed(2)}`} />
                  <Tooltip cursor={volcCursor} content={
                    <VolcTooltip
                      labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                      valueFormatter={(value, name) =>
                        name === 'Taxa de Conversão' ? `${Number(value).toFixed(2)}%` : `R$ ${Number(value).toFixed(2)}`
                      }
                    />
                  } />
                  <Bar
                    yAxisId="left"
                    dataKey="conversion_rate"
                    fill={chartColor(2)}
                    name="Taxa de Conversão"
                    radius={[4, 4, 0, 0]}
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="cpc"
                    stroke={chartColor(3)}
                    name="CPC"
                    {...volcLine}
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="cost_per_conversion"
                    stroke={chartColor(1)}
                    name="Custo/Conversão"
                    {...volcLine}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico ROAS vs ROI */}
          <Card className="hover-lift">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><TrendingUp className="h-4 w-4" /></span>
                ROAS vs ROI ({getChartPeriodTitle()})
              </CardTitle>
              <CardDescription className="text-xs">
                ROAS: {roas}% • ROI: {roi}% (imposto: {taxRate}%)
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                {historicalData.length <= 1 ? (
                  // Gráfico de barras para 1 dia
                  <BarChart data={[
                    { name: 'ROAS', value: Number(roas), fill: chartColor(4) },
                    { name: 'ROI', value: Number(roi), fill: chartColor(0) }
                  ]}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="name" {...volcAxis} />
                    <YAxis {...volcAxis} tickFormatter={(value) => `${value}%`} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip valueFormatter={(value) => `${Number(value).toFixed(1)}%`} />
                    } />
                    <Bar dataKey="value" name="" radius={[8, 8, 0, 0]}>
                      {[
                        { name: 'ROAS', value: Number(roas), fill: chartColor(4) },
                        { name: 'ROI', value: Number(roi), fill: chartColor(0) }
                      ].map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                ) : (
                  // Gráfico de linhas para múltiplos dias
                  <LineChart data={historicalData.map(item => {
                    const itemRevenue = item.revenue || 0;
                    const itemSpend = item.spend || 0;
                    // Usa calculateROAS (excess) para alinhar com cards e single-day chart.
                    // Bug anterior: ((itemRevenue / itemSpend) * 100) é ROAS tradicional, ficava 100% acima.
                    const itemRoas = calculateROAS(itemRevenue, itemSpend);
                    const itemRevenueAfterTax = itemRevenue * (1 - taxRate / 100);
                    const itemProfitAfterTax = itemRevenueAfterTax - itemSpend;
                    const itemRoi = itemSpend > 0 ? ((itemProfitAfterTax / itemSpend) * 100) : 0;

                    return {
                      ...item,
                      roas: itemRoas,
                      roi: itemRoi
                    };
                  })}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                      return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                    }} />
                    <YAxis {...volcAxis} tickFormatter={(value) => `${value}%`} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip
                        labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                        valueFormatter={(value) => `${Number(value).toFixed(1)}%`}
                      />
                    } />
                    <Line
                      type="monotone"
                      dataKey="roas"
                      stroke={chartColor(4)}
                      name="ROAS"
                      {...volcLine}
                    />
                    <Line
                      type="monotone"
                      dataKey="roi"
                      stroke={chartColor(0)}
                      name="ROI"
                      {...volcLine}
                    />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico eCPM vs CPC do Ad Exchange */}
          <Card className="hover-lift">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><Coins className="h-4 w-4" /></span>
                eCPM vs CPC - Ad Exchange ({getChartPeriodTitle()})
              </CardTitle>
              <CardDescription className="text-xs">
                Médias do período selecionado
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                {historicalData.length <= 1 ? (
                  // Gráfico de barras para 1 dia
                  <BarChart data={[
                    { name: 'eCPM', value: campaign.gam_ecpm || 0, fill: chartColor(2) },
                    { name: 'CPC', value: campaign.gam_cpc || 0, fill: chartColor(3) }
                  ]}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="name" {...volcAxis} />
                    <YAxis {...volcAxis} tickFormatter={(value) => `$${value.toFixed(2)}`} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip valueFormatter={(value) => `$${Number(value).toFixed(2)}`} />
                    } />
                    <Bar dataKey="value" name="" radius={[8, 8, 0, 0]}>
                      {[
                        { name: 'eCPM', value: campaign.gam_ecpm || 0, fill: chartColor(2) },
                        { name: 'CPC', value: campaign.gam_cpc || 0, fill: chartColor(3) }
                      ].map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                ) : (
                  // Gráfico combinado (barras + linha) para múltiplos dias
                  <ComposedChart data={historicalData}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                      return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                    }} />
                    <YAxis yAxisId="left" {...volcAxis} tickFormatter={(value) => `$${value.toFixed(2)}`} />
                    <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => `$${value.toFixed(2)}`} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip
                        labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                        valueFormatter={(value, name) =>
                          name === 'CPC' ? `$${Number(value).toFixed(4)}` : `$${Number(value).toFixed(2)}`
                        }
                      />
                    } />
                    <Bar
                      yAxisId="left"
                      dataKey="gam_ecpm"
                      fill={chartColor(2)}
                      name="eCPM"
                      radius={[4, 4, 0, 0]}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="gam_cpc"
                      stroke={chartColor(3)}
                      name="CPC"
                      {...volcLine}
                    />
                  </ComposedChart>
                )}
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico eCPM vs Taxa de Correspondência */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><BarChart3 className="h-4 w-4" /></span>
                eCPM vs Taxa de Correspondência - Ad Exchange ({getChartPeriodTitle()})
              </CardTitle>
              <CardDescription className="text-xs">
                eCPM médio: ${(campaign.gam_ecpm || 0).toFixed(2)} • Match Rate: {(campaign.match_rate || 0).toFixed(1)}%
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                {historicalData.length <= 1 ? (
                  // Gráfico de barras para 1 dia
                  <BarChart data={[
                    { name: 'eCPM', value: campaign.gam_ecpm || 0, fill: chartColor(2) },
                    { name: 'Match Rate', value: campaign.match_rate || 0, fill: chartColor(4) }
                  ]}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="name" {...volcAxis} />
                    <YAxis {...volcAxis} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip valueFormatter={(value) => Number(value).toLocaleString()} />
                    } />
                    <Bar dataKey="value" name="" radius={[8, 8, 0, 0]}>
                      {[
                        { name: 'eCPM', value: campaign.gam_ecpm || 0, fill: chartColor(2) },
                        { name: 'Match Rate', value: campaign.match_rate || 0, fill: chartColor(4) }
                      ].map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                ) : (
                  // Gráfico combinado (barras + linha) para múltiplos dias
                  <ComposedChart data={historicalData}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                      return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                    }} />
                    <YAxis yAxisId="left" {...volcAxis} tickFormatter={(value) => `$${value.toFixed(2)}`} />
                    <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => `${value.toFixed(0)}%`} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip
                        labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                        valueFormatter={(value, name) =>
                          name === 'eCPM' ? `$${Number(value).toFixed(2)}` : `${Number(value).toFixed(1)}%`
                        }
                      />
                    } />
                    <Bar
                      yAxisId="left"
                      dataKey="gam_ecpm"
                      fill={chartColor(2)}
                      name="eCPM"
                      radius={[4, 4, 0, 0]}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="match_rate"
                      stroke={chartColor(4)}
                      name="Taxa de Correspondência"
                      {...volcLine}
                    />
                  </ComposedChart>
                )}
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico Total de Solicitações vs Impressões vs Fill Rate */}
          <Card className="hover-lift">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><BarChart3 className="h-4 w-4" /></span>
                Solicitações vs Impressões vs Fill Rate - Ad Exchange ({getChartPeriodTitle()})
              </CardTitle>
              <CardDescription className="text-xs">
                Total Solicitações: {(campaign.gam_total_requests || 0).toLocaleString()} • Impressões GAM: {(campaign.gam_impressions || 0).toLocaleString()} • Fill Rate: {(campaign.fill_rate || 0).toFixed(1)}%
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={historicalData}>
                  <CartesianGrid {...volcGrid} />
                  <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                    return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                  }} />
                  <YAxis yAxisId="left" {...volcAxis} tickFormatter={(value) => value.toLocaleString()} />
                  <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => `${value.toFixed(0)}%`} />
                  <Tooltip cursor={volcCursor} content={
                    <VolcTooltip
                      labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                      valueFormatter={(value, name) =>
                        name === 'Fill Rate' ? `${Number(value).toFixed(1)}%` : Number(value).toLocaleString()
                      }
                    />
                  } />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="gam_total_requests"
                    stroke={chartColor(0)}
                    name="Total Solicitações"
                    {...volcLine}
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="gam_impressions"
                    stroke={chartColor(2)}
                    name="Impressões GAM"
                    {...volcLine}
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="fill_rate"
                    stroke={chartColor(4)}
                    name="Fill Rate"
                    {...volcLine}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico Impressões vs Cliques vs CTR vs CPC do Ad Exchange */}
          <Card className="hover-lift">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><MousePointer className="h-4 w-4" /></span>
                Impressões vs Cliques vs CTR vs CPC - Ad Exchange ({getChartPeriodTitle()})
              </CardTitle>
              <CardDescription className="text-xs">
                Impressões GAM: {(campaign.gam_impressions || 0).toLocaleString()} • Cliques GAM: {(campaign.gam_clicks || 0).toLocaleString()} • CTR: {(campaign.gam_ctr || 0).toFixed(2)}% • CPC: {formatCurrency((campaign.gam_cpc || 0) * exchangeRate)}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={historicalData}>
                  <CartesianGrid {...volcGrid} />
                  <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                    return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                  }} />
                  <YAxis yAxisId="left" {...volcAxis} tickFormatter={(value) => value.toLocaleString()} />
                  <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => `${value.toFixed(1)}%`} />
                  <Tooltip cursor={volcCursor} content={
                    <VolcTooltip
                      labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                      valueFormatter={(value, name) => {
                        if (name === 'CTR GAM') return `${Number(value).toFixed(2)}%`;
                        if (name === 'CPC GAM') return formatCurrency(Number(value) * exchangeRate);
                        return Number(value).toLocaleString();
                      }}
                    />
                  } />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="gam_impressions"
                    stroke={chartColor(2)}
                    name="Impressões GAM"
                    {...volcLine}
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="gam_clicks"
                    stroke={chartColor(0)}
                    name="Cliques GAM"
                    {...volcLine}
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="gam_ctr"
                    stroke={chartColor(4)}
                    name="CTR GAM"
                    {...volcLine}
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="gam_cpc"
                    stroke={chartColor(3)}
                    name="CPC GAM"
                    {...volcLine}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico Impressões vs Porcentagem de Impressões Visíveis */}
          <Card className="hover-lift">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><Eye className="h-4 w-4" /></span>
                Impressões vs Impressões Visíveis - Ad Exchange ({getChartPeriodTitle()})
              </CardTitle>
              <CardDescription className="text-xs">
                Impressões GAM: {(campaign.gam_impressions || 0).toLocaleString()} • Impressões Visíveis: {(campaign.viewable_impressions || 0).toFixed(1)}%
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                {historicalData.length <= 1 ? (
                  <ComposedChart data={[
                    { name: 'Impressões GAM', value: campaign.gam_impressions || 0, type: 'bar' },
                    { name: 'Impressões Visíveis', value: campaign.viewable_impressions || 0, type: 'line' }
                  ]}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="name" {...volcAxis} />
                    <YAxis yAxisId="left" {...volcAxis} tickFormatter={(value) => value.toLocaleString()} />
                    <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => `${value.toFixed(0)}%`} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip valueFormatter={(value) => Number(value).toLocaleString()} />
                    } />
                    <Bar yAxisId="left" dataKey="value" fill={chartColor(2)} name="Impressões GAM" radius={[4, 4, 0, 0]} />
                  </ComposedChart>
                ) : (
                  <ComposedChart data={historicalData}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                      return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                    }} />
                    <YAxis yAxisId="left" {...volcAxis} tickFormatter={(value) => value.toLocaleString()} />
                    <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => `${value.toFixed(0)}%`} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip
                        labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                        valueFormatter={(value, name) =>
                          name === 'Impressões Visíveis' ? `${Number(value).toFixed(1)}%` : Number(value).toLocaleString()
                        }
                      />
                    } />
                    <Bar
                      yAxisId="left"
                      dataKey="gam_impressions"
                      fill={chartColor(2)}
                      name="Impressões GAM"
                      radius={[4, 4, 0, 0]}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="viewable_impressions"
                      stroke={chartColor(4)}
                      name="Impressões Visíveis"
                      {...volcLine}
                    />
                  </ComposedChart>
                )}
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico ROI vs Faturamento */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><Crown className="h-4 w-4" /></span>
                ROI vs Faturamento ({getChartPeriodTitle()})
              </CardTitle>
              <CardDescription className="text-xs">
                Faturamento: {formatRevenue(revenue)} • ROI: {roi}% (imposto: {taxRate}%)
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                {historicalData.length <= 1 ? (
                  // Gráfico de barras para 1 dia
                  <ComposedChart data={[
                    { name: 'Faturamento', revenue: revenue, roi: Number(roi) }
                  ]}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="name" {...volcAxis} />
                    <YAxis yAxisId="left" {...volcAxis} tickFormatter={(value) => `R$ ${value.toFixed(0)}`} />
                    <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => `${value.toFixed(1)}%`} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip valueFormatter={(value, name) =>
                        name === 'ROI' ? `${Number(value).toFixed(1)}%` : `R$ ${Number(value).toFixed(2)}`
                      } />
                    } />
                    <Bar yAxisId="left" dataKey="revenue" fill={chartColor(4)} name="Faturamento" radius={[8, 8, 0, 0]} />
                    <Line yAxisId="right" type="monotone" dataKey="roi" stroke={chartColor(0)} name="ROI" {...volcLine} />
                  </ComposedChart>
                ) : (
                  // Gráfico combinado (barras + linha) para múltiplos dias
                  <ComposedChart data={historicalData.map(item => {
                    const itemRevenue = item.revenue || 0;
                    const itemSpend = item.spend || 0;
                    const itemRevenueAfterTax = itemRevenue * (1 - taxRate / 100);
                    const itemProfitAfterTax = itemRevenueAfterTax - itemSpend;
                    const itemRoi = itemSpend > 0 ? ((itemProfitAfterTax / itemSpend) * 100) : 0;

                    return {
                      ...item,
                      roi: itemRoi
                    };
                  })}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                      return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                    }} />
                    <YAxis yAxisId="left" {...volcAxis} tickFormatter={(value) => `R$ ${value.toFixed(0)}`} />
                    <YAxis yAxisId="right" orientation="right" {...volcAxis} tickFormatter={(value) => `${value.toFixed(1)}%`} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip
                        labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                        valueFormatter={(value, name) =>
                          name === 'ROI' ? `${Number(value).toFixed(1)}%` : `R$ ${Number(value).toFixed(2)}`
                        }
                      />
                    } />
                    <Bar
                      yAxisId="left"
                      dataKey="revenue"
                      fill={chartColor(4)}
                      name="Faturamento"
                      radius={[4, 4, 0, 0]}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="roi"
                      stroke={chartColor(0)}
                      name="ROI"
                      {...volcLine}
                    />
                  </ComposedChart>
                )}
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Gráfico Gasto vs Revenue */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-display">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><Coins className="h-4 w-4" /></span>
                Gasto vs Revenue ({getChartPeriodTitle()})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                {historicalData.length <= 1 ? (
                  // Gráfico de barras para 1 dia
                  <BarChart data={[
                    { name: 'Gasto', value: campaign.spend, fill: chartColor(3) },
                    { name: 'Revenue', value: revenue, fill: chartColor(4) },
                    { name: 'Lucro Bruto', value: profit, fill: chartColor(0) }
                  ]}>
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="name" {...volcAxis} />
                    <YAxis {...volcAxis} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip valueFormatter={(value) => `R$ ${Number(value).toFixed(2)}`} />
                    } />
                    <Bar dataKey="value" name="" radius={[8, 8, 0, 0]}>
                      {[
                        { name: 'Gasto', value: campaign.spend, fill: chartColor(3) },
                        { name: 'Revenue', value: revenue, fill: chartColor(4) },
                        { name: 'Lucro Bruto', value: profit, fill: chartColor(0) }
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
                    <CartesianGrid {...volcGrid} />
                    <XAxis dataKey="date" {...volcAxis} tickFormatter={(date) => {
                      return parseDateToSaoPaulo(date).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                    }} />
                    <YAxis {...volcAxis} />
                    <Tooltip cursor={volcCursor} content={
                      <VolcTooltip
                        labelFormatter={(date) => parseDateToSaoPaulo(String(date)).toLocaleDateString('pt-BR')}
                        valueFormatter={(value) => `R$ ${Number(value).toFixed(2)}`}
                      />
                    } />
                    <Line type="monotone" dataKey="spend" stroke={chartColor(3)} name="Gasto" {...volcLine} />
                    <Line type="monotone" dataKey="revenue" stroke={chartColor(4)} name="Revenue" {...volcLine} />
                    <Line type="monotone" dataKey="profit" stroke={chartColor(0)} name="Lucro Bruto" {...volcLine} />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        {/* Insights de IA - Orientação do Dia */}
        {orientacaoData && (
          <div className="mt-6">
            <OrientacaoBox
              orientacaoTexto={orientacaoData.orientacao_texto}
              orientacaoResumo={orientacaoData.orientacao_resumo}
              orientacaoGeradoEm={orientacaoData.orientacao_json?.gerado_em || orientacaoData.date}
            />
          </div>
        )}

        {/* Ajuste de Bidding - Ação Sugerida */}
        {orientacaoData?.orientacao_json?.decisao && (
          <div className="mt-6">
            <BiddingActionBox
              campaignId={campaignId!}
              currentBid={orientacaoData.orientacao_json.decisao.valor_referencia}
              suggestedBid={orientacaoData.orientacao_json.decisao.valor_sugerido}
              action={orientacaoData.orientacao_json.decisao.acao}
              risk={orientacaoData.orientacao_json.decisao.risco}
              variationPercent={orientacaoData.orientacao_json.decisao.variacao_percent}
              dataReferencia={orientacaoData.date || selectedDate}
            />
          </div>
        )}

        {/* Auto Adjust Realizado */}
        {otimizacaoData && (
          <div className="mt-6">
            <OtimizacaoBox
              otimizacaoResumo={otimizacaoData.otimizacao_resumo}
              otimizacaoJson={otimizacaoData.otimizacao_json}
              otimizacaoRealizadaEm={otimizacaoData.otimizacao_realizada_em}
            />
          </div>
        )}
      </div>

      {/* ROI Display por Placement */}
        {campaignId && selectedDate && (
          <DisplayROITable
            campaignId={campaignId}
            startDate={selectedDate}
            endDate={selectedEndDate || selectedDate}
          />
        )}

      {/* Sugestões de Negativação — Display only */}
        {campaignId && campaign?.advertising_channel === 'DISPLAY' && (
          <PlacementNegationCard campaignId={campaignId} />
        )}

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