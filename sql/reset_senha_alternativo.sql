-- ========================================
-- MÉTODO ALTERNATIVO: Reset via Supabase Admin API
-- ========================================
-- Se o método SQL não está funcionando, use a Admin API do Supabase

-- OPÇÃO 1: Via Dashboard do Supabase (RECOMENDADO)
-- ========================================
-- 1. Vá para: https://supabase.com/dashboard/project/[seu-project-id]/auth/users
-- 2. Procure por: marliseac@gmail.com
-- 3. Clique nos 3 pontinhos (...) ao lado do usuário
-- 4. Selecione "Reset password"
-- 5. Digite a nova senha: 123456
-- 6. Confirme

-- OPÇÃO 2: Deletar e Recriar do Zero
-- ========================================
-- Se nada funcionar, vamos recomeçar do zero

-- A. Salvar dados atuais (copie este resultado!)
SELECT
  u.id,
  u.email,
  u.name,
  u.role,
  array_agg(DISTINCT up.project_id) as project_ids,
  array_agg(DISTINCT uc.campaign_id) as campaign_ids
FROM users u
LEFT JOIN user_projects up ON up.user_id = u.id
LEFT JOIN user_campaigns uc ON uc.user_id = u.id
WHERE u.email = 'marliseac@gmail.com'
GROUP BY u.id, u.email, u.name, u.role;

-- B. Deletar completamente (CUIDADO!)
-- Descomente as linhas abaixo apenas se for realmente deletar:

/*
DELETE FROM user_campaigns WHERE user_id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';
DELETE FROM user_projects WHERE user_id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';
DELETE FROM users WHERE id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';
*/

-- C. Depois recrie no Dashboard da aplicação em /settings/users

-- OPÇÃO 3: Tentar outro algoritmo de criptografia
-- ========================================
-- Às vezes o Supabase usa md5 ou outro método

-- Testar com md5:
UPDATE auth.users
SET
  encrypted_password = '$2a$10$' || encode(digest('123456' || id::text, 'sha256'), 'base64'),
  email_confirmed_at = COALESCE(email_confirmed_at, now()),
  updated_at = now()
WHERE id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';

-- OPÇÃO 4: Forçar confirmação de email
-- ========================================
UPDATE auth.users
SET
  email_confirmed_at = now(),
  updated_at = now()
WHERE id = '0c4821f3-cadb-46de-ab8b-1f4ef416a0a2';
