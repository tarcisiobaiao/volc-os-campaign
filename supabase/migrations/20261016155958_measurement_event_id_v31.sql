-- VOLC Measurement v3.1
--
-- A chave anterior (sid, pid, event_name, ts_sec) descartava eventos legitimos
-- do mesmo tipo ocorridos no mesmo segundo. event_seq e monotono por pageview e
-- faz parte do envelope enviado pelo sensor. Repetir o mesmo envelope continua
-- idempotente, mas uma rajada de eventos deixa de colidir.

begin;

alter table public.raw_events
  add column if not exists event_seq integer not null default 0;

do $$
begin
  if not exists (
    select 1
      from pg_constraint
     where conrelid = 'public.raw_events'::regclass
       and conname = 'raw_events_event_seq_range'
  ) then
    alter table public.raw_events
      add constraint raw_events_event_seq_range
      check (event_seq between 0 and 2147483647);
  end if;
end $$;

drop index if exists public.raw_events_dedup;
create unique index raw_events_dedup
  on public.raw_events (sid, pid, event_name, ts_sec, event_seq);

comment on column public.raw_events.event_seq is
  'Monotonic event number inside one pageview. Zero means a legacy v3.0 envelope.';

notify pgrst, 'reload schema';

commit;
