# db/suites/v19_10_authenticated_minimo.sh — suíte da v19_10 (authenticated com
# privilégio mínimo; pacote separado do incidente anon, W4). Carregada por
# lab.sh testar. Base = schema de produção de 15/10 + pacote anon aplicado:
#
#   LAB_NOME=volc-lab-w4-auth \
#   LAB_DUMP=/Users/mac/Desktop/VOLC-OS-CAMPAIGN/handoffs/freedom-lab-20261015/prod-schema-only.sql \
#   LAB_DUMP_SHA256=2c70b4a4b5c6616d54c126c2a5e2be6d13d1f29e424f1ed2660d58f39e4c833c \
#   LAB_SEMENTE=tools/freedom-lab/db/suites/v19_incidente_anon_semente.sql \
#   MIGRATION=supabase/migrations/v19_10_authenticated_minimo.sql \
#   ROLLBACK=supabase/migrations/v19_10_rollback.sql \
#   MIGRATION_SUITE=tools/freedom-lab/db/suites/v19_10_authenticated_minimo.sh \
#   tools/freedom-lab/lab.sh recriar-prod
#
# Provas:
#   1. fluxos reais do app (cada .from/.rpc alcançável do frontend, com a linha
#      no código) dão o MESMO resultado como authenticated antes e depois da
#      v19_10 — nada que funcionava passa a dar 42501;
#   2. toda escrita fora da tabela de decisão é recusada (42501) e toda relação
#      que authenticated alcança tem RLS;
#   3. rollback devolve o fingerprint exato, aborta se a ACL mudou depois, é
#      idempotente; reaplicação idêntica; anon segue FECHADO o tempo todo.
W4_MIG="$RAIZ/supabase/migrations"; R="$RECIBOS"
ADMIN='{"sub":"a0000000-0000-4000-8000-00000000000a","email":"admin@example.invalid","role":"authenticated"}'
fp() { P -f - < "$FP" 2>&1 | grep '|' | tr -d ' ' > "$1"; }
aplicar() { local cmd=PA; [ "$1" = postgres ] && cmd=P
  if $cmd -f - < "$W4_MIG/$2" > "$R/aplicar-$2.log" 2>&1; then registrar "$W4_MIG/$2" "$1" ok; return 0
  else registrar "$W4_MIG/$2" "$1" falhou; tail -5 "$R/aplicar-$2.log"; return 1; fi; }
anon_fechado() { # mesma verificação do script de aplicação do pacote anon
  docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$NOME" psql -U postgres -d postgres -X -q -A -t -F'|' \
    < "$RAIZ/scripts/verificar-anon-w4.sql" 2>&1 | awk -F'|' '$1~/V[1234]/ && $3!=0 {a=1} END {print (a?"ABERTO":"FECHADO")}'; }

PA -c "CREATE SCHEMA IF NOT EXISTS volc_lab; CREATE TABLE IF NOT EXISTS volc_lab.migracao_aplicada (
  arquivo text NOT NULL, sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  aplicada_em timestamptz NOT NULL DEFAULT now(), base text NOT NULL, resultado text NOT NULL);
  GRANT USAGE ON SCHEMA volc_lab TO postgres; GRANT ALL ON volc_lab.migracao_aplicada TO postgres" >/dev/null
PA -f - < "$AQUI/db/suites/v19_10_apoio.sql" >/dev/null && ok "apoio da suíte carregado (schema volc_lab, fora do fingerprint)" || nao "apoio"

echo "▶ 0. pré-condição: pacote anon aplicado"
for f in v19_00_users_gatilho_papel_real.sql v8_03_users_rls_policies.sql v19_01_anon_fecha_public.sql; do
  aplicar supabase_admin "$f" || nao "pacote anon: $f"; done
aplicar postgres v8_05_users_safe_view.sql || nao "pacote anon: v8_05"
aplicar supabase_admin v19_02_default_acl_public_sem_anon.sql && ok "pacote anon aplicado (v19_00 v8_03 v19_01 v8_05 v19_02)" || nao "pacote anon: v19_02"
eq "$(anon_fechado)" "FECHADO" "anon FECHADO antes da v19_10"

# Fluxos do app: operação | relação ou RPC | chamada no código
cat > "$R/fluxos.txt" <<'FLUXOS'
select|projects|pages/ProjectDashboard.tsx:752
insert|projects|pages/settings/ProjectsSettings.tsx:374
update|projects|pages/settings/ProjectsSettings.tsx:440
select|campaigns|services/supabaseDataService.ts (14 selects)
insert|campaigns|services/supabaseDataService.ts:3057 upsert
update|campaigns|services/supabaseDataService.ts:3057 upsert
select|user_campaigns|services/usersService.ts:73
insert|user_campaigns|v6/services/campaignMembersService.ts:231
delete|user_campaigns|v6/services/campaignMembersService.ts:312
select|user_projects|pages/GeneralDashboard.tsx:128
insert|user_projects|v6/services/campaignMembersService.ts:252
delete|user_projects|v6/services/campaignMembersService.ts:343
select|system_settings|services/supabaseDataService.ts:4122
select|tax_history|services/taxHistoryService.ts:34
insert|tax_history|services/taxHistoryService.ts:91
update|tax_history|services/taxHistoryService.ts:76
select|campaign_funnel_urls|services/campaignFunnelUrlsService.ts:23
insert|campaign_funnel_urls|services/campaignFunnelUrlsService.ts:85
update|campaign_funnel_urls|services/campaignFunnelUrlsService.ts:46
select|daily_campaign_metrics|pages/CampaignDetailDashboard.tsx:166
select|daily_project_metrics|services/supabaseDataService.ts:862
select|gam_metrics|services/supabaseDataService.ts:2159
insert|gam_metrics|services/supabaseDataService.ts:3111 upsert
update|gam_metrics|services/supabaseDataService.ts:3111 upsert
select|operational_cost_categories|services/operationalCostsService.ts:33
insert|operational_cost_categories|services/operationalCostsService.ts:43
update|operational_cost_categories|services/operationalCostsService.ts:54
delete|operational_cost_categories|services/operationalCostsService.ts:66
select|operational_costs|services/operationalCostsService.ts:80
insert|operational_costs|services/operationalCostsService.ts:158
update|operational_costs|services/operationalCostsService.ts:172
delete|operational_costs|services/operationalCostsService.ts:187
select|incubator_sites|services/incubatorService.ts:17
insert|incubator_sites|services/incubatorService.ts:54
update|incubator_sites|services/incubatorService.ts:78
delete|incubator_sites|services/incubatorService.ts:94
select|incubator_articles|services/incubatorService.ts:105
update|incubator_articles|hooks/incubator/useTitles.ts:65
delete|incubator_articles|hooks/incubator/useTitles.ts:30
select|incubator_pipeline_logs|services/incubatorService.ts:118
select|v_incubator_schedule_progress|services/incubatorService.ts:243
select|vw_display_roi|hooks/useDisplayROI.ts:29
select|pautador_agent_logs|services/pautadorService.ts:147
select|pautador_countries|services/pautadorService.ts:36
insert|pautador_countries|services/pautadorService.ts:51
select|pautador_entities|services/pautadorEntityService.ts:25 (embed)
select|pautador_entity_funnel_hypotheses|services/pautadorEntityService.ts:41
select|pautador_entity_opportunities|services/pautadorEntityService.ts:24
update|pautador_entity_opportunities|services/pautadorEntityService.ts:77
select|pautador_entity_pains|services/pautadorEntityService.ts:39
select|pautador_entity_seed_queries|services/pautadorEntityService.ts:40
select|pautador_funnels|services/pautadorService.ts:134
select|pautador_keyword_clusters|services/pautadorService.ts:121
select|pautador_opportunities|services/pautadorService.ts:92
update|pautador_opportunities|services/pautadorService.ts:110
select|pautador_runs|services/pautadorService.ts:64
rpc|get_dashboard_totals|services/supabaseDataService.ts:1554
rpc|get_period_comparison|services/supabaseDataService.ts:1566
rpc|get_campaigns_aggregated|services/supabaseDataService.ts:3521
rpc|get_campaign_detailed_metrics|services/supabaseDataService.ts:2649
rpc|get_daily_metrics_aggregated|services/supabaseDataService.ts:1252
rpc|get_projects_summary|services/supabaseDataService.ts:568
rpc|get_operational_costs_aggregated|services/supabaseDataService.ts:276
rpc|get_current_date|services/supabaseDataService.ts:378
rpc|get_last_data_update|services/supabaseDataService.ts:4061
rpc|get_rotated_campaign_highlights|services/campaignHighlightsService.ts:42
rpc|update_all_revenue_conversions|services/currencyConversionService.ts:218
rpc|enrich_campaign_with_google_ads|services/supabaseDataService.ts:2988
rpc|process_gam_metrics_auto|services/supabaseDataService.ts:3091
rpc|user_update_campaign_status|services/supabaseDataService.ts:3973
rpc|insert_incubator_articles_batch|services/incubatorService.ts:67
rpc|volc_current_admin|v6/services/visaoDeAdmin.ts:24
FLUXOS
sql_de() { # sql_de <op> <alvo>
  if [ "$1" = rpc ]; then P -c "select coalesce(volc_lab.sql_rpc('$2'), 'SELECT 1/0 -- inexistente')"
  else P -c "select volc_lab.sql_minimo('public.$2'::regclass, '$1')"; fi; }
medir() { # medir <arquivo-saida>: SQLSTATE de cada fluxo como authenticated (JWT de ADMIN) e service_role
  : > "$1"
  # fd 3: estado/P usam docker exec -i e consumiriam o stdin do laço
  while IFS='|' read -r op alvo onde <&3; do
    sql=$(sql_de "$op" "$alvo")
    printf '%s|%s|%s|%s|%s\n' "$op" "$alvo" "$(estado authenticated "$sql" "$ADMIN" | cut -c1-5)" \
      "$(estado service_role "$sql" | cut -c1-5)" "$onde" >> "$1"
  done 3< "$R/fluxos.txt"
}

echo "▶ 1. fluxos do app ANTES da v19_10"
fp "$R/fp0.txt"
medir "$R/fluxos-antes.txt"
eq "$(wc -l < "$R/fluxos-antes.txt" | tr -d ' ')" "$(wc -l < "$R/fluxos.txt" | tr -d ' ')" "todos os $(wc -l < "$R/fluxos.txt" | tr -d ' ') fluxos medidos antes"
awk -F'|' '$3=="42501"' "$R/fluxos-antes.txt" > "$R/fluxos-ja-quebrados-antes.txt"
echo "  (informativo) fluxos que JÁ davam 42501 antes da v19_10: $(wc -l < "$R/fluxos-ja-quebrados-antes.txt" | tr -d ' ') — ver fluxos-ja-quebrados-antes.txt"

echo "▶ 2. aplica a v19_10"
aplicar supabase_admin v19_10_authenticated_minimo.sql && ok "v19_10 aplicou (supabase_admin)" || nao "v19_10"
fp "$R/fp1.txt"
eq "$(anon_fechado)" "FECHADO" "anon segue FECHADO depois da v19_10"

echo "▶ 3. fluxos do app DEPOIS: nenhum regride"
medir "$R/fluxos-depois.txt"
eq "$(wc -l < "$R/fluxos-depois.txt" | tr -d ' ')" "$(wc -l < "$R/fluxos.txt" | tr -d ' ')" "todos os fluxos medidos depois"
paste -d'|' "$R/fluxos-antes.txt" "$R/fluxos-depois.txt" | awk -F'|' '$3 != $8 {print $1"|"$2"|antes="$3"|depois="$8"|"$5}' > "$R/fluxos-regressao.txt"
if [ -s "$R/fluxos-regressao.txt" ]; then
  while read -r l; do nao "fluxo mudou de resultado: $l"; done < "$R/fluxos-regressao.txt"
else ok "os $(wc -l < "$R/fluxos.txt" | tr -d ' ') fluxos do app dão o mesmo resultado antes e depois (authenticated, JWT de ADMIN)"; fi
eq "$(awk -F'|' '$3=="42501" && $4!="42501"' "$R/fluxos-depois.txt" | wc -l | tr -d ' ')" "$(wc -l < "$R/fluxos-ja-quebrados-antes.txt" | tr -d ' ')" "42501 só onde já havia antes da v19_10"

echo "▶ 4. escrita fora da decisão é recusada; RLS onde authenticated alcança"
P -A -t -F'|' > "$R/fora-da-decisao.txt" <<'SQL'
SELECT s.relacao, p.cmd
  FROM app_auth.w4_auth_acl s
  CROSS JOIN (VALUES ('insert'),('update'),('delete')) p(cmd)
 WHERE s.coluna IS NULL AND s.relkind IN ('r','p')
   AND EXISTS (SELECT 1 FROM aclexplode(s.acl_antes) x WHERE x.grantee='authenticated'::regrole AND lower(x.privilege_type)=p.cmd)
   AND NOT has_table_privilege('authenticated', format('public.%I', s.relacao)::regclass, p.cmd)
 ORDER BY 1, 2;
SQL
n_fora=$(wc -l < "$R/fora-da-decisao.txt" | tr -d ' ')
n_ruim=0
n_testadas=0
while IFS='|' read -r rel op <&3; do
  n_testadas=$((n_testadas+1))
  st=$(estado authenticated "$(sql_de "$op" "$rel")" "$ADMIN" | cut -c1-5)
  [ "$st" = 42501 ] || { n_ruim=$((n_ruim+1)); echo "$rel|$op|$st" >> "$R/fora-da-decisao-aceita.txt"; }
done 3< "$R/fora-da-decisao.txt"
eq "$n_testadas" "$n_fora" "todas as $n_fora escritas tiradas foram exercitadas uma a uma"
[ "$n_fora" -gt 0 ] && ok "há $n_fora escritas que authenticated tinha e perdeu" || nao "nenhuma escrita foi tirada (prova vazia)"
eq "$n_ruim" "0" "todas as $n_fora escritas fora da decisão dão 42501 de verdade"
eq "$(P -c "select count(*) from pg_class c where c.relnamespace='public'::regnamespace and c.relkind in ('r','p') and c.relname<>'users' and has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE') and not c.relrowsecurity")" "0" "toda tabela que authenticated alcança tem RLS"
eq "$(estado authenticated "insert into public.raw_events default values" "$ADMIN" | cut -c1-5)" "42501" "exemplo: authenticated não grava raw_events (só o volc-ingest, com service_role)"
eq "$(estado authenticated "update public.system_settings set value=value where false" "$ADMIN" | cut -c1-5)" "42501" "exemplo: authenticated não altera system_settings (gatilho reescreveria 4 tabelas)"
eq "$(estado authenticated "delete from public.campaigns where false" "$ADMIN" | cut -c1-5)" "42501" "exemplo: authenticated não apaga campaigns"
eq "$(estado authenticated "select count(*) from public.joinads_metrics" "$ADMIN" | cut -c1-5)" "42501" "exemplo: authenticated não lê joinads_metrics (sem chamada no app)"
eq "$(estado service_role "select has_table_privilege('service_role','public.joinads_metrics','INSERT,UPDATE,SELECT')")" "ok:t" "service_role (n8n, backend) mantém joinads_metrics"
eq "$(estado authenticated 'select count(*) from public.users' "$ADMIN")" "ok:2" "users da v8_03 intacta (admin vê 2)"

echo "▶ 5. rollback"
PA -c "REVOKE SELECT ON public.projects FROM authenticated" >/dev/null
aplicar supabase_admin v19_10_rollback.sql && nao "rollback passou por cima de ACL alterada depois" \
  || { grep -q "mudou depois da v19_10" "$R/aplicar-v19_10_rollback.sql.log" && ok "rollback ABORTA se a ACL mudou depois, sem desfazer nada" || nao "rollback falhou por outro motivo"; }
PA -c "GRANT SELECT ON public.projects TO authenticated" >/dev/null
aplicar supabase_admin v19_10_rollback.sql && ok "rollback aplicou" || nao "rollback"
fp "$R/fp-rollback.txt"
diff "$R/fp0.txt" "$R/fp-rollback.txt" > "$R/diff-fp0-rollback.txt" && ok "rollback devolve o fingerprint EXATO de antes da v19_10" || nao "rollback deixou resíduo (diff-fp0-rollback.txt)"
aplicar supabase_admin v19_10_rollback.sql && ok "rollback idempotente" || nao "rollback idempotente"
medir "$R/fluxos-pos-rollback.txt"
diff -q "$R/fluxos-antes.txt" "$R/fluxos-pos-rollback.txt" >/dev/null && ok "fluxos depois do rollback = antes" || nao "fluxos mudaram depois do rollback"
eq "$(anon_fechado)" "FECHADO" "anon segue FECHADO depois do rollback da v19_10"

echo "▶ 6. reaplicação"
aplicar supabase_admin v19_10_authenticated_minimo.sql && ok "v19_10 reaplicou" || nao "reaplicação"
fp "$R/fp2.txt"
diff -q "$R/fp1.txt" "$R/fp2.txt" >/dev/null && ok "fingerprint idêntico entre 1ª e 2ª aplicação" || nao "fingerprint divergiu"
aplicar supabase_admin v19_10_authenticated_minimo.sql && nao "v19_10 reaplicou por cima" \
  || { grep -q "já aplicada" "$R/aplicar-v19_10_authenticated_minimo.sql.log" && ok "v19_10 por cima recusada pela guarda" || nao "falhou por outro motivo"; }

for f in v19_10_authenticated_minimo v19_10_rollback; do echo "$f.sql $(sha "$W4_MIG/$f.sql")"; done > "$R/pacote-sha256.txt"
P -f - < "$FP" > "$R/fp-final.out" 2>&1
