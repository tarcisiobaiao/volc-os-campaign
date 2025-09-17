# Implementação de Conversão de Revenue USD → BRL

## Resumo da Implementação

Foi implementado um sistema completo de conversão de moeda que permite:

1. **Definir taxa de câmbio manual** através do componente ExchangeRateManager
2. **Armazenar valores convertidos** na nova coluna `revenue_converted` 
3. **Exibir automaticamente valores em reais** em todo o sistema
4. **Manter compatibilidade** com dados existentes

## 📁 Arquivos Modificados/Criados

### 1. Migração do Banco de Dados
**Arquivo:** `src/sql/add_revenue_converted_column.sql`
- Adiciona coluna `revenue_converted` nas tabelas `daily_campaign_metrics` e `gam_metrics`
- Cria funções e triggers para conversão automática
- Atualiza valores existentes com taxa atual

### 2. Serviço de Conversão de Moeda
**Arquivo:** `src/services/currencyConversionService.ts`
- **Novos métodos:**
  - `updateDatabaseConversions()`: Atualiza todas as conversões no banco
  - `getRevenueValue()`: Obtém valor priorizando coluna convertida
  - `batchGetRevenueValues()`: Processamento em lote

### 3. Hooks Atualizados
**Arquivo:** `src/hooks/useCurrencyFormatter.ts`
- **Hook existente atualizado:** `useCurrencyFormatter` agora suporta registros com `revenue_converted`
- **Novo hook:** `useRevenueFormatter` específico para dados de revenue

### 4. Utilitários de Moeda
**Arquivo:** `src/utils/currencyUtils.ts`
- **Novas funções:**
  - `formatRevenueCurrency()`: Formata revenue priorizando valor convertido
  - `getRevenueDisplayValue()`: Obtém valor de exibição com metadados
  - `batchFormatRevenueCurrency()`: Formatação em lote

### 5. Componente de Gestão
**Arquivo:** `src/components/currency/ExchangeRateManager.tsx`
- Atualizado para chamar `updateDatabaseConversions()` quando taxa é alterada
- Feedback melhorado no toast de sucesso

### 6. Serviço de Dados
**Arquivo:** `src/services/supabaseDataService.ts`
- Consultas SQL atualizadas para incluir `revenue_converted`
- Lógica de agregação atualizada para priorizar valores convertidos

## 🚀 Como Usar

### 1. Aplicar Migração do Banco
```sql
-- Execute o arquivo SQL:
\i src/sql/add_revenue_converted_column.sql
```

### 2. Configurar Taxa de Câmbio Manual
```typescript
// No frontend, use o componente ExchangeRateManager
import { ExchangeRateManager } from '@/components/currency/ExchangeRateManager';

// O componente permite:
// - Visualizar taxa atual
// - Definir nova taxa manualmente
// - Atualizar automaticamente todas as conversões no banco
```

### 3. Usar nos Componentes
```typescript
// Novo hook para revenue
import { useRevenueFormatter } from '@/hooks/useCurrencyFormatter';

const MyComponent = () => {
  const { formatRevenue } = useRevenueFormatter();
  
  // Prioriza revenue_converted se disponível
  const displayRevenue = await formatRevenue(1000, 5500); // USD, BRL convertido
  
  return <div>{displayRevenue.formatted}</div>;
};
```

### 4. Usar Utilitários Diretos
```typescript
import { formatRevenueCurrency, getRevenueDisplayValue } from '@/utils/currencyUtils';

// Formatação simples
const formatted = await formatRevenueCurrency(1000, 5500);

// Com metadados completos
const { value, formatted, isFromDatabase } = await getRevenueDisplayValue(1000, 5500);
```

## 🔄 Fluxo de Funcionamento

### 1. Configuração da Taxa
1. User abre ExchangeRateManager
2. Define nova taxa (ex: R$ 5,50)
3. Sistema salva em `system_settings.dollar_exchange_rate`
4. Trigger automático atualiza todas as `revenue_converted`

### 2. Exibição de Dados
1. **Se `revenue_converted` existe e > 0:** usa valor do banco (rápido)
2. **Se não:** converte USD → BRL on-the-fly (compatibilidade)

### 3. Novos Dados
1. Quando novos registros de revenue são inseridos
2. Trigger automático calcula `revenue_converted`
3. Valor já fica disponível para exibição

## 📊 Estrutura de Dados

### Tabela: `daily_campaign_metrics`
```sql
-- Colunas existentes
revenue NUMERIC,           -- Valor original em USD
-- Nova coluna
revenue_converted NUMERIC  -- Valor convertido em BRL
```

### Tabela: `gam_metrics`
```sql
-- Colunas existentes
revenue NUMERIC,           -- Valor original em USD
-- Nova coluna  
revenue_converted NUMERIC  -- Valor convertido em BRL
```

### Configuração: `system_settings`
```sql
key = 'dollar_exchange_rate'
value = '5.50'  -- Taxa atual USD → BRL
```

## ✅ Vantagens da Implementação

1. **Performance:** Valores convertidos são pré-calculados e armazenados
2. **Consistência:** Todos os valores usam a mesma taxa de conversão
3. **Flexibilidade:** Taxa pode ser ajustada manualmente conforme necessário
4. **Compatibilidade:** Dados antigos continuam funcionando
5. **Auditoria:** Histórico de quando as taxas foram alteradas
6. **Eficiência:** Conversões em lote para grandes datasets

## 🔧 Manutenção

### Verificar Status das Conversões
```sql
-- Ver quantos registros têm conversão
SELECT 
  COUNT(*) as total,
  COUNT(revenue_converted) as converted
FROM daily_campaign_metrics;
```

### Forçar Recálculo Manual
```sql
-- Se necessário, pode chamar a função diretamente
SELECT update_all_revenue_conversions();
```

### Logs e Monitoramento
- Triggers geram logs com `RAISE NOTICE`
- ExchangeRateManager mostra feedback visual
- Console logs nos serviços para debugging

## 📝 Próximos Passos

1. **Executar migração** no banco de dados
2. **Testar componente** ExchangeRateManager
3. **Verificar dashboards** se valores estão em reais
4. **Monitorar performance** nas consultas
5. **Documentar** para equipe como configurar taxa

---

**Importante:** O sistema mantém total compatibilidade com dados existentes. Todos os valores de revenue serão exibidos em reais, seja usando a coluna `revenue_converted` (quando disponível) ou convertendo on-the-fly do valor USD original.




