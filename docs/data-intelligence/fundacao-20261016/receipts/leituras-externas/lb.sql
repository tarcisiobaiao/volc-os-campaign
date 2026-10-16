SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='google_ads_collection_run' ORDER BY ordinal_position;
SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='google_ads_raw_batch' ORDER BY ordinal_position;
with o as (
  select campaign_id, metric_date, collected_at, metrics,
         lag(metrics) over (partition by campaign_id, metric_date order by collected_at) as prev
  from google_ads_observation where resource_type = 'campaign' and metric_date >= current_date - 7)
select extract(hour from collected_at at time zone 'America/Sao_Paulo') as hora, count(*) as leituras, round(avg((metrics is distinct from prev)::int),3) as p_mudou
from o where prev is not null group by 1 order by 1;
select count(*) as lidas, count(distinct (observation_key, metrics)) as distintas from google_ads_observation where resource_type = 'search_term' and collected_at > now() - interval '7 days';
select relname, n_live_tup, pg_total_relation_size(relid) / greatest(n_live_tup, 1) as bytes_por_linha from pg_stat_user_tables where relname in ('google_ads_observation','google_ads_raw_batch','joinads_observation','joinads_raw_batch','raw_events');
select indexrelname, idx_scan, pg_relation_size(indexrelid) as bytes from pg_stat_user_indexes where relname in ('google_ads_observation','joinads_observation') order by idx_scan;
