# Como Funciona a Rotação de Campanhas Destacadas

## Resumo Executivo

✅ **Objetivo**: Mostrar campanhas diferentes todo dia na home
✅ **Regra**: Mesma campanha só pode reaparecer após 5 dias
✅ **Automático**: A função SQL já faz tudo sozinha

---

## Fluxo Completo

### 1. Usuário Acessa a Home

```
Usuário abre a home
    ↓
Frontend chama: campaignHighlightsService.getCampaignHighlights()
    ↓
Service chama: supabase.rpc('get_rotated_campaign_highlights')
    ↓
Função SQL executa
```

### 2. Dentro da Função SQL (get_rotated_campaign_highlights)

```sql
-- PASSO A: Calcular data de exclusão
v_exclude_date = HOJE - 5 dias

-- PASSO B: Buscar campanhas, MAS excluindo as que foram destacadas recentemente
SELECT campanhas
FROM daily_campaign_metrics
WHERE campanha NOT IN (
  SELECT campaign_id FROM campaign_highlights
  WHERE highlighted_at >= v_exclude_date  -- Últimos 5 dias
)

-- PASSO C: Selecionar top 5 em alta, 5 estagnadas, 5 em baixa

-- PASSO D: Salvar automaticamente na tabela campaign_highlights
INSERT INTO campaign_highlights (campaign_id, category, highlighted_at)
VALUES (123, 'em_alta', HOJE), (456, 'em_baixa', HOJE), ...

-- PASSO E: Retornar resultados para o frontend
RETURN campanhas_selecionadas
```

### 3. Frontend Exibe

```
Frontend recebe campanhas
    ↓
Agrupa por categoria: em_alta, estagnada, em_baixa, alerta_tecnico
    ↓
Renderiza na home
```

---

## Exemplo Prático

### Cenário: 10 dias de uso

#### **Dia 1 (Hoje - 09/Dez)**
```
SQL retorna e salva:
- Campanhas: 100, 101, 102, 103, 104 (em_alta)
- Campanhas: 200, 201, 202, 203, 204 (estagnada)
- Campanhas: 300, 301, 302, 303, 304 (em_baixa)

Tabela campaign_highlights:
| campaign_id | category   | highlighted_at |
|------------|-----------|---------------|
| 100        | em_alta    | 2025-12-09    |
| 101        | em_alta    | 2025-12-09    |
| ...        | ...        | 2025-12-09    |
```

#### **Dia 2 (10/Dez)**
```
SQL exclui campanhas de 05/Dez até hoje (últimos 5 dias)
    ↓
Campanhas 100-104, 200-204, 300-304 EXCLUÍDAS
    ↓
Retorna NOVAS campanhas: 105-109, 205-209, 305-309
    ↓
Salva na tabela com highlighted_at = 2025-12-10
```

#### **Dia 3, 4, 5 (11-13/Dez)**
```
Mesmo processo: sempre exclui os últimos 5 dias
Cada dia retorna campanhas DIFERENTES
```

#### **Dia 6 (14/Dez)**
```
v_exclude_date = 14/12 - 5 dias = 09/12
    ↓
Campanhas do Dia 1 (highlighted_at = 09/12) agora PODEM aparecer novamente!
    ↓
Mas só aparecem se ainda atenderem os critérios (ROAS alto, variação, etc.)
```

---

## Tabela campaign_highlights - Estrutura

```sql
CREATE TABLE campaign_highlights (
  id              BIGSERIAL PRIMARY KEY,
  campaign_id     BIGINT NOT NULL,           -- ID da campanha
  category        VARCHAR(50) NOT NULL,      -- 'em_alta', 'em_baixa', 'estagnada', 'alerta_tecnico'
  highlighted_at  DATE NOT NULL,             -- Data que foi destacada
  created_at      TIMESTAMP DEFAULT now(),

  UNIQUE(campaign_id, category, highlighted_at)  -- Evita duplicatas no mesmo dia
);
```

### Exemplo de Dados

```sql
SELECT * FROM campaign_highlights ORDER BY highlighted_at DESC LIMIT 10;

-- Resultado:
| id  | campaign_id | category   | highlighted_at | created_at          |
|-----|------------|-----------|---------------|---------------------|
| 150 | 12345      | em_alta    | 2025-12-09    | 2025-12-09 08:30:00 |
| 151 | 12346      | em_baixa   | 2025-12-09    | 2025-12-09 08:30:00 |
| 152 | 12347      | estagnada  | 2025-12-09    | 2025-12-09 08:30:00 |
| 140 | 12345      | em_alta    | 2025-12-03    | 2025-12-03 09:15:00 |  ← Mesma campanha, 6 dias antes
| ... | ...        | ...        | ...           | ...                 |
```

---

## Como a Exclusão Funciona no SQL

### Para Alertas Técnicos (GAM Match Rate)

```sql
tech_alert_list AS (
  SELECT m.campaign_id, ...
  FROM ...
  WHERE ...
    -- EXCLUSÃO: Não pegar campanhas que foram "alerta_tecnico" nos últimos 5 dias
    AND m.campaign_id NOT IN (
      SELECT ch.campaign_id
      FROM campaign_highlights ch
      WHERE ch.highlighted_at >= v_exclude_date
        AND ch.category = 'alerta_tecnico'
    )
)
```

### Para Campanhas Normais (em_alta, em_baixa, estagnada)

```sql
calculated AS (
  SELECT m.campaign_id, ...
  FROM ...
  WHERE ...
    -- EXCLUSÃO: Não pegar campanhas que foram destacadas em QUALQUER categoria nos últimos 5 dias
    AND m.campaign_id NOT IN (
      SELECT ch.campaign_id
      FROM campaign_highlights ch
      WHERE ch.highlighted_at >= v_exclude_date
    )
)
```

**Diferença importante**:
- Alertas técnicos: só excluem se foram alertas técnicos recentemente
- Outras categorias: excluem se apareceram em QUALQUER categoria recentemente

---

## Queries Úteis para Monitoramento

### 1. Verificar se está funcionando hoje

```sql
SELECT
  COUNT(*) as total_campanhas_destacadas_hoje,
  STRING_AGG(DISTINCT category, ', ') as categorias
FROM campaign_highlights
WHERE highlighted_at = CURRENT_DATE;

-- Esperado: > 0 (se já foi executado hoje)
```

### 2. Ver histórico de uma campanha específica

```sql
SELECT
  campaign_id,
  category,
  highlighted_at,
  AGE(CURRENT_DATE, highlighted_at) as dias_atras
FROM campaign_highlights
WHERE campaign_id = 12345
ORDER BY highlighted_at DESC;

-- Mostra quando a campanha 12345 foi destacada
```

### 3. Campanhas que apareceram mais vezes

```sql
SELECT
  campaign_id,
  COUNT(*) as vezes_destacada,
  STRING_AGG(DISTINCT category, ', ') as categorias_usadas,
  MIN(highlighted_at) as primeira_vez,
  MAX(highlighted_at) as ultima_vez
FROM campaign_highlights
GROUP BY campaign_id
HAVING COUNT(*) > 1
ORDER BY vezes_destacada DESC
LIMIT 20;

-- Mostra as "campeãs" que aparecem muito na home
```

### 4. Quantas campanhas estão em cooldown agora

```sql
SELECT COUNT(DISTINCT campaign_id) as campanhas_em_cooldown
FROM campaign_highlights
WHERE highlighted_at >= CURRENT_DATE - INTERVAL '5 days';

-- Quanto maior, menos campanhas disponíveis para aparecer hoje
```

### 5. Limpeza de dados antigos (opcional)

```sql
-- Manter apenas 30 dias de histórico
DELETE FROM campaign_highlights
WHERE highlighted_at < CURRENT_DATE - INTERVAL '30 days';

-- Ou 60 dias para análises mais longas
DELETE FROM campaign_highlights
WHERE highlighted_at < CURRENT_DATE - INTERVAL '60 days';
```

---

## Comportamento Especial: Poucas Campanhas

### E se não houver campanhas suficientes?

```sql
-- Exemplo: 100 campanhas ativas, mas 95 em cooldown
SELECT COUNT(*) FROM get_rotated_campaign_highlights();

-- Resultado: Pode retornar menos de 15 campanhas!
-- Motivos:
-- 1. Poucas campanhas elegíveis (spend > 20, dados >= 3 dias)
-- 2. Muitas em cooldown (últimos 5 dias)
-- 3. Critérios rigorosos (variação ROAS >= 15%)
```

**Solução**:
- Frontend deve tratar resultado vazio gracefully
- Exibir mensagem: "Sem destaques no momento"
- Ou reduzir o período de cooldown para 3 dias (ajustar v_exclude_date)

---

## Ajustes Possíveis

### 1. Mudar período de cooldown

```sql
-- Em get_rotated_campaign_highlights.sql
-- Linha ~18
v_exclude_date DATE := v_today_date - INTERVAL '5 days';  -- Mudar para 3 ou 7 dias
```

### 2. Mudar quantidade de campanhas por categoria

```sql
-- Linha ~129, 138, 148
LIMIT 5  -- Mudar para 10, por exemplo
```

### 3. Mudar critérios de variação de ROAS

```sql
-- Linha ~127 (em alta)
WHERE var_roas_pct >= 0.15  -- Mudar para 0.10 (10% ao invés de 15%)

-- Linha ~135 (em baixa)
WHERE var_roas_pct <= -0.15  -- Mudar para -0.10
```

---

## FAQ

**P: E se eu quiser forçar uma campanha a aparecer novamente?**

```sql
-- Deletar o registro de highlight
DELETE FROM campaign_highlights
WHERE campaign_id = 12345
  AND highlighted_at >= CURRENT_DATE - INTERVAL '5 days';

-- Na próxima execução, a campanha PODE aparecer (se atender critérios)
```

**P: Como garantir que a função é executada todo dia?**

R: A função é executada automaticamente quando o frontend chama. Mas você pode criar um cron job:

```sql
-- Criar extensão pg_cron (se disponível no Supabase)
SELECT cron.schedule('refresh-highlights', '0 6 * * *', $$
  SELECT get_rotated_campaign_highlights()
$$);
```

**P: A função salva SEMPRE, mesmo se retornar vazio?**

R: Não! Só salva se `v_result_count > 0`:

```sql
IF v_result_count > 0 THEN
  INSERT INTO campaign_highlights ...
END IF;
```

**P: O que acontece se rodar a função 2x no mesmo dia?**

R: A segunda execução retorna campanhas DIFERENTES da primeira (porque a primeira já foi salva e está em cooldown). Isso é proposital!

---

## Checklist de Deploy

- [ ] Criar tabela `campaign_highlights`
- [ ] Criar função `get_rotated_campaign_highlights()`
- [ ] Executar função pela primeira vez
- [ ] Verificar se salvou na tabela
- [ ] Executar novamente e verificar que retorna campanhas diferentes
- [ ] Testar no frontend (home)
- [ ] Verificar cache do service (5 minutos)
- [ ] Aguardar 6 dias e verificar que campanhas antigas podem reaparecer

---

## Conclusão

O sistema está **totalmente automático**:

1. Frontend chama a função
2. Função retorna campanhas (excluindo as dos últimos 5 dias)
3. Função salva automaticamente na tabela
4. Próxima vez: retorna campanhas diferentes
5. Após 5 dias: campanhas antigas podem voltar

Sem necessidade de cron jobs ou processos manuais! 🎉
