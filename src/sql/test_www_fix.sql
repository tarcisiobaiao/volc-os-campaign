-- Testes para validar a correção do bug de duplicação de projetos com www

-- ============================================================================
-- TESTE 1: Verificar que a limpeza de domínio funciona corretamente
-- ============================================================================

SELECT '========== TESTE 1: Limpeza de domínios ==========' as test_name;

-- Testar função de limpeza de URL do trigger
SELECT
    'https://www.educacaonamao.com.br/r/pronatec-2026-como-funciona-inscricao/' as url_original,
    LOWER(TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE('https://www.educacaonamao.com.br/r/pronatec-2026-como-funciona-inscricao/', '^https?://', '', 'i'),
            '^www\.', '', 'i'
        ),
        '/.*$', ''
    ))) as url_limpa,
    'educacaonamao.com.br' as esperado,
    CASE
        WHEN LOWER(TRIM(REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE('https://www.educacaonamao.com.br/r/pronatec-2026-como-funciona-inscricao/', '^https?://', '', 'i'),
                '^www\.', '', 'i'
            ),
            '/.*$', ''
        ))) = 'educacaonamao.com.br' THEN '✅ PASSOU'
        ELSE '❌ FALHOU'
    END as resultado;

-- ============================================================================
-- TESTE 2: Verificar busca de projetos com diferentes formatos de URL
-- ============================================================================

SELECT '========== TESTE 2: Busca de projetos ==========' as test_name;

-- Simular busca com diferentes formatos
DO $$
DECLARE
    cleaned_url TEXT;
    project_found INTEGER;
BEGIN
    -- Teste com www
    cleaned_url := LOWER(TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE('https://www.educacaonamao.com.br/r/test/', '^https?://', '', 'i'),
            '^www\.', '', 'i'
        ),
        '/.*$', ''
    )));

    SELECT id INTO project_found
    FROM projects
    WHERE LOWER(domain) = cleaned_url
       OR LOWER(main_url) = cleaned_url
    LIMIT 1;

    RAISE NOTICE 'URL com www: cleaned_url=[%], project_found=[%]', cleaned_url, project_found;

    -- Teste sem www
    cleaned_url := LOWER(TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE('educacaonamao.com.br/r/test/', '^https?://', '', 'i'),
            '^www\.', '', 'i'
        ),
        '/.*$', ''
    )));

    SELECT id INTO project_found
    FROM projects
    WHERE LOWER(domain) = cleaned_url
       OR LOWER(main_url) = cleaned_url
    LIMIT 1;

    RAISE NOTICE 'URL sem www: cleaned_url=[%], project_found=[%]', cleaned_url, project_found;
END $$;

-- ============================================================================
-- TESTE 3: Verificar projetos duplicados existentes
-- ============================================================================

SELECT '========== TESTE 3: Projetos duplicados ==========' as test_name;

SELECT
    p_www.id as id_com_www,
    p_www.domain as domain_com_www,
    p_www.created_at as criado_www,
    p_sem.id as id_sem_www,
    p_sem.domain as domain_sem_www,
    p_sem.created_at as criado_sem_www,
    (SELECT COUNT(*) FROM campaigns WHERE project_id = p_www.id) as campanhas_www,
    (SELECT COUNT(*) FROM campaigns WHERE project_id = p_sem.id) as campanhas_sem_www,
    CASE
        WHEN p_sem.created_at < p_www.created_at THEN '⚠️  Manter ' || p_sem.id || ', remover ' || p_www.id
        ELSE '⚠️  Manter ' || p_www.id || ', remover ' || p_sem.id
    END as acao_recomendada
FROM projects p_www
JOIN projects p_sem ON REPLACE(LOWER(p_www.domain), 'www.', '') = LOWER(p_sem.domain)
WHERE LOWER(p_www.domain) LIKE 'www.%'
  AND LOWER(p_sem.domain) NOT LIKE 'www.%'
  AND p_www.visible = true
  AND p_sem.visible = true
ORDER BY p_sem.created_at;

-- ============================================================================
-- TESTE 4: Simular inserção com URL problemática (NÃO EXECUTA, APENAS MOSTRA)
-- ============================================================================

SELECT '========== TESTE 4: Simulação de inserção ==========' as test_name;

-- Mostrar o que aconteceria com a URL problemática
SELECT
    'SIMULAÇÃO - NÃO SERÁ EXECUTADO' as aviso,
    'https://www.educacaonamao.com.br/r/pronatec-2026-como-funciona-inscricao/' as url_campanha,
    LOWER(TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE('https://www.educacaonamao.com.br/r/pronatec-2026-como-funciona-inscricao/', '^https?://', '', 'i'),
            '^www\.', '', 'i'
        ),
        '/.*$', ''
    ))) as url_limpa,
    (
        SELECT id
        FROM projects
        WHERE LOWER(domain) = LOWER(TRIM(REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE('https://www.educacaonamao.com.br/r/pronatec-2026-como-funciona-inscricao/', '^https?://', '', 'i'),
                '^www\.', '', 'i'
            ),
            '/.*$', ''
        )))
        LIMIT 1
    ) as project_id_encontrado,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM projects
            WHERE LOWER(domain) = 'educacaonamao.com.br'
        ) THEN '✅ Projeto encontrado - NÃO criará duplicata'
        ELSE '❌ Projeto NÃO encontrado - CRIARIA duplicata'
    END as resultado_esperado;

-- ============================================================================
-- TESTE 5: Verificar casos edge (domínios especiais)
-- ============================================================================

SELECT '========== TESTE 5: Casos edge ==========' as test_name;

-- Testar diferentes formatos de URL
SELECT
    url_teste,
    LOWER(TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(url_teste, '^https?://', '', 'i'),
            '^www\.', '', 'i'
        ),
        '/.*$', ''
    ))) as resultado_limpeza,
    esperado,
    CASE
        WHEN LOWER(TRIM(REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE(url_teste, '^https?://', '', 'i'),
                '^www\.', '', 'i'
            ),
            '/.*$', ''
        ))) = esperado THEN '✅ PASSOU'
        ELSE '❌ FALHOU'
    END as status
FROM (
    VALUES
        ('https://www.example.com/path', 'example.com'),
        ('http://www.example.com', 'example.com'),
        ('www.example.com', 'example.com'),
        ('example.com', 'example.com'),
        ('https://example.com/path/to/page', 'example.com'),
        ('https://sub.example.com', 'sub.example.com'),
        ('https://www.sub.example.com/path', 'sub.example.com')
) AS test_cases(url_teste, esperado);

-- ============================================================================
-- TESTE 6: Resumo final
-- ============================================================================

SELECT '========== RESUMO DOS TESTES ==========' as test_name;

SELECT
    'Total de projetos:' as metrica,
    COUNT(*) as valor
FROM projects
WHERE visible = true

UNION ALL

SELECT
    'Projetos com www:' as metrica,
    COUNT(*) as valor
FROM projects
WHERE domain LIKE 'www.%' AND visible = true

UNION ALL

SELECT
    'Projetos duplicados (www vs sem www):' as metrica,
    COUNT(*) as valor
FROM (
    SELECT DISTINCT p_www.id
    FROM projects p_www
    JOIN projects p_sem ON REPLACE(LOWER(p_www.domain), 'www.', '') = LOWER(p_sem.domain)
    WHERE LOWER(p_www.domain) LIKE 'www.%'
      AND LOWER(p_sem.domain) NOT LIKE 'www.%'
      AND p_www.visible = true
      AND p_sem.visible = true
) duplicates

UNION ALL

SELECT
    'Campanhas em projetos com www:' as metrica,
    COUNT(*) as valor
FROM campaigns c
JOIN projects p ON c.project_id = p.id
WHERE p.domain LIKE 'www.%' AND p.visible = true;

-- ============================================================================
-- INSTRUÇÕES FINAIS
-- ============================================================================

SELECT '
========== PRÓXIMOS PASSOS ==========

1. ✅ ANÁLISE: Revisar os resultados dos testes acima
2. ⚠️  BACKUP: Fazer backup antes de executar a mesclagem
3. 🔧 CORRIGIR: Se houver duplicatas, executar:

   -- Para mesclar educacaonamao.com.br especificamente:
   SELECT * FROM merge_duplicate_projects(35, 52);

   -- OU para mesclar TODOS os duplicados automaticamente:
   SELECT * FROM merge_all_www_duplicates();

4. ✅ VALIDAR: Executar este script novamente para confirmar correção
5. 🚀 DEPLOY: Fazer deploy do código corrigido em supabaseDataService.ts

========================================
' as instrucoes;
