#!/bin/bash

# Script de Deploy da Rotação de Campanhas Destacadas
# ARQUIVADO: fluxo legado e mutável. Preservado somente para rastreabilidade.

echo "BLOQUEADO: deploy legado de campaign_highlights. Consulte docs/archive/features/campaign-highlights/."
exit 2

set -e  # Parar em caso de erro

echo "🚀 Deploy da Rotação de Campanhas Destacadas"
echo "=============================================="
echo ""

# Verificar se o arquivo .env existe
if [ ! -f .env ]; then
  echo "❌ Erro: Arquivo .env não encontrado"
  echo "💡 Crie um arquivo .env com DATABASE_URL"
  exit 1
fi

# Carregar variáveis de ambiente
source .env

if [ -z "$DATABASE_URL" ]; then
  echo "❌ Erro: DATABASE_URL não definida no .env"
  exit 1
fi

echo "✅ DATABASE_URL encontrada"
echo ""

# Função para executar SQL via psql
execute_sql() {
  local file=$1
  local description=$2

  echo "📝 Executando: $description"
  echo "   Arquivo: $file"

  if [ ! -f "$file" ]; then
    echo "   ❌ Arquivo não encontrado: $file"
    return 1
  fi

  psql "$DATABASE_URL" -f "$file" -q

  if [ $? -eq 0 ]; then
    echo "   ✅ Sucesso!"
  else
    echo "   ❌ Erro ao executar $file"
    return 1
  fi
  echo ""
}

# PASSO 1: Criar tabela campaign_highlights
echo "PASSO 1/3: Criar tabela campaign_highlights"
execute_sql "src/sql/create_campaign_highlights_table.sql" "Tabela de rastreamento"

# PASSO 2: Criar função get_rotated_campaign_highlights
echo "PASSO 2/3: Criar função RPC"
execute_sql "src/sql/get_rotated_campaign_highlights.sql" "Função com rotação automática"

# PASSO 3: Testar a função
echo "PASSO 3/3: Testar função"
echo "📝 Executando teste..."

psql "$DATABASE_URL" -c "SELECT COUNT(*) as total FROM get_rotated_campaign_highlights();" -q

if [ $? -eq 0 ]; then
  echo "✅ Função executada com sucesso!"
  echo ""

  # Verificar se salvou na tabela
  echo "📝 Verificando salvamento na tabela..."
  psql "$DATABASE_URL" -c "SELECT COUNT(*) as campanhas_salvas_hoje FROM campaign_highlights WHERE highlighted_at = CURRENT_DATE;" -q

  echo ""
  echo "=============================================="
  echo "🎉 Deploy concluído com sucesso!"
  echo "=============================================="
  echo ""
  echo "📋 Próximos passos:"
  echo "   1. Acesse o frontend e verifique a home"
  echo "   2. Execute: npm run dev"
  echo "   3. A rotação está ativa! Campanhas só reaparecem após 5 dias"
  echo ""
  echo "🔍 Para testar manualmente:"
  echo "   Execute: psql \"\$DATABASE_URL\" -f test_rotacao.sql"
  echo ""
else
  echo "❌ Erro ao executar a função"
  exit 1
fi
