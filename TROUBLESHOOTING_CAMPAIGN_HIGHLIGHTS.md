# 🔧 Troubleshooting: Sistema de Campanhas Destacadas

## Problema: Tabela `campaign_highlights` não está sendo populada

### Passo 1: Verificar se a função existe

Execute no Supabase SQL Editor:

```sql
SELECT proname, prosrc 
FROM pg_proc 
WHERE proname = 'get_rotated_campaign_highlights';
```

**Se não retornar nada:** A função não foi criada. Execute o arquivo `get_rotated_campaign_highlights_v2.sql`.

### Passo 2: Testar a função manualmente

Execute no Supabase SQL Editor:

```sql
-- Testar a função
SELECT * FROM get_rotated_campaign_highlights();
```

**Se retornar erro:** Verifique o erro e corrija. Erros comuns:
- `relation "campaign_highlights" does not exist` → Execute `create_campaign_highlights_table.sql`
- `function does not exist` → Execute `get_rotated_campaign_highlights_v2.sql`
- Erro de tipo/permissão → Verifique permissões da função

### Passo 3: Verificar se há dados suficientes

Execute o script de teste completo:

```sql
-- Arquivo: test_campaign_highlights.sql
```

Isso vai mostrar:
- Se a tabela existe
- Se a função existe
- Quantos registros há na tabela
- Se há dados em `daily_campaign_metrics`
- Se há campanhas que atendem os critérios

### Passo 4: Verificar logs no console do navegador

Abra o DevTools (F12) e procure por:
- `🔄 Fetching campaign highlights from RPC...`
- `✅ RPC call successful`
- `❌ Error calling get_rotated_campaign_highlights RPC`

### Passo 5: Verificar se a função está registrando

Execute após chamar a função:

```sql
-- Verificar se registros foram criados HOJE
SELECT * FROM campaign_highlights 
WHERE highlighted_at = CURRENT_DATE
ORDER BY created_at DESC;
```

**Se não houver registros:** A função pode estar retornando vazio ou o INSERT não está funcionando.

## Problema: Função retorna vazio mas deveria retornar campanhas

### Verificar critérios básicos:

```sql
-- Verificar se há campanhas que atendem critérios básicos
SELECT 
  campaign_id,
  COUNT(*) as dias_com_dados,
  AVG(spend) as avg_spend,
  AVG(CASE WHEN spend > 0 THEN revenue_converted_revshare / spend ELSE 0 END) as avg_roas
FROM daily_campaign_metrics
WHERE date >= CURRENT_DATE - INTERVAL '14 days'
GROUP BY campaign_id
HAVING COUNT(*) >= 3 AND AVG(spend) > 20
ORDER BY avg_spend DESC
LIMIT 20;
```

**Se não retornar nada:** Não há campanhas com dados suficientes. Isso é normal se:
- Não há dados dos últimos 14 dias
- Campanhas têm `spend` médio <= 20
- Campanhas têm menos de 3 dias de dados

### Verificar se todas as campanhas estão em cooldown:

```sql
-- Verificar campanhas em cooldown
SELECT DISTINCT campaign_id 
FROM campaign_highlights 
WHERE highlighted_at >= CURRENT_DATE - INTERVAL '5 days';
```

**Se todas as campanhas elegíveis estão em cooldown:** Isso é esperado! A rotação está funcionando. Novas campanhas aparecerão quando:
- Passarem 5 dias desde a última vez que foram destacadas
- Novas campanhas atendam os critérios

## Problema: Erro no frontend

### Erro: "Função não encontrada"

**Solução:** Execute `get_rotated_campaign_highlights_v2.sql` no Supabase SQL Editor.

### Erro: "Tabela campaign_highlights não existe"

**Solução:** Execute `create_campaign_highlights_table.sql` no Supabase SQL Editor.

### Erro: "No campaign highlights returned"

**Possíveis causas:**
1. Não há campanhas que atendem critérios → Normal, não é erro
2. Todas as campanhas estão em cooldown → Normal, rotação funcionando
3. Não há dados em `daily_campaign_metrics` → Verifique sincronização de dados

## Solução Rápida: Recriar tudo do zero

Se nada funcionar, execute na ordem:

```sql
-- 1. Dropar função antiga (se existir)
DROP FUNCTION IF EXISTS get_rotated_campaign_highlights();

-- 2. Criar tabela (se não existir)
-- Execute: create_campaign_highlights_table.sql

-- 3. Criar função nova
-- Execute: get_rotated_campaign_highlights_v2.sql

-- 4. Testar
SELECT * FROM get_rotated_campaign_highlights();

-- 5. Verificar se registros foram criados
SELECT * FROM campaign_highlights WHERE highlighted_at = CURRENT_DATE;
```

## Verificar se está funcionando corretamente

### Teste completo:

1. **Chamar a função:**
   ```sql
   SELECT * FROM get_rotated_campaign_highlights();
   ```

2. **Verificar se registros foram criados:**
   ```sql
   SELECT COUNT(*) FROM campaign_highlights WHERE highlighted_at = CURRENT_DATE;
   ```

3. **Chamar novamente (deve retornar os mesmos resultados):**
   ```sql
   SELECT * FROM get_rotated_campaign_highlights();
   ```

4. **Verificar que não foram criados registros duplicados:**
   ```sql
   SELECT campaign_id, category, COUNT(*) 
   FROM campaign_highlights 
   WHERE highlighted_at = CURRENT_DATE
   GROUP BY campaign_id, category
   HAVING COUNT(*) > 1;
   ```
   **Deve retornar vazio** (sem duplicatas devido ao UNIQUE constraint)

5. **Simular passagem de 5 dias:**
   ```sql
   -- Atualizar registros para 6 dias atrás (fora do cooldown)
   UPDATE campaign_highlights 
   SET highlighted_at = CURRENT_DATE - INTERVAL '6 days'
   WHERE highlighted_at = CURRENT_DATE;
   ```

6. **Chamar função novamente (deve retornar campanhas diferentes):**
   ```sql
   SELECT * FROM get_rotated_campaign_highlights();
   ```

## Logs Úteis

No console do navegador, você deve ver:

```
🔄 Fetching campaign highlights from RPC...
✅ RPC call successful. Results: X campaigns
📊 Highlights grouped: { alertas_tecnicos: X, em_alta: X, estagnadas: X, em_baixa: X }
```

Se ver erros, copie e cole aqui para análise.














