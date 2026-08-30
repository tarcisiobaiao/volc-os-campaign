-- Script para corrigir o problema do projeto eleicoes.org
-- ARQUIVADO: correção de incidente específico; contém CREATE OR REPLACE e exige revisão antes de reutilizar.
-- Execute este script no Supabase para corrigir a função de correlação

-- 1. PRIMEIRA VERIFICAÇÃO: Executar o debug para identificar o problema
-- Execute o diagnóstico arquivado na mesma pasta primeiro.

-- 2. CRIAR função melhorada para buscar project_id pela URL
CREATE OR REPLACE FUNCTION get_project_id_by_url_improved(url_input TEXT)
RETURNS INTEGER AS $$
DECLARE
    project_id_result INTEGER;
    cleaned_url TEXT;
BEGIN
    -- Limpar a URL de entrada (remover protocolo, www, etc.)
    cleaned_url := LOWER(TRIM(url_input));
    cleaned_url := REPLACE(cleaned_url, 'https://', '');
    cleaned_url := REPLACE(cleaned_url, 'http://', '');
    cleaned_url := REPLACE(cleaned_url, 'www.', '');

    -- Tentar busca exata primeiro (prioridade)
    SELECT id INTO project_id_result
    FROM projects
    WHERE LOWER(domain) = cleaned_url
       OR LOWER(main_url) = cleaned_url
       OR LOWER(REPLACE(REPLACE(REPLACE(domain, 'https://', ''), 'http://', ''), 'www.', '')) = cleaned_url
       OR LOWER(REPLACE(REPLACE(REPLACE(main_url, 'https://', ''), 'http://', ''), 'www.', '')) = cleaned_url
    LIMIT 1;

    -- Se não encontrar busca exata, tentar busca com LIKE (mas mais restritiva)
    IF project_id_result IS NULL THEN
        SELECT id INTO project_id_result
        FROM projects
        WHERE LOWER(domain) LIKE '%' || cleaned_url || '%'
           OR LOWER(main_url) LIKE '%' || cleaned_url || '%'
        ORDER BY
            -- Priorizar matches mais exatos
            CASE
                WHEN LOWER(domain) = cleaned_url OR LOWER(main_url) = cleaned_url THEN 1
                WHEN LOWER(domain) LIKE cleaned_url || '%' OR LOWER(main_url) LIKE cleaned_url || '%' THEN 2
                ELSE 3
            END
        LIMIT 1;
    END IF;

    RETURN project_id_result;
END;
$$ LANGUAGE plpgsql;

-- 3. ATUALIZAR função original para usar a versão melhorada
CREATE OR REPLACE FUNCTION get_project_id_by_url(url_input TEXT)
RETURNS INTEGER AS $$
BEGIN
    RETURN get_project_id_by_url_improved(url_input);
END;
$$ LANGUAGE plpgsql;

-- 4. TESTAR a nova função com eleicoes.org
SELECT
    'eleicoes.org' as input_url,
    get_project_id_by_url('eleicoes.org') as new_function_result,
    get_project_id_by_url_improved('eleicoes.org') as improved_function_result;

-- 5. VERIFICAR se há conflitos para eleicoes.org
SELECT
    id,
    domain,
    main_url,
    project_name,
    CASE
        WHEN LOWER(domain) LIKE '%eleicoes%' OR LOWER(main_url) LIKE '%eleicoes%' THEN 'MATCH ENCONTRADO'
        ELSE 'NO MATCH'
    END as match_status
FROM projects
WHERE LOWER(domain) LIKE '%eleicoes%'
   OR LOWER(main_url) LIKE '%eleicoes%'
   OR LOWER(project_name) LIKE '%eleicoes%'
ORDER BY id;

-- 6. LIMPAR registros duplicados se existirem
-- ATENÇÃO: Execute apenas se necessário após verificar os dados

-- DELETE FROM daily_project_metrics
-- WHERE id IN (
--     SELECT id
--     FROM (
--         SELECT id,
--                ROW_NUMBER() OVER (PARTITION BY project_id, date ORDER BY updated_at DESC) as rn
--         FROM daily_project_metrics
--         WHERE project_id = 32 AND date = '2025-09-22'
--     ) t
--     WHERE t.rn > 1
-- );

-- 7. TESTAR inserção com a função corrigida
-- Primeiro vamos testar qual project_id a função retorna
SELECT
    'Teste de inserção para eleicoes.org' as teste,
    get_project_id_by_url('eleicoes.org') as project_id_que_sera_usado;

-- 8. INSERÇÃO SEGURA com UPSERT
INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES ('eleicoes.org', '2025-09-22', 5.81)
ON CONFLICT (project_id, date)
DO UPDATE SET
    revenue_converted = EXCLUDED.revenue_converted,
    updated_at = NOW()
RETURNING
    id,
    project_id,
    url_projeto,
    date,
    revenue_converted,
    revenue_converted_revshare,
    updated_at;

-- 9. VERIFICAÇÃO FINAL
SELECT
    'Verificação final' as status,
    COUNT(*) as total_registros_eleicoes
FROM daily_project_metrics
WHERE url_projeto = 'eleicoes.org';

-- 10. MOSTRAR todos os registros de eleicoes.org
SELECT
    id,
    project_id,
    url_projeto,
    date,
    revenue_converted,
    revenue_converted_revshare,
    updated_at
FROM daily_project_metrics
WHERE url_projeto = 'eleicoes.org'
ORDER BY date DESC;
