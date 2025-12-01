-- ============================================================================
-- PASSO 1: DROPAR FUNÇÃO ANTIGA
-- ============================================================================

DROP FUNCTION IF EXISTS merge_duplicate_projects(integer, integer);

-- ============================================================================
-- PASSO 2: CRIAR FUNÇÃO CORRIGIDA
-- ============================================================================

-- Função completa para mesclar projetos duplicados
-- Move dados de AMBAS as tabelas: daily_project_metrics E daily_campaign_metrics

CREATE OR REPLACE FUNCTION merge_duplicate_projects(
    project_id_to_keep INTEGER,
    project_id_to_remove INTEGER
)
RETURNS TABLE(
    status TEXT,
    campaigns_moved INTEGER,
    project_metrics_moved INTEGER,
    campaign_metrics_moved INTEGER,
    cost_sharing_moved INTEGER
) AS $$
DECLARE
    v_campaigns_moved INTEGER := 0;
    v_project_metrics_moved INTEGER := 0;
    v_campaign_metrics_moved INTEGER := 0;
    v_cost_sharing_moved INTEGER := 0;
BEGIN
    -- Validar que os projetos existem
    IF NOT EXISTS (SELECT 1 FROM projects WHERE id = project_id_to_keep) THEN
        RETURN QUERY SELECT
            'ERRO: Projeto a manter (ID ' || project_id_to_keep || ') não existe'::TEXT,
            0, 0, 0, 0;
        RETURN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM projects WHERE id = project_id_to_remove) THEN
        RETURN QUERY SELECT
            'ERRO: Projeto a remover (ID ' || project_id_to_remove || ') não existe'::TEXT,
            0, 0, 0, 0;
        RETURN;
    END IF;

    RAISE NOTICE '========================================';
    RAISE NOTICE 'Iniciando mesclagem: ID % -> ID %', project_id_to_remove, project_id_to_keep;
    RAISE NOTICE '========================================';

    -- 1. Mover campanhas
    RAISE NOTICE 'Passo 1/5: Movendo campanhas...';
    UPDATE campaigns
    SET project_id = project_id_to_keep,
        updated_at = NOW()
    WHERE project_id = project_id_to_remove;

    GET DIAGNOSTICS v_campaigns_moved = ROW_COUNT;
    RAISE NOTICE '✓ Campanhas movidas: %', v_campaigns_moved;

    -- 2. Mover métricas de PROJETO (daily_project_metrics - SEM campaign_id)
    RAISE NOTICE 'Passo 2/5: Movendo métricas de projeto (daily_project_metrics)...';
    INSERT INTO daily_project_metrics (
        project_id,
        date,
        revenue_converted,
        revenue_converted_revshare,
        url_projeto,
        created_at,
        updated_at
    )
    SELECT
        project_id_to_keep,
        date,
        revenue_converted,
        revenue_converted_revshare,
        url_projeto,
        created_at,
        NOW() as updated_at
    FROM daily_project_metrics
    WHERE project_id = project_id_to_remove
    ON CONFLICT (project_id, date)
    DO UPDATE SET
        revenue_converted = daily_project_metrics.revenue_converted + EXCLUDED.revenue_converted,
        revenue_converted_revshare = daily_project_metrics.revenue_converted_revshare + EXCLUDED.revenue_converted_revshare,
        updated_at = NOW();

    GET DIAGNOSTICS v_project_metrics_moved = ROW_COUNT;
    RAISE NOTICE '✓ Métricas de projeto movidas/consolidadas: %', v_project_metrics_moved;

    -- Deletar métricas antigas de projeto
    DELETE FROM daily_project_metrics WHERE project_id = project_id_to_remove;

    -- 3. Mover métricas de CAMPANHA (daily_campaign_metrics - COM campaign_id)
    -- Não precisa mover porque já movemos as campanhas, e o FK já está correto
    RAISE NOTICE 'Passo 3/5: Verificando métricas de campanha (daily_campaign_metrics)...';

    -- Atualizar o project_id das campanhas já atualiza automaticamente via FK
    -- Mas vamos contar quantas métricas existem para as campanhas que foram movidas
    SELECT COUNT(*) INTO v_campaign_metrics_moved
    FROM daily_campaign_metrics dcm
    JOIN campaigns c ON dcm.campaign_id = c.id
    WHERE c.project_id = project_id_to_keep;

    RAISE NOTICE '✓ Métricas de campanha associadas: %', v_campaign_metrics_moved;

    -- 4. Mover configurações de divisão de custos (se a tabela existir)
    RAISE NOTICE 'Passo 4/5: Movendo configurações de cost sharing...';
    BEGIN
        UPDATE project_cost_sharing
        SET project_id = project_id_to_keep,
            updated_at = NOW()
        WHERE project_id = project_id_to_remove;

        GET DIAGNOSTICS v_cost_sharing_moved = ROW_COUNT;
        RAISE NOTICE '✓ Configurações de cost sharing movidas: %', v_cost_sharing_moved;
    EXCEPTION
        WHEN undefined_table THEN
            RAISE NOTICE '⚠ Tabela project_cost_sharing não existe, pulando...';
            v_cost_sharing_moved := 0;
    END;

    -- 5. Marcar projeto antigo como invisível ao invés de deletar
    RAISE NOTICE 'Passo 5/5: Marcando projeto antigo como invisível...';
    UPDATE projects
    SET visible = false,
        status = 'Inactive',
        updated_at = NOW(),
        project_name = project_name || ' [MERGED INTO ID ' || project_id_to_keep || ']'
    WHERE id = project_id_to_remove;

    RAISE NOTICE '✓ Projeto ID % marcado como invisível', project_id_to_remove;
    RAISE NOTICE '========================================';
    RAISE NOTICE 'MESCLAGEM CONCLUÍDA COM SUCESSO!';
    RAISE NOTICE '========================================';

    -- Retornar resultado
    RETURN QUERY SELECT
        'SUCESSO: Projetos mesclados'::TEXT,
        v_campaigns_moved,
        v_project_metrics_moved,
        v_campaign_metrics_moved,
        v_cost_sharing_moved;
END;
$$ LANGUAGE plpgsql;

-- Comentário da função
COMMENT ON FUNCTION merge_duplicate_projects(INTEGER, INTEGER) IS
'Mescla dois projetos duplicados, movendo todas as campanhas, métricas (projeto e campanha) e configurações. Move dados de daily_project_metrics E daily_campaign_metrics.';

-- ============================================================================
-- PASSO 3: VISUALIZAÇÃO ANTES DE EXECUTAR
-- ============================================================================

SELECT '========== ANÁLISE ANTES DA MESCLAGEM ==========' as info;

-- Dados do projeto a MANTER (ID 35)
SELECT
    '🟢 Projeto ID 35 (MANTER - educacaonamao.com.br)' as tipo,
    p.id,
    p.project_name,
    p.domain,
    p.created_at,
    (SELECT COUNT(*) FROM campaigns WHERE project_id = 35) as total_campanhas,
    (SELECT COUNT(*) FROM daily_project_metrics WHERE project_id = 35) as metricas_projeto,
    (SELECT COUNT(*) FROM daily_campaign_metrics dcm
     JOIN campaigns c ON dcm.campaign_id = c.id
     WHERE c.project_id = 35) as metricas_campanha
FROM projects p WHERE p.id = 35

UNION ALL

-- Dados do projeto a REMOVER (ID 52)
SELECT
    '🔴 Projeto ID 52 (REMOVER - www.educacaonamao.com.br)' as tipo,
    p.id,
    p.project_name,
    p.domain,
    p.created_at,
    (SELECT COUNT(*) FROM campaigns WHERE project_id = 52) as total_campanhas,
    (SELECT COUNT(*) FROM daily_project_metrics WHERE project_id = 52) as metricas_projeto,
    (SELECT COUNT(*) FROM daily_campaign_metrics dcm
     JOIN campaigns c ON dcm.campaign_id = c.id
     WHERE c.project_id = 52) as metricas_campanha
FROM projects p WHERE p.id = 52;

-- Campanhas que serão movidas
SELECT '========== CAMPANHAS QUE SERÃO MOVIDAS (52 → 35) ==========' as info;

SELECT
    campaign_id,
    campaign_name,
    project_id,
    status,
    (SELECT COUNT(*) FROM daily_campaign_metrics WHERE campaign_id = campaigns.campaign_id) as metricas_campanha
FROM campaigns
WHERE project_id = 52
ORDER BY campaign_name;

-- ============================================================================
-- PASSO 4: EXECUTAR MESCLAGEM (DESCOMENTE PARA EXECUTAR)
-- ============================================================================

/*
-- ATENÇÃO: Revise os dados acima antes de executar!

SELECT * FROM merge_duplicate_projects(35, 52);

*/

-- ============================================================================
-- PASSO 5: VERIFICAÇÃO APÓS MESCLAGEM
-- ============================================================================

/*
SELECT '========== RESULTADO APÓS MESCLAGEM ==========' as info;

SELECT
    CASE
        WHEN id = 35 THEN '✅ Projeto ID 35 (ATIVO - com todos os dados)'
        WHEN id = 52 THEN '❌ Projeto ID 52 (INATIVO - mesclado)'
    END as status,
    id,
    project_name,
    domain,
    projects.status,
    visible,
    (SELECT COUNT(*) FROM campaigns WHERE project_id = projects.id) as campanhas,
    (SELECT COUNT(*) FROM daily_project_metrics WHERE project_id = projects.id) as metricas_projeto,
    (SELECT COUNT(*) FROM daily_campaign_metrics dcm
     JOIN campaigns c ON dcm.campaign_id = c.id
     WHERE c.project_id = projects.id) as metricas_campanha
FROM projects
WHERE id IN (35, 52)
ORDER BY id;

-- Ver todas as campanhas agora no projeto 35
SELECT '========== CAMPANHAS NO PROJETO ID 35 ==========' as info;

SELECT
    campaign_id,
    campaign_name,
    project_id,
    status,
    (SELECT COUNT(*) FROM daily_campaign_metrics WHERE campaign_id = campaigns.campaign_id) as metricas
FROM campaigns
WHERE project_id = 35
ORDER BY campaign_name;
*/
