-- Prevent superseded collector contracts from leaking into the serving view.
--
-- Raw batches and observations are intentionally immutable.  When a collector
-- contract is corrected, historical versions remain available for audit, but
-- only the newest completed/partial version of each collector may feed the
-- canonical latest-observation view.

BEGIN;

CREATE OR REPLACE VIEW public.joinads_observation_latest
WITH (security_invoker = true)
AS
WITH eligible_runs AS (
  SELECT r.*
  FROM public.joinads_collection_run r
  WHERE r.status IN ('completed', 'partial')
    AND r.collector_version = (
      SELECT max(r2.collector_version)
      FROM public.joinads_collection_run r2
      WHERE r2.collector = r.collector
        AND r2.status IN ('completed', 'partial')
    )
)
SELECT DISTINCT ON (
  o.endpoint, o.grain, o.metric_date, o.metric_hour, coalesce(o.domain,''),
  coalesce(o.campaign_id,''), coalesce(o.custom_key,''), coalesce(o.custom_value,''),
  coalesce(o.post_id,''), coalesce(o.land_uri,''), coalesce(o.ad_unit_name,''),
  coalesce(o.country_iso,'')
)
  o.*
FROM public.joinads_observation o
JOIN eligible_runs r ON r.run_key = o.run_key
ORDER BY
  o.endpoint, o.grain, o.metric_date, o.metric_hour, coalesce(o.domain,''),
  coalesce(o.campaign_id,''), coalesce(o.custom_key,''), coalesce(o.custom_value,''),
  coalesce(o.post_id,''), coalesce(o.land_uri,''), coalesce(o.ad_unit_name,''),
  coalesce(o.country_iso,''), o.collected_at DESC, o.observation_key DESC;

REVOKE ALL ON TABLE public.joinads_observation_latest FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.joinads_observation_latest TO service_role;

COMMENT ON VIEW public.joinads_observation_latest IS
  'Latest observation at each JoinAds grain, restricted to the newest successful collector contract.';

NOTIFY pgrst, 'reload schema';
COMMIT;
