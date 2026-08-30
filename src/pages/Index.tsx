import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, BarChart3, Users, DollarSign } from "lucide-react";
import { Link } from "react-router-dom";
import { useIsMobile } from "@/hooks/useIsMobile";

const Index = () => {
  const isMobile = useIsMobile();
  return (
    <div className="min-h-screen bg-background">
      {/* Hero Section */}
      <div className="relative overflow-hidden bg-gradient-dashboard">
        <div className="absolute inset-0 bg-grid-pattern opacity-10"></div>
        <div className={`relative max-w-7xl mx-auto px-4 ${isMobile ? 'py-16' : 'py-24 lg:py-32'}`}>
          <div className="text-center animate-fade-in">
            <h1 className={`${isMobile ? 'text-3xl' : 'text-4xl lg:text-6xl'} font-bold text-white mb-6`}>
              Dashboard de
              <span className="block bg-gradient-to-r from-white to-white/80 bg-clip-text text-transparent">
                Campanhas
              </span>
            </h1>
            <p className={`${isMobile ? 'text-base' : 'text-xl'} text-white/90 mb-8 max-w-2xl mx-auto`}>
              Monitore métricas, analise performance e otimize suas campanhas com insights em tempo real
            </p>
            <Link to="/dashboard/campaigns">
              <Button size="lg" className={`bg-white text-primary hover:bg-white/90 shadow-glow ${isMobile ? 'w-full touch-target' : ''}`}>
                <TrendingUp className="mr-2 h-5 w-5" />
                Acessar Dashboard
              </Button>
            </Link>
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className={`max-w-7xl mx-auto px-4 ${isMobile ? 'py-8' : 'py-16'}`}>
        <div className="text-center mb-12 animate-fade-in">
          <h2 className={`${isMobile ? 'text-2xl' : 'text-3xl'} font-bold mb-4`}>Recursos do Dashboard</h2>
          <p className={`text-muted-foreground ${isMobile ? 'text-base' : 'text-lg'} max-w-2xl mx-auto`}>
            Tudo que você precisa para monitorar e otimizar suas campanhas digitais
          </p>
        </div>

        <div className={`grid gap-6 ${isMobile ? 'grid-cols-1' : 'md:grid-cols-2 lg:grid-cols-3'} animate-scale-in`}>
          <Card className="shadow-card hover:shadow-glow transition-volc duration-200">
            <CardHeader>
              <div className="h-10 w-10 bg-primary/10 rounded-lg flex items-center justify-center mb-2">
                <BarChart3 className="h-5 w-5 text-primary" />
              </div>
              <CardTitle>Gráficos Interativos</CardTitle>
              <CardDescription>
                Visualize ROAS, CTR e investimentos com gráficos de linha e barras responsivos
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="shadow-card hover:shadow-glow transition-volc duration-200">
            <CardHeader>
              <div className="h-10 w-10 bg-success/10 rounded-lg flex items-center justify-center mb-2">
                <DollarSign className="h-5 w-5 text-success" />
              </div>
              <CardTitle>KPIs em Tempo Real</CardTitle>
              <CardDescription>
                Acompanhe investimento total, ROAS médio, page views e CTR com dados atualizados
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="shadow-card hover:shadow-glow transition-volc duration-200">
            <CardHeader>
              <div className="h-10 w-10 bg-info/10 rounded-lg flex items-center justify-center mb-2">
                <Users className="h-5 w-5 text-info" />
              </div>
              <CardTitle>Filtros Avançados</CardTitle>
              <CardDescription>
                Filtre dados por projeto, campanha e período customizado para análises específicas
              </CardDescription>
            </CardHeader>
          </Card>
        </div>

        {/* CTA Section */}
        <div className={`text-center ${isMobile ? 'mt-8' : 'mt-16'} animate-fade-in`}>
          <Card className="bg-gradient-card shadow-dashboard max-w-2xl mx-auto">
            <CardContent className={isMobile ? 'p-4' : 'p-8'}>
              <h3 className={`${isMobile ? 'text-xl' : 'text-2xl'} font-bold mb-4`}>Pronto para começar?</h3>
              <p className={`text-muted-foreground ${isMobile ? 'text-sm mb-4' : 'mb-6'}`}>
                Acesse o dashboard e comece a monitorar suas campanhas agora mesmo
              </p>
              <Link to="/dashboard/campaigns">
                <Button size="lg" className={`bg-gradient-primary hover:shadow-glow ${isMobile ? 'w-full touch-target' : ''}`}>
                  <TrendingUp className="mr-2 h-5 w-5" />
                  Ir para Dashboard
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default Index;
