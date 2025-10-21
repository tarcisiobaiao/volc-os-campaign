# Fluxo de Primeiro Acesso e Gerenciamento de Operadores

## 📋 Visão Geral

Sistema completo de primeiro acesso com senha provisória e controle de acesso para operadores.

## 🔐 Fluxo de Autenticação

### 1. Criação de Usuário (Admin)
- Admin cria usuário em `/settings/users`
- Define senha provisória (mínimo 6 caracteres)
- Seleciona perfil: **ADMIN** ou **OPERATOR**
- Para OPERATOR: atribui projetos específicos
- Sistema marca `needs_password_change = true` automaticamente

### 2. Primeiro Login do Usuário
1. Usuário faz login com email e senha provisória
2. Sistema detecta `needs_password_change = true`
3. Redireciona automaticamente para `/change-password`
4. Usuário não pode acessar outras páginas até trocar a senha

### 3. Mudança de Senha Obrigatória
**Página:** `/change-password`

**Requisitos da nova senha:**
- Mínimo 8 caracteres
- Pelo menos uma letra maiúscula
- Pelo menos uma letra minúscula
- Pelo menos um número

**Processo:**
1. Valida senha provisória
2. Valida requisitos da nova senha
3. Atualiza senha no Supabase Auth
4. Marca `needs_password_change = false`
5. Redireciona para dashboard

## 👥 Perfis de Usuário

### ADMIN (Administrador)
- ✅ Acesso total ao sistema
- ✅ Gerencia usuários
- ✅ Gerencia projetos e campanhas
- ✅ Configura custos e integrações
- ✅ Visualiza todos os projetos

### OPERATOR (Operador)
- ✅ Acesso limitado aos projetos atribuídos
- ✅ Visualiza apenas:
  - `/dashboard/projects` - Lista de projetos atribuídos
  - `/dashboard/project/:id` - Detalhes do projeto (se atribuído)
  - `/dashboard/campaign/:id` - Detalhes da campanha (se do projeto atribuído)
  - `/settings/campaigns` - Gerenciamento de campanhas dos projetos
- ❌ Não acessa:
  - Configurações de usuários
  - Configurações de custos
  - Integrações
  - Projetos não atribuídos

## 🗄️ Estrutura do Banco de Dados

### Tabela `users`
```sql
ALTER TABLE users 
ADD COLUMN needs_password_change BOOLEAN DEFAULT false NOT NULL;

-- Constraint de role (apenas ADMIN e OPERATOR)
ALTER TABLE users 
ADD CONSTRAINT users_role_check 
CHECK (role IN ('ADMIN', 'OPERATOR'));
```

### Tabela `user_projects`
```sql
-- Relacionamento muitos-para-muitos
CREATE TABLE user_projects (
  user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
  project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, project_id)
);
```

## 📁 Arquivos Modificados/Criados

### Novos Arquivos
1. **`src/pages/ChangePassword.tsx`**
   - Página de mudança de senha no primeiro acesso
   - Validação de requisitos de senha
   - Interface responsiva e intuitiva

2. **`src/sql/add_needs_password_change_column.sql`**
   - Script para adicionar coluna `needs_password_change`

3. **`src/sql/update_user_roles_remove_viewer.sql`**
   - Remove role VIEWER
   - Mantém apenas ADMIN e OPERATOR

### Arquivos Modificados

#### Frontend
1. **`src/App.tsx`**
   - Adicionada rota `/change-password`

2. **`src/components/ProtectedRoute.tsx`**
   - Redireciona para `/change-password` se `needs_password_change = true`
   - Controla acesso de operadores às páginas permitidas
   - Bloqueia acesso a `/change-password` após senha alterada

3. **`src/components/ui/modal.tsx`**
   - Melhorado para respeitar altura da tela (max-h-90vh)
   - Scroll interno no body
   - Melhor responsividade

4. **`src/contexts/AuthContext.tsx`**
   - Adicionado `needs_password_change` ao `UserProfile`

5. **`src/pages/Login.tsx`**
   - Redirecionamento automático via ProtectedRoute

6. **`src/pages/settings/UsersSettings.tsx`**
   - Removida opção VIEWER
   - Mantidas apenas opções ADMIN e OPERATOR
   - Grid de cards ajustado (3→2 colunas)

7. **`src/pages/GeneralDashboard.tsx`**
   - Filtro de projetos para operadores
   - Carrega projetos do usuário via `user_projects`
   - Exibe apenas projetos atribuídos

8. **`src/pages/settings/ProjectsSettings.tsx`**
   - Já tinha filtro de projetos implementado ✅

#### Services
1. **`src/services/usersService.ts`**
   - Marca `needs_password_change = true` ao criar usuário
   - Tipos atualizados (removido VIEWER)

#### Tipos TypeScript
1. **`src/hooks/useUserRole.ts`**
   - Tipo atualizado: `'ADMIN' | 'OPERATOR' | null`
   - Removida função `isViewer()`

2. **`src/hooks/useUserProfile.ts`**
   - Interface atualizada sem VIEWER

3. **`src/lib/supabase.ts`**
   - `DatabaseUser` sem VIEWER

## 🚀 Como Usar

### Para Administradores

#### 1. Criar Novo Operador
```
1. Ir em /settings/users
2. Clicar em "Adicionar Usuário"
3. Preencher:
   - Nome completo
   - Email
   - Senha provisória (ex: "Temp123")
   - Nível: Operador
   - Selecionar projetos que ele terá acesso
4. Clicar em "Criar Usuário"
```

#### 2. Informar Credenciais ao Operador
```
Email: operador@exemplo.com
Senha Provisória: Temp123

⚠️ No primeiro acesso, você precisará criar uma senha segura.
```

### Para Novos Usuários (Operadores)

#### 1. Primeiro Login
```
1. Acessar http://localhost:8081/login
2. Digite email e senha provisória
3. Clique em "Entrar"
```

#### 2. Mudança de Senha
```
Você será redirecionado automaticamente para:
http://localhost:8081/change-password

1. Digite a senha provisória
2. Crie uma nova senha (requisitos):
   - Mínimo 8 caracteres
   - 1 letra maiúscula
   - 1 letra minúscula
   - 1 número
3. Confirme a nova senha
4. Clique em "Confirmar e Continuar"
```

#### 3. Acesso ao Sistema
```
Após trocar a senha, você será redirecionado para:
http://localhost:8081/dashboard/projects

Você verá apenas os projetos atribuídos a você.
```

## 📊 Scripts SQL para Executar

### 1. Adicionar Coluna `needs_password_change`
```sql
-- Executar: src/sql/add_needs_password_change_column.sql
```

### 2. Remover VIEWER e Ajustar Constraints
```sql
-- Executar: src/sql/update_user_roles_remove_viewer.sql
```

## ✅ Checklist de Implementação

- [x] Criar coluna `needs_password_change` no banco
- [x] Remover role VIEWER
- [x] Criar página de mudança de senha
- [x] Atualizar tipos TypeScript
- [x] Implementar redirecionamento automático
- [x] Adicionar validação de senha forte
- [x] Filtrar projetos por operador (GeneralDashboard)
- [x] Filtrar projetos por operador (ProjectsSettings)
- [x] Controlar acesso às rotas por perfil
- [x] Melhorar UX/UI do modal de usuários
- [x] Atualizar documentação

## 🔍 Testes Recomendados

1. **Criar novo operador**
   - Verificar flag `needs_password_change = true`
   - Verificar projetos atribuídos em `user_projects`

2. **Login com senha provisória**
   - Deve redirecionar para `/change-password`
   - Não deve permitir acesso a outras páginas

3. **Mudança de senha**
   - Validar requisitos de senha
   - Verificar flag `needs_password_change = false` após mudança
   - Redirecionar para dashboard

4. **Filtro de projetos**
   - Operador deve ver apenas projetos atribuídos
   - Admin deve ver todos os projetos

5. **Controle de acesso**
   - Operador não deve acessar `/settings/users`
   - Operador não deve acessar `/settings/costs`
   - Operador não deve acessar `/settings/integrations`

## 🐛 Solução de Problemas

### Operador não consegue fazer login
- Verificar se o usuário existe na tabela `users`
- Verificar se o email está correto
- Tentar resetar senha pelo admin

### Não redireciona para mudança de senha
- Verificar se coluna `needs_password_change` existe
- Verificar se está marcada como `true`
- Verificar console do navegador para erros

### Operador vê todos os projetos
- Verificar se há registros em `user_projects`
- Verificar se `userProjectIds` está sendo carregado
- Verificar console para erros de query

### Senha provisória não aceita
- Verificar se usuário foi criado corretamente no Supabase Auth
- Tentar criar novo usuário

## 📝 Notas Importantes

- ⚠️ Executar scripts SQL no Supabase Dashboard antes de testar
- ⚠️ Senha provisória deve ter no mínimo 6 caracteres
- ⚠️ Nova senha deve cumprir todos os requisitos
- ⚠️ Operadores só veem projetos atribuídos
- ⚠️ VIEWER foi completamente removido do sistema

## 🎯 Próximos Passos (Opcional)

- [ ] Implementar recuperação de senha via email
- [ ] Adicionar log de alterações de senha
- [ ] Implementar expiração de senha provisória
- [ ] Adicionar 2FA (autenticação de dois fatores)
- [ ] Dashboard específico para operadores
- [ ] Notificação por email ao criar usuário



