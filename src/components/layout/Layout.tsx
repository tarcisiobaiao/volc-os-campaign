import React, { useState } from "react";
import { Navigation } from "./Navigation";
import { cn } from "@/lib/utils";

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [isNavigationCollapsed, setIsNavigationCollapsed] = useState(false);

  return (
    <div className="min-h-screen bg-background flex">
      {/* Navigation Sidebar */}
      <Navigation 
        isCollapsed={isNavigationCollapsed}
        setIsCollapsed={setIsNavigationCollapsed}
      />
      
      {/* Main Content */}
      <main className={cn(
        "flex-1 overflow-hidden transition-all duration-300",
        isNavigationCollapsed ? "ml-0" : "ml-0"
      )}>
        <div className="h-full overflow-auto">
          {children}
        </div>
      </main>
    </div>
  );
};