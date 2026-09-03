#!/usr/bin/env bash
# =============================================================================
# provar-ciclo-v14_01.sh — o ciclo da Publicacao Organica num Postgres
# descartavel: aplicar -> operar -> reverter -> reaplicar, com as contraprovas
# de AUTORIZACAO, OWNERSHIP, IDEMPOTENCIA, CONCORRENCIA, TIMEZONE, ESTADOS
# AMBIGUOS e NAO-VAZAMENTO. NUNCA toca em producao.
# =============================================================================
#
# ORDEM DE APLICACAO
#
# A v14_01 depende de v11_01 (o ato de aprovar), v11_02 (as finalidades, onde
# `instagram_organic` e de classe `organica`) e v13_01 (o destino e as tres
# funcoes genericas). O harness aplica as tres antes — nao para "fazer passar",
# mas porque a dependencia e real e a guarda da secao 0 da v14_01 aborta com
# mensagem nomeada quando falta alguma. Aplicar so a v14_01 aqui provaria a
# guarda, e nao o dominio.
#
# ⚠️ PRODUCAO E POSTGRESQL 15.8. O Homebrew desta maquina traz 16, e o modo
# `--local` IMPRIME a divergencia em vez de escondê-la. Com Docker disponivel a
# prova roda em `postgres:15`, que e a mesma major da producao.
#
# COMO RODAR
#   ./scripts/provar-ciclo-v14_01.sh
#   ./scripts/provar-ciclo-v14_01.sh --local     # sem Docker, usa initdb do PATH
#   ./scripts/provar-ciclo-v14_01.sh --manter    # nao destroi o cluster (debug)
# =============================================================================
set -euo pipefail
export LC_ALL=C LANG=C

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIG_V11_01="${RAIZ}/supabase/migrations/v11_01_estudio_criativo.sql"
MIG_V11_02="${RAIZ}/supabase/migrations/v11_02_parque_criativo.sql"
MIG_V13_01="${RAIZ}/supabase/migrations/v13_01_cofre_de_ativos.sql"
MIGRATION="${RAIZ}/supabase/migrations/v14_01_publicacao_organica.sql"
ROLLBACK="${RAIZ}/supabase/migrations/v14_99_publicacao_organica_rollback.sql"
IMAGEM="postgres:15"

MANTER=0; LOCAL=0
for arg in "$@"; do
  case "$arg" in
    --manter) MANTER=1 ;;
    --local)  LOCAL=1 ;;
    *) echo "argumento desconhecido: $arg" >&2; exit 2 ;;
  esac
done

for arquivo in "$MIG_V11_01" "$MIG_V11_02" "$MIG_V13_01" "$MIGRATION" "$ROLLBACK"; do
  [[ -f "$arquivo" ]] || { echo "ERRO: arquivo ausente: $arquivo" >&2; exit 1; }
done

BASE="$(mktemp -d "${TMPDIR:-/tmp}/volc-organico-prova.XXXXXX")"
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
  vivo_ou_morra() {
    if ! docker inspect -f '{{.State.Running}}' "$CID" 2>/dev/null | grep -q true; then
      echo "ERRO: o container morreu antes de aceitar conexao. Log:" >&2
      docker logs "$CID" 2>&1 | tail -20 >&2
      exit 1
    fi
  }
  # A imagem oficial sobe um servidor TEMPORARIO durante o initdb. Um pg_isready
  # disparado nessa janela responde "pronto" e o primeiro psql cai no intervalo
  # entre os dois servidores. Por isso esperamos o marcador de fim de init antes
  # de aceitar a prontidao. (Cicatriz herdada de provar-ciclo-v13_01.sh.)
  INICIALIZOU=0
  for _ in $(seq 1 360); do
    if docker logs "$CID" 2>&1 | grep -qE 'PostgreSQL init process complete|Skipping initialization'; then
      INICIALIZOU=1; break
    fi
    vivo_ou_morra; sleep 0.5
  done
  [[ $INICIALIZOU -eq 1 ]] || { echo "ERRO: initdb da imagem nao terminou em 180s" >&2; docker logs "$CID" 2>&1 | tail -20 >&2; exit 1; }
  PRONTO=0
  for _ in $(seq 1 180); do
    if docker exec "$CID" psql -U postgres -X -q -t -A -c 'select 1' >/dev/null 2>&1; then PRONTO=1; break; fi
    vivo_ou_morra; sleep 0.5
  done
  [[ $PRONTO -eq 1 ]] || { echo "ERRO: Postgres nao aceitou conexao em 90s" >&2; docker logs "$CID" 2>&1 | tail -20 >&2; exit 1; }
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
  # ⚠️ `TimeZone=UTC` NAO e conveniencia: e o controle da contraprova K. Se a
  # conversao de horario local para instante dependesse do TZ do servidor, ela
  # daria certo aqui e errado na maquina de quem roda em America/Sao_Paulo. O
  # servidor em UTC e o cenario onde o erro APARECE.
  pg_ctl -D "$PGDATA" -l "${BASE}/postgres.log" -o "-k ${SOCK} -h '' -c TimeZone=UTC" -w start >/dev/null
  executar() { psql -X -q -h "$SOCK" -U postgres -d postgres -v ON_ERROR_STOP=1 "$@"; }
  aplicar()  { psql -X -q -h "$SOCK" -U postgres -d postgres -v ON_ERROR_STOP=1 -f "$1"; }
fi

VERSAO=$(executar -tA -c "SHOW server_version")
TZ_SERVIDOR=$(executar -tA -c "SHOW TimeZone")
echo "  ✓ servidor ${VERSAO} (TimeZone=${TZ_SERVIDOR})"

# ---------------------------------------------------------------------------
# 1. Reproduzir o Supabase — inclusive o default ACL aberto
# ---------------------------------------------------------------------------
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
echo "  ✓ default ACL aberto reproduzido"

# ---------------------------------------------------------------------------
# 2. Pre-requisitos reais
# ---------------------------------------------------------------------------
echo; echo "▶ pre-requisitos (v11_01, v11_02, v13_01)"
aplicar "$MIG_V11_01" >/dev/null 2>&1 || { echo "ERRO ao aplicar v11_01" >&2; aplicar "$MIG_V11_01"; exit 1; }
echo "  ✓ v11_01 (aprovacao e peca)"
aplicar "$MIG_V11_02" >/dev/null 2>&1 || { echo "ERRO ao aplicar v11_02" >&2; aplicar "$MIG_V11_02"; exit 1; }
echo "  ✓ v11_02 (finalidades organicas)"
aplicar "$MIG_V13_01" >/dev/null 2>&1 || { echo "ERRO ao aplicar v13_01" >&2; aplicar "$MIG_V13_01"; exit 1; }
echo "  ✓ v13_01 (cofre e funcoes genericas)"

# A guarda da v14_01 tem de ABORTAR quando falta dependencia. Provamos isso
# derrubando temporariamente uma das tres funcoes genericas — e devolvendo-a.
echo "▶ conferindo que a guarda da v14_01 recusa dependencia ausente"
executar >/dev/null <<'SQL'
CREATE TABLE public._backup_hash AS
  SELECT pg_get_functiondef('public.cofre_entrada_hash(text,jsonb,jsonb)'::regprocedure) AS def;
DROP FUNCTION public.cofre_entrada_hash(text,jsonb,jsonb) CASCADE;
SQL
if aplicar "$MIGRATION" >/dev/null 2>&1; then
  echo "  ✗ PROVA FALHOU: a v14_01 aplicou sem cofre_entrada_hash" >&2
  exit 1
fi
echo "  ✓ a v14_01 aborta quando cofre_entrada_hash falta"
# Recompoe o mundo: a v13_01 inteira, num banco limpo, e mais barato e mais
# honesto do que remendar a funcao e torcer para as dependencias voltarem.
executar >/dev/null <<'SQL'
DROP TABLE public._backup_hash;
SQL
aplicar "${RAIZ}/supabase/migrations/v13_99_cofre_de_ativos_rollback.sql" >/dev/null 2>&1 || true
aplicar "$MIG_V13_01" >/dev/null
echo "  ✓ v13_01 recomposta"

# ---------------------------------------------------------------------------
# 3. DEGRAU 1 — aplicar do zero
# ---------------------------------------------------------------------------
echo; echo "DEGRAU 1 — aplicar"
aplicar "$MIGRATION" 2>&1 | sed 's/^NOTICE:  /  /'
echo "  ✓ v14_01 aplicada"

echo "▶ reaplicar sobre si mesma deve ser RECUSADO"
if aplicar "$MIGRATION" >/dev/null 2>&1; then
  echo "  ✗ PROVA FALHOU: a v14_01 aceitou ser aplicada duas vezes" >&2
  exit 1
fi
echo "  ✓ segunda aplicacao recusada pela guarda"

# ---------------------------------------------------------------------------
# 4. DEGRAU 2 — operar, com as contraprovas
# ---------------------------------------------------------------------------
echo; echo "DEGRAU 2 — operar (contraprovas A–N)"
cat > "${BASE}/provas.sql" <<'PROVAS'
\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- AJUDANTES QUE NAO ACEITAM QUALQUER ERRO
-- ---------------------------------------------------------------------------
-- Copiados de scripts/provar-ciclo-v13_01.sh (mesma casa, mesma disciplina).
-- Um ajudante que capturasse `WHEN others` e declarasse "ok" para QUALQUER
-- excecao deixaria um erro de digitacao no proprio teste contar como prova.
-- Aqui o SQLSTATE e sempre conferido, e o ALVO tambem — nome da constraint
-- quando a excecao o carrega, trecho citado quando e RAISE de funcao.
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
        rotulo, estado, sqlstate_esperado, left(erro, 160);
    END IF;
    IF coalesce(nome_constraint, '') <> '' THEN
      IF nome_constraint <> alvo_esperado AND position(alvo_esperado IN erro) = 0 THEN
        RAISE EXCEPTION 'PROVA FALHOU: % | violou % — esperava %', rotulo, nome_constraint, alvo_esperado;
      END IF;
    ELSIF position(alvo_esperado IN erro) = 0 THEN
      RAISE EXCEPTION 'PROVA FALHOU: % | a recusa nao cita "%" | %', rotulo, alvo_esperado, left(erro, 160);
    END IF;
    RAISE NOTICE 'PROVA ok: % | % %', rotulo, estado, coalesce(nullif(nome_constraint, ''), '~ ' || alvo_esperado);
    RETURN;
  END;
  RAISE EXCEPTION 'PROVA FALHOU: % | o banco ACEITOU o que deveria recusar', rotulo;
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
  RAISE NOTICE 'PROVA ok: % [%] | %', rotulo, papel, left(erro, 90);
END $$;

-- ---------------------------------------------------------------------------
-- CENARIO — dois donos, uma peca aprovada cada, um destino apto e um inapto
-- ---------------------------------------------------------------------------
CREATE TABLE _ctx (chave text PRIMARY KEY, valor text);
INSERT INTO _ctx VALUES
  ('dono_a',  '11111111-1111-1111-1111-111111111111'),
  ('dono_b',  '22222222-2222-2222-2222-222222222222'),
  ('email_a', 'a@agenciavolc.com.br'),
  ('email_b', 'b@agenciavolc.com.br'),
  -- ⚠️ O texto que NUNCA pode reaparecer em recibo, snapshot ou mensagem.
  -- ⚠️ Montado por concatenacao no proprio SQL: um literal com forma de
  -- credencial neste arquivo reprovaria scripts/verificar_segredos.py, e a
  -- saida seria enfraquecer o scanner para acomodar a prova.
  ('segredo', 'xox' || 'b-0123456789abcdefghij');

DO $cenario$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  dono_b uuid := '22222222-2222-2222-2222-222222222222';
  proj_a uuid; proj_b uuid;
  brief_a uuid; brief_b uuid;
  job_a uuid; job_b uuid;
  master_a uuid; master_a_v2 uuid; master_b uuid;
BEGIN
  -- Dois ativos sociais no Cofre, pela funcao governada (nao por INSERT direto).
  PERFORM public.cofre_cadastrar_ativo(jsonb_build_object(
    'ativo_id','asset:facebook-page:piloto','kind','facebook_page','cluster','social_presence',
    'nome','Pagina Piloto','plataforma','Facebook','estado','active','criticidade','high',
    'resumo','Pagina monetizada usada no piloto organico do VOLC O.S.',
    'dono_nome','VOLC','dono_custodia','declared','proxima_acao','Ligar a porta de publicacao organica.',
    'capacidades', '["publicar"]'::jsonb),
    'prova-cofre-fb-piloto-0001', dono_a, 'a@agenciavolc.com.br');

  PERFORM public.cofre_cadastrar_ativo(jsonb_build_object(
    'ativo_id','asset:instagram-profile:sem-adapter','kind','instagram_profile','cluster','social_presence',
    'nome','Perfil sem adapter','plataforma','Instagram','estado','declared','criticidade','medium',
    'resumo','Perfil inventariado que ainda nao tem integracao no control plane.',
    'dono_nome','VOLC','dono_custodia','declared','proxima_acao','Conectar a integracao no control plane.',
    'capacidades', '["publicar"]'::jsonb),
    'prova-cofre-ig-sem-adapter-01', dono_a, 'a@agenciavolc.com.br');

  -- Peca do dono A, versao 1 e versao 2 (a v2 nasce DEPOIS da aprovacao da v1).
  INSERT INTO public.criativo_projeto (titulo, dono_id) VALUES ('Projeto A', dono_a) RETURNING id INTO proj_a;
  INSERT INTO public.criativo_briefing (projeto_id, tipo, modo, formatos_pedidos)
    VALUES (proj_a, 'imagem', 'full_llm', '[{"slot":"1x1"}]'::jsonb) RETURNING id INTO brief_a;
  -- ⚠️ `succeeded` e obrigatorio: `criativo_aprovacao_exige_peca_pronta`
  -- (v11_01) recusa aprovar peca de job em draft/queued/cancelled/failed.
  INSERT INTO public.criativo_job (briefing_id, motor, motor_versao, idempotency_key, insumo_hash, criado_por, estado, iniciado_em, terminado_em)
    VALUES (brief_a, 'prova', '1', 'prova-job-a-0000000000000001', 'h', dono_a, 'succeeded', now() - interval '1 hour', now()) RETURNING id INTO job_a;
  INSERT INTO public.criativo_master
    (job_id, projeto_id, slot, kind, storage_chave, content_hash, mime, motor, motor_versao, insumo_hash, versao)
    VALUES (job_a, proj_a, '1x1', 'imagem', 'criativos/prova/a-v1.png',
            'sha256:' || repeat('a', 64), 'image/png', 'prova', '1', 'h', 1)
    RETURNING id INTO master_a;
  INSERT INTO public.criativo_master
    (job_id, projeto_id, slot, kind, storage_chave, content_hash, mime, motor, motor_versao, insumo_hash, versao, raiz_id)
    VALUES (job_a, proj_a, '1x1', 'imagem', 'criativos/prova/a-v2.png',
            'sha256:' || repeat('b', 64), 'image/png', 'prova', '1', 'h', 2, master_a)
    RETURNING id INTO master_a_v2;

  -- Peca do dono B.
  INSERT INTO public.criativo_projeto (titulo, dono_id) VALUES ('Projeto B', dono_b) RETURNING id INTO proj_b;
  INSERT INTO public.criativo_briefing (projeto_id, tipo, modo, formatos_pedidos)
    VALUES (proj_b, 'imagem', 'full_llm', '[{"slot":"1x1"}]'::jsonb) RETURNING id INTO brief_b;
  INSERT INTO public.criativo_job (briefing_id, motor, motor_versao, idempotency_key, insumo_hash, criado_por, estado, iniciado_em, terminado_em)
    VALUES (brief_b, 'prova', '1', 'prova-job-b-0000000000000001', 'h', dono_b, 'succeeded', now() - interval '1 hour', now()) RETURNING id INTO job_b;
  INSERT INTO public.criativo_master
    (job_id, projeto_id, slot, kind, storage_chave, content_hash, mime, motor, motor_versao, insumo_hash, versao)
    VALUES (job_b, proj_b, '1x1', 'imagem', 'criativos/prova/b-v1.png',
            'sha256:' || repeat('c', 64), 'image/png', 'prova', '1', 'h', 1)
    RETURNING id INTO master_b;

  -- O gatilho tambem exige uma rendition `pronta` DESTE master, com o mesmo
  -- job_id — a conferencia que a v11_01 acrescentou depois de um defeito medido.
  -- ⚠️ `criativo_rendition_slot_ux` e unique (job_id, slot): as duas versoes do
  -- master A dividem o job, entao a v2 usa outro slot.
  -- `criativo_rendition_pronta_tem_arquivo`: pronta exige arquivo, hash, master
  -- e instante de conclusao. A fixture respeita a mesma regra que producao.
  INSERT INTO public.criativo_rendition
    (job_id, master_id, slot, estado, largura_pedida, altura_pedida, proporcao_rotulo,
     storage_chave, content_hash, concluida_em)
    VALUES (job_a, master_a, '1x1', 'pronta', 1080, 1080, '1:1',
            'criativos/prova/a-v1.png', 'sha256:' || repeat('a', 64), now());
  INSERT INTO public.criativo_rendition
    (job_id, master_id, slot, estado, largura_pedida, altura_pedida, proporcao_rotulo,
     storage_chave, content_hash, concluida_em)
    VALUES (job_a, master_a_v2, '1x1-v2', 'pronta', 1080, 1080, '1:1',
            'criativos/prova/a-v2.png', 'sha256:' || repeat('b', 64), now());
  INSERT INTO public.criativo_rendition
    (job_id, master_id, slot, estado, largura_pedida, altura_pedida, proporcao_rotulo,
     storage_chave, content_hash, concluida_em)
    VALUES (job_b, master_b, '1x1', 'pronta', 1080, 1080, '1:1',
            'criativos/prova/b-v1.png', 'sha256:' || repeat('c', 64), now());

  INSERT INTO _ctx VALUES
    ('master_a', master_a::text), ('master_a_v2', master_a_v2::text), ('master_b', master_b::text);

  -- As aprovacoes. `instagram_organic` e classe `organica` (v11_02:852).
  INSERT INTO public.criativo_aprovacao (subject_tipo, subject_id, versao, finalidade, decisao, ator_id)
    VALUES ('master', master_a, 1, 'instagram_organic', 'aprovado', dono_a);
  INSERT INTO public.criativo_aprovacao (subject_tipo, subject_id, versao, finalidade, decisao, ator_id)
    VALUES ('master', master_b, 1, 'instagram_organic', 'aprovado', dono_b);
  -- Uma reprovada, uma revogada e uma de classe NAO organica, para as recusas.
  INSERT INTO public.criativo_aprovacao (subject_tipo, subject_id, versao, finalidade, decisao, ator_id, motivo)
    VALUES ('master', master_a, 2, 'instagram_organic', 'rejeitado', dono_a, 'fora da marca');
  INSERT INTO public.criativo_aprovacao (subject_tipo, subject_id, versao, finalidade, decisao, ator_id, revogada_em)
    VALUES ('master', master_a, 1, 'youtube_shorts', 'aprovado', dono_a, now());
  INSERT INTO public.criativo_aprovacao (subject_tipo, subject_id, versao, finalidade, decisao, ator_id)
    VALUES ('master', master_a, 1, 'google_display', 'aprovado', dono_a);

  -- Destinos: um apto (dono A), um inapto (dono A), um apto do dono B.
  PERFORM public.publicacao_organica_registrar_destino(jsonb_build_object(
    'ativo_id','asset:facebook-page:piloto','plataforma','facebook',
    'identidade_logica','PAGINA_PILOTO','referencia_externa','integ-piloto-0001',
    'adapter_apto', true, 'timezone_padrao','America/Sao_Paulo'),
    'prova-destino-apto-000001', dono_a, 'a@agenciavolc.com.br');

  PERFORM public.publicacao_organica_registrar_destino(jsonb_build_object(
    'ativo_id','asset:instagram-profile:sem-adapter','plataforma','instagram',
    'identidade_logica','PERFIL_SEM_ADAPTER',
    'adapter_apto', false, 'motivo_inapto','integracao ainda nao conectada no control plane'),
    'prova-destino-inapto-00001', dono_a, 'a@agenciavolc.com.br');

  PERFORM public.publicacao_organica_registrar_destino(jsonb_build_object(
    'ativo_id','asset:facebook-page:piloto','plataforma','x',
    'identidade_logica','PAGINA_PILOTO_B','referencia_externa','integ-b-0001',
    'adapter_apto', true),
    'prova-destino-b-0000001', dono_b, 'b@agenciavolc.com.br');

  RAISE NOTICE 'cenario montado';
END
$cenario$;

-- Guarda os ids no contexto para os blocos seguintes.
INSERT INTO _ctx
SELECT 'destino_apto', d.id::text FROM public.publicacao_organica_destino d
 WHERE d.identidade_logica = 'PAGINA_PILOTO';
INSERT INTO _ctx
SELECT 'destino_inapto', d.id::text FROM public.publicacao_organica_destino d
 WHERE d.identidade_logica = 'PERFIL_SEM_ADAPTER';
INSERT INTO _ctx
SELECT 'destino_b', d.id::text FROM public.publicacao_organica_destino d
 WHERE d.identidade_logica = 'PAGINA_PILOTO_B';
INSERT INTO _ctx
SELECT 'aprov_a', a.id::text FROM public.criativo_aprovacao a, _ctx c
 WHERE c.chave='master_a' AND a.subject_id = c.valor::uuid
   AND a.finalidade='instagram_organic' AND a.decisao='aprovado' AND a.versao=1;
INSERT INTO _ctx
SELECT 'aprov_b', a.id::text FROM public.criativo_aprovacao a, _ctx c
 WHERE c.chave='master_b' AND a.subject_id = c.valor::uuid AND a.decisao='aprovado';
INSERT INTO _ctx
SELECT 'aprov_rejeitada', a.id::text FROM public.criativo_aprovacao a
 WHERE a.decisao='rejeitado';
INSERT INTO _ctx
SELECT 'aprov_revogada', a.id::text FROM public.criativo_aprovacao a
 WHERE a.revogada_em IS NOT NULL;
INSERT INTO _ctx
SELECT 'aprov_paga', a.id::text FROM public.criativo_aprovacao a
 WHERE a.finalidade='google_display';


-- ===========================================================================
-- CONTRAPROVA A — publicacao SEM aprovacao vigente
-- ===========================================================================
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  m uuid  := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
  d text  := (SELECT valor FROM _ctx WHERE chave='destino_apto');
  base jsonb;
BEGIN
  base := jsonb_build_object('peca_tipo','master','peca_id',m,'peca_versao',1,
                             'destino_id',d,'modo','draft');

  PERFORM _prova_recusa('A1 decisao rejeitada nao autoriza',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
           (base || jsonb_build_object('autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_rejeitada'),
                                       'peca_versao',2))::text,
           'cp-a1-rejeitada-000001', dono_a, 'a@agenciavolc.com.br'),
    '23514', 'so "aprovado" autoriza publicar');

  PERFORM _prova_recusa('A2 aprovacao revogada nao autoriza',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
           (base || jsonb_build_object('autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_revogada')))::text,
           'cp-a2-revogada-0000001', dono_a, 'a@agenciavolc.com.br'),
    '23514', 'foi revogada');

  PERFORM _prova_recusa('A3 aprovacao de classe NAO organica nao autoriza feed',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
           (base || jsonb_build_object('autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_paga')))::text,
           'cp-a3-classe-paga-00001', dono_a, 'a@agenciavolc.com.br'),
    '23514', 'nao e de classe organica');
END
$bloco$;

-- ===========================================================================
-- CONTRAPROVA B — dono A publicando peca/destino do dono B
-- ===========================================================================
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  mb uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_b');
  ma uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
BEGIN
  PERFORM _prova_recusa('B1 peca de outro dono',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      jsonb_build_object('peca_tipo','master','peca_id',mb,'peca_versao',1,
        'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_b'),
        'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_apto'),'modo','draft')::text,
      'cp-b1-peca-alheia-00001', dono_a, 'a@agenciavolc.com.br'),
    '42501', 'pertence a outro dono');

  PERFORM _prova_recusa('B2 destino de outro dono',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
        'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
        'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_b'),'modo','draft')::text,
      'cp-b2-destino-alheio-01', dono_a, 'a@agenciavolc.com.br'),
    '42501', 'destino pertence a outro dono');
END
$bloco$;

-- ===========================================================================
-- CONTRAPROVA C — destino ausente, inapto ou divergente
-- CONTRAPROVA I — autorizacao nao e transferivel entre versoes
-- ===========================================================================
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  ma uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
  mav2 uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a_v2');
BEGIN
  PERFORM _prova_recusa('C1 destino inexistente',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
        'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
        'destino_id','00000000-0000-0000-0000-0000000000ff','modo','draft')::text,
      'cp-c1-destino-ausente-1', dono_a, 'a@agenciavolc.com.br'),
    '23503', 'destino inexistente');

  PERFORM _prova_recusa('C2 destino sem adapter apto',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
        'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
        'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_inapto'),'modo','draft')::text,
      'cp-c2-destino-inapto-1', dono_a, 'a@agenciavolc.com.br'),
    '23514', 'nao tem adapter apto');

  -- I: a aprovacao e da versao 1. Citar a peca v2 com ela e transferir
  -- autorizacao, e e exatamente o que a recusa 3 do gatilho existe para impedir.
  PERFORM _prova_recusa('I1 autorizacao da v1 nao cobre a peca v2',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      jsonb_build_object('peca_tipo','master','peca_id',mav2,'peca_versao',2,
        'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
        'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_apto'),'modo','draft')::text,
      'cp-i1-versao-nova-0001', dono_a, 'a@agenciavolc.com.br'),
    '23514', 'autorizacao nao e transferivel');
END
$bloco$;

-- ===========================================================================
-- CONTRAPROVA J — `now` sem consentimento humano explicito
-- CONTRAPROVA K — timezone e horario
-- ===========================================================================
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  ma uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
  base jsonb;
BEGIN
  base := jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
            'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
            'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_apto'));

  PERFORM _prova_recusa('J1 now sem consentimento',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      (base || jsonb_build_object('modo','now'))::text,
      'cp-j1-now-sem-sim-0001', dono_a, 'a@agenciavolc.com.br'),
    '23514', 'consentimento humano explicito');

  PERFORM _prova_recusa('J2 now com consentimento FALSE explicito',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      (base || jsonb_build_object('modo','now','consentimento_agora',false))::text,
      'cp-j2-now-nao-00000001', dono_a, 'a@agenciavolc.com.br'),
    '23514', 'consentimento humano explicito');

  PERFORM _prova_recusa('K1 timezone IANA inexistente',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      (base || jsonb_build_object('modo','schedule','timezone','America/Nao_Existe',
                                  'horario_local','2099-01-01 10:00:00'))::text,
      'cp-k1-tz-inventada-001', dono_a, 'a@agenciavolc.com.br'),
    '22023', 'timezone IANA desconhecido');

  PERFORM _prova_recusa('K2 agendar para o passado',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      (base || jsonb_build_object('modo','schedule','timezone','America/Sao_Paulo',
                                  'horario_local','2020-01-01 10:00:00'))::text,
      'cp-k2-passado-00000001', dono_a, 'a@agenciavolc.com.br'),
    '22023', 'agendar para o passado');

  PERFORM _prova_recusa('K3 horario local que nao existe (salto de DST)',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      (base || jsonb_build_object('modo','schedule','timezone','America/New_York',
                                  'horario_local','2099-03-08 02:30:00'))::text,
      'cp-k3-dst-inexistente-1', dono_a, 'a@agenciavolc.com.br'),
    '22023', 'nao existe nesta zona');

  PERFORM _prova_recusa('K4 schedule sem horario local declarado',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      (base || jsonb_build_object('modo','schedule','timezone','America/Sao_Paulo'))::text,
      'cp-k4-sem-horario-0001', dono_a, 'a@agenciavolc.com.br'),
    '22023', 'exige horario local declarado');
END
$bloco$;

-- K5: a conversao NAO depende do TimeZone do servidor. Provada mudando o TZ da
-- sessao entre duas criacoes do MESMO horario local e comparando os instantes.
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  ma uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
  base jsonb;
  r1 jsonb; r2 jsonb;
BEGIN
  base := jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
            'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
            'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_apto'),
            'modo','schedule','timezone','America/Sao_Paulo',
            'horario_local','2099-07-15 09:30:00');

  SET LOCAL TimeZone = 'UTC';
  r1 := public.publicacao_organica_criar_job(base, 'cp-k5-tz-utc-000000001', dono_a, 'a@agenciavolc.com.br');
  SET LOCAL TimeZone = 'Pacific/Kiritimati';
  r2 := public.publicacao_organica_criar_job(base, 'cp-k5-tz-kiri-00000001', dono_a, 'a@agenciavolc.com.br');
  RESET TimeZone;

  IF (r1->>'instante_utc')::timestamptz IS DISTINCT FROM (r2->>'instante_utc')::timestamptz THEN
    RAISE EXCEPTION 'PROVA FALHOU: K5 | o instante mudou com o TZ do servidor: % vs %',
      r1->>'instante_utc', r2->>'instante_utc';
  END IF;
  -- 09:30 em America/Sao_Paulo (UTC-3, sem horario de verao desde 2019) = 12:30Z.
  IF (r1->>'instante_utc')::timestamptz <> '2099-07-15 12:30:00+00'::timestamptz THEN
    RAISE EXCEPTION 'PROVA FALHOU: K5 | 09:30 America/Sao_Paulo deveria ser 12:30Z, obtido %',
      (r1->>'instante_utc')::timestamptz;
  END IF;
  RAISE NOTICE 'PROVA ok: K5 conversao independente do TZ do servidor | 12:30Z';

  INSERT INTO _ctx VALUES ('job_agendado', r1->>'job_id');
END
$bloco$;

-- ===========================================================================
-- CAMINHO FELIZ + CONTRAPROVAS D, E, F, G, L
-- ===========================================================================
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  ma uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
  base jsonb;
  criado jsonb;
  jid uuid;
  claim1 jsonb; claim2 jsonb;
  recibo jsonb;
  snapshot_antes jsonb; snapshot_depois jsonb;
BEGIN
  base := jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
            'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
            'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_apto'),
            'modo','draft', 'corpo', jsonb_build_object('texto','Primeira peca organica.'));

  criado := public.publicacao_organica_criar_job(base, 'cp-feliz-draft-0000001', dono_a, 'a@agenciavolc.com.br');
  jid := (criado->>'job_id')::uuid;
  INSERT INTO _ctx VALUES ('job_draft', jid::text);

  IF (criado->>'idempotente')::boolean IS NOT FALSE THEN
    RAISE EXCEPTION 'PROVA FALHOU: primeira criacao marcada como replay';
  END IF;

  -- E: MESMA chave, payload DIFERENTE -> unique_violation, e a chave NAO
  -- aparece na mensagem.
  PERFORM _prova_recusa('E mesma chave com payload diferente',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      (base || jsonb_build_object('corpo', jsonb_build_object('texto','OUTRO TEXTO')))::text,
      'cp-feliz-draft-0000001', dono_a, 'a@agenciavolc.com.br'),
    '23505', 'ja foi usada por outra operacao');

  -- Replay honesto: mesma chave, MESMA entrada -> devolve o recibo guardado.
  IF ((public.publicacao_organica_criar_job(base, 'cp-feliz-draft-0000001', dono_a, 'a@agenciavolc.com.br'))->>'idempotente')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'PROVA FALHOU: replay da mesma entrada nao foi marcado como idempotente';
  END IF;
  RAISE NOTICE 'PROVA ok: replay honesto devolve o recibo guardado';

  -- Um unico job foi criado apesar das tres chamadas.
  PERFORM _prova_igual('D0 tres chamadas, um job',
    format('SELECT count(*)::text FROM public.publicacao_organica_job WHERE chave_idempotencia=%L','cp-feliz-draft-0000001'),
    '1');

  PERFORM public.publicacao_organica_liberar(jid, dono_a);

  -- F: dois consumidores concorrentes. O segundo NAO reivindica.
  claim1 := public.publicacao_organica_reivindicar(jid, 'consumidor-1', 120);
  claim2 := public.publicacao_organica_reivindicar(jid, 'consumidor-2', 120);
  IF (claim1->>'reivindicado')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'PROVA FALHOU: F | o primeiro consumidor nao conseguiu reivindicar';
  END IF;
  IF (claim2->>'reivindicado')::boolean IS NOT FALSE THEN
    RAISE EXCEPTION 'PROVA FALHOU: F | o SEGUNDO consumidor tambem reivindicou';
  END IF;
  RAISE NOTICE 'PROVA ok: F dois consumidores, uma reivindicacao | %', claim2->>'motivo';

  -- G/L: sucesso SEM referencia externa nao e recibo.
  PERFORM _prova_recusa('G/L sucesso sem referencia externa',
    format('SELECT public.publicacao_organica_concluir_despacho(%L::uuid, %s, %L, %L, %L::jsonb, %L::uuid, %L)',
      jid, claim1->>'fencing', 'cp-g-sem-referencia-01', 'sucesso',
      jsonb_build_object('estado_externo','DRAFT')::text, dono_a, 'a@agenciavolc.com.br'),
    '23514', 'sucesso sem referencia externa nao e recibo');

  -- Fencing velho e recusado.
  PERFORM _prova_recusa('F2 fencing vencido',
    format('SELECT public.publicacao_organica_concluir_despacho(%L::uuid, %s, %L, %L, %L::jsonb, %L::uuid, %L)',
      jid, (claim1->>'fencing')::bigint - 1, 'cp-f2-fencing-velho-01', 'sucesso',
      jsonb_build_object('referencia_externa','post-x','estado_externo','DRAFT')::text,
      dono_a, 'a@agenciavolc.com.br'),
    '40001', 'fencing vencido');

  -- Despacho bem-sucedido: draft criado no control plane.
  recibo := public.publicacao_organica_concluir_despacho(
    jid, (claim1->>'fencing')::bigint, 'cp-feliz-despacho-00001', 'sucesso',
    jsonb_build_object('referencia_externa','post-0001','estado_externo','DRAFT'),
    dono_a, 'a@agenciavolc.com.br');

  PERFORM _prova_igual('estado apos draft aceito',
    format('SELECT estado FROM public.publicacao_organica_job WHERE id=%L', jid),
    'rascunho_externo');

  -- D: retry do MESMO despacho devolve o recibo, e NAO cria segundo recibo.
  IF ((public.publicacao_organica_concluir_despacho(
        jid, (claim1->>'fencing')::bigint, 'cp-feliz-despacho-00001', 'sucesso',
        jsonb_build_object('referencia_externa','post-0001','estado_externo','DRAFT'),
        dono_a, 'a@agenciavolc.com.br'))->>'idempotente')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'PROVA FALHOU: D | o retry do despacho nao foi replay';
  END IF;
  PERFORM _prova_igual('D um recibo externo apesar do retry',
    format('SELECT count(*)::text FROM public.publicacao_organica_recibo WHERE job_id=%L', jid),
    '1');
  RAISE NOTICE 'PROVA ok: D retry idempotente nao publica de novo';

  -- D2: um SEGUNDO sucesso de despacho para o mesmo job, com chave nova, e
  -- recusado FISICAMENTE pelo indice parcial — nao por convencao do executor.
  PERFORM _prova_recusa('D2 segundo sucesso de despacho no mesmo job',
    format('SELECT public.publicacao_organica_registra_operacao(%L::uuid, %L, %L, %L, %L::jsonb, %L, NULL, NULL)',
      jid, 'cp-d2-segundo-sucesso-1', 'publicacao_organica.concluir_despacho',
      repeat('f',64), '{"x":1}'::text, 'sucesso'),
    '23505', 'publicacao_organica_operacao_sucesso_ux');

  -- SNAPSHOT IMUTAVEL: nem por UPDATE direto (rodando como superusuario).
  SELECT solicitacao INTO snapshot_antes FROM public.publicacao_organica_job WHERE id = jid;
  PERFORM _prova_recusa('I2 snapshot e imutavel',
    format('UPDATE public.publicacao_organica_job SET solicitacao = %L::jsonb WHERE id=%L',
      '{"adulterado":true}'::text, jid),
    '23001', 'snapshot da solicitacao e imutavel');
  SELECT solicitacao INTO snapshot_depois FROM public.publicacao_organica_job WHERE id = jid;
  IF snapshot_antes IS DISTINCT FROM snapshot_depois THEN
    RAISE EXCEPTION 'PROVA FALHOU: I2 | o snapshot mudou';
  END IF;

  -- E o snapshot aponta para a v1, mesmo com a v2 ja existindo no banco.
  PERFORM _prova_igual('I3 snapshot preso a versao aprovada',
    format('SELECT (solicitacao->''peca''->>''versao'') FROM public.publicacao_organica_job WHERE id=%L', jid),
    '1');
  PERFORM _prova_igual('I4 snapshot preso ao content_hash aprovado',
    format('SELECT (solicitacao->''peca''->>''content_hash'') FROM public.publicacao_organica_job WHERE id=%L', jid),
    'sha256:' || repeat('a', 64));

  -- Transicao fora da lista e recusada. `rascunho_externo>pronto` e o exemplo
  -- que importa: rearmar um job que JA EXISTE no destino produziria um segundo
  -- post. Ela nunca entra na lista.
  PERFORM _prova_recusa('D3 rearmar job ja despachado',
    format('UPDATE public.publicacao_organica_job SET estado=''pronto'' WHERE id=%L', jid),
    '23514', 'nao e permitida');
  PERFORM _prova_recusa('D4 voltar para em_voo sem reivindicar',
    format('UPDATE public.publicacao_organica_job SET estado=''em_voo'' WHERE id=%L', jid),
    '23514', 'nao e permitida');

  -- Job nao se apaga.
  PERFORM _prova_recusa('job nao e apagado',
    format('DELETE FROM public.publicacao_organica_job WHERE id=%L', jid),
    '23001', 'job nao e apagado');

  -- Recibo e append-only.
  PERFORM _prova_recusa('recibo append-only',
    format('UPDATE public.publicacao_organica_recibo SET url_publicada=''x'' WHERE job_id=%L', jid),
    '23001', 'append-only');
END
$bloco$;

-- ===========================================================================
-- INDETERMINADO -> RECONCILIACAO (o estado que nao e sucesso nem falha)
-- ===========================================================================
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  jid uuid := (SELECT valor::uuid FROM _ctx WHERE chave='job_agendado');
  claim jsonb; r jsonb;
BEGIN
  PERFORM public.publicacao_organica_liberar(jid, dono_a);
  claim := public.publicacao_organica_reivindicar(jid, 'consumidor-1', 120);

  -- Timeout: o adaptador nao sabe o desfecho. Isso e `indeterminado`, e nao
  -- sucesso silencioso nem falha inventada.
  r := public.publicacao_organica_concluir_despacho(
    jid, (claim->>'fencing')::bigint, 'cp-g-timeout-00000001', 'indeterminado',
    jsonb_build_object('erro','timeout ao falar com o control plane'),
    dono_a, 'a@agenciavolc.com.br');

  PERFORM _prova_igual('G timeout vira indeterminado, nao sucesso',
    format('SELECT estado FROM public.publicacao_organica_job WHERE id=%L', jid),
    'indeterminado');
  PERFORM _prova_igual('G nenhum recibo externo foi inventado',
    format('SELECT count(*)::text FROM public.publicacao_organica_recibo WHERE job_id=%L', jid),
    '0');

  -- Reconciliacao que NAO encontra o objeto: relata, nao apaga, nao reprova.
  r := public.publicacao_organica_reconciliar(
    jid, 'cp-recon-vazia-0000001',
    jsonb_build_object('estado_externo','DESCONHECIDO'), dono_a, 'a@agenciavolc.com.br');
  IF (r->>'fechou')::boolean IS NOT FALSE THEN
    RAISE EXCEPTION 'PROVA FALHOU: reconciliacao sem referencia declarou fechado';
  END IF;
  PERFORM _prova_igual('reconciliacao vazia mantem indeterminado',
    format('SELECT estado FROM public.publicacao_organica_job WHERE id=%L', jid),
    'indeterminado');

  -- Reconciliacao que encontra QUEUE: o job vira agendado, e nao publicado.
  r := public.publicacao_organica_reconciliar(
    jid, 'cp-recon-queue-0000001',
    jsonb_build_object('referencia_externa','post-0002','estado_externo','QUEUE'),
    dono_a, 'a@agenciavolc.com.br');
  PERFORM _prova_igual('QUEUE nao e publicado',
    format('SELECT estado FROM public.publicacao_organica_job WHERE id=%L', jid),
    'agendado');

  -- PUBLISHED sem URL nem instante NAO fecha: e afirmacao sem prova.
  PERFORM _prova_recusa('L PUBLISHED sem URL nem instante',
    format('SELECT public.publicacao_organica_reconciliar(%L::uuid, %L, %L::jsonb, %L::uuid, %L)',
      jid, 'cp-l-published-sem-url', jsonb_build_object('referencia_externa','post-0002','estado_externo','PUBLISHED')::text,
      dono_a, 'a@agenciavolc.com.br'),
    '23514', 'publicacao_organica_recibo_publicado_tem_prova');

  -- PUBLISHED com URL e instante fecha em reconciliado.
  r := public.publicacao_organica_reconciliar(
    jid, 'cp-recon-published-001',
    jsonb_build_object('referencia_externa','post-0002','estado_externo','PUBLISHED',
                       'url_publicada','https://www.facebook.com/piloto/posts/0002',
                       'publicado_em', to_jsonb(now())),
    dono_a, 'a@agenciavolc.com.br');
  IF (r->>'fechou')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'PROVA FALHOU: PUBLISHED com prova nao fechou';
  END IF;
  PERFORM _prova_igual('reconciliado fecha o ciclo',
    format('SELECT estado FROM public.publicacao_organica_job WHERE id=%L', jid),
    'reconciliado');
  -- DUAS observacoes, e nao quatro: a reconciliacao vazia NAO inventa recibo
  -- (nao ha referencia externa) e a PUBLISHED-sem-prova foi recusada antes de
  -- gravar. Sobram QUEUE e PUBLISHED — as duas que realmente aconteceram.
  PERFORM _prova_igual('historico preserva as observacoes reais',
    format('SELECT count(*)::text FROM public.publicacao_organica_recibo WHERE job_id=%L', jid),
    '2');
  PERFORM _prova_igual('a primeira observacao nao foi sobrescrita',
    format('SELECT string_agg(estado_externo, '','' ORDER BY id) FROM public.publicacao_organica_recibo WHERE job_id=%L', jid),
    'QUEUE,PUBLISHED');
END
$bloco$;

-- ===========================================================================
-- O BURACO NEGRO DO LEASE — achado por revisao adversarial cruzada (02/09/2026)
-- ===========================================================================
-- `reivindicar` so aceita `pronto`, e todo claim move o job para `em_voo`. Logo
-- um despachante que morre entre reivindicar e concluir deixava o job preso:
-- reivindicar recusava, reconciliar recusava e cancelar recusava. Tres portas
-- fechadas. A saida e `expirar_lease`, e ela e guardada pelo RELOGIO.
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  ma uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
  criado jsonb; jid uuid; claim jsonb; r jsonb;
BEGIN
  criado := public.publicacao_organica_criar_job(
    jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
      'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
      'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_apto'),
      'modo','draft','corpo',jsonb_build_object('texto','despachante que morre')),
    'cp-lease-preso-0000001', dono_a, 'a@agenciavolc.com.br');
  jid := (criado->>'job_id')::uuid;
  PERFORM public.publicacao_organica_liberar(jid, dono_a);
  claim := public.publicacao_organica_reivindicar(jid, 'consumidor-que-morre', 1);

  -- Com o lease AINDA VALIDO, expirar e recusado: ha um despachante vivo.
  r := public.publicacao_organica_expirar_lease(jid);
  IF (r->>'expirado')::boolean IS NOT FALSE THEN
    RAISE EXCEPTION 'PROVA FALHOU: lease valido foi expirado';
  END IF;
  RAISE NOTICE 'PROVA ok: lease valido nao e expirado | %', r->>'motivo';

  -- Envelhece o lease sem tocar em mais nada (simula o relogio andando).
  UPDATE public.publicacao_organica_job
     SET lease_ate = now() - interval '1 minute' WHERE id = jid;

  -- Antes do conserto, as TRES portas estavam fechadas. Provamos duas ainda
  -- fechadas (elas DEVEM continuar fechadas) e a terceira agora aberta.
  PERFORM _prova_recusa('preso: reconciliar ainda recusa em_voo',
    format('SELECT public.publicacao_organica_reconciliar(%L::uuid, %L, %L::jsonb, %L::uuid, %L)',
      jid, 'cp-preso-recon-000001', '{"estado_externo":"DESCONHECIDO"}'::text,
      dono_a, 'a@agenciavolc.com.br'),
    '23514', 'nada a reconciliar');
  PERFORM _prova_recusa('preso: cancelar ainda recusa em_voo',
    format('SELECT public.publicacao_organica_cancelar(%L::uuid, %L, %L::uuid)', jid, 'desisti', dono_a),
    '23514', 'em voo nao e cancelado');

  PERFORM _prova_igual('preso aparece na lista de presos',
    format('SELECT count(*)::text FROM jsonb_array_elements(public.publicacao_organica_presos(50)) e WHERE e->>''job_id''=%L', jid),
    '1');

  r := public.publicacao_organica_expirar_lease(jid);
  IF (r->>'expirado')::boolean IS NOT TRUE THEN
    RAISE EXCEPTION 'PROVA FALHOU: lease vencido nao pode ser expirado: %', r->>'motivo';
  END IF;
  PERFORM _prova_igual('lease vencido vira indeterminado, e nao sucesso',
    format('SELECT estado FROM public.publicacao_organica_job WHERE id=%L', jid),
    'indeterminado');
  -- ⚠️ E NAO redespacha: o pedido pode ter chegado. `pronto` nao e alcancavel.
  PERFORM _prova_recusa('preso nao volta para pronto',
    format('UPDATE public.publicacao_organica_job SET estado=''pronto'' WHERE id=%L', jid),
    '23514', 'nao e permitida');
  -- Daqui a reconciliacao resolve, que e o caminho desenhado.
  r := public.publicacao_organica_reconciliar(
    jid, 'cp-preso-recon-000002',
    jsonb_build_object('estado_externo','DESCONHECIDO'), dono_a, 'a@agenciavolc.com.br');
  PERFORM _prova_igual('do indeterminado a reconciliacao ja funciona',
    format('SELECT estado FROM public.publicacao_organica_job WHERE id=%L', jid),
    'indeterminado');
  RAISE NOTICE 'PROVA ok: o buraco negro do lease tem saida, e ela nao redespacha';
END
$bloco$;

-- ===========================================================================
-- HORARIO AMBIGUO — o que acontece DUAS vezes no fim do horario de verao
-- ===========================================================================
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  ma uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
  base jsonb;
  r jsonb;
BEGIN
  base := jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
            'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
            'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_apto'),
            'modo','schedule');

  -- 2099-11-01 01:30 em America/New_York acontece duas vezes (EDT e EST).
  PERFORM _prova_recusa('K6 horario ambiguo (recuo do DST) e recusado',
    format('SELECT public.publicacao_organica_criar_job(%L::jsonb, %L, %L::uuid, %L)',
      (base || jsonb_build_object('timezone','America/New_York',
                                  'horario_local','2099-11-01 01:30:00'))::text,
      'cp-k6-ambiguo-0000001', dono_a, 'a@agenciavolc.com.br'),
    '22023', 'acontece DUAS vezes');

  -- ⚠️ E o CONTROLE: um horario normal na MESMA zona continua passando. Sem
  -- este par, a deteccao poderia estar recusando tudo e o teste ficaria verde.
  r := public.publicacao_organica_criar_job(
    base || jsonb_build_object('timezone','America/New_York',
                               'horario_local','2099-11-01 05:30:00'),
    'cp-k6-controle-000001', dono_a, 'a@agenciavolc.com.br');
  IF r->>'job_id' IS NULL THEN
    RAISE EXCEPTION 'PROVA FALHOU: K6 controle | horario normal foi recusado';
  END IF;
  RAISE NOTICE 'PROVA ok: K6 controle | horario normal na mesma zona passa';

  -- Offset fracionario continua correto: 09:30 em Asia/Kathmandu (+05:45) = 03:45Z.
  r := public.publicacao_organica_criar_job(
    base || jsonb_build_object('timezone','Asia/Kathmandu',
                               'horario_local','2099-07-15 09:30:00'),
    'cp-k7-kathmandu-00001', dono_a, 'a@agenciavolc.com.br');
  IF (r->>'instante_utc')::timestamptz <> '2099-07-15 03:45:00+00'::timestamptz THEN
    RAISE EXCEPTION 'PROVA FALHOU: K7 offset fracionario | obtido %', r->>'instante_utc';
  END IF;
  RAISE NOTICE 'PROVA ok: K7 offset fracionario (+05:45) | 03:45Z';
END
$bloco$;

-- ===========================================================================
-- CONTRAPROVA H — erro externo com material de credencial e RECUSADO
-- ===========================================================================
DO $bloco$
DECLARE
  jid uuid := (SELECT valor::uuid FROM _ctx WHERE chave='job_draft');
  segredo text := (SELECT valor FROM _ctx WHERE chave='segredo');
BEGIN
  PERFORM _prova_recusa('H erro com token nao entra na linha',
    format('UPDATE public.publicacao_organica_job SET ultimo_erro=%L WHERE id=%L',
      'falha do control plane: Authorization: ' || segredo, jid),
    '23514', 'publicacao_organica_job_prosa_limpa');

  PERFORM _prova_recusa('H2 chave sensivel no recibo e recusada antes de gravar',
    format('SELECT public.publicacao_organica_concluir_despacho(%L::uuid, 1, %L, %L, %L::jsonb, NULL, NULL)',
      jid, 'cp-h2-recibo-com-token', 'falha',
      jsonb_build_object('erro','x','access_token','abc')::text),
    '23001', 'campo proibido');
END
$bloco$;

-- ===========================================================================
-- CONTRAPROVA N — service_role NAO escreve direto, e nao le direto
-- ===========================================================================
DO $bloco$
BEGIN
  PERFORM _prova_recusa_como('N1 service_role nao le a tabela de jobs', 'service_role',
    'SELECT count(*) FROM public.publicacao_organica_job');
  PERFORM _prova_recusa_como('N2 service_role nao insere destino direto', 'service_role',
    $x$INSERT INTO public.publicacao_organica_destino
         (ativo_id, plataforma, identidade_logica, owner_sub, adapter_apto, referencia_externa)
       VALUES ('asset:facebook-page:piloto','facebook','X',
               '11111111-1111-1111-1111-111111111111', true, 'y')$x$);
  PERFORM _prova_recusa_como('N3 anon nao le recibo', 'anon',
    'SELECT count(*) FROM public.publicacao_organica_recibo');
  PERFORM _prova_recusa_como('N4 service_role nao chama a funcao interna de idempotencia',
    'service_role',
    $x$SELECT public.publicacao_organica_idempotencia('x','y','z')$x$);
END
$bloco$;

-- ===========================================================================
-- CANCELAMENTO SEGURO
-- ===========================================================================
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  dono_b uuid := '22222222-2222-2222-2222-222222222222';
  ma uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
  criado jsonb; jid uuid; claim jsonb;
BEGIN
  criado := public.publicacao_organica_criar_job(
    jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
      'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
      'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_apto'),
      'modo','draft','corpo',jsonb_build_object('texto','para cancelar')),
    'cp-cancelar-000000001', dono_a, 'a@agenciavolc.com.br');
  jid := (criado->>'job_id')::uuid;

  PERFORM _prova_recusa('cancelar exige motivo',
    format('SELECT public.publicacao_organica_cancelar(%L::uuid, %L, %L::uuid)', jid, '  ', dono_a),
    '22023', 'exige motivo');

  PERFORM _prova_recusa('cancelar job de outro dono',
    format('SELECT public.publicacao_organica_cancelar(%L::uuid, %L, %L::uuid)', jid, 'nao quero', dono_b),
    '42501', 'pertence a outro dono');

  PERFORM public.publicacao_organica_liberar(jid, dono_a);
  claim := public.publicacao_organica_reivindicar(jid, 'consumidor-1', 120);

  PERFORM _prova_recusa('job em voo nao e cancelado',
    format('SELECT public.publicacao_organica_cancelar(%L::uuid, %L, %L::uuid)', jid, 'mudei de ideia', dono_a),
    '23514', 'em voo nao e cancelado');

  PERFORM public.publicacao_organica_concluir_despacho(
    jid, (claim->>'fencing')::bigint, 'cp-cancelar-despacho-01', 'sucesso',
    jsonb_build_object('referencia_externa','post-0003','estado_externo','DRAFT'),
    dono_a, 'a@agenciavolc.com.br');
  PERFORM public.publicacao_organica_cancelar(jid, 'peca substituida', dono_a);

  PERFORM _prova_igual('cancelado preserva a trilha',
    format('SELECT estado FROM public.publicacao_organica_job WHERE id=%L', jid), 'cancelado');
  PERFORM _prova_igual('o recibo do rascunho continua la',
    format('SELECT count(*)::text FROM public.publicacao_organica_recibo WHERE job_id=%L', jid), '1');
END
$bloco$;

-- ===========================================================================
-- LEITURA — dono nao e filtro opcional; destino inapto aparece com motivo
-- ===========================================================================
DO $bloco$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  dono_b uuid := '22222222-2222-2222-2222-222222222222';
  destinos jsonb;
BEGIN
  destinos := public.publicacao_organica_listar_destinos(dono_a);
  IF jsonb_array_length(destinos) <> 2 THEN
    RAISE EXCEPTION 'PROVA FALHOU: o dono A deveria ver 2 destinos, viu %', jsonb_array_length(destinos);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(destinos) d
                  WHERE d->>'identidade_logica'='PERFIL_SEM_ADAPTER'
                    AND (d->>'apto')::boolean = false
                    AND d->>'motivo' = 'integracao ainda nao conectada no control plane') THEN
    RAISE EXCEPTION 'PROVA FALHOU: o destino inapto sumiu da lista ou perdeu o motivo';
  END IF;
  RAISE NOTICE 'PROVA ok: destino inapto aparece, inapto e COM motivo';

  -- Ler o job do outro dono devolve NULL — a mesma resposta de "nao existe",
  -- de proposito: a diferenca revelaria a existencia do job alheio.
  PERFORM _prova_igual('B3 detalhar job de outro dono devolve NULL',
    format('SELECT coalesce((public.publicacao_organica_detalhar_job(%L::uuid, %L::uuid))::text, ''NULO'')',
      (SELECT valor FROM _ctx WHERE chave='job_draft'), dono_b),
    'NULO');
END
$bloco$;

-- ===========================================================================
-- NAO-VAZAMENTO — o segredo nao aparece em NENHUMA coluna de NENHUMA tabela
-- ===========================================================================
DO $varredura$
DECLARE
  segredo text := (SELECT valor FROM _ctx WHERE chave='segredo');
  t text; c text; achou bigint;
BEGIN
  FOR t, c IN
    SELECT c.relname, a.attname
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid
     WHERE n.nspname='public' AND c.relkind='r'
       AND c.relname LIKE 'publicacao\_organica\_%'
       AND a.attnum > 0 AND NOT a.attisdropped
  LOOP
    EXECUTE format('SELECT count(*) FROM public.%I WHERE %I::text LIKE %L', t, c, '%' || segredo || '%')
      INTO achou;
    IF achou > 0 THEN
      RAISE EXCEPTION 'PROVA FALHOU: o segredo apareceu em %.%', t, c;
    END IF;
  END LOOP;
  RAISE NOTICE 'PROVA ok: o segredo nao aparece em nenhuma coluna das 5 tabelas';
END
$varredura$;

SELECT 'jobs: ' || count(*)::text FROM public.publicacao_organica_job;
SELECT 'operacoes: ' || count(*)::text FROM public.publicacao_organica_operacao;
SELECT 'recibos: ' || count(*)::text FROM public.publicacao_organica_recibo;
SELECT 'transicoes: ' || count(*)::text FROM public.publicacao_organica_transicao;
PROVAS

aplicar "${BASE}/provas.sql" 2>&1 | sed 's/^NOTICE:  /  /'
echo "  ✓ contraprovas A–N passaram"

# ---------------------------------------------------------------------------
# 4b. CONTRAPROVA F REAL — dois PROCESSOS disputando o mesmo job
# ---------------------------------------------------------------------------
# ⚠️ A prova F do bloco acima e SEQUENCIAL: duas chamadas na mesma sessao. Ela
# mostra que a segunda reivindicacao e recusada, e nao mostra o que acontece
# quando as duas chegam AO MESMO TEMPO — que e o caso que produz post duplicado
# em producao. Esta secao sobe dois processos psql de verdade, sincronizados por
# um advisory lock que so libera quando os dois ja estao esperando, e conta
# quantos venceram. Sem isso, "idempotente sob concorrencia" seria afirmacao
# sem prova.
echo; echo "DEGRAU 2b — corrida real entre dois processos"

executar >/dev/null <<'SQL'
-- Um job novo, liberado, so para a corrida.
DO $corrida$
DECLARE
  dono_a uuid := '11111111-1111-1111-1111-111111111111';
  ma uuid := (SELECT valor::uuid FROM _ctx WHERE chave='master_a');
  criado jsonb;
BEGIN
  criado := public.publicacao_organica_criar_job(
    jsonb_build_object('peca_tipo','master','peca_id',ma,'peca_versao',1,
      'autorizacao_id',(SELECT valor FROM _ctx WHERE chave='aprov_a'),
      'destino_id',(SELECT valor FROM _ctx WHERE chave='destino_apto'),
      'modo','draft','corpo',jsonb_build_object('texto','corrida')),
    'cp-f-corrida-000000001', dono_a, 'a@agenciavolc.com.br');
  PERFORM public.publicacao_organica_liberar((criado->>'job_id')::uuid, dono_a);
  INSERT INTO _ctx VALUES ('job_corrida', criado->>'job_id');
END
$corrida$;
CREATE TABLE _placar (consumidor text, venceu boolean, motivo text);
SQL

JOB_CORRIDA=$(executar -tA -c "SELECT valor FROM _ctx WHERE chave='job_corrida'")

cat > "${BASE}/corrida.sql" <<'CORRIDA'
\set ON_ERROR_STOP on
-- BARREIRA POR RELOGIO DO BANCO. Os dois processos ja estao conectados e
-- girando quando a largada chega; nenhum termina antes de o outro comecar.
-- (Uma barreira por advisory lock exigiria um arbitro vivo; matar o psql do
-- arbitro solta o lock e a "corrida" volta a ser sequencial disfarcada.)
SELECT pg_sleep(greatest(0, extract(epoch FROM
         (SELECT valor::timestamptz FROM _ctx WHERE chave='largada') - clock_timestamp())));
INSERT INTO _placar
SELECT :'quem',
       (r->>'reivindicado')::boolean,
       coalesce(r->>'motivo','venceu')
  FROM (SELECT public.publicacao_organica_reivindicar(:'job'::uuid, :'quem', 60) AS r) t;
CORRIDA

executar >/dev/null -c "INSERT INTO _ctx VALUES ('largada', (clock_timestamp() + interval '2 seconds')::text)"

if [[ -n "$SOCK" ]]; then
  psql -X -q -h "$SOCK" -U postgres -d postgres -v job="$JOB_CORRIDA" -v quem=corredor-1 -f "${BASE}/corrida.sql" >/dev/null 2>&1 &
  P1=$!
  psql -X -q -h "$SOCK" -U postgres -d postgres -v job="$JOB_CORRIDA" -v quem=corredor-2 -f "${BASE}/corrida.sql" >/dev/null 2>&1 &
  P2=$!
else
  docker exec -i "$CID" psql -U postgres -X -q -v job="$JOB_CORRIDA" -v quem=corredor-1 -v ON_ERROR_STOP=1 < "${BASE}/corrida.sql" >/dev/null 2>&1 &
  P1=$!
  docker exec -i "$CID" psql -U postgres -X -q -v job="$JOB_CORRIDA" -v quem=corredor-2 -v ON_ERROR_STOP=1 < "${BASE}/corrida.sql" >/dev/null 2>&1 &
  P2=$!
fi
wait $P1 || true
wait $P2 || true

executar >/dev/null <<'SQL'
DO $conferencia$
DECLARE
  linhas int; vencedores int; fencing_final bigint; tentativas_final int;
BEGIN
  SELECT count(*) INTO linhas FROM _placar;
  IF linhas <> 2 THEN
    RAISE EXCEPTION 'PROVA FALHOU: F-real | esperava 2 corredores, registrei %', linhas;
  END IF;
  SELECT count(*) INTO vencedores FROM _placar WHERE venceu;
  IF vencedores <> 1 THEN
    RAISE EXCEPTION
      'PROVA FALHOU: F-real | % consumidores venceram a mesma reivindicacao (deveria ser 1)', vencedores;
  END IF;
  SELECT j.fencing, j.tentativas INTO fencing_final, tentativas_final
    FROM public.publicacao_organica_job j, _ctx c
   WHERE c.chave='job_corrida' AND j.id = c.valor::uuid;
  -- Uma reivindicacao venceu, logo UMA tentativa e UM incremento de fencing.
  IF fencing_final <> 1 OR tentativas_final <> 1 THEN
    RAISE EXCEPTION
      'PROVA FALHOU: F-real | fencing=% tentativas=% (esperava 1 e 1)', fencing_final, tentativas_final;
  END IF;
  RAISE NOTICE 'PROVA ok: F-real dois processos, um vencedor, fencing=1 tentativas=1';
END
$conferencia$;
SQL
echo "  ✓ corrida real: exatamente um consumidor reivindicou"

# ---------------------------------------------------------------------------
# 5. DEGRAU 3 — reverter
# ---------------------------------------------------------------------------
echo; echo "DEGRAU 3 — reverter"
aplicar "$ROLLBACK" 2>&1 | sed 's/^NOTICE:  /  /'
executar >/dev/null <<'SQL'
DO $$
DECLARE sobrou text;
BEGIN
  SELECT string_agg(c.relname, ', ') INTO sobrou
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'publicacao\_organica\_%';
  IF sobrou IS NOT NULL THEN RAISE EXCEPTION 'sobrou tabela apos rollback: %', sobrou; END IF;
  -- O que NAO e do v14 continua de pe.
  IF to_regclass('public.criativo_aprovacao') IS NULL
     OR to_regclass('public.cofre_ativo') IS NULL
     OR to_regprocedure('public.cofre_entrada_hash(text,jsonb,jsonb)') IS NULL THEN
    RAISE EXCEPTION 'o rollback levou junto o que nao e dele';
  END IF;
END $$;
SQL
echo "  ✓ v14_99 removeu 5 tabelas e nao tocou em v11/v13"

# ---------------------------------------------------------------------------
# 6. DEGRAU 4 — reaplicar
# ---------------------------------------------------------------------------
echo; echo "DEGRAU 4 — reaplicar"
aplicar "$MIGRATION" 2>&1 | sed 's/^NOTICE:  /  /'
executar -tA -c "SELECT count(*) FROM public.publicacao_organica_job" >/dev/null
echo "  ✓ v14_01 reaplicada sobre o banco revertido"

echo
echo "═══════════════════════════════════════════════════════════════════════"
echo " CICLO COMPLETO: aplicar -> operar -> reverter -> reaplicar"
echo " servidor ${VERSAO}${TZ_SERVIDOR:+ (TimeZone=${TZ_SERVIDOR})}"
echo "═══════════════════════════════════════════════════════════════════════"
