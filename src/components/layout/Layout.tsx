import React, { useState } from "react";
import { Navigation } from "./Navigation";
import { Button } from "@/components/ui/button";
import { Menu } from "lucide-react";
import { useIsMobile } from "@/hooks/useIsMobile";

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [isNavigationCollapsed, setIsNavigationCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const isMobile = useIsMobile();

  return (
    <div className="min-h-screen bg-background flex">
      {/* Navigation Sidebar / Drawer */}
      <Navigation
        isCollapsed={isNavigationCollapsed}
        setIsCollapsed={setIsNavigationCollapsed}
        isMobileOpen={isMobileMenuOpen}
        setIsMobileOpen={setIsMobileMenuOpen}
      />

      {/* Main Content */}
      <main className="flex-1 overflow-hidden">
        {/* Mobile Header com botão hambúrguer */}
        {isMobile && (
          <div className="sticky top-0 z-30 h-14 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 flex items-center px-4 shadow-sm">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsMobileMenuOpen(true)}
              className="h-10 w-10 p-0 touch-target"
              aria-label="Abrir menu"
            >
              <Menu className="h-5 w-5" />
            </Button>
            <div className="ml-3 flex items-center gap-2 flex-1 min-w-0">
              <img
                src="/logo-webgocontent-horizontal.png"
                alt="WebGo Content"
                className="h-7 object-contain max-w-[140px]"
              />
            </div>
          </div>
        )}

        <div className="h-full overflow-auto">
          <div className={isMobile ? "pb-4" : ""}>
            {children}
          </div>
        </div>
      </main>
    </div>
  );
};