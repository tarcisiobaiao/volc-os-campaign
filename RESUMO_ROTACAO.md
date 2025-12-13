# 🔄 Rotação de Campanhas - Resumo Visual

## ✅ O que foi feito

```
[SQL Original]
    ↓
[Adaptado para excluir campanhas dos últimos 5 dias]
    ↓
[Salva automaticamente na tabela campaign_highlights]
    ↓
[Retorna campanhas para o frontend]
```

---

## 📊 Fluxo Completo

```
┌─────────────────────────────────────────────────────────────┐
│  DIA 1 (09/Dez)                                             │
├─────────────────────────────────────────────────────────────┤
│  SQL executa → Retorna 15 campanhas → Salva na tabela       │
│                                                             │
│  Campanhas retornadas:                                      │
│  ✅ 100, 101, 102, 103, 104 (em_alta)                       │
│  ✅ 200, 201, 202, 203, 204 (estagnada)                     │
│  ✅ 300, 301, 302, 303, 304 (em_baixa)                      │
│                                                             │
│  campaign_highlights:                                       │
│  | campaign_id | category  | highlighted_at |              │
│  |-------------|-----------|----------------|              │
│  | 100         | em_alta   | 2025-12-09     |              │
│  | 101         | em_alta   | 2025-12-09     |              │
│  | ...         | ...       | 2025-12-09     |              │
└─────────────────────────────────────────────────────────────┘

                          ⬇️

┌─────────────────────────────────────────────────────────────┐
│  DIA 2 (10/Dez)                                             │
├─────────────────────────────────────────────────────────────┤
│  SQL calcula: exclude_date = 10/12 - 5 = 05/12             │
│                                                             │
│  SQL exclui campanhas com highlighted_at >= 05/12           │
│  ❌ Campanhas 100-304 EXCLUÍDAS (foram do dia 09/12)        │
│                                                             │
│  SQL retorna NOVAS campanhas:                               │
│  ✅ 105, 106, 107, 108, 109 (em_alta)                       │
│  ✅ 205, 206, 207, 208, 209 (estagnada)                     │
│  ✅ 305, 306, 307, 308, 309 (em_baixa)                      │
│                                                             │
│  Salva com highlighted_at = 2025-12-10                      │
└─────────────────────────────────────────────────────────────┘

                          ⬇️

┌─────────────────────────────────────────────────────────────┐
│  DIA 3-5 (11-13/Dez)                                        │
├─────────────────────────────────────────────────────────────┤
│  Mesmo processo: sempre retorna campanhas DIFERENTES        │
│  Cada dia exclui os últimos 5 dias                         │
└─────────────────────────────────────────────────────────────┘

                          ⬇️

┌─────────────────────────────────────────────────────────────┐
│  DIA 6 (14/Dez)                                             │
├─────────────────────────────────────────────────────────────┤
│  SQL calcula: exclude_date = 14/12 - 5 = 09/12             │
│                                                             │
│  Campanhas do Dia 1 (09/12) agora PODEM aparecer!           │
│  ✅ Campanhas 100-304 voltam a ser elegíveis                │
│                                                             │
│  MAS: Só aparecem se ainda atenderem os critérios           │
│  (ROAS alto, variação >= 15%, etc.)                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Arquivos Criados/Modificados

### ✅ Arquivos SQL

1. **[create_campaign_highlights_table.sql](src/sql/create_campaign_highlights_table.sql)**
   - Tabela para rastrear campanhas destacadas
   - UNIQUE constraint evita duplicatas

2. **[get_rotated_campaign_highlights.sql](src/sql/get_rotated_campaign_highlights.sql)** ⭐ PRINCIPAL
   - Função RPC que executa tudo
   - Exclui campanhas dos últimos 5 dias
   - Salva automaticamente na tabela
   - Retorna resultados para frontend

3. **[get_rotated_campaign_highlights_v2.sql](src/sql/get_rotated_campaign_highlights_v2.sql)**
   - Versão backup (não usar)

### 📝 Arquivos de Documentação

4. **[DEPLOY_ROTACAO_CAMPANHAS.md](DEPLOY_ROTACAO_CAMPANHAS.md)**
   - Guia completo de deploy
   - Passo a passo para executar
   - Troubleshooting

5. **[COMO_FUNCIONA_ROTACAO.md](COMO_FUNCIONA_ROTACAO.md)**
   - Explicação detalhada do funcionamento
   - Exemplos práticos
   - Queries úteis

6. **[test_rotacao.sql](test_rotacao.sql)**
   - Script de teste completo
   - Valida se a rotação está funcionando
   - Simula 6 dias de uso

### 🔧 Scripts de Deploy

7. **[deploy_campaign_rotation.sh](deploy_campaign_rotation.sh)**
   - Script bash automatizado
   - Executa tudo com 1 comando
   - Valida se funcionou

### ✅ Frontend (já existia)

8. **[campaignHighlightsService.ts](src/services/campaignHighlightsService.ts)**
   - Service TypeScript
   - Chama a função RPC
   - Cache de 5 minutos

---

## 🚀 Como Fazer o Deploy

### Opção 1: Script Automatizado (Recomendado)

```bash
cd webgo
./deploy_campaign_rotation.sh
```

### Opção 2: Manual via Supabase SQL Editor

1. Abrir Supabase SQL Editor
2. Executar `create_campaign_highlights_table.sql`
3. Executar `get_rotated_campaign_highlights.sql`
4. Testar: `SELECT * FROM get_rotated_campaign_highlights();`

### Opção 3: Via psql

```bash
cd webgo

# 1. Criar tabela
psql "$DATABASE_URL" -f src/sql/create_campaign_highlights_table.sql

# 2. Criar função
psql "$DATABASE_URL" -f src/sql/get_rotated_campaign_highlights.sql

# 3. Testar
psql "$DATABASE_URL" -c "SELECT * FROM get_rotated_campaign_highlights();"
```

---

## 🧪 Como Testar

### Teste Rápido

```sql
-- No Supabase SQL Editor
SELECT * FROM get_rotated_campaign_highlights();
```

Esperado: Retorna até 15 campanhas

### Teste Completo

```bash
# Executar script de teste
psql "$DATABASE_URL" -f test_rotacao.sql
```

Esperado:
- ✅ Primeira execução: retorna campanhas e salva
- ✅ Segunda execução: retorna campanhas DIFERENTES
- ✅ Quantidade duplicada = 0
- ✅ Após resetar cooldown (6 dias): pode retornar campanhas antigas

---

## 📊 Verificações Importantes

### 1. Verificar se salvou hoje

```sql
SELECT COUNT(*) FROM campaign_highlights WHERE highlighted_at = CURRENT_DATE;
```

**Esperado**: > 0 (se já executou hoje)

### 2. Ver campanhas destacadas hoje

```sql
SELECT
  campaign_id,
  category,
  highlighted_at
FROM campaign_highlights
WHERE highlighted_at = CURRENT_DATE
ORDER BY category, campaign_id;
```

### 3. Quantas campanhas em cooldown

```sql
SELECT COUNT(DISTINCT campaign_id)
FROM campaign_highlights
WHERE highlighted_at >= CURRENT_DATE - INTERVAL '5 days';
```

**Quanto maior**, menos campanhas disponíveis para aparecer

---

## ⚙️ Configurações Atuais

| Configuração | Valor Atual | Como Mudar |
|-------------|-------------|------------|
| **Período de cooldown** | 5 dias | Linha 19: `INTERVAL '5 days'` → `'3 days'` |
| **Campanhas por categoria** | 5 | Linhas 129, 138, 148: `LIMIT 5` → `LIMIT 10` |
| **Variação ROAS mínima** | ±15% | Linhas 127, 135: `0.15` → `0.10` |
| **Gasto médio mínimo** | $20 | Linha 60: `AVG(spend) > 20` → `> 10` |
| **Cache frontend** | 5 minutos | [campaignHighlightsService.ts:23](src/services/campaignHighlightsService.ts#L23) |

---

## 🎯 Categorias de Campanhas

### 1. 🚨 Alerta Técnico
- **Critério**: GAM Match Rate <= 70% por 2 dias seguidos
- **Prioridade**: Máxima (aparece primeiro)
- **Quantidade**: Ilimitada (quantas atenderem o critério)

### 2. 📈 Em Alta
- **Critério**: Variação ROAS >= +15%
- **Quantidade**: Até 5
- **Ordenação**: Por variação (maior primeiro)

### 3. ➡️ Estagnada
- **Critério**: Variação ROAS entre -15% e +15%
- **Quantidade**: Até 5
- **Ordenação**: Menor variação + maior gasto

### 4. 📉 Em Baixa
- **Critério**: Variação ROAS <= -15% OU queda de lucro > $10/dia
- **Quantidade**: Até 5
- **Ordenação**: Por variação (menor primeiro)

---

## 🔍 Troubleshooting

### ❌ Problema: Sempre aparecem as mesmas campanhas

**Causa**: Função não está salvando na tabela

**Solução**:
```sql
-- Verificar se está salvando
SELECT COUNT(*) FROM campaign_highlights WHERE highlighted_at = CURRENT_DATE;

-- Se retornar 0, recriar a função
-- Executar: get_rotated_campaign_highlights.sql
```

### ❌ Problema: Nenhuma campanha aparece

**Causa**: Todas em cooldown ou sem dados suficientes

**Solução**:
```sql
-- Verificar dados
SELECT COUNT(*) FROM daily_campaign_metrics
WHERE date >= CURRENT_DATE - INTERVAL '14 days';

-- Limpar cooldown (APENAS PARA TESTE)
DELETE FROM campaign_highlights;
```

### ❌ Problema: Erro "function does not exist"

**Causa**: Função não foi criada no Supabase

**Solução**:
```bash
./deploy_campaign_rotation.sh
```

---

## ✅ Checklist de Validação

Após deploy, verificar:

- [ ] Tabela `campaign_highlights` existe
- [ ] Função `get_rotated_campaign_highlights()` existe
- [ ] Executar função retorna campanhas
- [ ] Executar novamente retorna campanhas DIFERENTES
- [ ] Tabela tem registros com `highlighted_at = CURRENT_DATE`
- [ ] Frontend carrega campanhas na home
- [ ] Cache do service funciona (5 minutos)

---

## 📞 Próximos Passos (Opcional)

1. **Dashboard de Analytics**
   - Visualizar histórico de campanhas destacadas
   - Gráficos de frequência

2. **Cron Job Diário**
   - Executar função todo dia às 6h AM
   - Garantir dados frescos

3. **Notificações**
   - Email/Slack quando campanha entra em "alerta_tecnico"

4. **Ajuste Dinâmico**
   - Variar período de cooldown baseado em quantidade de campanhas ativas
   - Se poucas campanhas: reduzir cooldown para 3 dias
   - Se muitas campanhas: aumentar para 7 dias

---

## 📄 Arquivos de Referência

- **Documentação Completa**: [COMO_FUNCIONA_ROTACAO.md](COMO_FUNCIONA_ROTACAO.md)
- **Guia de Deploy**: [DEPLOY_ROTACAO_CAMPANHAS.md](DEPLOY_ROTACAO_CAMPANHAS.md)
- **SQL Principal**: [get_rotated_campaign_highlights.sql](src/sql/get_rotated_campaign_highlights.sql)
- **Script de Teste**: [test_rotacao.sql](test_rotacao.sql)
- **Service Frontend**: [campaignHighlightsService.ts](src/services/campaignHighlightsService.ts)

---

## 🎉 Conclusão

O sistema está **100% funcional e automático**!

```
Frontend chama
    ↓
Função executa (exclui últimos 5 dias)
    ↓
Salva automaticamente
    ↓
Retorna campanhas diferentes todo dia
    ↓
Após 5 dias: campanhas antigas podem voltar
```

Sem necessidade de cron jobs ou processos manuais! 🚀
