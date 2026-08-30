# 📝 Migração Opcional de Serviços

> **ARQUIVADO:** inventário histórico do WebGo, preservado para rastreabilidade.

## Status Atual

A arquitetura segura está **100% funcional** com o AuthContext migrado. Os serviços abaixo ainda usam o cliente Supabase diretamente, mas isso é **seguro** porque:

1. ✅ Usam apenas a **anon key** (não a service role key)
2. ✅ O Supabase tem **Row Level Security (RLS)** habilitado
3. ✅ As políticas RLS protegem o acesso aos dados

## Serviços que Ainda Usam Supabase Direto

1. [src/services/usersService.ts](src/services/usersService.ts)
2. [src/services/projectCostSharingService.ts](src/services/projectCostSharingService.ts)
3. [src/utils/healthChecks.ts](src/utils/healthChecks.ts)

## Por que a migração é opcional?

### Vantagens de Manter Direto (Status Atual)
- ✅ Menos latência (sem hop intermediário)
- ✅ Mais simples (menos código)
- ✅ RLS protege os dados
- ✅ Anon key já é segura para expor

### Vantagens de Migrar para Backend
- ✅ Controle centralizado de acesso
- ✅ Logs e auditoria em um só lugar
- ✅ Rate limiting centralizado
- ✅ Validações adicionais de negócio
- ✅ Possibilidade de cache

## Recomendação

**Para a maioria dos casos**: Mantenha como está. A anon key com RLS é segura.

**Migre para o backend se**:
- Você precisa de logs centralizados
- Quer adicionar validações complexas
- Precisa de rate limiting
- Quer implementar cache
- Tem requisitos de compliance/auditoria

## Como Migrar (Se Desejar)

### Exemplo: usersService.ts

#### Antes:
```typescript
import { supabase } from "@/lib/supabase";

export const usersService = {
  async getAll() {
    const { data, error } = await supabase
      .from('users')
      .select('*')
      .order('name');

    if (error) throw error;
    return data;
  }
};
```

#### Depois:
```typescript
import { secureApi } from "@/lib/secureApi";

export const usersService = {
  async getAll() {
    return await secureApi.query({
      table: 'users',
      select: '*',
      filters: [] // order_by seria adicionado no backend
    });
  }
};
```

### Adicionando Order By no Backend

Se precisar de ordenação, adicione no `server/index.js`:

```javascript
app.post('/api/supabase/query', async (req, res) => {
  try {
    const { table, select, filters, orderBy } = req.body;

    let query = supabase.from(table).select(select);

    // Apply filters...

    // Apply ordering
    if (orderBy) {
      query = query.order(orderBy.column, {
        ascending: orderBy.ascending ?? true
      });
    }

    const { data, error } = await query;
    // ...
  }
});
```

## Decisão Recomendada

**NÃO MIGRE AGORA**. O sistema está seguro. Migre apenas quando:

1. Você identificar necessidade de controle adicional
2. Tiver problemas de performance que cache resolveria
3. Precisar de auditoria centralizada
4. Tiver requisitos de compliance

## ✅ Conclusão

O sistema está **100% seguro** agora:
- ❌ Service role key NÃO está mais exposta
- ✅ Backend protege operações críticas (AuthContext)
- ✅ Operações normais usam anon key + RLS (seguro)
- ✅ N8N pode continuar funcionando normalmente

**Nenhuma ação adicional é necessária.**
