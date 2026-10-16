\echo ===== H1 repetidas no mesmo lote JoinAds =====
SELECT endpoint, count(*) AS grupos_repetidos, sum(n) AS linhas FROM (SELECT batch_key, endpoint, coalesce(land_uri,''), coalesce(post_id,''), coalesce(campaign_id,''), coalesce(custom_value,''), coalesce(ad_unit_name,''), coalesce(country_iso,''), metric_date, metric_hour, count(*) n FROM public.joinads_observation GROUP BY 1,2,3,4,5,6,7,8,9,10 HAVING count(*)>1) s GROUP BY 1 ORDER BY 1;
SELECT endpoint, count(*) AS grupos_obs_key_repetida FROM (SELECT endpoint, observation_key, count(*) FROM public.joinads_observation GROUP BY 1,2 HAVING count(*)>1) s GROUP BY 1;
\echo ===== H5 vida do coletor de termos =====
SELECT min(collected_at), max(collected_at), count(DISTINCT run_id) FROM public.google_ads_observation WHERE resource_type='search_term';
