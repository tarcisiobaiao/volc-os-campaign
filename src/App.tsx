import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { OperatorRedirect } from "@/components/OperatorRedirect";
import Index from "./pages/Index";
import GeneralDashboard from "./pages/GeneralDashboard";
import SimpleTest from "./pages/SimpleTest";
import CampaignDetailDashboard from "./pages/CampaignDetailDashboard";
import ProjectDashboard from "./pages/ProjectDashboard";
import Reports from "./pages/Reports";
import ProjectsSettings from "./pages/settings/ProjectsSettings";
import CampaignsSettings from "./pages/settings/CampaignsSettings";
import CostsSettings from "./pages/settings/CostsSettings";
import IntegrationsSettings from "./pages/settings/IntegrationsSettings";
import UsersSettings from "./pages/settings/UsersSettings";
import Login from "./pages/Login";
import ChangePassword from "./pages/ChangePassword";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/change-password" element={<ProtectedRoute><ChangePassword /></ProtectedRoute>} />
            <Route path="/" element={<ProtectedRoute><OperatorRedirect><GeneralDashboard /></OperatorRedirect></ProtectedRoute>} />
            <Route path="/test" element={<ProtectedRoute><SimpleTest /></ProtectedRoute>} />
            <Route path="/dashboard/projects" element={<ProtectedRoute><ProjectsSettings /></ProtectedRoute>} />
            <Route path="/dashboard/campaign/:campaignId" element={<ProtectedRoute><CampaignDetailDashboard /></ProtectedRoute>} />
            <Route path="/dashboard/project/:projectId" element={<ProtectedRoute><ProjectDashboard /></ProtectedRoute>} />
            <Route path="/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
            <Route path="/settings/projects" element={<ProtectedRoute><ProjectsSettings /></ProtectedRoute>} />
            <Route path="/settings/campaigns" element={<ProtectedRoute><CampaignsSettings /></ProtectedRoute>} />
            <Route path="/settings/costs" element={<ProtectedRoute><CostsSettings /></ProtectedRoute>} />
            <Route path="/settings/integrations" element={<ProtectedRoute><IntegrationsSettings /></ProtectedRoute>} />
            <Route path="/settings/users" element={<ProtectedRoute><UsersSettings /></ProtectedRoute>} />
            {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
