#!/usr/bin/env bash
#
# A fronteira atômica do lançamento, provada num Postgres descartável.
#
# ## O defeito que este arquivo existe para provar morto
#
# A v10_01 tem três camadas contra "timeout mas criou", e todas as três vivem
# dentro de `IF NEW.estado IS DISTINCT FROM OLD.estado`. Abrir um recibo — o ato
# que precede a chamada à plataforma — não passava por gatilho nenhum. Medido em
# 31/08/2026, com v9_01..v9_04 + v10_01 + v10_02 aplicadas e SEM a v10_03:
#
#     item em `criando`, recibo tentativa=1 `em_voo`
#     INSERT trafego_recibo tentativa=2 'em_voo'  → ACEITO
#     recibos em voo simultâneos para o mesmo item: 2
#
# Duas chamadas de criação em voo para o mesmo plano, na mesma conta — e o
# índice de sucesso único garante que, se as duas criarem, a segunda campanha
# fica invisível para o sistema.
#
# ## O que este script prova
#
# Cada prova roda contra um cluster que nasce e morre aqui. Nada sai de /tmp e
# NENHUMA delas fala com banco de produção ou com o Google.
#
#   A. sem a v10_03, o segundo recibo em voo passa   ← a reprodução do defeito
#   B. com a v10_03, ele é RECUSADO pelo SQLSTATE certo
#   C. abrir → despachar → fechar percorre a cadeia inteira
#   D. a mesma chave não duplica (reaproveita)
#   E. a mesma chave com plano diferente falha fechado
#   F. aprovação de outra conta/canal é recusada
#   G. aprovação de outro plano é recusada
#   H. entrar em `criando` sem aprovação é recusado
#   I. sem resposta vira `indeterminado`, nunca `falhou`
#   J. a reconciliação tardia fecha O MESMO recibo, sem reenviar
#   K. o id externo resolve para exatamente um item
#   L. `anon`/`authenticated` não executam nenhuma função do ledger
#   M. o rollback devolve o banco, e a v10_01 continua inteira
#
# Uso:  ./scripts/provar-ledger-v10-03.sh

set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
M="$RAIZ/supabase/migrations"

for b in initdb pg_ctl psql; do
    command -v "$b" >/dev/null 2>&1 || { echo "falta $b — brew install postgresql@16"; exit 2; }
done

# /tmp e não o scratchpad: o socket unix tem teto de 103 bytes no caminho.
D=$(mktemp -d /tmp/volcledXXXX)
export LC_ALL=C LANG=C
limpar() { pg_ctl -D "$D/d" -m immediate stop >/dev/null 2>&1; rm -rf "$D"; }
trap limpar EXIT

initdb -D "$D/d" -U postgres --encoding=UTF8 --locale=C >/dev/null 2>&1
mkdir -p "$D/s"
pg_ctl -D "$D/d" -l "$D/pg.log" -o "-k $D/s -h ''" -w start >/dev/null 2>&1

P() { psql -h "$D/s" -U postgres -X -q -A -t "$@"; }

P -c "CREATE ROLE anon NOLOGIN NOINHERIT;
      CREATE ROLE authenticated NOLOGIN NOINHERIT;
      CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
      GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
      ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT ALL ON TABLES TO anon, authenticated, service_role;" >/dev/null

FALHAS=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; }
nao() { printf '  \033[31m✗\033[0m %s\n' "$1"; FALHAS=$((FALHAS+1)); }

# Mesma doutrina do provar-ciclo-v10.sh: "deu erro" não prova guarda. Classe 23
# (incluindo 23001/restrict_violation) e P0001 são guarda; classe 42, 3F000 e
# 22P02 são a PROVA quebrada — tabela renomeada, coluna com typo, sintaxe torta.
#
# ⚠️ DOIS CÓDIGOS DA CLASSE 22 SIGNIFICAM O OPOSTO UM DO OUTRO, e por isso a
# lista aqui é nominal em vez de por classe:
#
#   22023 `invalid_parameter_value` → uma função do ledger recusou o ARGUMENTO
#         (sucesso sem id externo, desfecho inexistente, sha256 torto). É guarda.
#   22P02 `invalid_text_representation` → um literal malformado no próprio SQL
#         da prova (um uuid torto no WHERE). É a prova quebrada.
#
# Aceitar a classe 22 inteira faria um uuid com typo passar por "guarda
# disparou"; recusá-la inteira reprovaria as guardas de contrato de entrada, que
# foi o que aconteceu na primeira execução desta prova.
#
# P0002 `no_data_found` é a recusa de operar sobre item/recibo inexistente.
GUARDA_DISPAROU='^(P0001|P0002|22023|23[0-9A-Z]{3})$'
PROVA_QUEBRADA='^(42[0-9A-Z]{3}|3F000|22P02)$'

estado_de() { printf '%s' "$1" | grep -oE '^ERROR:  [0-9A-Z]{5}:' | head -1 | awk '{print $2}' | tr -d ':'; }

recusa() {
    local rotulo="$1"; shift
    local saida estado
    saida=$(printf '\\set VERBOSITY verbose\nSET ROLE service_role;\n%s\n' "$*" \
            | psql -h "$D/s" -U postgres -X -A -t 2>&1)
    estado=$(estado_de "$saida")
    if printf '%s' "$estado" | grep -qE "$GUARDA_DISPAROU"; then
        ok "$rotulo — RECUSADO ($estado)"
    elif printf '%s' "$estado" | grep -qE "$PROVA_QUEBRADA"; then
        nao "$rotulo — a PROVA está quebrada ($estado): $(printf '%s' "$saida" | tr '\n' '|' | cut -c1-90)"
    else
        nao "$rotulo — PASSOU e não deveria (${estado:-sem erro})"
    fi
}

aceita() {
    local rotulo="$1"; shift
    if P -c "SET ROLE service_role; $*" >"$D/err" 2>&1; then ok "$rotulo"
    else nao "$rotulo — recusou e não deveria: $(head -3 "$D/err" | tr '\n' ' ' | cut -c1-140)"; fi
}

cmp_() {
    if [ "$1" = "$2" ]; then ok "$3"; else nao "$3 — esperado [$2], veio [$1]"; fi
}

semear() {
    if psql -h "$D/s" -U postgres -X -q -v ON_ERROR_STOP=1 -c "SET ROLE service_role; $*" >"$D/err" 2>&1; then
        return 0
    fi
    nao "SEMEADURA FALHOU — a prova seguinte mediria outra coisa: $(head -3 "$D/err" | tr '\n' ' ' | cut -c1-160)"
    return 1
}

aplicar() {
    if psql -h "$D/s" -U postgres -q -v ON_ERROR_STOP=1 -f "$M/$1.sql" >"$D/out" 2>&1; then
        ok "aplicou $1"
    else
        nao "aplicou $1"; tail -4 "$D/out" | sed 's/^/      /'; return 1
    fi
}

CHAVE='volc-canary-abc123def456'
IMPRESSAO=$(printf 'a%.0s' $(seq 1 64))
OUTRA=$(printf 'b%.0s' $(seq 1 64))

abrir_com() {  # $1 = chave · $2 = impressão · $3 = conta
    P -c "SET ROLE service_role;
      SELECT public.trafego_ledger_abrir_lancamento(
        p_idempotency_key := '$1', p_plataforma := 'GOOGLE_ADS',
        p_conta_externa := '$3', p_canal := 'SEARCH', p_objetivo := 'leads',
        p_rotulo := 'Maquininha', p_plano := '{\"canal\":\"SEARCH\"}'::jsonb,
        p_plano_impressao := '$2', p_declarada_por := 'dono@volc',
        p_declarada_com_base_em := 'pauta-74',
        p_blueprint_chave := 'search-canario', p_blueprint_titulo := 'Search canario',
        p_blueprint_corpo := '{}'::jsonb,
        p_validacoes := '[{\"camada\":\"local\",\"regra\":\"forma\",\"resultado\":\"passou\"},
                          {\"camada\":\"validate_only\",\"regra\":\"google\",\"resultado\":\"passou\"}]'::jsonb
      ) ->> 'item_id';"
}

echo "════ 0 · a base: v9 e v10_01/02, SEM a v10_03 ════"
for m in v9_01_trafego_inventario v9_02_atencao_sem_removida \
         v9_03_historico_e_ordem_operacional v9_04_url_final_preservada \
         v10_01_intencao_e_lote v10_02_autogestao; do
    aplicar "$m" || exit 1
done

echo
echo "════ A · a reprodução do defeito, ANTES da v10_03 ════"
semear "INSERT INTO trafego_linhagem (campaign_lineage_id, rotulo, declarada_por)
        VALUES ('11111111-1111-1111-1111-111111111111','canario','repro');
        INSERT INTO trafego_intencao (intencao_id, campaign_lineage_id, plataforma, conta_externa,
          objetivo, rotulo, declarada_por, declarada_com_base_em)
        VALUES ('22222222-2222-2222-2222-222222222222','11111111-1111-1111-1111-111111111111',
          'GOOGLE_ADS','5478096539','leads','Maquininha','repro','pauta-74');
        INSERT INTO trafego_blueprint (blueprint_id, chave, versao, plataforma, canal, titulo, corpo, declarado_por)
        VALUES ('33333333-3333-3333-3333-333333333333','bp',1,'GOOGLE_ADS','SEARCH','bp','{}'::jsonb,'repro');
        INSERT INTO trafego_lote (lote_id, intencao_id, blueprint_id, plataforma, conta_externa, canal, criado_por)
        VALUES ('44444444-4444-4444-4444-444444444444','22222222-2222-2222-2222-222222222222',
          '33333333-3333-3333-3333-333333333333','GOOGLE_ADS','5478096539','SEARCH','repro');
        INSERT INTO trafego_lote_item (item_id, lote_id, ordem, idempotency_key, rotulo, plano)
        VALUES ('55555555-5555-5555-5555-555555555555','44444444-4444-4444-4444-444444444444',
          1,'$CHAVE','Maquininha','{}'::jsonb);
        UPDATE trafego_lote SET estado='validando' WHERE lote_id='44444444-4444-4444-4444-444444444444';
        UPDATE trafego_lote SET estado='aguardando_aprovacao' WHERE lote_id='44444444-4444-4444-4444-444444444444';
        UPDATE trafego_lote SET estado='aprovado', aprovado_por='d', aprovado_em=now() WHERE lote_id='44444444-4444-4444-4444-444444444444';
        UPDATE trafego_lote_item SET estado='validado_local' WHERE item_id='55555555-5555-5555-5555-555555555555';
        UPDATE trafego_lote_item SET estado='validado_remoto' WHERE item_id='55555555-5555-5555-5555-555555555555';
        UPDATE trafego_lote_item SET estado='aprovado' WHERE item_id='55555555-5555-5555-5555-555555555555';
        INSERT INTO trafego_recibo (item_id, idempotency_key, tentativa, operacao, enviado_em)
        VALUES ('55555555-5555-5555-5555-555555555555','$CHAVE',1,'criar_campanha',now());
        UPDATE trafego_lote_item SET estado='criando', tentativas=1 WHERE item_id='55555555-5555-5555-5555-555555555555';"

aceita "SEM a v10_03 o segundo recibo em voo PASSA (é o defeito)" \
  "INSERT INTO trafego_recibo (item_id, idempotency_key, tentativa, operacao, enviado_em)
   VALUES ('55555555-5555-5555-5555-555555555555','$CHAVE',2,'criar_campanha',now());"
cmp_ "$(P -c "SELECT count(*)::text FROM trafego_recibo WHERE item_id='55555555-5555-5555-5555-555555555555' AND desfecho IN ('em_voo','sem_resposta');")" \
     "2" "o defeito medido: 2 recibos em voo para o mesmo item"

echo
echo "════ B · a v10_03 entra e o defeito morre ════"
# O cluster carrega o defeito semeado; a migration precisa aplicar mesmo assim.
aplicar "v10_03_recibo_atomico" || exit 1
recusa "CAMADA 4 · terceiro recibo em voo no mesmo item" \
  "INSERT INTO trafego_recibo (item_id, idempotency_key, tentativa, operacao, enviado_em)
   VALUES ('55555555-5555-5555-5555-555555555555','$CHAVE',3,'criar_campanha',now());"

echo
echo "════ C · a cadeia inteira por uma porta só ════"
ITEM=$(abrir_com 'volc-canary-cadeia0001' "$IMPRESSAO" '5478096539')
cmp_ "$(P -c "SELECT estado FROM trafego_lote_item WHERE item_id='$ITEM';")" \
     "validado_remoto" "abrir · intenção, blueprint, lote, item e as duas provas numa transação"
cmp_ "$(P -c "SELECT count(*)::text FROM trafego_validacao WHERE item_id='$ITEM';")" \
     "2" "abrir · as duas camadas de validação ficaram registradas"

echo
echo "════ D · a mesma chave não duplica ════"
cmp_ "$(P -c "SET ROLE service_role; SELECT (public.trafego_ledger_abrir_lancamento(
        p_idempotency_key := 'volc-canary-cadeia0001', p_plataforma := 'GOOGLE_ADS',
        p_conta_externa := '5478096539', p_canal := 'SEARCH', p_objetivo := 'leads',
        p_rotulo := 'Maquininha', p_plano := '{\"canal\":\"SEARCH\"}'::jsonb,
        p_plano_impressao := '$IMPRESSAO', p_declarada_por := 'dono@volc',
        p_declarada_com_base_em := 'pauta-74', p_blueprint_chave := 'search-canario',
        p_blueprint_titulo := 'x', p_blueprint_corpo := '{}'::jsonb) ->> 'reaproveitado');")" \
     "true" "reentrada com a mesma chave reaproveita, não cria um segundo caminho"
cmp_ "$(P -c "SELECT count(*)::text FROM trafego_lote_item WHERE idempotency_key='volc-canary-cadeia0001';")" \
     "1" "e continua existindo exatamente um item para a chave"

echo
echo "════ E · mesma chave, plano diferente → falha fechado ════"
recusa "a chave é derivada do conteúdo: conteúdo outro com chave igual é recusado" \
  "SELECT public.trafego_ledger_abrir_lancamento(
     p_idempotency_key := 'volc-canary-cadeia0001', p_plataforma := 'GOOGLE_ADS',
     p_conta_externa := '5478096539', p_canal := 'SEARCH', p_objetivo := 'leads',
     p_rotulo := 'Maquininha', p_plano := '{\"canal\":\"SEARCH\",\"outro\":1}'::jsonb,
     p_plano_impressao := '$OUTRA', p_declarada_por := 'dono@volc',
     p_declarada_com_base_em := 'pauta-74', p_blueprint_chave := 'search-canario',
     p_blueprint_titulo := 'x', p_blueprint_corpo := '{}'::jsonb);"

echo
echo "════ F/G/H · a autorização não atravessa conta, canal nem plano ════"
recusa "aprovação apresentada para OUTRA conta" \
  "SELECT public.trafego_ledger_despachar('volc-canary-cadeia0001','GOOGLE_ADS','9999999999','SEARCH','$IMPRESSAO','dono@volc','sub-1');"
recusa "aprovação apresentada para OUTRO canal" \
  "SELECT public.trafego_ledger_despachar('volc-canary-cadeia0001','GOOGLE_ADS','5478096539','DISPLAY','$IMPRESSAO','dono@volc','sub-1');"
recusa "aprovação de OUTRO plano (impressão divergente)" \
  "SELECT public.trafego_ledger_despachar('volc-canary-cadeia0001','GOOGLE_ADS','5478096539','SEARCH','$OUTRA','dono@volc','sub-1');"
recusa "entrar em \`criando\` sem aprovação registrada" \
  "UPDATE trafego_lote_item SET estado='aprovado' WHERE item_id='$ITEM';
   UPDATE trafego_lote_item SET estado='criando' WHERE item_id='$ITEM';"

echo
echo "════ C2 · o recibo em voo existe ANTES da fronteira ════"
REC=$(P -c "SET ROLE service_role; SELECT public.trafego_ledger_despachar(
        'volc-canary-cadeia0001','GOOGLE_ADS','5478096539','SEARCH','$IMPRESSAO','dono@volc','sub-1') ->> 'recibo_id';")
cmp_ "$(P -c "SELECT desfecho FROM trafego_recibo WHERE recibo_id='$REC';")" "em_voo" \
     "despachar deixou o recibo \`em_voo\` gravado — e só então a chamada poderia sair"
cmp_ "$(P -c "SELECT estado FROM trafego_lote_item WHERE item_id='$ITEM';")" "criando" \
     "o item está em \`criando\`, com a aprovação vinculada ao plano"
cmp_ "$(P -c "SELECT (aprovacao_impressao = plano_impressao)::text FROM trafego_lote_item WHERE item_id='$ITEM';")" \
     "true" "a impressão aprovada é a do plano — a constraint não deixa ser outra"
recusa "despachar de novo com um recibo em voo aberto" \
  "SELECT public.trafego_ledger_despachar('volc-canary-cadeia0001','GOOGLE_ADS','5478096539','SEARCH','$IMPRESSAO','dono@volc','sub-1');"

echo
echo "════ I · sem resposta vira indeterminado, nunca falhou ════"
aceita "fechar como \`sem_resposta\`" \
  "SELECT public.trafego_ledger_fechar('$REC'::uuid, 'sem_resposta', p_erro_mensagem := 'timeout de 30s');"
cmp_ "$(P -c "SELECT estado FROM trafego_lote_item WHERE item_id='$ITEM';")" "indeterminado" \
     "o item ficou \`indeterminado\` — não \`falhou\`, que seria convite a reenviar"
recusa "declarar \`falhou\` com recibo sem resposta (camada 2 da v10_01)" \
  "UPDATE trafego_lote_item SET estado='falhou', erro_mensagem='x' WHERE item_id='$ITEM';"
recusa "voltar a \`criando\` sem verificação concluída (camada 3 da v10_01)" \
  "UPDATE trafego_lote_item SET estado='criando' WHERE item_id='$ITEM';"

echo
echo "════ J · a reconciliação tardia fecha O MESMO recibo ════"
ITEM2=$(abrir_com 'volc-canary-tardia0001' "$IMPRESSAO" '5478096539')
REC2=$(P -c "SET ROLE service_role; SELECT public.trafego_ledger_despachar(
        'volc-canary-tardia0001','GOOGLE_ADS','5478096539','SEARCH','$IMPRESSAO','dono@volc','sub-1') ->> 'recibo_id';")
aceita "reconciliar: a campanha ESTAVA lá o tempo todo" \
  "SELECT public.trafego_ledger_reconciliar('$ITEM2'::uuid, 'busca_por_marca', true, 'operador',
     p_id_externo := '24183717006', p_volc_campaign_id := 'volc_cmp_tardia',
     p_customer_id := '5478096539', p_quantidade := 1);"
cmp_ "$(P -c "SELECT desfecho FROM trafego_recibo WHERE recibo_id='$REC2';")" "sucesso" \
     "o MESMO recibo fechou como sucesso — nenhum recibo novo foi aberto"
cmp_ "$(P -c "SELECT count(*)::text FROM trafego_recibo WHERE item_id='$ITEM2';")" "1" \
     "e continua existindo exatamente um recibo para o item"
cmp_ "$(P -c "SELECT estado||'|'||coalesce(id_externo,'-')||'|'||(id_externo_lido_em IS NOT NULL)::text
              FROM trafego_lote_item WHERE item_id='$ITEM2';")" \
     "criada_pausada|24183717006|true" "o item carimbou o id externo com a hora da leitura"

echo
echo "════ K · o id externo resolve para exatamente um item ════"
cmp_ "$(P -c "SELECT count(*)::text FROM trafego_lote_item WHERE id_externo='24183717006';")" "1" \
     "um id externo, um item"
cmp_ "$(P -c "SELECT procedencia FROM trafego_campanha WHERE volc_campaign_id='volc_cmp_tardia';")" \
     "volc_os" "a procedência da instância ficou declarada, não \`desconhecida\`"
# ⚠️ `p_quantidade := 1` é obrigatório AQUI: sem ele quem recusa é a CHECK
# `achou IS NOT TRUE OR quantidade >= 1` da v10_01, e a prova ficaria verde sem
# nunca ter exercitado a guarda que o rótulo anuncia. Medido: 23514 no lugar do
# 23001 da função. Uma prova que passa pelo motivo errado é pior que uma que falha.
recusa "verificação que diz \`achou\` sem trazer o id externo" \
  "SELECT public.trafego_ledger_reconciliar('$ITEM'::uuid, 'busca_por_marca', true, 'operador',
     p_quantidade := 1);"
aceita "verificação que não conseguiu ler (achou NULL) fica registrada" \
  "SELECT public.trafego_ledger_reconciliar('$ITEM'::uuid, 'listagem_da_conta', NULL, 'operador',
     p_motivo := 'a conta nao respondeu a listagem');"
cmp_ "$(P -c "SELECT estado FROM trafego_lote_item WHERE item_id='$ITEM';")" "indeterminado" \
     "não ler não move nada — ausência de leitura não é um fato sobre a conta"

echo
echo "════ N · erro RESPONDIDO é reentrável; ignorância não é ════"
ITEM3=$(abrir_com 'volc-canary-erro00000001' "$IMPRESSAO" '5478096539')
REC3=$(P -c "SET ROLE service_role; SELECT public.trafego_ledger_despachar(
        'volc-canary-erro00000001','GOOGLE_ADS','5478096539','SEARCH','$IMPRESSAO','dono@volc','sub-1') ->> 'recibo_id';")
aceita "fechar como \`erro\` (a plataforma respondeu que não criou)" \
  "SELECT public.trafego_ledger_fechar('$REC3'::uuid, 'erro', p_erro_codigo := 'INVALID_ARGUMENT',
     p_erro_mensagem := 'headline excede 30 caracteres');"
cmp_ "$(P -c "SELECT estado FROM trafego_lote_item WHERE item_id='$ITEM3';")" "falhou" \
     "o item ficou \`falhou\` — houve resposta, e resposta não é ignorância"
aceita "despachar de novo depois de erro respondido" \
  "SELECT public.trafego_ledger_despachar('volc-canary-erro00000001','GOOGLE_ADS','5478096539','SEARCH','$IMPRESSAO','dono@volc','sub-1');"
cmp_ "$(P -c "SELECT tentativas::text FROM trafego_lote_item WHERE item_id='$ITEM3';")" "2" \
     "a segunda tentativa foi contada, e a intenção não foi queimada"
cmp_ "$(P -c "SELECT count(*)::text FROM trafego_recibo WHERE item_id='$ITEM3';")" "2" \
     "dois recibos, um fechado e um em voo — nunca dois em voo"
recusa "despachar um item \`indeterminado\` (ignorância não é reentrável)" \
  "SELECT public.trafego_ledger_despachar('volc-canary-cadeia0001','GOOGLE_ADS','5478096539','SEARCH','$IMPRESSAO','dono@volc','sub-1');"

echo
echo "════ L · anon e authenticated não chamam o ledger ════"
cmp_ "$(P -c "SELECT count(*)::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='public' AND p.proname LIKE 'trafego\_ledger\_%'
                AND (has_function_privilege('anon', p.oid, 'EXECUTE')
                  OR has_function_privilege('authenticated', p.oid, 'EXECUTE'));")" \
     "0" "nenhuma função do ledger é executável por anon/authenticated"
cmp_ "$(P -c "SELECT count(*)::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='public' AND p.proname LIKE 'trafego\_ledger\_%' AND p.prosecdef;")" \
     "0" "nenhuma é SECURITY DEFINER"
cmp_ "$(P -c "SELECT count(*)::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='public' AND p.proname LIKE 'trafego\_ledger\_%'
                AND has_function_privilege('service_role', p.oid, 'EXECUTE');")" \
     "4" "as quatro são executáveis por service_role"

echo
echo "════ M · o rollback devolve o banco, e a v10_01 fica inteira ════"
# Contado, nunca fixado: um número cravado aqui vira falha toda vez que uma prova
# nova semeia um item, e a mensagem culparia o rollback.
ITENS_ANTES=$(P -c "SELECT count(*)::text FROM trafego_lote_item;")
aplicar "v10_03_rollback"
cmp_ "$(P -c "SELECT count(*)::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='public' AND p.proname LIKE 'trafego\_ledger\_%';")" "0" \
     "as funções do ledger sumiram"
cmp_ "$(P -c "SELECT count(*)::text FROM information_schema.columns
              WHERE table_schema='public' AND table_name='trafego_lote_item'
                AND column_name IN ('plano_impressao','aprovado_por','aprovado_por_sub','aprovado_em','aprovacao_impressao');")" \
     "0" "as colunas de aprovação sumiram"
cmp_ "$(P -c "SELECT count(*)::text FROM pg_trigger WHERE tgname='trafego_item_estado_valido';")" "1" \
     "o gatilho da v10_01 continua lá — o rollback não reescreveu regra alheia"
cmp_ "$(P -c "SELECT count(*)::text FROM trafego_lote_item;")" "$ITENS_ANTES" \
     "e os $ITENS_ANTES itens já registrados continuam de pé"
aplicar "v10_03_recibo_atomico"
cmp_ "$(P -c "SELECT count(*)::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='public' AND p.proname LIKE 'trafego\_ledger\_%';")" "4" \
     "reaplicada sobre banco com dado: as quatro voltaram"

echo
echo "════════════════════════════════════════════════"
if [ "$FALHAS" -eq 0 ]; then
    echo "  FRONTEIRA ATÔMICA PROVADA — o defeito reproduzido está fechado"
    exit 0
else
    echo "  $FALHAS PROVA(S) FALHARAM"
    exit 1
fi
