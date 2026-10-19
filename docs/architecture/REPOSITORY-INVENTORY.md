# Inventário de higiene do repositório

Gerado em `2026-10-19T07:53:00-03:00` por `scripts/auditar_repositorio.py`.

> Este relatório organiza evidências. Ele não declara arquivos mortos automaticamente.

## Resumo

- 1046 arquivos: 737 Markdown e 309 SQL;
- 1046 versionados e 0 ainda não versionados;
- 1 grupos de duplicatas exatas;
- 184 SQL com palavras de mutação de alto risco.

## Classificações

| Classe | Arquivos |
|---|---:|
| `archived` | 33 |
| `audit` | 58 |
| `documentation` | 543 |
| `generated` | 2 |
| `module-guide` | 47 |
| `product-document` | 23 |
| `project-control` | 4 |
| `reference` | 12 |
| `runtime-contract` | 20 |
| `sql-diagnostic` | 5 |
| `sql-migration-line` | 42 |
| `sql-needs-lineage` | 50 |
| `sql-needs-review` | 193 |
| `sql-validation` | 14 |

## Duplicatas exatas

- `funnelforge-migracao/docs/engine-hardening-2026-08-11.md` ↔ `funnelforge-migracao/engine/docs/engine-hardening-2026-08-11.md`

## SQL de alto risco

Arquivos abaixo contêm `DELETE`, `DROP` ou `TRUNCATE`. Isso não prova que
estejam errados, mas impede aplicação automática.

| Path | Classe | Nós no grafo | Grau |
|---|---|---:|---:|
| `docs/closure/traffic-operational-closure-v2/ler-catalogo-meta.sql` | `sql-needs-review` | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0001_schema_observacao.down.sql` | `sql-needs-review` | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0001_schema_observacao.sql` | `sql-needs-review` | 19 | 40 |
| `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0002_observacao_particionada.OPCIONAL.down.sql` | `sql-needs-review` | 2 | 2 |
| `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0002_observacao_particionada.OPCIONAL.sql` | `sql-needs-review` | 3 | 4 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_0001_google_ads_run_abandoned.down.sql` | `sql-needs-review` | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_0001_google_ads_run_abandoned.sql` | `sql-needs-review` | 3 | 4 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_0002_cotacao_usd_brl.down.sql` | `sql-needs-review` | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_0002_cotacao_usd_brl.sql` | `sql-needs-review` | 7 | 14 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_base_producao_reconstruida.sql` | `sql-needs-review` | 5 | 12 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/base_real/20261015163704_joinads_collection_canonical.sql` | `sql-needs-review` | 4 | 6 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/base_real/v21_01_google_ads_coleta_canonica.sql` | `sql-needs-review` | 3 | 4 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/dq_01_views_qualidade.down.sql` | `sql-needs-review` | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/dq_02_views_dil_obs.down.sql` | `sql-needs-review` | 1 | 0 |
| `scripts/preflight-incidente-anon-w4.sql` | `sql-needs-review` | 1 | 0 |
| `scripts/provar-google-inteligencia-v12_03.sql` | `sql-needs-review` | 6 | 12 |
| `scripts/provas-papeis-v11_03.sql` | `sql-needs-review` | 7 | 12 |
| `scripts/provas-v11_03.sql` | `sql-needs-review` | 4 | 6 |
| `scripts/provas-v12_02.sql` | `sql-needs-review` | 3 | 4 |
| `scripts/provas-v12_04.sql` | `sql-needs-review` | 6 | 12 |
| `scripts/verificar-anon-w4.sql` | `sql-needs-review` | 1 | 0 |
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
| `src/sql/add_commission_operator_automation.sql` | `sql-needs-lineage` | 8 | 16 |
| `src/sql/add_gam_metrics_columns.sql` | `sql-needs-lineage` | 4 | 8 |
| `src/sql/add_revenue_converted_column.sql` | `sql-needs-lineage` | 10 | 27 |
| `src/sql/add_revshare_automation.sql` | `sql-needs-lineage` | 10 | 33 |
| `src/sql/adsense_funnel_aggregation.sql` | `sql-needs-lineage` | 6 | 18 |
| `src/sql/auto_create_projects_trigger.sql` | `sql-needs-lineage` | 4 | 8 |
| `src/sql/create_project_cost_sharing_table.sql` | `sql-needs-lineage` | 5 | 14 |
| `src/sql/fix_campaigns_aggregated_pagination.sql` | `sql-needs-lineage` | 2 | 3 |
| `src/sql/fix_campaigns_revenue_revshare.sql` | `sql-needs-lineage` | 3 | 7 |
| `src/sql/fix_commission_role_and_recalculate.sql` | `sql-needs-lineage` | 3 | 6 |
| `src/sql/fix_tax_history_table.sql` | `sql-needs-lineage` | 2 | 2 |
| `src/sql/get_rotated_campaign_highlights.sql` | `sql-needs-lineage` | 2 | 7 |
| `src/sql/get_rotated_campaign_highlights_FINAL.sql` | `sql-needs-lineage` | 3 | 10 |
| `src/sql/get_rotated_campaign_highlights_WORKING.sql` | `sql-needs-lineage` | 3 | 10 |
| `src/sql/get_rotated_campaign_highlights_read_only.sql` | `sql-needs-lineage` | 2 | 5 |
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
| `src/sql/pautador/06_run_editorial_v2.sql` | `sql-migration-line` | 1 | 0 |
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
| `supabase/migrations/20260904183418_meta_create_paused_executor.sql` | `sql-needs-review` | 15 | 34 |
| `supabase/migrations/20260904183514_meta_create_paused_executor_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/20260907120000_meta_recovery_snapshot.sql` | `sql-needs-review` | 6 | 10 |
| `supabase/migrations/20260907120100_meta_recovery_snapshot_rollback.sql` | `sql-needs-review` | 4 | 6 |
| `supabase/migrations/20260907190000_meta_worker_fencing.sql` | `sql-needs-review` | 13 | 24 |
| `supabase/migrations/20260907190100_meta_worker_fencing_rollback.sql` | `sql-needs-review` | 10 | 19 |
| `supabase/migrations/20260907210000_meta_read_model_consistency.sql` | `sql-needs-review` | 5 | 15 |
| `supabase/migrations/20260907210100_meta_read_model_consistency_rollback.sql` | `sql-needs-review` | 2 | 3 |
| `supabase/migrations/20260908000000_meta_insights_escopo.sql` | `sql-needs-review` | 2 | 8 |
| `supabase/migrations/20260908020100_meta_asset_registration_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/20260908120000_meta_financeiro_conjunto_dia.sql` | `sql-needs-review` | 4 | 15 |
| `supabase/migrations/20260908120100_meta_financeiro_conjunto_dia_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/20260908205124_creative_reuse_packs.sql` | `sql-needs-review` | 3 | 5 |
| `supabase/migrations/20260908224044_meta_reference_visual.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/20260908230430_meta_creative_draft_pack_selection.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/20260908234824_meta_v2_approval_budget_manifest.sql` | `sql-needs-review` | 8 | 14 |
| `supabase/migrations/20260909073845_meta_draft_archive.sql` | `sql-needs-review` | 8 | 15 |
| `supabase/migrations/20260909215941_creative_pack_append_revisions.sql` | `sql-needs-review` | 6 | 12 |
| `supabase/migrations/20260909234342_creative_generation_versions.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/20260910143000_gam_attribution_grain_router.sql` | `sql-needs-review` | 5 | 20 |
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
| `supabase/migrations/v11_04_criativo_importacao.sql` | `sql-needs-review` | 3 | 8 |
| `supabase/migrations/v11_05_criativo_agente_meta.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v11_05_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v11_06_criativo_agente_endurecimento.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v11_06_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v11_07_criativo_agente_ponte_estudio.sql` | `sql-needs-review` | 2 | 3 |
| `supabase/migrations/v11_07_rollback.sql` | `sql-needs-review` | 1 | 0 |
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
| `supabase/migrations/v16_01_criativo_procedencia_e_anexo.sql` | `sql-needs-review` | 4 | 8 |
| `supabase/migrations/v16_01_rollback.sql` | `sql-needs-review` | 2 | 2 |
| `supabase/migrations/v17_01_gads_fatos_granulares.sql` | `sql-needs-review` | 8 | 16 |
| `supabase/migrations/v17_01_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v17_02_autonomia_gestao.PROPOSTA.sql` | `sql-needs-review` | 5 | 11 |
| `supabase/migrations/v17_03_rollback.sql` | `sql-needs-review` | 3 | 8 |
| `supabase/migrations/v17_04_arbitragem_reconciliada.sql` | `sql-needs-review` | 4 | 14 |
| `supabase/migrations/v17_04_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v18_01_identidade_leitura_minima.PROPOSTA.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v18_01_identidade_leitura_minima_rollback.PROPOSTA.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v19_01_anon_fecha_public.sql` | `sql-needs-review` | 2 | 2 |
| `supabase/migrations/v19_02_default_acl_public_sem_anon.sql` | `sql-needs-review` | 2 | 2 |
| `supabase/migrations/v19_10_authenticated_minimo.sql` | `sql-needs-review` | 15 | 39 |
| `supabase/migrations/v19_10_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v19_99_rollback.sql` | `sql-needs-review` | 2 | 2 |
| `supabase/migrations/v20_01_ledger_migrations.sql` | `sql-needs-review` | 4 | 16 |
| `supabase/migrations/v20_01_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v20_02_pos_v19_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v20_02_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v21_01_meta_capi_sites_privilegios.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v21_01_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v21_02_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v21_02_v6_rbac_privilegios.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v21_pacote_aplicar.sql` | `sql-needs-review` | 12 | 40 |
| `supabase/migrations/v21_pacote_reverter.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v23_01_receita_datada_cambio.sql` | `sql-needs-review` | 18 | 51 |
| `supabase/migrations/v23_01_rollback.sql` | `sql-needs-review` | 1 | 0 |
| `supabase/migrations/v25_01_conversao_offline_ledger.sql` | `sql-needs-review` | 14 | 48 |
| `supabase/migrations/v25_01_rollback.sql` | `sql-needs-review` | 1 | 0 |
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
| `tools/freedom-lab/db/sonda_acesso.sql` | `sql-needs-review` | 1 | 0 |
| `tools/freedom-lab/db/suites/v19_10_apoio.sql` | `sql-needs-review` | 4 | 11 |

## Fila da próxima onda

| Path | Classe | Risco SQL | Nós no grafo | Grau |
|---|---|---|---:|---:|
| `.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-B-economia/AUDITORIA-DADOS.md` | `audit` | — | 0 | 0 |
| `.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-C-dados/queries/assets-extraidas.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-C-dados/queries/negativas-extraidas.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-C-dados/queries/placements-extraidas.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-C-dados/queries/policy-extraidas.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-C-dados/queries/propostas-delta-volc.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `.claude-ads/runs/google-engine-nucleo-20261014-01/pesquisa-C-dados/queries/qs-extraidas.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `backend/app/motor_pautas/AUDITORIA-EXTERNA.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-DNA-R2.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-DNA-R3.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-DNA-R4-FECHAMENTO.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-DNA.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-R5-ROTEADOR.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/AUDITORIA-GEMINI-R6-BUG.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/REVISAO-CODEX.md` | `audit` | — | 0 | 0 |
| `backend/app/motor_pautas/REVISAO-EXTERNA.md` | `audit` | — | 0 | 0 |
| `docs/audits/ATTENTION-REPLAY-PROVA-AB-2026-10-15.md` | `audit` | — | 0 | 0 |
| `docs/audits/CAMPANHA-3-FUNIS-ACHADOS-MOTOR-2026-09-17.md` | `audit` | — | 0 | 0 |
| `docs/audits/CAMPANHA-3-FUNIS-EDUCACAO-2026-09-17.md` | `audit` | — | 0 | 0 |
| `docs/audits/CORRECAO-3-FUNIS-HANDOFF-2026-09-18.md` | `audit` | — | 0 | 0 |
| `docs/audits/CORRECAO-3-FUNIS-PREFLIGHT-2026-09-18.md` | `audit` | — | 0 | 0 |
| `docs/audits/CORRECAO-C6-E-PENDENCIAS-2026-09-18.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-ASSETS-PRE-REDACAO-2026-10-09.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-BUCKET-PESQUISA-UNICA-2026-10-10.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-COPY-NAVEGACAO-COMPOSICAO-2026-10-10.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-ENTRADAS-DO-REDATOR-2026-10-10.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-FECHAMENTO-CANARIO-EDITORIAL-2026-10-10.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-FECHAMENTO-MOTOR-2026-10-10.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-FECHAMENTO-TARIFA-SOCIAL-2026-10-10.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-JEV-ATTENTION-AB-2026-10-08.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-JEV-GEMINI-ARCHITECT-AB-2026-10-08.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-JEV-STATE-OF-ART-2026-10-08.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-LUCRO-POR-VISITA-AB-2026-10-08.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-MINERACAO-WORDPRESS-DRAFT-2026-10-09.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-OPORTUNIDADE-REAL-2026-10-09.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-PRE-REDACAO-2026-10-08.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-RECUPERACAO-MOTOR-2026-10-09.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-REVISAO-LOCALIZADA-2026-10-10.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-SEM-VETOS-MECANICOS-2026-10-10.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-VALIDACAO-REAL-CODEX-2026-10-09.md` | `audit` | — | 0 | 0 |
| `docs/audits/FUNNELFORGE-WRITER-AB-2026-10-08.md` | `audit` | — | 0 | 0 |
| `docs/audits/GOOGLE-HARNESS-GEMINI-WEBGO-2026-10-14.md` | `audit` | — | 0 | 0 |
| `docs/audits/GOOGLE-QUATRO-CANAIS-VALIDATE-ONLY-2026-10-09.md` | `audit` | — | 0 | 0 |
| `docs/audits/MODELOS-FUNIL-2026-10-07.md` | `audit` | — | 0 | 0 |
| `docs/audits/REDATOR-IDENTIDADE-EDITORIAL-2026-09-17.md` | `audit` | — | 0 | 0 |
| `docs/audits/REFINO-CONTEXTUAL-FUNIS-2026-09-18.md` | `audit` | — | 0 | 0 |
| `docs/audits/REFINO-VISUAL-AVISOS-2026-09-18.md` | `audit` | — | 0 | 0 |
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
| `docs/closure/meta-governed-create-paused-path-v1/REVISAO-ADVERSARIAL-CODEX.md` | `audit` | — | 0 | 0 |
| `docs/closure/meta-pack-reuse-20260909/verify-rollback.sql` | `sql-needs-review` | medium | 1 | 0 |
| `docs/closure/traffic-creative-operational-closure-v1/verificacao/REVISAO-CODEX-CRIATIVO.md` | `audit` | — | 0 | 0 |
| `docs/closure/traffic-creative-operational-closure-v1/verificacao/REVISAO-GEMINI-CONTRATOS.md` | `audit` | — | 0 | 0 |
| `docs/closure/traffic-operational-closure-v2/ler-catalogo-meta.sql` | `sql-needs-review` | high | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/handoffs/REVISAO-ADVERSARIAL-R1.md` | `audit` | — | 0 | 0 |
| `docs/data-intelligence/fundacao-20261016/handoffs/REVISAO-ADVERSARIAL-R2.md` | `audit` | — | 0 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/i5_cat.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/i5_fn.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/i5_fx.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/i5_fx2.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/i5_fx3.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/i5_ja.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/i5_rec.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/verificar_d1_canario.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/verificar_integridade.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/verificar_pos_cutover.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/l1.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/l10.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/l2.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/l4.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/l5.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/l5a.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/lb.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/lg_selects_qualidade.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/leituras-externas/lh_hipoteses_r1.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/rodada-autorizada-20261017/export_snapshot.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/rodada-autorizada-20261017/meta.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/rodada-autorizada-20261017/meta2.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/rodada-autorizada-20261017/re_agg.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/rodada-autorizada-20261017/re_meta.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `docs/data-intelligence/fundacao-20261016/receipts/rodada-autorizada-20261017/zstat.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0001_schema_observacao.down.sql` | `sql-needs-review` | high | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0001_schema_observacao.sql` | `sql-needs-review` | high | 19 | 40 |
| `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0002_observacao_particionada.OPCIONAL.down.sql` | `sql-needs-review` | high | 2 | 2 |
| `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0002_observacao_particionada.OPCIONAL.sql` | `sql-needs-review` | high | 3 | 4 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_0001_google_ads_run_abandoned.down.sql` | `sql-needs-review` | high | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_0001_google_ads_run_abandoned.sql` | `sql-needs-review` | high | 3 | 4 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_0002_cotacao_usd_brl.down.sql` | `sql-needs-review` | high | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_0002_cotacao_usd_brl.sql` | `sql-needs-review` | high | 7 | 14 |
| `experiments/data-intelligence-lab/migrations_candidatas/item5_base_producao_reconstruida.sql` | `sql-needs-review` | high | 5 | 12 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/base_real/00_prelude_somente_teste.sql` | `sql-needs-review` | medium | 2 | 2 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/base_real/20261015163704_joinads_collection_canonical.sql` | `sql-needs-review` | high | 4 | 6 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/base_real/v21_01_google_ads_coleta_canonica.sql` | `sql-needs-review` | high | 3 | 4 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/base_real/v21_02_google_ads_hash_no_servidor.sql` | `sql-needs-review` | medium | 2 | 2 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/base_real/v21_03_google_ads_finalizacao_run.sql` | `sql-needs-review` | medium | 3 | 4 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/dq_01_views_qualidade.down.sql` | `sql-needs-review` | high | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/dq_01_views_qualidade.sql` | `sql-needs-review` | medium | 2 | 2 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/dq_02_views_dil_obs.down.sql` | `sql-needs-review` | high | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/dq_02_views_dil_obs.sql` | `sql-needs-review` | medium | 6 | 15 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/export_recibo_somente_leitura.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `experiments/data-intelligence-lab/migrations_candidatas/views_qualidade/selects_somente_leitura.sql` | `sql-needs-review` | read-only-or-ddl-free | 1 | 0 |
| `scripts/preflight-incidente-anon-w4.sql` | `sql-needs-review` | high | 1 | 0 |
| `scripts/provar-google-inteligencia-v12_03.sql` | `sql-needs-review` | high | 6 | 12 |
| `scripts/provas-papeis-v11_03.sql` | `sql-needs-review` | high | 7 | 12 |
| `scripts/provas-v11_03.sql` | `sql-needs-review` | high | 4 | 6 |
| `scripts/provas-v12_02.sql` | `sql-needs-review` | high | 3 | 4 |
| `scripts/provas-v12_04.sql` | `sql-needs-review` | high | 6 | 12 |
| `scripts/provas-v17_01.sql` | `sql-needs-review` | medium | 3 | 4 |
| `scripts/provas-v17_04.sql` | `sql-needs-review` | medium | 1 | 0 |
| `scripts/verificar-anon-w4.sql` | `sql-needs-review` | high | 1 | 0 |

O inventário completo e legível por máquina está em
`docs/architecture/repository-inventory.json`.
