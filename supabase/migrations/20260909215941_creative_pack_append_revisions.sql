begin;

-- The library head may grow; every manifest used by a draft stays addressable.
create table public.criativo_reuso_pack_revision (
    pack_id uuid not null references public.criativo_reuso_pack(id) on delete restrict,
    owner_id uuid not null,
    nome text not null,
    manifest jsonb not null,
    manifest_sha256 text not null check (manifest_sha256 ~ '^[a-f0-9]{64}$'),
    created_at timestamptz not null,
    primary key (pack_id, manifest_sha256)
);
alter table public.criativo_reuso_pack_revision enable row level security;
alter table public.criativo_reuso_pack_revision force row level security;
revoke all on public.criativo_reuso_pack_revision from public, anon, authenticated, service_role;
grant select, insert on public.criativo_reuso_pack_revision to service_role;
create index criativo_reuso_pack_revision_owner on public.criativo_reuso_pack_revision(owner_id, pack_id);

create function public.criativo_reuso_pack_revision_immutable()
returns trigger language plpgsql security invoker set search_path = pg_catalog as $$
begin raise exception 'Pack revisions are immutable'; end $$;
revoke all on function public.criativo_reuso_pack_revision_immutable() from public, anon, authenticated;
create trigger criativo_reuso_pack_revision_immutable before update or delete
on public.criativo_reuso_pack_revision for each row execute function public.criativo_reuso_pack_revision_immutable();

create or replace function public.criativo_reuso_pack_immutable()
returns trigger language plpgsql security invoker set search_path = pg_catalog as $$
declare old_count integer; new_count integer;
begin
    if tg_op = 'DELETE' then raise exception 'Pack deletion is not supported'; end if;
    if (to_jsonb(new) - 'manifest' - 'manifest_sha256') is distinct from
       (to_jsonb(old) - 'manifest' - 'manifest_sha256') then
        raise exception 'Pack identity cannot change';
    end if;
    if (old.manifest->>'source') is distinct from 'STUDIO'
       or (new.manifest - 'items') is distinct from (old.manifest - 'items') then
        raise exception 'Only Studio items may be appended';
    end if;
    old_count := jsonb_array_length(old.manifest->'items');
    new_count := jsonb_array_length(new.manifest->'items');
    if new_count <= old_count or new_count > 10 then raise exception 'Pack accepts append up to 10 items'; end if;
    for i in 0..old_count - 1 loop
        if (new.manifest->'items'->i) is distinct from (old.manifest->'items'->i) then
            raise exception 'Existing pack items cannot change';
        end if;
    end loop;
    if exists (select 1 from jsonb_array_elements(new.manifest->'items') item
        where coalesce(item->>'master_ref','') !~ '^[a-f0-9-]{36}$')
       or (select count(distinct item->>'master_ref') from jsonb_array_elements(new.manifest->'items') item) <> new_count then
        raise exception 'Pack references must be unique';
    end if;
    insert into public.criativo_reuso_pack_revision(pack_id,owner_id,nome,manifest,manifest_sha256,created_at)
    values(old.id,old.owner_id,old.nome,old.manifest,old.manifest_sha256,old.created_at)
    on conflict (pack_id,manifest_sha256) do nothing;
    return new;
end $$;

grant update(manifest,manifest_sha256) on public.criativo_reuso_pack to service_role;

-- SECURITY INVOKER: service-only RPC, no public privileged functions.
create function public.criativo_reuso_pack_append(
    p_owner_id uuid, p_pack_id uuid, p_expected_manifest_sha256 text, p_manifest_canonical text
) returns jsonb language plpgsql security invoker set search_path = pg_catalog as $$
declare current_pack public.criativo_reuso_pack; next_manifest jsonb; next_digest text;
begin
    select * into current_pack from public.criativo_reuso_pack
      where id=p_pack_id and owner_id=p_owner_id for update;
    if not found or current_pack.manifest_sha256 is distinct from p_expected_manifest_sha256 then
        return jsonb_build_object('ok',false,'code','PACK_CHANGED');
    end if;
    next_manifest := p_manifest_canonical::jsonb;
    next_digest := encode(sha256(convert_to(p_manifest_canonical,'UTF8')),'hex');
    update public.criativo_reuso_pack set manifest=next_manifest,manifest_sha256=next_digest
      where id=p_pack_id and owner_id=p_owner_id returning * into current_pack;
    return jsonb_build_object('ok',true,'pack',to_jsonb(current_pack)-'owner_id');
end $$;
revoke all on function public.criativo_reuso_pack_append(uuid,uuid,text,text) from public, anon, authenticated;
grant execute on function public.criativo_reuso_pack_append(uuid,uuid,text,text) to service_role;

comment on table public.criativo_reuso_pack_revision is 'Immutable manifests retained when a library pack grows. Existing draft hash/reference bindings remain unchanged.';
notify pgrst, 'reload schema';
commit;
