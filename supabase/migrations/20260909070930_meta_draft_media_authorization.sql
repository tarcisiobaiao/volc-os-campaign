-- A server-issued grant for exact Studio bytes in one owned draft.
-- No public grant-creation RPC; only the database operator can issue/revoke.
BEGIN;
CREATE SCHEMA IF NOT EXISTS meta_media_private;
REVOKE ALL ON SCHEMA meta_media_private FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA meta_media_private TO service_role;
CREATE TABLE IF NOT EXISTS meta_media_private.draft_upload_grant (
  owner_id text NOT NULL,
  draft_ref uuid NOT NULL,
  account_ref text NOT NULL CHECK(length(account_ref) BETWEEN 8 AND 180),
  master_hashes jsonb NOT NULL CHECK(jsonb_typeof(master_hashes)='object' AND octet_length(master_hashes::text)<=4000),
  issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  authority_note text NOT NULL CHECK(length(authority_note) BETWEEN 10 AND 500),
  PRIMARY KEY(owner_id,draft_ref,account_ref),
  FOREIGN KEY(owner_id,draft_ref) REFERENCES public.trafego_meta_campaign_draft(owner_id,draft_ref),
  CHECK(expires_at>issued_at)
);
ALTER TABLE meta_media_private.draft_upload_grant ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_media_private.draft_upload_grant FORCE ROW LEVEL SECURITY;
REVOKE ALL ON meta_media_private.draft_upload_grant FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION meta_media_private.check_draft_upload(
  p_owner_id text,p_draft_ref uuid,p_account_ref text,p_master_refs uuid[])
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE grant_row meta_media_private.draft_upload_grant; ref uuid; current_draft jsonb;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_owner_id IS NULL OR p_draft_ref IS NULL OR p_account_ref IS NULL
     OR p_master_refs IS NULL OR cardinality(p_master_refs) NOT BETWEEN 1 AND 10
     OR array_position(p_master_refs,NULL) IS NOT NULL
     OR (SELECT count(DISTINCT x) FROM unnest(p_master_refs) x)<>cardinality(p_master_refs) THEN
    RETURN jsonb_build_object('allowed',false,'reason','META_DRAFT_UPLOAD_SELECTION_INVALID');
  END IF;
  SELECT * INTO grant_row FROM meta_media_private.draft_upload_grant g
    WHERE g.owner_id=p_owner_id AND g.draft_ref=p_draft_ref AND g.account_ref=p_account_ref
      AND g.revoked_at IS NULL AND g.expires_at>statement_timestamp();
  IF NOT FOUND THEN RETURN jsonb_build_object('allowed',false,'reason','META_DRAFT_UPLOAD_NOT_AUTHORIZED'); END IF;
  SELECT d.draft INTO current_draft FROM public.trafego_meta_campaign_draft d
    WHERE d.owner_id=p_owner_id AND d.draft_ref=p_draft_ref AND d.draft->>'accountRef'=p_account_ref;
  IF NOT FOUND THEN RETURN jsonb_build_object('allowed',false,'reason','META_DRAFT_UPLOAD_CONTEXT_CHANGED'); END IF;
  FOREACH ref IN ARRAY p_master_refs LOOP
    IF NOT EXISTS(SELECT 1 FROM public.criativo_master m JOIN public.criativo_job j ON j.id=m.job_id
      WHERE m.id=ref AND j.criado_por::text=p_owner_id AND m.arquivado_em IS NULL
        AND m.content_hash=grant_row.master_hashes->>ref::text)
      OR NOT EXISTS(SELECT 1 FROM public.trafego_meta_rascunho_pack s
        WHERE s.owner_id::text=p_owner_id AND s.draft_ref=p_draft_ref AND ref=ANY(s.master_refs)
          AND EXISTS(SELECT 1 FROM jsonb_array_elements(current_draft->'conjuntos') a WHERE a->>'key'=s.adset_key)) THEN
      RETURN jsonb_build_object('allowed',false,'reason','META_DRAFT_UPLOAD_CONTEXT_CHANGED');
    END IF;
  END LOOP;
  RETURN jsonb_build_object('allowed',true,'scope','DRAFT_SELECTED_MEDIA_ONLY','expires_at',grant_row.expires_at);
END $$;
REVOKE ALL ON FUNCTION meta_media_private.check_draft_upload(text,uuid,text,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION meta_media_private.check_draft_upload(text,uuid,text,uuid[]) TO service_role;
CREATE OR REPLACE FUNCTION public.trafego_meta_draft_upload_check(
  p_owner_id text,p_draft_ref uuid,p_account_ref text,p_master_refs uuid[])
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
  SELECT meta_media_private.check_draft_upload(p_owner_id,p_draft_ref,p_account_ref,p_master_refs);
$$;
REVOKE ALL ON FUNCTION public.trafego_meta_draft_upload_check(text,uuid,text,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_draft_upload_check(text,uuid,text,uuid[]) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
