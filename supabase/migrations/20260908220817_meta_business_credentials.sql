-- Server-only encrypted credentials. Encryption key never enters Postgres.
begin;
set local lock_timeout = '5s';
create table public.meta_business_credentials (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id),
  business_id text not null check (business_id ~ '^[0-9]{5,30}$'),
  name text not null check (length(name) between 1 and 120),
  ciphertext text not null check (ciphertext like 'gAAAA%' and length(ciphertext) between 100 and 16000),
  enabled boolean not null default true,
  verified_at timestamptz not null,
  updated_at timestamptz not null default now(),
  unique (owner_id, business_id),
  unique (owner_id, id)
);
create table public.meta_business_selection (
  owner_id uuid primary key references auth.users(id),
  credential_id uuid not null,
  updated_at timestamptz not null default now(),
  foreign key (owner_id, credential_id) references public.meta_business_credentials(owner_id, id)
);
alter table public.meta_business_credentials enable row level security;
alter table public.meta_business_credentials force row level security;
alter table public.meta_business_selection enable row level security;
alter table public.meta_business_selection force row level security;
revoke all on public.meta_business_credentials, public.meta_business_selection from public, anon, authenticated;
grant select, insert, update on public.meta_business_credentials, public.meta_business_selection to service_role;
comment on table public.meta_business_credentials is 'Fernet envelope bound to owner and business. Backend ADMIN endpoints only; no decrypted SQL view.';
notify pgrst, 'reload schema';
commit;
