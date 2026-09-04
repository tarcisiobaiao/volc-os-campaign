# Inventário de higiene do repositório

Gerado em `2026-09-04T16:10:02-03:00` por `scripts/auditar_repositorio.py`.

> Este relatório organiza evidências. Ele não declara arquivos mortos automaticamente.

## Resumo

- 645 arquivos: 471 Markdown e 174 SQL;
- 640 versionados e 5 ainda não versionados;
- 1 grupos de duplicatas exatas;
- 113 SQL com palavras de mutação de alto risco.

## Classificações

| Classe | Arquivos |
|---|---:|
| `archived` | 33 |
| `audit` | 23 |
| `documentation` | 323 |
| `generated` | 2 |
| `module-guide` | 36 |
| `product-document` | 23 |
| `project-control` | 4 |
| `reference` | 12 |
| `runtime-contract` | 20 |
| `sql-diagnostic` | 5 |
| `sql-migration-line` | 41 |
| `sql-needs-lineage` | 50 |
| `sql-needs-review` | 61 |
| `sql-validation` | 12 |

## Duplicatas exatas

- `funnelforge-migracao/docs/engine-hardening-2026-08-11.md` ↔ `funnelforge-migracao/engine/docs/engine-hardening-2026-08-11.md`

## SQL de alto risco

Arquivos abaixo contêm `DELETE`, `DROP` ou `TRUNCATE`. Isso não prova que
estejam errados, mas impede aplicação automática.

| Path | Classe | Nós no grafo | Grau |
|---|---|---:|---:|
| `scripts/provar-google-inteligencia-v12_03.sql` | `sql-needs-review` | 6 | 12 |
| `scripts/provas-papeis-v11_03.sql` | `sql-needs-review` | 7 | 12 |
| `scripts/provas-v11_03.sql` | `sql-needs-review` | 4 | 6 |
| `scripts/provas-v12_02.sql` | `sql-needs-review` | 3 | 4 |
| `scripts/provas-v12_04.sql` | `sql-needs-review` | 6 | 12 |
| `sql/2025-09-10_drop_costs_summary_by_category.sql` | `sql-needs-review` | 1 | 0 |
| `sql/add_user_campaigns.sql` | `sql-needs-review` | 2 | 7 |
| `sql/archive/campaign-highlights/APLICAR_NO_SUPABASE.sql` | `archived` | 0 | 0 |
| `sql/archive/campaign-highlights/test_rotacao.sql` | `archived` | 0 | 0 |
| `sql/archive/incidents/eleicoes-org/fix_eleicoes_project.sql` | `archived` | 0 | 0 |
| `sql/archive/one-off/operator-commission-role-fix.sql` | `archived` | 0 | 0 |
| `sql/debug_marliseac.sql` | `sql-diagnostic` | 1 | 0 |
| `sql/fix_user_campaigns_campaign_id.sql` | `sql-needs-review` | 1 | 0 |
| `sql/fix_user_campaigns_reference.sql` | `sql-needs-review` | 1 | 0 |
| `sql/recreate_marliseac.sql` | `sql-needs-review` | 1 | 0 |
| `sql/reset_senha_alternativo.sql` | `sql-needs-review` | 1 | 0 |
| `src/sql/add_commission_operator_automation.sql` | `sql-needs-lineage` | 8 | 18 |
| `src/sql/add_gam_metrics_columns.sql` | `sql-needs-lineage` | 4 | 8 |
| `src/sql/add_revenue_converted_column.sql` | `sql-needs-lineage` | 10 | 27 |
| `src/sql/add_revshare_automation.sql` | `sql-needs-lineage` | 10 | 33 |
| `src/sql/adsense_funnel_aggregation.sql` | `sql-needs-lineage` | 6 | 18 |
| `src/sql/auto_create_projects_trigger.sql` | `sql-needs-lineage` | 4 | 8 |
| `src/sql/create_project_cost_sharing_table.sql` | `sql-needs-lineage` | 5 | 14 |
| `src/sql/fix_campaigns_aggregated_pagination.sql` | `sql-needs-lineage` | 2 | 2 |
| `src/sql/fix_campaigns_revenue_revshare.sql` | `sql-needs-lineage` | 3 | 8 |
| `src/sql/fix_commission_role_and_recalculate.sql` | `sql-needs-lineage` | 3 | 4 |
| `src/sql/fix_tax_history_table.sql` | `sql-needs-lineage` | 2 | 2 |
| `src/sql/get_rotated_campaign_highlights.sql` | `sql-needs-lineage` | 2 | 6 |
| `src/sql/get_rotated_campaign_highlights_FINAL.sql` | `sql-needs-lineage` | 3 | 10 |
| `src/sql/get_rotated_campaign_highlights_WORKING.sql` | `sql-needs-lineage` | 3 | 10 |
| `src/sql/get_rotated_campaign_highlights_read_only.sql` | `sql-needs-lineage` | 2 | 6 |
| `src/sql/get_rotated_campaign_highlights_simple.sql` | `sql-needs-lineage` | 3 | 8 |
| `src/sql/get_rotated_campaign_highlights_v2.sql` | `sql-needs-lineage` | 3 | 10 |
| `src/sql/joinads/01_joinads_metrics.sql` | `sql-migration-line` | 4 | 7 |
| `src/sql/joinads/03_limpa_ingestao_ruim.sql` | `sql-migration-line` | 1 | 0 |
| `src/sql/merge_duplicate_projects_www.sql` | `sql-needs-lineage` | 3 | 6 |
| `src/sql/merge_projects_complete.sql` | `sql-needs-lineage` | 2 | 2 |
| `src/sql/merge_projects_final.sql` | `sql-needs-lineage` | 2 | 2 |
| `src/sql/merge_projects_fix.sql` | `sql-needs-lineage` | 2 | 2 |
| `src/sql/pautador/02_publicacao_por_projeto.sql` | `sql-migration-line` | 1 | 0 |
| `src/sql/pautador/03_perfil_enxuto.sql` | `sql-migration-line` | 1 | 0 |
| `src/sql/pautador/05_campanha_aponta_para_o_run.sql` | `sql-migration-line` | 1 | 0 |
| `src/sql/production-maintenance.sql` | `sql-needs-lineage` | 1 | 0 |
| `src/sql/refresh_campaign_highlights.sql` | `sql-needs-lineage` | 2 | 28 |
| `src/sql/refresh_campaign_highlights_v3.sql` | `sql-needs-lineage` | 2 | 16 |
| `src/sql/restructure_daily_project_metrics.sql` | `sql-needs-lineage` | 8 | 26 |
| `src/sql/rollback_sync_status.sql` | `sql-needs-lineage` | 1 | 0 |
| `src/sql/setup_users_rls_policies.sql` | `sql-needs-lineage` | 1 | 0 |
| `src/sql/sync_status_from_google_ads.sql` | `sql-needs-lineage` | 4 | 10 |
| `src/sql/test_auto_create_projects.sql` | `sql-validation` | 1 | 0 |
| `src/sql/test_daily_project_metrics.sql` | `sql-validation` | 1 | 0 |
| `src/sql/test_sync_status.sql` | `sql-validation` | 1 | 0 |
| `src/sql/timezone-trigger.sql` | `sql-needs-lineage` | 6 | 18 |
| `src/sql/update_user_roles_remove_viewer.sql` | `sql-needs-lineage` | 1 | 0 |
| `src/sql/v6_02_create_campaign_members.sql` | `sql-migration-line` | 2 | 6 |
| `src/sql/v6_03_create_campaign_commissions.sql` | `sql-migration-line` | 2 | 5 |
| `src/sql/v6_04_create_daily_campaign_member_payouts.sql` | `sql-migration-line` | 2 | 5 |
| `src/sql/v6_08_backfill_campaign_members.sql` | `sql-migration-line` | 1 | 0 |
| `src/sql/v6_09_backfill_campaign_commissions.sql` | `sql-migration-line` | 1 | 0 |
| `src/sql/v6_10_populate_payouts_full_history.sql` | `sql-migration-line` | 1 | 0 |
| `src/sql/v7_01_create_pautador_tables.sql` | `sql-migration-line` | 13 | 47 |
| `src/sql/v7_03_pautador_entities.sql` | `sql-migration-line` | 9 | 38 |
| `src/sql/v7_05_pautador_entity_extras.sql` | `sql-migration-line` | 1 | 0 |
| `src/sql/v7_08_pautador_cluster_fk_fix.sql` | `sql-migration-line` | 1 | 0 |
| `src/sql/v7_11_pautador_niches.sql` | `sql-migration-line` | 3 | 5 |
| `src/sql/v7_13_meta_capi_sites.sql` | `sql-migration-line` | 4 | 8 |
| `src/sql/v7_17_pautador_question_choice.sql` | `sql-migration-line` | 3 | 11 |
| `src/sql/volc-sync/01_incubator_tables.sql` | `sql-migration-line` | 8 | 24 |
| `src/sql/volc-sync/02_incubator_functions.sql` | `sql-migration-line` | 4 | 10 |
| `src/sql/volc-sync/03_display_roi.sql` | `sql-migration-line` | 4 | 11 |
| `src/sql/volc-sync/04_monthly_exchange_rate.BLOQUEADO.sql` | `sql-migration-line` | 6 | 10 |
| `src/sql/volc-sync/APLICAR_NO_STUDIO.sql` | `sql-migration-line` | 14 | 49 |
| `supabase/migrations/20260904183418_meta_create_paused_executor.sql` | `sql-needs-review` | 9 | 19 |
| `supabase/migrations/20260904183514_meta_create_paused_executor_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v10_01_intencao_e_lote.sql` | `sql-needs-review` | 37 | 131 |
| `supabase/migrations/v10_01_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v10_02_autogestao.sql` | `sql-needs-review` | 33 | 126 |
| `supabase/migrations/v10_02_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v10_03_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v11_01_estudio_criativo.sql` | `sql-needs-review` | 18 | 71 |
| `supabase/migrations/v11_01_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v11_02_parque_criativo.sql` | `sql-needs-review` | 17 | 48 |
| `supabase/migrations/v11_02_rollback.sql` | `sql-needs-review` | 2 | 3 |
| `supabase/migrations/v11_03_execucao_criativa.sql` | `sql-needs-review` | 18 | 55 |
| `supabase/migrations/v11_03_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v12_01_google_inteligencia_coletas.sql` | `sql-needs-review` | 3 | 4 |
| `supabase/migrations/v12_01_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v12_02_plano_de_mensuracao.sql` | `sql-needs-review` | 5 | 23 |
| `supabase/migrations/v12_02_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v12_03_pmax_observability_ledger.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v12_03_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v12_04_gads_fato_canonico_dia.sql` | `sql-needs-review` | 9 | 29 |
| `supabase/migrations/v12_04_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v13_01_cofre_de_ativos.sql` | `sql-needs-review` | 41 | 126 |
| `supabase/migrations/v13_02_cofre_recusa_sem_vazar_linha.sql` | `sql-needs-review` | 2 | 4 |
| `supabase/migrations/v13_99_cofre_de_ativos_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v14_01_publicacao_organica.sql` | `sql-needs-review` | 30 | 114 |
| `supabase/migrations/v14_99_publicacao_organica_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v15_01_meta_ads_read_model.sql` | `sql-needs-review` | 8 | 25 |
| `supabase/migrations/v15_02_meta_ads_insights.sql` | `sql-needs-review` | 5 | 13 |
| `supabase/migrations/v15_98_meta_ads_insights_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v15_99_meta_ads_read_model_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v8_01_app_auth_schema_and_roles.sql` | `sql-needs-review` | 12 | 34 |
| `supabase/migrations/v8_02_pautador_policies_rewire.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v8_03_users_rls_policies.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v8_04_users_grants.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v8_05_users_safe_view.sql` | `sql-needs-review` | 2 | 3 |
| `supabase/migrations/v8_07_default_privileges_hardening.OPCIONAL.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v8_99_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v9_01_trafego_inventario.sql` | `sql-needs-review` | 11 | 33 |
| `supabase/migrations/v9_03_historico_e_ordem_operacional.sql` | `sql-needs-review` | 2 | 6 |
| `supabase/migrations/v9_03_rollback.sql` | `sql-needs-review` | 2 | 6 |
| `supabase/migrations/v9_99_trafego_inventario_rollback.sql` | `sql-needs-review` | 1 | 0 |

## Fila da próxima onda

| Path | Classe | Risco SQL | Nós no grafo | Grau |
|---|---|---|---:|---:|
| `backend/app/motor_pautas/AUDITORIA-EXTERNA.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-DNA-R2.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-DNA-R3.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-DNA-R4-FECHAMENTO.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-DNA.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-R5-ROTEADOR.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-R6-BUG.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/REVISAO-CODEX.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/REVISAO-EXTERNA.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/AUDITORIA-EXTERNA.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/AUDITORIA-GEMINI-DNA-R2.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/AUDITORIA-GEMINI-DNA-R3.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/AUDITORIA-GEMINI-DNA-R4-FECHAMENTO.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/AUDITORIA-GEMINI-DNA.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/AUDITORIA-GEMINI-R5-ROTEADOR.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/AUDITORIA-GEMINI-R6-BUG.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/README.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/REVISAO-CODEX.md` | `audit` | — | 0 | 0 |
| `docs/audits/motor-pautas/REVISAO-EXTERNA.md` | `audit` | — | 0 | 0 |
| `docs/closure/asset-vault-onepassword-production-v1/REVISAO-ADVERSARIAL.md` | `audit` | — | 0 | 0 |
| `docs/closure/hermes-p10-t16-n8n-ledger-v12-v1/REVISAO-FOCAL.md` | `audit` | — | 0 | 0 |
| `docs/closure/traffic-creative-operational-closure-v1/verificacao/REVISAO-CODEX-CRIATIVO.md` | `audit` | — | 0 | 0 |
| `docs/closure/traffic-creative-operational-closure-v1/verificacao/REVISAO-GEMINI-CONTRATOS.md` | `audit` | — | 0 | 0 |
| `scripts/provar-google-inteligencia-v12_03.sql` | `sql-needs-review` | high | 6 | 12 |
| `scripts/provas-papeis-v11_03.sql` | `sql-needs-review` | high | 7 | 12 |
| `scripts/provas-v11_03.sql` | `sql-needs-review` | high | 4 | 6 |
| `scripts/provas-v12_02.sql` | `sql-needs-review` | high | 3 | 4 |
| `scripts/provas-v12_04.sql` | `sql-needs-review` | high | 6 | 12 |
| `sql/2025-09-10_drop_costs_summary_by_category.sql` | `sql-needs-review` | high | 1 | 0 |
| `sql/add_user_campaigns.sql` | `sql-needs-review` | high | 2 | 7 |
| `sql/fix_marliseac_password_final.sql` | `sql-needs-review` | medium | 1 | 0 |
| `sql/fix_user_campaigns_campaign_id.sql` | `sql-needs-review` | high | 1 | 0 |
| `sql/fix_user_campaigns_reference.sql` | `sql-needs-review` | high | 1 | 0 |
| `sql/recreate_marliseac.sql` | `sql-needs-review` | high | 1 | 0 |
| `sql/reset_marliseac_password.sql` | `sql-needs-review` | medium | 1 | 0 |
| `sql/reset_senha_alternativo.sql` | `sql-needs-review` | high | 1 | 0 |
| `src/sql/add_commission_operator_automation.sql` | `sql-needs-lineage` | high | 8 | 18 |
| `src/sql/add_costs_division_column.sql` | `sql-needs-lineage` | medium | 1 | 0 |
| `src/sql/add_gam_metrics_columns.sql` | `sql-needs-lineage` | high | 4 | 8 |
| `src/sql/add_needs_password_change_column.sql` | `sql-needs-lineage` | medium | 1 | 0 |
| `src/sql/add_revenue_converted_column.sql` | `sql-needs-lineage` | high | 10 | 27 |
| `src/sql/add_revshare_automation.sql` | `sql-needs-lineage` | high | 10 | 33 |
| `src/sql/adsense_funnel_aggregation.sql` | `sql-needs-lineage` | high | 6 | 18 |
| `src/sql/analysis_campaign_pool.sql` | `sql-needs-lineage` | read-only-or-ddl-free | 1 | 0 |
| `src/sql/auto_create_projects_trigger.sql` | `sql-needs-lineage` | high | 4 | 8 |
| `src/sql/check_existing_triggers.sql` | `sql-needs-lineage` | read-only-or-ddl-free | 1 | 0 |
| `src/sql/create_campaign_highlights_table.sql` | `sql-needs-lineage` | read-only-or-ddl-free | 2 | 10 |
| `src/sql/create_project_cost_sharing_table.sql` | `sql-needs-lineage` | high | 5 | 14 |
| `src/sql/cron_campaign_highlights.sql` | `sql-needs-lineage` | medium | 2 | 2 |
| `src/sql/cron_campaign_highlights_fixed.sql` | `sql-needs-lineage` | read-only-or-ddl-free | 1 | 0 |
| `src/sql/fix_campaigns_aggregated_pagination.sql` | `sql-needs-lineage` | high | 2 | 2 |
| `src/sql/fix_campaigns_revenue_revshare.sql` | `sql-needs-lineage` | high | 3 | 8 |
| `src/sql/fix_commission_role_and_recalculate.sql` | `sql-needs-lineage` | high | 3 | 4 |
| `src/sql/fix_tax_history_table.sql` | `sql-needs-lineage` | high | 2 | 2 |
| `src/sql/force_recalculate_commissions_today.sql` | `sql-needs-lineage` | medium | 1 | 0 |
| `src/sql/get_placement_negation_suggestions.sql` | `sql-needs-lineage` | medium | 2 | 3 |
| `src/sql/get_rotated_campaign_highlights.sql` | `sql-needs-lineage` | high | 2 | 6 |
| `src/sql/get_rotated_campaign_highlights_FINAL.sql` | `sql-needs-lineage` | high | 3 | 10 |
| `src/sql/get_rotated_campaign_highlights_WORKING.sql` | `sql-needs-lineage` | high | 3 | 10 |
| `src/sql/get_rotated_campaign_highlights_read_only.sql` | `sql-needs-lineage` | high | 2 | 6 |
| `src/sql/get_rotated_campaign_highlights_simple.sql` | `sql-needs-lineage` | high | 3 | 8 |
| `src/sql/get_rotated_campaign_highlights_v2.sql` | `sql-needs-lineage` | high | 3 | 10 |
| `src/sql/merge_duplicate_projects_www.sql` | `sql-needs-lineage` | high | 3 | 6 |
| `src/sql/merge_projects_complete.sql` | `sql-needs-lineage` | high | 2 | 2 |
| `src/sql/merge_projects_final.sql` | `sql-needs-lineage` | high | 2 | 2 |
| `src/sql/merge_projects_fix.sql` | `sql-needs-lineage` | high | 2 | 2 |
| `src/sql/n8n_insert_examples.sql` | `sql-needs-lineage` | medium | 1 | 0 |
| `src/sql/operational_costs_real_structure.sql` | `sql-needs-lineage` | medium | 1 | 0 |
| `src/sql/production-maintenance.sql` | `sql-needs-lineage` | high | 1 | 0 |
| `src/sql/refresh_campaign_highlights.sql` | `sql-needs-lineage` | high | 2 | 28 |
| `src/sql/refresh_campaign_highlights_v3.sql` | `sql-needs-lineage` | high | 2 | 16 |
| `src/sql/restructure_daily_project_metrics.sql` | `sql-needs-lineage` | high | 8 | 26 |
| `src/sql/rollback_sync_status.sql` | `sql-needs-lineage` | high | 1 | 0 |
| `src/sql/rpc_get_campaign_detailed_metrics.sql` | `sql-needs-lineage` | medium | 2 | 3 |
| `src/sql/rpc_get_daily_metrics_aggregated.sql` | `sql-needs-lineage` | medium | 2 | 6 |
| `src/sql/rpc_get_dashboard_totals.sql` | `sql-needs-lineage` | medium | 2 | 7 |
| `src/sql/rpc_get_operational_costs_aggregated.sql` | `sql-needs-lineage` | medium | 2 | 3 |
| `src/sql/rpc_get_period_comparison.sql` | `sql-needs-lineage` | medium | 2 | 6 |
| `src/sql/rpc_get_projects_summary.sql` | `sql-needs-lineage` | medium | 2 | 7 |
| `src/sql/rpc_get_top_campaigns_by_revenue.sql` | `sql-needs-lineage` | medium | 2 | 3 |
| `src/sql/setup_users_rls_policies.sql` | `sql-needs-lineage` | high | 1 | 0 |
| `src/sql/sync_status_from_google_ads.sql` | `sql-needs-lineage` | high | 4 | 10 |
| `src/sql/system-settings-timestamps.sql` | `sql-needs-lineage` | medium | 4 | 10 |
| `src/sql/timezone-trigger.sql` | `sql-needs-lineage` | high | 6 | 18 |
| `src/sql/update_sync_gam_function.sql` | `sql-needs-lineage` | medium | 2 | 2 |
| `src/sql/update_user_roles_remove_viewer.sql` | `sql-needs-lineage` | high | 1 | 0 |
| `supabase/migrations/20260904183418_meta_create_paused_executor.sql` | `sql-needs-review` | high | 9 | 19 |
| `supabase/migrations/20260904183514_meta_create_paused_executor_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v10_01_intencao_e_lote.sql` | `sql-needs-review` | high | 37 | 131 |
| `supabase/migrations/v10_01_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v10_02_autogestao.sql` | `sql-needs-review` | high | 33 | 126 |
| `supabase/migrations/v10_02_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v10_03_recibo_atomico.sql` | `sql-needs-review` | medium | 9 | 28 |
| `supabase/migrations/v10_03_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v10_04_rollback.sql` | `sql-needs-review` | medium | 3 | 5 |
| `supabase/migrations/v10_04_saida_do_indeterminado.sql` | `sql-needs-review` | medium | 3 | 6 |
| `supabase/migrations/v11_01_estudio_criativo.sql` | `sql-needs-review` | high | 18 | 71 |
| `supabase/migrations/v11_01_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v11_02_parque_criativo.sql` | `sql-needs-review` | high | 17 | 48 |
| `supabase/migrations/v11_02_rollback.sql` | `sql-needs-review` | high | 2 | 3 |
| `supabase/migrations/v11_03_execucao_criativa.sql` | `sql-needs-review` | high | 18 | 55 |
| `supabase/migrations/v11_03_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v12_01_google_inteligencia_coletas.sql` | `sql-needs-review` | high | 3 | 4 |
| `supabase/migrations/v12_01_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v12_02_plano_de_mensuracao.sql` | `sql-needs-review` | high | 5 | 23 |
| `supabase/migrations/v12_02_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v12_03_pmax_observability_ledger.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v12_03_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v12_04_gads_fato_canonico_dia.sql` | `sql-needs-review` | high | 9 | 29 |
| `supabase/migrations/v12_04_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v13_01_cofre_de_ativos.sql` | `sql-needs-review` | high | 41 | 126 |
| `supabase/migrations/v13_02_cofre_recusa_sem_vazar_linha.sql` | `sql-needs-review` | high | 2 | 4 |
| `supabase/migrations/v13_99_cofre_de_ativos_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v14_01_publicacao_organica.sql` | `sql-needs-review` | high | 30 | 114 |
| `supabase/migrations/v14_99_publicacao_organica_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v15_01_meta_ads_read_model.sql` | `sql-needs-review` | high | 8 | 25 |
| `supabase/migrations/v15_02_meta_ads_insights.sql` | `sql-needs-review` | high | 5 | 13 |
| `supabase/migrations/v15_98_meta_ads_insights_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v15_99_meta_ads_read_model_rollback.sql` | `sql-needs-review` | high | 1 | 0 |
| `supabase/migrations/v8_01_app_auth_schema_and_roles.sql` | `sql-needs-review` | high | 12 | 34 |

O inventário completo e legível por máquina está em
`docs/architecture/repository-inventory.json`.
