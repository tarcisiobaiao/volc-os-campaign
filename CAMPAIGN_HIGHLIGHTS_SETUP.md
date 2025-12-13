# 🎯 Setup: Sistema de Rotação de Campanhas Destacadas

Este documento explica como configurar o sistema de rotação automática de campanhas destacadas na home.

## 📋 O que faz?

- **Exibe 5 campanhas em alta**, **5 estagnadas** e **5 em baixa** na home
- **Rotaciona automaticamente**: Se uma campanha aparece hoje, ela só volta a aparecer depois de **5 dias**
- **Garante diversidade**: Diferentes campanhas recebem atenção ao longo do tempo

## 🚀 Passos de Instalação

### 1. Criar a Tabela de Rastreamento

Execute o SQL no Supabase SQL Editor:

```bash
# Arquivo: webgo/src/sql/create_campaign_highlights_table.sql
```

Ou copie e cole o conteúdo do arquivo diretamente no Supabase Dashboard → SQL Editor.

### 2. Criar a RPC Function

**⚠️ IMPORTANTE:** Use a versão corrigida (`v2`) que garante que o INSERT funcione corretamente.

Execute o SQL no Supabase SQL Editor:

```bash
# Arquivo: webgo/src/sql/get_rotated_campaign_highlights_v2.sql
```

Esta função:
- Executa o SQL modificado que você forneceu
- **Exclui automaticamente** campanhas destacadas nos últimos 5 dias
- **Registra automaticamente** as campanhas selecionadas na tabela `campaign_highlights`
- **Usa tabela temporária** para garantir que o INSERT aconteça antes do RETURN

**Nota:** Se você já executou a versão antiga, a versão `v2` vai substituí-la automaticamente.

### 3. Verificar Instalação

Após executar os SQLs, execute o script de teste completo:

```bash
# Arquivo: webgo/src/sql/test_campaign_highlights.sql
```

Ou teste manualmente:

```sql
-- 1. Testar a RPC function
SELECT * FROM get_rotated_campaign_highlights();

-- 2. Verificar se registros foram criados HOJE
SELECT * FROM campaign_highlights 
WHERE highlighted_at = CURRENT_DATE
ORDER BY created_at DESC;

-- 3. Verificar se a tabela foi criada corretamente
SELECT 
  COUNT(*) as total_registros,
  COUNT(DISTINCT campaign_id) as campanhas_unicas,
  MIN(highlighted_at) as primeira_data,
  MAX(highlighted_at) as ultima_data
FROM campaign_highlights;
```

**✅ Se tudo estiver OK:**
- A função deve retornar campanhas (ou vazio se não houver dados suficientes)
- Deve haver registros na tabela `campaign_highlights` com `highlighted_at = CURRENT_DATE`
- O componente na home deve mostrar as campanhas (ou mensagem de "nenhuma campanha")

**❌ Se houver problemas:**
- Consulte `TROUBLESHOOTING_CAMPAIGN_HIGHLIGHTS.md` para diagnóstico detalhado

## 🔄 Como Funciona

### Fluxo Automático:

1. **Usuário acessa a home** → Componente `CampaignHighlights` é renderizado
2. **Componente chama** `campaignHighlightsService.getCampaignHighlights()`
3. **Serviço chama** RPC function `get_rotated_campaign_highlights()`
4. **RPC function executa**:
   - SQL modificado com exclusão de campanhas destacadas nos últimos 5 dias
   - Seleciona as campanhas (5 em alta, 5 estagnadas, 5 em baixa)
   - **Registra automaticamente** na tabela `campaign_highlights`
   - Retorna os resultados
5. **Componente exibe** as campanhas agrupadas por categoria

### Rotação de 5 Dias:

- Quando uma campanha é selecionada, ela é registrada com `highlighted_at = CURRENT_DATE`
- Na próxima execução, a função exclui campanhas onde `highlighted_at >= CURRENT_DATE - 5 days`
- Isso garante que a mesma campanha só aparece novamente após 5 dias

## 📊 Estrutura de Dados

### Tabela `campaign_highlights`:

```sql
campaign_id      BIGINT    -- ID da campanha
category         VARCHAR   -- 'em_alta', 'em_baixa', 'estagnada', 'alerta_tecnico'
highlighted_at   DATE      -- Data em que foi destacada (usado para calcular rotação)
created_at       TIMESTAMP -- Timestamp de criação
```

### RPC Function `get_rotated_campaign_highlights()`:

**Retorna:**
- `campaign_id`: ID da campanha
- `status`: Categoria ('em_alta', 'em_baixa', 'estagnada', 'alerta_tecnico')
- `avg_spend`: Gasto médio
- `roas_inicio`: ROAS inicial
- `roas_fim`: ROAS final
- `variacao_roas`: Variação percentual de ROAS
- `motivo`: Mensagem explicativa

## 🎨 Componente React

O componente `CampaignHighlights` está localizado em:
```
webgo/src/components/dashboard/CampaignHighlights.tsx
```

**Características:**
- ✅ Agrupa campanhas por categoria
- ✅ Exibe alertas técnicos com prioridade máxima
- ✅ Cards clicáveis que navegam para detalhes da campanha
- ✅ Loading states e error handling
- ✅ Cache de 5 minutos para performance

## 🔧 Manutenção

### Limpar Histórico Antigo (Opcional):

Se quiser limpar registros muito antigos (> 30 dias):

```sql
DELETE FROM campaign_highlights 
WHERE highlighted_at < CURRENT_DATE - INTERVAL '30 days';
```

### Verificar Rotação:

```sql
-- Ver campanhas destacadas hoje
SELECT * FROM campaign_highlights 
WHERE highlighted_at = CURRENT_DATE;

-- Ver campanhas que estão "em cooldown" (não podem aparecer hoje)
SELECT DISTINCT campaign_id 
FROM campaign_highlights 
WHERE highlighted_at >= CURRENT_DATE - INTERVAL '5 days'
  AND highlighted_at < CURRENT_DATE;
```

## ⚠️ Troubleshooting

### Problema: Nenhuma campanha aparece

**Solução:**
1. Verifique se há dados em `daily_campaign_metrics` dos últimos 14 dias
2. Verifique se há campanhas com `avg_spend > 20` e pelo menos 3 dias de dados
3. Execute manualmente: `SELECT * FROM get_rotated_campaign_highlights();`

### Problema: Mesmas campanhas aparecem sempre

**Solução:**
1. Verifique se a tabela `campaign_highlights` está sendo populada:
   ```sql
   SELECT * FROM campaign_highlights ORDER BY highlighted_at DESC LIMIT 20;
   ```
2. Se não há registros, a função pode não estar registrando. Verifique os logs do Supabase.

### Problema: Erro ao chamar RPC function

**Solução:**
1. Verifique se a função foi criada:
   ```sql
   SELECT proname FROM pg_proc WHERE proname = 'get_rotated_campaign_highlights';
   ```
2. Verifique permissões: A função precisa ter acesso às tabelas `campaigns`, `projects`, `daily_campaign_metrics` e `campaign_highlights`

## 📝 Notas Importantes

- ⚠️ **A função registra automaticamente** as campanhas selecionadas. Não é necessário chamar manualmente.
- ⚠️ **O cache do serviço** é de 5 minutos. Para forçar atualização, chame `campaignHighlightsService.clearCache()`
- ⚠️ **A rotação é baseada em dias**, não horas. Uma campanha destacada hoje só pode aparecer novamente após 5 dias completos.

