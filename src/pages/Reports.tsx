import React, { useState, useEffect, useMemo } from 'react';
import { Layout } from "@/components/layout/Layout";
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { cn } from "@/lib/utils";
import { DataStatus } from "@/components/dashboard/DataStatus";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { 
  ArrowLeft, 
  BarChart3, 
  Settings, 
  TrendingUp,
  DollarSign,
  Target,
  Users,
  Activity,
  Download,
  RefreshCw,
  Info,
  PieChart,
  Calendar as CalendarIcon,
  FolderOpen,
  Coins,
  FileText,
  Circle,
  Crown,
  Rocket
} from 'lucide-react';
import { 
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
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/hooks/use-toast';
import { format, differenceInDays } from "date-fns";
import { ptBR } from "date-fns/locale";
import { useSupabaseData, supabaseDataService, Campaign } from "@/services/supabaseDataService";
import { formatBrlCurrency, formatCostCurrency } from "@/utils/currencyUtils";
import { calculateROAS, getROASColorStyles } from "@/utils/roasCalculations";
import { taxHistoryService } from "@/services/taxHistoryService";
import { operationalCostsService } from "@/services/operationalCostsService";
import { useUserProfile } from "@/hooks/useUserProfile";
import { useUserRole } from "@/hooks/useUserRole";
import { usersService, User } from "@/services/usersService";
import { operatorReportService, OperatorDailyMetric } from "@/services/operatorReportService";
import { RevenueTooltip } from "@/components/ui/revenue-tooltip";
import jsPDF from 'jspdf';
import { chartColor, volcGrid, volcAxis, volcCursor, VolcTooltip } from "@/lib/chartTheme";

const COLORS = ['hsl(var(--success))', 'hsl(var(--info))', 'hsl(var(--warning))', 'hsl(var(--destructive))'];

// Componente SVG decorativo
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

export default function Reports() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { getUserFirstName } = useUserProfile();
  const { role } = useUserRole();

  // Estados para filtros com ONTEM adicionado
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | 'yesterday' | 'current_month' | 'last_month' | '7d' | '30d' | 'custom' | 'range'>('today');
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedEndDate, setSelectedEndDate] = useState<string>("");
  const [selectedProject, setSelectedProject] = useState("all");
  const [currentTaxRate, setCurrentTaxRate] = useState<number>(8.1);
  const [dailyOperationalCosts, setDailyOperationalCosts] = useState<number>(0);
  const [totalOperationalCosts, setTotalOperationalCosts] = useState<number>(0);
  const [operationalCostsBreakdown, setOperationalCostsBreakdown] = useState<Array<{ month: string; costs: number; days: number }>>([]);
  const [isGeneratingPDF, setIsGeneratingPDF] = useState(false);

  // Estados para o filtro por operador (admin)
  // Sentinelas usadas quando o operador não tem campanhas atribuídas:
  // arrays vazios significam "sem restrição" no supabaseDataService,
  // então forçamos valores que não casam com nada para zerar o relatório.
  const OPERATOR_NONE_CAMPAIGN = '__NONE__';
  const [operators, setOperators] = useState<User[]>([]);
  const [selectedOperator, setSelectedOperator] = useState<string>('all');
  const [operatorAssignments, setOperatorAssignments] = useState<{
    operatorId: string;
    projectIds: number[];
    campaignIds: string[];
  } | null>(null);
  const [operatorLoading, setOperatorLoading] = useState(false);
  const [operatorDailyMetrics, setOperatorDailyMetrics] = useState<OperatorDailyMetric[]>([]);

  const isOperatorFiltered = selectedOperator !== 'all';
  const selectedOperatorInfo = operators.find(op => op.id === selectedOperator);
  const operatorAssignmentsReady = !isOperatorFiltered ||
    (operatorAssignments?.operatorId === selectedOperator && !operatorLoading);
  const operatorHasNoCampaigns = isOperatorFiltered && operatorAssignmentsReady &&
    operatorAssignments?.campaignIds.includes(OPERATOR_NONE_CAMPAIGN) === true;

  // Estados para o filtro customizado da página Reports
  const [isCustomPeriodOpen, setIsCustomPeriodOpen] = useState(false);
  const [customDate, setCustomDate] = useState<Date | undefined>(undefined);
  const [rangeStartDate, setRangeStartDate] = useState<Date | undefined>(undefined);
  const [rangeEndDate, setRangeEndDate] = useState<Date | undefined>(undefined);
  const [tempCustomDate, setTempCustomDate] = useState<Date | undefined>(undefined);
  const [tempRangeStartDate, setTempRangeStartDate] = useState<Date | undefined>(undefined);
  const [tempRangeEndDate, setTempRangeEndDate] = useState<Date | undefined>(undefined);

  // Initialize with current server date
  useEffect(() => {
    const initialize = async () => {
      try {
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);

        // Load current tax rate
        const currentMonth = serverDate.substring(0, 7);
        const taxRate = await taxHistoryService.getCurrentTaxRate(currentMonth);
        setCurrentTaxRate(taxRate);

        // Load daily operational costs for current month
        const dailyCosts = await operationalCostsService.getDailyActiveCosts(currentMonth);
        setDailyOperationalCosts(dailyCosts);

        // For single day, set total costs as daily costs
        setTotalOperationalCosts(dailyCosts);

      } catch (error) {
        console.error('Error during initialization:', error);
        const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(new Date());
        setSelectedDate(saoPauloDate);
      }
    };

    initialize();
  }, []);

  // Carregar lista de operadores para o filtro do admin
  useEffect(() => {
    if (role !== 'ADMIN') return;
    usersService.getAll()
      .then(users => setOperators(users.filter(u => u.role === 'OPERATOR')))
      .catch(error => console.error('Erro ao carregar operadores:', error));
  }, [role]);

  // Carregar atribuições (projetos/campanhas exclusivas) do operador selecionado.
  // Flag de cancelamento: respostas de um operador anterior não podem
  // sobrescrever a seleção atual (troca rápida A -> B).
  useEffect(() => {
    let cancelled = false;

    const loadOperatorAssignments = async () => {
      if (selectedOperator === 'all') {
        setOperatorAssignments(null);
        return;
      }
      setOperatorLoading(true);
      try {
        const [projectIds, campaignIds] = await Promise.all([
          usersService.getUserProjects(selectedOperator),
          usersService.getUserCampaigns(selectedOperator)
        ]);
        if (cancelled) return;

        setOperatorAssignments(
          campaignIds.length > 0
            ? { operatorId: selectedOperator, projectIds, campaignIds }
            : { operatorId: selectedOperator, projectIds: [-1], campaignIds: [OPERATOR_NONE_CAMPAIGN] }
        );
      } catch (error) {
        if (cancelled) return;
        console.error('Erro ao carregar atribuições do operador:', error);
        toast({
          title: "Erro",
          description: "Não foi possível carregar as campanhas do operador selecionado.",
          variant: "destructive"
        });
        setSelectedOperator('all');
        setOperatorAssignments(null);
      } finally {
        if (!cancelled) {
          setOperatorLoading(false);
        }
      }
    };

    loadOperatorAssignments();
    return () => { cancelled = true; };
  }, [selectedOperator]);

  // Campos de filtro do operador para o useSupabaseData.
  // Enquanto as atribuições do operador selecionado ainda carregam, mantém os
  // campos anteriores para não disparar um fetch com escopo errado.
  const lastOperatorFieldsRef = React.useRef<{ userProjectIds?: number[]; userCampaignIds?: string[] }>({});
  const operatorFilterFields = React.useMemo(() => {
    if (selectedOperator === 'all') {
      lastOperatorFieldsRef.current = {};
      return {};
    }
    if (operatorAssignments?.operatorId === selectedOperator) {
      const fields = {
        ...(operatorAssignments.projectIds.length > 0 && { userProjectIds: operatorAssignments.projectIds }),
        ...(operatorAssignments.campaignIds.length > 0 && { userCampaignIds: operatorAssignments.campaignIds })
      };
      lastOperatorFieldsRef.current = fields;
      return fields;
    }
    return lastOperatorFieldsRef.current;
  }, [selectedOperator, operatorAssignments]);

  // Use filtered data based on current selections - mesma lógica do Dashboard Geral
  // TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom' para usar a mesma lógica
  // useMemo para evitar re-renders desnecessários
  const filters = React.useMemo(() => ({
    date: selectedDate,
    endDate: selectedEndDate || undefined,
    projectId: selectedProject === "all" ? undefined : selectedProject,
    period: selectedPeriod === 'yesterday' ? 'custom' : (selectedPeriod === 'current_month' || selectedPeriod === 'last_month') ? 'range' : selectedPeriod,
    ...operatorFilterFields
  }), [selectedDate, selectedEndDate, selectedProject, selectedPeriod, operatorFilterFields]);

  const { projects, campaigns, dailyMetrics, summary, loading, error, lastUpdate, refresh } = useSupabaseData(filters);

  // Série diária do operador: getDailyMetrics/getSummary do service não aplicam
  // filtros de usuário, então agregamos daily_campaign_metrics restrito às
  // campanhas do operador que estão no recorte atual (respeita filtro de projeto).
  useEffect(() => {
    let cancelled = false;

    const loadOperatorDailyMetrics = async () => {
      if (!isOperatorFiltered || operatorAssignments?.operatorId !== selectedOperator || !selectedDate) {
        setOperatorDailyMetrics([]);
        return;
      }

      const assignedSet = new Set(
        operatorAssignments.campaignIds.filter(id => id !== OPERATOR_NONE_CAMPAIGN)
      );
      const scopedCampaignIds = (campaigns || [])
        .map(c => c.id)
        .filter(id => assignedSet.has(id));

      if (scopedCampaignIds.length === 0) {
        setOperatorDailyMetrics([]);
        return;
      }

      try {
        const data = await operatorReportService.getDailyMetricsForCampaigns(
          scopedCampaignIds,
          selectedDate,
          selectedEndDate || selectedDate
        );
        if (cancelled) return;
        setOperatorDailyMetrics(data);
      } catch (error) {
        if (cancelled) return;
        console.error('Erro ao carregar métricas diárias do operador:', error);
        setOperatorDailyMetrics([]);
      }
    };

    loadOperatorDailyMetrics();
    return () => { cancelled = true; };
  }, [isOperatorFiltered, operatorAssignments, selectedOperator, campaigns, selectedDate, selectedEndDate]);

  // Load tax rate based on selected date (not current date!)
  useEffect(() => {
    const loadTaxRateForPeriod = async () => {
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
      } catch (error) {
        console.error('Error loading tax rate for period:', error);
        setCurrentTaxRate(8.1); // Fallback
      }
    };

    if (selectedDate) {
      loadTaxRateForPeriod();
    }
  }, [selectedDate, selectedEndDate, selectedPeriod]); // Update tax rate whenever date range changes

  // Update operational costs when date range changes
  useEffect(() => {
    const updateOperationalCosts = async () => {
      try {
        if (selectedPeriod === 'range' && selectedDate && selectedEndDate) {
          // Multiple months: use getCostsForDateRange
          const costsData = await operationalCostsService.getCostsForDateRange(selectedDate, selectedEndDate);
          setTotalOperationalCosts(costsData.totalCosts);
          setDailyOperationalCosts(costsData.dailyAverage);
          setOperationalCostsBreakdown(costsData.monthlyBreakdown);

          console.log('Custos operacionais para range:', {
            startDate: selectedDate,
            endDate: selectedEndDate,
            totalCosts: costsData.totalCosts,
            dailyAverage: costsData.dailyAverage,
            numberOfDays: costsData.numberOfDays,
            breakdown: costsData.monthlyBreakdown
          });
        } else if (selectedDate) {
          // Single day: use getDailyActiveCosts
          const currentMonth = selectedDate.substring(0, 7);
          const dailyCosts = await operationalCostsService.getDailyActiveCosts(currentMonth);
          setDailyOperationalCosts(dailyCosts);
          setTotalOperationalCosts(dailyCosts);
          setOperationalCostsBreakdown([{ month: currentMonth, costs: dailyCosts, days: 1 }]);

          console.log('Custos operacionais para dia único:', {
            date: selectedDate,
            month: currentMonth,
            dailyCosts
          });
        }
      } catch (error) {
        console.error('Error updating operational costs:', error);
      }
    };

    updateOperationalCosts();
  }, [selectedDate, selectedEndDate, selectedPeriod]);


  // Funções de cálculo - versão correta
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

    // Se um projeto específico está selecionado, usar seu revenue share específico
    if (selectedProject !== 'all') {
      const specificProject = projects.find(p => p.id === selectedProject);
      if (specificProject) {
        const projectRevshare = specificProject.revshare || 0.1;
        const totalRevenueShareAmount = totalRevenue * projectRevshare;

        console.log({
          projectName: specificProject.name,
          projectRevshare: (projectRevshare * 100).toFixed(1) + '%',
          totalRevenue,
          totalRevenueShareAmount
        });

        return { 
          percentage: projectRevshare, 
          amount: totalRevenueShareAmount 
        };
      }
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
    operationalCostsTotal: number = 0
  ) => {
    // Cálculo simplificado: já temos o faturamento líquido (após revenue share)
    const grossProfit = totalRevenueAfterRevshare - totalInvestment;
    const taxAmount = totalRevenueAfterRevshare * (taxRate / 100);
    const netProfitBeforeCosts = grossProfit - taxAmount;
    const netProfit = netProfitBeforeCosts - operationalCostsTotal;

    return {
      netRevenue: totalRevenueAfterRevshare,
      grossProfit,
      taxAmount,
      totalOperationalCosts: operationalCostsTotal,
      netProfit,
      formula: `Faturamento Líquido (${totalRevenueAfterRevshare.toFixed(2)}) - Investimento (${totalInvestment.toFixed(2)}) - Impostos (${taxAmount.toFixed(2)}) - Custos Op. (${operationalCostsTotal.toFixed(2)}) = ${netProfit.toFixed(2)}`
    };
  };

  // Função para calcular número de dias baseado no período selecionado
  const calculateNumberOfDays = () => {
    if (selectedPeriod === 'range' && selectedDate && selectedEndDate) {
      const startDate = new Date(selectedDate);
      const endDate = new Date(selectedEndDate);
      return Math.abs(differenceInDays(endDate, startDate)) + 1; // +1 para incluir ambos os dias
    } else if (selectedPeriod === 'custom' && selectedDate) {
      return 1; // Um dia específico
    } else if (selectedPeriod === 'today') {
      return 1;
    } else if (selectedPeriod === '7d') {
      return 7;
    } else if (selectedPeriod === '30d') {
      return 30;
    }
    return 1; // Fallback
  };

  // Função para determinar cores do ROI
  const getROIColor = (roasExcess: number) => {
    return getROASColorStyles(roasExcess);
  };

  // Dados processados para relatórios
  const reportData = useMemo(() => {
    if (!summary || !projects) return null;

    const formatDay = (dateStr: string) => format(new Date(dateStr + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR });
    const periodLabel = (() => {
      if (selectedPeriod === 'range' && selectedDate && selectedEndDate) {
        return selectedDate === selectedEndDate
          ? formatDay(selectedDate)
          : `${formatDay(selectedDate)} a ${formatDay(selectedEndDate)}`;
      }
      if (selectedPeriod === 'custom' && selectedDate) return formatDay(selectedDate);
      if (selectedPeriod === 'today') return 'Hoje';
      if (selectedPeriod === 'yesterday') return 'Ontem';
      if (selectedPeriod === 'current_month') return 'Mês atual';
      if (selectedPeriod === 'last_month') return 'Mês anterior';
      if (selectedPeriod === '7d') return 'Últimos 7 dias';
      return 'Últimos 30 dias';
    })();

    // Recorte por operador: getSummary é global (não aplica filtros de usuário),
    // então os totais são recalculados a partir das campanhas exclusivas do operador.
    // Custos operacionais (fixos da empresa) não entram no recorte por operador.
    if (isOperatorFiltered) {
      const assignedSet = new Set(
        (operatorAssignments?.operatorId === selectedOperator ? operatorAssignments.campaignIds : [])
          .filter(id => id !== OPERATOR_NONE_CAMPAIGN)
      );
      const operatorCampaigns = (campaigns || [])
        .filter(c => assignedSet.has(c.id))
        .sort((a, b) => (b.revenue || 0) - (a.revenue || 0));

      const totalInvestment = operatorCampaigns.reduce((sum, c) => sum + (c.investment || 0), 0);
      const netRevenue = operatorCampaigns.reduce((sum, c) => sum + (c.revenue || 0), 0);
      const taxes = netRevenue * (currentTaxRate / 100);
      const netProfit = netRevenue - totalInvestment - taxes;
      const finalRoi = totalInvestment > 0 ? (netProfit / totalInvestment) * 100 : 0;

      const byProject = new Map<string, { investment: number; revenue: number; campaignCount: number }>();
      operatorCampaigns.forEach(c => {
        const acc = byProject.get(c.projectId) ?? { investment: 0, revenue: 0, campaignCount: 0 };
        acc.investment += c.investment || 0;
        acc.revenue += c.revenue || 0;
        acc.campaignCount += 1;
        byProject.set(c.projectId, acc);
      });
      const operatorProjects = Array.from(byProject.entries()).map(([projectId, metrics]) => {
        const projectInfo = projects.find(p => p.id === projectId);
        return {
          id: projectId,
          name: projectInfo?.name || `Projeto ${projectId}`,
          domain: projectInfo?.domain || projectInfo?.name || `Projeto ${projectId}`,
          investment: metrics.investment,
          revenue: metrics.revenue,
          roas: metrics.investment > 0 ? calculateROAS(metrics.revenue, metrics.investment) : 0,
          roi: metrics.investment > 0 ? ((metrics.revenue - metrics.investment) / metrics.investment) * 100 : 0,
          campaignCount: metrics.campaignCount
        };
      }).sort((a, b) => (b.revenue || 0) - (a.revenue || 0));

      return {
        period: periodLabel,
        operator: selectedOperatorInfo
          ? { id: selectedOperatorInfo.id, name: selectedOperatorInfo.name || selectedOperatorInfo.email, email: selectedOperatorInfo.email }
          : null,
        summary: {
          totalInvestment,
          totalRevenue: netRevenue,
          totalRevenueAfterRevshare: netRevenue, // Campaign.revenue já é líquido (revenue_converted_revshare)
          grossProfit: netRevenue - totalInvestment,
          taxes,
          netProfit,
          averageRoas: totalInvestment > 0 ? calculateROAS(netRevenue, totalInvestment) : 0,
          finalRoi,
          campaignCount: operatorCampaigns.length,
          projectCount: operatorProjects.length,
          operationalCostsBreakdown: [] as Array<{ month: string; costs: number; days: number }>
        },
        projects: operatorProjects,
        operatorCampaigns
      };
    }

    // Usar a nova fórmula correta para calcular lucro líquido com revenue share real
    const totalRevenue = summary.totalRevenue || 0;
    const totalInvestment = summary.totalInvestment || 0;

    // NEW: Usar cálculo simplificado com valores pré-calculados e custos operacionais totais
    const simplifiedCalculation = calculateSimplifiedNetProfit(
      (summary as any).totalRevenueAfterRevshare || totalRevenue, // Usar valor direto - já vem com revshare aplicado
      totalInvestment,
      currentTaxRate,
      totalOperationalCosts // Usar o valor total já calculado
    );
    const netProfit = simplifiedCalculation.netProfit;
    const finalROI = totalInvestment > 0 ? (netProfit / totalInvestment) * 100 : 0;

    return {
      period: periodLabel,
      operator: null,
      summary: {
        totalInvestment: summary.totalInvestment || 0,
        totalRevenue: summary.totalRevenue || 0,
        totalRevenueAfterRevshare: (summary as any).totalRevenueAfterRevshare || 0, // Incluir campo que estava faltando
        grossProfit: summary.totalProfit || 0,
        taxes: (summary.totalProfit || 0) * (currentTaxRate / 100),
        netProfit,
        averageRoas: summary.generalRoas || 0,
        finalRoi: finalROI,
        campaignCount: campaigns?.length || 0,
        projectCount: projects?.length || 0,
        operationalCostsBreakdown // Add breakdown for display
      },
      projects: projects.map(project => ({
        ...project,
        roas: project.revenue && project.investment ? calculateROAS(project.revenue, project.investment) : 0,
        roi: project.revenue && project.investment ? ((project.revenue - project.investment) / project.investment) * 100 : 0,
        campaignCount: campaigns?.filter(c => c.projectId === project.id).length || 0
      })).sort((a, b) => (b.revenue || 0) - (a.revenue || 0)),
      operatorCampaigns: [] as Campaign[]
    };
  }, [summary, projects, campaigns, selectedPeriod, selectedDate, selectedEndDate, currentTaxRate, totalOperationalCosts, operationalCostsBreakdown, isOperatorFiltered, operatorAssignments, selectedOperator, selectedOperatorInfo]);

  // Chart data for performance visualization - adaptado baseado no filtro
  const chartData = useMemo(() => {
    // Recorte por operador: dailyMetrics é global, usar a série agregada
    // de daily_campaign_metrics restrita às campanhas do operador
    if (isOperatorFiltered) {
      return operatorDailyMetrics.map(metric => ({
        date: format(new Date(metric.date + 'T12:00:00'), 'dd/MM', { locale: ptBR }),
        investment: metric.investment,
        revenue: metric.revenue,
        roas: metric.investment > 0 ? calculateROAS(metric.revenue, metric.investment) : 0,
        roi: 0
      }));
    }

    // Se for hoje ou ontem (período único), mostrar apenas dados sintéticos baseados no summary
    if (selectedPeriod === 'today' || selectedPeriod === 'yesterday') {
      if (summary && (summary.totalInvestment > 0 || summary.totalRevenue > 0)) {
        return [{
          date: selectedPeriod === 'today' ? 'Hoje' : 'Ontem',
          investment: summary.totalInvestment || 0,
          revenue: summary.totalRevenue || 0,
          roas: summary.totalInvestment && summary.totalRevenue ? calculateROAS(summary.totalRevenue, summary.totalInvestment) : 0,
          roi: summary.finalRoi || 0
        }];
      }
      return [];
    }

    // Para períodos múltiplos (custom, range), mostrar dailyMetrics
    if (!dailyMetrics || dailyMetrics.length === 0) return [];

    return dailyMetrics.map(metric => ({
      date: format(new Date(metric.date), 'dd/MM', { locale: ptBR }),
      investment: metric.investment || 0,
      revenue: metric.revenue || 0,
      roas: metric.revenue && metric.investment ? calculateROAS(metric.revenue, metric.investment) : 0,
      roi: metric.roi || 0
    }));
  }, [dailyMetrics, selectedPeriod, summary, isOperatorFiltered, operatorDailyMetrics]);

  // Project distribution data for pie chart
  const projectDistributionData = useMemo(() => {
    if (!reportData?.projects) return [];
    
    return reportData.projects.slice(0, 5).map((project, index) => ({
      name: project.domain || project.name,
      value: project.revenue || 0,
      color: COLORS[index % COLORS.length]
    }));
  }, [reportData]);

  const handlePeriodChange = async (period: 'today' | 'yesterday' | 'current_month' | 'last_month' | '7d' | '30d' | 'custom' | 'range') => {
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
    } else if (period === 'yesterday') {
      try {
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        // Calculate yesterday from server date
        const serverDateObj = new Date(serverDate + 'T00:00:00-03:00'); // São Paulo timezone
        const yesterdayObj = new Date(serverDateObj);
        yesterdayObj.setDate(yesterdayObj.getDate() - 1);
        const yesterdayStr = yesterdayObj.toISOString().split('T')[0];

        // Manter selectedPeriod como 'yesterday' para visualização front
        setSelectedDate(yesterdayStr);
        setSelectedEndDate("");
        setCustomDate(undefined);
        setRangeStartDate(undefined);
        setRangeEndDate(undefined);

        // TRATAMENTO COMO CUSTOM DATE: Force immediate refresh for yesterday data usando 'custom' period
        setTimeout(() => {
          const yesterdayFilters = {
            date: yesterdayStr,
            endDate: undefined,
            projectId: selectedProject === "all" ? undefined : selectedProject,
            period: 'custom',
            ...operatorFilterFields
          };
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

        // Manter selectedPeriod como 'yesterday' para visualização front
        setSelectedDate(saoPauloYesterday);
        setSelectedEndDate("");
        setCustomDate(undefined);
        setRangeStartDate(undefined);
        setRangeEndDate(undefined);

        // TRATAMENTO COMO CUSTOM DATE: Force immediate refresh for yesterday data (fallback) usando 'custom' period
        setTimeout(() => {
          const yesterdayFilters = {
            date: saoPauloYesterday,
            endDate: undefined,
            projectId: selectedProject === "all" ? undefined : selectedProject,
            period: 'custom',
            ...operatorFilterFields
          };
          refresh(yesterdayFilters);
        }, 100);
      }
    } else if (period === 'current_month') {
      try {
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        const serverDateObj = new Date(serverDate + 'T00:00:00-03:00');
        const firstDay = new Date(serverDateObj.getFullYear(), serverDateObj.getMonth(), 1);
        const lastDay = new Date(serverDateObj.getFullYear(), serverDateObj.getMonth() + 1, 0);

        const fmt = (d: Date) => new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo',
          year: 'numeric', month: '2-digit', day: '2-digit'
        }).format(d);

        const startStr = fmt(firstDay);
        const endStr = fmt(lastDay);

        setSelectedDate(startStr);
        setSelectedEndDate(endStr);
        setCustomDate(undefined);
        setRangeStartDate(firstDay);
        setRangeEndDate(lastDay);

        setTimeout(() => {
          const monthFilters = {
            date: startStr,
            endDate: endStr,
            projectId: selectedProject === "all" ? undefined : selectedProject,
            period: 'range' as const,
            ...operatorFilterFields
          };
          refresh(monthFilters);
        }, 100);
      } catch (error) {
        console.error('Error getting server date for current month:', error);
        const now = new Date();
        const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
        const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        const fmt = (d: Date) => new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo',
          year: 'numeric', month: '2-digit', day: '2-digit'
        }).format(d);
        setSelectedDate(fmt(firstDay));
        setSelectedEndDate(fmt(lastDay));
        setRangeStartDate(firstDay);
        setRangeEndDate(lastDay);
      }
    } else if (period === 'last_month') {
      try {
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        const serverDateObj = new Date(serverDate + 'T00:00:00-03:00');
        const firstDay = new Date(serverDateObj.getFullYear(), serverDateObj.getMonth() - 1, 1);
        const lastDay = new Date(serverDateObj.getFullYear(), serverDateObj.getMonth(), 0);

        const fmt = (d: Date) => new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo',
          year: 'numeric', month: '2-digit', day: '2-digit'
        }).format(d);

        const startStr = fmt(firstDay);
        const endStr = fmt(lastDay);

        setSelectedDate(startStr);
        setSelectedEndDate(endStr);
        setCustomDate(undefined);
        setRangeStartDate(firstDay);
        setRangeEndDate(lastDay);

        setTimeout(() => {
          const monthFilters = {
            date: startStr,
            endDate: endStr,
            projectId: selectedProject === "all" ? undefined : selectedProject,
            period: 'range' as const,
            ...operatorFilterFields
          };
          refresh(monthFilters);
        }, 100);
      } catch (error) {
        console.error('Error getting server date for last month:', error);
        const now = new Date();
        const firstDay = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        const lastDay = new Date(now.getFullYear(), now.getMonth(), 0);
        const fmt = (d: Date) => new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo',
          year: 'numeric', month: '2-digit', day: '2-digit'
        }).format(d);
        setSelectedDate(fmt(firstDay));
        setSelectedEndDate(fmt(lastDay));
        setRangeStartDate(firstDay);
        setRangeEndDate(lastDay);
      }
    } else if (period === 'custom') {
      // Para período customizado, não fazemos nada aqui
      // O usuário vai selecionar no calendário
    }
  };

  // Função para aplicar mudanças do filtro customizado
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
    setSelectedDate(startDate);
    setSelectedEndDate(endDate);
    setSelectedPeriod('range');
    
    const newFilters = {
      date: startDate,
      endDate: endDate,
      projectId: selectedProject === "all" ? undefined : selectedProject,
      period: 'range' as const,
      ...operatorFilterFields
    };
    setTimeout(() => {
      refresh(newFilters);
    }, 100);
  };

  const handleRefresh = () => {
    refresh(filters);
    toast({
      title: "Atualizado",
      description: "Dados do relatório atualizados com sucesso!",
    });
  };

  const handleExportPDF = async () => {
    if (!reportData) {
      toast({
        title: "Erro",
        description: "Dados do relatório não disponíveis para exportação.",
        variant: "destructive"
      });
      return;
    }

    if (loading || !operatorAssignmentsReady) {
      toast({
        title: "Aguarde",
        description: "Os dados do relatório ainda estão sendo carregados.",
      });
      return;
    }

    setIsGeneratingPDF(true);
    try {
      const pdf = new jsPDF('p', 'mm', 'a4');
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 15;
      let yPosition = margin;

      // Título do relatório
      pdf.setFontSize(16);
      pdf.setFont('helvetica', 'bold');
      pdf.text('Relatório de Performance', margin, yPosition);
      yPosition += 10;

      // Período
      pdf.setFontSize(12);
      pdf.setFont('helvetica', 'normal');
      pdf.text(`Período: ${reportData.period}`, margin, yPosition);
      yPosition += 8;

      if (selectedProject !== 'all') {
        const projectName = projects?.find(p => p.id === selectedProject)?.name || 'Projeto Selecionado';
        pdf.text(`Projeto: ${projectName}`, margin, yPosition);
        yPosition += 8;
      }

      if (isOperatorFiltered) {
        const operatorName = reportData.operator?.name || selectedOperatorInfo?.name || selectedOperatorInfo?.email || 'Operador';
        pdf.text(`Operador: ${operatorName}`, margin, yPosition);
        yPosition += 8;
      }

      yPosition += 5;

      // Resumo Geral
      pdf.setFontSize(14);
      pdf.setFont('helvetica', 'bold');
      pdf.text('Resumo Geral', margin, yPosition);
      yPosition += 8;

      pdf.setFontSize(10);
      pdf.setFont('helvetica', 'normal');

      const summaryData = [
        ['Total Investido', formatCostCurrency(reportData.summary.totalInvestment)],
        ['Total Faturado (Líquido)', formatBrlCurrency(reportData.summary.totalRevenueAfterRevshare || reportData.summary.totalRevenue)],
        ['Lucro Líquido', formatCostCurrency(reportData.summary.netProfit)],
        ['ROAS Médio', `${reportData.summary.averageRoas.toFixed(1)}%`],
        ['ROI Final', `${reportData.summary.finalRoi.toFixed(1)}%`],
        ['Projetos', reportData.summary.projectCount.toString()],
        ['Campanhas', reportData.summary.campaignCount.toString()]
      ];

      summaryData.forEach(([label, value]) => {
        pdf.text(`${label}:`, margin, yPosition);
        pdf.text(value, margin + 60, yPosition);
        yPosition += 6;
      });

      if (isOperatorFiltered) {
        yPosition += 2;
        pdf.setFontSize(8);
        pdf.setFont('helvetica', 'italic');
        pdf.text(
          `Impostos de ${currentTaxRate.toFixed(2)}% sobre o faturamento líquido. Custos operacionais não aplicados no recorte por operador.`,
          margin,
          yPosition
        );
        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        yPosition += 6;
      }

      yPosition += 10;

      // Tabela de Projetos
      if (reportData.projects.length > 0) {
        pdf.setFontSize(14);
        pdf.setFont('helvetica', 'bold');
        pdf.text('Performance por Projeto', margin, yPosition);
        yPosition += 8;

        // Cabeçalho da tabela
        pdf.setFontSize(9);
        pdf.setFont('helvetica', 'bold');

        const colWidths = [60, 35, 35, 25, 25];
        const headers = ['Projeto', 'Investimento', 'Revenue', 'ROAS', 'Campanhas'];

        let xPosition = margin;
        headers.forEach((header, index) => {
          pdf.text(header, xPosition, yPosition);
          xPosition += colWidths[index];
        });
        yPosition += 6;

        // Linha separadora
        pdf.line(margin, yPosition - 2, pageWidth - margin, yPosition - 2);
        yPosition += 2;

        // Dados dos projetos
        pdf.setFont('helvetica', 'normal');
        reportData.projects.forEach((project) => {
          // Verificar se precisa de nova página
          if (yPosition > pageHeight - 30) {
            pdf.addPage();
            yPosition = margin;
          }

          xPosition = margin;
          const projectData = [
            project.domain || project.name || '',
            formatCostCurrency(project.investment || 0),
            formatBrlCurrency(project.revenue || 0),
            `${project.roas.toFixed(1)}%`,
            project.campaignCount.toString()
          ];

          projectData.forEach((data, index) => {
            // Truncar texto se muito longo
            const truncatedData = data.length > 15 ? data.substring(0, 12) + '...' : data;
            pdf.text(truncatedData, xPosition, yPosition);
            xPosition += colWidths[index];
          });
          yPosition += 5;
        });
      }

      // Tabela de Campanhas do Operador (apenas no recorte por operador)
      if (isOperatorFiltered && reportData.operatorCampaigns.length > 0) {
        yPosition += 10;
        if (yPosition > pageHeight - 60) {
          pdf.addPage();
          yPosition = margin;
        }

        pdf.setFontSize(14);
        pdf.setFont('helvetica', 'bold');
        pdf.text('Campanhas do Operador', margin, yPosition);
        yPosition += 8;

        pdf.setFontSize(9);
        pdf.setFont('helvetica', 'bold');

        const campColWidths = [75, 30, 30, 20, 25];
        const campHeaders = ['Campanha', 'Investimento', 'Revenue', 'ROAS', 'Status'];

        let campX = margin;
        campHeaders.forEach((header, index) => {
          pdf.text(header, campX, yPosition);
          campX += campColWidths[index];
        });
        yPosition += 6;

        pdf.line(margin, yPosition - 2, pageWidth - margin, yPosition - 2);
        yPosition += 2;

        pdf.setFont('helvetica', 'normal');
        reportData.operatorCampaigns.forEach((campaign) => {
          if (yPosition > pageHeight - 30) {
            pdf.addPage();
            yPosition = margin;
          }

          campX = margin;
          const campaignData = [
            campaign.name || campaign.id,
            formatCostCurrency(campaign.investment || 0),
            formatBrlCurrency(campaign.revenue || 0),
            `${(campaign.roas || 0).toFixed(1)}%`,
            campaign.status === 'active' ? 'Ativa' : 'Pausada'
          ];

          campaignData.forEach((data, index) => {
            const maxLength = index === 0 ? 42 : 15;
            const truncatedData = data.length > maxLength ? data.substring(0, maxLength - 3) + '...' : data;
            pdf.text(truncatedData, campX, yPosition);
            campX += campColWidths[index];
          });
          yPosition += 5;
        });
      }

      // Rodapé
      yPosition = pageHeight - 20;
      pdf.setFontSize(8);
      pdf.setFont('helvetica', 'normal');
      pdf.text(`Gerado em: ${new Date().toLocaleString('pt-BR')}`, margin, yPosition);
      pdf.text('Sistema VOLC O.S. - Relatórios', pageWidth - margin - 50, yPosition);

      // Generate filename
      const reportDate = new Date().toLocaleDateString('pt-BR');
      const periodText = selectedPeriod === 'today' ? 'hoje' :
                        selectedPeriod === 'yesterday' ? 'ontem' :
                        selectedPeriod === 'current_month' ? 'mes-atual' :
                        selectedPeriod === 'last_month' ? 'mes-anterior' :
                        selectedPeriod === '7d' ? '7dias' :
                        selectedPeriod === '30d' ? '30dias' :
                        selectedPeriod === 'range' ? 'periodo' : selectedPeriod;

      const operatorSlug = isOperatorFiltered
        ? `operador-${(reportData.operator?.name || 'operador')
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '')}_`
        : '';

      const fileName = `relatorio_${operatorSlug}${periodText}_${reportDate.replace(/\//g, '-')}.pdf`;
      pdf.save(fileName);

      toast({
        title: "PDF Gerado",
        description: `Relatório "${fileName}" exportado com sucesso!`,
      });
    } catch (error) {
      console.error('Erro ao gerar PDF:', error);
      toast({
        title: "Erro",
        description: `Falha ao gerar relatório PDF: ${error?.message || 'Erro desconhecido'}`,
        variant: "destructive"
      });
    } finally {
      setIsGeneratingPDF(false);
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-screen">
          <LoadingSpinner size="lg" text="Gerando relatório..." />
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="flex flex-col items-center justify-center min-h-screen p-8">
          <div className="text-center">
            <Activity className="h-16 w-16 text-destructive mx-auto mb-4" />
            <h1 className="text-2xl font-bold mb-2">Erro ao carregar relatório</h1>
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

  const isMobile = window.innerWidth < 768;
  
  return (
    <Layout>
      <div className={`${isMobile ? 'p-4' : 'p-6'} space-y-6 md:space-y-8 max-w-7xl mx-auto`}>
        {/* Header with User and Controls */}
        <div className="space-y-4 transition-volc duration-200">
          {/* Title Section */}
          <div className="flex items-start gap-3 reveal" style={{ ['--i' as any]: 0 }}>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(-1)}
              className="flex-shrink-0 gap-2 touch-target"
            >
              <ArrowLeft className="h-4 w-4" />
              Voltar
            </Button>
            <div className="flex-1 min-w-0">
              <div className="kicker mb-2 flex items-center gap-2">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary" />
                Relatórios · Performance e ROI
              </div>
              <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-3`}>
                <h1 className={`font-display font-bold tracking-tight leading-[1.05] ${isMobile ? 'text-2xl' : 'text-4xl'}`}>
                  <span className="text-foreground">Relatórios</span>
                </h1>
                {!isMobile && (
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-card border border-border shadow-card flex-shrink-0">
                    <span className="h-6 w-6 rounded-md bg-primary/10 text-primary flex items-center justify-center">
                      <Settings className="h-3.5 w-3.5" />
                    </span>
                    <span className="text-sm font-medium">{getUserFirstName()}</span>
                  </div>
                )}
              </div>
              <div className="mt-3 aurora-rule w-16" />
              {isMobile && (
                <div className="mt-3 flex items-center gap-2 px-3 py-1.5 rounded-full bg-card border border-border shadow-card w-fit">
                  <span className="h-5 w-5 rounded-md bg-primary/10 text-primary flex items-center justify-center">
                    <Settings className="h-3 w-3" />
                  </span>
                  <span className="text-sm font-medium">{getUserFirstName()}</span>
                </div>
              )}
              <p className="mt-3 text-muted-foreground text-sm">
                Relatórios detalhados de performance e ROI
              </p>
            </div>
          </div>
          
          {/* Filters and Actions Section */}
          <div className={`flex ${isMobile ? 'flex-col w-full' : 'items-center'} gap-3 flex-wrap`}>
            
            <Select value={selectedProject} onValueChange={setSelectedProject}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Filtrar projeto" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">
                  <span className="flex items-center gap-2">
                    <FolderOpen className="h-4 w-4" />
                    Todos os Projetos
                  </span>
                </SelectItem>
                {projects?.map(project => (
                  <SelectItem key={project.id} value={project.id}>
                    {project.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Filtro por Operador (admin) */}
            {role === 'ADMIN' && (
              <Select value={selectedOperator} onValueChange={setSelectedOperator}>
                <SelectTrigger className="w-52">
                  <SelectValue placeholder="Filtrar operador" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">
                    <span className="flex items-center gap-2">
                      <Users className="h-4 w-4" />
                      Todos os Operadores
                    </span>
                  </SelectItem>
                  {operators.map(operator => (
                    <SelectItem key={operator.id} value={operator.id}>
                      {operator.name || operator.email}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}

            {/* Filtro de Período Customizado para Reports */}
            <div className="flex items-center gap-2">
              <Select value={selectedPeriod === 'today' ? 'today' : selectedPeriod === 'yesterday' ? 'yesterday' : selectedPeriod === 'current_month' ? 'current_month' : selectedPeriod === 'last_month' ? 'last_month' : 'custom'} onValueChange={(value) => {
                if (value === 'today') {
                  handlePeriodChange('today');
                } else if (value === 'yesterday') {
                  handlePeriodChange('yesterday');
                } else if (value === 'current_month') {
                  handlePeriodChange('current_month');
                } else if (value === 'last_month') {
                  handlePeriodChange('last_month');
                } else {
                  setSelectedPeriod('custom');
                }
              }}>
                <SelectTrigger className="w-44">
                  <CalendarIcon className="h-4 w-4 mr-2" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="today">
                    <span className="flex items-center gap-2">
                      <CalendarIcon className="h-4 w-4" />
                      Hoje
                    </span>
                  </SelectItem>
                  <SelectItem value="yesterday">
                    <span className="flex items-center gap-2">
                      <CalendarIcon className="h-4 w-4" />
                      Ontem
                    </span>
                  </SelectItem>
                  <SelectItem value="current_month">
                    <span className="flex items-center gap-2">
                      <CalendarIcon className="h-4 w-4" />
                      Mês atual
                    </span>
                  </SelectItem>
                  <SelectItem value="last_month">
                    <span className="flex items-center gap-2">
                      <CalendarIcon className="h-4 w-4" />
                      Mês anterior
                    </span>
                  </SelectItem>
                  <SelectItem value="custom">
                    <span className="flex items-center gap-2">
                      <CalendarIcon className="h-4 w-4" />
                      Selecionar período
                    </span>
                  </SelectItem>
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
                        <div className="mt-2 p-2 bg-primary/5 rounded border border-primary/20">
                          <p className="text-xs font-medium text-foreground">
                            {tempRangeStartDate && tempRangeEndDate ? (
                              <>
                                <BarChart3 className="h-4 w-4 mr-1" />
                                {format(tempRangeStartDate, "dd/MM/yyyy", { locale: ptBR })} até {format(tempRangeEndDate, "dd/MM/yyyy", { locale: ptBR })}
                              </>
                            ) : tempCustomDate ? (
                              <>
                                <CalendarIcon className="h-4 w-4 mr-1" />
                                {format(tempCustomDate, "dd/MM/yyyy", { locale: ptBR })}
                              </>
                            ) : null}
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">Clique em "Aplicar" para confirmar</p>
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
            
            <div className="flex items-center gap-2 flex-wrap">
              <Button onClick={handleRefresh} variant="outline" size="sm" className="flex-shrink-0">
                <RefreshCw className="h-4 w-4 mr-2" />
                Atualizar
              </Button>

              <Button
                onClick={handleExportPDF}
                variant="default"
                size="sm"
                disabled={isGeneratingPDF || loading || !operatorAssignmentsReady}
                className="flex-shrink-0"
              >
                <Download className={`h-4 w-4 mr-2 ${isGeneratingPDF ? 'animate-spin' : ''}`} />
                {isGeneratingPDF ? 'Gerando PDF...' : 'Exportar PDF'}
              </Button>
              
              <DataStatus 
                loading={loading} 
                error={error} 
                lastUpdate={lastUpdate}
                showDetails={true}
              />
            </div>
          </div>
        </div>

        {/* Banner do filtro por operador */}
        {isOperatorFiltered && (
          <Card className="p-3 bg-primary/5 border-primary/20 shadow-card">
            <div className="flex items-center gap-2 text-sm flex-wrap">
              <span className="rounded-md bg-primary/10 text-primary p-1.5 flex-shrink-0"><Users className="h-4 w-4" /></span>
              <span className="font-medium">Relatório filtrado por operador:</span>
              <Badge variant="outline" className="border-primary/40 text-primary">
                {selectedOperatorInfo?.name || selectedOperatorInfo?.email || 'Operador'}
              </Badge>
              {!operatorAssignmentsReady ? (
                <span className="text-muted-foreground">Carregando campanhas do operador...</span>
              ) : operatorHasNoCampaigns ? (
                <span className="text-destructive font-medium">Este operador não possui campanhas atribuídas.</span>
              ) : (
                <span className="text-muted-foreground">
                  {reportData?.summary.campaignCount ?? 0} campanhas exclusivas · custos operacionais não aplicados
                </span>
              )}
            </div>
          </Card>
        )}

        {/* Summary Cards */}
        {reportData && (
          <>
            <div className="grid gap-4 md:gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 transition-volc duration-200">
              <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 1 }}>
                <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
                <CardDecoration color="hsl(var(--info))" />
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
                  <span className="kicker">Total investido</span>
                  <span className="rounded-md bg-info/10 text-info p-1.5"><Coins className="h-4 w-4" /></span>
                </CardHeader>
                <CardContent className="relative z-10">
                  <div className="font-display text-2xl font-bold tabular tracking-tight">
                    {formatCostCurrency(reportData.summary.totalInvestment)}
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    {selectedPeriod === 'range' && selectedDate && selectedEndDate ? (
                      <>
                        {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM', { locale: ptBR })} a {format(new Date(selectedEndDate + 'T12:00:00'), 'dd/MM', { locale: ptBR })}
                        ({(() => {
                          const start = new Date(selectedDate + 'T00:00:00');
                          const end = new Date(selectedEndDate + 'T00:00:00');
                          const diffDays = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
                          return diffDays;
                        })()} dias)
                      </>
                    ) : reportData.period}
                  </p>
                </CardContent>
              </Card>

              <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 2 }}>
                <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
                <CardDecoration color="hsl(var(--success))" />
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
                  <span className="kicker">Total faturado (líquido)</span>
                  <span className="rounded-md bg-success/10 text-success p-1.5"><TrendingUp className="h-4 w-4" /></span>
                </CardHeader>
                <CardContent className="relative z-10">
                  <RevenueTooltip
                    netRevenue={reportData.summary.totalRevenueAfterRevshare || reportData.summary.totalRevenue}
                    revsharePercentage={0.1}
                    projectType="GAM" // Reports agregados: deixar como GAM para compatibilidade
                  >
                    <div className="font-display text-2xl font-bold tabular tracking-tight text-success">
                      {formatBrlCurrency(reportData.summary.totalRevenueAfterRevshare || reportData.summary.totalRevenue)}
                    </div>
                  </RevenueTooltip>
                  <p className="text-xs text-muted-foreground mt-2">Revenue líquido via UTM</p>
                </CardContent>
              </Card>

              <Card className="relative overflow-hidden group reveal hover-lift" style={{ ['--i' as any]: 3 }}>
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
                        <TooltipContent 
                          side="left" 
                          className="max-w-sm p-4 !z-[99999]" 
                          style={{ zIndex: 99999, position: 'fixed' }}
                        >
                          <div className="space-y-2 text-sm">
                            <div className="font-medium text-success mb-2 flex items-center gap-2">
                              <Circle className="h-4 w-4 fill-success" />
                              Cálculo do Lucro Líquido
                            </div>
                            {(() => {
                              const totalRevenue = reportData.summary.totalRevenue;
                              const totalInvestment = reportData.summary.totalInvestment;

                              // NEW: Usar cálculo simplificado com valores pré-calculados
                              // No recorte por operador, custos operacionais (fixos da empresa) não se aplicam
                              const calculation = calculateSimplifiedNetProfit(
                                reportData?.summary?.totalRevenueAfterRevshare || totalRevenue, // Usar valor direto - já vem com revshare aplicado
                                totalInvestment,
                                currentTaxRate,
                                isOperatorFiltered ? 0 : totalOperationalCosts
                              );

                              return (
                                <div className="space-y-1">
                                  <div className="flex justify-between">
                                    <span className="text-muted-foreground">Faturamento Líquido (após Rev Share):</span>
                                    <span className="font-mono text-primary">{formatBrlCurrency(calculation.netRevenue)}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-muted-foreground">Investimento:</span>
                                    <span className="font-mono text-destructive">-{formatCostCurrency(totalInvestment)}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-muted-foreground">Impostos SN ({currentTaxRate.toFixed(2)}%):</span>
                                    <span className="font-mono text-destructive">-{formatCostCurrency(calculation.taxAmount)}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-muted-foreground">
                                      Custos Operacionais{isOperatorFiltered ? ' (não aplicados por operador)' : ''}:
                                    </span>
                                    <span className="font-mono text-destructive">-{formatCostCurrency(calculation.totalOperationalCosts)}</span>
                                  </div>
                                  {!isOperatorFiltered && operationalCostsBreakdown.length > 1 && (
                                    <div className="ml-4 text-xs space-y-0.5 text-muted-foreground">
                                      {operationalCostsBreakdown.map((item, idx) => (
                                        <div key={idx} className="flex justify-between">
                                          <span>• {item.month} ({item.days} {item.days === 1 ? 'dia' : 'dias'}):</span>
                                          <span className="font-mono">-{formatCostCurrency(item.costs)}</span>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                  <div className="border-t pt-1 border-success/30">
                                    <div className="flex justify-between font-medium">
                                      <span>Lucro Líquido:</span>
                                      <span className="font-mono text-success">{formatCostCurrency(calculation.netProfit)}</span>
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
                  <div className="font-display text-2xl font-bold tabular tracking-tight text-success">
                    {formatCostCurrency(reportData.summary.netProfit)}
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Após {currentTaxRate.toFixed(2)}% SN{isOperatorFiltered ? ' · sem custos operacionais' : ''}
                  </p>
                </CardContent>
              </Card>

              <Card style={{ ['--i' as any]: 4 }} className={`relative overflow-hidden group reveal hover-lift ${getROIColor(reportData.summary.averageRoas)}`}>
                <CardDecoration color="hsl(var(--primary))" />
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
                  <span className="kicker">ROI final</span>
                  <span className="rounded-md bg-primary/10 text-primary p-1.5"><Target className="h-4 w-4" /></span>
                </CardHeader>
                <CardContent className="relative z-10">
                  <div className="font-display text-2xl font-bold tabular tracking-tight">
                    {reportData.summary.finalRoi.toFixed(1)}%
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    ROAS: {reportData.summary.averageRoas.toFixed(1)}%
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Performance Charts */}
            {chartData.length > 0 && (
              <div className="grid gap-4 md:gap-6 grid-cols-1 lg:grid-cols-2">
                <Card className="shadow-card">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <span className="rounded-md bg-primary/10 text-primary p-1.5"><BarChart3 className="h-4 w-4" /></span>
                      Investimento vs Revenue
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={chartData}>
                        <CartesianGrid {...volcGrid} />
                        <XAxis dataKey="date" {...volcAxis} />
                        <YAxis {...volcAxis} />
                        <RechartsTooltip
                          content={<VolcTooltip valueFormatter={(v) => formatBrlCurrency(Number(v))} />}
                          cursor={{ fill: 'hsl(var(--muted))', fillOpacity: 0.4 }}
                        />
                        <Bar dataKey="investment" fill={chartColor(0)} name="Investimento" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="revenue" fill={chartColor(1)} name="Revenue" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {projectDistributionData.length > 0 && (
                  <Card className="shadow-card">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <span className="rounded-md bg-primary/10 text-primary p-1.5"><PieChart className="h-4 w-4" /></span>
                        Distribuição por Projeto
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={300}>
                        <RechartsPieChart>
                          <Pie
                            data={projectDistributionData}
                            cx="50%"
                            cy="50%"
                            labelLine={false}
                            label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                            outerRadius={80}
                            fill={chartColor(0)}
                            dataKey="value"
                          >
                            {projectDistributionData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={chartColor(index)} />
                            ))}
                          </Pie>
                          <RechartsTooltip
                            content={<VolcTooltip valueFormatter={(v) => formatBrlCurrency(Number(v))} />}
                          />
                        </RechartsPieChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}

            {/* Projects Breakdown */}
            {reportData.projects.length > 0 && (
              <Card className="shadow-card">
                <CardHeader className="flex flex-row items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <span className="rounded-md bg-primary/10 text-primary p-1.5"><Users className="h-4 w-4" /></span>
                      Performance por Projeto
                    </CardTitle>
                    <p className="text-muted-foreground text-sm mt-1">
                      Detalhamento de {reportData.projects.length} projetos no período
                      {isOperatorFiltered ? ' · valores apenas das campanhas do operador' : ''}
                    </p>
                  </div>
                  <Badge variant="outline">
                    {reportData.summary.campaignCount} campanhas ativas
                  </Badge>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto -mx-4 md:mx-0 px-4 md:px-0">
                    <table className="w-full min-w-[600px] md:min-w-0">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left p-3 kicker">Projeto</th>
                          <th className="text-left p-3 kicker">Investimento</th>
                          <th className="text-left p-3 kicker">Revenue</th>
                          <th className="text-left p-3 kicker">ROAS</th>
                          <th className="text-left p-3 kicker">Campanhas</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reportData.projects.map((project, index) => (
                          <tr key={project.id} className="border-b border-border hover:bg-muted/40 transition-colors cursor-pointer" onClick={() => navigate(`/dashboard/project/${project.id}`)}>
                            <td className="p-3">
                              <div className="flex items-center gap-3">
                                <div className="h-8 w-8 bg-primary/10 text-primary rounded-md flex items-center justify-center font-display font-bold text-xs tabular">
                                  {index + 1}
                                </div>
                                <div>
                                  <p className="font-medium text-primary hover:text-primary/80 transition-colors">{project.domain}</p>
                                  <p className="text-xs text-muted-foreground">{project.name}</p>
                                </div>
                              </div>
                            </td>
                            <td className="p-3">
                              <div className="font-display font-bold tabular" data-numeric>
                                {formatCostCurrency(project.investment || 0)}
                              </div>
                            </td>
                            <td className="p-3">
                              <div className="font-display font-bold tabular text-success" data-numeric>
                                {formatBrlCurrency(project.revenue || 0)}
                              </div>
                            </td>
                            <td className="p-3">
                              <div className={`inline-flex px-3 py-1 rounded-full border font-bold tabular ${getROIColor(project.roas)}`} data-numeric>
                                {project.roas.toFixed(1)}%
                              </div>
                            </td>
                            <td className="p-3">
                              <Badge variant="outline" className="tabular">
                                {project.campaignCount}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Campanhas do Operador */}
            {isOperatorFiltered && reportData.operatorCampaigns.length > 0 && (
              <Card className="shadow-card">
                <CardHeader className="flex flex-row items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <span className="rounded-md bg-primary/10 text-primary p-1.5"><Activity className="h-4 w-4" /></span>
                      Performance por Campanha
                    </CardTitle>
                    <p className="text-muted-foreground text-sm mt-1">
                      Campanhas atribuídas a {reportData.operator?.name || 'operador'} no período
                    </p>
                  </div>
                  <Badge variant="outline">
                    {reportData.operatorCampaigns.length} campanhas
                  </Badge>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto -mx-4 md:mx-0 px-4 md:px-0">
                    <table className="w-full min-w-[600px] md:min-w-0">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left p-3 kicker">Campanha</th>
                          <th className="text-left p-3 kicker">Investimento</th>
                          <th className="text-left p-3 kicker">Revenue</th>
                          <th className="text-left p-3 kicker">ROAS</th>
                          <th className="text-left p-3 kicker">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reportData.operatorCampaigns.map((campaign) => (
                          <tr
                            key={campaign.id}
                            className="border-b border-border hover:bg-muted/40 transition-colors cursor-pointer"
                            onClick={() => navigate(`/dashboard/campaign/${campaign.id}`)}
                          >
                            <td className="p-3">
                              <p className="font-medium text-primary hover:text-primary/80 transition-colors">{campaign.name}</p>
                              <p className="text-xs text-muted-foreground">ID: {campaign.id}</p>
                            </td>
                            <td className="p-3">
                              <div className="font-display font-bold tabular" data-numeric>
                                {formatCostCurrency(campaign.investment || 0)}
                              </div>
                            </td>
                            <td className="p-3">
                              <div className="font-display font-bold tabular text-success" data-numeric>
                                {formatBrlCurrency(campaign.revenue || 0)}
                              </div>
                            </td>
                            <td className="p-3">
                              <div className={`inline-flex px-3 py-1 rounded-full border font-bold tabular ${getROIColor(campaign.roas || 0)}`} data-numeric>
                                {(campaign.roas || 0).toFixed(1)}%
                              </div>
                            </td>
                            <td className="p-3">
                              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${campaign.status === 'active' ? 'bg-success/12 text-success' : 'bg-muted text-muted-foreground'}`}>
                                {campaign.status === 'active' ? 'Ativa' : 'Pausada'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Report Summary Info */}
            <Card className="mt-6 p-4 bg-muted/30 border-border shadow-card">
              <h3 className="font-display font-semibold mb-3 flex items-center gap-2">
                <span className="rounded-md bg-primary/10 text-primary p-1.5"><FileText className="h-4 w-4" /></span>
                Resumo do Relatório · {reportData.period}
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-muted-foreground">
                <div className="space-y-2">
                  <p className="flex items-center gap-2">
                    <BarChart3 className="h-4 w-4" />
                    <strong>Tipo:</strong> {isOperatorFiltered ? `Por Operador — ${reportData.operator?.name || ''}` : 'Consolidado'}
                  </p>
                  <p className="flex items-center gap-2">
                    <Target className="h-4 w-4" />
                    <strong>Projetos:</strong> {reportData.summary.projectCount}
                  </p>
                </div>
                <div className="space-y-2">
                  <p className="flex items-center gap-2">
                    <CalendarIcon className="h-4 w-4" />
                    <strong>Período:</strong> {reportData.period}
                  </p>
                  <p className="flex items-center gap-2">
                    <Activity className="h-4 w-4" />
                    <strong>Campanhas:</strong> {reportData.summary.campaignCount}
                  </p>
                </div>
                <div className="space-y-2">
                  <RevenueTooltip
                    netRevenue={reportData.summary.totalRevenueAfterRevshare || reportData.summary.totalRevenue}
                    revsharePercentage={0.1}
                    projectType="GAM" // Reports agregados: deixar como GAM para compatibilidade
                  >
                    <p className="flex items-center gap-2">
                      <DollarSign className="h-4 w-4" />
                      <strong>Revenue Total (Líquido):</strong> {formatBrlCurrency(reportData.summary.totalRevenueAfterRevshare || reportData.summary.totalRevenue)}
                    </p>
                  </RevenueTooltip>
                  <p className="flex items-center gap-2">
                    <Coins className="h-4 w-4" />
                    <strong>Investimento:</strong> {formatCostCurrency(reportData.summary.totalInvestment)}
                  </p>
                </div>
                <div className="space-y-2">
                  <p className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4" />
                    <strong>ROAS Médio:</strong> {reportData.summary.averageRoas.toFixed(1)}%
                  </p>
                  <p className="flex items-center gap-2">
                    <Crown className="h-4 w-4" />
                    <strong>ROI Final:</strong> {reportData.summary.finalRoi.toFixed(1)}%
                  </p>
                </div>
              </div>
            </Card>
          </>
        )}
      </div>
    </Layout>
  );
}