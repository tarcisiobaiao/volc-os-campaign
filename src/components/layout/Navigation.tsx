import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Home,
  BarChart3,
  Settings,
  FileText,
  Menu,
  X,
  FolderOpen,
  Megaphone,
  DollarSign,
  Zap,
  Sparkles,
  LogOut,
  User,
  Users
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";

interface NavigationProps {
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
}

interface NavigationItem {
  title: string;
  href: string;
  icon: any;
  description: string;
  adminOnly?: boolean;
}

const navigationItems: NavigationItem[] = [
  {
    title: "Dashboard Geral",
    href: "/",
    icon: Home,
    description: "Visão geral de todas as campanhas",
    adminOnly: true // Apenas admin vê o dashboard geral
  },
  {
    title: "Projetos",
    href: "/dashboard/projects",
    icon: FolderOpen,
    description: "Gerenciar projetos",
    adminOnly: true // Apenas admin vê projetos
  },
  {
    title: "Campanhas",
    href: "/settings/campaigns",
    icon: Megaphone,
    description: "Ver e configurar campanhas"
  },
  {
    title: "Relatórios",
    href: "/reports",
    icon: FileText,
    description: "Relatórios e análises avançadas",
    adminOnly: true // Apenas admin vê relatórios
  }
];

const configurationItems: NavigationItem[] = [
  {
    title: "Custos",
    href: "/settings/costs",
    icon: DollarSign,
    description: "Definir custos e orçamentos",
    adminOnly: true // Apenas admin vê custos
  },
  {
    title: "Integrações",
    href: "/settings/integrations",
    icon: Zap,
    description: "Google Ads e Ad Manager",
    adminOnly: true // Apenas admin vê integrações
  },
  {
    title: "Usuários",
    href: "/settings/users",
    icon: Users,
    description: "Gerenciar usuários e permissões",
    adminOnly: true
  }
];

export const Navigation: React.FC<NavigationProps> = ({ isCollapsed, setIsCollapsed }) => {
  const location = useLocation();
  const { user, userProfile, signOut } = useAuth();
  const { toast } = useToast();

  const handleSignOut = async () => {
    try {
      await signOut();
      toast({
        title: "Logout realizado",
        description: "Você foi desconectado com sucesso.",
      });
    } catch (error) {
      toast({
        title: "Erro ao fazer logout",
        description: "Tente novamente.",
        variant: "destructive",
      });
    }
  };

  const NavItem = ({ item, isActive }: { item: NavigationItem; isActive: boolean }) => (
    <Link to={item.href}>
      <Button
        variant={isActive ? "secondary" : "ghost"}
        className={cn(
          "w-full justify-start gap-3 h-12 transition-all duration-200 relative overflow-hidden",
          isActive && "bg-gradient-to-r from-primary/10 via-purple-500/10 to-primary/10 text-primary font-medium border-r-2 border-primary shadow-sm",
          !isActive && "hover:bg-muted/50 hover:shadow-sm",
          isCollapsed && "justify-center px-2"
        )}
      >
        {isActive && (
          <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent opacity-50" />
        )}
        <item.icon className={cn("h-5 w-5 flex-shrink-0 relative z-10", isActive && "text-primary")} />
        {!isCollapsed && (
          <div className="flex flex-col items-start relative z-10">
            <span className="text-sm font-medium">{item.title}</span>
            <span className="text-xs text-muted-foreground">{item.description}</span>
          </div>
        )}
      </Button>
    </Link>
  );

  return (
    <div className={cn(
      "relative bg-gradient-to-b from-card via-card to-muted/30 border-r border-border transition-all duration-300 flex flex-col shadow-lg",
      isCollapsed ? "w-16" : "w-80"
    )}>
      {/* Header */}
      <div className="p-4 border-b border-border bg-gradient-to-r from-background to-muted/20 relative">
        <div className="flex items-center justify-center w-full">
          {!isCollapsed ? (
            <div className="animate-fade-in flex-1 flex flex-col items-center justify-center text-center">
              <img 
                src="/logo-webgocontent-horizontal.png" 
                alt="WebGo Content" 
                className="h-12 max-w-full object-contain mb-2"
              />
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Sparkles className="h-3 w-3" />
                Google Ads & Ad Manager
              </p>
            </div>
          ) : (
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-primary/10 to-purple-600/10 border border-primary/20">
              <span className="text-sm font-bold text-primary">W</span>
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="h-8 w-8 p-0 hover:bg-muted/50 transition-colors absolute top-4 right-4"
          >
            {isCollapsed ? (
              <Menu className="h-4 w-4" />
            ) : (
              <X className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Navigation Content */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-6">
          {/* Main Navigation */}
          <div>
            {!isCollapsed && (
              <h3 className="mb-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Principal
              </h3>
            )}
            <nav className="space-y-2">
              {navigationItems.map((item) => {
                // Filtrar itens adminOnly para operadores
                if (item.adminOnly && userProfile?.role !== 'ADMIN') {
                  return null;
                }
                return (
                  <NavItem
                    key={item.href}
                    item={item}
                    isActive={location.pathname === item.href}
                  />
                );
              })}
            </nav>
          </div>

          {/* Separator e Configuration - Ocultar seção inteira para OPERATORs */}
          {userProfile?.role !== 'OPERATOR' && (
            <>
              <Separator className="bg-gradient-to-r from-transparent via-border to-transparent" />
            <div>
              {!isCollapsed && (
                <h3 className="mb-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Configurações
                </h3>
              )}
              <nav className="space-y-2">
                {configurationItems.map((item) => {
                  // Hide admin-only items from non-admin users
                  if (item.adminOnly && userProfile?.role !== 'ADMIN') {
                    return null;
                  }
                  return (
                    <NavItem
                      key={item.href}
                      item={item}
                      isActive={location.pathname === item.href}
                    />
                  );
                })}
              </nav>
            </div>
            </>
          )}
        </div>
      </ScrollArea>

      {/* User Section */}
      <div className="p-4 border-t border-border bg-gradient-to-r from-muted/20 to-background">
        {!isCollapsed ? (
          <div className="space-y-3 animate-fade-in">
            {/* User Info */}
            <div className="flex items-center gap-3 p-3 rounded-lg bg-gradient-to-r from-primary/5 to-purple-500/5 border border-primary/10">
              <div className="h-8 w-8 rounded-full bg-gradient-to-r from-primary to-purple-600 flex items-center justify-center">
                <User className="h-4 w-4 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-primary truncate">
                  {user?.email || "Usuário"}
                </div>
                <div className="text-xs text-muted-foreground">
                  Online
                </div>
              </div>
            </div>

            {/* Logout Button */}
            <Button
              onClick={handleSignOut}
              variant="ghost"
              className="w-full justify-start gap-3 h-10 text-red-600 hover:text-red-700 hover:bg-red-50"
            >
              <LogOut className="h-4 w-4" />
              <span className="text-sm">Sair</span>
            </Button>

            {/* Integration Status */}
            <div className="text-center">
              <div className="text-xs text-muted-foreground mb-2">
                Integrado com
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-center gap-2 p-2 rounded-lg bg-gradient-to-r from-green-500/10 to-emerald-500/10 border border-green-500/20">
                  <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse"></div>
                  <span className="text-xs font-medium text-green-600">Google Ads</span>
                </div>
                <div className="flex items-center justify-center gap-2 p-2 rounded-lg bg-gradient-to-r from-blue-500/10 to-indigo-500/10 border border-blue-500/20">
                  <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></div>
                  <span className="text-xs font-medium text-blue-600">Ad Manager</span>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 rounded-full bg-gradient-to-r from-primary to-purple-600 flex items-center justify-center">
              <User className="h-4 w-4 text-white" />
            </div>
            <Button
              onClick={handleSignOut}
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
            >
              <LogOut className="h-4 w-4" />
            </Button>
            <div className="flex flex-col items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse"></div>
              <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};