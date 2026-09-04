import React, { useMemo, useState } from 'react';
import {
  ArrowLeft,
  BarChart3,
  Calendar,
  CheckCircle2,
  Circle,
  FolderOpen,
  Hash,
  RefreshCw,
  Search,
  Settings,
  Zap,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { Layout } from '@/components/layout/Layout';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { SeletorRedeCampanhas, type RedeDeCampanhas } from '@/components/campaign/SeletorRedeCampanhas';
import { IdentidadeDeCanal } from '@/components/trafego/hub/IdentidadeDeCanal';
import { MetaFrescorBadge, MetaPeriodoChip } from '@/components/campaign/MetaDemoStatus';
import { CampaignSortSelect } from '@/components/campaign/CampaignSortSelect';
import { sortCampaigns, type CampaignSortKey } from '@/lib/campaignSort';
import { calculateROAS, getROASColorCategory, getROASColorStyles } from '@/utils/roasCalculations';
import { META_DEMO, META_INSIGHTS_DEMO, type ObjetoMetaDemo } from '@/components/trafego/meta/modelo';

interface Props {
  onNetworkChange: (rede: RedeDeCampanhas) => void;
}

const moeda = (valor: number | null) => valor === null
  ? 'Não medido'
  : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(valor);

const dataBr = (iso?: string) => iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('pt-BR') : 'Não medido';

const LEGENDA_ROAS = [
  { cor: 'green' as const, dotClass: 'fill-green-600 text-green-600' },
  { cor: 'yellow' as const, dotClass: 'fill-yellow-600 text-yellow-600' },
  { cor: 'orange' as const, dotClass: 'fill-orange-600 text-orange-600' },
  { cor: 'red' as const, dotClass: 'fill-red-600 text-red-600' },
];

const Estado: React.FC<{ valor: ObjetoMetaDemo['status'] }> = ({ valor }) => {
  if (valor === 'ATIVO') {
    return (
      <Badge variant="outline" className="border-transparent bg-success/12 text-success rounded-full flex items-center gap-1">
        <Circle className="h-2 w-2 fill-current" aria-hidden />Ativa
      </Badge>
    );
  }
  if (valor === 'PAUSADO') {
    return (
      <Badge variant="outline" className="border-transparent bg-warning/12 text-warning rounded-full flex items-center gap-1">
        <Circle className="h-2 w-2 fill-current" aria-hidden />Pausada
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="border-transparent bg-muted text-muted-foreground rounded-full flex items-center gap-1">
      <Circle className="h-2 w-2 fill-current" aria-hidden />Rascunho
    </Badge>
  );
};

interface LeituraFinanceira {
  gasto: number | null;
  receita: number | null;
  lucro: number | null;
  retorno: number | null;
}

function leituraFinanceira(campanhaId: string): LeituraFinanceira {
  const leitura = META_INSIGHTS_DEMO[campanhaId];
  const gasto = leitura?.gasto ?? null;
  const receita = leitura?.receitaGam ?? null;
  const lucro = gasto !== null && receita !== null ? receita - gasto : null;
  const retorno = gasto !== null && receita !== null ? calculateROAS(receita, gasto) : null;
  return { gasto, receita, lucro, retorno };
}

export const MetaCampaignsSettingsDemo: React.FC<Props> = ({ onNetworkChange }) => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [busca, setBusca] = useState('');
  const [projetoFiltro, setProjetoFiltro] = useState('all');
  const [statusFiltro, setStatusFiltro] = useState('all');
  const [sortKey, setSortKey] = useState<CampaignSortKey>('roas');

  const projetos = useMemo(
    () => Array.from(new Set(META_DEMO.campanhas.map((c) => c.projeto).filter(Boolean))) as string[],
    [],
  );

  const campanhasFiltradas = useMemo(() => {
    const filtradas = META_DEMO.campanhas.filter((campanha) => {
      const matchesBusca = campanha.nome.toLocaleLowerCase('pt-BR').includes(busca.toLocaleLowerCase('pt-BR'));
      const matchesProjeto = projetoFiltro === 'all' || campanha.projeto === projetoFiltro;
      let matchesStatus = true;
      if (statusFiltro !== 'all') {
        const { retorno } = leituraFinanceira(campanha.id);
        matchesStatus = retorno !== null && getROASColorCategory(retorno) === statusFiltro;
      }
      return matchesBusca && matchesProjeto && matchesStatus;
    });

    const paraOrdenar = filtradas.map((campanha) => {
      const { gasto, receita } = leituraFinanceira(campanha.id);
      return { campanha, name: campanha.nome, investment: gasto ?? 0, revenue: receita ?? 0 };
    });
    return sortCampaigns(paraOrdenar, sortKey).map((item) => item.campanha);
  }, [busca, projetoFiltro, statusFiltro, sortKey]);

  const handleAtualizar = () => {
    toast({
      title: 'Pré-visualização Meta',
      description: 'A sincronização real com a Marketing API ainda não está conectada neste cenário.',
    });
  };

  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;

  return (
    <Layout>
      <div className={`${isMobile ? 'p-4' : 'p-6'} space-y-6 md:space-y-8 max-w-7xl mx-auto`}>
        {/* Header with Controls */}
        <div className="space-y-4 transition-volc duration-200">
          {/* Title Section */}
          <div className="flex items-start gap-3 reveal" style={{ ['--i' as any]: 0 }}>
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="flex-shrink-0 gap-2 touch-target">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Voltar
            </Button>
            <div className="flex-1 min-w-0">
              <div className="kicker mb-2 flex items-center gap-2">
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <Settings className="h-3 w-3" aria-hidden />
                </span>
                Configurações · Campanhas
              </div>
              <h1 className={`font-display font-bold tracking-tight leading-[1.05] ${isMobile ? 'text-[1.7rem]' : 'text-4xl'}`}>
                Campanhas
              </h1>
              <div className="mt-3 aurora-rule w-16" />
              <p className={`mt-3 text-muted-foreground ${isMobile ? 'text-sm' : ''}`}>
                A mesma leitura financeira do Google Ads, separada pela origem da mídia.
                {projetoFiltro !== 'all' && (
                  <span className={`${isMobile ? 'block mt-1' : 'ml-2'} text-primary`}>
                    • Projeto: {projetoFiltro}
                  </span>
                )}
              </p>
            </div>
          </div>

          <SeletorRedeCampanhas rede="meta" onChange={onNetworkChange} />

          {/* Filters and Actions Section */}
          <div className={`flex ${isMobile ? 'flex-col w-full' : 'items-center'} gap-3 flex-wrap`}>
            <Select value={projetoFiltro} onValueChange={setProjetoFiltro}>
              <SelectTrigger className={`${isMobile ? 'w-full' : 'w-48'}`}>
                <SelectValue placeholder="Filtrar projeto" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">
                  <span className="flex items-center gap-2">
                    <FolderOpen className="h-4 w-4" />
                    Todos os Projetos
                  </span>
                </SelectItem>
                {projetos.map((projeto) => (
                  <SelectItem key={projeto} value={projeto}>{projeto}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={statusFiltro} onValueChange={setStatusFiltro}>
              <SelectTrigger className={`${isMobile ? 'w-full' : 'w-48'}`}>
                <SelectValue placeholder="Filtrar por performance" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all"> Todas as Campanhas </SelectItem>
                <SelectItem value="green">
                  <span className="flex items-center gap-2">
                    <Circle className="h-3 w-3 fill-green-600 text-green-600" />
                    Campanhas Verdes (ROAS ≥ 80%)
                  </span>
                </SelectItem>
                <SelectItem value="yellow">
                  <span className="flex items-center gap-2">
                    <Circle className="h-3 w-3 fill-yellow-600 text-yellow-600" />
                    Campanhas Amarelas (ROAS 40-79%)
                  </span>
                </SelectItem>
                <SelectItem value="orange">
                  <span className="flex items-center gap-2">
                    <Circle className="h-3 w-3 fill-orange-600 text-orange-600" />
                    Campanhas Laranjas (ROAS 0-39%)
                  </span>
                </SelectItem>
                <SelectItem value="red">
                  <span className="flex items-center gap-2">
                    <Circle className="h-3 w-3 fill-red-600 text-red-600" />
                    Campanhas Vermelhas (ROAS negativo)
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>

            <MetaPeriodoChip label="Últimos 7 dias · demonstração" className={isMobile ? 'w-full' : 'w-56'} />

            <div className="flex items-center gap-2 flex-wrap">
              <Button onClick={handleAtualizar} variant="outline" size="sm" className="flex-shrink-0">
                <RefreshCw className="h-4 w-4 mr-2" />
                Atualizar
              </Button>

              <MetaFrescorBadge />
            </div>
          </div>
        </div>

        {/* Search Bar */}
        <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-4`}>
          <div className={`relative ${isMobile ? 'w-full' : 'flex-1 max-w-md'}`}>
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <label htmlFor="busca-de-campanhas-meta" className="sr-only">
              Buscar campanhas por nome
            </label>
            <Input
              id="busca-de-campanhas-meta"
              type="search"
              placeholder="Buscar campanhas..."
              value={busca}
              onChange={(event) => setBusca(event.target.value)}
              className={`pl-10 ${isMobile ? 'w-full touch-target' : ''}`}
            />
          </div>
          <CampaignSortSelect value={sortKey} onChange={setSortKey} className={isMobile ? 'w-full' : 'w-44'} />
          <div className={`flex ${isMobile ? 'flex-wrap w-full' : 'items-center'} gap-2`}>
            <Badge variant="outline" className="text-sm">
              <span className="tabular">{campanhasFiltradas.length}</span> {campanhasFiltradas.length === 1 ? 'campanha' : 'campanhas'}
            </Badge>
            {statusFiltro === 'all' && campanhasFiltradas.length > 0 && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                {LEGENDA_ROAS.map(({ cor, dotClass }) => (
                  <span key={cor} className="flex items-center gap-1">
                    <Circle className={`h-2 w-2 ${dotClass}`} />
                    {campanhasFiltradas.filter((c) => {
                      const { retorno } = leituraFinanceira(c.id);
                      return retorno !== null && getROASColorCategory(retorno) === cor;
                    }).length}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Campaigns List */}
        <div className="space-y-4">
          {campanhasFiltradas.map((campanha, index) => {
            const { gasto, receita, lucro, retorno } = leituraFinanceira(campanha.id);
            const periodo = META_INSIGHTS_DEMO[campanha.id]?.periodo ?? 'Cenário demonstrativo';
            return (
              <Link
                key={campanha.id}
                to={`/dashboard/campaign/${campanha.id}?rede=meta&modo=demo`}
                className="block no-underline text-inherit reveal"
                style={{ ['--i' as any]: Math.min(index, 8) }}
              >
                <Card className="relative overflow-hidden p-6 cursor-pointer shadow-card hover-lift">
                  <CardContent className="p-0">
                    <div className="space-y-4">
                      {/* Campaign Header */}
                      <div className="flex items-start justify-between">
                        <div className="min-w-0">
                          <h3 className="font-display font-semibold text-lg flex items-center gap-2 flex-wrap">
                            <Estado valor={campanha.status} />
                            <span className="truncate">{campanha.nome}</span>
                          </h3>
                          <IdentidadeDeCanal rede="meta" canal="Tráfego" className="mt-2" />
                          <p className="text-sm text-muted-foreground mt-1">
                            <span className="flex items-center gap-1">
                              <FolderOpen className="h-3 w-3" />
                              {campanha.projeto ?? 'Sem projeto vinculado'}
                            </span>
                          </p>
                        </div>
                      </div>

                      {/* Metrics Gasto vs Revenue */}
                      <div>
                        <div className="flex items-center gap-2 mb-3">
                          <span className="rounded-md bg-primary/10 text-primary p-1.5">
                            <BarChart3 className="h-3.5 w-3.5" />
                          </span>
                          <span className="kicker">Performance Financeira · {periodo}</span>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-4 text-sm">
                          <div className="relative overflow-hidden text-center p-3 rounded-lg border border-border bg-card">
                            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-info" />
                            <p className="kicker mb-1">Gasto</p>
                            <p className="font-display text-base md:text-lg font-bold tabular text-foreground">{moeda(gasto)}</p>
                          </div>
                          <div className="relative overflow-hidden text-center p-3 rounded-lg border border-border bg-card">
                            <span className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-success" />
                            <p className="kicker mb-1">Revenue</p>
                            <p className="font-display text-base md:text-lg font-bold tabular text-success">{moeda(receita)}</p>
                          </div>
                          <div className={`relative overflow-hidden text-center p-3 rounded-lg border ${retorno === null ? 'border-border bg-card' : getROASColorStyles(retorno)}`}>
                            <p className="kicker mb-1">ROAS</p>
                            <p className="font-display text-base md:text-lg font-bold tabular">{retorno === null ? 'Não medido' : `${retorno.toFixed(1)}%`}</p>
                          </div>
                          <div className="relative overflow-hidden text-center p-3 rounded-lg border border-border bg-card">
                            <span className={`pointer-events-none absolute inset-x-0 top-0 h-0.5 ${lucro === null ? 'bg-muted-foreground/30' : lucro >= 0 ? 'bg-success' : 'bg-destructive'}`} />
                            <p className="kicker mb-1">Lucro Bruto</p>
                            <p className={`font-display text-base md:text-lg font-bold tabular ${lucro === null ? 'text-foreground' : lucro >= 0 ? 'text-success' : 'text-destructive'}`}>{moeda(lucro)}</p>
                          </div>
                        </div>
                      </div>

                      {/* Campaign Details */}
                      <div className={`flex ${isMobile ? 'flex-col' : 'items-center'} gap-2 md:gap-4 ${isMobile ? 'text-xs' : 'text-sm'} text-muted-foreground pt-3 border-t border-border`}>
                        <span className="flex items-center gap-1.5">
                          <Hash className="h-3 w-3" />
                          <span className="tabular">{campanha.id}</span>
                        </span>
                        {!isMobile && <span className="text-border">|</span>}
                        <span className="flex items-center gap-1.5">
                          <Calendar className="h-3 w-3" />
                          Criada: <span className="tabular">{dataBr(campanha.criadoEm)}</span>
                        </span>
                        {!isMobile && <span className="text-border">|</span>}
                        <span className="flex items-center gap-1.5">Status: <Estado valor={campanha.status} /></span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}

          {campanhasFiltradas.length === 0 && (
            <Card className="p-8 text-center shadow-card">
              <p className="text-muted-foreground">Nenhuma campanha encontrada.</p>
            </Card>
          )}
        </div>

        {/* System Info */}
        <Card className="relative overflow-hidden mt-6 p-5 border-border shadow-card">
          <div className="flex items-center gap-2 mb-4">
            <span className="rounded-md bg-info/10 text-info p-1.5"><Zap className="h-4 w-4" /></span>
            <span className="kicker">Pré-visualização Meta Ads</span>
            <span className="hairline-aurora flex-1" />
          </div>
          <div className={`grid ${isMobile ? 'grid-cols-1' : 'grid-cols-2'} gap-4 ${isMobile ? 'text-xs' : 'text-sm'} text-muted-foreground`}>
            <div className="space-y-2">
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Cenário fictício:</strong> os três blocos acima validam a experiência, não uma conta real.</span></p>
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Sem Marketing API:</strong> nenhum token ou conta Meta foi consultado para gerar estes dados.</span></p>
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Sem escrita no Supabase:</strong> nada aqui foi migrado, criado ou ativado de verdade.</span></p>
            </div>
            <div className="space-y-2">
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Economia comum:</strong> gasto Meta × revenue GAM, a mesma espinha financeira do Google Ads.</span></p>
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Ausência ≠ zero:</strong> campanhas em rascunho mostram "Não medido", nunca um valor inventado.</span></p>
              <p className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" /><span><strong className="text-foreground">Ações reais bloqueadas:</strong> pausar, ativar ou editar seguem desativados neste cenário.</span></p>
            </div>
          </div>
        </Card>
      </div>
    </Layout>
  );
};

export default MetaCampaignsSettingsDemo;
