# Catálogo de Triggers - Banco de Dados

> **Snapshot de referência:** catálogo gerado; pode divergir do banco vivo.

**Arquivo de Backup:** `db_cluster-20-01-2026@07-30-01.backup`  
**Data de Catalogação:** 20 de Janeiro de 2026

---

## Resumo Executivo

- **Total de Triggers:** 40 triggers
- **Schemas:** public, storage, realtime
- **Event Triggers:** 6 event triggers

---

## Schema: PUBLIC

### 1. **populate_project_id_gam**
- **Tabela:** `gam_metrics`
- **Tipo:** BEFORE INSERT
- **Função:** `auto_populate_project_id_gam()`
- **Descrição:** Popula automaticamente o `project_id` baseado no `gam_network_code` quando não fornecido

### 2. **sync_revenue_to_daily_metrics**
- **Tabela:** `gam_metrics`
- **Tipo:** AFTER INSERT OR UPDATE
- **Função:** `sync_gam_revenue_to_daily_metrics()`
- **Descrição:** Sincroniza automaticamente revenue do GAM para daily_campaign_metrics quando dados GAM são inseridos/atualizados

### 3. **trg_campaigns_updated_at**
- **Tabela:** `campaigns`
- **Tipo:** BEFORE UPDATE
- **Função:** `set_updated_at()`
- **Descrição:** Atualiza automaticamente o campo `updated_at` em atualizações

### 4. **trg_dcm_updated_at**
- **Tabela:** `daily_campaign_metrics`
- **Tipo:** BEFORE UPDATE
- **Função:** `set_updated_at()`
- **Descrição:** Atualiza automaticamente o campo `updated_at` em atualizações

### 5. **trigger_adsense_metrics_change**
- **Tabela:** `adsense_metrics`
- **Tipo:** AFTER INSERT OR UPDATE
- **Função:** `trigger_adsense_metrics_change()`
- **Descrição:** Quando dados AdSense são inseridos/atualizados, atualiza campanhas relacionadas

### 6. **trigger_auto_populate_adsense_metrics**
- **Tabela:** `adsense_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE
- **Função:** `auto_populate_adsense_metrics()`
- **Descrição:** Preenche automaticamente campos relacionados em métricas AdSense

### 7. **trigger_calculate_gam_total_requests**
- **Tabela:** `daily_campaign_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE OF gam_impressions, unfilled_impressions
- **Função:** `calculate_gam_total_requests()`
- **Descrição:** Calcula total de requisições GAM baseado em impressões e impressões não preenchidas

### 8. **trigger_calculate_revenue_converted_adsense_historical**
- **Tabela:** `adsense_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE OF revenue, date
- **Função:** `calculate_revenue_converted_by_date()`
- **Descrição:** Calcula revenue convertido usando taxa de câmbio histórica baseada na data

### 9. **trigger_calculate_revenue_converted_campaign_historical**
- **Tabela:** `daily_campaign_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE OF revenue, date
- **Função:** `calculate_revenue_converted_by_date()`
- **Descrição:** Calcula revenue convertido usando taxa de câmbio histórica baseada na data

### 10. **trigger_calculate_revenue_converted_daily_project_historical**
- **Tabela:** `daily_project_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE OF revenue, date
- **Função:** `calculate_revenue_converted_by_date()`
- **Descrição:** Calcula revenue convertido usando taxa de câmbio histórica baseada na data

### 11. **trigger_calculate_revenue_converted_gam_historical**
- **Tabela:** `gam_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE OF revenue, date
- **Função:** `calculate_revenue_converted_by_date()`
- **Descrição:** Calcula revenue convertido usando taxa de câmbio histórica baseada na data

### 12. **trigger_campaign_funnel_urls_revenue_calculation**
- **Tabela:** `campaign_funnel_urls`
- **Tipo:** AFTER INSERT OR DELETE OR UPDATE
- **Função:** `trigger_calculate_adsense_campaign_revenue()`
- **Descrição:** Recalcula revenue de campanha quando URLs do funil são alteradas

### 13. **trigger_clean_funnel_url**
- **Tabela:** `campaign_funnel_urls`
- **Tipo:** BEFORE INSERT OR UPDATE
- **Função:** `clean_funnel_url()`
- **Descrição:** Remove automaticamente https://, http:// e www. das URLs do funil, além de barras finais

### 14. **trigger_daily_campaign_commission_calculation**
- **Tabela:** `daily_campaign_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE OF revenue_converted_revshare, spend
- **Função:** `trigger_calculate_commission_operator()`
- **Descrição:** Calcula comissão do operador baseado em revenue_converted_revshare, spend e taxa de imposto

### 15. **trigger_daily_campaign_metrics_revenue_conversion**
- **Tabela:** `daily_campaign_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE OF revenue
- **Função:** `trigger_new_revenue_conversion_daily_campaign()`
- **Descrição:** Converte revenue de USD para BRL usando taxa de câmbio atual

### 16. **trigger_daily_campaign_revshare_calculation**
- **Tabela:** `daily_campaign_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE
- **Função:** `trigger_auto_calculate_revshare()`
- **Descrição:** Calcula automaticamente revenue_converted_revshare baseado no revshare do projeto

### 17. **trigger_daily_project_metrics_insert**
- **Tabela:** `daily_project_metrics`
- **Tipo:** BEFORE INSERT
- **Função:** `trigger_daily_project_metrics_auto_fill()`
- **Descrição:** Preenche automaticamente project_id e calcula revenue_converted_revshare em novos registros

### 18. **trigger_daily_project_metrics_update**
- **Tabela:** `daily_project_metrics`
- **Tipo:** BEFORE UPDATE
- **Função:** `trigger_daily_project_metrics_auto_fill()`
- **Descrição:** Atualiza campos calculados em registros existentes

### 19. **trigger_exchange_rate_historical**
- **Tabela:** `system_settings`
- **Tipo:** AFTER UPDATE OF value
- **Função:** `record_exchange_rate_change()`
- **Descrição:** Registra mudanças na taxa de câmbio no histórico

### 20. **trigger_exchange_rate_update**
- **Tabela:** `system_settings`
- **Tipo:** AFTER UPDATE
- **Condição:** WHEN (new.key = 'dollar_exchange_rate')
- **Função:** `trigger_update_revenue_conversions()`
- **Descrição:** Recalcula todas as conversões de revenue quando taxa de câmbio é atualizada

### 21. **trigger_funnel_url_change**
- **Tabela:** `campaign_funnel_urls`
- **Tipo:** AFTER INSERT OR DELETE OR UPDATE
- **Função:** `trigger_funnel_url_change()`
- **Descrição:** Dispara agregação de revenue AdSense quando URLs do funil são alteradas

### 22. **trigger_gam_metrics_revenue_conversion**
- **Tabela:** `gam_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE OF revenue
- **Função:** `trigger_new_revenue_conversion_gam()`
- **Descrição:** Converte revenue de USD para BRL usando taxa de câmbio atual

### 23. **trigger_gam_metrics_updated_at**
- **Tabela:** `gam_metrics`
- **Tipo:** BEFORE UPDATE
- **Função:** `update_gam_metrics_updated_at()`
- **Descrição:** Atualiza automaticamente o campo `updated_at`

### 24. **trigger_normalize_url_projeto**
- **Tabela:** `daily_project_metrics`
- **Tipo:** BEFORE INSERT OR UPDATE
- **Função:** `normalize_url_projeto()`
- **Descrição:** Normaliza URL do projeto antes de inserir/atualizar

### 25. **trigger_operational_costs_updated_at**
- **Tabela:** `operational_costs`
- **Tipo:** BEFORE UPDATE
- **Função:** `update_updated_at_column()`
- **Descrição:** Atualiza automaticamente o campo `updated_at`

### 26. **trigger_project_revshare_update**
- **Tabela:** `projects`
- **Tipo:** AFTER UPDATE
- **Condição:** WHEN (old.revshare IS DISTINCT FROM new.revshare)
- **Função:** `trigger_recalculate_project_revshare()`
- **Descrição:** Recalcula revenue_converted_revshare em todas as métricas quando revshare do projeto muda

### 27. **trigger_sync_status_insert**
- **Tabela:** `campaigns`
- **Tipo:** BEFORE INSERT
- **Função:** `sync_status_from_google_ads()`
- **Descrição:** Sincroniza status da campanha com Google Ads em inserções

### 28. **trigger_sync_status_update**
- **Tabela:** `campaigns`
- **Tipo:** BEFORE UPDATE OF google_ads_status
- **Condição:** WHEN (old.google_ads_status IS DISTINCT FROM new.google_ads_status)
- **Função:** `sync_status_from_google_ads()`
- **Descrição:** Sincroniza status da campanha quando google_ads_status é alterado

### 29. **trigger_user_commission_update**
- **Tabela:** `users`
- **Tipo:** AFTER UPDATE OF commission_percentage
- **Condição:** WHEN (new.role = 'OPERATOR')
- **Função:** `trigger_update_user_commission()`
- **Descrição:** Recalcula comissões em todas as métricas quando comissão do operador é alterada

### 30. **update_system_settings_updated_at**
- **Tabela:** `system_settings`
- **Tipo:** BEFORE UPDATE
- **Função:** `update_system_settings_updated_at()`
- **Descrição:** Atualiza automaticamente o campo `updated_at`

---

## Schema: REALTIME

### 31. **tr_check_filters**
- **Tabela:** `subscription`
- **Tipo:** BEFORE INSERT OR UPDATE
- **Função:** `subscription_check_filters()`
- **Descrição:** Valida filtros de assinatura antes de inserir/atualizar

---

## Schema: STORAGE

### 32. **enforce_bucket_name_length_trigger**
- **Tabela:** `buckets`
- **Tipo:** BEFORE INSERT OR UPDATE OF name
- **Função:** `enforce_bucket_name_length()`
- **Descrição:** Garante que o nome do bucket não exceda 100 caracteres

### 33. **objects_delete_delete_prefix**
- **Tabela:** `objects`
- **Tipo:** AFTER DELETE
- **Função:** `delete_prefix_hierarchy_trigger()`
- **Descrição:** Remove hierarquia de prefixos quando objeto é deletado

### 34. **objects_insert_create_prefix**
- **Tabela:** `objects`
- **Tipo:** BEFORE INSERT
- **Função:** `objects_insert_prefix_trigger()`
- **Descrição:** Cria hierarquia de prefixos ao inserir novo objeto

### 35. **objects_update_create_prefix**
- **Tabela:** `objects`
- **Tipo:** BEFORE UPDATE
- **Condição:** WHEN (new.name <> old.name OR new.bucket_id <> old.bucket_id)
- **Função:** `objects_update_prefix_trigger()`
- **Descrição:** Atualiza hierarquia de prefixos quando nome ou bucket do objeto muda

### 36. **prefixes_create_hierarchy**
- **Tabela:** `prefixes`
- **Tipo:** BEFORE INSERT
- **Condição:** WHEN (pg_trigger_depth() < 1)
- **Função:** `prefixes_insert_trigger()`
- **Descrição:** Cria hierarquia de prefixos recursivamente

### 37. **prefixes_delete_hierarchy**
- **Tabela:** `prefixes`
- **Tipo:** AFTER DELETE
- **Função:** `delete_prefix_hierarchy_trigger()`
- **Descrição:** Remove hierarquia de prefixos quando prefixo é deletado

### 38. **update_objects_updated_at**
- **Tabela:** `objects`
- **Tipo:** BEFORE UPDATE
- **Função:** `update_updated_at_column()`
- **Descrição:** Atualiza automaticamente o campo `updated_at`

---

## EVENT TRIGGERS

### 39. **issue_graphql_placeholder**
- **Tipo:** EVENT TRIGGER
- **Evento:** sql_drop
- **Condição:** WHEN TAG IN ('DROP EXTENSION')
- **Função:** `extensions.set_graphql_placeholder()`
- **Descrição:** Define placeholder quando extensão GraphQL é removida

### 40. **issue_pg_cron_access**
- **Tipo:** EVENT TRIGGER
- **Evento:** ddl_command_end
- **Condição:** WHEN TAG IN ('CREATE EXTENSION')
- **Função:** `extensions.grant_pg_cron_access()`
- **Descrição:** Concede acesso ao pg_cron quando extensão é criada

### 41. **issue_pg_graphql_access**
- **Tipo:** EVENT TRIGGER
- **Evento:** ddl_command_end
- **Condição:** WHEN TAG IN ('CREATE FUNCTION')
- **Função:** `extensions.grant_pg_graphql_access()`
- **Descrição:** Concede acesso ao pg_graphql quando função é criada

### 42. **issue_pg_net_access**
- **Tipo:** EVENT TRIGGER
- **Evento:** ddl_command_end
- **Condição:** WHEN TAG IN ('CREATE EXTENSION')
- **Função:** `extensions.grant_pg_net_access()`
- **Descrição:** Concede acesso ao pg_net quando extensão é criada

### 43. **pgrst_ddl_watch**
- **Tipo:** EVENT TRIGGER
- **Evento:** ddl_command_end
- **Função:** `extensions.pgrst_ddl_watch()`
- **Descrição:** Monitora mudanças DDL para PostgREST

### 44. **pgrst_drop_watch**
- **Tipo:** EVENT TRIGGER
- **Evento:** sql_drop
- **Função:** `extensions.pgrst_drop_watch()`
- **Descrição:** Monitora remoções de objetos para PostgREST

---

## Triggers Removidos (Mencionados em Migrations)

Os seguintes triggers foram mencionados como removidos em migrations:

- `trigger_daily_campaign_revshare_calculation` (substituído)
- `trigger_daily_campaign_revshare_update` (substituído)
- `trigger_project_revshare_update` (substituído)
- `trigger_exchange_rate_sync` (substituído)
- `trigger_calculate_revenue_converted_daily_project` (substituído)
- `trigger_calculate_revenue_converted_gam` (substituído)
- `trigger_calculate_revenue_converted_adsense` (substituído)
- `trigger_calculate_revenue_converted_campaign` (substituído)
- `trigger_calculate_campaign_roas` (removido com tabela campaign_performance)

---

## Funções de Trigger

### Schema PUBLIC

1. `auto_populate_adsense_metrics()` - Preenche campos relacionados em métricas AdSense
2. `auto_populate_project_id_gam()` - Popula project_id baseado em gam_network_code
3. `calculate_gam_total_requests()` - Calcula total de requisições GAM
4. `calculate_revenue_converted_by_date()` - Converte revenue usando taxa histórica
5. `clean_funnel_url()` - Limpa e normaliza URLs de funil
6. `normalize_url_projeto()` - Normaliza URL do projeto
7. `record_exchange_rate_change()` - Registra mudanças na taxa de câmbio
8. `set_updated_at()` - Atualiza campo updated_at
9. `sync_gam_revenue_to_daily_metrics()` - Sincroniza revenue GAM para daily_campaign_metrics
10. `sync_status_from_google_ads()` - Sincroniza status com Google Ads
11. `trigger_adsense_metrics_change()` - Processa mudanças em métricas AdSense
12. `trigger_auto_calculate_revshare()` - Calcula revshare automaticamente
13. `trigger_calculate_adsense_campaign_revenue()` - Calcula revenue de campanha AdSense
14. `trigger_calculate_adsense_project_total_revenue()` - Calcula revenue total do projeto
15. `trigger_calculate_commission_operator()` - Calcula comissão do operador
16. `trigger_daily_project_metrics_auto_fill()` - Preenche campos em daily_project_metrics
17. `trigger_funnel_url_change()` - Processa mudanças em URLs de funil
18. `trigger_new_revenue_conversion_daily_campaign()` - Converte revenue para campanhas
19. `trigger_new_revenue_conversion_gam()` - Converte revenue para GAM
20. `trigger_recalculate_project_revshare()` - Recalcula revshare do projeto
21. `trigger_update_project_revshare()` - Atualiza revshare do projeto
22. `trigger_update_revenue_conversions()` - Atualiza conversões de revenue
23. `trigger_update_user_commission()` - Atualiza comissão do usuário
24. `update_gam_metrics_updated_at()` - Atualiza updated_at em gam_metrics
25. `update_system_settings_updated_at()` - Atualiza updated_at em system_settings
26. `update_updated_at_column()` - Atualiza campo updated_at genérico

### Schema STORAGE

1. `delete_prefix_hierarchy_trigger()` - Remove hierarquia de prefixos
2. `enforce_bucket_name_length()` - Valida comprimento do nome do bucket
3. `objects_insert_prefix_trigger()` - Cria prefixos ao inserir objeto
4. `objects_update_level_trigger()` - Atualiza nível do objeto
5. `objects_update_prefix_trigger()` - Atualiza prefixos ao atualizar objeto
6. `prefixes_insert_trigger()` - Cria hierarquia de prefixos
7. `update_updated_at_column()` - Atualiza campo updated_at

### Schema REALTIME

1. `subscription_check_filters()` - Valida filtros de assinatura

---

## Categorização por Funcionalidade

### Gestão de Timestamps
- `trg_campaigns_updated_at`
- `trg_dcm_updated_at`
- `trigger_gam_metrics_updated_at`
- `trigger_operational_costs_updated_at`
- `update_system_settings_updated_at`
- `update_objects_updated_at`

### Conversão de Moeda
- `trigger_calculate_revenue_converted_adsense_historical`
- `trigger_calculate_revenue_converted_campaign_historical`
- `trigger_calculate_revenue_converted_daily_project_historical`
- `trigger_calculate_revenue_converted_gam_historical`
- `trigger_daily_campaign_metrics_revenue_conversion`
- `trigger_gam_metrics_revenue_conversion`
- `trigger_exchange_rate_update`
- `trigger_exchange_rate_historical`

### Cálculo de Revenue Share
- `trigger_daily_campaign_revshare_calculation`
- `trigger_project_revshare_update`
- `trigger_daily_project_metrics_insert`
- `trigger_daily_project_metrics_update`

### Cálculo de Comissões
- `trigger_daily_campaign_commission_calculation`
- `trigger_user_commission_update`

### Sincronização de Dados
- `sync_revenue_to_daily_metrics`
- `trigger_adsense_metrics_change`
- `trigger_funnel_url_change`
- `trigger_campaign_funnel_urls_revenue_calculation`
- `trigger_sync_status_insert`
- `trigger_sync_status_update`

### Normalização e Limpeza de Dados
- `trigger_clean_funnel_url`
- `trigger_normalize_url_projeto`
- `trigger_auto_populate_adsense_metrics`
- `populate_project_id_gam`

### Gestão de Storage
- `enforce_bucket_name_length_trigger`
- `objects_insert_create_prefix`
- `objects_update_create_prefix`
- `objects_delete_delete_prefix`
- `prefixes_create_hierarchy`
- `prefixes_delete_hierarchy`

### Validação
- `tr_check_filters`

### Event Triggers (Sistema)
- `issue_graphql_placeholder`
- `issue_pg_cron_access`
- `issue_pg_graphql_access`
- `issue_pg_net_access`
- `pgrst_ddl_watch`
- `pgrst_drop_watch`

---

## Observações Importantes

1. **Triggers Históricos:** Vários triggers foram substituídos por versões que usam sistema histórico de taxas de câmbio (`*_historical`)

2. **Dependências:** Muitos triggers dependem de funções auxiliares e tabelas de configuração (ex: `system_settings` para taxa de câmbio)

3. **Performance:** Triggers que fazem UPDATEs em outras tabelas podem impactar performance em grandes volumes de dados

4. **Integridade:** Triggers de sincronização garantem consistência entre tabelas relacionadas (GAM, AdSense, Campaigns)

5. **Event Triggers:** Os event triggers são específicos do Supabase e gerenciam permissões e extensões automaticamente

---

## Notas de Manutenção

- Ao modificar triggers relacionados a revenue/conversão, verificar impacto em todos os cálculos dependentes
- Triggers de storage são críticos para manutenção da hierarquia de prefixos
- Triggers de sincronização podem causar loops se não forem cuidadosamente implementados
- Sempre testar triggers em ambiente de desenvolvimento antes de produção
