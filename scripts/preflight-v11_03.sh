#!/usr/bin/env bash
# =============================================================================
# preflight-v11_03.sh — confere as premissas da v11_03 num banco REAL. Não aplica.
# =============================================================================
# Este script é SOMENTE LEITURA. Ele não cria, não altera e não apaga nada: a
# PRIMEIRA coisa que cada sessão executa, já conectada, é
# `set session characteristics as transaction read only`, para que nem um erro de
# digitação consiga escrever; e todas as consultas são de catálogo ou `count(*)`.
#
# ⚠️ ACHADO A3, corrigido. Antes o read-only vinha de `PGOPTIONS`, e a garantia
# NÃO era incondicional: um DSN que carregue o seu próprio `options=` (por
# exemplo `...?options=-c%20statement_timeout%3D1000`) SOBREPÕE o `PGOPTIONS`
# inteiro — medido: `show default_transaction_read_only` volta `off` e um
# `create table` passa. Agora o read-only é aplicado por `SET` na própria sessão,
# DEPOIS de conectar, então nenhum parâmetro do DSN o desfaz. Fronteira real que
# permanece: quem tem privilégio e escreve `set default_transaction_read_only=off`
# de propósito desfaz — isto é uma guarda contra ENGANO, não contra sabotagem.
#
# ## Por que ele existe
# A v11_03 é transacional e tem verificação embutida, então uma aplicação errada
# aborta inteira. O que ela NÃO consegue detectar sozinha é a premissa de fora:
# uma tabela `criativo_render_*` já povoada (que o `create table if not exists`
# adotaria em silêncio, com o schema velho), uma função homônima com OUTRA
# assinatura (que o `create or replace` não substitui — cria uma sobrecarga), ou
# um `service_role` sem `BYPASSRLS` (que transforma RLS forçada + zero policies
# em "o papel operacional lê zero linhas").
#
# ## FAIL-CLOSED
# Toda conferência que o script não conseguiu fazer sai como `NAO CONFERIDO`, e
# `NAO CONFERIDO` conta como reprovação. Ausência de erro não é evidência.
#
# ## Uso
#   scripts/preflight-v11_03.sh "postgresql://USUARIO@HOST:5432/postgres"
#   V11_03_DSN="postgresql://..." scripts/preflight-v11_03.sh
#
# ⚠️ NÃO HÁ CREDENCIAL NESTE ARQUIVO, e não deve haver. Passe o DSN por argumento
# ou variável de ambiente, e prefira `~/.pgpass` (chmod 600) para a senha, de
# modo que ela não apareça no histórico do shell nem em `ps`.
#
# ## Saída
#   0  → todas as conferências APTO
#   1  → pelo menos um BLOQUEIO
#   2  → uso incorreto, ou pelo menos um NAO CONFERIDO
# =============================================================================
set -uo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
MIGRATION="$RAIZ/supabase/migrations/v11_03_execucao_criativa.sql"
ROLLBACK="$RAIZ/supabase/migrations/v11_03_rollback.sql"

DSN="${1:-${V11_03_DSN:-}}"
if [ -z "$DSN" ]; then
    cat >&2 <<'USO'
preflight-v11_03.sh: falta o DSN do banco a conferir.

  uso:  scripts/preflight-v11_03.sh "postgresql://USUARIO@HOST:5432/postgres"
        V11_03_DSN="postgresql://USUARIO@HOST:5432/postgres" scripts/preflight-v11_03.sh

O que falta, exatamente:
  - o endereço do banco (host, porta, nome do banco);
  - o usuário, que precisa ser `postgres` ou `supabase_admin` — é a guarda que a
    própria v11_03 aplica no primeiro bloco;
  - a senha, de preferência por ~/.pgpass (chmod 600) e não dentro do DSN.

Este script não descobre banco sozinho e não tem padrão embutido: um preflight
que adivinha o alvo é um preflight que confere o banco errado.
USO
    exit 2
fi

command -v psql >/dev/null || { echo "preflight: falta psql no PATH" >&2; exit 2; }

# Somente leitura, e sem ficar pendurado num banco ocupado.
#
# ⚠️ `PGOPTIONS` continua aqui como primeira camada (vale para o caso comum, em
# que o DSN não traz `options=`), mas ele NÃO é a garantia: um `options=` no DSN
# o substitui por inteiro. A garantia é o PRELUDIO abaixo, que roda como primeiro
# comando de cada sessão — depois da conexão, portanto fora do alcance do DSN.
export PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000"
PRELUDIO="set session characteristics as transaction read only;
          set statement_timeout = '15s';
          set lock_timeout = '3s';"

n_apto=0; n_bloq=0; n_nc=0
ERR="$(mktemp "${TMPDIR:-/tmp}/preflight1103.XXXXXX")"
trap 'rm -f "$ERR"' EXIT

apto()  { printf '  APTO          %s\n' "$1"; n_apto=$((n_apto+1)); }
bloq()  { printf '  BLOQUEIO      %s\n' "$1"; n_bloq=$((n_bloq+1)); }
nc()    { printf '  NAO CONFERIDO %s\n' "$1"; n_nc=$((n_nc+1)); }
info()  { printf '  info          %s\n' "$1"; }

# Executa SQL de leitura. Ecoa o resultado; devolve != 0 se a consulta não pôde
# ser feita — e nesse caso quem chama é OBRIGADO a reportar NAO CONFERIDO.
# O PRELUDIO vai num `-c` próprio, ANTES da consulta: `psql` roda os vários `-c`
# na MESMA sessão e na ordem dada, e `set session characteristics` vale para a
# sessão toda. Com `ON_ERROR_STOP=1`, se o próprio PRELUDIO falhar a consulta nem
# chega a ser enviada e quem chama reporta NAO CONFERIDO — fail-closed.
ler() { psql "$DSN" -X -q -At -v ON_ERROR_STOP=1 -c "$PRELUDIO" -c "$1" 2>"$ERR"; }

echo "════════════════════════════════════════════════════════"
echo "  PREFLIGHT v11_03 — leitura apenas, nada é aplicado"
echo "════════════════════════════════════════════════════════"

# ── 0. o arquivo que seria aplicado ─────────────────────────────────────────
soma() {
    if command -v shasum >/dev/null; then shasum -a 256 "$1" | awk '{print $1}'
    elif command -v sha256sum >/dev/null; then sha256sum "$1" | awk '{print $1}'
    else echo ""; fi
}
echo; echo "0. o arquivo que seria aplicado"
for arq in "$MIGRATION" "$ROLLBACK"; do
    if [ ! -f "$arq" ]; then
        nc "arquivo ausente: $arq"
    else
        h="$(soma "$arq")"
        if [ -z "$h" ]; then
            nc "sha256 de $(basename "$arq") — falta shasum/sha256sum no PATH"
        else
            info "$(basename "$arq")  sha256=$h  ($(wc -l < "$arq" | tr -d ' ') linhas)"
        fi
    fi
done

# ── 1. conexão e identidade ─────────────────────────────────────────────────
echo; echo "1. conexão, versão e quem sou eu"
if quem="$(ler "select current_user || '|' || current_database() || '|' || version()")"; then
    usuario="${quem%%|*}"; resto="${quem#*|}"; banco="${resto%%|*}"; versao="${resto#*|}"
    info "servidor: $versao"
    info "banco: $banco"
    if [ "$usuario" = "postgres" ] || [ "$usuario" = "supabase_admin" ]; then
        apto "conectado como '$usuario' — a guarda da v11_03 aceita"
    else
        bloq "conectado como '$usuario'; a v11_03 aborta fora de postgres/supabase_admin"
    fi
else
    nc "conexão: $(tr '\n' ' ' < "$ERR")"
    nc "versão do servidor Postgres"
    nc "usuário de aplicação"
    echo; echo "  Sem conexão não há preflight. Nada abaixo foi conferido."
    echo "  apto=$n_apto bloqueio=$n_bloq nao_conferido=$n_nc"
    exit 2
fi

# ── 1b. a sessão é mesmo somente-leitura? ───────────────────────────────────
# ⚠️ ACHADO A3. Afirmar "abro em read-only" no cabeçalho não é o mesmo que estar
# em read-only. Aqui a afirmação vira medida: a própria sessão é perguntada, e
# uma resposta diferente de `on` é BLOQUEIO — não seguimos lendo um banco em que
# a guarda contra engano não está de pé.
if ro="$(ler "show default_transaction_read_only")"; then
    if [ "$ro" = "on" ]; then
        apto "sessão em default_transaction_read_only=on (aplicado por SET, imune a 'options=' no DSN)"
    else
        bloq "sessão com default_transaction_read_only='$ro' — a guarda contra escrita acidental NÃO está de pé"
    fi
else
    nc "default_transaction_read_only: $(tr '\n' ' ' < "$ERR")"
fi

# ── 2. as 5 tabelas da v11_03: nada a perder ────────────────────────────────
echo; echo "2. os 5 nomes criativo_render_* — o nome tem de estar LIVRE"
# ⚠️ Existir já é sinal. `create table if not exists` ADOTA uma tabela homônima
# de schema diferente sem dizer nada, e a verificação embutida conta 5 tabelas e
# sai verde. Tabela vazia e preexistente é aviso; tabela com linha é bloqueio.
#
# ⚠️ ACHADO A1, corrigido. Esta conferência era feita em `pg_tables`, que só
# enxerga relkind 'r' e 'p'. Uma VIEW, MATERIALIZED VIEW, FOREIGN TABLE ou
# SEQUENCE ocupando o mesmo nome é INVISÍVEL para `pg_tables` — e o preflight,
# cujo único trabalho é impedir uma aplicação que vai falhar, declarava
# "criativo_render_job não existe / APTO / exit 0". Aplicar em seguida quebra em
# `ERROR: cannot create index on relation "criativo_render_job"`, porque o
# `create table if not exists` vê o nome ocupado, pula em silêncio, e o
# `create index` seguinte encontra uma view.
#
# Agora a pergunta é a do Postgres, não a do `pg_tables`: o NOME está livre no
# schema `public`? Isso se lê em `pg_class`/`pg_namespace`, que enxerga TODA
# relação. Nome ocupado por qualquer relkind é BLOQUEIO, e a mensagem diz por
# qual tipo de objeto ele está ocupado.
nome_relkind() {
    case "$1" in
        r) echo "TABELA" ;;
        p) echo "TABELA PARTICIONADA" ;;
        v) echo "VIEW" ;;
        m) echo "MATERIALIZED VIEW" ;;
        f) echo "FOREIGN TABLE" ;;
        S) echo "SEQUENCE" ;;
        i) echo "ÍNDICE" ;;
        I) echo "ÍNDICE PARTICIONADO" ;;
        c) echo "TIPO COMPOSTO" ;;
        t) echo "TABELA TOAST" ;;
        *) echo "RELKIND DESCONHECIDO '$1'" ;;
    esac
}
ALVOS="criativo_render_job criativo_render_transicao criativo_render_recibo criativo_render_artefato criativo_render_validacao"
for t in $ALVOS; do
    if rk="$(ler "select coalesce((select c.relkind::text from pg_class c
                                    join pg_namespace n on n.oid = c.relnamespace
                                   where n.nspname='public' and c.relname='$t'), '-')")"; then
        case "$rk" in
            -)
                apto "$t não existe (nenhuma relação com esse nome) — a v11_03 vai criá-la do zero" ;;
            r|p)
                if linhas="$(ler "select count(*) from public.$t")"; then
                    if [ "$linhas" = "0" ]; then
                        bloq "$t JÁ EXISTE como $(nome_relkind "$rk") (0 linhas) — 'if not exists' adotaria o schema atual sem avisar; confira coluna a coluna antes"
                    else
                        bloq "$t JÁ EXISTE como $(nome_relkind "$rk") com $linhas linha(s) — há o que perder; NÃO aplique"
                    fi
                else
                    nc "$t existe como $(nome_relkind "$rk") mas não pôde ser contada: $(tr '\n' ' ' < "$ERR")"
                fi ;;
            *)
                bloq "$t: o NOME está ocupado por uma $(nome_relkind "$rk") (relkind='$rk') — 'create table if not exists' pula em silêncio e o 'create index' seguinte falha com 'cannot create index on relation'" ;;
        esac
    else
        nc "$t — não deu para consultar o catálogo: $(tr '\n' ' ' < "$ERR")"
    fi
done

# ── 3. as 21 tabelas da v11_01/v11_02 ───────────────────────────────────────
echo; echo "3. as 21 tabelas da v11_01/v11_02 — a base de que a v11_03 depende"
ESPERADAS="criativo_motor criativo_modo_de_producao criativo_formato criativo_finalidade
criativo_exigencia_de_canal criativo_teto_combinado criativo_skin criativo_voz criativo_gate
criativo_master_gate criativo_master_direito criativo_brand_pack criativo_projeto
criativo_briefing criativo_job criativo_job_evento criativo_master criativo_rendition
criativo_aprovacao criativo_pacote criativo_entrega"
# ⚠️ ACHADO A1, corrigido também aqui: `pg_tables` daria "presente" a uma tabela
# e "ausente" a um nome ocupado por VIEW — mas daria a MESMA resposta ("ausente")
# aos dois casos, que exigem conserto diferente. Lendo `pg_class` dá para separar
# "não existe" de "existe, mas não é tabela".
faltando=""
nao_tabela=""
falhou_catalogo=0
for t in $ESPERADAS; do
    if rk="$(ler "select coalesce((select c.relkind::text from pg_class c
                                    join pg_namespace n on n.oid = c.relnamespace
                                   where n.nspname='public' and c.relname='$t'), '-')")"; then
        case "$rk" in
            r|p) : ;;
            -)   faltando="$faltando $t" ;;
            *)   nao_tabela="$nao_tabela $t($(nome_relkind "$rk"))" ;;
        esac
    else
        falhou_catalogo=1
    fi
done
if [ "$falhou_catalogo" = "1" ]; then
    nc "as 21 tabelas da v11_01/02 — consulta de catálogo falhou: $(tr '\n' ' ' < "$ERR")"
elif [ -z "$faltando" ] && [ -z "$nao_tabela" ]; then
    apto "as 21 tabelas da v11_01/02 estão presentes (conferidas por nome, e são tabelas)"
else
    [ -z "$faltando" ]   || bloq "faltam tabelas da v11_01/02:$faltando — aplique v11_01/v11_02 antes"
    [ -z "$nao_tabela" ] || bloq "nome da v11_01/02 ocupado por relação que NÃO é tabela:$nao_tabela — a base não é a que se supõe"
fi

# ── 4. o papel operacional ──────────────────────────────────────────────────
echo; echo "4. service_role — a premissa do modelo de acesso"
# ⚠️ A v11_03 deixa RLS habilitada E forçada, com ZERO policies. Nesse desenho o
# único jeito de o papel operacional ler e escrever é `BYPASSRLS`. Sem ele a
# migration aplica limpa e o produto para: todo SELECT devolve zero linhas e todo
# INSERT é recusado, silenciosamente, como se não houvesse dado.
if papel="$(ler "select coalesce((select case when rolbypassrls then 't' else 'f' end from pg_roles where rolname='service_role'), 'AUSENTE')")"; then
    case "$papel" in
        t)       apto "service_role existe e tem BYPASSRLS" ;;
        f)       bloq "service_role existe SEM BYPASSRLS — com RLS forçada e 0 policies ele lerá zero linhas" ;;
        AUSENTE) bloq "o papel service_role NÃO EXISTE — os GRANTs da v11_03 falham" ;;
        *)       nc "service_role: resposta inesperada '$papel'" ;;
    esac
else
    nc "service_role: $(tr '\n' ' ' < "$ERR")"
fi
# anon/authenticated não precisam existir, mas se existirem com BYPASSRLS a
# migration aplica e a tabela fica legível por quem não deveria.
if outros="$(ler "select coalesce(string_agg(rolname, ', ' order by rolname), '') from pg_roles where rolname in ('anon','authenticated') and rolbypassrls")"; then
    if [ -z "$outros" ]; then
        apto "anon/authenticated sem BYPASSRLS (ou inexistentes)"
    else
        bloq "papel público com BYPASSRLS: $outros — a RLS forçada da v11_03 não os deteria"
    fi
else
    nc "anon/authenticated: $(tr '\n' ' ' < "$ERR")"
fi

# ── 5. as 9 funções, por ASSINATURA ─────────────────────────────────────────
echo; echo "5. as 9 funções da v11_03 — nenhuma pode preexistir com outra assinatura"
# ⚠️ `create or replace function` só substitui quando NOME E ARGUMENTOS batem.
# Com argumentos diferentes ele CRIA UMA SOBRECARGA, as duas passam a existir, e
# quem chama sem qualificar tipo pode cair na antiga. O rollback também erra o
# alvo: ele dropa por assinatura. Por isso a conferência aqui é por assinatura, e
# não por nome.
# ⚠️ `pg_get_function_identity_arguments` traz os NOMES dos parâmetros junto
# ('p_tenant text, p_job uuid, ...'), e comparar isso com uma lista de TIPOS faz
# toda função legítima ser rotulada "outra assinatura". `oidvectortypes` devolve
# só os tipos — que é o que decide se `create or replace` substitui ou sobrecarrega.
ASSINATURAS='criativo_render_artefato_imutavel()
criativo_render_recibo_coerente()
criativo_render_retomada_legitima()
criativo_render_storage_do_dono()
criativo_render_transicao_append_only()
criativo_render_transicao_valida()
criativo_render_validacao_imutavel_apos_render()
criativo_storage_chave(text, uuid, text, text)
criativo_storage_chave_valida(text, text, uuid, text)'
if achadas="$(ler "select p.proname || '(' || coalesce(pg_catalog.oidvectortypes(p.proargtypes), '') || ')'
                     from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public'
                      and (p.proname like 'criativo_render_%' or p.proname like 'criativo_storage_chave%')
                    order by p.proname, coalesce(pg_catalog.oidvectortypes(p.proargtypes), '')")"; then
    if [ -z "$achadas" ]; then
        apto "nenhuma das 9 funções preexiste — a v11_03 as cria do zero"
    else
        intrusa=0
        while IFS= read -r linha; do
            [ -n "$linha" ] || continue
            if printf '%s\n' "$ASSINATURAS" | grep -qxF "$linha"; then
                bloq "função já existe com a assinatura ESPERADA: $linha — 'create or replace' a sobrescreve, mas confira que ela é da v11_03 e não de outra migration"
            else
                bloq "função homônima com OUTRA assinatura: $linha — viraria sobrecarga, e o rollback não a alcança"
            fi
            intrusa=$((intrusa+1))
        done <<< "$achadas"
        [ "$intrusa" -gt 0 ] || nc "as 9 funções — leitura vazia inesperada"
    fi
else
    nc "as 9 funções: $(tr '\n' ' ' < "$ERR")"
fi

# ── 6. gatilhos e tipos homônimos ───────────────────────────────────────────
echo; echo "6. gatilhos homônimos"
if trg="$(ler "select coalesce(string_agg(t.tgname, ', ' order by t.tgname), '')
                 from pg_trigger t join pg_class c on c.oid = t.tgrelid
                 join pg_namespace n on n.oid = c.relnamespace
                where n.nspname='public' and not t.tgisinternal
                  and t.tgname like 'criativo_render_%'")"; then
    if [ -z "$trg" ]; then
        apto "nenhum gatilho criativo_render_* preexiste"
    else
        bloq "gatilhos criativo_render_* já existem: $trg"
    fi
else
    nc "gatilhos: $(tr '\n' ' ' < "$ERR")"
fi

# ── veredito ────────────────────────────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════"
echo "  apto=$n_apto  bloqueio=$n_bloq  nao_conferido=$n_nc"
if [ "$n_nc" -gt 0 ]; then
    echo "  VEREDITO: NÃO APLICAR. Há conferência que não foi feita, e"
    echo "  'não deu erro' não é evidência de que está tudo bem."
    exit 2
fi
if [ "$n_bloq" -gt 0 ]; then
    echo "  VEREDITO: NÃO APLICAR. Resolva os BLOQUEIOs acima e rode de novo."
    exit 1
fi
echo "  VEREDITO: premissas conferidas. A aplicação continua sendo um gesto"
echo "  humano — este script não aplica nada."
