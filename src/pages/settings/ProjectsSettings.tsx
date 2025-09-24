import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal, useModal } from "@/components/ui/modal";
import { Layout } from "@/components/layout/Layout";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { DateFilter } from "@/components/dashboard/DateFilter";
import { DataStatus } from "@/components/dashboard/DataStatus";
import {
  Plus,
  Edit,
  Trash2,
  FolderOpen,
  Calendar as CalendarIcon,
  Settings,
  BarChart3,
  Search,
  CheckCircle,
  Link,
  DollarSign,
  Clock,
  ArrowLeft,
  AlertTriangle,
  X,
  RefreshCw,
  TrendingUp,
  ArrowDown,
  Info
} from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useNavigate } from "react-router-dom";
import { supabaseDataService, useSupabaseData, Project } from "@/services/supabaseDataService";
import { supabase } from "@/lib/supabase";
import { format, differenceInDays } from "date-fns";
import { ptBR } from "date-fns/locale";
import { cn } from "@/lib/utils";
import { formatBrlCurrency, formatCostCurrency } from "@/utils/currencyUtils";
import { calculateROAS, getROASColorStyles, getROASColorCategory } from "@/utils/roasCalculations";

interface ProjectIntegration {
  googleAds: {
    connected: boolean;
    account: string;
    id: string;
    status: string;
  };
  gam: {
    connected: boolean;
    account: string;
    networkCode?: string;
    status: string;
  };
  adxDiscount: number;
}


export default function ProjectsSettings() {
  console.log('🚀 ProjectsSettings component started loading');
  
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedProjectItem, setSelectedProjectItem] = useState<Project | null>(null);
  const [newProject, setNewProject] = useState({
    name: "",
    gamNetworkCode: "",
    revenueShare: ""
  });
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [isUpdatingProject, setIsUpdatingProject] = useState(false);
  const [editForm, setEditForm] = useState({
    gamNetworkCode: "",
    revenueShare: ""
  });
  const addModal = useModal();
  const editModal = useModal();
  const deleteModal = useModal();
  
  // Filter states - mesma lógica de Reports com ONTEM adicionado
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range'>('today');
  const [selectedDate, setSelectedDate] = useState<string>(""); // Will be set dynamically
  const [selectedEndDate, setSelectedEndDate] = useState<string>("");
  const [selectedProject, setSelectedProject] = useState<string>("all");

  // Estados para o filtro customizado - mesma lógica de Reports
  const [isCustomPeriodOpen, setIsCustomPeriodOpen] = useState(false);
  const [customDate, setCustomDate] = useState<Date | undefined>(undefined);
  const [rangeStartDate, setRangeStartDate] = useState<Date | undefined>(undefined);
  const [rangeEndDate, setRangeEndDate] = useState<Date | undefined>(undefined);
  const [tempCustomDate, setTempCustomDate] = useState<Date | undefined>(undefined);
  const [tempRangeStartDate, setTempRangeStartDate] = useState<Date | undefined>(undefined);
  const [tempRangeEndDate, setTempRangeEndDate] = useState<Date | undefined>(undefined);
  
  // Sort state
  const [sortBy, setSortBy] = useState<'revenue' | 'investment' | 'roi'>('revenue');
  
  // Initialize with current server date (São Paulo timezone)
  useEffect(() => {
    const initialize = async () => {
      try {
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);
        console.log('🇧🇷 ProjectsSettings initialized with São Paulo date:', serverDate);
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
  
  // Use filtered data based on current selections - mesma lógica do Dashboard Geral
  // TRATAMENTO ESPECIAL: Yesterday internamente vira 'custom' para usar a mesma lógica
  const filters = {
    date: selectedDate,
    endDate: selectedEndDate || undefined,
    projectId: selectedProject === "all" ? undefined : selectedProject,
    period: selectedPeriod === 'yesterday' ? 'custom' : selectedPeriod
  };
  
  // Use the same data hook as GeneralDashboard
  const { projects, campaigns, loading, error, refresh } = useSupabaseData(filters);
  
  // Debug: Log filtered data
  useEffect(() => {
    console.log('🏗️ ProjectsSettings - Filtered data received:', {
      filters,
      projects: projects.length,
      campaigns: campaigns.length,
      loading,
      error,
      sortBy,
      projectsData: projects.slice(0, 2) // Show first 2 projects for debugging
    });
  }, [projects, campaigns, loading, error, filters, sortBy]);

  // Filter handlers - mesma lógica de Reports
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
    console.log('🔄 ProjectsSettings handleDateRangeChange called with:', { startDate, endDate });
    setSelectedDate(startDate);
    setSelectedEndDate(endDate);
    setSelectedPeriod('range');

    const newFilters = {
      date: startDate,
      endDate: endDate,
      projectId: selectedProject === "all" ? undefined : selectedProject,
      period: 'range' as const
    };
    console.log('🔄 ProjectsSettings: Refreshing with range filters:', newFilters);
    setTimeout(() => {
      refresh(newFilters);
    }, 100);
  };

  const handleDateChange = (date: string) => {
    setSelectedDate(date);
  };
  
  const handleProjectFilterChange = (projectId: string) => {
    setSelectedProject(projectId);
  };
  
  const handleSortChange = (sortOption: 'revenue' | 'investment' | 'roi') => {
    setSortBy(sortOption);
  };


  const filteredProjects = projects.filter(project =>
    project.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    project.domain.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleAddProject = async () => {
    if (!newProject.name.trim() || !newProject.gamNetworkCode.trim() || !newProject.revenueShare.trim()) {
      return;
    }

    setIsCreatingProject(true);

    try {
      // Remove https:// if present and clean the domain
      const cleanDomain = newProject.name.replace(/^https?:\/\//, '').trim();
      
      // Insert new project into Supabase
      const { data, error } = await supabase
        .from('projects')
        .insert({
          project_name: cleanDomain,
          main_url: `https://${cleanDomain}`,
          domain: cleanDomain,
          gam_network_code: newProject.gamNetworkCode,
          revshare: parseFloat(newProject.revenueShare) / 100,
          status: 'active',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        })
        .select()
        .single();

      if (error) {
        console.error('Error creating project:', error);
        alert('Erro ao criar projeto: ' + error.message);
        return;
      }

      console.log('Project created successfully:', data);
      
      // Reset form
      setNewProject({
        name: "",
        gamNetworkCode: "",
        revenueShare: ""
      });
      
      addModal.closeModal();
      refresh(filters);
      
    } catch (error) {
      console.error('Error creating project:', error);
      alert('Erro ao criar projeto. Tente novamente.');
    } finally {
      setIsCreatingProject(false);
    }
  };

  const handleEditProject = async () => {
    if (!selectedProjectItem) {
      return;
    }

    // At least one field must be filled to save
    if (!editForm.gamNetworkCode.trim() && !editForm.revenueShare.trim()) {
      alert('Preencha pelo menos um dos campos para salvar.');
      return;
    }

    setIsUpdatingProject(true);

    try {
      // Build update object with only filled fields
      const updateData: any = {
        updated_at: new Date().toISOString()
      };

      if (editForm.gamNetworkCode.trim()) {
        updateData.gam_network_code = editForm.gamNetworkCode.trim();
      }

      if (editForm.revenueShare.trim()) {
        updateData.revshare = parseFloat(editForm.revenueShare) / 100;
      }

      // Update project in Supabase
      const { data, error } = await supabase
        .from('projects')
        .update(updateData)
        .eq('id', selectedProjectItem.id)
        .select()
        .single();

      if (error) {
        console.error('Error updating project:', error);
        alert('Erro ao atualizar projeto: ' + error.message);
        return;
      }

      console.log('Project updated successfully:', data);
      
      // Reset form and close modal
      setEditForm({
        gamNetworkCode: "",
        revenueShare: ""
      });
      setSelectedProjectItem(null);
      editModal.closeModal();
      refresh(filters);
      
    } catch (error) {
      console.error('Error updating project:', error);
      alert('Erro ao atualizar projeto. Tente novamente.');
    } finally {
      setIsUpdatingProject(false);
    }
  };

  const handleDeleteProject = () => {
    if (selectedProjectItem) {
      // TODO: Implement delete functionality with Supabase
      setSelectedProjectItem(null);
      deleteModal.closeModal();
      refresh(filters);
    }
  };


  // Função para formatar valores de REVENUE (já convertidos pelo database em revenue_conversao)
  const formatRevenue = (brlValue: number) => {
    return formatBrlCurrency(brlValue);
  };
  // Função para formatar valores de CUSTOS/GASTOS (já em BRL)
  const formatCurrency = (brlValue: number) => {
    return formatCostCurrency(brlValue);
  };
  // Using centralized ROAS calculation (excess percentage)

  // Loading state
  if (loading) {
    return (
      <Layout>
        <div className="p-6 space-y-8 max-w-7xl mx-auto">
          <div className="flex items-center justify-center min-h-64">
            <LoadingSpinner size="lg" text="Carregando projetos..." />
          </div>
        </div>
      </Layout>
    );
  }

  // Error state  
  if (error) {
    return (
      <Layout>
        <div className="p-6 space-y-8 max-w-7xl mx-auto">
          <div className="flex flex-col items-center justify-center min-h-64">
            <AlertTriangle className="h-16 w-16 text-destructive mx-auto mb-4" />
            <h1 className="text-2xl font-bold mb-2">Erro ao carregar projetos</h1>
            <p className="text-muted-foreground mb-4">{error}</p>
            <Button onClick={() => window.location.reload()} variant="outline">
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
        {/* Header */}
        <div className="flex items-center justify-between animate-fade-in">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-2">
              <ArrowLeft className="h-4 w-4" />
              Voltar
            </Button>
            <div>
              <h1 className="text-3xl font-bold bg-gradient-dashboard bg-clip-text text-transparent">
                Configurações &gt; Projetos
              </h1>
              <p className="text-muted-foreground mt-2">
                Configure e gerencie seus projetos e integrações
                <span className="ml-2 text-primary">• {projects.length} projetos carregados</span>
              </p>
            </div>
          </div>
          <Button onClick={addModal.openModal} className="gap-2">
            <Plus className="h-4 w-4" />
            Novo Projeto
          </Button>
        </div>

        {/* Filters */}
        <div className="flex gap-4 animate-scale-in flex-wrap items-center">
          {/* Filtro de Período Customizado - igual ao Reports */}
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
          <Select value={sortBy} onValueChange={handleSortChange}>
            <SelectTrigger className="w-52">
              <BarChart3 className="h-4 w-4 mr-2" />
              <SelectValue placeholder="Ordenar por" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="revenue">
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-green-500" />
                  <span>Maior Faturamento</span>
                </div>
              </SelectItem>
              <SelectItem value="investment">
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4 text-red-500" />
                  <span>Maior Investimento</span>
                </div>
              </SelectItem>
              <SelectItem value="roi">
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-blue-500" />
                  <span>Maior ROAS</span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
          <DataStatus
            loading={loading}
            error={error}
          />
          <div className="flex-1 relative min-w-[280px]">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
            <Input
              placeholder="🔍 Buscar projetos..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        {/* Projects Table */}
        <Card className="shadow-lg transition-all duration-300 bg-gradient-to-br from-background to-muted/30 hover:shadow-xl transition-shadow">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FolderOpen className="h-5 w-5 text-primary" />
                Lista de Projetos
              </CardTitle>
              <CardDescription>
                Gerenciamento completo dos seus projetos
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button onClick={addModal.openModal} className="gap-2">
                <Plus className="h-4 w-4" />
                Novo Projeto
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {filteredProjects.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <div className="bg-gradient-to-r from-slate-100 to-gray-100 rounded-full w-20 h-20 flex items-center justify-center mx-auto mb-4">
                  <FolderOpen className="h-10 w-10 opacity-50" />
                </div>
                <h3 className="text-lg font-medium mb-2">
                  {searchTerm ? 'Nenhum projeto encontrado' : 'Nenhum projeto cadastrado'}
                </h3>
                <p className="text-sm text-center">
                  {searchTerm 
                    ? 'Tente alterar os termos de busca para ver mais projetos'
                    : 'Crie seu primeiro projeto para começar a gerenciar campanhas'
                  }
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-3 font-medium">Projeto (Domínio)</th>
                      <th className={`text-left p-3 font-medium ${sortBy === 'investment' ? 'text-red-600 bg-red-50' : ''}`}>
                        <div className="flex items-center gap-1">
                          Gasto
                          {sortBy === 'investment' && <ArrowDown className="h-3 w-3" />}
                        </div>
                      </th>
                      <th className={`text-left p-3 font-medium ${sortBy === 'revenue' ? 'text-green-600 bg-green-50' : ''}`}>
                        <div className="flex items-center gap-1">
                          Revenue
                          {sortBy === 'revenue' && <ArrowDown className="h-3 w-3" />}
                        </div>
                      </th>
                      <th className={`text-left p-3 font-medium ${sortBy === 'roi' ? 'text-blue-600 bg-blue-50' : ''}`}>
                        <div className="flex items-center gap-1">
                          ROAS
                          {sortBy === 'roi' && <ArrowDown className="h-3 w-3" />}
                        </div>
                      </th>
                      <th className="text-left p-3 font-medium">
                        <div className="flex items-center gap-1">
                          Lucro Líquido
                        </div>
                      </th>
                      <th className="text-left p-3 font-medium">Campanhas</th>
                      <th className="text-left p-3 font-medium">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredProjects
                      .sort((a, b) => {
                        if (sortBy === 'revenue') {
                          return (b.revenue || 0) - (a.revenue || 0);
                        } else if (sortBy === 'investment') {
                          return (b.investment || 0) - (a.investment || 0);
                        } else { // roi
                          const roasA = calculateROAS(a.revenue || 0, a.investment || 0);
                          const roasB = calculateROAS(b.revenue || 0, b.investment || 0);
                          return roasB - roasA;
                        }
                      })
                      .map((project, index) => {
                        
                        // Using centralized ROAS color styling
                        const getROIColor = (roasExcess: number) => {
                          return getROASColorStyles(roasExcess);
                        };
                        
                        const roas = calculateROAS(project.revenue || 0, project.investment || 0);
                        
                        const netProfit = project.netProfit || 0;
                        const getNetProfitColor = (value: number) => {
                          if (value > 0) return "text-green-600";
                          if (value < 0) return "text-red-600";
                          return "text-gray-600";
                        };

                        return (
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
                                {formatCurrency(project.investment || 0)}
                              </div>
                              <div className="text-xs text-muted-foreground">Gasto total</div>
                            </td>
                            <td className="p-4">
                              <div className="text-lg font-bold text-green-600">
                                {formatRevenue(project.revenue || 0)}
                              </div>
                              <div className="text-xs text-muted-foreground">Revenue UTM</div>
                            </td>
                            <td className="p-4">
                              <div className={`text-lg font-bold px-3 py-1 rounded-lg border ${getROIColor(roas)}`}>
                                {Math.round(roas)}%
                              </div>
                              <div className="flex items-center gap-1 mt-1">
                                <span className="text-xs">Performance</span>
                              </div>
                            </td>
                            <td className="p-4">
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <div className="cursor-help">
                                      <div className={`text-lg font-bold flex items-center gap-1 ${getNetProfitColor(netProfit)}`}>
                                        {formatCurrency(netProfit)}
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
                                                <span className={getNetProfitColor(netProfit)}>{formatCurrency(netProfit)}</span>
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
                                    <DropdownMenuItem
                                      onClick={() => {
                                        setSelectedProjectItem(project);
                                        // Pre-fill the edit form with current values
                                        setEditForm({
                                          gamNetworkCode: project.gamNetworkCode || "",
                                          revenueShare: project.revshare ? (project.revshare * 100).toString() : ""
                                        });
                                        editModal.openModal();
                                      }}
                                    >
                                      <Edit className="h-4 w-4 mr-2" />
                                      Editar
                                    </DropdownMenuItem>
                                    <DropdownMenuItem
                                      onClick={() => {
                                        setSelectedProjectItem(project);
                                        deleteModal.openModal();
                                      }}
                                      className="text-destructive"
                                    >
                                      <Trash2 className="h-4 w-4 mr-2" />
                                      Excluir
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    }
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Add Project Modal */}
        <Modal
          isOpen={addModal.isOpen}
          onClose={addModal.closeModal}
          title="📂 Cadastrar Novo Projeto"
          size="md"
        >
          <div className="space-y-4">
            <div>
              <Label htmlFor="project-name">📝 Nome do Projeto (Domínio):</Label>
              <Input 
                id="project-name" 
                placeholder="Ex: meusite.com.br (sem https://)"
                value={newProject.name}
                onChange={(e) => setNewProject({...newProject, name: e.target.value})}
                className="mt-2"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Este será usado para project_name, main_url e domain no banco
              </p>
            </div>
            
            <div>
              <Label htmlFor="gam-network">🌐 GAM Network Code:</Label>
              <Input 
                id="gam-network" 
                placeholder="Ex: 12345678"
                value={newProject.gamNetworkCode}
                onChange={(e) => setNewProject({...newProject, gamNetworkCode: e.target.value})}
                className="mt-2"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Código do Google Ad Manager para este projeto
              </p>
            </div>
            
            <div>
              <Label htmlFor="revenue-share">💰 Taxa de Revenue Share (%):</Label>
              <Input 
                id="revenue-share" 
                placeholder="Ex: 70"
                type="number"
                min="0"
                max="100"
                step="0.1"
                value={newProject.revenueShare}
                onChange={(e) => setNewProject({...newProject, revenueShare: e.target.value})}
                className="mt-2"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Percentual de divisão de receita para este projeto
              </p>
            </div>

            <div className="flex justify-center gap-4 pt-6">
              <Button variant="outline" onClick={addModal.closeModal}>
                Cancelar
              </Button>
              <Button 
                onClick={handleAddProject} 
                className="gap-2"
                disabled={!newProject.name.trim() || !newProject.gamNetworkCode.trim() || !newProject.revenueShare.trim() || isCreatingProject}
              >
                {isCreatingProject ? (
                  <>
                    <LoadingSpinner size="sm" />
                    Salvando...
                  </>
                ) : (
                  <>
                    <Plus className="h-4 w-4" />
                    Salvar Projeto
                  </>
                )}
              </Button>
            </div>
          </div>
        </Modal>

        {/* Edit Project Modal */}
        <Modal
          isOpen={editModal.isOpen}
          onClose={editModal.closeModal}
          title="✏️ Editar Projeto"
          size="md"
        >
          {selectedProjectItem && (
            <div className="space-y-4">
              <div className="p-4 bg-muted/50 rounded-lg">
                <h4 className="font-medium mb-2">📂 {selectedProjectItem.name}</h4>
                <p className="text-sm text-muted-foreground">{selectedProjectItem.domain}</p>
              </div>
              
              <div>
                <Label htmlFor="edit-gam-network">🌐 GAM Network Code: <span className="text-xs text-muted-foreground">(opcional)</span></Label>
                <Input 
                  id="edit-gam-network" 
                  placeholder="Ex: 12345678 - deixe vazio para manter atual"
                  value={editForm.gamNetworkCode}
                  onChange={(e) => setEditForm({...editForm, gamNetworkCode: e.target.value})}
                  className="mt-2"
                />
              </div>
              
              <div>
                <Label htmlFor="edit-revenue-share">💰 Taxa de Revenue Share (%): <span className="text-xs text-muted-foreground">(opcional)</span></Label>
                {selectedProjectItem.revshare && (
                  <div className="text-sm text-muted-foreground mb-2">
                    Valor atual: <span className="font-medium text-primary">{(selectedProjectItem.revshare * 100).toFixed(1)}%</span>
                  </div>
                )}
                <Input 
                  id="edit-revenue-share" 
                  placeholder="Ex: 70 - deixe vazio para manter atual"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={editForm.revenueShare}
                  onChange={(e) => setEditForm({...editForm, revenueShare: e.target.value})}
                  className="mt-2"
                />
              </div>

              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-xs text-blue-700">
                  💡 <strong>Dica:</strong> Você pode editar apenas um dos campos ou ambos. Campos vazios manterão o valor atual.
                </p>
              </div>

              <div className="flex justify-center gap-4 pt-4">
                <Button variant="outline" onClick={editModal.closeModal}>
                  Cancelar
                </Button>
                <Button 
                  onClick={handleEditProject}
                  disabled={(!editForm.gamNetworkCode.trim() && !editForm.revenueShare.trim()) || isUpdatingProject}
                >
                  {isUpdatingProject ? (
                    <>
                      <LoadingSpinner size="sm" />
                      Salvando...
                    </>
                  ) : (
                    <>
                      <Edit className="h-4 w-4 mr-2" />
                      Salvar Alterações
                    </>
                  )}
                </Button>
              </div>
            </div>
          )}
        </Modal>

        {/* Delete Confirmation Modal */}
        <Modal
          isOpen={deleteModal.isOpen}
          onClose={deleteModal.closeModal}
          title="🗑️ Excluir Projeto"
          description="Esta ação não pode ser desfeita"
          size="sm"
        >
          {selectedProjectItem && (
            <div className="space-y-4">
              <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-lg">
                <p className="text-sm">
                  Tem certeza que deseja excluir o projeto <strong>{selectedProjectItem.name}</strong>?
                </p>
                <p className="text-xs text-muted-foreground mt-2">
                  • Todas as campanhas serão removidas<br/>
                  • As integrações serão desconectadas<br/>
                  • Os dados históricos serão perdidos
                </p>
              </div>
              
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={deleteModal.closeModal}>
                  Cancelar
                </Button>
                <Button variant="destructive" onClick={handleDeleteProject}>
                  Excluir Projeto
                </Button>
              </div>
            </div>
          )}
        </Modal>
      </div>
    </Layout>
  );
}