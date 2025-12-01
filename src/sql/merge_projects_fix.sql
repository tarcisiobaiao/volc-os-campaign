-- Função corrigida para mesclar projetos duplicados
-- Versão compatível com a estrutura atual de daily_project_metrics

CREATE OR REPLACE FUNCTION merge_duplicate_projects(
    project_id_to_keep INTEGER,
    project_id_to_remove INTEGER
)
RETURNS TABLE(
    status TEXT,
    campaigns_moved INTEGER,
    metrics_moved INTEGER,
    cost_sharing_moved INTEGER
) AS $$
DECLARE
    v_campaigns_moved INTEGER := 0;
    v_metrics_moved INTEGER := 0;
    v_cost_sharing_moved INTEGER := 0;
BEGIN
    -- Validar que os projetos existem
    IF NOT EXISTS (SELECT 1 FROM projects WHERE id = project_id_to_keep) THEN
        RETURN QUERY SELECT
            'ERRO: Projeto a manter (ID ' || project_id_to_keep || ') não existe'::TEXT,
            0, 0, 0;
        RETURN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM projects WHERE id = project_id_to_remove) THEN
        RETURN QUERY SELECT
            'ERRO: Projeto a remover (ID ' || project_id_to_remove || ') não existe'::TEXT,
            0, 0, 0;
        RETURN;
    END IF;

    RAISE NOTICE 'Iniciando mesclagem: ID % -> ID %', project_id_to_remove, project_id_to_keep;

    -- 1. Mover campanhas
    UPDATE campaigns
    SET project_id = project_id_to_keep,
        updated_at = NOW()
    WHERE project_id = project_id_to_remove;

    GET DIAGNOSTICS v_campaigns_moved = ROW_COUNT;
    RAISE NOTICE 'Campanhas movidas: %', v_campaigns_moved;

    -- 2. Mover métricas diárias (SEM campaign_id que não existe)
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

    GET DIAGNOSTICS v_metrics_moved = ROW_COUNT;
    RAISE NOTICE 'Métricas movidas/consolidadas: %', v_metrics_moved;

    -- Deletar métricas antigas do projeto que será removido
    DELETE FROM daily_project_metrics WHERE project_id = project_id_to_remove;

    -- 3. Mover configurações de divisão de custos (se a tabela existir)
    BEGIN
        UPDATE project_cost_sharing
        SET project_id = project_id_to_keep,
            updated_at = NOW()
        WHERE project_id = project_id_to_remove;

        GET DIAGNOSTICS v_cost_sharing_moved = ROW_COUNT;
        RAISE NOTICE 'Configurações de cost sharing movidas: %', v_cost_sharing_moved;
    EXCEPTION
        WHEN undefined_table THEN
            RAISE NOTICE 'Tabela project_cost_sharing não existe, pulando...';
            v_cost_sharing_moved := 0;
    END;

    -- 4. Marcar projeto antigo como invisível ao invés de deletar
    UPDATE projects
    SET visible = false,
        status = 'Inactive',
        updated_at = NOW(),
        project_name = project_name || ' [MERGED INTO ID ' || project_id_to_keep || ']'
    WHERE id = project_id_to_remove;

    RAISE NOTICE 'Projeto ID % marcado como invisível', project_id_to_remove;

    -- Retornar resultado
    RETURN QUERY SELECT
        'SUCESSO: Projetos mesclados'::TEXT,
        v_campaigns_moved,
        v_metrics_moved,
        v_cost_sharing_moved;
END;
$$ LANGUAGE plpgsql;

-- Comentário da função
COMMENT ON FUNCTION merge_duplicate_projects(INTEGER, INTEGER) IS
'Mescla dois projetos duplicados, movendo todas as campanhas, métricas e configurações do projeto a ser removido para o projeto a ser mantido. Versão corrigida sem campaign_id.';

-- ============================================================================
-- EXEMPLO DE USO
-- ============================================================================

-- Ver o que será mesclado antes de executar
SELECT
    'Projeto ID 35 (MANTER):' as tipo,
    id,
    project_name,
    domain,
    (SELECT COUNT(*) FROM campaigns WHERE project_id = 35) as campanhas,
    (SELECT COUNT(*) FROM daily_project_metrics WHERE project_id = 35) as metricas
FROM projects WHERE id = 35

UNION ALL

SELECT
    'Projeto ID 52 (REMOVER):' as tipo,
    id,
    project_name,
    domain,
    (SELECT COUNT(*) FROM campaigns WHERE project_id = 52) as campanhas,
    (SELECT COUNT(*) FROM daily_project_metrics WHERE project_id = 52) as metricas
FROM projects WHERE id = 52;

-- Executar mesclagem (DESCOMENTE PARA EXECUTAR)
/*
SELECT * FROM merge_duplicate_projects(35, 52);
*/

-- Verificar resultado após mesclagem
/*
SELECT
    'Após mesclagem:' as info;

SELECT
    id,
    project_name,
    domain,
    status,
    visible,
    (SELECT COUNT(*) FROM campaigns WHERE project_id = projects.id) as campanhas,
    (SELECT COUNT(*) FROM daily_project_metrics WHERE project_id = projects.id) as metricas
FROM projects
WHERE id IN (35, 52);

-- Ver campanhas do projeto mesclado
SELECT
    campaign_id,
    campaign_name,
    project_id,
    status
FROM campaigns
WHERE project_id = 35
ORDER BY campaign_name;
*/
