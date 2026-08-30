-- ==============================================================
-- Script: Configurar RLS (Row Level Security) para tabelas users e user_projects
-- Data: 2025-10-16
-- Descrição: Permite que ADMINs gerenciem usuários e atribuam projetos
-- ==============================================================

-- 1. Habilitar RLS nas tabelas (se ainda não estiver)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_projects ENABLE ROW LEVEL SECURITY;

-- 2. Remover políticas antigas se existirem
DROP POLICY IF EXISTS "Admin can manage all users" ON users;
DROP POLICY IF EXISTS "Users can read their own data" ON users;
DROP POLICY IF EXISTS "Admin can manage user projects" ON user_projects;
DROP POLICY IF EXISTS "Users can read their own projects" ON user_projects;
DROP POLICY IF EXISTS "Service role full access users" ON users;
DROP POLICY IF EXISTS "Service role full access user_projects" ON user_projects;

-- ==============================================================
-- POLÍTICAS PARA TABELA USERS
-- ==============================================================

-- Permitir que ADMINs façam SELECT em todos os usuários
CREATE POLICY "Admin can select all users"
ON users FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.google_oauth_id = auth.uid()
    AND users.role = 'ADMIN'
  )
);

-- Permitir que ADMINs façam INSERT de novos usuários
CREATE POLICY "Admin can insert users"
ON users FOR INSERT
TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.google_oauth_id = auth.uid()
    AND users.role = 'ADMIN'
  )
);

-- Permitir que ADMINs façam UPDATE em todos os usuários
CREATE POLICY "Admin can update all users"
ON users FOR UPDATE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.google_oauth_id = auth.uid()
    AND users.role = 'ADMIN'
  )
)
WITH CHECK (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.google_oauth_id = auth.uid()
    AND users.role = 'ADMIN'
  )
);

-- Permitir que ADMINs façam DELETE de usuários
CREATE POLICY "Admin can delete users"
ON users FOR DELETE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.google_oauth_id = auth.uid()
    AND users.role = 'ADMIN'
  )
);

-- Permitir que usuários leiam seus próprios dados
CREATE POLICY "Users can read own data"
ON users FOR SELECT
TO authenticated
USING (google_oauth_id = auth.uid());

-- ==============================================================
-- POLÍTICAS PARA TABELA USER_PROJECTS
-- ==============================================================

-- Permitir que ADMINs façam SELECT em todas as atribuições
CREATE POLICY "Admin can select all user_projects"
ON user_projects FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.google_oauth_id = auth.uid()
    AND users.role = 'ADMIN'
  )
);

-- Permitir que ADMINs façam INSERT de atribuições
CREATE POLICY "Admin can insert user_projects"
ON user_projects FOR INSERT
TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.google_oauth_id = auth.uid()
    AND users.role = 'ADMIN'
  )
);

-- Permitir que ADMINs façam DELETE de atribuições
CREATE POLICY "Admin can delete user_projects"
ON user_projects FOR DELETE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.google_oauth_id = auth.uid()
    AND users.role = 'ADMIN'
  )
);

-- Permitir que usuários leiam suas próprias atribuições
CREATE POLICY "Users can read own projects"
ON user_projects FOR SELECT
TO authenticated
USING (
  user_id IN (
    SELECT id FROM users WHERE google_oauth_id = auth.uid()
  )
);

-- ==============================================================
-- VERIFICAÇÕES
-- ==============================================================

-- Verificar políticas criadas para users
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual
FROM pg_policies
WHERE tablename = 'users'
ORDER BY policyname;

-- Verificar políticas criadas para user_projects
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual
FROM pg_policies
WHERE tablename = 'user_projects'
ORDER BY policyname;

-- ==============================================================
-- NOTAS IMPORTANTES
-- ==============================================================
-- 1. Apenas usuários com role='ADMIN' podem gerenciar outros usuários
-- 2. Todos os usuários podem ler seus próprios dados
-- 3. OPERATORs só veem suas próprias atribuições de projeto
-- 4. ADMINs têm controle total sobre users e user_projects
-- ==============================================================

































