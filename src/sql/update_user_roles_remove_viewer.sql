-- ==============================================================
-- Script: Atualização de Roles de Usuário - Remover VIEWER
-- Data: 2025-10-16
-- Descrição: Remove o role 'VIEWER' mantendo apenas 'ADMIN' e 'OPERATOR'
-- ==============================================================

-- 1. Verificar usuários com role VIEWER antes da mudança
SELECT id, name, email, role 
FROM users 
WHERE role = 'VIEWER';

-- 2. Atualizar todos os usuários VIEWER para OPERATOR
-- (Caso existam usuários VIEWER, eles serão convertidos para OPERATOR)
UPDATE users 
SET role = 'OPERATOR' 
WHERE role = 'VIEWER';

-- 3. Verificar se existe constraint de role e removê-la se existir
DO $$ 
BEGIN
    -- Remove constraint antiga se existir
    IF EXISTS (
        SELECT 1 
        FROM information_schema.constraint_column_usage 
        WHERE constraint_name = 'users_role_check'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
    END IF;
END $$;

-- 4. Adicionar nova constraint para aceitar apenas ADMIN e OPERATOR
ALTER TABLE users 
ADD CONSTRAINT users_role_check 
CHECK (role IN ('ADMIN', 'OPERATOR'));

-- 5. Verificar se existe ENUM type e ajustá-lo
DO $$ 
BEGIN
    -- Se existe um ENUM user_role_enum, precisamos recriá-lo
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role_enum') THEN
        -- Não é possível alterar ENUMs facilmente no PostgreSQL
        -- Então vamos garantir que a coluna use VARCHAR com constraint
        RAISE NOTICE 'ENUM user_role_enum existe. Certifique-se de que a constraint está correta.';
    END IF;
END $$;

-- 6. Verificação final - listar todos os roles únicos
SELECT DISTINCT role, COUNT(*) as total
FROM users 
GROUP BY role
ORDER BY role;

-- 7. Comentário informativo
COMMENT ON COLUMN users.role IS 'Role do usuário: ADMIN (acesso total) ou OPERATOR (acesso limitado aos projetos atribuídos)';

-- ==============================================================
-- NOTAS:
-- - Usuários VIEWER foram convertidos para OPERATOR
-- - Apenas ADMIN e OPERATOR são roles válidos agora
-- - ADMIN: Acesso total ao sistema
-- - OPERATOR: Acesso limitado aos projetos atribuídos
-- ==============================================================


