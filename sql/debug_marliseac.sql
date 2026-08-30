-- ========================================
-- DEBUG: Verificar usuário marliseac@gmail.com
-- ========================================

-- 1. Verificar se existe na tabela users
SELECT
  id,
  email,
  name,
  role,
  needs_password_change,
  first_login,
  created_at
FROM users
WHERE email = 'marliseac@gmail.com';

-- 2. Verificar se existe no auth.users
SELECT
  id,
  email,
  email_confirmed_at,
  created_at,
  updated_at,
  last_sign_in_at,
  confirmed_at,
  banned_until,
  deleted_at
FROM auth.users
WHERE email = 'marliseac@gmail.com';

-- 3. Comparar IDs (devem ser iguais)
SELECT
  u.id as users_id,
  au.id as auth_id,
  u.email,
  u.name,
  u.role,
  CASE WHEN u.id = au.id THEN '✓ IDs coincidem' ELSE '✗ IDs diferentes!' END as id_check
FROM users u
LEFT JOIN auth.users au ON au.email = u.email
WHERE u.email = 'marliseac@gmail.com';

-- ========================================
-- CASO O USUÁRIO NÃO EXISTA NO AUTH.USERS
-- ========================================
-- Se a query 2 não retornar nada, você precisa RECRIAR o usuário
-- Execute o script abaixo:

/*
-- A. Deletar o usuário da tabela users
DELETE FROM user_campaigns WHERE user_id = (SELECT id FROM users WHERE email = 'marliseac@gmail.com');
DELETE FROM user_projects WHERE user_id = (SELECT id FROM users WHERE email = 'marliseac@gmail.com');
DELETE FROM users WHERE email = 'marliseac@gmail.com';

-- B. Agora recrie o usuário pelo painel de Users Settings da aplicação
-- Ou use a função do Supabase para criar o usuário:

-- C. Criar usuário no auth (substitua os valores)
-- NOTA: Isso requer função admin ou use o Dashboard do Supabase
*/
