-- Synthetic contract checks only; all inserted rows are rolled back.
begin;
set local role service_role;
do $$
declare
 owner_ref uuid := gen_random_uuid(); pack_ref uuid := gen_random_uuid();
 draft_ref uuid := gen_random_uuid(); first_ref uuid := gen_random_uuid();
 original jsonb; expanded jsonb; result jsonb; d jsonb; readback jsonb;
begin
 original := jsonb_build_object('version','creative-pack-v1','source','STUDIO','launch_authorized',false,
 'items',jsonb_build_array(jsonb_build_object('master_ref',first_ref)));
 insert into public.criativo_reuso_pack(id,owner_id,nome,manifest,manifest_sha256)
 values(pack_ref,owner_ref,'Synthetic rollback contract',original,repeat('a',64));
 expanded := jsonb_set(original,'{items}',(original->'items') || jsonb_build_array(jsonb_build_object('master_ref',gen_random_uuid())));
 result := public.criativo_reuso_pack_append(gen_random_uuid(),pack_ref,repeat('a',64),expanded::text);
 if result->>'code' <> 'PACK_CHANGED' then raise exception 'OWNER_BOUNDARY_FAILED'; end if;
 result := public.criativo_reuso_pack_append(owner_ref,pack_ref,repeat('a',64),expanded::text);
 if result->>'ok' <> 'true' then raise exception 'APPEND_FAILED'; end if;
 if not exists(select 1 from public.criativo_reuso_pack_revision where pack_id=pack_ref and manifest=original)
 then raise exception 'HISTORY_FAILED'; end if;
 result := public.criativo_reuso_pack_append(owner_ref,pack_ref,repeat('a',64),expanded::text);
 if result->>'code' <> 'PACK_CHANGED' then raise exception 'CAS_FAILED'; end if;
 d := jsonb_build_object('conjuntos',jsonb_build_array(jsonb_build_object('key','adset-1','regulatoryIdentityRef','metareg_'||repeat('b',32))),
 'variations',jsonb_build_array(jsonb_build_object('key','ad-1','adsetKey','adset-1','existingPostRef','metapost_'||repeat('c',32))));
 result := public.trafego_meta_campaign_draft_save(owner_ref::text,draft_ref,0,d);
 readback := public.trafego_meta_campaign_draft_read(owner_ref::text,draft_ref);
 if readback->'draft'->'variations'->0->>'existingPostRef' <> 'metapost_'||repeat('c',32)
 then raise exception 'POST_PERSISTENCE_FAILED'; end if;
 begin
  perform public.trafego_meta_campaign_draft_save(owner_ref::text,gen_random_uuid(),0,
    jsonb_set(d,'{variations,0,existingPostRef}','"raw-post-id"'::jsonb));
  raise exception 'INVALID_POST_ACCEPTED';
 exception when others then
  if sqlerrm <> 'META_DRAFT_INVALID' then raise; end if;
 end;
 if has_function_privilege('anon','public.criativo_reuso_pack_append(uuid,uuid,text,text)','EXECUTE')
 or has_function_privilege('authenticated','public.criativo_reuso_pack_append(uuid,uuid,text,text)','EXECUTE')
 then raise exception 'PUBLIC_RPC_EXPOSED'; end if;
 raise notice 'PASS: append, owner, CAS, history, opaque post save/read, invalid reference and grants';
end $$;
rollback;
