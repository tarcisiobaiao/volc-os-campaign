-- Based on the live function: preserves regulatory identity, owner/CAS and approval resets.
begin;
CREATE OR REPLACE FUNCTION public.trafego_meta_campaign_draft_save(p_owner_id text, p_draft_ref uuid, p_expected_version integer, p_draft jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
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
      'publico','posicionamentoModo','posicionamentoValores','mensuracao','regulatoryIdentityRef'] <> '{}'::jsonb
      OR (aset ? 'regulatoryIdentityRef' AND (
        jsonb_typeof(aset->'regulatoryIdentityRef') IS DISTINCT FROM 'string'
        OR (aset->>'regulatoryIdentityRef') !~ '^metareg_[a-f0-9]{32}$')) THEN
      RAISE EXCEPTION 'META_DRAFT_INVALID';
    END IF;
  END LOOP;
  FOR ad IN SELECT * FROM jsonb_array_elements(p_draft->'variations') LOOP
    IF jsonb_typeof(ad) IS DISTINCT FROM 'object' OR ad-ARRAY['packOrigin','key','adsetKey','midia','assetRef',
      'videoRef','creativeName','adName','message','headline','description','cta','assetRightsConfirmed',
      'thirdPartyIdentityCleared','assetPolicyConfirmedAt','existingPostRef'] <> '{}'::jsonb THEN RAISE EXCEPTION 'META_DRAFT_INVALID'; END IF;
    IF ad ? 'existingPostRef' AND ad->'existingPostRef' <> 'null'::jsonb AND (
      jsonb_typeof(ad->'existingPostRef') IS DISTINCT FROM 'string'
      OR (ad->>'existingPostRef') !~ '^metapost_[a-f0-9]{32}$') THEN
      RAISE EXCEPTION 'META_DRAFT_INVALID';
    END IF;
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
END $function$;
notify pgrst, 'reload schema';
commit;
