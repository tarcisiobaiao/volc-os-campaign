-- =============================================================================
-- v27_01 — Bia/Hermes V1: conversas, execuções e eventos da Bia (modo consulta)
--
-- ESTADO: CANDIDATA. Não aplicada. Aplicar exige janela e autorização do
-- Tarcisio, pelo protocolo (scripts/migracao-protocolo.sh). Prova:
-- tools/freedom-lab/db/suites/v27_bia.sh (lab.sh recriar, banco descartável).
-- Rollback: v27_01_rollback.sql.
--
-- O QUE ESTE SCHEMA É, E O QUE NÃO É
--   É o histórico operacional da conversa da Bia: quem perguntou o quê, em que
--   estado ficou cada envio ao Hermes e o recibo de cada passo. NÃO é ledger
--   financeiro: nenhum custo, receita, conversão ou lucro do VOLC passa a
--   depender destas tabelas, e nenhuma view de negócio as lê.
--
-- O QUE GARANTE (é o banco, não o processo):
--   1. schema PRIVADO `agente_bia`: fora do Data API; anon, authenticated e
--      service_role sem USAGE no schema e sem privilégio nas tabelas; RLS ligada;
--   2. acesso só por 11 RPCs nomeadas em `public`, SECURITY DEFINER, com
--      search_path fixo, EXECUTE só para service_role. Toda RPC recebe o dono
--      (auth UUID que o backend apurou do token) e filtra por ele: não existe
--      chamada que leia conversa de outro dono;
--   3. idempotência: UNIQUE (dono, request_id); repetição com a mesma impressão
--      (sha256 de texto + contexto, calculada pelo backend) devolve a mesma
--      execução; com outra impressão ou outra conversa é `conflito`;
--   4. no máximo UMA execução em voo (queued/running) por dono (índice único
--      parcial), limite por minuto e bloqueio da conversa com execução
--      `uncertain` — tudo sob trava consultiva por dono;
--   5. transições fechadas por gatilho; identidade da execução imutável;
--      resposta só existe em `succeeded`; eventos append-only;
--   6. o id da sessão Hermes (`sessao_motor`) nunca sai pelas RPCs de leitura;
--   7. retenção: `agente_bia.expurgar(dias)` (180 por padrão), só para o dono
--      do schema; conversa some junto com o usuário do auth (ON DELETE CASCADE).
-- =============================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $pre$
BEGIN
  IF to_regnamespace('agente_bia') IS NOT NULL THEN
    RAISE EXCEPTION 'v27_01: schema agente_bia já existe; não reaplica por cima'
      USING ERRCODE = '55000';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
     OR to_regclass('auth.users') IS NULL THEN
    RAISE EXCEPTION 'v27_01: base errada (faltam papéis do Supabase ou auth.users)'
      USING ERRCODE = '55000';
  END IF;
END
$pre$;

CREATE SCHEMA agente_bia;
REVOKE ALL ON SCHEMA agente_bia FROM PUBLIC, anon, authenticated, service_role;

-- ──────────────────────────────────────────────────────────── conversas ──
CREATE TABLE agente_bia.conversa (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  dono            uuid        NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  -- ⚠️ id da sessão no Hermes: gerado pelo backend, nunca devolvido ao navegador
  sessao_motor    text        NOT NULL UNIQUE CHECK (sessao_motor ~ '^volc_[0-9a-f]{32}$'),
  titulo          text        CHECK (titulo IS NULL OR length(titulo) BETWEEN 1 AND 120),
  criada_em       timestamptz NOT NULL DEFAULT now(),
  atualizada_em   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT conversa_id_dono UNIQUE (id, dono)
);
CREATE INDEX conversa_dono_recente ON agente_bia.conversa (dono, atualizada_em DESC);

-- ──────────────────────────────────────────────────────────── execuções ──
CREATE TABLE agente_bia.execucao (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  conversa_id     uuid        NOT NULL,
  dono            uuid        NOT NULL,
  request_id      uuid        NOT NULL,
  impressao       text        NOT NULL CHECK (impressao ~ '^[0-9a-f]{64}$'),
  entrada         text        NOT NULL CHECK (length(entrada) BETWEEN 1 AND 8000),
  contexto        jsonb       CHECK (contexto IS NULL OR (jsonb_typeof(contexto) = 'object'
                                                          AND pg_column_size(contexto) <= 2048)),
  estado          text        NOT NULL DEFAULT 'queued' CHECK (estado IN
                    ('queued', 'running', 'succeeded', 'failed', 'uncertain', 'cancelled')),
  resposta        text        CHECK (resposta IS NULL OR length(resposta) <= 20100),
  erro_codigo     text        CHECK (erro_codigo IS NULL OR erro_codigo ~ '^[a-z_]{3,40}$'),
  detalhe         jsonb       NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(detalhe) = 'object'
                                                                  AND pg_column_size(detalhe) <= 4096),
  criada_em       timestamptz NOT NULL DEFAULT now(),
  iniciada_em     timestamptz,
  terminada_em    timestamptz,
  -- o dono da execução é o dono da conversa, por FK composta
  CONSTRAINT execucao_conversa_do_dono FOREIGN KEY (conversa_id, dono)
    REFERENCES agente_bia.conversa (id, dono) ON DELETE CASCADE,
  CONSTRAINT execucao_idempotente UNIQUE (dono, request_id),
  CONSTRAINT execucao_resposta_so_no_sucesso CHECK ((estado = 'succeeded') = (resposta IS NOT NULL)),
  CONSTRAINT execucao_codigo_so_em_falha CHECK (
    erro_codigo IS NULL OR estado IN ('failed', 'uncertain', 'cancelled')),
  CONSTRAINT execucao_terminal_tem_fim CHECK (
    (estado IN ('queued', 'running')) = (terminada_em IS NULL))
);
-- no máximo UMA execução em voo por dono
CREATE UNIQUE INDEX execucao_uma_em_voo_por_dono
  ON agente_bia.execucao (dono) WHERE estado IN ('queued', 'running');
CREATE INDEX execucao_da_conversa ON agente_bia.execucao (conversa_id, criada_em);
CREATE INDEX execucao_do_dono_recente ON agente_bia.execucao (dono, criada_em DESC);

-- ───────────────────────────────────────────────────────────── eventos ──
CREATE TABLE agente_bia.evento (
  id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  execucao_id     uuid        NOT NULL REFERENCES agente_bia.execucao (id) ON DELETE CASCADE,
  tipo            text        NOT NULL CHECK (tipo IN
                    ('reservada', 'iniciada', 'concluida', 'expirada', 'contexto_lido',
                     'reconciliada', 'reconciliacao_inconclusiva', 'conclusao_tardia_ignorada')),
  de              text,
  para            text,
  detalhe         jsonb       NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(detalhe) = 'object'
                                                                  AND pg_column_size(detalhe) <= 4096),
  criado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX evento_da_execucao ON agente_bia.evento (execucao_id, id);

ALTER TABLE agente_bia.conversa ENABLE ROW LEVEL SECURITY;
ALTER TABLE agente_bia.execucao ENABLE ROW LEVEL SECURITY;
ALTER TABLE agente_bia.evento   ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA agente_bia FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA agente_bia FROM PUBLIC, anon, authenticated, service_role;

-- ─────────────────────────────────────────────────────────── gatilhos ──
CREATE FUNCTION agente_bia.guarda_execucao() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $f$
DECLARE
  permitidas text[];
BEGIN
  IF (NEW.id, NEW.conversa_id, NEW.dono, NEW.request_id, NEW.impressao, NEW.entrada,
      NEW.contexto, NEW.criada_em)
     IS DISTINCT FROM
     (OLD.id, OLD.conversa_id, OLD.dono, OLD.request_id, OLD.impressao, OLD.entrada,
      OLD.contexto, OLD.criada_em) THEN
    RAISE EXCEPTION 'agente_bia: a identidade da execução é imutável' USING ERRCODE = '55000';
  END IF;
  IF NEW.estado IS DISTINCT FROM OLD.estado THEN
    permitidas := CASE OLD.estado
      WHEN 'queued'    THEN ARRAY['running', 'cancelled']
      WHEN 'running'   THEN ARRAY['succeeded', 'failed', 'uncertain']
      WHEN 'uncertain' THEN ARRAY['succeeded', 'failed']
      ELSE ARRAY[]::text[]
    END;
    IF NOT (NEW.estado = ANY (permitidas)) THEN
      RAISE EXCEPTION 'agente_bia: transição % → % recusada', OLD.estado, NEW.estado
        USING ERRCODE = '55000';
    END IF;
  ELSIF OLD.estado IN ('succeeded', 'failed', 'cancelled') THEN
    RAISE EXCEPTION 'agente_bia: execução terminal não muda' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END
$f$;
CREATE TRIGGER execucao_guarda BEFORE UPDATE ON agente_bia.execucao
  FOR EACH ROW EXECUTE FUNCTION agente_bia.guarda_execucao();

CREATE FUNCTION agente_bia.evento_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $f$
BEGIN
  RAISE EXCEPTION 'agente_bia: evento é append-only (% recusado)', TG_OP USING ERRCODE = '55000';
END
$f$;
CREATE TRIGGER evento_sem_update BEFORE UPDATE ON agente_bia.evento
  FOR EACH ROW EXECUTE FUNCTION agente_bia.evento_append_only();
CREATE TRIGGER evento_sem_truncate BEFORE TRUNCATE ON agente_bia.evento
  FOR EACH STATEMENT EXECUTE FUNCTION agente_bia.evento_append_only();

-- ───────────────────────────────────────────── projeções (sem sessão) ──
CREATE FUNCTION agente_bia.json_conversa(c agente_bia.conversa) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $f$
  SELECT jsonb_build_object('id', c.id, 'titulo', c.titulo,
                            'criada_em', c.criada_em, 'atualizada_em', c.atualizada_em)
$f$;

CREATE FUNCTION agente_bia.json_execucao(e agente_bia.execucao) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $f$
  SELECT jsonb_build_object('id', e.id, 'conversa_id', e.conversa_id, 'request_id', e.request_id,
                            'estado', e.estado, 'entrada', e.entrada, 'resposta', e.resposta,
                            'erro_codigo', e.erro_codigo, 'contexto', e.contexto,
                            'criada_em', e.criada_em, 'terminada_em', e.terminada_em)
$f$;

CREATE FUNCTION agente_bia.evento(p_execucao uuid, p_tipo text, p_de text, p_para text,
                                  p_detalhe jsonb) RETURNS void
LANGUAGE sql SET search_path = pg_catalog, pg_temp AS $f$
  INSERT INTO agente_bia.evento (execucao_id, tipo, de, para, detalhe)
  VALUES (p_execucao, p_tipo, p_de, p_para, coalesce(p_detalhe, '{}'::jsonb))
$f$;

-- ──────────────────────────────────────────────────────────────── RPCs ──
CREATE FUNCTION public.volc_agente_criar_conversa(p_dono uuid, p_sessao_motor text, p_titulo text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
DECLARE c agente_bia.conversa;
BEGIN
  INSERT INTO agente_bia.conversa (dono, sessao_motor, titulo)
  VALUES (p_dono, p_sessao_motor, nullif(btrim(p_titulo), ''))
  RETURNING * INTO c;
  RETURN agente_bia.json_conversa(c);
END
$f$;

CREATE FUNCTION public.volc_agente_listar_conversas(p_dono uuid, p_limite integer)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
  SELECT coalesce(jsonb_agg(agente_bia.json_conversa(c) ORDER BY c.atualizada_em DESC), '[]'::jsonb)
    FROM (SELECT * FROM agente_bia.conversa
           WHERE dono = p_dono
           ORDER BY atualizada_em DESC
           LIMIT greatest(1, least(coalesce(p_limite, 20), 50))) c
$f$;

CREATE FUNCTION public.volc_agente_historico(p_dono uuid, p_conversa uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
  SELECT jsonb_build_object(
           'conversa', agente_bia.json_conversa(c),
           'execucoes', coalesce((SELECT jsonb_agg(agente_bia.json_execucao(e) ORDER BY e.criada_em, e.id)
                                    FROM agente_bia.execucao e WHERE e.conversa_id = c.id), '[]'::jsonb))
    FROM agente_bia.conversa c
   WHERE c.id = p_conversa AND c.dono = p_dono
$f$;

CREATE FUNCTION public.volc_agente_execucao(p_dono uuid, p_execucao uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
  SELECT agente_bia.json_execucao(e) FROM agente_bia.execucao e
   WHERE e.id = p_execucao AND e.dono = p_dono
$f$;

CREATE FUNCTION public.volc_agente_reservar(p_dono uuid, p_conversa uuid, p_request_id uuid,
                                            p_entrada text, p_impressao text,
                                            p_limite_por_minuto integer, p_contexto jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
DECLARE
  e agente_bia.execucao;
  recentes integer;
BEGIN
  -- Serializa as reservas do MESMO dono; donos diferentes não se esperam.
  PERFORM pg_advisory_xact_lock(hashtextextended('agente_bia:' || p_dono::text, 0));

  SELECT * INTO e FROM agente_bia.execucao WHERE dono = p_dono AND request_id = p_request_id;
  IF FOUND THEN
    IF e.conversa_id = p_conversa AND e.impressao = p_impressao THEN
      RETURN jsonb_build_object('resultado', 'repetida', 'execucao', agente_bia.json_execucao(e));
    END IF;
    RETURN jsonb_build_object('resultado', 'conflito');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM agente_bia.conversa WHERE id = p_conversa AND dono = p_dono) THEN
    RETURN jsonb_build_object('resultado', 'conversa_inexistente');
  END IF;
  IF EXISTS (SELECT 1 FROM agente_bia.execucao
              WHERE conversa_id = p_conversa AND estado = 'uncertain') THEN
    RETURN jsonb_build_object('resultado', 'bloqueada_incerta');
  END IF;
  IF EXISTS (SELECT 1 FROM agente_bia.execucao
              WHERE dono = p_dono AND estado IN ('queued', 'running')) THEN
    RETURN jsonb_build_object('resultado', 'ocupado');
  END IF;
  SELECT count(*) INTO recentes FROM agente_bia.execucao
   WHERE dono = p_dono AND criada_em > now() - interval '60 seconds';
  IF recentes >= greatest(1, least(coalesce(p_limite_por_minuto, 6), 30)) THEN
    RETURN jsonb_build_object('resultado', 'limite');
  END IF;

  INSERT INTO agente_bia.execucao (conversa_id, dono, request_id, impressao, entrada, contexto)
  VALUES (p_conversa, p_dono, p_request_id, p_impressao, p_entrada, p_contexto)
  RETURNING * INTO e;
  UPDATE agente_bia.conversa SET atualizada_em = now() WHERE id = p_conversa;
  PERFORM agente_bia.evento(e.id, 'reservada', NULL, 'queued', '{}'::jsonb);
  RETURN jsonb_build_object('resultado', 'nova', 'execucao', agente_bia.json_execucao(e));
END
$f$;

CREATE FUNCTION public.volc_agente_iniciar(p_dono uuid, p_execucao uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
DECLARE e agente_bia.execucao; s text;
BEGIN
  UPDATE agente_bia.execucao SET estado = 'running', iniciada_em = now()
   WHERE id = p_execucao AND dono = p_dono AND estado = 'queued'
   RETURNING * INTO e;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  SELECT sessao_motor INTO s FROM agente_bia.conversa WHERE id = e.conversa_id;
  PERFORM agente_bia.evento(e.id, 'iniciada', 'queued', 'running', '{}'::jsonb);
  RETURN jsonb_build_object('sessao_motor', s, 'entrada', e.entrada, 'contexto', e.contexto);
END
$f$;

CREATE FUNCTION public.volc_agente_concluir(p_dono uuid, p_execucao uuid, p_estado text,
                                            p_resposta text, p_erro_codigo text, p_detalhe jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
DECLARE e agente_bia.execucao;
BEGIN
  IF p_estado NOT IN ('succeeded', 'failed', 'uncertain') THEN
    RAISE EXCEPTION 'agente_bia: conclusão para % recusada', p_estado USING ERRCODE = '22023';
  END IF;
  SELECT * INTO e FROM agente_bia.execucao WHERE id = p_execucao AND dono = p_dono FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'agente_bia: execução não encontrada' USING ERRCODE = 'P0002';
  END IF;
  IF e.estado <> 'running' THEN
    -- Já expirada/decidida por outro caminho: a conclusão tardia é registrada e
    -- ignorada. Nunca reabre nem sobrescreve.
    PERFORM agente_bia.evento(e.id, 'conclusao_tardia_ignorada', e.estado, p_estado,
                              jsonb_build_object('erro_codigo', p_erro_codigo));
    RETURN agente_bia.json_execucao(e);
  END IF;
  UPDATE agente_bia.execucao
     SET estado = p_estado,
         resposta = CASE WHEN p_estado = 'succeeded' THEN p_resposta END,
         erro_codigo = CASE WHEN p_estado = 'succeeded' THEN NULL ELSE p_erro_codigo END,
         detalhe = coalesce(p_detalhe, '{}'::jsonb),
         terminada_em = now()
   WHERE id = e.id
   RETURNING * INTO e;
  PERFORM agente_bia.evento(e.id, 'concluida', 'running', p_estado,
                            coalesce(p_detalhe, '{}'::jsonb)
                              || jsonb_strip_nulls(jsonb_build_object('erro_codigo', p_erro_codigo)));
  RETURN agente_bia.json_execucao(e);
END
$f$;

CREATE FUNCTION public.volc_agente_expirar(p_dono uuid, p_segundos integer)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
DECLARE r record; n integer := 0;
BEGIN
  FOR r IN SELECT id, estado FROM agente_bia.execucao
            WHERE dono = p_dono AND estado IN ('queued', 'running')
              AND coalesce(iniciada_em, criada_em) < now() - make_interval(secs => greatest(p_segundos, 30))
            FOR UPDATE
  LOOP
    -- queued nunca saiu para o Hermes (iniciar é atômico): cancelada é FATO.
    -- running pode ter saído: só incerta.
    UPDATE agente_bia.execucao
       SET estado = CASE WHEN r.estado = 'queued' THEN 'cancelled' ELSE 'uncertain' END,
           erro_codigo = 'processo_interrompido',
           terminada_em = now()
     WHERE id = r.id;
    PERFORM agente_bia.evento(r.id, 'expirada', r.estado,
                              CASE WHEN r.estado = 'queued' THEN 'cancelled' ELSE 'uncertain' END,
                              '{}'::jsonb);
    n := n + 1;
  END LOOP;
  RETURN n;
END
$f$;

CREATE FUNCTION public.volc_agente_para_reconciliar(p_dono uuid, p_execucao uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
  SELECT jsonb_build_object('sessao_motor', c.sessao_motor, 'entrada', e.entrada, 'contexto', e.contexto)
    FROM agente_bia.execucao e JOIN agente_bia.conversa c ON c.id = e.conversa_id
   WHERE e.id = p_execucao AND e.dono = p_dono AND e.estado = 'uncertain'
$f$;

CREATE FUNCTION public.volc_agente_reconciliar(p_dono uuid, p_execucao uuid, p_estado text,
                                               p_resposta text, p_detalhe jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
DECLARE e agente_bia.execucao;
BEGIN
  IF p_estado NOT IN ('succeeded', 'failed') THEN
    RAISE EXCEPTION 'agente_bia: reconciliação para % recusada', p_estado USING ERRCODE = '22023';
  END IF;
  UPDATE agente_bia.execucao
     SET estado = p_estado,
         resposta = CASE WHEN p_estado = 'succeeded' THEN p_resposta END,
         erro_codigo = CASE WHEN p_estado = 'succeeded' THEN NULL ELSE erro_codigo END,
         detalhe = detalhe || coalesce(p_detalhe, '{}'::jsonb)
   WHERE id = p_execucao AND dono = p_dono AND estado = 'uncertain'
   RETURNING * INTO e;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'agente_bia: só execução incerta é reconciliada' USING ERRCODE = '55000';
  END IF;
  PERFORM agente_bia.evento(e.id, 'reconciliada', 'uncertain', p_estado, coalesce(p_detalhe, '{}'::jsonb));
  RETURN agente_bia.json_execucao(e);
END
$f$;

CREATE FUNCTION public.volc_agente_registrar_evento(p_dono uuid, p_execucao uuid, p_tipo text,
                                                    p_detalhe jsonb)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $f$
BEGIN
  IF p_tipo NOT IN ('contexto_lido', 'reconciliacao_inconclusiva') THEN
    RAISE EXCEPTION 'agente_bia: evento % não é registrável pela API', p_tipo USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agente_bia.execucao WHERE id = p_execucao AND dono = p_dono) THEN
    RAISE EXCEPTION 'agente_bia: execução não encontrada' USING ERRCODE = 'P0002';
  END IF;
  PERFORM agente_bia.evento(p_execucao, p_tipo, NULL, NULL, coalesce(p_detalhe, '{}'::jsonb));
END
$f$;

-- ───────────────────────────────────────────────────────────── retenção ──
-- Só o dono do schema executa (job manual/cron do operador). Não é RPC.
CREATE FUNCTION agente_bia.expurgar(p_dias integer DEFAULT 180)
RETURNS integer LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $f$
DECLARE n integer;
BEGIN
  IF p_dias < 30 THEN
    RAISE EXCEPTION 'agente_bia: retenção mínima é 30 dias' USING ERRCODE = '22023';
  END IF;
  DELETE FROM agente_bia.conversa c
   WHERE c.atualizada_em < now() - make_interval(days => p_dias)
     AND NOT EXISTS (SELECT 1 FROM agente_bia.execucao e
                      WHERE e.conversa_id = c.id AND e.estado IN ('queued', 'running', 'uncertain'));
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$f$;

-- ────────────────────────────────────────────────────────────── grants ──
DO $g$
DECLARE f text;
BEGIN
  FOREACH f IN ARRAY ARRAY[
    'public.volc_agente_criar_conversa(uuid, text, text)',
    'public.volc_agente_listar_conversas(uuid, integer)',
    'public.volc_agente_historico(uuid, uuid)',
    'public.volc_agente_execucao(uuid, uuid)',
    'public.volc_agente_reservar(uuid, uuid, uuid, text, text, integer, jsonb)',
    'public.volc_agente_iniciar(uuid, uuid)',
    'public.volc_agente_concluir(uuid, uuid, text, text, text, jsonb)',
    'public.volc_agente_expirar(uuid, integer)',
    'public.volc_agente_para_reconciliar(uuid, uuid)',
    'public.volc_agente_reconciliar(uuid, uuid, text, text, jsonb)',
    'public.volc_agente_registrar_evento(uuid, uuid, text, jsonb)']
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated', f);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', f);
  END LOOP;
END
$g$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA agente_bia FROM PUBLIC, anon, authenticated, service_role;

COMMIT;
