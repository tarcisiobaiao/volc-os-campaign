#!/usr/bin/env bash
# =============================================================================
# testar_migration_descartavel.sh — prova a migration num Postgres que nasce e
# morre dentro deste script. NUNCA toca em producao.
# =============================================================================
#
# POR QUE UM CLUSTER DESCARTAVEL, E NAO UM BANCO DE TESTE
#
# Um banco de teste que sobrevive entre execucoes acumula estado, e o estado
# acumulado e o que faz uma migration "passar" numa maquina e falhar em
# producao. Aqui o cluster e criado do zero, recebe a migration inteira, e e
# destruido no fim — inclusive se o script falhar no meio (trap EXIT).
#
# O cluster tambem REPRODUZ DE PROPOSITO o defeito de plataforma medido em
# 24/08/2026: `pg_default_acl` de `public` concedendo `arwdDxt` a anon e
# authenticated em toda tabela nova. Sem isso, o teste de acesso negativo
# passaria por acidente — a tabela estaria fechada porque nada a abriu, e nao
# porque a migration a fechou. Testar contra um ambiente mais seguro que o real
# e a forma mais comum de um gate de seguranca mentir.
#
# COMO RODAR
#   ./scripts/testar_migration_descartavel.sh
#   ./scripts/testar_migration_descartavel.sh --manter   # nao destroi (debug)
#
# ⚠️ initdb roda com LC_ALL=C LANG=C. Sem isso, nesta maquina, o postmaster
#    aborta com "o processo servidor tornou-se multithread" ao carregar o
#    locale do sistema.
# =============================================================================
set -euo pipefail

# ⚠️ NAO E SO O initdb. Medido nesta maquina: com o locale do sistema, o
# postmaster ABORTA no startup com "postmaster became multithreaded during
# startup" — o carregamento do locale do macOS cria uma thread antes do fork.
# LC_ALL/LANG precisam valer para initdb, para pg_ctl E para o psql, entao o
# lugar certo e o processo inteiro. Efeito colateral util: as mensagens do
# servidor saem em ingles, e os greps abaixo param de depender do idioma.
export LC_ALL=C LANG=C

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATION="${RAIZ}/supabase/migrations/v9_01_trafego_inventario.sql"
ROLLBACK="${RAIZ}/supabase/migrations/v9_99_trafego_inventario_rollback.sql"

MANTER=0
[[ "${1:-}" == "--manter" ]] && MANTER=1

for binario in initdb pg_ctl psql; do
  command -v "$binario" >/dev/null 2>&1 || {
    echo "ERRO: '$binario' nao esta no PATH. Instale o PostgreSQL (brew install postgresql@16)." >&2
    exit 1
  }
done
[[ -f "$MIGRATION" ]] || { echo "ERRO: migration nao encontrada: $MIGRATION" >&2; exit 1; }
[[ -f "$ROLLBACK"  ]] || { echo "ERRO: rollback nao encontrado: $ROLLBACK"  >&2; exit 1; }

BASE="$(mktemp -d "${TMPDIR:-/tmp}/volc-pg-descartavel.XXXXXX")"
PGDATA="${BASE}/dados"
SOCK="${BASE}/sock"
LOG="${BASE}/postgres.log"
SAIDA="${BASE}/provas.out"
mkdir -p "$SOCK"

limpar() {
  local codigo=$?
  if [[ -d "$PGDATA" ]]; then
    pg_ctl -D "$PGDATA" -m immediate stop >/dev/null 2>&1 || true
  fi
  if [[ $MANTER -eq 1 ]]; then
    echo "→ cluster preservado em ${BASE} (--manter)"
  else
    rm -rf "$BASE"
  fi
  exit $codigo
}
trap limpar EXIT

echo "▶ cluster descartavel em ${BASE}"
initdb -D "$PGDATA" -U postgres --encoding=UTF8 \
  --locale=C >/dev/null

# Sem TCP: so socket unix dentro do diretorio temporario. Evita colisao de porta
# e torna impossivel, por construcao, que este cluster seja confundido com
# outro — inclusive por um script que tenha um host errado no ambiente.
pg_ctl -D "$PGDATA" -l "$LOG" -o "-k ${SOCK} -h ''" -w start >/dev/null

executar() { psql -X -q -h "$SOCK" -U postgres -d postgres -v ON_ERROR_STOP=1 "$@"; }

# ---------------------------------------------------------------------------
# 1. Reproduzir o Supabase — inclusive o que ele tem de errado
# ---------------------------------------------------------------------------
echo "▶ semeando papeis do Supabase e o default ACL QUEBRADO de public"
executar <<'SQL' >/dev/null
CREATE ROLE anon           NOLOGIN NOINHERIT;
CREATE ROLE authenticated  NOLOGIN NOINHERIT;
-- service_role tem BYPASSRLS no Supabase real. Reproduzir isso e o que impede
-- este teste de concluir que RLS protege o backend — ela nao protege.
CREATE ROLE service_role   NOLOGIN NOINHERIT BYPASSRLS;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

-- O defeito de plataforma, medido em 24/08/2026 (achado H da v8_07).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO anon, authenticated, service_role;
SQL

# Prova de que o defeito foi mesmo reproduzido: uma tabela qualquer criada agora
# tem de nascer aberta a anon. Se esta prova falhar, todas as outras de
# seguranca perdem o valor, porque estariam medindo um ambiente mais seguro que
# o real.
executar <<'SQL' >/dev/null
CREATE TABLE public._sonda_do_default_acl (id int);
DO $$
BEGIN
  IF NOT has_table_privilege('anon', 'public._sonda_do_default_acl', 'INSERT') THEN
    RAISE EXCEPTION
      'o cluster de teste NAO reproduziu o default ACL aberto; as provas de seguranca seriam falso-positivo';
  END IF;
END $$;
DROP TABLE public._sonda_do_default_acl;
SQL
echo "  ✓ default ACL aberto reproduzido (tabela nova nasce escrivel por anon)"

# ---------------------------------------------------------------------------
# 2. O preflight do README tem de RODAR — e concordar com o terreno
# ---------------------------------------------------------------------------
# Um preflight que o dono cola no banco antes de autorizar precisa ser SQL que
# executa, nao SQL que parece executar. Ele vive em markdown, longe do
# compilador de qualquer coisa, e envelhece em silencio a cada coluna renomeada.
# Aqui ele e extraido do README e rodado de verdade.
echo "▶ rodando o preflight do README"
executar -c "CREATE TABLE public.campaigns (id int, customer_id text);
             INSERT INTO public.campaigns VALUES (1,''),(2,''),(3,''),(4,'');" >/dev/null

python3 - "$RAIZ" "${BASE}/preflight.sql" <<'EXTRAI'
import sys
raiz, destino = sys.argv[1], sys.argv[2]
md = open(f"{raiz}/supabase/migrations/README.md", encoding="utf-8").read()
marca = md.index("PREFLIGHT v9_01")
bloco = md[md.rindex("```sql", 0, marca) + 6 : md.index("```", marca)]
open(destino, "w", encoding="utf-8").write(bloco)
EXTRAI

# Cada linha do preflight declara o valor esperado e se a divergencia ABORTA.
# O gate aqui usa a propria tabela do README, entao os dois nunca discordam.
DIVERGENTES=$(psql -X -tA -F'|' -h "$SOCK" -U postgres -d postgres \
  -v ON_ERROR_STOP=1 -f "${BASE}/preflight.sql" \
  | awk -F'|' '$4 == "ABORTA" && $2 != $3 { print "    " $1 ": <" $2 "> != <" $3 ">" }')
if [[ -n "$DIVERGENTES" ]]; then
  echo "  ✗ o preflight reprovaria a aplicacao num terreno limpo:" >&2
  echo "$DIVERGENTES" >&2
  exit 1
fi
echo "  ✓ preflight executa e aprova o terreno limpo"

# ---------------------------------------------------------------------------
# 3. Aplicar a migration do zero
# ---------------------------------------------------------------------------
echo "▶ aplicando ${MIGRATION##*/}"
executar -f "$MIGRATION" >/dev/null
echo "  ✓ aplicada"

# ---------------------------------------------------------------------------
# 4. As provas
# ---------------------------------------------------------------------------
echo "▶ rodando as provas"
cat > "${BASE}/provas.sql" <<'PROVAS'
\set ON_ERROR_STOP on

-- Ajudantes. Existem so no cluster descartavel; nao ha equivalente em producao.
-- ⚠️ ESTA FUNCAO JA ACEITOU QUALQUER ERRO, E ISSO NAO ERA PROVA NENHUMA.
--
-- A versao anterior capturava `WHEN others` e declarava "PROVA ok" para
-- QUALQUER excecao. Um erro de digitacao no proprio teste — coluna que nao
-- existe, tabela errada, virgula a mais — contava como prova de que o banco
-- recusa o que tem de recusar. A suite ficava verde medindo a si mesma.
--
-- Agora o motivo e OBRIGATORIO, em dois niveis:
--
--   sqlstate_esperado  o codigo, sempre conferido. `23514` e CHECK, `23505` e
--                      unique, `23503` e FK, `23001` e o `restrict_violation`
--                      que os gatilhos deste schema levantam. Um erro de
--                      digitacao vira `42703`/`42P01` e NAO casa com nenhum.
--   alvo_esperado      QUEM recusou. Quando a excecao carrega
--                      `CONSTRAINT_NAME`, ele tem de bater exatamente; quando
--                      nao carrega (gatilho com RAISE), o texto precisa citar
--                      o alvo. Sem isso, uma CHECK vizinha disparando por
--                      acidente passaria por prova da CHECK certa.
CREATE FUNCTION _prova_recusa(rotulo text, comando text,
                              sqlstate_esperado text, alvo_esperado text)
RETURNS void
LANGUAGE plpgsql AS $$
DECLARE estado text; nome_constraint text; erro text;
BEGIN
  BEGIN
    EXECUTE comando;
  EXCEPTION WHEN others THEN
    GET STACKED DIAGNOSTICS
      estado          = RETURNED_SQLSTATE,
      nome_constraint = CONSTRAINT_NAME,
      erro            = MESSAGE_TEXT;
    erro := replace(coalesce(erro, ''), E'\n', ' ');

    IF estado IS DISTINCT FROM sqlstate_esperado THEN
      RAISE EXCEPTION
        'PROVA FALHOU: % | recusado pelo motivo ERRADO: SQLSTATE % (esperado %) | %',
        rotulo, estado, sqlstate_esperado, left(erro, 120);
    END IF;

    IF coalesce(nome_constraint, '') <> '' THEN
      IF nome_constraint <> alvo_esperado THEN
        RAISE EXCEPTION
          'PROVA FALHOU: % | violou a constraint % — esperava %',
          rotulo, nome_constraint, alvo_esperado;
      END IF;
    ELSIF position(alvo_esperado IN erro) = 0 THEN
      RAISE EXCEPTION
        'PROVA FALHOU: % | a recusa nao cita % | %',
        rotulo, alvo_esperado, left(erro, 120);
    END IF;

    RAISE NOTICE 'PROVA ok: % | % %', rotulo, estado,
      coalesce(nullif(nome_constraint, ''), '~ ' || alvo_esperado);
    RETURN;
  END;
  RAISE EXCEPTION 'PROVA FALHOU: % | o banco ACEITOU o que deveria recusar', rotulo;
END $$;

CREATE FUNCTION _prova_aceita(rotulo text, comando text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE comando;
  RAISE NOTICE 'PROVA ok: %', rotulo;
EXCEPTION WHEN others THEN
  RAISE EXCEPTION 'PROVA FALHOU: % | o banco RECUSOU o que deveria aceitar: %',
    rotulo, replace(SQLERRM, E'\n', ' ');
END $$;

CREATE FUNCTION _prova_igual(rotulo text, consulta text, esperado text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE obtido text;
BEGIN
  EXECUTE consulta INTO obtido;
  IF obtido IS DISTINCT FROM esperado THEN
    RAISE EXCEPTION 'PROVA FALHOU: % | esperado <%>, obtido <%>',
      rotulo, esperado, coalesce(obtido, 'NULL');
  END IF;
  RAISE NOTICE 'PROVA ok: % | %', rotulo, esperado;
END $$;

-- Acesso NEGATIVO de verdade: troca de papel e tenta. Inspecionar catalogo
-- provaria que o GRANT nao esta la; so SET ROLE prova que a operacao falha.
-- Aqui o motivo ja era especifico: `WHEN insufficient_privilege` (42501) e a
-- unica clausula capturada, entao um erro de sintaxe no comando NAO e
-- silenciado — ele sobe e derruba a prova, que e o comportamento certo.
CREATE FUNCTION _prova_recusa_como(rotulo text, papel text, comando text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE recusou boolean := false; erro text;
BEGIN
  BEGIN
    EXECUTE format('SET LOCAL ROLE %I', papel);
    EXECUTE comando;
  EXCEPTION WHEN insufficient_privilege THEN
    recusou := true; erro := replace(SQLERRM, E'\n', ' ');
  END;
  EXECUTE 'RESET ROLE';
  IF NOT recusou THEN
    RAISE EXCEPTION 'PROVA FALHOU: % | % executou: %', rotulo, papel, comando;
  END IF;
  RAISE NOTICE 'PROVA ok: % [%] | %', rotulo, papel, left(erro, 110);
END $$;

CREATE FUNCTION _prova_aceita_como(rotulo text, papel text, comando text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE erro text; falhou boolean := false;
BEGIN
  BEGIN
    EXECUTE format('SET LOCAL ROLE %I', papel);
    EXECUTE comando;
  EXCEPTION WHEN others THEN
    falhou := true; erro := replace(SQLERRM, E'\n', ' ');
  END;
  EXECUTE 'RESET ROLE';
  IF falhou THEN
    RAISE EXCEPTION 'PROVA FALHOU: % | % foi recusado: %', rotulo, papel, erro;
  END IF;
  RAISE NOTICE 'PROVA ok: % [%]', rotulo, papel;
END $$;


-- ===========================================================================
-- BLOCO 1 — customer_id vazio e RECUSADO (o defeito medido em E-02 / E-10)
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_recusa(
    'customer_id = string vazia',
    -- ⚠️ `volc_campaign_id` viaja em TODA insercao a partir daqui. A coluna e
    -- text e NAO tem DEFAULT: identidade e derivada pelo dominio, nunca
    -- sorteada pelo banco. Sem ela, estas provas passariam por violacao de
    -- NOT NULL (23502) em vez da CHECK que elas dizem provar — que e
    -- exatamente o tipo de prova acidental que esta rodada veio fechar.
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
       VALUES ('gads-x-1', '', '24155134757', 'prova')$q$,
    '23514', 'trafego_campanha_customer_id_valido');

  PERFORM _prova_recusa(
    'customer_id so com espacos',
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
       VALUES ('gads-x-2', '   ', '24155134757', 'prova')$q$,
    '23514', 'trafego_campanha_customer_id_valido');

  PERFORM _prova_recusa(
    'customer_id com hifens (mesma conta, forma que nao casa em JOIN)',
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
       VALUES ('gads-x-3', '801-785-1692', '24155134757', 'prova')$q$,
    '23514', 'trafego_campanha_customer_id_valido');

  PERFORM _prova_recusa(
    'campaign_id vazio',
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
       VALUES ('gads-x-4', '8017851692', '', 'prova')$q$,
    '23514', 'trafego_campanha_campaign_id_valido');

  -- Ausencia CONHECIDA e NULL, e ela precisa passar: sao as linhas historicas
  -- que nascem `legado_nao_reconciliado` (ADR-13).
  PERFORM _prova_aceita(
    'customer_id NULL aceito (ausencia conhecida, nao vazio)',
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
       VALUES ('00000000-0000-0000-0000-0000000000fe', NULL, '901', 'prova-legado')$q$);
END $bloco$;


-- ===========================================================================
-- BLOCO 2 — identidade unica e IMUTAVEL
-- ===========================================================================
INSERT INTO public.trafego_campanha
  (volc_campaign_id, customer_id, campaign_id, criada_por)
VALUES
  ('00000000-0000-0000-0000-000000000001', '8017851692', '24155134757', 'prova'),
  ('00000000-0000-0000-0000-000000000002', '8017851692', '24156373085', 'prova');

DO $bloco$
BEGIN
  PERFORM _prova_recusa(
    'identidade externa (customer_id, campaign_id) duplicada',
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
       VALUES ('gads-outra-identidade', '8017851692', '24155134757', 'prova')$q$,
    '23505', 'trafego_campanha_identidade_externa_ux');

  PERFORM _prova_recusa(
    'duas linhas legadas sem conta com o mesmo campaign_id',
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
       VALUES ('legado-901-bis', NULL, '901', 'prova')$q$,
    '23505', 'trafego_campanha_legado_sem_conta_ux');

  PERFORM _prova_recusa(
    'volc_campaign_id imutavel',
    $q$UPDATE public.trafego_campanha
          SET volc_campaign_id = '00000000-0000-0000-0000-0000000000aa'
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '23001', 'volc_campaign_id e imutavel');

  PERFORM _prova_recusa(
    'campaign_id imutavel',
    $q$UPDATE public.trafego_campanha SET campaign_id = '99999'
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '23001', 'campaign_id e imutavel');

  PERFORM _prova_recusa(
    'customer_id conhecido nao vira outro',
    $q$UPDATE public.trafego_campanha SET customer_id = '3849678045'
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '23001', 'customer_id ja conhecido');

  PERFORM _prova_recusa(
    'customer_id conhecido nao volta a NULL',
    $q$UPDATE public.trafego_campanha SET customer_id = NULL
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '23001', 'customer_id ja conhecido');

  PERFORM _prova_recusa(
    'criada_em/criada_por sao registro de origem',
    $q$UPDATE public.trafego_campanha SET criada_por = 'outro'
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '23001', 'registro de origem');

  -- A UNICA transicao permitida: reconciliar uma linha legada.
  PERFORM _prova_aceita(
    'promocao monotonica customer_id NULL -> conhecido (reconciliacao do legado)',
    $q$UPDATE public.trafego_campanha SET customer_id = '5478096539'
        WHERE volc_campaign_id = '00000000-0000-0000-0000-0000000000fe'$q$);
END $bloco$;


-- ===========================================================================
-- BLOCO 3 — linhagem ESTAVEL
-- ===========================================================================
INSERT INTO public.trafego_linhagem (campaign_lineage_id, rotulo, declarada_por)
VALUES ('00000000-0000-0000-0000-00000000c001', 'FGTS Saque-Aniversario', 'operador'),
       ('00000000-0000-0000-0000-00000000c002', 'Maquininha de Cartao',   'operador');

DO $bloco$
BEGIN
  PERFORM _prova_recusa(
    'linhagem com rotulo vazio',
    $q$INSERT INTO public.trafego_linhagem (rotulo, declarada_por) VALUES ('  ', 'x')$q$,
    '23514', 'trafego_linhagem_rotulo_nao_vazio');

  PERFORM _prova_recusa(
    'linhagem sem quem a declarou',
    $q$INSERT INTO public.trafego_linhagem (rotulo, declarada_por) VALUES ('x', '')$q$,
    '23514', 'trafego_linhagem_declarante_nao_vazio');

  PERFORM _prova_aceita(
    'linhagem atribuida a uma campanha (uma vez)',
    $q$UPDATE public.trafego_campanha
          SET campaign_lineage_id = '00000000-0000-0000-0000-00000000c001'
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000002'$q$);

  PERFORM _prova_recusa(
    'linhagem ja atribuida nao vira outra (sinal FORTE da prova de duplicidade)',
    $q$UPDATE public.trafego_campanha
          SET campaign_lineage_id = '00000000-0000-0000-0000-00000000c002'
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000002'$q$,
    '23001', 'campaign_lineage_id ja atribuido');

  PERFORM _prova_recusa(
    'linhagem atribuida nao volta a NULL',
    $q$UPDATE public.trafego_campanha SET campaign_lineage_id = NULL
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000002'$q$,
    '23001', 'campaign_lineage_id ja atribuido');

  PERFORM _prova_recusa(
    'linhagem em uso nao pode ser apagada',
    $q$DELETE FROM public.trafego_linhagem
        WHERE campaign_lineage_id = '00000000-0000-0000-0000-00000000c001'$q$,
    '23503', 'trafego_campanha_campaign_lineage_id_fkey');

  PERFORM _prova_igual(
    'a linhagem da campanha continua a que foi declarada',
    $q$SELECT campaign_lineage_id::text FROM public.trafego_campanha
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000002'$q$,
    '00000000-0000-0000-0000-00000000c001');
END $bloco$;


-- ===========================================================================
-- BLOCO 4 — procedencia declarada NAO e sobrescrita (o conserto de E-08)
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_recusa(
    'procedencia determinada sem quem a declarou',
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por, procedencia)
       VALUES ('gads-8017851692-777', '8017851692', '777', 'prova', 'volc_os')$q$,
    '23514', 'trafego_campanha_procedencia_tem_autor');

  PERFORM _prova_recusa(
    'procedencia fora do vocabulario',
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por, procedencia,
              procedencia_declarada_por, procedencia_declarada_em)
       VALUES ('gads-8017851692-778', '8017851692', '778', 'prova', 'auto', 'x', now())$q$,
    '23514', 'trafego_campanha_procedencia_conhecida');

  PERFORM _prova_aceita(
    'procedencia resolvida de desconhecida para declarada',
    $q$UPDATE public.trafego_campanha
          SET procedencia = 'volc_os',
              procedencia_declarada_por = 'porta-de-criacao',
              procedencia_declarada_em  = now()
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$);

  PERFORM _prova_recusa(
    'procedencia declarada NAO e sobrescrita (era o que o trigger legado fazia)',
    $q$UPDATE public.trafego_campanha SET procedencia = 'descoberta'
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '23001', 'procedencia ja declarada');

  PERFORM _prova_igual(
    'a procedencia declarada sobreviveu',
    $q$SELECT procedencia FROM public.trafego_campanha
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    'volc_os');
END $bloco$;


-- ===========================================================================
-- BLOCO 5 — espelho: vocabulario de canal, zero != NULL, nada sem carimbo
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_recusa(
    'canal PMAX (apelido de tela) recusado — ADR-18',
    $q$INSERT INTO public.trafego_campanha_espelho (volc_campaign_id, lido_em, presenca, canal)
       VALUES ('00000000-0000-0000-0000-000000000001', now(), 'nao_encontrada', 'PMAX')$q$,
    '23514', 'trafego_espelho_canal_canonico');

  PERFORM _prova_recusa(
    'estado de presenca inventado ("sumiu_da_conta")',
    $q$INSERT INTO public.trafego_campanha_espelho (volc_campaign_id, lido_em, presenca)
       VALUES ('00000000-0000-0000-0000-000000000001', now(), 'sumiu_da_conta')$q$,
    '23514', 'trafego_espelho_presenca_conhecida');

  PERFORM _prova_recusa(
    'numero de entrega SEM carimbo de leitura (regra A)',
    $q$INSERT INTO public.trafego_campanha_espelho
         (volc_campaign_id, lido_em, presenca, impressoes, cliques, custo_micros)
       VALUES ('00000000-0000-0000-0000-000000000001', now(), 'nao_encontrada', 1, 0, 0)$q$,
    '23514', 'trafego_espelho_entrega_sem_carimbo');

  -- A campanha ESTA na conta e esta ENABLED: nenhum dos seis estados a nomeia,
  -- entao `presenca` fica NULL. E a lacuna registrada no cabecalho da migration.
  PERFORM _prova_aceita(
    'espelho de campanha presente e sem ressalva (E-01: 1 impressao, 0 clique, R$0,00)',
    $q$INSERT INTO public.trafego_campanha_espelho
         (volc_campaign_id, lido_em, presenca, nome, estado_externo, veiculacao,
          canal, estrategia, lance_micros, verba_diaria_micros,
          impressoes, cliques, custo_micros, moeda, entrega_lida_em)
       VALUES ('00000000-0000-0000-0000-000000000001', now() - interval '10 min',
               NULL, 'Maquininha de Cartao', 'ENABLED', 'SERVING',
               'SEARCH', 'MANUAL_CPC', 120000, 10000000,
               1, 0, 0, 'BRL', now() - interval '10 min')$q$);

  -- Zero e NULL sao coisas diferentes, e o schema tem de deixar distingui-las.
  PERFORM _prova_igual(
    'zero medido continua zero, nao vira NULL',
    $q$SELECT impressoes::text || '/' || cliques::text || '/' || custo_micros::text
         FROM public.trafego_campanha_espelho
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '1/0/0');

  PERFORM _prova_aceita(
    'espelho de campanha que a conta nao entregou dado (tudo NULL, sem carimbo)',
    $q$INSERT INTO public.trafego_campanha_espelho (volc_campaign_id, lido_em, presenca)
       VALUES ('00000000-0000-0000-0000-000000000002', now(), 'sincronizacao_falhou')$q$);

  PERFORM _prova_igual(
    'ausencia de medida e NULL, nao 0',
    $q$SELECT coalesce(impressoes::text, 'NULL') FROM public.trafego_campanha_espelho
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000002'$q$,
    'NULL');
END $bloco$;


-- ===========================================================================
-- BLOCO 6 — regra C: falha NOVA nao apaga o ultimo dado BOM
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_recusa(
    'leitura retroativa nao sobrescreve leitura mais nova (espelho)',
    $q$UPDATE public.trafego_campanha_espelho SET lido_em = now() - interval '2 day'
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '23001', 'mais velha que a corrente');

  -- A varredura seguinte falhou ao medir entrega: manda tudo NULL.
  PERFORM _prova_aceita(
    'varredura seguinte falha ao medir entrega (manda tudo NULL)',
    $q$UPDATE public.trafego_campanha_espelho
          SET lido_em = now(), presenca = 'sincronizacao_falhou',
              impressoes = NULL, cliques = NULL, custo_micros = NULL,
              moeda = NULL, entrega_lida_em = NULL
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$);

  PERFORM _prova_igual(
    'a ultima entrega BOA foi preservada pela falha',
    $q$SELECT impressoes::text || '/' || cliques::text || '/' || custo_micros::text
         FROM public.trafego_campanha_espelho
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '1/0/0');

  PERFORM _prova_recusa(
    'numero de entrega sem carimbo NAO e engolido pela preservacao',
    $q$UPDATE public.trafego_campanha_espelho
          SET lido_em = now(), impressoes = 42, entrega_lida_em = NULL
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    '23001', 'sem carimbo de leitura');

  PERFORM _prova_igual(
    'e o CARIMBO dela veio junto (numero velho nao passa por novo)',
    $q$SELECT CASE WHEN entrega_lida_em < lido_em THEN 'carimbo antigo preservado'
                   ELSE 'carimbo foi adulterado' END
         FROM public.trafego_campanha_espelho
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000001'$q$,
    'carimbo antigo preservado');
END $bloco$;


-- ===========================================================================
-- BLOCO 7 — snapshot de conta: cada tentativa, e a ultima boa separada
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_recusa(
    'snapshot com customer_id vazio',
    $q$INSERT INTO public.trafego_snapshot_conta (customer_id, tentativa_em, tentativa_resultado)
       VALUES ('', now(), 'ok')$q$,
    '23514', 'trafego_snapshot_customer_id_valido');

  PERFORM _prova_recusa(
    'falha sem motivo declarado',
    $q$INSERT INTO public.trafego_snapshot_conta (customer_id, tentativa_em, tentativa_resultado)
       VALUES ('3849678045', now(), 'falhou')$q$,
    '23514', 'trafego_snapshot_falha_tem_motivo');

  PERFORM _prova_aceita(
    'leitura boa da conta 8017851692 (2 campanhas)',
    $q$INSERT INTO public.trafego_snapshot_conta
         (customer_id, nome, tentativa_em, tentativa_resultado,
          leitura_boa_em, leitura_boa_campanhas, leitura_boa_duracao_ms)
       VALUES ('8017851692', 'Credito Up', now() - interval '40 min', 'ok',
               now() - interval '40 min', 2, 2400)$q$);

  PERFORM _prova_aceita(
    'conta lida com sucesso e VAZIA (0 campanhas) — nao e o mesmo que nunca lida',
    $q$INSERT INTO public.trafego_snapshot_conta
         (customer_id, nome, tentativa_em, tentativa_resultado,
          leitura_boa_em, leitura_boa_campanhas)
       VALUES ('5478096539', 'Portal Mundo Mais', now(), 'ok', now(), 0)$q$);

  -- A varredura seguinte falha nesta conta. As OUTRAS contas nao sao tocadas.
  PERFORM _prova_aceita(
    'varredura seguinte falha na conta 8017851692',
    $q$UPDATE public.trafego_snapshot_conta
          SET tentativa_em = now(), tentativa_resultado = 'falhou',
              tentativa_motivo = 'USER_PERMISSION_DENIED',
              leitura_boa_em = NULL, leitura_boa_campanhas = NULL
        WHERE customer_id = '8017851692'$q$);

  PERFORM _prova_igual(
    'a ultima leitura BOA da conta sobreviveu a falha',
    $q$SELECT leitura_boa_campanhas::text FROM public.trafego_snapshot_conta
        WHERE customer_id = '8017851692'$q$,
    '2');

  PERFORM _prova_igual(
    'falha de UMA conta nao contaminou a outra (regra C)',
    $q$SELECT tentativa_resultado || '/' || leitura_boa_campanhas::text
         FROM public.trafego_snapshot_conta WHERE customer_id = '5478096539'$q$,
    'ok/0');

  PERFORM _prova_igual(
    'conta nunca varrida simplesmente NAO tem linha (nunca_lido != vazio_confirmado)',
    $q$SELECT count(*)::text FROM public.trafego_snapshot_conta
        WHERE customer_id = '3849678045'$q$,
    '0');

  PERFORM _prova_recusa(
    'contagem de campanhas sem o instante da leitura boa',
    $q$UPDATE public.trafego_snapshot_conta
          SET tentativa_em = now(), leitura_boa_em = NULL, leitura_boa_campanhas = 7
        WHERE customer_id = '8017851692'$q$,
    '23001', 'sem o instante da leitura boa');

  PERFORM _prova_recusa(
    'tentativa retroativa recusada (snapshot)',
    $q$UPDATE public.trafego_snapshot_conta SET tentativa_em = now() - interval '3 day'
        WHERE customer_id = '8017851692'$q$,
    '23001', 'mais velha que a corrente');

  -- O diario: cada tentativa virou evento, sem o sincronizador precisar lembrar.
  PERFORM _prova_igual(
    'cada tentativa de leitura virou evento append-only',
    $q$SELECT count(*)::text FROM public.trafego_evento
        WHERE tipo LIKE 'sincronizacao.conta.%'$q$,
    '3');
END $bloco$;


-- ===========================================================================
-- BLOCO 8 — vinculo: exige humano, e reversivel, e nunca apagado
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_recusa(
    'vinculo sem quem confirmou',
    $q$INSERT INTO public.trafego_vinculo (volc_campaign_id, opportunity_id, regra, confirmado_por)
       VALUES ('00000000-0000-0000-0000-000000000002', 65, 'url_final', '')$q$,
    '23514', 'trafego_vinculo_confirmado_por_nao_vazio');

  PERFORM _prova_recusa(
    'vinculo sem regra visivel (sugestao sem regra nao e oferecida)',
    $q$INSERT INTO public.trafego_vinculo (volc_campaign_id, opportunity_id, regra, confirmado_por)
       VALUES ('00000000-0000-0000-0000-000000000002', 65, '  ', 'operador')$q$,
    '23514', 'trafego_vinculo_regra_nao_vazia');

  PERFORM _prova_recusa(
    'vinculo que nao aponta para nada',
    $q$INSERT INTO public.trafego_vinculo (volc_campaign_id, regra, confirmado_por)
       VALUES ('00000000-0000-0000-0000-000000000002', 'url_final', 'operador')$q$,
    '23514', 'trafego_vinculo_tem_alvo');

  PERFORM _prova_aceita(
    'vinculo confirmado por humano, com regra e evidencia (FGTS -> funil run 9)',
    $q$INSERT INTO public.trafego_vinculo
         (volc_campaign_id, opportunity_id, funnel_run_id, regra, evidencia, confirmado_por)
       VALUES ('00000000-0000-0000-0000-000000000002', 65, 9, 'url_final_igual_a_lp_url',
               '{"lp_url": "/r/fgts-saque-aniversario/"}'::jsonb, 'tarcisio')$q$);
END $bloco$;

DO $bloco$
DECLARE primeiro uuid;
BEGIN
  SELECT vinculo_id INTO primeiro FROM public.trafego_vinculo
   WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000002' AND desfeito_em IS NULL;

  PERFORM _prova_recusa(
    'dois vinculos ATIVOS na mesma campanha',
    $q$INSERT INTO public.trafego_vinculo (volc_campaign_id, project_id, regra, confirmado_por)
       VALUES ('00000000-0000-0000-0000-000000000002', 3, 'slug', 'outro')$q$,
    '23505', 'trafego_vinculo_ativo_por_campanha_ux');

  PERFORM _prova_recusa(
    'a decisao confirmada e imutavel (nao se reescreve o alvo)',
    format($q$UPDATE public.trafego_vinculo SET opportunity_id = 66 WHERE vinculo_id = %L$q$, primeiro),
    '23001', 'a decisao confirmada e imutavel');

  PERFORM _prova_recusa(
    'DELETE de vinculo recusado (apagar destroi a trilha)',
    format($q$DELETE FROM public.trafego_vinculo WHERE vinculo_id = %L$q$, primeiro),
    '23001', 'DELETE recusado');

  PERFORM _prova_aceita(
    'desfazer registra quem, quando e por que',
    format($q$UPDATE public.trafego_vinculo
                 SET desfeito_por = 'tarcisio', desfeito_em = now(),
                     desfeito_motivo = 'era o funil errado'
               WHERE vinculo_id = %L$q$, primeiro));

  PERFORM _prova_recusa(
    'o registro do desfazer nao se reescreve',
    format($q$UPDATE public.trafego_vinculo SET desfeito_motivo = 'outro motivo'
               WHERE vinculo_id = %L$q$, primeiro),
    '23001', 'ja foi desfeito');

  PERFORM _prova_aceita(
    'vinculo novo aponta para o anterior (cadeia auditavel)',
    format($q$INSERT INTO public.trafego_vinculo
        (volc_campaign_id, opportunity_id, regra, confirmado_por, vinculo_anterior)
        VALUES ('00000000-0000-0000-0000-000000000002', 65, 'confirmacao_manual', 'tarcisio', %L)$q$,
      primeiro));

  PERFORM _prova_igual(
    'a linha desfeita continua la (reversivel, nao apagada)',
    $q$SELECT count(*)::text FROM public.trafego_vinculo
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000002'$q$,
    '2');

  PERFORM _prova_igual(
    'so um vinculo ativo',
    $q$SELECT count(*)::text FROM public.trafego_vinculo
        WHERE volc_campaign_id = '00000000-0000-0000-0000-000000000002'
          AND desfeito_em IS NULL$q$,
    '1');
END $bloco$;


-- ===========================================================================
-- BLOCO 9 — evento APPEND-ONLY
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_aceita(
    'evento de falha de persistencia sobre campanha que NAO existe como linha',
    $q$INSERT INTO public.trafego_evento
         (tipo, chave_de_agrupamento, produtor, sujeito_tipo,
          volc_campaign_id, customer_id, carga)
       VALUES ('persistencia.falhou', 'opaca-4f2a', 'porta-de-criacao', 'campanha',
               '00000000-0000-0000-0000-0000000000ff', '8017851692',
               '{"erro": "insert recusado"}'::jsonb)$q$);

  PERFORM _prova_recusa(
    'UPDATE em trafego_evento',
    $q$UPDATE public.trafego_evento SET tipo = 'outro' WHERE tipo = 'persistencia.falhou'$q$,
    '23001', 'append-only');

  PERFORM _prova_recusa(
    'DELETE em trafego_evento',
    $q$DELETE FROM public.trafego_evento WHERE tipo = 'persistencia.falhou'$q$,
    '23001', 'append-only');

  PERFORM _prova_recusa(
    'evento sem tipo',
    $q$INSERT INTO public.trafego_evento (tipo, chave_de_agrupamento, produtor)
       VALUES ('  ', 'k', 'p')$q$,
    '23514', 'trafego_evento_tipo_nao_vazio');

  PERFORM _prova_recusa(
    'evento sem chave de agrupamento',
    $q$INSERT INTO public.trafego_evento (tipo, chave_de_agrupamento, produtor)
       VALUES ('t', '', 'p')$q$,
    '23514', 'trafego_evento_chave_nao_vazia');
END $bloco$;


-- ===========================================================================
-- BLOCO 10 — ACESSO NEGATIVO REAL: anon e authenticated, com SET ROLE
-- ===========================================================================
DO $bloco$
DECLARE t text; papel text;
BEGIN
  FOREACH papel IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    FOREACH t IN ARRAY ARRAY[
      'trafego_linhagem', 'trafego_campanha', 'trafego_campanha_espelho',
      'trafego_snapshot_conta', 'trafego_vinculo', 'trafego_evento'
    ] LOOP
      PERFORM _prova_recusa_como('SELECT em ' || t, papel,
        format('SELECT 1 FROM public.%I', t));
      PERFORM _prova_recusa_como('DELETE em ' || t, papel,
        format('DELETE FROM public.%I', t));
    END LOOP;
  END LOOP;
END $bloco$;

DO $bloco$
BEGIN
  PERFORM _prova_recusa_como('INSERT em trafego_campanha', 'anon',
    $q$INSERT INTO public.trafego_campanha (volc_campaign_id, customer_id, campaign_id, criada_por)
       VALUES ('gads-8017851692-555', '8017851692', '555', 'anon')$q$);
  PERFORM _prova_recusa_como('UPDATE em trafego_campanha', 'authenticated',
    $q$UPDATE public.trafego_campanha SET criada_por = 'anon'$q$);
  PERFORM _prova_recusa_como('INSERT em trafego_evento', 'anon',
    $q$INSERT INTO public.trafego_evento (tipo, chave_de_agrupamento, produtor)
       VALUES ('forjado', 'k', 'anon')$q$);
END $bloco$;

-- Defesa em profundidade: mesmo COM grant, a RLS de zero policies nega.
-- Em transacao propria, revertida no fim — o grant nao persiste.
BEGIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.trafego_campanha TO anon;
DO $bloco$
DECLARE linhas int; total int;
BEGIN
  SELECT count(*) INTO total FROM public.trafego_campanha;
  IF total = 0 THEN RAISE EXCEPTION 'prova inutil: a tabela esta vazia'; END IF;

  EXECUTE 'SET LOCAL ROLE anon';
  SELECT count(*) INTO linhas FROM public.trafego_campanha;
  EXECUTE 'RESET ROLE';

  IF linhas <> 0 THEN
    RAISE EXCEPTION
      'PROVA FALHOU: com GRANT, anon leu % de % linhas — RLS nao esta segurando', linhas, total;
  END IF;
  RAISE NOTICE
    'PROVA ok: mesmo COM GRANT, anon le 0 de % linhas (RLS ligada, zero policies)', total;
END $bloco$;
ROLLBACK;

-- E o grant de fato nao sobreviveu ao ROLLBACK.
DO $bloco$
BEGIN
  PERFORM _prova_recusa_como('grant temporario nao vazou da transacao', 'anon',
    'SELECT 1 FROM public.trafego_campanha');
END $bloco$;


-- ===========================================================================
-- BLOCO 11 — service_role: o backend funciona, e mesmo ele nao apaga
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_aceita_como('backend le o inventario', 'service_role',
    'SELECT 1 FROM public.trafego_campanha');
  PERFORM _prova_aceita_como('backend registra evento', 'service_role',
    $q$INSERT INTO public.trafego_evento (tipo, chave_de_agrupamento, produtor)
       VALUES ('sincronizacao.iniciada', 'opaca-9b1', 'sincronizador')$q$);

  PERFORM _prova_recusa_como('nem o backend apaga campanha', 'service_role',
    'DELETE FROM public.trafego_campanha');
  PERFORM _prova_recusa_como('nem o backend apaga evento', 'service_role',
    'DELETE FROM public.trafego_evento');
  PERFORM _prova_recusa_como('nem o backend altera evento', 'service_role',
    $q$UPDATE public.trafego_evento SET tipo = 'x'$q$);
  PERFORM _prova_recusa_como('nem o backend apaga vinculo', 'service_role',
    'DELETE FROM public.trafego_vinculo');
END $bloco$;



-- ===========================================================================
-- BLOCO 13 — O ESPELHO PRESERVA ROTULO E NUNCA NUMERO
-- ===========================================================================
-- A pergunta que decide cada coluna: NULO aqui pode ser um fato MEDIDO?
-- Se pode, preservar INVENTA. Se nao pode, aceitar o nulo APAGA dado bom.
INSERT INTO public.trafego_campanha
  (volc_campaign_id, customer_id, campaign_id, criada_por)
VALUES ('gads-8017851692-3001', '8017851692', '3001', 'varredura'),
       ('gads-8017851692-3002', '8017851692', '3002', 'varredura'),
       ('gads-8017851692-3003', '8017851692', '3003', 'varredura'),
       ('gads-8017851692-3004', '8017851692', '3004', 'varredura');

DO $bloco$
BEGIN
  -- MOEDA SEM ENTREGA. Antes, a CHECK a agrupava com as medidas e obrigava a
  -- apaga-la sempre que a entrega nao voltava — a verba do dia aparecia na tela
  -- sem dizer em que moeda. Moeda e UNIDADE, e o carimbo dela e `lido_em`.
  PERFORM _prova_aceita(
    'moeda sem entrega medida (unidade nao e medida)',
    $q$INSERT INTO public.trafego_campanha_espelho
         (volc_campaign_id, lido_em, nome, estado_externo, veiculacao, canal,
          estrategia, moeda, verba_diaria_micros, lance_micros)
       VALUES ('gads-8017851692-3001', now() - interval '20 min',
               'Consorcio', 'ENABLED', 'SERVING', 'SEARCH', 'MANUAL_CPC',
               'BRL', 10000000, 120000)$q$);

  PERFORM _prova_aceita(
    'a varredura seguinte nao trouxe rotulo nenhum (leitura parcial)',
    $q$UPDATE public.trafego_campanha_espelho
          SET lido_em = now(), nome = NULL, estado_externo = NULL,
              veiculacao = NULL, canal = NULL, moeda = NULL,
              estrategia = NULL, lance_micros = NULL, verba_diaria_micros = NULL
        WHERE volc_campaign_id = 'gads-8017851692-3001'$q$);

  PERFORM _prova_igual(
    'ROTULO preservado: a linha nao fica sem nome na tela',
    $q$SELECT nome || '/' || estado_externo || '/' || veiculacao || '/' || canal || '/' || moeda
         FROM public.trafego_campanha_espelho
        WHERE volc_campaign_id = 'gads-8017851692-3001'$q$,
    'Consorcio/ENABLED/SERVING/SEARCH/BRL');

  -- E o outro lado da regra, que e o que a torna honesta: NUMERO nao sobrevive.
  -- O carimbo de `lance_micros` e `verba_diaria_micros` e o `lido_em` que
  -- acabou de avancar; preserva-los seria dado velho passando por novo.
  PERFORM _prova_igual(
    'NUMERO nao preservado: lance e verba somem em vez de envelhecer',
    $q$SELECT coalesce(lance_micros::text, 'NULL') || '/' ||
              coalesce(verba_diaria_micros::text, 'NULL')
         FROM public.trafego_campanha_espelho
        WHERE volc_campaign_id = 'gads-8017851692-3001'$q$,
    'NULL/NULL');

  -- ESTRATEGIA fica de fora dos rotulos, e o motivo tem consequencia em dinheiro:
  -- ela MUDA na vida da campanha, e `estrategia_canonica()` devolve NULL para
  -- estrategia fora do vocabulario — o nulo PODE ser medicao. Preservada, a tela
  -- mostraria MANUAL_CPC numa campanha ja em TARGET_ROAS, e o teto de cliques
  -- seria calculado a partir de um lance que ninguem mais usa.
  PERFORM _prova_igual(
    'estrategia NAO preservada (o nulo dela pode ser medicao)',
    $q$SELECT coalesce(estrategia, 'NULL') FROM public.trafego_campanha_espelho
        WHERE volc_campaign_id = 'gads-8017851692-3001'$q$,
    'NULL');
END $bloco$;

DO $bloco$
BEGIN
  -- PRESENCA nunca e preservada, e este e o caso que prova por que: NULO E O
  -- FATO "presente, sem ressalva". Preservada, `removida` ficaria colada para
  -- sempre numa campanha reativada.
  PERFORM _prova_aceita(
    'campanha lida como removida',
    $q$INSERT INTO public.trafego_campanha_espelho
         (volc_campaign_id, lido_em, presenca, nome, estado_externo)
       VALUES ('gads-8017851692-3002', now() - interval '10 min',
               'removida', 'Antiga', 'REMOVED')$q$);

  PERFORM _prova_aceita(
    'a campanha voltou a aparecer sem ressalva (presenca NULA)',
    $q$UPDATE public.trafego_campanha_espelho
          SET lido_em = now(), presenca = NULL, estado_externo = 'ENABLED'
        WHERE volc_campaign_id = 'gads-8017851692-3002'$q$);

  PERFORM _prova_igual(
    'presenca voltou a NULL — nao ficou colada em removida',
    $q$SELECT coalesce(presenca, 'NULL') FROM public.trafego_campanha_espelho
        WHERE volc_campaign_id = 'gads-8017851692-3002'$q$,
    'NULL');
END $bloco$;


-- ===========================================================================
-- BLOCO 14 — SNAPSHOT: `parcial` sobrevive, e sem motivo nao entra
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_recusa(
    'tentativa parcial sem dizer o que faltou',
    $q$INSERT INTO public.trafego_snapshot_conta
         (customer_id, tentativa_em, tentativa_resultado)
       VALUES ('3849678045', now(), 'parcial')$q$,
    '23514', 'trafego_snapshot_falha_tem_motivo');

  -- REGRA E. Se `parcial` tivesse de virar 'ok' para caber no schema,
  -- `frescor_da_conta()` responderia `recente` para uma conta que nao entregou
  -- metade do que foi pedido — e frescor desconhecido virando `recente` e
  -- exatamente o que nao pode acontecer.
  PERFORM _prova_aceita(
    'tentativa parcial com motivo e escopo (regra E)',
    $q$INSERT INTO public.trafego_snapshot_conta
         (customer_id, nome, tentativa_em, tentativa_resultado, tentativa_motivo,
          tentativa_escopo, leitura_boa_em, leitura_boa_campanhas)
       VALUES ('3849678045', 'Conta Parcial', now(), 'parcial',
               'TimeoutError: entrega nao voltou', 'entrega(ultimos_7d)',
               now(), 3)$q$);

  PERFORM _prova_igual(
    'a projecao de conta entrega escopo e vazio_confirmado derivados',
    $q$SELECT tentativa_resultado || '/' || escopo_parcial || '/' || vazio_confirmado::text
         FROM public.trafego_inventario_conta WHERE customer_id = '3849678045'$q$,
    'parcial/entrega(ultimos_7d)/false');

  -- `vazio_confirmado` e DERIVADO, e nao coluna: guardado, seria uma segunda
  -- fonte da mesma verdade, capaz de divergir de `leitura_boa_campanhas`.
  PERFORM _prova_igual(
    'leitura boa com zero campanhas e vazio_confirmado; sem leitura boa, nao e',
    $q$SELECT string_agg(customer_id || '=' || vazio_confirmado::text, ' ' ORDER BY customer_id)
         FROM public.trafego_inventario_conta$q$,
    '3849678045=false 5478096539=true 8017851692=false');
END $bloco$;


-- ===========================================================================
-- BLOCO 15 — A PROJECAO DE CAMPANHA: `atencao` sem coluna gerada
-- ===========================================================================
-- A condicao de atencao era uma coluna GERADA que so existia numa DDL apagada.
-- Aqui ela e uma projecao explicita sobre o modelo canonico, e cada termo e um
-- FATO OBSERVADO. As provas abaixo isolam um termo de cada vez.
DO $bloco$
BEGIN
  -- Conta 3849678045 esta 'parcial' (nao 'falhou'), entao o termo (1) nao arma.
  PERFORM _prova_aceita(
    'campanha ligada, entregando, sem ressalva',
    $q$INSERT INTO public.trafego_campanha_espelho
         (volc_campaign_id, lido_em, nome, estado_externo, canal, estrategia,
          impressoes, cliques, custo_micros, moeda, entrega_lida_em)
       VALUES ('gads-8017851692-3003', now(), 'Saudavel', 'ENABLED', 'SEARCH',
               'MANUAL_CPC', 40, 3, 9000, 'BRL', now())$q$);

  PERFORM _prova_aceita(
    'campanha ligada e sem entrega medida',
    $q$INSERT INTO public.trafego_campanha_espelho
         (volc_campaign_id, lido_em, nome, estado_externo, canal)
       VALUES ('gads-8017851692-3004', now(), 'Sem medida', 'ENABLED', 'SEARCH')$q$);

  -- ⚠️ A conta 8017851692 esta com tentativa 'falhou' desde o BLOCO 7, entao
  -- TODA campanha dela arma o termo (1) — "nao sabemos nada sobre ela agora".
  -- Isso e o E-07 em forma de consulta: tres contas falhando era visualmente
  -- identico a "tudo bem".
  PERFORM _prova_igual(
    'conta que falhou marca todas as campanhas dela',
    $q$SELECT string_agg(DISTINCT atencao::text, ',')
         FROM public.trafego_inventario_campanha WHERE customer_id = '8017851692'$q$,
    'true');

  PERFORM _prova_aceita(
    'a conta volta a responder',
    $q$UPDATE public.trafego_snapshot_conta
          SET tentativa_em = now(), tentativa_resultado = 'ok',
              tentativa_motivo = NULL, leitura_boa_em = now(),
              leitura_boa_campanhas = 4
        WHERE customer_id = '8017851692'$q$);

  PERFORM _prova_igual(
    'ligada + entregando + sem ressalva NAO pede atencao',
    $q$SELECT atencao::text FROM public.trafego_inventario_campanha
        WHERE volc_campaign_id = 'gads-8017851692-3003'$q$,
    'false');

  PERFORM _prova_igual(
    'ligada e SEM entrega medida pede atencao (esta gastando e nao sei quanto)',
    $q$SELECT atencao::text FROM public.trafego_inventario_campanha
        WHERE volc_campaign_id = 'gads-8017851692-3004'$q$,
    'true');

  PERFORM _prova_aceita(
    'a campanha saudavel para de aparecer no leilao (zero MEDIDO)',
    $q$UPDATE public.trafego_campanha_espelho
          SET lido_em = now(), impressoes = 0, cliques = 0, custo_micros = 0,
              entrega_lida_em = now()
        WHERE volc_campaign_id = 'gads-8017851692-3003'$q$);

  PERFORM _prova_igual(
    'zero MEDIDO pede atencao — e nao se confunde com "nao consegui medir"',
    $q$SELECT atencao::text FROM public.trafego_inventario_campanha
        WHERE volc_campaign_id = 'gads-8017851692-3003'$q$,
    'true');

  -- Campanha PAUSADA nunca entra por nao entregar: ela nao deveria entregar.
  -- Marca-la encheria a aba de linhas CORRETAS, o operador pararia de olhar, e
  -- o alerta morreria — que e o unico jeito de um alerta falhar de vez.
  PERFORM _prova_aceita(
    'a campanha e pausada',
    $q$UPDATE public.trafego_campanha_espelho
          SET lido_em = now(), estado_externo = 'PAUSED'
        WHERE volc_campaign_id = 'gads-8017851692-3004'$q$);

  PERFORM _prova_igual(
    'pausada e sem entrega NAO pede atencao',
    $q$SELECT atencao::text FROM public.trafego_inventario_campanha
        WHERE volc_campaign_id = 'gads-8017851692-3004'$q$,
    'false');
END $bloco$;

DO $bloco$
BEGIN
  -- Identidade DECLARADA e ainda nao espelhada: a janela entre "o operador
  -- criou" e "a varredura passou". Nulo em `presenca` significa "presente, sem
  -- ressalva", e uma campanha que NUNCA foi lida nao pode herdar essa
  -- afirmacao.
  PERFORM _prova_aceita(
    'campanha declarada pela porta de criacao, sem espelho ainda',
    $q$INSERT INTO public.trafego_campanha
         (volc_campaign_id, customer_id, campaign_id, criada_por)
       VALUES ('gads-8017851692-3005', '8017851692', '3005', 'porta-de-criacao')$q$);

  PERFORM _prova_igual(
    'sem espelho, a view NAO declara "presente" — e nem escolhe um dos seis',
    $q$SELECT presenca || '/' || atencao::text
         FROM public.trafego_inventario_campanha
        WHERE volc_campaign_id = 'gads-8017851692-3005'$q$,
    'nao_espelhada/true');

  -- `nao_espelhada` esta FORA das seis de proposito, e nunca pode ser GRAVADA:
  -- a CHECK do espelho a recusa. Ela so existe como projecao, para a leitura
  -- degradar sozinha para a afirmacao mais fraca disponivel.
  PERFORM _prova_recusa(
    'nao_espelhada nao pode ser gravada (so projetada)',
    $q$INSERT INTO public.trafego_campanha_espelho (volc_campaign_id, lido_em, presenca)
       VALUES ('gads-8017851692-3005', now(), 'nao_espelhada')$q$,
    '23514', 'trafego_espelho_presenca_conhecida');
END $bloco$;

DO $bloco$
BEGIN
  PERFORM _prova_aceita(
    'vinculo desfeito e vinculo ativo na MESMA campanha',
    $q$INSERT INTO public.trafego_vinculo
         (vinculo_id, volc_campaign_id, opportunity_id, regra, confirmado_por,
          desfeito_por, desfeito_em, desfeito_motivo)
       VALUES ('00000000-0000-0000-0000-00000000d001', 'gads-8017851692-3003',
               11, 'url_final', 'tarcisio', 'tarcisio', now(), 'funil errado')$q$);

  PERFORM _prova_aceita(
    'o vinculo que substituiu o desfeito',
    $q$INSERT INTO public.trafego_vinculo
         (volc_campaign_id, opportunity_id, project_id, regra, confirmado_por,
          vinculo_anterior)
       VALUES ('gads-8017851692-3003', 65, 3, 'confirmacao_manual', 'tarcisio',
               '00000000-0000-0000-0000-00000000d001')$q$);

  -- Sem o indice parcial de vinculo ativo, este LEFT JOIN multiplicaria a linha
  -- e o sino passaria a contar a mesma campanha duas vezes.
  PERFORM _prova_igual(
    'vinculo desfeito NAO multiplica a linha da campanha na projecao',
    $q$SELECT count(*)::text || '/' || max(opportunity_id)::text
         FROM public.trafego_inventario_campanha
        WHERE volc_campaign_id = 'gads-8017851692-3003'$q$,
    '1/65');

  PERFORM _prova_igual(
    'procedencia desconhecida e vinculo ausente viajam SEPARADOS de atencao',
    $q$SELECT procedencia_desconhecida::text || '/' || sem_vinculo::text || '/' || atencao::text
         FROM public.trafego_inventario_campanha
        WHERE volc_campaign_id = 'gads-8017851692-3004'$q$,
    'true/true/false');
END $bloco$;


-- ===========================================================================
-- BLOCO 16 — AS VIEWS NAO SAO UM TUNEL POR CIMA DA RLS
-- ===========================================================================
-- Uma view roda com os privilegios do DONO por padrao. Uma view de postgres
-- sobre estas seis tabelas entregaria tudo a quem tivesse SELECT nela, e todo o
-- trabalho de RLS viraria decoracao.
DO $bloco$
DECLARE v text;
BEGIN
  FOREACH v IN ARRAY ARRAY['trafego_inventario_campanha', 'trafego_inventario_conta'] LOOP
    PERFORM _prova_recusa_como('anon nao le ' || v, 'anon',
      format('SELECT 1 FROM public.%I', v));
    PERFORM _prova_recusa_como('authenticated nao le ' || v, 'authenticated',
      format('SELECT 1 FROM public.%I', v));
    PERFORM _prova_aceita_como('o backend le ' || v, 'service_role',
      format('SELECT 1 FROM public.%I', v));
  END LOOP;

  PERFORM _prova_igual('as duas views tem security_invoker ligado',
    $q$SELECT count(*)::text FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname='public' AND c.relkind='v' AND c.relname LIKE 'trafego\_%'
         AND array_to_string(c.reloptions, ',') LIKE '%security_invoker=true%'$q$,
    '2');

  -- Defesa em profundidade: mesmo COM grant, `security_invoker` faz a RLS das
  -- tabelas de baixo valer para quem chama. Em transacao propria, revertida.
  PERFORM _prova_igual('view nao concede escrita a ninguem',
    $q$SELECT count(*)::text FROM information_schema.role_table_grants
        WHERE table_schema='public' AND table_name LIKE 'trafego\_inventario%'
          AND privilege_type <> 'SELECT' AND grantee <> 'postgres'$q$,
    '0');
END $bloco$;

-- O teste que importa: E SE ALGUEM CONCEDER SELECT NA VIEW POR ENGANO?
--
-- Numa view comum (privilegios do dono), esse GRANT bastaria: anon leria as
-- seis tabelas inteiras atraves dela. Com `security_invoker`, o GRANT na view
-- nao serve de nada — o Postgres passa a exigir de anon o mesmo que exigiria se
-- ele consultasse as tabelas diretamente, e ele nao tem.
--
-- ⚠️ A recusa aqui e MAIS FORTE que a da BLOCO 10. La, anon tinha grant na
-- tabela e a RLS o segurava devolvendo ZERO LINHA. Aqui ele nem chega a abrir a
-- consulta: o erro e 42501 na tabela de baixo. Duas travas de naturezas
-- diferentes, e esta prova mostra a segunda.
-- Em transacao propria, revertida no fim — o grant nao persiste.
BEGIN;
GRANT SELECT ON public.trafego_inventario_campanha TO anon;
DO $bloco$
DECLARE total int;
BEGIN
  SELECT count(*) INTO total FROM public.trafego_inventario_campanha;
  IF total = 0 THEN RAISE EXCEPTION 'prova inutil: a view esta vazia'; END IF;

  PERFORM _prova_recusa_como(
    'GRANT na view nao abre as tabelas de baixo', 'anon',
    'SELECT 1 FROM public.trafego_inventario_campanha');

  RAISE NOTICE
    'PROVA ok: com GRANT na view, anon continua barrado nas % linhas (security_invoker)', total;
END $bloco$;
ROLLBACK;

-- E o grant de fato nao sobreviveu ao ROLLBACK.
DO $bloco$
BEGIN
  PERFORM _prova_recusa_como('grant temporario na view nao vazou', 'anon',
    'SELECT 1 FROM public.trafego_inventario_campanha');
END $bloco$;

-- ===========================================================================
-- BLOCO 12 — o estado final do catalogo
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_igual('6 tabelas do dominio criadas',
    $q$SELECT count(*)::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'trafego\_%'$q$, '6');

  PERFORM _prova_igual('todas com RLS ligada E forcada',
    $q$SELECT count(*)::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'trafego\_%'
          AND c.relrowsecurity AND c.relforcerowsecurity$q$, '6');

  PERFORM _prova_igual('zero policies (a negacao e por ausencia)',
    $q$SELECT count(*)::text FROM pg_policies
        WHERE schemaname='public' AND tablename LIKE 'trafego\_%'$q$, '0');

  PERFORM _prova_igual('zero privilegio de anon/authenticated em qualquer delas',
    $q$SELECT count(*)::text FROM information_schema.role_table_grants
        WHERE table_schema='public' AND table_name LIKE 'trafego\_%'
          AND grantee IN ('anon','authenticated')$q$, '0');

  PERFORM _prova_igual('nenhum DELETE concedido a ninguem',
    $q$SELECT count(*)::text FROM information_schema.role_table_grants
        WHERE table_schema='public' AND table_name LIKE 'trafego\_%'
          AND privilege_type='DELETE' AND grantee <> 'postgres'$q$, '0');

  -- Gate de acoplamento do SPEC 9.4: o nucleo nao conhece semantica de canal.
  PERFORM _prova_igual('gate de acoplamento: zero vocabulario de canal no schema',
    $q$SELECT count(*)::text FROM information_schema.columns
        WHERE table_schema='public' AND table_name LIKE 'trafego\_%'
          AND (column_name ~* 'keyword|asset_group|placement|audience|match_type')$q$, '0');
END $bloco$;

DROP FUNCTION _prova_recusa(text, text, text, text);
DROP FUNCTION _prova_aceita(text, text);
DROP FUNCTION _prova_igual(text, text, text);
DROP FUNCTION _prova_recusa_como(text, text, text);
DROP FUNCTION _prova_aceita_como(text, text, text);
PROVAS

set +e
psql -X -q -h "$SOCK" -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -f "${BASE}/provas.sql" > "$SAIDA" 2>&1
CODIGO=$?
set -e

# psql -f prefixa cada aviso com "psql:arquivo:linha:". Sem tirar o prefixo, a
# saida vira ruido e ninguem le a lista de provas — que e o produto deste script.
sed -E 's/^psql:[^ ]+: //; s/^NOTICE:  /  /' "$SAIDA" \
  | grep -E '^( +PROVA|ERROR|FATAL)' || true

APROVADAS=$(grep -c 'PROVA ok' "$SAIDA" || true)
if [[ $CODIGO -ne 0 ]]; then
  echo ""
  echo "✗ PROVAS FALHARAM (${APROVADAS} passaram antes da falha)"
  exit 1
fi
echo "  ✓ ${APROVADAS} provas passaram"

# ---------------------------------------------------------------------------
# 5. Rollback, e reaplicacao do zero
# ---------------------------------------------------------------------------
echo "▶ aplicando o rollback"
executar -f "$ROLLBACK" >/dev/null
executar <<'SQL' >/dev/null
DO $$
BEGIN
  IF to_regclass('public.trafego_campanha') IS NOT NULL THEN
    RAISE EXCEPTION 'o rollback deixou trafego_campanha de pe';
  END IF;
END $$;
SQL
echo "  ✓ dominio removido; nada com prefixo trafego_ restou"

echo "▶ reaplicando a migration sobre o banco revertido"
executar -f "$MIGRATION" >/dev/null
echo "  ✓ reaplicavel depois do rollback"

echo "▶ conferindo que a migration recusa reaplicacao POR CIMA"
if executar -f "$MIGRATION" >/dev/null 2>&1; then
  echo "  ✗ a migration aceitou rodar duas vezes seguidas — a guarda nao funcionou" >&2
  exit 1
fi
echo "  ✓ recusada com a tabela ja existente"

# ---------------------------------------------------------------------------
# 6. A CAMADA DE ACESSO, contra um cluster igual a este
# ---------------------------------------------------------------------------
# O schema estar certo nao prova que o codigo fala com ele. O defeito que esta
# rodada fechou era exatamente isso: `backend/app/trafego/` consultava tres
# tabelas que nenhuma migration cria, e a suite passava porque tudo era dublado.
#
# `test_trafego_persistencia.py` sobe o proprio cluster descartavel, aplica esta
# mesma migration e roda `persistencia.py` contra ela. Fica aqui, e nao so no
# pytest, para que um `CREATE TABLE` alterado neste arquivo derrube o gate da
# migration — e nao apareca so quando alguem lembrar de rodar os testes.
VENV="${RAIZ}/backend/.venv/bin/python"
if [[ -x "$VENV" ]]; then
  echo "▶ rodando a camada de acesso contra um cluster com esta migration"
  if "$VENV" -m pytest "${RAIZ}/backend/tests/test_trafego_persistencia.py" \
       -q -p no:warnings > "${BASE}/persistencia.out" 2>&1; then
    echo "  ✓ $(grep -Eo '[0-9]+ passed' "${BASE}/persistencia.out" | tail -1) em persistencia.py"
  else
    echo "  ✗ a camada de acesso NAO fala com este schema:" >&2
    tail -25 "${BASE}/persistencia.out" >&2
    exit 1
  fi
else
  echo "  ⚠ backend/.venv ausente: a camada de acesso NAO foi exercitada"
  echo "    (rode: backend/.venv/bin/python -m pytest backend/tests/test_trafego_persistencia.py)"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo " ${APROVADAS} provas · migration aplicavel, reversivel e reaplicavel"
echo " cluster descartado. Nada foi tocado em producao."
echo "════════════════════════════════════════════════════════════════"
