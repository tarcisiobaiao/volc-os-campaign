-- ========================================
-- DIAGNÓSTICO COMPLETO
-- marliseac@gmail.com
-- ========================================

-- 1. Verificar dados completos do auth.users
SELECT
  'AUTH.USERS' as tabela,
  id,
  email,
  encrypted_password IS NOT NULL as tem_senha,
  email_confirmed_at,
  confirmed_at,
  confirmation_sent_at,
  recovery_sent_at,
  email_change_sent_at,
  last_sign_in_at,
  raw_app_meta_data,
  raw_user_meta_data,
  is_super_admin,
  created_at,
  updated_at,
  phone,
  phone_confirmed_at,
  banned_until,
  deleted_at,
  is_sso_user
FROM auth.users
WHERE email = 'marliseac@gmail.com';

-- 2. Verificar dados da tabela users
SELECT
  'USERS' as tabela,
  id,
  email,
  name,
  role,
  needs_password_change,
  first_login,
  created_at,
  updated_at
FROM users
WHERE email = 'marliseac@gmail.com';

-- 3. Verificar se há algum problema com a extensão pgcrypto
SELECT
  'Testando pgcrypto' as teste,
  crypt('123456', gen_salt('bf')) as senha_encriptada;

-- 4. Verificar se o email está em minúsculas (importante!)
SELECT
  'Verificação de case' as teste,
  email,
  LOWER(email) as email_lower,
  CASE
    WHEN email = LOWER(email) THEN '✓ Email em minúsculas'
    ELSE '✗ Email tem maiúsculas!'
  END as status
FROM auth.users
WHERE email ILIKE 'marliseac@gmail.com';

-- 5. Verificar projetos e campanhas
SELECT
  'USER_PROJECTS' as tabela,
  COUNT(*) as total_projetos
FROM user_projects
WHERE user_id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';

SELECT
  'USER_CAMPAIGNS' as tabela,
  COUNT(*) as total_campanhas
FROM user_campaigns
WHERE user_id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';
