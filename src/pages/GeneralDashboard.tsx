import React, { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Badge, StatusBadge, ROASBadge, PerformanceBadge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { SimpleDateFilter } from "@/components/dashboard/SimpleDateFilter";
import { DataStatus } from "@/components/dashboard/DataStatus";
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
  Clock,
  RefreshCw,
  Minus,
  User,
  ArrowUpRight,
  ArrowDown,
  Target,
  PieChart,
  Activity,
  CheckCircle,
  X,
  Info,
  Settings
} from "lucide-react";
import { 
  LineChart, 
  Line, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip as RechartsTooltip, 
  ResponsiveContainer,
  PieChart as RechartsPieChart,
  Pie,
  Cell
} from "recharts";
import { Link, useNavigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { cn } from "@/lib/utils";
import { useSupabaseData, supabaseDataService } from "@/services/supabaseDataService";
import { operationalCostsService } from "@/services/operationalCostsService";
import { FinalExchangeRateManager } from "@/components/currency/FinalExchangeRateManager";
import { currencyConversionService } from "@/services/currencyConversionService";
import { taxHistoryService } from "@/services/taxHistoryService";
// import { SiteAnalysis } from "@/components/dashboard/SiteAnalysis";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { formatBrlCurrency, formatCostCurrency, getCachedExchangeRate, preloadExchangeRate } from "@/utils/currencyUtils";
import { calculateROAS, getROASColorStyles, getROASBadgeColor, getROASColorCategory } from "@/utils/roasCalculations";
import { useUserProfile } from "@/hooks/useUserProfile";
import { RevenueTooltip } from "@/components/ui/revenue-tooltip";

const integrationStatus = [
  { name: "Google Ads", status: "online", lastSync: "2 min atrás" },
  { name: "Google Ad Manager", status: "online", lastSync: "5 min atrás" },
  { name: "Analytics", status: "pending", lastSync: "15 min atrás" }
];



const COLORS = ['hsl(var(--success))', 'hsl(var(--info))', 'hsl(var(--warning))', 'hsl(var(--destructive))'];

// Componente SVG decorativo para cards
const CardDecoration = ({ color }: { color: string }) => (
  <svg
    className="absolute right-0 top-0 h-full w-2/3 pointer-events-none opacity-10"
    viewBox="0 0 300 200"
    fill="none"
    style={{ zIndex: 0 }}
  >
    <circle cx="220" cy="100" r="90" fill={color} />
    <circle cx="260" cy="60" r="60" fill={color} />
    <circle cx="200" cy="160" r="50" fill={color} />
    <circle cx="270" cy="150" r="30" fill={color} />
  </svg>
);

export default function GeneralDashboard() {
  const navigate = useNavigate();
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | 'yesterday' | 'custom'>("today");
  const [selectedDate, setSelectedDate] = useState<string>(""); // Will be set dynamically
  const [exchangeRate, setExchangeRate] = useState<number>(5.50);
  const [webhookStatus, setWebhookStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [currentTaxRate, setCurrentTaxRate] = useState<number>(8.1);
  const [dailyOperationalCosts, setDailyOperationalCosts] = useState<number>(0);
  const { getUserFirstName } = useUserProfile();
  
  // Initialize with current server date (São Paulo timezone) and preload exchange rate
  React.useEffect(() => {
    const initialize = async () => {
      try {
        // Initialize date
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);
        console.log('🇧🇷 Dashboard initialized with São Paulo date:', serverDate);
        
        // Preload exchange rate for currency conversion
        const rate = await preloadExchangeRate();
        setExchangeRate(rate);
        console.log('💱 Exchange rate preloaded:', rate);

        // Load current tax rate
        const currentMonth = serverDate.substring(0, 7); // YYYY-MM format
        const taxRate = await taxHistoryService.getCurrentTaxRate(currentMonth);
        setCurrentTaxRate(taxRate);
        console.log('📊 Current tax rate loaded:', taxRate, '%');
      } catch (error) {
        console.error('Error during initialization:', error);
        // Fallback to São Paulo timezone date
        const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(new Date());
        setSelectedDate(saoPauloDate);
      }
    };
    
    initialize();
  }, []);
  
  // Use filtered data based on current selections - sempre mostra todos os projetos
  // TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom' para usar a mesma lógica
  const filters = {
    date: selectedDate,
    projectId: 'all', // Sempre todos os projetos no dashboard geral
    period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod
  };

  // Debug: Log current filters for monitoring
  React.useEffect(() => {
    console.log('🔍 Current filters applied:', filters);
    console.log('🔍 DETAILED DEBUG:', {
      selectedPeriod,
      selectedDate,
      filterPeriod: filters.period,
      filterDate: filters.date,
      isYesterdayTreatedAsCustom: selectedPeriod === 'yesterday' && filters.period === 'custom'
    });
  }, [filters]);
  
  const { projects, campaigns, dailyMetrics, summary, loading, error, lastUpdate, refresh } = useSupabaseData(filters);
  
  // Debug: Verificar dados no banco para data atual
  React.useEffect(() => {
    if (selectedPeriod === 'today') {
      console.log('📅 Current selected date for debug:', selectedDate);
      // Clear cache and force fresh data
      supabaseDataService.clearServerDateCache();
      supabaseDataService.debugDataForDate(selectedDate);
    }
  }, [selectedPeriod, selectedDate]);
  
  // Force refresh data when period changes
  React.useEffect(() => {
    if (selectedPeriod === 'today' || selectedPeriod === 'yesterday') {
      console.log('🔄 Forcing refresh for period:', selectedPeriod);
      setTimeout(() => {
        refresh(filters);
      }, 500);
    }
  }, [selectedPeriod, selectedDate]);

  // Load daily operational costs
  React.useEffect(() => {
    const loadDailyOperationalCosts = async () => {
      try {
        const currentMonth = new Date().toISOString().slice(0, 7); // YYYY-MM
        const dailyCosts = await operationalCostsService.getDailyActiveCosts(currentMonth);
        setDailyOperationalCosts(dailyCosts);
        console.log('💼 Daily operational costs loaded:', dailyCosts);
      } catch (error) {
        console.error('Error loading daily operational costs:', error);
        setDailyOperationalCosts(0);
      }
    };

    loadDailyOperationalCosts();
  }, []);
  
  // Create synthetic daily data when dailyMetrics is empty but we have summary data
  const chartData = React.useMemo(() => {
    if (dailyMetrics && dailyMetrics.length > 0) {
      return dailyMetrics;
    }
    
    // If no daily metrics but we have summary data, create synthetic data for today
    if (summary && (summary.totalInvestment > 0 || summary.totalRevenue > 0)) {
      const today = format(new Date(), 'yyyy-MM-dd');
      return [{
        date: today,
        investment: summary.totalInvestment,
        revenue: summary.totalRevenue,
        profit: summary.totalProfit,
        roas: summary.generalRoas,
        roi: summary.finalRoi,
        impressions: 0,
        clicks: 0,
        ctr: 0,
        conversions: 0,
        ecpm: 0,
        cpc: 0,
        viewability: 0,
        pmr: 0,
        rps: 0
      }];
    }
    
    return [];
  }, [dailyMetrics, summary]);
  
  // Debug logs
  console.log('🔍 Dashboard Debug:', {
    campaigns: campaigns?.length || 0,
    dailyMetrics: dailyMetrics?.length || 0,
    chartData: chartData?.length || 0,
    summary,
    filters,
    loading,
    error
  });
  
  // Log chart data being used
  if (chartData && chartData.length > 0) {
    console.log('📊 Chart data:', chartData);
  }

  const handlePeriodChange = async (period: 'today' | 'yesterday' | 'custom') => {
    setSelectedPeriod(period);
    // Reset to current server date when changing to 'today' or 'yesterday'
    if (period === 'today') {
      try {
        // Clear cache and get fresh server date
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);
        console.log('🔄 Updated to current server date:', serverDate);
      } catch (error) {
        console.error('Error getting server date:', error);
        // Fallback to São Paulo timezone date
        const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(new Date());
        setSelectedDate(saoPauloDate);
      }
    } else if (period === 'yesterday') {
      try {
        // Clear caches for fresh data
        supabaseDataService.clearServerDateCache();

        // Get server date and calculate yesterday
        const serverDate = await supabaseDataService.getServerDate();
        console.log('🔍 DEBUG YESTERDAY - Server date:', serverDate);
        const serverDateObj = new Date(serverDate + 'T00:00:00-03:00'); // São Paulo timezone
        const yesterdayObj = new Date(serverDateObj);
        yesterdayObj.setDate(yesterdayObj.getDate() - 1);
        const yesterdayStr = yesterdayObj.toISOString().split('T')[0];
        setSelectedDate(yesterdayStr);
        console.log('🔄 Updated to yesterday:', yesterdayStr);
        console.log('🔍 DEBUG YESTERDAY - Calculation:', {
          serverDate,
          serverDateObj: serverDateObj.toISOString(),
          yesterdayObj: yesterdayObj.toISOString(),
          finalYesterdayString: yesterdayStr
        });

        // TRATAMENTO COMO CUSTOM DATE: Force immediate refresh for yesterday data usando 'custom' period
        setTimeout(() => {
          const yesterdayFilters = { ...filters, date: yesterdayStr, period: 'custom' };
          console.log('🔄 Forcing immediate refresh for yesterday AS CUSTOM:', yesterdayFilters);
          refresh(yesterdayFilters);
        }, 100);
      } catch (error) {
        console.error('Error getting server date for yesterday:', error);
        // Fallback to São Paulo timezone yesterday
        const now = new Date();
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        const saoPauloYesterday = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(yesterday);
        setSelectedDate(saoPauloYesterday);

        // TRATAMENTO COMO CUSTOM DATE: Force immediate refresh for yesterday data (fallback) usando 'custom' period
        setTimeout(() => {
          const yesterdayFilters = { ...filters, date: saoPauloYesterday, period: 'custom' };
          console.log('🔄 Forcing immediate refresh for yesterday AS CUSTOM (fallback):', yesterdayFilters);
          refresh(yesterdayFilters);
        }, 100);
      }
    }
  };

  const handleDateChange = (date: string) => {
    console.log('📅 Date changed to:', date, 'period:', selectedPeriod);
    setSelectedDate(date);
    // Force a refresh when date changes to ensure data is up to date
    // TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom'
    const newFilters = {
      ...filters,
      date,
      period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod
    };
    console.log('🔄 Refreshing with new filters:', newFilters);
    setTimeout(() => {
      refresh(newFilters);
    }, 100);
  };


  // Função para formatar valores de REVENUE (já convertidos pelo database em revenue_conversao)
  const formatRevenue = (brlValue: number) => {
    return formatBrlCurrency(brlValue);
  };

  // Função para formatar valores de CUSTOS/GASTOS (já em BRL)
  const formatCurrency = (brlValue: number) => {
    return formatCostCurrency(brlValue);
  };

  // Função para calcular lucro (Revenue BRL - Custo BRL)
  const calculateProfit = (revenueBrl: number, costBrl: number) => {
    return revenueBrl - costBrl;
  };

  // Using centralized ROAS calculation (excess percentage)

  // Função para calcular ROI corretamente (Profit / Spend * 100)
  const calculateROI = (revenueBrl: number, spendBrl: number) => {
    if (spendBrl <= 0) return 0;
    const profit = calculateProfit(revenueBrl, spendBrl);
    return (profit / spendBrl) * 100;
  };

  // UPDATED: Função para calcular ROI final usando valores pré-calculados (revenue já líquido)
  const calculateFinalROI = (totalRevenueAfterRevshare: number, totalInvestment: number, taxRate: number) => {
    if (totalInvestment <= 0) return 0;

    // Usar cálculo simplificado com valores já processados
    const calculation = calculateSimplifiedNetProfit(totalRevenueAfterRevshare, totalInvestment, taxRate, dailyOperationalCosts);

    return (calculation.netProfit / totalInvestment) * 100;
  };

  // Função para calcular lucro líquido CORRETO: Revenue Bruto - Revenue Share - Impostos (sobre líquido)
  const calculateNetProfitAfterTax = (grossProfit: number, taxRate: number) => {
    // Esta função mantida para compatibilidade, mas agora é apenas um wrapper
    return calculateCorrectNetProfit(grossProfit, 0, taxRate, 0);
  };

  // Função para calcular revenue share real baseado nos projetos
  const calculateRealRevenueShare = () => {
    if (!projects || projects.length === 0) {
      return { percentage: 0.1, amount: 0 }; // 10% padrão se não houver dados
    }

    const totalRevenue = summary?.totalRevenue || 0;
    if (totalRevenue === 0) {
      return { percentage: 0.1, amount: 0 };
    }

    // Para dashboard geral, calcular média ponderada por revenue de cada projeto
    let totalWeightedRevshare = 0;
    let totalProjectRevenue = 0;

    projects.forEach(project => {
      const projectRevenue = project.revenue || 0;
      const projectRevshare = project.revshare || 0.1; // 10% se não definido
      
      totalWeightedRevshare += projectRevenue * projectRevshare;
      totalProjectRevenue += projectRevenue;
    });

    const averageRevshare = totalProjectRevenue > 0 ? totalWeightedRevshare / totalProjectRevenue : 0.1;
    const totalRevenueShareAmount = totalRevenue * averageRevshare;

    console.log('📊 Revenue Share Calculation:', {
      projects: projects.length,
      totalRevenue,
      averageRevshare: (averageRevshare * 100).toFixed(1) + '%',
      totalRevenueShareAmount
    });

    return { 
      percentage: averageRevshare, 
      amount: totalRevenueShareAmount 
    };
  };

  // Nova função para calcular lucro líquido corretamente com revenue share real
  const calculateCorrectNetProfit = (
    totalRevenue: number, 
    totalInvestment: number, 
    taxRate: number,
    customRevenueShare?: number
  ) => {
    // Usar revenue share real se não fornecido customizado
    const revenueShareData = customRevenueShare !== undefined ? 
      { percentage: customRevenueShare, amount: totalRevenue * customRevenueShare } : 
      calculateRealRevenueShare();

    // 1. Faturamento Bruto (GAM) - Revenue Share = Faturamento Líquido
    const revenueAfterShare = totalRevenue - revenueShareData.amount;
    
    // 2. Faturamento Líquido - Investimento = Lucro Bruto
    const grossProfit = revenueAfterShare - totalInvestment;
    
    // 3. Imposto aplicado sobre o Faturamento Líquido (não sobre lucro bruto)
    const taxAmount = revenueAfterShare * (taxRate / 100);
    
    // 4. Lucro Líquido = Lucro Bruto - Impostos
    const netProfit = grossProfit - taxAmount;
    
    return {
      revenueAfterShare,
      grossProfit,
      taxAmount,
      netProfit,
      revenueSharePercentage: revenueShareData.percentage,
      revenueShareAmount: revenueShareData.amount
    };
  };

  // NEW: Função simplificada usando valores pré-calculados de revenue_converted_revshare
  const calculateSimplifiedNetProfit = (
    totalRevenueAfterRevshare: number,
    totalInvestment: number,
    taxRate: number,
    dailyOperationalCosts: number = 0
  ) => {
    // Cálculo simplificado: já temos o faturamento líquido (após revenue share)
    const grossProfit = totalRevenueAfterRevshare - totalInvestment;
    const taxAmount = totalRevenueAfterRevshare * (taxRate / 100);
    const netProfitBeforeCosts = grossProfit - taxAmount;
    const netProfit = netProfitBeforeCosts - dailyOperationalCosts;

    return {
      netRevenue: totalRevenueAfterRevshare,
      grossProfit,
      taxAmount,
      dailyOperationalCosts,
      netProfit,
      formula: `Faturamento Líquido (${totalRevenueAfterRevshare.toFixed(2)}) - Investimento (${totalInvestment.toFixed(2)}) - Impostos (${taxAmount.toFixed(2)}) - Custos Op. Diários (${dailyOperationalCosts.toFixed(2)}) = ${netProfit.toFixed(2)}`
    };
  };

  // Função para obter informações de imposto para tooltip
  const getTaxTooltipInfo = (grossProfit: number, taxRate: number) => {
    const taxAmount = grossProfit * (taxRate / 100);
    const netProfit = grossProfit - taxAmount;
    return {
      grossProfit,
      taxRate,
      taxAmount,
      netProfit
    };
  };

  const getTrendIcon = (trend: 'up' | 'down' | 'stable') => {
    switch (trend) {
      case 'up': return <TrendingUp className="h-4 w-4 text-green-500" />;
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

  // Using centralized ROAS color styling
  const getROIColor = (roasExcess: number) => {
    return getROASColorStyles(roasExcess);
  };

  // Using centralized ROAS badge color
  const getROIBadgeColor = (roasExcess: number) => {
    return getROASBadgeColor(roasExcess);
  };

  const handleRefresh = async () => {
    console.log('🔄 Manual refresh triggered');
    
    // Check if we need to force revenue conversion
    try {
      console.log('🔄 Checking if revenue conversion is needed...');
      await currencyConversionService.updateDatabaseConversions();
      console.log('✅ Revenue conversion check completed');
    } catch (error) {
      console.warn('⚠️ Revenue conversion failed:', error);
    }
    
    refresh(filters);
  };

  const handleUpdateGAM = async () => {
    console.log('🔄 Triggering N8N GAM update...');
    setWebhookStatus('loading');

    try {
      const response = await fetch('https://n8n.srv860769.hstgr.cloud/webhook/a0466725-8a5f-4b7f-b110-04e413eaf9dc', {
        method: 'GET'
      });
      
      if (response.ok) {
        console.log('✅ N8N webhook triggered successfully');
        setWebhookStatus('success');
        
        // Reset status after 3 seconds
        setTimeout(() => {
          setWebhookStatus('idle');
        }, 3000);
      } else {
        console.error('❌ N8N webhook failed:', response.status, response.statusText);
        setWebhookStatus('error');
        
        // Reset status after 3 seconds
        setTimeout(() => {
          setWebhookStatus('idle');
        }, 3000);
      }
    } catch (error) {
      console.error('❌ Error triggering N8N webhook:', error);
      setWebhookStatus('error');
      
      // Reset status after 3 seconds
      setTimeout(() => {
        setWebhookStatus('idle');
      }, 3000);
    }
  };

  const handleUpdateGoogleAds = async () => {
    console.log('🔄 Triggering N8N Google Ads update...');
    setWebhookStatus('loading');

    try {
      const response = await fetch('https://n8n.srv860769.hstgr.cloud/webhook/a3aa1e8c-5d20-41af-96e9-30ba589ae35d', {
        method: 'GET'
      });

      if (response.ok) {
        console.log('✅ N8N Google Ads webhook triggered successfully');
        setWebhookStatus('success');

        // Reset status after 3 seconds
        setTimeout(() => {
          setWebhookStatus('idle');
        }, 3000);
      } else {
        console.error('❌ N8N Google Ads webhook failed:', response.status, response.statusText);
        setWebhookStatus('error');

        // Reset status after 3 seconds
        setTimeout(() => {
          setWebhookStatus('idle');
        }, 3000);
      }
    } catch (error) {
      console.error('❌ Error triggering N8N Google Ads webhook:', error);
      setWebhookStatus('error');

      // Reset status after 3 seconds
      setTimeout(() => {
        setWebhookStatus('idle');
      }, 3000);
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-screen">
          <LoadingSpinner size="lg" text="Carregando dashboard..." />
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="flex flex-col items-center justify-center min-h-screen p-8">
          <div className="text-center">
            <AlertTriangle className="h-16 w-16 text-destructive mx-auto mb-4" />
            <h1 className="text-2xl font-bold mb-2">Erro ao carregar dados</h1>
            <p className="text-muted-foreground mb-4">{error}</p>
            <Button onClick={handleRefresh} variant="outline">
              <RefreshCw className="h-4 w-4 mr-2" />
              Tentar novamente
            </Button>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="p-6 space-y-8 max-w-7xl mx-auto">
        {/* Header with User and Controls */}
        <div className="flex items-center justify-between transition-all duration-300">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold bg-gradient-to-r from-primary via-purple-600 to-blue-600 bg-clip-text text-transparent">
                Dashboard Geral
              </h1>
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-gradient-to-r from-primary/10 to-purple-500/10 border border-primary/20">
                <User className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium text-primary">{getUserFirstName()}</span>
              </div>
            </div>
            <p className="text-muted-foreground">
              Visão geral de todas as campanhas e projetos
              {selectedPeriod === 'custom' && selectedDate && (
                <span className="ml-2 text-primary">
                  • Data: {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}
                </span>
              )}
              {selectedPeriod !== 'custom' && (
                <span className="ml-2 text-primary">
                  • Período: {selectedPeriod === 'today' ? 'Hoje' : selectedPeriod === 'yesterday' ? 'Ontem' : 'Data personalizada'}
                </span>
              )}
            </p>
          </div>
          
          <div className="flex items-center gap-3 flex-wrap">
            
            <div className="flex flex-col gap-1">
              <SimpleDateFilter
                selectedPeriod={selectedPeriod}
                selectedDate={selectedDate}
                onPeriodChange={handlePeriodChange}
                onDateChange={handleDateChange}
              />
              {selectedPeriod === 'custom' && selectedDate && (
                <div className="text-xs text-muted-foreground px-2 flex items-center gap-1">
                  📅 Consultando data: {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}
                  {!loading && campaigns.length === 0 && (
                    <span className="text-amber-600">⚠️ Sem dados</span>
                  )}
                  {!loading && campaigns.length > 0 && (
                    <span className="text-green-600">✓ {campaigns.length} campanhas</span>
                  )}
                </div>
              )}
            </div>
            
            <Button onClick={handleRefresh} variant="outline" size="sm">
              <RefreshCw className="h-4 w-4 mr-2" />
              Atualizar
            </Button>
            
            <div className="flex items-center gap-2">
              <Button
                onClick={handleUpdateGAM}
                variant="default"
                size="sm"
                disabled={webhookStatus === 'loading'}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${webhookStatus === 'loading' ? 'animate-spin' : ''}`} />
                Atualizar GAM
              </Button>

              <Button
                onClick={handleUpdateGoogleAds}
                variant="default"
                size="sm"
                disabled={webhookStatus === 'loading'}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${webhookStatus === 'loading' ? 'animate-spin' : ''}`} />
                Atualizar Google Ads
              </Button>
              
              {webhookStatus === 'success' && (
                <CheckCircle className="h-4 w-4 text-green-500" />
              )}
              
              {webhookStatus === 'error' && (
                <X className="h-4 w-4 text-red-500" />
              )}
            </div>
            
            <DataStatus 
              loading={loading} 
              error={error} 
              lastUpdate={lastUpdate}
              showDetails={true}
            />
          </div>
        </div>


        {/* Campanhas Controladas pelo Usuário - Destaque */}
        {campaigns.filter(c => c.statusSource === 'user').length > 0 && (
          <Card className="shadow-lg transition-all duration-500 border-blue-500/30 bg-gradient-to-r from-blue-500/10 to-indigo-500/10">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-blue-700">
                <User className="h-5 w-5" />
                Campanhas Controladas Manualmente
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {campaigns
                  .filter(c => c.statusSource === 'user')
                  .slice(0, 6)
                  .map((campaign, index) => (
                    <div key={index} className="flex items-center justify-between p-3 rounded-lg bg-blue-50 border border-blue-200">
                      <div>
                        <p className="text-sm font-medium text-blue-900">{campaign.name}</p>
                        <p className="text-xs text-blue-600">
                          {campaign.status === 'paused' ? '⏸️ Pausada' : '▶️ Ativa'} pelo usuário
                        </p>
                      </div>
                      <Badge variant="outline" className="text-blue-700 border-blue-300">
                        R$ {campaign.revenue?.toFixed(2) || '0.00'}
                      </Badge>
                    </div>
                  ))}
              </div>
              {campaigns.filter(c => c.statusSource === 'user').length > 6 && (
                <p className="text-center text-sm text-blue-600 mt-3">
                  +{campaigns.filter(c => c.statusSource === 'user').length - 6} campanhas com controle manual
                </p>
              )}
            </CardContent>
          </Card>
        )}



        {/* Site Analysis - Main Chart */}
        <div className="grid gap-6 transition-all duration-300">
          {/* <SiteAnalysis /> */}
        </div>

        {/* KPI Overview - Cards Resumo */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 transition-all duration-300">
          <Card className="relative overflow-hidden shadow-lg border-info/20 bg-gradient-to-br from-info/5 via-violet-500/5 to-info/10 hover:shadow-xl transition-shadow">
            <CardDecoration color="hsl(var(--info))" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <CardTitle className="text-sm font-medium">💸 Gasto Total</CardTitle>
              <DollarSign className="h-4 w-4 text-blue-500" />
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="text-2xl font-bold">{formatCurrency(summary?.totalInvestment || 0)}</div>
              <div className="flex items-center text-xs mt-1">
                <ArrowUpRight className="mr-1 h-3 w-3 text-green-500" />
                <span className="text-green-500">+{summary?.trendsPercentage?.investment || 0}%</span>
                <span className="text-muted-foreground ml-2">vs período anterior</span>
              </div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden shadow-lg border-green-500/20 bg-gradient-to-br from-green-500/5 via-green-400/5 to-green-500/10 hover:shadow-xl transition-shadow">
            <CardDecoration color="rgb(34, 197, 94)" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <CardTitle className="text-sm font-medium">💰 Revenue Total</CardTitle>
              <TrendingUp className="h-4 w-4 text-green-500" />
            </CardHeader>
            <CardContent className="relative z-10">
              <RevenueTooltip
                netRevenue={summary?.totalRevenue || 0}
                revsharePercentage={0.1}
                projectType="GAM" // Dashboard geral: mix de projetos, mas mostra como GAM para compatibilidade
              >
                <div className="text-2xl font-bold text-green-600">{formatRevenue(summary?.totalRevenue || 0)}</div>
              </RevenueTooltip>
              <div className="flex items-center text-xs mt-1">
                <ArrowUpRight className="mr-1 h-3 w-3 text-green-500" />
                <span className="text-green-500">+{summary?.trendsPercentage?.revenue || 0}%</span>
                <span className="text-muted-foreground ml-2">via UTM campaigns (líquido)</span>
              </div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden shadow-lg border-info/20 bg-gradient-to-br from-info/5 via-violet-500/5 to-info/10 hover:shadow-xl transition-shadow">
            <CardDecoration color="hsl(var(--info))" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <CardTitle className="text-sm font-medium">📈 ROAS Geral</CardTitle>
              <BarChart3 className="h-4 w-4 text-blue-500" />
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="text-2xl font-bold">{summary?.generalRoas || 0}%</div>
              <div className="flex items-center text-xs mt-1">
                <ArrowUpRight className="mr-1 h-3 w-3 text-green-500" />
                <span className="text-green-500">+{summary?.trendsPercentage?.roas || 0}%</span>
              </div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden shadow-lg border-success/20 bg-gradient-to-br from-success/5 via-emerald-500/5 to-success/10 hover:shadow-xl transition-shadow">
            <CardDecoration color="hsl(var(--success))" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <div className="flex items-center gap-2">
                <CardTitle className="text-sm font-medium">💚 Lucro Líq</CardTitle>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="h-3 w-3 text-green-600 opacity-60 hover:opacity-100 cursor-help transition-opacity" />
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs p-4">
                      <div className="space-y-2 text-sm">
                        <div className="font-medium text-green-600 mb-2">Cálculo do Lucro Líquido</div>
                        {(() => {
                          const totalRevenue = summary?.totalRevenue || 0;
                          const totalInvestment = summary?.totalInvestment || 0;
                          
                          // NEW: Usar cálculo simplificado com valores pré-calculados
                          const calculation = calculateSimplifiedNetProfit(
                            summary?.totalRevenueAfterRevshare || totalRevenue * 0.9, // Fallback
                            totalInvestment,
                            currentTaxRate,
                            dailyOperationalCosts
                          );
                          
                          return (
                            <div className="space-y-1">
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Faturamento Total (pós-processamento):</span>
                                <span className="font-mono text-blue-600">{formatRevenue(calculation.netRevenue)}</span>
                              </div>
                              <div className="text-xs text-muted-foreground italic mb-2">
                                * Inclui GAM (após RevShare) + AdSense (sem RevShare)
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Investimento:</span>
                                <span className="font-mono text-red-600">-{formatCurrency(totalInvestment)}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Impostos SN ({currentTaxRate}%):</span>
                                <span className="font-mono text-red-600">-{formatCurrency(calculation.taxAmount)}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Custos Op. Diários:</span>
                                <span className="font-mono text-red-600">-{formatCurrency(calculation.dailyOperationalCosts)}</span>
                              </div>
                              <div className="border-t pt-1 border-green-200">
                                <div className="flex justify-between font-medium">
                                  <span>Lucro Líquido:</span>
                                  <span className="font-mono text-green-600">{formatCurrency(calculation.netProfit)}</span>
                                </div>
                              </div>
                            </div>
                          );
                        })()}
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <DollarSign className="h-4 w-4 text-green-500" />
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="text-2xl font-bold">
                {(() => {
                  const totalRevenue = summary?.totalRevenue || 0;
                  const totalInvestment = summary?.totalInvestment || 0;

                  // NEW: Usar cálculo simplificado com valores pré-calculados (mesmo do tooltip)
                  const calculation = calculateSimplifiedNetProfit(
                    summary?.totalRevenueAfterRevshare || totalRevenue * 0.9, // Fallback
                    totalInvestment,
                    currentTaxRate,
                    dailyOperationalCosts
                  );

                  return formatCurrency(calculation.netProfit);
                })()}
              </div>
              <div className="flex items-center justify-between text-xs mt-1">
                <div className="flex items-center">
                  <ArrowUpRight className="mr-1 h-3 w-3 text-green-500" />
                  <span className="text-green-500">+{summary?.trendsPercentage?.profit || 0}%</span>
                </div>
                <span className="text-muted-foreground">
                  {(() => {
                    const revenueShareData = calculateRealRevenueShare();
                    return `Após ${(revenueShareData.percentage * 100).toFixed(1)}% RS e ${currentTaxRate}% SN`;
                  })()}
                </span>
              </div>
            </CardContent>
          </Card>

          <Card className={`relative overflow-hidden shadow-lg hover:shadow-xl transition-shadow ${
            (() => {
              const finalRoi = calculateFinalROI(summary?.totalRevenue || 0, summary?.totalInvestment || 0, currentTaxRate);
              return getROIColor(finalRoi);
            })()
          }`}>
            <CardDecoration color={(() => {
              const finalRoi = calculateFinalROI(summary?.totalRevenue || 0, summary?.totalInvestment || 0, currentTaxRate);
              return getROIBadgeColor(finalRoi);
            })()} />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <div className="flex items-center gap-2">
                <CardTitle className="text-sm font-medium">👑 ROI Final</CardTitle>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="h-3 w-3 text-muted-foreground opacity-60 hover:opacity-100 cursor-help transition-opacity" />
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs p-4">
                      <div className="space-y-2 text-sm">
                        <div className="font-medium text-primary mb-2">Cálculo do ROI Final</div>
                        {(() => {
                          const totalRevenue = summary?.totalRevenue || 0; // Já é líquido (após revshare)
                          const totalInvestment = summary?.totalInvestment || 0;

                          // Cálculo simplificado: valor já vem líquido do banco
                          const calculation = calculateSimplifiedNetProfit(
                            totalRevenue, // Já é revenue_converted_revshare (líquido)
                            totalInvestment,
                            currentTaxRate,
                            dailyOperationalCosts
                          );

                          // ROI final
                          const finalRoi = totalInvestment > 0 ? (calculation.netProfit / totalInvestment) * 100 : 0;

                          return (
                            <div className="space-y-1">
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Faturamento Total (pós-processamento):</span>
                                <span className="font-mono text-blue-600">{formatRevenue(totalRevenue)}</span>
                              </div>
                              <div className="text-xs text-muted-foreground italic mb-2">
                                * Inclui GAM (após RevShare) + AdSense (sem RevShare)
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Investimento:</span>
                                <span className="font-mono text-red-600">-{formatCurrency(totalInvestment)}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Impostos SN ({currentTaxRate}%):</span>
                                <span className="font-mono text-red-600">-{formatCurrency(calculation.taxAmount)}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Custos Op. Diários:</span>
                                <span className="font-mono text-red-600">-{formatCurrency(calculation.dailyOperationalCosts)}</span>
                              </div>
                              <div className="border-t pt-1 border-primary/20">
                                <div className="flex justify-between font-medium">
                                  <span className="text-muted-foreground">Lucro Líquido:</span>
                                  <span className="font-mono text-green-600">{formatCurrency(calculation.netProfit)}</span>
                                </div>
                              </div>
                              <div className="border-t pt-2 border-primary/20">
                                <div className="flex justify-between font-medium">
                                  <span>ROI Final:</span>
                                  <span className="font-mono text-primary">{finalRoi.toFixed(1)}%</span>
                                </div>
                                <div className="text-xs text-muted-foreground mt-1">
                                  (Lucro Líquido ÷ Investimento) × 100
                                </div>
                              </div>
                            </div>
                          );
                        })()}
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <Target className="h-4 w-4" />
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="text-2xl font-bold">
                {calculateFinalROI(summary?.totalRevenue || 0, summary?.totalInvestment || 0, currentTaxRate).toFixed(1)}%
              </div>
              <div className="flex items-center justify-between text-xs mt-1">
                <div className="flex items-center">
                  <ArrowUpRight className="mr-1 h-3 w-3 text-green-500" />
                  <span className="text-green-500">+{summary?.trendsPercentage?.roi || 0}%</span>
                </div>
                <span className="text-muted-foreground">
                  Com {currentTaxRate}% SN
                </span>
              </div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden shadow-lg border-purple-500/20 bg-gradient-to-br from-purple-500/5 via-purple-600/5 to-purple-500/10 hover:shadow-xl transition-shadow">
            <CardDecoration color="rgb(147, 51, 234)" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <CardTitle className="text-sm font-medium">🎯 Campanhas</CardTitle>
              <Users className="h-4 w-4 text-purple-500" />
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="text-2xl font-bold">{campaigns.length} Total</div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs">🟢 {campaigns.filter(c => c.status === 'active').length} Ativas</span>
                <span className="text-xs">🟡 {campaigns.filter(c => c.status === 'paused').length} Pausadas</span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs">👤 {campaigns.filter(c => c.statusSource === 'user').length} Controladas</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Top 5 Campanhas - Versão Compacta */}
        <Card className="shadow-lg transition-all duration-300 bg-gradient-to-br from-background to-muted/30 hover:shadow-xl transition-shadow">
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-lg">
                  🏆 Top 5 Campanhas por Performance
                </CardTitle>
                <CardDescription className="mt-1 text-sm">
                  Maiores revenues por UTM campaign • {campaigns.filter(c => c.revenue && c.revenue > 0).length} campanhas ativas
                </CardDescription>
              </div>
              <div className="text-right text-xs text-muted-foreground">
                <div className="bg-gradient-to-r from-green-500/20 to-emerald-500/20 px-2 py-1 rounded border border-green-200">
                  <div className="font-bold text-green-600 text-sm">
                    {formatRevenue(campaigns.reduce((sum, c) => sum + (c.revenue || 0), 0))}
                  </div>
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {campaigns
                .filter(campaign => {
                  // Apply status filters
                  
                  // Only show campaigns with revenue > 0
                  return campaign.revenue && campaign.revenue > 0;
                })
                .sort((a, b) => (b.revenue || 0) - (a.revenue || 0))
                .slice(0, 5)
                .map((campaign, index) => {
                  const project = projects.find(p => p.id === campaign.projectId);
                  const medalEmoji = index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : `${index + 1}°`;
                  
                  return (
                    <div 
                      key={campaign.id} 
                      className="group flex items-center gap-3 p-3 rounded-lg border bg-gradient-to-r from-slate-50 to-gray-50 border-slate-200 hover:border-slate-300 hover:shadow-md transition-all duration-200 cursor-pointer"
                      onClick={() => navigate(`/dashboard/campaign/${campaign.utmCampaignValue || campaign.id}`)}
                    >
                      {/* Rank */}
                      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-r from-slate-400 to-gray-400 text-white text-sm font-bold flex-shrink-0">
                        {medalEmoji}
                      </div>
                      
                      {/* Campaign info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-medium text-slate-900 truncate text-sm">
                            {campaign.name.substring(0, 40)}
                            {campaign.name.length > 40 && '...'}
                          </h3>
                          <div className={`px-1.5 py-0.5 rounded text-xs ${
                            campaign.status === 'active' 
                              ? 'bg-green-100 text-green-700' 
                              : 'bg-yellow-100 text-yellow-700'
                          }`}>
                            {campaign.status === 'active' ? '🟢' : '🟡'}
                            {campaign.statusSource === 'user' && ' 👤'}
                          </div>
                        </div>
                        
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span>📂 {project?.domain || project?.name || 'N/A'}</span>
                          <span>•</span>
                          <span className="font-mono">ID: {campaign.utmCampaignValue || campaign.id}</span>
                        </div>
                      </div>
                      
                      {/* Performance metrics - Compact */}
                      <div className="text-right flex-shrink-0">
                        <RevenueTooltip
                          netRevenue={campaign.revenue || 0}
                          revsharePercentage={project?.revshare || 0.1}
                          projectType={project?.project_type}
                          showInfo={false}
                        >
                          <div className="text-lg font-bold text-green-600">
                            {formatRevenue(campaign.revenue || 0)}
                          </div>
                        </RevenueTooltip>
                        <div className="text-xs text-muted-foreground">
                          💸 {formatCurrency(campaign.investment || 0)} • 📈 {Math.round(calculateROAS(campaign.revenue || 0, campaign.investment || 0))}%
                        </div>
                      </div>
                    </div>
                  );
                })}
              
              {/* Empty state */}
              {campaigns.filter(campaign => {
                return campaign.revenue && campaign.revenue > 0;
              }).length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  <Target className="h-12 w-12 mx-auto mb-3 opacity-50" />
                  <h3 className="font-medium mb-1">Nenhuma campanha encontrada</h3>
                  <p className="text-sm">
                    {false 
                      ? 'Tente alterar o filtro de status' 
                      : 'Verifique as campanhas com dados de GAM'
                    }
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Projects Table */}
        <Card className="shadow-lg transition-all duration-300 bg-gradient-to-br from-background to-muted/30 hover:shadow-xl transition-shadow">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5 text-primary" />
                📂 Resumo por Projeto
              </CardTitle>
              <CardDescription>
                Performance detalhada - Gasto vs Revenue por domínio
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Link to="/settings/campaigns">
                <Button variant="outline" size="sm" className="hover:translate-y-1 transition-transform">
                  🤖 Ver Campanhas
                </Button>
              </Link>
              <Link to="/settings/projects">
                <Button variant="outline" size="sm" className="hover:translate-y-1 transition-transform">
                  📂 Ver Projetos
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-3 font-medium">Projeto (Domínio)</th>
                    <th className="text-left p-3 font-medium">Gasto</th>
                    <th className="text-left p-3 font-medium">Revenue</th>
                    <th className="text-left p-3 font-medium">ROAS</th>
                    <th className="text-left p-3 font-medium">
                      <div className="flex items-center gap-1">
                        Lucro Líquido
                      </div>
                    </th>
                    <th className="text-left p-3 font-medium">Campanhas</th>
                    <th className="text-left p-3 font-medium">Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {projects
                    .sort((a, b) => (b.revenue || 0) - (a.revenue || 0))
                    .map((project, index) => (
                    <tr key={index} className="border-b hover:bg-muted/50 transition-colors cursor-pointer" onClick={() => navigate(`/dashboard/project/${project.id}`)}>
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div className="h-12 w-12 bg-gradient-to-br from-primary to-purple-600 rounded-lg flex items-center justify-center text-white font-bold shadow-lg animate-float">
                            📂
                          </div>
                          <div>
                            <p className="font-medium text-base">{project.domain}</p>
                            <p className="text-sm text-muted-foreground">{project.name}</p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <div className="text-lg font-bold">
                          {formatCurrency(project.investment)}
                        </div>
                        <div className="text-xs text-muted-foreground">Gasto total</div>
                      </td>
                      <td className="p-4">
                        <RevenueTooltip
                          netRevenue={project.revenue}
                          revsharePercentage={project.revshare || 0.1}
                          projectType={project.project_type}
                          showInfo={false}
                        >
                          <div className="text-lg font-bold text-green-600">
                            {formatRevenue(project.revenue)}
                          </div>
                        </RevenueTooltip>
                        <div className="text-xs text-muted-foreground">Revenue UTM</div>
                      </td>
                      <td className="p-4">
                        <div className={`text-lg font-bold px-3 py-1 rounded-lg border ${getROIColor(calculateROAS(project.revenue, project.investment))}`}>
                          {Math.round(calculateROAS(project.revenue, project.investment))}%
                        </div>
                        <div className="flex items-center gap-1 mt-1">
                          {getTrendIcon(project.trend)}
                          <span className="text-xs">{getTrendText(project.trend)}</span>
                        </div>
                      </td>
                      <td className="p-4">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div className="cursor-help">
                                <div className={`text-lg font-bold flex items-center gap-1 ${(() => {
                                  const netProfit = project.netProfit || 0;
                                  if (netProfit > 0) return "text-green-600";
                                  if (netProfit < 0) return "text-red-600";
                                  return "text-gray-600";
                                })()}`}>
                                  {formatCurrency(project.netProfit || 0)}
                                  <Info className="h-3 w-3 opacity-60 hover:opacity-100 transition-opacity" />
                                </div>
                                <div className="text-xs text-muted-foreground">
                                  {project.costs_division ? '📊 Div. custos' : '🚫 Sem div.'}
                                </div>
                              </div>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-xs p-4">
                              <div className="space-y-2 text-sm">
                                <div className="font-medium text-primary mb-2">Cálculo do Lucro Líquido</div>
                                {(() => {
                                  // Simular o mesmo cálculo feito no backend
                                  const revenue = project.revenue || 0;
                                  const investment = project.investment || 0;
                                  const taxRate = 0.081; // 8.1%
                                  const taxAmount = revenue * taxRate;
                                  const netProfit = project.netProfit || 0;

                                  // Estimar custo operacional (será 0 se não participa da divisão)
                                  const estimatedOperationalCost = project.costs_division ? (netProfit - (revenue - investment - taxAmount)) * -1 : 0;

                                  return (
                                    <div className="space-y-1">
                                      <div className="flex justify-between">
                                        <span className="text-muted-foreground">
                                          {project.project_type === 'ADSENSE' ? 'Revenue Total:' : 'Revenue (após RevShare):'}
                                        </span>
                                        <span className="font-medium text-green-600">{formatRevenue(revenue)}</span>
                                      </div>
                                      {project.project_type === 'ADSENSE' && (
                                        <div className="text-xs text-muted-foreground italic mb-2">
                                          * Projeto AdSense: Revenue sem desconto de RevShare
                                        </div>
                                      )}
                                      <div className="flex justify-between">
                                        <span className="text-muted-foreground">- Investimento:</span>
                                        <span className="font-medium text-red-600">-{formatCurrency(investment)}</span>
                                      </div>
                                      <div className="flex justify-between">
                                        <span className="text-muted-foreground">- Impostos (8,1%):</span>
                                        <span className="font-medium text-orange-600">-{formatCurrency(taxAmount)}</span>
                                      </div>
                                      {project.costs_division && estimatedOperationalCost > 0 && (
                                        <div className="flex justify-between">
                                          <span className="text-muted-foreground">- Custo Operacional:</span>
                                          <span className="font-medium text-purple-600">-{formatCurrency(estimatedOperationalCost)}</span>
                                        </div>
                                      )}
                                      <div className="border-t pt-1 mt-2">
                                        <div className="flex justify-between font-bold">
                                          <span>Lucro Líquido:</span>
                                          <span className={(() => {
                                            if (netProfit > 0) return "text-green-600";
                                            if (netProfit < 0) return "text-red-600";
                                            return "text-gray-600";
                                          })()}>{formatCurrency(netProfit)}</span>
                                        </div>
                                      </div>
                                      {!project.costs_division && (
                                        <div className="text-xs text-muted-foreground mt-2 italic">
                                          * Este projeto não participa da divisão de custos operacionais
                                        </div>
                                      )}
                                    </div>
                                  );
                                })()}
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </td>
                      <td className="p-4">
                        <div className="space-y-1">
                          <div className="font-medium">
                            {campaigns.filter(c => c.projectId === project.id).length} total
                          </div>
                          <div className="flex items-center gap-1 text-xs">
                            {(() => {
                              const projectCampaigns = campaigns.filter(c => c.projectId === project.id);
                              const colors = {
                                green: projectCampaigns.filter(c => {
                                  const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                                  return getROASColorCategory(roasExcess) === "green";
                                }).length,
                                yellow: projectCampaigns.filter(c => {
                                  const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                                  return getROASColorCategory(roasExcess) === "yellow";
                                }).length,
                                orange: projectCampaigns.filter(c => {
                                  const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                                  return getROASColorCategory(roasExcess) === "orange";
                                }).length,
                                red: projectCampaigns.filter(c => {
                                  const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                                  return getROASColorCategory(roasExcess) === "red";
                                }).length
                              };

                              return (
                                <>
                                  {colors.green > 0 && <span className="text-green-600">🟢{colors.green}</span>}
                                  {colors.yellow > 0 && <span className="text-yellow-600">🟡{colors.yellow}</span>}
                                  {colors.orange > 0 && <span className="text-orange-600">🟠{colors.orange}</span>}
                                  {colors.red > 0 && <span className="text-red-600">🔴{colors.red}</span>}
                                  {projectCampaigns.length === 0 && <span className="text-gray-400">-</span>}
                                </>
                              );
                            })()}
                          </div>
                        </div>
                      </td>
                      <td className="p-4" onClick={(e) => e.stopPropagation()}>
                        <div className="flex gap-2">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="sm" className="text-xs">
                                ⚙️ Menu
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent>
                              <DropdownMenuItem onClick={() => navigate(`/dashboard/project/${project.id}`)}>
                                <Settings className="h-4 w-4 mr-2" />
                                Dashboard
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => navigate(`/settings/campaigns?project=${project.id}`)}>
                                <Target className="h-4 w-4 mr-2" />
                                Campanhas
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Integration Status and Settings */}
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2 shadow-lg transition-all duration-300 bg-gradient-to-br from-background to-muted/30 hover:shadow-xl transition-shadow">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-orange-500" />
                Status das Integrações
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-3">
                {integrationStatus.map((integration, index) => (
                  <div key={index} className="flex items-center justify-between p-4 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors hover:translate-y-1 transition-transform">
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

          {/* Exchange Rate Manager - Discreto no lado direito */}
          <div className="lg:col-span-1">
            <FinalExchangeRateManager />
          </div>
        </div>
      </div>
    </Layout>
  );
}