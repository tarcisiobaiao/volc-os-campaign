-- CANDIDATA (item 5, 2026-10-17). NÃO APLICADA. Aplicar só com autorização nominal do dono e o sha256 deste arquivo.
-- Estado 'abandoned' para runs do coletor Google Ads v21, por evento append-only, sem apagar nada.
--
-- 1. status ganha 'abandoned' (o CHECK de finished_at continua valendo: abandoned exige finished_at);
-- 2. google_ads_run_abandonment: um evento por run (PK = run_id), append-only, com motivo, minutos sem atividade,
--    última atividade, estado da execução n8n informado pelo reaper, evidência e autor;
-- 3. volc_abandon_google_ads_run(...): única porta para abandonar. Idempotente (2ª chamada devolve 'ja_abandonado'
--    sem escrever), trava o run (FOR UPDATE), só age em 'running', exige > 60 min sem atividade pelo relógio do banco
--    (máximo de started_at e created_at de lote e observação) e exige que o reaper prove que a execução n8n NÃO está
--    ativa ('success', 'error', 'crashed' ou 'canceled'); job longo com lote recente devolve 'nenhuma:atividade_recente';
-- 4. google_ads_run_guard_abandoned: protege contra conclusão tardia. Um UPDATE que tente tirar o run de 'abandoned'
--    (por exemplo, o ON CONFLICT de volc_finish_google_ads_run) não muda status/finished_at/erro; a tentativa fica
--    registrada em receipt.late_activity. Lote tardio é fato append-only: os contadores seguem a verdade do que foi
--    gravado e a chegada tardia fica registrada em receipt.late_activity. Ninguém além da função marca abandoned
--    (guarda contra acidente, não contra quem já tem UPDATE direto e liga a flag de sessão de propósito).
-- Rollback: item5_0001_google_ads_run_abandoned.down.sql (recusa se já houver run abandoned, para não reescrever
-- histórico; nesse caso o rollback seguro é revogar EXECUTE da função).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

ALTER TABLE public.google_ads_collection_run DROP CONSTRAINT google_ads_run_status;
ALTER TABLE public.google_ads_collection_run ADD CONSTRAINT google_ads_run_status
  CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'partial'::text, 'failed'::text, 'abandoned'::text])));

CREATE TABLE public.google_ads_run_abandonment (
  run_id uuid PRIMARY KEY REFERENCES public.google_ads_collection_run(run_id),
  collector text NOT NULL,
  reason text NOT NULL CHECK (reason = 'sem_atividade_alem_do_limite'),
  limit_minutes integer NOT NULL CHECK (limit_minutes >= 60),
  inactive_minutes integer NOT NULL CHECK (inactive_minutes > limit_minutes),
  last_activity_at timestamptz NOT NULL,
  n8n_execution_status text NOT NULL CHECK (n8n_execution_status IN ('success', 'error', 'crashed', 'canceled')),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence) = 'object'),
  decided_by text NOT NULL CHECK (btrim(decided_by) <> ''),
  decided_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER google_ads_run_abandonment_append_only BEFORE DELETE OR UPDATE ON public.google_ads_run_abandonment
  FOR EACH ROW EXECUTE FUNCTION public.google_ads_append_only();
ALTER TABLE public.google_ads_run_abandonment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.google_ads_run_abandonment FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.google_ads_run_abandonment FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.google_ads_run_abandonment TO service_role;

CREATE FUNCTION public.google_ads_run_guard_abandoned() RETURNS trigger
LANGUAGE plpgsql SET search_path TO 'pg_catalog', 'public' AS $$
DECLARE
  v_tentativa jsonb;
BEGIN
  IF OLD.status = 'abandoned' THEN
    IF NEW.status IS DISTINCT FROM OLD.status OR NEW.finished_at IS DISTINCT FROM OLD.finished_at
       OR NEW.error_class IS DISTINCT FROM OLD.error_class OR NEW.error_code IS DISTINCT FROM OLD.error_code
       OR NEW.batches_written IS DISTINCT FROM OLD.batches_written OR NEW.rows_written IS DISTINCT FROM OLD.rows_written THEN
      v_tentativa := jsonb_build_object('at', now(), 'status_pedido', NEW.status, 'finished_at_pedido', NEW.finished_at,
                                        'error_class_pedido', NEW.error_class,
                                        'batches_written_pedido', NEW.batches_written, 'rows_written_pedido', NEW.rows_written);
      NEW.status := OLD.status;
      NEW.finished_at := OLD.finished_at;
      NEW.error_class := OLD.error_class;
      NEW.error_code := OLD.error_code;
      -- contadores (batches_written, rows_written) seguem o que foi de fato gravado; só a chegada fica registrada
      NEW.receipt := OLD.receipt || jsonb_build_object('late_activity',
                       coalesce(OLD.receipt->'late_activity', '[]'::jsonb) || jsonb_build_array(v_tentativa));
    END IF;
  ELSIF NEW.status = 'abandoned' AND coalesce(current_setting('volc.abandono_autorizado', true), '') <> 'on' THEN
    RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'abandoned só pela função volc_abandon_google_ads_run';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER google_ads_run_guard_abandoned BEFORE UPDATE ON public.google_ads_collection_run
  FOR EACH ROW EXECUTE FUNCTION public.google_ads_run_guard_abandoned();

CREATE FUNCTION public.volc_abandon_google_ads_run(p_run_id uuid, p_n8n_execution_status text, p_decided_by text,
                                                   p_evidence jsonb DEFAULT '{}'::jsonb, p_limit_minutes integer DEFAULT 60)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'public' AS $$
DECLARE
  r public.google_ads_collection_run;
  v_last timestamptz;
  v_inativo integer;
BEGIN
  IF p_limit_minutes IS NULL OR p_limit_minutes < 60 THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'limite mínimo é 60 minutos';
  END IF;
  IF p_n8n_execution_status IS NULL OR p_n8n_execution_status NOT IN ('success', 'error', 'crashed', 'canceled') THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'execução n8n ativa ou desconhecida: não abandonar';
  END IF;
  IF p_evidence IS NULL OR jsonb_typeof(p_evidence) <> 'object' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'evidência precisa ser objeto JSON';
  END IF;
  SELECT * INTO r FROM public.google_ads_collection_run WHERE run_id = p_run_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'run inexistente';
  END IF;
  IF r.status = 'abandoned' THEN
    RETURN jsonb_build_object('run_id', r.run_id, 'acao', 'ja_abandonado', 'status', r.status);
  END IF;
  IF r.status <> 'running' THEN
    RETURN jsonb_build_object('run_id', r.run_id, 'acao', 'nenhuma:run_ja_finalizado', 'status', r.status);
  END IF;
  SELECT greatest(r.started_at,
                  (SELECT max(b.created_at) FROM public.google_ads_raw_batch b WHERE b.run_id = r.run_id),
                  (SELECT max(o.created_at) FROM public.google_ads_observation o WHERE o.run_id = r.run_id))
    INTO v_last;
  v_inativo := floor(extract(epoch FROM (now() - v_last)) / 60);
  IF v_inativo <= p_limit_minutes THEN
    RETURN jsonb_build_object('run_id', r.run_id, 'acao', 'nenhuma:atividade_recente', 'status', r.status,
                              'ultima_atividade', v_last, 'minutos_sem_atividade', v_inativo);
  END IF;
  INSERT INTO public.google_ads_run_abandonment (run_id, collector, reason, limit_minutes, inactive_minutes,
                                                 last_activity_at, n8n_execution_status, evidence, decided_by)
  VALUES (r.run_id, r.collector, 'sem_atividade_alem_do_limite', p_limit_minutes, v_inativo, v_last,
          p_n8n_execution_status, p_evidence, p_decided_by);
  PERFORM set_config('volc.abandono_autorizado', 'on', true);
  UPDATE public.google_ads_collection_run
     SET status = 'abandoned', finished_at = now(), error_class = 'abandoned', error_code = 'sem_atividade_alem_do_limite',
         receipt = receipt || jsonb_build_object('abandoned', jsonb_build_object(
                     'at', now(), 'minutos_sem_atividade', v_inativo, 'ultima_atividade', v_last,
                     'n8n_execution_status', p_n8n_execution_status, 'decided_by', p_decided_by))
   WHERE run_id = r.run_id;
  PERFORM set_config('volc.abandono_autorizado', '', true);
  RETURN jsonb_build_object('run_id', r.run_id, 'acao', 'abandonado', 'status', 'abandoned',
                            'ultima_atividade', v_last, 'minutos_sem_atividade', v_inativo);
END $$;
REVOKE ALL ON FUNCTION public.volc_abandon_google_ads_run(uuid, text, text, jsonb, integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.volc_abandon_google_ads_run(uuid, text, text, jsonb, integer) TO service_role;
REVOKE ALL ON FUNCTION public.google_ads_run_guard_abandoned() FROM PUBLIC, anon, authenticated;

COMMIT;
