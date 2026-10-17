\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
-- só contagens por versão do sensor; nenhum sid, path, ref ou valor de utm sai
SELECT v, min(created_at) primeiro, max(created_at) ultimo, count(*) eventos, count(DISTINCT sid) sessoes,
       count(*) FILTER (WHERE event_seq > 0) com_seq,
       count(DISTINCT sid) FILTER (WHERE (payload->'utm'->>'paid')='1') sessoes_pagas,
       count(DISTINCT sid) FILTER (WHERE (payload->'utm'->>'paid')='1' AND payload->'utm' ? 'campaign') pagas_com_campaign,
       count(DISTINCT sid) FILTER (WHERE (payload->'utm'->>'paid')='1' AND payload->'utm' ? 'source') pagas_com_source
  FROM raw_events WHERE created_at >= '2026-10-15' AND event_name='volc_sensor_ready' GROUP BY v ORDER BY v;
ROLLBACK;
