-- Only summaries, only through the authenticated backend. No table grants.
BEGIN;
CREATE SCHEMA IF NOT EXISTS meta_draft_private;
REVOKE ALL ON SCHEMA meta_draft_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA meta_draft_private TO service_role;

CREATE OR REPLACE FUNCTION meta_draft_private.list_campaign_drafts(p_owner_id text, p_offset integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE result jsonb;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_owner_id IS NULL OR length(btrim(p_owner_id)) NOT BETWEEN 1 AND 200
     OR p_offset IS NULL OR p_offset NOT BETWEEN 0 AND 100000 THEN
    RAISE EXCEPTION 'META_DRAFT_INVALID';
  END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.updated_at DESC, t.draft_ref), '[]'::jsonb) INTO result
  FROM (
    SELECT d.draft_ref,d.version,d.updated_at,
      left(coalesce(d.draft->>'campaignName',''),160) AS campaign_name,
      jsonb_array_length(coalesce(d.draft->'conjuntos','[]'::jsonb)) AS adset_count,
      jsonb_array_length(coalesce(d.draft->'variations','[]'::jsonb)) AS ad_count
    FROM public.trafego_meta_campaign_draft d
    WHERE d.owner_id=p_owner_id
    ORDER BY d.updated_at DESC,d.draft_ref LIMIT 21 OFFSET p_offset
  ) t;
  RETURN result;
END $$;
REVOKE ALL ON FUNCTION meta_draft_private.list_campaign_drafts(text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION meta_draft_private.list_campaign_drafts(text,integer) TO service_role;

CREATE OR REPLACE FUNCTION public.trafego_meta_campaign_draft_list(p_owner_id text,p_offset integer DEFAULT 0)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
  SELECT meta_draft_private.list_campaign_drafts(p_owner_id,p_offset);
$$;
REVOKE ALL ON FUNCTION public.trafego_meta_campaign_draft_list(text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_campaign_draft_list(text,integer) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
