-- Rollback da candidata item5_0001. Recusa se já existir run 'abandoned' ou evento de abandono: desfazer isso
-- reescreveria histórico. Nesse caso, o rollback seguro é parar novas transições sem tocar dados:
--   REVOKE EXECUTE ON FUNCTION public.volc_abandon_google_ads_run(uuid, text, text, jsonb, integer) FROM service_role;
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM public.google_ads_collection_run WHERE status = 'abandoned')
     OR EXISTS (SELECT 1 FROM public.google_ads_run_abandonment) THEN
    RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'há run abandoned: rollback recusado (use o REVOKE do cabeçalho)';
  END IF;
END $$;
DROP FUNCTION public.volc_abandon_google_ads_run(uuid, text, text, jsonb, integer);
DROP TRIGGER google_ads_run_guard_abandoned ON public.google_ads_collection_run;
DROP FUNCTION public.google_ads_run_guard_abandoned();
DROP TABLE public.google_ads_run_abandonment;
ALTER TABLE public.google_ads_collection_run DROP CONSTRAINT google_ads_run_status;
ALTER TABLE public.google_ads_collection_run ADD CONSTRAINT google_ads_run_status
  CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'partial'::text, 'failed'::text])));
COMMIT;
