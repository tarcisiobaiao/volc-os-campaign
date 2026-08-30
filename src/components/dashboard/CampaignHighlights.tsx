import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { AlertTriangle, TrendingUp, TrendingDown, Minus, ArrowRight, ChevronDown, ChevronUp, Target, DollarSign, BarChart3, Sparkles } from 'lucide-react';
import { useNavigate, Link } from 'react-router-dom';
import { campaignHighlightsService, CampaignHighlight } from '@/services/campaignHighlightsService';
import { formatBrlCurrency } from '@/utils/currencyUtils';
import { cn } from '@/lib/utils';
import { useIsMobile } from '@/hooks/useIsMobile';

interface CampaignHighlightsProps {
  className?: string;
}

// Chips tingidos por tom semântico (literais para o JIT do Tailwind captar).
const toneChip: Record<'destructive' | 'success' | 'warning', string> = {
  destructive: 'bg-destructive/10 text-destructive',
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
};

export function CampaignHighlights({ className }: CampaignHighlightsProps) {
  const navigate = useNavigate();
  const [highlights, setHighlights] = useState<{
    alertas_tecnicos: CampaignHighlight[];
    em_alta: CampaignHighlight[];
    estagnadas: CampaignHighlight[];
    em_baixa: CampaignHighlight[];
  }>({
    alertas_tecnicos: [],
    em_alta: [],
    estagnadas: [],
    em_baixa: []
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Estados para controlar toggle de cada seção - TODOS MINIMIZADOS POR PADRÃO
  const [expandedSections, setExpandedSections] = useState({
    alertas_tecnicos: false,  // Alertas minimizado por padrão
    em_alta: false,           // Em alta minimizado por padrão
    estagnadas: false,        // Estagnadas minimizado por padrão
    em_baixa: false           // Em baixa minimizado por padrão
  });
  const isMobile = useIsMobile();

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  useEffect(() => {
    const fetchHighlights = async () => {
      try {
        setLoading(true);
        setError(null);
        // Limpar cache antes de buscar
        campaignHighlightsService.clearCache();
        const grouped = await campaignHighlightsService.getCampaignHighlightsGrouped();
        console.log('🔍 Highlights carregados:', grouped);
        setHighlights(grouped);
      } catch (err) {
        console.error('Error fetching campaign highlights:', err);
        setError(err instanceof Error ? err.message : 'Erro ao carregar campanhas destacadas');
      } finally {
        setLoading(false);
      }
    };

    fetchHighlights();
  }, []);

  const getStatusIcon = (status: CampaignHighlight['status']) => {
    switch (status) {
      case 'alerta_tecnico':
        return <AlertTriangle className="h-3.5 w-3.5" />;
      case 'em_alta':
        return <TrendingUp className="h-3.5 w-3.5" />;
      case 'em_baixa':
        return <TrendingDown className="h-3.5 w-3.5" />;
      case 'estagnada':
        return <Minus className="h-3.5 w-3.5" />;
      default:
        return null;
    }
  };

  // Pill de status em token semântico (cor herda no ícone via currentColor).
  const getStatusBadgeColor = (status: CampaignHighlight['status']) => {
    switch (status) {
      case 'alerta_tecnico':
        return 'bg-destructive/12 text-destructive';
      case 'em_alta':
        return 'bg-success/12 text-success';
      case 'em_baixa':
        return 'bg-destructive/12 text-destructive';
      case 'estagnada':
        return 'bg-warning/12 text-warning';
      default:
        return 'bg-muted text-muted-foreground';
    }
  };

  // Título de cartão reutilizado nos estados loading/error/empty/full.
  const cardTitle = (
    <CardTitle className={cn("flex items-center gap-2", isMobile ? "text-xl" : "")}>
      <span className="rounded-md bg-primary/10 text-primary p-1.5"><Target className="h-4 w-4" /></span>
      Campanhas Destacadas
    </CardTitle>
  );

  const renderCampaignList = (
    title: string,
    campaigns: CampaignHighlight[],
    icon: React.ReactNode,
    sectionKey: keyof typeof expandedSections,
    tone: 'destructive' | 'success' | 'warning',
    emptyMessage: string
  ) => {
    if (campaigns.length === 0) {
      return null;
    }

    const isExpanded = expandedSections[sectionKey];

    return (
      <div className="space-y-2">
        {/* Header com toggle - touch target aumentado em mobile */}
        <button
          onClick={() => toggleSection(sectionKey)}
          className={cn(
            "group/sec w-full flex items-center gap-2.5 mb-3 rounded-lg p-2 -ml-2 transition-colors hover:bg-muted/40",
            isMobile && "min-h-[48px] active:bg-muted/50"
          )}
        >
          <span className={cn("inline-flex items-center justify-center rounded-md p-1.5 shrink-0", toneChip[tone])}>
            {icon}
          </span>
          <span className={cn("kicker text-left", isMobile ? "text-xs" : "")}>{title}</span>
          <span className={cn(
            "inline-flex items-center justify-center rounded-full bg-muted px-2 py-0.5 font-medium tabular text-muted-foreground",
            isMobile ? "text-sm" : "text-xs"
          )}>
            {campaigns.length}
          </span>
          <span className="hairline-aurora flex-1 min-w-[1rem]" />
          {isExpanded ? (
            <ChevronUp className={cn(isMobile ? "h-5 w-5" : "h-4 w-4", "text-muted-foreground transition-transform group-hover/sec:-translate-y-0.5")} />
          ) : (
            <ChevronDown className={cn(isMobile ? "h-5 w-5" : "h-4 w-4", "text-muted-foreground transition-transform group-hover/sec:translate-y-0.5")} />
          )}
        </button>

        {/* Lista de campanhas (mostra apenas se expandido) */}
        {isExpanded && (
          <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
            {campaigns.map((campaign, index) => (
              <Link
                key={`${campaign.campaign_id}-${index}`}
                to={`/dashboard/campaign/${campaign.campaign_id}`}
                className={cn(
                  "block no-underline text-inherit rounded-lg border border-border bg-card hover:border-primary/30 hover-lift cursor-pointer group",
                  isMobile ? "p-4 active:scale-[0.98]" : "p-3"
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    {/* Mobile: Layout vertical mais espaçado */}
                    <div className={cn("flex items-center gap-2", isMobile ? "mb-2 flex-wrap" : "mb-1")}>
                      <span className={cn(
                        "inline-flex items-center justify-center rounded-full",
                        isMobile ? "p-1" : "p-0.5",
                        getStatusBadgeColor(campaign.status)
                      )}>
                        {getStatusIcon(campaign.status)}
                      </span>
                      <span className={cn("font-medium text-foreground", isMobile ? "text-base" : "text-sm")}>
                        {campaign.campaign_name}
                      </span>
                      {!isMobile && (
                        <span className="text-xs text-muted-foreground font-mono">
                          (ID: {campaign.campaign_id})
                        </span>
                      )}
                    </div>
                    {/* ID separado em mobile */}
                    {isMobile && (
                      <span className="text-xs text-muted-foreground font-mono block mb-2">
                        ID: {campaign.campaign_id}
                      </span>
                    )}
                    <p className={cn("font-medium text-foreground mb-2", isMobile ? "text-sm" : "text-sm")}>
                      {campaign.motivo}
                    </p>
                    {/* Mobile: métricas em stack vertical */}
                    <div className={cn(
                      "text-xs text-muted-foreground",
                      isMobile ? "flex flex-col gap-2" : "flex items-center gap-4"
                    )}>
                      <span className={cn("inline-flex items-center gap-1.5", isMobile ? "text-sm" : "")}>
                        <DollarSign className="h-3.5 w-3.5 text-muted-foreground/70 flex-shrink-0" />
                        <span className="tabular">{formatBrlCurrency(campaign.avg_spend)}</span>
                      </span>
                      <span className={cn("inline-flex items-center gap-1.5", isMobile ? "text-sm" : "")}>
                        <BarChart3 className="h-3.5 w-3.5 text-muted-foreground/70 flex-shrink-0" />
                        <span className="tabular">ROAS: {(campaign.roas_inicio - 1).toFixed(2)} → {(campaign.roas_fim - 1).toFixed(2)}</span>
                      </span>
                      <span
                        className={cn(
                          campaign.variacao_roas.startsWith('-') ? 'text-destructive' : 'text-success',
                          'font-medium tabular',
                          isMobile ? 'text-sm' : 'cursor-help'
                        )}
                        title={!isMobile ? `Variação do ROAS nos últimos 14 dias (até ontem):\n(${campaign.roas_fim.toFixed(2)} - ${campaign.roas_inicio.toFixed(2)}) / ${campaign.roas_inicio.toFixed(2)} = ${campaign.variacao_roas}` : undefined}
                      >
                        {campaign.variacao_roas}
                      </span>
                    </div>
                  </div>
                  <ArrowRight className={cn(
                    "text-muted-foreground transition-volc flex-shrink-0 group-hover:translate-x-0.5",
                    isMobile ? "h-5 w-5 opacity-100" : "h-4 w-4 opacity-0 group-hover:opacity-100"
                  )} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <Card className={cn("relative overflow-hidden shadow-card", className)}>
        <CardHeader>
          {cardTitle}
          <CardDescription>Top 10 em alta, 10 estagnadas e 10 em baixa (rotacionadas a cada 5 dias)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <LoadingSpinner size="md" text="Carregando campanhas..." />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={cn("relative overflow-hidden shadow-card", className)}>
        <CardHeader>
          {cardTitle}
          <CardDescription>Top 10 em alta, 10 estagnadas e 10 em baixa (rotacionadas a cada 5 dias)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center text-center py-8 text-destructive">
            <span className="rounded-md bg-destructive/10 text-destructive p-2 mb-3"><AlertTriangle className="h-6 w-6" /></span>
            <p className="text-sm">{error}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const totalCampaigns =
    highlights.alertas_tecnicos.length +
    highlights.em_alta.length +
    highlights.estagnadas.length +
    highlights.em_baixa.length;

  if (totalCampaigns === 0) {
    return (
      <Card className={cn("relative overflow-hidden shadow-card", className)}>
        <CardHeader>
          {cardTitle}
          <CardDescription>Top 10 em alta, 10 estagnadas e 10 em baixa (rotacionadas a cada 5 dias)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center text-center py-10">
            <span className="rounded-md bg-primary/10 text-primary p-2 mb-3"><Sparkles className="h-6 w-6" /></span>
            <p className="kicker mb-1">Sem destaques</p>
            <p className="text-sm text-muted-foreground">Nenhuma campanha destacada no momento</p>
            <p className="text-xs text-muted-foreground mt-1">As campanhas são rotacionadas automaticamente a cada 5 dias</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn("relative overflow-hidden shadow-card", className)}>
      <CardHeader className={isMobile ? "p-4" : ""}>
        <div className={cn(
          "flex items-center justify-between",
          isMobile && "flex-col items-start gap-3"
        )}>
          <div>
            {cardTitle}
            <CardDescription className={cn("mt-1", isMobile ? "text-sm" : "")}>
              {isMobile ? (
                <>Top 10 em alta, 10 estagnadas e 10 em baixa</>
              ) : (
                <>Top 10 em alta, 10 estagnadas e 10 em baixa • Rotacionadas automaticamente a cada 5 dias</>
              )}
            </CardDescription>
          </div>
          <Badge variant="outline" className={cn("tabular", isMobile ? "text-sm self-end" : "text-xs")}>
            {totalCampaigns} campanhas
          </Badge>
        </div>
      </CardHeader>
      <CardContent className={cn("space-y-6", isMobile ? "p-4" : "")}>
        {/* Alertas Técnicos - Prioridade Máxima */}
        {renderCampaignList(
          'Alertas Técnicos',
          highlights.alertas_tecnicos,
          <AlertTriangle className="h-4 w-4" />,
          'alertas_tecnicos',
          'destructive',
          'Nenhum alerta técnico no momento'
        )}

        {/* Campanhas em Alta */}
        {renderCampaignList(
          'Campanhas em Alta',
          highlights.em_alta,
          <TrendingUp className="h-4 w-4" />,
          'em_alta',
          'success',
          'Nenhuma campanha em alta no momento'
        )}

        {/* Campanhas Estagnadas */}
        {renderCampaignList(
          'Campanhas Estagnadas',
          highlights.estagnadas,
          <Minus className="h-4 w-4" />,
          'estagnadas',
          'warning',
          'Nenhuma campanha estagnada no momento'
        )}

        {/* Campanhas em Baixa */}
        {renderCampaignList(
          'Campanhas em Baixa',
          highlights.em_baixa,
          <TrendingDown className="h-4 w-4" />,
          'em_baixa',
          'destructive',
          'Nenhuma campanha em baixa no momento'
        )}
      </CardContent>
    </Card>
  );
}
