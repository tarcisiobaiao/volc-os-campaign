BEGIN;

CREATE OR REPLACE FUNCTION public.volc_ingest_google_ads_batch_auto(documento jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, extensions
AS $$
DECLARE
  payload_hash text;
BEGIN
  IF jsonb_typeof(documento) <> 'object'
     OR jsonb_typeof(coalesce(documento->'payload','null'::jsonb)) NOT IN ('object','array') THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='documento/payload inválido';
  END IF;
  payload_hash := encode(extensions.digest((documento->'payload')::text, 'sha256'), 'hex');
  RETURN public.volc_ingest_google_ads_batch(
    documento || jsonb_build_object('payload_sha256', payload_hash)
  );
END;
$$;

REVOKE ALL ON FUNCTION public.volc_ingest_google_ads_batch_auto(jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.volc_ingest_google_ads_batch_auto(jsonb)
  TO service_role;

COMMENT ON FUNCTION public.volc_ingest_google_ads_batch_auto(jsonb) IS
  'Fronteira n8n: canoniza o JSONB e calcula o SHA-256 no banco antes da ingestão.';

NOTIFY pgrst, 'reload schema';
COMMIT;
