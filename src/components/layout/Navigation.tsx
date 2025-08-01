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
  Zap
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";

interface NavigationProps {
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
}

const navigationItems = [
  {
    title: "Dashboard Geral",
    href: "/",
    icon: Home,
    description: "Visão geral de todas as campanhas"
  },
  {
    title: "Dashboard por Projeto",
    href: "/dashboard/campaigns",
    icon: BarChart3,
    description: "Métricas detalhadas por projeto"
  },
  {
    title: "Relatórios",
    href: "/reports",
    icon: FileText,
    description: "Relatórios e análises avançadas"
  }
];

const configurationItems = [
  {
    title: "Projetos",
    href: "/settings/projects",
    icon: FolderOpen,
    description: "Gerenciar projetos"
  },
  {
    title: "Campanhas",
    href: "/settings/campaigns",
    icon: Megaphone,
    description: "Configurar campanhas"
  },
  {
    title: "Custos",
    href: "/settings/costs",
    icon: DollarSign,
    description: "Definir custos e orçamentos"
  },
  {
    title: "Integrações",
    href: "/settings/integrations",
    icon: Zap,
    description: "Google Ads e Ad Manager"
  }
];

export const Navigation: React.FC<NavigationProps> = ({ isCollapsed, setIsCollapsed }) => {
  const location = useLocation();

  const NavItem = ({ item, isActive }: { item: typeof navigationItems[0]; isActive: boolean }) => (
    <Link to={item.href}>
      <Button
        variant={isActive ? "secondary" : "ghost"}
        className={cn(
          "w-full justify-start gap-3 h-12 transition-all duration-200",
          isActive && "bg-primary/10 text-primary font-medium border-r-2 border-primary",
          !isActive && "hover:bg-muted/50",
          isCollapsed && "justify-center px-2"
        )}
      >
        <item.icon className={cn("h-5 w-5 flex-shrink-0", isActive && "text-primary")} />
        {!isCollapsed && (
          <div className="flex flex-col items-start">
            <span className="text-sm font-medium">{item.title}</span>
            <span className="text-xs text-muted-foreground">{item.description}</span>
          </div>
        )}
      </Button>
    </Link>
  );

  return (
    <div className={cn(
      "relative bg-card border-r border-border transition-all duration-300 flex flex-col",
      isCollapsed ? "w-16" : "w-80"
    )}>
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between">
          {!isCollapsed && (
            <div className="animate-fade-in">
              <h2 className="text-lg font-bold bg-gradient-dashboard bg-clip-text text-transparent">
                Campaign Manager
              </h2>
              <p className="text-xs text-muted-foreground">
                Google Ads & Ad Manager
              </p>
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="h-8 w-8 p-0 hover:bg-muted/50"
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
              {navigationItems.map((item) => (
                <NavItem
                  key={item.href}
                  item={item}
                  isActive={location.pathname === item.href}
                />
              ))}
            </nav>
          </div>

          <Separator />

          {/* Configuration */}
          <div>
            {!isCollapsed && (
              <h3 className="mb-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Configurações
              </h3>
            )}
            <nav className="space-y-2">
              {configurationItems.map((item) => (
                <NavItem
                  key={item.href}
                  item={item}
                  isActive={location.pathname === item.href}
                />
              ))}
            </nav>
          </div>
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        {!isCollapsed ? (
          <div className="text-center animate-fade-in">
            <div className="text-xs text-muted-foreground">
              Integrado com
            </div>
            <div className="flex items-center justify-center gap-2 mt-1">
              <div className="h-2 w-2 rounded-full bg-success animate-pulse"></div>
              <span className="text-xs font-medium">Google Ads</span>
            </div>
            <div className="flex items-center justify-center gap-2 mt-1">
              <div className="h-2 w-2 rounded-full bg-success animate-pulse"></div>
              <span className="text-xs font-medium">Ad Manager</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1">
            <div className="h-2 w-2 rounded-full bg-success animate-pulse"></div>
            <div className="h-2 w-2 rounded-full bg-success animate-pulse"></div>
          </div>
        )}
      </div>
    </div>
  );
};