-- ARQUIVADO: correção one-off de role/comissões; não é migração idempotente oficial.
-- ============================================================
-- EXECUTAR ESTE SQL NO SUPABASE SQL EDITOR
-- Fix: Corrigir role de 'OPERADOR' para 'OPERATOR' e recalcular comissões
-- ============================================================

-- 1. Atualizar função get_campaign_operator_commission_percentage
CREATE OR REPLACE FUNCTION get_campaign_operator_commission_percentage(campaign_id_param TEXT)
RETURNS NUMERIC AS $$
DECLARE
    commission_pct NUMERIC;
BEGIN
    SELECT COALESCE(u.commission_percentage, 0) INTO commission_pct
    FROM user_campaigns uc
    JOIN users u ON u.id = uc.user_id
    WHERE uc.campaign_id = campaign_id_param
      AND u.role = 'OPERATOR'
    LIMIT 1;
    RETURN COALESCE(commission_pct, 0);
END;
$$ LANGUAGE plpgsql STABLE;

-- 2. Atualizar função recalculate_all_operator_commissions
CREATE OR REPLACE FUNCTION recalculate_all_operator_commissions()
RETURNS void AS $$
DECLARE
    total_affected INTEGER := 0;
BEGIN
    UPDATE daily_campaign_metrics dcm
    SET commission_operator = calculate_operator_commission(
            dcm.revenue_converted_revshare,
            dcm.spend,
            COALESCE(u.commission_percentage, 0),
            dcm.date
        ),
        updated_at = NOW()
    FROM user_campaigns uc
    JOIN users u ON u.id = uc.user_id
    WHERE dcm.campaign_id = uc.campaign_id
      AND u.role = 'OPERATOR';
    GET DIAGNOSTICS total_affected = ROW_COUNT;
    RAISE NOTICE 'Recalculated % campaign metrics with operator commissions', total_affected;
END;
$$ LANGUAGE plpgsql;

-- 3. Recriar trigger
DROP TRIGGER IF EXISTS trigger_user_commission_update ON users;
CREATE TRIGGER trigger_user_commission_update
    AFTER UPDATE OF commission_percentage ON users
    FOR EACH ROW
    WHEN (NEW.role = 'OPERATOR')
    EXECUTE FUNCTION trigger_update_user_commission();

-- 4. Recriar índice
DROP INDEX IF EXISTS idx_users_commission_percentage;
CREATE INDEX idx_users_commission_percentage
ON users(commission_percentage, role) WHERE role = 'OPERATOR';

-- 5. RECALCULAR COMISSÕES DE 2025-10-20 EM DIANTE
UPDATE daily_campaign_metrics dcm
SET commission_operator = calculate_operator_commission(
        dcm.revenue_converted_revshare,
        dcm.spend,
        COALESCE(u.commission_percentage, 0),
        dcm.date
    ),
    updated_at = NOW()
FROM user_campaigns uc
JOIN users u ON u.id = uc.user_id
WHERE dcm.campaign_id = uc.campaign_id
  AND u.role = 'OPERATOR'
  AND u.commission_percentage > 0
  AND dcm.date >= '2025-10-20'
  AND dcm.revenue_converted_revshare IS NOT NULL
  AND dcm.spend IS NOT NULL;

-- 6. VERIFICAR RESULTADOS PARA marliseac@gmail.com
SELECT
    dcm.date,
    COUNT(DISTINCT dcm.campaign_id) as campaigns_count,
    SUM(dcm.revenue_converted_revshare) as total_revenue,
    SUM(dcm.spend) as total_spend,
    SUM(dcm.commission_operator) as total_commission,
    u.email,
    u.commission_percentage
FROM daily_campaign_metrics dcm
JOIN campaigns c ON c.id = dcm.campaign_id
JOIN user_campaigns uc ON uc.campaign_id = dcm.campaign_id
JOIN users u ON u.id = uc.user_id
WHERE u.email = 'marliseac@gmail.com'
  AND dcm.date >= '2025-10-20'
  AND dcm.commission_operator > 0
GROUP BY dcm.date, u.email, u.commission_percentage
ORDER BY dcm.date DESC;

-- 7. RESUMO POR OPERADOR
SELECT
    u.email,
    u.commission_percentage,
    COUNT(DISTINCT uc.campaign_id) as assigned_campaigns,
    COUNT(DISTINCT dcm.id) as metrics_with_commission,
    ROUND(SUM(dcm.commission_operator), 2) as total_commission,
    MIN(dcm.date) as first_commission_date,
    MAX(dcm.date) as last_commission_date
FROM users u
JOIN user_campaigns uc ON uc.user_id = u.id
LEFT JOIN daily_campaign_metrics dcm ON dcm.campaign_id = uc.campaign_id AND dcm.commission_operator > 0
WHERE u.role = 'OPERATOR'
  AND u.commission_percentage > 0
GROUP BY u.id, u.email, u.commission_percentage
ORDER BY u.email;
