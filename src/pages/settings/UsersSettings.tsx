import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal, useModal } from "@/components/ui/modal";
import { Layout } from "@/components/layout/Layout";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Edit, Trash2, Users, Shield, Search, FolderOpen, CheckCircle2, Circle, AlertCircle, Lock } from "lucide-react";
import { usersService, User, CreateUserInput } from "@/services/usersService";
import { useAuth } from "@/contexts/AuthContext";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";

export default function UsersSettings() {
  const { userProfile } = useAuth();
  const { toast } = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [projects, setProjects] = useState<{ id: number; project_name: string }[]>([]);
  const [campaigns, setCampaigns] = useState<{ id: number; campaign_id: string; campaign_name: string; project_id: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [selectedUserProjects, setSelectedUserProjects] = useState<number[]>([]);
  const [selectedUserCampaigns, setSelectedUserCampaigns] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isLoadingEdit, setIsLoadingEdit] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [assignedCampaigns, setAssignedCampaigns] = useState<string[]>([]);

  const addModal = useModal();
  const editModal = useModal();
  const deleteModal = useModal();

  // Limpar dados ao fechar modais
  const handleCloseAddModal = () => {
    addModal.close();
    setNewUser({
      name: "",
      email: "",
      role: "OPERATOR",
      password: "",
      commission_percentage: 0,
      project_ids: [],
      campaign_ids: []
    });
    setCampaigns([]);
  };

  const handleCloseEditModal = () => {
    editModal.close();
    setEditUser({
      name: "",
      email: "",
      role: "OPERATOR",
      commission_percentage: 0,
      project_ids: [],
      campaign_ids: []
    });
    setCampaigns([]);
    setSelectedUser(null);
  };

  const [newUser, setNewUser] = useState<CreateUserInput>({
    name: "",
    email: "",
    role: "OPERATOR",
    password: "",
    commission_percentage: 0,
    project_ids: [],
    campaign_ids: []
  });

  const [editUser, setEditUser] = useState<Partial<CreateUserInput>>({
    name: "",
    email: "",
    role: "OPERATOR",
    commission_percentage: 0,
    project_ids: [],
    campaign_ids: []
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [usersData, projectsData] = await Promise.all([
        usersService.getAll(),
        usersService.getAllProjects()
      ]);
      setUsers(usersData);
      setProjects(projectsData);
      console.log('📊 Dados carregados:', { users: usersData.length, projects: projectsData.length });
    } catch (error) {
      console.error("Erro ao carregar dados:", error);
      toast({
        title: "Erro",
        description: "Não foi possível carregar os dados",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    console.log('🔨 Criando usuário:', newUser);

    if (!newUser.name.trim() || !newUser.email.trim() || !newUser.password.trim()) {
      toast({
        title: "Campos obrigatórios",
        description: "Preencha todos os campos obrigatórios",
        variant: "destructive"
      });
      return;
    }

    if (newUser.role === "OPERATOR" && (!newUser.project_ids || newUser.project_ids.length === 0)) {
      toast({
        title: "Selecione projetos",
        description: "Operadores precisam ter pelo menos um projeto associado",
        variant: "destructive"
      });
      return;
    }

    try {
      setIsCreating(true);
      console.log('✅ Salvando novo usuário:', {
        projetos: newUser.project_ids,
        campanhas: newUser.campaign_ids
      });
      await usersService.create(newUser);
      await loadData();
      handleCloseAddModal();
      setNewUser({
        name: "",
        email: "",
        role: "OPERATOR",
        password: "",
        commission_percentage: 0,
        project_ids: [],
        campaign_ids: []
      });
      toast({
        title: "Usuário criado",
        description: `${newUser.name} foi adicionado com sucesso`
      });
    } catch (error: any) {
      console.error("❌ Erro ao criar usuário:", error);
      toast({
        title: "Erro ao criar usuário",
        description: error.message || "Tente novamente",
        variant: "destructive"
      });
    } finally {
      setIsCreating(false);
    }
  };

  const handleEdit = async () => {
    if (!selectedUser) return;

    console.log('✏️ Editando usuário:', editUser);

    if (editUser.role === "OPERATOR" && (!editUser.project_ids || editUser.project_ids.length === 0)) {
      toast({
        title: "Selecione projetos",
        description: "Operadores precisam ter pelo menos um projeto associado",
        variant: "destructive"
      });
      return;
    }

    try {
      setIsUpdating(true);
      console.log('✅ Salvando alterações:', {
        projetos: editUser.project_ids,
        campanhas: editUser.campaign_ids
      });
      await usersService.update(selectedUser.id, editUser);
      await loadData();
      handleCloseEditModal();
      toast({
        title: "Usuário atualizado",
        description: `${editUser.name} foi atualizado com sucesso`
      });
    } catch (error: any) {
      console.error("❌ Erro ao atualizar usuário:", error);
      toast({
        title: "Erro ao atualizar",
        description: error.message || "Tente novamente",
        variant: "destructive"
      });
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedUser) return;

    try {
      setIsDeleting(true);
      await usersService.delete(selectedUser.id);
      await loadData();
      deleteModal.close();
      setSelectedUser(null);
      toast({
        title: "Usuário removido",
        description: `${selectedUser.name} foi removido do sistema`
      });
    } catch (error: any) {
      console.error("Erro ao deletar usuário:", error);
      toast({
        title: "Erro ao deletar",
        description: error.message || "Tente novamente",
        variant: "destructive"
      });
    } finally {
      setIsDeleting(false);
    }
  };

  const openEditModal = async (user: User) => {
    try {
      console.log('📝 Abrindo modal de edição para:', user);
      setIsLoadingEdit(true);
      setSelectedUser(user);

      const [userProjects, userCampaigns] = await Promise.all([
        usersService.getUserProjects(user.id),
        usersService.getUserCampaigns(user.id)
      ]);

      console.log('📁 Projetos do usuário:', userProjects);
      console.log('📊 Campanhas do usuário:', userCampaigns);
      setSelectedUserProjects(userProjects);
      setSelectedUserCampaigns(userCampaigns);

      // Carregar campanhas dos projetos selecionados e campanhas já atribuídas
      if (userProjects.length > 0) {
        const [projectCampaigns, assigned] = await Promise.all([
          usersService.getCampaignsByProjects(userProjects),
          usersService.getAssignedCampaigns(user.id)
        ]);
        setCampaigns(projectCampaigns);
        setAssignedCampaigns(assigned);
        console.log('📊 Campanhas dos projetos carregadas:', projectCampaigns.length);
      } else {
        setCampaigns([]);
        setAssignedCampaigns([]);
      }

      setEditUser({
        name: user.name,
        email: user.email,
        role: user.role,
        commission_percentage: user.commission_percentage || 0,
        project_ids: userProjects,
        campaign_ids: userCampaigns
      });

      setIsLoadingEdit(false);
      editModal.open();
    } catch (error) {
      console.error('❌ Erro ao abrir modal de edição:', error);
      setIsLoadingEdit(false);
      toast({
        title: "Erro ao carregar dados",
        description: "Não foi possível carregar as informações do usuário",
        variant: "destructive"
      });
    }
  };

  const openDeleteModal = (user: User) => {
    setSelectedUser(user);
    deleteModal.open();
  };

  const getRoleIcon = (role: string) => {
    switch (role) {
      case "ADMIN":
        return <Shield className="h-5 w-5 text-red-500" />;
      case "OPERATOR":
        return <Users className="h-5 w-5 text-blue-500" />;
      default:
        return null;
    }
  };

  const getRoleLabel = (role: string) => {
    switch (role) {
      case "ADMIN":
        return "Administrador";
      case "OPERATOR":
        return "Operador";
      default:
        return role;
    }
  };

  const getRoleBadgeColor = (role: string) => {
    switch (role) {
      case "ADMIN":
        return "bg-red-100 text-red-700 border-red-200";
      case "OPERATOR":
        return "bg-blue-100 text-blue-700 border-blue-200";
      default:
        return "bg-gray-100 text-gray-700 border-gray-200";
    }
  };

  // Carregar campanhas quando os projetos do novo usuário mudarem
  const handleNewUserProjectsChange = async (projectIds: number[]) => {
    setNewUser({ ...newUser, project_ids: projectIds, campaign_ids: [] });
    if (projectIds.length > 0) {
      const [projectCampaigns, assigned] = await Promise.all([
        usersService.getCampaignsByProjects(projectIds),
        usersService.getAssignedCampaigns()
      ]);
      setCampaigns(projectCampaigns);
      setAssignedCampaigns(assigned);
    } else {
      setCampaigns([]);
      setAssignedCampaigns([]);
    }
  };

  // Carregar campanhas quando os projetos do usuário editado mudarem
  const handleEditUserProjectsChange = async (projectIds: number[]) => {
    // Primeiro carregar as novas campanhas dos projetos selecionados
    if (projectIds.length > 0) {
      const [projectCampaigns, assigned] = await Promise.all([
        usersService.getCampaignsByProjects(projectIds),
        usersService.getAssignedCampaigns(selectedUser?.id)
      ]);
      setCampaigns(projectCampaigns);
      setAssignedCampaigns(assigned);

      // Filtrar as campanhas selecionadas anteriormente que ainda pertencem aos projetos atuais
      // IMPORTANTE: Usar campaign_id (VARCHAR) ao invés de id (INTEGER)
      const newCampaignIds = editUser.campaign_ids?.filter(cid =>
        projectCampaigns.some(c => c.campaign_id === cid)
      ) || [];

      setEditUser({ ...editUser, project_ids: projectIds, campaign_ids: newCampaignIds });
    } else {
      setCampaigns([]);
      setAssignedCampaigns([]);
      setEditUser({ ...editUser, project_ids: projectIds, campaign_ids: [] });
    }
  };

  const filteredUsers = users.filter(user =>
    user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.email.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-screen">
          <LoadingSpinner />
        </div>
      </Layout>
    );
  }

  // Only ADMIN can access this page
  if (userProfile?.role !== "ADMIN") {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center space-y-4">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto" />
            <p className="text-gray-500">Você não tem permissão para acessar esta página.</p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-primary to-purple-600 bg-clip-text text-transparent">
              Gerenciamento de Usuários
            </h1>
            <p className="text-muted-foreground mt-2">
              Gerencie usuários e controle de acesso aos projetos
            </p>
          </div>
          <Button onClick={addModal.open} className="shadow-lg">
            <Plus className="h-4 w-4 mr-2" />
            Adicionar Usuário
          </Button>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card className="border-l-4 border-l-red-500">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Administradores</p>
                  <p className="text-2xl font-bold">{users.filter(u => u.role === 'ADMIN').length}</p>
                </div>
                <Shield className="h-8 w-8 text-red-500 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card className="border-l-4 border-l-blue-500">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Operadores</p>
                  <p className="text-2xl font-bold">{users.filter(u => u.role === 'OPERATOR').length}</p>
                </div>
                <Users className="h-8 w-8 text-blue-500 opacity-50" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Search */}
        <Card>
          <CardContent className="pt-6">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por nome ou email..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
          </CardContent>
        </Card>

        {/* Users List */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Usuários do Sistema
            </CardTitle>
            <CardDescription>
              {filteredUsers.length} usuário{filteredUsers.length !== 1 ? 's' : ''} encontrado{filteredUsers.length !== 1 ? 's' : ''}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {filteredUsers.length === 0 ? (
                <div className="text-center py-12">
                  <Users className="h-12 w-12 text-muted-foreground mx-auto mb-4 opacity-20" />
                  <p className="text-muted-foreground">Nenhum usuário encontrado</p>
                </div>
              ) : (
                filteredUsers.map((user) => (
                  <div
                    key={user.id}
                    className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-all hover:shadow-md"
                  >
                    <div className="flex items-center gap-4 flex-1">
                      <div className="h-12 w-12 rounded-full bg-gradient-to-br from-primary/20 to-purple-500/20 flex items-center justify-center border-2 border-primary/20">
                        {getRoleIcon(user.role)}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-1">
                          <p className="font-semibold text-lg">{user.name}</p>
                          <Badge className={getRoleBadgeColor(user.role)}>
                            {getRoleLabel(user.role)}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">{user.email}</p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openEditModal(user)}
                        disabled={isLoadingEdit}
                        className="hover:bg-blue-50 hover:text-blue-600 hover:border-blue-300"
                      >
                        {isLoadingEdit ? (
                          <LoadingSpinner className="h-4 w-4 mr-1" />
                        ) : (
                          <Edit className="h-4 w-4 mr-1" />
                        )}
                        Editar
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openDeleteModal(user)}
                        className="hover:bg-red-50 hover:text-red-600 hover:border-red-300"
                      >
                        <Trash2 className="h-4 w-4 mr-1" />
                        Excluir
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Add User Modal */}
      <Modal
        isOpen={addModal.isOpen}
        onClose={handleCloseAddModal}
        title="Adicionar Novo Usuário"
        description="Preencha os dados do novo usuário e selecione os projetos que ele terá acesso"
        size="lg"
      >
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Label htmlFor="name" className="text-sm font-semibold">
                Nome Completo <span className="text-red-500">*</span>
              </Label>
              <Input
                id="name"
                value={newUser.name}
                onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
                placeholder="Ex: João Silva"
                className="mt-1.5"
              />
            </div>

            <div className="col-span-2">
              <Label htmlFor="email" className="text-sm font-semibold">
                Email <span className="text-red-500">*</span>
              </Label>
              <Input
                id="email"
                type="email"
                value={newUser.email}
                onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                placeholder="joao@exemplo.com"
                className="mt-1.5"
              />
            </div>

            <div className="col-span-2">
              <Label htmlFor="password" className="text-sm font-semibold">
                Senha Provisória <span className="text-red-500">*</span>
              </Label>
              <Input
                id="password"
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                placeholder="Mínimo 6 caracteres"
                className="mt-1.5"
              />
              <p className="text-xs text-muted-foreground mt-1">
                O usuário poderá alterar a senha no primeiro acesso
              </p>
            </div>

            <div className="col-span-2">
              <Label htmlFor="role" className="text-sm font-semibold">
                Nível de Acesso <span className="text-red-500">*</span>
              </Label>
              <Select value={newUser.role} onValueChange={(value: any) => {
                setNewUser({ ...newUser, role: value, project_ids: [], campaign_ids: [] });
                setCampaigns([]);
              }}>
                <SelectTrigger className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ADMIN">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-red-500" />
                      <span>Administrador - Acesso total</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="OPERATOR">
                    <div className="flex items-center gap-2">
                      <Users className="h-4 w-4 text-blue-500" />
                      <span>Operador - Acesso limitado aos projetos</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {newUser.role === "OPERATOR" && (
              <div className="col-span-2">
                <Label htmlFor="commission" className="text-sm font-semibold">
                  Comissão (%)
                </Label>
                <Input
                  id="commission"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={newUser.commission_percentage || 0}
                  onChange={(e) => setNewUser({ ...newUser, commission_percentage: parseFloat(e.target.value) || 0 })}
                  className="mt-1.5"
                  placeholder="Ex: 10.5"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Porcentagem do lucro líquido (0-100%). Mudanças valem a partir de D0.
                </p>
              </div>
            )}
          </div>

          {newUser.role === "OPERATOR" && (
            <div className="border-t pt-4">
              <Label className="text-sm font-semibold flex items-center gap-2 mb-3">
                <FolderOpen className="h-4 w-4" />
                Projetos com Acesso <span className="text-red-500">*</span>
              </Label>
              <p className="text-xs text-muted-foreground mb-3">
                Selecione os projetos que este operador poderá visualizar e gerenciar
              </p>
              <div className="border rounded-lg p-4 space-y-2.5 max-h-64 overflow-y-auto bg-muted/20">
                {projects.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <FolderOpen className="h-8 w-8 mx-auto mb-2 opacity-20" />
                    <p className="text-sm">Nenhum projeto disponível</p>
                  </div>
                ) : (
                  projects.map((project) => (
                    <div
                      key={project.id}
                      className="flex items-center space-x-3 p-2.5 rounded-md hover:bg-background transition-colors"
                    >
                      <Checkbox
                        id={`new-project-${project.id}`}
                        checked={newUser.project_ids?.includes(project.id)}
                        onCheckedChange={(checked) => {
                          const newProjectIds = checked
                            ? [...(newUser.project_ids || []), project.id]
                            : newUser.project_ids?.filter((id) => id !== project.id) || [];
                          handleNewUserProjectsChange(newProjectIds);
                        }}
                      />
                      <label
                        htmlFor={`new-project-${project.id}`}
                        className="text-sm font-medium cursor-pointer flex-1 flex items-center gap-2"
                      >
                        {newUser.project_ids?.includes(project.id) ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : (
                          <Circle className="h-4 w-4 text-muted-foreground" />
                        )}
                        {project.project_name}
                      </label>
                    </div>
                  ))
                )}
              </div>
              {newUser.project_ids && newUser.project_ids.length > 0 && (
                <p className="text-xs text-muted-foreground mt-2">
                  {newUser.project_ids.length} projeto{newUser.project_ids.length !== 1 ? 's' : ''} selecionado{newUser.project_ids.length !== 1 ? 's' : ''}
                </p>
              )}
            </div>
          )}

          {newUser.role === "OPERATOR" && newUser.project_ids && newUser.project_ids.length > 0 && (
            <div className="border-t pt-4">
              <Label className="text-sm font-semibold flex items-center gap-2 mb-3">
                <FolderOpen className="h-4 w-4" />
                Campanhas com Acesso
              </Label>
              <p className="text-xs text-muted-foreground mb-3">
                Selecione as campanhas específicas que este operador poderá visualizar (opcional - se nenhuma for selecionada, terá acesso a todas)
              </p>
              <div className="border rounded-lg p-4 space-y-2.5 max-h-64 overflow-y-auto bg-muted/20">
                {campaigns.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <FolderOpen className="h-8 w-8 mx-auto mb-2 opacity-20" />
                    <p className="text-sm">Nenhuma campanha disponível nos projetos selecionados</p>
                  </div>
                ) : (
                  <>
                    {projects
                      .filter(p => newUser.project_ids?.includes(p.id))
                      .map((project) => {
                        const projectCampaigns = campaigns.filter(c => c.project_id === project.id);
                        if (projectCampaigns.length === 0) return null;

                        return (
                          <div key={project.id} className="mb-4">
                            <p className="text-sm font-semibold text-muted-foreground mb-2 px-2">
                              {project.project_name}
                            </p>
                            {projectCampaigns.map((campaign) => {
                              const isAssigned = assignedCampaigns.includes(campaign.campaign_id);
                              return (
                                <div
                                  key={campaign.id}
                                  className={`flex items-center space-x-3 p-2.5 rounded-md transition-colors ${
                                    isAssigned ? 'bg-muted/50 opacity-60' : 'hover:bg-background'
                                  }`}
                                >
                                  <Checkbox
                                    id={`new-campaign-${campaign.campaign_id}`}
                                    checked={newUser.campaign_ids?.includes(campaign.campaign_id)}
                                    disabled={isAssigned}
                                    onCheckedChange={(checked) => {
                                      if (checked) {
                                        setNewUser({
                                          ...newUser,
                                          campaign_ids: [...(newUser.campaign_ids || []), campaign.campaign_id]
                                        });
                                      } else {
                                        setNewUser({
                                          ...newUser,
                                          campaign_ids: newUser.campaign_ids?.filter((id) => id !== campaign.campaign_id) || []
                                        });
                                      }
                                    }}
                                  />
                                  <label
                                    htmlFor={`new-campaign-${campaign.campaign_id}`}
                                    className={`text-sm font-medium flex-1 flex items-center gap-2 ${
                                      isAssigned ? 'cursor-not-allowed' : 'cursor-pointer'
                                    }`}
                                  >
                                    {isAssigned ? (
                                      <>
                                        <Lock className="h-4 w-4 text-orange-500" />
                                        {campaign.campaign_name}
                                        <Badge variant="outline" className="ml-auto text-xs bg-orange-50 text-orange-700 border-orange-200">
                                          Já atribuída
                                        </Badge>
                                      </>
                                    ) : newUser.campaign_ids?.includes(campaign.campaign_id) ? (
                                      <>
                                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                                        {campaign.campaign_name}
                                      </>
                                    ) : (
                                      <>
                                        <Circle className="h-4 w-4 text-muted-foreground" />
                                        {campaign.campaign_name}
                                      </>
                                    )}
                                  </label>
                                </div>
                              );
                            })}
                          </div>
                        );
                      })}
                  </>
                )}
              </div>
              {newUser.campaign_ids && newUser.campaign_ids.length > 0 && (
                <p className="text-xs text-muted-foreground mt-2">
                  {newUser.campaign_ids.length} campanha{newUser.campaign_ids.length !== 1 ? 's' : ''} selecionada{newUser.campaign_ids.length !== 1 ? 's' : ''}
                </p>
              )}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button variant="outline" onClick={handleCloseAddModal}>
              Cancelar
            </Button>
            <Button onClick={handleCreate} disabled={isCreating} className="min-w-[120px]">
              {isCreating ? (
                <>
                  <LoadingSpinner className="h-4 w-4 mr-2" />
                  Criando...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4 mr-2" />
                  Criar Usuário
                </>
              )}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Edit User Modal */}
      <Modal
        isOpen={editModal.isOpen}
        onClose={handleCloseEditModal}
        title="Editar Usuário"
        description="Atualize as informações e permissões do usuário"
        size="lg"
      >
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Label htmlFor="edit-name" className="text-sm font-semibold">Nome Completo</Label>
              <Input
                id="edit-name"
                value={editUser.name}
                onChange={(e) => setEditUser({ ...editUser, name: e.target.value })}
                className="mt-1.5"
              />
            </div>

            <div className="col-span-2">
              <Label htmlFor="edit-email" className="text-sm font-semibold">Email</Label>
              <Input
                id="edit-email"
                type="email"
                value={editUser.email}
                onChange={(e) => setEditUser({ ...editUser, email: e.target.value })}
                className="mt-1.5"
              />
            </div>

            <div className="col-span-2">
              <Label htmlFor="edit-role" className="text-sm font-semibold">Nível de Acesso</Label>
              <Select value={editUser.role} onValueChange={(value: any) => {
                setEditUser({ ...editUser, role: value, project_ids: value === 'OPERATOR' ? editUser.project_ids : [], campaign_ids: [] });
                if (value !== 'OPERATOR') setCampaigns([]);
              }}>
                <SelectTrigger className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ADMIN">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-red-500" />
                      <span>Administrador - Acesso total</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="OPERATOR">
                    <div className="flex items-center gap-2">
                      <Users className="h-4 w-4 text-blue-500" />
                      <span>Operador - Acesso limitado aos projetos</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {editUser.role === "OPERATOR" && (
              <div className="col-span-2">
                <Label htmlFor="edit-commission" className="text-sm font-semibold">
                  Comissão (%)
                </Label>
                <Input
                  id="edit-commission"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={editUser.commission_percentage || 0}
                  onChange={(e) => setEditUser({ ...editUser, commission_percentage: parseFloat(e.target.value) || 0 })}
                  className="mt-1.5"
                  placeholder="Ex: 10.5"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Porcentagem do lucro líquido (0-100%). Mudanças valem a partir de D0.
                </p>
              </div>
            )}
          </div>

          {editUser.role === "OPERATOR" && (
            <div className="border-t pt-4">
              <Label className="text-sm font-semibold flex items-center gap-2 mb-3">
                <FolderOpen className="h-4 w-4" />
                Projetos com Acesso <span className="text-red-500">*</span>
              </Label>
              <p className="text-xs text-muted-foreground mb-3">
                Selecione os projetos que este operador poderá visualizar e gerenciar
              </p>
              <div className="border rounded-lg p-4 space-y-2.5 max-h-64 overflow-y-auto bg-muted/20">
                {projects.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <FolderOpen className="h-8 w-8 mx-auto mb-2 opacity-20" />
                    <p className="text-sm">Nenhum projeto disponível</p>
                  </div>
                ) : (
                  projects.map((project) => (
                    <div
                      key={project.id}
                      className="flex items-center space-x-3 p-2.5 rounded-md hover:bg-background transition-colors"
                    >
                      <Checkbox
                        id={`edit-project-${project.id}`}
                        checked={editUser.project_ids?.includes(project.id)}
                        onCheckedChange={(checked) => {
                          const newProjectIds = checked
                            ? [...(editUser.project_ids || []), project.id]
                            : editUser.project_ids?.filter((id) => id !== project.id) || [];
                          handleEditUserProjectsChange(newProjectIds);
                        }}
                      />
                      <label
                        htmlFor={`edit-project-${project.id}`}
                        className="text-sm font-medium cursor-pointer flex-1 flex items-center gap-2"
                      >
                        {editUser.project_ids?.includes(project.id) ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : (
                          <Circle className="h-4 w-4 text-muted-foreground" />
                        )}
                        {project.project_name}
                      </label>
                    </div>
                  ))
                )}
              </div>
              {editUser.project_ids && editUser.project_ids.length > 0 && (
                <p className="text-xs text-muted-foreground mt-2">
                  {editUser.project_ids.length} projeto{editUser.project_ids.length !== 1 ? 's' : ''} selecionado{editUser.project_ids.length !== 1 ? 's' : ''}
                </p>
              )}
            </div>
          )}

          {editUser.role === "OPERATOR" && editUser.project_ids && editUser.project_ids.length > 0 && (
            <div className="border-t pt-4">
              <Label className="text-sm font-semibold flex items-center gap-2 mb-3">
                <FolderOpen className="h-4 w-4" />
                Campanhas com Acesso
              </Label>
              <p className="text-xs text-muted-foreground mb-3">
                Selecione as campanhas específicas que este operador poderá visualizar (opcional - se nenhuma for selecionada, terá acesso a todas)
              </p>
              <div className="border rounded-lg p-4 space-y-2.5 max-h-64 overflow-y-auto bg-muted/20">
                {campaigns.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <FolderOpen className="h-8 w-8 mx-auto mb-2 opacity-20" />
                    <p className="text-sm">Nenhuma campanha disponível nos projetos selecionados</p>
                  </div>
                ) : (
                  <>
                    {projects
                      .filter(p => editUser.project_ids?.includes(p.id))
                      .map((project) => {
                        const projectCampaigns = campaigns.filter(c => c.project_id === project.id);
                        if (projectCampaigns.length === 0) return null;

                        return (
                          <div key={project.id} className="mb-4">
                            <p className="text-sm font-semibold text-muted-foreground mb-2 px-2">
                              {project.project_name}
                            </p>
                            {projectCampaigns.map((campaign) => {
                              const isAssigned = assignedCampaigns.includes(campaign.campaign_id);
                              return (
                                <div
                                  key={campaign.id}
                                  className={`flex items-center space-x-3 p-2.5 rounded-md transition-colors ${
                                    isAssigned ? 'bg-muted/50 opacity-60' : 'hover:bg-background'
                                  }`}
                                >
                                  <Checkbox
                                    id={`edit-campaign-${campaign.campaign_id}`}
                                    checked={editUser.campaign_ids?.includes(campaign.campaign_id)}
                                    disabled={isAssigned}
                                    onCheckedChange={(checked) => {
                                      if (checked) {
                                        setEditUser({
                                          ...editUser,
                                          campaign_ids: [...(editUser.campaign_ids || []), campaign.campaign_id]
                                        });
                                      } else {
                                        setEditUser({
                                          ...editUser,
                                          campaign_ids: editUser.campaign_ids?.filter((id) => id !== campaign.campaign_id) || []
                                        });
                                      }
                                    }}
                                  />
                                  <label
                                    htmlFor={`edit-campaign-${campaign.campaign_id}`}
                                    className={`text-sm font-medium flex-1 flex items-center gap-2 ${
                                      isAssigned ? 'cursor-not-allowed' : 'cursor-pointer'
                                    }`}
                                  >
                                    {isAssigned ? (
                                      <>
                                        <Lock className="h-4 w-4 text-orange-500" />
                                        {campaign.campaign_name}
                                        <Badge variant="outline" className="ml-auto text-xs bg-orange-50 text-orange-700 border-orange-200">
                                          Já atribuída
                                        </Badge>
                                      </>
                                    ) : editUser.campaign_ids?.includes(campaign.campaign_id) ? (
                                      <>
                                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                                        {campaign.campaign_name}
                                      </>
                                    ) : (
                                      <>
                                        <Circle className="h-4 w-4 text-muted-foreground" />
                                        {campaign.campaign_name}
                                      </>
                                    )}
                                  </label>
                                </div>
                              );
                            })}
                          </div>
                        );
                      })}
                  </>
                )}
              </div>
              {editUser.campaign_ids && editUser.campaign_ids.length > 0 && (
                <p className="text-xs text-muted-foreground mt-2">
                  {editUser.campaign_ids.length} campanha{editUser.campaign_ids.length !== 1 ? 's' : ''} selecionada{editUser.campaign_ids.length !== 1 ? 's' : ''}
                </p>
              )}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button variant="outline" onClick={handleCloseEditModal}>
              Cancelar
            </Button>
            <Button onClick={handleEdit} disabled={isUpdating} className="min-w-[140px]">
              {isUpdating ? (
                <>
                  <LoadingSpinner className="h-4 w-4 mr-2" />
                  Salvando...
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4 mr-2" />
                  Salvar Alterações
                </>
              )}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Delete User Modal */}
      <Modal
        isOpen={deleteModal.isOpen}
        onClose={deleteModal.close}
        title="Confirmar Exclusão"
        description="Esta ação não pode ser desfeita"
      >
        <div className="space-y-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex gap-3">
              <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-red-900">
                  Você está prestes a excluir o usuário
                </p>
                <p className="text-sm text-red-700 mt-1">
                  <strong>{selectedUser?.name}</strong> ({selectedUser?.email})
                </p>
                <p className="text-xs text-red-600 mt-2">
                  Todas as permissões e acessos serão revogados permanentemente.
                </p>
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button variant="outline" onClick={deleteModal.close}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={isDeleting}
              className="min-w-[120px]"
            >
              {isDeleting ? (
                <>
                  <LoadingSpinner className="h-4 w-4 mr-2" />
                  Excluindo...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Excluir
                </>
              )}
            </Button>
          </div>
        </div>
      </Modal>
    </Layout>
  );
}
