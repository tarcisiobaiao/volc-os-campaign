-- Pack escolhido por conjunto dentro de um rascunho Meta.
-- É estado de preparação, não aprovação de mídia e não autoriza chamada à Meta.
begin;

create table public.trafego_meta_rascunho_pack (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null,
    draft_ref uuid not null,
    adset_key text not null,
    pack_id uuid not null references public.criativo_reuso_pack(id) on delete restrict,
    manifest_sha256 text not null,
    master_refs uuid[] not null,
    version integer not null default 1,
    selected_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint trafego_meta_rascunho_pack_identity unique (owner_id, draft_ref, adset_key),
    constraint trafego_meta_rascunho_pack_adset_key check (
        adset_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
    ),
    constraint trafego_meta_rascunho_pack_digest check (
        manifest_sha256 ~ '^[a-f0-9]{64}$'
    ),
    constraint trafego_meta_rascunho_pack_refs check (
        cardinality(master_refs) between 1 and 10
        and array_position(master_refs, null) is null
    ),
    constraint trafego_meta_rascunho_pack_version check (version >= 1)
);

create index trafego_meta_rascunho_pack_owner_draft
    on public.trafego_meta_rascunho_pack(owner_id, draft_ref, adset_key);

alter table public.trafego_meta_rascunho_pack enable row level security;
alter table public.trafego_meta_rascunho_pack force row level security;
revoke all on public.trafego_meta_rascunho_pack from public, anon, authenticated;
revoke all on public.trafego_meta_rascunho_pack from service_role;
grant select, insert, update, delete on public.trafego_meta_rascunho_pack to service_role;

comment on table public.trafego_meta_rascunho_pack is
    'Owner-scoped, versioned pack binding per Meta draft/adset. Draft media only; never launch authorization.';
comment on column public.trafego_meta_rascunho_pack.version is
    'Optimistic concurrency token. Every replacement must compare the previous value.';

commit;
