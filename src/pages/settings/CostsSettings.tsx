import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Plus, Edit, Trash2, Save, BarChart3, DollarSign, Users, Settings, Building, Shield, AlertTriangle, ChevronLeft, ChevronRight, Calendar, Lightbulb } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useNavigate } from 'react-router-dom';
import { toast } from '@/hooks/use-toast';
import { Layout } from "@/components/layout/Layout";
import { operationalCostsService, OperationalCostCategory, OperationalCost, OperationalCostInput } from '@/services/operationalCostsService';
import { taxHistoryService, TaxHistoryDisplay } from '@/services/taxHistoryService';
import { useUserRole } from '@/hooks/useUserRole';
import { ProjectCostSharing } from '@/components/cost-sharing/ProjectCostSharing';
import { useIsMobile } from '@/hooks/useIsMobile';


export default function CostsSettings() {
  const navigate = useNavigate();
  const { canManageCategories, canEditCosts, isAdmin } = useUserRole();
  const isMobile = useIsMobile();
  
  // Helper function to get current month in YYYY-MM format
  const getCurrentMonth = () => {
    const now = new Date();
    return `${now.getFullYear()}-${(now.getMonth() + 1).toString().padStart(2, '0')}`;
  };

  // State management
  const [selectedMonth, setSelectedMonth] = useState(getCurrentMonth());
  const [currentTaxRate, setCurrentTaxRate] = useState(8.1);
  const [loading, setLoading] = useState(true);
  
  // Tax management
  const [taxHistory, setTaxHistory] = useState<TaxHistoryDisplay[]>([]);
  const [isUpdatingTax, setIsUpdatingTax] = useState(false);

  // Categories management
  const [categories, setCategories] = useState<OperationalCostCategory[]>([]);
  const [isCategoryDialogOpen, setIsCategoryDialogOpen] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [isLoadingCategories, setIsLoadingCategories] = useState(false);

  // Costs management
  const [costs, setCosts] = useState<OperationalCost[]>([]);
  const [groupedCosts, setGroupedCosts] = useState<{ [categoryName: string]: OperationalCost[] }>({});
  const [editingCost, setEditingCost] = useState<OperationalCost | null>(null);
  const [isAddCostDialogOpen, setIsAddCostDialogOpen] = useState(false);
  const [selectedCategoryForAdd, setSelectedCategoryForAdd] = useState<number | null>(null);
  
  // Category editing
  const [editingCategory, setEditingCategory] = useState<OperationalCostCategory | null>(null);
  const [editingCategoryName, setEditingCategoryName] = useState('');

  // Project cost sharing
  const [selectedProjectsForCosts, setSelectedProjectsForCosts] = useState<string[]>([]);
  const [costPerProject, setCostPerProject] = useState<number>(0);

  // Clone costs state
  const [isCloningCosts, setIsCloningCosts] = useState(false);


  // Load initial data
  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        
        // Check if we need to copy data from previous month for current month
        if (isCurrentMonth()) {
          // Check for first day of month auto-creation for taxes
          const taxCreated = await taxHistoryService.checkAndCreateNextMonthTax();
          if (taxCreated) {
            toast({ 
              title: 'Novo mês detectado', 
              description: `Imposto herdado do mês anterior para ${formatMonthDisplay(selectedMonth)}`,
            });
          }

          // Copy operational costs from previous month if needed
          const dataCopied = await operationalCostsService.checkAndCopyMonthData(selectedMonth);
          if (dataCopied) {
            toast({ 
              title: 'Dados copiados', 
              description: `Custos do mês anterior foram copiados para ${formatMonthDisplay(selectedMonth)}`,
            });
          }
        }

        // Load categories, costs, and tax data in parallel
        const [categoriesData, costsData, taxRate, taxHistoryData] = await Promise.all([
          operationalCostsService.getCategories(),
          operationalCostsService.getCostsByMonth(selectedMonth),
          taxHistoryService.getCurrentTaxRate(selectedMonth),
          taxHistoryService.getTaxHistoryDisplay(selectedMonth)
        ]);
        
        setCategories(categoriesData);
        setCosts(costsData);
        setCurrentTaxRate(taxRate);
        setTaxHistory(taxHistoryData);
        
        // Group costs by category
        const grouped = await operationalCostsService.getCostsByCategory(selectedMonth);
        setGroupedCosts(grouped);
        
      } catch (error: any) {
        console.error('Erro ao carregar dados:', error);
        toast({ 
          title: 'Erro ao carregar dados', 
          description: String(error?.message || error),
          variant: 'destructive'
        });
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [selectedMonth]);

  // Category management functions
  const handleCreateCategory = async () => {
    if (!canManageCategories()) {
      toast({ 
        title: 'Acesso negado', 
        description: 'Apenas administradores podem criar categorias',
        variant: 'destructive'
      });
      return;
    }
    
    if (!newCategoryName.trim()) {
      toast({ title: 'Informe um nome para a categoria' });
      return;
    }
    
    try {
      setIsLoadingCategories(true);
      const newCategory = await operationalCostsService.createCategory(newCategoryName);
      setCategories(prev => [...prev, newCategory].sort((a,b) => a.name.localeCompare(b.name)));
      setNewCategoryName('');
      setIsCategoryDialogOpen(false);
      toast({ title: 'Categoria criada com sucesso!' });
    } catch (error: any) {
      console.error('Erro ao criar categoria:', error);
      toast({ 
        title: 'Erro ao criar categoria', 
        description: String(error?.message || error),
        variant: 'destructive'
      });
    } finally {
      setIsLoadingCategories(false);
    }
  };

  const handleDeleteCategory = async (category: OperationalCostCategory) => {
    if (!canManageCategories()) {
      toast({ 
        title: 'Acesso negado', 
        description: 'Apenas administradores podem excluir categorias',
        variant: 'destructive'
      });
      return;
    }

    const confirmDelete = window.confirm(`Excluir a categoria "${category.name}"?\n\nEsta ação não pode ser desfeita.`);
    if (!confirmDelete) return;

    try {
      await operationalCostsService.deleteCategory(category.id);
      setCategories(prev => prev.filter(c => c.id !== category.id));
      toast({ title: 'Categoria excluída com sucesso!' });
    } catch (error: any) {
      console.error('Erro ao excluir categoria:', error);
      toast({ 
        title: 'Erro ao excluir categoria', 
        description: String(error?.message || error),
        variant: 'destructive'
      });
    }
  };

  const handleEditCategory = (category: OperationalCostCategory) => {
    setEditingCategory(category);
    setEditingCategoryName(category.name);
  };

  const handleSaveCategoryName = async () => {
    if (!editingCategory || !editingCategoryName.trim()) return;

    try {
      const updatedCategory = await operationalCostsService.updateCategory(
        editingCategory.id, 
        editingCategoryName.trim()
      );
      
      setCategories(prev => prev.map(cat => 
        cat.id === editingCategory.id ? updatedCategory : cat
      ));
      
      // Update grouped costs with new category name
      const oldName = editingCategory.name;
      const newName = updatedCategory.name;
      if (oldName !== newName && groupedCosts[oldName]) {
        const newGroupedCosts = { ...groupedCosts };
        newGroupedCosts[newName] = newGroupedCosts[oldName];
        delete newGroupedCosts[oldName];
        setGroupedCosts(newGroupedCosts);
      }
      
      setEditingCategory(null);
      setEditingCategoryName('');
      toast({ title: 'Nome da categoria atualizado!' });
    } catch (error: any) {
      console.error('Erro ao atualizar categoria:', error);
      toast({ 
        title: 'Erro ao atualizar categoria', 
        description: String(error?.message || error),
        variant: 'destructive'
      });
    }
  };

  const handleCancelEditCategory = () => {
    setEditingCategory(null);
    setEditingCategoryName('');
  };

  // Month navigation functions
  const formatMonthDisplay = (monthStr: string) => {
    const [year, month] = monthStr.split('-');
    const monthNames = [
      'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
      'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
    ];
    return `${monthNames[parseInt(month) - 1]} ${year}`;
  };

  const navigateMonth = (direction: 'prev' | 'next') => {
    const [year, month] = selectedMonth.split('-').map(num => parseInt(num));
    let newYear = year;
    let newMonth = month;

    if (direction === 'prev') {
      newMonth -= 1;
      if (newMonth < 1) {
        newMonth = 12;
        newYear -= 1;
      }
    } else {
      newMonth += 1;
      if (newMonth > 12) {
        newMonth = 1;
        newYear += 1;
      }
    }

    const newMonthStr = `${newYear}-${newMonth.toString().padStart(2, '0')}`;
    setSelectedMonth(newMonthStr);
  };

  const isCurrentMonth = () => {
    return selectedMonth === getCurrentMonth();
  };

  const canNavigateNext = () => {
    const current = getCurrentMonth();
    return selectedMonth < current;
  };

  // Tax management functions
  const handleUpdateTaxRate = async () => {
    if (!isCurrentMonth()) {
      toast({ 
        title: 'Ação não permitida', 
        description: 'Só é possível alterar impostos no mês atual',
        variant: 'destructive'
      });
      return;
    }

    if (currentTaxRate < 0 || currentTaxRate > 100) {
      toast({ 
        title: 'Valor inválido', 
        description: 'O percentual deve estar entre 0% e 100%',
        variant: 'destructive'
      });
      return;
    }

    try {
      setIsUpdatingTax(true);
      
      await taxHistoryService.updateTaxRate(getCurrentMonth(), currentTaxRate);
      
      // Reload tax history to show the update
      const updatedHistory = await taxHistoryService.getTaxHistoryDisplay(selectedMonth);
      setTaxHistory(updatedHistory);
      
      toast({ 
        title: 'Imposto atualizado', 
        description: `Novo percentual de ${currentTaxRate}% vigente a partir de ${formatMonthDisplay(getCurrentMonth())}`,
      });
    } catch (error: any) {
      console.error('Erro ao atualizar imposto:', error);
      toast({ 
        title: 'Erro ao atualizar imposto', 
        description: String(error?.message || error),
        variant: 'destructive'
      });
    } finally {
      setIsUpdatingTax(false);
    }
  };

  // Cost management functions
  const handleCreateCost = async (costData: Omit<OperationalCostInput, 'month'>) => {
    if (!canEditCosts()) {
      toast({ 
        title: 'Acesso negado', 
        description: 'Você não tem permissão para editar custos',
        variant: 'destructive'
      });
      return;
    }

    try {
      const monthValue = selectedMonth.length === 7 ? `${selectedMonth}-01` : selectedMonth;
      
      const newCost = await operationalCostsService.createCost({
        ...costData,
        month: monthValue
      });
      
      setCosts(prev => [...prev, newCost]);
      
      // Update grouped costs
      const grouped = await operationalCostsService.getCostsByCategory(selectedMonth);
      setGroupedCosts(grouped);
      
      setIsAddCostDialogOpen(false);
      toast({ title: 'Custo adicionado com sucesso!' });
    } catch (error: any) {
      console.error('Erro ao criar custo:', error);
      toast({ 
        title: 'Erro ao criar custo', 
        description: String(error?.message || error),
        variant: 'destructive'
      });
    }
  };

  const handleUpdateCost = async (id: number, updates: Partial<OperationalCostInput>) => {
    if (!canEditCosts()) {
      toast({ 
        title: 'Acesso negado', 
        description: 'Você não tem permissão para editar custos',
        variant: 'destructive'
      });
      return;
    }

    try {
      const updatedCost = await operationalCostsService.updateCost(id, updates);
      setCosts(prev => prev.map(cost => cost.id === id ? updatedCost : cost));
      
      // Update grouped costs
      const grouped = await operationalCostsService.getCostsByCategory(selectedMonth);
      setGroupedCosts(grouped);
      
      setEditingCost(null);
      toast({ title: 'Custo atualizado com sucesso!' });
    } catch (error: any) {
      console.error('Erro ao atualizar custo:', error);
      toast({ 
        title: 'Erro ao atualizar custo', 
        description: String(error?.message || error),
        variant: 'destructive'
      });
    }
  };

  const handleDeleteCost = async (cost: OperationalCost) => {
    if (!canEditCosts()) {
      toast({ 
        title: 'Acesso negado', 
        description: 'Você não tem permissão para editar custos',
        variant: 'destructive'
      });
      return;
    }

    const confirmDelete = window.confirm(`Excluir o custo "${cost.name}"?`);
    if (!confirmDelete) return;

    try {
      await operationalCostsService.deleteCost(cost.id);
      setCosts(prev => prev.filter(c => c.id !== cost.id));
      
      // Update grouped costs
      const grouped = await operationalCostsService.getCostsByCategory(selectedMonth);
      setGroupedCosts(grouped);
      
      toast({ title: 'Custo removido com sucesso!' });
    } catch (error: any) {
      console.error('Erro ao excluir custo:', error);
      toast({ 
        title: 'Erro ao excluir custo', 
        description: String(error?.message || error),
        variant: 'destructive'
      });
    }
  };

  const getTotalCosts = () => {
    return costs.reduce((total, cost) => {
      return total + (cost.amount || 0);
    }, 0);
  };

  // NEW: Get total of only ACTIVE costs for calculations
  const getTotalActiveCosts = () => {
    return costs.reduce((total, cost) => {
      return total + (cost.is_active ? (cost.amount || 0) : 0);
    }, 0);
  };

  const handleProjectCostSharingChange = (selectedProjects: string[], costPerProjectValue: number) => {
    setSelectedProjectsForCosts(selectedProjects);
    setCostPerProject(costPerProjectValue);
  };

  const getCategoryTotal = (categoryName: string) => {
    const categoryCosts = groupedCosts[categoryName] || [];
    return categoryCosts.reduce((total, cost) => {
      return total + (cost.amount || 0);
    }, 0);
  };

  // NEW: Get total of only ACTIVE costs for a category
  const getCategoryActiveTotal = (categoryName: string) => {
    const categoryCosts = groupedCosts[categoryName] || [];
    return categoryCosts.reduce((total, cost) => {
      return total + (cost.is_active ? (cost.amount || 0) : 0);
    }, 0);
  };

  // NEW: Manual clone costs from previous month
  const handleClonePreviousMonth = async () => {
    if (!canEditCosts()) {
      toast({
        title: 'Acesso negado',
        description: 'Apenas administradores podem clonar custos',
        variant: 'destructive'
      });
      return;
    }

    const confirmClone = window.confirm(
      `Clonar custos do mês anterior para ${formatMonthDisplay(selectedMonth)}?\n\n` +
      `Isso irá copiar todos os custos do mês anterior para o mês selecionado.`
    );

    if (!confirmClone) return;

    try {
      setIsCloningCosts(true);

      // Use the checkAndCopyMonthData method
      const dataCopied = await operationalCostsService.checkAndCopyMonthData(`${selectedMonth}-01`);

      if (dataCopied) {
        toast({
          title: 'Custos clonados com sucesso!',
          description: `Custos do mês anterior foram copiados para ${formatMonthDisplay(selectedMonth)}`
        });

        // Reload data
        const [costsData] = await Promise.all([
          operationalCostsService.getCostsByMonth(selectedMonth)
        ]);

        setCosts(costsData);

        // Group costs by category
        const grouped = await operationalCostsService.getCostsByCategory(selectedMonth);
        setGroupedCosts(grouped);
      } else {
        toast({
          title: 'Mês já possui custos',
          description: `O mês ${formatMonthDisplay(selectedMonth)} já possui custos cadastrados. Não é possível clonar.`,
          variant: 'destructive'
        });
      }
    } catch (error: any) {
      console.error('Erro ao clonar custos:', error);
      toast({
        title: 'Erro ao clonar custos',
        description: String(error?.message || error),
        variant: 'destructive'
      });
    } finally {
      setIsCloningCosts(false);
    }
  };

  // Render loading state
  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center space-y-4">
            <LoadingSpinner size="lg" />
            <p className="text-muted-foreground">Carregando dados de custos...</p>
          </div>
        </div>
      </Layout>
    );
  }

  // Cost Dialog Component
  const CostDialog = ({ cost, categoryId }: { cost?: OperationalCost; categoryId?: number }) => {
    const [costName, setCostName] = useState(cost?.name || '');
    const [amount, setAmount] = useState(cost?.amount || 0);
    const [selectedCategoryId, setSelectedCategoryId] = useState(cost?.category_id || categoryId || categories[0]?.id || 0);
    const [isActive, setIsActive] = useState(cost?.is_active !== undefined ? cost.is_active : true);

    const handleSave = () => {
      const costData = {
        category_id: selectedCategoryId,
        name: costName,
        amount: amount,
        is_active: isActive
      };

      if (cost) {
        handleUpdateCost(cost.id, costData);
      } else {
        handleCreateCost(costData);
      }
    };

    return (
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{cost ? 'Editar Custo' : 'Adicionar Custo'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label htmlFor="category">Categoria</Label>
            <Select value={selectedCategoryId.toString()} onValueChange={(value) => setSelectedCategoryId(parseInt(value))}>
              <SelectTrigger>
                <SelectValue placeholder="Selecione uma categoria" />
              </SelectTrigger>
              <SelectContent>
                {categories.map(cat => (
                  <SelectItem key={cat.id} value={cat.id.toString()}>
                    {cat.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="costName">Nome do Custo</Label>
            <Input
              id="costName"
              value={costName}
              onChange={(e) => setCostName(e.target.value)}
              placeholder="Digite o nome do custo"
            />
          </div>
          <div>
            <Label htmlFor="amount">Valor (R$)</Label>
            <Input
              id="amount"
              type="number"
              value={amount}
              onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
              placeholder="0,00"
              step="0.01"
            />
          </div>
          <div className="flex items-center space-x-2">
            <input
              type="checkbox"
              id="isActive"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="rounded border border-gray-300"
            />
            <Label htmlFor="isActive">Custo ativo</Label>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => { 
              setEditingCost(null); 
              setIsAddCostDialogOpen(false); 
            }}>
              Cancelar
            </Button>
            <Button onClick={handleSave} disabled={!costName || !amount || !selectedCategoryId}>
              Salvar
            </Button>
          </div>
        </div>
      </DialogContent>
    );
  };

  return (
    <Layout>
      <div className={`${isMobile ? 'p-4' : 'p-6'} space-y-8 max-w-7xl mx-auto`}>
        {/* Header with enhanced styling */}
        <div className={`flex ${isMobile ? 'flex-col' : 'items-center justify-between'} transition-all duration-300 gap-4`}>
          <div>
            <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-3 mb-2`}>
              <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="touch-target">
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-3`}>
                <h1 className={`${isMobile ? 'text-2xl' : 'text-3xl'} font-bold bg-gradient-to-r from-primary via-purple-600 to-blue-600 bg-clip-text text-transparent`}>
                  Configurações de Custos
                </h1>
                {isAdmin() && (
                  <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                    <Shield className="h-3 w-3 mr-1" />
                    Admin
                  </Badge>
                )}
              </div>
            </div>
            <p className={`text-muted-foreground ${isMobile ? 'text-sm ml-0' : 'ml-11'}`}>
              Gerencie custos operacionais e impostos por mês
              {!canEditCosts() && (
                <span className="text-amber-600 ml-2">• Visualização apenas</span>
              )}
            </p>
          </div>
        </div>

        {/* Month Selector */}
        <Card className="shadow-lg transition-all duration-300 bg-gradient-to-br from-blue-500/5 to-purple-600/10 border-blue-500/20 hover:shadow-xl">
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-blue-600" />
              Período de Referência
            </CardTitle>
            <CardDescription>
              Navegue pelos meses para visualizar custos históricos
              {isCurrentMonth() && (
                <span className="text-blue-600 font-medium ml-2">• Mês atual</span>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className={`flex ${isMobile ? 'flex-col' : 'items-center justify-between'} gap-4`}>
            <div className={`flex ${isMobile ? 'flex-col w-full' : 'items-center'} gap-4`}>
                <Label className={`font-medium ${isMobile ? 'text-sm' : ''}`}>Mês:</Label>
                <div className={`flex items-center gap-2 bg-white/50 rounded-lg border p-1 ${isMobile ? 'w-full justify-between' : ''}`}>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigateMonth('prev')}
                    className={`${isMobile ? 'h-10 w-10' : 'h-8 w-8'} p-0 touch-target`}
                    title="Mês anterior"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <div className={`flex items-center gap-2 ${isMobile ? 'px-2' : 'px-4'} py-1 ${isMobile ? 'min-w-0 flex-1' : 'min-w-[180px]'} justify-center`}>
                    <span className={`font-medium ${isMobile ? 'text-base' : 'text-lg'}`}>
                      {formatMonthDisplay(selectedMonth)}
                    </span>
                    {isCurrentMonth() && (
                      <Badge variant="default" className="bg-blue-100 text-blue-800 text-xs px-2 py-0.5">
                        Atual
                      </Badge>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => navigateMonth('next')}
                    disabled={!canNavigateNext()}
                    className={`${isMobile ? 'h-10 w-10' : 'h-8 w-8'} p-0 touch-target`}
                    title="Próximo mês"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <div className={`flex ${isMobile ? 'flex-col w-full' : 'items-center'} gap-4`}>
                {!isMobile && (
                  <div className="text-right">
                    <p className="text-sm text-muted-foreground">
                      Use as setas para navegar entre os meses
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Dados são copiados automaticamente na virada do mês
                    </p>
                  </div>
                )}
                {canEditCosts() && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleClonePreviousMonth}
                    disabled={isCloningCosts}
                    className={`gap-2 ${isMobile ? 'w-full touch-target' : ''}`}
                  >
                    {isCloningCosts ? (
                      <>
                        <LoadingSpinner size="sm" />
                        Clonando...
                      </>
                    ) : (
                      <>
                        <Plus className="h-4 w-4" />
                        Clonar Mês Anterior
                      </>
                    )}
                  </Button>
                )}
                {isMobile && (
                  <div className="text-center text-xs text-muted-foreground">
                    Use as setas para navegar entre os meses
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Add New Category Button */}
        {canManageCategories() && (
          <div className="flex justify-center">
            <Dialog open={isCategoryDialogOpen} onOpenChange={setIsCategoryDialogOpen}>
              <DialogTrigger asChild>
                <Button size="lg" className="bg-primary hover:bg-primary/90 shadow-lg">
                  <Plus className="h-5 w-5 mr-2" />
                  Nova Categoria
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Nova categoria de custo</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label>Nome da categoria</Label>
                    <Input
                      value={newCategoryName}
                      onChange={(e) => setNewCategoryName(e.target.value)}
                      placeholder="Ex.: Pessoas, Infraestrutura, Administrativo"
                      autoFocus
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={() => setIsCategoryDialogOpen(false)}>Cancelar</Button>
                    <Button onClick={handleCreateCategory} disabled={isLoadingCategories}>
                      {isLoadingCategories ? 'Salvando...' : 'Salvar'}
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
              </div>
            )}

        {/* Taxes Section */}
        <Card className="shadow-lg transition-all duration-300 bg-gradient-to-br from-yellow-500/5 to-orange-600/10 border-yellow-500/20 hover:shadow-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-yellow-600" />
              Impostos - Simples Nacional
            </CardTitle>
            <CardDescription>
              Alterações no percentual são válidas a partir do mês atual
              {!isCurrentMonth() && (
                <span className="text-amber-600 font-medium ml-2">• Visualizando mês anterior</span>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className={`grid ${isMobile ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-3'} gap-6`}>
              <div className="space-y-2">
                <Label className={`font-medium ${isMobile ? 'text-sm' : ''}`}>Percentual Atual:</Label>
                <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-2`}>
                  <Input
                    type="number"
                    value={currentTaxRate}
                    onChange={(e) => setCurrentTaxRate(parseFloat(e.target.value) || 0)}
                    step="0.1"
                    className={`${isMobile ? 'w-full touch-target' : 'w-20'}`}
                    disabled={!isCurrentMonth()}
                  />
                  <span className={`${isMobile ? 'text-xs' : 'text-sm'} text-muted-foreground`}>% (Simples Nacional)</span>
                </div>
                {!isCurrentMonth() && (
                  <p className="text-xs text-amber-600">
                    Só é possível alterar no mês atual
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label className="font-medium">Vigência:</Label>
                <p className="text-sm font-medium bg-yellow-100 text-yellow-800 px-2 py-1 rounded w-fit">
                  A partir de {formatMonthDisplay(getCurrentMonth())}
                </p>
                <p className="text-xs text-muted-foreground">
                  Vigente até próxima alteração
                </p>
              </div>
              <div className="space-y-2">
                <Label className="font-medium">Histórico (3 meses):</Label>
                <div className="text-xs text-muted-foreground space-y-1">
                  {taxHistory.map((h, index) => (
                    <div key={`${h.month}-${index}`} className="flex justify-between">
                      <span>{h.month}:</span>
                      <span className="font-mono">{h.percentage}%</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className={`flex ${isMobile ? 'flex-col' : 'justify-between items-center'} pt-2 gap-2`}>
              <Button 
                variant="outline" 
                size="sm"
                className={`bg-yellow-50 border-yellow-200 hover:bg-yellow-100 text-yellow-800 ${isMobile ? 'w-full touch-target' : ''}`}
                disabled={!isCurrentMonth() || isUpdatingTax}
                onClick={handleUpdateTaxRate}
              >
                {isUpdatingTax ? (
                  <LoadingSpinner size="sm" className="mr-2" />
                ) : (
                  <Save className="h-4 w-4 mr-2" />
                )}
                {isUpdatingTax ? 'Salvando...' : 'Alterar Percentual'}
              </Button>
              
              {!isCurrentMonth() && (
                <div className={`flex items-center gap-2 ${isMobile ? 'text-xs' : 'text-sm'} text-amber-600 ${isMobile ? 'justify-center' : ''}`}>
                  <AlertTriangle className="h-4 w-4" />
                  <span>Para alterar impostos, navegue para o mês atual</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Project Cost Sharing - Compact */}
        <Card className="shadow-lg transition-all duration-300 bg-gradient-to-br from-blue-500/5 to-purple-600/10 border-blue-500/20 hover:shadow-xl">
          <CardContent className="py-4">
            <ProjectCostSharing
              totalCost={getTotalActiveCosts()}
              selectedMonth={selectedMonth}
              onSelectionChange={handleProjectCostSharingChange}
            />
          </CardContent>
        </Card>

        {/* Category Cards */}
        {categories.map((category) => {
          const categoryCosts = groupedCosts[category.name] || [];
          const categoryTotal = getCategoryTotal(category.name);
          const isEditingThis = editingCategory?.id === category.id;
          
          return (
            <Card 
              key={category.id}
              className="shadow-lg transition-all duration-300 bg-gradient-to-br from-background to-muted/30 hover:shadow-xl border-l-4 border-l-primary"
            >
              <CardHeader className="flex flex-row items-center justify-between">
                <div className="flex-1">
                  {isEditingThis ? (
                    <div className="flex items-center gap-2 mb-2">
                      <DollarSign className="h-5 w-5 text-primary" />
                      <Input
                        value={editingCategoryName}
                        onChange={(e) => setEditingCategoryName(e.target.value)}
                        className="text-lg font-semibold"
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveCategoryName();
                          if (e.key === 'Escape') handleCancelEditCategory();
                        }}
                        autoFocus
                      />
                      <Button size="sm" onClick={handleSaveCategoryName} disabled={!editingCategoryName.trim()}>
                        <Save className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="outline" onClick={handleCancelEditCategory}>
                        ✕
                      </Button>
                    </div>
                  ) : (
                    <CardTitle className="flex items-center gap-2 mb-2">
                      <DollarSign className="h-5 w-5 text-primary" />
                      <span>{category.name}</span>
                      {canManageCategories() && (
                        <Button 
                          size="sm" 
                          variant="ghost" 
                          onClick={() => handleEditCategory(category)}
                          className="ml-2 h-6 w-6 p-0"
                        >
                          <Edit className="h-3 w-3" />
                        </Button>
                      )}
                  </CardTitle>
                  )}
                  <CardDescription>
                    Subtotal: R$ {categoryTotal.toFixed(2).replace('.', ',')}
                    <span className="text-xs text-muted-foreground ml-2">
                      • {categoryCosts.length} {categoryCosts.length === 1 ? 'item' : 'itens'}
                    </span>
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  {canEditCosts() && (
                    <Dialog open={isAddCostDialogOpen && selectedCategoryForAdd === category.id} onOpenChange={(open) => {
                      setIsAddCostDialogOpen(open);
                      if (open) setSelectedCategoryForAdd(category.id);
                      else setSelectedCategoryForAdd(null);
                }}>
                  <DialogTrigger asChild>
                        <Button variant="outline" size="sm" onClick={() => setSelectedCategoryForAdd(category.id)}>
                      <Plus className="h-4 w-4 mr-2" />
                          Adicionar Custo
                        </Button>
                      </DialogTrigger>
                      <CostDialog categoryId={category.id} />
                    </Dialog>
                  )}
                  {canManageCategories() && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-500 hover:text-red-700 h-8 w-8 p-0"
                      onClick={() => handleDeleteCategory(category)}
                      title={`Excluir categoria ${category.name}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {categoryCosts.map(cost => (
                    <div key={cost.id} className="flex items-center justify-between p-4 border rounded-lg bg-white/50 hover:bg-white/80 transition-colors">
                      <div className="flex items-center gap-4 flex-1">
                        <div className={`h-2 w-2 rounded-full ${cost.is_active ? 'bg-primary' : 'bg-gray-400'}`}></div>
                        <div className="flex-1">
                          <div className="font-medium">{cost.name}</div>
                          {!cost.is_active && (
                            <div className="text-xs text-amber-600">Inativo</div>
                          )}
                        </div>
                        <div className="text-right">
                          <span className="font-semibold text-lg">
                            R$ {(cost.amount || 0).toFixed(2).replace('.', ',')}
                          </span>
                        </div>
                      </div>
                      {canEditCosts() && (
                        <div className="flex gap-1 ml-4">
                          <Dialog open={editingCost?.id === cost.id} onOpenChange={(open) => {
                            if (!open) setEditingCost(null);
                            else setEditingCost(cost);
                        }}>
                          <DialogTrigger asChild>
                            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                              <Edit className="h-4 w-4" />
                            </Button>
                          </DialogTrigger>
                            <CostDialog cost={editingCost!} />
                        </Dialog>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0 text-red-500 hover:text-red-700 hover:bg-red-50"
                            onClick={() => handleDeleteCost(cost)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                      )}
                    </div>
                  ))}
                  {categoryCosts.length === 0 && (
                    <div className="text-center py-8 text-muted-foreground">
                      <DollarSign className="h-12 w-12 mx-auto mb-3 opacity-50" />
                      <p>Nenhum custo cadastrado nesta categoria</p>
                      {canEditCosts() ? (
                        <p className="text-sm text-blue-600 mt-2">
                          Clique em "Adicionar Custo" para começar
                        </p>
                      ) : (
                        <p className="text-sm text-amber-600 mt-2">
                          <AlertTriangle className="h-4 w-4 inline mr-1" />
                          Solicite permissão para adicionar custos
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}

        {/* Empty state for no categories */}
        {categories.length === 0 && (
          <Card className="shadow-lg transition-all duration-300 bg-gradient-to-br from-background to-muted/30">
            <CardContent className="text-center py-12">
              <Settings className="h-16 w-16 mx-auto mb-4 opacity-50 text-muted-foreground" />
              <h3 className="text-lg font-medium mb-2">Nenhuma categoria cadastrada</h3>
              <p className="text-muted-foreground mb-4">
                Comece criando categorias para organizar seus custos
              </p>
              {canManageCategories() ? (
                <p className="text-sm text-blue-600">
                  Clique em "Nova Categoria" acima para começar
                </p>
              ) : (
                <p className="text-sm text-amber-600">
                  <AlertTriangle className="h-4 w-4 inline mr-1" />
                  Solicite a um administrador para criar categorias
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Total Summary */}
        <Card className="shadow-lg transition-all duration-300 bg-gradient-to-br from-primary/5 to-purple-600/10 border-primary/20 hover:shadow-xl">
          <CardContent className="p-8">
            <div className="text-center space-y-4">
              <div className="flex items-center justify-center gap-3">
                <DollarSign className="h-8 w-8 text-primary" />
                <h3 className="text-2xl font-bold text-primary">
                  Total Custos Operacionais
                </h3>
              </div>
              <div className="space-y-2">
                <div className="text-4xl font-bold bg-gradient-to-r from-primary to-purple-600 bg-clip-text text-transparent">
                  R$ {getTotalActiveCosts().toFixed(2).replace('.', ',')}
                </div>
                <div className="space-y-1">
                  <p className="text-muted-foreground">
                    Apenas custos ativos são somados • Impostos calculados automaticamente ({currentTaxRate}% Simples Nacional)
                  </p>
                  {selectedProjectsForCosts.length > 0 && (
                    <p className="text-sm text-green-600 font-medium">
                      <span className="flex items-center gap-1">
                        <Lightbulb className="h-4 w-4" />
                        Dividido entre {selectedProjectsForCosts.length} {selectedProjectsForCosts.length === 1 ? 'projeto' : 'projetos'}
                      </span> 
                      - R$ {costPerProject.toFixed(2).replace('.', ',')} por projeto
                    </p>
                  )}
                </div>
              </div>
              
              {categories.length > 0 && (
              <div className={`grid ${isMobile ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-3'} gap-4 pt-4 border-t`}>
                  {categories.slice(0, 3).map((category, index) => {
                    const colors = ['text-blue-600', 'text-green-600', 'text-purple-600'];
                    const categoryCosts = groupedCosts[category.name] || [];
                    return (
                      <div key={category.id} className="text-center space-y-1">
                        <div className={`text-sm font-medium ${colors[index] || 'text-primary'}`}>
                          {category.name}
                        </div>
                  <div className="text-lg font-semibold">
                          R$ {getCategoryActiveTotal(category.name).toFixed(2).replace('.', ',')}
                  </div>
                        <div className="text-xs text-muted-foreground">
                          {categoryCosts.length} {categoryCosts.length === 1 ? 'item' : 'itens'}
                  </div>
                </div>
                    );
                  })}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Action Buttons */}
        <div className={`flex flex-wrap gap-4 ${isMobile ? 'flex-col' : 'justify-center'}`}>
          {canEditCosts() && (
            <Button 
              onClick={() => window.location.reload()} 
              size="lg" 
              className={`shadow-lg hover:shadow-xl transition-shadow ${isMobile ? 'w-full touch-target' : ''}`}
            >
            <Save className="h-5 w-5 mr-2" />
              Recarregar Dados
          </Button>
          )}
          <Button variant="outline" size="lg" className={`shadow-lg hover:shadow-xl transition-shadow ${isMobile ? 'w-full touch-target' : ''}`}>
            <BarChart3 className="h-5 w-5 mr-2" />
            Ver Histórico Completo
          </Button>
        </div>
      </div>
    </Layout>
  );
}
