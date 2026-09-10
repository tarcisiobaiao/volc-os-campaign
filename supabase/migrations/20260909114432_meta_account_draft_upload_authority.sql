-- Explicit operator-issued account permission. Never issued by an editable draft.
BEGIN;
CREATE TABLE IF NOT EXISTS meta_media_private.account_upload_grant (
  owner_id text NOT NULL,
  account_ref text NOT NULL CHECK(length(account_ref) BETWEEN 8 AND 180),
  issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  revoked_at timestamptz,
  authority_note text NOT NULL CHECK(length(authority_note) BETWEEN 10 AND 500),
  PRIMARY KEY(owner_id,account_ref)
);
ALTER TABLE meta_media_private.account_upload_grant ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_media_private.account_upload_grant FORCE ROW LEVEL SECURITY;
REVOKE ALL ON meta_media_private.account_upload_grant FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION meta_media_private.check_draft_upload(
  p_owner_id text,p_draft_ref uuid,p_account_ref text,p_master_refs uuid[])
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
  grant_row meta_media_private.draft_upload_grant;
  ref uuid;
  current_draft jsonb;
  account_allowed boolean;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_owner_id IS NULL OR p_draft_ref IS NULL OR p_account_ref IS NULL
     OR p_master_refs IS NULL OR cardinality(p_master_refs) NOT BETWEEN 1 AND 10
     OR array_position(p_master_refs,NULL) IS NOT NULL
     OR (SELECT count(DISTINCT x) FROM unnest(p_master_refs) x)<>cardinality(p_master_refs) THEN
    RETURN jsonb_build_object('allowed',false,'reason','META_DRAFT_UPLOAD_SELECTION_INVALID');
  END IF;
  SELECT d.draft INTO current_draft FROM public.trafego_meta_campaign_draft d
    WHERE d.owner_id=p_owner_id AND d.draft_ref=p_draft_ref
      AND d.draft->>'accountRef'=p_account_ref AND d.archived_at IS NULL;
  IF NOT FOUND THEN RETURN jsonb_build_object('allowed',false,'reason','META_DRAFT_UPLOAD_CONTEXT_CHANGED'); END IF;
  SELECT EXISTS(SELECT 1 FROM meta_media_private.account_upload_grant g
    WHERE g.owner_id=p_owner_id AND g.account_ref=p_account_ref AND g.revoked_at IS NULL)
    INTO account_allowed;
  IF NOT account_allowed THEN
    SELECT * INTO grant_row FROM meta_media_private.draft_upload_grant g
      WHERE g.owner_id=p_owner_id AND g.draft_ref=p_draft_ref AND g.account_ref=p_account_ref
        AND g.revoked_at IS NULL AND g.expires_at>statement_timestamp();
    IF NOT FOUND THEN RETURN jsonb_build_object('allowed',false,'reason','META_DRAFT_UPLOAD_NOT_AUTHORIZED'); END IF;
  END IF;
  FOREACH ref IN ARRAY p_master_refs LOOP
    IF NOT EXISTS(SELECT 1 FROM public.criativo_master m JOIN public.criativo_job j ON j.id=m.job_id
      WHERE m.id=ref AND j.criado_por::text=p_owner_id AND m.arquivado_em IS NULL
        AND m.content_hash IS NOT NULL
        AND (account_allowed OR m.content_hash=grant_row.master_hashes->>ref::text))
      OR NOT EXISTS(SELECT 1 FROM public.trafego_meta_rascunho_pack s
        WHERE s.owner_id::text=p_owner_id AND s.draft_ref=p_draft_ref AND ref=ANY(s.master_refs)
          AND EXISTS(SELECT 1 FROM jsonb_array_elements(current_draft->'conjuntos') a WHERE a->>'key'=s.adset_key)) THEN
      RETURN jsonb_build_object('allowed',false,'reason','META_DRAFT_UPLOAD_CONTEXT_CHANGED');
    END IF;
  END LOOP;
  RETURN jsonb_build_object('allowed',true,
    'scope',CASE WHEN account_allowed THEN 'ACCOUNT_OWNED_DRAFTS' ELSE 'DRAFT_SELECTED_MEDIA_ONLY' END,
    'expires_at',CASE WHEN account_allowed THEN NULL ELSE grant_row.expires_at END);
END $$;
REVOKE ALL ON FUNCTION meta_media_private.check_draft_upload(text,uuid,text,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION meta_media_private.check_draft_upload(text,uuid,text,uuid[]) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
