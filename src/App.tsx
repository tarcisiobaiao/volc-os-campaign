import React, { lazy, Suspense } from "react";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "next-themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
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
import QGAgenticoPage from "./pages/settings/QGAgenticoPage";
import QgTaskPage from "./pages/settings/QgTaskPage";
import Login from "./pages/Login";
import AssetVaultPage from "./pages/settings/AssetVaultPage";
import ChangePassword from "./pages/ChangePassword";
import NotFound from "./pages/NotFound";
import IncubatorPage from "./pages/incubator/IncubatorPage";
import IncubatorDetailPage from "./pages/incubator/IncubatorDetailPage";
import { CommandPalette } from "@/components/CommandPalette";
import PautadorProPage from "./pages/pautador-pro/PautadorProPage";
import RedatorPage from "./pages/redator/RedatorPage";
import FunilPage from "./pages/redator/FunilPage";
import ConfigRedatorPage from "./pages/redator/ConfigRedatorPage";
import PaginaDoFunilPage from "./pages/redator/PaginaDoFunilPage";
/**
 * A bancada visual — só em desenvolvimento, e o guarda fica NO `lazy`.
 *
 * ⚠️ Guardar apenas a `<Route>` não bastava, e a prova de bundle mediu isso: um
 * `React.lazy(() => import(...))` no topo do módulo é um ponto de entrada para o
 * Rollup MESMO com a rota eliminada — ele emitia `assets/BancadaVisual-*.js` no
 * build de produção. Com o `import()` dentro do ramo, a condição vira o literal
 * `false` e o ramo inteiro sai antes de virar chunk.
 */
const BancadaVisual = import.meta.env.DEV
  ? React.lazy(() => import("./pages/qa/BancadaVisual"))
  : null;
import HubDeTrafegoPage from "./pages/trafego/HubDeTrafegoPage";
import QuadroDeOportunidades from "./components/trafego/oportunidades/QuadroDeOportunidades";
import NovaCampanhaPage from "./pages/trafego/NovaCampanhaPage";
import CampanhaCanonPage from "./pages/trafego/CampanhaCanonPage";
import DecisionIntelligenceLabPage from "./pages/trafego/DecisionIntelligenceLabPage";
// Estúdio Criativo — área de PRODUÇÃO, não subaba de Tráfego (SPEC §6).
// Carregado sob demanda: quem nunca abre `/criativos` não baixa o chunk.
const EstudioHomePage = lazy(() => import("./pages/criativos/EstudioHomePage"));
const BriefingDeImagemPage = lazy(() => import("./pages/criativos/BriefingDeImagemPage"));
const BriefingDeVideoPage = lazy(() => import("./pages/criativos/BriefingDeVideoPage"));
const LeituraDeVideoPage = lazy(() => import("./pages/criativos/LeituraDeVideoPage"));
const JobPage = lazy(() => import("./pages/criativos/JobPage"));
const BibliotecaPage = lazy(() => import("./pages/criativos/BibliotecaPage"));
const AtivoPage = lazy(() => import("./pages/criativos/AtivoPage"));
const AprovacoesPage = lazy(() => import("./pages/criativos/AprovacoesPage"));
const BrandPacksPage = lazy(() => import("./pages/criativos/BrandPacksPage"));
const LaboratorioPage = lazy(() => import("./pages/criativos/LaboratorioPage"));
// v6 RBAC — Etapa 3.A. Lazy load: chunk só é baixado se a feature
// flag estiver ligada E a rota /admin/v6 for visitada.
import { isV6Enabled } from "@/v6/featureFlag";
const V6AdminPage = lazy(() => import("@/v6/pages/V6AdminPage"));

const queryClient = new QueryClient();

/**
 * Rota do Estúdio: sessão + carregamento do chunk sob demanda.
 *
 * O `fallback` não é `null` de propósito: uma tela em branco durante o download
 * do chunk é indistinguível de uma tela quebrada, e quem está numa conexão ruim
 * é justamente quem mais espera.
 */
const RotaDoEstudio = ({ children }: { children: React.ReactNode }) => (
  <ProtectedRoute>
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center" role="status">
          <LoadingSpinner />
          <span className="sr-only">Carregando o Estúdio Criativo</span>
        </div>
      }
    >
      {children}
    </Suspense>
  </ProtectedRoute>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    {/* ⚠️ O tema escuro existia inteiro no CSS e era INALCANÇÁVEL: nada aplicava
        a classe `dark`, não havia controle e não havia consulta ao sistema.
        `attribute="class"` casa com `darkMode: ["class"]` do Tailwind, e o
        padrão é claro porque é o tema da cena de referência do DESIGN.md. */}
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            {/* ⚠️ A bancada visual existe SÓ em desenvolvimento.
                `import.meta.env.DEV` vira o literal `false` no build, e o ramo
                inteiro — inclusive o `import()` dinâmico — sai na eliminação de
                código morto. Ela monta os componentes reais contra fixtures
                para que os estados que uma conta saudável não produz (leitura
                falhou, portão sem causa, contrato truncado) possam ser
                conferidos em navegador. Fora de `ProtectedRoute` de propósito:
                não toca dado de ninguém. */}
            {import.meta.env.DEV && BancadaVisual != null && (
              <Route
                path="/qa/trafego/:superficie/:estado"
                element={
                  <React.Suspense fallback={null}>
                    <BancadaVisual />
                  </React.Suspense>
                }
              />
            )}
            {import.meta.env.DEV && BancadaVisual != null && (
              <Route
                path="/qa/trafego"
                element={
                  <React.Suspense fallback={null}>
                    <BancadaVisual />
                  </React.Suspense>
                }
              />
            )}
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
            <Route path="/settings/cofre-ativos" element={<ProtectedRoute><AssetVaultPage /></ProtectedRoute>} />
            <Route path="/settings/qg-agentico/tarefas/:taskId" element={<ProtectedRoute><QgTaskPage /></ProtectedRoute>} />
            <Route path="/settings/qg-agentico" element={<ProtectedRoute><QGAgenticoPage /></ProtectedRoute>} />
            <Route path="/settings/qd-agentico" element={<Navigate to="/settings/qg-agentico" replace />} />
            <Route path="/incubator" element={<ProtectedRoute><IncubatorPage /></ProtectedRoute>} />
            <Route path="/incubator/:siteId" element={<ProtectedRoute><IncubatorDetailPage /></ProtectedRoute>} />
            <Route path="/pautador-pro" element={<ProtectedRoute><PautadorProPage /></ProtectedRoute>} />
            <Route path="/redator" element={<ProtectedRoute><RedatorPage /></ProtectedRoute>} />
            {/* `/config` ANTES de `/funil/:runId` não é necessário aqui — as duas
                rotas não se sobrepõem —, mas ambas precisam vir depois de
                `/redator` puro, que é a exata (o router v6 já resolve por
                especificidade; a ordem fica explícita para quem ler). */}
            <Route path="/redator/config" element={<ProtectedRoute><ConfigRedatorPage /></ProtectedRoute>} />
            <Route path="/redator/funil/:runId" element={<ProtectedRoute><FunilPage /></ProtectedRoute>} />
            <Route path="/redator/funil/:runId/p/:n" element={<ProtectedRoute><PaginaDoFunilPage /></ProtectedRoute>} />
            {/* O quadro de funis entra como CONTEÚDO da aba Oportunidades, e o que
                entra é o componente EMBUTÍVEL — não a página. `TrafegoPage`
                ainda existe e ainda traz o recuo de quando era rota inteira;
                montá-la aqui desenhava a aba mais estreita e mais baixa que as
                outras duas, e o operador via a tela pular a cada troca de aba. */}
            <Route path="/trafego" element={<ProtectedRoute><HubDeTrafegoPage oportunidades={<QuadroDeOportunidades />} /></ProtectedRoute>} />
            <Route path="/trafego/laboratorio/inteligencia/:scenarioId" element={<ProtectedRoute><DecisionIntelligenceLabPage /></ProtectedRoute>} />
            <Route path="/trafego/campanhas/:volcCampaignId" element={<ProtectedRoute><CampanhaCanonPage /></ProtectedRoute>} />
            <Route path="/trafego/nova/:opportunityId" element={<ProtectedRoute><NovaCampanhaPage /></ProtectedRoute>} />
            {/* Estúdio Criativo. `/criativos/novo` abre a Home com o seletor de
                tipo já revelado: a SPEC §7 pede o seletor só quando a ação é
                iniciada, e essa rota É a ação iniciada. */}
            <Route path="/criativos" element={<RotaDoEstudio><EstudioHomePage /></RotaDoEstudio>} />
            <Route path="/criativos/novo" element={<RotaDoEstudio><EstudioHomePage abrirSeletor /></RotaDoEstudio>} />
            <Route path="/criativos/imagens/novo" element={<RotaDoEstudio><BriefingDeImagemPage /></RotaDoEstudio>} />
            <Route path="/criativos/videos/novo" element={<RotaDoEstudio><BriefingDeVideoPage /></RotaDoEstudio>} />
            {/* `/videos/novo` é EXATA e vem antes: `:buildSlug` casaria com "novo". */}
            <Route path="/criativos/videos/:buildSlug" element={<RotaDoEstudio><LeituraDeVideoPage /></RotaDoEstudio>} />
            <Route path="/criativos/jobs/:creativeJobId" element={<RotaDoEstudio><JobPage /></RotaDoEstudio>} />
            {/* O Laboratório cria RECEITA; `/criativos/novo` cria PEÇA. Duas
                rotas, dois verbos — a confusão entre elas publica a coisa errada. */}
            <Route path="/criativos/laboratorio" element={<RotaDoEstudio><LaboratorioPage /></RotaDoEstudio>} />
            <Route path="/criativos/templates" element={<Navigate to="/criativos/laboratorio" replace />} />
            <Route path="/criativos/biblioteca" element={<RotaDoEstudio><BibliotecaPage /></RotaDoEstudio>} />
            <Route path="/criativos/assets/:assetId" element={<RotaDoEstudio><AtivoPage /></RotaDoEstudio>} />
            <Route path="/criativos/aprovacoes" element={<RotaDoEstudio><AprovacoesPage /></RotaDoEstudio>} />
            <Route path="/criativos/brand-packs" element={<RotaDoEstudio><BrandPacksPage /></RotaDoEstudio>} />
            {/* v6 RBAC — registrada apenas se a feature flag estiver ligada */}
            {isV6Enabled() && (
              <Route
                path="/admin/v6"
                element={
                  <ProtectedRoute>
                    <Suspense fallback={null}>
                      <V6AdminPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
            )}
            {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
            <Route path="*" element={<NotFound />} />
          </Routes>
          <CommandPalette />
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
