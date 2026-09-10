-- Recoverable deletion: preserve draft, packs, files and external receipts.
BEGIN;
ALTER TABLE public.trafego_meta_campaign_draft ADD COLUMN IF NOT EXISTS archived_at timestamptz;
CREATE OR REPLACE FUNCTION meta_draft_private.guard_archived_draft()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
  IF OLD.archived_at IS NOT NULL THEN RAISE EXCEPTION 'META_DRAFT_ARCHIVED'; END IF;
  IF NEW.archived_at IS NOT NULL THEN
    UPDATE meta_media_private.draft_upload_grant SET revoked_at=clock_timestamp()
      WHERE owner_id=OLD.owner_id AND draft_ref=OLD.draft_ref AND revoked_at IS NULL;
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION meta_draft_private.guard_archived_draft() FROM PUBLIC,anon,authenticated,service_role;
DROP TRIGGER IF EXISTS guard_archived_draft ON public.trafego_meta_campaign_draft;
CREATE TRIGGER guard_archived_draft BEFORE UPDATE ON public.trafego_meta_campaign_draft
FOR EACH ROW EXECUTE FUNCTION meta_draft_private.guard_archived_draft();

CREATE OR REPLACE FUNCTION meta_draft_private.archive_campaign_draft(p_owner_id text,p_draft_ref uuid,p_expected_version integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE saved public.trafego_meta_campaign_draft;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_owner_id IS NULL OR p_draft_ref IS NULL OR p_expected_version IS NULL OR p_expected_version<1 THEN
    RAISE EXCEPTION 'META_DRAFT_INVALID';
  END IF;
  SELECT * INTO saved FROM public.trafego_meta_campaign_draft
    WHERE owner_id=p_owner_id AND draft_ref=p_draft_ref FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF saved.archived_at IS NULL THEN
    IF saved.version<>p_expected_version THEN RAISE EXCEPTION 'META_DRAFT_VERSION_CONFLICT'; END IF;
    UPDATE public.trafego_meta_campaign_draft SET archived_at=clock_timestamp(),version=version+1,updated_at=clock_timestamp()
      WHERE owner_id=p_owner_id AND draft_ref=p_draft_ref RETURNING * INTO saved;
  END IF;
  RETURN jsonb_build_object('draft_ref',saved.draft_ref,'version',saved.version,'archived',true,'archived_at',saved.archived_at);
END $$;
REVOKE ALL ON FUNCTION meta_draft_private.archive_campaign_draft(text,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION meta_draft_private.archive_campaign_draft(text,uuid,integer) TO service_role;
CREATE OR REPLACE FUNCTION public.trafego_meta_campaign_draft_archive(p_owner_id text,p_draft_ref uuid,p_expected_version integer)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $$
  SELECT meta_draft_private.archive_campaign_draft(p_owner_id,p_draft_ref,p_expected_version);
$$;
REVOKE ALL ON FUNCTION public.trafego_meta_campaign_draft_archive(text,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_campaign_draft_archive(text,uuid,integer) TO service_role;

CREATE OR REPLACE FUNCTION meta_draft_private.read_campaign_draft(p_owner_id text,p_draft_ref uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE result jsonb;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  SELECT jsonb_build_object('draft_ref',d.draft_ref,'version',d.version,'draft',d.draft,
    'updated_at',d.updated_at,'scope','DRAFT_ONLY','launch_authorized',false) INTO result
    FROM public.trafego_meta_campaign_draft d
    WHERE d.owner_id=p_owner_id AND d.draft_ref=p_draft_ref AND d.archived_at IS NULL;
  RETURN result;
END $$;
REVOKE ALL ON FUNCTION meta_draft_private.read_campaign_draft(text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION meta_draft_private.read_campaign_draft(text,uuid) TO service_role;
CREATE OR REPLACE FUNCTION public.trafego_meta_campaign_draft_read(p_owner_id text,p_draft_ref uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
  SELECT meta_draft_private.read_campaign_draft(p_owner_id,p_draft_ref);
$$;

CREATE OR REPLACE FUNCTION meta_draft_private.list_campaign_drafts(p_owner_id text,p_offset integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE result jsonb;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_owner_id IS NULL OR length(btrim(p_owner_id)) NOT BETWEEN 1 AND 200
    OR p_offset IS NULL OR p_offset NOT BETWEEN 0 AND 100000 THEN RAISE EXCEPTION 'META_DRAFT_INVALID'; END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.updated_at DESC,t.draft_ref),'[]'::jsonb) INTO result
  FROM (SELECT d.draft_ref,d.version,d.updated_at,left(coalesce(d.draft->>'campaignName',''),160) campaign_name,
    jsonb_array_length(coalesce(d.draft->'conjuntos','[]'::jsonb)) adset_count,
    jsonb_array_length(coalesce(d.draft->'variations','[]'::jsonb)) ad_count
    FROM public.trafego_meta_campaign_draft d WHERE d.owner_id=p_owner_id AND d.archived_at IS NULL
    ORDER BY d.updated_at DESC,d.draft_ref LIMIT 21 OFFSET p_offset) t;
  RETURN result;
END $$;
NOTIFY pgrst,'reload schema';
COMMIT;
