-- Script de Teste para verificar se o sistema de highlights está funcionando

-- 1. Verificar se a tabela existe
SELECT 
  'Tabela campaign_highlights existe?' as teste,
  EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'campaign_highlights'
  ) as resultado;

-- 2. Verificar se a função existe
SELECT 
  'Função get_rotated_campaign_highlights existe?' as teste,
  EXISTS (
    SELECT FROM pg_proc 
    WHERE proname = 'get_rotated_campaign_highlights'
  ) as resultado;

-- 3. Verificar dados na tabela campaign_highlights
SELECT 
  'Registros na tabela campaign_highlights' as teste,
  COUNT(*) as total_registros,
  COUNT(DISTINCT campaign_id) as campanhas_unicas,
  MIN(highlighted_at) as primeira_data,
  MAX(highlighted_at) as ultima_data
FROM campaign_highlights;

-- 4. Verificar campanhas destacadas hoje
SELECT 
  'Campanhas destacadas HOJE' as teste,
  COUNT(*) as total,
  category,
  COUNT(*) as quantidade
FROM campaign_highlights
WHERE highlighted_at = CURRENT_DATE
GROUP BY category
ORDER BY 
  CASE category
    WHEN 'alerta_tecnico' THEN 0
    WHEN 'em_alta' THEN 1
    WHEN 'estagnada' THEN 2
    WHEN 'em_baixa' THEN 3
  END;

-- 5. Verificar campanhas em "cooldown" (não podem aparecer hoje)
SELECT 
  'Campanhas em cooldown (últimos 5 dias)' as teste,
  COUNT(DISTINCT campaign_id) as total_campanhas,
  category,
  COUNT(*) as registros
FROM campaign_highlights
WHERE highlighted_at >= CURRENT_DATE - INTERVAL '5 days'
  AND highlighted_at < CURRENT_DATE
GROUP BY category;

-- 6. Testar a função diretamente
SELECT 
  'Teste da função get_rotated_campaign_highlights' as teste,
  COUNT(*) as resultados_retornados
FROM get_rotated_campaign_highlights();

-- 7. Ver resultados detalhados da função
SELECT * FROM get_rotated_campaign_highlights()
ORDER BY 
  CASE status
    WHEN 'alerta_tecnico' THEN 0
    WHEN 'em_alta' THEN 1
    WHEN 'estagnada' THEN 2
    WHEN 'em_baixa' THEN 3
  END,
  campaign_id;

-- 8. Verificar se as campanhas foram registradas após chamar a função
SELECT 
  'Registros APÓS chamar função' as teste,
  COUNT(*) as total_registros_hoje
FROM campaign_highlights
WHERE highlighted_at = CURRENT_DATE;

-- 9. Verificar dados necessários para a função funcionar
SELECT 
  'Dados disponíveis para cálculo' as teste,
  COUNT(DISTINCT campaign_id) as campanhas_com_dados,
  MIN(date) as primeira_data,
  MAX(date) as ultima_data,
  COUNT(*) as total_registros
FROM daily_campaign_metrics
WHERE date >= CURRENT_DATE - INTERVAL '14 days';

-- 10. Verificar campanhas que atendem critérios básicos
SELECT 
  'Campanhas que atendem critérios (spend > 20, >= 3 dias)' as teste,
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














