-- Reusable snapshots, NOT publication approvals. Backend ownership is mandatory.
begin;
create table if not exists public.criativo_reuso_pack (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null,
    nome text not null check (length(btrim(nome)) between 1 and 120),
    manifest jsonb not null check (jsonb_typeof(manifest) = 'object'),
    manifest_sha256 text not null check (manifest_sha256 ~ '^[a-f0-9]{64}$'),
    created_at timestamptz not null default now(),
    constraint criativo_reuso_pack_identity unique (owner_id, manifest_sha256),
    constraint criativo_reuso_pack_version check ((manifest->>'version' = 'creative-pack-v1') is true),
    constraint criativo_reuso_pack_no_approval check ((manifest->'launch_authorized' = 'false'::jsonb) is true),
    constraint criativo_reuso_pack_items check (
        (jsonb_typeof(manifest->'items') = 'array'
        and jsonb_array_length(manifest->'items') between 1 and 10) is true
    )
);
create index if not exists criativo_reuso_pack_owner_date
    on public.criativo_reuso_pack(owner_id, created_at desc, id);
alter table public.criativo_reuso_pack enable row level security;
alter table public.criativo_reuso_pack force row level security;
revoke all on public.criativo_reuso_pack from public, anon, authenticated;
revoke all on public.criativo_reuso_pack from service_role;
grant select, insert on public.criativo_reuso_pack to service_role;
-- Immutable even for privileged backend code: edits create a new snapshot.
create or replace function public.criativo_reuso_pack_immutable()
returns trigger language plpgsql set search_path = pg_catalog as $$
begin
    raise exception 'Creative packs are immutable snapshots';
end $$;
revoke all on function public.criativo_reuso_pack_immutable() from public, anon, authenticated;
drop trigger if exists criativo_reuso_pack_immutable on public.criativo_reuso_pack;
create trigger criativo_reuso_pack_immutable before update or delete
on public.criativo_reuso_pack for each row execute function public.criativo_reuso_pack_immutable();
comment on table public.criativo_reuso_pack is
    'Owner-scoped immutable reuse snapshots. References, not copied image bytes; no policy approval, dark-post eligibility or Meta mutation implied.';
commit;
