// Sistema de dados mockados com localStorage
import { useState, useEffect } from 'react';
import { format, subDays, startOfDay } from 'date-fns';

export interface Project {
  id: string;
  name: string;
  domain: string;
  investment: number;
  revenue: number;
  roas: number;
  roi: number;
  grossProfit: number;
  netProfit: number;
  trend: 'up' | 'down' | 'stable';
  campaigns: {
    green: number;
    yellow: number;
    red: number;
  };
  status: 'active' | 'paused' | 'completed';
  manager: string;
  description: string;
}

export interface DailyMetrics {
  date: string;
  investment: number;
  revenue: number;
  profit: number;
  roas: number;
  roi: number;
  impressions: number;
  clicks: number;
  ctr: number;
  conversions: number;
  // Novas métricas para gráfico avançado
  ecpm: number;
  cpc: number;
  viewability: number;
  pmr: number; // Page Match Rate
  rps: number; // Revenue Per Session
}

export interface Campaign {
  id: string;
  name: string;
  projectId: string;
  status: 'active' | 'paused' | 'completed';
  performance: 'excellent' | 'good' | 'average' | 'poor';
  investment: number;
  revenue: number;
  roas: number;
  impressions: number;
  clicks: number;
  ctr: number;
  startDate: string;
  endDate?: string;
}

export interface DashboardSummary {
  totalInvestment: number;
  totalRevenue: number;
  totalProfit: number;
  generalRoas: number;
  finalRoi: number;
  activeCampaigns: number;
  campaignStatus: {
    green: number;
    yellow: number;
    red: number;
  };
  trendsPercentage: {
    investment: number;
    revenue: number;
    profit: number;
    roas: number;
    roi: number;
  };
}

class MockDataService {
  private readonly STORAGE_KEY = 'campaign_dashboard_data';
  private readonly VERSION_KEY = 'data_version';
  private readonly CURRENT_VERSION = '1.0';

  constructor() {
    this.initializeData();
  }

  private initializeData() {
    const version = localStorage.getItem(this.VERSION_KEY);
    if (version !== this.CURRENT_VERSION) {
      this.generateFreshData();
      localStorage.setItem(this.VERSION_KEY, this.CURRENT_VERSION);
    }
  }

  private generateFreshData() {
    const projects = this.generateProjects();
    const campaigns = this.generateCampaigns(projects);
    const dailyMetrics = this.generateDailyMetrics();
    const summary = this.calculateSummary(projects, dailyMetrics);

    const data = {
      projects,
      campaigns,
      dailyMetrics,
      summary,
      lastUpdated: new Date().toISOString()
    };

    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(data));
  }

  private generateProjects(): Project[] {
    return [
      {
        id: '1',
        name: 'Direito2',
        domain: 'direito2.com.br',
        investment: 1847,
        revenue: 3102,
        roas: 168,
        roi: 52,
        grossProfit: 1255,
        netProfit: 1154,
        trend: 'up',
        campaigns: { green: 8, yellow: 3, red: 1 },
        status: 'active',
        manager: 'Felipe Silva',
        description: 'Portal jurídico especializado em direito empresarial'
      },
      {
        id: '2',
        name: 'Folha do Sul',
        domain: 'folhadosul.com.br',
        investment: 742,
        revenue: 1076,
        roas: 145,
        roi: 38,
        grossProfit: 334,
        netProfit: 284,
        trend: 'down',
        campaigns: { green: 3, yellow: 4, red: 2 },
        status: 'active',
        manager: 'Maria Santos',
        description: 'Portal de notícias regional do sul do Brasil'
      },
      {
        id: '3',
        name: 'Cartão e Crédito',
        domain: 'cartaoecredito.com.br',
        investment: 258,
        revenue: 346,
        roas: 134,
        roi: 28,
        grossProfit: 88,
        netProfit: 72,
        trend: 'stable',
        campaigns: { green: 1, yellow: 1, red: 0 },
        status: 'active',
        manager: 'Carlos Lima',
        description: 'Comparador de cartões de crédito e empréstimos'
      }
    ];
  }

  private generateCampaigns(projects: Project[]): Campaign[] {
    const campaigns: Campaign[] = [];
    
    projects.forEach(project => {
      // Campanhas verdes (excelentes)
      for (let i = 0; i < project.campaigns.green; i++) {
        campaigns.push({
          id: `${project.id}-green-${i}`,
          name: `${project.name} - Premium ${i + 1}`,
          projectId: project.id,
          status: 'active',
          performance: 'excellent',
          investment: Math.floor(project.investment * 0.3 / project.campaigns.green),
          revenue: Math.floor(project.revenue * 0.4 / project.campaigns.green),
          roas: 180 + Math.random() * 20,
          impressions: Math.floor(50000 + Math.random() * 30000),
          clicks: Math.floor(1200 + Math.random() * 800),
          ctr: 2.5 + Math.random() * 1.5,
          startDate: format(subDays(new Date(), Math.floor(Math.random() * 30)), 'yyyy-MM-dd')
        });
      }

      // Campanhas amarelas (boas)
      for (let i = 0; i < project.campaigns.yellow; i++) {
        campaigns.push({
          id: `${project.id}-yellow-${i}`,
          name: `${project.name} - Standard ${i + 1}`,
          projectId: project.id,
          status: 'active',
          performance: 'good',
          investment: Math.floor(project.investment * 0.4 / project.campaigns.yellow),
          revenue: Math.floor(project.revenue * 0.35 / project.campaigns.yellow),
          roas: 130 + Math.random() * 30,
          impressions: Math.floor(30000 + Math.random() * 20000),
          clicks: Math.floor(800 + Math.random() * 400),
          ctr: 1.8 + Math.random() * 1.0,
          startDate: format(subDays(new Date(), Math.floor(Math.random() * 45)), 'yyyy-MM-dd')
        });
      }

      // Campanhas vermelhas (ruins)
      for (let i = 0; i < project.campaigns.red; i++) {
        campaigns.push({
          id: `${project.id}-red-${i}`,
          name: `${project.name} - Basic ${i + 1}`,
          projectId: project.id,
          status: 'active',
          performance: 'poor',
          investment: Math.floor(project.investment * 0.3 / Math.max(project.campaigns.red, 1)),
          revenue: Math.floor(project.revenue * 0.25 / Math.max(project.campaigns.red, 1)),
          roas: 80 + Math.random() * 40,
          impressions: Math.floor(15000 + Math.random() * 10000),
          clicks: Math.floor(300 + Math.random() * 200),
          ctr: 1.0 + Math.random() * 0.8,
          startDate: format(subDays(new Date(), Math.floor(Math.random() * 60)), 'yyyy-MM-dd')
        });
      }
    });

    return campaigns;
  }

  private generateDailyMetrics(): DailyMetrics[] {
    const metrics: DailyMetrics[] = [];
    
    // Gerar dados dos últimos 7 dias
    for (let i = 6; i >= 0; i--) {
      const date = format(subDays(startOfDay(new Date()), i), 'yyyy-MM-dd');
      const baseInvestment = 400 + Math.random() * 200;
      const baseRevenue = baseInvestment * (1.4 + Math.random() * 0.4);
      const profit = baseRevenue - baseInvestment;
      const impressions = Math.floor(80000 + Math.random() * 40000);
      const clicks = Math.floor(2000 + Math.random() * 1000);
      const conversions = Math.floor(150 + Math.random() * 100);
      
      metrics.push({
        date,
        investment: Math.floor(baseInvestment),
        revenue: Math.floor(baseRevenue),
        profit: Math.floor(profit),
        roas: Math.floor((baseRevenue / baseInvestment) * 100),
        roi: Math.floor((profit / baseInvestment) * 100),
        impressions,
        clicks,
        ctr: Number(((clicks / impressions) * 100).toFixed(2)),
        conversions,
        // Novas métricas calculadas
        ecpm: Number((baseRevenue / (impressions / 1000)).toFixed(2)),
        cpc: Number((baseInvestment / clicks).toFixed(2)),
        viewability: Number((75 + Math.random() * 20).toFixed(2)), // 75-95%
        pmr: Number((80 + Math.random() * 15).toFixed(2)), // 80-95%
        rps: Number((baseRevenue / (clicks * 0.8)).toFixed(2)) // Assumindo 80% de sessões
      });
    }

    return metrics;
  }

  private calculateSummary(projects: Project[], dailyMetrics: DailyMetrics[]): DashboardSummary {
    const totalInvestment = projects.reduce((sum, p) => sum + p.investment, 0);
    const totalRevenue = projects.reduce((sum, p) => sum + p.revenue, 0);
    const totalProfit = totalRevenue - totalInvestment;
    
    const campaignStatus = projects.reduce(
      (sum, p) => ({
        green: sum.green + p.campaigns.green,
        yellow: sum.yellow + p.campaigns.yellow,
        red: sum.red + p.campaigns.red
      }),
      { green: 0, yellow: 0, red: 0 }
    );

    const activeCampaigns = campaignStatus.green + campaignStatus.yellow + campaignStatus.red;

    return {
      totalInvestment,
      totalRevenue,
      totalProfit,
      generalRoas: Math.floor((totalRevenue / totalInvestment) * 100),
      finalRoi: Math.floor((totalProfit / totalInvestment) * 100),
      activeCampaigns,
      campaignStatus,
      trendsPercentage: {
        investment: 12,
        revenue: 8,
        profit: 15,
        roas: 3,
        roi: 5
      }
    };
  }

  // Métodos públicos para acessar os dados
  getData() {
    const data = localStorage.getItem(this.STORAGE_KEY);
    if (!data) {
      this.generateFreshData();
      return this.getData();
    }
    return JSON.parse(data);
  }

  getProjects(): Project[] {
    return this.getData().projects;
  }

  getCampaigns(): Campaign[] {
    return this.getData().campaigns;
  }

  getDailyMetrics(): DailyMetrics[] {
    return this.getData().dailyMetrics;
  }

  getSummary(): DashboardSummary {
    return this.getData().summary;
  }

  getCampaignsByProject(projectId: string): Campaign[] {
    return this.getCampaigns().filter(c => c.projectId === projectId);
  }

  getProjectById(id: string): Project | undefined {
    return this.getProjects().find(p => p.id === id);
  }

  // Simular atualizações em tempo real
  updateMetrics() {
    const data = this.getData();
    const now = new Date();
    
    // Atualizar apenas se passou mais de 5 minutos desde a última atualização
    const lastUpdate = new Date(data.lastUpdated);
    const timeDiff = now.getTime() - lastUpdate.getTime();
    const minutesDiff = timeDiff / (1000 * 60);

    if (minutesDiff >= 5) {
      // Pequenas flutuações nos dados atuais
      data.projects.forEach((project: Project) => {
        const variation = 0.95 + Math.random() * 0.1; // ±5%
        project.investment = Math.floor(project.investment * variation);
        project.revenue = Math.floor(project.revenue * variation);
        project.roas = Math.floor((project.revenue / project.investment) * 100);
        project.roi = Math.floor(((project.revenue - project.investment) / project.investment) * 100);
      });

      data.summary = this.calculateSummary(data.projects, data.dailyMetrics);
      data.lastUpdated = now.toISOString();
      
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(data));
    }

    return data;
  }

  // Resetar dados para testing
  resetData() {
    localStorage.removeItem(this.STORAGE_KEY);
    localStorage.removeItem(this.VERSION_KEY);
    this.generateFreshData();
  }
}

// Instância singleton
export const mockDataService = new MockDataService();

// Hooks para React
export const useMockData = () => {
  return {
    projects: mockDataService.getProjects(),
    campaigns: mockDataService.getCampaigns(),
    dailyMetrics: mockDataService.getDailyMetrics(),
    summary: mockDataService.getSummary(),
    refresh: () => mockDataService.updateMetrics(),
    reset: () => mockDataService.resetData()
  };
};

export const useProjectData = (projectId: string) => {
  const [projectData, setProjectData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!projectId) {
      setProjectData(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setTimeout(() => {
      const projects = mockDataService.getProjects();
      const campaigns = mockDataService.getCampaigns();
      
      const project = projects.find(p => p.id === projectId);
      const projectCampaigns = campaigns.filter(c => c.projectId === projectId);
      
      // Generate yesterday data for comparison
      const yesterdayData = project ? {
        investment: project.investment * 0.89,
        revenue: project.revenue * 0.93,
        roas: project.roas * 1.04,
        roi: project.roi * 1.11,
        grossProfit: project.grossProfit * 0.92,
        netProfit: project.netProfit * 0.91
      } : null;

      // Generate historical data
      const historicalData = [];
      for (let i = 30; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        historicalData.push({
          date: date.toISOString().split('T')[0],
          dateFormatted: date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }),
          revenue: Math.floor(Math.random() * 1000 + 1500),
          investment: Math.floor(Math.random() * 600 + 800),
          roas: Math.floor(Math.random() * 50 + 120),
          roi: Math.floor(Math.random() * 40 + 30)
        });
      }
      
      setProjectData({
        project,
        campaigns: projectCampaigns,
        dailyMetrics: mockDataService.getDailyMetrics(),
        yesterdayData,
        historicalData
      });
      setIsLoading(false);
    }, 300);
  }, [projectId]);

  return { projectData, isLoading };
};