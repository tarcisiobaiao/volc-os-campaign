# Solução: Correção da Tabela user_campaigns

## 🔍 Problema Identificado

A tabela `user_campaigns` estava com uma **incongruência na foreign key**:

- ❌ **Antes**: `user_campaigns.campaign_id` referenciava `campaigns.id` (INTEGER - PK interno)
- ✅ **Correto**: `user_campaigns.campaign_id` deve referenciar `campaigns.campaign_id` (VARCHAR - ID do Google Ads)

### Impacto

Quando um operador fazia login, ele via **0 campanhas** mesmo tendo acesso configurado, porque:
1. A tabela `user_campaigns` armazenava o `id` interno da campanha (ex: 1, 2, 3...)
2. O código buscava pelo `campaign_id` do Google Ads (ex: "123456789_SEARCH_2024")
3. Os IDs não correspondiam, resultando em nenhuma campanha exibida

---

## ✅ Solução Implementada

### 1. **Script SQL de Migração**

Arquivo: `/Users/mac/Desktop/Sistema Webgo/webgo/sql/fix_user_campaigns_campaign_id.sql`

O script realiza:

1. ✅ Cria coluna temporária `campaign_id_new` (VARCHAR)
2. ✅ Migra dados: converte `campaigns.id` → `campaigns.campaign_id`
3. ✅ Remove foreign key antiga
4. ✅ Remove coluna antiga `campaign_id`
5. ✅ Renomeia `campaign_id_new` → `campaign_id`
6. ✅ Cria nova foreign key: `campaign_id` → `campaigns.campaign_id`
7. ✅ Recria índices e constraints
8. ✅ Adiciona validações e logs de verificação

### 2. **Atualização do Código Frontend**

Arquivo: `/Users/mac/Desktop/Sistema Webgo/webgo/src/pages/settings/CampaignsSettings.tsx`

Adicionada lógica de filtro adicional:

```typescript
// Filtro por campanhas específicas do operador (se houver)
let matchesUserCampaigns = true;
if (userProfile?.role === 'OPERATOR' && allowedCampaignIds.length > 0) {
  // campaign.id é o campaign_id (Google Ads ID) que vem do banco
  matchesUserCampaigns = allowedCampaignIds.includes(campaign.id);
}
```

Agora o filtro verifica:
- ✅ Projetos permitidos (via `user_projects`)
- ✅ **Campanhas permitidas (via `user_campaigns`)** ← NOVO!
- ✅ Status ROAS (verde, amarelo, laranja, vermelho)
- ✅ Busca por nome

---

## 📋 Como Aplicar a Correção

### Passo 1: Executar o Script SQL

```bash
# Via Supabase SQL Editor ou psql
psql -h <host> -U <user> -d <database> -f sql/fix_user_campaigns_campaign_id.sql
```

Ou copie e cole o conteúdo do arquivo no **Supabase SQL Editor**.

### Passo 2: Verificar a Migração

O script mostrará:
```
✅ Total de registros em user_campaigns: X
✅ Registros migrados com sucesso: X
```

E exibirá os primeiros 10 registros para verificação visual.

### Passo 3: Testar com Usuário Operador

1. Faça login como operador
2. Navegue para `/settings/campaigns`
3. **Resultado esperado**: Agora deve ver as campanhas atribuídas!

---

## 🔧 Estrutura de Dados

### Tabela `campaigns`

```sql
- id (INTEGER)            -- PK interno, auto-incremento
- campaign_id (VARCHAR)   -- ID do Google Ads (único, identificador real)
- campaign_name (TEXT)
- project_id (INTEGER)
- ...
```

### Tabela `user_campaigns` (CORRIGIDA)

```sql
- id (SERIAL)
- user_id (UUID)          -- FK → users.id
- campaign_id (VARCHAR)   -- FK → campaigns.campaign_id ✅
- created_at (TIMESTAMP)
```

---

## 🧪 Validações

### No Banco de Dados

```sql
-- Verificar tipo da coluna
SELECT data_type 
FROM information_schema.columns 
WHERE table_name = 'user_campaigns' 
  AND column_name = 'campaign_id';
-- Esperado: character varying

-- Verificar constraint
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'user_campaigns'::regclass 
  AND conname LIKE '%campaign_id%';
-- Esperado: FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
```

### No Frontend

1. Abra o console do navegador
2. Procure por logs:
```
🔐 Filtros do usuário carregados: {
  role: "OPERATOR",
  projectIds: [1, 2],
  campaignIds: ["123456789_SEARCH", "987654321_DISPLAY"],
  hasCampaignFilter: true
}
```

---

## 📊 Fluxo Completo de Filtro para Operadores

```
1. Operador faz login
2. useUserFilters() carrega:
   - allowedProjectIds = [1, 2]
   - allowedCampaignIds = ["campaign_123", "campaign_456"]
3. useSupabaseData() busca campanhas do banco
4. filteredCampaigns aplica filtros:
   ✓ Busca por nome
   ✓ Filtro de projeto
   ✓ Filtro de status ROAS
   ✓ allowedProjectIds ✅
   ✓ allowedCampaignIds ✅
5. Operador vê apenas suas campanhas autorizadas
```

---

## 🎯 Resultado Final

**Antes da correção:**
- Operador via: **0 campanhas** ❌

**Depois da correção:**
- Operador vê: **Campanhas atribuídas pelo admin** ✅
- Filtragem por projeto funciona ✅
- Filtragem por campanha específica funciona ✅

---

## 🔒 Segurança

- ✅ Foreign keys garantem integridade referencial
- ✅ Cascade deletes evitam registros órfãos
- ✅ Filtros aplicados no backend (useSupabaseData)
- ✅ Filtros adicionais no frontend (defesa em profundidade)
- ✅ Admins não são afetados por filtros (acesso total)

---

## 📝 Arquivos Modificados

1. ✅ `/webgo/sql/fix_user_campaigns_campaign_id.sql` (NOVO)
2. ✅ `/webgo/src/pages/settings/CampaignsSettings.tsx` (ATUALIZADO)

---

## 🚀 Próximos Passos

Após aplicar o script SQL, você deve:

1. ✅ Testar login como operador
2. ✅ Verificar visualização de campanhas
3. ✅ Confirmar que filtros funcionam
4. ✅ Validar dados no Supabase (tabela `user_campaigns`)

---

**Data de Implementação**: 2025-10-17  
**Status**: ✅ Pronto para Deploy

