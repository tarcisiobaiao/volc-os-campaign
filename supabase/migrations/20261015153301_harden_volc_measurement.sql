-- VOLC measurement ingress is the only writer of browser telemetry.
-- Browser clients must never reach raw_events through PostgREST directly.
-- The Edge Function uses service_role and remains the validation boundary.

begin;

alter table public.raw_events enable row level security;
alter table public.raw_events force row level security;

revoke all privileges on table public.raw_events from anon;
revoke all privileges on table public.raw_events from authenticated;

-- Keep the existing Edge Function contract explicit. service_role bypasses RLS,
-- but nominal privileges make the intended owner and blast radius auditable.
revoke update, delete, truncate, trigger, references on table public.raw_events from service_role;
grant select, insert on table public.raw_events to service_role;

comment on table public.raw_events is
  'Validated first-party telemetry. Writes enter only through volc-ingest; no direct browser Data API access.';

notify pgrst, 'reload schema';

commit;
