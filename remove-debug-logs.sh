#!/bin/bash

# Script para remover console.log e console.info do código
# Mantém console.error e console.warn

echo "🧹 Removendo debug logs do código..."

# Função para processar um arquivo
process_file() {
  file="$1"

  # Remove linhas que contêm apenas console.log ou console.info (incluindo espaços)
  # Mantém console.error e console.warn
  sed -i '' '/^[[:space:]]*console\.log(/d' "$file"
  sed -i '' '/^[[:space:]]*console\.info(/d' "$file"
  sed -i '' '/^[[:space:]]*console\.debug(/d' "$file"
}

# Processar arquivos principais
echo "📄 Processando supabaseDataService.ts..."
process_file "src/services/supabaseDataService.ts"

echo "📄 Processando GeneralDashboard.tsx..."
process_file "src/pages/GeneralDashboard.tsx"

echo "📄 Processando SimpleDateFilter.tsx..."
process_file "src/components/dashboard/SimpleDateFilter.tsx"

echo "📄 Processando DataStatus.tsx..."
process_file "src/components/dashboard/DataStatus.tsx"

echo "📄 Processando Reports.tsx..."
process_file "src/pages/Reports.tsx"

echo "📄 Processando ProjectDashboard.tsx..."
process_file "src/pages/ProjectDashboard.tsx"

echo "📄 Processando CampaignDetailDashboard.tsx..."
process_file "src/pages/CampaignDetailDashboard.tsx"

echo "✅ Debug logs removidos com sucesso!"
echo "⚠️  console.error e console.warn foram mantidos para debug de erros"
