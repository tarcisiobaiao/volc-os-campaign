#!/usr/bin/env bash
#
# O ciclo completo da série v10 num Postgres descartável — aplicar, reverter,
# reaplicar — com prova de segurança e prova de COMPORTAMENTO em cada degrau.
#
# ## Por que um script, e não um comando anotado
#
# Um rollback só existe se alguém o executa. O da v9_03 estava documentado como
# "reaplique a v9_02" e **abortava** — `cannot drop columns from view` —, e isso
# só apareceu quando a auditoria adversarial tentou. Este script roda o ciclo
# inteiro do zero, a cada execução, num cluster que nasce e morre aqui. Ele não
# toca em nada fora de /tmp e NUNCA fala com o banco de produção.
#
# ## O que ele prova
#
# ESTRUTURA, em cada degrau:
#   · a migration aplica sem erro;
#   · os objetos que ela promete existem (ou sumiram, no rollback);
#   · `service_role` lê as views e NÃO escreve nelas;
#   · `anon`/`authenticated` sem NENHUM dos 4 privilégios em NENHUMA tabela;
#   · `security_invoker` ligado em todas as views;
#   · RLS ligada E forçada, com zero policies;
#   · DELETE não concedido a ninguém.
#
# COMPORTAMENTO — as guardas que justificam o schema inteiro:
#   1. a mesma chave de idempotência não entra duas vezes;
#   2. o segundo SUCESSO com a mesma chave é fisicamente recusado;
#   3. o item com recibo EM VOO não pode ser declarado `falhou`;
#   4. o lote não executa sem aprovação humana;
#   5. `null` de verificação não é `false` — e o número sem carimbo é recusado;
#   6. a proposta que estoura o limite da regra é recusada;
#   7. a proposta sobre evidência insuficiente é recusada;
#   8. a aplicação com aprovação de OUTRA proposta é recusada;
#   9. o cooldown nasce sozinho e bloqueia a aplicação seguinte;
#  10. `proxima_acao` do Python e a da view respondem a MESMA coisa.
#
# INDEPENDÊNCIA: reverter a v10_02 não derruba a v10_01, e nenhuma das duas
# toca no inventário da v9.
#
# Uso:  ./scripts/provar-ciclo-v10.sh

set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
M="$RAIZ/supabase/migrations"

for b in initdb pg_ctl psql; do
    command -v "$b" >/dev/null 2>&1 || { echo "falta $b — brew install postgresql@16"; exit 2; }
done
PY="$RAIZ/backend/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 || true)"
# O comparador Python x view importa `app.trafego.lote`. Sem este default, o
# degrau 2 falharia com um ImportError que nao fala de PYTHONPATH.
export BACKEND="${BACKEND:-$RAIZ/backend}"

# ⚠️ /tmp e não o scratchpad: o socket unix tem teto de 103 bytes no caminho, e
# um diretório fundo estoura com uma mensagem que não fala de tamanho.
D=$(mktemp -d /tmp/volcv10XXXX)
export LC_ALL=C LANG=C
limpar() { pg_ctl -D "$D/d" -m immediate stop >/dev/null 2>&1; rm -rf "$D"; }
trap limpar EXIT

initdb -D "$D/d" -U postgres --encoding=UTF8 --locale=C >/dev/null 2>&1
mkdir -p "$D/s"
pg_ctl -D "$D/d" -l "$D/pg.log" -o "-k $D/s -h ''" -w start >/dev/null 2>&1

P() { psql -h "$D/s" -U postgres -X -q -A -t "$@"; }

# Os papéis do Supabase, INCLUSIVE o default ACL quebrado de `public` (achado H,
# 24/08/2026) — sem reproduzir o defeito, a prova de que a migration fecha a
# tabela mediria um ambiente mais seguro que o real.
P -c "CREATE ROLE anon NOLOGIN NOINHERIT;
      CREATE ROLE authenticated NOLOGIN NOINHERIT;
      CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
      GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
      ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT ALL ON TABLES TO anon, authenticated, service_role;" >/dev/null

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

# `recusa <rótulo> <sql>` — a prova NEGATIVA. Ela é a que importa: uma guarda
# que ninguém tentou furar é uma guarda que ninguém sabe se existe.
#: **A guarda disparou** — por CLASSE, não por código solto.
#:
#:   P0001  `RAISE EXCEPTION` de gatilho ou função
#:   23xxx  violação de restrição de integridade: CHECK (23514), chave duplicada
#:          (23505), chave estrangeira (23503), NOT NULL (23502), exclusão
#:          (23P01) e **restrict_violation (23001)**
#:
#: ⚠️ A primeira versão desta lista enumerava códigos e **esquecia o 23001** —
#: que é justamente o que as guardas desta migration usam, via
#: `USING ERRCODE = 'restrict_violation'`. O efeito foi imediato e didático: o
#: harness passou a acusar "o DONO passou" nas quatro guardas que estavam
#: funcionando perfeitamente. Uma lista por enumeração envelhece a cada guarda
#: nova; a classe 23 inteira é a afirmação que se queria fazer.
GUARDA_DISPAROU='^(P0001|23[0-9A-Z]{3})$'

#: **A PROVA está quebrada**, não o código sob prova. Classe 42 é violação de
#: regra de sintaxe ou de acesso — tabela (42P01) ou coluna (42703) inexistente,
#: sintaxe (42601), permissão (42501), função (42883). `3F000` é schema que não
#: existe e `22P02` é literal malformado (um uuid torto no WHERE, por exemplo).
PROVA_QUEBRADA='^(42[0-9A-Z]{3}|3F000|22P02)$'

# `recusa <rótulo> <sql>` — a prova NEGATIVA, e ela precisa de DUAS afirmações.
#
# ⚠️ Uma guarda que ninguém tentou furar é uma guarda que ninguém sabe se
# existe. Mas "a instrução deu erro" não prova que a guarda funcionou: tabela
# renomeada, coluna com typo, sintaxe torta e permissão faltando **também** dão
# erro, e a versão anterior desta função marcava os quatro como RECUSADO.
#
# Medido em 26/08/2026, contra um Postgres limpo:
#
#     tabela inexistente → 42P01     erro de sintaxe   → 42601
#     coluna inexistente → 42703     permissão negada  → 42501
#     guarda de gatilho  → P0001     CHECK violado     → 23514
#
# Os dois grupos não se tocam. Então a prova passou a exigir o SQLSTATE certo:
# um rename de tabela agora DERRUBA a prova em vez de mantê-la verde com a
# guarda ausente — que é o modo de falha mais caro que um harness pode ter,
# porque ele não some, ele mente.
recusa() {
    local rotulo="$1"; shift
    local saida rc estado
    saida=$(printf '\\set VERBOSITY verbose\nSET ROLE service_role;\n%s\n' "$*" \
            | psql -h "$D/s" -U postgres -X -A -t 2>&1); rc=$?
    printf '%s' "$saida" > "$D/err"
    estado=$(printf '%s' "$saida" | grep -oE '^ERROR:  [0-9A-Z]{5}:' | head -1 | awk '{print $2}' | tr -d ':')

    if [ -n "$estado" ]; then
        if printf '%s' "$estado" | grep -qE "$GUARDA_DISPAROU"; then
            ok "$rotulo — RECUSADO ($estado)"
        elif printf '%s' "$estado" | grep -qE "$PROVA_QUEBRADA"; then
            nao "$rotulo — a PROVA está quebrada ($estado), não o código: $(printf '%s' "$saida" | grep -m1 '^ERROR' | cut -c1-100)"
        else
            # SQLSTATE desconhecido: pode ser guarda legítima nova. Aceita, mas
            # DIZ qual foi — para ninguém descobrir a mudança por acaso.
            ok "$rotulo — RECUSADO ($estado, não catalogado)"
        fi
    elif printf '%s' "$saida" | grep -qE '^(UPDATE|DELETE) 0$'; then
        # ⚠️ A PROVA MEDIU O VAZIO. Um UPDATE que não encontra linha nenhuma sai
        # com sucesso, e a recusa fica verde por falta de alvo — não por a
        # guarda ter funcionado. Foi exatamente assim que a guarda de
        # `valor_anterior` passou na primeira rodada, com a linha inexistente.
        nao "$rotulo — não tocou linha nenhuma: a prova mediria o vazio"
    elif [ $rc -ne 0 ]; then
        nao "$rotulo — erro sem SQLSTATE (conexão? psql?): $(printf '%s' "$saida" | head -1 | cut -c1-100)"
    else
        nao "$rotulo — PASSOU, e não deveria"
    fi
}

# `recusa_em_camadas <rótulo> <sql>` — para o que é protegido DUAS vezes.
#
# ⚠️ O achado que criou esta função. Quatro provas estavam verdes por 42501
# (permissão negada) — a propriedade era verdadeira, mas garantida pela AUSÊNCIA
# DE GRANT, e o rótulo dizia "a intenção continua imutável", que sugere gatilho.
# A camada de privilégio SOMBREIA a de gatilho: como `service_role` nem alcança
# a tabela, os gatilhos `trafego_intencao_imutavel`, `trafego_item_sem_delete` e
# o append-only NUNCA FORAM EXECUTADOS por prova nenhuma.
#
# Isso importa no dia em que alguém conceder UPDATE para consertar outra coisa:
# a proteção passaria a depender inteiramente de um gatilho que ninguém nunca
# viu disparar. Duas camadas provadas uma vez cada valem mais que duas camadas
# das quais só a de fora foi testada.
#
#   camada 1 — `service_role`: recusado por privilégio (42501) OU por guarda
#   camada 2 — o DONO da tabela, que passa pelo GRANT: recusado por GUARDA
recusa_em_camadas() {
    local rotulo="$1"; shift
    local saida estado

    # camada 1 · a muralha de fora
    saida=$(printf '\\set VERBOSITY verbose\nSET ROLE service_role;\n%s\n' "$*" \
            | psql -h "$D/s" -U postgres -X -A -t 2>&1)
    estado=$(printf '%s' "$saida" | grep -oE '^ERROR:  [0-9A-Z]{5}:' | head -1 | awk '{print $2}' | tr -d ':')
    if [ "$estado" = "42501" ]; then
        ok "$rotulo · camada 1 — sem privilégio (42501)"
    elif printf '%s' "$estado" | grep -qE "$GUARDA_DISPAROU"; then
        ok "$rotulo · camada 1 — guarda ($estado)"
    else
        nao "$rotulo · camada 1 — nem privilégio nem guarda (${estado:-sem erro})"
        return
    fi

    # camada 2 · o dono passa pelo GRANT; só a guarda pode barrá-lo
    saida=$(printf '\\set VERBOSITY verbose\n%s\n' "$*" \
            | psql -h "$D/s" -U postgres -X -A -t 2>&1)
    estado=$(printf '%s' "$saida" | grep -oE '^ERROR:  [0-9A-Z]{5}:' | head -1 | awk '{print $2}' | tr -d ':')
    if printf '%s' "$estado" | grep -qE "$GUARDA_DISPAROU"; then
        ok "$rotulo · camada 2 — a GUARDA disparou ($estado)"
    elif printf '%s' "$estado" | grep -qE "$PROVA_QUEBRADA"; then
        nao "$rotulo · camada 2 — a PROVA está quebrada ($estado)"
    elif printf '%s' "$saida" | grep -qE '^(UPDATE|DELETE) 0$'; then
        nao "$rotulo · camada 2 — não tocou linha nenhuma: mediria o vazio"
    else
        nao "$rotulo · camada 2 — o DONO passou. A guarda NÃO pega este caso [$(printf '%s' "$saida" | tr '\n' '|' | cut -c1-70)]"
    fi
}
aceita() {
    local rotulo="$1"; shift
    if P -c "SET ROLE service_role; $*" >"$D/err" 2>&1; then
        ok "$rotulo"
    else
        nao "$rotulo — recusou e não deveria"; tail -2 "$D/err" | sed 's/^/      /'
    fi
}

# ⚠️ A semeadura NAO pode engolir erro. Este bloco terminava com
# `>/dev/null 2>&1`, e quando o INSERT passasse a ser recusado por uma guarda
# nova, a falha sumiria — e a prova seguinte, que depende destas duas linhas,
# ficaria verde por violacao de chave estrangeira em vez de pela guarda que ela
# diz provar. Fixture silenciosa e como uma secao inteira de teste vira
# decoracao.
#
# O alvo tambem passou a ser a campanha da evidencia: esta proposta existe para
# provar OUTRA coisa (que a aplicacao exige a aprovacao daquela proposta), e uma
# fixture ilegitima numa dimensao que nao esta sob teste faz a prova passar pelo
# motivo errado.
semear() {
    if psql -h "$D/s" -U postgres -X -q -v ON_ERROR_STOP=1 -c "SET ROLE service_role; $*" >"$D/err" 2>&1; then
        return 0
    fi
    nao "SEMEADURA FALHOU — a prova seguinte mediria outra coisa: $(head -3 "$D/err" | tr '\n' ' ' | cut -c1-150)"
    return 1
}


existe() { P -c "SELECT (to_regclass('public.$1') IS NOT NULL)::text;"; }
invoker() {
    P -c "SELECT count(*)::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND c.relkind='v' AND c.relname = ANY(ARRAY[$1])
             AND NOT coalesce((SELECT option_value='true' FROM pg_options_to_table(c.reloptions)
                               WHERE option_name='security_invoker'), false);"
}

# ── a bateria de segurança, aplicada a uma lista de objetos ─────────────────
seguranca() {
    local etapa="$1"; shift
    local lista="$1"; shift   # ex.: "'trafego_lote','trafego_recibo'"
    local views="$1"

    local abertas
    abertas=$(P -c "SELECT coalesce(string_agg(DISTINCT c.relname, ','), '')
                      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE n.nspname='public' AND c.relname = ANY(ARRAY[$lista])
                       AND (has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE')
                            OR has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE'));")
    cmp_ "$abertas" "" "$etapa · anon e authenticated SEM acesso (4 privilégios × 2 papéis)"

    local sem_rls
    sem_rls=$(P -c "SELECT coalesce(string_agg(c.relname, ','), '')
                      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE n.nspname='public' AND c.relname = ANY(ARRAY[$lista])
                       AND c.relkind='r' AND NOT (c.relrowsecurity AND c.relforcerowsecurity);")
    cmp_ "$sem_rls" "" "$etapa · RLS ligada E forçada em toda tabela"

    local policies
    policies=$(P -c "SELECT coalesce(string_agg(tablename, ','), '') FROM pg_policies
                      WHERE schemaname='public' AND tablename = ANY(ARRAY[$lista]);")
    cmp_ "$policies" "" "$etapa · zero policies (a negação é por AUSÊNCIA)"

    local com_delete
    com_delete=$(P -c "SELECT coalesce(string_agg(c.relname, ','), '')
                         FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE n.nspname='public' AND c.relname = ANY(ARRAY[$lista])
                          AND c.relkind='r'
                          AND has_table_privilege('service_role', c.oid, 'DELETE');")
    cmp_ "$com_delete" "" "$etapa · DELETE não concedido a ninguém"

    cmp_ "$(invoker "$views")" "0" "$etapa · security_invoker ligado em toda view"

    local view_escrivel
    view_escrivel=$(P -c "SELECT coalesce(string_agg(c.relname, ','), '')
                            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                           WHERE n.nspname='public' AND c.relname = ANY(ARRAY[$views])
                             AND (has_table_privilege('service_role', c.oid, 'INSERT')
                               OR has_table_privilege('service_role', c.oid, 'UPDATE')
                               OR has_table_privilege('service_role', c.oid, 'DELETE'));")
    cmp_ "$view_escrivel" "" "$etapa · service_role SÓ com SELECT nas views"
}

T01="'trafego_intencao','trafego_blueprint','trafego_lote','trafego_lote_item','trafego_lote_asset','trafego_validacao','trafego_recibo','trafego_verificacao','trafego_rollback','trafego_lote_transicao'"
V01="'trafego_item_situacao','trafego_lote_painel'"
T02="'trafego_regra_otimizacao','trafego_evidencia','trafego_diagnostico','trafego_proposta','trafego_aprovacao','trafego_aplicacao','trafego_acompanhamento','trafego_atuacao_reversao','trafego_cooldown'"
V02="'trafego_regra_vigente','trafego_cooldown_ativo','trafego_proposta_painel'"

echo "════ 0 · a base: a série v9 aplicada ════"
for m in v9_01_trafego_inventario v9_02_atencao_sem_removida \
         v9_03_historico_e_ordem_operacional v9_04_url_final_preservada; do
    aplicar "$m"
done

echo
echo "════ 1 · aplicar a v10 ════"
aplicar "v10_01_intencao_e_lote"
aplicar "v10_02_autogestao"
cmp_ "$(existe trafego_lote_item)" "true" "v10_01 · trafego_lote_item existe"
cmp_ "$(existe trafego_regra_otimizacao)" "true" "v10_02 · trafego_regra_otimizacao existe"
seguranca "aplicado v10_01" "$T01" "$V01"
seguranca "aplicado v10_02" "$T02" "$V02"

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "════ 2 · o ciclo de criação, exercitado ════"

# A campanha da v9 que o item vai adotar quando for criada.
semear "
  INSERT INTO trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
    VALUES ('gads-8017851692-901','8017851692','901','prova'),
           ('gads-8017851692-902','8017851692','902','prova');"

semear "
  INSERT INTO trafego_intencao (intencao_id, plataforma, conta_externa, objetivo,
      rotulo, declarada_por, declarada_com_base_em)
    VALUES ('11111111-1111-1111-1111-111111111111','GOOGLE_ADS','8017851692',
            'leads','FGTS agosto','tarcisio','pauta 812');
  INSERT INTO trafego_blueprint (blueprint_id, chave, versao, plataforma, canal,
      titulo, corpo, declarado_por)
    VALUES ('22222222-2222-2222-2222-222222222222','search_padrao',1,
            'GOOGLE_ADS','SEARCH','Search padrao','{}'::jsonb,'tarcisio');
  INSERT INTO trafego_lote (lote_id, intencao_id, blueprint_id, plataforma,
      conta_externa, canal, criado_por)
    VALUES ('33333333-3333-3333-3333-333333333333',
            '11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222','GOOGLE_ADS','8017851692',
            'SEARCH','tarcisio');
  INSERT INTO trafego_lote_item (item_id, lote_id, ordem, idempotency_key, rotulo, plano)
    VALUES ('44444444-4444-4444-4444-444444444444',
            '33333333-3333-3333-3333-333333333333',0,
            'volc-gads-0000-aaaaaaaaaaaaaaaa','FGTS exato','{\"nome\":\"a\"}'::jsonb);"

# ── 1. a chave é única na tabela inteira ───────────────────────────────────
recusa "chave de idempotência repetida (outro lote, mesma chave)" \
  "INSERT INTO trafego_lote_item (lote_id, ordem, idempotency_key, rotulo, plano)
     VALUES ('33333333-3333-3333-3333-333333333333',1,
             'volc-gads-0000-aaaaaaaaaaaaaaaa','clone','{}'::jsonb);"

recusa "chave curta demais (colidiria como rótulo na conta)" \
  "INSERT INTO trafego_lote_item (lote_id, ordem, idempotency_key, rotulo, plano)
     VALUES ('33333333-3333-3333-3333-333333333333',2,'abc','x','{}'::jsonb);"

# ── 4. aprovação humana é estrutural ───────────────────────────────────────
semear "
  UPDATE trafego_lote SET estado='validando' WHERE lote_id='33333333-3333-3333-3333-333333333333';
  UPDATE trafego_lote SET estado='aguardando_aprovacao' WHERE lote_id='33333333-3333-3333-3333-333333333333';
  UPDATE trafego_lote SET estado='aprovado' WHERE lote_id='33333333-3333-3333-3333-333333333333';"

recusa "lote executa SEM aprovação humana registrada" \
  "UPDATE trafego_lote SET estado='executando' WHERE lote_id='33333333-3333-3333-3333-333333333333';"

aceita "lote executa DEPOIS da aprovação" \
  "UPDATE trafego_lote SET aprovado_por='tarcisio', aprovado_em=now()
     WHERE lote_id='33333333-3333-3333-3333-333333333333';
   UPDATE trafego_lote SET estado='executando'
     WHERE lote_id='33333333-3333-3333-3333-333333333333';"

recusa "aprovação já dada é reescrita" \
  "UPDATE trafego_lote SET aprovado_por='outro'
     WHERE lote_id='33333333-3333-3333-3333-333333333333';"

recusa "transição de estado que não existe (executando -> preparando)" \
  "UPDATE trafego_lote SET estado='preparando' WHERE lote_id='33333333-3333-3333-3333-333333333333';"

# ── ⚠️ 3. O CASO INTEIRO: TIMEOUT MAS CRIOU ────────────────────────────────
semear "
  UPDATE trafego_lote_item SET estado='validado_local' WHERE item_id='44444444-4444-4444-4444-444444444444';
  UPDATE trafego_lote_item SET estado='validado_remoto' WHERE item_id='44444444-4444-4444-4444-444444444444';
  UPDATE trafego_lote_item SET estado='aprovado' WHERE item_id='44444444-4444-4444-4444-444444444444';
  UPDATE trafego_lote_item SET estado='criando', tentativas=1 WHERE item_id='44444444-4444-4444-4444-444444444444';
  -- O recibo nasce ANTES da chamada. O processo morre aqui.
  INSERT INTO trafego_recibo (recibo_id, item_id, idempotency_key, tentativa, operacao, enviado_em)
    VALUES ('55555555-5555-5555-5555-555555555555',
            '44444444-4444-4444-4444-444444444444',
            'volc-gads-0000-aaaaaaaaaaaaaaaa',1,'criar_campanha', now());"

cmp_ "$(P -c "SELECT desfecho FROM trafego_recibo WHERE recibo_id='55555555-5555-5555-5555-555555555555';")" \
     "em_voo" "recibo sobrevive à queda do processo como 'em_voo'"

recusa "⚠️ item declarado 'falhou' com recibo EM VOO (criaria a 2ª campanha)" \
  "UPDATE trafego_lote_item SET estado='falhou', erro_codigo='TIMEOUT',
      erro_mensagem='sem resposta', erro_em=now()
     WHERE item_id='44444444-4444-4444-4444-444444444444';"

aceita "item vai para 'indeterminado' — o estado honesto" \
  "UPDATE trafego_lote_item SET estado='indeterminado'
     WHERE item_id='44444444-4444-4444-4444-444444444444';"

cmp_ "$(P -c "SELECT proxima_acao FROM trafego_item_situacao WHERE item_id='44444444-4444-4444-4444-444444444444';")" \
     "verificar" "⚠️ a view manda VERIFICAR, nunca reenviar"

# A verificação remota encontra a campanha: ela FOI criada.
aceita "verificação remota encontra a campanha pela marca" \
  "INSERT INTO trafego_verificacao (item_id, recibo_id, verificado_em, verificado_por,
      metodo, achou, id_externo_encontrado, quantidade_encontrada)
     VALUES ('44444444-4444-4444-4444-444444444444',
             '55555555-5555-5555-5555-555555555555', now(),'reconciliador',
             'busca_por_marca', true, '901', 1);"

recusa "verificação que não conseguiu ler, e sem dizer por quê" \
  "INSERT INTO trafego_verificacao (item_id, verificado_em, verificado_por, metodo, achou)
     VALUES ('44444444-4444-4444-4444-444444444444', now(),'r','busca_por_marca', NULL);"

recusa "id externo observado SEM carimbo de leitura (regra A)" \
  "UPDATE trafego_lote_item SET id_externo='901'
     WHERE item_id='44444444-4444-4444-4444-444444444444';"

aceita "recibo fecha como sucesso e o item adota a campanha" \
  "UPDATE trafego_recibo SET desfecho='sucesso', respondido_em=now(),
      resposta_id_externo='901', request_id='req-1'
     WHERE recibo_id='55555555-5555-5555-5555-555555555555';
   UPDATE trafego_lote_item SET id_externo='901', id_externo_lido_em=now(),
      volc_campaign_id='gads-8017851692-901', estado='criada_pausada'
     WHERE item_id='44444444-4444-4444-4444-444444444444';"

# ── ⚠️ 2. o segundo sucesso com a mesma chave ──────────────────────────────
recusa "⚠️ SEGUNDO sucesso com a mesma (chave, operação)" \
  "INSERT INTO trafego_recibo (item_id, idempotency_key, tentativa, operacao,
      enviado_em, respondido_em, desfecho, resposta_id_externo)
     VALUES ('44444444-4444-4444-4444-444444444444',
             'volc-gads-0000-aaaaaaaaaaaaaaaa',2,'criar_campanha',
             now(), now(),'sucesso','999');"

recusa "recibo fechado reabre" \
  "UPDATE trafego_recibo SET desfecho='erro', erro_mensagem='x'
     WHERE recibo_id='55555555-5555-5555-5555-555555555555';"

recusa "sucesso sem o id que a plataforma devolveu" \
  "INSERT INTO trafego_recibo (item_id, idempotency_key, tentativa, operacao,
      enviado_em, respondido_em, desfecho)
     VALUES ('44444444-4444-4444-4444-444444444444',
             'volc-gads-0000-aaaaaaaaaaaaaaaa',3,'pausar', now(), now(),'sucesso');"

# ── 4b. duas campanhas para a mesma chave, e a duplicidade que ela pega ─────
semear "
  INSERT INTO trafego_lote_item (item_id, lote_id, ordem, idempotency_key, rotulo, plano)
    VALUES ('66666666-6666-6666-6666-666666666666',
            '33333333-3333-3333-3333-333333333333',9,
            'volc-gads-0009-bbbbbbbbbbbbbbbb','outro','{}'::jsonb);"

recusa "dois itens reivindicando a MESMA campanha" \
  "UPDATE trafego_lote_item SET id_externo='901', id_externo_lido_em=now(),
      volc_campaign_id='gads-8017851692-901'
     WHERE item_id='66666666-6666-6666-6666-666666666666';"

# ── 5. append-only e DELETE ────────────────────────────────────────────────
recusa_em_camadas "DELETE em trafego_lote_item" \
  "DELETE FROM trafego_lote_item WHERE item_id='66666666-6666-6666-6666-666666666666';"
recusa_em_camadas "UPDATE em trafego_verificacao (append-only)" \
  "UPDATE trafego_verificacao SET achou=false WHERE item_id='44444444-4444-4444-4444-444444444444';"
recusa_em_camadas "UPDATE na intenção declarada" \
  "UPDATE trafego_intencao SET objetivo='outro' WHERE intencao_id='11111111-1111-1111-1111-111111111111';"

# ── 6. o diário de transições nasceu sozinho ───────────────────────────────
TRANS=$(P -c "SELECT count(*)::text FROM trafego_lote_transicao WHERE lote_id='33333333-3333-3333-3333-333333333333';")
[ "$TRANS" -ge 8 ] && ok "diário de transições escrito por gatilho ($TRANS linhas)" \
                   || nao "diário de transições vazio demais ($TRANS)"

# ── 10. Python e SQL respondem a MESMA coisa ───────────────────────────────
echo "  ── proxima_acao: Python × view ──"
semear "
  INSERT INTO trafego_lote_item (item_id, lote_id, ordem, idempotency_key, rotulo, plano, estado)
    VALUES ('77777777-7777-7777-7777-777777777777','33333333-3333-3333-3333-333333333333',
            20,'volc-gads-0020-cccccccccccccccc','aprovado','{}'::jsonb,'planejado');
  UPDATE trafego_lote_item SET estado='validado_local' WHERE item_id='77777777-7777-7777-7777-777777777777';
  UPDATE trafego_lote_item SET estado='validado_remoto' WHERE item_id='77777777-7777-7777-7777-777777777777';
  UPDATE trafego_lote_item SET estado='aprovado' WHERE item_id='77777777-7777-7777-7777-777777777777';"

P -c "SELECT item_id||'|'||estado||'|'||coalesce(recibo_em_voo_id::text,'')||'|'||
             coalesce(ultima_verificacao_quantidade::text,'')||'|'||proxima_acao
        FROM trafego_item_situacao ORDER BY item_id;" > "$D/view.txt"

if "$PY" - "$D/view.txt" <<'PYEOF' >"$D/py.txt" 2>"$D/pyerr.txt"
import sys, os
sys.path.insert(0, os.environ["BACKEND"])
from app.trafego import lote as lo
saida = []
for linha in open(sys.argv[1], encoding="utf-8"):
    linha = linha.rstrip("\n")
    if not linha:
        continue
    item, estado, em_voo, qtd, acao_sql = linha.split("|")
    acao_py = lo.proxima_acao({
        "item_id": item, "estado": estado,
        "recibo_em_voo_id": em_voo or None,
        "ultima_verificacao_quantidade": int(qtd) if qtd else None})
    saida.append(f"{item}|{acao_sql}|{acao_py}|{'OK' if acao_sql == acao_py else 'DIVERGE'}")
print("\n".join(saida))
PYEOF
then
    DIVERGE=$(grep -c DIVERGE "$D/py.txt" || true)
    LINHAS=$(grep -c . "$D/py.txt" || true)
    cmp_ "$DIVERGE" "0" "proxima_acao: Python e view concordam em $LINHAS item(ns)"
    [ "$DIVERGE" = "0" ] || grep DIVERGE "$D/py.txt" | sed 's/^/      /'
else
    nao "não consegui comparar Python × view"; tail -3 "$D/pyerr.txt" | sed 's/^/      /'
fi

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "════ 3 · a autogestão, exercitada ════"

semear "
  INSERT INTO trafego_regra_otimizacao (regra_id, chave, versao, titulo, objetivo,
      plataformas, canais, janela_minima_dias, atraso_conversao_dias,
      frescor_maximo_horas, amostra_minima_cliques, dados_obrigatorios,
      teto_orcamento_micros, teto_orcamento_moeda, limite_alteracao_pct,
      cooldown_horas, confianca_minima, condicao_rollback, rollback_janela_horas,
      responsavel, deteccao, acao, declarada_por, fonte, vigente_desde)
    VALUES ('a1111111-1111-1111-1111-111111111111','ajustar_verba',1,
            'Ajustar verba','eficiencia', ARRAY['GOOGLE_ADS'], ARRAY['SEARCH'],
            7, 3, 24, 30, ARRAY['cliques','custo_micros'],
            100000000,'BRL', 20, 24, 0.8, 'cpa subiu 30 por cento', 72,
            'tarcisio','{}'::jsonb,'{}'::jsonb,'tarcisio','humano', now());"

recusa "⚠️ regra em nível T2 (a máquina aplicando sozinha — ADR-11)" \
  "INSERT INTO trafego_regra_otimizacao (chave, versao, titulo, objetivo, plataformas,
      canais, janela_minima_dias, atraso_conversao_dias, frescor_maximo_horas,
      amostra_minima_cliques, dados_obrigatorios, limite_alteracao_pct, cooldown_horas,
      confianca_minima, condicao_rollback, rollback_janela_horas, responsavel,
      nivel_autonomia, deteccao, acao, declarada_por, fonte)
    VALUES ('regra_t2',1,'t','o',ARRAY['GOOGLE_ADS'],ARRAY['*'],7,3,24,30,
            ARRAY['cliques'],20,24,0.8,'c',72,'r','T2','{}'::jsonb,'{}'::jsonb,'d','f');"

recusa "regra SEM limite de alteração (autorização ilimitada)" \
  "INSERT INTO trafego_regra_otimizacao (chave, versao, titulo, objetivo, plataformas,
      canais, janela_minima_dias, atraso_conversao_dias, frescor_maximo_horas,
      amostra_minima_cliques, dados_obrigatorios, cooldown_horas, confianca_minima,
      condicao_rollback, rollback_janela_horas, responsavel, deteccao, acao,
      declarada_por, fonte)
    VALUES ('sem_limite',1,'t','o',ARRAY['GOOGLE_ADS'],ARRAY['*'],7,3,24,30,
            ARRAY['cliques'],24,0.8,'c',72,'r','{}'::jsonb,'{}'::jsonb,'d','f');"

recusa "regra SEM amostra mínima (dispara sobre 1 clique)" \
  "INSERT INTO trafego_regra_otimizacao (chave, versao, titulo, objetivo, plataformas,
      canais, janela_minima_dias, atraso_conversao_dias, frescor_maximo_horas,
      dados_obrigatorios, limite_alteracao_pct, cooldown_horas, confianca_minima,
      condicao_rollback, rollback_janela_horas, responsavel, deteccao, acao,
      declarada_por, fonte)
    VALUES ('sem_amostra',1,'t','o',ARRAY['GOOGLE_ADS'],ARRAY['*'],7,3,24,
            ARRAY['cliques'],20,24,0.8,'c',72,'r','{}'::jsonb,'{}'::jsonb,'d','f');"

recusa "regra imutável reescrita (mudaria o porquê de um gasto antigo)" \
  "UPDATE trafego_regra_otimizacao SET limite_alteracao_pct=90
     WHERE regra_id='a1111111-1111-1111-1111-111111111111';"

# Evidência ainda NÃO avaliada + diagnóstico.
semear "
  INSERT INTO trafego_evidencia (evidencia_id, regra_id, plataforma, conta_externa,
      volc_campaign_id, janela_inicio, janela_fim, colhida_em, origem,
      cliques, custo_micros, moeda)
    VALUES ('b1111111-1111-1111-1111-111111111111',
            'a1111111-1111-1111-1111-111111111111','GOOGLE_ADS','8017851692',
            'gads-8017851692-901','2026-08-15','2026-08-22', now(),
            'trafego_campanha_espelho', 120, 45000000,'BRL');
  INSERT INTO trafego_diagnostico (diagnostico_id, evidencia_id, regra_id,
      detectado_em, produtor, sintoma, explicacao, confianca, severidade)
    VALUES ('c1111111-1111-1111-1111-111111111111',
            'b1111111-1111-1111-1111-111111111111',
            'a1111111-1111-1111-1111-111111111111', now(),'motor',
            'cpa acima do alvo','cliques 120 e custo 45 BRL', 0.9,'media');"

PROP="INSERT INTO trafego_proposta (proposta_id, diagnostico_id, regra_id,
      volc_campaign_id, alvo_nivel, alvo_chave, operacao, valor_atual,
      valor_atual_lido_em, valor_proposto, delta_pct, moeda, idempotency_key, criada_por, expira_em)
    VALUES ('d1111111-1111-1111-1111-111111111111',
            'c1111111-1111-1111-1111-111111111111',
            'a1111111-1111-1111-1111-111111111111','gads-8017851692-901',
            'campanha','campanha:gads-8017851692-901','ajustar_orcamento',
            '{\"verba_diaria_micros\": 50000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 55000000}'::jsonb, 10,'BRL',
            'volc-prop-0000-dddddddddddddddd',
            'motor', now() + interval '1 day');"

# ── 7. evidência ainda não avaliada não sustenta proposta ──────────────────
recusa "⚠️ proposta sobre evidência NÃO avaliada" "$PROP"

semear "
  UPDATE trafego_evidencia SET suficiencia='insuficiente', suficiencia_em=now(),
      suficiencia_motivo='faltou conversoes', faltantes=ARRAY['conversoes']
    WHERE evidencia_id='b1111111-1111-1111-1111-111111111111';"
recusa "⚠️ proposta sobre evidência INSUFICIENTE" "$PROP"

recusa "reavaliar uma suficiência já declarada" \
  "UPDATE trafego_evidencia SET suficiencia='suficiente'
     WHERE evidencia_id='b1111111-1111-1111-1111-111111111111';"

recusa "reescrever uma MEDIDA da evidência" \
  "UPDATE trafego_evidencia SET cliques=9999
     WHERE evidencia_id='b1111111-1111-1111-1111-111111111111';"

# Uma evidência nova, agora suficiente.
semear "
  INSERT INTO trafego_evidencia (evidencia_id, regra_id, plataforma, conta_externa,
      volc_campaign_id, janela_inicio, janela_fim, colhida_em, origem,
      cliques, custo_micros, moeda, suficiencia, suficiencia_em)
    VALUES ('b2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','GOOGLE_ADS','8017851692',
            'gads-8017851692-901','2026-08-15','2026-08-22', now(),
            'trafego_campanha_espelho', 120, 45000000,'BRL','suficiente', now());
  INSERT INTO trafego_diagnostico (diagnostico_id, evidencia_id, regra_id,
      detectado_em, produtor, sintoma, explicacao)
    VALUES ('c2222222-2222-2222-2222-222222222222',
            'b2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111', now(),'motor','cpa alto','x');"

# ── 8. limites da regra ────────────────────────────────────────────────────
recusa "⚠️ proposta com alteração de 80% contra limite de 20%" \
  "INSERT INTO trafego_proposta (diagnostico_id, regra_id, volc_campaign_id, alvo_nivel, alvo_chave,
      operacao, valor_atual, valor_atual_lido_em, valor_proposto, delta_pct, moeda,
      idempotency_key, criada_por, expira_em)
    VALUES ('c2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','gads-8017851692-901','campanha','campanha:gads-8017851692-901',
            'ajustar_orcamento','{\"verba_diaria_micros\": 50000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 90000000}'::jsonb, 80,'BRL',
            'volc-prop-0001-eeeeeeeeeeeeeeee',
            'motor', now() + interval '1 day');"

recusa "⚠️ proposta que estoura o TETO de orçamento da regra" \
  "INSERT INTO trafego_proposta (diagnostico_id, regra_id, volc_campaign_id, alvo_nivel, alvo_chave,
      operacao, valor_atual, valor_atual_lido_em, valor_proposto, delta_pct, moeda,
      idempotency_key, criada_por, expira_em)
    VALUES ('c2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','gads-8017851692-901','campanha','campanha:gads-8017851692-901',
            'ajustar_orcamento','{\"verba_diaria_micros\": 99000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 108000000}'::jsonb, 9,'BRL',
            'volc-prop-0002-ffffffffffffffff',
            'motor', now() + interval '1 day');"

recusa "⚠️ proposta com 'antes' mais velho que o frescor da regra (24h)" \
  "INSERT INTO trafego_proposta (diagnostico_id, regra_id, volc_campaign_id, alvo_nivel, alvo_chave,
      operacao, valor_atual, valor_atual_lido_em, valor_proposto, delta_pct, moeda,
      idempotency_key, criada_por, expira_em)
    VALUES ('c2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','gads-8017851692-901','campanha','campanha:gads-8017851692-901',
            'ajustar_orcamento','{\"verba_diaria_micros\": 50000000}'::jsonb,
            now() - interval '5 days',
            '{\"verba_diaria_micros\": 55000000}'::jsonb, 10,'BRL',
            'volc-prop-0003-1111111111111111',
            'motor', now() + interval '1 day');"

aceita "proposta dentro de TODOS os limites" \
  "INSERT INTO trafego_proposta (proposta_id, diagnostico_id, regra_id,
      volc_campaign_id, alvo_nivel, alvo_chave, operacao, valor_atual,
      valor_atual_lido_em, valor_proposto, delta_pct, moeda, idempotency_key, criada_por, expira_em)
    VALUES ('d2222222-2222-2222-2222-222222222222',
            'c2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','gads-8017851692-901',
            'campanha','campanha:gads-8017851692-901','ajustar_orcamento',
            '{\"verba_diaria_micros\": 50000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 55000000}'::jsonb, 10,'BRL',
            'volc-prop-0004-2222222222222222',
            'motor', now() + interval '1 day');"

cmp_ "$(P -c "SELECT proximo_passo FROM trafego_proposta_painel WHERE proposta_id='d2222222-2222-2222-2222-222222222222';")" \
     "aguardar_humano" "o painel diz: aguardar humano"

# ── 8b. as guardas de AMARRACAO, achadas pela auditoria adversarial ────────
#
# Sem elas, o diagnostico da campanha A autorizava mudanca na campanha B — e o
# painel mostrava a explicacao de A ao lado do alvo B, que e a forma mais
# convincente de um humano aprovar a coisa errada.

recusa "⚠️ proposta apontando para OUTRA campanha que não a da evidência" \
  "INSERT INTO trafego_proposta (diagnostico_id, regra_id, volc_campaign_id, alvo_nivel,
      alvo_chave, operacao, valor_atual, valor_atual_lido_em, valor_proposto,
      delta_pct, moeda, idempotency_key, criada_por, expira_em)
    VALUES ('c2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','gads-8017851692-902','campanha',
            'campanha:gads-8017851692-902','ajustar_orcamento',
            '{\"verba_diaria_micros\": 50000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 55000000}'::jsonb, 10,'BRL',
            'volc-prop-0006-4444444444444444','motor', now() + interval '1 day');"

recusa "⚠️ alvo_nivel = campanha SEM volc_campaign_id (alvo só na string)" \
  "INSERT INTO trafego_proposta (diagnostico_id, regra_id, alvo_nivel,
      alvo_chave, operacao, valor_atual, valor_atual_lido_em, valor_proposto,
      delta_pct, moeda, idempotency_key, criada_por, expira_em)
    VALUES ('c2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','campanha',
            'campanha:so-na-string','ajustar_orcamento',
            '{\"verba_diaria_micros\": 50000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 55000000}'::jsonb, 10,'BRL',
            'volc-prop-0007-5555555555555555','motor', now() + interval '1 day');"

recusa "⚠️ proposta citando regra DIFERENTE da regra do diagnóstico" \
  "INSERT INTO trafego_regra_otimizacao (regra_id, chave, versao, titulo, objetivo,
      plataformas, canais, janela_minima_dias, atraso_conversao_dias,
      frescor_maximo_horas, amostra_minima_cliques, dados_obrigatorios,
      limite_alteracao_pct, cooldown_horas, confianca_minima, condicao_rollback,
      rollback_janela_horas, responsavel, deteccao, acao, declarada_por, fonte,
      vigente_desde)
    VALUES ('a9999999-9999-9999-9999-999999999999','regra_permissiva',1,
            'Permissiva','eficiencia', ARRAY['GOOGLE_ADS'], ARRAY['SEARCH'],
            7, 3, 24, 30, ARRAY['cliques'], 90, 24, 0.8, 'x', 72,
            'tarcisio','{}'::jsonb,'{}'::jsonb,'tarcisio','humano', now());
   INSERT INTO trafego_proposta (diagnostico_id, regra_id, volc_campaign_id, alvo_nivel,
      alvo_chave, operacao, valor_atual, valor_atual_lido_em, valor_proposto,
      delta_pct, moeda, idempotency_key, criada_por, expira_em)
    VALUES ('c2222222-2222-2222-2222-222222222222',
            'a9999999-9999-9999-9999-999999999999','gads-8017851692-901','campanha',
            'campanha:gads-8017851692-901','ajustar_orcamento',
            '{\"verba_diaria_micros\": 50000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 90000000}'::jsonb, 80,'BRL',
            'volc-prop-0008-6666666666666666','motor', now() + interval '1 day');"

recusa "⚠️ proposta SEM delta, contra regra que declara limite de alteração" \
  "INSERT INTO trafego_proposta (diagnostico_id, regra_id, volc_campaign_id, alvo_nivel,
      alvo_chave, operacao, valor_atual, valor_atual_lido_em, valor_proposto,
      moeda, idempotency_key, criada_por, expira_em)
    VALUES ('c2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','gads-8017851692-901','campanha',
            'campanha:gads-8017851692-901','ajustar_orcamento',
            '{\"verba_diaria_micros\": 50000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 55000000}'::jsonb,'BRL',
            'volc-prop-0009-7777777777777777','motor', now() + interval '1 day');"

# ── 8c. metrica sem a janela que ela mede, e a aplicacao sem resposta ──────

recusa "⚠️ acompanhamento com métrica e SEM a janela que ela mede" \
  "INSERT INTO trafego_acompanhamento (aplicacao_id, momento, observado_em,
      observado_por, cliques, custo_micros, moeda)
    VALUES ('f1111111-1111-1111-1111-111111111111','pos_24h', now(),
            'motor', 1200, 45000000, 'BRL');"

recusa "⚠️ lote declarando conta diferente da conta da intenção" \
  "INSERT INTO trafego_lote (intencao_id, blueprint_id, plataforma, conta_externa, canal)
    VALUES ('11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222','GOOGLE_ADS','9999999999','SEARCH');"

recusa "⚠️ lote declarando canal diferente do canal do blueprint" \
  "INSERT INTO trafego_lote (intencao_id, blueprint_id, plataforma, conta_externa, canal)
    VALUES ('11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222','GOOGLE_ADS','8017851692','DISPLAY');"


# ── 9. T1: aplicação exige aprovação DAQUELA proposta ──────────────────────
semear "
  INSERT INTO trafego_proposta (proposta_id, diagnostico_id, regra_id, volc_campaign_id, alvo_nivel,
      alvo_chave, operacao, valor_atual, valor_atual_lido_em, valor_proposto,
      delta_pct, moeda, idempotency_key, criada_por, expira_em)
    VALUES ('d3333333-3333-3333-3333-333333333333',
            'c2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','gads-8017851692-901','campanha','campanha:gads-8017851692-901',
            'ajustar_orcamento','{\"verba_diaria_micros\": 10000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 11000000}'::jsonb, 10,'BRL',
            'volc-prop-0005-3333333333333333',
            'motor', now() + interval '1 day');
  INSERT INTO trafego_aprovacao (aprovacao_id, proposta_id, decisao, decidida_por, diff_apresentado)
    VALUES ('e3333333-3333-3333-3333-333333333333',
            'd3333333-3333-3333-3333-333333333333','aprovada','tarcisio','{}'::jsonb);"

recusa "⚠️ aplicação com aprovação de OUTRA proposta" \
  "INSERT INTO trafego_aplicacao (proposta_id, aprovacao_id, idempotency_key,
      tentativa, enviado_em, valor_anterior)
    VALUES ('d2222222-2222-2222-2222-222222222222',
            'e3333333-3333-3333-3333-333333333333',
            'volc-prop-0004-2222222222222222',1, now(),'{}'::jsonb);"

semear "
  INSERT INTO trafego_aprovacao (aprovacao_id, proposta_id, decisao, decidida_por,
      observacao, diff_apresentado)
    VALUES ('e2222222-2222-2222-2222-222222222222',
            'd2222222-2222-2222-2222-222222222222','aprovada','tarcisio',
            'ok','{\"de\":50000000,\"para\":55000000}'::jsonb);"

recusa "segunda decisão humana sobre a mesma proposta" \
  "INSERT INTO trafego_aprovacao (proposta_id, decisao, decidida_por, observacao, diff_apresentado)
    VALUES ('d2222222-2222-2222-2222-222222222222','recusada','outro','nao','{}'::jsonb);"

aceita "aplicação com a aprovação certa" \
  "INSERT INTO trafego_aplicacao (aplicacao_id, proposta_id, aprovacao_id,
      idempotency_key, tentativa, enviado_em, valor_anterior)
    VALUES ('f2222222-2222-2222-2222-222222222222',
            'd2222222-2222-2222-2222-222222222222',
            'e2222222-2222-2222-2222-222222222222',
            'volc-prop-0004-2222222222222222',1, now(),
            '{\"verba_diaria_micros\": 50000000}'::jsonb);"

cmp_ "$(P -c "SELECT proximo_passo FROM trafego_proposta_painel WHERE proposta_id='d2222222-2222-2222-2222-222222222222';")" \
     "verificar" "aplicação em voo: o painel manda VERIFICAR, não reaplicar"

# ── 10. o cooldown nasce sozinho e bloqueia ────────────────────────────────
aceita "aplicação fecha em sucesso" \
  "UPDATE trafego_aplicacao SET desfecho='sucesso', respondido_em=now(), request_id='req-9'
     WHERE aplicacao_id='f2222222-2222-2222-2222-222222222222';"

cmp_ "$(P -c "SELECT count(*)::text FROM trafego_cooldown_ativo WHERE regra_chave='ajustar_verba';")" \
     "1" "⚠️ a carência nasceu por gatilho, sem ninguém lembrar"

semear "
  INSERT INTO trafego_proposta (proposta_id, diagnostico_id, regra_id, volc_campaign_id, alvo_nivel,
      alvo_chave, operacao, valor_atual, valor_atual_lido_em, valor_proposto,
      delta_pct, moeda, idempotency_key, criada_por, expira_em)
    VALUES ('d4444444-4444-4444-4444-444444444444',
            'c2222222-2222-2222-2222-222222222222',
            'a1111111-1111-1111-1111-111111111111','gads-8017851692-901','campanha',
            'campanha:gads-8017851692-901','ajustar_orcamento',
            '{\"verba_diaria_micros\": 55000000}'::jsonb, now(),
            '{\"verba_diaria_micros\": 60000000}'::jsonb, 9,'BRL',
            'volc-prop-0010-4444444444444444',
            'motor', now() + interval '1 day');
  INSERT INTO trafego_aprovacao (aprovacao_id, proposta_id, decisao, decidida_por, diff_apresentado)
    VALUES ('e4444444-4444-4444-4444-444444444444',
            'd4444444-4444-4444-4444-444444444444','aprovada','tarcisio','{}'::jsonb);"

recusa "⚠️ segunda aplicação da MESMA regra sobre o MESMO alvo, em carência" \
  "INSERT INTO trafego_aplicacao (proposta_id, aprovacao_id, idempotency_key,
      tentativa, enviado_em, valor_anterior)
    VALUES ('d4444444-4444-4444-4444-444444444444',
            'e4444444-4444-4444-4444-444444444444',
            'volc-prop-0006-4444444444444444',1, now(),'{}'::jsonb);"

recusa "reescrever o valor_anterior (destruiria o rollback)" \
  "UPDATE trafego_aplicacao SET valor_anterior='{}'::jsonb
     WHERE aplicacao_id='f2222222-2222-2222-2222-222222222222';"

aceita "rollback com o valor anterior guardado no envio" \
  "INSERT INTO trafego_atuacao_reversao (aplicacao_id, motivo, acionado_por, valor_restaurado)
    SELECT aplicacao_id, 'cpa piorou', 'regra:ajustar_verba@1', valor_anterior
      FROM trafego_aplicacao WHERE aplicacao_id='f2222222-2222-2222-2222-222222222222';"

cmp_ "$(P -c "SELECT valor_restaurado->>'verba_diaria_micros' FROM trafego_atuacao_reversao
                WHERE aplicacao_id='f2222222-2222-2222-2222-222222222222';")" \
     "50000000" "o rollback restaura o valor de ANTES, e não um inventado"

recusa "duas reversões para a mesma aplicação" \
  "INSERT INTO trafego_atuacao_reversao (aplicacao_id, motivo, acionado_por, valor_restaurado)
     VALUES ('f2222222-2222-2222-2222-222222222222','outra','humano:x','{}'::jsonb);"

# ═══════════════════════════════════════════════════════════════════════════
echo
echo "════ 4 · reverter a v10_02 (a v10_01 e a v9 continuam de pé) ════"
aplicar "v10_02_rollback"
cmp_ "$(existe trafego_regra_otimizacao)" "false" "v10_02 · sumiu"
cmp_ "$(existe trafego_lote_item)"        "true"  "v10_01 · INTACTA"
cmp_ "$(existe trafego_inventario_campanha)" "true" "v9 · inventário INTACTO"
cmp_ "$(P -c "SELECT count(*)::text FROM trafego_lote_item;")" "3" "v10_01 · os itens continuam lá"
seguranca "pós-rollback v10_02" "$T01" "$V01"

echo
echo "════ 5 · reverter a v10_01 ════"
aplicar "v10_01_rollback"
cmp_ "$(existe trafego_lote_item)" "false" "v10_01 · sumiu"
cmp_ "$(existe trafego_inventario_campanha)" "true" "v9 · inventário INTACTO"
cmp_ "$(P -c "SELECT count(*)::text FROM trafego_campanha;")" "2" "v9 · as campanhas continuam lá"

echo
echo "════ 6 · reaplicar as duas ════"
aplicar "v10_01_intencao_e_lote"
aplicar "v10_02_autogestao"
cmp_ "$(existe trafego_lote_item)" "true" "v10_01 · reaplicada"
cmp_ "$(existe trafego_regra_otimizacao)" "true" "v10_02 · reaplicada"
seguranca "reaplicado v10_01" "$T01" "$V01"
seguranca "reaplicado v10_02" "$T02" "$V02"

# As guardas voltam vivas — e não só as tabelas.
semear "
  INSERT INTO trafego_intencao (intencao_id, plataforma, conta_externa, objetivo,
      rotulo, declarada_por, declarada_com_base_em)
    VALUES ('99999999-9999-9999-9999-999999999999','GOOGLE_ADS','8017851692',
            'leads','pós-reaplicação','tarcisio','prova');"
recusa_em_camadas "pós-reaplicação · a intenção continua imutável" \
  "UPDATE trafego_intencao SET rotulo='outro' WHERE intencao_id='99999999-9999-9999-9999-999999999999';"
recusa "pós-reaplicação · T2 continua fora do vocabulário" \
  "INSERT INTO trafego_regra_otimizacao (chave, versao, titulo, objetivo, plataformas,
      canais, janela_minima_dias, atraso_conversao_dias, frescor_maximo_horas,
      amostra_minima_cliques, dados_obrigatorios, limite_alteracao_pct, cooldown_horas,
      confianca_minima, condicao_rollback, rollback_janela_horas, responsavel,
      nivel_autonomia, deteccao, acao, declarada_por, fonte)
    VALUES ('t2_de_novo',1,'t','o',ARRAY['GOOGLE_ADS'],ARRAY['*'],7,3,24,30,
            ARRAY['cliques'],20,24,0.8,'c',72,'r','T2','{}'::jsonb,'{}'::jsonb,'d','f');"

echo
echo "════════════════════════════════════════════════"
if [ "$FALHAS" = 0 ]; then
    echo "  CICLO COMPLETO VERDE — aplicar, reverter, reaplicar"
    exit 0
else
    echo "  $FALHAS FALHA(S)"
    exit 1
fi
