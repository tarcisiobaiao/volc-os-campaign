-- Script para mesclar projetos duplicados (com www vs sem www)
-- Este script identifica e mescla projetos que diferem apenas pelo prefixo www.

-- ============================================================================
-- PARTE 1: IDENTIFICAR PROJETOS DUPLICADOS
-- ============================================================================

-- Visualizar projetos duplicados (com www vs sem www)
SELECT
    'Projetos com www que têm duplicata sem www:' as info;

SELECT
    p_www.id as id_com_www,
    p_www.project_name as nome_com_www,
    p_www.domain as domain_com_www,
    p_www.created_at as criado_em_www,
    p_sem.id as id_sem_www,
    p_sem.project_name as nome_sem_www,
    p_sem.domain as domain_sem_www,
    p_sem.created_at as criado_em_sem_www,
    CASE
        WHEN p_www.created_at > p_sem.created_at THEN 'Manter ID ' || p_sem.id || ' (mais antigo)'
        ELSE 'Manter ID ' || p_www.id || ' (mais antigo)'
    END as recomendacao
FROM projects p_www
JOIN projects p_sem ON REPLACE(LOWER(p_www.domain), 'www.', '') = LOWER(p_sem.domain)
WHERE LOWER(p_www.domain) LIKE 'www.%'
  AND LOWER(p_sem.domain) NOT LIKE 'www.%'
ORDER BY p_sem.created_at;

-- ============================================================================
-- PARTE 2: FUNÇÃO PARA MESCLAR PROJETOS
-- ============================================================================

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

    -- 1. Mover campanhas
    UPDATE campaigns
    SET project_id = project_id_to_keep,
        updated_at = NOW()
    WHERE project_id = project_id_to_remove;

    GET DIAGNOSTICS v_campaigns_moved = ROW_COUNT;

    -- 2. Mover métricas diárias
    -- Usar ON CONFLICT para evitar duplicatas de mesma data
    INSERT INTO daily_project_metrics (
        project_id,
        date,
        revenue_converted,
        revenue_converted_revshare,
        url_projeto,
        campaign_id,
        created_at,
        updated_at
    )
    SELECT
        project_id_to_keep,
        date,
        revenue_converted,
        revenue_converted_revshare,
        url_projeto,
        campaign_id,
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

    -- Deletar métricas antigas do projeto que será removido
    DELETE FROM daily_project_metrics WHERE project_id = project_id_to_remove;

    -- 3. Mover configurações de divisão de custos
    UPDATE project_cost_sharing
    SET project_id = project_id_to_keep,
        updated_at = NOW()
    WHERE project_id = project_id_to_remove;

    GET DIAGNOSTICS v_cost_sharing_moved = ROW_COUNT;

    -- 4. Marcar projeto antigo como invisível ao invés de deletar
    UPDATE projects
    SET visible = false,
        status = 'Inactive',
        updated_at = NOW(),
        project_name = project_name || ' [MERGED INTO ID ' || project_id_to_keep || ']'
    WHERE id = project_id_to_remove;

    -- Retornar resultado
    RETURN QUERY SELECT
        'SUCESSO: Projetos mesclados'::TEXT,
        v_campaigns_moved,
        v_metrics_moved,
        v_cost_sharing_moved;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PARTE 3: EXECUTAR MESCLAGEM (COMENTADO - DESCOMENTAR PARA EXECUTAR)
-- ============================================================================

/*
-- ATENÇÃO: Revise os IDs antes de executar!

-- Exemplo específico: educacaonamao.com.br
-- ID 35: educacaonamao.com.br (criado em 2025-08-29) - MANTER
-- ID 52: www.educacaonamao.com.br (criado em 2025-11-25) - REMOVER

SELECT * FROM merge_duplicate_projects(
    35,  -- project_id_to_keep (projeto SEM www, mais antigo)
    52   -- project_id_to_remove (projeto COM www, mais novo)
);

-- Verificar resultado
SELECT
    'Após mesclagem:' as info;

SELECT
    id,
    project_name,
    domain,
    status,
    visible,
    (SELECT COUNT(*) FROM campaigns WHERE project_id = projects.id) as total_campaigns,
    (SELECT COUNT(*) FROM daily_project_metrics WHERE project_id = projects.id) as total_metrics
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

-- ============================================================================
-- PARTE 4: SCRIPT AUTOMÁTICO PARA MESCLAR TODOS OS DUPLICADOS
-- ============================================================================

-- Função para mesclar automaticamente todos os projetos www duplicados
CREATE OR REPLACE FUNCTION merge_all_www_duplicates()
RETURNS TABLE(
    domain_merged TEXT,
    kept_project_id INTEGER,
    removed_project_id INTEGER,
    campaigns_moved INTEGER,
    metrics_moved INTEGER
) AS $$
DECLARE
    duplicate_record RECORD;
    merge_result RECORD;
BEGIN
    -- Iterar sobre todos os duplicados (www vs sem www)
    FOR duplicate_record IN
        SELECT
            p_sem.id as id_to_keep,
            p_www.id as id_to_remove,
            p_sem.domain as clean_domain
        FROM projects p_www
        JOIN projects p_sem ON REPLACE(LOWER(p_www.domain), 'www.', '') = LOWER(p_sem.domain)
        WHERE LOWER(p_www.domain) LIKE 'www.%'
          AND LOWER(p_sem.domain) NOT LIKE 'www.%'
          AND p_www.visible = true
          AND p_sem.visible = true
        ORDER BY p_sem.created_at
    LOOP
        -- Executar mesclagem
        SELECT * INTO merge_result
        FROM merge_duplicate_projects(
            duplicate_record.id_to_keep,
            duplicate_record.id_to_remove
        );

        -- Retornar resultado
        RETURN QUERY SELECT
            duplicate_record.clean_domain::TEXT,
            duplicate_record.id_to_keep,
            duplicate_record.id_to_remove,
            merge_result.campaigns_moved,
            merge_result.metrics_moved;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PARTE 5: COMENTÁRIOS E DOCUMENTAÇÃO
-- ============================================================================

COMMENT ON FUNCTION merge_duplicate_projects(INTEGER, INTEGER) IS
'Mescla dois projetos duplicados, movendo todas as campanhas, métricas e configurações do projeto a ser removido para o projeto a ser mantido';

COMMENT ON FUNCTION merge_all_www_duplicates() IS
'Identifica e mescla automaticamente todos os projetos duplicados que diferem apenas pelo prefixo www.';

-- ============================================================================
-- PARTE 6: EXEMPLOS DE USO
-- ============================================================================

-- Listar duplicados antes de mesclar
/*
SELECT
    p_sem.domain as domain_limpo,
    p_sem.id as id_manter,
    p_www.id as id_remover,
    p_sem.created_at as criado_sem_www,
    p_www.created_at as criado_com_www
FROM projects p_www
JOIN projects p_sem ON REPLACE(LOWER(p_www.domain), 'www.', '') = LOWER(p_sem.domain)
WHERE LOWER(p_www.domain) LIKE 'www.%'
  AND LOWER(p_sem.domain) NOT LIKE 'www.%'
  AND p_www.visible = true
  AND p_sem.visible = true;

-- Mesclar um projeto específico
SELECT * FROM merge_duplicate_projects(35, 52);

-- Mesclar todos os duplicados automaticamente
SELECT * FROM merge_all_www_duplicates();

-- Verificar projetos mesclados (agora invisíveis)
SELECT
    id,
    project_name,
    domain,
    status,
    visible
FROM projects
WHERE project_name LIKE '%[MERGED%'
ORDER BY updated_at DESC;
*/
