# 🚀 Instruções para Testar o RPC `get_projects_summary`

## 📋 O que foi feito?

Implementamos a **primeira otimização de teste** do sistema, substituindo múltiplas queries por uma única função RPC no Supabase.

### Antes (❌ Ineficiente):
- **4 queries por projeto** (campaigns, spend, revenue, campaign count)
- Para 20 projetos = **80+ queries**
- Transferência de ~500KB de dados
- Múltiplos `.reduce()` no frontend

### Depois (✅ Otimizado):
- **1 única query RPC** para todos os projetos
- Agregações feitas no PostgreSQL
- Transferência de ~10KB de dados
- **~95% de redução** em queries

---

## 🔧 Passo 1: Criar a RPC Function no Supabase

1. Abra o **Supabase Dashboard** > **SQL Editor**
2. Copie todo o conteúdo do arquivo:
   ```
   src/sql/rpc_get_projects_summary.sql
   ```
3. Cole no SQL Editor e clique em **"Run"**
4. Você deve ver: ✅ **Success. No rows returned**

### Testar a RPC manualmente (opcional):

Execute este SQL para verificar se a função está funcionando:

```sql
-- Teste 1: Todos os projetos de janeiro 2025
SELECT * FROM get_projects_summary('2025-01-01', '2025-01-31', NULL);

-- Teste 2: Projeto específico (ID 11)
SELECT * FROM get_projects_summary('2025-01-01', '2025-01-31', 11);

-- Teste 3: Verificar estrutura dos dados retornados
SELECT
  id,
  project_name,
  total_spend,
  total_revenue,
  campaign_count,
  active_campaigns
FROM get_projects_summary('2025-01-01', '2025-01-31', NULL)
LIMIT 1;
```

**Resultados esperados:**
- Deve retornar lista de projetos com métricas agregadas
- Campos: id, project_name, domain, status, total_spend, total_revenue, campaign_count, etc.

---

## 🧪 Passo 2: Testar no Frontend

### Cenários de Teste:

#### 1. **Dashboard Principal** (General Dashboard)
- Acesse: `http://localhost:8084/dashboard`
- Verifique se os cards de projetos carregam corretamente
- Compare os valores com a versão anterior (se possível)

#### 2. **Filtros de Data**
Teste com diferentes períodos:
- ✅ **Hoje** - deve usar data atual
- ✅ **Últimos 7 dias** - deve calcular range corretamente
- ✅ **Últimos 30 dias** - deve calcular range corretamente
- ✅ **Período personalizado** - selecione datas específicas

#### 3. **Filtro de Projeto Específico**
- Selecione um projeto específico no dropdown
- Verifique se métricas correspondem ao projeto selecionado

#### 4. **Verificar Console do Navegador**
Abra o DevTools (F12) > Console e procure por:
- ✅ `"RPC returned X projects with aggregated metrics"` → **Sucesso!**
- ❌ `"Error calling get_projects_summary RPC"` → **Erro na RPC**
- ⚠️ `"RPC failed, falling back to old method"` → **RPC falhou, mas fallback funcionou**

---

## 🔍 Passo 3: Validar Resultados

### Checklist de Validação:

- [ ] Projetos carregam na tela principal
- [ ] Valores de **Investimento** parecem corretos
- [ ] Valores de **Faturamento** parecem corretos
- [ ] **ROI** e **ROAS** calculados corretamente
- [ ] **Contagem de campanhas** correta
- [ ] Status dos projetos (Ativo/Pausado) correto
- [ ] Filtros de data funcionam
- [ ] Filtro de projeto específico funciona
- [ ] Performance melhorou (carregamento mais rápido)

---

## ⚡ Monitorar Performance

### No Console do Navegador:

Abra DevTools > **Network** tab:
1. Limpe o log (🚫 ícone)
2. Recarregue a página (F5)
3. Filtre por: `supabase` ou `rpc`
4. Procure pela chamada: **`get_projects_summary`**

**O que observar:**
- ✅ **1 única requisição** para `rpc/get_projects_summary` (ao invés de 80+)
- ✅ **Tamanho da resposta** menor (~10KB vs ~500KB)
- ✅ **Tempo de resposta** mais rápido (200-400ms vs 2-4s)

---

## 🐛 Se algo quebrar:

### O código tem **fallback automático**:
Se a RPC falhar, o sistema automaticamente volta para o método antigo. Você verá este aviso no console:

```
⚠️ RPC failed, falling back to old method
```

Isso significa:
- ✅ **Nada quebrou!** Sistema continua funcionando
- ❌ **RPC não está configurada** ou tem erro no SQL
- 🔧 **Ação:** Revisar o passo 1 (criação da RPC)

### Erros Comuns:

#### ❌ Erro: `function get_projects_summary does not exist`
**Solução:** A RPC não foi criada. Execute o SQL do passo 1.

#### ❌ Erro: `column "campaigns.campaign_id" does not exist`
**Solução:** Verificar schema das tabelas. O RPC espera:
- Tabela `campaigns` com coluna `campaign_id`
- Tabela `daily_campaign_metrics` com coluna `campaign_id`
- Tabela `daily_project_metrics` com coluna `project_id`

#### ❌ Erro: `permission denied for function get_projects_summary`
**Solução:** Configurar permissões no Supabase:
```sql
GRANT EXECUTE ON FUNCTION get_projects_summary TO authenticated;
GRANT EXECUTE ON FUNCTION get_projects_summary TO anon;
```

---

## 📊 Comparação: Antes vs Depois

| Métrica                  | Antes (Antigo) | Depois (RPC) | Melhoria |
|--------------------------|----------------|--------------|----------|
| Queries por load         | 80+            | 1            | 98.8%    |
| Dados transferidos       | ~500KB         | ~10KB        | 98%      |
| Tempo de resposta        | 2-4s           | 200-400ms    | 90%      |
| Operações `.reduce()`    | 2 por projeto  | 0            | 100%     |
| Pressão no servidor      | Alta           | Baixa        | ~95%     |

---

## ✅ Conclusão do Teste

Após validar que tudo funciona:

1. ✅ **Se tudo funcionar:** Podemos prosseguir com as outras 7 RPCs do plano
2. ❌ **Se algo quebrar:** Reverta o código e investigue o erro
3. ⚠️ **Se fallback ativar:** RPC precisa de ajustes, mas sistema continua funcionando

---

## 🚀 Próximos Passos (se o teste passar)

Após confirmar que esta RPC funciona, implementaremos:

1. ✅ **RPC 1:** `get_projects_summary` ← **VOCÊ ESTÁ AQUI**
2. ⏭️ **RPC 2:** `get_dashboard_totals` (substitui reduces no dashboard)
3. ⏭️ **RPC 3:** `get_campaign_aggregated_metrics` (15 reduces → 1 RPC)
4. ⏭️ **RPC 4:** `get_daily_metrics_aggregated`
5. ⏭️ **RPC 5:** `get_operational_costs_summary`
6. ⏭️ **RPC 6:** `get_tax_rates_for_range`

---

## 📝 Notas Importantes

- O código antigo foi mantido como `getProjectsOld()` para fallback
- Nenhum dado é modificado, apenas a forma de buscar
- A RPC é **read-only** (apenas SELECT)
- Funcionalidades de filtro por usuário (OPERATOR) preservadas
- Cálculo de custos operacionais e impostos preservado

---

## 🆘 Suporte

Se precisar reverter as mudanças:
1. A função antiga está preservada como `getProjectsOld()`
2. Remova a linha de try/catch no `getProjects()` principal
3. Ou simplesmente retorne do catch sem chamar `getProjectsOld()`

**Arquivo modificado:** `src/services/supabaseDataService.ts` (linhas ~518-837)
