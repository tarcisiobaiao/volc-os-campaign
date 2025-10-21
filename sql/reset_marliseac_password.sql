-- ========================================
-- RESET DE SENHA: marliseac@gmail.com
-- ========================================
-- Este script reseta a senha para '123456' e força troca no primeiro login
-- Execute TODAS as queries abaixo na ordem

-- ========================================
-- 1. ATUALIZAR TABELA USERS
-- ========================================
-- Marca que o usuário precisa trocar a senha no primeiro login
UPDATE users
SET
  needs_password_change = true,
  first_login = true
WHERE email = 'marliseac@gmail.com';

-- ========================================
-- 2. RESETAR SENHA NO AUTH
-- ========================================
-- IMPORTANTE: Esta query precisa ser executada no SQL Editor do Supabase
-- com permissões adequadas para modificar auth.users

-- Opção 1: Usando extensão pgcrypto (mais comum)
UPDATE auth.users
SET
  encrypted_password = crypt('123456', gen_salt('bf')),
  -- Remove confirmação de email se necessário
  email_confirmed_at = COALESCE(email_confirmed_at, now()),
  -- Atualiza timestamp
  updated_at = now()
WHERE email = 'marliseac@gmail.com';

-- ========================================
-- 3. VERIFICAR SE FUNCIONOU
-- ========================================
-- Verifica se o usuário existe e está configurado corretamente
SELECT
  u.id,
  u.email,
  u.name,
  u.role,
  u.needs_password_change,
  u.first_login,
  au.email_confirmed_at,
  au.last_sign_in_at
FROM users u
LEFT JOIN auth.users au ON au.id = u.id
WHERE u.email = 'marliseac@gmail.com';

-- ========================================
-- INSTRUÇÕES
-- ========================================
-- 1. Execute as queries 1, 2 e 3 no SQL Editor do Supabase
-- 2. Verifique o resultado da query 3:
--    - needs_password_change deve ser TRUE
--    - first_login deve ser TRUE
--    - email_confirmed_at não deve ser NULL
-- 3. A usuária pode fazer login com:
--    Email: marliseac@gmail.com
--    Senha: 123456
-- 4. Ela será redirecionada automaticamente para /change-password
-- 5. Nova senha deve ter:
--    - Mínimo 8 caracteres
--    - Pelo menos 1 letra maiúscula
--    - Pelo menos 1 letra minúscula
--    - Pelo menos 1 número
