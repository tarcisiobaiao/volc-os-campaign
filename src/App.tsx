import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import GeneralDashboard from "./pages/GeneralDashboard";
import CampaignDashboard from "./pages/dashboard/CampaignDashboard";
import ProjectDashboard from "./pages/ProjectDashboard";
import Reports from "./pages/Reports";
import ProjectsSettings from "./pages/settings/ProjectsSettings";
import CampaignsSettings from "./pages/settings/CampaignsSettings";
import IntegrationsSettings from "./pages/settings/IntegrationsSettings";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<GeneralDashboard />} />
          <Route path="/dashboard/campaigns" element={<CampaignDashboard />} />
          <Route path="/dashboard/project/:projectId" element={<ProjectDashboard />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings/projects" element={<ProjectsSettings />} />
          <Route path="/settings/campaigns" element={<CampaignsSettings />} />
          <Route path="/settings/integrations" element={<IntegrationsSettings />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
