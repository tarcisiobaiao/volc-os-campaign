-- Editable intent only. Existing pack/adset selections remain independently versioned.
BEGIN;
CREATE TABLE IF NOT EXISTS public.trafego_meta_campaign_draft (
  owner_id text NOT NULL CHECK(length(btrim(owner_id)) BETWEEN 1 AND 200),
  draft_ref uuid NOT NULL,
  version integer NOT NULL CHECK(version > 0),
  draft jsonb NOT NULL CHECK(jsonb_typeof(draft)='object' AND octet_length(draft::text)<=120000),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(owner_id,draft_ref)
);
ALTER TABLE public.trafego_meta_campaign_draft ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_campaign_draft FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.trafego_meta_campaign_draft FROM PUBLIC,anon,authenticated,service_role;

-- Defense against privileged callers bypassing the typed HTTP endpoint.
CREATE OR REPLACE FUNCTION public.trafego_meta_draft_refuse_secrets(p_value jsonb,p_depth integer DEFAULT 0)
RETURNS void LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE item record; value jsonb;
BEGIN
  IF p_depth>12 THEN RAISE EXCEPTION 'META_DRAFT_INVALID'; END IF;
  IF jsonb_typeof(p_value)='object' THEN
    FOR item IN SELECT * FROM jsonb_each(p_value) LOOP
      IF item.key ~* '(token|secret|password|credential|api.?key|approval|access.?key)'
         OR item.key IN ('account_id','campaign_id','adset_id','ad_id','image_hash','service_role') THEN
        RAISE EXCEPTION 'META_DRAFT_SECRET_FORBIDDEN';
      END IF;
      PERFORM public.trafego_meta_draft_refuse_secrets(item.value,p_depth+1);
    END LOOP;
  ELSIF jsonb_typeof(p_value)='array' THEN
    FOR value IN SELECT * FROM jsonb_array_elements(p_value) LOOP
      PERFORM public.trafego_meta_draft_refuse_secrets(value,p_depth+1);
    END LOOP;
  ELSIF jsonb_typeof(p_value)='string' AND p_value::text ~*
      '(sk-(proj-|ant-)?[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,}|EAA[A-Za-z0-9]{40,}|Bearer[[:space:]]+[A-Za-z0-9._-]{12,}|eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|access_token=)' THEN
    RAISE EXCEPTION 'META_DRAFT_SECRET_FORBIDDEN';
  END IF;
END $$;
REVOKE ALL ON FUNCTION public.trafego_meta_draft_refuse_secrets(jsonb,integer) FROM PUBLIC,anon,authenticated;

CREATE OR REPLACE FUNCTION public.trafego_meta_campaign_draft_save(
  p_owner_id text,p_draft_ref uuid,p_expected_version integer,p_draft jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE saved public.trafego_meta_campaign_draft; clean jsonb; ad jsonb; aset jsonb; ads jsonb:='[]';
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_owner_id IS NULL OR length(btrim(p_owner_id)) NOT BETWEEN 1 AND 200 OR p_draft_ref IS NULL
     OR p_expected_version IS NULL OR p_expected_version NOT BETWEEN 0 AND 2147483646
     OR jsonb_typeof(p_draft) IS DISTINCT FROM 'object' OR octet_length(p_draft::text)>120000 THEN
    RAISE EXCEPTION 'META_DRAFT_INVALID';
  END IF;
  IF p_draft - ARRAY['recipeId','accountRef','pageRef','instagramActorRef','campaignName','destinationUrl',
      'nivelDeOrcamento','periodoDeOrcamento','budgetBrl','categoryConfirmed','creativeMode','conjuntos','variations'] <> '{}'::jsonb
     OR jsonb_typeof(p_draft->'conjuntos') IS DISTINCT FROM 'array'
     OR jsonb_typeof(p_draft->'variations') IS DISTINCT FROM 'array'
     OR jsonb_array_length(p_draft->'conjuntos') NOT BETWEEN 1 AND 10
     OR jsonb_array_length(p_draft->'variations') NOT BETWEEN 0 AND 10 THEN
    RAISE EXCEPTION 'META_DRAFT_INVALID';
  END IF;
  PERFORM public.trafego_meta_draft_refuse_secrets(p_draft);
  IF (SELECT count(DISTINCT x->>'key') FROM jsonb_array_elements(p_draft->'conjuntos') x)
     <> jsonb_array_length(p_draft->'conjuntos')
     OR (SELECT count(DISTINCT x->>'key') FROM jsonb_array_elements(p_draft->'variations') x)
     <> jsonb_array_length(p_draft->'variations') THEN RAISE EXCEPTION 'META_DRAFT_LINK_INVALID'; END IF;
  FOR aset IN SELECT * FROM jsonb_array_elements(p_draft->'conjuntos') LOOP
    IF jsonb_typeof(aset) IS DISTINCT FROM 'object' OR aset-ARRAY['key','nome','startTime','endTime','orcamentoBrl',
      'publico','posicionamentoModo','posicionamentoValores','mensuracao'] <> '{}'::jsonb THEN
      RAISE EXCEPTION 'META_DRAFT_INVALID';
    END IF;
  END LOOP;
  FOR ad IN SELECT * FROM jsonb_array_elements(p_draft->'variations') LOOP
    IF jsonb_typeof(ad) IS DISTINCT FROM 'object' OR ad-ARRAY['packOrigin','key','adsetKey','midia','assetRef',
      'videoRef','creativeName','adName','message','headline','description','cta','assetRightsConfirmed',
      'thirdPartyIdentityCleared','assetPolicyConfirmedAt'] <> '{}'::jsonb THEN RAISE EXCEPTION 'META_DRAFT_INVALID'; END IF;
    IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p_draft->'conjuntos') x WHERE x->>'key'=ad->>'adsetKey') THEN
      RAISE EXCEPTION 'META_DRAFT_LINK_INVALID';
    END IF;
    IF ad ? 'packOrigin' AND (ad->'packOrigin'->>'accountRef') IS DISTINCT FROM p_draft->>'accountRef' THEN
      RAISE EXCEPTION 'META_DRAFT_LINK_INVALID';
    END IF;
    ads:=ads || jsonb_build_array(ad || '{"assetRightsConfirmed":false,"thirdPartyIdentityCleared":false,"assetPolicyConfirmedAt":""}'::jsonb);
  END LOOP;
  clean:=p_draft || jsonb_build_object('categoryConfirmed',false,'variations',ads);
  IF p_expected_version=0 THEN
    INSERT INTO public.trafego_meta_campaign_draft(owner_id,draft_ref,version,draft)
      VALUES(p_owner_id,p_draft_ref,1,clean) ON CONFLICT(owner_id,draft_ref) DO NOTHING RETURNING * INTO saved;
  ELSE
    UPDATE public.trafego_meta_campaign_draft SET draft=clean,version=version+1,updated_at=clock_timestamp()
      WHERE owner_id=p_owner_id AND draft_ref=p_draft_ref AND version=p_expected_version RETURNING * INTO saved;
  END IF;
  IF saved.draft_ref IS NULL THEN RAISE EXCEPTION 'META_DRAFT_VERSION_CONFLICT'; END IF;
  RETURN jsonb_build_object('draft_ref',saved.draft_ref,'version',saved.version,'draft',saved.draft,
    'updated_at',saved.updated_at,'scope','DRAFT_ONLY','launch_authorized',false);
END $$;

CREATE OR REPLACE FUNCTION public.trafego_meta_campaign_draft_read(p_owner_id text,p_draft_ref uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER STABLE SET search_path=pg_catalog,public AS $$
DECLARE result jsonb;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  SELECT jsonb_build_object('draft_ref',d.draft_ref,'version',d.version,'draft',d.draft,
    'updated_at',d.updated_at,'scope','DRAFT_ONLY','launch_authorized',false) INTO result
    FROM public.trafego_meta_campaign_draft d WHERE d.owner_id=p_owner_id AND d.draft_ref=p_draft_ref;
  RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.trafego_meta_campaign_draft_save(text,uuid,integer,jsonb) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_campaign_draft_read(text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_campaign_draft_save(text,uuid,integer,jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_campaign_draft_read(text,uuid) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
