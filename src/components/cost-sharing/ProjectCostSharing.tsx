import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Users, ChevronDown, CheckCircle, X, Save } from 'lucide-react';
import { supabaseDataService, Project } from '@/services/supabaseDataService';
import { projectCostSharingService } from '@/services/projectCostSharingService';

interface ProjectCostSharingProps {
  totalCost: number;
  selectedMonth: string;
  onSelectionChange?: (selectedProjects: string[], costPerProject: number) => void;
}

export function ProjectCostSharing({ totalCost, selectedMonth, onSelectionChange }: ProjectCostSharingProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjects, setSelectedProjects] = useState<Set<string>>(new Set());
  const [originalSelectedProjects, setOriginalSelectedProjects] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Load projects on component mount
  useEffect(() => {
    const loadProjects = async () => {
      try {
        setLoading(true);
        
        const filters = {
          date: selectedMonth,
          projectId: 'all',
          period: 'today' as const
        };
        
        const projectsData = await supabaseDataService.getProjects(filters);
        const activeProjects = projectsData.filter(p => p.status === 'active');
        
        setProjects(activeProjects);
        
        // Initialize selected projects from costs_division field
        const initialSelected = new Set(
          activeProjects
            .filter(p => p.costs_division === true)
            .map(p => p.id)
        );
        
        console.log('📋 Projetos carregados:', {
          total: activeProjects.length,
          comDivisao: initialSelected.size,
          projetosDivisao: activeProjects.filter(p => p.costs_division === true).map(p => ({ id: p.id, domain: p.domain }))
        });
        
        setSelectedProjects(initialSelected);
        setOriginalSelectedProjects(new Set(initialSelected));
        setHasChanges(false);
        
      } catch (error: unknown) {
        console.error('❌ Erro ao carregar projetos:', error);
        // Garantir que o loading pare mesmo com erro
        setProjects([]);
        setSelectedProjects(new Set());
      } finally {
        setLoading(false);
      }
    };

    // Timeout de segurança para evitar loading infinito
    const timeoutId = setTimeout(() => {
      setLoading(false);
    }, 10000);

    loadProjects();
    
    return () => clearTimeout(timeoutId);
  }, [selectedMonth]);

  // Notify parent when selection changes (memoized to avoid loops)
  useEffect(() => {
    if (!loading && projects.length >= 0) {
      const costPerProject = selectedProjects.size > 0 ? totalCost / selectedProjects.size : 0;
      onSelectionChange?.(Array.from(selectedProjects), costPerProject);
    }
  }, [selectedProjects.size, totalCost, loading]);

  // Handle project toggle (local state only)
  const toggleProject = (projectId: string) => {
    const isSelected = selectedProjects.has(projectId);
    const newSelected = new Set(selectedProjects);
    
    if (isSelected) {
      newSelected.delete(projectId);
    } else {
      newSelected.add(projectId);
    }
    
    setSelectedProjects(newSelected);
    
    // Check if there are changes
    const hasChangesNow = !areSetsEqual(newSelected, originalSelectedProjects);
    setHasChanges(hasChangesNow);
  };

  // Helper function to compare sets
  const areSetsEqual = (set1: Set<string>, set2: Set<string>): boolean => {
    if (set1.size !== set2.size) return false;
    for (const item of set1) {
      if (!set2.has(item)) return false;
    }
    return true;
  };

  // Select all projects (local state only)
  const selectAll = () => {
    const allProjectIds = new Set(projects.map(p => p.id));
    setSelectedProjects(allProjectIds);
    
    const hasChangesNow = !areSetsEqual(allProjectIds, originalSelectedProjects);
    setHasChanges(hasChangesNow);
  };

  // Clear all projects (local state only)
  const clearAll = () => {
    const emptySet = new Set<string>();
    setSelectedProjects(emptySet);
    
    const hasChangesNow = !areSetsEqual(emptySet, originalSelectedProjects);
    setHasChanges(hasChangesNow);
  };

  // Save changes to database
  const saveChanges = async () => {
    setSaving(true);
    
    try {
      // Update each project that changed
      const projectsToUpdate = projects.filter(project => {
        const isCurrentlySelected = selectedProjects.has(project.id);
        const wasOriginallySelected = originalSelectedProjects.has(project.id);
        return isCurrentlySelected !== wasOriginallySelected;
      });

      for (const project of projectsToUpdate) {
        const shouldBeDivision = selectedProjects.has(project.id);
        await projectCostSharingService.updateProjectCostsDivision(project.id, shouldBeDivision);
      }

      // Update original state to match current state
      setOriginalSelectedProjects(new Set(selectedProjects));
      setHasChanges(false);
      
      console.log('✅ Configurações de divisão de custos salvas com sucesso');
      
    } catch (error: unknown) {
      console.error('❌ Erro ao salvar configurações:', error);
      
      if (error instanceof Error && error.message.includes('ALTER TABLE projects ADD COLUMN')) {
        alert(`❌ Coluna costs_division não encontrada no banco!\n\nPara habilitar esta funcionalidade, execute no Supabase SQL Editor:\n\nALTER TABLE projects ADD COLUMN costs_division BOOLEAN DEFAULT false;`);
      } else {
        alert('Erro ao salvar as configurações. Tente novamente.');
      }
    } finally {
      setSaving(false);
    }
  };

  const selectedCount = selectedProjects.size;
  const costPerProject = selectedCount > 0 ? totalCost / selectedCount : 0;

  if (loading) {
    return (
      <div className="flex items-center gap-2">
        <Label className="text-sm text-muted-foreground">Divisão de Custos:</Label>
        <span className="text-xs">Carregando...</span>
      </div>
    );
  }

  if (projects.length === 0) {
    return null; // Não mostrar se não há projetos
  }

  return (
    <div className="flex items-center gap-3">
      <Label className="text-sm font-medium">Divisão de Custos:</Label>
      
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-2 min-w-[200px] justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              {selectedCount > 0 ? (
                <span>{selectedCount} {selectedCount === 1 ? 'projeto' : 'projetos'}</span>
              ) : (
                <span className="text-muted-foreground">Selecionar projetos</span>
              )}
            </div>
            <ChevronDown className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        
        <DropdownMenuContent align="start" className="w-64">
          <DropdownMenuLabel className="flex items-center justify-between">
            <span>Projetos para Divisão</span>
            {selectedCount > 0 && (
              <span className="text-xs text-muted-foreground">
                R$ {costPerProject.toFixed(0)} cada
              </span>
            )}
          </DropdownMenuLabel>
          
          <DropdownMenuSeparator />
          
          {/* Quick actions */}
          <div className="flex gap-1 p-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={selectAll}
              disabled={selectedCount === projects.length}
              className="flex-1 h-8 text-xs"
            >
              <CheckCircle className="h-3 w-3 mr-1" />
              Todos
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearAll}
              disabled={selectedCount === 0}
              className="flex-1 h-8 text-xs"
            >
              <X className="h-3 w-3 mr-1" />
              Limpar
            </Button>
          </div>
          
          <DropdownMenuSeparator />
          
          {/* Project list */}
          <div className="max-h-60 overflow-y-auto">
            {projects.map((project) => (
              <DropdownMenuItem
                key={project.id}
                className="flex items-center gap-3 px-3 py-2 cursor-pointer"
                onSelect={(e) => {
                  e.preventDefault(); // Prevent dropdown from closing
                  toggleProject(project.id);
                }}
              >
                <Checkbox
                  checked={selectedProjects.has(project.id)}
                  onCheckedChange={() => toggleProject(project.id)}
                  className="pointer-events-none"
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">
                    {project.domain}
                  </div>
                  <div className="text-xs text-muted-foreground truncate">
                    {project.name}
                  </div>
                </div>
              </DropdownMenuItem>
            ))}
          </div>
          
          {selectedCount > 0 && (
            <>
              <DropdownMenuSeparator />
              <div className="px-3 py-2 text-xs text-muted-foreground">
                Total: R$ {totalCost.toFixed(2).replace('.', ',')} ÷ {selectedCount} = R$ {costPerProject.toFixed(2).replace('.', ',')} por projeto
              </div>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      
      {/* Botão Salvar */}
      <Button
        onClick={saveChanges}
        disabled={!hasChanges || saving}
        size="sm"
        variant={hasChanges ? "default" : "outline"}
        className="gap-2"
      >
        <Save className="h-4 w-4" />
        {saving ? 'Salvando...' : 'Salvar'}
      </Button>
      
      {selectedCount > 0 && (
        <span className="text-xs text-green-600 font-medium">
          ✓ {selectedCount} {selectedCount === 1 ? 'projeto selecionado' : 'projetos selecionados'}
          {hasChanges && <span className="text-orange-600 ml-1">(não salvo)</span>}
        </span>
      )}
    </div>
  );
}