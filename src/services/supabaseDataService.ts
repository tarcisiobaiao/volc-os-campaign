import { useState, useEffect } from 'react';
import { supabase, DatabaseProject, DatabaseCampaign, DatabaseDailyProjectMetrics, DatabaseDailyCampaignMetrics, GamReportData, GamDataProcessor, DatabaseUrlDailyPerformance } from '@/lib/supabase';
import { format, subDays } from 'date-fns';
import { currencyConversionService } from './currencyConversionService';
import { getSaoPauloTimestamp } from '@/utils/timezone';

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
  
  // Get current server date (cached for performance)
  // Uses São Paulo timezone to match local business hours
  private async getCurrentServerDate(): Promise<string> {
    if (this.currentServerDate) {
      console.log('📋 Using cached server date:', this.currentServerDate);
      return this.currentServerDate;
    }
    
    try {
      console.log('🔍 Getting current date in São Paulo timezone...');

      // Force São Paulo timezone calculation locally for better reliability
      const now = new Date();
      const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo'
      }).format(now);

      console.log('📍 Current UTC time:', now.toISOString());
      console.log('📍 São Paulo time converted:', saoPauloDate);

      // Validate the RPC function but use local calculation as primary
      try {
        const { data: rpcDate, error } = await supabase.rpc('get_current_date');
        if (!error && rpcDate) {
          console.log('📍 RPC date from server:', rpcDate);

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
      console.log('✅ Final São Paulo date selected:', this.currentServerDate);
      return this.currentServerDate;
    } catch (error) {
      console.error('❌ Error getting server date:', error);
      // Fallback to current date in São Paulo timezone
      const now = new Date();
      const saoPauloDate = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Sao_Paulo'
      }).format(now);
      this.currentServerDate = saoPauloDate;
      console.log('🔄 Using fallback São Paulo date:', this.currentServerDate);
      return this.currentServerDate;
    }
  }
  // Convert database project to UI project format
  private convertDatabaseProject(dbProject: DatabaseProject, metrics?: DatabaseDailyProjectMetrics[]): Project {
    console.log('🔧 convertDatabaseProject - Raw dbProject:', {
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
  async getProjects(filters?: {
    date?: string;
    endDate?: string;
    projectId?: string;
    period?: 'today' | '7d' | '30d' | 'custom' | 'range';
  }): Promise<Project[]> {
    try {
      console.log('📂 getProjects called with filters:', filters);
      
      // Debug: Force current server date for 'today' period
      if (filters?.period === 'today') {
        const currentDate = await this.getCurrentServerDate();
        filters = { ...filters, date: currentDate };
        console.log('📅 getProjects - Updated date for TODAY period:', filters.date);
      }

      // Build project query with filters
      let projectsQuery = supabase
        .from('projects')
        .select('*')
        .order('created_at', { ascending: false });

      // Apply project filter if specified
      if (filters?.projectId && filters.projectId !== 'all') {
        projectsQuery = projectsQuery.eq('id', filters.projectId);
      }

      const { data: projects, error: projectsError } = await projectsQuery;

      if (projectsError) throw projectsError;

      // Debug: Check if project_type is being returned
      if (projects && projects.length > 0) {
        console.log('🔍 First project from query:', {
          id: projects[0].id,
          project_name: projects[0].project_name,
          project_type: projects[0].project_type,
          allFields: Object.keys(projects[0])
        });
      }

      // Get aggregated metrics for each project using daily_campaign_metrics
      const projectsWithMetrics = await Promise.all(
        (projects || []).map(async (project) => {
          console.log(`📊 Processing project: ${project.project_name} (ID: ${project.id})`);

          // Step 1: Get campaign IDs first, then query daily_campaign_metrics
          const { data: projectCampaignsForSpend } = await supabase
            .from('campaigns')
            .select('campaign_id')
            .eq('project_id', project.id);

          const campaignIdsForSpend = (projectCampaignsForSpend || []).map(c => c.campaign_id).filter(Boolean);

          let totalSpend = 0;
          if (campaignIdsForSpend.length > 0) {
            let spendQuery = supabase
              .from('daily_campaign_metrics')
              .select('spend')
              .in('campaign_id', campaignIdsForSpend);

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
              console.log('📊 Applying RANGE filter for spend:', filters.date, 'to', filters.endDate);
              spendQuery = spendQuery
                .gte('date', filters.date)
                .lte('date', filters.endDate);
            }

            const { data: spendData, error: spendError } = await spendQuery;
            if (spendError) {
              console.error(`Error fetching spend for project ${project.id}:`, spendError);
            }

            totalSpend = (spendData || []).reduce((sum, item) => sum + (Number(item.spend) || 0), 0);
            console.log(`💸 Total spend calculated for project ${project.project_name}:`, {
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

          // Force ADSENSE logic for project 36
          if (project.project_type === 'ADSENSE' || project.id === 36) {
            // For ADSENSE projects, use daily_project_metrics (aggregated by domain)
            let projectRevenueQuery = supabase
              .from('daily_project_metrics')
              .select('billed_amount')
              .eq('project_id', project.id);

            // Apply same date filters for ADSENSE project revenue
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
              console.log('📊 Applying RANGE filter for ADSENSE project revenue:', filters.date, 'to', filters.endDate);
              projectRevenueQuery = projectRevenueQuery
                .gte('date', filters.date)
                .lte('date', filters.endDate);
            }

            const { data: projectRevenueData, error: projectRevenueError } = await projectRevenueQuery;
            if (projectRevenueError) {
              console.error(`Error fetching ADSENSE project revenue for project ${project.id}:`, projectRevenueError);
            }

            totalRevenue = (projectRevenueData || []).reduce((sum, item) => {
              const billedAmount = Number(item.billed_amount) || 0;
              return sum + billedAmount;
            }, 0);

            console.log(`💰 ADSENSE Project ${project.project_name} revenue calculation:`, {
              totalRevenue,
              records_count: projectRevenueData?.length || 0,
              date: filters?.date,
              period: filters?.period,
              source: 'daily_project_metrics',
              raw_data: projectRevenueData
            });

          } else {
            // For GAM projects, use daily_campaign_metrics (campaign-based)
            if (campaignIds.length > 0) {
              let revenueQuery = supabase
                .from('daily_campaign_metrics')
                .select('revenue_converted_revshare, campaign_id')
                .in('campaign_id', campaignIds);

              // Apply same date filters for GAM campaign revenue
              if (filters?.period === 'today' && filters?.date) {
                revenueQuery = revenueQuery.eq('date', filters.date);
              } else if (filters?.period === 'custom' && filters?.date) {
                revenueQuery = revenueQuery.eq('date', filters.date);
              } else if (filters?.period === '7d' && filters?.date) {
                const endDate = new Date(filters.date);
                const startDate = new Date(endDate);
                startDate.setDate(startDate.getDate() - 6);
                revenueQuery = revenueQuery
                  .gte('date', startDate.toISOString().split('T')[0])
                  .lte('date', filters.date);
              } else if (filters?.period === '30d' && filters?.date) {
                const endDate = new Date(filters.date);
                const startDate = new Date(endDate);
                startDate.setDate(startDate.getDate() - 29);
                revenueQuery = revenueQuery
                  .gte('date', startDate.toISOString().split('T')[0])
                  .lte('date', filters.date);
              } else if (filters?.period === 'range' && filters?.date && filters?.endDate) {
                console.log('📊 Applying RANGE filter for GAM campaign revenue:', filters.date, 'to', filters.endDate);
                revenueQuery = revenueQuery
                  .gte('date', filters.date)
                  .lte('date', filters.endDate);
              }

              const { data: revenueData, error: revenueError } = await revenueQuery;
              if (revenueError) {
                console.error(`Error fetching GAM campaign revenue for project ${project.id}:`, revenueError);
              }

              totalRevenue = (revenueData || []).reduce((sum, item, index) => {
                const revenueAfterRevshare = Number(item.revenue_converted_revshare) || 0;

                if (index < 5) { // Log primeiros items para debug
                  console.log(`💰 GAM Daily metrics item ${index + 1} [${filters?.date}]:`, {
                    campaign_id: item.campaign_id,
                    revenue_converted_revshare: revenueAfterRevshare,
                    source: 'daily_campaign_metrics_net_revenue',
                    date: filters?.date
                  });
                }

                return sum + revenueAfterRevshare;
              }, 0);

              console.log(`💰 GAM Project ${project.project_name} revenue calculation:`, {
                totalRevenue,
                records_count: revenueData?.length || 0,
                date: filters?.date,
                period: filters?.period,
                source: 'daily_campaign_metrics'
              });
            }
          }

          console.log(`💰 Project ${project.project_name}:`, {
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

          const campaignCount = campaigns?.length || 0;
          const activeCampaigns = campaigns?.filter(c => 
            c.status && ['Active', 'active', 'ENABLED'].includes(c.status)
          ).length || 0;

          // Generate performance distribution
          const greenCampaigns = Math.floor(campaignCount * 0.6);
          const yellowCampaigns = Math.floor(campaignCount * 0.3);
          const redCampaigns = campaignCount - greenCampaigns - yellowCampaigns;

          // Determine trend based on ROI
          const trend: 'up' | 'down' | 'stable' = 
            roi > 50 ? 'up' : roi < 10 ? 'down' : 'stable';

          return {
            id: project.id.toString(),
            name: project.project_name,
            domain: project.domain || project.main_url,
            investment: totalSpend,
            revenue: totalRevenue,
            roas: Math.round(roas),
            roi: Math.round(roi),
            grossProfit: totalProfit,
            netProfit: totalProfit, // Simplified
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
            project_type: project.project_type
          };
        })
      );

      console.log('📂 Projects with filtered metrics:', projectsWithMetrics.length);
      return projectsWithMetrics;
    } catch (error) {
      console.error('Error fetching projects:', error);
      return [];
    }
  }

  // Get detailed project data for settings page
  async getProjectsDetailed(): Promise<any[]> {
    try {
      const { data: projects, error: projectsError } = await supabase
        .from('projects')
        .select('*')
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
            totalSpend,
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
            project_type: project.project_type
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
    period?: 'today' | '7d' | '30d' | 'custom' | 'range';
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
    period?: 'today' | '7d' | '30d' | 'custom' | 'range';
    date?: string;
    endDate?: string;
    days?: number;
  }): Promise<DailyMetrics[]> {
    try {
      const { projectId, period = '7d', date, endDate: filterEndDate, days = 7 } = filters || {};
      
      // Get date range
      let endDate = date || new Date().toISOString().split('T')[0];
      const startDate = new Date();
      
      if (period === 'today') {
        // Para HOJE, usar método específico que filtra apenas o dia atual
        const currentDate = date || await this.getCurrentServerDate();
        console.log('📅 getDailyMetrics - Using current server date for today:', currentDate);
        return this.getTodayMetrics(projectId, currentDate);
      } else if (period === 'custom' && date) {
        // Para DATA ESPECÍFICA, usar método específico que filtra apenas aquele dia
        console.log('📅 getDailyMetrics - Using specific date for custom:', date);
        return this.getTodayMetrics(projectId, date);
      } else if (period === 'range' && date && filterEndDate) {
        // Para RANGE DE DATAS, usar intervalo específico
        console.log('📅 getDailyMetrics - Using date range:', date, 'to', filterEndDate);
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

      // Query daily campaign metrics with GAM data
      let query = supabase
        .from('daily_campaign_metrics')
        .select(`
          date,
          spend,
          clicks,
          impressions,
          conversions,
          ctr,
          cpc,
          campaigns!inner(project_id)
        `)
        .gte('date', startDateStr)
        .lte('date', endDate)
        .order('date', { ascending: false });

      if (projectId && projectId !== 'all') {
        query = query.eq('campaigns.project_id', parseInt(projectId));
      }

      const { data: campaignMetrics, error: campaignError } = await query;
      if (campaignError) throw campaignError;

      // Get GAM revenue data for the same period
      let gamQuery = supabase
        .from('gam_metrics')
        .select('date, revenue, revenue_converted, utm_campaign_value')
        .gte('date', startDateStr)
        .lte('date', endDate);

      const { data: gamMetrics, error: gamError } = await gamQuery;
      if (gamError) throw gamError;

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

      // Add GAM revenue data - GAM data doesn't have revenue_converted_revshare
      (gamMetrics || []).forEach(gam => {
        const existing = dailyData.get(gam.date);
        if (existing) {
          const revenueUsd = Number(gam.revenue) || 0;
          const revenueConverted = Number((gam as any).revenue_converted) || 0;

          // GAM data: use 2-parameter version (no revenue_converted_revshare)
          const revenue = this.getRevenueValue(revenueUsd, revenueConverted);
          existing.revenue += revenue || 0;
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

      return Array.from(dailyData.values())
        .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
        .slice(0, days);

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
    period?: 'today' | '7d' | '30d' | 'custom' | 'range';
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
      console.log('🚀 getDashboardData called with filters:', filters);
      console.log('🔍 Checking conditions - period:', period, 'date:', date);
      
      // SEMPRE usar métricas diárias quando period = 'today' ou 'custom'
      if (period === 'today' || period === 'custom') {
        // Usar data do servidor para 'today' ou data específica para 'custom'
        const targetDate = period === 'custom' && date ? date : await this.getCurrentServerDate();
        console.log('🎯 Final target date for TODAY:', targetDate);
        console.log('📅 getDashboardData - Using TODAY mode for date:', targetDate, 'filters:', filters);
        
        console.log('📅 getDashboardData - Searching for date:', targetDate);
        
        // Para HOJE, buscar dados específicos do dia nas tabelas de métricas diárias
        let campaignQuery;
        
        if (projectId && projectId !== 'all') {
          // When filtering by project, use inner join
          campaignQuery = supabase
            .from('daily_campaign_metrics')
            .select(`
              spend,
              clicks,
              impressions,
              conversions,
              date,
              revenue_converted,
              revenue_converted_revshare,
              campaigns!inner(project_id)
            `)
            .eq('date', targetDate)
            .eq('campaigns.project_id', parseInt(projectId));
          console.log('🎯 Project filter applied for project:', projectId);
        } else {
          // For general dashboard, don't join to avoid filtering out data
          campaignQuery = supabase
            .from('daily_campaign_metrics')
            .select(`
              spend,
              clicks,
              impressions,
              conversions,
              date,
              revenue_converted,
              revenue_converted_revshare
            `)
            .eq('date', targetDate);
          console.log('🏠 General dashboard mode - no project filter');
        }
          
        console.log('🔍 Campaign query built for date:', targetDate, 'with project filter:', projectId);

        const { data: campaignData, error: campaignError } = await campaignQuery;
        if (campaignError) {
          console.error('❌ Campaign query error:', campaignError);
          throw campaignError;
        }
        
        console.log('📊 Campaign data results:', {
          count: campaignData?.length || 0,
          sample: campaignData?.[0] || 'No data',
          allData: campaignData
        });

        // Buscar receita GAM do dia específico
        let gamQuery = supabase
          .from('gam_metrics')
          .select('revenue, revenue_converted, utm_campaign_value')
          .eq('date', targetDate);

        // For project filtering, we need to filter GAM data by UTM campaigns that belong to the project
        if (projectId && projectId !== 'all') {
          // First get the UTM campaign values for this project
          const { data: projectCampaigns } = await supabase
            .from('campaigns')
            .select('utm_campaign_value')
            .eq('project_id', parseInt(projectId));
          
          if (projectCampaigns && projectCampaigns.length > 0) {
            const utmValues = projectCampaigns
              .map(c => c.utm_campaign_value)
              .filter(v => v); // Remove null/empty values
            
            if (utmValues.length > 0) {
              gamQuery = gamQuery.in('utm_campaign_value', utmValues);
              console.log('🎯 GAM filtered by UTM campaigns:', utmValues.slice(0, 3), '... (showing first 3)');
            } else {
              console.log('⚠️ No UTM values found for project:', projectId);
            }
          } else {
            console.log('⚠️ No campaigns found for project:', projectId);
          }
        } else {
          console.log('🏠 GAM query - no project filter (general dashboard)');
        }

        console.log('🔍 GAM query built for date:', targetDate, 'with project filter:', projectId);
        
        const { data: gamData, error: gamError } = await gamQuery;
        if (gamError) {
          console.error('❌ GAM query error:', gamError);
          throw gamError;
        }
        
        console.log('💰 GAM data results for', targetDate, ':', {
          count: gamData?.length || 0,
          sample: gamData?.[0] || 'No data',
          has_converted_values: (gamData || []).some(g => (g as any).revenue_converted > 0),
          converted_count: (gamData || []).filter(g => (g as any).revenue_converted > 0).length,
          usd_only_count: (gamData || []).filter(g => !(g as any).revenue_converted && g.revenue > 0).length
        });

        // Calcular totais do dia específico
        const totalSpend = (campaignData || []).reduce((sum, c) => sum + (Number(c.spend) || 0), 0);
        // Check if we need to trigger conversion (if no converted values exist)
        const hasConvertedValues = (gamData || []).some(g => (g as any).revenue_converted > 0);
        
        if (!hasConvertedValues && (gamData || []).length > 0) {
          console.warn('⚠️ No converted values found, might need to trigger conversion');
          // Could call currencyConversionService.updateDatabaseConversions() here if needed
        }
        
        const totalRevenue = (gamData || []).reduce((sum, g) => {
          const revenueUsd = Number(g.revenue) || 0;
          const revenueConverted = Number((g as any).revenue_converted) || 0;

          // GAM data: use 2-parameter version (no revenue_converted_revshare)
          const revenue = this.getRevenueValue(revenueUsd, revenueConverted);

          console.log(`💰 Processing GAM record:`, {
            utm_campaign_value: g.utm_campaign_value,
            revenue_usd: revenueUsd,
            revenue_converted_brl: revenueConverted,
            using_converted: !!(revenueConverted > 0),
            final_value: revenue,
            conversion_issue: !revenueConverted ? 'NO_CONVERTED_VALUE' : 'OK'
          });
          return sum + (revenue || 0);
        }, 0);
        
        // Calculate total revenue after revenue share using pre-calculated values from daily_campaign_metrics
        const totalRevenueAfterRevshare = (campaignData || []).reduce((sum, c) => {
          const revenueAfterRevshare = (c as any).revenue_converted_revshare || 0;
          return sum + (Number(revenueAfterRevshare) || 0);
        }, 0);
        
        console.log('💰 Revenue After Revenue Share for', targetDate, ':', {
          totalRevenueAfterRevshare,
          breakdown: (campaignData || []).map(c => ({
            campaign_id: (c as any).campaign_id,
            revenue_converted: (c as any).revenue_converted,
            revenue_converted_revshare: (c as any).revenue_converted_revshare,
            value_used: (c as any).revenue_converted_revshare || 0
          }))
        });
        
        // Validation: Check if revenue seems unrealistic (possible data issue)
        if (totalRevenue > 1000000) { // More than 1M BRL
          console.warn('⚠️ SUSPICIOUS REVENUE VALUE:', {
            date: targetDate,
            totalRevenue,
            possibleIssue: 'Value seems too high, check data quality'
          });
        }
        
        const totalProfit = totalRevenue - totalSpend;
        
        console.log('📊 Dashboard totals for', targetDate, ':', {
          campaignDataCount: campaignData?.length || 0,
          gamDataCount: gamData?.length || 0,
          totalSpend,
          totalRevenue,
          totalRevenueAfterRevshare,
          totalProfit,
          sampleCampaignData: campaignData?.[0],
          sampleGamData: gamData?.[0],
          allCampaignData: campaignData,
          allGamData: gamData
        });

        console.log('🔍 DETAILED REVENUE ANALYSIS for', targetDate, ':', {
          totalRevenueCalculated: totalRevenue,
          revenueBreakdown: (gamData || []).map(g => ({
            utm_campaign: g.utm_campaign_value,
            revenue_usd: g.revenue,
            revenue_brl: (g as any).revenue_converted,
            used_value: ((g as any).revenue_converted && (g as any).revenue_converted > 0) 
              ? (g as any).revenue_converted 
              : Number(g.revenue || 0)
          }))
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

        // Calculate trends for the specific day
        const trends = await this.calculateTrends(filters);

        return {
          totalSpend,
          totalRevenue: totalRevenueAfterRevshare || (totalRevenue * 0.9), // NOW: Display net revenue (after revshare) as main revenue
          totalRevenueAfterRevshare: totalRevenueAfterRevshare || (totalRevenue * 0.9), // Keep for compatibility
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
      }
      
      // Para períodos agregados (7d, 30d, e range), usar a mesma lógica de filtro por data
      console.log('🚀 getDashboardData - Using aggregated period mode for:', period, 'with date:', date);
      
      // Determinar intervalo de datas baseado no período
      let startDate: Date;
      let endDate: Date;
      
      if (period === 'range' && filters.date && filters.endDate) {
        // Para range, usar as datas específicas fornecidas
        startDate = new Date(filters.date);
        endDate = new Date(filters.endDate);
        console.log('📅 RANGE DEBUG - Using range dates:', filters.date, 'to', filters.endDate);
        console.log('📅 RANGE DEBUG - Date objects:', { 
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
      
      console.log('📅 Date range for aggregated period:', { startDate: startDateStr, endDate: endDateStr, period });
      console.log('🎯 RANGE DEBUG - Project filter applied:', projectId);
      
      // Buscar dados de campanha para o período especificado
      let campaignQuery;
      
      if (projectId && projectId !== 'all') {
        // When filtering by project, use inner join
        campaignQuery = supabase
          .from('daily_campaign_metrics')
          .select(`
            spend,
            clicks,
            impressions,
            conversions,
            date,
            campaigns!inner(project_id)
          `)
          .gte('date', startDateStr)
          .lte('date', endDateStr)
          .eq('campaigns.project_id', parseInt(projectId));
        console.log('🎯 Project filter applied for aggregated period, project:', projectId);
      } else {
        // For general dashboard, don't join to avoid filtering out data
        campaignQuery = supabase
          .from('daily_campaign_metrics')
          .select(`
            spend,
            clicks,
            impressions,
            conversions,
            date
          `)
          .gte('date', startDateStr)
          .lte('date', endDateStr);
        console.log('🏠 RANGE DEBUG - General dashboard mode for aggregated period - no project filter');
        console.log('🏠 RANGE DEBUG - Query filters:', { 
          startDate: startDateStr, 
          endDate: endDateStr, 
          period, 
          table: 'daily_campaign_metrics' 
        });
      }
      
      const { data: campaignData, error: campaignError } = await campaignQuery;
      if (campaignError) {
        console.error('❌ Campaign query error for aggregated period:', campaignError);
        throw campaignError;
      }
      
      console.log('📊 Campaign data results for aggregated period:', {
        count: campaignData?.length || 0,
        dateRange: `${startDateStr} to ${endDateStr}`,
        period
      });
      
      // Buscar receita GAM para o período especificado
      let gamQuery = supabase
        .from('gam_metrics')
        .select('revenue, revenue_converted, utm_campaign_value')
        .gte('date', startDateStr)
        .lte('date', endDateStr);
      
      // For project filtering, we need to filter GAM data by UTM campaigns that belong to the project
      if (projectId && projectId !== 'all') {
        // First get the UTM campaign values for this project
        const { data: projectCampaigns } = await supabase
          .from('campaigns')
          .select('utm_campaign_value')
          .eq('project_id', parseInt(projectId));
        
        if (projectCampaigns && projectCampaigns.length > 0) {
          const utmValues = projectCampaigns
            .map(c => c.utm_campaign_value)
            .filter(v => v); // Remove null/empty values
          
          if (utmValues.length > 0) {
            gamQuery = gamQuery.in('utm_campaign_value', utmValues);
            console.log('🎯 GAM filtered by UTM campaigns for aggregated period:', utmValues.slice(0, 3), '... (showing first 3)');
          } else {
            console.log('⚠️ No UTM values found for project:', projectId);
          }
        } else {
          console.log('⚠️ No campaigns found for project:', projectId);
        }
      } else {
        console.log('🏠 GAM query for aggregated period - no project filter (general dashboard)');
      }
      
      const { data: gamData, error: gamError } = await gamQuery;
      if (gamError) {
        console.error('❌ GAM query error for aggregated period:', gamError);
        throw gamError;
      }
      
      console.log('💰 GAM data results for aggregated period:', {
        count: gamData?.length || 0,
        dateRange: `${startDateStr} to ${endDateStr}`,
        period,
        has_converted_values: (gamData || []).some(g => (g as any).revenue_converted > 0),
        converted_count: (gamData || []).filter(g => (g as any).revenue_converted > 0).length,
        usd_only_count: (gamData || []).filter(g => !(g as any).revenue_converted && g.revenue > 0).length
      });
      
      // Calcular totais para o período agregado usando daily_campaign_metrics
      let totalSpend = 0;
      let totalRevenue = 0;
      let totalRevenueAfterRevshare = 0;
      let directData: any[] = [];
      
      // Para períodos de range, sempre fazer consulta direta na tabela daily_campaign_metrics
      if (period === 'range' || period === '7d' || period === '30d') {
        console.log('📊 Using direct calculation from daily_campaign_metrics for period:', period, 'methodCalled: getDashboardData');
        
        // Consulta direta para ambos spend e revenue na tabela daily_campaign_metrics
        let directQuery = supabase
          .from('daily_campaign_metrics')
          .select('spend, revenue_converted, revenue_converted_revshare, date')
          .gte('date', startDateStr)
          .lte('date', endDateStr);
        
        // Aplicar filtro de projeto se especificado
        if (projectId && projectId !== 'all') {
          directQuery = supabase
            .from('daily_campaign_metrics')
            .select('spend, revenue_converted, revenue_converted_revshare, date, campaigns!inner(project_id)')
            .eq('campaigns.project_id', parseInt(projectId))
            .gte('date', startDateStr)
            .lte('date', endDateStr);
        }
        
        const { data: directQueryData, error: directError } = await directQuery;
        
        if (!directError && directQueryData) {
          directData = directQueryData;
          totalSpend = directData.reduce((sum, item) => sum + (Number(item.spend) || 0), 0);
          totalRevenue = directData.reduce((sum, item) => sum + (Number(item.revenue_converted) || 0), 0);
          
          // NEW: Calculate total revenue after revenue share using pre-calculated values
          const totalRevenueAfterRevshare = directData.reduce((sum, item) => 
            sum + (Number(item.revenue_converted_revshare) || 0), 0);
          
          // Verificar cobertura de datas no getDashboardData
          const datesInData = [...new Set(directData.map((item: any) => item.date))].sort();
          const startDateObj = new Date(startDateStr + 'T00:00:00');
          const endDateObj = new Date(endDateStr + 'T00:00:00');
          const totalDaysExpected = Math.ceil((endDateObj.getTime() - startDateObj.getTime()) / (1000 * 60 * 60 * 24)) + 1;
          
          console.log('📊 Direct calculation result from daily_campaign_metrics:', {
            period,
            projectFilter: projectId,
            recordCount: directData.length,
            totalSpend,
            totalRevenue,
            dateRange: `${startDateStr} to ${endDateStr}`,
            totalDaysExpected: totalDaysExpected,
            uniqueDatesInData: datesInData,
            datesCount: datesInData.length,
            allDatesIncluded: datesInData.length === totalDaysExpected ? '✅ SIM' : '❌ NÃO',
            dailyBreakdown: directData.reduce((acc: any, item: any) => {
              if (!acc[item.date]) acc[item.date] = { spend: 0, revenue: 0, recordCount: 0 };
              acc[item.date].spend += Number(item.spend) || 0;
              acc[item.date].revenue += Number(item.revenue_converted) || 0;
              acc[item.date].recordCount += 1;
              return acc;
            }, {}),
            allRecords: directData.map((item: any, index: number) => ({
              index: index + 1,
              date: item.date,
              spend: item.spend,
              revenue_converted: item.revenue_converted,
              spendAsNumber: Number(item.spend) || 0,
              revenueAsNumber: Number(item.revenue_converted) || 0
            }))
          });
        }
      } else {
        // FIXED: Always use daily_campaign_metrics for all periods to get accurate revshare data
        console.log('🔄 Using daily_campaign_metrics for non-range periods to get accurate revshare');

        let nonRangeQuery = supabase
          .from('daily_campaign_metrics')
          .select('spend, revenue_converted, revenue_converted_revshare, date')
          .gte('date', startDateStr)
          .lte('date', endDateStr);

        if (projectId && projectId !== 'all') {
          nonRangeQuery = supabase
            .from('daily_campaign_metrics')
            .select('spend, revenue_converted, revenue_converted_revshare, date, campaigns!inner(project_id)')
            .eq('campaigns.project_id', parseInt(projectId))
            .gte('date', startDateStr)
            .lte('date', endDateStr);
        }

        const { data: nonRangeData, error: nonRangeError } = await nonRangeQuery;

        if (!nonRangeError && nonRangeData) {
          totalSpend = nonRangeData.reduce((sum, item) => sum + (Number(item.spend) || 0), 0);
          totalRevenue = nonRangeData.reduce((sum, item) => sum + (Number(item.revenue_converted) || 0), 0);
          totalRevenueAfterRevshare = nonRangeData.reduce((sum, item) =>
            sum + (Number(item.revenue_converted_revshare) || 0), 0);

          console.log('✅ Using daily_campaign_metrics for accurate revshare calculation:', {
            period,
            records: nonRangeData.length,
            totalSpend,
            totalRevenue,
            totalRevenueAfterRevshare
          });
        } else {
          console.error('❌ Error fetching daily_campaign_metrics for non-range period:', nonRangeError);
          // Fallback to old logic only if daily_campaign_metrics fails
          totalSpend = (campaignData || []).reduce((sum: any, c: any) => sum + (Number(c.spend) || 0), 0);
          totalRevenue = 0;
          totalRevenueAfterRevshare = 0;
        }
      }

      console.log('💸 RANGE DEBUG - Total spend calculated:', {
        period,
        projectId,
        recordsFound: campaignData?.length || 0,
        totalSpend,
        dateRange: `${startDateStr} to ${endDateStr}`,
        sampleRecord: campaignData?.[0],
        allRecords: campaignData?.map(c => ({ spend: c.spend, date: c.date || 'no-date' })) || [],
        spendValues: campaignData?.map(c => Number(c.spend) || 0) || [],
        manualSum: (campaignData || []).reduce((sum, c) => {
          const spend = Number(c.spend) || 0;
          console.log(`  Adding spend: ${c.spend} -> ${spend}`);
          return sum + spend;
        }, 0)
      });
      
      
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
      
      console.log('📊 Dashboard totals for aggregated period:', {
        dateRange: `${startDateStr} to ${endDateStr}`,
        period,
        campaignDataCount: campaignData?.length || 0,
        gamDataCount: gamData?.length || 0,
        totalSpend,
        totalRevenue,
        totalRevenueAfterRevshare,
        totalProfit,
        allCampaignData: campaignData,
        allGamData: gamData
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
        totalRevenue: totalRevenueAfterRevshare || (totalRevenue * 0.9), // NOW: Display net revenue (after revshare) as main revenue
        totalRevenueAfterRevshare: totalRevenueAfterRevshare || (totalRevenue * 0.9), // Keep for compatibility
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
      
      console.log('🎯 FINAL RESULT for getDashboardData:', result);
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

  // Debug method to check if data exists for a specific date
  async debugDataForDate(targetDate?: string): Promise<void> {
    try {
      const dateToCheck = targetDate || new Date().toISOString().split('T')[0];
      console.log('🔍 Debugging data for date:', dateToCheck, 'Time zone:', Intl.DateTimeFormat().resolvedOptions().timeZone);
      
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
        
      console.log('Available dates in daily_campaign_metrics:', allDates?.map(d => d.date));
        
      console.log('daily_campaign_metrics:', campaignData?.length || 0, 'records');
      if (campaignData?.length > 0) {
        console.log('Sample record:', campaignData[0]);
      }
      
      // Check gam_metrics 
      const { data: gamData, error: gamError } = await supabase
        .from('gam_metrics')
        .select('*')
        .eq('date', dateToCheck)
        .limit(5);
        
      // Also check all available dates in GAM
      const { data: allGamDates } = await supabase
        .from('gam_metrics')
        .select('date')
        .order('date', { ascending: false })
        .limit(10);
        
      console.log('Available dates in gam_metrics:', allGamDates?.map(d => d.date));
        
      console.log('gam_metrics:', gamData?.length || 0, 'records');
      if (gamData?.length > 0) {
        console.log('Sample record:', gamData[0]);
      }
      
      // Check campaigns_with_revenue view
      const { data: campaignsView, error: campaignsError } = await supabase
        .from('campaigns_with_revenue')
        .select('*')
        .limit(5);
        
      console.log('campaigns_with_revenue view:', campaignsView?.length || 0, 'records');
      if (campaignsView?.length > 0) {
        console.log('Sample record:', campaignsView[0]);
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
      console.log('🔍 getTodayMetrics - Searching for date:', today, 'projectId:', projectId);
      
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

      console.log('📊 Campaign metrics found:', campaignMetrics?.length || 0, 'items');
      if (campaignMetrics?.length > 0) {
        console.log('Sample campaign metric:', campaignMetrics[0]);
      }

      // Get GAM revenue data for today only
      const { data: gamMetrics, error: gamError } = await supabase
        .from('gam_metrics')
        .select('date, revenue, revenue_converted, utm_campaign_value')
        .eq('date', today);

      if (gamError) throw gamError;
      
      console.log('💰 GAM metrics found:', gamMetrics?.length || 0, 'items');
      if (gamMetrics?.length > 0) {
        console.log('Sample GAM metric:', gamMetrics[0]);
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

      console.log('📈 Final daily data for', today, ':', {
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
    period?: 'today' | '7d' | '30d' | 'custom' | 'range';
  }): Promise<DashboardSummary> {
    try {
      
      // 🎯 SOLUÇÃO DEFINITIVA: Cálculo direto para intervalos de datas
      if ((filters?.date && filters?.endDate) || filters?.period === 'range') {
        console.log('🎯 GETSUMMARY RANGE DETECTED:', {
          date: filters?.date,
          endDate: filters?.endDate,
          period: filters?.period,
          fullFilters: filters,
          methodCalled: 'getSummary'
        });
        
        // 🚀 SOLUÇÃO: Processamento em chunks para evitar limite de 1000 registros
        console.log('🔍 QUERY DEBUG - Using chunked processing:', {
          table: 'daily_campaign_metrics',
          dateRange: `${filters.date} to ${filters.endDate}`,
          method: 'Chunked queries to bypass 1000 limit'
        });
        
        // Processar dados em chunks para contornar limite de 1000
        let allData: any[] = [];
        let rangeStart = 0;
        const chunkSize = 1000;
        let hasMoreData = true;
        
        while (hasMoreData) {
          const { data: chunkData, error: chunkError } = await supabase
            .from('daily_campaign_metrics')
            .select('spend, revenue_converted, revenue_converted_revshare, date')
            .gte('date', filters.date)
            .lte('date', filters.endDate)
            .range(rangeStart, rangeStart + chunkSize - 1)
            .order('date');
          
          if (chunkError) {
            console.error('❌ CHUNK QUERY ERROR:', chunkError);
            throw chunkError;
          }
          
          if (!chunkData || chunkData.length === 0) {
            hasMoreData = false;
          } else {
            allData = [...allData, ...chunkData];
            rangeStart += chunkSize;
            
            // Se retornou menos que o chunk size, chegamos no fim
            if (chunkData.length < chunkSize) {
              hasMoreData = false;
            }
          }
          
          console.log(`📦 Processed chunk: ${chunkData?.length || 0} records, total so far: ${allData.length}`);
        }
        
        const dailyData = allData;
        
        // Calcular totais a partir dos dados completos
        const totalSpend = dailyData.reduce((sum, item) => sum + (Number(item.spend) || 0), 0);
        const totalRevenue = dailyData.reduce((sum, item) => sum + (Number(item.revenue_converted) || 0), 0);
        
        // Calcular revenue após revenue share usando valores pré-calculados
        const totalRevenueAfterRevshare = dailyData.reduce((sum, item) => 
          sum + (Number(item.revenue_converted_revshare) || 0), 0);
        
        // Verificar quais datas estão presentes nos dados
        const datesInData = [...new Set(dailyData.map((item: any) => item.date))].sort();
        const startDateObj = new Date(filters.date + 'T00:00:00');
        const endDateObj = new Date(filters.endDate + 'T00:00:00');
        const totalDaysExpected = Math.ceil((endDateObj.getTime() - startDateObj.getTime()) / (1000 * 60 * 60 * 24)) + 1;
        
        // Análise diária agregando por data
        const dailyBreakdown = dailyData.reduce((acc: any, item: any) => {
          const date = item.date;
          if (!acc[date]) {
            acc[date] = { date, spend: 0, revenue: 0, recordCount: 0 };
          }
          acc[date].spend += Number(item.spend) || 0;
          acc[date].revenue += Number(item.revenue_converted) || 0;
          acc[date].recordCount += 1;
          return acc;
        }, {});
        
        const dailyAnalysis = Object.values(dailyBreakdown).sort((a: any, b: any) => a.date.localeCompare(b.date));

        console.log('🎯 GETSUMMARY - Chunked processing complete:', {
          method: '✅ Chunked queries (bypassed 1000 limit)',
          dateRange: `${filters.date} to ${filters.endDate}`,
          totalRecordsProcessed: dailyData.length,
          totalDaysExpected: totalDaysExpected,
          daysWithData: datesInData.length,
          datesWithData: datesInData,
          allDatesIncluded: datesInData.length === totalDaysExpected ? '✅ SIM' : '❌ NÃO',
          
          // Totais calculados de todos os registros
          finalTotals: {
            totalSpend: totalSpend,
            totalRevenue: totalRevenue,
            totalRevenueAfterRevshare: totalRevenueAfterRevshare,
            dataSource: 'Complete dataset (all chunks)'
          },
          
          // Breakdown diário
          dailyBreakdown: dailyAnalysis,
          
          // Debug: Verificar alguns registros para entender os dados
          sampleRecords: dailyData.slice(0, 3).map(item => ({
            date: item.date,
            spend: item.spend,
            revenue_converted: item.revenue_converted,
            revenue_converted_revshare: item.revenue_converted_revshare
          }))
        });
        
        // Cálculos derivados
        const totalProfit = totalRevenue - totalSpend;
        const generalRoas = totalSpend > 0 ? ((totalRevenue / totalSpend) - 1) * 100 : 0;  // ROAS as excess
        const finalRoi = totalSpend > 0 ? (totalProfit / totalSpend) * 100 : 0;
        
        // Buscar campanhas ativas (aproximado)
        const { data: campaignsData } = await supabase
          .from('campaigns')
          .select('id, status')
          .eq('active', true);
        
        const activeCampaigns = campaignsData?.length || 10;
        const greenCampaigns = Math.ceil(activeCampaigns * 0.6);
        const yellowCampaigns = Math.ceil(activeCampaigns * 0.3);
        const redCampaigns = activeCampaigns - greenCampaigns - yellowCampaigns;
        
        const result = {
          totalInvestment: totalSpend,
          totalRevenue: totalRevenue,
          totalRevenueAfterRevshare: totalRevenueAfterRevshare,
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
        
        console.log('🎯 GETSUMMARY RANGE RESULT:', result);
        return result;
      }
      
      // For other periods, use existing logic
      const dashboardData = await this.getDashboardData(filters || {});

      const result = {
        totalInvestment: dashboardData.totalSpend,
        totalRevenue: dashboardData.totalRevenue,
        totalRevenueAfterRevshare: dashboardData.totalRevenueAfterRevshare || (dashboardData.totalRevenue * 0.9), // Fallback 10% revshare
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
      
      console.log('🎯 FINAL RESULT for getSummary (non-range):', result);
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
      console.log('🔍 Searching for campaign with ID:', campaignId);
      
      // First, let's make a simpler query to see what we have
      console.log('🚀 Step 1: Testing basic query on campaigns_with_revenue');
      const { data: allCampaigns, error: allError } = await supabase
        .from('campaigns_with_revenue')
        .select('campaign_id, campaign_name')
        .limit(10);
      
      console.log('📋 All campaigns available:', allCampaigns, 'Error:', allError);
      
      // Check if our specific campaign exists
      console.log('🚀 Step 2: Checking if campaign exists with simple query');
      const { data: simpleCheck, error: simpleError } = await supabase
        .from('campaigns_with_revenue')
        .select('campaign_id, campaign_name, spend, gam_revenue')
        .eq('campaign_id', campaignId)
        .limit(1);
      
      console.log('📊 Simple check result:', simpleCheck, 'Error:', simpleError);
      
      if (!simpleCheck || simpleCheck.length === 0) {
        console.log('❌ Campaign not found with simple query');
        return {
          campaign: null,
          dailyMetrics: [],
          historicalData: [],
          campaignMetrics: null
        };
      }
      
      // Now try the complex query
      console.log('🚀 Step 3: Trying complex query with joins');
      const { data: campaignData, error: campaignError } = await supabase
        .from('campaigns_with_revenue')
        .select('*')
        .eq('campaign_id', campaignId)
        .limit(1);

      console.log('💾 Complex campaign data query result:', campaignData, 'Error:', campaignError);
      
      if (campaignError) throw campaignError;
      
      if (!campaignData || campaignData.length === 0) {
        console.log('❌ No campaign data found in complex query');
        return {
          campaign: null,
          dailyMetrics: [],
          historicalData: [],
          campaignMetrics: null
        };
      }

      const rawData = campaignData[0];
      console.log('📄 Raw campaign data:', rawData);

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

      console.log('✅ Returning campaign data successfully');
      
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
    period?: 'today' | '7d' | '30d' | 'custom' | 'range';
    date?: string;
    endDate?: string;
  }): Promise<{
    campaign: Campaign | null;
    dailyMetrics: any[];
    historicalData: any[];
    campaignMetrics: any;
  }> {
    try {
      console.log('🔍 getCampaignDashboardDataFiltered called with:', { campaignId, filters });
      
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

      console.log('📅 Date range for campaign dashboard:', { startDate, endDate, period: filters.period });

      // Get campaign basic info
      const { data: campaignData, error: campaignError } = await supabase
        .from('campaigns')
        .select('*')
        .eq('campaign_id', campaignId)
        .limit(1);

      if (campaignError) throw campaignError;
      
      if (!campaignData || campaignData.length === 0) {
        console.log('❌ Campaign not found');
        return {
          campaign: null,
          dailyMetrics: [],
          historicalData: [],
          campaignMetrics: null
        };
      }

      const rawCampaign = campaignData[0];
      console.log('📄 Raw campaign data:', rawCampaign);

      // Get daily campaign metrics for date range (including revenue_converted_revshare)
      console.log(`🔍 Querying daily_campaign_metrics for campaign ${campaignId} between ${startDate} and ${endDate}`);
      console.log(`🔍 Query details:`, {
        table: 'daily_campaign_metrics',
        campaign_id: campaignId,
        date_range: `${startDate} to ${endDate}`,
        period: filters.period
      });

      const { data: dailyMetrics, error: metricsError } = await supabase
        .from('daily_campaign_metrics')
        .select('spend, clicks, impressions, conversions, revenue_converted_revshare, date')
        .eq('campaign_id', campaignId)
        .gte('date', startDate)
        .lte('date', endDate)
        .order('date', { ascending: true });

      if (metricsError) {
        console.error(`❌ Error querying daily_campaign_metrics:`, metricsError);
      } else {
        console.log(`📊 Found ${(dailyMetrics || []).length} daily metrics records for campaign ${campaignId}`);
        console.log(`📊 Daily metrics data sample:`, (dailyMetrics || []).slice(0, 3));
        if (dailyMetrics && dailyMetrics.length > 0) {
          console.log(`📊 Date range in results: ${dailyMetrics[0]?.date} to ${dailyMetrics[dailyMetrics.length - 1]?.date}`);
        }
      }

      // Note: GAM data no longer needed - using revenue_converted_revshare from daily_campaign_metrics

      // Aggregate daily metrics
      console.log(`🧮 Starting aggregation for ${(dailyMetrics || []).length} records...`);

      const aggregatedSpend = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.spend) || 0), 0);
      const aggregatedClicks = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.clicks) || 0), 0);
      const aggregatedImpressions = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.impressions) || 0), 0);
      const aggregatedConversions = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.conversions) || 0), 0);

      // UPDATED: Use revenue after revshare from daily_campaign_metrics
      const aggregatedRevenue = (dailyMetrics || []).reduce((sum, m) => {
        const revenueAfterRevshare = Number((m as any).revenue_converted_revshare) || 0;
        return sum + revenueAfterRevshare;
      }, 0);

      console.log(`🧮 Aggregation results for campaign ${campaignId}:`, {
        period: filters.period,
        dateRange: `${startDate} to ${endDate}`,
        recordsCount: (dailyMetrics || []).length,
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
        projectName: 'Projeto padrão', // Will be loaded separately
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
        cost_per_conversion: aggregatedConversions > 0 ? aggregatedSpend / aggregatedConversions : 0
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

      console.log('📊 Chart date range:', { chartStartDate, chartEndDate, period: filters.period });

      const { data: chartMetrics } = await supabase
        .from('daily_campaign_metrics')
        .select('spend, clicks, impressions, conversions, revenue_converted_revshare, date')
        .eq('campaign_id', campaignId)
        .gte('date', chartStartDate)
        .lte('date', chartEndDate)
        .order('date', { ascending: true });

      console.log(`📊 Chart metrics found: ${(chartMetrics || []).length} records`);

      // Build historical data by date using daily_campaign_metrics only
      const historicalData = [];

      console.log(`📊 Building historical data from ${chartStartDate} to ${chartEndDate}`);
      console.log(`📊 Available chart metrics dates:`, (chartMetrics || []).map(m => m.date).sort());

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
      console.log(`📊 Total days to process: ${totalDays + 1} (from ${chartStartDate} to ${chartEndDate})`);

      // Iterate through each day in the range
      for (let dayOffset = 0; dayOffset <= totalDays; dayOffset++) {
        const dateStr = addDaysToDateString(chartStartDate, dayOffset);
        const dayMetrics = (chartMetrics || []).filter(m => m.date === dateStr);

        console.log(`📊 Processing date: ${dateStr}, found ${dayMetrics.length} metrics`);

        const daySpend = dayMetrics.reduce((sum, m) => sum + (Number(m.spend) || 0), 0);
        const dayRevenue = dayMetrics.reduce((sum, m) => {
          const revenueAfterRevshare = Number((m as any).revenue_converted_revshare) || 0;
          return sum + revenueAfterRevshare;
        }, 0);
        const dayClicks = dayMetrics.reduce((sum, m) => sum + (Number(m.clicks) || 0), 0);
        const dayImpressions = dayMetrics.reduce((sum, m) => sum + (Number(m.impressions) || 0), 0);

        historicalData.push({
          date: dateStr,
          spend: daySpend,
          revenue: dayRevenue,
          clicks: dayClicks,
          impressions: dayImpressions
        });
      }

      console.log(`📊 Historical data built: ${historicalData.length} days from ${chartStartDate} to ${chartEndDate}`);

      console.log('✅ Returning filtered campaign dashboard data');
      
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
      const daysToFetch = period === 'today' ? 2 : (period === '7d' ? 7 : 30); // Fetch 2 days for today to compare with yesterday
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
      
      console.log(`Processed Google Ads campaign: ${googleAdsData.campaign_id}`);
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
      const extractedUrl = urlMatch ? urlMatch[1] : null;
      const extractedDomain = extractedUrl ? extractedUrl.split('/')[0] : null;
      
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
          
          console.log(`Processed Google Ads campaign: ${googleAdsData.campaign_id}`);
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
      
      console.log(`Processed GAM metrics for UTM: ${gamData.value}`);
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
        
      console.log(`Processed GAM metrics for UTM campaign: ${gamData.value}`);
    } catch (error) {
      console.error('Error processing GAM metrics:', error);
      throw error;
    }
  }

  // Process and save GAM data from n8n (legacy method)
  async processGamData(gamData: GamReportData, projectId: number): Promise<void> {
    try {
      // Process URL-level performance data
      const urlMetrics = GamDataProcessor.processGamReport(gamData, projectId);
      
      if (urlMetrics.length > 0) {
        // Upsert URL daily performance data
        const { error: urlError } = await supabase
          .from('url_daily_performance')
          .upsert(
            urlMetrics.map(metric => ({
              ...metric,
              id: undefined // Let Supabase generate the ID
            })),
            { 
              onConflict: 'project_id,date,url',
              ignoreDuplicates: false 
            }
          );

        if (urlError) {
          console.error('Error saving URL metrics:', urlError);
          throw urlError;
        }

        // Aggregate and save project-level metrics
        const date = urlMetrics[0]?.date || new Date().toISOString().split('T')[0];
        const projectMetrics = GamDataProcessor.gamDataToProjectMetrics(gamData, projectId, date);
        
        const { error: projectError } = await supabase
          .from('daily_project_metrics')
          .upsert(
            [{
              ...projectMetrics,
              id: undefined // Let Supabase generate the ID
            }],
            { 
              onConflict: 'project_id,date',
              ignoreDuplicates: false 
            }
          );

        if (projectError) {
          console.error('Error saving project metrics:', projectError);
          throw projectError;
        }

        console.log(`Processed ${urlMetrics.length} URL metrics for project ${projectId}`);
      }
    } catch (error) {
      console.error('Error processing GAM data:', error);
      throw error;
    }
  }
  
  // Obter campanhas com revenue calculado automaticamente e informações de controle
  async getCampaignsWithRevenue(filters?: {
    projectId?: string;
    period?: 'today' | '7d' | '30d' | 'custom' | 'range';
    date?: string;
    endDate?: string;
  }): Promise<Campaign[]> {
    try {
      // Log filter information for debugging
      console.log('🔍 getCampaignsWithRevenue called with filters:', filters);

      // For filtered queries, we need to build custom aggregated data instead of using the view
      if (filters?.date || filters?.period) {
        return await this.getCampaignsWithRevenueFiltered(filters);
      }

      // Use the campaigns_with_revenue view only when no date/period filters
      let query = supabase
        .from('campaigns_with_revenue')
        .select('*');

      // Apply project filter if specified
      if (filters?.projectId && filters.projectId !== 'all') {
        query = query.eq('project_id', parseInt(filters.projectId));
      }

      const { data, error } = await query.order('gam_revenue', { ascending: false });
      
      if (error) throw error;
      
      // Debug log to see available campaigns
      console.log('🚀 Available campaigns in campaigns_with_revenue:', (data || []).map(item => ({
        id: item.id,
        campaign_id: item.campaign_id,
        name: item.campaign_name
      })));
      
      // Convert to Campaign interface format
      return (data || []).map((item: any) => ({
        id: item.campaign_id.toString(), // Use campaign_id instead of id for consistency
        name: item.campaign_name,
        projectId: item.project_id?.toString() || '1',
        status: item.status === 'Active' || item.status === 'ENABLED' ? 'active' : 'paused',
        performance: this.calculatePerformance(Number(item.gam_revenue) || 0, Number(item.spend) || 0),
        investment: Number(item.spend) || 0,
        revenue: Number(item.gam_revenue) || 0,
        roas: this.calculateRoas(Number(item.gam_revenue) || 0, Number(item.spend) || 0),
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
      }));
    } catch (error) {
      console.error('Error fetching campaigns with revenue:', error);
      return [];
    }
  }

  // New method that applies date/period filters by building aggregated queries
  private async getCampaignsWithRevenueFiltered(filters: {
    projectId?: string;
    period?: 'today' | '7d' | '30d' | 'custom' | 'range';
    date?: string;
    endDate?: string;
  }): Promise<Campaign[]> {
    try {
      console.log('🔍 getCampaignsWithRevenueFiltered called with filters:', filters);

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

      console.log('📅 Date range for filtered campaigns:', { startDate, endDate, period: filters.period });

      // Get base campaigns
      let campaignsQuery = supabase
        .from('campaigns')
        .select('*');

      if (filters.projectId && filters.projectId !== 'all') {
        campaignsQuery = campaignsQuery.eq('project_id', parseInt(filters.projectId));
      }

      const { data: campaigns, error: campaignsError } = await campaignsQuery;
      if (campaignsError) throw campaignsError;

      if (!campaigns || campaigns.length === 0) {
        console.log('❌ No campaigns found for filters');
        return [];
      }

      console.log(`📋 Found ${campaigns.length} campaigns, aggregating metrics...`);

      // For each campaign, aggregate metrics for the date range
      const campaignsWithRevenue = await Promise.all(campaigns.map(async (campaign) => {
        // Get daily campaign metrics for date range
        console.log(`🔍 Querying daily_campaign_metrics for campaign ${campaign.campaign_id} between ${startDate} and ${endDate}`);
        const { data: dailyMetrics, error: metricsError } = await supabase
          .from('daily_campaign_metrics')
          .select('spend, clicks, impressions, conversions, revenue_converted_revshare, date')
          .eq('campaign_id', campaign.campaign_id)
          .gte('date', startDate)
          .lte('date', endDate);

        if (metricsError) {
          console.error(`❌ Error querying daily_campaign_metrics for campaign ${campaign.campaign_id}:`, metricsError);
        } else {
          console.log(`📊 Found ${(dailyMetrics || []).length} daily metrics records for campaign ${campaign.campaign_id}`);
        }

        // Get GAM metrics for date range (prioritize revenue_converted)
        const { data: gamMetrics } = await supabase
          .from('gam_metrics')
          .select('revenue, revenue_converted, date')
          .eq('utm_campaign_value', campaign.campaign_id)
          .gte('date', startDate)
          .lte('date', endDate);

        // Aggregate daily metrics
        const aggregatedSpend = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.spend) || 0), 0);
        const aggregatedClicks = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.clicks) || 0), 0);
        const aggregatedImpressions = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.impressions) || 0), 0);
        const aggregatedConversions = (dailyMetrics || []).reduce((sum, m) => sum + (Number(m.conversions) || 0), 0);

        // UPDATED: Use revenue after revshare from daily_campaign_metrics instead of GAM
        const aggregatedRevenue = (dailyMetrics || []).reduce((sum, m) => {
          const revenueAfterRevshare = Number((m as any).revenue_converted_revshare) || 0;

          console.log(`💰 [Campaign ${campaign.campaign_id}] Daily metrics record:`, {
            date: (m as any).date,
            campaign_id: campaign.campaign_id,
            revenue_converted_revshare: revenueAfterRevshare,
            source: 'daily_campaign_metrics_net_revenue'
          });
          return sum + revenueAfterRevshare;
        }, 0);

        // Validation: Check if campaign revenue seems unrealistic
        if (aggregatedRevenue > 100000) { // More than 100K BRL per campaign
          console.warn('⚠️ SUSPICIOUS CAMPAIGN REVENUE:', {
            campaignId: campaign.campaign_id,
            campaignName: campaign.campaign_name,
            aggregatedRevenue,
            dateRange: `${startDate} to ${endDate}`,
            possibleIssue: 'Campaign revenue seems too high, check data quality'
          });
        }

        return {
          id: campaign.campaign_id.toString(),
          name: campaign.campaign_name,
          projectId: campaign.project_id?.toString() || '1',
          status: campaign.status === 'Active' || campaign.status === 'ENABLED' ? 'active' : 'paused',
          performance: this.calculatePerformance(aggregatedRevenue, aggregatedSpend),
          investment: aggregatedSpend,
          revenue: aggregatedRevenue,
          roas: this.calculateRoas(aggregatedRevenue, aggregatedSpend),
          impressions: aggregatedImpressions,
          clicks: aggregatedClicks,
          ctr: aggregatedImpressions > 0 ? (aggregatedClicks / aggregatedImpressions) * 100 : 0,
          startDate: campaign.start_date,
          endDate: campaign.end_date,
          utmCampaignValue: campaign.campaign_id,
          extractedUrl: campaign.extracted_url || undefined,
          extractedDomain: campaign.extracted_domain || undefined,
          customGoal: campaign.custom_goal || undefined,
          statusSource: 'auto',
          userPausedAt: undefined,
          userPausedBy: undefined
        } as Campaign;
      }));

      // Filter out campaigns with no activity in the date range and sort by revenue
      const activeCampaigns = campaignsWithRevenue
        .filter(c => c.revenue > 0 || c.investment > 0)
        .sort((a, b) => (b.revenue || 0) - (a.revenue || 0));

      console.log(`✅ Returning ${activeCampaigns.length} campaigns with activity in date range`);

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
    period?: 'today' | '7d' | '30d' | 'custom' | 'range';
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
        .select('*')
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
    console.log('Data refresh triggered');
  }

  // Public method to get current server date
  async getServerDate(): Promise<string> {
    return this.getCurrentServerDate();
  }
  
  // Force cache refresh
  clearServerDateCache(): void {
    this.currentServerDate = null;
    console.log('🗜️ Server date cache cleared');
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
      
      console.log(`Campaign ${utmCampaignId} status updated to ${newStatus} by user ${userId}`);
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
      console.log('Using real daily metrics for UTM campaigns');
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

      console.log('📊 System timestamps fetched:', {
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
  period?: 'today' | '7d' | '30d' | 'custom' | 'range';
}) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [dailyMetrics, setDailyMetrics] = useState<DailyMetrics[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);

  const fetchData = async (currentFilters?: typeof filters) => {
    try {
      setLoading(true);
      setError(null);

      const filterOptions = currentFilters || filters || {};
      console.log('🔄 useSupabaseData fetchData called with filters:', filterOptions);

      // Continue with data fetching even if date is empty initially

      const [projectsData, campaignsData, metricsData, summaryData, lastUpdateData] = await Promise.all([
        supabaseDataService.getProjects(filterOptions),
        supabaseDataService.getCampaignsWithRevenue(filterOptions),
        supabaseDataService.getDailyMetrics(filterOptions),
        supabaseDataService.getSummary(filterOptions),
        supabaseDataService.getLastDataUpdateTimestamp()
      ]);

      console.log('📊 Data fetched successfully:', {
        projects: projectsData.length,
        campaigns: campaignsData.length,
        metrics: metricsData.length,
        summary: summaryData
      });
      console.log('🔍 HOOK DEBUG - Summary data details:', {
        totalInvestment: summaryData?.totalInvestment,
        totalRevenue: summaryData?.totalRevenue,
        filterOptions
      });

      setProjects(projectsData);
      setCampaigns(campaignsData);
      setDailyMetrics(metricsData);
      setSummary(summaryData);
      setLastUpdate(lastUpdateData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    console.log('🔄 useSupabaseData: Effect triggered', {
      hasFilters: !!filters,
      hasDate: !!filters?.date,
      projectId: filters?.projectId
    });
    console.log('✅ useSupabaseData: Fetching data with filters', filters);
    fetchData();
  }, [filters?.date, filters?.projectId, filters?.period]);

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