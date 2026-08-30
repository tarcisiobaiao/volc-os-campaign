-- Script de Teste para Rotação de Campanhas
-- ARQUIVADO: o teste executa DELETE e funções com efeito; não é smoke test seguro.
-- Execute este script no Supabase SQL Editor para validar o funcionamento

-- ========================================
-- PASSO 1: Limpar dados de teste anteriores
-- ========================================
DELETE FROM campaign_highlights WHERE highlighted_at >= CURRENT_DATE - INTERVAL '10 days';

-- ========================================
-- PASSO 2: Executar a função pela primeira vez
-- ========================================
SELECT
  campaign_id,
  status,
  avg_spend,
  roas_inicio,
  roas_fim,
  variacao_roas,
  motivo
FROM get_rotated_campaign_highlights();

-- ========================================
-- PASSO 3: Verificar se salvou na tabela
-- ========================================
SELECT
  COUNT(*) as total_campanhas_salvas,
  COUNT(DISTINCT campaign_id) as campanhas_unicas,
  STRING_AGG(DISTINCT category, ', ') as categorias_usadas
FROM campaign_highlights
WHERE highlighted_at = CURRENT_DATE;

-- ========================================
-- PASSO 4: Ver detalhes do que foi salvo
-- ========================================
SELECT
  campaign_id,
  category,
  highlighted_at,
  created_at
FROM campaign_highlights
WHERE highlighted_at = CURRENT_DATE
ORDER BY category, campaign_id;

-- ========================================
-- PASSO 5: Executar novamente (deve retornar campanhas DIFERENTES)
-- ========================================
-- IMPORTANTE: As campanhas do PASSO 2 NÃO devem aparecer aqui
SELECT
  campaign_id,
  status,
  motivo
FROM get_rotated_campaign_highlights();

-- ========================================
-- PASSO 6: Verificar exclusão (campanhas do PASSO 2 vs PASSO 5)
-- ========================================
WITH primeira_execucao AS (
  SELECT DISTINCT campaign_id
  FROM campaign_highlights
  WHERE highlighted_at = CURRENT_DATE
  LIMIT 15 -- Primeiras 15 campanhas salvas
),
segunda_execucao AS (
  SELECT campaign_id
  FROM get_rotated_campaign_highlights()
)
SELECT
  'Campanhas que apareceram nas DUAS execuções (ERRO - não deveria ter nenhuma):' as teste,
  COUNT(*) as quantidade_duplicada
FROM primeira_execucao pe
WHERE pe.campaign_id IN (SELECT campaign_id FROM segunda_execucao);

-- ========================================
-- PASSO 7: Simular passagem de 6 dias (resetar cooldown)
-- ========================================
-- Atualizar highlighted_at para 6 dias atrás
UPDATE campaign_highlights
SET highlighted_at = CURRENT_DATE - INTERVAL '6 days'
WHERE highlighted_at = CURRENT_DATE;

-- Executar novamente - agora PODE retornar as mesmas campanhas
SELECT
  campaign_id,
  status,
  motivo
FROM get_rotated_campaign_highlights()
LIMIT 5;

-- ========================================
-- PASSO 8: Restaurar dados (opcional)
-- ========================================
-- Voltar as datas para hoje
UPDATE campaign_highlights
SET highlighted_at = CURRENT_DATE
WHERE highlighted_at = CURRENT_DATE - INTERVAL '6 days';

-- ========================================
-- RESULTADO ESPERADO:
-- ========================================
-- ✅ PASSO 2: Retorna até 15 campanhas (5 alta + 5 estagnada + 5 baixa + alertas)
-- ✅ PASSO 3: Mostra que salvou no mínimo 1 campanha (total_campanhas_salvas > 0)
-- ✅ PASSO 5: Retorna campanhas DIFERENTES do PASSO 2
-- ✅ PASSO 6: quantidade_duplicada = 0 (nenhuma campanha repetida)
-- ✅ PASSO 7: Após resetar cooldown, PODE retornar campanhas antigas
