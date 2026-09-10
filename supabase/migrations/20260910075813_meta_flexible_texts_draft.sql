-- Additive to the installed RPC: preserve owner/CAS, archive, identity, post,
-- secret and approval-reset guards rather than replacing their latest body.
BEGIN;
DO $migration$
DECLARE
  definition text;
  old_allowlist text := $old$'mensuracao','regulatoryIdentityRef'] <> '{}'::jsonb$old$;
  new_allowlist text := $new$'mensuracao','regulatoryIdentityRef','flexibleTexts'] <> '{}'::jsonb$new$;
  anchor text := $anchor$  FOR ad IN SELECT * FROM jsonb_array_elements(p_draft->'variations') LOOP$anchor$;
  guard text := $guard$
  -- FLEXIBLE_TEXTS_DRAFT_V1: editable intent, never a publication approval.
  FOR aset IN SELECT * FROM jsonb_array_elements(p_draft->'conjuntos') LOOP
    IF aset ? 'flexibleTexts' THEN
      IF jsonb_typeof(aset->'flexibleTexts') IS DISTINCT FROM 'object'
        OR (aset->'flexibleTexts') - ARRAY['primary_text','headline','description'] <> '{}'::jsonb
        OR jsonb_typeof(aset->'flexibleTexts'->'primary_text') IS DISTINCT FROM 'array'
        OR jsonb_typeof(aset->'flexibleTexts'->'headline') IS DISTINCT FROM 'array'
        OR jsonb_typeof(aset->'flexibleTexts'->'description') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'META_DRAFT_FLEXIBLE_TEXTS_INVALID';
      END IF;
      IF EXISTS (
        SELECT 1 FROM jsonb_each(aset->'flexibleTexts') AS field(key, value)
        WHERE jsonb_array_length(field.value) > 5
      ) THEN RAISE EXCEPTION 'META_DRAFT_FLEXIBLE_TEXTS_INVALID'; END IF;
      IF EXISTS (
        SELECT 1 FROM jsonb_each(aset->'flexibleTexts') AS field(key, value)
        CROSS JOIN LATERAL jsonb_array_elements(field.value) AS option(value)
        WHERE jsonb_typeof(option.value) IS DISTINCT FROM 'string'
          OR length(option.value #>> '{}') > CASE WHEN field.key='primary_text' THEN 2200 ELSE 255 END
      ) THEN RAISE EXCEPTION 'META_DRAFT_FLEXIBLE_TEXTS_INVALID'; END IF;
    END IF;
  END LOOP;
$guard$;
BEGIN
  SELECT pg_get_functiondef('public.trafego_meta_campaign_draft_save(text,uuid,integer,jsonb)'::regprocedure)
    INTO definition;
  IF position(new_allowlist IN definition)>0
    AND position(guard IN definition)>0 THEN RETURN; END IF;
  IF position(old_allowlist IN definition)=0 OR position(anchor IN definition)=0
    OR position('FLEXIBLE_TEXTS_DRAFT_V1' IN definition)>0 THEN
    RAISE EXCEPTION 'META_DRAFT_FLEXIBLE_MIGRATION_BASE_MISMATCH';
  END IF;
  definition := replace(definition,old_allowlist,new_allowlist);
  definition := replace(definition,anchor,guard || anchor);
  EXECUTE definition;
END $migration$;
NOTIFY pgrst, 'reload schema';
COMMIT;
