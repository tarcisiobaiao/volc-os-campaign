import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
// Removed Popover and Calendar - now using SimpleDateFilter
import { SimpleDateFilter } from "@/components/dashboard/SimpleDateFilter";
import { DataStatus } from "@/components/dashboard/DataStatus";
import {
  ArrowLeft,
  RefreshCw,
  Search,
  Download,
  Edit,
  Eye,
  DollarSign,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Calendar as CalendarIcon,
  Info
} from "lucide-react";
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend
} from "recharts";
import { cn } from "@/lib/utils";
import { Layout } from "@/components/layout/Layout";
import { useSupabaseData, supabaseDataService } from "@/services/supabaseDataService";
import { supabase } from "@/lib/supabase";
import { operationalCostsService } from "@/services/operationalCostsService";
import { taxHistoryService } from "@/services/taxHistoryService";
import { useCurrencyConverter } from "@/services/currencyConversionService";
import { formatBrlCurrency, formatCostCurrency, preloadExchangeRate } from "@/utils/currencyUtils";
import { getROASColorCategory, getROASColorStyles, calculateROAS } from "@/utils/roasCalculations";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { FunnelUrlsEditor } from "@/components/campaign/FunnelUrlsEditor";
import { useToast } from "@/hooks/use-toast";

// Types

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

// Campaign Card Component - Updated to match CampaignsSettings UI
const CampaignCard = ({
  campaign,
  onAction,
  formatRevenue,
  currentProject,
  selectedPeriod,
  selectedDate,
  navigate
}: {
  campaign: any;
  onAction: (action: string, campaignId: string) => void;
  formatRevenue: (brl: number) => string;
  currentProject: any;
  selectedPeriod: string;
  selectedDate: string;
  navigate: (path: string) => void;
}) => {
  // Calculate ROAS using centralized function (includes special case for revenue without investment)
  const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);

  // Use centralized ROAS color functions
  const getCampaignColorCategory = (roasExcess: number) => {
    return getROASColorCategory(roasExcess);
  };

  const getROIColor = (roasExcess: number) => {
    return getROASColorStyles(roasExcess);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <Badge variant="default" className="bg-green-500">🟢 Ativa</Badge>;
      case 'paused':
        return <Badge variant="secondary" className="bg-yellow-500">🟡 Pausada</Badge>;
      case 'stopped':
        return <Badge variant="destructive" className="bg-red-500">🔴 Parada</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  // Only show edit button for ADSENSE projects
  const isAdSenseProject = currentProject?.project_type === 'ADSENSE';

  return (
    <Card
      className="p-6 cursor-pointer hover:shadow-lg transition-shadow duration-200"
      onClick={() => navigate(`/dashboard/campaign/${campaign.utmCampaignValue || campaign.id}`)}
    >
      <CardContent className="p-0">
        <div className="space-y-4">
          {/* Campaign Header */}
          <div className="flex items-start justify-between">
            <div>
              <h3 className="font-semibold text-lg">
                {getStatusBadge(campaign.status || 'active')} {campaign.name}
              </h3>
              <p className="text-sm text-muted-foreground">
                {campaign.description || 'Campanha do projeto'}
              </p>
            </div>
            {/* Edit button only for ADSENSE projects */}
            {isAdSenseProject && (
              <Button
                size="sm"
                variant="outline"
                onClick={(e) => {
                  e.stopPropagation();
                  onAction("edit", campaign.id);
                }}
                className="flex items-center gap-2"
              >
                <Edit className="h-3 w-3" />
                Editar Funis
              </Button>
            )}
          </div>

          {/* Metrics Section */}
          <div>
            <h4 className="font-medium mb-3">📊 Performance Financeira ({
              selectedPeriod === 'today' ? 'Hoje' :
              selectedPeriod === 'yesterday' ? 'Ontem' :
              selectedPeriod === 'range' ? 'Período Selecionado' :
              `Data: ${new Date(selectedDate).toLocaleDateString('pt-BR')}`
            }):</h4>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className="text-center p-3 bg-red-50 rounded-lg">
                <p className="text-xs text-muted-foreground mb-1">Gasto</p>
                <p className="font-semibold text-red-600">
                  {new Intl.NumberFormat('pt-BR', {
                    style: 'currency',
                    currency: 'BRL'
                  }).format(campaign.investment || 0)}
                </p>
              </div>
              <div className="text-center p-3 bg-green-50 rounded-lg">
                <p className="text-xs text-muted-foreground mb-1">Revenue</p>
                <p className="font-semibold text-green-600">{formatRevenue(campaign.revenue || 0)}</p>
              </div>
              <div className={`text-center p-3 rounded-lg border ${getROIColor(roasExcess)}`}>
                <p className="text-xs text-muted-foreground mb-1">ROAS</p>
                <p className="font-semibold">{roasExcess.toFixed(1)}%</p>
              </div>
            </div>
          </div>

          {/* Campaign Details */}
          <div className="flex items-center gap-4 text-sm">
            <span>🎯 ID: {campaign.utmCampaignValue || campaign.googleAdsCampaignId || campaign.id}</span>
            <span>|</span>
            <span>📅 Criada: {campaign.startDate ? new Date(campaign.startDate).toLocaleDateString('pt-BR') : 'N/A'}</span>
            <span>|</span>
            <span>Tipo: {currentProject?.project_type || 'N/A'}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default function ProjectDashboard() {
  try {
  const { projectId } = useParams();
  const navigate = useNavigate();

  console.log('🚀 ProjectDashboard: Component rendered with projectId:', projectId);
    console.log('🚀 ProjectDashboard: typeof projectId:', typeof projectId);
    console.log('🚀 ProjectDashboard: window.location.pathname:', window.location.pathname);

  // Early return if no projectId
  if (!projectId) {
    console.log('❌ ProjectDashboard: No projectId provided');
    return (
      <Layout>
        <div className="p-6">
          <div className="text-center py-12">
            <h2 className="text-xl font-semibold mb-2">ID do projeto não fornecido</h2>
            <p className="text-sm text-muted-foreground mb-4">
              A URL deve incluir um ID de projeto válido
            </p>
            <Button onClick={() => navigate("/")} variant="outline">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Voltar ao Dashboard
            </Button>
          </div>
        </div>
      </Layout>
    );
  }
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | 'yesterday' | 'custom' | 'range'>('today');
  const [selectedDate, setSelectedDate] = useState<string>(""); // Will be set dynamically
  const [selectedEndDate, setSelectedEndDate] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentTaxRate, setCurrentTaxRate] = useState<number>(8.1);
  const [dailyOperationalCosts, setDailyOperationalCosts] = useState<number>(0);

  // State for campaigns revenue to handle async operation
  const [campaignsRevenue, setCampaignsRevenue] = useState<number>(0);
  const [projectsWithCostDivisionCount, setProjectsWithCostDivisionCount] = useState<number>(1);

  // Note: Filtro customizado agora é gerenciado pelo SimpleDateFilter component
  
  const [searchFilter, setSearchFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  // Estados para o popup de URLs do funil (AdSense)
  const [isFunnelUrlsOpen, setIsFunnelUrlsOpen] = useState(false);
  const [selectedCampaignForUrls, setSelectedCampaignForUrls] = useState<{id: string, name: string} | null>(null);

  const { toast } = useToast();

  // Initialize with current server date (São Paulo timezone) and preload exchange rate
  React.useEffect(() => {
    const initialize = async () => {
      try {
        // Initialize date
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);
        console.log('🇧🇷 Project Dashboard initialized with São Paulo date:', serverDate);

        // Preload exchange rate for currency conversion
        await preloadExchangeRate();
        console.log('💱 Exchange rate preloaded');

        // Load current tax rate
        const currentMonth = serverDate.substring(0, 7); // YYYY-MM format
        const taxRate = await taxHistoryService.getCurrentTaxRate(currentMonth);
        setCurrentTaxRate(taxRate);
        console.log('📊 Current tax rate loaded:', taxRate, '%');

        // AUTO-TRIGGER: Check and copy operational costs for new month (day 1)
        try {
          const dataCopied = await operationalCostsService.checkAndCopyMonthData(currentMonth);
          if (dataCopied) {
            console.log('✅ Operational costs auto-copied for new month:', currentMonth);
          }
        } catch (error) {
          console.error('⚠️ Error auto-copying operational costs:', error);
        }

        // AUTO-TRIGGER: Check and create tax record for new month (day 1)
        try {
          const taxCreated = await taxHistoryService.checkAndCreateNextMonthTax();
          if (taxCreated) {
            console.log('✅ Tax record auto-created for new month:', currentMonth);
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

  // Load daily operational costs based on selected date
  React.useEffect(() => {
    const loadDailyOperationalCosts = async () => {
      try {
        // Use the month from the selected date being viewed
        const monthToUse = selectedDate ? selectedDate.substring(0, 7) : new Date().toISOString().slice(0, 7); // YYYY-MM
        const dailyCosts = await operationalCostsService.getDailyActiveCosts(monthToUse);
        setDailyOperationalCosts(dailyCosts);
        console.log('💼 Daily operational costs loaded for month:', monthToUse, '=', dailyCosts);
      } catch (error) {
        console.error('Error loading daily operational costs:', error);
        setDailyOperationalCosts(0);
      }
    };

    if (selectedDate) {
      loadDailyOperationalCosts();
    }
  }, [selectedDate]); // Re-calculate when date changes

  // Use filtered data based on current selections - TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom' para usar a mesma lógica
  const filters = {
    date: selectedDate,
    endDate: selectedEndDate || undefined,
    projectId: projectId || "",
    period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod
  };

  console.log('🔍 ProjectDashboard: selectedEndDate:', selectedEndDate);

  // Debug: Log current filters for monitoring
  React.useEffect(() => {
    console.log('🔍 ProjectDashboard Current filters applied:', filters);
    console.log('🔍 ProjectDashboard DETAILED DEBUG:', {
      selectedPeriod,
      selectedDate,
      filterPeriod: filters.period,
      filterDate: filters.date,
      isYesterdayTreatedAsCustom: selectedPeriod === 'yesterday' && filters.period === 'custom'
    });
  }, [filters]);

  // Force refresh data when period changes
  React.useEffect(() => {
    if (selectedPeriod === 'today' || selectedPeriod === 'yesterday') {
      console.log('🔄 ProjectDashboard Forcing refresh for period:', selectedPeriod);
      setTimeout(() => {
        refresh(filters);
      }, 500);
    }
  }, [selectedPeriod, selectedDate]);

  // Always call useSupabaseData with filters like GeneralDashboard
  const { projects, campaigns, dailyMetrics, summary, loading: dataLoading, error: dataError, refresh } = useSupabaseData(filters);

  // Get current project data from filtered data - MOVED UP to avoid initialization error
  const currentProject = useMemo(() => {
    console.log('🔍 ProjectDashboard: Finding project', {
      projectId,
      projectIdType: typeof projectId,
      projectsCount: projects?.length,
      projects: projects?.map(p => ({ id: p.id, name: p.name, idType: typeof p.id }))
    });
    if (!projects || !projectId) return null;

    // Try multiple comparison methods since projectId can be string or number
    const projectIdNum = parseInt(projectId, 10);
    const found = projects.find(p => {
      const pId = typeof p.id === 'string' ? parseInt(p.id, 10) : p.id;
      return pId === projectIdNum || String(p.id) === projectId;
    });

    console.log('🔍 ProjectDashboard: Project search result:', {
      found: found?.name || 'Not found',
      foundId: found?.id,
      foundProjectType: found?.project_type,
      searchMethods: {
        'p.id === projectIdNum': projects.some(p => (typeof p.id === 'string' ? parseInt(p.id, 10) : p.id) === projectIdNum),
        'String(p.id) === projectId': projects.some(p => String(p.id) === projectId)
      }
    });


    return found;
  }, [projects, projectId]);

  // Filter campaigns by current project - MOVED UP to avoid initialization error
  const projectCampaigns = useMemo(() => {
    if (!campaigns || !projectId) return [];
    // Convert projectId to number for comparison since URL params are strings
    const projectIdNum = parseInt(projectId, 10);
    return campaigns.filter(c => {
      const cProjectId = typeof c.projectId === 'string' ? parseInt(c.projectId, 10) : c.projectId;
      const matches = cProjectId === projectIdNum;
      console.log('🔍 Campaign filter:', { campaignId: c.id, cProjectId, projectIdNum, matches });
      return matches;
    });
  }, [campaigns, projectId]);

  // Set loading and error from useSupabaseData
  useEffect(() => {
    console.log('🔄 ProjectDashboard: Loading state changed', { 
      dataLoading, 
      dataError, 
      selectedDate
    });
    setLoading(dataLoading);
    setError(dataError);
  }, [dataLoading, dataError]);


  // Handle period changes - igual ao GeneralDashboard
  const handlePeriodChange = async (period: 'today' | 'yesterday' | 'custom' | 'range') => {
    setSelectedPeriod(period);
    // Reset to current server date when changing to 'today' or 'yesterday'
    if (period === 'today') {
      try {
        // Clear cache and get fresh server date
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);
        setSelectedEndDate("");
        setCustomDate(undefined);
        setRangeStartDate(undefined);
        setRangeEndDate(undefined);
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
        setSelectedEndDate("");
        setCustomDate(undefined);
        setRangeStartDate(undefined);
        setRangeEndDate(undefined);
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
        setSelectedEndDate("");
        setCustomDate(undefined);
        setRangeStartDate(undefined);
        setRangeEndDate(undefined);

        // TRATAMENTO COMO CUSTOM DATE: Force immediate refresh for yesterday data (fallback) usando 'custom' period
        setTimeout(() => {
          const yesterdayFilters = { ...filters, date: saoPauloYesterday, period: 'custom' };
          console.log('🔄 Forcing immediate refresh for yesterday AS CUSTOM (fallback):', yesterdayFilters);
          refresh(yesterdayFilters);
        }, 100);
      }
    } else if (period === 'custom') {
      // Para período customizado, não fazemos nada aqui
      // O usuário vai selecionar no calendário
    }
  };

  const handleDateChange = (date: string) => {
    console.log('📅 ProjectDashboard Date changed to:', date, 'period:', selectedPeriod);
    setSelectedDate(date);
    // Force a refresh when date changes to ensure data is up to date
    // TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom'
    const newFilters = {
      ...filters,
      date,
      period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod
    };
    console.log('🔄 ProjectDashboard Refreshing with new filters:', newFilters);
    setTimeout(() => {
      refresh(newFilters);
    }, 100);
  };

  // Note: handleApplyCustomPeriod removido - SimpleDateFilter gerencia isso

  // Note: handleDateRangeChange removido - SimpleDateFilter gerencia isso


  // Format functions (revenue is now pre-converted by database)
  const formatRevenue = useCallback((brlValue: number) => {
    return formatBrlCurrency(brlValue);
  }, []);

  const formatCurrency = useCallback((brlValue: number) => {
    return formatCostCurrency(brlValue);
  }, []);

  // Função para calcular custos operacionais proporcionais aos dias selecionados
  const calculateProportionalOperationalCosts = useCallback(() => {
    if (!currentProject || !currentProject.costs_division || dailyOperationalCosts <= 0) {
      return 0;
    }

    // Calcular quantos dias estão no período selecionado
    let daysInPeriod = 1;

    if (selectedPeriod === 'today' || selectedPeriod === 'yesterday' || selectedPeriod === 'custom') {
      daysInPeriod = 1;
    } else if (selectedPeriod === 'range' && selectedDate && selectedEndDate) {
      const start = new Date(selectedDate);
      const end = new Date(selectedEndDate);
      daysInPeriod = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
    }

    // Dividir custos operacionais pelo número de projetos que participam da divisão
    const totalOperationalCosts = dailyOperationalCosts * daysInPeriod;
    return totalOperationalCosts / projectsWithCostDivisionCount;
  }, [currentProject, dailyOperationalCosts, selectedPeriod, selectedDate, selectedEndDate, projectsWithCostDivisionCount]);

  // Função para calcular ROI final com impostos e custos operacionais (similar ao dashboard geral)
  const calculateFinalROI = useCallback((totalRevenue: number, totalInvestment: number) => {
    if (totalInvestment <= 0) return 0;

    // Calcular lucro líquido com impostos e custos operacionais
    const calculation = calculateSimplifiedNetProfit(totalRevenue, totalInvestment);
    return (calculation.netProfit / totalInvestment) * 100;
  }, [currentTaxRate, calculateProportionalOperationalCosts]);

  // Função simplificada para calcular lucro líquido (similar ao dashboard geral)
  const calculateSimplifiedNetProfit = useCallback((
    totalRevenueAfterRevshare: number,
    totalInvestment: number
  ) => {
    // Custos operacionais proporcionais ao período
    const proportionalOperationalCosts = calculateProportionalOperationalCosts();

    // Cálculo simplificado: já temos o faturamento líquido (após revenue share)
    const grossProfit = totalRevenueAfterRevshare - totalInvestment;
    const taxAmount = totalRevenueAfterRevshare * (currentTaxRate / 100);
    const netProfitBeforeCosts = grossProfit - taxAmount;
    const netProfit = netProfitBeforeCosts - proportionalOperationalCosts;

    return {
      netRevenue: totalRevenueAfterRevshare,
      grossProfit,
      taxAmount,
      operationalCosts: proportionalOperationalCosts,
      netProfit,
      formula: `Faturamento Líquido (${totalRevenueAfterRevshare.toFixed(2)}) - Investimento (${totalInvestment.toFixed(2)}) - Impostos (${taxAmount.toFixed(2)}) - Custos Op. (${proportionalOperationalCosts.toFixed(2)}) = ${netProfit.toFixed(2)}`
    };
  }, [currentTaxRate, calculateProportionalOperationalCosts]);


  // Note: calculateCorrectNetProfit removido - não utilizado no novo modelo




  // Effect to fetch campaigns revenue using optimized aggregated query
  useEffect(() => {
    const fetchCampaignsRevenue = async () => {
      if (!currentProject || !filters) return;

      try {
        // Determine date range for campaigns aggregation
        let startDate = filters?.date || await supabaseDataService.getServerDate();
        let endDate = filters?.endDate || startDate;

        // Note: ProjectDashboard now only supports today, yesterday, custom periods
        // No 7d or 30d periods like in GeneralDashboard

        const aggregatedMetrics = await supabaseDataService.getCampaignAggregatedMetrics(
          currentProject.id,
          startDate,
          endDate
        );

        setCampaignsRevenue(aggregatedMetrics.totalRevenue);

        console.log('🚀 OPTIMIZED: Campaign metrics fetched with single aggregated query:', {
          projectId: currentProject.id,
          startDate,
          endDate,
          campaignsRevenue: aggregatedMetrics.totalRevenue,
          campaignCount: aggregatedMetrics.campaignCount
        });

      } catch (error) {
        console.error('Error fetching aggregated campaign metrics, falling back to frontend sum:', error);
        // Fallback to frontend calculation
        const fallbackRevenue = projectCampaigns?.reduce((sum, campaign) => {
          return sum + (campaign.revenue || 0);
        }, 0) || 0;
        setCampaignsRevenue(fallbackRevenue);
      }
    };

    fetchCampaignsRevenue();
  }, [currentProject, filters, projectCampaigns]);

  // Effect to fetch projects with cost division count for operational cost calculation
  useEffect(() => {
    const fetchProjectsWithCostDivision = async () => {
      if (!currentProject?.costs_division) {
        setProjectsWithCostDivisionCount(1);
        return;
      }

      try {
        // Query projects with cost division directly
        const { data: projectsWithCostDivision, error } = await supabase
          .from('projects')
          .select('id')
          .eq('costs_division', true);

        if (error) {
          console.error('Error fetching projects with cost division:', error);
          setProjectsWithCostDivisionCount(1);
        } else {
          const count = projectsWithCostDivision?.length || 1;
          setProjectsWithCostDivisionCount(count);
          console.log('📊 Projects with cost division count:', count);
        }
      } catch (error) {
        console.error('Error fetching projects with cost division:', error);
        setProjectsWithCostDivisionCount(1);
      }
    };

    fetchProjectsWithCostDivision();
  }, [currentProject]);

  // Calculate metrics with comparison - using specific project data
  const metrics = useMemo(() => {
    try {
      if (!currentProject || !projectCampaigns || !summary) {
        console.log('⚠️ Metrics calculation skipped - missing data:', {
          currentProject: !!currentProject,
          projectCampaigns: !!projectCampaigns,
          summary: !!summary
        });
        return null;
      }

    // Calculate project-specific metrics
    const projectInvestment = projectCampaigns.reduce((sum, c) => sum + (c.investment || 0), 0);

    // All projects use daily_project_metrics for total revenue (optimized for better performance and reduced egress)
    // Revenue is already pre-calculated with revshare discount in daily_project_metrics
    const projectRevenue = currentProject.revenue || 0;

    // Calculate organic excedent using the optimized campaigns revenue
    const organicExcedent = projectRevenue - campaignsRevenue;
    const organicExcedentPercentage = projectRevenue > 0 ? (organicExcedent / projectRevenue) * 100 : 0;

    console.log('🎯 Revenue calculation method:', {
      projectType: currentProject?.project_type,
      projectRevenue,
      campaignsRevenue,
      organicExcedent,
      organicExcedentPercentage: `${organicExcedentPercentage.toFixed(1)}%`,
      source: 'daily_project_metrics (optimized for all project types)'
    });
    const projectProfit = calculateSimplifiedNetProfit(projectRevenue, projectInvestment).netProfit; // Lucro líquido com impostos e custos
    const projectRoas = calculateROAS(projectRevenue, projectInvestment); // ROAS com caso especial para faturamento sem gasto
    const projectRoi = calculateFinalROI(projectRevenue, projectInvestment); // ROI final com impostos e custos operacionais

    console.log('📊 Project metrics calculated:', {
      projectId: currentProject.id,
      projectType: currentProject?.project_type,
      campaignsCount: projectCampaigns.length,
      projectInvestment,
      projectRevenue,
      projectProfit,
      projectRoas,
      projectRoi,
      calculations: {
        roas_formula: `((${projectRevenue} - ${projectInvestment}) / ${projectInvestment}) * 100 = ${projectRoas}%`,
        profit_formula: `calculateSimplifiedNetProfit(${projectRevenue}, ${projectInvestment}) = ${projectProfit}`,
        roi_formula: `calculateFinalROI(${projectRevenue}, ${projectInvestment}) = ${projectRoi}%`
      }
    });

    return {
      investment: {
        value: projectInvestment,
        comparison: 0, // TODO: Add previous period comparison
        change: summary?.trendsPercentage?.investment || 0
      },
      revenue: {
        value: projectRevenue,
        comparison: 0, // TODO: Add previous period comparison
        change: summary?.trendsPercentage?.revenue || 0
      },
      roas: {
        value: projectRoas,
        comparison: 0, // TODO: Add previous period comparison
        change: summary?.trendsPercentage?.roas || 0
      },
      grossProfit: {
        value: projectProfit,
        comparison: 0, // TODO: Add previous period comparison
        change: summary?.trendsPercentage?.profit || 0
      },
      roi: {
        value: projectRoi,
        comparison: 0, // TODO: Add previous period comparison
        change: summary?.trendsPercentage?.roi || 0
      },
      organicExcedent: {
        value: organicExcedent,
        percentage: organicExcedentPercentage
      }
    };
    } catch (error) {
      console.error('💥 Error calculating metrics:', error);
      return null;
    }
  }, [currentProject, projectCampaigns, summary, campaignsRevenue, calculateSimplifiedNetProfit, calculateFinalROI]);

  // Filter campaigns
  const filteredCampaigns = useMemo(() => {
    try {
    if (!projectCampaigns) return [];

    return projectCampaigns.filter((campaign: any) => {
      const matchesSearch = campaign.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
                           (campaign.description || '').toLowerCase().includes(searchFilter.toLowerCase());

      const campaignROAS = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
      const matchesStatus = statusFilter === "all" ||
                           (statusFilter === "critical" && campaignROAS < 0) ||
                           (statusFilter === "active" && campaign.status === "active") ||
                           (statusFilter === "paused" && campaign.status === "paused");

      return matchesSearch && matchesStatus;
    });
    } catch (error) {
      console.error('💥 Error filtering campaigns:', error);
      return [];
    }
  }, [projectCampaigns, searchFilter, statusFilter]);

  // Handle campaign actions
  const handleCampaignAction = useCallback((action: string, campaignId: string) => {
    console.log(`🎬 Action: ${action} on campaign: ${campaignId}`);
    console.log('🔍 Debug currentProject:', {
      currentProject: currentProject ? {
        id: currentProject.id,
        name: currentProject.name,
        project_type: currentProject.project_type
      } : null
    });
    console.log('🔍 Debug states:', {
      isFunnelUrlsOpen,
      selectedCampaignForUrls
    });

    if (action === 'edit') {
      // Verificar se o projeto é do tipo ADSENSE
      const isAdSenseProject = currentProject?.project_type === 'ADSENSE';
      console.log('🚩 Project type check:', {
        project_type: currentProject?.project_type,
        isAdSenseProject
      });

      if (isAdSenseProject) {
        console.log('✅ AdSense project detected - opening funnel URLs popup');
        // Para projetos AdSense, abrir popup de URLs do funil
        const campaign = filteredCampaigns?.find(c => c.id === campaignId);
        console.log('🔍 Campaign found:', campaign ? {
          id: campaign.id,
          name: campaign.name,
          googleAdsCampaignId: campaign.googleAdsCampaignId
        } : 'Not found');
        console.log('🔍 filteredCampaigns total:', filteredCampaigns?.length);
        console.log('🔍 All campaigns:', filteredCampaigns?.map(c => ({ id: c.id, name: c.name })));

        if (campaign) {
          // Para projetos AdSense, usar googleAdsCampaignId se disponível, senão usar id
          const funnelCampaignId = campaign.googleAdsCampaignId || campaignId;
          console.log('🔗 Using funnel campaign ID:', funnelCampaignId);

          const campaignData = {
            id: funnelCampaignId,
            name: campaign.name || `Campanha ${campaignId}`
          };

          console.log('🎯 Setting popup state:', campaignData);
          setSelectedCampaignForUrls(campaignData);
          setIsFunnelUrlsOpen(true);
          console.log('🎯 Popup should open now - states set');

          // Verificar se o estado foi definido
          setTimeout(() => {
            console.log('🔍 States after timeout:', {
              isFunnelUrlsOpen,
              selectedCampaignForUrls
            });
          }, 100);
        } else {
          console.error('❌ Campaign not found in filteredCampaigns');
          console.error('❌ Searched for ID:', campaignId, 'Type:', typeof campaignId);
        }
      } else {
        // Para projetos GAM, mostrar mensagem informativa discreta
        console.log('📋 GAM project - showing info toast');
        toast({
          title: "Cadastro de Funis por URL",
          description: "Este recurso só está disponível em projetos AdSense. Em projetos GAM, o processo é feito automaticamente pelo sistema.",
          variant: "default",
        });
      }
    } else {
      // Outras ações (pause, play, etc.)
      console.log(`Other action: ${action} - TODO: implement`);
    }
  }, [currentProject, filteredCampaigns, isFunnelUrlsOpen, selectedCampaignForUrls]);

  console.log('🎯 ProjectDashboard: Render conditions', {
    loading,
    error,
    currentProject: !!currentProject,
    selectedDate,
    dataLoading,
    projectsCount: projects?.length,
    hasFilters: !!filters,
    projectId,
    filters
  });

  // Debug do projeto atual
  console.log('🔍 Current Project Debug:', {
    currentProject: currentProject ? {
      id: currentProject.id,
      name: currentProject.name,
      project_type: currentProject.project_type,
      allProperties: Object.keys(currentProject)
    } : null,
    projectId,
    isAdSenseProject: currentProject?.project_type === 'ADSENSE'
  });

  if (loading) {
    console.log('🔄 ProjectDashboard: Showing loading state');
    return (
      <Layout>
        <div className="p-6 space-y-8 max-w-7xl mx-auto">
          <div className="flex items-center justify-center min-h-64">
            <LoadingSpinner size="lg" text="Carregando dashboard do projeto..." />
          </div>
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="p-6 space-y-8 max-w-7xl mx-auto">
          <div className="flex flex-col items-center justify-center min-h-64">
            <AlertTriangle className="h-16 w-16 text-destructive mx-auto mb-4" />
            <h1 className="text-2xl font-bold mb-2">Erro ao carregar projeto</h1>
            <p className="text-muted-foreground mb-4">{error}</p>
            <Button onClick={() => window.location.reload()} variant="outline">
              Tentar novamente
            </Button>
          </div>
        </div>
      </Layout>
    );
  }

  if (!currentProject && !loading) {
    console.log('❌ ProjectDashboard: Project not found', { 
      projectId, 
      projectsCount: projects?.length,
      projects: projects?.map(p => ({ id: p.id, name: p.name })),
      selectedDate,
      loading,
      dataLoading
    });
    return (
      <Layout>
        <div className="p-6">
          <div className="text-center py-12">
            <h2 className="text-xl font-semibold mb-2">Projeto não encontrado</h2>
            <p className="text-sm text-muted-foreground mb-4">
              ID: {projectId} | Projetos carregados: {projects?.length || 0}
            </p>
            <div className="text-xs text-muted-foreground mb-4">
              Debug: loading={loading}, dataLoading={dataLoading}, selectedDate={selectedDate}
            </div>
            <Button onClick={() => navigate("/settings/projects")} variant="outline">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Voltar aos Projetos
            </Button>
          </div>
        </div>
      </Layout>
    );
  }

  console.log('✅ ProjectDashboard: Rendering main dashboard', {
    currentProject: currentProject?.name,
    campaignsCount: projectCampaigns?.length,
    metricsAvailable: !!metrics
  });

  return (
    <Layout>
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header with User and Controls */}
        <div className="flex items-center justify-between transition-all duration-300">
          <div className="flex items-center gap-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate("/")}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Voltar ao Dashboard
            </Button>
            <div>
              <h1 className="text-3xl font-bold bg-gradient-to-r from-primary via-purple-600 to-blue-600 bg-clip-text text-transparent flex items-center gap-2">
                📂 {currentProject?.name || 'Carregando...'}
              </h1>
              <p className="text-muted-foreground">
                Dashboard do projeto • {filteredCampaigns.length} campanhas filtradas •
                Status: {currentProject?.status === 'active' ? '🟢 Ativo' : '🟡 Pausado'}
                {selectedPeriod === 'custom' && selectedDate && (
                  <span className="ml-2 text-primary">
                    • Data: {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}
                  </span>
                )}
                {selectedPeriod !== 'custom' && selectedPeriod !== 'range' && (
                  <span className="ml-2 text-primary">
                    • Período: {selectedPeriod === 'today' ? 'Hoje' : selectedPeriod === 'yesterday' ? 'Ontem' : 'Data customizada'}
                  </span>
                )}
                {selectedPeriod === 'range' && selectedDate && selectedEndDate && (
                  <span className="ml-2 text-primary">
                    • Período: {selectedDate} até {selectedEndDate} ({(() => {
                      const start = new Date(selectedDate + 'T00:00:00');
                      const end = new Date(selectedEndDate + 'T00:00:00');
                      const diffDays = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
                      return diffDays;
                    })()} dias)
                  </span>
                )}
              </p>
              <p className="text-sm text-muted-foreground flex items-center gap-2">
                🌐 {currentProject?.domain}
                {/* Ícone discreto do tipo de projeto abaixo da URL */}
                {currentProject?.project_type && (
                  <span
                    className="text-xs text-gray-400 opacity-70 font-medium"
                    title={`Projeto do tipo ${currentProject.project_type}`}
                  >
                    • {currentProject.project_type}
                  </span>
                )}
              </p>
            </div>
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
                  {!loading && (!filteredCampaigns || filteredCampaigns.length === 0) && (
                    <span className="text-amber-600">⚠️ Sem dados</span>
                  )}
                  {!loading && filteredCampaigns && filteredCampaigns.length > 0 && (
                    <span className="text-green-600">✓ {filteredCampaigns.length} campanhas</span>
                  )}
                </div>
              )}
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => refresh(filters)}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Atualizar
            </Button>

            
            <DataStatus 
              loading={loading} 
              error={error} 
              lastUpdate={new Date().toLocaleTimeString('pt-BR')}
            />
          </div>
        </div>


        {/* Metrics Cards */}
        {metrics && (
          <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-5">
            <MetricCard
              title="💰 Investido"
              value={formatCurrency(metrics.investment.value)}
              comparison={`Ontem: ${formatCurrency(metrics.investment.comparison)}`}
              change={metrics.investment.change}
              icon={<DollarSign />}
              color="info"
            />
            {/* Custom Revenue Card with organic excedent indicator */}
            <Card className="animate-fade-in shadow-card border-success/20 bg-gradient-to-br from-success/5 to-success/10">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    {currentProject?.project_type === 'ADSENSE' ? '💵 Revenue Total' : '💵 Faturado (Líquido)'}
                  </CardTitle>
                  {metrics.organicExcedent && metrics.organicExcedent.value !== 0 && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div className={`w-2 h-2 rounded-full ${
                            metrics.organicExcedent.value > 0 ? 'bg-blue-500' : 'bg-orange-500'
                          } opacity-70`} />
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-xs p-3">
                          <div className="space-y-1 text-sm">
                            <div className="font-medium text-primary">Revenue Orgânico</div>
                            <div className="text-muted-foreground">
                              {metrics.organicExcedent.value > 0 ? 'Excedente' : 'Déficit'}:
                              <span className={`font-mono ml-1 ${
                                metrics.organicExcedent.value > 0 ? 'text-blue-600' : 'text-orange-600'
                              }`}>
                                {formatRevenue(Math.abs(metrics.organicExcedent.value))}
                              </span>
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {Math.abs(metrics.organicExcedent.percentage).toFixed(1)}% do faturamento total
                            </div>
                            <div className="text-xs text-muted-foreground border-t pt-1 mt-2">
                              <div>
                                {currentProject?.project_type === 'ADSENSE' ? 'Revenue Total' : 'Faturamento Total'}: {formatRevenue(metrics.revenue.value)}
                              </div>
                              <div>Campanhas: {formatRevenue(campaignsRevenue)}</div>
                              <div className="font-medium">
                                {metrics.organicExcedent.value > 0 ? 'Orgânico' : 'Déficit'}: {formatRevenue(Math.abs(metrics.organicExcedent.value))}
                              </div>
                              {currentProject?.project_type === 'ADSENSE' && (
                                <div className="text-xs italic mt-1 text-blue-600">
                                  * AdSense: Revenue sem RevShare
                                </div>
                              )}
                            </div>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                </div>
                <div className="h-4 w-4 text-primary"><DollarSign /></div>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold mb-1">{formatRevenue(metrics.revenue.value)}</div>
                <div className="text-xs text-muted-foreground mb-2">{`Ontem: ${formatRevenue(metrics.revenue.comparison)}`}</div>
                <div className="flex items-center text-xs">
                  <TrendingUp className="mr-1 h-3 w-3 text-success" />
                  <span className="text-success">
                    +{metrics.revenue.change.toFixed(1)}%
                  </span>
                  {metrics.organicExcedent && metrics.organicExcedent.value !== 0 && (
                    <span className={`ml-2 text-xs ${
                      metrics.organicExcedent.value > 0 ? 'text-blue-600' : 'text-orange-600'
                    }`}>
                      • {metrics.organicExcedent.value > 0 ? 'Org+' : 'Org-'}{Math.abs(metrics.organicExcedent.percentage).toFixed(0)}%
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
            <MetricCard
              title="📈 ROAS"
              value={`${metrics.roas.value.toFixed(0)}%`}
              comparison={`Ontem: ${metrics.roas.comparison.toFixed(0)}%`}
              change={metrics.roas.change}
              icon={<TrendingUp />}
              color="success"
            />
            <MetricCard
              title="💚 L. Líquido"
              value={formatCurrency(metrics.grossProfit.value)}
              comparison={`Ontem: ${formatCurrency(metrics.grossProfit.comparison)}`}
              change={metrics.grossProfit.change}
              icon={<DollarSign />}
              color="success"
            />

            <Card className="animate-fade-in shadow-card border-info/20 bg-gradient-to-br from-info/5 to-info/10">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">👑 ROI Final</CardTitle>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="h-3 w-3 text-muted-foreground opacity-60 hover:opacity-100 cursor-help transition-opacity" />
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs p-4">
                        <div className="space-y-2 text-sm">
                          <div className="font-medium text-primary mb-2">Cálculo do ROI Final</div>
                          {(() => {
                            const calculation = calculateSimplifiedNetProfit(metrics.revenue.value, metrics.investment.value);
                            return (
                              <div className="space-y-1">
                                <div className="flex justify-between">
                                  <span className="text-muted-foreground">
                                    {currentProject?.project_type === 'ADSENSE' ? 'Revenue Total:' : 'Faturamento Líquido (após RevShare):'}
                                  </span>
                                  <span className="font-mono text-blue-600">{formatRevenue(calculation.netRevenue)}</span>
                                </div>
                                {currentProject?.project_type === 'ADSENSE' && (
                                  <div className="text-xs text-muted-foreground italic mb-2">
                                    * Projeto AdSense: Revenue sem desconto de RevShare
                                  </div>
                                )}
                                <div className="flex justify-between">
                                  <span className="text-muted-foreground">Investimento:</span>
                                  <span className="font-mono text-red-600">-{formatCurrency(metrics.investment.value)}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-muted-foreground">Impostos SN ({currentTaxRate}%):</span>
                                  <span className="font-mono text-red-600">-{formatCurrency(calculation.taxAmount)}</span>
                                </div>
                                {calculation.operationalCosts > 0 && (
                                  <div className="flex justify-between">
                                    <span className="text-muted-foreground">Custos Operacionais:</span>
                                    <span className="font-mono text-red-600">-{formatCurrency(calculation.operationalCosts)}</span>
                                  </div>
                                )}
                                <div className="border-t pt-1 border-primary/20">
                                  <div className="flex justify-between font-medium">
                                    <span className="text-muted-foreground">Lucro Líquido:</span>
                                    <span className="font-mono text-green-600">{formatCurrency(calculation.netProfit)}</span>
                                  </div>
                                </div>
                                <div className="border-t pt-2 border-primary/20">
                                  <div className="flex justify-between font-medium">
                                    <span>ROI Final:</span>
                                    <span className="font-mono text-primary">{metrics.roi.value.toFixed(1)}%</span>
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
                <div className="h-4 w-4 text-primary"><TrendingUp /></div>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold mb-1">{`${metrics.roi.value.toFixed(1)}%`}</div>
                <div className="text-xs text-muted-foreground mb-2">{`Ontem: ${metrics.roi.comparison.toFixed(0)}%`}</div>
                <div className="flex items-center text-xs">
                  <TrendingUp className="mr-1 h-3 w-3 text-info" />
                  <span className="text-info">
                    +{metrics.roi.change.toFixed(1)}%
                  </span>
                  <span className="ml-2 text-muted-foreground">
                    Com {currentTaxRate}% SN
                    {currentProject?.costs_division && ` + Custos Op.`}
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Campaigns List */}
        <Card className="shadow-card animate-fade-in">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Lista de Campanhas</CardTitle>
                <div className="flex items-center gap-4 mt-2">
                  <Badge variant="outline" className="text-sm">
                    {filteredCampaigns.length} {filteredCampaigns.length === 1 ? 'campanha' : 'campanhas'}
                  </Badge>
                  {projectCampaigns && projectCampaigns.length > 0 && (
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        🟢 {projectCampaigns.filter(c => {
                          const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                          return getROASColorCategory(roasExcess) === "green";
                        }).length}
                      </span>
                      <span className="flex items-center gap-1">
                        🟡 {projectCampaigns.filter(c => {
                          const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                          return getROASColorCategory(roasExcess) === "yellow";
                        }).length}
                      </span>
                      <span className="flex items-center gap-1">
                        🟠 {projectCampaigns.filter(c => {
                          const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                          return getROASColorCategory(roasExcess) === "orange";
                        }).length}
                      </span>
                      <span className="flex items-center gap-1">
                        🔴 {projectCampaigns.filter(c => {
                          const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                          return getROASColorCategory(roasExcess) === "red";
                        }).length}
                      </span>
                    </div>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline">
                  <Download className="h-4 w-4 mr-2" />
                  Exportar
                </Button>
                {currentProject?.project_type === 'ADSENSE' && (
                  <Badge variant="secondary" className="text-xs">
                    Modo AdSense - Edição de funis disponível
                  </Badge>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {filteredCampaigns?.map((campaign: any) => (
                <CampaignCard
                  key={campaign.id}
                  campaign={campaign}
                  onAction={handleCampaignAction}
                  formatRevenue={formatRevenue}
                  currentProject={currentProject}
                  selectedPeriod={selectedPeriod}
                  selectedDate={selectedDate}
                  navigate={navigate}
                />
              )) || []}
            </div>

            {(!filteredCampaigns || filteredCampaigns.length === 0) && (
              <div className="text-center py-12">
                <p className="text-muted-foreground">Nenhuma campanha encontrada com os filtros aplicados</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Historical Chart - Only show for non-today periods */}
        {dailyMetrics && dailyMetrics.length > 0 && selectedPeriod !== 'today' && (
          <Card className="shadow-card animate-fade-in">
            <CardHeader>
              <CardTitle>📈 Histórico - {
                selectedPeriod === 'yesterday' ? 'Ontem' :
                selectedPeriod === 'range' && selectedDate && selectedEndDate ?
                  `${selectedDate} até ${selectedEndDate}` :
                `Data: ${format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}`
              }</CardTitle>
              <div className="flex gap-2">
                <Badge variant="outline">Receita</Badge>
                <Badge variant="outline">Investimento</Badge>
                <Badge variant="outline">ROAS</Badge>
                <Badge variant="outline">ROI</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={dailyMetrics}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis
                    dataKey="date"
                    className="text-xs"
                    tickFormatter={(value) => {
                      try {
                        return format(new Date(value), "dd/MM");
                      } catch {
                        return value;
                      }
                    }}
                  />
                  <YAxis className="text-xs" />
                  <RechartsTooltip
                    labelFormatter={(value) => {
                      try {
                        return format(new Date(value), "dd/MM/yyyy");
                      } catch {
                        return value;
                      }
                    }}
                    formatter={(value: number, name: string) => {
                      if (name === "investment" || name === "revenue") {
                        return [formatCurrency(value), name === "investment" ? "💸 Investimento" : "💰 Receita"];
                      }
                      return [value + "%", name === "roas" ? "📈 ROAS" : "👑 ROI"];
                    }}
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
                    name="revenue"
                  />
                  <Line
                    type="monotone"
                    dataKey="investment"
                    stroke="hsl(var(--warning))"
                    strokeWidth={2}
                    name="investment"
                  />
                  <Line
                    type="monotone"
                    dataKey="roas"
                    stroke="hsl(var(--primary))"
                    strokeWidth={2}
                    name="roas"
                  />
                  <Line
                    type="monotone"
                    dataKey="roi"
                    stroke="hsl(var(--info))"
                    strokeWidth={2}
                    name="roi"
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Popup de URLs do funil para projetos AdSense */}
      {(() => {
        console.log('🎯 Render popup check:', {
          selectedCampaignForUrls: !!selectedCampaignForUrls,
          isFunnelUrlsOpen,
          campaignId: selectedCampaignForUrls?.id,
          campaignName: selectedCampaignForUrls?.name
        });
        return selectedCampaignForUrls ? (
          <FunnelUrlsEditor
            isOpen={isFunnelUrlsOpen}
            onClose={() => {
              console.log('🎯 Popup closing');
              setIsFunnelUrlsOpen(false);
              setSelectedCampaignForUrls(null);
            }}
            campaignId={selectedCampaignForUrls.id}
            campaignName={selectedCampaignForUrls.name}
            onSave={() => {
              // Opcional: refresh dos dados após salvar
              console.log('URLs do funil salvas com sucesso');
            }}
          />
        ) : null;
      })()}
    </Layout>
  );

  } catch (error) {
    console.error('💥 ProjectDashboard: Critical error caught:', error);
    return (
      <Layout>
        <div className="p-6">
          <div className="text-center py-12">
            <h2 className="text-xl font-semibold mb-2 text-red-600">Erro Crítico</h2>
            <p className="text-sm text-muted-foreground mb-4">
              {error instanceof Error ? error.message : 'Erro desconhecido'}
            </p>
            <pre className="text-xs bg-red-50 p-4 rounded text-left mb-4">
              {error instanceof Error ? error.stack : JSON.stringify(error)}
            </pre>
            <Button onClick={() => window.location.reload()} variant="outline">
              <RefreshCw className="h-4 w-4 mr-2" />
              Recarregar página
            </Button>
          </div>
      </div>
    </Layout>
  );
  }
}