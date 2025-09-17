# Sistema de Conversão de Moeda - Guia Completo

## 📋 Visão Geral

Este sistema permite armazenar valores em **dólares (USD)** no banco de dados e exibi-los automaticamente convertidos para **reais (BRL)** no dashboard, usando uma taxa de câmbio configurável manualmente.

## 🏗️ Arquitetura do Sistema

### 1. Tabela de Configurações (`system_settings`)

- **Localização**: Supabase → `system_settings`
- **Função**: Armazena configurações globais do sistema, incluindo taxa de câmbio
- **Campos principais**:
  - `dollar_exchange_rate`: Taxa atual USD/BRL (ex: "5.50")
  - `currency_display`: Moeda de exibição padrão ("BRL") 
  - `auto_convert_values`: Se ativada conversão automática ("true")
  - `last_currency_update`: Timestamp da última atualização manual

### 2. Componente de Gerenciamento (`ExchangeRateManager`)

- **Localização**: `src/components/currency/ExchangeRateManager.tsx`
- **Função**: Interface para definir taxa de câmbio manualmente
- **Características**:
  - Exibe taxa atual
  - Permite inserir nova taxa
  - Mostra exemplos de conversão
  - Registra horário da última atualização

### 3. Serviços de Backend

#### SystemSettingsService
- **Localização**: `src/services/systemSettingsService.ts`
- **Funções**:
  - Buscar/salvar configurações do sistema
  - Cache de 5 minutos para performance
  - Métodos específicos para taxa de câmbio

#### CurrencyConversionService  
- **Localização**: `src/services/currencyConversionService.ts`
- **Funções**:
  - Conversão USD ↔ BRL usando taxa configurada
  - Formatação com locale brasileiro
  - Cache inteligente
  - Conversão em lote para dashboards

### 4. Hooks React

#### useCurrencyFormatter
- **Localização**: `src/hooks/useCurrencyFormatter.ts`
- **Função**: Hook para formatação de valores com conversão automática
- **Métodos**:
  - `formatCurrency()`: Converte USD → BRL formatado
  - `batchFormatCurrency()`: Conversão em lote
  - `formatWithConversion()`: Detalhes completos da conversão

## 🎯 Como Funciona na Prática

### Fluxo de Dados

1. **Armazenamento**: Valores salvos em **USD** no banco (ex: Google Ads spend = $100)
2. **Configuração**: Taxa definida manualmente (ex: R$ 5,50 por USD)
3. **Exibição**: Sistema converte automaticamente ($100 × 5.50 = R$ 550,00)
4. **Cache**: Taxa fica em cache por 5 minutos para performance
5. **Atualização**: Ao alterar taxa, cache é limpo automaticamente

### Exemplo Prático - Dashboard

```typescript
// Dados do banco (em USD)
const campaignData = {
  spend: 1000,      // $1000 USD  
  revenue: 1500     // $1500 USD
}

// Conversão automática para exibição
const displayData = await currencyConversionService.convertDashboardData(campaignData);

// Resultado exibido
// Gasto: R$ 5.500,00  
// Revenue: R$ 8.250,00
// Lucro: R$ 2.750,00
```

## 🚀 Como Usar

### 1. Definir Taxa de Câmbio

1. Abra o **Dashboard Geral** (primeira página)
2. Localize o card **"Taxa de Câmbio USD/BRL"**
3. Digite o valor em reais que equivale a 1 dólar
4. Clique em **"Atualizar"**
5. A nova taxa será aplicada imediatamente em todo o sistema

### 2. Visualizar Valores Convertidos

- Todos os valores financeiros são exibidos automaticamente em BRL
- Passe o mouse sobre os valores para ver detalhes da conversão
- A taxa usada e timestamp aparecem no componente de câmbio

### 3. Para Desenvolvedores

#### Usar conversão em novos componentes:

```typescript
import { useCurrencyFormatter } from '@/hooks/useCurrencyFormatter';

const MyComponent = () => {
  const { formatCurrency } = useCurrencyFormatter();
  
  const formatValue = async (usdValue: number) => {
    const formatted = await formatCurrency(usdValue);
    return formatted; // "R$ 5.500,00"
  };
};
```

#### Conversão manual:

```typescript
import { currencyConversionService } from '@/services/currencyConversionService';

// Converter $100 USD para BRL
const brlValue = await currencyConversionService.convertUsdToBrl(100);
const formatted = currencyConversionService.formatCurrency(brlValue, 'BRL');
```

## Configurações Avançadas

### Desativar Conversão Automática

```sql
UPDATE system_settings 
SET value = 'false' 
WHERE key = 'auto_convert_values';
```

### Alterar Taxa via SQL

```sql
UPDATE system_settings 
SET value = '5.75', updated_at = now() 
WHERE key = 'dollar_exchange_rate';
```

### Verificar Histórico de Alterações

```sql
SELECT * FROM system_settings 
WHERE key LIKE '%currency%' 
ORDER BY updated_at DESC;
```

## 🔧 Manutenção

### Cache e Performance

- **Cache automático**: 5 minutos para taxa de câmbio
- **Limpeza**: Cache é limpo ao atualizar taxa manualmente
- **Fallback**: Se erro, usa taxa padrão (R$ 5,50)

### Logs e Debug

- Erros são logados no console do navegador
- Timestamps registrados a cada atualização manual
- Service detecta automaticamente mudanças de taxa

### Backup das Configurações

```sql
-- Backup das configurações de moeda
SELECT key, value, description, updated_at 
FROM system_settings 
WHERE category = 'currency';
```

## 📊 Impacto no Sistema

### O que é convertido:
- ✅ Valores de gasto (spend)
- ✅ Revenue/receita  
- ✅ Lucro/profit
- ✅ Totais do dashboard
- ✅ Métricas de campanhas
- ✅ Resumos por projeto

### O que NÃO é convertido:
- ❌ ROAS (permanece em %)
- ❌ ROI (permanece em %)
- ❌ CTR (permanece em %)
- ❌ Impressões e cliques (números absolutos)

## 🎯 Benefícios

1. **Flexibilidade**: Taxa ajustável sem mexer no código
2. **Performance**: Sistema de cache evita consultas desnecessárias  
3. **Consistência**: Todos os valores seguem a mesma taxa
4. **Transparência**: Usuário vê taxa atual e quando foi atualizada
5. **Fallback**: Sistema continua funcionando mesmo com erros
6. **Histórico**: Registra quando e quem alterou a taxa

## 🚨 Notas Importantes

- ⚠️ **Alterar a taxa afeta IMEDIATAMENTE todos os valores exibidos**
- ⚠️ **Dados no banco permanecem em USD** (não são alterados)
- ⚠️ **Cache é compartilhado** entre todos os usuários
- ⚠️ **Recomendado atualizar taxa diariamente** para precisão

---

*Última atualização: Setembro 2025*
*Sistema implementado por: Claude Code*