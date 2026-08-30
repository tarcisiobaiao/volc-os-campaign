-- ==============================================================
-- Script: Adicionar coluna needs_password_change
-- Data: 2025-10-16
-- Descrição: Adiciona flag para forçar mudança de senha no primeiro acesso
-- ==============================================================

-- 1. Adicionar coluna needs_password_change (padrão false para usuários existentes)
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS needs_password_change BOOLEAN DEFAULT false NOT NULL;

-- 2. Comentário explicativo
COMMENT ON COLUMN users.needs_password_change IS 
'Indica se o usuário precisa alterar a senha no próximo login (senha provisória)';

-- 3. Verificar estrutura da tabela
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;

-- ==============================================================
-- NOTAS:
-- - Novos usuários criados com senha provisória terão esta flag = true
-- - Após trocar a senha, a flag será alterada para false
-- - Usuários existentes começam com false (não precisam trocar)
-- ==============================================================



