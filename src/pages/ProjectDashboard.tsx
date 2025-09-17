import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { DateFilter } from "@/components/dashboard/DateFilter";
import { DataStatus } from "@/components/dashboard/DataStatus";
import {
  ArrowLeft,
  RefreshCw,
  Search,
  Download,
  Plus,
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
import { operationalCostsService } from "@/services/operationalCostsService";
import { taxHistoryService } from "@/services/taxHistoryService";
import { useCurrencyConverter } from "@/services/currencyConversionService";
import { formatBrlCurrency, formatCostCurrency, preloadExchangeRate } from "@/utils/currencyUtils";
import { format, differenceInDays } from "date-fns";
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

// Campaign Card Component
const CampaignCard = ({ 
  campaign, 
  onAction, 
  formatRevenue
}: { 
  campaign: any; 
  onAction: (action: string, campaignId: string) => void;
  formatRevenue: (brl: number) => string;
}) => {
  const getStatusColor = (roasStandard: number) => {
    if (roasStandard >= 50) return "success";   // 50% return over investment
    if (roasStandard >= 0) return "warning";    // Break-even or positive
    return "danger";                            // Loss
  };

  const getStatusIcon = (roasStandard: number) => {
    if (roasStandard >= 50) return "🟢";   // Good return
    if (roasStandard >= 0) return "🟡";    // Break-even or small profit
    return "🔴";                           // Loss
  };

  const calculatedROAS = campaign.investment > 0 ? ((campaign.revenue - campaign.investment) / campaign.investment) * 100 : 0;
  const isCritical = calculatedROAS < 0;  // Checking for loss

  return (
    <Card className={cn(
      "animate-fade-in hover:shadow-lg transition-all duration-300",
      isCritical && "border-destructive/40 bg-destructive/5"
    )}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{getStatusIcon(calculatedROAS)}</span>
            <div>
              <h3 className="font-semibold text-sm">{campaign.name}</h3>
              <p className="text-xs text-muted-foreground">{campaign.description}</p>
            </div>
          </div>
          {isCritical && (
            <AlertTriangle className="h-4 w-4 text-destructive" />
          )}
        </div>

        <div className="grid grid-cols-3 gap-4 mb-3">
          <div>
            <p className="text-xs text-muted-foreground">Investido</p>
            <p className="font-semibold">R$ {campaign.investment.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Faturado (Líquido)</p>
            <p className="font-semibold">{formatRevenue(campaign.revenue || 0)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">ROAS</p>
            <Badge variant={getStatusColor(calculatedROAS)}>
              {Math.round(calculatedROAS)}%
            </Badge>
          </div>
        </div>

        <div className="flex items-center justify-end text-xs text-muted-foreground mb-3">
          <span>👁️ {campaign.views || Math.floor(Math.random() * 1000 + 100)} views</span>
        </div>

        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              console.log("🖱️ Button clicked! Campaign ID:", campaign.id);
              console.log("🖱️ onAction function:", typeof onAction);
              onAction("edit", campaign.id);
            }}
            className="flex-1"
          >
            <Edit className="h-3 w-3 mr-1" />
            Editar
          </Button>
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
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | '7d' | '30d' | 'custom' | 'range'>('today');
  const [selectedDate, setSelectedDate] = useState<string>(""); // Will be set dynamically
  const [selectedEndDate, setSelectedEndDate] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentTaxRate, setCurrentTaxRate] = useState<number>(8.1);
  const [dailyOperationalCosts, setDailyOperationalCosts] = useState<number>(0);

  // Estados para o filtro customizado - mesma lógica de Reports
  const [isCustomPeriodOpen, setIsCustomPeriodOpen] = useState(false);
  const [customDate, setCustomDate] = useState<Date | undefined>(undefined);
  const [rangeStartDate, setRangeStartDate] = useState<Date | undefined>(undefined);
  const [rangeEndDate, setRangeEndDate] = useState<Date | undefined>(undefined);
  const [tempCustomDate, setTempCustomDate] = useState<Date | undefined>(undefined);
  const [tempRangeStartDate, setTempRangeStartDate] = useState<Date | undefined>(undefined);
  const [tempRangeEndDate, setTempRangeEndDate] = useState<Date | undefined>(undefined);
  
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

  // Use filtered data based on current selections - same approach as Reports
  const filters = {
    date: selectedDate,
    endDate: selectedEndDate || undefined,
    projectId: projectId || "",
    period: selectedPeriod
  };

  console.log('🔍 ProjectDashboard: selectedEndDate:', selectedEndDate);

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


  // Handle period changes - mesma lógica de Reports
  const handlePeriodChange = async (period: 'today' | '7d' | '30d' | 'custom' | 'range') => {
    setSelectedPeriod(period);
    if (period === 'today') {
      try {
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
    } else if (period === 'custom') {
      // Para período customizado, não fazemos nada aqui
      // O usuário vai selecionar no calendário
    }
  };

  // Função para aplicar mudanças do filtro customizado - mesma lógica de Reports
  const handleApplyCustomPeriod = () => {
    if (tempRangeStartDate && tempRangeEndDate) {
      // Range selecionado
      setRangeStartDate(tempRangeStartDate);
      setRangeEndDate(tempRangeEndDate);
      setCustomDate(undefined);
      setSelectedPeriod('range');

      const startDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      }).format(tempRangeStartDate);

      const endDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      }).format(tempRangeEndDate);

      setSelectedDate(startDate);
      setSelectedEndDate(endDate);
      handleDateRangeChange(startDate, endDate);
    } else if (tempCustomDate) {
      // Data única selecionada - também usar 'range' com mesma data de início e fim
      setCustomDate(tempCustomDate);
      setRangeStartDate(tempCustomDate);
      setRangeEndDate(tempCustomDate);
      setSelectedPeriod('range'); // Mudança aqui: usar 'range' em vez de 'custom'

      const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      }).format(tempCustomDate);

      setSelectedDate(saoPauloDate);
      setSelectedEndDate(saoPauloDate); // Mudança aqui: usar a mesma data como endDate

      // Usar handleDateRangeChange com a mesma data para início e fim
      handleDateRangeChange(saoPauloDate, saoPauloDate);
    }

    setIsCustomPeriodOpen(false);
  };

  const handleDateRangeChange = (startDate: string, endDate: string) => {
    console.log('🔄 ProjectDashboard handleDateRangeChange called with:', { startDate, endDate });
    setSelectedDate(startDate);
    setSelectedEndDate(endDate);
    setSelectedPeriod('range');

    const newFilters = {
      date: startDate,
      endDate: endDate,
      projectId: projectId || "",
      period: 'range' as const
    };
    console.log('🔄 ProjectDashboard: Refreshing with range filters:', newFilters);
    console.log('🔄 ProjectDashboard: About to call refresh with filters');
    setTimeout(() => {
      refresh(newFilters);
    }, 100);
  };


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

    if (selectedPeriod === 'today') {
      daysInPeriod = 1;
    } else if (selectedPeriod === '7d') {
      daysInPeriod = 7;
    } else if (selectedPeriod === '30d') {
      daysInPeriod = 30;
    } else if (selectedPeriod === 'range' && selectedDate && selectedEndDate) {
      const start = new Date(selectedDate);
      const end = new Date(selectedEndDate);
      daysInPeriod = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
    }

    // Retornar custos operacionais proporcionais aos dias
    return dailyOperationalCosts * daysInPeriod;
  }, [currentProject, dailyOperationalCosts, selectedPeriod, selectedDate, selectedEndDate]);

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


  // Calculate corrected net profit with real revenue share
  const calculateCorrectNetProfit = useCallback((revenueBrl: number, spendBrl: number) => {
    try {
      if (!currentProject || typeof revenueBrl !== 'number' || typeof spendBrl !== 'number') {
        return revenueBrl - spendBrl;
      }

      const projectRevshare = currentProject.revshare || 0.1;
      const liquidRevenue = revenueBrl - (revenueBrl * projectRevshare);
      const netProfit = liquidRevenue - spendBrl;

      return isNaN(netProfit) ? 0 : netProfit;
    } catch (error) {
      console.error('💥 Error in calculateCorrectNetProfit:', error);
      return 0;
    }
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
    
    // For ADSENSE projects, revenue comes from daily_project_metrics (already included in currentProject.revenue)
    // For GAM projects, revenue comes from campaign aggregation
    const projectRevenue = currentProject?.project_type === 'ADSENSE' 
      ? currentProject.revenue || 0 
      : projectCampaigns.reduce((sum, c) => sum + (c.revenue || 0), 0);
    
    console.log('🎯 Revenue calculation method:', {
      projectType: currentProject?.project_type,
      isAdSense: currentProject?.project_type === 'ADSENSE',
      projectRevenue,
      source: currentProject?.project_type === 'ADSENSE' ? 'daily_project_metrics (via currentProject.revenue)' : 'daily_campaign_metrics (aggregated campaigns)'
    });
    const projectProfit = calculateSimplifiedNetProfit(projectRevenue, projectInvestment).netProfit; // Lucro líquido com impostos e custos
    const projectRoas = projectInvestment > 0 ? ((projectRevenue - projectInvestment) / projectInvestment) * 100 : 0; // ROAS padrão: excesso sobre investimento
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
      }
    };
    } catch (error) {
      console.error('💥 Error calculating metrics:', error);
      return null;
    }
  }, [currentProject, projectCampaigns, summary]);

  // Filter campaigns
  const filteredCampaigns = useMemo(() => {
    try {
    if (!projectCampaigns) return [];

    return projectCampaigns.filter((campaign: any) => {
      const matchesSearch = campaign.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
                           (campaign.description || '').toLowerCase().includes(searchFilter.toLowerCase());

      const campaignROAS = campaign.investment > 0 ? ((campaign.revenue - campaign.investment) / campaign.investment) * 100 : 0;
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
                    • Período: {selectedPeriod === 'today' ? 'Hoje' : selectedPeriod === '7d' ? '7 dias' : '30 dias'}
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
            {/* Filtro de Período Customizado - igual ao Reports */}
            <div className="flex items-center gap-2">
              <Select value={selectedPeriod === 'today' ? 'today' : 'custom'} onValueChange={(value) => {
                if (value === 'today') {
                  handlePeriodChange('today');
                } else {
                  setSelectedPeriod('custom');
                }
              }}>
                <SelectTrigger className="w-40">
                  <CalendarIcon className="h-4 w-4 mr-2" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="today">📅 Hoje</SelectItem>
                  <SelectItem value="custom">🗓️ Selecionar período</SelectItem>
                </SelectContent>
              </Select>

              {(selectedPeriod === 'custom' || selectedPeriod === 'range') && (
                <Popover open={isCustomPeriodOpen} onOpenChange={(open) => {
                  setIsCustomPeriodOpen(open);
                  if (open) {
                    // Reset temporary states to current values when opening
                    setTempCustomDate(customDate);
                    setTempRangeStartDate(rangeStartDate);
                    setTempRangeEndDate(rangeEndDate);
                  }
                }}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className={cn(
                        "w-[320px] justify-start text-left font-normal",
                        (!customDate && !rangeStartDate) && "text-muted-foreground"
                      )}
                    >
                      <CalendarIcon className="mr-2 h-4 w-4" />
                      {rangeStartDate && rangeEndDate ? (
                        <>
                          {format(rangeStartDate, "dd/MM/yyyy", { locale: ptBR })}
                          {" até "}
                          {format(rangeEndDate, "dd/MM/yyyy", { locale: ptBR })}
                          <span className="ml-2 text-xs text-muted-foreground">
                            ({differenceInDays(rangeEndDate, rangeStartDate) + 1} dias)
                          </span>
                        </>
                      ) : customDate ? (
                        format(customDate, "dd/MM/yyyy", { locale: ptBR })
                      ) : (
                        <span>Selecionar período</span>
                      )}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <div className="p-3 border-b">
                      <h4 className="font-medium text-sm">Selecionar período</h4>
                      <p className="text-xs text-muted-foreground mt-1">
                        Clique em uma data para dia específico, ou selecione intervalo
                      </p>
                      {(tempCustomDate || (tempRangeStartDate && tempRangeEndDate)) && (
                        <div className="mt-2 p-2 bg-blue-50 rounded border border-blue-200">
                          <p className="text-xs font-medium text-blue-800">
                            {tempRangeStartDate && tempRangeEndDate ? (
                              <>📊 {format(tempRangeStartDate, "dd/MM/yyyy", { locale: ptBR })} até {format(tempRangeEndDate, "dd/MM/yyyy", { locale: ptBR })}</>
                            ) : tempCustomDate ? (
                              <>📅 {format(tempCustomDate, "dd/MM/yyyy", { locale: ptBR })}</>
                            ) : null}
                          </p>
                          <p className="text-xs text-blue-600 mt-1">Clique em "Aplicar" para confirmar</p>
                </div>
                      )}
                    </div>
                    <Calendar
                      mode="range"
                      selected={{
                        from: tempRangeStartDate || tempCustomDate,
                        to: tempRangeEndDate
                      }}
                      onSelect={(dates) => {
                        if (dates?.from && dates?.to) {
                          // Range selecionado (temporário)
                          setTempRangeStartDate(dates.from);
                          setTempRangeEndDate(dates.to);
                          setTempCustomDate(undefined);
                        } else if (dates?.from && !dates?.to) {
                          // Data única selecionada (temporário)
                          setTempCustomDate(dates.from);
                          setTempRangeStartDate(undefined);
                          setTempRangeEndDate(undefined);
                        }
                      }}
                      disabled={(date) =>
                        date > new Date() || date < new Date("1900-01-01")
                      }
                      locale={ptBR}
                      initialFocus
                      numberOfMonths={2}
                    />
                    <div className="p-3 border-t">
                      <div className="flex gap-2 mb-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="flex-1"
                          onClick={async () => {
                            try {
                              const serverDate = await supabaseDataService.getServerDate();
                              const today = new Date(serverDate + 'T12:00:00');
                              setTempCustomDate(today);
                              setTempRangeStartDate(undefined);
                              setTempRangeEndDate(undefined);
                            } catch (error) {
                              const today = new Date();
                              setTempCustomDate(today);
                              setTempRangeStartDate(undefined);
                              setTempRangeEndDate(undefined);
                            }
                          }}
                        >
                          Hoje
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="flex-1"
                          onClick={async () => {
                            try {
                              const serverDate = await supabaseDataService.getServerDate();
                              const today = new Date(serverDate + 'T12:00:00');
                              const lastWeek = new Date(today);
                              lastWeek.setDate(lastWeek.getDate() - 6);
                              setTempRangeStartDate(lastWeek);
                              setTempRangeEndDate(today);
                              setTempCustomDate(undefined);
                            } catch (error) {
                              const today = new Date();
                              const lastWeek = new Date(today);
                              lastWeek.setDate(lastWeek.getDate() - 6);
                              setTempRangeStartDate(lastWeek);
                              setTempRangeEndDate(today);
                              setTempCustomDate(undefined);
                            }
                          }}
                        >
                          Últimos 7 dias
                        </Button>
                      </div>
                      <Button
                        size="sm"
                        className="w-full"
                        onClick={handleApplyCustomPeriod}
                        disabled={!tempCustomDate && !tempRangeStartDate}
                      >
                        Aplicar
                      </Button>
                    </div>
                  </PopoverContent>
                </Popover>
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
            <MetricCard
              title="💵 Faturado (Líquido)"
              value={formatRevenue(metrics.revenue.value)}
              comparison={`Ontem: ${formatRevenue(metrics.revenue.comparison)}`}
              change={metrics.revenue.change}
              icon={<DollarSign />}
              color="success"
            />
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
                                  <span className="text-muted-foreground">Faturamento Líquido:</span>
                                  <span className="font-mono text-blue-600">{formatRevenue(calculation.netRevenue)}</span>
                                </div>
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
              <CardTitle>Lista de Campanhas</CardTitle>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline">
                  <Download className="h-4 w-4 mr-2" />
                  Exportar
                </Button>
                <Button size="sm">
                  <Plus className="h-4 w-4 mr-2" />
                  Nova Campanha
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-1">
              {filteredCampaigns?.map((campaign: any) => (
                <CampaignCard
                  key={campaign.id}
                  campaign={campaign}
                  onAction={handleCampaignAction}
                  formatRevenue={formatRevenue}
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
                selectedPeriod === '7d' ? 'Últimos 7 dias' :
                selectedPeriod === '30d' ? 'Últimos 30 dias' :
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