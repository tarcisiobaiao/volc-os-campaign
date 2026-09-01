#!/usr/bin/env bash
# =============================================================================
# provar-ciclo-v13_01.sh — o ciclo do Cofre de Ativos num Postgres descartavel:
# aplicar -> operar -> reverter -> reaplicar, com prova de ESTRUTURA, SEGURANCA,
# COMPORTAMENTO e NAO-VAZAMENTO. NUNCA toca em producao.
# =============================================================================
#
# POR QUE DOCKER postgres:15 E NAO O initdb LOCAL
#
# Producao e `supabase/postgres:15.8.1.085` — PostgreSQL 15 (medido em
# docs/INCIDENTE-JWT-RUNBOOK.md:161 e confirmado por `SHOW server_version` =
# 15.8 em 01/09/2026). O Homebrew desta maquina traz o 16. Provar num 16 e
# aplicar num 15 e uma divergencia silenciosa: sintaxe e comportamento que o 16
# aceita podem nao existir no 15, e a falha aparece em producao. Os harnesses
# anteriores deste repositorio pedem `postgresql@16` e nao conferem a versao —
# esta prova fecha essa lacuna usando a MESMA major da producao.
#
# `--local` cai para o initdb do PATH e IMPRIME a divergencia de versao em vez
# de escondê-la.
#
# COMO RODAR
#   ./scripts/provar-ciclo-v13_01.sh
#   ./scripts/provar-ciclo-v13_01.sh --local     # sem Docker, usa initdb do PATH
#   ./scripts/provar-ciclo-v13_01.sh --manter    # nao destroi o cluster (debug)
# =============================================================================
set -euo pipefail
export LC_ALL=C LANG=C

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATION="${RAIZ}/supabase/migrations/v13_01_cofre_de_ativos.sql"
ROLLBACK="${RAIZ}/supabase/migrations/v13_99_cofre_de_ativos_rollback.sql"
IMAGEM="postgres:15"

MANTER=0; LOCAL=0
for arg in "$@"; do
  case "$arg" in
    --manter) MANTER=1 ;;
    --local)  LOCAL=1 ;;
    *) echo "argumento desconhecido: $arg" >&2; exit 2 ;;
  esac
done

[[ -f "$MIGRATION" ]] || { echo "ERRO: migration nao encontrada: $MIGRATION" >&2; exit 1; }
[[ -f "$ROLLBACK"  ]] || { echo "ERRO: rollback nao encontrado: $ROLLBACK"  >&2; exit 1; }

BASE="$(mktemp -d "${TMPDIR:-/tmp}/volc-cofre-prova.XXXXXX")"
CID=""; PGDATA=""; SOCK=""

limpar() {
  local codigo=$?
  if [[ -n "$CID" ]]; then docker rm -f "$CID" >/dev/null 2>&1 || true; fi
  if [[ -n "$PGDATA" && -d "$PGDATA" ]]; then pg_ctl -D "$PGDATA" -m immediate stop >/dev/null 2>&1 || true; fi
  if [[ $MANTER -eq 1 ]]; then echo "→ artefatos preservados em ${BASE} (--manter)"; else rm -rf "$BASE"; fi
  exit $codigo
}
trap limpar EXIT

if [[ $LOCAL -eq 0 ]] && command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "▶ cluster descartavel em Docker (${IMAGEM} — mesma major da producao)"
  CID=$(docker run -d --rm -e POSTGRES_PASSWORD=prova -e POSTGRES_HOST_AUTH_METHOD=trust "$IMAGEM" -c fsync=off)
  for _ in $(seq 1 60); do
    if docker exec "$CID" pg_isready -U postgres -q 2>/dev/null; then break; fi
    sleep 0.5
  done
  docker exec "$CID" pg_isready -U postgres -q || { echo "ERRO: Postgres nao subiu" >&2; exit 1; }
  executar() { docker exec -i "$CID" psql -U postgres -X -q -v ON_ERROR_STOP=1 "$@"; }
  aplicar()  { docker exec -i "$CID" psql -U postgres -X -q -v ON_ERROR_STOP=1 < "$1"; }
else
  for binario in initdb pg_ctl psql; do
    command -v "$binario" >/dev/null 2>&1 || { echo "ERRO: '$binario' ausente e Docker indisponivel." >&2; exit 1; }
  done
  PGDATA="${BASE}/dados"; SOCK="${BASE}/sock"; mkdir -p "$SOCK"
  echo "▶ cluster descartavel local com $(initdb --version)"
  echo "  ⚠ producao e PostgreSQL 15.8; divergencia de major NAO e conferida neste modo"
  initdb -D "$PGDATA" -U postgres --encoding=UTF8 --locale=C >/dev/null
  pg_ctl -D "$PGDATA" -l "${BASE}/postgres.log" -o "-k ${SOCK} -h ''" -w start >/dev/null
  executar() { psql -X -q -h "$SOCK" -U postgres -d postgres -v ON_ERROR_STOP=1 "$@"; }
  aplicar()  { psql -X -q -h "$SOCK" -U postgres -d postgres -v ON_ERROR_STOP=1 -f "$1"; }
fi

VERSAO=$(executar -tA -c "SHOW server_version")
echo "  ✓ servidor ${VERSAO}"

# ---------------------------------------------------------------------------
# 1. Reproduzir o Supabase — inclusive o que ele tem de errado
# ---------------------------------------------------------------------------
# Os atributos abaixo NAO sao chutados: foram lidos de `pg_roles` no Supabase
# oficial em 01/09/2026, por consulta somente leitura.
#
#   postgres      rolsuper=f  rolbypassrls=t
#   service_role  rolsuper=f  rolbypassrls=t   <- RLS nao contem o backend
#   authenticated rolsuper=f  rolbypassrls=f
#   anon          rolsuper=f  rolbypassrls=f
#
# Reproduzir o BYPASSRLS de service_role e o que impede esta prova de concluir
# que RLS protege o backend — ela nao protege. Quem protege e o REVOKE nominal.
echo "▶ semeando papeis do Supabase e o default ACL QUEBRADO de public"
executar >/dev/null <<'SQL'
CREATE ROLE anon           NOLOGIN NOINHERIT;
CREATE ROLE authenticated  NOLOGIN NOINHERIT;
CREATE ROLE service_role   NOLOGIN NOINHERIT BYPASSRLS;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO anon, authenticated, service_role;
SQL

# Sonda: se o defeito de plataforma NAO for reproduzido, toda prova de seguranca
# abaixo vira falso-positivo — a tabela estaria fechada porque nada a abriu.
executar >/dev/null <<'SQL'
CREATE TABLE public._sonda_do_default_acl (id int);
DO $$
BEGIN
  IF NOT has_table_privilege('anon', 'public._sonda_do_default_acl', 'INSERT') THEN
    RAISE EXCEPTION 'o cluster NAO reproduziu o default ACL aberto; as provas de seguranca seriam falso-positivo';
  END IF;
END $$;
DROP TABLE public._sonda_do_default_acl;
SQL
echo "  ✓ default ACL aberto reproduzido (tabela nova nasce escrivel por anon)"

# ---------------------------------------------------------------------------
# 2. DEGRAU 1 — aplicar do zero
# ---------------------------------------------------------------------------
echo; echo "DEGRAU 1 — aplicar"
aplicar "$MIGRATION" 2>&1 | sed 's/^NOTICE:  /  /'
echo "  ✓ v13_01 aplicada"

# ---------------------------------------------------------------------------
# 3. DEGRAU 2 — operar, com provas
# ---------------------------------------------------------------------------
echo; echo "DEGRAU 2 — operar"
cat > "${BASE}/provas.sql" <<'PROVAS'
\set ON_ERROR_STOP on

-- ⚠️ AJUDANTES QUE NAO ACEITAM QUALQUER ERRO.
--
-- Uma versao ingenua destes ajudantes captura `WHEN others` e declara "PROVA ok"
-- para QUALQUER excecao — e ai um erro de digitacao no proprio teste (coluna
-- inexistente, virgula a mais) conta como prova de que o banco recusa o que tem
-- de recusar. A suite fica verde medindo a si mesma.
--
-- Aqui o motivo e obrigatorio em dois niveis: o SQLSTATE, sempre conferido
-- (23514 CHECK, 23505 unique, 23503 FK, 23001 restrict_violation, 22023
-- invalid_parameter_value, P0002 no_data_found, 42501 privilegio), e QUEM
-- recusou — nome da constraint quando a excecao o carrega, ou trecho citado na
-- mensagem quando e um RAISE de funcao.
CREATE FUNCTION _prova_recusa(rotulo text, comando text,
                              sqlstate_esperado text, alvo_esperado text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE estado text; nome_constraint text; erro text;
BEGIN
  BEGIN
    EXECUTE comando;
  EXCEPTION WHEN others THEN
    GET STACKED DIAGNOSTICS estado = RETURNED_SQLSTATE, nome_constraint = CONSTRAINT_NAME, erro = MESSAGE_TEXT;
    erro := replace(coalesce(erro, ''), E'\n', ' ');
    IF estado IS DISTINCT FROM sqlstate_esperado THEN
      RAISE EXCEPTION 'PROVA FALHOU: % | recusado pelo motivo ERRADO: SQLSTATE % (esperado %) | %',
        rotulo, estado, sqlstate_esperado, left(erro, 140);
    END IF;
    IF coalesce(nome_constraint, '') <> '' THEN
      IF nome_constraint <> alvo_esperado THEN
        RAISE EXCEPTION 'PROVA FALHOU: % | violou a constraint % — esperava %', rotulo, nome_constraint, alvo_esperado;
      END IF;
    ELSIF position(alvo_esperado IN erro) = 0 THEN
      RAISE EXCEPTION 'PROVA FALHOU: % | a recusa nao cita % | %', rotulo, alvo_esperado, left(erro, 140);
    END IF;
    RAISE NOTICE 'PROVA ok: % | % %', rotulo, estado, coalesce(nullif(nome_constraint, ''), '~ ' || alvo_esperado);
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
  RAISE EXCEPTION 'PROVA FALHOU: % | o banco RECUSOU o que deveria aceitar: %', rotulo, replace(SQLERRM, E'\n', ' ');
END $$;

CREATE FUNCTION _prova_igual(rotulo text, consulta text, esperado text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE obtido text;
BEGIN
  EXECUTE consulta INTO obtido;
  IF obtido IS DISTINCT FROM esperado THEN
    RAISE EXCEPTION 'PROVA FALHOU: % | esperado <%>, obtido <%>', rotulo, esperado, coalesce(obtido, 'NULL');
  END IF;
  RAISE NOTICE 'PROVA ok: % | %', rotulo, esperado;
END $$;

-- Acesso NEGATIVO de verdade: troca de papel e TENTA. Inspecionar catalogo
-- provaria que o GRANT nao esta la; so SET ROLE prova que a operacao falha.
-- `WHEN insufficient_privilege` e a unica clausula capturada, entao erro de
-- sintaxe no comando sobe e derruba a prova — que e o comportamento certo.
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
  RAISE NOTICE 'PROVA ok: % [%] | %', rotulo, papel, left(erro, 100);
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

-- Constantes das provas. `_SEGREDO` e o texto que NUNCA pode reaparecer.
CREATE TABLE _ctx (chave text PRIMARY KEY, valor text);
INSERT INTO _ctx VALUES
  ('autor',    '00000000-0000-0000-0000-000000000001'),
  ('email',    'prova@agenciavolc.com.br'),
  ('locator',  'op://VOLC/Pagina%20Piloto/credential'),
  ('segredo',  'Tr0ub4dor&3-NUNCA-PODE-VAZAR');


-- ===========================================================================
-- BLOCO 1 — ESTRUTURA: a gaveta e integridade referencial, nao CHECK duplicada
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_igual('as 7 gavetas existem',
    $q$SELECT count(*)::text FROM public.cofre_gaveta$q$, '7');
  PERFORM _prova_igual('os 28 tipos existem (27 do contrato + browser_profile)',
    $q$SELECT count(*)::text FROM public.cofre_tipo$q$, '28');
  PERFORM _prova_igual('nenhum tipo em duas gavetas',
    $q$SELECT count(*)::text FROM (SELECT kind FROM public.cofre_tipo GROUP BY kind HAVING count(*) > 1) d$q$, '0');

  -- O par (kind, cluster) e FK. Classificar uma pagina do Facebook como midia
  -- paga nao e "recusado": e inexprimivel, porque o par nao existe no catalogo.
  PERFORM _prova_recusa(
    'facebook_page na gaveta errada (paid_media)',
    $q$INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade,
         resumo, dono_nome, dono_custodia, capacidades, proxima_acao)
       VALUES ('asset:erro:gaveta','facebook_page','paid_media','Pagina de prova','Meta','declared','low',
               'resumo suficientemente longo para a check','V','declared',ARRAY['a'],'acao suficientemente longa')$q$,
    '23503', 'cofre_ativo_gaveta_coerente');
END $bloco$;


-- ===========================================================================
-- BLOCO 2 — SEGURANCA sob papel real
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_recusa_como('anon nao le cofre_ativo', 'anon',
    $q$SELECT * FROM public.cofre_ativo$q$);
  PERFORM _prova_recusa_como('authenticated nao le cofre_ativo', 'authenticated',
    $q$SELECT * FROM public.cofre_ativo$q$);
  PERFORM _prova_recusa_como('anon nao le a view de inventario', 'anon',
    $q$SELECT * FROM public.cofre_inventario$q$);

  -- service_role tem BYPASSRLS. Se a contencao dependesse de RLS, esta prova
  -- falharia — e o fato de ela passar e que mostra que o REVOKE nominal e a
  -- trava que importa.
  PERFORM _prova_recusa_como('service_role NAO escreve direto na tabela', 'service_role',
    $q$INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade,
         resumo, dono_nome, dono_custodia, capacidades, proxima_acao)
       VALUES ('asset:direto:1','domain','web_properties','Dominio de prova','Registro','declared','low',
               'resumo suficientemente longo para a check','V','declared',ARRAY['a'],'acao suficientemente longa')$q$);
  PERFORM _prova_recusa_como('service_role NAO le a tabela de referencias', 'service_role',
    $q$SELECT * FROM public.cofre_credencial_referencia$q$);
  PERFORM _prova_recusa_como('service_role NAO le a trilha de operacoes', 'service_role',
    $q$SELECT * FROM public.cofre_operacao$q$);

  PERFORM _prova_recusa_como('anon nao executa a API governada', 'anon',
    $q$SELECT public.cofre_listar_ativos()$q$);
  PERFORM _prova_recusa_como('authenticated nao executa a API governada', 'authenticated',
    $q$SELECT public.cofre_listar_ativos()$q$);
  PERFORM _prova_recusa_como('authenticated nao cadastra ativo', 'authenticated',
    $q$SELECT public.cofre_cadastrar_ativo('{}'::jsonb,'chave-teste-0001','00000000-0000-0000-0000-000000000001'::uuid,'x@y.z')$q$);

  -- Nenhuma funcao INTERNA e chamavel de fora, nem por service_role.
  PERFORM _prova_recusa_como('service_role nao chama o construtor de snapshot', 'service_role',
    $q$SELECT public.cofre_snapshot_ativo('x')$q$);
  PERFORM _prova_recusa_como('service_role nao grava recibo direto', 'service_role',
    $q$SELECT public.cofre_registra_operacao('chave-teste-0002','r','0000000000000000000000000000000000000000000000000000000000000000','{}'::jsonb,'00000000-0000-0000-0000-000000000001'::uuid,'x@y.z')$q$);

  PERFORM _prova_igual('zero policy em cofre_*',
    $q$SELECT count(*)::text FROM pg_policies WHERE schemaname='public' AND tablename LIKE 'cofre\_%'$q$, '0');
  PERFORM _prova_igual('zero grant de tabela para anon/authenticated',
    $q$SELECT count(*)::text FROM information_schema.role_table_grants
        WHERE table_schema='public' AND table_name LIKE 'cofre\_%' AND grantee IN ('anon','authenticated','PUBLIC')$q$, '0');
  PERFORM _prova_igual('RLS forcada nas 9 tabelas',
    $q$SELECT count(*)::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'cofre\_%'
          AND c.relrowsecurity AND c.relforcerowsecurity$q$, '9');
  -- "DELETE a ninguem" quer dizer a nenhum papel do Data API. O DONO sempre
  -- retem DELETE — e como o rollback e o TRUNCATE existem. Afirmar zero
  -- absoluto seria afirmar algo falso e desistir da afirmacao util.
  PERFORM _prova_igual('DELETE nao foi concedido a nenhum papel do Data API',
    $q$SELECT count(*)::text FROM information_schema.role_table_grants
        WHERE table_schema='public' AND table_name LIKE 'cofre\_%'
          AND privilege_type='DELETE'
          AND grantee IN ('anon','authenticated','service_role','PUBLIC')$q$, '0');
  PERFORM _prova_igual('service_role nao tem privilegio NENHUM de tabela',
    $q$SELECT count(*)::text FROM information_schema.role_table_grants
        WHERE table_schema='public' AND table_name LIKE 'cofre\_%' AND grantee='service_role'$q$, '0');
END $bloco$;
PROVAS

cat >> "${BASE}/provas.sql" <<'PROVAS'

-- ===========================================================================
-- BLOCO 3 — CONTRAPROVAS: campo sensivel simples, aninhado, alias, desconhecido
-- ===========================================================================
-- Estas sao as provas que o contrato publico pedia e que ate agora so existiam
-- no frontend. Cada uma tenta um caminho diferente de fazer segredo entrar.
DO $bloco$
DECLARE
  autor uuid := (SELECT valor FROM _ctx WHERE chave='autor')::uuid;
  email text := (SELECT valor FROM _ctx WHERE chave='email');
BEGIN
  -- (a) SIMPLES, no topo: cai na allowlist, antes de qualquer outra coisa.
  PERFORM _prova_recusa('campo sensivel simples no topo (password)',
    format($q$SELECT public.cofre_cadastrar_ativo('{"ativo_id":"asset:x:1","password":"x"}'::jsonb,'chave-sens-0001',%L::uuid,%L)$q$, autor, email),
    '22023', 'nao conhece');

  -- (b) ANINHADO dentro de campo PERMITIDO: a allowlist nao ve; a varredura ve.
  PERFORM _prova_recusa('campo sensivel ANINHADO em campo permitido',
    format($q$SELECT public.cofre_cadastrar_ativo('{"ativo_id":"asset:x:1","tags":[{"meta":{"password":"x"}}]}'::jsonb,'chave-sens-0002',%L::uuid,%L)$q$, autor, email),
    '23001', 'campo proibido no Cofre');

  -- (c) ALIAS camelCase: `accessToken` normaliza para `accesstoken`.
  PERFORM _prova_recusa('alias camelCase (accessToken)',
    format($q$SELECT public.cofre_cadastrar_ativo('{"ativo_id":"asset:x:1","tags":[{"accessToken":"x"}]}'::jsonb,'chave-sens-0003',%L::uuid,%L)$q$, autor, email),
    '23001', 'accessToken');

  -- (d) ALIAS com separador diferente: `ACCESS-TOKEN` normaliza igual.
  PERFORM _prova_recusa('alias com hifen e maiuscula (ACCESS-TOKEN)',
    format($q$SELECT public.cofre_cadastrar_ativo('{"ativo_id":"asset:x:1","tags":[{"ACCESS-TOKEN":"x"}]}'::jsonb,'chave-sens-0004',%L::uuid,%L)$q$, autor, email),
    '23001', 'ACCESS-TOKEN');

  -- (e) ALIAS em portugues.
  PERFORM _prova_recusa('alias em portugues (codigo_recuperacao)',
    format($q$SELECT public.cofre_cadastrar_ativo('{"ativo_id":"asset:x:1","tags":[{"codigo_recuperacao":"x"}]}'::jsonb,'chave-sens-0005',%L::uuid,%L)$q$, autor, email),
    '23001', 'codigo_recuperacao');

  -- (f) DENTRO DE ARRAY, dois niveis abaixo — o esconderijo classico.
  PERFORM _prova_recusa('campo sensivel dentro de array aninhado',
    format($q$SELECT public.cofre_cadastrar_ativo('{"ativo_id":"asset:x:1","capacidades":[{"extras":[{"private_key":"x"}]}]}'::jsonb,'chave-sens-0006',%L::uuid,%L)$q$, autor, email),
    '23001', 'campo proibido no Cofre');

  -- (g) PAYLOAD DESCONHECIDO: campo novo e recusado, nao ignorado em silencio.
  PERFORM _prova_recusa('campo desconhecido no payload',
    format($q$SELECT public.cofre_cadastrar_ativo('{"ativo_id":"asset:x:1","campo_que_ninguem_declarou":1}'::jsonb,'chave-sens-0007',%L::uuid,%L)$q$, autor, email),
    '22023', 'nao conhece');

  -- (h) `localizador` viajando dentro de um ativo comum: proibido fora da
  --     unica porta que o aceita.
  PERFORM _prova_recusa('localizador tentando entrar por cofre_cadastrar_ativo',
    format($q$SELECT public.cofre_cadastrar_ativo('{"ativo_id":"asset:x:1","tags":[{"localizador":"op://a/b/c"}]}'::jsonb,'chave-sens-0008',%L::uuid,%L)$q$, autor, email),
    '23001', 'localizador');
END $bloco$;


-- ===========================================================================
-- BLOCO 4 — O CAMINHO FELIZ, e o que ele grava
-- ===========================================================================
DO $bloco$
DECLARE
  autor   uuid := (SELECT valor FROM _ctx WHERE chave='autor')::uuid;
  email   text := (SELECT valor FROM _ctx WHERE chave='email');
  locator text := (SELECT valor FROM _ctx WHERE chave='locator');
BEGIN
  PERFORM _prova_aceita_como('service_role cadastra ativo pela funcao governada', 'service_role',
    format($q$SELECT public.cofre_cadastrar_ativo(jsonb_build_object(
      'ativo_id','asset:facebook-page:piloto','kind','facebook_page','cluster','social_presence',
      'nome','Pagina monetizada do piloto','plataforma','Meta','estado','declared','criticidade','high',
      'resumo','Pagina declarada pelo dono, sem identidade tecnica conferida no VOLC.',
      'dono_nome','Tarcisio','dono_custodia','declared',
      'capacidades', jsonb_build_array('Publicacao organica','Distribuicao de video'),
      'tags', jsonb_build_array('piloto','meta'),
      'proxima_acao','Conferir ID da pagina, Business Portfolio e administradores.'),
      'chave-cadastro-0001',%L::uuid,%L)$q$, autor, email));

  PERFORM _prova_igual('o ativo existe com revisao 1',
    $q$SELECT revisao_atual::text FROM public.cofre_ativo WHERE ativo_id='asset:facebook-page:piloto'$q$, '1');
  PERFORM _prova_igual('a revisao 1 foi gravada na trilha',
    $q$SELECT operacao FROM public.cofre_ativo_revisao WHERE ativo_id='asset:facebook-page:piloto' AND revisao=1$q$, 'cadastro');

  -- Referencia de credencial: forma valida entra.
  PERFORM _prova_aceita_como('referencia 1Password bem formada entra', 'service_role',
    format($q$SELECT public.cofre_referenciar_credencial(jsonb_build_object(
      'ativo_id','asset:facebook-page:piloto','provider','1password','nome_logico','FB_PAGE_ADMIN',
      'localizador',%L,'finalidade','Acesso administrativo a pagina do piloto organico',
      'owner_nome','Tarcisio'), 'chave-credencial-0001',%L::uuid,%L)$q$, locator, autor, email));

  PERFORM _prova_igual('a referencia esta registrada',
    $q$SELECT count(*)::text FROM public.cofre_credencial_referencia WHERE ativo_id='asset:facebook-page:piloto'$q$, '1');
END $bloco$;


-- ===========================================================================
-- BLOCO 5 — A FRONTEIRA DO SEGREDO
-- ===========================================================================
DO $bloco$
DECLARE
  autor   uuid := (SELECT valor FROM _ctx WHERE chave='autor')::uuid;
  email   text := (SELECT valor FROM _ctx WHERE chave='email');
  segredo text := (SELECT valor FROM _ctx WHERE chave='segredo');
  locator text := (SELECT valor FROM _ctx WHERE chave='locator');
  saida   text;
BEGIN
  -- (a) Senha bruta no campo de localizador: recusada pela GRAMATICA.
  PERFORM _prova_recusa('senha bruta no localizador',
    format($q$SELECT public.cofre_referenciar_credencial(jsonb_build_object(
      'ativo_id','asset:facebook-page:piloto','provider','1password','nome_logico','X_TOKEN',
      'localizador',%L,'finalidade','tentativa','owner_nome','V'),'chave-senha-0001',%L::uuid,%L)$q$, segredo, autor, email),
    '22023', 'forma esperada');

  -- (b) ⚠️ E A RECUSA NAO PODE ECOAR O QUE RECUSOU.
  --     Defeito medido em 01/09/2026: a violacao de CHECK anexa
  --     `DETAIL: Failing row contains (…)` com a LINHA INTEIRA — a senha
  --     recusada aparecia no log do servidor e no corpo do erro do PostgREST.
  --     Esta prova e a que impede o defeito de voltar.
  BEGIN
    PERFORM public.cofre_referenciar_credencial(jsonb_build_object(
      'ativo_id','asset:facebook-page:piloto','provider','1password','nome_logico','X_TOKEN',
      'localizador',segredo,'finalidade','tentativa','owner_nome','V'),'chave-senha-0002',autor,email);
    RAISE EXCEPTION 'PROVA FALHOU: a senha bruta foi ACEITA no localizador';
  EXCEPTION WHEN invalid_parameter_value THEN
    saida := SQLERRM;
    IF position(segredo IN saida) > 0 THEN
      RAISE EXCEPTION 'PROVA FALHOU: a mensagem de recusa ECOA o valor recusado';
    END IF;
    RAISE NOTICE 'PROVA ok: a recusa nao repete o valor | %', left(replace(saida, E'\n',' '), 110);
  END;

  -- (c) JWT e PEM em campo de prosa.
  --     ⚠️ O JWT abaixo e o exemplo PUBLICO de jwt.io, SEM assinatura:
  --     header {"alg":"HS256","typ":"JWT"} e payload {"sub":"1234567890"}. Ele
  --     nao autentica nada e nunca autenticou. Esta aqui porque provar que o
  --     detector reconhece o formato exige um texto com o formato — e o unico
  --     token seguro de versionar e um que ja e publico e nao vale nada.
  PERFORM _prova_recusa('JWT colado no resumo do ativo',
    $q$INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade,
        resumo, dono_nome, dono_custodia, capacidades, proxima_acao)
       VALUES ('asset:jwt:1','domain','web_properties','Dominio de prova','Registro','declared','low',
               'chave eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0 anexada','V','declared',
               ARRAY['a'],'acao suficientemente longa')$q$,
    '23514', 'cofre_ativo_prosa_limpa');

  PERFORM _prova_recusa('chave PEM colada na proxima acao',
    $q$INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade,
        resumo, dono_nome, dono_custodia, capacidades, proxima_acao)
       VALUES ('asset:pem:1','domain','web_properties','Dominio de prova','Registro','declared','low',
               'resumo suficientemente longo para a check','V','declared',ARRAY['a'],
               '-----BEGIN RSA PRIVATE KEY----- MIIEow')$q$,
    '23514', 'cofre_ativo_prosa_limpa');

  -- (d) op:// com query string: recusado de proposito (aponta para MFA).
  PERFORM _prova_recusa('referencia op:// com ?attribute=otp',
    format($q$SELECT public.cofre_referenciar_credencial(jsonb_build_object(
      'ativo_id','asset:facebook-page:piloto','provider','1password','nome_logico','X_OTP',
      'localizador','op://VOLC/Item/campo?attribute=otp','finalidade','tentativa','owner_nome','V'),
      'chave-otp-0001',%L::uuid,%L)$q$, autor, email),
    '22023', 'forma esperada');

  -- (e) ⚠️ A PROVA CENTRAL: NENHUMA funcao concedida a service_role devolve o
  --     localizador. Nao e inspecao de catalogo — e chamar cada uma delas e
  --     procurar a string no texto da resposta.
  SELECT string_agg(t, ' ') INTO saida FROM (
    SELECT public.cofre_listar_ativos()::text                                       AS t
    UNION ALL SELECT public.cofre_listar_ativos(NULL,NULL,NULL,NULL,true)::text
    UNION ALL SELECT public.cofre_detalhar_ativo('asset:facebook-page:piloto')::text
    UNION ALL SELECT public.cofre_postura_credencial('asset:facebook-page:piloto')::text
    UNION ALL SELECT public.cofre_engines_disponiveis()::text
    UNION ALL SELECT coalesce((SELECT string_agg(snapshot::text,' ') FROM public.cofre_ativo_revisao), '')
    UNION ALL SELECT coalesce((SELECT string_agg(resultado::text,' ') FROM public.cofre_operacao), '')
    UNION ALL SELECT coalesce((SELECT string_agg(motivo,' ') FROM public.cofre_ativo_revisao), '')
  ) s;

  IF position(locator IN saida) > 0 THEN
    RAISE EXCEPTION 'PROVA FALHOU: o localizador VAZOU pela superficie de leitura';
  END IF;
  IF position('op://' IN saida) > 0 THEN
    RAISE EXCEPTION 'PROVA FALHOU: uma secret reference apareceu na superficie de leitura';
  END IF;
  RAISE NOTICE 'PROVA ok: nenhuma funcao, snapshot, recibo ou motivo contem o localizador (% bytes varridos)', length(saida);

  -- E a postura CONTINUA util sem ele: provider, nome logico e estado saem.
  PERFORM _prova_igual('a postura publica o provider sem o endereco',
    $q$SELECT public.cofre_postura_credencial('asset:facebook-page:piloto')->0->>'provider'$q$, '1password');
  PERFORM _prova_igual('a postura publica o nome logico',
    $q$SELECT public.cofre_postura_credencial('asset:facebook-page:piloto')->0->>'nome_logico'$q$, 'FB_PAGE_ADMIN');
  PERFORM _prova_igual('a postura NAO tem chave localizador',
    $q$SELECT (public.cofre_postura_credencial('asset:facebook-page:piloto')->0 ? 'localizador')::text$q$, 'false');
END $bloco$;
PROVAS

cat >> "${BASE}/provas.sql" <<'PROVAS'

-- ===========================================================================
-- BLOCO 6 — COMPORTAMENTO: idempotencia, append-only, aposentadoria, ausencia
-- ===========================================================================
DO $bloco$
DECLARE
  autor    uuid := (SELECT valor FROM _ctx WHERE chave='autor')::uuid;
  email    text := (SELECT valor FROM _ctx WHERE chave='email');
  primeiro jsonb;
  segundo  jsonb;
BEGIN
  -- IDEMPOTENCIA — replay devolve o MESMO recibo, marcado.
  primeiro := public.cofre_revisar_ativo('asset:facebook-page:piloto',
    '{"estado":"verified"}'::jsonb, 'chave-revisao-0001', autor, email, 'conferido no Business Portfolio');
  segundo  := public.cofre_revisar_ativo('asset:facebook-page:piloto',
    '{"estado":"verified"}'::jsonb, 'chave-revisao-0001', autor, email, 'conferido no Business Portfolio');

  IF (primeiro->>'revisao') IS DISTINCT FROM (segundo->>'revisao') THEN
    RAISE EXCEPTION 'PROVA FALHOU: o replay produziu revisao diferente (% vs %)',
      primeiro->>'revisao', segundo->>'revisao';
  END IF;
  IF (primeiro->>'idempotente') <> 'false' OR (segundo->>'idempotente') <> 'true' THEN
    RAISE EXCEPTION 'PROVA FALHOU: o recibo nao distingue primeira execucao de replay';
  END IF;
  RAISE NOTICE 'PROVA ok: replay devolve o mesmo recibo, marcado idempotente';

  PERFORM _prova_igual('o retry NAO criou uma segunda revisao',
    $q$SELECT count(*)::text FROM public.cofre_ativo_revisao
        WHERE ativo_id='asset:facebook-page:piloto' AND operacao='revisao'$q$, '1');

  -- O ramo que quase sempre falta: MESMA chave, entrada DIFERENTE.
  PERFORM _prova_recusa('mesma chave de idempotencia com entrada diferente',
    format($q$SELECT public.cofre_revisar_ativo('asset:facebook-page:piloto','{"estado":"active"}'::jsonb,'chave-revisao-0001',%L::uuid,%L,'outra coisa')$q$, autor, email),
    '23505', 'ja foi usada por outra operacao');

  -- APPEND-ONLY nas tres trilhas.
  PERFORM _prova_recusa('UPDATE na trilha de revisoes',
    $q$UPDATE public.cofre_ativo_revisao SET motivo='reescrito' WHERE revisao=1$q$,
    '23001', 'append-only');
  PERFORM _prova_recusa('DELETE na trilha de revisoes',
    $q$DELETE FROM public.cofre_ativo_revisao WHERE revisao=1$q$,
    '23001', 'append-only');
  PERFORM _prova_recusa('UPDATE na trilha de operacoes',
    $q$UPDATE public.cofre_operacao SET rota='outra' WHERE operacao_id=1$q$,
    '23001', 'append-only');

  -- AUSENCIA E NULL, NUNCA ZERO.
  PERFORM _prova_recusa('engine com zero formatos (contagem inventada)',
    $q$INSERT INTO public.cofre_engine_perfil (ativo_id, modalidade, estado_operacional, formatos,
         manifesto_fonte, capacidades_observadas, limitacoes)
       VALUES ('asset:facebook-page:piloto','imagem','catalogado',0,'docs/x.json',ARRAY[]::text[],ARRAY[]::text[])$q$,
    '23514', 'cofre_engine_formatos_positivos');

  PERFORM _prova_aceita('engine com formatos NULL (o manifesto nao declara)',
    $q$INSERT INTO public.cofre_engine_perfil (ativo_id, modalidade, estado_operacional, formatos,
         manifesto_fonte, capacidades_observadas, limitacoes)
       VALUES ('asset:facebook-page:piloto','imagem','catalogado',NULL,'docs/x.json',ARRAY[]::text[],ARRAY[]::text[])$q$);
  PERFORM _prova_aceita('limpando o perfil de engine da prova',
    $q$DELETE FROM public.cofre_engine_perfil WHERE ativo_id='asset:facebook-page:piloto'$q$);

  -- NENHUMA VERIFICACAO SEM CARIMBO.
  PERFORM _prova_recusa('credencial diz verified sem instante',
    $q$UPDATE public.cofre_credencial_referencia SET verificacao_estado='verified', verificado_em=NULL$q$,
    '23514', 'cofre_credencial_verificacao_sem_carimbo');
  PERFORM _prova_recusa('verificacao datada no futuro',
    $q$INSERT INTO public.cofre_verificacao (ativo_id, alvo, resultado, metodo, procedencia, evidencia,
         observado_em, autor_sub, autor_email)
       VALUES ('asset:facebook-page:piloto','ativo','verified','manual','owner_declaration',
               'evidencia suficientemente longa', now() + interval '2 days',
               '00000000-0000-0000-0000-000000000001'::uuid,'x@y.z')$q$,
    '23514', 'cofre_verificacao_nao_futura');

  -- RELACOES.
  PERFORM _prova_recusa('relacao de um ativo consigo mesmo',
    $q$INSERT INTO public.cofre_relacao (origem_id, tipo, destino_id, destino_rotulo, estado, declarada_por)
       VALUES ('asset:facebook-page:piloto','depends_on','asset:facebook-page:piloto','X','declared','prova')$q$,
    '23514', 'cofre_relacao_sem_laco');
  -- ⚠️ `destino_id` diferente da origem DE PROPOSITO: com o mesmo id, a CHECK de
  -- laco dispara primeiro e a prova mediria a trava errada. CHECK e avaliada no
  -- insert da tupla e a FK e gatilho AFTER, entao `um_destino` vence a FK aqui.
  PERFORM _prova_recusa('relacao com destino interno E externo',
    $q$INSERT INTO public.cofre_relacao (origem_id, tipo, destino_id, destino_externo, destino_rotulo, estado, declarada_por)
       VALUES ('asset:facebook-page:piloto','depends_on','asset:outro:qualquer','concept:x','X','declared','prova')$q$,
    '23514', 'cofre_relacao_um_destino');
  PERFORM _prova_recusa('relacao sem destino nenhum',
    $q$INSERT INTO public.cofre_relacao (origem_id, tipo, destino_rotulo, estado, declarada_por)
       VALUES ('asset:facebook-page:piloto','depends_on','X','declared','prova')$q$,
    '23514', 'cofre_relacao_um_destino');

  PERFORM _prova_aceita_como('relacao para alvo externo entra', 'service_role',
    format($q$SELECT public.cofre_relacionar(jsonb_build_object(
      'origem_id','asset:facebook-page:piloto','tipo','produces_for',
      'destino_externo','cap:organic-content','destino_rotulo','Operacao de conteudo organico'),
      'chave-relacao-0001',%L::uuid,%L)$q$, autor, email));

  PERFORM _prova_recusa('a MESMA relacao ativa duas vezes',
    $q$INSERT INTO public.cofre_relacao (origem_id, tipo, destino_externo, destino_rotulo, estado, declarada_por)
       VALUES ('asset:facebook-page:piloto','produces_for','cap:organic-content','X','declared','prova')$q$,
    '23505', 'cofre_relacao_ativa_unica');

  -- APOSENTADORIA REVERSIVEL, sem DELETE.
  PERFORM _prova_aceita_como('aposentar o ativo', 'service_role',
    format($q$SELECT public.cofre_aposentar_ativo('asset:facebook-page:piloto',
      'piloto encerrado; a pagina sai de operacao sem sair do inventario','chave-aposenta-0001',%L::uuid,%L)$q$, autor, email));
  PERFORM _prova_igual('o ativo continua existindo, aposentado',
    $q$SELECT estado FROM public.cofre_ativo WHERE ativo_id='asset:facebook-page:piloto'$q$, 'retired');
  PERFORM _prova_igual('aposentado sai da listagem padrao',
    $q$SELECT jsonb_array_length(public.cofre_listar_ativos()->'ativos')::text$q$, '0');
  PERFORM _prova_igual('e aparece quando pedido explicitamente',
    $q$SELECT jsonb_array_length(public.cofre_listar_ativos(NULL,NULL,NULL,NULL,true)->'ativos')::text$q$, '1');

  PERFORM _prova_aceita_como('reativar o ativo', 'service_role',
    format($q$SELECT public.cofre_reativar_ativo('asset:facebook-page:piloto','active',
      'piloto retomado apos decisao do dono','chave-reativa-0001',%L::uuid,%L)$q$, autor, email));
  PERFORM _prova_igual('o ativo voltou',
    $q$SELECT estado FROM public.cofre_ativo WHERE ativo_id='asset:facebook-page:piloto'$q$, 'active');
  PERFORM _prova_igual('a trilha guardou aposentadoria E reativacao',
    $q$SELECT count(*)::text FROM public.cofre_ativo_revisao
        WHERE ativo_id='asset:facebook-page:piloto' AND operacao IN ('aposentadoria','reativacao')$q$, '2');

  -- AS SETE GAVETAS VIAJAM SEMPRE.
  PERFORM _prova_igual('a listagem devolve as 7 gavetas',
    $q$SELECT jsonb_array_length(public.cofre_listar_ativos()->'gavetas')::text$q$, '7');
  PERFORM _prova_igual('gaveta vazia vem com contagem zero, nao some',
    $q$SELECT (SELECT g->>'total' FROM jsonb_array_elements(public.cofre_listar_ativos()->'gavetas') g
               WHERE g->>'cluster'='infrastructure')$q$, '0');

  -- FALHA DE ATIVO INEXISTENTE E ERRO, NAO SILENCIO.
  PERFORM _prova_recusa('revisar ativo que nao existe',
    format($q$SELECT public.cofre_revisar_ativo('asset:nao:existe','{"estado":"active"}'::jsonb,'chave-fantasma-01',%L::uuid,%L,'motivo qualquer')$q$, autor, email),
    'P0002', 'nao existe no Cofre');
END $bloco$;

SELECT 'PROVAS CONCLUIDAS' AS fim;
PROVAS

set +e
aplicar "${BASE}/provas.sql" > "${BASE}/provas.out" 2>&1
CODIGO=$?
set -e

sed -E 's/^psql:[^ ]+: //; s/^NOTICE:  /  /' "${BASE}/provas.out" | grep -E '^( +PROVA|ERROR|FATAL)' || true
APROVADAS=$(grep -c 'PROVA ok' "${BASE}/provas.out" || true)
if [[ $CODIGO -ne 0 ]]; then
  echo; echo "✗ PROVAS FALHARAM (${APROVADAS} passaram antes da falha)" >&2
  exit 1
fi
echo "  ✓ ${APROVADAS} provas passaram"

# ---------------------------------------------------------------------------
# 4. DEGRAU 3 — reverter
# ---------------------------------------------------------------------------
echo; echo "DEGRAU 3 — reverter"
aplicar "$ROLLBACK" 2>&1 | sed 's/^NOTICE:  /  /'
executar >/dev/null <<'SQL'
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
   WHERE ns.nspname='public' AND c.relname LIKE 'cofre\_%';
  IF n <> 0 THEN RAISE EXCEPTION 'o rollback deixou % objeto(s) cofre_ de pe', n; END IF;
END $$;
SQL
echo "  ✓ nada com prefixo cofre_ restou"

# ---------------------------------------------------------------------------
# 5. DEGRAU 4 — reaplicar sobre o banco revertido
# ---------------------------------------------------------------------------
echo; echo "DEGRAU 4 — reaplicar"
aplicar "$MIGRATION" >/dev/null 2>&1
echo "  ✓ reaplicavel depois do rollback"

echo "▶ conferindo que a migration recusa reaplicacao POR CIMA"
if aplicar "$MIGRATION" >/dev/null 2>&1; then
  echo "  ✗ a migration aceitou rodar duas vezes seguidas — a guarda nao funcionou" >&2
  exit 1
fi
echo "  ✓ recusada com as tabelas ja existentes"

echo
echo "════════════════════════════════════════════════════════════════"
echo " ${APROVADAS} provas · PostgreSQL ${VERSAO}"
echo " v13_01 aplicavel → operavel → reversivel → reaplicavel"
echo " cluster descartado. Nada foi tocado em producao."
echo "════════════════════════════════════════════════════════════════"
