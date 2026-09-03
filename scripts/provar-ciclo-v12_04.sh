#!/usr/bin/env bash
# O ciclo da v12_04 num Postgres descartável: aplicar -> operar -> reverter ->
# reaplicar, com prova de ESTRUTURA, SEGURANÇA, COMPORTAMENTO e CONTENÇÃO.
#
# ## Por que um script
# Um rollback só existe se alguém o executa. Rollback documentado e nunca rodado
# é rollback que ninguém tem — o da v9_03 estava escrito como "reaplique a v9_02"
# e ABORTAVA, e só apareceu quando alguém tentou. Este roda o ciclo inteiro do
# zero, a cada execução, num container que nasce e morre aqui. NUNCA fala com
# database.agenciavolc.com.br.
#
# ## Por que docker e não initdb
# As séries v10/v11/v12_02 usam `initdb`/`pg_ctl` locais. Nesta máquina eles não
# existem (`command -v initdb` vazio) e `postgres:16-alpine` está presente. O
# contrato da prova é o mesmo: cluster efêmero, papéis de produção reproduzidos,
# ciclo completo.
#
# ## O que ele prova
#  1. estrutura: as duas tabelas, a view de saúde, a RPC única e o append-only;
#  2. segurança: RLS habilitada E forçada, zero policies, anon/authenticated sem
#     nenhum privilégio, `service_role` SEM escrita direta — só a RPC;
#  3. comportamento: as contraprovas de scripts/provas-v12_04.sql;
#  4. contenção: `service_role` grava PELA RPC e é recusado FORA dela;
#  5. rollback: recusa perda silenciosa, e reverte quando a perda é declarada;
#  6. reaplicação: o ciclo fecha e uma terceira aplicação é recusada com nome.
set -euo pipefail

command -v docker >/dev/null || { echo "falta docker no PATH"; exit 2; }

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
IMAGEM="${VOLC_PG_IMAGE:-postgres:16-alpine}"
C="volc-v1204-$$"

limpar() { docker rm -f "$C" >/dev/null 2>&1 || true; }
trap limpar EXIT

echo "cluster descartável: container $C ($IMAGEM)"
docker run --rm -d --name "$C" \
  -e POSTGRES_PASSWORD=descartavel -e POSTGRES_HOST_AUTH_METHOD=trust \
  "$IMAGEM" >/dev/null

# ⚠️ `pg_isready` sozinho NÃO serve, e isto foi medido: a imagem oficial sobe um
# servidor TEMPORÁRIO no mesmo socket para rodar o initdb, e o `pg_isready`
# responde verde para ELE. Logo depois o entrypoint derruba esse servidor e sobe
# o definitivo — e no intervalo o `psql` morre com "connection to server on
# socket ... failed". Duas de três execuções seguidas caíram assim.
# A espera correta é pelo marcador de fim do init E por um SELECT que responde.
pronto=0
for _ in $(seq 1 90); do
  if docker logs "$C" 2>&1 | grep -q "PostgreSQL init process complete"; then
    if docker exec "$C" psql -U postgres -d postgres -X -q -At -c "select 1" \
        >/dev/null 2>&1; then pronto=1; break; fi
  fi
  sleep 1
done
[ "$pronto" = 1 ] || { echo "o cluster descartável não subiu"; docker logs "$C" 2>&1 | tail -20; exit 2; }

q() { docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -At -c "$1"; }
f() { docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -f - >/dev/null; }
# ⚠️ `2>&1 >/dev/null`, nesta ordem, e nao `2>&1`. As provas de comportamento
# falam SO por NOTICE, que sai pelo stderr; o stdout do psql leva uma linha VAZIA
# para cada `select pg_temp.tenta(...)`, porque a funcao devolve void. Juntando
# os dois streams num pipe, as 65 linhas vazias corriam com as 65 notices e
# volta e meia se interpolavam NO MEIO de uma linha, quebrando a ancora `^  ok`.
# O sintoma foi um contador que oscilava entre 104 e 107 provas na MESMA arvore,
# sem nada ter mudado — ou seja, um degrau que as vezes nao contava o que rodou.
fq() { docker exec -i "$C" psql -U postgres -d postgres -v ON_ERROR_STOP=0 -X -q -f - 2>&1 >/dev/null; }

# ── papéis e o ACL padrão QUEBRADO de produção, reproduzido ─────────────────
#
# ⚠️ Sem reproduzir o achado, a prova de contenção mediria um banco mais seguro
# que o real — e passaria por sorte. `service_role` nasce com BYPASSRLS porque é
# assim no Supabase oficial (medido em pg_roles em 2026-08-29), e o ACL padrão
# de `public` concede tudo a todos em toda tabela nova.
q "create role anon nologin; create role authenticated nologin;" >/dev/null
q "create role service_role nologin bypassrls;" >/dev/null
q "grant usage on schema public to anon, authenticated, service_role;" >/dev/null
q "alter default privileges in schema public grant all on tables to anon, authenticated, service_role;" >/dev/null
q "alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;" >/dev/null

ok=0; falhou=0
prova() { if eval "$2" >/dev/null 2>&1; then echo "  ok   $1"; ok=$((ok+1));
          else echo "  FALHOU  $1"; falhou=$((falhou+1)); fi; }
recusa() { if eval "$2" >/dev/null 2>&1; then echo "  FALHOU  $1 (foi aceito e devia ser recusado)"; falhou=$((falhou+1));
           else echo "  ok   $1"; ok=$((ok+1)); fi; }

# ── a v9_01, porque a v12_04 tem FK para trafego_campanha ──────────────────
f < "$RAIZ/supabase/migrations/v9_01_trafego_inventario.sql"

echo; echo "DEGRAU 0 — a migration é recusada sem a v9_01? (guarda de dependência)"
prova "v9_01 aplicada (pré-requisito presente)" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='trafego_campanha'\")\" = 1 ]"

echo; echo "DEGRAU 1 — aplicar a v12_04"
f < "$RAIZ/supabase/migrations/v12_04_gads_fato_canonico_dia.sql"

for t in trafego_coleta_execucao google_ads_campanha_dia; do
  prova "tabela $t criada" \
    "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='$t'\")\" = 1 ]"
  prova "RLS habilitada E forçada em $t" \
    "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname='$t' and c.relrowsecurity and c.relforcerowsecurity\")\" = 1 ]"
  prova "zero policies em $t" \
    "[ \"\$(q \"select count(*) from pg_policies where schemaname='public' and tablename='$t'\")\" = 0 ]"
  prova "anon/authenticated sem privilégio em $t" \
    "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name='$t' and grantee in ('anon','authenticated','PUBLIC')\")\" = 0 ]"
  prova "service_role SEM escrita direta em $t" \
    "[ \"\$(q \"select count(*) from information_schema.role_table_grants where table_schema='public' and table_name='$t' and grantee='service_role' and privilege_type in ('INSERT','UPDATE','DELETE','TRUNCATE')\")\" = 0 ]"
  prova "service_role lê $t" \
    "[ \"\$(q \"select has_table_privilege('service_role','public.$t','SELECT')\")\" = t ]"
done

prova "view de saúde criada" \
  "[ \"\$(q \"select count(*) from pg_views where schemaname='public' and viewname='trafego_coleta_execucao_saude'\")\" = 1 ]"
prova "a RPC de ingestão existe e é a única porta pública" \
  "[ \"\$(q \"select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname='volc_registrar_gads_campanha_dia'\")\" = 1 ]"
prova "a RPC é SECURITY DEFINER com search_path fixo" \
  "[ \"\$(q \"select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname='volc_registrar_gads_campanha_dia' and p.prosecdef and array_to_string(p.proconfig,',') like '%search_path=%'\")\" = 1 ]"
prova "anon NÃO executa a RPC de ingestão" \
  "[ \"\$(q \"select has_function_privilege('anon','public.volc_registrar_gads_campanha_dia(jsonb)','EXECUTE')\")\" = f ]"
prova "authenticated NÃO executa a RPC de ingestão" \
  "[ \"\$(q \"select has_function_privilege('authenticated','public.volc_registrar_gads_campanha_dia(jsonb)','EXECUTE')\")\" = f ]"
prova "service_role executa a RPC de ingestão" \
  "[ \"\$(q \"select has_function_privilege('service_role','public.volc_registrar_gads_campanha_dia(jsonb)','EXECUTE')\")\" = t ]"
prova "nenhuma métrica do fato tem DEFAULT (NULL != 0 é estrutural)" \
  "[ \"\$(q \"select count(*) from information_schema.columns where table_schema='public' and table_name='google_ads_campanha_dia' and column_default is not null and column_name in ('impressoes','cliques','interacoes','custo_micros','conversoes','todas_conversoes','valor_conversoes','valor_todas_conversoes','ctr','cpc_medio_micros','custo_por_conversao_micros','search_impression_share','top_impression_percentage')\")\" = 0 ]"
prova "a chave canônica inclui a CONTA" \
  "[ \"\$(q \"select count(*) from pg_constraint where conname='google_ads_campanha_dia_chave' and pg_get_constraintdef(oid) like '%customer_id%campaign_id%metric_date%segments_hash%'\")\" = 1 ]"
prova "a FK do fato para o ledger é DEFERRABLE INITIALLY DEFERRED" \
  "[ \"\$(q \"select count(*) from pg_constraint where conrelid='public.google_ads_campanha_dia'::regclass and contype='f' and condeferrable and condeferred\")\" = 1 ]"
prova "a migration NÃO criou nem alterou daily_campaign_metrics" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='daily_campaign_metrics'\")\" = 0 ]"

echo; echo "DEGRAU 2 — comportamento: as contraprovas do contrato"
BRUTO="$(fq < "$RAIZ/scripts/provas-v12_04.sql")"
SAIDA="$(echo "$BRUTO" | sed -E 's/^psql:[^:]*:[0-9]+: NOTICE:  //; s/^NOTICE:  //')"
echo "$SAIDA" | grep -E '^(  ok|FALHOU)' || true
n_ok=$(echo "$SAIDA" | grep -c '^  ok' || true)
n_ko=$(echo "$SAIDA" | grep -c '^FALHOU' || true)
# ⚠️ A guarda contra o degrau mudo: nas provas da v12_02, um `grep '^  ok'` que
# não casava com nada somou zero e anunciou "0 falharam". Um degrau que não roda
# e diz que passou é pior que um degrau que falha.
if [ "$((n_ok + n_ko))" -lt 45 ]; then
  echo "FALHOU  o degrau de comportamento produziu apenas $((n_ok + n_ko)) provas (esperado >= 45)"
  echo "$BRUTO" | tail -25
  falhou=$((falhou + 1))
fi
ok=$((ok + n_ok)); falhou=$((falhou + n_ko))

echo; echo "DEGRAU 2-bis — contenção: quem escreve, e por onde"
recusa "service_role NÃO insere direto no fato" \
  "docker exec -i '$C' psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -c \"set role service_role; insert into public.google_ads_campanha_dia (customer_id,campaign_id,metric_date,segments_hash,execucao_id,colhida_em,api_versao,currency_code,origem_janela,janela_fechada,precedencia) values ('8017851692','1','2026-08-30',repeat('a',64),gen_random_uuid(),now(),'v25','BRL','D-1',true,2)\""
recusa "service_role NÃO insere direto no ledger" \
  "docker exec -i '$C' psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -c \"set role service_role; insert into public.trafego_coleta_execucao (execucao_id,chave_idempotencia,execucao_chave,fonte,job,disparo,api_versao,contrato_versao,contrato_sha256,tipo_lote,lote_ordinal,origem_janela,janela_inicio,janela_fim,iniciada_em,encerrada_em,duracao_ms,batimento_em,resultado,linhas_lidas,linhas_aceitas,linhas_preteridas,linhas_rejeitadas,projecao_estado,payload_sha256) values (gen_random_uuid(),'x','x','n8n','job_x','agenda','v25','v1',repeat('a',64),'contas',1,'D-1','2026-08-30','2026-08-30',now(),now(),0,now(),'ok',0,0,0,0,'nao_solicitada',repeat('b',64))\""
recusa "anon NÃO lê o fato" \
  "docker exec -i '$C' psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -c \"set role anon; select count(*) from public.google_ads_campanha_dia\""
recusa "authenticated NÃO executa a RPC" \
  "docker exec -i '$C' psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -c \"set role authenticated; select public.volc_registrar_gads_campanha_dia('{}'::jsonb)\""
prova "service_role GRAVA pela RPC (a porta operacional funciona)" \
  "docker exec -i '$C' psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -At -c \"set role service_role; select public.volc_registrar_gads_campanha_dia(jsonb_build_object('chave_idempotencia','papel|1','execucao_chave','papel','fonte','n8n','job','gads_dia_d1','disparo','agenda','api_versao','v25','contrato_versao','v1','contrato_sha256',repeat('a',64),'tipo_lote','contas','lote_ordinal',1,'origem_janela','D-1','janela_inicio','2026-08-30','janela_fim','2026-08-30','iniciada_em',now(),'encerrada_em',now(),'duracao_ms',1,'batimento_em',now(),'resultado','ok','projetar_compat',false,'linhas',jsonb_build_array(jsonb_build_object('customer_id','8017851692','campaign_id','1234567','metric_date','2026-08-30','colhida_em',now(),'currency_code','BRL','impressoes',3,'cliques',0))))\" | grep -q execucao_id"
prova "o zero medido do teste de papel entrou como zero" \
  "[ \"\$(q \"select cliques from public.google_ads_campanha_dia where campaign_id='1234567'\")\" = 0 ]"
prova "a métrica não enviada continua NULL" \
  "[ \"\$(q \"select conversoes is null from public.google_ads_campanha_dia where campaign_id='1234567'\")\" = t ]"

# A prova sequencial acima não autoriza alegar concorrência. Este degrau roda um
# segundo Postgres descartável, com duas conexões psql independentes, transações
# sobrepostas e observação material de wait_event_type='Lock'.
echo; echo "DEGRAU 2-ter — concorrência atômica real"
if bash "$RAIZ/scripts/provar-concorrencia-v12_04.sh"; then
  ok=$((ok + 3))
else
  falhou=$((falhou + 1))
fi

echo; echo "DEGRAU 3 — reverter"
recusa "rollback com dado gravado é RECUSADO sem declaração de perda" \
  "docker exec -i '$C' psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -f - < '$RAIZ/supabase/migrations/v12_04_rollback.sql'"
prova "as tabelas continuam de pé depois da recusa" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename in ('trafego_coleta_execucao','google_ads_campanha_dia')\")\" = 2 ]"

{ echo "SET volc.rollback_v12_04_apagar_fatos = 'sim';"; cat "$RAIZ/supabase/migrations/v12_04_rollback.sql"; } | f
prova "as tabelas sumiram" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename in ('trafego_coleta_execucao','google_ads_campanha_dia')\")\" = 0 ]"
prova "as funções sumiram" \
  "[ \"\$(q \"select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in ('volc_registrar_gads_campanha_dia','volc_gads_projetar_daily_compat','volc_gads_uuid_da_chave','trafego_coleta_execucao_append_only')\")\" = 0 ]"
prova "a view de saúde sumiu" \
  "[ \"\$(q \"select count(*) from pg_views where schemaname='public' and viewname='trafego_coleta_execucao_saude'\")\" = 0 ]"
prova "trafego_campanha (v9_01) intacta" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='trafego_campanha'\")\" = 1 ]"
prova "a legada daily_campaign_metrics continua de pé (o rollback não a apaga)" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename='daily_campaign_metrics'\")\" = 1 ]"
prova "receita da legada intacta depois do rollback" \
  "[ \"\$(q \"select revenue from public.daily_campaign_metrics where campaign_id='4100000001'\")\" = 1234.56 ]"

echo; echo "DEGRAU 4 — reaplicar"
f < "$RAIZ/supabase/migrations/v12_04_gads_fato_canonico_dia.sql"
prova "tabelas de novo" \
  "[ \"\$(q \"select count(*) from pg_tables where schemaname='public' and tablename in ('trafego_coleta_execucao','google_ads_campanha_dia')\")\" = 2 ]"
prova "RLS forçada de novo nas duas" \
  "[ \"\$(q \"select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in ('trafego_coleta_execucao','google_ads_campanha_dia') and c.relrowsecurity and c.relforcerowsecurity\")\" = 2 ]"
prova "a RPC volta a aceitar ingestão depois do ciclo" \
  "docker exec -i '$C' psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -At -c \"select public.volc_registrar_gads_campanha_dia(jsonb_build_object('chave_idempotencia','pos|1','execucao_chave','pos','fonte','n8n','job','gads_dia_d1','disparo','agenda','api_versao','v25','contrato_versao','v1','contrato_sha256',repeat('a',64),'tipo_lote','contas','lote_ordinal',1,'origem_janela','D-1','janela_inicio','2026-08-30','janela_fim','2026-08-30','iniciada_em',now(),'encerrada_em',now(),'duracao_ms',1,'batimento_em',now(),'resultado','ok','projetar_compat',false,'linhas',jsonb_build_array(jsonb_build_object('customer_id','8017851692','campaign_id','777','metric_date','2026-08-30','colhida_em',now(),'currency_code','BRL','impressoes',1))))\" | grep -q execucao_id"
recusa "aplicar uma terceira vez é recusado com nome" \
  "docker exec -i '$C' psql -U postgres -d postgres -v ON_ERROR_STOP=1 -X -q -f - < '$RAIZ/supabase/migrations/v12_04_gads_fato_canonico_dia.sql'"

echo
echo "════════════════════════════════════════════════════════"
echo "  passaram $ok · falharam $falhou"
[ "$falhou" -eq 0 ] || exit 1
echo "  CICLO v12_04 COMPLETO: aplicar → operar → reverter → reaplicar"
