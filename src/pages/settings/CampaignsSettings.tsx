import React, { useState, useMemo, useEffect } from "react";
import { Layout } from "@/components/layout/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { useToast } from "@/hooks/use-toast";
import { ArrowLeft, Search, Edit, Copy, Pause, Trash2, RefreshCw, Play, Settings, AlertTriangle, User } from "lucide-react";
import { useSupabaseData, Campaign, Project, supabaseDataService } from "@/services/supabaseDataService";
import { useNavigate } from "react-router-dom";
import { DateFilter } from "@/components/dashboard/DateFilter";
import { DataStatus } from "@/components/dashboard/DataStatus";
import { format } from "date-fns";
import { getROASColorCategory, getROASColorStyles, calculateROAS } from "@/utils/roasCalculations";
import { useAuth } from "@/contexts/AuthContext";
import { supabase } from "@/lib/supabase";
import { useUserFilters } from "@/hooks/useUserFilters";

const CampaignsSettings = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { userProfile } = useAuth();
  
  // Estados para filtros
  const [searchTerm, setSearchTerm] = useState("");
  const [projectFilter, setProjectFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
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
  const { allowedProjectIds, allowedCampaignIds } = useUserFilters();

  // Use filtered data based on current selections
  // IMPORTANTE: Só passar os filtros se tiverem valores (não passar arrays vazios)
  const filters = {
    date: selectedDate,
    endDate: selectedEndDate || undefined,
    projectId: projectFilter === "all" ? undefined : projectFilter,
    period: selectedPeriod,
    ...(allowedProjectIds.length > 0 && { userProjectIds: allowedProjectIds }),
    ...(allowedCampaignIds.length > 0 && { userCampaignIds: allowedCampaignIds })
  };

  const { projects, campaigns, loading, error, refresh } = useSupabaseData(filters);

  // Format revenue values when campaigns are loaded
  useEffect(() => {
    if (campaigns && campaigns.length > 0) {
      const formattedValues: {[key: string]: string} = {};
      
      for (const campaign of campaigns) {
        try {
          // The revenue from getCampaignsWithRevenueFiltered is already the correct value
          // It uses revenue_converted when available, otherwise the USD value
          // We just need to format it properly for BRL display
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
    
    return campaigns.filter(campaign => {
      const matchesSearch = campaign.name.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesProject = projectFilter === "all" || campaign.projectId === projectFilter;
      
      // Filtro por projetos do operador
      let matchesUserProjects = true;
      if (userProfile?.role === 'OPERATOR' && allowedProjectIds.length > 0) {
        // Converter projectId para number se necessário
        const campaignProjectId = typeof campaign.projectId === 'string' 
          ? parseInt(campaign.projectId) 
          : campaign.projectId;
        matchesUserProjects = allowedProjectIds.includes(campaignProjectId);
      }
      
      // Filtro por campanhas específicas do operador (se houver)
      let matchesUserCampaigns = true;
      if (userProfile?.role === 'OPERATOR' && allowedCampaignIds.length > 0) {
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
  }, [campaigns, searchTerm, projectFilter, statusFilter, userProfile, allowedProjectIds, allowedCampaignIds]);

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
        return <Badge variant="default" className="bg-green-500">🟢 Ativa</Badge>;
      case 'paused':
        return <Badge variant="secondary" className="bg-yellow-500">🟡 Pausada</Badge>;
      case 'stopped':
        return <Badge variant="destructive" className="bg-red-500">🔴 Parada</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  return (
    <Layout>
      <div className="p-6 space-y-8 max-w-7xl mx-auto">
        {/* Header with Controls */}
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
                Campanhas
              </h1>
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-gradient-to-r from-primary/10 to-purple-500/10 border border-primary/20">
                <Settings className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium text-primary">Configurações</span>
              </div>
            </div>
            <p className="text-muted-foreground">
              Campanhas criadas automaticamente via integração GAM/Google Ads
              {projectFilter !== 'all' && (
                <span className="ml-2 text-primary">
                  • Projeto: {projects.find(p => p.id === projectFilter)?.name || 'Selecionado'}
                </span>
              )}
              {selectedPeriod === 'yesterday' && (
                <span className="ml-2 text-primary">
                  • Data: Ontem ({selectedDate ? format(new Date(selectedDate), 'dd/MM/yyyy') : ''})
                </span>
              )}
              {selectedPeriod === 'custom' && (
                <span className="ml-2 text-primary">
                  • Data: {selectedDate ? format(new Date(selectedDate), 'dd/MM/yyyy') : ''}
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
              {selectedPeriod !== 'custom' && selectedPeriod !== 'range' && (
                <span className="ml-2 text-primary">
                  • Período: {selectedPeriod === 'today' ? 'Hoje' : selectedPeriod === '7d' ? '7 dias' : '30 dias'}
                </span>
              )}
            </p>
          </div>
          
          <div className="flex items-center gap-3 flex-wrap">
            <Select value={projectFilter} onValueChange={setProjectFilter}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Filtrar projeto" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">📂 Todos os Projetos</SelectItem>
                {projects
                  .filter(project => {
                    // Para OPERATORs, mostrar apenas projetos atribuídos
                    if (userProfile?.role === 'OPERATOR' && allowedProjectIds.length > 0) {
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
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Filtrar por performance" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all"> Todas as Campanhas </SelectItem>
                <SelectItem value="green">🟢 Campanhas Verdes (ROAS ≥ 80%)</SelectItem>
                <SelectItem value="yellow">🟡 Campanhas Amarelas (ROAS 40-79%)</SelectItem>
                <SelectItem value="orange">🟠 Campanhas Laranjas (ROAS 0-39%)</SelectItem>
                <SelectItem value="red">🔴 Campanhas Vermelhas (ROAS negativo)</SelectItem>
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
            
            <Button onClick={handleRefresh} variant="outline" size="sm">
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

        {/* Search Bar */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar campanhas..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-sm">
              {filteredCampaigns.length} {filteredCampaigns.length === 1 ? 'campanha' : 'campanhas'}
            </Badge>
            {statusFilter === "all" && filteredCampaigns && filteredCampaigns.length > 0 && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  🟢 {filteredCampaigns.filter(c => {
                    const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                    return getCampaignColorCategory(roasExcess) === "green";
                  }).length}
                </span>
                <span className="flex items-center gap-1">
                  🟡 {filteredCampaigns.filter(c => {
                    const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                    return getCampaignColorCategory(roasExcess) === "yellow";
                  }).length}
                </span>
                <span className="flex items-center gap-1">
                  🟠 {filteredCampaigns.filter(c => {
                    const roasExcess = calculateROAS(c.revenue || 0, c.investment || 0);
                    return getCampaignColorCategory(roasExcess) === "orange";
                  }).length}
                </span>
                <span className="flex items-center gap-1">
                  🔴 {filteredCampaigns.filter(c => {
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
          <Card className="p-6 border-red-200 bg-red-50">
            <div className="flex items-center gap-2 text-red-800">
              <AlertTriangle className="h-5 w-5" />
              <h3 className="font-medium">Erro ao carregar campanhas</h3>
            </div>
            <p className="text-red-700 text-sm mt-2">{error}</p>
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
          {filteredCampaigns.map(campaign => (
            <Card 
              key={campaign.id} 
              className="p-6 cursor-pointer hover:shadow-lg transition-shadow duration-200" 
              onClick={() => navigate(`/dashboard/campaign/${campaign.utmCampaignValue || campaign.id}`)}
            >
              <CardContent className="p-0">
                <div className="space-y-4">
                  {/* Campaign Header */}
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold text-lg">
                        {getStatusBadge(campaign.status)} {campaign.name}
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        📂 {getProjectName(campaign.projectId)}
                      </p>
                    </div>
                  </div>

                  {/* Metrics Gasto vs Revenue */}
                  <div>
                    <h4 className="font-medium mb-3">📊 Performance Financeira ({
                      selectedPeriod === 'today' ? 'Hoje' :
                      selectedPeriod === 'yesterday' ? 'Ontem' :
                      selectedPeriod === '7d' ? 'Últimos 7 dias' :
                      selectedPeriod === '30d' ? 'Últimos 30 dias' :
                      selectedPeriod === 'range' && selectedEndDate ?
                        `${selectedDate} até ${selectedEndDate}` :
                        `Data: ${new Date(selectedDate).toLocaleDateString('pt-BR')}`
                    }):</h4>
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div className="text-center p-3 bg-blue-50 rounded-lg">
                        <p className="text-xs text-muted-foreground mb-1">Gasto</p>
                        <p className="font-semibold text-slate-800">{new Intl.NumberFormat('pt-BR', {
                          style: 'currency',
                          currency: 'BRL'
                        }).format(campaign.investment || 0)}</p>
                      </div>
                      <div className="text-center p-3 bg-green-50 rounded-lg">
                        <p className="text-xs text-muted-foreground mb-1">Revenue</p>
                        <p className="font-semibold text-green-600">{formattedRevenues[campaign.id] || 'R$ 0,00'}</p>
                      </div>
                      <div className={`text-center p-3 rounded-lg border ${(() => {
                        const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
                        return getROIColor(roasExcess);
                      })()}`}>
                        <p className="text-xs text-muted-foreground mb-1">ROAS</p>
                        <p className="font-semibold">{(() => {
                          const roasExcess = calculateROAS(campaign.revenue || 0, campaign.investment || 0);
                          return roasExcess.toFixed(1);
                        })()}%</p>
                      </div>
                    </div>

                  </div>

                  {/* Campaign Details */}
                  <div className="flex items-center gap-4 text-sm">
                    <span>🎯 ID: {campaign.utmCampaignValue || campaign.googleAdsCampaignId || 'N/A'}</span>
                    <span>|</span>
                    <span>📅 Criada: {new Date(campaign.startDate).toLocaleDateString('pt-BR')}</span>
                    <span>|</span>
                    <span>Status: {getStatusBadge(campaign.status)}</span>
                  </div>

                </div>
              </CardContent>
            </Card>
          ))}

          {filteredCampaigns.length === 0 && (
            <Card className="p-8 text-center">
              <p className="text-muted-foreground">Nenhuma campanha encontrada.</p>
            </Card>
          )}
        </div>
        )}

        {/* System Info */}
        <Card className="mt-6 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
          <h3 className="font-medium text-blue-800 mb-3 flex items-center gap-2">
            🤖 Sistema Automático de Campanhas
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm text-blue-700">
            <div className="space-y-2">
              <p>✓ <strong>Auto-criação:</strong> Campanhas criadas via integração GAM</p>
              <p>✓ <strong>UTM tracking:</strong> Revenue atribuído via UTM campaign</p>
              <p>✓ <strong>Validação:</strong> Apenas IDs válidos (10-12 dígitos) processados</p>
            </div>
            <div className="space-y-2">
              <p>✓ <strong>Filtros por período:</strong> Dados agregados de daily_campaign_metrics</p>
              <p>✓ <strong>Conversão automática:</strong> Revenue em BRL via revenue_converted</p>
              <p>✓ <strong>Timezone:</strong> Dados filtrados no fuso de São Paulo</p>
            </div>
          </div>
        </Card>
      </div>
    </Layout>
  );
};

export default CampaignsSettings;