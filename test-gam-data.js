// Test script to validate GAM data processing with actual Supabase schema
import { GamDataProcessor } from './src/lib/supabase.js';

// Test data matching the n8n format you provided
const testGamData = {
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
    }
  ]
};

console.log('🧪 Testing GAM Data Processing...\n');

// Test URL performance conversion
const urlData = GamDataProcessor.gamRowToUrlPerformance(testGamData.rows[0], 1);
console.log('📊 URL Performance Data:');
console.log(JSON.stringify(urlData, null, 2));

// Test project metrics aggregation  
const projectData = GamDataProcessor.gamDataToProjectMetrics(testGamData, 1, '2025-08-13');
console.log('\n📈 Project Metrics Data:');
console.log(JSON.stringify(projectData, null, 2));

console.log('\n✅ All tests completed!');