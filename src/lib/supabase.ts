import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

// GAM Data Processing Types
export interface GamDataColumn {
  name: string
  Val: string
}

export interface GamDataRow {
  Column: GamDataColumn[]
}

export interface GamReportData {
  rows?: GamDataRow[]
}

// Database types
export interface DatabaseProject {
  id: number
  project_name: string
  main_url: string
  start_date: string
  status: 'Active' | 'Paused'
  dollar_rate: number
  last_google_ads_sync?: string
  last_gam_sync?: string
  google_ads_status: string
  gam_status: string
  google_ads_customer_id?: string
  gam_network_code?: string
  gam_ad_unit_id?: string
  created_at: string
  updated_at: string
  last_sync_date?: string
  revshare?: number
  taxes?: number
  google_ads_manager_id?: string
  project_type?: 'GAM' | 'ADSENSE'
}

export interface DatabaseCampaign {
  id: number
  project_id: number
  campaign_name: string
  start_date: string
  status: 'Active' | 'Paused'
  notes?: string
  google_ads_campaign_id?: string
  google_ads_status?: string
  created_at: string
  updated_at: string
  end_date?: string
  advertising_channel_type?: 'SEARCH' | 'DISPLAY' | 'VIDEO' | 'SHOPPING' | 'DISCOVERY' | 'PERFORMANCE_MAX'
}

export interface DatabaseDailyProjectMetrics {
  id: number
  project_id: number
  url_projeto: string
  date: string
  revenue_converted: number
  revenue_converted_revshare: number
  updated_at: string
}

export interface DatabaseDailyCampaignMetrics {
  id: number
  campaign_id: number
  date: string
  spend: number
  revenue: number
  roas: number
  page_views: number
  ecpm: number
  cpc: number
  viewability: number
  pmr: number
  ctr: number
  rps: number
  clicks: number
  impressions: number
  created_at: string
  updated_at: string
  revenue_converted_revshare: number
}

export interface DatabaseUser {
  id: string // UUID
  name: string
  email: string
  password_hash?: string
  role: 'ADMIN' | 'OPERATOR'
  needs_password_change?: boolean
  first_login?: boolean
  created_at: string
  updated_at: string
}

// Ad Groups
export interface DatabaseAdGroup {
  id: number
  campaign_id: number
  google_ads_ad_group_id: string
  name?: string
  status?: string
  type?: string
  created_at: string
  updated_at: string
}

export interface DatabaseDailyAdGroupMetrics {
  id: number
  ad_group_id: number
  date: string
  clicks: number
  impressions: number
  conversions: number
  spend: number
  avg_cpc: number
  avg_cpm: number
  ctr: number
  conv_rate: number
  cpa: number
  created_at: string
  updated_at: string
}

// Alerts & Notifications
export interface DatabaseAlert {
  id: number
  alert_type: 'PERFORMANCE' | 'BUDGET' | 'CONVERSION' | 'TRAFFIC'
  threshold_value: number
  notification_channel: 'EMAIL' | 'SLACK' | 'WEBHOOK' | 'SMS'
  status: 'ACTIVE' | 'INACTIVE' | 'TRIGGERED'
  project_id?: number
  campaign_id?: number
  created_at: string
  updated_at: string
}

export interface DatabaseNotificationLog {
  id: number
  alert_id: number
  user_id?: number
  message: string
  sent_at: string
  channel_used: 'EMAIL' | 'SLACK' | 'WEBHOOK' | 'SMS'
}

// Integrations
export interface DatabaseIntegration {
  id: number
  project_id: number
  integration_type: 'GOOGLE_ADS' | 'GAM' | 'ANALYTICS' | 'FACEBOOK'
  account_name: string
  account_id: string
  access_token: string
  refresh_token: string
  is_encrypted: boolean
  encryption_version: string
  token_expiration_date: string
  created_at: string
  updated_at: string
}

// GAM Accounts
export interface DatabaseGamAccount {
  id: number
  created_at: string
  name: string
  network_code: string
  updated_at?: string
  project_id?: number
  ad_unit_id?: string
  gam_status: string
  last_sync?: string
}

// Campaign Related
export interface DatabaseCampaignBudgetHistory {
  id: number
  campaign_id: number
  campaign_budget_id: string
  amount: number
  captured_at: string
}

export interface DatabaseCampaignConversionGoal {
  id: number
  campaign_id: number
  custom_conversion_goal_id: string
  custom_conversion_goal_name: string
}

export interface DatabaseCampaignFunnelUrl {
  id: number
  campaign_id: number
  url: string
  is_primary: boolean
  created_at: string
}

// Operational Costs
export interface DatabaseOperationalCostCategory {
  id: number
  name: string
}

export interface DatabaseOperationalCost {
  id: number
  category_id: number
  subcategory_name?: string
  cost_name: string
  amount?: number
  reference_month: string
  is_percentage: boolean
  percentage_value?: number
  created_at: string
  updated_at: string
}

export interface DatabaseTaxHistory {
  id: number
  cost_id: number
  percentage_value: number
  effective_date: string
  created_at: string
}

// URL Performance
export interface DatabaseUrlDailyPerformance {
  id: number
  project_id: number
  date: string
  url: string
  estimated_earnings_usd: number
  page_views: number
  ecpm: number
  pmr: number
  viewability: number
  ctr: number
  rps: number
  created_at: string
  updated_at: string
}

// Sync Logs
export interface DatabaseSyncLog {
  id: number
  project_id: number
  sync_type: string
  status: string
  records_processed?: number
  records_created?: number
  records_updated?: number
  error_message?: string
  sync_date: string
  started_at: string
  completed_at?: string
  metadata?: Record<string, any>
}

// GAM Data Utilities
export class GamDataProcessor {
  // Convert GAM column array to object
  static columnsToObject(columns: GamDataColumn[]): Record<string, string> {
    return columns.reduce((obj, col) => {
      obj[col.name] = col.Val
      return obj
    }, {} as Record<string, string>)
  }

  // Parse currency values (R$1.39 → 1.39)
  static parseCurrency(value: string): number {
    if (!value) return 0
    return parseFloat(value.replace(/[R$,\s]/g, '').replace(',', '.')) || 0
  }

  // Parse percentage values (90.32% → 0.9032)
  static parsePercentage(value: string): number {
    if (!value) return 0
    return parseFloat(value.replace('%', '')) / 100 || 0
  }

  // Parse date (8/13/25 → 2025-08-13) - ALWAYS UTC
  static parseDate(value: string): string {
    if (!value) return new Date().toISOString().split('T')[0]
    
    const parts = value.split('/')
    if (parts.length === 3) {
      const month = parts[0].padStart(2, '0')
      const day = parts[1].padStart(2, '0')
      let year = parts[2]
      
      // Handle 2-digit years
      if (year.length === 2) {
        const currentYear = new Date().getFullYear()
        const currentYearLast2 = currentYear % 100
        year = parseInt(year) <= currentYearLast2 + 10 
          ? `20${year}` 
          : `19${year}`
      }
      
      // Return YYYY-MM-DD format (UTC)
      return `${year}-${month}-${day}`
    }
    
    return new Date().toISOString().split('T')[0]
  }

  // Convert Google Ads micros to USD (micros ÷ 1,000,000)
  static parseMicros(value: string | number): number {
    const micros = typeof value === 'string' ? parseInt(value) : value
    return micros ? micros / 1000000 : 0
  }

  // Convert GAM data row to DatabaseUrlDailyPerformance
  static gamRowToUrlPerformance(
    row: GamDataRow, 
    projectId: number
  ): Partial<DatabaseUrlDailyPerformance> {
    const data = this.columnsToObject(row.Column)
    
    return {
      project_id: projectId,
      date: this.parseDate(data.date),
      url: data.XFP_URL_NAME || '',
      estimated_earnings_usd: this.parseCurrency(data.adxReservationPubCostDelivered),
      page_views: parseInt(data.totalImpressions) || 0,
      ecpm: this.parseCurrency(data.adxEcpm) || 0,
      pmr: this.parsePercentage(data.adxMatchRate) || 0,
      viewability: this.parsePercentage(data.activeViewAdxViewableImpressionsRate) || 0,
      ctr: this.parsePercentage(data.adxCtr) || 0,
      rps: this.parseCurrency(data.adxRevenuePerSession) || 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }
  }

  // Batch process GAM report data
  static processGamReport(
    gamData: GamReportData,
    projectId: number
  ): Partial<DatabaseUrlDailyPerformance>[] {
    if (!gamData.rows) return []
    
    return gamData.rows.map(row => 
      this.gamRowToUrlPerformance(row, projectId)
    ).filter(item => item.url && item.date)
  }

  // Convert GAM data to project metrics aggregate
  static gamDataToProjectMetrics(
    gamData: GamReportData,
    projectId: number,
    date: string
  ): Partial<DatabaseDailyProjectMetrics> {
    if (!gamData.rows) {
      return {
        project_id: projectId,
        date,
        invested_amount: 0,
        billed_amount: 0,
        roas: 0,
        roi: 0,
        gross_profit: 0,
        net_profit: 0,
        page_views: 0,
        rpm: 0,
        ecpm: 0,
        cpc: 0,
        viewability: 0,
        pmr: 0,
        ctr: 0,
        rps: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    }

    // Aggregate metrics from all URLs
    const urlMetrics = this.processGamReport(gamData, projectId)
    
    const totalRevenue = urlMetrics.reduce((sum, item) => sum + (item.estimated_earnings_usd || 0), 0)
    const totalPageViews = urlMetrics.reduce((sum, item) => sum + (item.page_views || 0), 0)
    const avgViewability = urlMetrics.length > 0 
      ? urlMetrics.reduce((sum, item) => sum + (item.viewability || 0), 0) / urlMetrics.length 
      : 0
    const avgPmr = urlMetrics.length > 0 
      ? urlMetrics.reduce((sum, item) => sum + (item.pmr || 0), 0) / urlMetrics.length 
      : 0
    const avgCtr = urlMetrics.length > 0 
      ? urlMetrics.reduce((sum, item) => sum + (item.ctr || 0), 0) / urlMetrics.length 
      : 0
    const avgEcpm = urlMetrics.length > 0 
      ? urlMetrics.reduce((sum, item) => sum + (item.ecpm || 0), 0) / urlMetrics.length 
      : 0
    const avgRps = urlMetrics.length > 0 
      ? urlMetrics.reduce((sum, item) => sum + (item.rps || 0), 0) / urlMetrics.length 
      : 0

    return {
      project_id: projectId,
      date,
      invested_amount: 0, // This would come from Google Ads
      billed_amount: totalRevenue,
      roas: 0, // Calculated when we have investment data
      roi: 0, // Calculated when we have investment data  
      gross_profit: totalRevenue,
      net_profit: totalRevenue, // Would be adjusted for operational costs
      page_views: totalPageViews,
      rpm: totalPageViews > 0 ? (totalRevenue / totalPageViews) * 1000 : 0,
      ecpm: avgEcpm || 0,
      cpc: 0, // This would come from Google Ads
      viewability: avgViewability || 0,
      pmr: avgPmr || 0,
      ctr: avgCtr || 0,
      rps: avgRps || 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }
  }
}

// Common GAM field mappings
export const GAM_FIELD_MAPPINGS = {
  // Date fields
  DATE: 'date',
  
  // URL fields
  URL: 'XFP_URL_NAME',
  
  // Revenue fields
  REVENUE: 'adxReservationPubCostDelivered',
  ECPM: 'adxEcpm',
  REVENUE_PER_SESSION: 'adxRevenuePerSession',
  
  // Traffic fields
  IMPRESSIONS: 'totalImpressions',
  PAGE_VIEWS: 'totalImpressions',
  
  // Performance fields
  VIEWABILITY: 'activeViewAdxViewableImpressionsRate',
  MATCH_RATE: 'adxMatchRate',
  CLICKS: 'adxClicks',
  CTR: 'adxCtr'
} as const
