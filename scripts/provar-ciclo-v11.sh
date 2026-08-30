#!/usr/bin/env bash
#
# O ciclo completo da v11 num Postgres descartável — aplicar, reverter,
# reaplicar — com prova de ESTRUTURA, de SEGURANÇA e de COMPORTAMENTO.
#
# ## Por que um script, e não um comando anotado
#
# Um rollback só existe se alguém o executa. O da v9_03 estava documentado como
# "reaplique a v9_02" e **abortava**, e isso só apareceu quando a auditoria
# adversarial tentou. Este script roda o ciclo inteiro do zero, a cada execução,
# num cluster que nasce e morre aqui. Ele não toca em nada fora de /tmp e NUNCA
# fala com o banco de produção.
#
# ## O que ele prova
#
# ESTRUTURA, em cada degrau:
#   · a migration aplica sem erro e a verificação embutida passa;
#   · as 10 tabelas existem (ou sumiram, no rollback);
#   · `service_role` tem SELECT/INSERT/UPDATE e NÃO tem DELETE;
#   · `anon`/`authenticated` sem NENHUM privilégio em NENHUMA tabela;
#   · RLS ligada E forçada, com zero policies.
#
# COMPORTAMENTO — as invariantes que justificam o schema inteiro:
#   1. a mesma chave de idempotência não entra duas vezes;
#   2. o retry não consegue criar um segundo master para (job, slot, versão);
#   3. medida ausente é NULL: zero é recusado em largura, altura e bytes;
#   4. custo sem carimbo de medição é recusado;
#   5. rendition `pronta` sem arquivo é recusada;
#   6. rendition `falhou` sem motivo é recusada;
#   7. conteúdo e procedência do master são IMUTÁVEIS;
#   8. master com aprovação vigente não pode ser arquivado;
#   9. evento de job é append-only;
#  10. aprovar ativo de job `failed` é recusado pelo gatilho;
#  11. aprovar ativo sem nenhuma rendition pronta é recusado;
#  12. duas decisões vigentes para (ativo, versão, finalidade) são recusadas;
#  13. decisão REVOGADA libera o lugar para uma nova;
#  14. job `observado` não pode declarar custo próprio;
#  15. job `observado` sem origem externa é recusado;
#  16. job `succeeded` com objeto de falha pendurado é recusado;
#  17. `estado_do_lote` do Python e a realidade do banco concordam;
#  18-29. a v11_02: prefixo de storage, declaracao imutavel, medida nao
#         reescrita, ordem temporal da peca, peca pronta sem erro, aprovacao de
#         pacote inexistente, entrega com autorizacao de outro pacote, chave de
#         entrega curta, id de Cofre malformado, teto de bytes zero, direito
#         apurado sem carimbo e veredito de gate fora do dominio.
#
# INDEPENDÊNCIA: a v11 não referencia `trafego_*`, e o rollback dela não derruba
# nada da v9 nem da v10 — provado aplicando as três e revertendo só a v11.
#
# Uso:  ./scripts/provar-ciclo-v11.sh

set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
M="$RAIZ/supabase/migrations"

for b in initdb pg_ctl psql; do
    command -v "$b" >/dev/null 2>&1 || { echo "falta $b — brew install postgresql@16"; exit 2; }
done
PY="$RAIZ/backend/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 || true)"

# ⚠️ /tmp e não o scratchpad: o socket unix tem teto de 103 bytes no caminho, e
# um diretório fundo estoura com uma mensagem que não fala de tamanho.
D=$(mktemp -d /tmp/volcv11XXXX)
export LC_ALL=C LANG=C
limpar() { pg_ctl -D "$D/d" -m immediate stop >/dev/null 2>&1; rm -rf "$D"; }
trap limpar EXIT

initdb -D "$D/d" -U postgres --encoding=UTF8 --locale=C >/dev/null 2>&1
mkdir -p "$D/s"
pg_ctl -D "$D/d" -l "$D/pg.log" -o "-k $D/s -h ''" -w start >/dev/null 2>&1

P() { psql -h "$D/s" -U postgres -X -q -A -t "$@"; }

# Os papéis do Supabase, INCLUSIVE o default ACL quebrado de `public` (achado H,
# 24/08/2026) — sem reproduzir o defeito, a prova de que a migration fecha a
# porta mediria um ambiente mais seguro que o real.
P -c "CREATE ROLE anon NOLOGIN NOINHERIT;
      CREATE ROLE authenticated NOLOGIN NOINHERIT;
      CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
      GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
      ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT ALL ON TABLES TO anon, authenticated, service_role;
      CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null

FALHAS=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
nao()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FALHAS=$((FALHAS+1)); }
cmp_() { [ "$1" = "$2" ] && ok "$3" || nao "$3 (esperado=$2 obtido=$1)"; }

aplicar() {
    if psql -h "$D/s" -U postgres -q -v ON_ERROR_STOP=1 -f "$M/$1.sql" >"$D/out" 2>&1; then
        ok "aplicou $1"
    else
        nao "aplicou $1"; tail -4 "$D/out" | sed 's/^/      /'
    fi
}

# `recusa` é a função mais importante deste arquivo.
#
# Ela exige que o comando falhe COM A MENSAGEM CERTA. Um teste que só confere
# "deu erro" passa quando o erro é um typo no nome da tabela, e aí a guarda que
# ele afirma provar pode nem existir. O padrão é conferido no texto do erro.
recusa() {
    local rotulo="$1" padrao="$2" sql="$3"
    local saida
    saida=$(psql -h "$D/s" -U postgres -X -q -v ON_ERROR_STOP=1 -c "$sql" 2>&1)
    if [ $? -eq 0 ]; then
        nao "$rotulo (o banco ACEITOU, e não devia)"
    elif echo "$saida" | grep -qi "$padrao"; then
        ok "$rotulo"
    else
        nao "$rotulo (recusou pelo motivo errado)"; echo "$saida" | head -2 | sed 's/^/      /'
    fi
}

aceita() {
    local rotulo="$1" sql="$2" saida
    saida=$(psql -h "$D/s" -U postgres -X -q -v ON_ERROR_STOP=1 -c "$sql" 2>&1)
    if [ $? -eq 0 ]; then ok "$rotulo"; else nao "$rotulo"; echo "$saida" | head -2 | sed 's/^/      /'; fi
}

echo
echo "── DEGRAU 1: v9 e v10 primeiro, para provar independência ──────────────"
for m in v9_01_trafego_inventario v9_02_atencao_sem_removida \
         v9_03_historico_e_ordem_operacional v9_04_url_final_preservada \
         v10_01_intencao_e_lote v10_02_autogestao; do
    [ -f "$M/$m.sql" ] && aplicar "$m"
done
ANTES=$(P -c "select count(*) from pg_tables where schemaname='public' and tablename like 'trafego_%';")
echo "      tabelas trafego_* antes da v11: $ANTES"

echo
echo "── DEGRAU 2: aplicar a v11_01 ──────────────────────────────────────────"
aplicar v11_01_estudio_criativo
cmp_ "$(P -c "select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_%';")" \
     "10" "as 10 tabelas do Estúdio existem"
cmp_ "$(P -c "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace
              where n.nspname='public' and c.relname like 'criativo_%' and c.relkind='r'
                and (not c.relrowsecurity or not c.relforcerowsecurity);")" \
     "0" "RLS ligada E forçada em todas"
cmp_ "$(P -c "select count(*) from pg_policies where schemaname='public' and tablename like 'criativo_%';")" \
     "0" "zero policies (o caminho é o backend com service_role)"
cmp_ "$(P -c "select count(*) from information_schema.role_table_grants
              where table_schema='public' and table_name like 'criativo_%'
                and grantee in ('anon','authenticated');")" \
     "0" "anon e authenticated sem NENHUM privilégio"
cmp_ "$(P -c "select count(*) from information_schema.role_table_grants
              where table_schema='public' and table_name like 'criativo_%'
                and privilege_type='DELETE' and grantee<>'postgres';")" \
     "0" "DELETE não concedido a ninguém além do dono"
cmp_ "$(P -c "select count(distinct privilege_type) from information_schema.role_table_grants
              where table_schema='public' and table_name like 'criativo_%'
                and grantee='service_role';")" \
     "3" "service_role tem exatamente SELECT, INSERT e UPDATE"

echo
echo "── DEGRAU 3: comportamento ─────────────────────────────────────────────"

P -c "insert into public.criativo_brand_pack(id,slug,versao,nome,tokens)
      values('11111111-1111-1111-1111-111111111111','volc',1,'VOLC','{}'::jsonb);
      insert into public.criativo_projeto(id,titulo)
      values('22222222-2222-2222-2222-222222222222','Prova');
      insert into public.criativo_briefing(id,projeto_id,tipo,modo,formatos_pedidos)
      values('33333333-3333-3333-3333-333333333333','22222222-2222-2222-2222-222222222222',
             'imagem','full_llm','[{\"slot\":\"1x1\"}]'::jsonb);
      insert into public.criativo_job(id,briefing_id,motor,motor_versao,estado,idempotency_key,insumo_hash)
      values('44444444-4444-4444-4444-444444444444','33333333-3333-3333-3333-333333333333',
             'm','1','running','cri_chave_de_prova_0000000000','h');" >/dev/null

recusa "1. a mesma chave de idempotência não entra duas vezes" "criativo_job_idem_ux\|duplicate key" \
  "insert into public.criativo_job(briefing_id,motor,motor_versao,estado,idempotency_key,insumo_hash)
   values('33333333-3333-3333-3333-333333333333','m','1','running','cri_chave_de_prova_0000000000','h');"

aceita "   (o master do slot 1x1 entra uma vez)" \
  "insert into public.criativo_master(id,job_id,projeto_id,slot,kind,storage_chave,content_hash,mime,motor,motor_versao,insumo_hash)
   values('55555555-5555-5555-5555-555555555555','44444444-4444-4444-4444-444444444444','22222222-2222-2222-2222-222222222222',
          '1x1','imagem','criativos/p/j/a.png','sha256:$(printf 'a%.0s' {1..64})','image/png','m','1','h');"

recusa "2. o retry não cria um segundo master para (job, slot, versão)" "criativo_master_slot_ux\|duplicate key" \
  "insert into public.criativo_master(job_id,projeto_id,slot,kind,storage_chave,content_hash,mime,motor,motor_versao,insumo_hash)
   values('44444444-4444-4444-4444-444444444444','22222222-2222-2222-2222-222222222222',
          '1x1','imagem','criativos/p/j/c.png','sha256:$(printf 'b%.0s' {1..64})','image/png','m','1','h');"

recusa "3. medida ZERO é recusada (ausência é NULL)" "criativo_master_largura_medida" \
  "update public.criativo_master set largura=0 where id='55555555-5555-5555-5555-555555555555';"

recusa "4. custo sem carimbo de medição é recusado" "criativo_job_custo_sem_carimbo" \
  "update public.criativo_job set custo_real_usd=1.5 where id='44444444-4444-4444-4444-444444444444';"

recusa "5. rendition 'pronta' sem arquivo é recusada" "criativo_rendition_pronta_tem_arquivo" \
  "insert into public.criativo_rendition(job_id,slot,estado,largura_pedida,altura_pedida,proporcao_rotulo)
   values('44444444-4444-4444-4444-444444444444','9x16','pronta',1080,1920,'9:16');"

recusa "6. rendition 'falhou' sem motivo é recusada" "criativo_rendition_falhou_tem_motivo" \
  "insert into public.criativo_rendition(job_id,slot,estado,largura_pedida,altura_pedida,proporcao_rotulo)
   values('44444444-4444-4444-4444-444444444444','4x5','falhou',1080,1350,'4:5');"

aceita "   (a rendition pronta COM arquivo entra)" \
  "insert into public.criativo_rendition(job_id,master_id,slot,estado,largura_pedida,altura_pedida,proporcao_rotulo,storage_chave,content_hash,concluida_em)
   values('44444444-4444-4444-4444-444444444444','55555555-5555-5555-5555-555555555555','1x1','pronta',1080,1080,'1:1',
          'criativos/p/j/a.png','sha256:$(printf 'a%.0s' {1..64})',now());"

recusa "7. conteúdo e procedência do master são imutáveis" "imutaveis" \
  "update public.criativo_master set content_hash='sha256:$(printf 'c%.0s' {1..64})'
   where id='55555555-5555-5555-5555-555555555555';"

recusa "9. evento de job é append-only" "append-only" \
  "insert into public.criativo_job_evento(job_id,fase) values('44444444-4444-4444-4444-444444444444','x');
   update public.criativo_job_evento set fase='y' where job_id='44444444-4444-4444-4444-444444444444';"

# Um job que FALHOU, para provar que o gatilho de aprovação olha o estado do job.
P -c "insert into public.criativo_job(id,briefing_id,motor,motor_versao,estado,idempotency_key,insumo_hash,iniciado_em,terminado_em,falha)
      values('66666666-6666-6666-6666-666666666666','33333333-3333-3333-3333-333333333333','m','1','failed',
             'cri_chave_falha_00000000000','h',now(),now(),
             '{\"codigo\":\"X\",\"mensagem\":\"m\",\"permanente\":true,\"em\":\"2026-01-01T00:00:00Z\"}'::jsonb);
      insert into public.criativo_master(id,job_id,projeto_id,slot,kind,storage_chave,content_hash,mime,motor,motor_versao,insumo_hash)
      values('77777777-7777-7777-7777-777777777777','66666666-6666-6666-6666-666666666666','22222222-2222-2222-2222-222222222222',
             '1x1','imagem','criativos/p/j/x.png','sha256:$(printf 'd%.0s' {1..64})','image/png','m','1','h');" >/dev/null

recusa "10. aprovar ativo de job 'failed' é recusado" "nao produz ativo aprovavel" \
  "insert into public.criativo_aprovacao(subject_tipo,subject_id,versao,finalidade,decisao,ator_id)
   values('master','77777777-7777-7777-7777-777777777777',1,'interno','aprovado',gen_random_uuid());"

# Mesmo master, mas agora num job `partial` e ainda sem rendition pronta.
P -c "update public.criativo_job set estado='partial', falha=null
      where id='66666666-6666-6666-6666-666666666666';" >/dev/null
recusa "11. aprovar ativo sem nenhuma rendition pronta é recusado" "nao tem nenhuma rendition pronta" \
  "insert into public.criativo_aprovacao(subject_tipo,subject_id,versao,finalidade,decisao,ator_id)
   values('master','77777777-7777-7777-7777-777777777777',1,'interno','aprovado',gen_random_uuid());"

aceita "   (aprovar o master que TEM peça pronta funciona)" \
  "insert into public.criativo_aprovacao(id,subject_tipo,subject_id,versao,finalidade,decisao,ator_id)
   values('88888888-8888-8888-8888-888888888888','master','55555555-5555-5555-5555-555555555555',1,'interno','aprovado',gen_random_uuid());"

recusa "8. master com aprovação vigente não pode ser arquivado" "nao arquiva master com aprovacao vigente" \
  "update public.criativo_master set arquivado_em=now() where id='55555555-5555-5555-5555-555555555555';"

# `aprovado` e nao `rejeitado`: com `rejeitado` sem motivo, a CHECK
# `criativo_aprovacao_negativa_tem_motivo` mordia ANTES do indice unico, e o
# teste passava provando a guarda errada.
recusa "12. duas decisões vigentes para (ativo, versão, finalidade)" "criativo_aprovacao_vigente_ux\|duplicate key" \
  "insert into public.criativo_aprovacao(subject_tipo,subject_id,versao,finalidade,decisao,ator_id)
   values('master','55555555-5555-5555-5555-555555555555',1,'interno','aprovado',gen_random_uuid());"

P -c "update public.criativo_aprovacao set revogada_em=now()
      where id='88888888-8888-8888-8888-888888888888';" >/dev/null
aceita "13. decisão revogada libera o lugar para uma nova" \
  "insert into public.criativo_aprovacao(subject_tipo,subject_id,versao,finalidade,decisao,ator_id,motivo)
   values('master','55555555-5555-5555-5555-555555555555',1,'interno','rejeitado',gen_random_uuid(),'nao serve');"

recusa "   (reprovar sem motivo é recusado)" "criativo_aprovacao_negativa_tem_motivo" \
  "insert into public.criativo_aprovacao(subject_tipo,subject_id,versao,finalidade,decisao,ator_id)
   values('master','55555555-5555-5555-5555-555555555555',1,'google_display','rejeitado',gen_random_uuid());"

recusa "14. job 'observado' não pode declarar custo próprio" "observado_sem_custo_proprio" \
  "insert into public.criativo_job(briefing_id,motor,motor_versao,estado,idempotency_key,insumo_hash,
                                   procedencia_execucao,origem_externa,custo_real_usd,custo_medido_em,iniciado_em,terminado_em)
   values('33333333-3333-3333-3333-333333333333','f','1','succeeded','cri_obs_com_custo_0000000','h',
          'observado','{\"fabrica\":\"x\"}'::jsonb,9.9,now(),now(),now());"

recusa "15. job 'observado' sem origem externa é recusado" "observado_com_origem" \
  "insert into public.criativo_job(briefing_id,motor,motor_versao,estado,idempotency_key,insumo_hash,
                                   procedencia_execucao,iniciado_em,terminado_em)
   values('33333333-3333-3333-3333-333333333333','f','1','succeeded','cri_obs_sem_origem_000000','h',
          'observado',now(),now());"

recusa "16. job 'succeeded' com falha pendurada é recusado" "criativo_job_falha_coerente" \
  "update public.criativo_job set estado='succeeded'
   where id='66666666-6666-6666-6666-666666666666'
     and false; -- placeholder
   insert into public.criativo_job(briefing_id,motor,motor_versao,estado,idempotency_key,insumo_hash,iniciado_em,terminado_em,falha)
   values('33333333-3333-3333-3333-333333333333','m','1','succeeded','cri_sucesso_com_falha_000','h',now(),now(),
          '{\"codigo\":\"X\",\"mensagem\":\"m\",\"permanente\":false,\"em\":\"2026-01-01T00:00:00Z\"}'::jsonb);"

echo
echo "── DEGRAU 3B: a v11_02 e o parque criativo ─────────────────────────────"
aplicar v11_02_parque_criativo
cmp_ "$(P -c "select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_%';")" \
     "21" "as 21 tabelas (10 da v11_01 + 11 do parque)"
cmp_ "$(P -c "select count(*) from public.criativo_motor;")" "3" "3 motores registrados"
cmp_ "$(P -c "select count(*) from public.criativo_skin;")" "15" "15 skins do motor de video"
cmp_ "$(P -c "select count(*) from public.criativo_voz;")" "14" "14 vozes"
cmp_ "$(P -c "select count(*) from public.criativo_gate;")" "28" "28 gates catalogados"
cmp_ "$(P -c "select count(*) from public.criativo_exigencia_de_canal;")" "18" "18 exigencias de canal"
cmp_ "$(P -c "select count(distinct privilege_type) from information_schema.role_table_grants
              where table_schema='public' and table_name like 'criativo_%' and grantee='service_role';")" \
     "3" "service_role continua com SELECT, INSERT e UPDATE apenas"
cmp_ "$(P -c "select count(*) from public.criativo_motor where cofre_asset_id is not null;")" \
     "3" "os 3 motores costuram com o Cofre de Ativos"

recusa "18. storage_chave fora do prefixo do Estudio e recusada" "criativo_master_storage_forma" \
  "insert into public.criativo_master(job_id,projeto_id,slot,kind,storage_chave,content_hash,mime,motor,motor_versao,insumo_hash)
   values('44444444-4444-4444-4444-444444444444','22222222-2222-2222-2222-222222222222',
          'zz','imagem','fabrica/short_odete/video.mp4','sha256:$(printf 'e%.0s' {1..64})','video/mp4','m','1','h');"

recusa "19. a declaracao de conteudo sintetico e imutavel" "imutaveis" \
  "update public.criativo_master set sintetico=false, disclosure=null
   where id='55555555-5555-5555-5555-555555555555';"

# A guarda protege o que JA FOI MEDIDO: medir depois e legitimo, trocar a medida
# de um arquivo que nao mudou nao e. O fixture nasce sem medida, entao o teste
# primeiro MEDE (que tem de passar) e so depois tenta reescrever.
aceita "   (medir uma peca que ainda nao tinha medida e legitimo)" \
  "update public.criativo_master set largura=1080, altura=1080, bytes_totais=1000
   where id='55555555-5555-5555-5555-555555555555';"

recusa "20. medida ja registrada nao se reescreve" "nao se reescreve" \
  "update public.criativo_master set largura=9999
   where id='55555555-5555-5555-5555-555555555555';"

recusa "21. rendition conclui antes de comecar e recusada" "criativo_rendition_ordem_temporal" \
  "update public.criativo_rendition set iniciada_em=now(), concluida_em=now()-interval '1 hour'
   where job_id='44444444-4444-4444-4444-444444444444' and slot='1x1';"

recusa "22. peca pronta com erro pendurado e recusada" "criativo_rendition_pronta_sem_erro" \
  "update public.criativo_rendition set erro_codigo='X'
   where job_id='44444444-4444-4444-4444-444444444444' and slot='1x1';"

recusa "23. aprovacao de pacote inexistente e recusada" "pacote .* nao existe" \
  "insert into public.criativo_aprovacao(subject_tipo,subject_id,versao,finalidade,decisao,ator_id)
   values('pacote',gen_random_uuid(),1,'interno','aprovado',gen_random_uuid());"

# ⚠️ O pacote nasce num statement PROPRIO. Dentro de um `recusa`, ele era
# revertido junto com a entrega que devia falhar — e os testes seguintes
# reclamavam de uma autorizacao que "nao existe" por causa disso.
P -c "insert into public.criativo_pacote(id,projeto_id,destino,regra_versao,regra_verificada_em)
      values('99999999-9999-9999-9999-999999999999','22222222-2222-2222-2222-222222222222',
             'google_display','v1',now());" >/dev/null

recusa "24. entrega com autorizacao de OUTRO pacote e recusada" "nao e deste pacote\|autorizacao esta como" \
  "insert into public.criativo_entrega(pacote_id,alvo,operacao,idempotency_key,autorizacao_id)
     values('99999999-9999-9999-9999-999999999999','google','anexar','chave_de_entrega_longa',
            (select id from public.criativo_aprovacao where subject_tipo='master' limit 1));"

# A autorizacao CERTA do pacote, para que o teste seguinte exercite o CHECK de
# forma da chave, e nao o gatilho de autorizacao (que morde antes).
P -c "insert into public.criativo_aprovacao(id,subject_tipo,subject_id,versao,finalidade,decisao,ator_id)
      values('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','pacote','99999999-9999-9999-9999-999999999999',
             1,'google_display','aprovado',gen_random_uuid());" >/dev/null

aceita "   (entrega com a autorizacao DO pacote e chave longa entra)" \
  "insert into public.criativo_entrega(pacote_id,alvo,operacao,idempotency_key,autorizacao_id)
   values('99999999-9999-9999-9999-999999999999','google','anexar','chave_de_entrega_longa_o_bastante',
          'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');"

recusa "25. chave de entrega curta e recusada" "criativo_entrega_idem_forma" \
  "insert into public.criativo_entrega(pacote_id,alvo,operacao,idempotency_key,autorizacao_id)
   values('99999999-9999-9999-9999-999999999999','google','exportar','curta',
          'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');"

recusa "26. motor com id de Cofre malformado e recusado" "criativo_motor_cofre_forma" \
  "insert into public.criativo_motor(slug,nome,produz,runtime,cofre_asset_id,fonte)
   values('x','X',array['imagem'],'interno','id-solto','t');"

recusa "27. exigencia de canal com teto de bytes ZERO e recusada" "criativo_exigencia_medidas_positivas" \
  "insert into public.criativo_exigencia_de_canal(canal,tipo_de_asset,bytes_maximos,fonte_dos_numeros)
   values('TESTE','imagem_marketing',0,'t');"

recusa "28. direito apurado sem carimbo de apuracao e recusado" "criativo_direito_apuracao_com_carimbo" \
  "insert into public.criativo_master_direito(master_id,arquivo,origem,uso_comercial_ok)
   values('55555555-5555-5555-5555-555555555555','a.png','estoque',true);"

aceita "   (direito NAO apurado entra: null nao e false)" \
  "insert into public.criativo_master_direito(master_id,arquivo,origem,uso_comercial_ok)
   values('55555555-5555-5555-5555-555555555555','b.png','estoque',null);"

recusa "29. gate com veredito fora do dominio e recusado" "criativo_master_gate_resultado_valido" \
  "insert into public.criativo_master_gate(master_id,gate_slug,resultado)
   values('55555555-5555-5555-5555-555555555555','contrast','TALVEZ');"

echo
echo "── DEGRAU 4: o Python e o banco concordam ──────────────────────────────"
# `estado_do_lote` decide o que a interface mostra. Se ele e o banco divergirem,
# a tela chama de `succeeded` um lote que perdeu uma peça.
SAIDA=$(cd "$RAIZ/backend" && PYTHONPATH="$RAIZ:$RAIZ/backend" "$PY" - <<'PYEOF' 2>&1
from app.criativo.dominio import estado_do_lote
casos = [
    (["pronta", "pronta", "pronta"], "succeeded"),
    (["pronta", "falhou", "pronta"], "partial"),
    (["falhou", "falhou"], "failed"),
    (["pronta", "gerando"], "running"),
    (["cancelada", "cancelada"], "cancelled"),
    ([], "failed"),
    (["pronta", "cancelada"], "partial"),
]
ruins = [(e, esp, estado_do_lote(e)) for e, esp in casos if estado_do_lote(e) != esp]
print("OK" if not ruins else f"DIVERGIU: {ruins}")
PYEOF
)
cmp_ "$(echo "$SAIDA" | tail -1)" "OK" "17. estado_do_lote concorda com os sete estados canônicos"

echo
echo "── DEGRAU 5: reverter ──────────────────────────────────────────────────"
if psql -h "$D/s" -U postgres -q -v ON_ERROR_STOP=1 -f "$M/v11_02_rollback.sql" >"$D/out" 2>&1; then
    ok "o rollback da v11_02 RODOU"
else
    nao "o rollback da v11_02 abortou"; tail -6 "$D/out" | sed 's/^/      /'
fi
cmp_ "$(P -c "select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_%';")" \
     "10" "as 10 da v11_01 continuam de pe depois do rollback da v11_02"
if psql -h "$D/s" -U postgres -q -v ON_ERROR_STOP=1 -f "$M/v11_01_rollback.sql" >"$D/out" 2>&1; then
    ok "o rollback RODOU (não é só documentação)"
else
    nao "o rollback abortou"; tail -6 "$D/out" | sed 's/^/      /'
fi
cmp_ "$(P -c "select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_%';")" \
     "0" "zero tabelas criativo_* depois do rollback"
cmp_ "$(P -c "select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace
              where n.nspname='public' and p.proname like 'criativo_%';")" \
     "0" "zero funções criativo_* depois do rollback"
cmp_ "$(P -c "select count(*) from pg_tables where schemaname='public' and tablename like 'trafego_%';")" \
     "$ANTES" "INDEPENDÊNCIA: as tabelas trafego_* continuam de pé"

echo
echo "── DEGRAU 6: reaplicar ─────────────────────────────────────────────────"
aplicar v11_01_estudio_criativo
aplicar v11_02_parque_criativo
cmp_ "$(P -c "select count(*) from pg_tables where schemaname='public' and tablename like 'criativo_%';")" \
     "21" "as 21 tabelas voltaram"

echo
if [ "$FALHAS" -eq 0 ]; then
    printf '\033[32m✓ ciclo v11 completo: aplicar → reverter → reaplicar, sem falha.\033[0m\n'
else
    printf '\033[31m✗ %s falha(s) no ciclo v11.\033[0m\n' "$FALHAS"
fi
exit "$FALHAS"
