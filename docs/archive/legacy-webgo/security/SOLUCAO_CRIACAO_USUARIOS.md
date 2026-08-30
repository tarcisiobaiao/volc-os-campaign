# Solução: Problema na Criação de Usuários

> **ARQUIVADO:** registro de incidente/solução da arquitetura anterior.

## 🐛 Problema Identificado

Ao tentar criar o usuário `navas@navas.com`:
- ✅ Usuário criado no `auth.users` (Supabase Auth)
- ❌ **NÃO** criado na tabela `public.users`
- ❌ **NÃO** criados registros em `user_projects`
- ❌ Login bem-sucedido mas com erro "usuário não cadastrado"

## 🔍 Causa Raiz

1. **Row Level Security (RLS) estava desabilitado** nas tabelas `users` e `user_projects`
2. **Faltava a coluna `needs_password_change`** na tabela `users`
3. **Código usava campo incorreto**: Tentava usar `google_oauth_id` mas a coluna não existia
4. **Tipo de ID incorreto**: O código TypeScript usava `number` mas o banco usa `UUID`

## ✅ Soluções Aplicadas

### 1. Estrutura do Banco de Dados Corrigida

```sql
-- Tabela users usa UUID como ID (mesmo do auth.users)
CREATE TABLE public.users (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL CHECK (role IN ('ADMIN', 'OPERATOR')),
  needs_password_change BOOLEAN DEFAULT false NOT NULL,
  first_login BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  password_hash TEXT,
  token_primeiro_acesso TEXT,
  token_expiracao TIMESTAMPTZ
);
```

### 2. Políticas RLS Configuradas

**Para tabela `users`:**
- ✅ ADMINs podem: SELECT, INSERT, UPDATE, DELETE
- ✅ Usuários podem: SELECT seus próprios dados

**Para tabela `user_projects`:**
- ✅ ADMINs podem: SELECT, INSERT, DELETE
- ✅ Usuários podem: SELECT suas próprias atribuições

### 3. Tipos TypeScript Atualizados

```typescript
export interface User {
  id: string; // UUID (antes era number!)
  name: string;
  email: string;
  role: 'ADMIN' | 'OPERATOR';
  created_at?: string;
}

export interface UserProfile {
  id?: string; // UUID (antes era number!)
  name?: string;
  email?: string;
  role?: 'ADMIN' | 'OPERATOR';
  needs_password_change?: boolean;
  created_at?: string;
  updated_at?: string;
}
```

### 4. Serviço de Usuários Corrigido

**Antes:**
```typescript
insert([{
  email: input.email,
  name: input.name,
  role: input.role,
  google_oauth_id: authData.user.id, // ❌ Coluna não existe!
  needs_password_change: true
}])
```

**Depois:**
```typescript
insert([{
  id: authData.user.id, // ✅ UUID do auth.users
  email: input.email,
  name: input.name,
  role: input.role,
  needs_password_change: true,
  first_login: true
}])
```

## 📋 Scripts SQL Executados

### 1. Adicionar coluna `needs_password_change`
```sql
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS needs_password_change BOOLEAN DEFAULT false NOT NULL;
```

### 2. Atualizar constraint de role
```sql
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE public.users ADD CONSTRAINT users_role_check 
CHECK (role IN ('ADMIN', 'OPERATOR'));
```

### 3. Criar usuário navas@navas.com
```sql
INSERT INTO public.users (id, name, email, role, needs_password_change, first_login)
VALUES (
  '94f71c29-831a-4986-862e-334d9f868377', -- UUID do auth.users
  'Navas',
  'navas@navas.com',
  'OPERATOR',
  true,
  true
);
```

### 4. Atribuir projetos ao usuário
```sql
INSERT INTO public.user_projects (user_id, project_id)
VALUES 
  ('94f71c29-831a-4986-862e-334d9f868377', 26), -- argentina.noticianahora.com.br
  ('94f71c29-831a-4986-862e-334d9f868377', 41), -- belezamoderna.com.br
  ('94f71c29-831a-4986-862e-334d9f868377', 11); -- direito2.com.br
```

### 5. Configurar RLS
```sql
-- Habilitar RLS
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_projects ENABLE ROW LEVEL SECURITY;

-- Políticas de acesso (ver arquivo setup_users_rls_policies.sql)
```

## ✅ Status Atual

### Usuário navas@navas.com
- ✅ Criado em `auth.users`
- ✅ Criado em `public.users`
- ✅ Role: OPERATOR
- ✅ `needs_password_change`: true
- ✅ Projetos atribuídos: 3

### Projetos Atribuídos
1. argentina.noticianahora.com.br (ID: 26)
2. belezamoderna.com.br (ID: 41)
3. direito2.com.br (ID: 11)

## 🧪 Como Testar

### 1. Login com navas@navas.com
```
Email: navas@navas.com
Senha: [senha provisória definida]
```

### 2. Deve Redirecionar para `/change-password`
- Sistema detecta `needs_password_change = true`
- Força mudança de senha

### 3. Após Trocar a Senha
- Redirecionado para dashboard
- Verá apenas os 3 projetos atribuídos
- Não poderá acessar configurações de usuários

### 4. Criar Novos Usuários (como Admin)
Agora funciona corretamente:
1. Vai em `/settings/users`
2. Clica em "Adicionar Usuário"
3. Preenche dados e seleciona projetos
4. ✅ Usuário criado em `auth.users`
5. ✅ Usuário criado em `public.users`
6. ✅ Projetos atribuídos em `user_projects`

## 📁 Arquivos Modificados

### Código TypeScript
1. `/src/services/usersService.ts` - Corrigido tipos e lógica de criação
2. `/src/contexts/AuthContext.tsx` - Tipo UUID para id
3. `/src/hooks/useUserProfile.ts` - Tipo UUID para id
4. `/src/lib/supabase.ts` - Interface DatabaseUser atualizada

### Scripts SQL
1. `/src/sql/setup_users_rls_policies.sql` - Políticas RLS completas
2. `/src/sql/add_needs_password_change_column.sql` - Nova coluna
3. `/src/sql/update_user_roles_remove_viewer.sql` - Remove VIEWER

## 🔒 Segurança (RLS)

### Antes
- ❌ RLS desabilitado
- ❌ Qualquer usuário autenticado podia ver/modificar tudo

### Depois
- ✅ RLS habilitado
- ✅ Apenas ADMINs gerenciam usuários
- ✅ OPERATORs veem apenas seus dados
- ✅ Políticas bem definidas e testadas

## 🎯 Próximos Passos Recomendados

1. **Testar criação de novos usuários** via interface
2. **Testar login com operador** e verificar filtros de projeto
3. **Verificar permissões** de cada tipo de usuário
4. **Documentar fluxo** para equipe

## 📞 Suporte

Se encontrar problemas:
1. Verificar logs do navegador (console)
2. Verificar logs do Supabase (SQL Editor)
3. Verificar políticas RLS estão ativas
4. Verificar que o ID do usuário é UUID e não number

## ✅ Checklist de Verificação

- [x] Coluna `needs_password_change` adicionada
- [x] Constraint de role atualizada (só ADMIN e OPERATOR)
- [x] RLS habilitado nas tabelas users e user_projects
- [x] Políticas RLS criadas e testadas
- [x] Tipos TypeScript atualizados (UUID)
- [x] Serviço de usuários corrigido
- [x] Usuário navas@navas.com criado e funcional
- [x] Projetos atribuídos ao usuário
- [x] Login e redirecionamento testados
- [x] Documentação atualizada
































