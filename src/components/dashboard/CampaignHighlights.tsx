import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { AlertTriangle, TrendingUp, TrendingDown, Minus, ArrowRight, ChevronDown, ChevronUp } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { campaignHighlightsService, CampaignHighlight } from '@/services/campaignHighlightsService';
import { formatBrlCurrency } from '@/utils/currencyUtils';
import { cn } from '@/lib/utils';

interface CampaignHighlightsProps {
  className?: string;
}

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
        return <AlertTriangle className="h-4 w-4 text-red-500" />;
      case 'em_alta':
        return <TrendingUp className="h-4 w-4 text-green-500" />;
      case 'em_baixa':
        return <TrendingDown className="h-4 w-4 text-red-500" />;
      case 'estagnada':
        return <Minus className="h-4 w-4 text-yellow-500" />;
      default:
        return null;
    }
  };

  const getStatusBadgeColor = (status: CampaignHighlight['status']) => {
    switch (status) {
      case 'alerta_tecnico':
        return 'bg-red-100 text-red-700 border-red-300';
      case 'em_alta':
        return 'bg-green-100 text-green-700 border-green-300';
      case 'em_baixa':
        return 'bg-red-100 text-red-700 border-red-300';
      case 'estagnada':
        return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  const renderCampaignList = (
    title: string,
    campaigns: CampaignHighlight[],
    icon: React.ReactNode,
    sectionKey: keyof typeof expandedSections,
    emptyMessage: string
  ) => {
    if (campaigns.length === 0) {
      return null;
    }

    const isExpanded = expandedSections[sectionKey];

    return (
      <div className="space-y-2">
        {/* Header com toggle */}
        <button
          onClick={() => toggleSection(sectionKey)}
          className="w-full flex items-center gap-2 mb-3 hover:opacity-70 transition-opacity"
        >
          {icon}
          <h3 className="font-semibold text-sm">{title}</h3>
          <Badge variant="outline" className="text-xs">
            {campaigns.length}
          </Badge>
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 ml-auto text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 ml-auto text-muted-foreground" />
          )}
        </button>

        {/* Lista de campanhas (mostra apenas se expandido) */}
        {isExpanded && (
          <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
            {campaigns.map((campaign, index) => (
              <div
                key={`${campaign.campaign_id}-${index}`}
                onClick={() => navigate(`/dashboard/campaign/${campaign.campaign_id}`)}
                className="p-3 rounded-lg border bg-card hover:bg-muted/50 cursor-pointer transition-all hover:shadow-md group"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge className={cn('text-xs', getStatusBadgeColor(campaign.status))}>
                        {campaign.status === 'alerta_tecnico' ? '🚨' : ''}
                        {campaign.status === 'em_alta' ? '📈' : ''}
                        {campaign.status === 'em_baixa' ? '📉' : ''}
                        {campaign.status === 'estagnada' ? '➡️' : ''}
                      </Badge>
                      <span className="text-sm font-medium text-foreground">
                        {campaign.campaign_name}
                      </span>
                      <span className="text-xs text-muted-foreground font-mono">
                        (ID: {campaign.campaign_id})
                      </span>
                    </div>
                    <p className="text-sm font-medium text-foreground mb-1">
                      {campaign.motivo}
                    </p>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>💸 {formatBrlCurrency(campaign.avg_spend)}</span>
                      <span>📊 ROAS: {(campaign.roas_inicio - 1).toFixed(2)} → {(campaign.roas_fim - 1).toFixed(2)}</span>
                      <span
                        className={cn(
                          campaign.variacao_roas.startsWith('-') ? 'text-red-600' : 'text-green-600',
                          'font-medium cursor-help'
                        )}
                        title={`Variação do ROAS nos últimos 14 dias (até ontem):\n(${campaign.roas_fim.toFixed(2)} - ${campaign.roas_inicio.toFixed(2)}) / ${campaign.roas_inicio.toFixed(2)} = ${campaign.variacao_roas}`}
                      >
                        {campaign.variacao_roas}
                      </span>
                    </div>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>🎯 Campanhas Destacadas</CardTitle>
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
      <Card className={className}>
        <CardHeader>
          <CardTitle>🎯 Campanhas Destacadas</CardTitle>
          <CardDescription>Top 10 em alta, 10 estagnadas e 10 em baixa (rotacionadas a cada 5 dias)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-destructive">
            <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
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
      <Card className={className}>
        <CardHeader>
          <CardTitle>🎯 Campanhas Destacadas</CardTitle>
          <CardDescription>Top 10 em alta, 10 estagnadas e 10 em baixa (rotacionadas a cada 5 dias)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            <p className="text-sm">Nenhuma campanha destacada no momento</p>
            <p className="text-xs mt-1">As campanhas são rotacionadas automaticamente a cada 5 dias</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              🎯 Campanhas Destacadas
            </CardTitle>
            <CardDescription className="mt-1">
              Top 10 em alta, 10 estagnadas e 10 em baixa • Rotacionadas automaticamente a cada 5 dias
            </CardDescription>
          </div>
          <Badge variant="outline" className="text-xs">
            {totalCampaigns} campanhas
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Alertas Técnicos - Prioridade Máxima */}
        {renderCampaignList(
          '🚨 Alertas Técnicos',
          highlights.alertas_tecnicos,
          <AlertTriangle className="h-5 w-5 text-red-500" />,
          'alertas_tecnicos',
          'Nenhum alerta técnico no momento'
        )}

        {/* Campanhas em Alta */}
        {renderCampaignList(
          '📈 Campanhas em Alta',
          highlights.em_alta,
          <TrendingUp className="h-5 w-5 text-green-500" />,
          'em_alta',
          'Nenhuma campanha em alta no momento'
        )}

        {/* Campanhas Estagnadas */}
        {renderCampaignList(
          '➡️ Campanhas Estagnadas',
          highlights.estagnadas,
          <Minus className="h-5 w-5 text-yellow-500" />,
          'estagnadas',
          'Nenhuma campanha estagnada no momento'
        )}

        {/* Campanhas em Baixa */}
        {renderCampaignList(
          '📉 Campanhas em Baixa',
          highlights.em_baixa,
          <TrendingDown className="h-5 w-5 text-red-500" />,
          'em_baixa',
          'Nenhuma campanha em baixa no momento'
        )}
      </CardContent>
    </Card>
  );
}










