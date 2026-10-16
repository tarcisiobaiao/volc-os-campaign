-- Rollback conservador da v3.1. Ele recusa perder eventos: depois que duas
-- linhas diferirem apenas por event_seq, voltar a chave v3.0 seria destrutivo.

begin;

do $$
begin
  if exists (
    select 1
      from public.raw_events
     group by sid, pid, event_name, ts_sec
    having count(*) > 1
  ) then
    raise exception using
      errcode = '55000',
      message = 'rollback v3.1 recusado: a chave antiga descartaria eventos legitimos';
  end if;
end $$;

drop index if exists public.raw_events_dedup;
alter table public.raw_events
  drop constraint if exists raw_events_event_seq_range,
  drop column if exists event_seq;
create unique index raw_events_dedup
  on public.raw_events (sid, pid, event_name, ts_sec);

notify pgrst, 'reload schema';

commit;
