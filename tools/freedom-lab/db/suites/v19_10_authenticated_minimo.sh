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
# Provas (revisão local de 15/10, ciclo 1 da v19_10):
#   1. FLUXOS VIVOS com linhas reais (semente v19_10_semente.sql) e gatilhos
#      disparando: cada fluxo roda como authenticated (JWT de ADMIN) numa
#      transação desfeita; o critério é o RESULTADO inteiro (linhas devolvidas e
#      o efeito dos gatilhos nas tabelas de dinheiro), antes × depois;
#   2. MUTANTE: a v19_10 sem o INSERT de daily_campaign_metrics (grant que só os
#      gatilhos usam) TEM de ser pega pelos fluxos — senão a prova é cega;
#   3. OPERADOR (JWT sem papel ADMIN) é recusado ao reescrever dinheiro, forjar
#      sync_logs, dar setval e mudar coluna fora da lista — e antes conseguia;
#   4. escrita fora da decisão = 42501; RLS em tudo que authenticated alcança;
#   5. rollback aborta se ACL, RLS ou policy mudou depois; fingerprint exato;
#      idempotente; reaplicação idêntica; ordem com o v19_99; anon FECHADO.
W4_MIG="$RAIZ/supabase/migrations"; R="$RECIBOS"
ADMIN='{"sub":"a0000000-0000-4000-8000-00000000000a","email":"admin@example.invalid","role":"authenticated"}'
OPER='{"sub":"a0000000-0000-4000-8000-00000000000b","email":"operador@example.invalid","role":"authenticated"}'
SEMPAPEL='{"sub":"a0000000-0000-4000-8000-0000000000ff","email":"conta-nova@example.invalid","role":"authenticated"}'
fp() { P -f - < "$FP" 2>&1 | grep '|' | tr -d ' ' > "$1"; }
aplicar() { local cmd=PA arq="$W4_MIG/$2"; [ "$1" = postgres ] && cmd=P; [ -f "$2" ] && arq="$2"
  if $cmd -f - < "$arq" > "$R/aplicar-$(basename "$arq").log" 2>&1; then registrar "$arq" "$1" ok; return 0
  else registrar "$arq" "$1" falhou; tail -3 "$R/aplicar-$(basename "$arq").log"; return 1; fi; }
anon_fechado() {
  docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$NOME" psql -U postgres -d postgres -X -q -A -t -F'|' \
    < "$RAIZ/scripts/verificar-anon-w4.sql" 2>&1 | awk -F'|' '$1~/V[1234]/ && $3!=0 {a=1} END {print (a?"ABERTO":"FECHADO")}'; }

PA -c "CREATE SCHEMA IF NOT EXISTS volc_lab; CREATE TABLE IF NOT EXISTS volc_lab.migracao_aplicada (
  arquivo text NOT NULL, sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  aplicada_em timestamptz NOT NULL DEFAULT now(), base text NOT NULL, resultado text NOT NULL);
  GRANT USAGE ON SCHEMA volc_lab TO postgres; GRANT ALL ON volc_lab.migracao_aplicada TO postgres" >/dev/null
PA -f - < "$AQUI/db/suites/v19_10_apoio.sql" >/dev/null && ok "apoio da suíte carregado (schema volc_lab, fora do fingerprint)" || nao "apoio"

echo "▶ 0. pré-condição: pacote anon + semente com linhas reais"
for f in v19_00_users_gatilho_papel_real.sql v8_03_users_rls_policies.sql v19_01_anon_fecha_public.sql; do
  aplicar supabase_admin "$f" || nao "pacote anon: $f"; done
aplicar postgres v8_05_users_safe_view.sql || nao "pacote anon: v8_05"
aplicar supabase_admin v19_02_default_acl_public_sem_anon.sql && ok "pacote anon aplicado (v19_00 v8_03 v19_01 v8_05 v19_02)" || nao "pacote anon: v19_02"
PA -f - < "$AQUI/db/suites/v19_10_semente.sql" > "$R/semente-v19_10.log" 2>&1 && ok "semente v19_10 (linhas reais para os gatilhos)" || { nao "semente v19_10"; tail -3 "$R/semente-v19_10.log"; }
eq "$(anon_fechado)" "FECHADO" "anon FECHADO antes da v19_10"

# ---------------------------------------------------------------------------
# Fluxos vivos. run <nome> <claims> <prep-como-superusuário> <sql-como-authenticated> [efeito]
# Saída: nome|OK|<linhas devolvidas + efeito> ou nome|ERRO|<mensagem>. RETURNING
# sem id de sequência (a sequência avança mesmo com ROLLBACK).
# ---------------------------------------------------------------------------
# Efeito medido na campanha do fluxo (123456789). Campanhas alheias têm prova
# própria: a v19_10 deixa de recalculá-las (ciclo 3 da revisão).
EFEITO="RESET ROLE; SELECT 'dcm', campaign_id, date, revenue, revenue_converted, revenue_converted_revshare, commission_operator FROM public.daily_campaign_metrics WHERE campaign_id='123456789' ORDER BY 2,3; SELECT 'dpm', project_id, revenue_converted, revenue_converted_revshare FROM public.daily_project_metrics ORDER BY 2; SELECT 'ads', url, revenue_converted FROM public.adsense_metrics ORDER BY 2; SELECT 'gam', utm_campaign_value, revenue_converted FROM public.gam_metrics ORDER BY 2; SELECT 'proj', count(*) FROM public.projects;"
run() {
  local out err
  out=$(printf '\\set VERBOSITY terse\nBEGIN;\n%s\nSET LOCAL ROLE authenticated;\nSET LOCAL request.jwt.claims = %s;\n%s\n%s\nROLLBACK;\n' \
        "$3" "'$2'" "$4" "${5:-}" | docker exec -i "$NOME" psql -h localhost -U supabase_admin -d postgres -X -A -t -q 2>&1)
  err=$(printf '%s\n' "$out" | grep -m1 -E 'ERROR:' | sed -E 's/^psql:<stdin>:[0-9]+: //')
  if [ -n "$err" ]; then echo "$1|ERRO|$err"
  else echo "$1|OK|$(printf '%s\n' "$out" | grep -v NOTICE | grep -v '^$' | tr '\n' ' ')"; fi
}
fluxos() { # fluxos <arquivo-saida> — 1 docker exec por fluxo; nada lê o stdin do laço
  local O="$1"; : > "$O"
  run cfu_insert__campaignFunnelUrlsService.ts:85 "$ADMIN" "" "INSERT INTO public.campaign_funnel_urls (campaign_id, url, \"Active\") VALUES ('123456789','https://www.p1.example/b', true) RETURNING url;" "$EFEITO" >> "$O"
  run cfu_update__campaignFunnelUrlsService.ts:46 "$ADMIN" "" "UPDATE public.campaign_funnel_urls SET \"Active\"=false, updated_at=now() WHERE campaign_id='123456789';" "$EFEITO" >> "$O"
  run cfu_upsert__campaignFunnelUrlsService.ts:59 "$ADMIN" "" "INSERT INTO public.campaign_funnel_urls (campaign_id, url, \"Active\") VALUES ('123456789','p1.example/a', true) ON CONFLICT (campaign_id,url) DO UPDATE SET \"Active\"=EXCLUDED.\"Active\" RETURNING url, \"Active\";" "$EFEITO" >> "$O"
  run projects_insert__ProjectsSettings.tsx:374 "$ADMIN" "" "INSERT INTO public.projects (project_name, main_url, domain, start_date, status, revshare) VALUES ('p2.example','https://p2.example','p2.example',current_date,'Active',0.1) RETURNING project_name;" "$EFEITO" >> "$O"
  run projects_update_revshare__ProjectsSettings.tsx:440 "$ADMIN" "" "UPDATE public.projects SET revshare=0.3, updated_at=now() WHERE id=9001;" "$EFEITO" >> "$O"
  run projects_update_type__ProjectDashboard.tsx:509 "$ADMIN" "" "UPDATE public.projects SET project_type='ADSENSE', updated_at=now() WHERE id=9001;" "$EFEITO" >> "$O"
 # já quebrado antes da v19_10 (gatilho de gam_metrics lê trafego_meta_adset sem grant)
  run MORTO_conversoes_com_gam__currencyConversionService.ts:218 "$ADMIN" "" "SELECT public.update_all_revenue_conversions();" "$EFEITO" >> "$O"
  run conversoes_sem_gam__currencyConversionService.ts:218 "$ADMIN" "DELETE FROM public.gam_metrics;" "SELECT public.update_all_revenue_conversions();" "$EFEITO" >> "$O"
  run incubator_batch__incubatorService.ts:67 "$ADMIN" "" "SELECT public.insert_incubator_articles_batch(9001, ARRAY['novo titulo','t1']);" >> "$O"
  run incubator_sites_insert__incubatorService.ts:54 "$ADMIN" "" "INSERT INTO public.incubator_sites (site_name, site_niche, site_audience, wp_url) VALUES ('s2','n','a','https://s2.example') RETURNING site_name;" >> "$O"
  run incubator_sites_update__incubatorService.ts:78 "$ADMIN" "" "UPDATE public.incubator_sites SET status=status, updated_at=now() WHERE id=9001 RETURNING 1;" >> "$O"
  run incubator_articles_update__useTitles.ts:65 "$ADMIN" "" "UPDATE public.incubator_articles SET title='t1b' WHERE id=9001 RETURNING title;" >> "$O"
  run incubator_articles_delete__useTitles.ts:30 "$ADMIN" "" "DELETE FROM public.incubator_articles WHERE id=9001 RETURNING 1;" >> "$O"
  run incubator_sites_delete__incubatorService.ts:94 "$ADMIN" "DELETE FROM public.incubator_articles WHERE site_id=9001;" "DELETE FROM public.incubator_sites WHERE id=9001 RETURNING 1;" >> "$O"
  run opcost_insert__operationalCostsService.ts:158 "$ADMIN" "" "INSERT INTO public.operational_costs (name, amount, category_id, month) VALUES ('cost2', 5, 9001, date_trunc('month', current_date)::date) RETURNING name;" >> "$O"
  run opcost_update__operationalCostsService.ts:172 "$ADMIN" "" "UPDATE public.operational_costs SET amount=11 WHERE id=9001 RETURNING amount;" >> "$O"
  run opcost_delete__operationalCostsService.ts:187 "$ADMIN" "" "DELETE FROM public.operational_costs WHERE id=9001 RETURNING 1;" >> "$O"
  run opcat_insert__operationalCostsService.ts:43 "$ADMIN" "" "INSERT INTO public.operational_cost_categories (name) VALUES ('cat2') RETURNING name;" >> "$O"
  run opcat_update__operationalCostsService.ts:54 "$ADMIN" "" "UPDATE public.operational_cost_categories SET name='cat1b' WHERE id=9001 RETURNING name;" >> "$O"
  run opcat_delete__operationalCostsService.ts:66 "$ADMIN" "DELETE FROM public.operational_costs WHERE category_id=9001;" "DELETE FROM public.operational_cost_categories WHERE id=9001 RETURNING 1;" >> "$O"
  run tax_insert__taxHistoryService.ts:91 "$ADMIN" "" "INSERT INTO public.tax_history (month, percentage, effective_date) VALUES ((date_trunc('month', current_date) + interval '1 month')::date, 12, now()) RETURNING percentage;" >> "$O"
  run tax_update__taxHistoryService.ts:76 "$ADMIN" "" "UPDATE public.tax_history SET percentage=11 WHERE month=date_trunc('month', current_date)::date RETURNING percentage;" "$EFEITO" >> "$O"
  run uc_insert__campaignMembersService.ts:231 "$ADMIN" "" "INSERT INTO public.user_campaigns (user_id, campaign_id) VALUES ('b0000000-0000-4000-8000-00000000000a','123456789') RETURNING campaign_id;" >> "$O"
  run uc_delete__campaignMembersService.ts:312 "$ADMIN" "" "DELETE FROM public.user_campaigns WHERE user_id='b0000000-0000-4000-8000-00000000000b' AND campaign_id='123456789' RETURNING 1;" >> "$O"
  run up_insert__campaignMembersService.ts:252 "$ADMIN" "" "INSERT INTO public.user_projects (user_id, project_id) VALUES ('b0000000-0000-4000-8000-00000000000a', 9001) RETURNING project_id;" >> "$O"
  run up_delete__campaignMembersService.ts:343 "$ADMIN" "" "DELETE FROM public.user_projects WHERE user_id='b0000000-0000-4000-8000-00000000000b' RETURNING 1;" >> "$O"
  run pautador_opp_update__pautadorService.ts:110 "$ADMIN" "" "UPDATE public.pautador_opportunities SET status='validating' WHERE id=9001 RETURNING status;" >> "$O"
  run pautador_entopp_update__pautadorEntityService.ts:77 "$ADMIN" "" "UPDATE public.pautador_entity_opportunities SET status='validating', kanban_stage='validating' WHERE id=9001 RETURNING status, kanban_stage;" >> "$O"
  run pautador_countries_insert__pautadorService.ts:51 "$ADMIN" "" "INSERT INTO public.pautador_countries (country_code, country_name, native_language) VALUES ('ZZ','Z','z') RETURNING country_code;" >> "$O"
  run users_commission__usersService.ts:215 "$ADMIN" "" "UPDATE public.users SET commission_percentage=7 WHERE role='OPERATOR' RETURNING commission_percentage;" "$EFEITO" >> "$O"
  # OPERADOR: tudo que o app oferece a ele (rota /dashboard/campaign/ e "Configurar" → FunnelUrlsEditor)
  run OP_cfu_insert__campaignFunnelUrlsService.ts:85 "$OPER" "" "INSERT INTO public.campaign_funnel_urls (campaign_id, url, \"Active\") VALUES ('123456789','https://www.p1.example/op', true) RETURNING url;" "$EFEITO" >> "$O"
  run OP_cfu_update__campaignFunnelUrlsService.ts:46 "$OPER" "" "UPDATE public.campaign_funnel_urls SET \"Active\"=false, updated_at=now() WHERE campaign_id='123456789';" "$EFEITO" >> "$O"
  run OP_cfu_upsert__campaignFunnelUrlsService.ts:59 "$OPER" "" "INSERT INTO public.campaign_funnel_urls (campaign_id, url, \"Active\") VALUES ('123456789','p1.example/a', true) ON CONFLICT (campaign_id,url) DO UPDATE SET \"Active\"=EXCLUDED.\"Active\" RETURNING url, \"Active\";" "$EFEITO" >> "$O"
  run OP_cfu_update_url__campaignFunnelUrlsService.ts:110 "$OPER" "" "UPDATE public.campaign_funnel_urls SET url='p1.example/a2', updated_at=now() WHERE campaign_id='123456789' AND url='p1.example/a' RETURNING url;" "$EFEITO" >> "$O"
  run OP_read_dcm__CampaignDetailDashboard.tsx:166 "$OPER" "" "SELECT count(*), sum(revenue_converted) FROM public.daily_campaign_metrics;" >> "$O"
  run OP_rpc_detalhe__supabaseDataService.ts:2649 "$OPER" "" "SELECT count(*) FROM (SELECT * FROM public.get_campaign_detailed_metrics('123456789', current_date-30, current_date)) x;" >> "$O"
  run OP_troca_senha__ChangePassword.tsx:91 "$OPER" "" "UPDATE public.users SET needs_password_change=false WHERE email='operador@example.invalid' RETURNING needs_password_change;" >> "$O"
  run OP_rpc_dashboard_totals__supabaseDataService.ts:1554 "$OPER" "" "SELECT count(*) FROM (SELECT public.get_dashboard_totals(current_date-30, current_date, NULL)) x;" >> "$O"
  run read_vw_display_roi__useDisplayROI.ts:29 "$ADMIN" "" "SELECT count(*) FROM public.vw_display_roi;" >> "$O"
  run read_v_incubator_schedule__incubatorService.ts:243 "$ADMIN" "" "SELECT count(*) FROM public.v_incubator_schedule_progress;" >> "$O"
  run read_dcm__CampaignDetailDashboard.tsx:166 "$ADMIN" "" "SELECT count(*), sum(revenue_converted) FROM public.daily_campaign_metrics;" >> "$O"
  run rpc_dashboard_totals__supabaseDataService.ts:1554 "$ADMIN" "" "SELECT count(*) FROM (SELECT public.get_dashboard_totals(current_date-30, current_date, NULL)) x;" >> "$O"
  run rpc_projects_summary__supabaseDataService.ts:568 "$ADMIN" "" "SELECT count(*) FROM (SELECT * FROM public.get_projects_summary(current_date-30, current_date, NULL)) x;" >> "$O"
  run rpc_daily_metrics__supabaseDataService.ts:1252 "$ADMIN" "" "SELECT count(*) FROM (SELECT * FROM public.get_daily_metrics_aggregated(current_date-30, current_date, NULL)) x;" >> "$O"
  run rpc_period_comparison__supabaseDataService.ts:1566 "$ADMIN" "" "SELECT count(*) FROM (SELECT public.get_period_comparison(current_date-30, current_date, NULL)) x;" >> "$O"
  run rpc_campaigns_aggregated__supabaseDataService.ts:3521 "$ADMIN" "" "SELECT count(*) FROM (SELECT * FROM public.get_campaigns_aggregated(9001, current_date-30, current_date)) x;" >> "$O"
  run rpc_rotated_highlights__campaignHighlightsService.ts:42 "$ADMIN" "" "SELECT count(*) FROM (SELECT * FROM public.get_rotated_campaign_highlights()) x;" >> "$O"
  run rpc_last_data_update__supabaseDataService.ts:4061 "$ADMIN" "" "SELECT count(*) FROM (SELECT public.get_last_data_update()) x;" >> "$O"
  # mortos ou já quebrados: medidos e reportados, fora do critério de igualdade
  run MORTO_rpc_user_update_campaign_status__CampaignsSettings.tsx:261 "$ADMIN" "" "SELECT public.user_update_campaign_status('123456789','Paused','current_user');" >> "$O"
  run MORTO_gam_upsert__supabaseDataService.ts:3111 "$ADMIN" "" "INSERT INTO public.gam_metrics (date, utm_campaign_value, revenue, gam_accounts_id) VALUES (current_date,'123456789',3,'g1') ON CONFLICT (date,utm_campaign_value,gam_accounts_id) DO UPDATE SET revenue=EXCLUDED.revenue;" >> "$O"
  run MORTO_rpc_process_gam_metrics_auto__supabaseDataService.ts:3091 "$ADMIN" "" "SELECT public.process_gam_metrics_auto('{\"value\":\"123456789\",\"date\":\"2026-10-14\",\"revenue\":\"1\",\"gam_accounts_id\":\"g2\"}'::jsonb);" >> "$O"
  run MORTO_rpc_enrich_campaign__supabaseDataService.ts:2988 "$ADMIN" "" "SELECT public.enrich_campaign_with_google_ads('{\"campaign_id\":\"987654321\",\"campaign_name\":\"x / y / novo.example/z\",\"status\":\"ENABLED\",\"start_date\":\"2026-10-01\"}'::jsonb);" >> "$O"
}
vivos() { grep -v '^MORTO_' "$1"; }
comparar() { # comparar <antes> <depois> <saida-dif> → nº de fluxos vivos que mudaram
  diff <(vivos "$1") <(vivos "$2") > "$3"; grep -c '^>' "$3" || true; }

# Tentativas de OPERADOR (JWT sem ADMIN em app_auth). Saída: nome|SQLSTATE ou ok:
operador() {
  local O="$1"; : > "$O"
  t() { echo "$1|$(estado authenticated "$2" "$OPER" | cut -c1-5)" >> "$O"; }
  t dcm_commission_operator "update public.daily_campaign_metrics set commission_operator=999999 where true returning 1"
  t dcm_revenue "update public.daily_campaign_metrics set revenue=0 where true returning 1"
  t dcm_insert "insert into public.daily_campaign_metrics (campaign_id, date, revenue) values ('123456789', current_date+1, 999) returning 1"
  t adsense_revenue "update public.adsense_metrics set revenue=12345 where true returning 1"
  t gam_revenue "update public.gam_metrics set revenue_converted=1 where true returning 1"
  t dpm_revenue "update public.daily_project_metrics set revenue_converted=1 where true returning 1"
  t projects_revshare "update public.projects set revshare=0.99 where id=9001 returning 1"
  t tax_percentage "update public.tax_history set percentage=1 where true returning 1"
  t opcost_amount "update public.operational_costs set amount=1 where true returning 1"
  t sync_logs_forjado "insert into public.sync_logs (sync_type,status,message,details) values ('user_action','success','x','{}')"
  t setval_joinads "select setval('public.joinads_metrics_id_seq', 1)"
  t pautador_opp_outra_coluna "update public.pautador_opportunities set keyword='x' where id=9001 returning 1"
}

# Ataques da revisão (ciclo 2): campanha alheia 222222222 (projeto 9002), sem vínculo.
# Saída por ataque: nome|ABERTO (efeito aconteceu) ou nome|FECHADO.
VITIMA="RESET ROLE; SELECT 'vitima', coalesce(sum(revenue_converted_revshare), -1) FROM public.daily_campaign_metrics WHERE campaign_id='222222222';"
ataques() {
  local O="$1" quem claims base r; : > "$O"
  base=$(run base "$ADMIN" "" "SELECT 1;" "$VITIMA" | grep -o 'vitima|[^ ]*')
  for quem in OPER SEMPAPEL; do
    [ "$quem" = OPER ] && claims="$OPER" || claims="$SEMPAPEL"
    r=$(run a1 "$claims" "" "UPDATE public.campaign_funnel_urls SET \"Active\"=false WHERE campaign_id='222222222';" "$VITIMA" | grep -o 'vitima|[^ ]*')
    [ "$r" != "$base" ] && echo "$quem·zera_receita_alheia|ABERTO" >> "$O" || echo "$quem·zera_receita_alheia|FECHADO" >> "$O"
    r=$(run a2 "$claims" "" "INSERT INTO public.campaign_funnel_urls (campaign_id, url, \"Active\") VALUES ('123456789','p2v.example/x', true);" "RESET ROLE; SELECT 'puxou', count(*) FROM public.campaign_funnel_urls WHERE campaign_id='123456789' AND url LIKE 'p2v.example%';")
    printf '%s' "$r" | grep -q 'puxou|1' && echo "$quem·puxa_receita_de_outro_projeto|ABERTO" >> "$O" || echo "$quem·puxa_receita_de_outro_projeto|FECHADO" >> "$O"
    r=$(run a3 "$claims" "" "INSERT INTO public.user_campaigns (user_id, campaign_id) VALUES ('b0000000-0000-4000-8000-00000000000b','222222222');" "RESET ROLE; SELECT 'vinculou', count(*) FROM public.user_campaigns WHERE campaign_id='222222222';")
    printf '%s' "$r" | grep -q 'vinculou|1' && echo "$quem·vincula_operador_a_campanha_alheia|ABERTO" >> "$O" || echo "$quem·vincula_operador_a_campanha_alheia|FECHADO" >> "$O"
  done
}

echo "▶ 1. ANTES da v19_10 (com linhas reais)"
fp "$R/fp0.txt"
defacl() { P -c "select defaclrole::regrole::text||'|'||defaclobjtype::text||'|'||(select string_agg(i::text, ',' order by i::text) from unnest(defaclacl) i) from pg_default_acl where defaclnamespace='public'::regnamespace order by 1" > "$1" 2>&1; }
defacl "$R/defacl0.txt"
[ -s "$R/defacl0.txt" ] && ! grep -q ERROR "$R/defacl0.txt" && ok "default ACL de public lido ($(wc -l < "$R/defacl0.txt" | tr -d ' ') entradas)" || nao "leitura do default ACL vazia ou com erro"
fluxos "$R/fluxos-antes.txt"
operador "$R/operador-antes.txt"
eq "$(vivos "$R/fluxos-antes.txt" | grep -c '|OK|')" "$(vivos "$R/fluxos-antes.txt" | wc -l | tr -d ' ')" "todos os $(vivos "$R/fluxos-antes.txt" | wc -l | tr -d ' ') fluxos vivos funcionam antes (ADMIN)"
grep -v '|ok:' "$R/operador-antes.txt" > "$R/operador-antes-ja-negado.txt" || true
# gam_revenue já falha antes (gatilho lê trafego_meta_adset); pautador_opp_outra_coluna depende da policy antiga
eq "$(grep -vE '^(pautador_opp_outra_coluna|gam_revenue)\|' "$R/operador-antes.txt" | grep -c '|ok:')" "$(grep -vcE '^(pautador_opp_outra_coluna|gam_revenue)\|' "$R/operador-antes.txt")" "antes da v19_10 o OPERADOR consegue as escritas de dinheiro, sync_logs e setval (o buraco existe)"
eq "$(grep '^OP_' "$R/fluxos-antes.txt" | grep -c '|OK|')" "$(grep -c '^OP_' "$R/fluxos-antes.txt")" "fluxos de OPERADOR funcionam antes (inclusive salvar URL de funil)"
ataques "$R/ataques-antes.txt"
eq "$(grep -c '|ABERTO' "$R/ataques-antes.txt")" "6" "antes da v19_10 os 3 ataques da revisão funcionam como operador e como conta sem papel (o buraco existe)"
grep -q 'dcm|123456789' "$R/fluxos-antes.txt" && ok "os fluxos medem o efeito dos gatilhos (linhas de daily_campaign_metrics no resultado)" || nao "fluxos sem efeito de gatilho"

echo "▶ 2. MUTANTES (a prova tem de enxergar gatilhos e o operador)"
mutante() { # mutante <nome> <arquivo-gerado> <descrição>
  local n
  aplicar supabase_admin "$2" && ok "mutante $1 aplicou" || nao "mutante $1 não aplicou"
  fluxos "$R/fluxos-mutante-$1.txt"
  n=$(comparar "$R/fluxos-antes.txt" "$R/fluxos-mutante-$1.txt" "$R/dif-mutante-$1.txt")
  [ "${n:-0}" -gt 0 ] && ok "a suíte PEGA o mutante $1 ($3): $n fluxo(s) vivo(s) mudam" || nao "a suíte não pega o mutante $1 ($3)"
  aplicar supabase_admin v19_10_rollback.sql && ok "rollback do mutante $1" || nao "rollback do mutante $1"
  fp "$R/fp-pos-mutante-$1.txt"; diff -q "$R/fp0.txt" "$R/fp-pos-mutante-$1.txt" >/dev/null && ok "base intacta depois do mutante $1" || nao "mutante $1 deixou resíduo"
}
MUT_A="$R/v19_10_MUTANTE_A_sem_update_dcm.sql"
sed "s/^ ('daily_campaign_metrics',      true, true,  true,  false,/ ('daily_campaign_metrics',      true, true,  false, false,/" "$W4_MIG/v19_10_authenticated_minimo.sql" > "$MUT_A"
grep -q "('daily_campaign_metrics',      true, true,  false, false" "$MUT_A" && ok "mutante A gerado (sem o UPDATE de daily_campaign_metrics, que só gatilhos usam)" || nao "mutante A não gerado"
mutante A "$MUT_A" "grant usado só por gatilho"
MUT_B="$R/v19_10_MUTANTE_B_funil_invoker.sql"
sed -e '/^ALTER FUNCTION public.trigger_\(calculate_adsense_campaign_revenue\|funnel_url_change\)() OWNER TO volc_agregador_funil;/d' \
    -e 's/^RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS \$f\$/RETURNS trigger LANGUAGE plpgsql AS $f$/' \
    "$W4_MIG/v19_10_authenticated_minimo.sql" > "$MUT_B"
grep -q 'OWNER TO volc_agregador_funil' "$MUT_B" && nao "mutante B não gerado" || ok "mutante B gerado (gatilhos do funil continuam INVOKER)"
mutante B "$MUT_B" "operador salvando URL de funil"
MUT_C="$R/v19_10_MUTANTE_C_sem_escopo_funil.sql"
sed -e 's/^  SELECT public.volc_current_admin()$/  SELECT true OR public.volc_current_admin()/' "$W4_MIG/v19_10_authenticated_minimo.sql" > "$MUT_C"
grep -q 'SELECT true OR public.volc_current_admin()' "$MUT_C" && ok "mutante C gerado (escopo do funil aberto)" || nao "mutante C não gerado"
aplicar supabase_admin "$MUT_C" && ok "mutante C aplicou" || nao "mutante C"
ataques "$R/ataques-mutante-C.txt"
grep -q '|ABERTO' "$R/ataques-mutante-C.txt" && ok "os testes de ataque PEGAM o mutante C (escopo aberto)" || nao "os testes de ataque não pegam o escopo aberto"
aplicar supabase_admin v19_10_rollback.sql && ok "rollback do mutante C" || nao "rollback do mutante C"

echo "▶ 3. aplica a v19_10"
aplicar supabase_admin v19_10_authenticated_minimo.sql && ok "v19_10 aplicou (supabase_admin)" || nao "v19_10"
fp "$R/fp1.txt"
eq "$(anon_fechado)" "FECHADO" "anon segue FECHADO depois da v19_10"
fluxos "$R/fluxos-depois.txt"
n_reg=$(comparar "$R/fluxos-antes.txt" "$R/fluxos-depois.txt" "$R/dif-regressao.txt")
eq "${n_reg:-0}" "0" "os $(vivos "$R/fluxos-antes.txt" | wc -l | tr -d ' ') fluxos vivos dão o MESMO resultado (linhas e efeito dos gatilhos) antes e depois"
grep '^MORTO_' "$R/fluxos-depois.txt" | cut -d'|' -f1,2 > "$R/fluxos-mortos-depois.txt"
echo "  (informativo) mortos/já quebrados depois: $(tr '\n' ' ' < "$R/fluxos-mortos-depois.txt")"

eq "$(run vizinho "$ADMIN" "" "INSERT INTO public.campaign_funnel_urls (campaign_id, url, \"Active\") VALUES ('123456789','p1.example/v', true);" "$VITIMA" | grep -o 'vitima|[^ ]*')" "$(run base "$ADMIN" "" "SELECT 1;" "$VITIMA" | grep -o 'vitima|[^ ]*')" "gravar URL na própria campanha não recalcula a campanha alheia (antes recalculava todas)"
grep -o 'vitima|[^ ]*' <(run vizinho_antes "$ADMIN" "" "SELECT 1;" "$VITIMA") > /dev/null
echo "▶ 4. OPERADOR recusado"
ataques "$R/ataques-depois.txt"
while IFS='|' read -r nome st <&3; do
  [ "$st" = FECHADO ] && ok "ataque · $nome recusado" || nao "ataque · $nome AINDA funciona"
done 3< "$R/ataques-depois.txt"
operador "$R/operador-depois.txt"
while IFS='|' read -r nome st <&3; do
  [ "$st" = 42501 ] && ok "operador · $nome recusado (42501)" || nao "operador · $nome NÃO recusado ($st)"
done 3< "$R/operador-depois.txt"
eq "$(estado authenticated "update public.daily_campaign_metrics set commission_operator=commission_operator where campaign_id='123456789' returning 1" "$ADMIN" | cut -c1-4)" "ok:1" "ADMIN ainda grava dinheiro (telas de admin)"
eq "$(P -c "select count(*) from pg_class c where c.relnamespace='public'::regnamespace and c.relkind='S' and case when c.relkind='S' then has_sequence_privilege('authenticated', c.oid, 'UPDATE') end")" "0" "nenhuma sequência de public com setval para authenticated"
# W12 (câmbio): system_settings e a sequência do histórico de câmbio
eq "$(estado authenticated "update public.system_settings set value='9.99' where key='dollar_exchange_rate' returning 1" "$OPER" | cut -c1-5)" "42501" "W12 · operador não altera dollar_exchange_rate"
eq "$(estado authenticated "update public.system_settings set value='9.99' where key='dollar_exchange_rate' returning 1" "$ADMIN" | cut -c1-5)" "42501" "W12 · nem admin altera system_settings pelo browser (UPDATE só em componente sem import)"
eq "$(estado anon "update public.system_settings set value='9.99' where key='dollar_exchange_rate' returning 1" | cut -c1-5)" "42501" "W12 · anon não altera system_settings (v19_01)"
eq "$(estado authenticated "select setval('public.exchange_rate_history_id_seq', 1)" "$OPER" | cut -c1-5)" "42501" "W12 · operador não dá setval em exchange_rate_history_id_seq"
eq "$(P -c "select has_sequence_privilege('authenticated','public.exchange_rate_history_id_seq','USAGE') or has_sequence_privilege('authenticated','public.exchange_rate_history_id_seq','SELECT') or has_sequence_privilege('authenticated','public.exchange_rate_history_id_seq','UPDATE') or has_sequence_privilege('anon','public.exchange_rate_history_id_seq','USAGE') or has_sequence_privilege('anon','public.exchange_rate_history_id_seq','UPDATE')")" "f" "W12 · exchange_rate_history_id_seq sem USAGE/SELECT/UPDATE para anon e authenticated"

echo "▶ 5. escrita fora da decisão é recusada; RLS onde authenticated alcança"
P -A -t -F'|' > "$R/fora-da-decisao.txt" <<'SQL'
SELECT s.relacao, p.cmd
  FROM app_auth.w4_auth_acl s
  CROSS JOIN (VALUES ('insert'),('update'),('delete')) p(cmd)
 WHERE s.coluna IS NULL AND s.relkind IN ('r','p')
   AND EXISTS (SELECT 1 FROM aclexplode(s.acl_antes) x WHERE x.grantee='authenticated'::regrole AND lower(x.privilege_type)=p.cmd)
   AND NOT has_table_privilege('authenticated', format('public.%I', s.relacao)::regclass, p.cmd)
   AND NOT (p.cmd = 'update' AND has_any_column_privilege('authenticated', format('public.%I', s.relacao)::regclass, 'UPDATE'))
 ORDER BY 1, 2;
SQL
n_fora=$(wc -l < "$R/fora-da-decisao.txt" | tr -d ' '); n_ruim=0; n_testadas=0
while IFS='|' read -r rel op <&3; do
  n_testadas=$((n_testadas+1))
  st=$(estado authenticated "$(P -c "select volc_lab.sql_minimo('public.$rel'::regclass, '$op')")" "$ADMIN" | cut -c1-5)
  [ "$st" = 42501 ] || { n_ruim=$((n_ruim+1)); echo "$rel|$op|$st" >> "$R/fora-da-decisao-aceita.txt"; }
done 3< "$R/fora-da-decisao.txt"
eq "$n_testadas" "$n_fora" "todas as $n_fora escritas tiradas exercitadas uma a uma"
eq "$n_ruim" "0" "todas as $n_fora escritas fora da decisão dão 42501"
eq "$(P -c "select count(*) from pg_class c where c.relnamespace='public'::regnamespace and c.relkind in ('r','p') and c.relname<>'users' and has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE') and not c.relrowsecurity")" "0" "toda tabela que authenticated alcança tem RLS"
eq "$(estado authenticated "select count(*) from public.joinads_metrics" "$ADMIN" | cut -c1-5)" "42501" "authenticated não lê joinads_metrics (sem chamada no app)"
eq "$(estado service_role "select has_table_privilege('service_role','public.joinads_metrics','INSERT,UPDATE,SELECT') and has_sequence_privilege('service_role','public.joinads_metrics_id_seq','USAGE,UPDATE')")" "ok:t" "service_role (n8n, backend) mantém joinads_metrics e a sequência"
eq "$(estado authenticated 'select count(*) from public.users' "$ADMIN")" "ok:2" "users da v8_03 intacta (admin vê 2)"

echo "▶ 5b. objeto NOVO depois da v19_10 (default ACL)"
P -c "create table public.w4_nova_tabela (id serial primary key, v int); insert into public.w4_nova_tabela (v) values (1)" >/dev/null
PA -c "create sequence public.w4_nova_seq_admin" >/dev/null
eq "$(estado authenticated 'insert into public.w4_nova_tabela (v) values (2)' "$OPER" | cut -c1-5)" "42501" "tabela nova de postgres · operador não insere"
eq "$(estado authenticated 'update public.w4_nova_tabela set v=3' "$ADMIN" | cut -c1-5)" "42501" "tabela nova de postgres · nem admin (pelo browser) altera sem GRANT da migration"
eq "$(estado authenticated 'select count(*) from public.w4_nova_tabela' "$OPER" | cut -c1-5)" "42501" "tabela nova de postgres · authenticated não lê sem GRANT"
eq "$(estado authenticated "select setval('public.w4_nova_tabela_id_seq', 1)" "$OPER" | cut -c1-5)" "42501" "sequência nova de postgres · operador não dá setval"
eq "$(estado authenticated "select setval('public.w4_nova_seq_admin', 1)" "$OPER" | cut -c1-5)" "42501" "sequência nova de supabase_admin · operador não dá setval"
eq "$(estado anon 'select count(*) from public.w4_nova_tabela' | cut -c1-5)" "42501" "tabela nova · anon nada"
eq "$(estado service_role 'insert into public.w4_nova_tabela (v) values (4) returning v')" "ok:4" "tabela nova · service_role (backend) grava"
P -c "drop table public.w4_nova_tabela" >/dev/null; PA -c "drop sequence public.w4_nova_seq_admin" >/dev/null
eq "$(P -c "select prosecdef::text||'|'||pg_get_userbyid(proowner) from pg_proc where oid='public.trigger_funnel_url_change()'::regprocedure")" "true|volc_agregador_funil" "agregação do funil roda como o papel dedicado (SECURITY DEFINER)"
eq "$(P -c "select rolsuper::text||'|'||rolbypassrls::text||'|'||rolcanlogin::text from pg_roles where rolname='volc_agregador_funil'")" "false|false|false" "volc_agregador_funil: não superusuário, sem BYPASSRLS, sem login"
eq "$(estado authenticated "select public.volc_pode_editar_funil('222222222','p2v.example/x')" "$OPER")" "ok:f" "escopo: operador não edita funil de campanha sem vínculo"
eq "$(estado authenticated "select public.volc_pode_editar_funil('123456789','p2v.example/x')" "$OPER")" "ok:f" "escopo: operador não pendura URL de outro domínio na própria campanha"
eq "$(estado authenticated "select public.volc_pode_editar_funil('123456789','https://www.p1.example/z')" "$OPER")" "ok:t" "escopo: operador edita a própria campanha no domínio do projeto"
eq "$(P -c "select array_to_string(proconfig, ',') from pg_proc where oid='public.trigger_calculate_adsense_campaign_revenue()'::regprocedure")" "search_path=public, pg_temp" "agregação do funil com search_path fixo"

echo "▶ 6. rollback"
PA -c "REVOKE SELECT ON public.projects FROM authenticated" >/dev/null
aplicar supabase_admin v19_10_rollback.sql && nao "rollback passou por cima de ACL alterada" \
  || { grep -q "mudaram depois da v19_10" "$R/aplicar-v19_10_rollback.sql.log" && ok "rollback ABORTA se a ACL mudou depois" || nao "rollback (ACL) falhou por outro motivo"; }
PA -c "GRANT SELECT ON public.projects TO authenticated" >/dev/null
PA -c "ALTER POLICY w4a_update ON public.projects USING (false)" >/dev/null
aplicar supabase_admin v19_10_rollback.sql && nao "rollback passou por cima de policy alterada" \
  || { grep -q "mudaram depois da v19_10" "$R/aplicar-v19_10_rollback.sql.log" && ok "rollback ABORTA se uma policy criada por ela foi alterada" || nao "rollback (policy alterada) falhou por outro motivo"; }
PA -c "ALTER POLICY w4a_update ON public.projects USING (true)" >/dev/null
PA -c "CREATE POLICY w4_teste_restritiva ON public.daily_campaign_metrics AS RESTRICTIVE FOR SELECT TO authenticated USING (false)" >/dev/null
aplicar supabase_admin v19_10_rollback.sql && nao "rollback passou por cima de policy nova" \
  || { grep -q "mudaram depois da v19_10" "$R/aplicar-v19_10_rollback.sql.log" && ok "rollback ABORTA se apareceu policy nova numa relação que ela mudou" || nao "rollback (policy nova) falhou por outro motivo"; }
PA -c "DROP POLICY w4_teste_restritiva ON public.daily_campaign_metrics" >/dev/null
aplicar supabase_admin v19_10_rollback.sql && ok "rollback aplicou" || nao "rollback"
fp "$R/fp-rollback.txt"
diff "$R/fp0.txt" "$R/fp-rollback.txt" > "$R/diff-fp0-rollback.txt" && ok "rollback devolve o fingerprint EXATO de antes da v19_10 (inclui funções do funil de volta a INVOKER)" || nao "rollback deixou resíduo (diff-fp0-rollback.txt)"
defacl "$R/defacl-rollback.txt"
[ -s "$R/defacl-rollback.txt" ] && diff -q "$R/defacl0.txt" "$R/defacl-rollback.txt" >/dev/null && ok "rollback devolve o default ACL de public exato" || nao "default ACL diferente (ou vazio) depois do rollback"
# mutação da própria checagem: um GRANT padrão a mais tem de aparecer como diferença
PA -c "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO anon" >/dev/null
defacl "$R/defacl-mutado.txt"
diff -q "$R/defacl0.txt" "$R/defacl-mutado.txt" >/dev/null && nao "a checagem de default ACL não vê um GRANT a mais (prova vazia)" || ok "a checagem de default ACL pega um GRANT padrão a mais (mutação)"
PA -c "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE SELECT ON TABLES FROM anon" >/dev/null
defacl "$R/defacl-desmutado.txt"; diff -q "$R/defacl0.txt" "$R/defacl-desmutado.txt" >/dev/null && ok "default ACL volta ao da base depois de desfazer a mutação" || nao "default ACL não voltou depois da mutação"
aplicar supabase_admin v19_10_rollback.sql && ok "rollback idempotente" || nao "rollback idempotente"
fluxos "$R/fluxos-pos-rollback.txt"
eq "$(comparar "$R/fluxos-antes.txt" "$R/fluxos-pos-rollback.txt" "$R/dif-pos-rollback.txt")" "0" "fluxos depois do rollback = antes"
eq "$(anon_fechado)" "FECHADO" "anon segue FECHADO depois do rollback da v19_10"

echo "▶ 7. reaplicação e ordem de rollback"
aplicar supabase_admin v19_10_authenticated_minimo.sql && ok "v19_10 reaplicou" || nao "reaplicação"
fp "$R/fp2.txt"
diff -q "$R/fp1.txt" "$R/fp2.txt" >/dev/null && ok "fingerprint idêntico entre 1ª e 2ª aplicação" || nao "fingerprint divergiu"
aplicar supabase_admin v19_10_authenticated_minimo.sql && nao "v19_10 reaplicou por cima" \
  || { grep -q "já aplicada" "$R/aplicar-v19_10_authenticated_minimo.sql.log" && ok "v19_10 por cima recusada pela guarda" || nao "falhou por outro motivo"; }
aplicar supabase_admin v19_99_rollback.sql && nao "v19_99 passou com a v19_10 aplicada" \
  || ok "ordem: v19_99 recusa enquanto a v19_10 está aplicada (reverter a v19_10 antes)"

for f in v19_10_authenticated_minimo v19_10_rollback; do echo "$f.sql $(sha "$W4_MIG/$f.sql")"; done > "$R/pacote-sha256.txt"
P -f - < "$FP" > "$R/fp-final.out" 2>&1
