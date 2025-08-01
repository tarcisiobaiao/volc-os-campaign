import React, { useState, useMemo } from "react";
import { Layout } from "@/components/layout/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Modal, useModal } from "@/components/ui/modal";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { ArrowLeft, Search, Plus, Edit, Copy, Pause, Trash2, Minus } from "lucide-react";
import { useMockData } from "@/services/mockDataService";
import { useNavigate } from "react-router-dom";

interface CampaignUrl {
  id: string;
  url: string;
  isPrimary: boolean;
}

interface CampaignFormData {
  projectId: string;
  name: string;
  urls: CampaignUrl[];
  startDate: string;
  status: "active" | "paused";
  notes: string;
}

const CampaignsSettings = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const mockData = useMockData();
  const { isOpen, openModal, closeModal } = useModal();
  
  const [searchTerm, setSearchTerm] = useState("");
  const [projectFilter, setProjectFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [formData, setFormData] = useState<CampaignFormData>({
    projectId: "",
    name: "",
    urls: [{ id: "1", url: "", isPrimary: true }],
    startDate: new Date().toISOString().split('T')[0],
    status: "active",
    notes: ""
  });

  const filteredCampaigns = useMemo(() => {
    if (!mockData.campaigns) return [];
    
    return mockData.campaigns.filter(campaign => {
      const matchesSearch = campaign.name.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesProject = projectFilter === "all" || campaign.projectId === projectFilter;
      const matchesStatus = statusFilter === "all" || campaign.status === statusFilter;
      
      return matchesSearch && matchesProject && matchesStatus;
    });
  }, [mockData.campaigns, searchTerm, projectFilter, statusFilter]);

  const getProjectName = (projectId: string) => {
    return mockData.projects.find(p => p.id === projectId)?.name || projectId;
  };

  const addUrl = () => {
    const newUrl: CampaignUrl = {
      id: Date.now().toString(),
      url: "",
      isPrimary: false
    };
    setFormData(prev => ({
      ...prev,
      urls: [...prev.urls, newUrl]
    }));
  };

  const removeUrl = (urlId: string) => {
    setFormData(prev => ({
      ...prev,
      urls: prev.urls.filter(url => url.id !== urlId)
    }));
  };

  const updateUrl = (urlId: string, newUrl: string) => {
    setFormData(prev => ({
      ...prev,
      urls: prev.urls.map(url => 
        url.id === urlId ? { ...url, url: newUrl } : url
      )
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.projectId || !formData.name || !formData.urls[0].url) {
      toast({
        title: "Erro",
        description: "Por favor, preencha todos os campos obrigatórios.",
        variant: "destructive"
      });
      return;
    }

    // Simulate campaign creation
    toast({
      title: "Sucesso",
      description: "Campanha criada com sucesso!",
    });
    
    closeModal();
    // Reset form
    setFormData({
      projectId: "",
      name: "",
      urls: [{ id: "1", url: "", isPrimary: true }],
      startDate: new Date().toISOString().split('T')[0],
      status: "active",
      notes: ""
    });
  };

  const handleAction = (action: string, campaignId: string, campaignName: string) => {
    switch (action) {
      case 'edit':
        toast({
          title: "Editar Campanha",
          description: `Editando campanha: ${campaignName}`,
        });
        break;
      case 'copy':
        toast({
          title: "Campanha Copiada",
          description: `Campanha ${campaignName} copiada com sucesso!`,
        });
        break;
      case 'pause':
        toast({
          title: "Campanha Pausada",
          description: `Campanha ${campaignName} foi pausada.`,
        });
        break;
      case 'delete':
        toast({
          title: "Campanha Excluída",
          description: `Campanha ${campaignName} foi excluída.`,
          variant: "destructive"
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
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(-1)}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Voltar
            </Button>
            <div>
              <h1 className="text-2xl font-bold">⚙️ Configurações &gt; Campanhas</h1>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-4 p-4 bg-card rounded-lg border">
          <div className="flex items-center gap-2">
            <Label>Projeto:</Label>
            <Select value={projectFilter} onValueChange={setProjectFilter}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {mockData.projects.map(project => (
                  <SelectItem key={project.id} value={project.id}>
                    {project.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <Label>Status:</Label>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-32">
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="active">Ativas</SelectItem>
                <SelectItem value="paused">Pausadas</SelectItem>
                <SelectItem value="stopped">Paradas</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar campanhas..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 w-64"
              />
            </div>
            <Button onClick={openModal} className="gap-2">
              <Plus className="h-4 w-4" />
              Nova Campanha
            </Button>
          </div>
        </div>

        {/* Campaigns List */}
        <div className="space-y-4">
          {filteredCampaigns.map(campaign => (
            <Card key={campaign.id} className="p-6">
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

                  {/* URLs do Funil */}
                  <div>
                    <h4 className="font-medium mb-2">🎯 URLs do Funil:</h4>
                    <div className="space-y-1 ml-4">
                      {campaign.urls?.map((url, index) => (
                        <p key={index} className="text-sm">
                          {index + 1}. {url}
                        </p>
                      )) || [
                        <p key="1" className="text-sm">1. {getProjectName(campaign.projectId).toLowerCase().replace('.com.br', '.com.br')}/exemplo-url</p>
                      ]}
                    </div>
                  </div>

                  {/* Performance */}
                  <div className="flex items-center gap-4 text-sm">
                    <span>📊 Performance: ROAS {campaign.roas}%</span>
                    <span>|</span>
                    <span>Status: {getStatusBadge(campaign.status)}</span>
                  </div>

                  {/* Dates */}
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span>📅 Criada: {new Date(campaign.startDate).toLocaleDateString('pt-BR')}</span>
                    <span>|</span>
                    <span>Modificada: há {Math.floor(Math.random() * 7) + 1} dias</span>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 pt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleAction('edit', campaign.id, campaign.name)}
                      className="gap-2"
                    >
                      <Edit className="h-4 w-4" />
                      Editar
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleAction('copy', campaign.id, campaign.name)}
                      className="gap-2"
                    >
                      <Copy className="h-4 w-4" />
                      Copiar
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleAction('pause', campaign.id, campaign.name)}
                      className="gap-2"
                    >
                      <Pause className="h-4 w-4" />
                      Pausar
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleAction('delete', campaign.id, campaign.name)}
                      className="gap-2"
                    >
                      <Trash2 className="h-4 w-4" />
                      Excluir
                    </Button>
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

        {/* New Campaign Modal */}
        <Modal
          isOpen={isOpen}
          onClose={closeModal}
          title="🎯 Cadastrar Nova Campanha"
          size="lg"
        >
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Project Selection */}
            <div className="space-y-2">
              <Label htmlFor="project">📂 Projeto: *</Label>
              <Select value={formData.projectId} onValueChange={(value) => setFormData(prev => ({ ...prev, projectId: value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecione um projeto" />
                </SelectTrigger>
                <SelectContent>
                  {mockData.projects.map(project => (
                    <SelectItem key={project.id} value={project.id}>
                      {project.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Campaign Name */}
            <div className="space-y-2">
              <Label htmlFor="name">🏷️ Nome da Campanha: *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                placeholder="D2-XXX/Tema/projeto.com.br/url-slug"
                required
              />
            </div>

            {/* URLs */}
            <div className="space-y-4">
              <Label>🎯 URLs do Funil:</Label>
              
              {formData.urls.map((urlItem, index) => (
                <div key={urlItem.id} className="space-y-2">
                  <Label className="text-sm">
                    {index === 0 ? "URL Principal (obrigatória):" : "URL Secundária:"}
                  </Label>
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <Input
                        value={urlItem.url}
                        onChange={(e) => updateUrl(urlItem.id, e.target.value)}
                        placeholder={`${formData.projectId ? getProjectName(formData.projectId).toLowerCase() : 'projeto.com.br'}/exemplo-url`}
                        required={index === 0}
                      />
                    </div>
                    {index > 0 && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => removeUrl(urlItem.id)}
                      >
                        <Minus className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              ))}
              
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addUrl}
                className="gap-2"
              >
                <Plus className="h-4 w-4" />
                Adicionar URL
              </Button>
            </div>

            {/* Start Date */}
            <div className="space-y-2">
              <Label htmlFor="startDate">📅 Data de Início:</Label>
              <Input
                id="startDate"
                type="date"
                value={formData.startDate}
                onChange={(e) => setFormData(prev => ({ ...prev, startDate: e.target.value }))}
              />
            </div>

            {/* Status */}
            <div className="space-y-2">
              <Label>📊 Status Inicial:</Label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="status"
                    value="active"
                    checked={formData.status === "active"}
                    onChange={(e) => setFormData(prev => ({ ...prev, status: e.target.value as "active" | "paused" }))}
                  />
                  Ativa
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="status"
                    value="paused"
                    checked={formData.status === "paused"}
                    onChange={(e) => setFormData(prev => ({ ...prev, status: e.target.value as "active" | "paused" }))}
                  />
                  Pausada
                </label>
              </div>
            </div>

            {/* Notes */}
            <div className="space-y-2">
              <Label htmlFor="notes">📝 Observações:</Label>
              <Textarea
                id="notes"
                value={formData.notes}
                onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))}
                placeholder="Observações sobre a campanha..."
                rows={3}
              />
            </div>

            {/* Form Actions */}
            <div className="flex justify-end gap-4 pt-4">
              <Button type="button" variant="outline" onClick={closeModal}>
                Cancelar
              </Button>
              <Button type="submit">
                Salvar Campanha
              </Button>
            </div>
          </form>
        </Modal>
      </div>
    </Layout>
  );
};

export default CampaignsSettings;