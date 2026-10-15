# shellcheck shell=bash
# =============================================================================
# tools/freedom-lab/db/suites/v26_bia.sh — suíte da v26_01 (Bia/Hermes V1) para o lab.sh
#
# Prova (banco descartável, sem rede, sem porta, nunca produção):
#
#   LAB_NOME=volc-freedom-lab-bia \
#   MIGRATION=supabase/migrations/v26_01_agente_bia.sql \
#   ROLLBACK=supabase/migrations/v26_01_rollback.sql \
#   MIGRATION_SUITE=tools/freedom-lab/db/suites/v26_bia.sh \
#   tools/freedom-lab/lab.sh recriar
#
# O que prova, sobre v26_01_agente_bia.sql e v26_01_rollback.sql:
#   1. aplicar como supabase_admin; reaplicar por cima é recusado (55000)
#   2. matriz: anon e authenticated sem EXECUTE nas 11 RPCs e sem acesso ao
#      schema; service_role executa as RPCs mas NÃO lê as tabelas direto
#   3. semântica: idempotência (repetida), conflito, conversa de outro dono,
#      ocupado (uma em voo por dono), limite por minuto, conversa com incerta
#      bloqueada, iniciar só de queued, concluir só de running (tardia é
#      ignorada e registrada), expirar (queued→cancelled, running→uncertain),
#      reconciliar só de uncertain, sessão Hermes ausente das leituras
#   4. transições fechadas e identidade imutável mesmo para o dono do schema;
#      evento append-only (UPDATE/TRUNCATE recusados)
#   5. concorrência real: duas sessões reservando para o MESMO dono — a segunda
#      espera a trava e recebe `ocupado`
#   6. apagar o usuário do auth apaga as conversas dele (cascade)
#   7. rollback com dado é recusado e atômico; com a declaração explícita
#      descarta; devolve o fingerprint anterior; é idempotente; reaplicar dá o
#      mesmo fingerprint
#
# Dados sintéticos fixos (UUIDs de teste, e-mails .invalid); nenhum dado real.
# =============================================================================

for _f in P PA ok nao eq estado; do
  declare -F "$_f" >/dev/null || { echo "ERRO: v26_bia.sh precisa ser carregada pelo lab.sh (falta $_f)" >&2; return 1 2>/dev/null || exit 1; }
done
unset _f

BIA_APLICAR="$RAIZ/supabase/migrations/v26_01_agente_bia.sql"
BIA_REVERTER="$RAIZ/supabase/migrations/v26_01_rollback.sql"
U1=aaaaaaaa-0000-4000-8000-000000000001
U2=aaaaaaaa-0000-4000-8000-000000000002
S1="volc_$(printf '1%.0s' $(seq 32))"
S2="volc_$(printf '2%.0s' $(seq 32))"
IMP="$(printf 'f%.0s' $(seq 64))"
IMP2="$(printf 'e%.0s' $(seq 64))"

bia_aplicar()  { PA -f - < "$BIA_APLICAR"  > "$RECIBOS/bia-$1.out" 2>&1; }
bia_reverter() { PA -f - < "$BIA_REVERTER" > "$RECIBOS/bia-$1.out" 2>&1; }
bia_fp() { P -f - < "$FP" 2>/dev/null | grep _TOTAL | tr -d ' '; }
# fingerprint do próprio schema privado (o FP oficial cobre public + app_auth)
bia_fp_privado() {
  PA -c "select md5(coalesce(string_agg(x, ',' order by x), '')) from (
           select format('%s.%s|%s|rls=%s', n.nspname, c.relname, c.relkind, c.relrowsecurity) x
             from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'agente_bia'
           union all select format('%s|%s', p.proname, md5(p.prosrc)) from pg_proc p
             join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'agente_bia'
           union all select format('acl:%s|%s', c.relname, coalesce(c.relacl::text, '')) from pg_class c
             join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'agente_bia') s"
}
# como service_role (SET ROLE pelo supabase_admin), numa transação desfeita
como_sr() { ESTADO_COMO=supabase_admin estado service_role "$1"; }
# como service_role, COMMITANDO (para a sequência semântica)
sr() { printf 'SET ROLE service_role;\n%s\n' "$1" | PA 2>&1 | tail -1; }

echo "▶ v26_bia: aplicar"
FP_ANTES="$(bia_fp)"
bia_aplicar aplicar && ok "v26_01 aplica como supabase_admin" || nao "v26_01 não aplicou (ver bia-aplicar.out)"
FP_DEPOIS="$(bia_fp)"; FPP_DEPOIS="$(bia_fp_privado)"
[ "$FP_ANTES" != "$FP_DEPOIS" ] && ok "fingerprint public mudou (RPCs novas)" || nao "fingerprint não mudou"
bia_aplicar reaplicar; grep -q "55000\|já existe" "$RECIBOS/bia-reaplicar.out" \
  && ok "reaplicar por cima é recusado" || nao "reaplicação não foi recusada"

echo "▶ v26_bia: matriz de acesso"
for papel in anon authenticated; do
  eq "$(ESTADO_COMO=supabase_admin estado "$papel" "select public.volc_agente_listar_conversas('$U1', 5)")" 42501 \
     "$papel sem EXECUTE em volc_agente_listar_conversas"
  eq "$(ESTADO_COMO=supabase_admin estado "$papel" "select public.volc_agente_reservar('$U1','$U1','$U1','x','$IMP',6,null)")" 42501 \
     "$papel sem EXECUTE em volc_agente_reservar"
  eq "$(ESTADO_COMO=supabase_admin estado "$papel" "select count(*) from agente_bia.conversa")" 42501 \
     "$papel sem acesso ao schema agente_bia"
done
eq "$(como_sr "select count(*) from agente_bia.execucao")" 42501 "service_role não lê a tabela direto"
eq "$(como_sr "select public.volc_agente_listar_conversas('$U1', 5)")" "ok:[]" "service_role executa a RPC"
eq "$(PA -c "select count(*) from information_schema.role_routine_grants where routine_name like 'volc_agente_%' and grantee in ('anon','authenticated','PUBLIC')")" 0 \
   "nenhum grant de RPC para anon/authenticated/PUBLIC"
eq "$(PA -c "select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'volc_agente_%' and p.prosecdef and array_to_string(p.proconfig, ',') like 'search_path=%'")" 11 \
   "11 RPCs SECURITY DEFINER com search_path fixo"
eq "$(PA -c "select bool_and(relrowsecurity) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='agente_bia' and relkind='r'")" t \
   "RLS ligada nas 3 tabelas"

echo "▶ v26_bia: semântica"
PA -c "insert into auth.users (id, aud, role, email) values ('$U1','authenticated','authenticated','u1@lab.invalid'), ('$U2','authenticated','authenticated','u2@lab.invalid')" >/dev/null \
  && ok "dois usuários sintéticos no auth" || nao "não criou usuários sintéticos"
C1="$(sr "select (public.volc_agente_criar_conversa('$U1', '$S1', null))->>'id'")"
C2="$(sr "select (public.volc_agente_criar_conversa('$U2', '$S2', null))->>'id'")"
[ ${#C1} = 36 ] && ok "conversa criada (id público uuid)" || nao "conversa não criada: $C1"
eq "$(sr "select public.volc_agente_historico('$U1', '$C1')::text like '%volc_1111%'")" f "sessão Hermes não sai no histórico"
eq "$(sr "select public.volc_agente_historico('$U2', '$C1') is null")" t "dono B não lê conversa de A"
eq "$(como_sr "select public.volc_agente_criar_conversa('$U1', 'nao-e-sessao', null)")" 23514 "sessão fora do formato recusada"

R1=11111111-aaaa-4aaa-8aaa-000000000001
reserva() { sr "select (public.volc_agente_reservar('$1','$2','$3','$4','$5',$6,null))->>'resultado'"; }
eq "$(reserva "$U1" "$C1" "$R1" "oi" "$IMP" 6)" nova "reserva nova"
eq "$(reserva "$U1" "$C1" "$R1" "oi" "$IMP" 6)" repetida "mesmo request_id e conteúdo: repetida"
eq "$(reserva "$U1" "$C1" "$R1" "outro" "$IMP2" 6)" conflito "mesmo request_id, outro conteúdo: conflito"
eq "$(reserva "$U2" "$C1" "22222222-aaaa-4aaa-8aaa-000000000002" "oi" "$IMP" 6)" conversa_inexistente "conversa de outro dono: inexistente"
eq "$(reserva "$U1" "$C1" "33333333-aaaa-4aaa-8aaa-000000000003" "dois" "$IMP2" 6)" ocupado "segunda em voo do mesmo dono: ocupado"
E1="$(sr "select id from (select (public.volc_agente_historico('$U1','$C1'))->'execucoes'->0->>'id' id) s")"
eq "$(sr "select (public.volc_agente_iniciar('$U2','$E1')) is null")" t "outro dono não inicia"
eq "$(sr "select (public.volc_agente_iniciar('$U1','$E1'))->>'sessao_motor'")" "$S1" "iniciar devolve a sessão só ao backend"
eq "$(sr "select public.volc_agente_iniciar('$U1','$E1') is null")" t "iniciar duas vezes não reabre"
eq "$(sr "select (public.volc_agente_concluir('$U1','$E1','succeeded','resposta',null,'{\"duracao_ms\":10}'))->>'estado'")" succeeded "concluir running → succeeded"
eq "$(sr "select (public.volc_agente_concluir('$U1','$E1','failed',null,'hermes_timeout','{}'))->>'estado'")" succeeded "conclusão tardia não sobrescreve"
eq "$(PA -c "select count(*) from agente_bia.evento where execucao_id='$E1' and tipo='conclusao_tardia_ignorada'")" 1 "conclusão tardia registrada"
eq "$(como_sr "select public.volc_agente_concluir('$U1','$E1','cancelled',null,null,'{}')")" 22023 "concluir não aceita cancelled"

# limite por minuto = 2 (a 1ª já conta)
R2=44444444-aaaa-4aaa-8aaa-000000000004; R3=55555555-aaaa-4aaa-8aaa-000000000005
eq "$(reserva "$U1" "$C1" "$R2" "b" "$IMP2" 2)" nova "segunda no minuto (limite 2): nova"
E2="$(PA -c "select id from agente_bia.execucao where request_id='$R2'")"
sr "select public.volc_agente_iniciar('$U1','$E2')" >/dev/null
sr "select public.volc_agente_concluir('$U1','$E2','uncertain',null,'hermes_timeout','{}')" >/dev/null
eq "$(reserva "$U1" "$C1" "$R3" "c" "$IMP2" 6)" bloqueada_incerta "conversa com incerta bloqueia novo envio"
eq "$(reserva "$U1" "$C1" "$R3" "c" "$IMP2" 2)" bloqueada_incerta "incerta é conferida antes do limite"
C1B="$(sr "select (public.volc_agente_criar_conversa('$U1', 'volc_$(printf '3%.0s' $(seq 32))', null))->>'id'")"
eq "$(reserva "$U1" "$C1B" "$R3" "c" "$IMP2" 2)" limite "limite por minuto"
eq "$(sr "select (public.volc_agente_para_reconciliar('$U1','$E2'))->>'sessao_motor'")" "$S1" "incerta é reconciliável"
eq "$(sr "select (public.volc_agente_reconciliar('$U1','$E2','succeeded','lida na sessão','{\"via\":\"read_back_sessao\"}'))->>'estado'")" succeeded "reconciliar uncertain → succeeded"
eq "$(como_sr "select public.volc_agente_reconciliar('$U1','$E2','succeeded','x','{}')")" 55000 "só incerta é reconciliada"

# expirar: queued antiga → cancelled; running antiga → uncertain
R4=66666666-aaaa-4aaa-8aaa-000000000006
PA -c "delete from agente_bia.execucao where dono='$U1' and criada_em > now() - interval '1 hour' and estado in ('succeeded')" >/dev/null
eq "$(reserva "$U1" "$C1B" "$R4" "d" "$IMP2" 30)" nova "reserva para expirar"
E4="$(PA -c "select id from agente_bia.execucao where request_id='$R4'")"
PA -c "update agente_bia.execucao set iniciada_em = now() - interval '1 hour' where id='$E4'" >/dev/null
eq "$(sr "select public.volc_agente_expirar('$U1', 150)")" 1 "expirar pega a órfã"
eq "$(PA -c "select estado||'/'||erro_codigo from agente_bia.execucao where id='$E4'")" cancelled/processo_interrompido "queued órfã vira cancelled (nunca saiu)"
R5=77777777-aaaa-4aaa-8aaa-000000000007
eq "$(reserva "$U1" "$C1B" "$R5" "e" "$IMP" 30)" nova "reserva para expirar em voo"
E5="$(PA -c "select id from agente_bia.execucao where request_id='$R5'")"
sr "select public.volc_agente_iniciar('$U1','$E5')" >/dev/null
PA -c "update agente_bia.execucao set iniciada_em = now() - interval '1 hour' where id='$E5'" >/dev/null
sr "select public.volc_agente_expirar('$U1', 150)" >/dev/null
eq "$(PA -c "select estado from agente_bia.execucao where id='$E5'")" uncertain "running órfã vira uncertain (nunca replay)"

echo "▶ v26_bia: imutabilidade"
# ⚠️ Na imagem Supabase `postgres` é membro de pg_read_all_data: LÊ tudo (papel de
# administração do banco, não da API). O que se prova é que ele não ESCREVE.
eq "$(PA -c "select pg_has_role('postgres', 'pg_read_all_data', 'member')")" t "postgres lê só via pg_read_all_data (papel administrativo da imagem)"
eq "$(sqlstate "insert into agente_bia.evento (execucao_id, tipo) values (gen_random_uuid(), 'iniciada')")" 42501 "postgres não escreve no schema"
eq "$(PA -c "update agente_bia.execucao set estado='running' where id='$E4'" 2>&1 | grep -o 'transição')" "transição" "cancelled → running recusado até para o dono"
eq "$(PA -c "update agente_bia.execucao set estado='cancelled' where id='$E5'" 2>&1 | grep -o 'transição')" "transição" "uncertain → cancelled recusado (timeout nunca vira cancelamento)"
eq "$(PA -c "update agente_bia.execucao set entrada='trocada' where id='$E5'" 2>&1 | grep -o 'imutável')" "imutável" "entrada da execução é imutável"
eq "$(PA -c "update agente_bia.evento set tipo='iniciada'" 2>&1 | grep -o 'append-only')" "append-only" "evento: UPDATE recusado"
eq "$(PA -c "truncate agente_bia.evento" 2>&1 | grep -o 'append-only')" "append-only" "evento: TRUNCATE recusado"
eq "$(PA -c "insert into agente_bia.execucao (conversa_id, dono, request_id, impressao, entrada) values ('$C1', '$U2', gen_random_uuid(), '$IMP', 'x')" 2>&1 | grep -o 'execucao_conversa_do_dono')" \
   execucao_conversa_do_dono "execução não pode apontar para conversa de outro dono"

echo "▶ v26_bia: concorrência (duas sessões, mesmo dono)"
C2B="$(sr "select (public.volc_agente_criar_conversa('$U2', 'volc_$(printf '4%.0s' $(seq 32))', null))->>'id'")"
( printf "SET ROLE service_role; BEGIN; SELECT (public.volc_agente_reservar('$U2','$C2B','88888888-aaaa-4aaa-8aaa-000000000008','x','$IMP',30,null))->>'resultado'; SELECT pg_sleep(2); COMMIT;\n" \
  | PA > "$RECIBOS/bia-conc-1.out" 2>&1 ) &
sleep 0.5
INICIO=$(date +%s)
SEGUNDA="$(sr "select (public.volc_agente_reservar('$U2','$C2B','99999999-aaaa-4aaa-8aaa-000000000009','y','$IMP2',30,null))->>'resultado'")"
ESPERA=$(( $(date +%s) - INICIO ))
wait
eq "$(grep -E '^(nova|ocupado)$' "$RECIBOS/bia-conc-1.out" | head -1)" nova "1ª sessão reserva"
eq "$SEGUNDA" ocupado "2ª sessão concorrente recebe ocupado"
[ "$ESPERA" -ge 1 ] && ok "2ª sessão esperou a trava ($ESPERA s)" || nao "2ª sessão não esperou a trava"

echo "▶ v26_bia: retenção e cascade"
PA -c "delete from auth.users where id='$U2'" >/dev/null
eq "$(PA -c "select count(*) from agente_bia.conversa where dono='$U2'")" 0 "apagar o usuário apaga as conversas dele"
eq "$(PA -c "select agente_bia.expurgar(10)" 2>&1 | grep -o 'mínima')" "mínima" "retenção mínima de 30 dias"
eq "$(ESTADO_COMO=supabase_admin estado service_role "select agente_bia.expurgar(180)")" 42501 "service_role não executa expurgo"

echo "▶ v26_bia: rollback"
bia_reverter com-dado; grep -q "55000\|descartar_historico" "$RECIBOS/bia-com-dado.out" \
  && ok "rollback com dado é recusado" || nao "rollback com dado não foi recusado"
eq "$(PA -c "select to_regnamespace('agente_bia') is not null")" t "rollback recusado é atômico (schema intacto)"
{ echo "SET agente_bia.descartar_historico = 'sim';"; cat "$BIA_REVERTER"; } | PA > "$RECIBOS/bia-descartar.out" 2>&1
eq "$(PA -c "select to_regnamespace('agente_bia') is null")" t "rollback com declaração explícita remove o schema"
eq "$(PA -c "select count(*) from pg_proc where proname like 'volc_agente_%'")" 0 "rollback remove as 11 RPCs"
eq "$(bia_fp)" "$FP_ANTES" "fingerprint volta ao anterior"
bia_reverter idempotente && grep -q "nada a desfazer" "$RECIBOS/bia-idempotente.out" \
  && ok "rollback é idempotente" || nao "rollback não é idempotente"
bia_aplicar reaplicar-limpo && ok "reaplica depois do rollback" || nao "não reaplicou"
eq "$(bia_fp)" "$FP_DEPOIS" "reaplicar dá o mesmo fingerprint public"
eq "$(bia_fp_privado)" "$FPP_DEPOIS" "reaplicar dá o mesmo fingerprint do schema privado"
P -f - < "$FP" > "$RECIBOS/fp-final.out" 2>&1
