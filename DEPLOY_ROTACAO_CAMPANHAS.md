# Deploy da Rotação de Campanhas Destacadas

## O que foi implementado

✅ **Sistema de Rotação Automática**: Campanhas destacadas só podem reaparecer após 5 dias
✅ **Salvamento Automático**: A função `get_rotated_campaign_highlights()` agora registra automaticamente na tabela `campaign_highlights`
✅ **Exclusão Inteligente**: O SQL já exclui campanhas que foram destacadas nos últimos 5 dias

## Passos para Deploy

### 1. Criar a tabela `campaign_highlights` (se ainda não existir)

Execute no Supabase SQL Editor:

```sql
-- Arquivo: create_campaign_highlights_table.sql
```

Ou execute diretamente:

```bash
cd webgo
npx supabase db push --file src/sql/create_campaign_highlights_table.sql
```

### 2. Criar/Atualizar a função RPC

Execute no Supabase SQL Editor:

```sql
-- Arquivo: get_rotated_campaign_highlights.sql
```

Ou execute:

```bash
cd webgo
npx supabase db push --file src/sql/get_rotated_campaign_highlights.sql
```

### 3. Verificar se funcionou

Execute no Supabase SQL Editor:

```sql
-- Chamar a função
SELECT * FROM get_rotated_campaign_highlights();

-- Verificar se salvou na tabela
SELECT * FROM campaign_highlights ORDER BY highlighted_at DESC;
```

## Como funciona

### 1. **Exclusão de Campanhas Recentes**

```sql
-- Para alertas técnicos
AND m.campaign_id NOT IN (
  SELECT ch.campaign_id
  FROM campaign_highlights ch
  WHERE ch.highlighted_at >= CURRENT_DATE - INTERVAL '5 days'
    AND ch.category = 'alerta_tecnico'
)

-- Para campanhas normais (em_alta, em_baixa, estagnada)
AND m.campaign_id NOT IN (
  SELECT ch.campaign_id
  FROM campaign_highlights ch
  WHERE ch.highlighted_at >= CURRENT_DATE - INTERVAL '5 days'
)
```

### 2. **Salvamento Automático**

Após executar o SQL e coletar os resultados:

```sql
INSERT INTO campaign_highlights (campaign_id, category, highlighted_at)
SELECT DISTINCT
  th.campaign_id,
  th.status::VARCHAR,
  CURRENT_DATE
FROM temp_highlights th
ON CONFLICT (campaign_id, category, highlighted_at) DO NOTHING;
```

### 3. **Uso no Frontend**

O serviço TypeScript já está configurado:

```typescript
// Buscar campanhas destacadas (já com rotação aplicada)
const highlights = await campaignHighlightsService.getCampaignHighlights();

// Ou agrupadas por categoria
const grouped = await campaignHighlightsService.getCampaignHighlightsGrouped();
```

## Comportamento Esperado

### Dia 1 (Hoje)
- SQL retorna: 5 em alta, 5 estagnadas, 5 em baixa, X alertas técnicos
- Salva automaticamente na tabela `campaign_highlights`

### Dia 2-5
- SQL exclui as campanhas do Dia 1
- Retorna NOVAS campanhas que não foram destacadas recentemente
- Salva as novas campanhas

### Dia 6
- As campanhas do Dia 1 podem aparecer novamente (passaram 5 dias)
- O ciclo se repete

## Tabela campaign_highlights

Estrutura:

```sql
CREATE TABLE campaign_highlights (
  id BIGSERIAL PRIMARY KEY,
  campaign_id BIGINT NOT NULL,
  category VARCHAR(50) NOT NULL, -- 'em_alta', 'em_baixa', 'estagnada', 'alerta_tecnico'
  highlighted_at DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),

  UNIQUE(campaign_id, category, highlighted_at)
);
```

### Queries Úteis

```sql
-- Ver histórico de uma campanha
SELECT *
FROM campaign_highlights
WHERE campaign_id = 123
ORDER BY highlighted_at DESC;

-- Ver quantas vezes cada campanha foi destacada
SELECT
  campaign_id,
  COUNT(*) as vezes_destacada,
  STRING_AGG(DISTINCT category, ', ') as categorias,
  MIN(highlighted_at) as primeira_vez,
  MAX(highlighted_at) as ultima_vez
FROM campaign_highlights
GROUP BY campaign_id
ORDER BY vezes_destacada DESC;

-- Limpar dados antigos (opcional - manter histórico de 30 dias)
DELETE FROM campaign_highlights
WHERE highlighted_at < CURRENT_DATE - INTERVAL '30 days';
```

## Troubleshooting

### Problema: "Sempre aparecem as mesmas campanhas"

```sql
-- Verificar se está salvando corretamente
SELECT COUNT(*) FROM campaign_highlights WHERE highlighted_at = CURRENT_DATE;

-- Se retornar 0, a função não está salvando
-- Executar novamente o SQL de criação da função
```

### Problema: "Não aparece nenhuma campanha"

```sql
-- Verificar se há dados
SELECT COUNT(*) FROM daily_campaign_metrics
WHERE date >= CURRENT_DATE - INTERVAL '14 days';

-- Verificar quantas campanhas estão em cooldown
SELECT COUNT(DISTINCT campaign_id) FROM campaign_highlights
WHERE highlighted_at >= CURRENT_DATE - INTERVAL '5 days';
```

### Problema: "Erro 42883 - function does not exist"

Execute novamente:

```bash
cd webgo
npx supabase db push --file src/sql/get_rotated_campaign_highlights.sql
```

## Cache no Frontend

O serviço tem cache de 5 minutos:

```typescript
// Limpar cache manualmente (se precisar forçar refresh)
campaignHighlightsService.clearCache();
```

## Próximos Passos (Opcional)

1. **Cron Job Diário**: Executar `get_rotated_campaign_highlights()` todo dia às 6h AM
2. **Dashboard de Analytics**: Criar página para visualizar histórico de highlights
3. **Notificações**: Alertar quando uma campanha entra em "alerta_tecnico"
4. **Export CSV**: Permitir download do histórico de campanhas destacadas
