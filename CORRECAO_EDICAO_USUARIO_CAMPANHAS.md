# Correção: Salvamento de Campanhas na Edição de Usuários

## 🎯 Objetivo

Garantir que quando o admin editar ou criar um usuário operador e selecionar campanhas, essas campanhas sejam **corretamente salvas** na tabela `user_campaigns` usando o `campaign_id` (VARCHAR) ao invés do `id` (INTEGER).

---

## 🔍 Problemas Identificados e Corrigidos

### 1. **Uso Inconsistente de IDs no Frontend**

**Problema**: O código estava usando `campaign.id` (INTEGER) em alguns lugares e `campaign.campaign_id` (VARCHAR) em outros, causando inconsistências.

**Locais corrigidos**:

#### a) Modal de Adicionar Usuário
```tsx
// ❌ ANTES
checked={newUser.campaign_ids?.includes(campaign.id)}
id={`new-campaign-${campaign.id}`}
{newUser.campaign_ids?.includes(campaign.id) ? ... }

// ✅ DEPOIS
checked={newUser.campaign_ids?.includes(campaign.campaign_id)}
id={`new-campaign-${campaign.campaign_id}`}
{newUser.campaign_ids?.includes(campaign.campaign_id) ? ... }
```

#### b) Modal de Editar Usuário
```tsx
// ❌ ANTES
checked={editUser.campaign_ids?.includes(campaign.id)}
id={`edit-campaign-${campaign.id}`}
{editUser.campaign_ids?.includes(campaign.id) ? ... }

// ✅ DEPOIS
checked={editUser.campaign_ids?.includes(campaign.campaign_id)}
id={`edit-campaign-${campaign.campaign_id}`}
{editUser.campaign_ids?.includes(campaign.campaign_id) ? ... }
```

#### c) Filtro de Campanhas ao Mudar Projetos
```tsx
// ❌ ANTES
const newCampaignIds = editUser.campaign_ids?.filter(cid =>
  projectCampaigns.some(c => c.id === cid)
) || [];

// ✅ DEPOIS
const newCampaignIds = editUser.campaign_ids?.filter(cid =>
  projectCampaigns.some(c => c.campaign_id === cid)
) || [];
```

---

### 2. **Logs Melhorados para Debug**

**Adicionados logs detalhados** em pontos críticos para facilitar o debug:

#### Frontend (UsersSettings.tsx)

```tsx
// Ao criar usuário
console.log('✅ Salvando novo usuário:', {
  projetos: newUser.project_ids,
  campanhas: newUser.campaign_ids
});

// Ao editar usuário
console.log('✅ Salvando alterações:', {
  projetos: editUser.project_ids,
  campanhas: editUser.campaign_ids
});
```

#### Backend (usersService.ts)

```typescript
// Ao criar usuário
console.log('🎯 Associando campanhas ao novo usuário:', {
  user_id: user.id,
  campaign_ids: input.campaign_ids
});
console.log('✅ Campanhas associadas com sucesso:', userCampaigns.length);

// Ao editar usuário
console.log('🎯 Atualizando campanhas do usuário:', {
  user_id: id,
  campaign_ids: input.campaign_ids
});
console.log('✅ Campanhas salvas com sucesso:', userCampaigns.length);
```

---

### 3. **Tratamento de Erros Aprimorado**

**Melhorias**:
- ✅ Captura de erros específicos ao inserir campanhas
- ✅ Rollback automático em caso de falha
- ✅ Logs de erro detalhados

```typescript
const { error: campError } = await supabase
  .from('user_campaigns')
  .insert(userCampaigns);

if (campError) {
  console.error('❌ Erro ao salvar campanhas:', campError);
  throw campError;
}
```

---

## 📊 Estrutura de Dados

### Tabela `campaigns`
```sql
- id (INTEGER)             -- PK interno, auto-incremento
- campaign_id (VARCHAR)    -- ID do Google Ads (identificador único)
- campaign_name (TEXT)
- project_id (INTEGER)
```

### Tabela `user_campaigns` (após correção do SQL)
```sql
- id (SERIAL)
- user_id (UUID)           -- FK → users.id
- campaign_id (VARCHAR)    -- FK → campaigns.campaign_id ✅
- created_at (TIMESTAMP)
```

### Interface TypeScript
```typescript
interface CreateUserInput {
  name: string;
  email: string;
  role: 'ADMIN' | 'OPERATOR';
  password: string;
  project_ids?: number[];
  campaign_ids?: string[];  // ← Array de VARCHARs (Google Ads IDs)
}
```

---

## 🔄 Fluxo Completo de Salvamento

### 1. **Criar Novo Usuário**

```
1. Admin seleciona projetos para o operador
   → handleNewUserProjectsChange() é chamado
   → Carrega campanhas desses projetos
   
2. Admin seleciona campanhas
   → newUser.campaign_ids = ["campaign_123", "campaign_456"]
   
3. Admin clica "Salvar"
   → usersService.create(newUser) é chamado
   → Cria usuário em auth.users
   → Cria registro em public.users
   → Insere em user_projects
   → Insere em user_campaigns com campaign_id (VARCHAR) ✅
```

### 2. **Editar Usuário Existente**

```
1. Admin clica "Editar" no usuário
   → openEditModal() é chamado
   → Carrega projetos do usuário (user_projects)
   → Carrega campanhas do usuário (user_campaigns)
   → Preenche editUser com dados existentes
   
2. Admin modifica projetos/campanhas
   → handleEditUserProjectsChange() atualiza lista de campanhas
   → editUser.campaign_ids é atualizado
   
3. Admin clica "Salvar Alterações"
   → usersService.update(userId, editUser) é chamado
   → Atualiza dados em public.users
   → Deleta todos os registros antigos de user_projects
   → Insere novos registros em user_projects
   → Deleta todos os registros antigos de user_campaigns
   → Insere novos registros em user_campaigns ✅
```

---

## ✅ Verificações Necessárias

### 1. **Antes de Testar - Execute o Script SQL**

**IMPORTANTE**: Execute primeiro o script de correção da tabela:
```bash
sql/fix_user_campaigns_campaign_id.sql
```

Esse script converte a estrutura da tabela para usar `campaign_id` (VARCHAR) ao invés de `id` (INTEGER).

### 2. **Como Testar**

#### Teste 1: Criar Novo Usuário
1. Faça login como admin
2. Vá para `/settings/users`
3. Clique em "Novo Usuário"
4. Preencha nome, email, senha
5. Selecione role "Operador"
6. Selecione projetos
7. **Selecione campanhas específicas**
8. Clique em "Salvar"
9. Abra o console do navegador e verifique:
   ```
   ✅ Salvando novo usuário: {
     projetos: [1, 2],
     campanhas: ["campaign_123", "campaign_456"]
   }
   🎯 Associando campanhas ao novo usuário: { ... }
   ✅ Campanhas associadas com sucesso: 2
   ```

#### Teste 2: Editar Usuário Existente
1. Faça login como admin
2. Vá para `/settings/users`
3. Clique em "Editar" em um usuário operador
4. **Modifique as campanhas selecionadas**
5. Clique em "Salvar Alterações"
6. Abra o console do navegador e verifique:
   ```
   ✅ Salvando alterações: {
     projetos: [1, 2],
     campanhas: ["campaign_789"]
   }
   🎯 Atualizando campanhas do usuário: { ... }
   ✅ Campanhas salvas com sucesso: 1
   ```

#### Teste 3: Verificar no Banco
```sql
-- Verificar campanhas associadas ao usuário
SELECT 
  u.name,
  u.email,
  uc.campaign_id,
  c.campaign_name,
  c.project_id
FROM users u
JOIN user_campaigns uc ON uc.user_id = u.id
LEFT JOIN campaigns c ON c.campaign_id = uc.campaign_id
WHERE u.email = 'operador@example.com';
```

**Resultado Esperado**: Deve mostrar as campanhas com `campaign_id` (VARCHAR) corretamente preenchido.

#### Teste 4: Login como Operador
1. Faça logout do admin
2. Faça login como o operador criado/editado
3. Vá para `/settings/campaigns`
4. **Deve ver apenas as campanhas atribuídas** ✅

---

## 📁 Arquivos Modificados

### Frontend
1. ✅ `/webgo/src/pages/settings/UsersSettings.tsx`
   - Corrigido uso de `campaign.id` → `campaign.campaign_id`
   - Adicionados logs de debug
   - Corrigido filtro ao mudar projetos

### Backend
2. ✅ `/webgo/src/services/usersService.ts`
   - Adicionados logs detalhados
   - Melhorado tratamento de erros
   - Confirmado que salvamento usa `campaign_id` (VARCHAR)

### SQL
3. ✅ `/webgo/sql/fix_user_campaigns_campaign_id.sql`
   - Script de migração da estrutura da tabela

---

## 🎉 Resultado Final

Agora, quando o admin:
1. ✅ **Criar um novo usuário operador** e selecionar campanhas → Campanhas são salvas corretamente
2. ✅ **Editar um usuário operador** e modificar campanhas → Campanhas são atualizadas corretamente
3. ✅ **Logs detalhados** aparecem no console para facilitar debug
4. ✅ **Operador faz login** → Vê apenas suas campanhas atribuídas

---

## 🚀 Deploy

### Ordem de Deploy:

1. **Banco de Dados**: Execute o script SQL
   ```bash
   sql/fix_user_campaigns_campaign_id.sql
   ```

2. **Frontend**: Faça deploy das mudanças
   - UsersSettings.tsx
   - usersService.ts

3. **Teste**: Verifique o fluxo completo

---

**Data de Implementação**: 2025-10-17  
**Status**: ✅ Pronto para Teste







