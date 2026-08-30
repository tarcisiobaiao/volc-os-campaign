import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CampaignSortSelect } from "@/components/campaign/CampaignSortSelect";
import { sortCampaigns, type CampaignSortKey } from "@/lib/campaignSort";
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
  Info,
  FolderOpen,
  BarChart3,
  Coins,
  Circle,
  Crown,
  FileText,
  Settings,
  CheckCircle
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
import { chartColor, volcGrid, volcAxis, volcLine, volcCursor, VolcTooltip } from "@/lib/chartTheme";
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
import { PublicacaoDoProjeto } from "@/components/publicacao/PublicacaoDoProjeto";
import { useToast } from "@/hooks/use-toast";
import { MetricDelta } from "@/components/campaign/MetricDelta";
import { useCampaignComparisons, CampaignComparison } from "@/hooks/useCampaignComparisons";

// Types

interface MetricCardProps {
  title: React.ReactNode;
  value: string;
  comparison: string;
  change: number;
  icon: React.ReactNode;
  color: "success" | "warning" | "danger" | "info";
  index?: number;
}

// Metric Card with Comparison — VOLC stat tile
const MetricCard = ({ title, value, comparison, change, icon, color, index = 0 }: MetricCardProps) => {
  const isPositive = change > 0;
  const accentClasses = {
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-destructive",
    info: "bg-info"
  };
  const chipClasses = {
    success: "bg-success/10 text-success",
    warning: "bg-warning/10 text-warning",
    danger: "bg-destructive/10 text-destructive",
    info: "bg-info/10 text-info"
  };

  return (
    <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: index }}>
      <span className={cn("pointer-events-none absolute inset-x-0 top-0 h-0.5", accentClasses[color])} />
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
        <span className="kicker">{title}</span>
        <span className={cn("rounded-md p-1.5", chipClasses[color])}>{icon}</span>
      </CardHeader>
      <CardContent className="relative z-10">
        <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight mb-1">{value}</div>
        <div className="text-xs text-muted-foreground mb-2">{comparison}</div>
        <div className="flex items-center text-xs">
          {isPositive ? (
            <TrendingUp className="mr-1 h-3 w-3 text-success" />
          ) : (
            <TrendingDown className="mr-1 h-3 w-3 text-destructive" />
          )}
          <span className={cn("font-medium tabular", isPositive ? "text-success" : "text-destructive")}>
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
  navigate,
  comparison,
  loadingComparisons,
}: {
  campaign: any;
  onAction: (action: string, campaignId: string) => void;
  formatRevenue: (brl: number) => string;
  currentProject: any;
  selectedPeriod: string;
  selectedDate: string;
  navigate: (path: string) => void;
  comparison: CampaignComparison | undefined;
  loadingComparisons: boolean;
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
        return <Badge variant="default" className="bg-success text-white flex items-center gap-1">
          <Circle className="h-2 w-2 fill-white" />
          Ativa
        </Badge>;
      case 'paused':
        return <Badge variant="secondary" className="bg-warning text-white flex items-center gap-1">
          <Circle className="h-2 w-2 fill-white" />
          Pausada
        </Badge>;
      case 'stopped':
        return <Badge variant="destructive" className="bg-destructive text-white flex items-center gap-1">
          <Circle className="h-2 w-2 fill-white" />
          Parada
        </Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  // Only show edit button for ADSENSE projects
  const isAdSenseProject = currentProject?.project_type === 'ADSENSE';

  return (
    <Link
      to={`/dashboard/campaign/${campaign.utmCampaignValue || campaign.id}`}
      className="block no-underline text-inherit"
    >
    <Card
      className="p-6 cursor-pointer shadow-card hover-lift"
    >
      <CardContent className="p-0">
        <div className="space-y-4">
          {/* Campaign Header */}
          <div className="flex items-start justify-between">
            <div>
              <h3 className="font-display font-semibold text-lg tracking-tight">
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
                  e.preventDefault();
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
            <h4 className="mb-3 flex items-center gap-2">
              <span className="rounded-md bg-primary/10 text-primary p-1.5"><BarChart3 className="h-4 w-4" /></span>
              <span className="kicker">Performance Financeira · {
              selectedPeriod === 'today' ? 'Hoje' :
              selectedPeriod === 'yesterday' ? 'Ontem' :
              selectedPeriod === 'range' ? 'Período Selecionado' :
              `Data: ${new Date(selectedDate).toLocaleDateString('pt-BR')}`
            }</span></h4>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className="text-center p-3 bg-destructive/10 rounded-lg">
                <p className="kicker mb-1">Gasto</p>
                <p className="font-display font-semibold tabular text-destructive">
                  {new Intl.NumberFormat('pt-BR', {
                    style: 'currency',
                    currency: 'BRL'
                  }).format(campaign.investment || 0)}
                </p>
                <MetricDelta
                  current={campaign.investment || 0}
                  previous={comparison?.prevInvestment}
                  label={comparison?.comparisonLabel ?? ''}
                  isLoading={loadingComparisons}
                />
              </div>
              <div className="text-center p-3 bg-success/10 rounded-lg">
                <p className="kicker mb-1">Revenue</p>
                <p className="font-display font-semibold tabular text-success">{formatRevenue(campaign.revenue || 0)}</p>
                <MetricDelta
                  current={campaign.revenue || 0}
                  previous={comparison?.prevRevenue}
                  label={comparison?.comparisonLabel ?? ''}
                  isLoading={loadingComparisons}
                />
              </div>
              <div className={`text-center p-3 rounded-lg border ${getROIColor(roasExcess)}`}>
                <p className="kicker mb-1">ROAS</p>
                <p className="font-display font-semibold tabular">{roasExcess.toFixed(1)}%</p>
                <MetricDelta
                  current={roasExcess}
                  previous={comparison?.prevRoas}
                  label={comparison?.comparisonLabel ?? ''}
                  isLoading={loadingComparisons}
                />
              </div>
            </div>
          </div>

          {/* Campaign Details */}
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>ID: {campaign.utmCampaignValue || campaign.googleAdsCampaignId || campaign.id}</span>
            <span>|</span>
            <span className="flex items-center gap-1">
              <CalendarIcon className="h-3 w-3" />
              Criada: {campaign.startDate ? new Date(campaign.startDate).toLocaleDateString('pt-BR') : 'N/A'}
            </span>
            <span>|</span>
            <span>Tipo: {currentProject?.project_type || 'N/A'}</span>
          </div>
        </div>
      </CardContent>
    </Card>
    </Link>
  );
};

export default function ProjectDashboard() {
  try {
  const { projectId } = useParams();
  const navigate = useNavigate();


  // Early return if no projectId
  if (!projectId) {
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
  const [sortKey, setSortKey] = useState<CampaignSortKey>("roas");

  // Estados para o popup de URLs do funil (AdSense)
  const [isFunnelUrlsOpen, setIsFunnelUrlsOpen] = useState(false);
  const [selectedCampaignForUrls, setSelectedCampaignForUrls] = useState<{id: string, name: string} | null>(null);

  const [isUpdatingProjectType, setIsUpdatingProjectType] = useState(false);

  const { toast } = useToast();

  // Initialize with current server date (São Paulo timezone) and preload exchange rate
  React.useEffect(() => {
    const initialize = async () => {
      try {
        // Initialize date
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);

        // Preload exchange rate for currency conversion
        await preloadExchangeRate();

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

  // Load tax rate and daily operational costs based on selected date
  React.useEffect(() => {
    const loadFinancialData = async () => {
      try {
        let taxRate: number;

        // If it's a range spanning multiple months, use weighted average
        if (selectedPeriod === 'range' && selectedDate && selectedEndDate &&
            selectedDate.substring(0, 7) !== selectedEndDate.substring(0, 7)) {
          // Multiple months: use weighted average tax rate
          taxRate = await taxHistoryService.getTaxRateForDateRange(selectedDate, selectedEndDate);
        } else {
          // Single month: use that month's tax rate
          const monthToUse = selectedDate ? selectedDate.substring(0, 7) : new Date().toISOString().slice(0, 7);
          taxRate = await taxHistoryService.getCurrentTaxRate(monthToUse);
        }

        setCurrentTaxRate(taxRate);

        // Load daily operational costs for the selected month
        const monthToUse = selectedDate ? selectedDate.substring(0, 7) : new Date().toISOString().slice(0, 7);
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
  }, [selectedDate, selectedEndDate, selectedPeriod]); // Re-calculate when date range changes

  // Use filtered data based on current selections - TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom' para usar a mesma lógica
  // useMemo para evitar re-renders desnecessários
  const filters = React.useMemo(() => ({
    date: selectedDate,
    endDate: selectedEndDate || undefined,
    projectId: projectId || "",
    period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod
  }), [selectedDate, selectedEndDate, projectId, selectedPeriod]);


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

  // Force refresh data when period changes
  React.useEffect(() => {
    if (selectedPeriod === 'today' || selectedPeriod === 'yesterday') {
      setTimeout(() => {
        refresh(filters);
      }, 500);
    }
  }, [selectedPeriod, selectedDate]);

  // Always call useSupabaseData with filters like GeneralDashboard
  const { projects, campaigns, dailyMetrics, summary, loading: dataLoading, error: dataError, refresh } = useSupabaseData(filters);

  // Get current project data from filtered data - MOVED UP to avoid initialization error
  const currentProject = useMemo(() => {
    console.log({
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

    console.log({
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
      return matches;
    });
  }, [campaigns, projectId]);

  // Set loading and error from useSupabaseData
  useEffect(() => {
    console.log({
      dataLoading,
      dataError,
      selectedDate
    });
    setLoading(dataLoading);
    setError(dataError);
  }, [dataLoading, dataError]);


  // Persist project_type change (GAM <-> ADSENSE)
  const handleProjectTypeChange = async (newType: 'GAM' | 'ADSENSE') => {
    if (!currentProject?.id || newType === currentProject.project_type) return;
    try {
      setIsUpdatingProjectType(true);
      const { error: updateError } = await supabase
        .from('projects')
        .update({ project_type: newType, updated_at: new Date().toISOString() })
        .eq('id', currentProject.id);
      if (updateError) throw updateError;

      refresh(filters);

      toast({
        title: "Tipo de projeto atualizado",
        description: `Agora este projeto é do tipo ${newType}.`,
      });
    } catch (err) {
      console.error('Error updating project_type:', err);
      const msg = err instanceof Error ? err.message : String(err);
      toast({
        title: "Erro ao alterar tipo",
        description: msg || "Tente novamente em alguns instantes",
        variant: "destructive",
      });
    } finally {
      setIsUpdatingProjectType(false);
    }
  };

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
        setSelectedEndDate("");
        setCustomDate(undefined);
        setRangeStartDate(undefined);
        setRangeEndDate(undefined);
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
        setSelectedEndDate("");
        setCustomDate(undefined);
        setRangeStartDate(undefined);
        setRangeEndDate(undefined);

        // TRATAMENTO COMO CUSTOM DATE: Force immediate refresh for yesterday data (fallback) usando 'custom' period
        setTimeout(() => {
          const yesterdayFilters = { ...filters, date: saoPauloYesterday, period: 'custom' };
          refresh(yesterdayFilters);
        }, 100);
      }
    } else if (period === 'custom') {
      // Para período customizado, não fazemos nada aqui
      // O usuário vai selecionar no calendário
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

        console.log({
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
        console.log({
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

    console.log({
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

    console.log({
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

    const filtered = projectCampaigns.filter((campaign: any) => {
      const matchesSearch = campaign.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
                           (campaign.description || '').toLowerCase().includes(searchFilter.toLowerCase());

      const campaignROAS = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
      const matchesStatus = statusFilter === "all" ||
                           (statusFilter === "critical" && campaignROAS < 0) ||
                           (statusFilter === "active" && campaign.status === "active") ||
                           (statusFilter === "paused" && campaign.status === "paused");

      return matchesSearch && matchesStatus;
    });

    return sortCampaigns(filtered, sortKey);
    } catch (error) {
      console.error('💥 Error filtering campaigns:', error);
      return [];
    }
  }, [projectCampaigns, searchFilter, statusFilter, sortKey]);

  const { comparisons: campaignComparisons, loadingComparisons } = useCampaignComparisons(
    filteredCampaigns,
    { period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod, date: selectedDate, endDate: selectedEndDate || undefined }
  );

  // Handle campaign actions
  const handleCampaignAction = useCallback((action: string, campaignId: string) => {
    console.log({
      currentProject: currentProject ? {
        id: currentProject.id,
        name: currentProject.name,
        project_type: currentProject.project_type
      } : null
    });
    console.log({
      isFunnelUrlsOpen,
      selectedCampaignForUrls
    });

    if (action === 'edit') {
      // Verificar se o projeto é do tipo ADSENSE
      const isAdSenseProject = currentProject?.project_type === 'ADSENSE';
      console.log({
        project_type: currentProject?.project_type,
        isAdSenseProject
      });

      if (isAdSenseProject) {
        // Para projetos AdSense, abrir popup de URLs do funil
        const campaign = filteredCampaigns?.find(c => c.id === campaignId);
        console.log(campaign ? {
          id: campaign.id,
          name: campaign.name,
          googleAdsCampaignId: campaign.googleAdsCampaignId
        } : 'Not found');

        if (campaign) {
          // Para projetos AdSense, usar googleAdsCampaignId se disponível, senão usar id
          const funnelCampaignId = campaign.googleAdsCampaignId || campaignId;

          const campaignData = {
            id: funnelCampaignId,
            name: campaign.name || `Campanha ${campaignId}`
          };

          setSelectedCampaignForUrls(campaignData);
          setIsFunnelUrlsOpen(true);

          // Verificar se o estado foi definido
          setTimeout(() => {
            console.log({
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
        toast({
          title: "Cadastro de Funis por URL",
          description: "Este recurso só está disponível em projetos AdSense. Em projetos GAM, o processo é feito automaticamente pelo sistema.",
          variant: "default",
        });
      }
    } else {
      // Outras ações (pause, play, etc.)
    }
  }, [currentProject, filteredCampaigns, isFunnelUrlsOpen, selectedCampaignForUrls]);

  console.log({
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
  console.log({
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
    console.log({
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

  console.log({
    currentProject: currentProject?.name,
    campaignsCount: projectCampaigns?.length,
    metricsAvailable: !!metrics
  });

  const isMobile = window.innerWidth < 768;
  
  return (
    <Layout>
      <div className={`${isMobile ? 'p-4' : 'p-6'} space-y-4 md:space-y-6 max-w-7xl mx-auto`}>
        {/* Header with User and Controls */}
        <div className="space-y-4 transition-volc duration-200">
          {/* Title Section */}
          <div className="flex items-start gap-4 reveal" style={{ ['--i' as any]: 0 }}>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate("/")}
              className="flex-shrink-0 touch-target"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Voltar ao Dashboard
            </Button>
            {/* Publicação: configura-se uma vez por site e some. Fica em
                engrenagem, com um ponto quando ainda falta resolver algo —
                o único momento em que isso merece atenção nesta página. */}
            {currentProject?.id && (
              <PublicacaoDoProjeto
                projectId={typeof currentProject.id === 'string' ? parseInt(currentProject.id, 10) : currentProject.id}
                dominioSugerido={currentProject.domain || null}
              />
            )}
            <div className="flex-1 min-w-0">
              <div className="kicker mb-2 flex items-center gap-2">
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${currentProject?.status === 'active' ? 'bg-success animate-pulse' : 'bg-warning'}`} />
                Dashboard do projeto · {filteredCampaigns.length} campanhas
              </div>
              <h1 className={`font-display font-bold tracking-tight leading-[1.05] flex items-center gap-2 ${isMobile ? 'text-2xl' : 'text-4xl'}`}>
                <span className="rounded-lg bg-primary/10 text-primary p-1.5 flex-shrink-0"><FolderOpen className={`${isMobile ? 'h-5 w-5' : 'h-6 w-6'}`} /></span>
                <span className="truncate text-foreground">{currentProject?.name || 'Carregando...'}</span>
              </h1>
              <div className="mt-3 aurora-rule w-16" />
              <p className={`text-muted-foreground ${isMobile ? 'text-sm' : ''} mt-3`}>
                Status: <span className="flex items-center gap-1 inline-flex">
                  <Circle className={`h-2 w-2 ${currentProject?.status === 'active' ? 'fill-success text-success' : 'fill-warning text-warning'}`} />
                  {currentProject?.status === 'active' ? 'Ativo' : 'Pausado'}
                </span>
                {selectedPeriod === 'custom' && selectedDate && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} text-primary`}>
                    • Data: {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}
                  </span>
                )}
                {selectedPeriod !== 'custom' && selectedPeriod !== 'range' && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} text-primary`}>
                    • Período: {selectedPeriod === 'today' ? 'Hoje' : selectedPeriod === 'yesterday' ? 'Ontem' : 'Data customizada'}
                  </span>
                )}
                {selectedPeriod === 'range' && selectedDate && selectedEndDate && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} text-primary`}>
                    • Período: {selectedDate} até {selectedEndDate} ({(() => {
                      const start = new Date(selectedDate + 'T00:00:00');
                      const end = new Date(selectedEndDate + 'T00:00:00');
                      const diffDays = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
                      return diffDays;
                    })()} dias)
                  </span>
                )}
              </p>
              <div className={`${isMobile ? 'text-xs' : 'text-sm'} text-muted-foreground flex ${isMobile ? 'flex-col' : 'items-center'} gap-2 mt-1`}>
                <span className="font-medium text-foreground/80">{currentProject?.domain}</span>
                {currentProject && (
                  <div className="flex items-center gap-1 text-xs text-gray-400 opacity-80">
                    <span>•</span>
                    <Select
                      value={currentProject.project_type || 'GAM'}
                      onValueChange={(v) => handleProjectTypeChange(v as 'GAM' | 'ADSENSE')}
                      disabled={isUpdatingProjectType}
                    >
                      <SelectTrigger
                        className="h-6 w-auto gap-1 border-0 bg-transparent px-1.5 py-0 text-xs font-medium text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus:ring-1 focus:ring-gray-300 disabled:opacity-50"
                        title="Clique para alterar o tipo de projeto"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent align="start" className="min-w-[8rem]">
                        <SelectItem value="GAM">GAM</SelectItem>
                        <SelectItem value="ADSENSE">ADSENSE</SelectItem>
                      </SelectContent>
                    </Select>
                    {isUpdatingProjectType && <RefreshCw className="h-3 w-3 animate-spin" />}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Filters and Actions Section */}
          <div className={`flex ${isMobile ? 'flex-col w-full' : 'items-center'} gap-3 flex-wrap`}>
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
                    <CalendarIcon className="h-3 w-3" />
                    Consultando data: {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}
                  </span>
                  {!loading && (!filteredCampaigns || filteredCampaigns.length === 0) && (
                    <span className="text-amber-600 flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" />
                      Sem dados
                    </span>
                  )}
                  {!loading && filteredCampaigns && filteredCampaigns.length > 0 && (
                    <span className="text-green-600 flex items-center gap-1">
                      <CheckCircle className="h-3 w-3" />
                      {filteredCampaigns.length} campanhas
                    </span>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                onClick={() => refresh(filters)}
                className="flex-shrink-0"
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
        </div>


        {/* Metrics Cards */}
        {metrics && (
          <div className="grid gap-3 md:gap-4 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
            <MetricCard
              title="Investido"
              value={formatCurrency(metrics.investment.value)}
              comparison={`Ontem: ${formatCurrency(metrics.investment.comparison)}`}
              change={metrics.investment.change}
              icon={<Coins className="h-4 w-4" />}
              color="info"
              index={1}
            />
            {/* Custom Revenue Card with organic excedent indicator */}
            <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 2 }}>
              <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10 overflow-visible">
                <div className="flex items-center gap-2">
                  <span className="kicker">
                    {currentProject?.project_type === 'ADSENSE' ? 'Revenue Total' : 'Faturado (Líquido)'}
                  </span>
                  {metrics.organicExcedent && metrics.organicExcedent.value !== 0 && (
                    <TooltipProvider delayDuration={0}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div className={`w-2 h-2 rounded-full ${
                            metrics.organicExcedent.value > 0 ? 'bg-info' : 'bg-warning'
                          } opacity-70 cursor-help`} />
                        </TooltipTrigger>
                        <TooltipContent
                          side="bottom"
                          align="start"
                          sideOffset={10}
                          alignOffset={-10}
                          className="max-w-xs p-3 z-[99999] bg-popover text-popover-foreground shadow-elevated border"
                          avoidCollisions={true}
                          collisionPadding={20}
                        >
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
                <span className="rounded-md bg-success/10 text-success p-1.5"><DollarSign className="h-4 w-4" /></span>
              </CardHeader>
              <CardContent className="relative z-10">
                <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight text-success mb-1">{formatRevenue(metrics.revenue.value)}</div>
                <div className="text-xs text-muted-foreground mb-2">{`Ontem: ${formatRevenue(metrics.revenue.comparison)}`}</div>
                <div className="flex items-center text-xs">
                  <TrendingUp className="mr-1 h-3 w-3 text-success" />
                  <span className="text-success font-medium tabular">
                    +{metrics.revenue.change.toFixed(1)}%
                  </span>
                  {metrics.organicExcedent && metrics.organicExcedent.value !== 0 && (
                    <span className={`ml-2 text-xs font-medium ${
                      metrics.organicExcedent.value > 0 ? 'text-info' : 'text-warning'
                    }`}>
                      • {metrics.organicExcedent.value > 0 ? 'Org+' : 'Org-'}{Math.abs(metrics.organicExcedent.percentage).toFixed(0)}%
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
            <MetricCard
              title="ROAS"
              value={`${metrics.roas.value.toFixed(0)}%`}
              comparison={`Ontem: ${metrics.roas.comparison.toFixed(0)}%`}
              change={metrics.roas.change}
              icon={<BarChart3 className="h-4 w-4" />}
              color="success"
              index={3}
            />
            <MetricCard
              title="L. Líquido"
              value={formatCurrency(metrics.grossProfit.value)}
              comparison={`Ontem: ${formatCurrency(metrics.grossProfit.comparison)}`}
              change={metrics.grossProfit.change}
              icon={<DollarSign className="h-4 w-4" />}
              color="success"
              index={4}
            />

            <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 5 }}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10 overflow-visible">
                <div className="flex items-center gap-2">
                  <span className="kicker">ROI Final</span>
                  <TooltipProvider delayDuration={0}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="h-3 w-3 text-muted-foreground opacity-60 hover:opacity-100 cursor-help transition-opacity" />
                      </TooltipTrigger>
                      <TooltipContent
                        side="bottom"
                        align="start"
                        sideOffset={10}
                        alignOffset={-10}
                        className="max-w-sm p-4 z-[99999] bg-popover text-popover-foreground shadow-elevated border"
                        avoidCollisions={true}
                        collisionPadding={20}
                      >
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
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><Crown className="h-4 w-4" /></span>
              </CardHeader>
              <CardContent className="relative z-10">
                <div className="font-display text-2xl md:text-3xl font-bold tabular tracking-tight mb-1">{`${metrics.roi.value.toFixed(1)}%`}</div>
                <div className="text-xs text-muted-foreground mb-2">{`Ontem: ${metrics.roi.comparison.toFixed(0)}%`}</div>
                <div className="flex items-center text-xs">
                  <TrendingUp className="mr-1 h-3 w-3 text-info" />
                  <span className="text-info font-medium tabular">
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
        <Card className="shadow-card reveal" style={{ ['--i' as any]: 6 }}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="font-display tracking-tight">Lista de Campanhas</CardTitle>
                <div className="flex items-center gap-4 mt-2">
                  <Badge variant="outline" className="text-sm">
                    {filteredCampaigns.length} {filteredCampaigns.length === 1 ? 'campanha' : 'campanhas'}
                  </Badge>
                  {projectCampaigns && projectCampaigns.length > 0 && (
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Circle className="h-2 w-2 fill-green-600 text-green-600" />
                        {projectCampaigns.filter(c => {
                          const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                          return getROASColorCategory(roasExcess) === "green";
                        }).length}
                      </span>
                      <span className="flex items-center gap-1">
                        <Circle className="h-2 w-2 fill-yellow-600 text-yellow-600" />
                        {projectCampaigns.filter(c => {
                          const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                          return getROASColorCategory(roasExcess) === "yellow";
                        }).length}
                      </span>
                      <span className="flex items-center gap-1">
                        <Circle className="h-2 w-2 fill-orange-600 text-orange-600" />
                        {projectCampaigns.filter(c => {
                          const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                          return getROASColorCategory(roasExcess) === "orange";
                        }).length}
                      </span>
                      <span className="flex items-center gap-1">
                        <Circle className="h-2 w-2 fill-red-600 text-red-600" />
                        {projectCampaigns.filter(c => {
                          const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                          return getROASColorCategory(roasExcess) === "red";
                        }).length}
                      </span>
                    </div>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <CampaignSortSelect
                  value={sortKey}
                  onChange={setSortKey}
                  className="h-9 w-40"
                />
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
                  comparison={campaignComparisons?.get(campaign.id)}
                  loadingComparisons={loadingComparisons}
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
          <Card className="shadow-card reveal" style={{ ['--i' as any]: 7 }}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 font-display tracking-tight">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><TrendingUp className="h-4 w-4" /></span>
                Histórico · {
                selectedPeriod === 'yesterday' ? 'Ontem' :
                selectedPeriod === 'range' && selectedDate && selectedEndDate ?
                  `${selectedDate} até ${selectedEndDate}` :
                `${format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })}`
              }</CardTitle>
              <div className="flex gap-2 flex-wrap mt-1">
                <Badge variant="outline" className="gap-1.5"><span className="h-2 w-2 rounded-[2px]" style={{ background: chartColor(0) }} />Receita</Badge>
                <Badge variant="outline" className="gap-1.5"><span className="h-2 w-2 rounded-[2px]" style={{ background: chartColor(1) }} />Investimento</Badge>
                <Badge variant="outline" className="gap-1.5"><span className="h-2 w-2 rounded-[2px]" style={{ background: chartColor(2) }} />ROAS</Badge>
                <Badge variant="outline" className="gap-1.5"><span className="h-2 w-2 rounded-[2px]" style={{ background: chartColor(3) }} />ROI</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={dailyMetrics}>
                  <CartesianGrid {...volcGrid} />
                  <XAxis
                    dataKey="date"
                    {...volcAxis}
                    tickFormatter={(value) => {
                      try {
                        return format(new Date(value), "dd/MM");
                      } catch {
                        return value;
                      }
                    }}
                  />
                  <YAxis {...volcAxis} />
                  <RechartsTooltip
                    cursor={volcCursor}
                    content={
                      <VolcTooltip
                        labelFormatter={(value) => {
                          try {
                            return format(new Date(value as string), "dd/MM/yyyy");
                          } catch {
                            return value;
                          }
                        }}
                        valueFormatter={(value, name) => {
                          if (name === "Receita" || name === "Investimento") {
                            return formatCurrency(Number(value));
                          }
                          return `${value}%`;
                        }}
                      />
                    }
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="revenue"
                    stroke={chartColor(0)}
                    name="Receita"
                    {...volcLine}
                  />
                  <Line
                    type="monotone"
                    dataKey="investment"
                    stroke={chartColor(1)}
                    name="Investimento"
                    {...volcLine}
                  />
                  <Line
                    type="monotone"
                    dataKey="roas"
                    stroke={chartColor(2)}
                    name="ROAS"
                    {...volcLine}
                  />
                  <Line
                    type="monotone"
                    dataKey="roi"
                    stroke={chartColor(3)}
                    name="ROI"
                    {...volcLine}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Popup de URLs do funil para projetos AdSense */}
      {(() => {
        console.log({
          selectedCampaignForUrls: !!selectedCampaignForUrls,
          isFunnelUrlsOpen,
          campaignId: selectedCampaignForUrls?.id,
          campaignName: selectedCampaignForUrls?.name
        });
        return selectedCampaignForUrls ? (
          <FunnelUrlsEditor
            isOpen={isFunnelUrlsOpen}
            onClose={() => {
              setIsFunnelUrlsOpen(false);
              setSelectedCampaignForUrls(null);
            }}
            campaignId={selectedCampaignForUrls.id}
            campaignName={selectedCampaignForUrls.name}
            onSave={() => {
              // Opcional: refresh dos dados após salvar
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