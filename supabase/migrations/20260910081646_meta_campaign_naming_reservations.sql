-- Names are editable intent. Reservations belong to the physical Meta account,
-- never to a BM, owner, topic or funnel. No FK/cascade: numbers are never reused.
BEGIN;
CREATE TABLE IF NOT EXISTS meta_draft_private.campaign_naming_reservation (
  account_id text NOT NULL CHECK(account_id ~ '^[0-9]{1,40}$'),
  campaign_number integer NOT NULL CHECK(campaign_number > 0),
  owner_id text NOT NULL CHECK(length(btrim(owner_id)) BETWEEN 1 AND 200),
  draft_ref uuid NOT NULL,
  account_ref text NOT NULL CHECK(account_ref ~ '^metaacct_[a-f0-9]{24}$'),
  history_count integer NOT NULL CHECK(history_count >= 0),
  history_max integer NOT NULL CHECK(history_max >= 0),
  history_complete boolean NOT NULL CHECK(history_complete),
  reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(account_id,campaign_number),
  UNIQUE(owner_id,draft_ref,account_id)
);
ALTER TABLE meta_draft_private.campaign_naming_reservation ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_draft_private.campaign_naming_reservation FORCE ROW LEVEL SECURITY;
REVOKE ALL ON meta_draft_private.campaign_naming_reservation FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION meta_draft_private.reserve_campaign_number(
  p_owner_id text,p_draft_ref uuid,p_expected_version integer,p_account_id text,
  p_account_ref text,p_history_max integer,p_history_count integer,p_history_complete boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $function$
DECLARE
  saved public.trafego_meta_campaign_draft;
  reservation meta_draft_private.campaign_naming_reservation;
  previous_number bigint;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_owner_id IS NULL OR length(btrim(p_owner_id)) NOT BETWEEN 1 AND 200
    OR p_draft_ref IS NULL OR p_expected_version IS NULL OR p_expected_version<1
    OR p_account_id IS NULL OR p_account_id !~ '^[0-9]{1,40}$'
    OR p_history_complete IS DISTINCT FROM true OR p_history_max IS NULL OR p_history_max<0
    OR p_history_count IS NULL OR p_history_count<0 THEN RAISE EXCEPTION 'META_NAMING_INVALID'; END IF;
  IF p_account_ref IS DISTINCT FROM ('metaacct_' || substr(encode(sha256(convert_to('META_ADS:account:' || p_account_id,'UTF8')),'hex'),1,24)) THEN
    RAISE EXCEPTION 'META_NAMING_ACCOUNT_CHANGED';
  END IF;
  SELECT * INTO saved FROM public.trafego_meta_campaign_draft
    WHERE owner_id=p_owner_id AND draft_ref=p_draft_ref FOR UPDATE;
  IF saved.draft_ref IS NULL THEN RAISE EXCEPTION 'META_DRAFT_NOT_FOUND'; END IF;
  IF saved.archived_at IS NOT NULL THEN RAISE EXCEPTION 'META_DRAFT_ARCHIVED'; END IF;
  IF saved.version<>p_expected_version THEN RAISE EXCEPTION 'META_DRAFT_VERSION_CONFLICT'; END IF;
  IF saved.draft->>'accountRef' IS DISTINCT FROM p_account_ref THEN RAISE EXCEPTION 'META_NAMING_ACCOUNT_CHANGED'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('meta-campaign-naming:' || p_account_id,0));
  SELECT * INTO reservation FROM meta_draft_private.campaign_naming_reservation
    WHERE owner_id=p_owner_id AND draft_ref=p_draft_ref AND account_id=p_account_id;
  IF reservation.draft_ref IS NULL THEN
    SELECT greatest(coalesce(max(campaign_number),0),p_history_max)::bigint INTO previous_number
      FROM meta_draft_private.campaign_naming_reservation WHERE account_id=p_account_id;
    IF previous_number>=2147483647 THEN RAISE EXCEPTION 'META_NAMING_RANGE_EXHAUSTED'; END IF;
    INSERT INTO meta_draft_private.campaign_naming_reservation(
      account_id,campaign_number,owner_id,draft_ref,account_ref,history_count,history_max,history_complete)
    VALUES(p_account_id,(previous_number+1)::integer,p_owner_id,p_draft_ref,p_account_ref,p_history_count,p_history_max,true)
    RETURNING * INTO reservation;
  END IF;
  RETURN jsonb_build_object('campaign_number',reservation.campaign_number,'account_ref',reservation.account_ref,
    'draft_ref',reservation.draft_ref,'history_complete',reservation.history_complete,'history_count',reservation.history_count);
END $function$;
REVOKE ALL ON FUNCTION meta_draft_private.reserve_campaign_number(text,uuid,integer,text,text,integer,integer,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION meta_draft_private.reserve_campaign_number(text,uuid,integer,text,text,integer,integer,boolean) TO service_role;
CREATE OR REPLACE FUNCTION public.trafego_meta_campaign_naming_reserve(
  p_owner_id text,p_draft_ref uuid,p_expected_version integer,p_account_id text,
  p_account_ref text,p_history_max integer,p_history_count integer,p_history_complete boolean)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $function$
  SELECT meta_draft_private.reserve_campaign_number(p_owner_id,p_draft_ref,p_expected_version,p_account_id,
    p_account_ref,p_history_max,p_history_count,p_history_complete);
$function$;
REVOKE ALL ON FUNCTION public.trafego_meta_campaign_naming_reserve(text,uuid,integer,text,text,integer,integer,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_campaign_naming_reserve(text,uuid,integer,text,text,integer,integer,boolean) TO service_role;

CREATE OR REPLACE FUNCTION meta_draft_private.validate_naming_intent(value jsonb)
RETURNS void LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog AS $function$
DECLARE field record; item record; text_limit integer;
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'object'
    OR value - ARRAY['enabled','topic','site','landingType','quiz','conversionLabel','campaignNumber','accountRef','adsetNumbers','adNumbers','generated'] <> '{}'::jsonb
    OR NOT (value ?& ARRAY['enabled','topic','site','landingType','quiz','conversionLabel','adsetNumbers','adNumbers','generated'])
    OR jsonb_typeof(value->'enabled') IS DISTINCT FROM 'boolean'
    OR jsonb_typeof(value->'quiz') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
  FOR field IN SELECT * FROM jsonb_each(value) LOOP
    IF field.key IN ('topic','site','landingType','conversionLabel','accountRef') THEN
      text_limit := CASE field.key WHEN 'topic' THEN 200 WHEN 'site' THEN 80 WHEN 'landingType' THEN 40 WHEN 'accountRef' THEN 180 ELSE 80 END;
      IF jsonb_typeof(field.value) IS DISTINCT FROM 'string' OR length(field.value #>> '{}')>text_limit THEN
        RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
      IF field.key='accountRef' AND (field.value #>> '{}') !~ '^[A-Za-z][A-Za-z0-9:_-]{7,179}$' THEN
        RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
    ELSIF field.key='campaignNumber' THEN
      IF jsonb_typeof(field.value) IS DISTINCT FROM 'number' OR (field.value #>> '{}') !~ '^[0-9]{1,10}$' THEN
        RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
      IF (field.value #>> '{}')::bigint NOT BETWEEN 1 AND 2147483647 THEN RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
    ELSIF field.key IN ('adsetNumbers','adNumbers','generated') THEN
      IF jsonb_typeof(field.value) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
      IF (SELECT count(*) FROM jsonb_each(field.value))>100 THEN RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
      FOR item IN SELECT * FROM jsonb_each(field.value) LOOP
        IF field.key='generated' THEN
          IF item.key !~ '^[A-Za-z0-9:_-]{1,80}$' OR jsonb_typeof(item.value) IS DISTINCT FROM 'string'
            OR length(item.value #>> '{}')>400 THEN RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
        ELSE
          IF (field.key='adsetNumbers' AND item.key !~ '^[a-z0-9][a-z0-9_-]{0,31}$')
            OR (field.key='adNumbers' AND item.key !~ '^[a-z0-9][a-z0-9:_-]{0,64}$')
            OR jsonb_typeof(item.value) IS DISTINCT FROM 'number' OR (item.value #>> '{}') !~ '^[0-9]{1,10}$' THEN
            RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
          IF (item.value #>> '{}')::bigint NOT BETWEEN 1 AND 2147483647 THEN RAISE EXCEPTION 'META_DRAFT_NAMING_INVALID'; END IF;
        END IF;
      END LOOP;
    END IF;
  END LOOP;
END $function$;
REVOKE ALL ON FUNCTION meta_draft_private.validate_naming_intent(jsonb) FROM PUBLIC,anon,authenticated,service_role;

-- Preserve the installed save body (including flexibleTexts and archive guards).
DO $migration$
DECLARE definition text;
  old_clause text := $old$'creativeMode','conjuntos','variations'] <> '{}'::jsonb$old$;
  new_clause text := $new$'creativeMode','conjuntos','variations','naming'] <> '{}'::jsonb$new$;
  anchor text := '  PERFORM public.trafego_meta_draft_refuse_secrets(p_draft);';
  guard text := $guard$
  IF p_draft ? 'naming' THEN
    PERFORM meta_draft_private.validate_naming_intent(p_draft->'naming');
  END IF;
$guard$;
BEGIN
  SELECT pg_get_functiondef('public.trafego_meta_campaign_draft_save(text,uuid,integer,jsonb)'::regprocedure) INTO definition;
  IF position(new_clause IN definition)>0 AND position(guard IN definition)>0 THEN RETURN; END IF;
  IF position(old_clause IN definition)=0 OR position(anchor IN definition)=0
    OR position('validate_naming_intent' IN definition)>0 THEN RAISE EXCEPTION 'META_NAMING_MIGRATION_BASE_MISMATCH'; END IF;
  definition := replace(definition,old_clause,new_clause);
  definition := replace(definition,anchor,anchor || guard);
  EXECUTE definition;
END $migration$;
NOTIFY pgrst,'reload schema';
COMMIT;
