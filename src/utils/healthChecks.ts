// Health & Monitoring utilities for production
import { supabase } from '@/lib/supabase'

export interface HealthCheckResult {
  name: string
  status: 'OK' | 'WARNING' | 'ERROR'
  message: string
  data?: any
}

export class ProductionHealthChecks {
  
  // Smoke check diário - verifica duplicatas
  static async checkDuplicates(): Promise<HealthCheckResult[]> {
    const results: HealthCheckResult[] = []
    
    try {
      // DAGM duplicadas
      const { data: dagmDuplicates, error: dagmError } = await supabase.rpc(
        'check_dagm_duplicates',
        {},
        {
          count: 'exact'
        }
      )
      
      if (dagmError) {
        // Fallback query se RPC não existir
        const { data: fallbackDagm } = await supabase
          .from('daily_ad_group_metrics')
          .select('ad_group_id, date')
          .then(async ({ data }) => {
            if (!data) return { data: [] }
            
            // Group by e count em JS (não ideal mas funciona)
            const grouped = data.reduce((acc, row) => {
              const key = `${row.ad_group_id}-${row.date}`
              acc[key] = (acc[key] || 0) + 1
              return acc
            }, {} as Record<string, number>)
            
            const duplicates = Object.entries(grouped)
              .filter(([_, count]) => count > 1)
              .map(([key, count]) => ({ key, count }))
            
            return { data: duplicates }
          })
        
        results.push({
          name: 'DAGM Duplicates Check',
          status: fallbackDagm?.data?.length === 0 ? 'OK' : 'ERROR',
          message: fallbackDagm?.data?.length === 0 
            ? 'No duplicates found' 
            : `${fallbackDagm?.data?.length} duplicate groups found`,
          data: fallbackDagm?.data
        })
      } else {
        results.push({
          name: 'DAGM Duplicates Check',
          status: (dagmDuplicates as any)?.length === 0 ? 'OK' : 'ERROR',
          message: (dagmDuplicates as any)?.length === 0 
            ? 'No duplicates found' 
            : `${(dagmDuplicates as any)?.length} duplicate groups found`,
          data: dagmDuplicates
        })
      }

      // DCM duplicadas
      const { data: dcmCheck } = await supabase
        .from('daily_campaign_metrics')
        .select('campaign_id, date')
      
      if (dcmCheck) {
        const dcmGrouped = dcmCheck.reduce((acc, row) => {
          const key = `${row.campaign_id}-${row.date}`
          acc[key] = (acc[key] || 0) + 1
          return acc
        }, {} as Record<string, number>)
        
        const dcmDuplicates = Object.entries(dcmGrouped)
          .filter(([_, count]) => count > 1)
          .map(([key, count]) => ({ key, count }))
        
        results.push({
          name: 'DCM Duplicates Check',
          status: dcmDuplicates.length === 0 ? 'OK' : 'ERROR',
          message: dcmDuplicates.length === 0 
            ? 'No duplicates found' 
            : `${dcmDuplicates.length} duplicate groups found`,
          data: dcmDuplicates
        })
      }
      
    } catch (error) {
      results.push({
        name: 'Duplicates Check',
        status: 'ERROR',
        message: `Error running duplicates check: ${error instanceof Error ? error.message : 'Unknown error'}`,
        data: error
      })
    }
    
    return results
  }
  
  // Lag de ingestão - verifica últimas datas
  static async checkIngestionLag(): Promise<HealthCheckResult[]> {
    const results: HealthCheckResult[] = []
    
    try {
      const checks = await Promise.all([
        supabase.from('daily_ad_group_metrics').select('date').order('date', { ascending: false }).limit(1),
        supabase.from('daily_campaign_metrics').select('date').order('date', { ascending: false }).limit(1),
        supabase.from('url_daily_performance').select('date').order('date', { ascending: false }).limit(1)
      ])
      
      const sources = ['DAGM', 'DCM', 'URL Performance']
      const today = new Date().toISOString().split('T')[0]
      
      checks.forEach((check, index) => {
        const lastDate = check.data?.[0]?.date
        const daysBehind = lastDate 
          ? Math.floor((new Date(today).getTime() - new Date(lastDate).getTime()) / (1000 * 60 * 60 * 24))
          : 999
        
        let status: 'OK' | 'WARNING' | 'ERROR' = 'OK'
        if (daysBehind > 2) status = 'ERROR'
        else if (daysBehind > 1) status = 'WARNING'
        
        results.push({
          name: `${sources[index]} Ingestion Lag`,
          status,
          message: lastDate 
            ? `Last data: ${lastDate} (${daysBehind} days behind)`
            : 'No data found',
          data: { lastDate, daysBehind }
        })
      })
      
    } catch (error) {
      results.push({
        name: 'Ingestion Lag Check',
        status: 'ERROR',
        message: `Error checking ingestion lag: ${error instanceof Error ? error.message : 'Unknown error'}`,
        data: error
      })
    }
    
    return results
  }
  
  // Executar todos os health checks
  static async runAllChecks(): Promise<{
    overall: 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY'
    checks: HealthCheckResult[]
    summary: {
      ok: number
      warning: number
      error: number
    }
  }> {
    try {
      const duplicateChecks = await this.checkDuplicates()
      const lagChecks = await this.checkIngestionLag()
      
      const allChecks = [...duplicateChecks, ...lagChecks]
      
      const summary = {
        ok: allChecks.filter(c => c.status === 'OK').length,
        warning: allChecks.filter(c => c.status === 'WARNING').length,
        error: allChecks.filter(c => c.status === 'ERROR').length
      }
      
      let overall: 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY' = 'HEALTHY'
      if (summary.error > 0) overall = 'UNHEALTHY'
      else if (summary.warning > 0) overall = 'DEGRADED'
      
      return {
        overall,
        checks: allChecks,
        summary
      }
      
    } catch (error) {
      return {
        overall: 'UNHEALTHY',
        checks: [{
          name: 'Health Check System',
          status: 'ERROR',
          message: `Failed to run health checks: ${error instanceof Error ? error.message : 'Unknown error'}`,
          data: error
        }],
        summary: { ok: 0, warning: 0, error: 1 }
      }
    }
  }
}

// Hook React para usar nos componentes
export const useHealthChecks = () => {
  const [healthStatus, setHealthStatus] = React.useState<{
    overall: 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY'
    checks: HealthCheckResult[]
    summary: { ok: number; warning: number; error: number }
    lastCheck?: string
  } | null>(null)
  
  const [loading, setLoading] = React.useState(false)
  
  const runChecks = async () => {
    setLoading(true)
    try {
      const results = await ProductionHealthChecks.runAllChecks()
      setHealthStatus({
        ...results,
        lastCheck: new Date().toISOString()
      })
    } catch (error) {
      console.error('Health check failed:', error)
    } finally {
      setLoading(false)
    }
  }
  
  React.useEffect(() => {
    // Executar health checks na montagem
    runChecks()
    
    // Executar a cada 5 minutos em desenvolvimento
    // Em produção, execute via cron job
    if (process.env.NODE_ENV === 'development') {
      const interval = setInterval(runChecks, 5 * 60 * 1000)
      return () => clearInterval(interval)
    }
  }, [])
  
  return {
    healthStatus,
    loading,
    runChecks
  }
}

// Utility para logs estruturados
export const logHealthCheck = (results: HealthCheckResult[]) => {
  const timestamp = new Date().toISOString()
  
  results.forEach(result => {
    const logLevel = result.status === 'ERROR' ? 'error' : result.status === 'WARNING' ? 'warn' : 'info'
    
    console[logLevel](`[HEALTH_CHECK] ${timestamp}`, {
      check: result.name,
      status: result.status,
      message: result.message,
      data: result.data
    })
  })
}