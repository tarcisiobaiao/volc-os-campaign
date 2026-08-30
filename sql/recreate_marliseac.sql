-- ========================================
-- RECRIAR USUÁRIO: marliseac@gmail.com
-- ========================================
-- ATENÇÃO: Execute este script APENAS se o debug confirmar que
-- o usuário não existe no auth.users OU os IDs estão diferentes

-- ========================================
-- PASSO 1: Limpar usuário antigo
-- ========================================

-- Salvar os dados do usuário antes de deletar (para referência)
-- Copie o resultado desta query antes de continuar:
SELECT
  id,
  email,
  name,
  role,
  created_at
FROM users
WHERE email = 'marliseac@gmail.com';

-- Deletar relacionamentos e usuário da tabela users
DELETE FROM user_campaigns WHERE user_id = (SELECT id FROM users WHERE email = 'marliseac@gmail.com');
DELETE FROM user_projects WHERE user_id = (SELECT id FROM users WHERE email = 'marliseac@gmail.com');
DELETE FROM users WHERE email = 'marliseac@gmail.com';

-- Tentar deletar do auth.users (se existir)
-- NOTA: Esta query pode falhar se não tiver permissão, tudo bem
DELETE FROM auth.users WHERE email = 'marliseac@gmail.com';

-- ========================================
-- PASSO 2: Recriar via Dashboard
-- ========================================
-- Agora você DEVE recriar o usuário usando a interface da aplicação:
--
-- 1. Acesse: http://localhost:8081/settings/users (ou sua URL de produção)
-- 2. Clique em "Adicionar Usuário"
-- 3. Preencha:
--    - Nome: Marlise AC (ou o nome correto)
--    - Email: marliseac@gmail.com
--    - Senha Provisória: 123456
--    - Nível: Operador
--    - Selecione os projetos que ela deve ter acesso
-- 4. Clique em "Criar Usuário"
--
-- Isso vai criar corretamente tanto no auth.users quanto na tabela users
-- com os IDs sincronizados e as flags corretas.

-- ========================================
-- PASSO 3: Verificar
-- ========================================
-- Após recriar, execute esta query para confirmar:
SELECT
  u.id as users_id,
  au.id as auth_id,
  u.email,
  u.name,
  u.role,
  u.needs_password_change,
  u.first_login,
  au.email_confirmed_at,
  CASE WHEN u.id = au.id THEN '✓ IDs coincidem' ELSE '✗ IDs diferentes!' END as id_check
FROM users u
INNER JOIN auth.users au ON au.id = u.id
WHERE u.email = 'marliseac@gmail.com';

-- Resultado esperado:
-- - needs_password_change: true
-- - first_login: true
-- - email_confirmed_at: [alguma data]
-- - id_check: ✓ IDs coincidem
