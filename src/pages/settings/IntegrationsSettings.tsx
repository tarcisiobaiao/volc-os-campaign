import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Layout } from "@/components/layout/Layout";
import { 
  Zap, 
  CheckCircle, 
  AlertTriangle, 
  Settings, 
  Key,
  RefreshCw,
  ExternalLink,
  Calendar,
  Clock
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";

interface Integration {
  id: string;
  name: string;
  description: string;
  status: "connected" | "disconnected" | "error";
  lastSync: string;
  apiKey?: string;
  accountId?: string;
  features: string[];
  setupUrl?: string;
}

const integrations: Integration[] = [
  {
    id: "google-ads",
    name: "Google Ads",
    description: "Importe dados de campanhas, métricas de performance e otimizações automáticas",
    status: "connected",
    lastSync: "2 minutos atrás",
    apiKey: "ya29.a0AfB_byC...",
    accountId: "123-456-7890",
    features: ["Campanhas", "Métricas", "Conversões", "Audiências"],
    setupUrl: "https://ads.google.com/home/tools/manager-accounts/"
  },
  {
    id: "google-ad-manager",
    name: "Google Ad Manager",
    description: "Gerencie inventário de anúncios e otimize receita programática",
    status: "connected", 
    lastSync: "5 minutos atrás",
    apiKey: "AIzaSyB3...",
    accountId: "22247574",
    features: ["Inventário", "Receita", "eCPM", "Fill Rate"],
    setupUrl: "https://admanager.google.com/"
  },
  {
    id: "google-analytics",
    name: "Google Analytics",
    description: "Conecte dados de comportamento do usuário e jornada de conversão",
    status: "error",
    lastSync: "2 horas atrás",
    features: ["Audiências", "Eventos", "Conversões", "Funis"],
    setupUrl: "https://analytics.google.com/"
  },
  {
    id: "facebook-ads",
    name: "Facebook Ads",
    description: "Importe campanhas do Facebook e Instagram para análise unificada",
    status: "disconnected",
    lastSync: "Nunca",
    features: ["Campanhas", "Métricas", "Audiências", "Criativos"],
    setupUrl: "https://business.facebook.com/"
  }
];

export default function IntegrationsSettings() {
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});

  const getStatusIcon = (status: Integration["status"]) => {
    switch (status) {
      case "connected":
        return <CheckCircle className="h-5 w-5 text-success" />;
      case "error":
        return <AlertTriangle className="h-5 w-5 text-destructive" />;
      default:
        return <AlertTriangle className="h-5 w-5 text-muted-foreground" />;
    }
  };

  const getStatusVariant = (status: Integration["status"]) => {
    switch (status) {
      case "connected": return "success";
      case "error": return "danger";
      case "disconnected": return "warning";
      default: return "default";
    }
  };

  const getStatusLabel = (status: Integration["status"]) => {
    switch (status) {
      case "connected": return "Conectado";
      case "error": return "Erro";
      case "disconnected": return "Desconectado";
      default: return status;
    }
  };

  const handleConnect = (integrationId: string) => {
    console.log(`Conectar integração: ${integrationId}`);
    // Aqui você implementaria a lógica de autenticação OAuth
  };

  const handleDisconnect = (integrationId: string) => {
    console.log(`Desconectar integração: ${integrationId}`);
  };

  const handleTestConnection = (integrationId: string) => {
    console.log(`Testar conexão: ${integrationId}`);
  };

  const handleSyncNow = (integrationId: string) => {
    console.log(`Sincronizar agora: ${integrationId}`);
  };

  return (
    <Layout>
      <div className="p-6 space-y-8 max-w-5xl mx-auto">
        {/* Header */}
        <div className="animate-fade-in">
          <h1 className="text-3xl font-bold bg-gradient-dashboard bg-clip-text text-transparent">
            Integrações
          </h1>
          <p className="text-muted-foreground mt-2">
            Configure conexões com Google Ads, Ad Manager e outras plataformas
          </p>
        </div>

        {/* Overview Cards */}
        <div className="grid gap-4 md:grid-cols-3 animate-scale-in">
          <Card className="shadow-card border-success/20">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Conectadas</CardTitle>
              <CheckCircle className="h-4 w-4 text-success" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-success">
                {integrations.filter(i => i.status === "connected").length}
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-destructive/20">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Com Erro</CardTitle>
              <AlertTriangle className="h-4 w-4 text-destructive" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-destructive">
                {integrations.filter(i => i.status === "error").length}
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-card border-warning/20">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Disponíveis</CardTitle>
              <Zap className="h-4 w-4 text-warning" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-warning">
                {integrations.filter(i => i.status === "disconnected").length}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Integrations List */}
        <div className="space-y-6 animate-fade-in">
          {integrations.map((integration) => (
            <Card key={integration.id} className="shadow-card">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-4">
                    <div className="h-12 w-12 bg-gradient-dashboard rounded-lg flex items-center justify-center">
                      {getStatusIcon(integration.status)}
                    </div>
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        {integration.name}
                        <Badge variant={getStatusVariant(integration.status) as any}>
                          {getStatusLabel(integration.status)}
                        </Badge>
                      </CardTitle>
                      <CardDescription className="mt-1">
                        {integration.description}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {integration.status === "connected" && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleSyncNow(integration.id)}
                        >
                          <RefreshCw className="h-4 w-4 mr-2" />
                          Sincronizar
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleTestConnection(integration.id)}
                        >
                          <Settings className="h-4 w-4 mr-2" />
                          Testar
                        </Button>
                      </>
                    )}
                    {integration.status === "disconnected" || integration.status === "error" ? (
                      <Button
                        onClick={() => handleConnect(integration.id)}
                        className="gap-2"
                      >
                        <Zap className="h-4 w-4" />
                        {integration.status === "error" ? "Reconectar" : "Conectar"}
                      </Button>
                    ) : (
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => handleDisconnect(integration.id)}
                      >
                        Desconectar
                      </Button>
                    )}
                  </div>
                </div>
              </CardHeader>
              
              <CardContent className="space-y-6">
                {/* Last Sync Info */}
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  <span>Última sincronização: {integration.lastSync}</span>
                </div>

                {/* Features */}
                <div>
                  <h4 className="font-medium mb-3">Recursos Disponíveis</h4>
                  <div className="flex flex-wrap gap-2">
                    {integration.features.map((feature) => (
                      <Badge key={feature} variant="outline">
                        {feature}
                      </Badge>
                    ))}
                  </div>
                </div>

                {/* Configuration */}
                {integration.status === "connected" && (
                  <div className="space-y-4">
                    <Separator />
                    <h4 className="font-medium">Configuração</h4>
                    
                    <div className="grid gap-4 md:grid-cols-2">
                      {integration.apiKey && (
                        <div>
                          <Label htmlFor={`${integration.id}-api-key`}>API Key</Label>
                          <div className="flex gap-2">
                            <Input
                              id={`${integration.id}-api-key`}
                              type="password"
                              value={integration.apiKey}
                              readOnly
                              className="font-mono text-xs"
                            />
                            <Button variant="outline" size="sm">
                              <Key className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      )}
                      
                      {integration.accountId && (
                        <div>
                          <Label htmlFor={`${integration.id}-account-id`}>Account ID</Label>
                          <Input
                            id={`${integration.id}-account-id`}
                            value={integration.accountId}
                            readOnly
                            className="font-mono"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Setup Link */}
                {integration.setupUrl && (
                  <div className="pt-4 border-t">
                    <Button variant="ghost" size="sm" asChild>
                      <a 
                        href={integration.setupUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2"
                      >
                        <ExternalLink className="h-4 w-4" />
                        Acessar {integration.name}
                      </a>
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Help Section */}
        <Card className="shadow-card border-info/20 bg-gradient-to-br from-info/5 to-info/10 animate-fade-in">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-info">
              <Zap className="h-5 w-5" />
              Precisa de Ajuda?
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Para configurar as integrações, você precisará de:
            </p>
            <ul className="text-sm text-muted-foreground space-y-1 ml-4">
              <li>• Conta ativa nas plataformas (Google Ads, Ad Manager, etc.)</li>
              <li>• Permissões de administrador ou gerente</li>
              <li>• API Keys ou credenciais OAuth configuradas</li>
            </ul>
            <div className="pt-2">
              <Button variant="outline" size="sm">
                <ExternalLink className="h-4 w-4 mr-2" />
                Ver Documentação
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}