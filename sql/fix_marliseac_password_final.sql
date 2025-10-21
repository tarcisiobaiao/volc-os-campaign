-- ========================================
-- RESET DEFINITIVO DE SENHA
-- marliseac@gmail.com
-- ID: 0c4821f3-cadb-46de-ab8b-1f4ef416a0a2
-- ========================================

-- PASSO 1: Confirmar que o usuário existe
SELECT
  'Usuário encontrado!' as status,
  u.id,
  u.email,
  u.name,
  u.role,
  u.needs_password_change,
  u.first_login
FROM users u
WHERE u.id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';

-- PASSO 2: Verificar auth.users
SELECT
  'Auth encontrado!' as status,
  id,
  email,
  email_confirmed_at,
  confirmed_at,
  banned_until,
  deleted_at
FROM auth.users
WHERE id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';

-- ========================================
-- PASSO 3: RESETAR SENHA PARA 123456
-- ========================================
-- IMPORTANTE: Execute esta query no SQL Editor do Supabase
-- NOTA: confirmed_at é uma coluna gerada, não pode ser atualizada diretamente

UPDATE auth.users
SET
  encrypted_password = crypt('123456', gen_salt('bf')),
  email_confirmed_at = COALESCE(email_confirmed_at, now()),
  updated_at = now()
WHERE id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';

-- ========================================
-- PASSO 4: GARANTIR FLAGS NA TABELA USERS
-- ========================================
UPDATE users
SET
  needs_password_change = true,
  first_login = true
WHERE id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';

-- ========================================
-- PASSO 5: VERIFICAÇÃO FINAL
-- ========================================
SELECT
  'Verificação Final' as etapa,
  u.id,
  u.email,
  u.name,
  u.role,
  u.needs_password_change as needs_pwd_change,
  u.first_login,
  au.email_confirmed_at as email_confirmed,
  au.confirmed_at as confirmed,
  CASE
    WHEN au.email_confirmed_at IS NOT NULL THEN '✓ Email confirmado'
    ELSE '✗ Email NÃO confirmado'
  END as email_status,
  CASE
    WHEN u.needs_password_change = true THEN '✓ Vai pedir troca de senha'
    ELSE '✗ NÃO vai pedir troca'
  END as password_change_status
FROM users u
INNER JOIN auth.users au ON au.id = u.id
WHERE u.id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';

-- ========================================
-- RESULTADO ESPERADO:
-- ========================================
-- ✓ needs_password_change: true
-- ✓ first_login: true
-- ✓ email_confirmed_at: [data preenchida]
-- ✓ confirmed_at: [data preenchida]
--
-- Após executar:
-- Login: marliseac@gmail.com
-- Senha: 123456
-- Será redirecionada para /change-password
