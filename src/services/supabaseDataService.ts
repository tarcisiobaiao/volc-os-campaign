import { useState, useEffect, useRef, useMemo } from 'react';
import { supabase, DatabaseProject, DatabaseCampaign, DatabaseDailyProjectMetrics, DatabaseDailyCampaignMetrics, DatabaseUrlDailyPerformance } from '@/lib/supabase';
import { format, subDays, differenceInDays } from 'date-fns';
import { currencyConversionService } from './currencyConversionService';
import { getSaoPauloTimestamp } from '@/utils/timezone';
import { operationalCostsService } from './operationalCostsService';
import { taxHistoryService } from './taxHistoryService';

// Types that match the UI components
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
  costs_division?: boolean;
  revshare?: number;
  gamNetworkCode?: string;
  project_type?: 'GAM' | 'ADSENSE';
  visible?: boolean; // Frontend-only filter flag
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
  commission?: number; // NEW: Comissão do operador
  // Novos campos para nova lógica
  googleAdsCampaignId?: string;
  utmCampaignValue?: string;
  extractedUrl?: string;
  extractedDomain?: string;
  customGoal?: string;
  // Campos de controle de status
  statusSource?: 'auto' | 'user';
  userPausedAt?: string;
  userPausedBy?: string;
  // URLs mantidas para compatibilidade, mas deprecated
  urls?: string[];
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
  ecpm: number;
  cpc: number;
  viewability: number;
  pmr: number;
  rps: number;
}

export interface DashboardSummary {
  totalInvestment: number;
  totalRevenue: number;
  totalRevenueAfterRevshare?: number; // NEW: Faturamento líquido após revenue share
  totalProfit: number;
  totalCommission?: number; // NEW: Total de comissão dos operadores
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

class SupabaseDataService {
  // Cache for current server date
  private currentServerDate: string | null = null;

  // 🔄 Invalidar cache quando dados são atualizados
  static invalidateCache(): void {
    localStorage.setItem('lastDataUpdate', Date.now().toString());
  }

  // 🎯 Check if cache is still valid based on database updated_at
  private async isCacheValid(cacheKey: string, cacheTimestamp: number, date?: string, table: 'daily_project_metrics' | 'daily_campaign_metrics' = 'daily_project_metrics'): Promise<boolean> {
    try {
      // For today data, check if database has newer data
      if (date) {
        const { data: latestUpdate } = await supabase
          .from(table)
          .select('updated_at')
          .eq('date', date)
          .order('updated_at', { ascending: false })
          .limit(1);

        if (latestUpdate && latestUpdate[0]?.updated_at) {
          const dbTimestamp = new Date(latestUpdate[0].updated_at).getTime();
          const cacheIsNewer = cacheTimestamp > dbTimestamp;

          console.log({
            cacheKey,
            table,
            cacheTimestamp: new Date(cacheTimestamp).toISOString(),
            dbTimestamp: new Date(dbTimestamp).toISOString(),
            cacheIsValid: cacheIsNewer
          });

          return cacheIsNewer;
        }
      }

      // If no database data or no date provided, cache is valid
      return true;
    } catch (error) {
      console.warn('⚠️ Error checking cache validity, assuming valid:', error);
      return true;
    }
  }

  // 🎯 Check cache validity for campaign-based data using daily_campaign_metrics
  private async isCampaignCacheValid(cacheKey: string, cacheTimestamp: number, dateRange?: { startDate: string, endDate: string }): Promise<boolean> {
    try {
      if (dateRange) {
        const { data: latestUpdate } = await supabase
          .from('daily_campaign_metrics')
          .select('updated_at')
          .gte('date', dateRange.startDate)
          .lte('date', dateRange.endDate)
          .order('updated_at', { ascending: false })
          .limit(1);

        if (latestUpdate && latestUpdate[0]?.updated_at) {
          const dbTimestamp = new Date(latestUpdate[0].updated_at).getTime();
          const cacheIsNewer = cacheTimestamp > dbTimestamp;

          console.log({
            cacheKey,
            table: 'daily_campaign_metrics',
            cacheTimestamp: new Date(cacheTimestamp).toISOString(),
            dbTimestamp: new Date(dbTimestamp).toISOString(),
            cacheIsValid: cacheIsNewer
          });

          return cacheIsNewer;
        }
      }

      return true;
    } catch (error) {
      console.warn('⚠️ Error checking campaign cache validity, assuming valid:', error);
      return true;
    }
  }
  
  // UPDATED: Now uses revenue_converted_revshare as primary value (net revenue after revshare)
  private getRevenueValue(revenueUsd: number, revenueConverted?: number, revenueConvertedRevshare?: number): number {
    // 1. HIGHEST PRIORITY: Use revenue_converted_revshare if available (net revenue after revshare discount)
    // This applies to daily_campaign_metrics data
    if (revenueConvertedRevshare !== undefined && revenueConvertedRevshare > 0) {
      return revenueConvertedRevshare;
    }

    // 2. FALLBACK: Use revenue_converted if available (gross BRL revenue)
    if (revenueConverted && revenueConverted > 0) {
      return revenueConverted;
    }

    // 3. LAST RESORT: Convert USD to BRL using fixed rate
    if (revenueUsd > 0) {
      return revenueUsd * 5.50; // Using fixed rate for consistency
    }

    return 0;
  }

  // NEW: Get gross revenue before revshare (for tooltips)
  private getGrossRevenueValue(revenueUsd: number, revenueConverted?: number): number {
    // 1. Use revenue_converted if available (gross BRL revenue)
    if (revenueConverted && revenueConverted > 0) {
      return revenueConverted;
    }

    // 2. FALLBACK: Convert USD to BRL using fixed rate
    if (revenueUsd > 0) {
      return revenueUsd * 5.50;
    }

    return 0;
  }

  // NEW: Calculate simplified net profit using pre-calculated revenue share values
  public calculateSimplifiedNetProfit(
    revenueAfterRevshare: number, 
    totalInvestment: number, 
    taxRate: number = 0.081
  ): {
    netRevenue: number;
    grossProfit: number;
    taxAmount: number;
    netProfit: number;
    formula: string;
  } {
    // Simplified calculation using pre-calculated values
    const grossProfit = revenueAfterRevshare - totalInvestment;
    const taxAmount = revenueAfterRevshare * taxRate; // Tax on net revenue
    const netProfit = grossProfit - taxAmount;

    return {
      netRevenue: revenueAfterRevshare,
      grossProfit,
      taxAmount,
      netProfit,
      formula: `Faturamento Líquido (${revenueAfterRevshare.toFixed(2)}) - Investimento (${totalInvestment.toFixed(2)}) - Impostos (${taxAmount.toFixed(2)}) = ${netProfit.toFixed(2)}`
    };
  }

  // NEW: Calculate net profit with operational costs division for projects list
  public async calculateProjectNetProfitWithOperationalCosts(
    revenueAfterRevshare: number,
    totalInvestment: number,
    startDate: string,
    endDate: string,
    projectCostsDivision: boolean,
    taxRate: number = 0.081
  ): Promise<{
    netRevenue: number;
    grossProfit: number;
    taxAmount: number;
    operationalCostShare: number;
    netProfit: number;
    formula: string;
  }> {
    try {
      // Calculate basic values
      const grossProfit = revenueAfterRevshare - totalInvestment;
      const taxAmount = revenueAfterRevshare * taxRate;

      let operationalCostShare = 0;

      if (projectCostsDivision) {
        // 🚀 RPC OPTIMIZATION: Tentar usar get_operational_costs_aggregated primeiro
        try {
          console.log('🚀 calculateProjectNetProfitWithOperationalCosts RPC call:', { startDate, endDate });

          const { data: rpcData, error: rpcError } = await supabase.rpc('get_operational_costs_aggregated', {
            p_start_date: startDate,
            p_end_date: endDate
          });

          if (!rpcError && rpcData && rpcData.length > 0) {
            operationalCostShare = Number(rpcData[0].cost_per_project_per_day) || 0;
            console.log('✅ Operational costs RPC success:', { operationalCostShare });
          } else {
            throw new Error(rpcError?.message || 'RPC returned empty');
          }
        } catch (rpcException) {
          console.warn('⚠️ Operational costs RPC failed, using fallback:', rpcException);

          // 🔄 FALLBACK: Método antigo (loop de meses)
          const startMonth = startDate.slice(0, 7);
          const endMonth = endDate.slice(0, 7);

          const months = [];
          const currentMonth = new Date(startMonth + '-01');
          const finalMonth = new Date(endMonth + '-01');

          while (currentMonth <= finalMonth) {
            months.push(currentMonth.toISOString().slice(0, 7));
            currentMonth.setMonth(currentMonth.getMonth() + 1);
          }

          let totalOperationalCosts = 0;
          for (const month of months) {
            const activeCosts = await operationalCostsService.getActiveCostsByMonth(month);
            const monthlyTotal = activeCosts.reduce((sum, cost) => sum + (cost.amount || 0), 0);
            totalOperationalCosts += monthlyTotal;
          }

          const { data: projectsWithCostDivision, error } = await supabase
            .from('projects')
            .select('id')
            .eq('costs_division', true);

          if (!error) {
            const projectsCount = projectsWithCostDivision?.length || 1;
            const daysInPeriod = differenceInDays(new Date(endDate), new Date(startDate)) + 1;

            let totalDaysInMonths = 0;
            for (const month of months) {
              const [year, monthNum] = month.split('-').map(Number);
              const daysInMonth = new Date(year, monthNum, 0).getDate();
              totalDaysInMonths += daysInMonth;
            }

            const dailyOperationalCost = totalOperationalCosts / totalDaysInMonths;
            operationalCostShare = (dailyOperationalCost * daysInPeriod) / projectsCount;
          }
        }
      }

      const netProfit = grossProfit - taxAmount - operationalCostShare;

      return {
        netRevenue: revenueAfterRevshare,
        grossProfit,
        taxAmount,
        operationalCostShare,
        netProfit,
        formula: `Revenue (${revenueAfterRevshare.toFixed(2)}) - Investimento (${totalInvestment.toFixed(2)}) - Impostos (${taxAmount.toFixed(2)}) - Custo Op. (${operationalCostShare.toFixed(2)}) = ${netProfit.toFixed(2)}`
      };
    } catch (error) {
      console.error('Error calculating operational costs:', error);
      // Fallback to simple calculation
      const grossProfit = revenueAfterRevshare - totalInvestment;
      const taxAmount = revenueAfterRevshare * taxRate;
      const netProfit = grossProfit - taxAmount;

      return {
        netRevenue: revenueAfterRevshare,
        grossProfit,
        taxAmount,
        operationalCostShare: 0,
        netProfit,
        formula: `Revenue (${revenueAfterRevshare.toFixed(2)}) - Investimento (${totalInvestment.toFixed(2)}) - Impostos (${taxAmount.toFixed(2)}) = ${netProfit.toFixed(2)}`
      };
    }
  }
  
  // Get current server date (cached for performance)
  // Uses São Paulo timezone to match local business hours
  private async getCurrentServerDate(): Promise<string> {
    if (this.currentServerDate) {
      return this.currentServerDate;
    }
    
    try {

      // Force São Paulo timezone calculation locally for better reliability
      const now = new Date();
      const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo'
      }).format(now);


      // Validate the RPC function but use local calculation as primary
      try {
        const { data: rpcDate, error } = await supabase.rpc('get_current_date');
        if (!error && rpcDate) {

          // Compare and warn if there's a mismatch
          if (rpcDate !== saoPauloDate) {
            console.warn('⚠️ Date mismatch between local calculation and RPC:', {
              local: saoPauloDate,
              rpc: rpcDate
            });
          }
        }
      } catch (rpcError) {
        console.warn('⚠️ RPC get_current_date failed, using local calculation:', rpcError);
      }

      this.currentServerDate = saoPauloDate;
      return this.currentServerDate;
    } catch (error) {
      console.error('❌ Error getting server date:', error);
      // Fallback to current date in São Paulo timezone
      const now = new Date();
      const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo'
      }).format(now);
      this.currentServerDate = saoPauloDate;
      return this.currentServerDate;
    }
  }
  // Convert database project to UI project format
  private convertDatabaseProject(dbProject: DatabaseProject, metrics?: DatabaseDailyProjectMetrics[]): Project {
    console.log({
      id: dbProject.id,
      project_name: dbProject.project_name,
      project_type: dbProject.project_type,
      allFields: Object.keys(dbProject)
    });
    const latestMetrics = metrics?.[0]; // Assuming metrics are ordered by date desc
    
    // Calculate campaign performance distribution from real data
    const projectCampaigns = metrics?.length || 0;
    // Determine performance based on ROAS values
    const roas = latestMetrics?.roas || 0;
    let greenCampaigns = 0, yellowCampaigns = 0, redCampaigns = 0;
    
    if (projectCampaigns > 0) {
      if (roas >= 180) {
        greenCampaigns = Math.max(1, Math.floor(projectCampaigns * 0.8));
        yellowCampaigns = Math.floor(projectCampaigns * 0.2);
      } else if (roas >= 130) {
        greenCampaigns = Math.floor(projectCampaigns * 0.6);
        yellowCampaigns = Math.floor(projectCampaigns * 0.3);
        redCampaigns = projectCampaigns - greenCampaigns - yellowCampaigns;
      } else if (roas >= 100) {
        greenCampaigns = Math.floor(projectCampaigns * 0.4);
        yellowCampaigns = Math.floor(projectCampaigns * 0.4);
        redCampaigns = projectCampaigns - greenCampaigns - yellowCampaigns;
      } else {
        yellowCampaigns = Math.floor(projectCampaigns * 0.3);
        redCampaigns = projectCampaigns - yellowCampaigns;
      }
    }

    // Determine trend based on actual performance metrics
    const roi = latestMetrics?.roi || 0;
    const trend: 'up' | 'down' | 'stable' = 
      roi > 50 ? 'up' : roi < 10 ? 'down' : 'stable';

    return {
      id: dbProject.id.toString(),
      name: dbProject.project_name,
      domain: dbProject.main_url,
      investment: latestMetrics?.invested_amount || 0,
      revenue: latestMetrics?.billed_amount || 0,
      roas: latestMetrics?.roas || 0,
      roi: latestMetrics?.roi || 0,
      grossProfit: latestMetrics?.gross_profit || 0,
      netProfit: latestMetrics?.net_profit || 0,
      trend,
      campaigns: {
        green: greenCampaigns,
        yellow: yellowCampaigns,
        red: redCampaigns
      },
      status: (dbProject.status === 'Active' ? 'active' : 'paused') as 'active' | 'paused' | 'completed',
      manager: 'Felipe Silva', // Default manager
      description: `Projeto ${dbProject.project_name} - ${dbProject.main_url}`,
      revshare: dbProject.revshare,
      gamNetworkCode: dbProject.gam_network_code,
      project_type: dbProject.project_type || 'GAM'
    };
  }

  // Convert database campaign to UI campaign format
  private convertDatabaseCampaign(dbCampaign: DatabaseCampaign, metrics?: DatabaseDailyCampaignMetrics[]): Campaign {
    const latestMetrics = metrics?.[0]; // Assuming metrics are ordered by date desc
    
    // Determine performance based on ROAS
    let performance: 'excellent' | 'good' | 'average' | 'poor' = 'average';
    if (latestMetrics?.roas) {
      if (latestMetrics.roas >= 180) performance = 'excellent';
      else if (latestMetrics.roas >= 130) performance = 'good';
      else if (latestMetrics.roas >= 100) performance = 'average';
      else performance = 'poor';
    }

    return {
      id: dbCampaign.id.toString(),
      name: dbCampaign.campaign_name,
      projectId: dbCampaign.project_id.toString(),
      status: dbCampaign.status === 'Active' ? 'active' : 'paused',
      performance,
      investment: latestMetrics?.spend || 0,
      revenue: latestMetrics?.revenue || 0,
      roas: latestMetrics?.roas || 0,
      impressions: latestMetrics?.impressions || 0,
      clicks: latestMetrics?.clicks || 0,
      ctr: latestMetrics?.ctr || 0,
      startDate: dbCampaign.start_date,
      // Novos campos extraídos do banco
      googleAdsCampaignId: dbCampaign.google_ads_campaign_id || undefined,
      extractedUrl: (dbCampaign as any).extracted_url || undefined,
      extractedDomain: (dbCampaign as any).extracted_domain || undefined,
      customGoal: (dbCampaign as any).custom_goal || undefined,
      // UTM campaign será obtido via join com campaign_utm_mapping
      utmCampaignValue: undefined // TODO: implementar join
    };
  }

  // Convert database metrics to UI metrics format
  private convertDatabaseMetrics(dbMetrics: DatabaseDailyProjectMetrics): DailyMetrics {
    return {
      date: dbMetrics.date,
      investment: dbMetrics.invested_amount,
      revenue: dbMetrics.billed_amount,
      profit: dbMetrics.gross_profit,
      roas: dbMetrics.roas,
      roi: dbMetrics.roi,
      impressions: dbMetrics.page_views,
      clicks: Math.floor(dbMetrics.page_views * (dbMetrics.ctr / 100)), // Calculate clicks from CTR
      ctr: dbMetrics.ctr,
      conversions: Math.floor(dbMetrics.page_views * 0.02), // Assuming 2% conversion rate
      ecpm: dbMetrics.ecpm,
      cpc: dbMetrics.cpc,
      viewability: dbMetrics.viewability,
      pmr: dbMetrics.pmr,
      rps: dbMetrics.rps
    };
  }

  // Fetch projects from Supabase with real metrics
  // 🚀 OPTIMIZED VERSION: Using Supabase RPC for aggregations
  async getProjects(filters?: {
    date?: string;
    endDate?: string;
    projectId?: string;
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
    userProjectIds?: number[]; // IDs dos projetos permitidos ao usuário (OPERATOR)
    userCampaignIds?: string[]; // Google Ads campaign IDs permitidos ao usuário (OPERATOR)
  }): Promise<Project[]> {
    try {
      // Debug: Force current server date for 'today' period
      if (filters?.period === 'today') {
        const currentDate = await this.getCurrentServerDate();
        filters = { ...filters, date: currentDate };
      }

      // Calculate date range for RPC
      let startDate = filters?.date || await this.getCurrentServerDate();
      let endDate = filters?.endDate || startDate;

      if (filters?.period === '7d' && filters?.date) {
        const endDateObj = new Date(filters.date);
        const startDateObj = new Date(endDateObj);
        startDateObj.setDate(startDateObj.getDate() - 6);
        startDate = startDateObj.toISOString().split('T')[0];
        endDate = filters.date;
      } else if (filters?.period === '30d' && filters?.date) {
        const endDateObj = new Date(filters.date);
        const startDateObj = new Date(endDateObj);
        startDateObj.setDate(startDateObj.getDate() - 29);
        startDate = startDateObj.toISOString().split('T')[0];
        endDate = filters.date;
      }

      // Determine project ID filter
      const projectIdFilter = (filters?.projectId && filters.projectId !== 'all')
        ? parseInt(filters.projectId)
        : null;

      // 🚀 Call RPC function instead of multiple queries
      const { data: projectsSummary, error: rpcError } = await supabase.rpc('get_projects_summary', {
        p_start_date: startDate,
        p_end_date: endDate,
        p_project_id: projectIdFilter
      });

      if (rpcError) {
        console.error('Error calling get_projects_summary RPC:', rpcError);
        throw rpcError;
      }

      if (!projectsSummary || projectsSummary.length === 0) {
        console.log('No projects returned from RPC');
        return [];
      }

      console.log(`RPC returned ${projectsSummary.length} projects with aggregated metrics`);

      // Apply user project filter for OPERATORS (if not already filtered by RPC)
      let filteredProjects = projectsSummary;
      if (filters?.userProjectIds && filters.userProjectIds.length > 0) {
        filteredProjects = projectsSummary.filter(p =>
          filters.userProjectIds!.includes(p.id)
        );
      }

      // Apply user campaign filter if needed
      // For campaign-level filtering, we need to re-fetch with campaign filters
      if (filters?.userCampaignIds && filters.userCampaignIds.length > 0) {
        // This is a more complex case - for now, we'll filter projects that have at least one allowed campaign
        const projectsWithAllowedCampaigns = await Promise.all(
          filteredProjects.map(async (project) => {
            const { data: campaigns } = await supabase
              .from('campaigns')
              .select('campaign_id')
              .eq('project_id', project.id);

            const hasAllowedCampaign = (campaigns || []).some(c =>
              filters.userCampaignIds!.includes(c.campaign_id)
            );

            return hasAllowedCampaign ? project : null;
          })
        );

        filteredProjects = projectsWithAllowedCampaigns.filter(p => p !== null);
      }

      // Transform RPC results to Project format with additional calculations
      const projectsWithMetrics = await Promise.all(
        filteredProjects.map(async (project) => {
          const totalSpend = Number(project.total_spend) || 0;
          const totalRevenue = Number(project.total_revenue) || 0;
          const totalProfit = totalRevenue - totalSpend;
          const roas = totalSpend > 0 ? (totalRevenue / totalSpend) * 100 : 0;
          const roi = totalSpend > 0 ? (totalProfit / totalSpend) * 100 : 0;

          // Get campaign info for status breakdown
          const campaignCount = project.campaign_count || 0;
          const activeCampaigns = project.active_campaigns || 0;
          const pausedCampaigns = project.paused_campaigns || 0;

          // Generate performance distribution (simplified estimation)
          const greenCampaigns = Math.floor(campaignCount * 0.6);
          const yellowCampaigns = Math.floor(campaignCount * 0.3);
          const redCampaigns = campaignCount - greenCampaigns - yellowCampaigns;

          // Determine trend based on ROI
          const trend: 'up' | 'down' | 'stable' =
            roi > 50 ? 'up' : roi < 10 ? 'down' : 'stable';

          // Calculate net profit with operational costs
          let netProfitCalculation;
          try {
            // Get tax rate for the specific period being calculated
            let currentTaxRate: number;
            if (startDate !== endDate && startDate.substring(0, 7) !== endDate.substring(0, 7)) {
              currentTaxRate = await taxHistoryService.getTaxRateForDateRange(startDate, endDate) / 100;
            } else {
              const currentMonth = startDate.substring(0, 7);
              currentTaxRate = await taxHistoryService.getCurrentTaxRate(currentMonth) / 100;
            }

            netProfitCalculation = await this.calculateProjectNetProfitWithOperationalCosts(
              totalRevenue,
              totalSpend,
              startDate,
              endDate,
              project.costs_division || false,
              currentTaxRate
            );
          } catch (error) {
            console.error('Error calculating net profit for project:', project.project_name, error);
            netProfitCalculation = {
              netProfit: totalProfit,
              operationalCostShare: 0,
              taxAmount: 0,
              grossProfit: totalProfit,
              netRevenue: totalRevenue,
              formula: `Fallback calculation: ${totalProfit.toFixed(2)}`
            };
          }

          console.log({
            projectId: project.id,
            projectName: project.project_name,
            spend: totalSpend,
            revenue: totalRevenue,
            campaignCount,
            activeCampaigns,
            pausedCampaigns,
            source: 'rpc_get_projects_summary'
          });

          return {
            id: project.id.toString(),
            name: project.project_name,
            domain: project.domain,
            investment: totalSpend,
            revenue: totalRevenue,
            roas: Math.round(roas),
            roi: Math.round(roi),
            grossProfit: totalProfit,
            netProfit: netProfitCalculation.netProfit,
            trend,
            campaigns: {
              green: greenCampaigns,
              yellow: yellowCampaigns,
              red: redCampaigns
            },
            status: (project.status === 'Active' ? 'active' : 'paused') as 'active' | 'paused' | 'completed',
            manager: 'Felipe Silva',
            description: `Projeto ${project.project_name} - ${project.domain}`,
            costs_division: project.costs_division,
            project_type: project.project_type,
            visible: true
          };
        })
      );

      return projectsWithMetrics;
    } catch (error) {
      console.error('Error fetching projects with RPC:', error);
      // Fallback to old method if RPC fails
      console.warn('⚠️ RPC failed, falling back to old method');
      return this.getProjectsOld(filters);
    }
  }

  // 🔄 OLD VERSION: Kept as fallback (makes 4+ queries per project)
  private async getProjectsOld(filters?: {
    date?: string;
    endDate?: string;
    projectId?: string;
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
    userProjectIds?: number[];
    userCampaignIds?: string[];
  }): Promise<Project[]> {
    try {
      // Debug: Force current server date for 'today' period
      if (filters?.period === 'today') {
        const currentDate = await this.getCurrentServerDate();
        filters = { ...filters, date: currentDate };
      }

      // Build project query with filters - only select needed columns
      let projectsQuery = supabase
        .from('projects')
        .select('*')
        .eq('visible', true) // Filter only visible projects
        .order('created_at', { ascending: false });

      // Apply project filter if specified
      if (filters?.projectId && filters.projectId !== 'all') {
        projectsQuery = projectsQuery.eq('id', filters.projectId);
      }

      // Apply user project filter for OPERATORS
      if (filters?.userProjectIds && filters.userProjectIds.length > 0) {
        projectsQuery = projectsQuery.in('id', filters.userProjectIds);
      }

      const { data: projects, error: projectsError } = await projectsQuery;

      if (projectsError) throw projectsError;

      // Debug: Check if project_type is being returned
      if (projects && projects.length > 0) {
        console.log({
          id: projects[0].id,
          project_name: projects[0].project_name,
          project_type: projects[0].project_type,
          allFields: Object.keys(projects[0])
        });
      }

      // Get aggregated metrics for each project using daily_campaign_metrics
      const projectsWithMetrics = await Promise.all(
        (projects || []).map(async (project) => {

          // Step 1: Get campaign IDs first, then query daily_campaign_metrics
          const { data: projectCampaignsForSpend } = await supabase
            .from('campaigns')
            .select('*')
            .eq('project_id', project.id);

          // IMPORTANTE: usar campaign_id (string do Google Ads) não id (PK da tabela)
          let campaignIdsForSpend = (projectCampaignsForSpend || []).map(c => c.campaign_id).filter(Boolean);

          console.log({
            totalCampaigns: (projectCampaignsForSpend || []).length,
            campaignIds: campaignIdsForSpend,
            hasUserFilter: !!(filters?.userCampaignIds && filters.userCampaignIds.length > 0),
            userCampaignIds: filters?.userCampaignIds
          });

          // Apply user campaign filter if specified
          // userCampaignIds agora contém campaign_id (Google Ads IDs) diretamente
          if (filters?.userCampaignIds && filters.userCampaignIds.length > 0) {
            const beforeFilter = campaignIdsForSpend.length;
            // Filtrar apenas os campaign_ids que estão na lista permitida
            campaignIdsForSpend = campaignIdsForSpend.filter(cid =>
              filters.userCampaignIds!.includes(cid)
            );

            console.log({
              before: beforeFilter,
              after: campaignIdsForSpend.length,
              allowedCampaignIds: filters.userCampaignIds,
              filteredCampaignIds: campaignIdsForSpend
            });
          }

          let totalSpend = 0;
          console.log({
            campaignIdsCount: campaignIdsForSpend.length,
            campaignIds: campaignIdsForSpend
          });

          if (campaignIdsForSpend.length > 0) {
            let spendQuery = supabase
              .from('daily_campaign_metrics')
              .select('*')
              .in('campaign_id', campaignIdsForSpend)
              .limit(50000); // Aumentar limite para evitar perda de dados

            // Apply date filters for spend
            if (filters?.period === 'today' && filters?.date) {
              spendQuery = spendQuery.eq('date', filters.date);
            } else if (filters?.period === 'custom' && filters?.date) {
              spendQuery = spendQuery.eq('date', filters.date);
            } else if (filters?.period === '7d' && filters?.date) {
              const endDate = new Date(filters.date);
              const startDate = new Date(endDate);
              startDate.setDate(startDate.getDate() - 6);
              spendQuery = spendQuery
                .gte('date', startDate.toISOString().split('T')[0])
                .lte('date', filters.date);
            } else if (filters?.period === '30d' && filters?.date) {
              const endDate = new Date(filters.date);
              const startDate = new Date(endDate);
              startDate.setDate(startDate.getDate() - 29);
              spendQuery = spendQuery
                .gte('date', startDate.toISOString().split('T')[0])
                .lte('date', filters.date);
            } else if (filters?.period === 'range' && filters?.date && filters?.endDate) {
              spendQuery = spendQuery
                .gte('date', filters.date)
                .lte('date', filters.endDate);
            }

            const { data: spendData, error: spendError } = await spendQuery;
            if (spendError) {
              console.error(`Error fetching spend for project ${project.id}:`, spendError);
            }

            totalSpend = (spendData || []).reduce((sum, item) => sum + (Number(item.spend) || 0), 0);
            console.log({
              period: filters?.period,
              dateRange: filters?.period === 'range' ? `${filters.date} to ${filters.endDate}` : filters?.date,
              recordsFound: spendData?.length || 0,
              totalSpend
            });
          }

          // Step 2: Use the same campaign IDs for revenue query
          const campaignIds = campaignIdsForSpend;

          // UPDATED: Get revenue - use different sources based on project type
          let totalRevenue = 0;

          // 🚀 UNIFIED OPTIMIZATION: All projects use daily_project_metrics for total revenue

          let projectRevenueQuery = supabase
            .from('daily_project_metrics')
            .select('revenue_converted_revshare')
            .eq('project_id', project.id)
            .limit(50000); // Aumentar limite para evitar perda de dados

          // Apply date filters based on period
          if (filters?.period === 'today' && filters?.date) {
            projectRevenueQuery = projectRevenueQuery.eq('date', filters.date);
          } else if (filters?.period === 'custom' && filters?.date) {
            projectRevenueQuery = projectRevenueQuery.eq('date', filters.date);
          } else if (filters?.period === '7d' && filters?.date) {
            const endDate = new Date(filters.date);
            const startDate = new Date(endDate);
            startDate.setDate(startDate.getDate() - 6);
            projectRevenueQuery = projectRevenueQuery
              .gte('date', startDate.toISOString().split('T')[0])
              .lte('date', filters.date);
          } else if (filters?.period === '30d' && filters?.date) {
            const endDate = new Date(filters.date);
            const startDate = new Date(endDate);
            startDate.setDate(startDate.getDate() - 29);
            projectRevenueQuery = projectRevenueQuery
              .gte('date', startDate.toISOString().split('T')[0])
              .lte('date', filters.date);
          } else if (filters?.period === 'range' && filters?.date && filters?.endDate) {
            projectRevenueQuery = projectRevenueQuery
              .gte('date', filters.date)
              .lte('date', filters.endDate);
          }

          const { data: projectRevenueData, error: projectRevenueError } = await projectRevenueQuery;
          if (projectRevenueError) {
            console.error(`Error fetching project revenue for project ${project.id}:`, projectRevenueError);
          }

          totalRevenue = (projectRevenueData || []).reduce((sum, item) => {
            const revenueRevshare = Number(item.revenue_converted_revshare) || 0;
            return sum + revenueRevshare;
          }, 0);

          console.log({
            totalRevenue,
            records_count: projectRevenueData?.length || 0,
            date: filters?.date,
            period: filters?.period,
            source: 'daily_project_metrics_unified',
            project_type: project.project_type
          });

          console.log({
            period: filters?.period || 'all',
            date: filters?.date || 'none',
            campaignIds: campaignIds.length,
            spend: totalSpend,
            revenue: totalRevenue,
            campaignIdsArray: campaignIds
          });

          // Calculate derived metrics
          const totalProfit = totalRevenue - totalSpend;
          const roas = totalSpend > 0 ? (totalRevenue / totalSpend) * 100 : 0;
          const roi = totalSpend > 0 ? (totalProfit / totalSpend) * 100 : 0;

          // Get campaign count
          const { data: campaigns } = await supabase
            .from('campaigns')
            .select('id, status')
            .eq('project_id', project.id);

          // Apply user campaign filter to campaign count
          let filteredCampaigns = campaigns || [];
          if (filters?.userCampaignIds && filters.userCampaignIds.length > 0) {
            filteredCampaigns = filteredCampaigns.filter(c => filters.userCampaignIds!.includes(c.campaign_id));
          }

          const campaignCount = filteredCampaigns.length;
          const activeCampaigns = filteredCampaigns.filter(c =>
            c.status && ['Active', 'active', 'ENABLED'].includes(c.status)
          ).length;

          // Generate performance distribution
          const greenCampaigns = Math.floor(campaignCount * 0.6);
          const yellowCampaigns = Math.floor(campaignCount * 0.3);
          const redCampaigns = campaignCount - greenCampaigns - yellowCampaigns;

          // Determine trend based on ROI
          const trend: 'up' | 'down' | 'stable' =
            roi > 50 ? 'up' : roi < 10 ? 'down' : 'stable';

          // Calculate net profit with operational costs
          let netProfitCalculation;
          try {
            // Determine date range for calculations
            let startDate = filters?.date || await this.getCurrentServerDate();
            let endDate = filters?.endDate || startDate;

            if (filters?.period === '7d' && filters?.date) {
              const endDateObj = new Date(filters.date);
              const startDateObj = new Date(endDateObj);
              startDateObj.setDate(startDateObj.getDate() - 6);
              startDate = startDateObj.toISOString().split('T')[0];
              endDate = filters.date;
            } else if (filters?.period === '30d' && filters?.date) {
              const endDateObj = new Date(filters.date);
              const startDateObj = new Date(endDateObj);
              startDateObj.setDate(startDateObj.getDate() - 29);
              startDate = startDateObj.toISOString().split('T')[0];
              endDate = filters.date;
            }

            // Get tax rate for the specific period being calculated
            // If it's a range spanning multiple months, use weighted average
            let currentTaxRate: number;
            if (startDate !== endDate && startDate.substring(0, 7) !== endDate.substring(0, 7)) {
              // Multiple months: use weighted average tax rate
              currentTaxRate = await taxHistoryService.getTaxRateForDateRange(startDate, endDate) / 100;
            } else {
              // Single month: use that month's tax rate
              const currentMonth = startDate.substring(0, 7); // YYYY-MM format
              currentTaxRate = await taxHistoryService.getCurrentTaxRate(currentMonth) / 100;
            }

            netProfitCalculation = await this.calculateProjectNetProfitWithOperationalCosts(
              totalRevenue, // Already revenue after revshare
              totalSpend,
              startDate,
              endDate,
              project.costs_division || false,
              currentTaxRate
            );
          } catch (error) {
            console.error('Error calculating net profit for project:', project.project_name, error);
            // Fallback to simple calculation
            netProfitCalculation = {
              netProfit: totalProfit,
              operationalCostShare: 0,
              taxAmount: 0,
              grossProfit: totalProfit,
              netRevenue: totalRevenue,
              formula: `Fallback calculation: ${totalProfit.toFixed(2)}`
            };
          }

          return {
            id: project.id.toString(),
            name: project.project_name,
            domain: project.domain || project.main_url,
            investment: totalSpend,
            revenue: totalRevenue,
            roas: Math.round(roas),
            roi: Math.round(roi),
            grossProfit: totalProfit,
            netProfit: netProfitCalculation.netProfit,
            trend,
            campaigns: {
              green: greenCampaigns,
              yellow: yellowCampaigns,
              red: redCampaigns
            },
            status: (project.status === 'Active' ? 'active' : 'paused') as 'active' | 'paused' | 'completed',
            manager: 'Felipe Silva', // Default manager
            description: `Projeto ${project.project_name} - ${project.domain || project.main_url}`,
            costs_division: project.costs_division,
            project_type: project.project_type,
            visible: project.visible ?? true // Frontend-only filter flag
          };
        })
      );

      return projectsWithMetrics;
    } catch (error) {
      console.error('Error fetching projects (old method):', error);
      return [];
    }
  }

  // Get detailed project data for settings page
  async getProjectsDetailed(): Promise<any[]> {
    try {
      const { data: projects, error: projectsError } = await supabase
        .from('projects')
        .select('*')
        .eq('visible', true) // Filter only visible projects
        .order('created_at', { ascending: false });

      if (projectsError) throw projectsError;

      // Get detailed project info with campaign counts and metrics
      const detailedProjects = await Promise.all(
        (projects || []).map(async (project) => {
          // Get campaign count
          const { data: campaigns } = await supabase
            .from('campaigns')
            .select('id, status')
            .eq('project_id', project.id);

          const campaignCount = campaigns?.length || 0;

          // UPDATED: Get aggregated metrics using net revenue (after revshare) from daily_campaign_metrics
          const { data: campaignData } = await supabase
            .from('daily_campaign_metrics')
            .select('spend, revenue_converted_revshare, campaign_id')
            .in('campaign_id', (campaigns || []).map(c => c.campaign_id).filter(Boolean));

          const totalSpend = (campaignData || []).reduce((sum, c) => sum + (Number(c.spend) || 0), 0);
          const totalRevenue = (campaignData || []).reduce((sum, c) => sum + (Number(c.revenue_converted_revshare) || 0), 0);

          // Format last sync dates
          const formatLastSync = (date: string | null) => {
            if (!date) return 'Nunca';
            const syncDate = new Date(date);
            const now = new Date();
            const diffInMinutes = Math.floor((now.getTime() - syncDate.getTime()) / (1000 * 60));
            
            if (diffInMinutes < 1) return 'Agora mesmo';
            if (diffInMinutes < 60) return `há ${diffInMinutes}min`;
            if (diffInMinutes < 1440) return `há ${Math.floor(diffInMinutes / 60)}h`;
            return `há ${Math.floor(diffInMinutes / 1440)} dias`;
          };

          return {
            id: project.id.toString(),
            name: project.project_name,
            domain: project.main_url,
            status: project.status === 'Active' ? 'active' : 'paused',
            campaignsCount: campaignCount,
            createdDate: new Date(project.created_at).toLocaleDateString('pt-BR'),
            lastSync: formatLastSync(project.last_google_ads_sync || project.last_gam_sync),
            totalSpend: totalSpend,
            totalRevenue,
            integrations: {
              googleAds: {
                connected: project.google_ads_status === 'connected',
                account: 'Felipe Ltda',
                id: project.google_ads_customer_id || '977-272-9198',
                status: project.google_ads_status || 'disconnected'
              },
              gam: {
                connected: project.gam_status === 'connected',
                account: project.project_name,
                networkCode: project.gam_network_code,
                status: project.gam_status || 'disconnected'
              },
              adxDiscount: 10 // Default value, could be stored in database
            },
            // Raw project data for editing
            rawProject: project,
            project_type: project.project_type,
            visible: project.visible ?? true // Frontend-only filter flag
          };
        })
      );

      return detailedProjects;
    } catch (error) {
      console.error('Error fetching detailed projects:', error);
      return [];
    }
  }

  // Fetch campaigns from Supabase (novo método que usa a view com revenue)
  async getCampaigns(filters?: {
    projectId?: string;
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
    date?: string;
    endDate?: string;
  }): Promise<Campaign[]> {
    try {
      return await this.getCampaignsWithRevenue(filters);
    } catch (error) {
      console.error('Error fetching campaigns:', error);
      return [];
    }
  }
  
  // Método legacy para campanhas (manter para compatibilidade)
  async getCampaignsLegacy(): Promise<Campaign[]> {
    try {
      const { data: campaigns, error: campaignsError } = await supabase
        .from('campaigns')
        .select('*')
        .order('created_at', { ascending: false });

      if (campaignsError) throw campaignsError;

      // Fetch recent metrics for each campaign
      const campaignsWithMetrics = await Promise.all(
        (campaigns || []).map(async (campaign) => {
          const { data: metrics } = await supabase
            .from('daily_campaign_metrics')
            .select('*')
            .eq('campaign_id', campaign.id)
            .order('date', { ascending: false })
            .limit(1);

          return this.convertDatabaseCampaign(campaign, metrics || []);
        })
      );

      return campaignsWithMetrics;
    } catch (error) {
      console.error('Error fetching campaigns:', error);
      return [];
    }
  }

  // Fetch daily metrics from Supabase with real campaign data
  async getDailyMetrics(filters?: {
    projectId?: string;
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
    date?: string;
    endDate?: string;
    days?: number;
  }): Promise<DailyMetrics[]> {
    try {
      const { projectId, period = '7d', date, endDate: filterEndDate, days = 7 } = filters || {};
      
      // Get date range
      let endDate = date || new Date().toISOString().split('T')[0];
      const startDate = new Date();
      
      if (period === 'today' || period === 'yesterday') {
        // Para HOJE ou ONTEM, usar método específico que filtra apenas o dia específico
        let targetDate: string;
        if (period === 'yesterday') {
          const serverDate = await this.getCurrentServerDate();
          const serverDateObj = new Date(serverDate + 'T00:00:00-03:00'); // São Paulo timezone
          const yesterdayObj = new Date(serverDateObj);
          yesterdayObj.setDate(yesterdayObj.getDate() - 1);
          targetDate = yesterdayObj.toISOString().split('T')[0];
        } else {
          targetDate = date || await this.getCurrentServerDate();
        }
        return this.getTodayMetrics(projectId, targetDate);
      } else if (period === 'custom' && date) {
        // Para DATA ESPECÍFICA, usar método específico que filtra apenas aquele dia
        return this.getTodayMetrics(projectId, date);
      } else if (period === 'range' && date && filterEndDate) {
        // Para RANGE DE DATAS, usar intervalo específico
        endDate = filterEndDate;
        startDate.setTime(new Date(date).getTime());
      } else if (period === '7d') {
        startDate.setDate(startDate.getDate() - 7);
      } else if (period === '30d') {
        startDate.setDate(startDate.getDate() - 30);
      } else {
        startDate.setDate(startDate.getDate() - days);
      }

      const startDateStr = startDate.toISOString().split('T')[0];

      // 🚀 CACHE INTELIGENTE para daily metrics com validação híbrida
      const cacheKey = `daily_metrics_${JSON.stringify({projectId, period, date, endDate: filterEndDate, days})}`;
      const cacheTimestamp = localStorage.getItem(`${cacheKey}_timestamp`);
      const cachedData = localStorage.getItem(cacheKey);

      if (cachedData && cacheTimestamp) {
        const cacheAge = Date.now() - parseInt(cacheTimestamp);
        const cacheValidTime = 4 * 60 * 1000; // 4 minutos para daily metrics

        // Validar cache usando ambas as tabelas (project + campaign metrics)
        const dateRange = { startDate: startDateStr, endDate };

        // Check both tables since getDailyMetrics uses both
        const [projectCacheValid, campaignCacheValid] = await Promise.all([
          this.isCacheValid(cacheKey, parseInt(cacheTimestamp), date, 'daily_project_metrics'),
          this.isCampaignCacheValid(cacheKey, parseInt(cacheTimestamp), dateRange)
        ]);

        if (cacheAge < cacheValidTime && projectCacheValid && campaignCacheValid) {
          console.log({
            cacheKey,
            cacheAge: `${Math.round(cacheAge / 1000)}s`,
            dateRange
          });
          return JSON.parse(cachedData);
        } else if (!projectCacheValid || !campaignCacheValid) {
          console.log({
            projectCacheValid,
            campaignCacheValid
          });
        }
      }

      // 🚀 RPC OPTIMIZATION: Tentar usar get_daily_metrics_aggregated primeiro
      const rpcProjectId = projectId && projectId !== 'all' ? parseInt(projectId) : null;

      console.log('🚀 getDailyMetrics RPC call:', { startDateStr, endDate, rpcProjectId });

      try {
        const { data: rpcData, error: rpcError } = await supabase.rpc('get_daily_metrics_aggregated', {
          p_start_date: startDateStr,
          p_end_date: endDate,
          p_project_id: rpcProjectId
        });

        if (!rpcError && rpcData && rpcData.length > 0) {
          console.log('✅ getDailyMetrics RPC success:', { records: rpcData.length });

          const result: DailyMetrics[] = rpcData.map((row: any) => ({
            date: row.metric_date,
            investment: Number(row.investment) || 0,
            revenue: Number(row.revenue) || 0,
            profit: Number(row.profit) || 0,
            roas: Number(row.roas) || 0,
            roi: Number(row.roi) || 0,
            impressions: Number(row.impressions) || 0,
            clicks: Number(row.clicks) || 0,
            ctr: Number(row.ctr) || 0,
            conversions: Number(row.conversions) || 0,
            ecpm: 0,
            cpc: Number(row.cpc) || 0,
            viewability: 0,
            pmr: 0,
            rps: 0
          })).slice(0, days);

          // 💾 SALVAR NO CACHE
          localStorage.setItem(cacheKey, JSON.stringify(result));
          localStorage.setItem(`${cacheKey}_timestamp`, Date.now().toString());

          return result;
        } else if (rpcError) {
          console.warn('⚠️ getDailyMetrics RPC failed, using fallback:', rpcError.message);
        }
      } catch (rpcException) {
        console.warn('⚠️ getDailyMetrics RPC exception, using fallback:', rpcException);
      }

      // 🔄 FALLBACK: Método antigo (2 queries separadas)
      console.log('🔄 getDailyMetrics usando fallback');

      // Step 1: Get revenue from daily_project_metrics (much more efficient)
      let revenueQuery = supabase
        .from('daily_project_metrics')
        .select('date, revenue_converted_revshare, project_id')
        .gte('date', startDateStr)
        .lte('date', endDate)
        .limit(50000);

      if (projectId && projectId !== 'all') {
        revenueQuery = revenueQuery.eq('project_id', parseInt(projectId));
      }

      const { data: revenueMetrics, error: revenueError } = await revenueQuery;
      if (revenueError) throw revenueError;

      // Step 2: Get spend from daily_campaign_metrics (only necessary fields)
      let spendQuery = supabase
        .from('daily_campaign_metrics')
        .select(`
          date,
          spend,
          clicks,
          impressions,
          conversions,
          campaigns!inner(project_id)
        `)
        .gte('date', startDateStr)
        .lte('date', endDate)
        .limit(50000);

      if (projectId && projectId !== 'all') {
        spendQuery = spendQuery.eq('campaigns.project_id', parseInt(projectId));
      }

      const { data: campaignMetrics, error: campaignError } = await spendQuery;
      if (campaignError) throw campaignError;

      console.log({
        revenueRecords: revenueMetrics.length,
        spendRecords: campaignMetrics.length
      });

      // Group by date and aggregate
      const dailyData = new Map<string, DailyMetrics>();

      // Initialize dates with zero values
      for (let d = new Date(startDate); d <= new Date(endDate); d.setDate(d.getDate() + 1)) {
        const dateStr = d.toISOString().split('T')[0];
        dailyData.set(dateStr, {
          date: dateStr,
          investment: 0,
          revenue: 0,
          profit: 0,
          roas: 0,
          roi: 0,
          impressions: 0,
          clicks: 0,
          ctr: 0,
          conversions: 0,
          ecpm: 0,
          cpc: 0,
          viewability: 0,
          pmr: 0,
          rps: 0
        });
      }

      // Aggregate campaign metrics by date
      (campaignMetrics || []).forEach(metric => {
        const existing = dailyData.get(metric.date) || dailyData.set(metric.date, {
          date: metric.date,
          investment: 0,
          revenue: 0,
          profit: 0,
          roas: 0,
          roi: 0,
          impressions: 0,
          clicks: 0,
          ctr: 0,
          conversions: 0,
          ecpm: 0,
          cpc: 0,
          viewability: 0,
          pmr: 0,
          rps: 0
        }).get(metric.date)!;

        existing.investment += Number(metric.spend) || 0;
        existing.clicks += Number(metric.clicks) || 0;
        existing.impressions += Number(metric.impressions) || 0;
        existing.conversions += Number(metric.conversions) || 0;
        existing.cpc += Number(metric.cpc) || 0;
      });

      // 🚀 OTIMIZAÇÃO: Add revenue data from daily_project_metrics (already includes revshare discount)
      (revenueMetrics || []).forEach(revenue => {
        const existing = dailyData.get(revenue.date);
        if (existing) {
          const revenueAfterRevshare = Number(revenue.revenue_converted_revshare) || 0;

          // Use optimized revenue (already includes revshare discount)
          existing.revenue += revenueAfterRevshare;
        }
      });

      // Calculate derived metrics
      dailyData.forEach(daily => {
        daily.profit = daily.revenue - daily.investment;
        daily.roas = daily.investment > 0 ? (daily.revenue / daily.investment) * 100 : 0;
        daily.roi = daily.investment > 0 ? (daily.profit / daily.investment) * 100 : 0;
        daily.ctr = daily.impressions > 0 ? (daily.clicks / daily.impressions) * 100 : 0;
        daily.cpc = daily.clicks > 0 ? daily.investment / daily.clicks : 0;
      });

      const result = Array.from(dailyData.values())
        .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
        .slice(0, days);

      // 💾 SALVAR NO CACHE para próximas consultas
      const currentTimestamp = Date.now().toString();
      localStorage.setItem(cacheKey, JSON.stringify(result));
      localStorage.setItem(`${cacheKey}_timestamp`, currentTimestamp);

      return result;

    } catch (error) {
      console.error('Error fetching daily metrics:', error);
      return [];
    }
  }


  // Get real-time dashboard data with filters
  async getDashboardData(filters: {
    date?: string;
    endDate?: string;
    projectId?: string;
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
  }): Promise<{
    totalSpend: number;
    totalRevenue: number;
    totalRevenueAfterRevshare?: number;
    totalProfit: number;
    generalRoas: number;
    finalRoi: number;
    activeCampaigns: number;
    pausedCampaigns: number;
    trendsPercentage: {
      investment: number;
      revenue: number;
      profit: number;
      roas: number;
      roi: number;
    };
  }> {
    try {
      const { projectId, period, date } = filters;

      console.log('🔍 getDashboardData INICIANDO:', {
        period,
        date,
        projectId,
        projectIdType: typeof projectId,
        allFilters: filters
      });

      // 🚀 CACHE INTELIGENTE COM INVALIDAÇÃO: Reduz egress mas mantém dados atualizados
      const cacheKey = `dashboard_${JSON.stringify({projectId, period, date})}`;
      const cacheTimestamp = localStorage.getItem(`${cacheKey}_timestamp`);
      const cachedData = localStorage.getItem(cacheKey);
      const lastDataUpdate = localStorage.getItem('lastDataUpdate');

      // 📊 METRICS: Track cache performance
      const cacheHitMetric = localStorage.getItem('cache_hits') || '0';
      const cacheMissMetric = localStorage.getItem('cache_misses') || '0';

      if (cachedData && cacheTimestamp) {
        const cacheAge = Date.now() - parseInt(cacheTimestamp);
        const cacheValidTime = (period === 'today' || period === 'yesterday') ? 2 * 60 * 1000 : 5 * 60 * 1000; // 2min para today/yesterday, 5min para outros

        // Se há timestamp de atualização de dados e é mais recente que o cache, invalidar
        const dataWasUpdated = lastDataUpdate && parseInt(lastDataUpdate) > parseInt(cacheTimestamp);

        // 🎯 NEW: Check database updated_at for today data
        if ((period === 'today' || period === 'yesterday') && date) {
          const isCacheStillValid = await this.isCacheValid(cacheKey, parseInt(cacheTimestamp), date);
          if (cacheAge < cacheValidTime && !dataWasUpdated && isCacheStillValid) {
            // 📊 METRICS: Increment cache hit
            localStorage.setItem('cache_hits', String(parseInt(cacheHitMetric) + 1));
            console.log({
              cacheKey,
              cacheAge: `${Math.round(cacheAge / 1000)}s`,
              validFor: `${Math.round((cacheValidTime - cacheAge) / 1000)}s mais`,
              cacheHitRate: `${((parseInt(cacheHitMetric) + 1) / (parseInt(cacheHitMetric) + parseInt(cacheMissMetric) + 1) * 100).toFixed(1)}%`
            });
            return JSON.parse(cachedData);
          } else if (!isCacheStillValid) {
          }
        } else {
          // For other periods, use time-based cache
          if (cacheAge < cacheValidTime && !dataWasUpdated) {
            // 📊 METRICS: Increment cache hit
            localStorage.setItem('cache_hits', String(parseInt(cacheHitMetric) + 1));
            console.log({
              cacheKey,
              cacheAge: `${Math.round(cacheAge / 1000)}s`,
              validFor: `${Math.round((cacheValidTime - cacheAge) / 1000)}s mais`,
              cacheHitRate: `${((parseInt(cacheHitMetric) + 1) / (parseInt(cacheHitMetric) + parseInt(cacheMissMetric) + 1) * 100).toFixed(1)}%`
            });
            return JSON.parse(cachedData);
          } else if (dataWasUpdated) {
          }
        }
      }
      
      // 🚀 RPC OPTIMIZATION: Tentar usar get_dashboard_totals primeiro
      try {
        // Calcular datas baseado no período
        let rpcStartDate: string;
        let rpcEndDate: string;
        
        if (period === 'today') {
          const serverDate = await this.getCurrentServerDate();
          rpcStartDate = serverDate;
          rpcEndDate = serverDate;
        } else if (period === 'yesterday') {
          const serverDate = await this.getCurrentServerDate();
          const serverDateObj = new Date(serverDate + 'T00:00:00-03:00');
          const yesterdayObj = new Date(serverDateObj);
          yesterdayObj.setDate(yesterdayObj.getDate() - 1);
          rpcStartDate = yesterdayObj.toISOString().split('T')[0];
          rpcEndDate = rpcStartDate;
        } else if (period === 'custom' && date) {
          rpcStartDate = date;
          rpcEndDate = date;
        } else if (period === 'range' && date && filters.endDate) {
          rpcStartDate = date;
          rpcEndDate = filters.endDate;
        } else if (period === '7d') {
          const today = new Date();
          today.setDate(today.getDate() - 7);
          rpcStartDate = today.toISOString().split('T')[0];
          rpcEndDate = new Date().toISOString().split('T')[0];
        } else if (period === '30d') {
          const today = new Date();
          today.setDate(today.getDate() - 30);
          rpcStartDate = today.toISOString().split('T')[0];
          rpcEndDate = new Date().toISOString().split('T')[0];
        } else {
          // Default: últimos 30 dias
          const today = new Date();
          today.setDate(today.getDate() - 30);
          rpcStartDate = today.toISOString().split('T')[0];
          rpcEndDate = new Date().toISOString().split('T')[0];
        }

        const rpcProjectId = projectId && projectId !== 'all' ? parseInt(projectId) : null;

        console.log('🚀 getDashboardData RPC call:', { rpcStartDate, rpcEndDate, rpcProjectId, period });

        const { data: rpcData, error: rpcError } = await supabase.rpc('get_dashboard_totals', {
          p_start_date: rpcStartDate,
          p_end_date: rpcEndDate,
          p_project_id: rpcProjectId
        });

        if (!rpcError && rpcData && rpcData.length > 0) {
          const rpc = rpcData[0];
          
          // 🚀 Buscar tendências com get_period_comparison
          let trendsPercentage = { investment: 0, revenue: 0, profit: 0, roas: 0, roi: 0 };
          try {
            const { data: trendsData, error: trendsError } = await supabase.rpc('get_period_comparison', {
              p_current_start: rpcStartDate,
              p_current_end: rpcEndDate,
              p_project_id: rpcProjectId
            });

            if (!trendsError && trendsData && trendsData.length > 0) {
              const t = trendsData[0];
              trendsPercentage = {
                investment: Number(Number(t.trend_investment || 0).toFixed(1)),
                revenue: Number(Number(t.trend_revenue || 0).toFixed(1)),
                profit: Number(Number(t.trend_profit || 0).toFixed(1)),
                roas: Number(Number(t.trend_roas || 0).toFixed(1)),
                roi: Number(Number(t.trend_roi || 0).toFixed(1))
              };
              console.log('✅ Trends RPC success:', trendsPercentage);
            }
          } catch (trendsException) {
            console.warn('⚠️ Trends RPC failed:', trendsException);
          }

          const result = {
            totalSpend: Number(rpc.total_spend) || 0,
            totalRevenue: Number(rpc.total_revenue) || 0,
            totalRevenueAfterRevshare: Number(rpc.total_revenue) || 0,
            totalProfit: Number(rpc.total_profit) || 0,
            generalRoas: Math.floor(Number(rpc.general_roas) || 0),
            finalRoi: Math.floor(Number(rpc.final_roi) || 0),
            activeCampaigns: Number(rpc.active_campaigns) || 0,
            pausedCampaigns: Number(rpc.paused_campaigns) || 0,
            trendsPercentage
          };

          console.log('✅ getDashboardData RPC success:', result);

          // Salvar no cache
          localStorage.setItem(cacheKey, JSON.stringify(result));
          localStorage.setItem(`${cacheKey}_timestamp`, String(Date.now()));

          return result;
        } else if (rpcError) {
          console.warn('⚠️ getDashboardData RPC failed, using fallback:', rpcError.message);
        }
      } catch (rpcException) {
        console.warn('⚠️ getDashboardData RPC exception, using fallback:', rpcException);
      }

      // 🔄 FALLBACK: Método antigo (múltiplas queries)
      console.log('🔄 getDashboardData usando fallback (método antigo)');
      
      // SEMPRE usar métricas diárias quando period = 'today', 'yesterday' ou 'custom'
      if (period === 'today' || period === 'yesterday' || period === 'custom') {
        // Usar data do servidor para 'today', data específica para 'custom', ou calcular yesterday
        let targetDate: string;
        if (period === 'custom' && date) {
          targetDate = date;
        } else if (period === 'yesterday') {
          const serverDate = await this.getCurrentServerDate();
          const serverDateObj = new Date(serverDate + 'T00:00:00-03:00'); // São Paulo timezone
          const yesterdayObj = new Date(serverDateObj);
          yesterdayObj.setDate(yesterdayObj.getDate() - 1);
          targetDate = yesterdayObj.toISOString().split('T')[0];
        } else {
          targetDate = await this.getCurrentServerDate();
        }

        console.log({
          period,
          providedDate: date,
          isCustom: period === 'custom',
          isYesterday: period === 'yesterday',
          willUseProvidedDate: period === 'custom' && date,
          finalTargetDate: targetDate,
          today: new Date().toISOString().split('T')[0]
        });

        // 🚀 NOVA LÓGICA OTIMIZADA PARA SINGLE DAY: usar daily_project_metrics

        // DEBUG: Primeiro verificar que datas estão disponíveis na tabela (apenas em desenvolvimento)
        if (import.meta.env.DEV) {
          const { data: availableDates } = await supabase
            .from('daily_project_metrics')
            .select('date, revenue_converted_revshare')
            .order('date', { ascending: false })
            .limit(10);

          console.log({
            availableDates: availableDates?.map(d => ({ date: d.date, revenue: d.revenue_converted_revshare })) || [],
            totalRecords: availableDates?.length || 0,
            targetDateSearching: targetDate
          });
        }

        // 1. REVENUE: Consulta eficiente na daily_project_metrics para TODAY
        // 🚀 SELECT OTIMIZADO: Apenas campos necessários
        let revenueQuery = supabase
          .from('daily_project_metrics')
          .select('revenue_converted_revshare')
          .eq('date', targetDate)
          .limit(50000); // Aumentar limite para evitar perda de dados

        // Aplicar filtro de projeto se especificado
        if (projectId && projectId !== 'all') {
          revenueQuery = revenueQuery.eq('project_id', parseInt(projectId));
        } else {
        }

        const { data: revenueData, error: revenueError } = await revenueQuery;
        let todayTotalRevenueAfterRevshare = 0;

        console.log({
          targetDate,
          projectFilter: projectId,
          error: revenueError,
          dataLength: revenueData?.length || 0,
          hasData: !!revenueData,
          firstRecord: revenueData?.[0] || 'No records'
        });

        if (revenueError) {
          console.error('❌ Revenue query error:', revenueError);
        }

        if (!revenueError && revenueData) {
          todayTotalRevenueAfterRevshare = revenueData.reduce((sum, item) =>
            sum + (Number(item.revenue_converted_revshare) || 0), 0);

          console.log({
            targetDate,
            projectFilter: projectId,
            recordCount: revenueData.length,
            totalRevenueAfterRevshare: todayTotalRevenueAfterRevshare,
            allRecords: revenueData
          });
        } else {
          console.warn('⚠️ No revenue data found for TODAY mode:', {
            targetDate,
            projectFilter: projectId,
            hasError: !!revenueError,
            hasData: !!revenueData
          });
        }

        // 2. SPEND: Consulta na daily_campaign_metrics apenas para spend (TODAY)
        // 🚀 SELECT OTIMIZADO COM PAGINAÇÃO: Buscar TODOS os registros (não apenas 1000)
        let allSpendData: any[] = [];
        const pageSize = 1000;
        let page = 0;
        let hasMore = true;

        while (hasMore) {
          let spendQuery;

          if (projectId && projectId !== 'all') {
            // 🚀 CORREÇÃO BUG 400: Buscar campanhas do projeto primeiro, depois métricas
            // Supabase não aceita JOIN + range() corretamente, causando erro 400
            const { data: projectCampaigns } = await supabase
              .from('campaigns')
              .select('campaign_id')
              .eq('project_id', parseInt(projectId));

            if (!projectCampaigns || projectCampaigns.length === 0) {
              console.warn('⚠️ Nenhuma campanha encontrada para o projeto:', projectId);
              hasMore = false;
              break;
            }

            const campaignIds = projectCampaigns.map(c => c.campaign_id);

            spendQuery = supabase
              .from('daily_campaign_metrics')
              .select('spend')
              .eq('date', targetDate)
              .in('campaign_id', campaignIds)
              .range(page * pageSize, (page + 1) * pageSize - 1);
          } else {
            spendQuery = supabase
              .from('daily_campaign_metrics')
              .select('spend')
              .eq('date', targetDate)
              .range(page * pageSize, (page + 1) * pageSize - 1);
          }

          const { data: spendData, error: spendError } = await spendQuery;

          if (spendError) {
            console.error('❌ Erro ao buscar spend para TODAY (página ' + page + '):', spendError);
            break;
          }

          if (spendData && spendData.length > 0) {
            allSpendData.push(...spendData);
            page++;
            hasMore = spendData.length === pageSize;
          } else {
            hasMore = false;
          }
        }

        let todayTotalSpend = 0;

        if (allSpendData.length > 0) {
          // 🔍 DEBUGGING DETALHADO: Verificar se há duplicação
          const uniqueCampaignIds = [...new Set(allSpendData.map((d: any) => d.campaign_id))];
          const spendByCampaign = allSpendData.reduce((acc: any, item: any) => {
            const campaignId = item.campaign_id || 'unknown';
            if (!acc[campaignId]) {
              acc[campaignId] = { count: 0, total: 0 };
            }
            acc[campaignId].count++;
            acc[campaignId].total += Number(item.spend) || 0;
            return acc;
          }, {});

          todayTotalSpend = allSpendData.reduce((sum, item) => sum + (Number(item.spend) || 0), 0);

          console.log('✅ BUG CORRIGIDO - Paginação implementada:', {
            targetDate,
            projectFilter: projectId,
            totalPagesProcessed: page,
            recordCount: allSpendData.length,
            totalSpend: todayTotalSpend,
            note: 'Agora busca TODOS os registros, não apenas 1000!'
          });
        } else {
          console.warn('⚠️ Nenhum dado de spend encontrado para TODAY:', {
            targetDate,
            projectFilter: projectId
          });
        }

        // ✅ OTIMIZAÇÃO CONCLUÍDA: A lógica GAM antiga foi substituída pela consulta direta
        // em daily_project_metrics (muito mais eficiente em termos de egress)

        const totalProfit = todayTotalRevenueAfterRevshare - todayTotalSpend;

        console.log({
          totalSpend: todayTotalSpend,
          totalRevenueAfterRevshare: todayTotalRevenueAfterRevshare,
          totalProfit
        });

        const generalRoas = todayTotalSpend > 0 ? ((todayTotalRevenueAfterRevshare / todayTotalSpend) - 1) * 100 : 0;
        const finalRoi = todayTotalSpend > 0 ? (totalProfit / todayTotalSpend) * 100 : 0;
        
        // Get campaign counts separately (with project filter if needed)
        let campaignCountQuery = supabase
          .from('campaigns')
          .select('status');
        
        // Apply project filter if specified
        if (projectId && projectId !== 'all') {
          campaignCountQuery = campaignCountQuery.eq('project_id', parseInt(projectId));
        }
        
        const { data: allCampaigns } = await campaignCountQuery;
        
        const activeCampaigns = (allCampaigns || []).filter(c => 
          c.status && ['Active', 'active', 'ENABLED'].includes(c.status)
        ).length;
        
        const pausedCampaigns = (allCampaigns || []).filter(c => 
          c.status && ['Paused', 'paused', 'PAUSED'].includes(c.status)
        ).length;

        // Calculate trends for the specific day
        const trends = await this.calculateTrends(filters);

        // ✅ USAR VALORES OTIMIZADOS DE daily_project_metrics
        const finalTotalRevenue = todayTotalRevenueAfterRevshare;
        const finalTotalProfit = finalTotalRevenue - todayTotalSpend;
        const finalGeneralRoas = todayTotalSpend > 0 ? ((finalTotalRevenue / todayTotalSpend) - 1) * 100 : 0;
        const todayFinalRoi = todayTotalSpend > 0 ? ((finalTotalProfit / todayTotalSpend) - 1) * 100 : 0;

        console.log({
          finalTotalRevenue,
          finalTotalProfit,
          finalGeneralRoas,
          finalRoi: todayFinalRoi,
          optimization: '🚀 Dados vindos de daily_project_metrics!'
        });

        console.log('📊 getDashboardData - retornando para period=' + period + ':', {
          targetDate,
          projectFilter: projectId,
          todayTotalSpend,
          finalTotalRevenue,
          finalTotalProfit,
          activeCampaigns
        });

        return {
          totalSpend: todayTotalSpend,
          totalRevenue: finalTotalRevenue,
          totalRevenueAfterRevshare: finalTotalRevenue,
          totalProfit: finalTotalProfit,
          generalRoas: finalGeneralRoas,
          finalRoi: todayFinalRoi,
          activeCampaigns,
          pausedCampaigns,
          trendsPercentage: {
            investment: Number(trends.investment.toFixed(1)),
            revenue: Number(trends.revenue.toFixed(1)),
            profit: Number(trends.profit.toFixed(1)),
            roas: Number(trends.roas.toFixed(1)),
            roi: Number(trends.roi.toFixed(1))
          }
        };
      }
      
      // Para períodos agregados (7d, 30d, e range), usar a mesma lógica de filtro por data
      
      // Determinar intervalo de datas baseado no período
      let startDate: Date;
      let endDate: Date;
      
      if (period === 'range' && filters.date && filters.endDate) {
        // Para range, usar as datas específicas fornecidas
        startDate = new Date(filters.date);
        endDate = new Date(filters.endDate);
        console.log({
          startDate: startDate.toISOString(),
          endDate: endDate.toISOString(),
          startDateStr: startDate.toISOString().split('T')[0],
          endDateStr: endDate.toISOString().split('T')[0]
        });
      } else if (period === '7d') {
        endDate = date ? new Date(date) : new Date();
        startDate = new Date(endDate);
        startDate.setDate(startDate.getDate() - 6); // Últimos 7 dias incluindo hoje
      } else if (period === '30d') {
        endDate = date ? new Date(date) : new Date();
        startDate = new Date(endDate);
        startDate.setDate(startDate.getDate() - 29); // Últimos 30 dias incluindo hoje
      } else {
        // Fallback para 30 dias se period não for reconhecido
        endDate = date ? new Date(date) : new Date();
        startDate = new Date(endDate);
        startDate.setDate(startDate.getDate() - 29);
      }
      
      const startDateStr = startDate.toISOString().split('T')[0];
      const endDateStr = endDate.toISOString().split('T')[0];
      
      
      // 🚀 OTIMIZAÇÃO RANGE: Usar daily_project_metrics (consistente com TODAY)

      // 1. REVENUE: Consulta otimizada na daily_project_metrics para RANGE
      let revenueQuery = supabase
        .from('daily_project_metrics')
        .select('revenue_converted_revshare')
        .gte('date', startDateStr)
        .lte('date', endDateStr)
        .limit(50000); // Aumentar limite para evitar perda de dados em períodos longos

      if (projectId && projectId !== 'all') {
        revenueQuery = revenueQuery.eq('project_id', parseInt(projectId));
      } else {
      }

      // 2. SPEND: Consulta otimizada na daily_campaign_metrics para RANGE COM PAGINAÇÃO
      let spendData: any[] = [];
      const pageSize = 1000;
      let page = 0;
      let hasMore = true;

      // 🚀 CORREÇÃO BUG 400 PARA RANGE: Buscar campanhas do projeto primeiro
      let campaignIdsForProject: string[] | undefined;
      if (projectId && projectId !== 'all') {
        const { data: projectCampaigns } = await supabase
          .from('campaigns')
          .select('campaign_id')
          .eq('project_id', parseInt(projectId));

        if (!projectCampaigns || projectCampaigns.length === 0) {
          console.warn('⚠️ Nenhuma campanha encontrada para o projeto (RANGE):', projectId);
          campaignIdsForProject = [];
        } else {
          campaignIdsForProject = projectCampaigns.map(c => c.campaign_id);
        }
      }

      while (hasMore) {
        let spendQuery;

        if (projectId && projectId !== 'all' && campaignIdsForProject && campaignIdsForProject.length > 0) {
          spendQuery = supabase
            .from('daily_campaign_metrics')
            .select('spend')
            .gte('date', startDateStr)
            .lte('date', endDateStr)
            .in('campaign_id', campaignIdsForProject)
            .range(page * pageSize, (page + 1) * pageSize - 1);
        } else if (projectId && projectId !== 'all' && (!campaignIdsForProject || campaignIdsForProject.length === 0)) {
          // Projeto sem campanhas - não buscar nada
          break;
        } else {
          spendQuery = supabase
            .from('daily_campaign_metrics')
            .select('spend')
            .gte('date', startDateStr)
            .lte('date', endDateStr)
            .range(page * pageSize, (page + 1) * pageSize - 1);
        }

        const { data: pageData, error: spendError } = await spendQuery;

        if (spendError) {
          console.error('❌ Spend query error for RANGE (page ' + page + '):', spendError);
          throw spendError;
        }

        if (pageData && pageData.length > 0) {
          spendData.push(...pageData);
          page++;
          hasMore = pageData.length === pageSize;
        } else {
          hasMore = false;
        }
      }


      // Executar consulta de revenue
      const { data: revenueData, error: revenueError } = await revenueQuery;

      if (revenueError) {
        console.error('❌ Revenue query error for RANGE:', revenueError);
        throw revenueError;
      }

      if (spendError) {
        console.error('❌ Spend query error for RANGE:', spendError);
        throw spendError;
      }

      console.log({
        revenueRecords: revenueData?.length || 0,
        spendRecords: spendData?.length || 0,
        dateRange: `${startDateStr} to ${endDateStr}`,
        period
      });

      // 🚀 CÁLCULOS OTIMIZADOS PARA RANGE: Usar dados pré-processados
      const totalRevenueAfterRevshare = (revenueData || []).reduce((sum, item) => {
        return sum + (Number(item.revenue_converted_revshare) || 0);
      }, 0);

      const totalSpend = (spendData || []).reduce((sum, item) => {
        return sum + (Number(item.spend) || 0);
      }, 0);

      console.log('✅ RANGE - Dados agregados com sucesso:', {
        totalRevenueAfterRevshare,
        totalSpend,
        dateRange: `${startDateStr} to ${endDateStr}`,
        period,
        projectFilter: projectId,
        spendRecords: spendData.length,
        revenueRecords: revenueData?.length || 0
      });
      // 🚀 USAR VALORES JÁ CALCULADOS (evitar duplicação)
      const totalRevenue = totalRevenueAfterRevshare; // Para compatibilidade
      
      
      // Validation: Check if revenue seems unrealistic (possible data issue)
      if (totalRevenue > 5000000) { // More than 5M BRL for aggregated period
        console.warn('⚠️ SUSPICIOUS REVENUE VALUE for aggregated period:', {
          dateRange: `${startDateStr} to ${endDateStr}`,
          period,
          totalRevenue,
          possibleIssue: 'Value seems too high, check data quality'
        });
      }
      
      const totalProfit = totalRevenue - totalSpend;

      console.log({
        dateRange: `${startDateStr} to ${endDateStr}`,
        period,
        revenueDataCount: revenueData?.length || 0,
        spendDataCount: spendData?.length || 0,
        totalSpend,
        totalRevenue,
        totalRevenueAfterRevshare,
        totalProfit,
        allRevenueData: revenueData,
        allSpendData: spendData
      });

      const generalRoas = totalSpend > 0 ? ((totalRevenue / totalSpend) - 1) * 100 : 0;  // ROAS as excess
      const finalRoi = totalSpend > 0 ? (totalProfit / totalSpend) * 100 : 0;
      
      // Get campaign counts separately (with project filter if needed)
      let campaignCountQuery = supabase
        .from('campaigns')
        .select('status');
      
      // Apply project filter if specified
      if (projectId && projectId !== 'all') {
        campaignCountQuery = campaignCountQuery.eq('project_id', parseInt(projectId));
      }
      
      const { data: allCampaigns } = await campaignCountQuery;
      
      const activeCampaigns = (allCampaigns || []).filter(c => 
        c.status && ['Active', 'active', 'ENABLED'].includes(c.status)
      ).length;
      
      const pausedCampaigns = (allCampaigns || []).filter(c => 
        c.status && ['Paused', 'paused', 'PAUSED'].includes(c.status)
      ).length;
      
      // Calculate trends for the aggregated period
      const trends = await this.calculateTrends(filters);
      
      const result = {
        totalSpend,
        totalRevenue: totalRevenueAfterRevshare, // NOW: Display net revenue (after revshare) as main revenue
        totalRevenueAfterRevshare: totalRevenueAfterRevshare, // Keep for compatibility
        totalProfit,
        generalRoas,
        finalRoi,
        activeCampaigns,
        pausedCampaigns,
        trendsPercentage: {
          investment: Number(trends.investment.toFixed(1)),
          revenue: Number(trends.revenue.toFixed(1)),
          profit: Number(trends.profit.toFixed(1)),
          roas: Number(trends.roas.toFixed(1)),
          roi: Number(trends.roi.toFixed(1))
        }
      };

      // 💾 SALVAR NO CACHE: Reduz egress futuro
      localStorage.setItem(cacheKey, JSON.stringify(result));
      localStorage.setItem(`${cacheKey}_timestamp`, Date.now().toString());

      // 📊 METRICS: Increment cache miss (dados foram buscados do banco)
      localStorage.setItem('cache_misses', String(parseInt(cacheMissMetric) + 1));
      const totalRequests = parseInt(cacheHitMetric) + parseInt(cacheMissMetric) + 1;
      const hitRate = (parseInt(cacheHitMetric) / totalRequests * 100);

      console.log({
        cacheKey,
        cacheHitRate: `${hitRate.toFixed(1)}%`,
        egressSaved: hitRate > 0 ? `~${(hitRate * 500 / 100).toFixed(0)}KB per hit` : 'N/A'
      });

      return result;
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      return {
        totalSpend: 0,
        totalRevenue: 0,
        totalProfit: 0,
        generalRoas: 0,
        finalRoi: 0,
        activeCampaigns: 0,
        pausedCampaigns: 0,
        trendsPercentage: { investment: 0, revenue: 0, profit: 0, roas: 0, roi: 0 }
      };
    }
  }

  // Debug method to check if data exists for a specific date (apenas em desenvolvimento)
  async debugDataForDate(targetDate?: string): Promise<void> {
    if (!import.meta.env.DEV) {
      return; // Não executar em produção
    }

    try {
      const dateToCheck = targetDate || new Date().toISOString().split('T')[0];

      // Check daily_campaign_metrics
      const { data: campaignData, error: campaignError } = await supabase
        .from('daily_campaign_metrics')
        .select('*')
        .eq('date', dateToCheck)
        .limit(5);

      // Also check all available dates
      const { data: allDates } = await supabase
        .from('daily_campaign_metrics')
        .select('date')
        .order('date', { ascending: false })
        .limit(10);


      if (campaignData?.length > 0) {
      }

      // Check gam_metrics
      const { data: gamData, error: gamError } = await supabase
        .from('gam_metrics')
        .select('date, revenue, impressions, clicks')
        .eq('date', dateToCheck)
        .limit(5);

      // Also check all available dates in GAM
      const { data: allGamDates } = await supabase
        .from('gam_metrics')
        .select('date')
        .order('date', { ascending: false })
        .limit(10);


      if (gamData?.length > 0) {
      }

      // Check campaigns_with_revenue view
      const { data: campaignsView, error: campaignsError } = await supabase
        .from('campaigns_with_revenue')
        .select('*')
        .limit(5);

      if (campaignsView?.length > 0) {
      }

    } catch (error) {
      console.error('Error in debugDataForDate:', error);
    }
  }

  // Get metrics for today only (specific date filtering)
  private async getTodayMetrics(projectId?: string, targetDate?: string): Promise<DailyMetrics[]> {
    try {
      // Fix: Use the current server date dynamically
      const today = targetDate || await this.getCurrentServerDate();
      
      // Query daily campaign metrics for today only
      let campaignQuery = supabase
        .from('daily_campaign_metrics')
        .select(`
          date,
          spend,
          clicks,
          impressions,
          conversions,
          ctr,
          cpc
        `)
        .eq('date', today)
        .order('date', { ascending: false});

      const { data: campaignMetrics, error: campaignError } = await campaignQuery;
      if (campaignError) throw campaignError;

      if (campaignMetrics?.length > 0) {
      }

      // Get GAM revenue data for today only
      const { data: gamMetrics, error: gamError } = await supabase
        .from('gam_metrics')
        .select('date, revenue, revenue_converted, utm_campaign_value')
        .eq('date', today);

      if (gamError) throw gamError;
      
      if (gamMetrics?.length > 0) {
      }

      // Create single day data entry
      const dailyData: DailyMetrics = {
        date: today,
        investment: 0,
        revenue: 0,
        profit: 0,
        roas: 0,
        roi: 0,
        impressions: 0,
        clicks: 0,
        ctr: 0,
        conversions: 0,
        ecpm: 0,
        cpc: 0,
        viewability: 0,
        pmr: 0,
        rps: 0
      };

      // Aggregate campaign metrics for today
      (campaignMetrics || []).forEach(metric => {
        dailyData.investment += Number(metric.spend) || 0;
        dailyData.clicks += Number(metric.clicks) || 0;
        dailyData.impressions += Number(metric.impressions) || 0;
        dailyData.conversions += Number(metric.conversions) || 0;
        dailyData.cpc += Number(metric.cpc) || 0;
      });

      // Add GAM revenue data for today - GAM data doesn't have revenue_converted_revshare
      (gamMetrics || []).forEach(gam => {
        const revenueUsd = Number(gam.revenue) || 0;
        const revenueConverted = Number((gam as any).revenue_converted) || 0;

        // GAM data: use 2-parameter version (no revenue_converted_revshare)
        const revenue = this.getRevenueValue(revenueUsd, revenueConverted);
        dailyData.revenue += revenue || 0;
      });

      // Calculate derived metrics for today
      dailyData.profit = dailyData.revenue - dailyData.investment;
      dailyData.roas = dailyData.investment > 0 ? (dailyData.revenue / dailyData.investment) * 100 : 0;
      dailyData.roi = dailyData.investment > 0 ? (dailyData.profit / dailyData.investment) * 100 : 0;
      dailyData.ctr = dailyData.impressions > 0 ? (dailyData.clicks / dailyData.impressions) * 100 : 0;
      dailyData.cpc = dailyData.clicks > 0 ? dailyData.investment / dailyData.clicks : 0;

      console.log({
        investment: dailyData.investment,
        revenue: dailyData.revenue,
        profit: dailyData.profit,
        roas: dailyData.roas
      });

      return [dailyData];
    } catch (error) {
      console.error('Error fetching today metrics:', error);
      return [];
    }
  }

  // Calculate dashboard summary (legacy method - now uses getDashboardData)
  async getSummary(filters?: {
    date?: string;
    endDate?: string;
    projectId?: string;
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
  }): Promise<DashboardSummary> {
    try {
      
      // 🎯 SOLUÇÃO DEFINITIVA: Usar RPC get_dashboard_totals (1 linha, sem paginação!)
      if ((filters?.date && filters?.endDate) || filters?.period === 'range') {
        const projectIdInt = filters.projectId && filters.projectId !== 'all' ? parseInt(filters.projectId) : null;
        
        console.log('🚀 getSummary: Using RPC get_dashboard_totals (1 row)', {
          dateRange: `${filters.date} to ${filters.endDate}`,
          projectId: projectIdInt
        });

        // 🚀 SINGLE RPC CALL - Returns 1 row with all aggregated totals
        const { data: dashboardTotals, error: rpcError } = await supabase.rpc('get_dashboard_totals', {
          p_start_date: filters.date,
          p_end_date: filters.endDate,
          p_project_id: projectIdInt
        });

        if (rpcError) {
          console.error('❌ RPC get_dashboard_totals error:', rpcError);
          throw rpcError;
        }

        if (!dashboardTotals || dashboardTotals.length === 0) {
          console.warn('⚠️ RPC returned no data, using defaults');
          return {
            totalInvestment: 0,
            totalRevenue: 0,
            totalRevenueAfterRevshare: 0,
            totalProfit: 0,
            generalRoas: 0,
            finalRoi: 0,
            activeCampaigns: 0,
            campaignStatus: { green: 0, yellow: 0, red: 0 },
            trendsPercentage: { investment: 0, revenue: 0, profit: 0, roas: 0, roi: 0 }
          };
        }

        const totals = dashboardTotals[0];
        console.log('✅ RPC get_dashboard_totals result (1 row):', totals);

        // Extract values from RPC result
        const totalSpend = Number(totals.total_spend) || 0;
        const totalRevenueAfterRevshare = Number(totals.total_revenue) || 0;
        const totalProfit = Number(totals.total_profit) || 0;
        const generalRoas = Number(totals.general_roas) || 0;
        const finalRoi = Number(totals.final_roi) || 0;
        const activeCampaigns = Number(totals.active_campaigns) || 0;
        const greenCampaigns = Math.ceil(activeCampaigns * 0.6);
        const yellowCampaigns = Math.ceil(activeCampaigns * 0.3);
        const redCampaigns = activeCampaigns - greenCampaigns - yellowCampaigns;
        
        const result = {
          totalInvestment: totalSpend,
          totalRevenue: totalRevenueAfterRevshare,  // Use after revshare as main revenue
          totalRevenueAfterRevshare: totalRevenueAfterRevshare, // Keep for compatibility
          totalProfit: totalProfit,
          generalRoas: Math.floor(generalRoas),
          finalRoi: Math.floor(finalRoi),
          activeCampaigns: activeCampaigns,
          campaignStatus: {
            green: greenCampaigns,
            yellow: yellowCampaigns,
            red: redCampaigns
          },
          trendsPercentage: { investment: 0, revenue: 0, profit: 0, roas: 0, roi: 0 }
        };
        
        return result;
      }
      
      // For other periods, use existing logic
      const dashboardData = await this.getDashboardData(filters || {});

      console.log('🔍 getSummary - mapeando dashboardData para result:', {
        dashboardDataTotalSpend: dashboardData.totalSpend,
        filters: filters,
        willMapTo_totalInvestment: dashboardData.totalSpend
      });

      const result = {
        totalInvestment: dashboardData.totalSpend,
        totalRevenue: dashboardData.totalRevenue,
        totalRevenueAfterRevshare: dashboardData.totalRevenueAfterRevshare, // Usar valor direto - já vem com revshare aplicado
        totalProfit: dashboardData.totalProfit,
        generalRoas: Math.floor(dashboardData.generalRoas),
        finalRoi: Math.floor(dashboardData.finalRoi),
        activeCampaigns: dashboardData.activeCampaigns,
        campaignStatus: {
          green: Math.floor(dashboardData.activeCampaigns * 0.6),
          yellow: Math.floor(dashboardData.activeCampaigns * 0.3),
          red: dashboardData.activeCampaigns - Math.floor(dashboardData.activeCampaigns * 0.6) - Math.floor(dashboardData.activeCampaigns * 0.3)
        },
        trendsPercentage: dashboardData.trendsPercentage
      };

      console.log('✅ getSummary - result final:', result);

      return result;
    } catch (error) {
      console.error('Error calculating summary:', error);
      return {
        totalInvestment: 0,
        totalRevenue: 0,
        totalProfit: 0,
        generalRoas: 0,
        finalRoi: 0,
        activeCampaigns: 0,
        campaignStatus: { green: 0, yellow: 0, red: 0 },
        trendsPercentage: { investment: 0, revenue: 0, profit: 0, roas: 0, roi: 0 }
      };
    }
  }

  // Get campaigns by project
  async getCampaignsByProject(projectId: string): Promise<Campaign[]> {
    try {
      const campaigns = await this.getCampaigns();
      return campaigns.filter(c => c.projectId === projectId);
    } catch (error) {
      console.error('Error fetching campaigns by project:', error);
      return [];
    }
  }

  // Get detailed campaign data for individual dashboard
  async getCampaignDashboardData(campaignId: string): Promise<{
    campaign: Campaign | null;
    dailyMetrics: any[];
    historicalData: any[];
    campaignMetrics: any;
  }> {
    try {
      
      // First, let's make a simpler query to see what we have
      const { data: allCampaigns, error: allError } = await supabase
        .from('campaigns_with_revenue')
        .select('campaign_id, campaign_name')
        .limit(10);
      
      
      // Check if our specific campaign exists
      const { data: simpleCheck, error: simpleError } = await supabase
        .from('campaigns_with_revenue')
        .select('*')
        .eq('campaign_id', campaignId)
        .limit(1);
      
      
      if (!simpleCheck || simpleCheck.length === 0) {
        return {
          campaign: null,
          dailyMetrics: [],
          historicalData: [],
          campaignMetrics: null
        };
      }
      
      // Now try the complex query
      const { data: campaignData, error: campaignError } = await supabase
        .from('campaigns_with_revenue')
        .select('*')
        .eq('campaign_id', campaignId)
        .limit(1);

      
      if (campaignError) throw campaignError;
      
      if (!campaignData || campaignData.length === 0) {
        return {
          campaign: null,
          dailyMetrics: [],
          historicalData: [],
          campaignMetrics: null
        };
      }

      const rawData = campaignData[0];

      // Use the simple data format without joins for now
      const campaignMetrics = {
        campaignId: rawData.campaign_id,
        campaign_name: rawData.campaign_name || 'Campanha sem nome',
        projectName: 'Projeto padrão', // Will be loaded separately
        status: rawData.status || 'ENABLED',
        custom_goal: rawData.custom_goal || 'Meta não definida',
        advertising_channel: rawData.advertising_channel || 'Google Ads',
        bidding_strategy: rawData.bidding_strategy || 'Maximize conversions',
        start_date: rawData.start_date || new Date().toISOString(),
        end_date: rawData.end_date || new Date().toISOString(),
        budget_amount: rawData.budget_amount || 100,
        spend: Number(rawData.spend) || 0,
        revenue: Number(rawData.gam_revenue) || 0,
        profit: Number(rawData.profit) || 0,
        roas: this.calculateRoas(Number(rawData.gam_revenue) || 0, Number(rawData.spend) || 0),
        impressions: Number(rawData.impressions) || 0,
        clicks: Number(rawData.clicks) || 0,
        conversions: Number(rawData.conversions) || 0,
        ctr: rawData.impressions > 0 ? (Number(rawData.clicks) / Number(rawData.impressions)) * 100 : 0,
        cpc: rawData.impressions > 0 ? Number(rawData.spend) / Number(rawData.clicks) : 0,
        cost_per_conversion: rawData.conversions > 0 ? Number(rawData.spend) / Number(rawData.conversions) : 0
      };

      // Get daily metrics for this campaign (last 30 days)
      await supabase
        .from('daily_campaign_metrics')
        .select('*')
        .eq('campaign_id', campaignId)
        .order('date', { ascending: false })
        .limit(30);

      // Generate simplified historical data (mock for now)
      const historicalData = Array.from({ length: 7 }, (_, i) => {
        const date = new Date();
        date.setDate(date.getDate() - i);
        return {
          date: date.toISOString(),
          spend: Number(rawData.spend) / 7,
          revenue: Number(rawData.gam_revenue) / 7,
          clicks: Number(rawData.clicks) / 7,
          impressions: Number(rawData.impressions) / 7
        };
      }).reverse();

      
      return {
        campaign: null, // Not needed for this dashboard format
        dailyMetrics: [],
        historicalData: historicalData,
        campaignMetrics: campaignMetrics
      };
    } catch (error) {
      console.error('Error fetching campaign dashboard data:', error);
      return {
        campaign: null,
        dailyMetrics: [],
        historicalData: [],
        campaignMetrics: null
      };
    }
  }

  // New filtered version of getCampaignDashboardData that respects date filters
  async getCampaignDashboardDataFiltered(campaignId: string, filters: {
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
    date?: string;
    endDate?: string;
  }): Promise<{
    campaign: Campaign | null;
    dailyMetrics: any[];
    historicalData: any[];
    campaignMetrics: any;
  }> {
    try {
      
      // Determine date range based on filters
      let startDate: string;
      let endDate: string;

      if (filters.period === 'today' && filters.date) {
        startDate = filters.date;
        endDate = filters.date;
      } else if (filters.period === 'custom' && filters.date) {
        startDate = filters.date;
        endDate = filters.date;
      } else if (filters.period === 'range' && filters.date && filters.endDate) {
        // Range period: use both start and end dates
        startDate = filters.date;
        endDate = filters.endDate;
      } else if (filters.period === '7d') {
        const end = filters.date ? new Date(filters.date) : new Date();
        const start = new Date(end);
        start.setDate(start.getDate() - 6);
        endDate = end.toISOString().split('T')[0];
        startDate = start.toISOString().split('T')[0];
      } else if (filters.period === '30d') {
        const end = filters.date ? new Date(filters.date) : new Date();
        const start = new Date(end);
        start.setDate(start.getDate() - 29);
        endDate = end.toISOString().split('T')[0];
        startDate = start.toISOString().split('T')[0];
      } else {
        const today = filters.date || new Date().toISOString().split('T')[0];
        startDate = today;
        endDate = today;
      }


      // Get campaign basic info with project data
      const { data: campaignData, error: campaignError } = await supabase
        .from('campaigns')
        .select(`
          *,
          projects(project_type, project_name)
        `)
        .eq('campaign_id', campaignId)
        .limit(1);

      if (campaignError) throw campaignError;
      
      if (!campaignData || campaignData.length === 0) {
        return {
          campaign: null,
          dailyMetrics: [],
          historicalData: [],
          campaignMetrics: null
        };
      }

      const rawCampaign = campaignData[0];

      // Get daily campaign metrics for date range (including revenue_converted_revshare)
      console.log({
        table: 'daily_campaign_metrics',
        campaign_id: campaignId,
        date_range: `${startDate} to ${endDate}`,
        period: filters.period
      });

      const { data: dailyMetrics, error: metricsError } = await supabase
        .from('daily_campaign_metrics')
        .select('spend, clicks, impressions, conversions, revenue_converted_revshare, date, gam_ecpm, gam_cpc, match_rate, gam_total_requests, gam_impressions, fill_rate, gam_clicks, gam_ctr, viewable_impressions')
        .eq('campaign_id', campaignId)
        .gte('date', startDate)
        .lte('date', endDate)
        .order('date', { ascending: true });

      if (metricsError) {
        console.error(`❌ Error querying daily_campaign_metrics:`, metricsError);
      } else {
        if (dailyMetrics && dailyMetrics.length > 0) {
        }
      }

      // Note: GAM data no longer needed - using revenue_converted_revshare from daily_campaign_metrics

      // 🚀 RPC OPTIMIZATION: Tentar usar get_campaign_detailed_metrics primeiro
      let aggregatedSpend = 0;
      let aggregatedClicks = 0;
      let aggregatedImpressions = 0;
      let aggregatedConversions = 0;
      let aggregatedRevenue = 0;
      let aggregatedGamTotalRequests = 0;
      let aggregatedGamImpressions = 0;
      let aggregatedGamClicks = 0;
      let aggregatedViewableImpressions = 0;
      let avgGamEcpm = 0;
      let avgGamCpc = 0;
      let avgMatchRate = 0;
      let avgFillRate = 0;
      let avgGamCtr = 0;
      let avgViewableImpressions = 0;

      try {
        console.log('🚀 getCampaignDashboardDataFiltered RPC call:', { campaignId, startDate, endDate });

        const { data: rpcData, error: rpcError } = await supabase.rpc('get_campaign_detailed_metrics', {
          p_campaign_id: campaignId,
          p_start_date: startDate,
          p_end_date: endDate
        });

        if (!rpcError && rpcData && rpcData.length > 0) {
          const rpc = rpcData[0];
          
          aggregatedSpend = Number(rpc.total_spend) || 0;
          aggregatedClicks = Number(rpc.total_clicks) || 0;
          aggregatedImpressions = Number(rpc.total_impressions) || 0;
          aggregatedConversions = Number(rpc.total_conversions) || 0;
          aggregatedRevenue = Number(rpc.total_revenue) || 0;
          aggregatedGamTotalRequests = Number(rpc.total_gam_total_requests) || 0;
          aggregatedGamImpressions = Number(rpc.total_gam_impressions) || 0;
          aggregatedGamClicks = Number(rpc.total_gam_clicks) || 0;
          aggregatedViewableImpressions = Number(rpc.total_viewable_impressions) || 0;
          avgGamEcpm = Number(rpc.avg_gam_ecpm) || 0;
          avgGamCpc = Number(rpc.avg_gam_cpc) || 0;
          avgMatchRate = Number(rpc.avg_match_rate) || 0;
          avgFillRate = Number(rpc.avg_fill_rate) || 0;
          avgGamCtr = Number(rpc.avg_gam_ctr) || 0;
          avgViewableImpressions = Number(rpc.total_viewable_impressions) || 0;

          console.log('✅ getCampaignDashboardDataFiltered RPC success:', {
            spend: aggregatedSpend,
            revenue: aggregatedRevenue,
            clicks: aggregatedClicks,
            impressions: aggregatedImpressions
          });
        } else {
          throw new Error(rpcError?.message || 'RPC returned empty');
        }
      } catch (rpcException) {
        console.warn('⚠️ getCampaignDashboardDataFiltered RPC failed, using fallback:', rpcException);
        
        // 🔄 FALLBACK: Método antigo com reduces
        aggregatedSpend = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.spend) || 0), 0);
        aggregatedClicks = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.clicks) || 0), 0);
        aggregatedImpressions = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.impressions) || 0), 0);
        aggregatedConversions = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.conversions) || 0), 0);
        aggregatedRevenue = (dailyMetrics || []).reduce((sum, m) => {
          return sum + (Number((m as any).revenue_converted_revshare) || 0);
        }, 0);

        const metricsCount = (dailyMetrics || []).length;
        const aggregatedGamEcpmSum = (dailyMetrics || []).reduce((sum, m) => sum + (Number((m as any).gam_ecpm) || 0), 0);
        const aggregatedGamCpcSum = (dailyMetrics || []).reduce((sum, m) => sum + (Number((m as any).gam_cpc) || 0), 0);
        const aggregatedMatchRateSum = (dailyMetrics || []).reduce((sum, m) => sum + (Number((m as any).match_rate) || 0), 0);
        aggregatedGamTotalRequests = (dailyMetrics || []).reduce((sum, m) => sum + (Number((m as any).gam_total_requests) || 0), 0);
        aggregatedGamImpressions = (dailyMetrics || []).reduce((sum, m) => sum + (Number((m as any).gam_impressions) || 0), 0);
        const aggregatedFillRateSum = (dailyMetrics || []).reduce((sum, m) => sum + (Number((m as any).fill_rate) || 0), 0);
        aggregatedGamClicks = (dailyMetrics || []).reduce((sum, m) => sum + (Number((m as any).gam_clicks) || 0), 0);
        const aggregatedGamCtrSum = (dailyMetrics || []).reduce((sum, m) => sum + (Number((m as any).gam_ctr) || 0), 0);
        aggregatedViewableImpressions = (dailyMetrics || []).reduce((sum, m) => sum + (Number((m as any).viewable_impressions) || 0), 0);
        
        avgGamEcpm = metricsCount > 0 ? aggregatedGamEcpmSum / metricsCount : 0;
        avgGamCpc = metricsCount > 0 ? aggregatedGamCpcSum / metricsCount : 0;
        avgMatchRate = metricsCount > 0 ? aggregatedMatchRateSum / metricsCount : 0;
        avgFillRate = metricsCount > 0 ? aggregatedFillRateSum / metricsCount : 0;
        avgGamCtr = metricsCount > 0 ? aggregatedGamCtrSum / metricsCount : 0;
        avgViewableImpressions = metricsCount > 0 ? aggregatedViewableImpressions / metricsCount : 0;
      }

      console.log({
        period: filters.period,
        dateRange: `${startDate} to ${endDate}`,
        aggregatedSpend,
        aggregatedRevenue,
        aggregatedClicks,
        aggregatedImpressions,
        aggregatedConversions
      });

      // Build campaign metrics object with filtered data
      const campaignMetrics = {
        campaignId: rawCampaign.campaign_id,
        campaign_name: rawCampaign.campaign_name || 'Campanha sem nome',
        projectName: (rawCampaign as any).projects?.project_name || 'Projeto padrão',
        project_type: (rawCampaign as any).projects?.project_type || 'GAM',
        status: rawCampaign.status || 'ENABLED',
        custom_goal: rawCampaign.custom_goal || 'Meta não definida',
        advertising_channel: rawCampaign.advertising_channel || 'Google Ads',
        bidding_strategy: rawCampaign.bidding_strategy || 'Maximize conversions',
        start_date: rawCampaign.start_date || new Date().toISOString(),
        end_date: rawCampaign.end_date || new Date().toISOString(),
        budget_amount: rawCampaign.budget_amount || 100,
        spend: aggregatedSpend,
        revenue: aggregatedRevenue,
        profit: aggregatedRevenue - aggregatedSpend,
        roas: this.calculateRoas(aggregatedRevenue, aggregatedSpend),
        impressions: aggregatedImpressions,
        clicks: aggregatedClicks,
        conversions: aggregatedConversions,
        ctr: aggregatedImpressions > 0 ? (aggregatedClicks / aggregatedImpressions) * 100 : 0,
        cpc: aggregatedClicks > 0 ? aggregatedSpend / aggregatedClicks : 0,
        cost_per_conversion: aggregatedConversions > 0 ? aggregatedSpend / aggregatedConversions : 0,
        gam_ecpm: avgGamEcpm,
        gam_cpc: avgGamCpc,
        match_rate: avgMatchRate,
        gam_total_requests: aggregatedGamTotalRequests,
        gam_impressions: aggregatedGamImpressions,
        fill_rate: avgFillRate,
        gam_clicks: aggregatedGamClicks,
        gam_ctr: avgGamCtr,
        viewable_impressions: avgViewableImpressions
      };

      // Get historical data for charts - use the same range as the main metrics
      let chartStartDate: string;
      let chartEndDate: string;

      if (filters.period === 'range' && filters.date && filters.endDate) {
        // For range period, use exact dates from the filter
        chartStartDate = filters.date;
        chartEndDate = filters.endDate;
      } else {
        // For other periods, use the same logic as main metrics
        chartStartDate = startDate;
        chartEndDate = endDate;
      }


      const { data: chartMetrics } = await supabase
        .from('daily_campaign_metrics')
        .select('spend, clicks, impressions, conversions, revenue_converted_revshare, date, gam_ecpm, gam_cpc, match_rate, gam_total_requests, gam_impressions, fill_rate, gam_clicks, gam_ctr, viewable_impressions')
        .eq('campaign_id', campaignId)
        .gte('date', chartStartDate)
        .lte('date', chartEndDate)
        .order('date', { ascending: true });


      // Build historical data by date using daily_campaign_metrics only
      const historicalData = [];


      // 🚀 CORREÇÃO: Use string-based date arithmetic with São Paulo timezone awareness
      const addDaysToDateString = (dateStr: string, days: number): string => {
        // Parse date string ensuring São Paulo timezone
        const [year, month, day] = dateStr.split('-').map(Number);

        // Create date in São Paulo timezone using explicit offset
        const date = new Date(`${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T12:00:00-03:00`);
        date.setDate(date.getDate() + days);

        // Format back to YYYY-MM-DD in São Paulo timezone
        return new Intl.DateTimeFormat('sv-SE', {
          timeZone: 'America/Sao_Paulo'
        }).format(date);
      };

      const getDaysBetweenDates = (startStr: string, endStr: string): number => {
        const start = new Date(`${startStr}T12:00:00-03:00`);
        const end = new Date(`${endStr}T12:00:00-03:00`);
        return Math.floor((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
      };

      const totalDays = getDaysBetweenDates(chartStartDate, chartEndDate);

      // Iterate through each day in the range
      for (let dayOffset = 0; dayOffset <= totalDays; dayOffset++) {
        const dateStr = addDaysToDateString(chartStartDate, dayOffset);
        const dayMetrics = (chartMetrics || []).filter(m => m.date === dateStr);


        const daySpend = dayMetrics.reduce((sum, m) => sum + (Number(m.spend) || 0), 0);
        const dayRevenue = dayMetrics.reduce((sum, m) => {
          const revenueAfterRevshare = Number((m as any).revenue_converted_revshare) || 0;
          return sum + revenueAfterRevshare;
        }, 0);
        const dayClicks = dayMetrics.reduce((sum, m) => sum + (Number(m.clicks) || 0), 0);
        const dayImpressions = dayMetrics.reduce((sum, m) => sum + (Number(m.impressions) || 0), 0);
        const dayConversions = dayMetrics.reduce((sum, m) => sum + (Number(m.conversions) || 0), 0);

        // Calculate averages for GAM metrics for this day
        const dayMetricsCount = dayMetrics.length;
        const dayGamEcpmSum = dayMetrics.reduce((sum, m) => sum + (Number((m as any).gam_ecpm) || 0), 0);
        const dayGamCpcSum = dayMetrics.reduce((sum, m) => sum + (Number((m as any).gam_cpc) || 0), 0);
        const dayMatchRateSum = dayMetrics.reduce((sum, m) => sum + (Number((m as any).match_rate) || 0), 0);
        const dayGamTotalRequests = dayMetrics.reduce((sum, m) => sum + (Number((m as any).gam_total_requests) || 0), 0);
        const dayGamImpressions = dayMetrics.reduce((sum, m) => sum + (Number((m as any).gam_impressions) || 0), 0);
        const dayFillRateSum = dayMetrics.reduce((sum, m) => sum + (Number((m as any).fill_rate) || 0), 0);
        const dayGamClicks = dayMetrics.reduce((sum, m) => sum + (Number((m as any).gam_clicks) || 0), 0);
        const dayGamCtrSum = dayMetrics.reduce((sum, m) => sum + (Number((m as any).gam_ctr) || 0), 0);
        const dayViewableImpressionsSum = dayMetrics.reduce((sum, m) => sum + (Number((m as any).viewable_impressions) || 0), 0);
        const dayGamEcpm = dayMetricsCount > 0 ? dayGamEcpmSum / dayMetricsCount : 0;
        const dayGamCpc = dayMetricsCount > 0 ? dayGamCpcSum / dayMetricsCount : 0;
        const dayMatchRate = dayMetricsCount > 0 ? dayMatchRateSum / dayMetricsCount : 0;
        const dayFillRate = dayMetricsCount > 0 ? dayFillRateSum / dayMetricsCount : 0;
        const dayGamCtr = dayMetricsCount > 0 ? dayGamCtrSum / dayMetricsCount : 0;
        const dayViewableImpressions = dayMetricsCount > 0 ? dayViewableImpressionsSum / dayMetricsCount : 0;

        // Calculate derived metrics for the day
        const dayCpc = dayClicks > 0 ? daySpend / dayClicks : 0;
        const dayCostPerConversion = dayConversions > 0 ? daySpend / dayConversions : 0;

        historicalData.push({
          date: dateStr,
          spend: daySpend,
          revenue: dayRevenue,
          clicks: dayClicks,
          impressions: dayImpressions,
          conversions: dayConversions,
          cpc: dayCpc,
          cost_per_conversion: dayCostPerConversion,
          gam_ecpm: dayGamEcpm,
          gam_cpc: dayGamCpc,
          match_rate: dayMatchRate,
          gam_total_requests: dayGamTotalRequests,
          gam_impressions: dayGamImpressions,
          fill_rate: dayFillRate,
          gam_clicks: dayGamClicks,
          gam_ctr: dayGamCtr,
          viewable_impressions: dayViewableImpressions
        });
      }


      
      return {
        campaign: null,
        dailyMetrics: dailyMetrics || [],
        historicalData: historicalData,
        campaignMetrics: campaignMetrics
      };
    } catch (error) {
      console.error('Error fetching filtered campaign dashboard data:', error);
      return {
        campaign: null,
        dailyMetrics: [],
        historicalData: [],
        campaignMetrics: null
      };
    }
  }

  // Get project by ID with detailed data
  async getProjectById(id: string): Promise<Project | undefined> {
    try {
      const projects = await this.getProjects();
      return projects.find(p => p.id === id);
    } catch (error) {
      console.error('Error fetching project by ID:', error);
      return undefined;
    }
  }

  // Get detailed project data for individual dashboard
  async getProjectDashboardData(projectId: string, period?: 'today' | '7d' | '30d'): Promise<{
    project: Project | null;
    campaigns: Campaign[];
    dailyMetrics: DailyMetrics[];
    yesterdayData: any;
    historicalData: any[];
  }> {
    try {
      // Get project data
      const project = await this.getProjectById(projectId);
      if (!project) {
        return {
          project: null,
          campaigns: [],
          dailyMetrics: [],
          yesterdayData: null,
          historicalData: []
        };
      }

      // Get campaigns for this project
      const campaigns = await this.getCampaigns({ projectId });

      // Get daily metrics for the project based on period
      const daysToFetch = (period === 'today' || period === 'yesterday') ? 2 : (period === '7d' ? 7 : 30); // Fetch 2 days for today/yesterday to compare
      const dailyMetrics = await this.getDailyMetrics({ projectId, period: period || '30d', days: daysToFetch });

      // Get yesterday's real data
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      
      const yesterdayMetrics = await this.getDailyMetrics({ 
        projectId, 
        period: 'today',
        days: 1 
      });
      
      const yesterdayData = yesterdayMetrics.length > 0 ? {
        investment: yesterdayMetrics[0].investment || 0,
        revenue: yesterdayMetrics[0].revenue || 0,
        roas: yesterdayMetrics[0].roas || 0,
        roi: yesterdayMetrics[0].roi || 0,
        grossProfit: (yesterdayMetrics[0].revenue || 0) - (yesterdayMetrics[0].investment || 0),
        netProfit: ((yesterdayMetrics[0].revenue || 0) - (yesterdayMetrics[0].investment || 0)) * 0.8 // Assumindo 20% de custos operacionais
      } : {
        investment: 0,
        revenue: 0,
        roas: 0,
        roi: 0,
        grossProfit: 0,
        netProfit: 0
      };

      // Generate historical chart data from daily metrics
      const historicalData = dailyMetrics.map(metric => ({
        date: metric.date,
        dateFormatted: (() => {
          const [year, month, day] = metric.date.split('-').map(Number);
          const saoPauloDate = new Date(`${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T12:00:00-03:00`);
          return saoPauloDate.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
        })(),
        revenue: metric.revenue,
        investment: metric.investment,
        roas: metric.roas,
        roi: metric.roi
      }));

      return {
        project,
        campaigns,
        dailyMetrics,
        yesterdayData,
        historicalData
      };
    } catch (error) {
      console.error('Error fetching project dashboard data:', error);
      return {
        project: null,
        campaigns: [],
        dailyMetrics: [],
        yesterdayData: null,
        historicalData: []
      };
    }
  }

  // Método principal para processar dados do Google Ads (novo fluxo automático)
  async processGoogleAdsData(googleAdsData: any): Promise<void> {
    try {
      // Chamar função do banco para enriquecer campanhas
      const { error } = await supabase.rpc('enrich_campaign_with_google_ads', {
        google_ads_data: googleAdsData
      });
      
      if (error) {
        console.error('Error processing Google Ads data:', error);
        throw error;
      }
      
    } catch (error) {
      console.error('Error in processGoogleAdsData:', error);
      throw error;
    }
  }
  
  // Método legacy - manter para compatibilidade
  async processGoogleAdsDataLegacy(googleAdsData: any): Promise<void> {
    try {
      // Extrair URL e domínio do nome da campanha
      const campaignName = googleAdsData.campaign_name || '';
      const urlMatch = campaignName.match(/([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[\/\w.-]*)/i);
      let extractedUrl = urlMatch ? urlMatch[1] : null;
      let extractedDomain = extractedUrl ? extractedUrl.split('/')[0] : null;

      // Remover www. do domínio e URL para evitar duplicatas
      if (extractedDomain) {
        extractedDomain = extractedDomain.replace(/^www\./i, '');
      }
      if (extractedUrl) {
        extractedUrl = extractedUrl.replace(/^www\./i, '');
      }

      if (extractedDomain) {
        // Auto-criar projeto se necessário
        const { data: existingProject } = await supabase
          .from('projects')
          .select('id')
          .eq('domain', extractedDomain)
          .single();
        
        let projectId = existingProject?.id;
        
        if (!projectId) {
          const { data: newProject } = await supabase
            .from('projects')
            .insert({
              project_name: extractedDomain,
              main_url: `https://${extractedDomain}`,
              domain: extractedDomain,
              start_date: new Date().toISOString().split('T')[0],
              status: 'active',
              dollar_rate: 5.50,
              google_ads_status: 'pending',
              gam_status: 'pending',
              auto_created: true,
              created_at: getSaoPauloTimestamp(),
              updated_at: getSaoPauloTimestamp()
            })
            .select('id')
            .single();
          
          projectId = newProject?.id;
        }
        
        if (projectId) {
          // Inserir/atualizar campanha
          const customGoal = campaignName.split(' / ')[0] || campaignName;
          
          await supabase
            .from('campaigns')
            .upsert({
              project_id: projectId,
              campaign_name: campaignName,
              google_ads_campaign_id: googleAdsData.campaign_id,
              start_date: googleAdsData.start_date,
              end_date: googleAdsData.end_date,
              status: googleAdsData.status === 'ENABLED' ? 'active' : 'paused',
              google_ads_status: googleAdsData.status,
              bidding_strategy: googleAdsData.bidding_strategy,
              advertising_channel: googleAdsData.advertising_channel,
              budget_amount: googleAdsData.budget_amount,
              budget_id: googleAdsData.budget_id,
              target_value: googleAdsData.target_value,
              custom_goal: customGoal,
              extracted_url: extractedUrl,
              extracted_domain: extractedDomain,
              updated_at: getSaoPauloTimestamp()
            }, {
              onConflict: 'google_ads_campaign_id'
            });
          
        }
      }
    } catch (error) {
      console.error('Error processing Google Ads data:', error);
      throw error;
    }
  }
  
  // Método principal para processar métricas GAM (novo fluxo automático)
  async processGamMetrics(gamData: any): Promise<void> {
    try {
      // Chamar função do banco para processar automaticamente
      const { error } = await supabase.rpc('process_gam_metrics_auto', {
        gam_data: gamData
      });
      
      if (error) {
        console.error('Error processing GAM metrics:', error);
        throw error;
      }
      
    } catch (error) {
      console.error('Error in processGamMetrics:', error);
      throw error;
    }
  }
  
  // Método legacy - manter para compatibilidade 
  async processGamMetricsLegacy(gamData: any): Promise<void> {
    try {
      // Inserir métricas GAM
      await supabase
        .from('gam_metrics')
        .upsert({
          date: gamData.date,
          utm_campaign_key: gamData.key,
          utm_campaign_value: gamData.value,
          revenue: gamData.revenue,
          gam_accounts_id: gamData.gam_accounts_id,
          created_at: getSaoPauloTimestamp(),
          updated_at: getSaoPauloTimestamp()
        }, {
          onConflict: 'date,utm_campaign_value,gam_accounts_id'
        });
        
    } catch (error) {
      console.error('Error processing GAM metrics:', error);
      throw error;
    }
  }

  
  // Obter campanhas com revenue calculado automaticamente e informações de controle
  async getCampaignsWithRevenue(filters?: {
    projectId?: string;
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
    date?: string;
    endDate?: string;
    userProjectIds?: number[];
    userCampaignIds?: string[];
  }): Promise<Campaign[]> {
    try {
      // Log filter information for debugging

      // For filtered queries, we need to build custom aggregated data instead of using the view
      if (filters?.date || filters?.period) {
        return await this.getCampaignsWithRevenueFiltered(filters);
      }

      // Use the campaigns_with_revenue view only when no date/period filters
      // 🚀 COM PAGINAÇÃO para evitar limite de 1000 registros
      const allData: any[] = [];
      const pageSize = 1000;
      let page = 0;
      let hasMore = true;

      while (hasMore) {
        let query = supabase
          .from('campaigns_with_revenue')
          .select('*')
          .range(page * pageSize, (page + 1) * pageSize - 1);

        // Apply project filter if specified
        if (filters?.projectId && filters.projectId !== 'all') {
          query = query.eq('project_id', parseInt(filters.projectId));
        }

        // Apply user project filter for OPERATORS
        if (filters?.userProjectIds && filters.userProjectIds.length > 0) {
          query = query.in('project_id', filters.userProjectIds);
        }

        query = query.order('gam_revenue', { ascending: false });

        const { data: pageData, error } = await query;

        if (error) {
          console.error(`❌ Erro ao buscar campaigns_with_revenue (página ${page}):`, error);
          throw error;
        }

        if (pageData && pageData.length > 0) {
          allData.push(...pageData);
          page++;
          hasMore = pageData.length === pageSize;
        } else {
          hasMore = false;
        }
      }

      console.log(`✅ campaigns_with_revenue: ${allData.length} campanhas carregadas em ${page} página(s)`);

      const data = allData;

      // Debug log to see available campaigns
      console.log({
        total: (data || []).length,
        hasUserFilter: !!(filters?.userCampaignIds && filters.userCampaignIds.length > 0),
        userCampaignIds: filters?.userCampaignIds,
        sampleCampaign: data?.[0] ? {
          id: data[0].id,
          campaign_id: data[0].campaign_id,
          name: data[0].campaign_name
        } : null
      });

      // Filter campaigns by user permissions if specified
      let filteredData = data || [];
      if (filters?.userCampaignIds && filters.userCampaignIds.length > 0) {
        filteredData = filteredData.filter((item: any) => {
          const isAllowed = filters.userCampaignIds!.includes(item.campaign_id);
          if (!isAllowed) {
          }
          return isAllowed;
        });
        console.log({
          total: data?.length,
          filtered: filteredData.length
        });
      }

      // Convert to Campaign interface format
      // Use revenue (revenue_converted_revshare - líquido) not gam_revenue
      return filteredData.map((item: any) => {
        const revenue = Number(item.revenue) || 0;
        const spend = Number(item.spend) || 0;
        return {
        id: item.campaign_id.toString(), // Use campaign_id instead of id for consistency
        name: item.campaign_name,
        projectId: item.project_id?.toString() || '1',
        status: item.status === 'Active' || item.status === 'ENABLED' ? 'active' : 'paused',
        performance: this.calculatePerformance(revenue, spend),
        investment: spend,
        revenue,
        roas: this.calculateRoas(revenue, spend),
        impressions: Number(item.impressions) || 0,
        clicks: Number(item.clicks) || 0,
        ctr: 0, // TODO: calculate from impressions/clicks if needed
        startDate: item.start_date,
        endDate: item.end_date,
        utmCampaignValue: item.campaign_id,
        extractedUrl: item.extracted_url || undefined,
        extractedDomain: item.extracted_domain || undefined,
        customGoal: item.custom_goal || undefined,
        // Additional fields
        statusSource: 'auto', // Default since view doesn't have this info
        userPausedAt: undefined,
        userPausedBy: undefined
      };
      });
    } catch (error) {
      console.error('Error fetching campaigns with revenue:', error);
      return [];
    }
  }


  // 🛡️ FALLBACK: Buscar campanhas diretamente quando RPC falhar
  private async getCampaignsWithRevenueDirectFallback(
    filters: {
      projectId?: string;
      period?: string;
      userProjectIds?: number[];
      userCampaignIds?: string[];
    },
    startDate: string,
    endDate: string
  ): Promise<Campaign[]> {
    try {
      // PAGE_SIZE abaixo do cap silencioso (1000) do PostgREST. Iteramos
      // até a página voltar < PAGE_SIZE, com tiebreaker estável por id.
      const PAGE_SIZE = 1000;
      const HARD_CAP_PAGES = 500;

      // 1) Buscar metadata de campaigns (paginado, com tiebreaker)
      const allCampaigns: any[] = [];
      for (let page = 0; page < HARD_CAP_PAGES; page++) {
        let q = supabase
          .from('campaigns')
          .select('*')
          .order('id', { ascending: true })
          .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1);

        if (filters.projectId && filters.projectId !== 'all') {
          q = q.eq('project_id', parseInt(filters.projectId));
        }

        const { data: pageData, error: e } = await q;
        if (e) {
          console.error(`❌ Erro ao buscar campanhas (página ${page}):`, e);
          break;
        }
        if (!pageData || pageData.length === 0) break;
        allCampaigns.push(...pageData);
        if (pageData.length < PAGE_SIZE) break;
      }

      // Aplicar filtros de visibilidade do operador na metadata
      let campaigns = allCampaigns;
      if (filters.userProjectIds && filters.userProjectIds.length > 0) {
        const projSet = new Set(filters.userProjectIds);
        campaigns = campaigns.filter(c => projSet.has(c.project_id));
      }
      if (filters.userCampaignIds && filters.userCampaignIds.length > 0) {
        const cidSet = new Set(filters.userCampaignIds);
        campaigns = campaigns.filter(c => cidSet.has(c.campaign_id));
      }

      console.log(`✅ Fallback: ${allCampaigns.length} campanhas brutas, ${campaigns.length} após filtros de usuário`);

      if (campaigns.length === 0) return [];

      // 2) Buscar agregado de daily_campaign_metrics no range, restrito aos campaign_ids
      //    relevantes. Chunkamos o `.in()` para evitar estourar limite de URL do PostgREST.
      const targetCampaignIds = campaigns.map(c => c.campaign_id).filter(Boolean);
      const IN_CHUNK = 200;
      const metricsByCampaign = new Map<string, {
        spend: number; revenue: number; impressions: number; clicks: number;
      }>();

      for (let i = 0; i < targetCampaignIds.length; i += IN_CHUNK) {
        const slice = targetCampaignIds.slice(i, i + IN_CHUNK);

        // Paginação dentro do chunk: pode haver até PAGE_SIZE × (date_range × IN_CHUNK) linhas
        for (let page = 0; page < HARD_CAP_PAGES; page++) {
          const { data: rows, error: e } = await supabase
            .from('daily_campaign_metrics')
            .select('campaign_id, spend, revenue_converted_revshare, impressions, clicks')
            .gte('date', startDate)
            .lte('date', endDate)
            .in('campaign_id', slice)
            .order('campaign_id', { ascending: true })
            .order('date', { ascending: true })
            .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1);

          if (e) {
            console.error(`❌ Erro ao buscar daily_campaign_metrics (chunk ${i}, página ${page}):`, e);
            break;
          }
          if (!rows || rows.length === 0) break;

          for (const r of rows) {
            const acc = metricsByCampaign.get(r.campaign_id) ?? {
              spend: 0, revenue: 0, impressions: 0, clicks: 0,
            };
            acc.spend += Number(r.spend ?? 0);
            acc.revenue += Number(r.revenue_converted_revshare ?? 0);
            acc.impressions += Number(r.impressions ?? 0);
            acc.clicks += Number(r.clicks ?? 0);
            metricsByCampaign.set(r.campaign_id, acc);
          }

          if (rows.length < PAGE_SIZE) break;
        }
      }

      // 3) Compor Campaign[] com métricas agregadas (zero quando sem dados no range)
      const result: Campaign[] = campaigns.map((c: any) => {
        const agg = metricsByCampaign.get(c.campaign_id) ?? {
          spend: 0, revenue: 0, impressions: 0, clicks: 0,
        };
        const roas = agg.spend > 0 ? ((agg.revenue / agg.spend) - 1) * 100 : 0;
        const ctr = agg.impressions > 0 ? (agg.clicks / agg.impressions) * 100 : 0;
        const isActive = c.status === 'Active' || c.status === 'active' || c.status === 'ENABLED';
        return {
          id: c.campaign_id?.toString() || c.id?.toString(),
          name: c.campaign_name || 'Unnamed Campaign',
          projectId: c.project_id?.toString() || '1',
          status: isActive ? 'active' : 'paused',
          performance: this.calculatePerformance(agg.revenue, agg.spend),
          investment: agg.spend,
          revenue: agg.revenue,
          roas,
          impressions: agg.impressions,
          clicks: agg.clicks,
          ctr,
          startDate: c.start_date,
          endDate: c.end_date,
          utmCampaignValue: c.campaign_id || c.utm_campaign_value,
          extractedUrl: undefined,
          extractedDomain: undefined,
          customGoal: c.custom_goal || undefined,
          statusSource: 'auto',
          userPausedAt: undefined,
          userPausedBy: undefined,
        } as Campaign;
      });

      return result.sort((a, b) => (b.revenue || 0) - (a.revenue || 0));
    } catch (error) {
      console.error('❌ Erro no fallback getCampaignsWithRevenueDirectFallback:', error);
      return [];
    }
  }

  // OTIMIZADO: Server-side aggregation usando RPC - reduz egress drasticamente
  private async getCampaignsWithRevenueFiltered(filters: {
    projectId?: string;
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
    date?: string;
    endDate?: string;
    userProjectIds?: number[];
    userCampaignIds?: string[];
  }): Promise<Campaign[]> {
    try {

      // 🚀 CACHE INTELIGENTE para campanhas com validação via daily_campaign_metrics
      const cacheKey = `campaigns_optimized_${JSON.stringify(filters)}`;
      const cacheTimestamp = localStorage.getItem(`${cacheKey}_timestamp`);
      const cachedData = localStorage.getItem(cacheKey);

      if (cachedData && cacheTimestamp) {
        const cacheAge = Date.now() - parseInt(cacheTimestamp);
        const cacheValidTime = 3 * 60 * 1000; // 3 minutos para campanhas

        // Calcular range de datas para validação do cache
        let dateRange;
        if (filters.period === 'today' && filters.date) {
          dateRange = { startDate: filters.date, endDate: filters.date };
        } else if (filters.period === 'custom' && filters.date) {
          dateRange = { startDate: filters.date, endDate: filters.date };
        } else if (filters.period === 'range' && filters.date && filters.endDate) {
          dateRange = { startDate: filters.date, endDate: filters.endDate };
        } else if (filters.period === '7d' && filters.date) {
          const end = new Date(filters.date);
          const start = new Date(end);
          start.setDate(start.getDate() - 6);
          dateRange = {
            startDate: start.toISOString().split('T')[0],
            endDate: filters.date
          };
        } else if (filters.period === '30d' && filters.date) {
          const end = new Date(filters.date);
          const start = new Date(end);
          start.setDate(start.getDate() - 29);
          dateRange = {
            startDate: start.toISOString().split('T')[0],
            endDate: filters.date
          };
        }

        if (dateRange) {
          const isCacheStillValid = await this.isCampaignCacheValid(cacheKey, parseInt(cacheTimestamp), dateRange);
          if (cacheAge < cacheValidTime && isCacheStillValid) {
            console.log({
              cacheKey,
              cacheAge: `${Math.round(cacheAge / 1000)}s`,
              dateRange
            });
            return JSON.parse(cachedData);
          } else if (!isCacheStillValid) {
          }
        } else {
          // Fallback para cache baseado em tempo quando não temos range
          if (cacheAge < cacheValidTime) {
            console.log({
              cacheKey,
              cacheAge: `${Math.round(cacheAge / 1000)}s`
            });
            return JSON.parse(cachedData);
          }
        }
      }

      // Determine date range based on filters
      let startDate: string;
      let endDate: string;

      if (filters.period === 'today' && filters.date) {
        // Use specific date for "today"
        startDate = filters.date;
        endDate = filters.date;
      } else if (filters.period === 'custom' && filters.date) {
        // Use specific date for "custom" selection
        startDate = filters.date;
        endDate = filters.date;
      } else if (filters.period === 'range' && filters.date && filters.endDate) {
        // Use date range for "range" selection
        startDate = filters.date;
        endDate = filters.endDate;
      } else if (filters.period === '7d') {
        // Last 7 days
        const end = filters.date ? new Date(filters.date) : new Date();
        const start = new Date(end);
        start.setDate(start.getDate() - 6);
        endDate = end.toISOString().split('T')[0];
        startDate = start.toISOString().split('T')[0];
      } else if (filters.period === '30d') {
        // Last 30 days
        const end = filters.date ? new Date(filters.date) : new Date();
        const start = new Date(end);
        start.setDate(start.getDate() - 29);
        endDate = end.toISOString().split('T')[0];
        startDate = start.toISOString().split('T')[0];
      } else {
        // Fallback to today if no proper period is specified
        const today = filters.date || new Date().toISOString().split('T')[0];
        startDate = today;
        endDate = today;
      }


      // 🚀 RPC paginada — escapa do cap silencioso de 1000 linhas do PostgREST.
      // A função SQL aceita p_limit/p_offset; iteramos até a página voltar < PAGE_SIZE.
      // PAGE_SIZE bem abaixo do cap (1000) para garantir que nenhuma página seja truncada.
      const PAGE_SIZE = 500;
      const HARD_CAP_PAGES = 200; // teto: 100k campanhas

      const rpcParams = {
        p_project_id: filters.projectId && filters.projectId !== 'all' ? parseInt(filters.projectId) : null,
        p_start_date: startDate,
        p_end_date: endDate,
      };
      console.log('🔍 Chamando get_campaigns_aggregated (paginada) com:', {
        ...rpcParams,
        pageSize: PAGE_SIZE,
        period: filters.period,
      });

      const aggregatedCampaigns: any[] = [];
      let lastRpcError: any = null;
      for (let page = 0; page < HARD_CAP_PAGES; page++) {
        const { data: pageData, error: pageError } = await supabase.rpc('get_campaigns_aggregated', {
          ...rpcParams,
          p_limit: PAGE_SIZE,
          p_offset: page * PAGE_SIZE,
        });

        if (pageError) {
          lastRpcError = pageError;
          break;
        }
        if (!pageData || pageData.length === 0) break;

        aggregatedCampaigns.push(...pageData);
        if (pageData.length < PAGE_SIZE) break;
      }

      console.log('📊 RPC get_campaigns_aggregated retornou:', {
        count: aggregatedCampaigns.length,
        pages: Math.ceil(aggregatedCampaigns.length / PAGE_SIZE),
        error: lastRpcError,
        firstCampaign: aggregatedCampaigns[0],
      });

      if (lastRpcError) {
        console.error('❌ Error calling get_campaigns_aggregated RPC:', lastRpcError);
        console.warn('⚠️ RPC falhou - usando fallback para buscar campanhas diretamente');
        return await this.getCampaignsWithRevenueDirectFallback(filters, startDate, endDate);
      }

      if (aggregatedCampaigns.length === 0) {
        console.log('⚠️ RPC retornou vazio - usando fallback');
        return await this.getCampaignsWithRevenueDirectFallback(filters, startDate, endDate);
      }


      // Apply user filters before converting
      let filteredAggregatedCampaigns = aggregatedCampaigns;

      // Filter by user allowed project IDs
      if (filters.userProjectIds && filters.userProjectIds.length > 0) {
        filteredAggregatedCampaigns = filteredAggregatedCampaigns.filter((campaign: any) =>
          filters.userProjectIds!.includes(campaign.project_id)
        );
        console.log({
          total: aggregatedCampaigns.length,
          filtered: filteredAggregatedCampaigns.length
        });
      }

      // Filter by user allowed campaign IDs
      if (filters.userCampaignIds && filters.userCampaignIds.length > 0) {
        filteredAggregatedCampaigns = filteredAggregatedCampaigns.filter((campaign: any) =>
          filters.userCampaignIds!.includes(campaign.campaign_id)
        );
        console.log({
          total: filteredAggregatedCampaigns.length,
          filtered: filteredAggregatedCampaigns.length
        });
      }

      // Convert RPC results to Campaign format
      const activeCampaigns = filteredAggregatedCampaigns
        // 🛡️ NÃO FILTRAR campanhas com revenue/spend = 0, pois campanhas novas podem ter dados vazios temporariamente
        .map((campaign: any) => {
          // Validation: Check if campaign revenue seems unrealistic
          if (Number(campaign.aggregated_revenue) > 100000) {
            console.warn('⚠️ SUSPICIOUS CAMPAIGN REVENUE:', {
              campaignId: campaign.campaign_id,
              campaignName: campaign.campaign_name,
              aggregatedRevenue: campaign.aggregated_revenue,
              dateRange: `${startDate} to ${endDate}`,
              possibleIssue: 'Campaign revenue seems too high, check data quality'
            });
          }

          return {
            id: campaign.campaign_id.toString(),
            name: campaign.campaign_name,
            projectId: campaign.project_id?.toString() || '1',
            status: campaign.status === 'Active' || campaign.status === 'ENABLED' ? 'active' : 'paused',
            performance: this.calculatePerformance(Number(campaign.aggregated_revenue), Number(campaign.aggregated_spend)),
            investment: Number(campaign.aggregated_spend) || 0,
            revenue: Number(campaign.aggregated_revenue) || 0,
            commission: campaign.aggregated_commission && Number(campaign.aggregated_commission) > 0 ? Number(campaign.aggregated_commission) : undefined,
            roas: Number(campaign.roas) || 0,
            impressions: Number(campaign.aggregated_impressions) || 0,
            clicks: Number(campaign.aggregated_clicks) || 0,
            ctr: Number(campaign.ctr) || 0,
            startDate: campaign.start_date,
            endDate: campaign.end_date,
            utmCampaignValue: campaign.campaign_id,
            extractedUrl: undefined, // Campo não existe na tabela
            extractedDomain: undefined, // Campo não existe na tabela
            customGoal: campaign.custom_goal || undefined,
            statusSource: 'auto',
            userPausedAt: undefined,
            userPausedBy: undefined
          } as Campaign;
        })
        .sort((a, b) => (b.revenue || 0) - (a.revenue || 0));


      // 💾 SALVAR NO CACHE para próximas consultas (com tratamento de quota)
      try {
        const currentTimestamp = Date.now().toString();
        localStorage.setItem(cacheKey, JSON.stringify(activeCampaigns));
        localStorage.setItem(`${cacheKey}_timestamp`, currentTimestamp);
        console.log('✅ Cache salvo com sucesso:', { cacheKey, campaignsCount: activeCampaigns.length });
      } catch (storageError) {
        if (storageError instanceof Error && storageError.name === 'QuotaExceededError') {
          console.warn('⚠️ localStorage quota exceeded - limpando cache antigo...');

          // Limpar todos os caches de campanhas antigos
          try {
            const keysToRemove: string[] = [];
            for (let i = 0; i < localStorage.length; i++) {
              const key = localStorage.key(i);
              if (key && (key.startsWith('campaigns_optimized_') || key.startsWith('campaigns_with_revenue_'))) {
                keysToRemove.push(key);
              }
            }

            console.log(`🗑️ Removendo ${keysToRemove.length} caches antigos...`);
            keysToRemove.forEach(key => localStorage.removeItem(key));

            // Tentar salvar novamente após limpar
            const currentTimestamp = Date.now().toString();
            localStorage.setItem(cacheKey, JSON.stringify(activeCampaigns));
            localStorage.setItem(`${cacheKey}_timestamp`, currentTimestamp);
            console.log('✅ Cache salvo após limpeza');
          } catch (retryError) {
            console.error('❌ Ainda não foi possível salvar cache após limpeza:', retryError);
            // Não bloqueia a execução - continua sem cache
          }
        } else {
          console.error('❌ Erro ao salvar cache (não é quota):', storageError);
        }
      }

      return activeCampaigns;

    } catch (error) {
      console.error('Error in getCampaignsWithRevenueFiltered:', error);
      return [];
    }
  }
  
  // Calculate real trends based on historical data comparison
  private async calculateTrends(_filters?: {
    date?: string;
    endDate?: string;
    projectId?: string;
    period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
  }): Promise<{
    investment: number;
    revenue: number;
    profit: number;
    roas: number;
    roi: number;
  }> {
    try {
      // For now, return simple mock trends since this doesn't affect main calculations
      // In the future, implement proper historical trend calculation using daily_campaign_metrics
      const baseVariation = Math.random() * 20 - 10; // -10% to +10%
      
      return {
        investment: Number((baseVariation).toFixed(1)),
        revenue: Number((baseVariation + 5).toFixed(1)), // Revenue typically performs better
        profit: Number((baseVariation + 2).toFixed(1)),
        roas: Number((baseVariation / 2).toFixed(1)),
        roi: Number((baseVariation + 1).toFixed(1))
      };
    } catch (error) {
      console.error('Error calculating trends:', error);
      return { investment: 0, revenue: 0, profit: 0, roas: 0, roi: 0 };
    }
  }
  
  // Funções auxiliares
  private calculatePerformance(revenue: number, investment: number): 'excellent' | 'good' | 'average' | 'poor' {
    if (!investment || investment === 0) return 'average';
    const roas = (revenue / investment) * 100;
    
    if (roas >= 180) return 'excellent';
    if (roas >= 130) return 'good';
    if (roas >= 100) return 'average';
    return 'poor';
  }
  
  private calculateRoas(revenue: number, investment: number): number {
    if (!investment || investment === 0) return 0;
    return Math.round((revenue / investment) * 100 * 100) / 100; // Round to 2 decimal places
  }
  
  // Novo método para obter revenue por UTM campaign
  async getRevenueByUtmCampaign(startDate: string, endDate: string): Promise<any[]> {
    try {
      const { data, error } = await supabase
        .from('gam_metrics')
        .select('utm_campaign_value, revenue, revenue_converted, date')
        .gte('date', startDate)
        .lte('date', endDate)
        .order('date', { ascending: false });
      
      if (error) throw error;
      
      // Agrupar por UTM campaign usando centralized conversion logic
      const groupedData = (data || []).reduce((acc, item) => {
        const key = item.utm_campaign_value;
        if (!acc[key]) {
          acc[key] = {
            utmCampaignValue: key,
            totalRevenue: 0,
            dates: []
          };
        }

        const revenueUsd = Number(item.revenue) || 0;
        const revenueConverted = Number(item.revenue_converted) || 0;

        // GAM data: use 2-parameter version (no revenue_converted_revshare)
        const revenue = this.getRevenueValue(revenueUsd, revenueConverted);

        acc[key].totalRevenue += revenue;
        acc[key].dates.push({
          date: item.date,
          revenue: revenue
        });
        return acc;
      }, {} as any);
      
      return Object.values(groupedData).sort((a: any, b: any) => b.totalRevenue - a.totalRevenue);
    } catch (error) {
      console.error('Error fetching revenue by UTM campaign:', error);
      return [];
    }
  }

  // Get URL performance data
  async getUrlPerformance(projectId: string, days: number = 7): Promise<DatabaseUrlDailyPerformance[]> {
    try {
      const { data, error } = await supabase
        .from('url_daily_performance')
        .select('id, project_id, date, url, estimated_earnings_usd, page_views, ecpm, pmr, viewability, ctr')
        .eq('project_id', parseInt(projectId))
        .order('date', { ascending: false })
        .limit(days * 10); // Assuming ~10 URLs per day average

      if (error) throw error;
      return data || [];
    } catch (error) {
      console.error('Error fetching URL performance:', error);
      return [];
    }
  }

  // Get top performing URLs for a project
  async getTopUrls(projectId: string, days: number = 7, limit: number = 10): Promise<any[]> {
    try {
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(endDate.getDate() - days);

      const { data, error } = await supabase
        .from('url_daily_performance')
        .select('url, estimated_earnings_usd, page_views, ecpm, viewability')
        .eq('project_id', parseInt(projectId))
        .gte('date', startDate.toISOString().split('T')[0])
        .lte('date', endDate.toISOString().split('T')[0])
        .order('estimated_earnings_usd', { ascending: false })
        .limit(limit);

      if (error) throw error;
      
      // Aggregate by URL
      const urlAggregates = (data || []).reduce((acc, item) => {
        if (!acc[item.url]) {
          acc[item.url] = {
            url: item.url,
            totalRevenue: 0,
            totalPageViews: 0,
            avgEcpm: 0,
            avgViewability: 0,
            dataPoints: 0
          };
        }
        
        acc[item.url].totalRevenue += item.estimated_earnings_usd;
        acc[item.url].totalPageViews += item.page_views;
        acc[item.url].avgEcpm += item.ecpm;
        acc[item.url].avgViewability += item.viewability;
        acc[item.url].dataPoints += 1;
        
        return acc;
      }, {} as any);

      // Calculate averages and return sorted
      return Object.values(urlAggregates)
        .map((item: any) => ({
          ...item,
          avgEcpm: item.avgEcpm / item.dataPoints,
          avgViewability: item.avgViewability / item.dataPoints,
        }))
        .sort((a: any, b: any) => b.totalRevenue - a.totalRevenue);
        
    } catch (error) {
      console.error('Error fetching top URLs:', error);
      return [];
    }
  }

  // Refresh/sync data (placeholder for real-time updates)
  async refreshData(): Promise<void> {
    // In a real implementation, this might trigger data sync from Google Ads/GAM
  }

  // Public method to get current server date
  async getServerDate(): Promise<string> {
    return this.getCurrentServerDate();
  }
  
  // Force cache refresh
  clearServerDateCache(): void {
    this.currentServerDate = null;
  }

  // NEW: Get aggregated campaign metrics for a project (optimized for minimal egress)
  async getCampaignAggregatedMetrics(
    projectId: string,
    startDate: string,
    endDate?: string
  ): Promise<{
    totalRevenue: number;
    totalInvestment: number;
    campaignCount: number;
  }> {
    try {

      // Step 1: Get campaign IDs for this project
      const { data: projectCampaigns, error: campaignsError } = await supabase
        .from('campaigns')
        .select('campaign_id')
        .eq('project_id', projectId);

      if (campaignsError) {
        console.error('Error fetching campaigns:', campaignsError);
        return { totalRevenue: 0, totalInvestment: 0, campaignCount: 0 };
      }

      const campaignIds = (projectCampaigns || []).map(c => c.campaign_id).filter(Boolean);

      if (campaignIds.length === 0) {
        return { totalRevenue: 0, totalInvestment: 0, campaignCount: 0 };
      }

      // Step 2: Get aggregated metrics from daily_campaign_metrics with single query
      let metricsQuery = supabase
        .from('daily_campaign_metrics')
        .select('spend, revenue_converted_revshare')
        .in('campaign_id', campaignIds)
        .limit(50000); // Aumentar limite para evitar perda de dados

      // Apply date filters
      if (endDate && endDate !== startDate) {
        metricsQuery = metricsQuery
          .gte('date', startDate)
          .lte('date', endDate);
      } else {
        metricsQuery = metricsQuery.eq('date', startDate);
      }

      const { data: metrics, error: metricsError } = await metricsQuery;

      if (metricsError) {
        console.error('Error fetching campaign metrics:', metricsError);
        return { totalRevenue: 0, totalInvestment: 0, campaignCount: campaignIds.length };
      }

      // Step 3: Aggregate in a single pass
      const aggregated = (metrics || []).reduce(
        (acc, metric) => {
          acc.totalRevenue += this.getRevenueValue(
            0, // revenueUsd - not used
            metric.revenue_converted_revshare || 0, // Use revshare-adjusted revenue
            metric.revenue_converted_revshare // revenueConvertedRevshare
          );
          acc.totalInvestment += metric.spend || 0;
          return acc;
        },
        { totalRevenue: 0, totalInvestment: 0 }
      );

      console.log({
        projectId,
        campaignCount: campaignIds.length,
        totalRevenue: aggregated.totalRevenue,
        totalInvestment: aggregated.totalInvestment,
        dateRange: endDate ? `${startDate} to ${endDate}` : startDate
      });

      return {
        ...aggregated,
        campaignCount: campaignIds.length
      };

    } catch (error) {
      console.error('Error in getCampaignAggregatedMetrics:', error);
      return { totalRevenue: 0, totalInvestment: 0, campaignCount: 0 };
    }
  }

  // Currency conversion utility methods
  async formatCurrencyWithConversion(usdAmount: number): Promise<string> {
    try {
      return await currencyConversionService.convertAndFormat(usdAmount, 'USD', 'BRL');
    } catch (error) {
      console.error('Error converting currency:', error);
      // Fallback to standard BRL formatting
      return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
      }).format(usdAmount * 5.50); // Use default rate as fallback
    }
  }

  // Batch convert multiple USD values to BRL for display
  async batchConvertForDisplay(values: { [key: string]: number }): Promise<{ [key: string]: string }> {
    try {
      const result: { [key: string]: string } = {};
      
      for (const [key, value] of Object.entries(values)) {
        result[key] = await this.formatCurrencyWithConversion(value);
      }
      
      return result;
    } catch (error) {
      console.error('Error in batch currency conversion:', error);
      // Fallback to standard formatting
      const result: { [key: string]: string } = {};
      for (const [key, value] of Object.entries(values)) {
        result[key] = new Intl.NumberFormat('pt-BR', {
          style: 'currency',
          currency: 'BRL'
        }).format(value * 5.50);
      }
      return result;
    }
  }
  
  // Método NOVO para atualizar status da campanha com prioridade do usuário
  async updateCampaignStatus(utmCampaignId: string, newStatus: 'active' | 'paused', userId: string = 'system'): Promise<void> {
    try {
      const { error } = await supabase.rpc('user_update_campaign_status', {
        utm_campaign_id_param: utmCampaignId,
        new_status: newStatus,
        user_id_param: userId
      });
      
      if (error) {
        console.error('Error updating campaign status:', error);
        throw error;
      }
      
    } catch (error) {
      console.error('Error in updateCampaignStatus:', error);
      throw error;
    }
  }
  
  // Método para verificar se campanha tem status controlado pelo usuário
  async isStatusUserControlled(utmCampaignId: string): Promise<boolean> {
    try {
      const { data, error } = await supabase
        .from('campaigns')
        .select('status_source')
        .eq('utm_campaign_id', utmCampaignId)
        .single();
      
      if (error) throw error;
      return data?.status_source === 'user';
    } catch (error) {
      console.error('Error checking status control:', error);
      return false;
    }
  }

  // Get UTM campaign daily aggregated data
  async getUtmCampaignDailyData(projectId?: string, days: number = 7): Promise<DailyMetrics[]> {
    try {
      // Query to get aggregated data by date combining campaigns and gam_metrics
      let query = `
        SELECT 
          date_trunc('day', c.created_at)::date as date,
          COALESCE(SUM(c.spend), 0) as spend,
          COALESCE(SUM(gm.revenue), 0) as revenue,
          COALESCE(SUM(gm.revenue) - SUM(c.spend), 0) as profit,
          CASE 
            WHEN SUM(c.spend) > 0 THEN (SUM(gm.revenue) / SUM(c.spend)) * 100 
            ELSE 0 
          END as roas,
          COALESCE(SUM(c.clicks), 0) as clicks,
          COALESCE(SUM(c.impressions), 0) as impressions,
          CASE 
            WHEN SUM(c.impressions) > 0 THEN (SUM(c.clicks)::float / SUM(c.impressions)) * 100 
            ELSE 0 
          END as ctr,
          COALESCE(SUM(c.conversions), 0) as conversions,
          CASE 
            WHEN SUM(c.clicks) > 0 THEN SUM(c.spend) / SUM(c.clicks) 
            ELSE 0 
          END as cpc
        FROM campaigns c
        LEFT JOIN gam_metrics gm ON c.utm_campaign_id = gm.utm_campaign_value::text
        WHERE date_trunc('day', c.created_at)::date >= CURRENT_DATE - INTERVAL '${days} days'
      `;
      
      if (projectId) {
        query += ` AND c.project_id = ${projectId}`;
      }
      
      query += `
        GROUP BY date_trunc('day', c.created_at)::date
        ORDER BY date DESC
        LIMIT ${days}
      `;

      // Use real daily metrics instead of mock data
      return await this.getDailyMetrics({ projectId, days });
    } catch (error) {
      console.error('Error fetching UTM campaign daily data:', error);
      // Return empty data as fallback instead of mock data
      return [];
    }
  }

  // Get last updated timestamp from system_settings (GAM and Google Ads)
  async getLastDataUpdateTimestamp(): Promise<string | null> {
    try {
      // Use the SQL function to get the most recent timestamp
      const { data, error } = await supabase
        .rpc('get_last_data_update');

      if (error) {
        console.error('Error fetching system settings timestamps:', error);
        // Fallback to the old method if system_settings is not configured
        return await this.getLastDataUpdateTimestampFallback();
      }

      if (data && data.length > 0) {
        const result = data[0];
        // Return the most recent timestamp
        if (result.most_recent) {
          return result.most_recent;
        }
        
        // If no system_settings data, fallback
        return await this.getLastDataUpdateTimestampFallback();
      }

      return null;
    } catch (error) {
      console.error('Error in getLastDataUpdateTimestamp:', error);
      // Fallback to the old method
      return await this.getLastDataUpdateTimestampFallback();
    }
  }

  // Fallback method using daily_campaign_metrics (legacy)
  private async getLastDataUpdateTimestampFallback(): Promise<string | null> {
    try {
      const { data, error } = await supabase
        .from('daily_campaign_metrics')
        .select('updated_at')
        .order('updated_at', { ascending: false })
        .limit(1);

      if (error) {
        console.error('Error fetching last update timestamp from daily_campaign_metrics:', error);
        return null;
      }

      if (data && data.length > 0) {
        return data[0].updated_at;
      }

      return null;
    } catch (error) {
      console.error('Error in fallback timestamp fetch:', error);
      return null;
    }
  }

  // Get detailed system update timestamps (GAM and Google Ads separately)
  async getSystemUpdateTimestamps(): Promise<{
    gamLastUpdate: string | null;
    googleAdsLastUpdate: string | null;
    mostRecent: string | null;
  }> {
    try {
      // Fetch timestamps directly from system_settings table
      const { data, error } = await supabase
        .from('system_settings')
        .select('key, value')
        .in('key', ['gam_last_update', 'google_ads_last_update'])
        .not('value', 'is', null);

      if (error) {
        console.error('Error fetching system_settings timestamps:', error);
        return {
          gamLastUpdate: null,
          googleAdsLastUpdate: null,
          mostRecent: null
        };
      }

      let gamLastUpdate: string | null = null;
      let googleAdsLastUpdate: string | null = null;

      if (data) {
        // Process the timestamps
        data.forEach(row => {
          if (row.key === 'gam_last_update' && row.value) {
            gamLastUpdate = row.value;
          } else if (row.key === 'google_ads_last_update' && row.value) {
            googleAdsLastUpdate = row.value;
          }
        });
      }

      // Determine the most recent timestamp
      let mostRecent: string | null = null;
      if (gamLastUpdate && googleAdsLastUpdate) {
        // Compare both timestamps and return the most recent
        const gamDate = new Date(gamLastUpdate);
        const adsDate = new Date(googleAdsLastUpdate);
        mostRecent = gamDate > adsDate ? gamLastUpdate : googleAdsLastUpdate;
      } else if (gamLastUpdate) {
        mostRecent = gamLastUpdate;
      } else if (googleAdsLastUpdate) {
        mostRecent = googleAdsLastUpdate;
      }

      console.log({
        gamLastUpdate,
        googleAdsLastUpdate,
        mostRecent
      });

      return {
        gamLastUpdate,
        googleAdsLastUpdate,
        mostRecent
      };
    } catch (error) {
      console.error('Error in getSystemUpdateTimestamps:', error);
      return {
        gamLastUpdate: null,
        googleAdsLastUpdate: null,
        mostRecent: null
      };
    }
  }
}

// Singleton instance
export const supabaseDataService = new SupabaseDataService();

// React hooks for data fetching with filters
export const useSupabaseData = (filters?: {
  date?: string;
  endDate?: string;
  projectId?: string;
  period?: 'today' | 'yesterday' | '7d' | '30d' | 'custom' | 'range';
  userProjectIds?: number[];
  userCampaignIds?: string[];
}) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [dailyMetrics, setDailyMetrics] = useState<DailyMetrics[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);

  // Guarda contra respostas obsoletas: fetches sobrepostos com filtros diferentes
  // (ex.: troca de operador/projeto) não podem sobrescrever o resultado mais recente
  const requestSeqRef = useRef(0);

  const fetchData = async (currentFilters?: typeof filters) => {
    const requestId = ++requestSeqRef.current;
    try {
      setLoading(true);
      setError(null);

      const filterOptions = currentFilters || filters || {};

      // Continue with data fetching even if date is empty initially

      const [projectsData, campaignsData, metricsData, summaryData, lastUpdateData] = await Promise.all([
        supabaseDataService.getProjects(filterOptions),
        supabaseDataService.getCampaignsWithRevenue(filterOptions),
        supabaseDataService.getDailyMetrics(filterOptions),
        supabaseDataService.getSummary(filterOptions),
        supabaseDataService.getLastDataUpdateTimestamp()
      ]);

      if (requestId !== requestSeqRef.current) {
        console.log('⏭️ useSupabaseData - Resposta obsoleta descartada (novo fetch em andamento)');
        return;
      }

      console.log('📊 useSupabaseData - Dados carregados:', {
        projects: projectsData.length,
        campaigns: campaignsData.length,
        metrics: metricsData.length,
        summary: summaryData,
        filters: filterOptions
      });

      if (campaignsData.length === 0) {
        console.warn('⚠️ ATENÇÃO: Nenhuma campanha retornada! Verifique:', {
          filters: filterOptions,
          projectsCount: projectsData.length,
          cacheCleared: 'Pode ser cache ou filtros muito restritivos'
        });
      }

      setProjects(projectsData);
      setCampaigns(campaignsData);
      setDailyMetrics(metricsData);
      setSummary(summaryData);
      setLastUpdate(lastUpdateData);
    } catch (err) {
      if (requestId !== requestSeqRef.current) return;
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
    } finally {
      if (requestId === requestSeqRef.current) {
        setLoading(false);
      }
    }
  };

  // Memoize array stringifications to avoid infinite re-renders
  const userProjectIdsStr = useMemo(
    () => JSON.stringify(filters?.userProjectIds || []),
    [filters?.userProjectIds]
  );
  const userCampaignIdsStr = useMemo(
    () => JSON.stringify(filters?.userCampaignIds || []),
    [filters?.userCampaignIds]
  );

  useEffect(() => {
    console.log('🔄 useSupabaseData useEffect disparado:', {
      hasFilters: !!filters,
      hasDate: !!filters?.date,
      hasEndDate: !!filters?.endDate,
      projectId: filters?.projectId,
      userProjectIds: filters?.userProjectIds?.length,
      userCampaignIds: filters?.userCampaignIds?.length
    });
    fetchData();
  }, [
    filters?.date,
    filters?.endDate,
    filters?.projectId,
    filters?.period,
    userProjectIdsStr,
    userCampaignIdsStr
  ]);

  const refresh = (newFilters?: typeof filters) => {
    supabaseDataService.refreshData();
    fetchData(newFilters);
  };

  return {
    projects,
    campaigns,
    dailyMetrics,
    summary,
    loading,
    error,
    lastUpdate,
    refresh,
    refetch: fetchData
  };
};

interface ProjectData {
  project: Project | null;
  campaigns: Campaign[];
  dailyMetrics: DailyMetrics[];
  yesterdayData: any;
  historicalData: any[];
}

export const useProjectData = (projectId: string) => {
  const [projectData, setProjectData] = useState<ProjectData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!projectId) {
      setProjectData(null);
      setIsLoading(false);
      return;
    }

    const fetchProjectData = async () => {
      setIsLoading(true);
      try {
        const [project, campaigns, dailyMetrics] = await Promise.all([
          supabaseDataService.getProjectById(projectId),
          supabaseDataService.getCampaignsByProject(projectId),
          supabaseDataService.getDailyMetrics({ projectId, days: 30 })
        ]);

        // Generate historical data for charts
        const historicalData = dailyMetrics.map(metric => ({
          date: metric.date,
          dateFormatted: format(new Date(metric.date), 'dd/MM'),
          revenue: metric.revenue,
          investment: metric.investment,
          roas: metric.roas,
          roi: metric.roi
        }));

        // Get yesterday's real data from daily metrics
        const yesterdayMetrics = dailyMetrics.length > 1 ? dailyMetrics[dailyMetrics.length - 2] : null;
        const yesterdayData = yesterdayMetrics ? {
          investment: yesterdayMetrics.investment || 0,
          revenue: yesterdayMetrics.revenue || 0,
          roas: yesterdayMetrics.roas || 0,
          roi: yesterdayMetrics.roi || 0,
          grossProfit: (yesterdayMetrics.revenue || 0) - (yesterdayMetrics.investment || 0),
          netProfit: ((yesterdayMetrics.revenue || 0) - (yesterdayMetrics.investment || 0)) * 0.8
        } : {
          investment: 0,
          revenue: 0,
          roas: 0,
          roi: 0,
          grossProfit: 0,
          netProfit: 0
        };

        setProjectData({
          project,
          campaigns,
          dailyMetrics,
          yesterdayData,
          historicalData
        });
      } catch (error) {
        console.error('Error fetching project data:', error);
        setProjectData(null);
      } finally {
        setIsLoading(false);
      }
    };

    fetchProjectData();
  }, [projectId]);

  return { projectData, isLoading };
};

// Hook for UTM campaign daily data
export const useUtmCampaignData = (projectId?: string, days: number = 7) => {
  const [utmData, setUtmData] = useState<DailyMetrics[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchUtmData = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await supabaseDataService.getDailyMetrics({ projectId, days });
        setUtmData(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error occurred');
        console.error('Error fetching UTM campaign data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchUtmData();
  }, [projectId, days]);

  return { utmData, loading, error };
};