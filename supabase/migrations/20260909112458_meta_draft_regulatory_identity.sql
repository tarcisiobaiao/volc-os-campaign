-- Extend editable intent only. No media, plan or launch authority is granted.
-- Guard the exact existing clause so all owner/CAS/archive/security behavior survives.
BEGIN;
DO $migration$
DECLARE
  definition text := pg_get_functiondef('public.trafego_meta_campaign_draft_save(text,uuid,integer,jsonb)'::regprocedure);
  previous_clause text := $old$'publico','posicionamentoModo','posicionamentoValores','mensuracao'] <> '{}'::jsonb THEN$old$;
  current_clause text := $new$'publico','posicionamentoModo','posicionamentoValores','mensuracao','regulatoryIdentityRef'] <> '{}'::jsonb
      OR (aset ? 'regulatoryIdentityRef' AND (
        jsonb_typeof(aset->'regulatoryIdentityRef') IS DISTINCT FROM 'string'
        OR (aset->>'regulatoryIdentityRef') !~ '^metareg_[a-f0-9]{32}$')) THEN$new$;
BEGIN
  IF strpos(definition,current_clause)>0 THEN
    RETURN; -- safe reapplication; already has the exact validated clause
  END IF;
  IF (length(definition)-length(replace(definition,previous_clause,'')))/length(previous_clause) <> 1 THEN
    RAISE EXCEPTION 'META_DRAFT_REGULATORY_MIGRATION_SOURCE_CHANGED';
  END IF;
  EXECUTE replace(definition,previous_clause,current_clause);
END $migration$;
NOTIFY pgrst, 'reload schema';
COMMIT;
