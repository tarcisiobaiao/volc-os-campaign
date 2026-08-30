import React, { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Badge, StatusBadge, ROASBadge, PerformanceBadge } from "@/components/ui/badge";
import { VariacaoDoPeriodo } from "@/components/dashboard/VariacaoDoPeriodo";
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
  Settings,
  FolderOpen,
  Calendar,
  Medal,
  Circle,
  Award,
  Trophy,
  Coins,
  FileText,
  MoreVertical
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
import { MonthlyExchangeRates } from "@/components/currency/MonthlyExchangeRates";
import { currencyConversionService } from "@/services/currencyConversionService";
import { taxHistoryService } from "@/services/taxHistoryService";
// import { SiteAnalysis } from "@/components/dashboard/SiteAnalysis";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { formatBrlCurrency, formatCostCurrency, getCachedExchangeRate, preloadExchangeRate } from "@/utils/currencyUtils";
import { calculateROAS, getROASColorStyles, getROASBadgeColor, getROASColorCategory } from "@/utils/roasCalculations";
import { useUserProfile } from "@/hooks/useUserProfile";
import { RevenueTooltip } from "@/components/ui/revenue-tooltip";
import { useAuth } from "@/contexts/AuthContext";
import { supabase } from "@/lib/supabase";
import { useUserFilters } from "@/hooks/useUserFilters";
import { CampaignHighlights } from "@/components/dashboard/CampaignHighlights";
import { AnimatedGradient } from "@/components/ui/animated-gradient";

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
  const { userProfile } = useAuth();
  const [userProjectIds, setUserProjectIds] = useState<number[]>([]);
  const [isMobile, setIsMobile] = useState(false);

  // Detectar mobile viewport
  React.useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);
  
  // Fetch user projects for OPERATOR users
  React.useEffect(() => {
    const fetchUserProjects = async () => {
      if (userProfile?.role === 'OPERATOR' && userProfile.id) {
        const { data, error } = await supabase
          .from('user_projects')
          .select('project_id')
          .eq('user_id', userProfile.id);

        if (!error && data) {
          setUserProjectIds(data.map(up => up.project_id));
        }
      }
    };
    fetchUserProjects();
  }, [userProfile]);

  // Initialize with current server date (São Paulo timezone) and preload exchange rate
  React.useEffect(() => {
    const initialize = async () => {
      try{
        // Initialize date
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);

        // Preload exchange rate for currency conversion
        const rate = await preloadExchangeRate();
        setExchangeRate(rate);

        // Load current tax rate
        const currentMonth = serverDate.substring(0, 7); // YYYY-MM format
        const taxRate = await taxHistoryService.getCurrentTaxRate(currentMonth);
        setCurrentTaxRate(taxRate);

        // AUTO-TRIGGER: Check and copy operational costs for new month (day 1)
        try {
          const dataCopied = await operationalCostsService.checkAndCopyMonthData(currentMonth);
          if (dataCopied) {
          }
        } catch (error) {
          console.error('⚠️ Error auto-copying operational costs:', error);
        }

        // AUTO-TRIGGER: Check and create tax record for new month (day 1)
        try {
          const taxCreated = await taxHistoryService.checkAndCreateNextMonthTax();
          if (taxCreated) {
          }
        } catch (error) {
          console.error('⚠️ Error auto-creating tax record:', error);
        }
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
  
  // Get user filters for operators
  const { allowedProjectIds, allowedCampaignIds, isLoading: filtersLoading } = useUserFilters();

  // Use filtered data based on current selections - sempre mostra todos os projetos
  // TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom' para usar a mesma lógica
  // IMPORTANTE: Só passar os filtros se tiverem valores (não passar arrays vazios)
  // useMemo para evitar re-renders desnecessários quando a referência dos arrays muda
  const filters = React.useMemo(() => ({
    date: selectedDate,
    projectId: 'all', // Sempre todos os projetos no dashboard geral
    period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod,
    ...(allowedProjectIds.length > 0 && { userProjectIds: allowedProjectIds }),
    ...(allowedCampaignIds.length > 0 && { userCampaignIds: allowedCampaignIds })
  }), [selectedDate, selectedPeriod, allowedProjectIds, allowedCampaignIds]);

  // Debug: Log current filters for monitoring
  React.useEffect(() => {
    console.log({
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
      // Clear cache and force fresh data
      supabaseDataService.clearServerDateCache();
      supabaseDataService.debugDataForDate(selectedDate);
    }
  }, [selectedPeriod, selectedDate]);
  
  // Force refresh data when period changes
  React.useEffect(() => {
    if (selectedPeriod === 'today' || selectedPeriod === 'yesterday') {
      setTimeout(() => {
        refresh(filters);
      }, 500);
    }
  }, [selectedPeriod, selectedDate]);

  // Load tax rate and daily operational costs based on selected date
  React.useEffect(() => {
    const loadFinancialData = async () => {
      try {
        // Use the month from the selected date being viewed
        const monthToUse = selectedDate ? selectedDate.substring(0, 7) : new Date().toISOString().slice(0, 7); // YYYY-MM

        // Load tax rate for the selected month
        const taxRate = await taxHistoryService.getCurrentTaxRate(monthToUse);
        setCurrentTaxRate(taxRate);

        // Load daily operational costs for the selected month
        const dailyCosts = await operationalCostsService.getDailyActiveCosts(monthToUse);
        setDailyOperationalCosts(dailyCosts);
      } catch (error) {
        console.error('Error loading financial data:', error);
        setCurrentTaxRate(8.1); // Fallback
        setDailyOperationalCosts(0);
      }
    };

    if (selectedDate) {
      loadFinancialData();
    }
  }, [selectedDate]); // Re-calculate when date changes
  
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
  console.log({
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
        const serverDateObj = new Date(serverDate + 'T00:00:00-03:00'); // São Paulo timezone
        const yesterdayObj = new Date(serverDateObj);
        yesterdayObj.setDate(yesterdayObj.getDate() - 1);
        const yesterdayStr = yesterdayObj.toISOString().split('T')[0];
        setSelectedDate(yesterdayStr);
        console.log({
          serverDate,
          serverDateObj: serverDateObj.toISOString(),
          yesterdayObj: yesterdayObj.toISOString(),
          finalYesterdayString: yesterdayStr
        });

        // TRATAMENTO COMO CUSTOM DATE: Force immediate refresh for yesterday data usando 'custom' period
        setTimeout(() => {
          const yesterdayFilters = { ...filters, date: yesterdayStr, period: 'custom' };
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
          refresh(yesterdayFilters);
        }, 100);
      }
    }
  };

  const handleDateChange = (date: string) => {
    setSelectedDate(date);
    // Force a refresh when date changes to ensure data is up to date
    // TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom'
    const newFilters = {
      ...filters,
      date,
      period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod
    };
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

    console.log({
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

  // Using centralized ROAS color styling
  const getROIColor = (roasExcess: number) => {
    return getROASColorStyles(roasExcess);
  };

  // Using centralized ROAS badge color
  const getROIBadgeColor = (roasExcess: number) => {
    return getROASBadgeColor(roasExcess);
  };

  const handleRefresh = async () => {
    
    // Check if we need to force revenue conversion
    try {
      await currencyConversionService.updateDatabaseConversions();
    } catch (error) {
      console.warn('⚠️ Revenue conversion failed:', error);
    }
    
    refresh(filters);
  };

  const handleUpdateGAM = async () => {
    setWebhookStatus('loading');

    try {
      const response = await fetch('https://fluxos.agenciavolc.com.br/webhook/e8c5cc2a-4154-4527-a5e3-f2cf84fae469', {
        method: 'GET'
      });
      
      if (response.ok) {
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
    setWebhookStatus('loading');

    try {
      const response = await fetch('https://fluxos.agenciavolc.com.br/webhook/43dd1321-07a0-42f0-a119-65c531ef73fc', {
        method: 'GET'
      });

      if (response.ok) {
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
      <div className={`${isMobile ? 'p-4' : 'p-6'} space-y-6 md:space-y-8 max-w-7xl mx-auto`}>
        {/* Header with User and Controls */}
        <div className="space-y-4 transition-volc duration-200">
          {/* Title Section */}
          <div className="flex items-start justify-between gap-4 reveal" style={{ ['--i' as any]: 0 }}>
            <div className="flex-1 min-w-0">
              <div className="kicker mb-2 flex items-center gap-2">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
                Visão geral · Tempo real
              </div>
              <h1 className={`font-display font-bold tracking-tight leading-[1.05] ${isMobile ? 'text-[1.7rem]' : 'text-4xl'}`}>
                Dashboard <span className="text-foreground">Geral</span>
              </h1>
              <div className="mt-3 aurora-rule w-16" />
              <p className={`mt-3 text-muted-foreground ${isMobile ? 'text-sm' : ''}`}>
                Todas as campanhas e projetos
                {selectedPeriod === 'custom' && selectedDate && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} font-medium text-foreground`}>
                    • {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}
                  </span>
                )}
                {selectedPeriod !== 'custom' && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} font-medium text-foreground`}>
                    • {selectedPeriod === 'today' ? 'Hoje' : selectedPeriod === 'yesterday' ? 'Ontem' : 'Data personalizada'}
                  </span>
                )}
              </p>
              {isMobile && (
                <div className="mt-3 flex items-center gap-2 px-3 py-1.5 rounded-full bg-card border border-border shadow-card w-fit">
                  <span className="h-5 w-5 rounded-md bg-primary/10 text-primary flex items-center justify-center">
                    <User className="h-3 w-3" />
                  </span>
                  <span className="text-sm font-medium">{getUserFirstName()}</span>
                </div>
              )}
            </div>
            {!isMobile && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-card border border-border shadow-card flex-shrink-0">
                <span className="h-6 w-6 rounded-md bg-primary/10 text-primary flex items-center justify-center">
                  <User className="h-3.5 w-3.5" />
                </span>
                <span className="text-sm font-medium">{getUserFirstName()}</span>
              </div>
            )}
          </div>
          
          {/* Filters and Actions Section */}
          {/* Mobile: Controles em stack vertical */}
          {isMobile ? (
            <div className="flex flex-col gap-3 w-full">
              <SimpleDateFilter
                selectedPeriod={selectedPeriod}
                selectedDate={selectedDate}
                onPeriodChange={handlePeriodChange}
                onDateChange={handleDateChange}
              />
              {selectedPeriod === 'custom' && selectedDate && (
                <div className="text-xs text-muted-foreground px-2 flex items-center gap-1 flex-wrap">
                    <span className="flex items-center gap-1">
                      <Calendar className="h-4 w-4" />
                      {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}
                    </span>
                  {!loading && campaigns.length === 0 && (
                    <span className="text-warning flex items-center gap-1"><AlertTriangle className="h-3 w-3" /> Sem dados</span>
                  )}
                  {!loading && campaigns.length > 0 && (
                    <span className="text-success flex items-center gap-1 tabular"><CheckCircle className="h-3 w-3" /> {campaigns.length}</span>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 gap-2">
                <Button onClick={handleRefresh} variant="outline" size="sm" className="h-10">
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Atualizar
                </Button>

                <Button
                  onClick={handleUpdateGAM}
                  variant="default"
                  size="sm"
                  disabled={webhookStatus === 'loading'}
                  className="h-10"
                >
                  <RefreshCw className={`h-4 w-4 mr-1 ${webhookStatus === 'loading' ? 'animate-spin' : ''}`} />
                  GAM
                </Button>
              </div>

              <Button
                onClick={handleUpdateGoogleAds}
                variant="default"
                size="sm"
                disabled={webhookStatus === 'loading'}
                className="w-full h-10"
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${webhookStatus === 'loading' ? 'animate-spin' : ''}`} />
                Atualizar Google Ads
                {webhookStatus === 'success' && (
                  <CheckCircle className="h-4 w-4 ml-2 text-success" />
                )}
                {webhookStatus === 'error' && (
                  <X className="h-4 w-4 ml-2 text-destructive" />
                )}
              </Button>

              <DataStatus
                loading={loading}
                error={error}
                lastUpdate={lastUpdate}
                showDetails={false}
              />
            </div>
          ) : (
            /* Desktop: Layout horizontal com flex-wrap */
            <div className="flex items-center gap-3 flex-wrap flex-shrink-0">
              <div className="flex flex-col gap-1">
                <SimpleDateFilter
                  selectedPeriod={selectedPeriod}
                  selectedDate={selectedDate}
                  onPeriodChange={handlePeriodChange}
                  onDateChange={handleDateChange}
                />
                {selectedPeriod === 'custom' && selectedDate && (
                  <div className="text-xs text-muted-foreground px-2 flex items-center gap-1 flex-wrap">
                    <span className="flex items-center gap-1">
                      <Calendar className="h-4 w-4" />
                      Consultando data: {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}
                    </span>
                    {!loading && campaigns.length === 0 && (
                      <span className="text-warning flex items-center gap-1"><AlertTriangle className="h-3 w-3" /> Sem dados</span>
                    )}
                    {!loading && campaigns.length > 0 && (
                      <span className="text-success flex items-center gap-1 tabular"><CheckCircle className="h-3 w-3" /> {campaigns.length} campanhas</span>
                    )}
                  </div>
                )}
              </div>

              <Button onClick={handleRefresh} variant="outline" size="sm" className="flex-shrink-0">
                <RefreshCw className="h-4 w-4 mr-2" />
                Atualizar
              </Button>

              <div className="flex items-center gap-2 flex-wrap">
                <Button
                  onClick={handleUpdateGAM}
                  variant="default"
                  size="sm"
                  disabled={webhookStatus === 'loading'}
                  className="flex-shrink-0"
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${webhookStatus === 'loading' ? 'animate-spin' : ''}`} />
                  Atualizar GAM
                </Button>

                <Button
                  onClick={handleUpdateGoogleAds}
                  variant="default"
                  size="sm"
                  disabled={webhookStatus === 'loading'}
                  className="flex-shrink-0"
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${webhookStatus === 'loading' ? 'animate-spin' : ''}`} />
                  Atualizar Google Ads
                </Button>

                {webhookStatus === 'success' && (
                  <CheckCircle className="h-4 w-4 text-success flex-shrink-0" />
                )}

                {webhookStatus === 'error' && (
                  <X className="h-4 w-4 text-destructive flex-shrink-0" />
                )}
              </div>

              <DataStatus
                loading={loading}
                error={error}
                lastUpdate={lastUpdate}
                showDetails={true}
              />
            </div>
          )}
        </div>


        {/* Campanhas Controladas pelo Usuário - Destaque */}
        {campaigns.filter(c => c.statusSource === 'user').length > 0 && (
          <Card className="relative overflow-hidden shadow-card border-info/30 reveal" style={{ ['--i' as any]: 7 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <span className="rounded-md bg-info/10 text-info p-1.5"><User className="h-4 w-4" /></span>
                Campanhas Controladas Manualmente
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {campaigns
                  .filter(c => c.statusSource === 'user')
                  .slice(0, 6)
                  .map((campaign, index) => (
                    <div key={index} className="flex items-center justify-between p-3 rounded-lg bg-info/5 border border-info/20 hover:bg-info/10 transition-colors">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{campaign.name}</p>
                        <p className="text-xs mt-0.5">
                          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${campaign.status === 'paused' ? 'bg-warning/12 text-warning' : 'bg-success/12 text-success'}`}>
                            <Circle className="h-2 w-2 fill-current" />
                            {campaign.status === 'paused' ? 'Pausada' : 'Ativa'}
                          </span>
                          <span className="text-muted-foreground ml-1.5">pelo usuário</span>
                        </p>
                      </div>
                      <Badge variant="outline" className="text-info border-info/30 tabular flex-shrink-0">
                        R$ {campaign.revenue?.toFixed(2) || '0.00'}
                      </Badge>
                    </div>
                  ))}
              </div>
              {campaigns.filter(c => c.statusSource === 'user').length > 6 && (
                <p className="text-center text-sm text-muted-foreground mt-3">
                  +{campaigns.filter(c => c.statusSource === 'user').length - 6} campanhas com controle manual
                </p>
              )}
            </CardContent>
          </Card>
        )}



        {/* Site Analysis - Main Chart */}
        <div className="grid gap-6 transition-volc duration-200">
          {/* <SiteAnalysis /> */}
        </div>

        {/* KPI Overview - Cards Resumo */}
        <div className="grid gap-4 md:gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 transition-volc duration-200">
          <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 1 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
            <CardDecoration color="hsl(var(--info))" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <span className="kicker">Investimento total</span>
              <span className="rounded-md bg-info/10 text-info p-1.5"><Coins className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="font-display text-3xl font-bold tabular tracking-tight">{formatCurrency(summary?.totalInvestment || 0)}</div>
              <VariacaoDoPeriodo
                className="mt-2"
                valor={summary?.trendsPercentage?.investment}
                base="vs período anterior"
              />
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 2 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
            <CardDecoration color="rgb(34, 197, 94)" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <span className="kicker">Revenue total</span>
              <span className="rounded-md bg-success/10 text-success p-1.5"><TrendingUp className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent className="relative z-10">
              <RevenueTooltip
                netRevenue={summary?.totalRevenue || 0}
                revsharePercentage={0.1}
                projectType="GAM" // Dashboard geral: mix de projetos, mas mostra como GAM para compatibilidade
              >
                <div className="font-display text-3xl font-bold tabular tracking-tight text-success">{formatRevenue(summary?.totalRevenue || 0)}</div>
              </RevenueTooltip>
              <VariacaoDoPeriodo
                className="mt-2"
                valor={summary?.trendsPercentage?.revenue}
                base="via UTM campaigns (líquido)"
              />
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 3 }}>
            <CardDecoration color="hsl(var(--info))" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <span className="kicker">ROAS geral</span>
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><BarChart3 className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="font-display text-3xl font-bold tabular tracking-tight">{summary?.generalRoas || 0}%</div>
              <VariacaoDoPeriodo className="mt-2" valor={summary?.trendsPercentage?.roas} />
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 4 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
            <CardDecoration color="hsl(var(--success))" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <div className="flex items-center gap-2">
                <span className="kicker">Lucro líquido</span>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="h-3 w-3 text-success opacity-60 hover:opacity-100 cursor-help transition-opacity" />
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs p-4">
                      <div className="space-y-2 text-sm">
                        <div className="font-medium text-success mb-2">Cálculo do Lucro Líquido</div>
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
                                <span className="font-mono text-primary">{formatRevenue(calculation.netRevenue)}</span>
                              </div>
                              <div className="text-xs text-muted-foreground italic mb-2">
                                * Inclui GAM (após RevShare) + AdSense (sem RevShare)
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Investimento:</span>
                                <span className="font-mono text-destructive">-{formatCurrency(totalInvestment)}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Impostos SN ({currentTaxRate}%):</span>
                                <span className="font-mono text-destructive">-{formatCurrency(calculation.taxAmount)}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Custos Op. Diários:</span>
                                <span className="font-mono text-destructive">-{formatCurrency(calculation.dailyOperationalCosts)}</span>
                              </div>
                              <div className="border-t pt-1 border-success/30">
                                <div className="flex justify-between font-medium">
                                  <span>Lucro Líquido:</span>
                                  <span className="font-mono text-success">{formatCurrency(calculation.netProfit)}</span>
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
              <span className="rounded-md bg-success/10 text-success p-1.5"><DollarSign className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="font-display text-3xl font-bold tabular tracking-tight">
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
              <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 text-xs mt-1">
                <VariacaoDoPeriodo valor={summary?.trendsPercentage?.profit} />
                <span className="text-muted-foreground">
                  {(() => {
                    const revenueShareData = calculateRealRevenueShare();
                    return `Após ${(revenueShareData.percentage * 100).toFixed(1)}% RS e ${currentTaxRate}% SN`;
                  })()}
                </span>
              </div>
            </CardContent>
          </Card>

          <Card style={{ ['--i' as any]: 5 }} className={`relative overflow-hidden group reveal hover-lift ${
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
                <span className="kicker">ROI final</span>
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
                                <span className="font-mono text-primary">{formatRevenue(totalRevenue)}</span>
                              </div>
                              <div className="text-xs text-muted-foreground italic mb-2">
                                * Inclui GAM (após RevShare) + AdSense (sem RevShare)
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Investimento:</span>
                                <span className="font-mono text-destructive">-{formatCurrency(totalInvestment)}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Impostos SN ({currentTaxRate}%):</span>
                                <span className="font-mono text-destructive">-{formatCurrency(calculation.taxAmount)}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-muted-foreground">Custos Op. Diários:</span>
                                <span className="font-mono text-destructive">-{formatCurrency(calculation.dailyOperationalCosts)}</span>
                              </div>
                              <div className="border-t pt-1 border-primary/20">
                                <div className="flex justify-between font-medium">
                                  <span className="text-muted-foreground">Lucro Líquido:</span>
                                  <span className="font-mono text-success">{formatCurrency(calculation.netProfit)}</span>
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
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><Target className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="font-display text-3xl font-bold tabular tracking-tight">
                {calculateFinalROI(summary?.totalRevenue || 0, summary?.totalInvestment || 0, currentTaxRate).toFixed(1)}%
              </div>
              <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 text-xs mt-1">
                <VariacaoDoPeriodo valor={summary?.trendsPercentage?.roi} />
                <span className="text-muted-foreground">
                  Com {currentTaxRate}% SN
                </span>
              </div>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 6 }}>
            <CardDecoration color="rgb(147, 51, 234)" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <span className="kicker">Campanhas</span>
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><Users className="h-4 w-4" /></span>
            </CardHeader>
            <CardContent className="relative z-10">
              <div className="font-display text-3xl font-bold tabular tracking-tight">{campaigns.length} <span className="text-base font-medium text-muted-foreground">Total</span></div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs flex items-center gap-1">
                  <Circle className="h-2 w-2 fill-success text-success" />
                  {campaigns.filter(c => c.status === 'active').length} Ativas
                </span>
                <span className="text-xs flex items-center gap-1">
                  <Circle className="h-2 w-2 fill-warning text-warning" />
                  {campaigns.filter(c => c.status === 'paused').length} Pausadas
                </span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs flex items-center gap-1">
                  <User className="h-3 w-3" />
                  {campaigns.filter(c => c.statusSource === 'user').length} Controladas
                </span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Campanhas Destacadas - Rotação Automática */}
        <CampaignHighlights />

        {/* Top 5 Campanhas - Versão Compacta */}
        <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 8 }}>
          <CardHeader className={`pb-4 ${isMobile ? 'p-4' : ''}`}>
            <div className={`flex ${isMobile ? 'flex-col' : 'items-center justify-between'} gap-3`}>
              <div>
                <CardTitle className={`flex items-center gap-2 ${isMobile ? 'text-base' : 'text-lg'}`}>
                  <span className="rounded-md bg-warning/10 text-warning p-1.5"><Trophy className="h-4 w-4" /></span>
                  Top 5 Campanhas por Performance
                </CardTitle>
                <CardDescription className={`mt-1 ${isMobile ? 'text-xs' : 'text-sm'}`}>
                  Maiores revenues por UTM campaign • {campaigns.filter(c => c.revenue && c.revenue > 0).length} campanhas ativas
                </CardDescription>
              </div>
              <div className={`text-right ${isMobile ? 'text-xs w-full' : 'text-xs'} text-muted-foreground`}>
                <div className={`bg-success/10 border border-success/20 ${isMobile ? 'px-3 py-2' : 'px-2 py-1'} rounded ${isMobile ? 'w-full' : ''}`}>
                  <div className={`font-display font-bold tabular text-success ${isMobile ? 'text-base' : 'text-sm'}`}>
                    {formatRevenue(campaigns.reduce((sum, c) => sum + (c.revenue || 0), 0))}
                  </div>
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className={isMobile ? 'p-4' : ''}>
            <div className="space-y-2 md:space-y-3">
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
                  const MedalIcon = index === 0 ? Trophy : index === 1 ? Award : index === 2 ? Medal : Circle;
                  
                  return (
                    <Link
                      key={campaign.id}
                      to={`/dashboard/campaign/${campaign.utmCampaignValue || campaign.id}`}
                      className={`group flex ${isMobile ? 'flex-col' : 'items-center'} gap-3 ${isMobile ? 'p-4' : 'p-3'} rounded-lg border bg-card border-border hover:border-primary/30 hover:shadow-card transition-volc duration-200 cursor-pointer touch-target no-underline text-inherit`}
                    >
                      {/* Rank e Header */}
                      <div className={`flex ${isMobile ? 'items-start' : 'items-center'} gap-3 w-full`}>
                        {/* Rank */}
                        <div className={`flex items-center justify-center ${isMobile ? 'w-10 h-10' : 'w-8 h-8'} rounded-md bg-primary/10 text-primary flex-shrink-0`}>
                          {index < 3 ? (
                            <MedalIcon className={`${isMobile ? 'h-5 w-5' : 'h-4 w-4'}`} />
                          ) : (
                            <span className={`${isMobile ? 'text-base' : 'text-sm'} font-bold`}>{index + 1}°</span>
                          )}
                        </div>
                        
                        {/* Campaign info */}
                        <div className="flex-1 min-w-0">
                          <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-2 mb-1`}>
                            <h3 className={`font-medium text-foreground truncate ${isMobile ? 'text-base' : 'text-sm'}`}>
                              {campaign.name.substring(0, isMobile ? 50 : 40)}
                              {campaign.name.length > (isMobile ? 50 : 40) && '...'}
                            </h3>
                            <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${
                              campaign.status === 'active'
                                ? 'bg-success/12 text-success'
                                : 'bg-warning/12 text-warning'
                            }`}>
                              <Circle className="h-2 w-2 fill-current" />
                              {campaign.statusSource === 'user' && <User className="h-3 w-3 ml-1" />}
                            </div>
                          </div>
                          
                          <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-2 ${isMobile ? 'text-xs' : 'text-xs'} text-muted-foreground`}>
                            <span className="flex items-center gap-1">
                              <FolderOpen className="h-3 w-3" />
                              {project?.domain || project?.name || 'N/A'}
                            </span>
                            {!isMobile && <span>•</span>}
                            <span className="font-mono">ID: {campaign.utmCampaignValue || campaign.id}</span>
                          </div>
                        </div>
                      </div>
                      
                      {/* Performance metrics - Mobile: full width */}
                      <div className={`${isMobile ? 'w-full border-t pt-3 mt-2' : 'text-right flex-shrink-0'}`}>
                        <RevenueTooltip
                          netRevenue={campaign.revenue || 0}
                          revsharePercentage={project?.revshare || 0.1}
                          projectType={project?.project_type}
                          showInfo={false}
                        >
                          <div className={`${isMobile ? 'text-xl' : 'text-lg'} font-display font-bold tabular text-success`}>
                            {formatRevenue(campaign.revenue || 0)}
                          </div>
                        </RevenueTooltip>
                        <div className={`${isMobile ? 'text-sm flex flex-col gap-1 mt-2' : 'text-xs'} text-muted-foreground`}>
                          <span className="flex items-center gap-1 tabular"><Coins className="h-3 w-3" /> {formatCurrency(campaign.investment || 0)}</span>
                          <span className="flex items-center gap-1 tabular">
                            <TrendingUp className="h-3 w-3" />
                            {Math.round(calculateROAS(campaign.revenue || 0, campaign.investment || 0))}%
                          </span>
                          {campaign.commission && campaign.commission > 0 && (
                            <div className={`${isMobile ? 'text-sm' : 'text-xs'} text-primary font-medium ${isMobile ? 'mt-1' : 'mt-0.5'}`}>
                              <span className="flex items-center gap-1 tabular">
                                <Coins className="h-3 w-3" />
                                Comissão: {formatCurrency(campaign.commission)}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    </Link>
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
        <Card className="relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 9 }}>
          <CardHeader className={`flex ${isMobile ? 'flex-col' : 'flex-row items-center justify-between'} gap-4`}>
            <div>
              <CardTitle className={`flex items-center gap-2 ${isMobile ? 'text-lg' : ''}`}>
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><FolderOpen className="h-4 w-4" /></span>
                Resumo por Projeto
              </CardTitle>
              <CardDescription className={isMobile ? 'text-sm' : ''}>
                Performance detalhada - Gasto vs Revenue por domínio
              </CardDescription>
            </div>
            <div className={`flex ${isMobile ? 'flex-col w-full' : 'gap-2'}`}>
              <Link to="/settings/campaigns" className={isMobile ? 'w-full' : ''}>
                <Button variant="outline" size="sm" className={`${isMobile ? 'w-full' : ''} hover-lift touch-target`}>
                  <span className="flex items-center gap-2">
                    <Target className="h-4 w-4" />
                    Ver Campanhas
                  </span>
                </Button>
              </Link>
              <Link to="/settings/projects" className={isMobile ? 'w-full' : ''}>
                <Button variant="outline" size="sm" className={`${isMobile ? 'w-full mt-2' : ''} hover-lift touch-target`}>
                  <span className="flex items-center gap-2">
                    <FolderOpen className="h-4 w-4" />
                    Ver Projetos
                  </span>
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto -mx-4 md:mx-0 px-4 md:px-0">
              <table className="w-full min-w-[600px] md:min-w-0">
                <thead>
                  <tr className="border-b border-border">
                    <th className={`text-left kicker ${isMobile ? 'p-2' : 'p-3'}`}>Projeto (Domínio)</th>
                    <th className={`text-left kicker ${isMobile ? 'p-2' : 'p-3'}`}>Gasto</th>
                    <th className={`text-left kicker ${isMobile ? 'p-2' : 'p-3'}`}>Revenue</th>
                    <th className={`text-left kicker ${isMobile ? 'p-2' : 'p-3'}`}>ROAS</th>
                    <th className={`text-left kicker ${isMobile ? 'p-2' : 'p-3'}`}>
                      <div className="flex items-center gap-1">
                        Lucro Líquido
                      </div>
                    </th>
                    <th className={`text-left kicker ${isMobile ? 'p-2' : 'p-3'}`}>Campanhas</th>
                    <th className={`text-left kicker ${isMobile ? 'p-2' : 'p-3'}`}>Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {projects
                    .filter(project => {
                      // FRONTEND-ONLY FILTER: Hide projects marked as invisible
                      if (project.visible === false) {
                        return false;
                      }
                      // Filter by user projects for OPERATOR users
                      if (userProfile?.role === 'OPERATOR') {
                        return userProjectIds.includes(project.id);
                      }
                      return true;
                    })
                    .sort((a, b) => (b.revenue || 0) - (a.revenue || 0))
                    .map((project, index) => (
                    <tr key={index} className="border-b border-border hover:bg-muted/40 transition-colors cursor-pointer" onClick={() => navigate(`/dashboard/project/${project.id}`)}>
                      <td className={isMobile ? 'p-2' : 'p-4'}>
                        <div className={`flex items-center gap-${isMobile ? '2' : '3'}`}>
                          <div className={`${isMobile ? 'h-8 w-8 text-xs' : 'h-12 w-12'} bg-primary/10 text-primary rounded-md flex items-center justify-center font-bold`}>
                            <FolderOpen className="h-6 w-6" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className={`font-medium ${isMobile ? 'text-sm truncate' : 'text-base'}`}>{project.domain}</p>
                            <p className={`${isMobile ? 'text-xs' : 'text-sm'} text-muted-foreground truncate`}>{project.name}</p>
                          </div>
                        </div>
                      </td>
                      <td className={isMobile ? 'p-2' : 'p-4'}>
                        <div className={`${isMobile ? 'text-sm' : 'text-lg'} font-display font-bold tabular`}>
                          {formatCurrency(project.investment)}
                        </div>
                        <div className={`${isMobile ? 'text-[10px]' : 'text-xs'} text-muted-foreground`}>Gasto total</div>
                      </td>
                      <td className={isMobile ? 'p-2' : 'p-4'}>
                        <RevenueTooltip
                          netRevenue={project.revenue}
                          revsharePercentage={project.revshare || 0.1}
                          projectType={project.project_type}
                          showInfo={false}
                        >
                          <div className={`${isMobile ? 'text-sm' : 'text-lg'} font-display font-bold tabular text-success`}>
                            {formatRevenue(project.revenue)}
                          </div>
                        </RevenueTooltip>
                        <div className={`${isMobile ? 'text-[10px]' : 'text-xs'} text-muted-foreground`}>Revenue UTM</div>
                      </td>
                      <td className={isMobile ? 'p-2' : 'p-4'}>
                        <div className={`${isMobile ? 'text-sm px-2 py-0.5' : 'text-lg px-3 py-1'} font-bold tabular rounded-lg border ${getROIColor(calculateROAS(project.revenue, project.investment))}`}>
                          {Math.round(calculateROAS(project.revenue, project.investment))}%
                        </div>
                        <div className={`flex items-center gap-1 ${isMobile ? 'mt-0.5' : 'mt-1'}`}>
                          {getTrendIcon(project.trend)}
                          <span className={`${isMobile ? 'text-[10px]' : 'text-xs'}`}>{getTrendText(project.trend)}</span>
                        </div>
                      </td>
                      <td className={isMobile ? 'p-2' : 'p-4'}>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div className="cursor-help">
                                <div className={`text-lg font-display font-bold tabular flex items-center gap-1 ${(() => {
                                  const netProfit = project.netProfit || 0;
                                  if (netProfit > 0) return "text-success";
                                  if (netProfit < 0) return "text-destructive";
                                  return "text-muted-foreground";
                                })()}`}>
                                  {formatCurrency(project.netProfit || 0)}
                                  <Info className="h-3 w-3 opacity-60 hover:opacity-100 transition-opacity" />
                                </div>
                                <div className="text-xs text-muted-foreground">
                                  <span className="flex items-center gap-1">
                                    {project.costs_division ? (
                                      <>
                                        <BarChart3 className="h-3 w-3" />
                                        Div. custos
                                      </>
                                    ) : (
                                      <>
                                        <X className="h-3 w-3" />
                                        Sem div.
                                      </>
                                    )}
                                  </span>
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
                                  const taxRate = currentTaxRate / 100; // Usar taxa vigente
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
                                        <span className="font-medium tabular text-success">{formatRevenue(revenue)}</span>
                                      </div>
                                      {project.project_type === 'ADSENSE' && (
                                        <div className="text-xs text-muted-foreground italic mb-2">
                                          * Projeto AdSense: Revenue sem desconto de RevShare
                                        </div>
                                      )}
                                      <div className="flex justify-between">
                                        <span className="text-muted-foreground">- Investimento:</span>
                                        <span className="font-medium tabular text-destructive">-{formatCurrency(investment)}</span>
                                      </div>
                                      <div className="flex justify-between">
                                        <span className="text-muted-foreground">- Impostos ({currentTaxRate}%):</span>
                                        <span className="font-medium tabular text-warning">-{formatCurrency(taxAmount)}</span>
                                      </div>
                                      {project.costs_division && estimatedOperationalCost > 0 && (
                                        <div className="flex justify-between">
                                          <span className="text-muted-foreground">- Custo Operacional:</span>
                                          <span className="font-medium tabular text-primary">-{formatCurrency(estimatedOperationalCost)}</span>
                                        </div>
                                      )}
                                      <div className="border-t border-border pt-1 mt-2">
                                        <div className="flex justify-between font-bold">
                                          <span>Lucro Líquido:</span>
                                          <span className={`tabular ${(() => {
                                            if (netProfit > 0) return "text-success";
                                            if (netProfit < 0) return "text-destructive";
                                            return "text-muted-foreground";
                                          })()}`}>{formatCurrency(netProfit)}</span>
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
                          <div className="font-medium tabular">
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
                                  {colors.green > 0 && (
                                    <span className="text-success flex items-center gap-1">
                                      <Circle className="h-2 w-2 fill-success" />
                                      {colors.green}
                                    </span>
                                  )}
                                  {colors.yellow > 0 && (
                                    <span className="text-warning flex items-center gap-1">
                                      <Circle className="h-2 w-2 fill-warning" />
                                      {colors.yellow}
                                    </span>
                                  )}
                                  {colors.orange > 0 && (
                                    <span className="text-warning flex items-center gap-1">
                                      <Circle className="h-2 w-2 fill-warning" />
                                      {colors.orange}
                                    </span>
                                  )}
                                  {colors.red > 0 && (
                                    <span className="text-destructive flex items-center gap-1">
                                      <Circle className="h-2 w-2 fill-destructive" />
                                      {colors.red}
                                    </span>
                                  )}
                                  {projectCampaigns.length === 0 && <span className="text-muted-foreground">-</span>}
                                </>
                              );
                            })()}
                          </div>
                        </div>
                      </td>
                      <td className={isMobile ? 'p-2' : 'p-4'} onClick={(e) => e.stopPropagation()}>
                        <div className="flex gap-2">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size={isMobile ? 'sm' : 'sm'} className={`${isMobile ? 'text-[10px] px-2' : 'text-xs'} touch-target`}>
                                <span className="flex items-center gap-1">
                                  <Settings className="h-4 w-4" />
                                  {isMobile ? '' : 'Menu'}
                                </span>
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align={isMobile ? 'end' : 'start'}>
                              <DropdownMenuItem onClick={() => navigate(`/dashboard/project/${project.id}`)} className="touch-target">
                                <Settings className="h-4 w-4 mr-2" />
                                Dashboard
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => navigate(`/settings/campaigns?project=${project.id}`)} className="touch-target">
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
        <div className="grid gap-4 md:gap-6 grid-cols-1 lg:grid-cols-3">
          <Card className="lg:col-span-2 relative overflow-hidden shadow-card reveal" style={{ ['--i' as any]: 10 }}>
            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-warning" />
            <CardHeader>
              <CardTitle className={`flex items-center gap-2 ${isMobile ? 'text-lg' : ''}`}>
                <span className="rounded-md bg-warning/10 text-warning p-1.5"><Zap className="h-4 w-4" /></span>
                Status das Integrações
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:gap-4 grid-cols-1 md:grid-cols-3">
                {integrationStatus.map((integration, index) => (
                  <div key={index} className="flex items-center justify-between p-4 rounded-lg bg-muted/30 hover-lift transition-colors">
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
          <div className="lg:col-span-1 space-y-4">
            <FinalExchangeRateManager />
            <MonthlyExchangeRates />
          </div>
        </div>
      </div>
    </Layout>
  );
}