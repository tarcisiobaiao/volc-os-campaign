-- Export READ-ONLY para o recibo de saúde com dado real (thread G). Um único SELECT; não cria nada.
-- Rodar com PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=60000', saída -A -t
-- para um arquivo NO SCRATCHPAD (não commitar: observation_key de termos contém o texto do termo).
-- Depois: python -m volc_dil.fundacao.qualidade.recibo --entrada <arquivo>.json --agora <instante do export> --saida <dir>
--
-- Minimização: payloads brutos NÃO saem. Do lote Google só sai `payload->'metrics'` (prova de linha de
-- métrica, zero sintetizado); do lote JoinAds só request_meta (custom_key pedido) — a deriva de esquema
-- fica com a view dq_esquema_joinads. dimensions/attributes/receipt do Google não saem; o sensor sai só
-- agregado por dia (nenhum sid/pid). Janela: 15 dias.
SELECT jsonb_build_object(
  'formato', 'tabelas',
  'tabelas', jsonb_build_object(
    'google_ads_collection_run', (
      SELECT coalesce(jsonb_agg(to_jsonb(r) - 'receipt'), '[]'::jsonb)
      FROM public.google_ads_collection_run r WHERE r.started_at > now() - interval '15 days'),
    'google_ads_raw_batch', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
               'batch_id', b.batch_id, 'run_id', b.run_id, 'collected_at', b.collected_at,
               'payload', CASE WHEN jsonb_typeof(b.payload) = 'object' AND b.payload ? 'metrics'
                               THEN jsonb_build_object('metrics', b.payload -> 'metrics') ELSE '[]'::jsonb END)),
             '[]'::jsonb)
      FROM public.google_ads_raw_batch b WHERE b.collected_at > now() - interval '15 days'),
    'google_ads_observation', (
      SELECT coalesce(jsonb_agg(to_jsonb(o) - 'dimensions' - 'attributes'), '[]'::jsonb)
      FROM public.google_ads_observation o WHERE o.collected_at > now() - interval '15 days'),
    'joinads_collection_run', (
      SELECT coalesce(jsonb_agg(to_jsonb(r)), '[]'::jsonb)
      FROM public.joinads_collection_run r WHERE r.started_at > now() - interval '15 days'),
    'joinads_raw_batch', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
               'batch_key', b.batch_key, 'run_key', b.run_key, 'collected_at', b.collected_at,
               'request_meta', b.request_meta)), '[]'::jsonb)
      FROM public.joinads_raw_batch b WHERE b.collected_at > now() - interval '15 days'),
    'joinads_observation', (
      SELECT coalesce(jsonb_agg(to_jsonb(o) - 'dimensions' - 'attributes' - 'advertiser'), '[]'::jsonb)
      FROM public.joinads_observation o WHERE o.collected_at > now() - interval '15 days')
  ),
  'cobertura_sensor', (
    SELECT coalesce(jsonb_agg(jsonb_build_object(
             'dia', d.dia, 'sessoes_total', d.sessoes_total, 'sessoes_pagas', d.sessoes_pagas,
             'pagas_com_campanha', d.pagas_com_campanha, 'pagas_com_source', d.pagas_com_source)), '[]'::jsonb)
    FROM (
      SELECT (e.ts AT TIME ZONE 'America/Sao_Paulo')::date AS dia, count(*) AS sessoes_total,
             count(*) FILTER (WHERE coalesce(e.payload -> 'utm' ->> 'paid', '') IN ('1', 'true')) AS sessoes_pagas,
             count(*) FILTER (WHERE coalesce(e.payload -> 'utm' ->> 'paid', '') IN ('1', 'true')
                              AND nullif(btrim(coalesce(e.payload -> 'utm' ->> 'campaign', '')), '') IS NOT NULL)
               AS pagas_com_campanha,
             count(*) FILTER (WHERE coalesce(e.payload -> 'utm' ->> 'paid', '') IN ('1', 'true')
                              AND nullif(coalesce(e.payload -> 'utm' ->> 'source', ''), '') IS NOT NULL)
               AS pagas_com_source
      FROM public.raw_events e
      WHERE e.event_name = 'volc_sensor_ready' AND e.ts > now() - interval '14 days' AND e.ts <= now()
      GROUP BY 1
    ) d)
);
