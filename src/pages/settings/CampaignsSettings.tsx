import React, { useState, useMemo, useEffect } from "react";
import { Layout } from "@/components/layout/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { useToast } from "@/hooks/use-toast";
import { ArrowLeft, Search, Edit, Copy, Pause, Trash2, RefreshCw, Play, Settings, AlertTriangle, User, FolderOpen, Calendar, Circle, BarChart3, Coins, DollarSign, Hash, Zap, CheckCircle2 } from "lucide-react";
import { useSupabaseData, Campaign, Project, supabaseDataService } from "@/services/supabaseDataService";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { DateFilter } from "@/components/dashboard/DateFilter";
import { DataStatus } from "@/components/dashboard/DataStatus";
import { format } from "date-fns";
import { getROASColorCategory, getROASColorStyles, calculateROAS } from "@/utils/roasCalculations";
import { useAuth } from "@/contexts/AuthContext";
import { supabase } from "@/lib/supabase";
import { useUserFilters } from "@/hooks/useUserFilters";
import { CampaignSortSelect } from "@/components/campaign/CampaignSortSelect";
import { sortCampaigns, type CampaignSortKey } from "@/lib/campaignSort";
import { MetricDelta } from "@/components/campaign/MetricDelta";
import { useCampaignComparisons } from "@/hooks/useCampaignComparisons";
import { IdentidadeDeCanal } from "@/components/trafego/hub/IdentidadeDeCanal";
import { SeletorRedeCampanhas, type RedeDeCampanhas } from "@/components/campaign/SeletorRedeCampanhas";
import MetaCampaignsSettingsDemo from "./MetaCampaignsSettingsDemo";

const GoogleCampaignsSettings: React.FC<{ onNetworkChange: (rede: RedeDeCampanhas) => void }> = ({ onNetworkChange }) => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { userProfile } = useAuth();
  
  // Estados para filtros
  const [searchTerm, setSearchTerm] = useState("");
  const [projectFilter, setProjectFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortKey, setSortKey] = useState<CampaignSortKey>("roas");
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range'>('today');
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedEndDate, setSelectedEndDate] = useState<string>("");
  const [formattedRevenues, setFormattedRevenues] = useState<{[key: string]: string}>({});

  // Initialize with current server date
  useEffect(() => {
    const initialize = async () => {
      try {
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);
        console.log('🗓️ CampaignsSettings initialized with server date:', serverDate);
      } catch (error) {
        console.error('Error getting server date:', error);
        const now = new Date();
        const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(now);
        setSelectedDate(saoPauloDate);
      }
    };
    
    initialize();
  }, []);

  // Get user filters for operators
  const { allowedProjectIds, allowedCampaignIds, hasFilters } = useUserFilters();

  // Use filtered data based on current selections
  // IMPORTANTE: Só passar os filtros se tiverem valores (não passar arrays vazios)
  // useMemo para evitar re-renders desnecessários quando a referência dos arrays muda
  const filters = useMemo(() => ({
    date: selectedDate,
    endDate: selectedEndDate || undefined,
    projectId: projectFilter === "all" ? undefined : projectFilter,
    period: selectedPeriod,
    ...(hasFilters && allowedProjectIds.length > 0 && { userProjectIds: allowedProjectIds }),
    ...(hasFilters && allowedCampaignIds.length > 0 && { userCampaignIds: allowedCampaignIds })
  }), [selectedDate, selectedEndDate, projectFilter, selectedPeriod, hasFilters, allowedProjectIds, allowedCampaignIds]);

  // Debug log para identificar o problema
  useEffect(() => {
    console.log('🔍 CampaignsSettings - Filtros atualizados:', {
      userRole: userProfile?.role,
      hasFilters,
      allowedProjectIds,
      allowedCampaignIds,
      finalFilters: filters
    });
  }, [hasFilters, allowedProjectIds, allowedCampaignIds, filters, userProfile]);

  const { projects, campaigns, loading, error, refresh } = useSupabaseData(filters);

  // Adicionar log quando campaigns mudam
  useEffect(() => {
    console.log('📊 Campanhas recebidas do hook:', {
      count: campaigns?.length || 0,
      loading,
      error
    });
  }, [campaigns, loading, error]);

  // Format revenue values when campaigns are loaded
  useEffect(() => {
    if (campaigns && campaigns.length > 0) {
      const formattedValues: {[key: string]: string} = {};
      
      for (const campaign of campaigns) {
        try {
          // Revenue from getCampaignsWithRevenue uses revenue_converted_revshare (líquido)
          // Format for BRL display
          const revenueValue = campaign.revenue || 0;
          formattedValues[campaign.id] = new Intl.NumberFormat('pt-BR', {
            style: 'currency',
            currency: 'BRL'
          }).format(revenueValue);
        } catch (error) {
          console.error('Error formatting revenue for campaign', campaign.id, error);
          formattedValues[campaign.id] = 'R$ 0,00';
        }
      }
      
      setFormattedRevenues(formattedValues);
    }
  }, [campaigns]);

  // Função para determinar a cor da campanha baseada no ROI
  // Using centralized ROAS color category
  const getCampaignColorCategory = (roasExcess: number) => {
    return getROASColorCategory(roasExcess);
  };

  const filteredCampaigns = useMemo(() => {
    if (!campaigns) return [];

    console.log('🎯 Filtrando campanhas:', {
      totalCampaigns: campaigns.length,
      hasFilters,
      allowedProjectIds,
      allowedCampaignIds
    });

    const filtered = campaigns.filter(campaign => {
      const matchesSearch = campaign.name.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesProject = projectFilter === "all" || campaign.projectId === projectFilter;

      // Filtro por projetos do operador - APENAS se for operador com filtros
      let matchesUserProjects = true;
      if (hasFilters && allowedProjectIds.length > 0) {
        // Converter projectId para number se necessário
        const campaignProjectId = typeof campaign.projectId === 'string'
          ? parseInt(campaign.projectId)
          : campaign.projectId;
        matchesUserProjects = allowedProjectIds.includes(campaignProjectId);
      }

      // Filtro por campanhas específicas do operador - APENAS se houver filtro de campanhas
      let matchesUserCampaigns = true;
      if (hasFilters && allowedCampaignIds.length > 0) {
        // campaign.id é o campaign_id (Google Ads ID) que vem do banco
        matchesUserCampaigns = allowedCampaignIds.includes(campaign.id);
      }

      // Nova lógica de filtro por cor ROAS
      let matchesStatus = true;
      if (statusFilter !== "all") {
        const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
        const campaignColorCategory = getCampaignColorCategory(roasExcess);
        matchesStatus = statusFilter === campaignColorCategory;
      }

      return matchesSearch && matchesProject && matchesStatus && matchesUserProjects && matchesUserCampaigns;
    });

    console.log('✅ Campanhas filtradas:', filtered.length);
    return sortCampaigns(filtered, sortKey);
  }, [campaigns, searchTerm, projectFilter, statusFilter, hasFilters, allowedProjectIds, allowedCampaignIds, sortKey]);

  const { comparisons, loadingComparisons } = useCampaignComparisons(
    filteredCampaigns,
    { period: selectedPeriod, date: selectedDate, endDate: selectedEndDate || undefined }
  );

  // Using centralized ROAS color styling
  const getROIColor = (roasExcess: number) => {
    return getROASColorStyles(roasExcess);
  };

  const getProjectName = (projectId: string) => {
    return projects.find(p => p.id === projectId)?.name || `Projeto ${projectId}`;
  };

  // Handlers para filtros de data
  const handlePeriodChange = async (period: 'today' | '7d' | '30d' | 'custom' | 'range') => {
    setSelectedPeriod(period);
    if (period === 'today') {
      try {
        supabaseDataService.clearServerDateCache();
        const serverDate = await supabaseDataService.getServerDate();
        setSelectedDate(serverDate);
        setSelectedEndDate(""); // Clear end date for today
        console.log('🔄 CampaignsSettings updated to current server date:', serverDate);
      } catch (error) {
        console.error('Error getting server date:', error);
        // Fallback to São Paulo timezone date
        const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(new Date());
        setSelectedDate(saoPauloDate);
        setSelectedEndDate(""); // Clear end date for today
      }
    }
  };

  const handleDateChange = (date: string) => {
    console.log('📅 CampaignsSettings Date changed to:', date, 'period:', selectedPeriod);
    setSelectedDate(date);
    setSelectedEndDate(""); // Clear end date for single date selection
    const newFilters = { date, endDate: undefined, projectId: projectFilter === "all" ? undefined : projectFilter, period: selectedPeriod };
    console.log('🔄 CampaignsSettings Refreshing with new filters:', newFilters);
    setTimeout(() => {
      refresh(newFilters);
    }, 100);
  };

  const handleDateRangeChange = (startDate: string, endDate: string) => {
    console.log('📅 CampaignsSettings Date range changed to:', startDate, 'to', endDate);
    setSelectedDate(startDate);
    setSelectedEndDate(endDate);
    setSelectedPeriod('range');
    const newFilters = { date: startDate, endDate, projectId: projectFilter === "all" ? undefined : projectFilter, period: 'range' as const };
    console.log('🔄 CampaignsSettings Refreshing with range filters:', newFilters);
    setTimeout(() => {
      refresh(newFilters);
    }, 100);
  };

  const handleRefresh = async () => {
    toast({
      title: "Sincronizando",
      description: "Buscando novas campanhas...",
    });
    
    try {
      await refresh(filters);
      toast({
        title: "Sincronizado",
        description: "Campanhas atualizadas com sucesso!",
      });
    } catch (error) {
      toast({
        title: "Erro",
        description: "Falha ao sincronizar campanhas.",
        variant: "destructive"
      });
    }
  };

  const handleAction = async (action: string, campaignId: string, campaignName: string) => {
    switch (action) {
      case 'pause':
        try {
          await supabaseDataService.updateCampaignStatus(campaignId, 'paused', 'current_user');
          await refresh();
          
          toast({
            title: "Campanha Pausada",
            description: `${campaignName} foi pausada pelo usuário. Status será preservado mesmo com sincronização do Google Ads.`,
            variant: "default"
          });
        } catch (error) {
          console.error('Error pausing campaign:', error);
          toast({
            title: "Erro",
            description: "Falha ao pausar campanha.",
            variant: "destructive"
          });
        }
        break;
      case 'activate':
        try {
          await supabaseDataService.updateCampaignStatus(campaignId, 'active', 'current_user');
          await refresh();
          
          toast({
            title: "Campanha Reativada",
            description: `${campaignName} foi reativada pelo usuário.`,
          });
        } catch (error) {
          console.error('Error activating campaign:', error);
          toast({
            title: "Erro",
            description: "Falha ao reativar campanha.",
            variant: "destructive"
          });
        }
        break;
      case 'edit':
        toast({
          title: "Informação",
          description: "Campanhas são sincronizadas automaticamente. Use os botões Pausar/Ativar para controle manual.",
        });
        break;
      default:
        toast({
          title: "Informação",
          description: "Esta ação não está disponível para campanhas automáticas.",
        });
        break;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <Badge variant="outline" className="border-transparent bg-success/12 text-success rounded-full flex items-center gap-1">
          <Circle className="h-2 w-2 fill-current" />
          Ativa
        </Badge>;
      case 'paused':
        return <Badge variant="outline" className="border-transparent bg-warning/12 text-warning rounded-full flex items-center gap-1">
          <Circle className="h-2 w-2 fill-current" />
          Pausada
        </Badge>;
      case 'stopped':
        return <Badge variant="outline" className="border-transparent bg-destructive/12 text-destructive rounded-full flex items-center gap-1">
          <Circle className="h-2 w-2 fill-current" />
          Parada
        </Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
  
  return (
    <Layout>
      <div className={`${isMobile ? 'p-4' : 'p-6'} space-y-6 md:space-y-8 max-w-7xl mx-auto`}>
        {/* Header with Controls */}
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
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <Settings className="h-3 w-3" />
                </span>
                Configurações · Campanhas
              </div>
              <h1 className={`font-display font-bold tracking-tight leading-[1.05] ${isMobile ? 'text-[1.7rem]' : 'text-4xl'}`}>
                Campanhas
              </h1>
              <div className="mt-3 aurora-rule w-16" />
              <p className={`mt-3 text-muted-foreground ${isMobile ? 'text-sm' : ''}`}>
                Campanhas criadas automaticamente via integração GAM/Google Ads
                {projectFilter !== 'all' && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} text-primary`}>
                    • Projeto: {projects.find(p => p.id === projectFilter)?.name || 'Selecionado'}
                  </span>
                )}
                {selectedPeriod === 'yesterday' && selectedDate && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} text-primary`}>
                    • Data: Ontem ({format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy')})
                  </span>
                )}
                {selectedPeriod === 'custom' && selectedDate && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} text-primary`}>
                    • Data: {format(new Date(selectedDate + 'T12:00:00'), 'dd/MM/yyyy')}
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
                {selectedPeriod !== 'custom' && selectedPeriod !== 'range' && selectedPeriod !== 'yesterday' && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} text-primary`}>
                    • Período: {selectedPeriod === 'today' ? 'Hoje' : selectedPeriod === '7d' ? '7 dias' : '30 dias'}
                  </span>
                )}
              </p>
            </div>
          </div>

          <SeletorRedeCampanhas rede="google" onChange={onNetworkChange} />
          
          {/* Filters and Actions Section */}
          <div className={`flex ${isMobile ? 'flex-col w-full' : 'items-center'} gap-3 flex-wrap`}>
            <Select value={projectFilter} onValueChange={setProjectFilter}>
              <SelectTrigger className={`${isMobile ? 'w-full' : 'w-48'}`}>
                <SelectValue placeholder="Filtrar projeto" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">
                  <span className="flex items-center gap-2">
                    <FolderOpen className="h-4 w-4" />
                    Todos os Projetos
                  </span>
                </SelectItem>
                {projects
                  .filter(project => {
                    // Para OPERATORs com filtros, mostrar apenas projetos atribuídos
                    if (hasFilters && allowedProjectIds.length > 0) {
                      const projectId = typeof project.id === 'string' ? parseInt(project.id) : project.id;
                      return allowedProjectIds.includes(projectId);
                    }
                    return true;
                  })
                  .map(project => (
                    <SelectItem key={project.id} value={project.id}>
                      {project.name}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
            
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className={`${isMobile ? 'w-full' : 'w-48'}`}>
                <SelectValue placeholder="Filtrar por performance" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all"> Todas as Campanhas </SelectItem>
                <SelectItem value="green">
                  <span className="flex items-center gap-2">
                    <Circle className="h-3 w-3 fill-green-600 text-green-600" />
                    Campanhas Verdes (ROAS ≥ 80%)
                  </span>
                </SelectItem>
                <SelectItem value="yellow">
                  <span className="flex items-center gap-2">
                    <Circle className="h-3 w-3 fill-yellow-600 text-yellow-600" />
                    Campanhas Amarelas (ROAS 40-79%)
                  </span>
                </SelectItem>
                <SelectItem value="orange">
                  <span className="flex items-center gap-2">
                    <Circle className="h-3 w-3 fill-orange-600 text-orange-600" />
                    Campanhas Laranjas (ROAS 0-39%)
                  </span>
                </SelectItem>
                <SelectItem value="red">
                  <span className="flex items-center gap-2">
                    <Circle className="h-3 w-3 fill-red-600 text-red-600" />
                    Campanhas Vermelhas (ROAS negativo)
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
            
            <DateFilter
              selectedPeriod={selectedPeriod}
              selectedDate={selectedDate}
              selectedEndDate={selectedEndDate}
              onPeriodChange={handlePeriodChange}
              onDateChange={handleDateChange}
              onDateRangeChange={handleDateRangeChange}
            />
            
            <div className="flex items-center gap-2 flex-wrap">
              <Button onClick={handleRefresh} variant="outline" size="sm" className="flex-shrink-0">
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

        {/* Search Bar */}
        <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-4`}>
          <div className={`relative ${isMobile ? 'w-full' : 'flex-1 max-w-md'}`}>
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            {/* `design.md` §Forms: "Never rely on placeholder text as a label".
                O placeholder some quando a pessoa começa a digitar — e é
                justamente aí que ela precisa saber o que aquele campo filtra. */}
            <label htmlFor="busca-de-campanhas" className="sr-only">
              Buscar campanhas por nome
            </label>
            <Input
              id="busca-de-campanhas"
              type="search"
              placeholder="Buscar campanhas..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className={`pl-10 ${isMobile ? 'w-full touch-target' : ''}`}
            />
          </div>
          <CampaignSortSelect
            value={sortKey}
            onChange={setSortKey}
            className={isMobile ? 'w-full' : 'w-44'}
          />
          <div className={`flex ${isMobile ? 'flex-wrap w-full' : 'items-center'} gap-2`}>
            <Badge variant="outline" className="text-sm">
              <span className="tabular">{filteredCampaigns.length}</span> {filteredCampaigns.length === 1 ? 'campanha' : 'campanhas'}
            </Badge>
            {statusFilter === "all" && filteredCampaigns && filteredCampaigns.length > 0 && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Circle className="h-2 w-2 fill-green-600 text-green-600" />
                  {filteredCampaigns.filter(c => {
                    const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                    return getCampaignColorCategory(roasExcess) === "green";
                  }).length}
                </span>
                <span className="flex items-center gap-1">
                  <Circle className="h-2 w-2 fill-yellow-600 text-yellow-600" />
                  {filteredCampaigns.filter(c => {
                    const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                    return getCampaignColorCategory(roasExcess) === "yellow";
                  }).length}
                </span>
                <span className="flex items-center gap-1">
                  <Circle className="h-2 w-2 fill-orange-600 text-orange-600" />
                  {filteredCampaigns.filter(c => {
                    const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                    return getCampaignColorCategory(roasExcess) === "orange";
                  }).length}
                </span>
                <span className="flex items-center gap-1">
                  <Circle className="h-2 w-2 fill-red-600 text-red-600" />
                  {filteredCampaigns.filter(c => {
                    const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                    return getCampaignColorCategory(roasExcess) === "red";
                  }).length}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <Card className="p-8 text-center">
            <LoadingSpinner />
            <p className="text-muted-foreground mt-4">Carregando campanhas...</p>
          </Card>
        )}

        {/* Error State */}
        {error && (
          <Card className="p-6 border-destructive/30 bg-destructive/5 shadow-card">
            <div className="flex items-center gap-2 text-destructive">
              <span className="rounded-md bg-destructive/10 text-destructive p-1.5"><AlertTriangle className="h-4 w-4" /></span>
              <h3 className="font-display font-semibold">Erro ao carregar campanhas</h3>
            </div>
            <p className="text-muted-foreground text-sm mt-2">{error}</p>
            <Button 
              onClick={handleRefresh} 
              variant="outline" 
              className="mt-4 gap-2"
            >
              <RefreshCw className="h-4 w-4" />
              Tentar novamente
            </Button>
          </Card>
        )}

        {/* Campaigns List */}
        {!loading && !error && (
        <div className="space-y-4">
          {filteredCampaigns.map((campaign, index) => (
            <Link
              key={campaign.id}
              to={`/dashboard/campaign/${campaign.utmCampaignValue || campaign.id}`}
              className="block no-underline text-inherit reveal"
              style={{ ['--i' as any]: Math.min(index, 8) }}
            >
            <Card
              className="relative overflow-hidden p-6 cursor-pointer shadow-card hover-lift"
            >
              <CardContent className="p-0">
                <div className="space-y-4">
                  {/* Campaign Header */}
                  <div className="flex items-start justify-between">
                    <div className="min-w-0">
                      <h3 className="font-display font-semibold text-lg flex items-center gap-2 flex-wrap">
                        {getStatusBadge(campaign.status)}
                        <span className="truncate">{campaign.name}</span>
                      </h3>
                      <IdentidadeDeCanal
                        rede="google"
                        className="mt-2"
                      />
                      <p className="text-sm text-muted-foreground mt-1">
                        <span className="flex items-center gap-1">
                          <FolderOpen className="h-3 w-3" />
                          {getProjectName(campaign.projectId)}
                        </span>
                      </p>
                    </div>
                  </div>

                  {/* Metrics Gasto vs Revenue */}
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="rounded-md bg-primary/10 text-primary p-1.5">
                        <BarChart3 className="h-3.5 w-3.5" />
                      </span>
                      <span className="kicker">Performance Financeira · {
                      selectedPeriod === 'today' ? 'Hoje' :
                      selectedPeriod === 'yesterday' ? 'Ontem' :
                      selectedPeriod === '7d' ? 'Últimos 7 dias' :
                      selectedPeriod === '30d' ? 'Últimos 30 dias' :
                      selectedPeriod === 'range' && selectedEndDate ?
                        `${selectedDate} até ${selectedEndDate}` :
                        `Data: ${new Date(selectedDate).toLocaleDateString('pt-BR')}`
                    }</span>
                    </div>
                    <div className={`grid ${campaign.commission && campaign.commission > 0 ? 'grid-cols-2 md:grid-cols-5' : 'grid-cols-2 md:grid-cols-4'} gap-2 md:gap-4 text-sm`}>
                      <div className="relative overflow-hidden text-center p-3 rounded-lg border border-border bg-card">
                        <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
                        <p className="kicker mb-1">Gasto</p>
                        <p className="font-display text-base md:text-lg font-bold tabular text-foreground">{new Intl.NumberFormat('pt-BR', {
                          style: 'currency',
                          currency: 'BRL'
                        }).format(campaign.investment || 0)}</p>
                        <MetricDelta
                          current={campaign.investment || 0}
                          previous={comparisons?.get(campaign.id)?.prevInvestment}
                          label={comparisons?.get(campaign.id)?.comparisonLabel ?? ''}
                          isLoading={loadingComparisons}
                        />
                      </div>
                      <div className="relative overflow-hidden text-center p-3 rounded-lg border border-border bg-card">
                        <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
                        <p className="kicker mb-1">Revenue</p>
                        <p className="font-display text-base md:text-lg font-bold tabular text-success">{formattedRevenues[campaign.id] || 'R$ 0,00'}</p>
                        <MetricDelta
                          current={campaign.revenue || 0}
                          previous={comparisons?.get(campaign.id)?.prevRevenue}
                          label={comparisons?.get(campaign.id)?.comparisonLabel ?? ''}
                          isLoading={loadingComparisons}
                        />
                      </div>
                      <div className={`relative overflow-hidden text-center p-3 rounded-lg border ${(() => {
                        const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
                        return getROIColor(roasExcess);
                      })()}`}>
                        <p className="kicker mb-1">ROAS</p>
                        <p className="font-display text-base md:text-lg font-bold tabular">{(() => {
                          const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
                          return roasExcess.toFixed(1);
                        })()}%</p>
                        <MetricDelta
                          current={calculateROAS(campaign.revenue || 0, campaign.investment || 0)}
                          previous={comparisons?.get(campaign.id)?.prevRoas}
                          label={comparisons?.get(campaign.id)?.comparisonLabel ?? ''}
                          isLoading={loadingComparisons}
                        />
                      </div>
                      <div className="relative overflow-hidden text-center p-3 rounded-lg border border-border bg-card">
                        <span className={`pointer-events-none absolute inset-x-0 top-0 h-0.5 ${(() => {
                          const grossProfit = (campaign.revenue || 0) - (campaign.investment || 0);
                          return grossProfit >= 0 ? 'bg-success' : 'bg-destructive';
                        })()}`} />
                        <p className="kicker mb-1">Lucro Bruto</p>
                        <p className={`font-display text-base md:text-lg font-bold tabular ${(() => {
                          const grossProfit = (campaign.revenue || 0) - (campaign.investment || 0);
                          return grossProfit >= 0 ? 'text-success' : 'text-destructive';
                        })()}`}>{new Intl.NumberFormat('pt-BR', {
                          style: 'currency',
                          currency: 'BRL'
                        }).format((campaign.revenue || 0) - (campaign.investment || 0))}</p>
                        <MetricDelta
                          current={(campaign.revenue || 0) - (campaign.investment || 0)}
                          previous={
                            comparisons?.get(campaign.id)
                              ? (comparisons.get(campaign.id)!.prevRevenue - comparisons.get(campaign.id)!.prevInvestment)
                              : undefined
                          }
                          label={comparisons?.get(campaign.id)?.comparisonLabel ?? ''}
                          isLoading={loadingComparisons}
                        />
                      </div>
                      {campaign.commission && campaign.commission > 0 && (
                        <div className="relative overflow-hidden text-center p-3 rounded-lg border border-border bg-card">
                          <p className="kicker mb-1 flex items-center justify-center gap-1">
                            <Coins className="h-3 w-3" />
                            Comissão
                          </p>
                          <p className="font-display text-base md:text-lg font-bold tabular text-primary">{new Intl.NumberFormat('pt-BR', {
                            style: 'currency',
                            currency: 'BRL'
                          }).format(campaign.commission)}</p>
                        </div>
                      )}
                    </div>

                  </div>

                  {/* Campaign Details */}
                  <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-2 md:gap-4 ${isMobile ? 'text-xs' : 'text-sm'} text-muted-foreground pt-3 border-t border-border`}>
                    <span className="flex items-center gap-1.5">
                      <Hash className="h-3 w-3" />
                      <span className="tabular">{campaign.utmCampaignValue || campaign.googleAdsCampaignId || 'N/A'}</span>
                    </span>
                    {!isMobile && <span className="text-border">|</span>}
                    <span className="flex items-center gap-1.5">
                      <Calendar className="h-3 w-3" />
                      Criada: <span className="tabular">{new Date(campaign.startDate).toLocaleDateString('pt-BR')}</span>
                    </span>
                    {!isMobile && <span className="text-border">|</span>}
                    <span className="flex items-center gap-1.5">Status: {getStatusBadge(campaign.status)}</span>
                  </div>

                </div>
              </CardContent>
            </Card>
            </Link>
          ))}

          {filteredCampaigns.length === 0 && (
            <Card className="p-8 text-center shadow-card">
              <p className="text-muted-foreground">Nenhuma campanha encontrada.</p>
            </Card>
          )}
        </div>
        )}

        {/* System Info */}
        <Card className="relative overflow-hidden mt-6 p-5 border-border shadow-card">
          <div className="flex items-center gap-2 mb-4">
            <span className="rounded-md bg-info/10 text-info p-1.5"><Zap className="h-4 w-4" /></span>
            <span className="kicker">Sistema Automático de Campanhas</span>
            <span className="hairline-aurora flex-1" />
          </div>
          <div className={`grid ${isMobile ? 'grid-cols-1' : 'grid-cols-2'} gap-4 ${isMobile ? 'text-xs' : 'text-sm'} text-muted-foreground`}>
            <div className="space-y-2">
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Auto-criação:</strong> Campanhas criadas via integração GAM</span></p>
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">UTM tracking:</strong> Revenue atribuído via UTM campaign</span></p>
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Validação:</strong> Apenas IDs válidos (10-12 dígitos) processados</span></p>
            </div>
            <div className="space-y-2">
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Filtros por período:</strong> Dados agregados de daily_campaign_metrics</span></p>
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Revenue líquido:</strong> revenue_converted_revshare (após revshare)</span></p>
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Timezone:</strong> Dados filtrados no fuso de São Paulo</span></p>
            </div>
          </div>
        </Card>
      </div>
    </Layout>
  );
};

const CampaignsSettings = () => {
  const [params, setParams] = useSearchParams();
  const rede: RedeDeCampanhas = params.get('rede') === 'meta' ? 'meta' : 'google';

  const mudarRede = (proximaRede: RedeDeCampanhas) => {
    const proximos = new URLSearchParams(params);
    if (proximaRede === 'meta') proximos.set('rede', 'meta');
    else proximos.delete('rede');
    setParams(proximos, { replace: true });
  };

  return rede === 'meta'
    ? <MetaCampaignsSettingsDemo onNetworkChange={mudarRede} />
    : <GoogleCampaignsSettings onNetworkChange={mudarRede} />;
};

export default CampaignsSettings;
