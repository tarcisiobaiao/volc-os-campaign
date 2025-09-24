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
  Calendar as CalendarIcon
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
import { useSupabaseData, supabaseDataService } from "@/services/supabaseDataService";
import { formatBrlCurrency, formatCostCurrency } from "@/utils/currencyUtils";
import { calculateROAS, getROASColorStyles } from "@/utils/roasCalculations";
import { taxHistoryService } from "@/services/taxHistoryService";
import { operationalCostsService } from "@/services/operationalCostsService";
import { useUserProfile } from "@/hooks/useUserProfile";
import { RevenueTooltip } from "@/components/ui/revenue-tooltip";
import jsPDF from 'jspdf';

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
  
  // Estados para filtros com ONTEM adicionado
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range'>('today');
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedEndDate, setSelectedEndDate] = useState<string>("");
  const [selectedProject, setSelectedProject] = useState("all");
  const [currentTaxRate, setCurrentTaxRate] = useState<number>(8.1);
  const [dailyOperationalCosts, setDailyOperationalCosts] = useState<number>(0);
  const [isGeneratingPDF, setIsGeneratingPDF] = useState(false);
  
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

        // Load daily operational costs
        const dailyCosts = await operationalCostsService.getDailyActiveCosts(currentMonth);
        setDailyOperationalCosts(dailyCosts);
        
        console.log('📊 Reports initialized with server date:', serverDate);
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

  // Use filtered data based on current selections - mesma lógica do Dashboard Geral
  // TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom' para usar a mesma lógica
  const filters = {
    date: selectedDate,
    endDate: selectedEndDate || undefined,
    projectId: selectedProject === "all" ? undefined : selectedProject,
    period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod
  };

  const { projects, campaigns, dailyMetrics, summary, loading, error, lastUpdate, refresh } = useSupabaseData(filters);

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
        
        console.log('📊 Revenue Share Calculation (Specific Project):', {
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

    console.log('📊 Revenue Share Calculation (All Projects):', {
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
    dailyOperationalCosts: number = 0,
    numberOfDays: number = 1
  ) => {
    // Cálculo simplificado: já temos o faturamento líquido (após revenue share)
    const grossProfit = totalRevenueAfterRevshare - totalInvestment;
    const taxAmount = totalRevenueAfterRevshare * (taxRate / 100);
    const totalOperationalCosts = dailyOperationalCosts * numberOfDays;
    const netProfitBeforeCosts = grossProfit - taxAmount;
    const netProfit = netProfitBeforeCosts - totalOperationalCosts;

    return {
      netRevenue: totalRevenueAfterRevshare,
      grossProfit,
      taxAmount,
      dailyOperationalCosts,
      totalOperationalCosts,
      numberOfDays,
      netProfit,
      formula: `Faturamento Líquido (${totalRevenueAfterRevshare.toFixed(2)}) - Investimento (${totalInvestment.toFixed(2)}) - Impostos (${taxAmount.toFixed(2)}) - Custos Op. (${dailyOperationalCosts.toFixed(2)} × ${numberOfDays} dias = ${totalOperationalCosts.toFixed(2)}) = ${netProfit.toFixed(2)}`
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

    // Usar a nova fórmula correta para calcular lucro líquido com revenue share real
    const totalRevenue = summary.totalRevenue || 0;
    const totalInvestment = summary.totalInvestment || 0;
    
    // NEW: Usar cálculo simplificado com valores pré-calculados
    const numberOfDays = calculateNumberOfDays();
    const simplifiedCalculation = calculateSimplifiedNetProfit(
      (summary as any).totalRevenueAfterRevshare || totalRevenue, // Usar valor direto - já vem com revshare aplicado
      totalInvestment,
      currentTaxRate,
      dailyOperationalCosts,
      numberOfDays
    );
    const netProfit = simplifiedCalculation.netProfit;
    const finalROI = totalInvestment > 0 ? (netProfit / totalInvestment) * 100 : 0;

    return {
      period: selectedPeriod === 'custom' 
        ? format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy', { locale: ptBR })
        : selectedPeriod === 'today' ? 'Hoje' : selectedPeriod === '7d' ? 'Últimos 7 dias' : 'Últimos 30 dias',
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
        projectCount: projects?.length || 0
      },
      projects: projects.map(project => ({
        ...project,
        roas: project.revenue && project.investment ? calculateROAS(project.revenue, project.investment) : 0,
        roi: project.revenue && project.investment ? ((project.revenue - project.investment) / project.investment) * 100 : 0,
        campaignCount: campaigns?.filter(c => c.projectId === project.id).length || 0
      })).sort((a, b) => (b.revenue || 0) - (a.revenue || 0))
    };
  }, [summary, projects, campaigns, selectedPeriod, selectedDate, currentTaxRate]);

  // Chart data for performance visualization - adaptado baseado no filtro
  const chartData = useMemo(() => {
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
  }, [dailyMetrics, selectedPeriod, summary]);

  // Project distribution data for pie chart
  const projectDistributionData = useMemo(() => {
    if (!reportData?.projects) return [];
    
    return reportData.projects.slice(0, 5).map((project, index) => ({
      name: project.domain || project.name,
      value: project.revenue || 0,
      color: COLORS[index % COLORS.length]
    }));
  }, [reportData]);

  const handlePeriodChange = async (period: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range') => {
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
            period: 'custom'
          };
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
            period: 'custom'
          };
          console.log('🔄 Forcing immediate refresh for yesterday AS CUSTOM (fallback):', yesterdayFilters);
          refresh(yesterdayFilters);
        }, 100);
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
    console.log('🔄 handleDateRangeChange called with:', { startDate, endDate });
    setSelectedDate(startDate);
    setSelectedEndDate(endDate);
    setSelectedPeriod('range');
    
    const newFilters = { 
      date: startDate,
      endDate: endDate,
      projectId: selectedProject === "all" ? undefined : selectedProject, 
      period: 'range' as const
    };
    console.log('🔄 Refreshing with range filters:', newFilters);
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

      // Rodapé
      yPosition = pageHeight - 20;
      pdf.setFontSize(8);
      pdf.setFont('helvetica', 'normal');
      pdf.text(`Gerado em: ${new Date().toLocaleString('pt-BR')}`, margin, yPosition);
      pdf.text('Sistema Webgo - Relatórios', pageWidth - margin - 50, yPosition);

      // Generate filename
      const reportDate = new Date().toLocaleDateString('pt-BR');
      const periodText = selectedPeriod === 'today' ? 'hoje' :
                        selectedPeriod === '7d' ? '7dias' :
                        selectedPeriod === '30d' ? '30dias' :
                        selectedPeriod === 'range' ? 'periodo' : selectedPeriod;

      const fileName = `relatorio_${periodText}_${reportDate.replace(/\//g, '-')}.pdf`;
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

  return (
    <Layout>
      <div className="p-6 space-y-8 max-w-7xl mx-auto">
        {/* Header with User and Controls */}
        <div className="flex items-center justify-between transition-all duration-300">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate(-1)}
                className="gap-2"
              >
                <ArrowLeft className="h-4 w-4" />
                Voltar
              </Button>
              <h1 className="text-3xl font-bold bg-gradient-to-r from-primary via-purple-600 to-blue-600 bg-clip-text text-transparent">
                Relatórios
              </h1>
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-gradient-to-r from-primary/10 to-purple-500/10 border border-primary/20">
                <Settings className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium text-primary">{getUserFirstName()}</span>
              </div>
            </div>
            <p className="text-muted-foreground">
              Relatórios detalhados de performance e ROI
              {selectedProject !== 'all' && (
                <span className="ml-2 text-primary">
                  • Projeto: {projects?.find(p => p.id === selectedProject)?.name || 'Selecionado'}
                </span>
              )}
              {selectedPeriod === 'custom' && (
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
          </div>
          
          <div className="flex items-center gap-3 flex-wrap">
            
            <Select value={selectedProject} onValueChange={setSelectedProject}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Filtrar projeto" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">📂 Todos os Projetos</SelectItem>
                {projects?.map(project => (
                  <SelectItem key={project.id} value={project.id}>
                    {project.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            
            {/* Filtro de Período Customizado para Reports */}
            <div className="flex items-center gap-2">
              <Select value={selectedPeriod === 'today' ? 'today' : selectedPeriod === 'yesterday' ? 'yesterday' : 'custom'} onValueChange={(value) => {
                if (value === 'today') {
                  handlePeriodChange('today');
                } else if (value === 'yesterday') {
                  handlePeriodChange('yesterday');
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
                  <SelectItem value="yesterday">📆 Ontem</SelectItem>
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
            
            <Button onClick={handleRefresh} variant="outline" size="sm">
              <RefreshCw className="h-4 w-4 mr-2" />
              Atualizar
            </Button>

            <Button 
              onClick={handleExportPDF} 
              variant="default" 
              size="sm"
              disabled={isGeneratingPDF}
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

        {/* Summary Cards */}
        {reportData && (
          <>
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4 transition-all duration-300">
              <Card className="relative overflow-hidden shadow-lg border-red-500/20 bg-gradient-to-br from-red-500/5 via-red-400/5 to-red-500/10 hover:shadow-xl transition-shadow">
                <CardDecoration color="rgb(239, 68, 68)" />
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
                  <CardTitle className="text-sm font-medium">💸 Total Investido</CardTitle>
                  <DollarSign className="h-4 w-4 text-red-500" />
                </CardHeader>
                <CardContent className="relative z-10">
                  <div className="text-2xl font-bold text-red-600">
                    {formatCostCurrency(reportData.summary.totalInvestment)}
                  </div>
                  <p className="text-xs text-muted-foreground">{reportData.period}</p>
                </CardContent>
              </Card>

              <Card className="relative overflow-hidden shadow-lg border-green-500/20 bg-gradient-to-br from-green-500/5 via-green-400/5 to-green-500/10 hover:shadow-xl transition-shadow">
                <CardDecoration color="rgb(34, 197, 94)" />
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
                  <CardTitle className="text-sm font-medium">💰 Total Faturado (Líquido)</CardTitle>
                  <TrendingUp className="h-4 w-4 text-green-500" />
                </CardHeader>
                <CardContent className="relative z-10">
                  <RevenueTooltip
                    netRevenue={reportData.summary.totalRevenueAfterRevshare || reportData.summary.totalRevenue}
                    revsharePercentage={0.1}
                    projectType="GAM" // Reports agregados: deixar como GAM para compatibilidade
                  >
                    <div className="text-2xl font-bold text-green-600">
                      {formatBrlCurrency(reportData.summary.totalRevenueAfterRevshare || reportData.summary.totalRevenue)}
                    </div>
                  </RevenueTooltip>
                  <p className="text-xs text-muted-foreground">Revenue líquido via UTM</p>
                </CardContent>
              </Card>

              <Card className="relative overflow-hidden shadow-lg border-success/20 bg-gradient-to-br from-success/5 via-emerald-500/5 to-success/10 hover:shadow-xl transition-shadow">
                <CardDecoration color="hsl(var(--success))" />
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative">
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-sm font-medium">💚 Lucro Líquido</CardTitle>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Info className="h-3 w-3 text-green-600 opacity-60 hover:opacity-100 cursor-help transition-opacity" />
                        </TooltipTrigger>
                        <TooltipContent 
                          side="left" 
                          className="max-w-sm p-4 !z-[99999]" 
                          style={{ zIndex: 99999, position: 'fixed' }}
                        >
                          <div className="space-y-2 text-sm">
                            <div className="font-medium text-green-600 mb-2">Cálculo do Lucro Líquido </div>
                            {(() => {
                              const totalRevenue = reportData.summary.totalRevenue;
                              const totalInvestment = reportData.summary.totalInvestment;
                              
                              // NEW: Usar cálculo simplificado com valores pré-calculados
                              const numberOfDays = calculateNumberOfDays();
                              const calculation = calculateSimplifiedNetProfit(
                                reportData?.summary?.totalRevenueAfterRevshare || totalRevenue, // Usar valor direto - já vem com revshare aplicado
                                totalInvestment,
                                currentTaxRate,
                                dailyOperationalCosts,
                                numberOfDays
                              );
                              
                              return (
                                <div className="space-y-1">
                                  <div className="flex justify-between">
                                    <span className="text-muted-foreground">Faturamento Líquido (após Rev Share):</span>
                                    <span className="font-mono text-blue-600">{formatBrlCurrency(calculation.netRevenue)}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-muted-foreground">Investimento:</span>
                                    <span className="font-mono text-red-600">-{formatCostCurrency(totalInvestment)}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-muted-foreground">Impostos SN ({currentTaxRate}%):</span>
                                    <span className="font-mono text-red-600">-{formatCostCurrency(calculation.taxAmount)}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-muted-foreground">
                                      Custos Op. ({calculation.numberOfDays} {calculation.numberOfDays === 1 ? 'dia' : 'dias'}):
                                    </span>
                                    <span className="font-mono text-red-600">-{formatCostCurrency(calculation.totalOperationalCosts)}</span>
                                  </div>
                                  <div className="border-t pt-1 border-green-200">
                                    <div className="flex justify-between font-medium">
                                      <span>Lucro Líquido:</span>
                                      <span className="font-mono text-green-600">{formatCostCurrency(calculation.netProfit)}</span>
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
                <CardContent className="relative">
                  <div className="text-2xl font-bold text-green-600">
                    {formatCostCurrency(reportData.summary.netProfit)}
                  </div>
                  <p className="text-xs text-muted-foreground">Após {currentTaxRate}% SN</p>
                </CardContent>
              </Card>

              <Card className={`relative overflow-hidden shadow-lg hover:shadow-xl transition-shadow ${getROIColor(reportData.summary.averageRoas)}`}>
                <CardDecoration color="hsl(var(--primary))" />
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative z-10">
                  <CardTitle className="text-sm font-medium">👑 ROI Final</CardTitle>
                  <Target className="h-4 w-4" />
                </CardHeader>
                <CardContent className="relative z-10">
                  <div className="text-2xl font-bold">
                    {reportData.summary.finalRoi.toFixed(1)}%
                  </div>
                  <p className="text-xs text-muted-foreground">
                    ROAS: {reportData.summary.averageRoas.toFixed(1)}%
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Performance Charts */}
            {chartData.length > 0 && (
              <div className="grid gap-6 lg:grid-cols-2">
                <Card className="shadow-lg">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <BarChart3 className="h-5 w-5 text-primary" />
                      📈 Investimento vs Revenue
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis />
                        <RechartsTooltip 
                          formatter={(value: any) => [formatBrlCurrency(Number(value)), '']}
                          labelFormatter={(label) => `Data: ${label}`}
                        />
                        <Bar dataKey="investment" fill="hsl(var(--destructive))" name="Investimento" />
                        <Bar dataKey="revenue" fill="hsl(var(--success))" name="Revenue" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {projectDistributionData.length > 0 && (
                  <Card className="shadow-lg">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <PieChart className="h-5 w-5 text-primary" />
                        📊 Distribuição por Projeto
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
                            fill="#8884d8"
                            dataKey="value"
                          >
                            {projectDistributionData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.color} />
                            ))}
                          </Pie>
                          <RechartsTooltip 
                            formatter={(value: any) => [formatBrlCurrency(Number(value)), 'Revenue']}
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
              <Card className="shadow-lg">
                <CardHeader className="flex flex-row items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Users className="h-5 w-5 text-primary" />
                      📂 Performance por Projeto
                    </CardTitle>
                    <p className="text-muted-foreground text-sm mt-1">
                      Detalhamento de {reportData.projects.length} projetos no período
                    </p>
                  </div>
                  <Badge variant="outline">
                    {reportData.summary.campaignCount} campanhas ativas
                  </Badge>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left p-3 font-medium">Projeto</th>
                          <th className="text-left p-3 font-medium">Investimento</th>
                          <th className="text-left p-3 font-medium">Revenue</th>
                          <th className="text-left p-3 font-medium">ROAS</th>
                          <th className="text-left p-3 font-medium">Campanhas</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reportData.projects.map((project, index) => (
                          <tr key={project.id} className="border-b hover:bg-muted/50 transition-colors cursor-pointer" onClick={() => navigate(`/dashboard/project/${project.id}`)}>
                            <td className="p-3">
                              <div className="flex items-center gap-3">
                                <div className="h-8 w-8 bg-gradient-to-br from-primary to-purple-600 rounded-lg flex items-center justify-center text-white font-bold text-xs">
                                  {index + 1}
                                </div>
                                <div>
                                  <p className="font-medium text-primary hover:text-primary/80 transition-colors">{project.domain}</p>
                                  <p className="text-xs text-muted-foreground">{project.name}</p>
                                </div>
                              </div>
                            </td>
                            <td className="p-3">
                              <div className="font-bold">
                                {formatCostCurrency(project.investment || 0)}
                              </div>
                            </td>
                            <td className="p-3">
                              <div className="font-bold text-green-600">
                                {formatBrlCurrency(project.revenue || 0)}
                              </div>
                            </td>
                            <td className="p-3">
                              <div className={`px-3 py-1 rounded-lg border font-bold ${getROIColor(project.roas)}`}>
                                {project.roas.toFixed(1)}%
                              </div>
                            </td>
                            <td className="p-3">
                              <Badge variant="outline">
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

            {/* Report Summary Info */}
            <Card className="mt-6 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
              <h3 className="font-medium text-blue-800 mb-3 flex items-center gap-2">
                📋 Resumo do Relatório - {reportData.period}
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-blue-700">
                <div className="space-y-2">
                  <p>📊 <strong>Tipo:</strong> Consolidado</p>
                  <p>🎯 <strong>Projetos:</strong> {reportData.summary.projectCount}</p>
                </div>
                <div className="space-y-2">
                  <p>📅 <strong>Período:</strong> {reportData.period}</p>
                  <p>🚀 <strong>Campanhas:</strong> {reportData.summary.campaignCount}</p>
                </div>
                <div className="space-y-2">
                  <RevenueTooltip
                    netRevenue={reportData.summary.totalRevenueAfterRevshare || reportData.summary.totalRevenue}
                    revsharePercentage={0.1}
                    projectType="GAM" // Reports agregados: deixar como GAM para compatibilidade
                  >
                    <p>💰 <strong>Revenue Total (Líquido):</strong> {formatBrlCurrency(reportData.summary.totalRevenueAfterRevshare || reportData.summary.totalRevenue)}</p>
                  </RevenueTooltip>
                  <p>💸 <strong>Investimento:</strong> {formatCostCurrency(reportData.summary.totalInvestment)}</p>
                </div>
                <div className="space-y-2">
                  <p>📈 <strong>ROAS Médio:</strong> {reportData.summary.averageRoas.toFixed(1)}%</p>
                  <p>👑 <strong>ROI Final:</strong> {reportData.summary.finalRoi.toFixed(1)}%</p>
                </div>
              </div>
            </Card>
          </>
        )}
      </div>
    </Layout>
  );
}