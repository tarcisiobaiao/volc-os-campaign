import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Modal, useModal } from "@/components/ui/modal";
import { Layout } from "@/components/layout/Layout";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { 
  Plus, 
  Edit, 
  Trash2, 
  FolderOpen, 
  Calendar,
  Settings,
  BarChart3,
  Pause,
  Play,
  Search,
  CheckCircle,
  Link,
  DollarSign,
  Clock,
  ArrowLeft
} from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useNavigate } from "react-router-dom";

interface ProjectIntegration {
  googleAds: {
    connected: boolean;
    account: string;
    id: string;
  };
  gam: {
    connected: boolean;
    account: string;
  };
  adxDiscount: number;
}

interface ProjectConfig {
  id: string;
  name: string;
  domain: string;
  status: "active" | "paused" | "completed";
  campaignsCount: number;
  createdDate: string;
  lastSync: string;
  integrations: ProjectIntegration;
}

const mockProjectsConfig: ProjectConfig[] = [
  {
    id: "1",
    name: "direito2.com.br",
    domain: "https://direito2.com.br",
    status: "active",
    campaignsCount: 23,
    createdDate: "15/03/2024",
    lastSync: "há 2min",
    integrations: {
      googleAds: {
        connected: true,
        account: "Felipe Ltda",
        id: "977-272-9198"
      },
      gam: {
        connected: true,
        account: "direito2.com.br"
      },
      adxDiscount: 10
    }
  },
  {
    id: "2",
    name: "folhadosul.com.br", 
    domain: "https://folhadosul.com.br",
    status: "active",
    campaignsCount: 9,
    createdDate: "22/04/2024",
    lastSync: "há 5min",
    integrations: {
      googleAds: {
        connected: true,
        account: "Felipe Ltda",
        id: "977-272-9198"
      },
      gam: {
        connected: true,
        account: "folhadosul.com.br"
      },
      adxDiscount: 10
    }
  },
  {
    id: "3",
    name: "mundodigital.com.br",
    domain: "https://mundodigital.com.br", 
    status: "paused",
    campaignsCount: 5,
    createdDate: "08/05/2024",
    lastSync: "há 1h",
    integrations: {
      googleAds: {
        connected: true,
        account: "Felipe Ltda",
        id: "977-272-9198"
      },
      gam: {
        connected: false,
        account: ""
      },
      adxDiscount: 15
    }
  }
];

export default function ProjectsSettings() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectConfig[]>(mockProjectsConfig);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedProject, setSelectedProject] = useState<ProjectConfig | null>(null);
  const [newProject, setNewProject] = useState({
    name: "",
    domain: "",
    googleAdsConnection: "existing",
    gamConnection: "existing", 
    adxDiscount: 10,
    startDate: "2025-08-01"
  });
  const addModal = useModal();
  const editModal = useModal();
  const deleteModal = useModal();

  const getStatusColor = (status: ProjectConfig["status"]) => {
    switch (status) {
      case "active": return "success";
      case "paused": return "warning"; 
      case "completed": return "secondary";
      default: return "default";
    }
  };

  const getStatusLabel = (status: ProjectConfig["status"]) => {
    switch (status) {
      case "active": return "✅ Ativo";
      case "paused": return "⏸️ Pausado";
      case "completed": return "✔️ Concluído";
      default: return status;
    }
  };

  const filteredProjects = projects.filter(project =>
    project.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    project.domain.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleAddProject = () => {
    const newId = (projects.length + 1).toString();
    const projectToAdd: ProjectConfig = {
      id: newId,
      name: newProject.name,
      domain: newProject.domain,
      status: "active",
      campaignsCount: 0,
      createdDate: new Date().toLocaleDateString('pt-BR'),
      lastSync: "há poucos segundos",
      integrations: {
        googleAds: {
          connected: newProject.googleAdsConnection === "existing",
          account: "Felipe Ltda",
          id: "977-272-9198"
        },
        gam: {
          connected: newProject.gamConnection === "existing",
          account: newProject.name
        },
        adxDiscount: newProject.adxDiscount
      }
    };
    setProjects([...projects, projectToAdd]);
    setNewProject({
      name: "",
      domain: "",
      googleAdsConnection: "existing",
      gamConnection: "existing",
      adxDiscount: 10,
      startDate: "2025-08-01"
    });
    addModal.closeModal();
  };

  const handleEditProject = () => {
    editModal.closeModal();
  };

  const handleDeleteProject = () => {
    if (selectedProject) {
      setProjects(projects.filter(p => p.id !== selectedProject.id));
      setSelectedProject(null);
      deleteModal.closeModal();
    }
  };

  const handleToggleStatus = (projectId: string) => {
    setProjects(projects.map(p => 
      p.id === projectId 
        ? { ...p, status: p.status === "active" ? "paused" : "active" }
        : p
    ));
  };

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
                ⚙️ Configurações &gt; Projetos
              </h1>
              <p className="text-muted-foreground mt-2">
                Configure e gerencie seus projetos e integrações
              </p>
            </div>
          </div>
          <Button onClick={addModal.openModal} className="gap-2">
            <Plus className="h-4 w-4" />
            Novo Projeto
          </Button>
        </div>

        {/* Search */}
        <div className="flex gap-4 animate-scale-in">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
            <Input
              placeholder="🔍 Buscar projetos..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        {/* Projects List */}
        <div className="space-y-6 animate-fade-in">
          {filteredProjects.map((project) => (
            <Card key={project.id} className="shadow-card hover:shadow-glow transition-all duration-300">
              <CardHeader className="pb-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 bg-primary/10 rounded-lg flex items-center justify-center">
                      <FolderOpen className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-xl">📂 {project.name}</CardTitle>
                      <CardDescription className="text-sm text-muted-foreground mt-1">
                        {project.domain}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => {
                      setSelectedProject(project);
                      editModal.openModal();
                    }}>
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => {
                      setSelectedProject(project);
                      deleteModal.openModal();
                    }} className="text-destructive hover:text-destructive">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="space-y-4">
                {/* Integrações */}
                <div>
                  <h4 className="font-medium mb-3">🔗 Integrações:</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-green-500" />
                      <span>Google Ads: {project.integrations.googleAds.account} ({project.integrations.googleAds.id})</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-green-500" />
                      <span>GAM: {project.integrations.gam.account}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <DollarSign className="h-4 w-4 text-blue-500" />
                      <span>Desconto AdX: {project.integrations.adxDiscount}%</span>
                    </div>
                  </div>
                </div>

                {/* Status e Info */}
                <div className="grid grid-cols-2 gap-6 pt-4 border-t">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-muted-foreground">📊 Status:</span>
                      <Badge variant={getStatusColor(project.status) as any}>
                        {getStatusLabel(project.status)}
                      </Badge>
                      <span className="text-muted-foreground">| Campanhas: {project.campaignsCount}</span>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="text-sm text-muted-foreground">
                      📅 Criado: {project.createdDate} | Última sync: {project.lastSync}
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex gap-2 pt-4 border-t">
                  <Button variant="outline" size="sm" className="gap-2">
                    <Settings className="h-4 w-4" />
                    Configurar
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="gap-2"
                    onClick={() => navigate(`/dashboard/project/${project.id}`)}
                  >
                    <BarChart3 className="h-4 w-4" />
                    Ver Dashboard
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="gap-2"
                    onClick={() => handleToggleStatus(project.id)}
                  >
                    {project.status === "active" ? (
                      <>
                        <Pause className="h-4 w-4" />
                        Pausar
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4" />
                        Ativar
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Add Project Modal */}
        <Modal
          isOpen={addModal.isOpen}
          onClose={addModal.closeModal}
          title="📂 Cadastrar Novo Projeto"
          size="lg"
        >
          <div className="space-y-6">
            <div>
              <Label htmlFor="project-name">📝 Nome do Projeto:</Label>
              <Input 
                id="project-name" 
                placeholder="Ex: meusite.com.br"
                value={newProject.name}
                onChange={(e) => setNewProject({...newProject, name: e.target.value})}
                className="mt-1"
              />
            </div>
            
            <div>
              <Label htmlFor="project-url">🌐 URL Principal:</Label>
              <Input 
                id="project-url" 
                placeholder="https://meusite.com.br"
                value={newProject.domain}
                onChange={(e) => setNewProject({...newProject, domain: e.target.value})}
                className="mt-1"
              />
            </div>

            <div className="space-y-4">
              <Label>🔗 Google Ads:</Label>
              <RadioGroup 
                value={newProject.googleAdsConnection} 
                onValueChange={(value) => setNewProject({...newProject, googleAdsConnection: value})}
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="existing" id="ads-existing" />
                  <Label htmlFor="ads-existing">○ Conectar conta existente</Label>
                </div>
                {newProject.googleAdsConnection === "existing" && (
                  <Select defaultValue="felipe-ltda">
                    <SelectTrigger className="ml-6 w-64">
                      <SelectValue placeholder="Selecionar conta" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="felipe-ltda">Felipe Ltda (977-272-9198)</SelectItem>
                      <SelectItem value="other">Outra conta...</SelectItem>
                    </SelectContent>
                  </Select>
                )}
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="new" id="ads-new" />
                  <Label htmlFor="ads-new">○ Criar nova conexão</Label>
                </div>
                {newProject.googleAdsConnection === "new" && (
                  <Button variant="outline" className="ml-6 gap-2">
                    <Link className="h-4 w-4" />
                    Autorizar Google Ads
                  </Button>
                )}
              </RadioGroup>
            </div>

            <div className="space-y-4">
              <Label>🔗 Google Ad Manager:</Label>
              <RadioGroup 
                value={newProject.gamConnection} 
                onValueChange={(value) => setNewProject({...newProject, gamConnection: value})}
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="existing" id="gam-existing" />
                  <Label htmlFor="gam-existing">○ Conectar GAM existente</Label>
                </div>
                {newProject.gamConnection === "existing" && (
                  <Select defaultValue="current-gam">
                    <SelectTrigger className="ml-6 w-64">
                      <SelectValue placeholder="Selecionar GAM" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="current-gam">GAM Principal</SelectItem>
                      <SelectItem value="other">Outro GAM...</SelectItem>
                    </SelectContent>
                  </Select>
                )}
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="new" id="gam-new" />
                  <Label htmlFor="gam-new">○ Criar nova conexão</Label>
                </div>
                {newProject.gamConnection === "new" && (
                  <Button variant="outline" className="ml-6 gap-2">
                    <Link className="h-4 w-4" />
                    Autorizar GAM
                  </Button>
                )}
              </RadioGroup>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="adx-discount">💰 Desconto AdX (%):</Label>
                <Input 
                  id="adx-discount" 
                  type="number"
                  value={newProject.adxDiscount}
                  onChange={(e) => setNewProject({...newProject, adxDiscount: Number(e.target.value)})}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="start-date">📅 Data de Início:</Label>
                <Input 
                  id="start-date" 
                  type="date"
                  value={newProject.startDate}
                  onChange={(e) => setNewProject({...newProject, startDate: e.target.value})}
                  className="mt-1"
                />
              </div>
            </div>

            <div className="flex justify-center gap-4 pt-6">
              <Button variant="outline" onClick={addModal.closeModal}>
                Cancelar
              </Button>
              <Button onClick={handleAddProject} className="gap-2">
                <Plus className="h-4 w-4" />
                Salvar Projeto
              </Button>
            </div>
          </div>
        </Modal>

        {/* Edit Project Modal */}
        <Modal
          isOpen={editModal.isOpen}
          onClose={editModal.closeModal}
          title="✏️ Editar Projeto"
          description="Modificar configurações do projeto"
          size="lg"
        >
          {selectedProject && (
            <div className="space-y-4">
              <div className="p-4 bg-muted/50 rounded-lg">
                <h4 className="font-medium mb-2">📂 {selectedProject.name}</h4>
                <p className="text-sm text-muted-foreground">{selectedProject.domain}</p>
              </div>
              
              <div className="text-sm text-muted-foreground">
                💡 Para editar configurações avançadas, acesse o painel de configurações do projeto.
              </div>

              <div className="flex justify-end gap-2 pt-4">
                <Button variant="outline" onClick={editModal.closeModal}>
                  Cancelar
                </Button>
                <Button onClick={handleEditProject}>
                  Salvar Alterações
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
          {selectedProject && (
            <div className="space-y-4">
              <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-lg">
                <p className="text-sm">
                  Tem certeza que deseja excluir o projeto <strong>{selectedProject.name}</strong>?
                </p>
                <p className="text-xs text-muted-foreground mt-2">
                  • Todas as {selectedProject.campaignsCount} campanhas serão removidas<br/>
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