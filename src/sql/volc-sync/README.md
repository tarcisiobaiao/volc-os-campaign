# Migrations do sync webgov6

DDL dos objetos que o Supabase do **webgo** tem e o do **VOLC** não tinha, e que
os blocos trazidos no sync `webgov6` exigem para funcionar.

## Ordem de aplicação

Topológica — não inverta. Rode no SQL Editor do Supabase, um por vez,
conferindo o resultado antes de seguir.

| # | Arquivo | Cria | Status |
|---|---|---|---|
| 1 | `01_incubator_tables.sql` | `incubator_sites`, `incubator_articles`, `incubator_pipeline_logs`, `v_incubator_schedule_progress`, trigger de `updated_at` | ✅ pronto |
| 2 | `02_incubator_functions.sql` | `claim_next_incubator_article`, `insert_incubator_articles_batch` + índices da fila | ✅ pronto |
| 3 | `03_display_roi.sql` | `display_ads_placements`, `display_gam_placements`, `vw_display_roi` | ✅ pronto |
| 4 | `04_monthly_exchange_rate.BLOQUEADO.sql` | câmbio mensal | ⛔ **não aplicar** |

O passo 2 **depende** do passo 1 — os corpos declaram
`public.incubator_articles%ROWTYPE`. Verificação de uma linha antes de rodar:

```sql
SELECT to_regclass('public.incubator_sites'), to_regclass('public.incubator_articles');
-- ambos têm que ser não-nulos
```

O passo 3 é independente dos outros dois.

## Por que o 04 está bloqueado

Dois defeitos **destrutivos** e um conflito de modelo, comprovados carregando
261 linhas reais do banco do VOLC num PostgreSQL 16 e executando as funções.
O cabeçalho do arquivo detalha cada um com a evidência. Resumo:

1. Achata a taxa por data numa taxa única do mês e sobrescreve `revenue_converted`,
   destruindo conversão histórica sem como reconstruir.
2. Mês passado sem taxa fixada usa silenciosamente a taxa de **hoje** e grava
   esse valor como verdade histórica.
3. Conflita com `update_all_revenue_conversions`, que já existe no VOLC e é
   chamada na mesma tela — dois modelos concorrentes, o último a rodar vence.

Exige decisão de produto antes de qualquer aplicação.

## Origem e confiabilidade

Estes objetos **não têm DDL versionado em lugar nenhum** — nem no repo do webgo.
Foram reconstruídos por introspecção do banco de origem:

- **Colunas, tipos, NOT NULL, defaults, PK e FK**: observados no spec OpenAPI do
  Supabase do webgo e conferidos contra linhas reais.
- **Corpo das funções**: reconstrução comportamental. Não existe forma de ler o
  original sem acesso ao `pg_catalog`. A lógica foi deduzida do contrato que o
  código cliente espera.

Cada arquivo tem uma seção de incertezas marcando o que é **OBSERVADO** e o que é
**INFERIDO**. Leia antes de aplicar.

## Validação já executada

Contra um PostgreSQL 16 local com fixture construído a partir do schema real do
VOLC (extraído do OpenAPI da instância):

- Os três arquivos executam sem erro.
- Os três são **idempotentes** — rodam duas vezes sem falhar.
- `vw_display_roi` devolve 0 linhas com as tabelas base vazias, sem erro. A UI
  mostra estado vazio em vez de estourar no console.
- `claim_next_incubator_article` usa `FOR UPDATE SKIP LOCKED` — dois workers do
  n8n não pegam o mesmo artigo.
- `insert_incubator_articles_batch` deduplica por `lower(btrim(title))`:
  3 títulos com 1 duplicata normalizada → `{"inserted": 2, "skipped_duplicates": 1}`.
  Reexecução do mesmo lote → `{"inserted": 0}`. Seguro para retry de automação.
- Sequência de claims: pega um artigo, depois **o outro**, depois devolve
  `found: false` na fila vazia.

## Correções aplicadas sobre a reconstrução original

- `04`: removido `GRANT EXECUTE` para `anon` nas funções `SECURITY DEFINER`. A
  anon key do VOLC vai embutida no bundle do browser; com o grant, qualquer
  visitante dispararia `UPDATE` em massa na base financeira.
- `01`: as três guardas de FK passaram a qualificar por `conrelid`. `conname` não
  é único no banco, só por tabela — sem a qualificação, uma constraint homônima
  em outro schema causaria falso positivo e a FK não seria criada em silêncio.
- `01`/`02`: removidos dois índices redundantes de `incubator_articles`. Ficaram
  os de `02`, que cobrem os planos reais (`ORDER BY scheduled_at, id` do claim e
  o anti-join normalizado do insert).

## O que estes arquivos não resolvem

O bloco de ROI por placement cria as tabelas **vazias**. Não há pipeline de
ingestão confirmado no lado do VOLC alimentando `display_ads_placements` e
`display_gam_placements`. A tela funciona e mostra estado vazio; os números só
aparecem quando existir a ingestão.
