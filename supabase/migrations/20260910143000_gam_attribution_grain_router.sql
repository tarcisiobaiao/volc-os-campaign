-- =============================================================================
-- GAM attribution router — campaign grain (Google) x adset grain (Meta)
-- =============================================================================
--
-- `gam_metrics.utm_campaign_value` is a transport key, not a universal
-- campaign id. In the legacy Google contract it resolves to `campaigns`, while
-- Meta deliberately emits `{{adset.id}}`. Treating both as campaign ids creates
-- fake rows in `daily_campaign_metrics` and makes Meta revenue impossible to
-- reconcile with its campaign hierarchy.
--
-- This migration therefore:
--   * preserves every raw GAM row;
--   * routes a value to `daily_campaign_metrics` only when it resolves to one
--     real, project-compatible legacy campaign;
--   * never routes a known Meta ad set to campaign-grain storage;
--   * never invents a campaign for an unknown or ambiguous value;
--   * exposes a service-role-only diagnostic view for unresolved keys.
--
-- Meta revenue remains in `gam_metrics` and is consumed at adset/day grain by
-- `vw_trafego_meta_financeiro_conjunto_dia_gam`; campaign totals are roll-ups
-- of those child rows, never a second campaign-level attribution.
-- =============================================================================

BEGIN;

DO $guard$
DECLARE
  v_missing text;
BEGIN
  SELECT string_agg(required_name, ', ' ORDER BY required_name)
    INTO v_missing
    FROM unnest(ARRAY[
      'campaigns',
      'daily_campaign_metrics',
      'gam_metrics',
      'trafego_meta_adset',
      'trafego_meta_campaign',
      'trafego_meta_project_binding'
    ]) AS required_name
   WHERE to_regclass('public.' || required_name) IS NULL;

  IF v_missing IS NOT NULL THEN
    RAISE EXCEPTION
      'GAM_ATTRIBUTION_ROUTER_MISSING_DEPENDENCIES: %', v_missing;
  END IF;

  IF NOT EXISTS (
    SELECT 1
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'gam_metrics'
       AND column_name = 'project_id'
  ) THEN
    RAISE EXCEPTION
      'GAM_ATTRIBUTION_ROUTER_PROJECT_REQUIRED: gam_metrics.project_id is required to prevent cross-project attribution';
  END IF;
END
$guard$;

-- Lookup indexes. The Meta schema guarantees uniqueness under the parent, but
-- attribution starts with the external adset id, so it needs its own access
-- path. The project/date index also serves the financial read model.
CREATE INDEX IF NOT EXISTS trafego_meta_adset_external_id_ix
  ON public.trafego_meta_adset (external_id);

CREATE INDEX IF NOT EXISTS trafego_meta_binding_project_active_ix
  ON public.trafego_meta_project_binding (project_id, ad_account_ativo_id)
  WHERE desfeito_em IS NULL;

CREATE INDEX IF NOT EXISTS gam_metrics_project_utm_date_ix
  ON public.gam_metrics (project_id, utm_campaign_value, date);

-- ---------------------------------------------------------------------------
-- Diagnostic read model
-- ---------------------------------------------------------------------------
-- One row per raw GAM fact. This view does not move or duplicate money; it only
-- explains which namespace the key resolves to. A Meta match always prevents
-- projection to `daily_campaign_metrics`, even when the project binding is
-- missing or mismatched: an incomplete Meta catalog must not create a fake
-- legacy campaign.
DROP VIEW IF EXISTS public.vw_gam_attribution_route;

CREATE VIEW public.vw_gam_attribution_route
WITH (security_invoker = true) AS
SELECT
  gm.id AS gam_metric_id,
  gm.date,
  gm.project_id,
  gm.gam_accounts_id,
  gm.utm_campaign_value,
  gm.revenue,
  gm.revenue_converted,
  coalesce(meta.matches_total, 0) AS meta_adset_matches,
  coalesce(meta.matches_in_project, 0) AS meta_adset_project_matches,
  coalesce(google.matches_in_project, 0) AS google_campaign_matches,
  meta.meta_campaign_external_id,
  CASE
    WHEN coalesce(meta.matches_total, 0) > 0
         AND coalesce(google.matches_in_project, 0) > 0
      THEN 'AMBIGUOUS_NAMESPACE'
    WHEN coalesce(meta.matches_total, 0) > 0
         AND gm.project_id IS NOT NULL
         AND coalesce(meta.matches_in_project, 0) = 0
      THEN 'META_ADSET_PROJECT_UNBOUND_OR_MISMATCHED'
    WHEN coalesce(meta.matches_total, 0) > 0
      THEN 'META_ADSET'
    WHEN coalesce(google.matches_in_project, 0) = 1
      THEN 'GOOGLE_CAMPAIGN'
    WHEN coalesce(google.matches_in_project, 0) > 1
      THEN 'AMBIGUOUS_GOOGLE_CAMPAIGN'
    ELSE 'UNMATCHED'
  END AS attribution_route,
  CASE
    WHEN coalesce(meta.matches_total, 0) > 0
      THEN 'GAM.utm_campaign_value = Meta adset_id'
    WHEN coalesce(google.matches_in_project, 0) = 1
      THEN 'GAM.utm_campaign_value = legacy campaign_id'
  END AS attribution_method
FROM public.gam_metrics gm
LEFT JOIN LATERAL (
  SELECT
    count(DISTINCT s.meta_adset_id) AS matches_total,
    count(DISTINCT s.meta_adset_id) FILTER (
      WHERE gm.project_id IS NULL OR b.project_id = gm.project_id
    ) AS matches_in_project,
    min(c.external_id) AS meta_campaign_external_id
  FROM public.trafego_meta_adset s
  JOIN public.trafego_meta_campaign c
    ON c.meta_campaign_id = s.meta_campaign_id
  LEFT JOIN public.trafego_meta_project_binding b
    ON b.ad_account_ativo_id = c.ad_account_ativo_id
   AND b.desfeito_em IS NULL
  WHERE s.external_id = gm.utm_campaign_value
    AND s.ausente_desde IS NULL
    AND c.ausente_desde IS NULL
) meta ON true
LEFT JOIN LATERAL (
  SELECT count(*) AS matches_in_project
  FROM public.campaigns c
  WHERE c.campaign_id = gm.utm_campaign_value
    AND (gm.project_id IS NULL OR c.project_id = gm.project_id)
) google ON true;

COMMENT ON VIEW public.vw_gam_attribution_route IS
  'Classifies each raw GAM row without moving money. Meta resolves at adset/day; legacy Google resolves at campaign/day. UNMATCHED and ambiguous rows remain in gam_metrics for reconciliation and never create synthetic campaigns.';

REVOKE ALL ON public.vw_gam_attribution_route FROM PUBLIC;
REVOKE ALL ON public.vw_gam_attribution_route FROM anon;
REVOKE ALL ON public.vw_gam_attribution_route FROM authenticated;
REVOKE ALL ON public.vw_gam_attribution_route FROM service_role;
GRANT SELECT ON public.vw_gam_attribution_route TO service_role;

-- ---------------------------------------------------------------------------
-- Project-scoped Meta revenue views (installed when the Meta insight grain is
-- already present)
-- ---------------------------------------------------------------------------
-- The first financial draft left project/GAM-account scoping to its caller.
-- That is too easy to forget in a dashboard or backfill. The replacement makes
-- the active project binding part of the SQL join itself. A missing binding,
-- missing project_id or multiple GAM accounts produces an explicit status and
-- NULL revenue; it can never fan out and duplicate Meta spend.
DO $meta_financial$
BEGIN
  IF to_regclass('public.vw_trafego_meta_financeiro_conjunto_dia') IS NULL THEN
    RAISE NOTICE
      'GAM attribution router: Meta insight grain not installed yet; financial views will be created after its migration is applied';
    RETURN;
  END IF;

  DROP VIEW IF EXISTS public.vw_trafego_meta_financeiro_campanha_dia_gam;
  DROP VIEW IF EXISTS public.vw_trafego_meta_financeiro_conjunto_dia_gam;

  EXECUTE $sql$
    CREATE VIEW public.vw_trafego_meta_financeiro_conjunto_dia_gam
    WITH (security_invoker = true) AS
    SELECT
      g.*,
      binding.project_id,
      m.gam_accounts_id,
      CASE
        WHEN binding.project_id IS NULL THEN NULL
        WHEN coalesce(m.n_rows, 0) = 1 THEN m.revenue
      END AS gam_revenue_original,
      CASE
        WHEN binding.project_id IS NULL THEN NULL
        WHEN coalesce(m.n_rows, 0) = 1 THEN m.revenue_converted
      END AS gam_revenue_brl,
      CASE
        WHEN binding.project_id IS NULL THEN NULL
        WHEN coalesce(m.n_rows, 0) = 1 THEN m.updated_at
      END AS revenue_freshness,
      CASE
        WHEN binding.project_id IS NULL
          THEN 'META_PROJECT_BINDING_MISSING'
        WHEN m.utm_campaign_value IS NULL
          THEN 'SEM_UTM_ADSET_NO_GAM'
        WHEN coalesce(m.n_rows, 0) > 1
          THEN 'GAM_AMBIGUO_MULTIPLAS_CONTAS'
        ELSE 'FATURAMENTO_ATRIBUIDO_VIA_ADSET'
      END AS mapping_status,
      CASE
        WHEN binding.project_id IS NOT NULL AND coalesce(m.n_rows, 0) = 1
          THEN 'GAM.project_id = Meta project binding; GAM.utm_campaign_value = adset_id'
      END AS attribution_method,
      CASE
        WHEN binding.project_id IS NOT NULL
         AND coalesce(m.n_rows, 0) = 1
         AND m.revenue IS NOT NULL
         AND m.revenue <> 0
         AND m.revenue_converted IS NOT NULL
          THEN m.revenue_converted / m.revenue
      END AS fx_rate
    FROM public.vw_trafego_meta_financeiro_conjunto_dia g
    LEFT JOIN public.trafego_meta_project_binding binding
      ON binding.ad_account_ativo_id = g.ad_account_ativo_id
     AND binding.desfeito_em IS NULL
    LEFT JOIN LATERAL (
      SELECT
        count(*) OVER () AS n_rows,
        x.gam_accounts_id,
        x.utm_campaign_value,
        x.revenue,
        x.revenue_converted,
        x.updated_at
      FROM public.gam_metrics x
      WHERE binding.project_id IS NOT NULL
        AND x.project_id = binding.project_id
        AND x.utm_campaign_value = g.adset_id
        AND x.date = g.date
      ORDER BY x.gam_accounts_id
      LIMIT 1
    ) m ON true
  $sql$;

  COMMENT ON VIEW public.vw_trafego_meta_financeiro_conjunto_dia_gam IS
    'Canonical Meta adset/day fact plus GAM revenue. Join requires the active Meta account→project binding, equal gam_metrics.project_id, equal date and utm_campaign_value=adset_id. At most one row leaves the lateral join; ambiguity becomes NULL revenue and an explicit status, never duplicated spend.';

  REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia_gam FROM PUBLIC;
  REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia_gam FROM anon;
  REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia_gam FROM authenticated;
  REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia_gam FROM service_role;
  GRANT SELECT ON public.vw_trafego_meta_financeiro_conjunto_dia_gam TO service_role;

  EXECUTE $sql$
    CREATE VIEW public.vw_trafego_meta_financeiro_campanha_dia_gam
    WITH (security_invoker = true) AS
    SELECT
      c.*,
      revenue.adsets_in_revenue_rollup,
      CASE
        WHEN NOT c.completo THEN NULL
        WHEN revenue.adsets_in_revenue_rollup <> c.conjuntos_no_dia THEN NULL
        WHEN revenue.unmapped_adsets > 0 OR revenue.null_revenue_adsets > 0 THEN NULL
        ELSE revenue.gam_revenue_original
      END AS gam_revenue_original,
      CASE
        WHEN NOT c.completo THEN NULL
        WHEN revenue.adsets_in_revenue_rollup <> c.conjuntos_no_dia THEN NULL
        WHEN revenue.unmapped_adsets > 0 OR revenue.null_revenue_brl_adsets > 0 THEN NULL
        ELSE revenue.gam_revenue_brl
      END AS gam_revenue_brl,
      CASE
        WHEN NOT c.completo THEN 'META_INSIGHTS_INCOMPLETOS'
        WHEN coalesce(revenue.adsets_in_revenue_rollup, 0) <> c.conjuntos_no_dia
          THEN 'GAM_ROLLUP_ADSET_INCOMPLETO'
        WHEN revenue.unmapped_adsets > 0
          THEN 'GAM_NAO_ATRIBUIDO_EM_TODOS_CONJUNTOS'
        WHEN revenue.null_revenue_adsets > 0
          THEN 'GAM_RECEITA_AUSENTE_EM_CONJUNTO'
        ELSE 'FATURAMENTO_SOMADO_DOS_CONJUNTOS'
      END AS revenue_rollup_status,
      revenue.revenue_freshness
    FROM public.vw_trafego_meta_financeiro_campanha_dia c
    LEFT JOIN LATERAL (
      SELECT
        count(*) AS adsets_in_revenue_rollup,
        count(*) FILTER (
          WHERE g.mapping_status <> 'FATURAMENTO_ATRIBUIDO_VIA_ADSET'
        ) AS unmapped_adsets,
        count(*) FILTER (WHERE g.gam_revenue_original IS NULL) AS null_revenue_adsets,
        count(*) FILTER (WHERE g.gam_revenue_brl IS NULL) AS null_revenue_brl_adsets,
        sum(g.gam_revenue_original) AS gam_revenue_original,
        sum(g.gam_revenue_brl) AS gam_revenue_brl,
        min(g.revenue_freshness) AS revenue_freshness
      FROM public.vw_trafego_meta_financeiro_conjunto_dia_gam g
      WHERE g.ad_account_ativo_id = c.ad_account_ativo_id
        AND g.campaign_id = c.campaign_id
        AND g.date = c.date
    ) revenue ON true
  $sql$;

  COMMENT ON VIEW public.vw_trafego_meta_financeiro_campanha_dia_gam IS
    'Meta campaign/day roll-up. Spend and revenue are derived only from child adsets. Any incomplete insight, missing adset revenue, missing project binding or ambiguous GAM match makes campaign revenue NULL with an explicit status; no partial sum is presented as a complete total.';

  REVOKE ALL ON public.vw_trafego_meta_financeiro_campanha_dia_gam FROM PUBLIC;
  REVOKE ALL ON public.vw_trafego_meta_financeiro_campanha_dia_gam FROM anon;
  REVOKE ALL ON public.vw_trafego_meta_financeiro_campanha_dia_gam FROM authenticated;
  REVOKE ALL ON public.vw_trafego_meta_financeiro_campanha_dia_gam FROM service_role;
  GRANT SELECT ON public.vw_trafego_meta_financeiro_campanha_dia_gam TO service_role;
END
$meta_financial$;

-- ---------------------------------------------------------------------------
-- Safe compatibility projection
-- ---------------------------------------------------------------------------
-- The old trigger updated or INSERTED `daily_campaign_metrics` for every GAM
-- key. That assumes every UTM is a campaign id. The replacement is fail-closed:
-- Meta, unknown and ambiguous keys remain only in the raw GAM fact table.
CREATE OR REPLACE FUNCTION public.sync_gam_revenue_to_daily_metrics()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $function$
DECLARE
  v_meta_matches   bigint;
  v_google_matches bigint;
BEGIN
  SELECT count(DISTINCT s.meta_adset_id)
    INTO v_meta_matches
    FROM public.trafego_meta_adset s
   WHERE s.external_id = NEW.utm_campaign_value
     AND s.ausente_desde IS NULL;

  -- A known Meta id is adset-grain revenue. It must never enter a table whose
  -- identity is campaign_id + date. Project mismatch is surfaced by the view;
  -- it is not "repaired" by writing to the wrong grain.
  IF v_meta_matches > 0 THEN
    RETURN NEW;
  END IF;

  SELECT count(*)
    INTO v_google_matches
    FROM public.campaigns c
   WHERE c.campaign_id = NEW.utm_campaign_value
     AND (NEW.project_id IS NULL OR c.project_id = NEW.project_id);

  -- Unknown and ambiguous keys remain safely in `gam_metrics`. In particular,
  -- the function no longer invents a zero-spend campaign merely because a GAM
  -- row arrived before its advertising catalog.
  IF v_google_matches <> 1 THEN
    RETURN NEW;
  END IF;

  UPDATE public.daily_campaign_metrics
     SET revenue               = NEW.revenue,
         gam_impressions       = NEW.gam_impressions,
         gam_clicks            = NEW.gam_clicks,
         gam_ctr               = NEW.gam_ctr,
         gam_ecpm              = NEW.gam_ecpm,
         gam_cpc               = NEW.gam_cpc,
         match_rate            = NEW.match_rate,
         unfilled_impressions  = NEW.unfilled_impressions,
         viewable_impressions  = NEW.viewable_impressions,
         updated_at            = now()
   WHERE campaign_id = NEW.utm_campaign_value
     AND date = NEW.date;

  IF NOT FOUND THEN
    INSERT INTO public.daily_campaign_metrics (
      campaign_id, date, revenue,
      gam_impressions, gam_clicks, gam_ctr, gam_ecpm, gam_cpc, match_rate,
      unfilled_impressions, viewable_impressions,
      spend, clicks, impressions, conversions, cpc, ctr, roas,
      cost_per_conversion, page_views, ecpm, viewability, pmr, rps
    ) VALUES (
      NEW.utm_campaign_value, NEW.date, NEW.revenue,
      NEW.gam_impressions, NEW.gam_clicks, NEW.gam_ctr, NEW.gam_ecpm,
      NEW.gam_cpc, NEW.match_rate, NEW.unfilled_impressions,
      NEW.viewable_impressions,
      0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    );
  END IF;

  RETURN NEW;
END
$function$;

COMMENT ON FUNCTION public.sync_gam_revenue_to_daily_metrics() IS
  'Compatibility projection for real legacy campaigns only. Meta adset ids, unknown keys and namespace ambiguities stay in gam_metrics and are diagnosed by vw_gam_attribution_route.';

-- Some portable installs have the function but not the trigger. Install it
-- exactly once; existing official installs keep their current trigger intact.
DO $trigger$
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM pg_trigger
     WHERE tgrelid = 'public.gam_metrics'::regclass
       AND tgname = 'sync_revenue_to_daily_metrics'
       AND NOT tgisinternal
  ) THEN
    CREATE TRIGGER sync_revenue_to_daily_metrics
      AFTER INSERT OR UPDATE ON public.gam_metrics
      FOR EACH ROW
      EXECUTE FUNCTION public.sync_gam_revenue_to_daily_metrics();
  END IF;
END
$trigger$;

DO $verify$
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname = 'vw_gam_attribution_route'
       AND c.reloptions @> ARRAY['security_invoker=true']
  ) THEN
    RAISE EXCEPTION 'GAM_ATTRIBUTION_ROUTER_UNSAFE_VIEW: security_invoker missing';
  END IF;

  IF EXISTS (
    SELECT 1
      FROM information_schema.role_table_grants
     WHERE table_schema = 'public'
       AND table_name = 'vw_gam_attribution_route'
       AND grantee IN ('PUBLIC', 'anon', 'authenticated')
  ) THEN
    RAISE EXCEPTION 'GAM_ATTRIBUTION_ROUTER_UNSAFE_GRANT';
  END IF;
END
$verify$;

COMMIT;
