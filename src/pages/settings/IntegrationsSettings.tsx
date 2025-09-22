import { Layout } from "@/components/layout/Layout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Zap,
  Wrench,
  Clock,
  Sparkles
} from "lucide-react";

export default function IntegrationsSettings() {
  return (
    <Layout>
      <div className="p-6 space-y-8 max-w-4xl mx-auto">
        {/* Header */}
        <div className="animate-fade-in text-center">
          <h1 className="text-3xl font-bold bg-gradient-dashboard bg-clip-text text-transparent">
            Integrações
          </h1>
          <p className="text-muted-foreground mt-2">
            Configure conexões com Google Ads, Ad Manager e outras plataformas
          </p>
        </div>

        {/* Coming Soon Card */}
        <div className="flex justify-center animate-scale-in">
          <Card className="shadow-card w-full max-w-2xl border-primary/20 bg-gradient-to-br from-primary/5 to-primary/10">
            <CardHeader className="text-center pb-6">
              <div className="mx-auto h-16 w-16 bg-gradient-dashboard rounded-full flex items-center justify-center mb-4">
                <Wrench className="h-8 w-8 text-white" />
              </div>
              <CardTitle className="text-2xl flex items-center justify-center gap-2">
                <Sparkles className="h-6 w-6 text-primary animate-pulse" />
                Em Breve...
                <Sparkles className="h-6 w-6 text-primary animate-pulse" />
              </CardTitle>
              <CardDescription className="text-lg">
                Funcionalidade em desenvolvimento
              </CardDescription>
            </CardHeader>

            <CardContent className="text-center space-y-6">
              <div className="space-y-4">
                <p className="text-muted-foreground">
                  Estamos trabalhando para trazer as melhores integrações para o seu dashboard.
                </p>

                <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  <span>Nossa equipe está desenvolvendo esta funcionalidade</span>
                </div>
              </div>

              {/* Future Integrations Preview */}
              <div className="pt-6 border-t">
                <h3 className="font-medium mb-4 text-foreground">Integrações Planejadas</h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-background/50">
                    <div className="h-2 w-2 bg-green-500 rounded-full"></div>
                    Google Ads
                  </div>
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-background/50">
                    <div className="h-2 w-2 bg-blue-500 rounded-full"></div>
                    Google Ad Manager
                  </div>
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-background/50">
                    <div className="h-2 w-2 bg-orange-500 rounded-full"></div>
                    Google Analytics
                  </div>
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-background/50">
                    <div className="h-2 w-2 bg-purple-500 rounded-full"></div>
                    Facebook Ads
                  </div>
                </div>
              </div>

              {/* Progress Indicator */}
              <div className="pt-6">
                <div className="flex items-center justify-center gap-2">
                  <div className="h-2 w-2 bg-primary rounded-full animate-pulse"></div>
                  <div className="h-2 w-2 bg-primary/60 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
                  <div className="h-2 w-2 bg-primary/30 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Additional Info */}
        <div className="text-center animate-fade-in">
          <Card className="shadow-card border-info/20 bg-gradient-to-br from-info/5 to-info/10">
            <CardContent className="p-6">
              <div className="flex items-center justify-center gap-2 text-info mb-3">
                <Zap className="h-5 w-5" />
                <span className="font-medium">Aguarde Novidades</span>
              </div>
              <p className="text-sm text-muted-foreground">
                Em breve você poderá conectar suas contas do Google Ads, Ad Manager e outras plataformas
                para centralizar todos os seus dados de marketing em um só lugar.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}