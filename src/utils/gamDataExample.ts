// Example: How to process GAM data from n8n webhook
import { supabaseDataService } from '@/services/supabaseDataService'
import { GamReportData, GamDataProcessor } from '@/lib/supabase'

/**
 * Example GAM data structure coming from n8n webhook
 */
export const exampleGamData: GamReportData = {
  rows: [
    {
      Column: [
        { name: "date", Val: "8/13/25" },
        { name: "XFP_URL_NAME", Val: "cartaoecredito.org/nubank-surpreende-com-forma-inedita-para-que-clientes-aumentem-o-limite-na-hora" },
        { name: "adxReservationPubCostDelivered", Val: "R$1.39" },
        { name: "activeViewAdxViewableImpressionsRate", Val: "90.32%" },
        { name: "totalImpressions", Val: "1250" },
        { name: "adxEcpm", Val: "R$1.11" },
        { name: "adxMatchRate", Val: "85.5%" },
        { name: "adxCtr", Val: "0.8%" },
        { name: "adxRevenuePerSession", Val: "R$0.05" }
      ]
    },
    {
      Column: [
        { name: "date", Val: "8/13/25" },
        { name: "XFP_URL_NAME", Val: "cartaoecredito.org/cartao-de-credito-sem-anuidade-top-5-opcoes" },
        { name: "adxReservationPubCostDelivered", Val: "R$2.85" },
        { name: "activeViewAdxViewableImpressionsRate", Val: "88.7%" },
        { name: "totalImpressions", Val: "2340" },
        { name: "adxEcpm", Val: "R$1.22" },
        { name: "adxMatchRate", Val: "92.1%" },
        { name: "adxCtr", Val: "1.2%" },
        { name: "adxRevenuePerSession", Val: "R$0.08" }
      ]
    }
  ]
}

/**
 * Function to be called by n8n webhook or API endpoint
 * This would process incoming GAM data and save it to Supabase
 */
export async function processIncomingGamData(
  gamData: GamReportData, 
  projectId: number
): Promise<{ success: boolean; message: string; processedRows: number }> {
  try {
    // Validate input data
    if (!gamData.rows || gamData.rows.length === 0) {
      return {
        success: false,
        message: 'No data rows provided',
        processedRows: 0
      }
    }

    // Process and save GAM data using the service
    await supabaseDataService.processGamData(gamData, projectId)

    return {
      success: true,
      message: `Successfully processed GAM data for project ${projectId}`,
      processedRows: gamData.rows.length
    }
  } catch (error) {
    console.error('Failed to process GAM data:', error)
    return {
      success: false,
      message: `Error processing GAM data: ${error instanceof Error ? error.message : 'Unknown error'}`,
      processedRows: 0
    }
  }
}

/**
 * Utility function to test data parsing
 */
export function testGamDataProcessing() {
  const projectId = 1
  
  console.log('🧪 Testing GAM Data Processing...')
  
  // Test individual row processing
  if (exampleGamData.rows && exampleGamData.rows.length > 0) {
    const firstRow = exampleGamData.rows[0]
    const processedUrl = GamDataProcessor.gamRowToUrlPerformance(firstRow, projectId)
    
    console.log('📊 Processed URL Data:')
    console.log(JSON.stringify(processedUrl, null, 2))
    
    // Test project metrics aggregation
    const projectMetrics = GamDataProcessor.gamDataToProjectMetrics(
      exampleGamData, 
      projectId, 
      '2025-08-13'
    )
    
    console.log('📈 Aggregated Project Metrics:')
    console.log(JSON.stringify(projectMetrics, null, 2))
  }
  
  console.log('✅ GAM Data Processing Test Complete')
}

/**
 * Example n8n webhook handler
 * This would be the endpoint that n8n calls to send GAM data
 */
export async function n8nWebhookHandler(request: {
  body: {
    projectId: number
    gamData: GamReportData
    syncTimestamp: string
  }
}): Promise<Response> {
  try {
    const { projectId, gamData, syncTimestamp } = request.body
    
    console.log(`📡 Received GAM data webhook for project ${projectId} at ${syncTimestamp}`)
    
    const result = await processIncomingGamData(gamData, projectId)
    
    if (result.success) {
      return new Response(JSON.stringify({
        status: 'success',
        message: result.message,
        processedRows: result.processedRows,
        timestamp: new Date().toISOString()
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    } else {
      return new Response(JSON.stringify({
        status: 'error',
        message: result.message,
        timestamp: new Date().toISOString()
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      })
    }
  } catch (error) {
    console.error('Webhook handler error:', error)
    
    return new Response(JSON.stringify({
      status: 'error',
      message: 'Internal server error',
      timestamp: new Date().toISOString()
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    })
  }
}