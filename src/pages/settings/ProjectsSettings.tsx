import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Modal, useModal } from "@/components/ui/modal";
import { Layout } from "@/components/layout/Layout";
import { 
  Plus, 
  Edit, 
  Trash2, 
  FolderOpen, 
  Calendar,
  Users,
  DollarSign,
  MoreHorizontal,
  Search
} from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

interface Project {
  id: string;
  name: string;
  description: string;
  budget: number;
  startDate: string;
  endDate?: string;
  status: "active" | "paused" | "completed";
  campaignsCount: number;
  totalSpent: number;
  manager: string;
}

const mockProjects: Project[] = [
  {
    id: "1",
    name: "E-commerce Store",
    description: "Campanhas para loja online de roupas",
    budget: 50000,
    startDate: "2024-01-01",
    endDate: "2024-12-31",
    status: "active",
    campaignsCount: 4,
    totalSpent: 15200,
    manager: "João Silva"
  },
  {
    id: "2", 
    name: "SaaS Platform",
    description: "Aquisição de usuários para plataforma SaaS",
    budget: 75000,
    startDate: "2024-02-01",
    status: "active",
    campaignsCount: 3,
    totalSpent: 18600,
    manager: "Maria Santos"
  },
  {
    id: "3",
    name: "Mobile App",
    description: "Download e engajamento do app mobile",
    budget: 30000,
    startDate: "2024-01-15",
    endDate: "2024-06-15",
    status: "completed",
    campaignsCount: 3,
    totalSpent: 28500,
    manager: "Pedro Costa"
  }
];

export default function ProjectsSettings() {
  const [projects, setProjects] = useState<Project[]>(mockProjects);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const addModal = useModal();
  const editModal = useModal();
  const deleteModal = useModal();

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('pt-BR');
  };

  const getStatusColor = (status: Project["status"]) => {
    switch (status) {
      case "active": return "success";
      case "paused": return "warning";
      case "completed": return "secondary";
      default: return "default";
    }
  };

  const getStatusLabel = (status: Project["status"]) => {
    switch (status) {
      case "active": return "Ativo";
      case "paused": return "Pausado";
      case "completed": return "Concluído";
      default: return status;
    }
  };

  const filteredProjects = projects.filter(project =>
    project.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    project.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleAddProject = () => {
    // Aqui você implementaria a lógica para adicionar projeto
    console.log("Adicionar projeto");
    addModal.closeModal();
  };

  const handleEditProject = () => {
    // Aqui você implementaria a lógica para editar projeto
    console.log("Editar projeto", selectedProject);
    editModal.closeModal();
  };

  const handleDeleteProject = () => {
    if (selectedProject) {
      setProjects(projects.filter(p => p.id !== selectedProject.id));
      setSelectedProject(null);
      deleteModal.closeModal();
    }
  };

  return (
    <Layout>
      <div className="p-6 space-y-8 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between animate-fade-in">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-dashboard bg-clip-text text-transparent">
              Gerenciar Projetos
            </h1>
            <p className="text-muted-foreground mt-2">
              Configure e gerencie seus projetos de campanhas
            </p>
          </div>
          <Button onClick={addModal.openModal} className="gap-2">
            <Plus className="h-4 w-4" />
            Novo Projeto
          </Button>
        </div>

        {/* Search and Filters */}
        <Card className="shadow-card animate-scale-in">
          <CardContent className="p-6">
            <div className="flex gap-4">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                <Input
                  placeholder="Buscar projetos..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Projects List */}
        <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3 animate-fade-in">
          {filteredProjects.map((project) => (
            <Card key={project.id} className="shadow-card hover:shadow-glow transition-all duration-300">
              <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 bg-primary/10 rounded-lg flex items-center justify-center">
                    <FolderOpen className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle className="text-lg">{project.name}</CardTitle>
                    <CardDescription className="mt-1">{project.description}</CardDescription>
                  </div>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem 
                      onClick={() => {
                        setSelectedProject(project);
                        editModal.openModal();
                      }}
                    >
                      <Edit className="mr-2 h-4 w-4" />
                      Editar
                    </DropdownMenuItem>
                    <DropdownMenuItem 
                      onClick={() => {
                        setSelectedProject(project);
                        deleteModal.openModal();
                      }}
                      className="text-destructive"
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      Excluir
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Status</span>
                  <Badge variant={getStatusColor(project.status) as any}>
                    {getStatusLabel(project.status)}
                  </Badge>
                </div>
                
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Orçamento</span>
                    <p className="font-medium">{formatCurrency(project.budget)}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Gasto</span>
                    <p className="font-medium">{formatCurrency(project.totalSpent)}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Users className="h-3 w-3" />
                      Campanhas
                    </span>
                    <p className="font-medium">{project.campaignsCount}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      Início
                    </span>
                    <p className="font-medium">{formatDate(project.startDate)}</p>
                  </div>
                </div>

                <div className="pt-2 border-t">
                  <span className="text-xs text-muted-foreground">Gerente: {project.manager}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Add Project Modal */}
        <Modal
          isOpen={addModal.isOpen}
          onClose={addModal.closeModal}
          title="Novo Projeto"
          description="Criar um novo projeto de campanhas"
          size="lg"
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="name">Nome do Projeto</Label>
                <Input id="name" placeholder="Digite o nome..." />
              </div>
              <div>
                <Label htmlFor="manager">Gerente</Label>
                <Input id="manager" placeholder="Nome do gerente..." />
              </div>
            </div>
            
            <div>
              <Label htmlFor="description">Descrição</Label>
              <Input id="description" placeholder="Descrição do projeto..." />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <Label htmlFor="budget">Orçamento</Label>
                <Input id="budget" type="number" placeholder="0" />
              </div>
              <div>
                <Label htmlFor="startDate">Data Início</Label>
                <Input id="startDate" type="date" />
              </div>
              <div>
                <Label htmlFor="endDate">Data Fim</Label>
                <Input id="endDate" type="date" />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={addModal.closeModal}>
                Cancelar
              </Button>
              <Button onClick={handleAddProject}>
                Criar Projeto
              </Button>
            </div>
          </div>
        </Modal>

        {/* Edit Project Modal */}
        <Modal
          isOpen={editModal.isOpen}
          onClose={editModal.closeModal}
          title="Editar Projeto"
          description="Modificar informações do projeto"
          size="lg"
        >
          {selectedProject && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="edit-name">Nome do Projeto</Label>
                  <Input id="edit-name" defaultValue={selectedProject.name} />
                </div>
                <div>
                  <Label htmlFor="edit-manager">Gerente</Label>
                  <Input id="edit-manager" defaultValue={selectedProject.manager} />
                </div>
              </div>
              
              <div>
                <Label htmlFor="edit-description">Descrição</Label>
                <Input id="edit-description" defaultValue={selectedProject.description} />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <Label htmlFor="edit-budget">Orçamento</Label>
                  <Input id="edit-budget" type="number" defaultValue={selectedProject.budget} />
                </div>
                <div>
                  <Label htmlFor="edit-startDate">Data Início</Label>
                  <Input id="edit-startDate" type="date" defaultValue={selectedProject.startDate} />
                </div>
                <div>
                  <Label htmlFor="edit-endDate">Data Fim</Label>
                  <Input id="edit-endDate" type="date" defaultValue={selectedProject.endDate} />
                </div>
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
          title="Excluir Projeto"
          description="Esta ação não pode ser desfeita"
          size="sm"
        >
          {selectedProject && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Tem certeza que deseja excluir o projeto <strong>{selectedProject.name}</strong>?
                Todas as campanhas associadas também serão removidas.
              </p>
              
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