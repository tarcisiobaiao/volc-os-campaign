"""Proves the GAM key router against a disposable PostgreSQL cluster.

The production defect is a grain defect, so string assertions are not enough:
this suite executes the trigger and proves which rows may and may not reach the
legacy campaign/day table. It never connects to the official Supabase.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20260910143000_gam_attribution_grain_router.sql"


@pytest.fixture(scope="module")
def postgres():
    missing = [name for name in ("initdb", "pg_ctl", "psql") if shutil.which(name) is None]
    if missing:
        pytest.skip("PostgreSQL binaries unavailable: " + ", ".join(missing))

    base = Path(tempfile.mkdtemp(prefix="volc-gam-router-pg."))
    data, socket = base / "data", base / "socket"
    socket.mkdir(parents=True)
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, env=env, capture_output=True, text=True)

    try:
        result = run("initdb", "-D", str(data), "-U", "postgres", "--encoding=UTF8", "--locale=C")
        assert result.returncode == 0, result.stderr
        result = run("pg_ctl", "-D", str(data), "-l", str(base / "postgres.log"),
                     "-o", f"-k {socket} -h ''", "-w", "start")
        assert result.returncode == 0, result.stderr

        db_env = {**env, "PGHOST": str(socket), "PGUSER": "postgres", "PGDATABASE": "postgres"}

        def sql(statement: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-At", "-c", statement],
                env=db_env, capture_output=True, text=True,
            )

        def apply() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-f", str(MIGRATION)],
                env=db_env, capture_output=True, text=True,
            )

        schema = sql("""
          CREATE ROLE anon NOLOGIN;
          CREATE ROLE authenticated NOLOGIN;
          CREATE ROLE service_role NOLOGIN BYPASSRLS;

          CREATE TABLE public.campaigns (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            project_id bigint,
            campaign_id text NOT NULL UNIQUE
          );

          CREATE TABLE public.daily_campaign_metrics (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            campaign_id text NOT NULL,
            date date NOT NULL,
            revenue numeric DEFAULT 0,
            gam_impressions bigint DEFAULT 0,
            gam_clicks bigint DEFAULT 0,
            gam_ctr numeric DEFAULT 0,
            gam_ecpm numeric DEFAULT 0,
            gam_cpc numeric DEFAULT 0,
            match_rate numeric DEFAULT 0,
            unfilled_impressions bigint DEFAULT 0,
            viewable_impressions numeric DEFAULT 0,
            spend numeric NOT NULL DEFAULT 0,
            clicks bigint NOT NULL DEFAULT 0,
            impressions bigint NOT NULL DEFAULT 0,
            conversions numeric DEFAULT 0,
            cpc numeric NOT NULL DEFAULT 0,
            ctr numeric NOT NULL DEFAULT 0,
            roas numeric NOT NULL DEFAULT 0,
            cost_per_conversion numeric DEFAULT 0,
            page_views bigint DEFAULT 0,
            ecpm numeric DEFAULT 0,
            viewability numeric DEFAULT 0,
            pmr numeric DEFAULT 0,
            rps numeric DEFAULT 0,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (campaign_id, date)
          );

          CREATE TABLE public.gam_metrics (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            date date NOT NULL,
            utm_campaign_value text NOT NULL,
            revenue numeric NOT NULL DEFAULT 0,
            revenue_converted numeric DEFAULT 0,
            gam_accounts_id text NOT NULL,
            project_id bigint,
            gam_impressions bigint,
            gam_clicks bigint,
            gam_ctr numeric,
            gam_ecpm numeric,
            gam_cpc numeric,
            match_rate numeric,
            unfilled_impressions bigint,
            viewable_impressions numeric,
            updated_at timestamptz DEFAULT now(),
            UNIQUE (date, utm_campaign_value, gam_accounts_id)
          );

          CREATE TABLE public.trafego_meta_campaign (
            meta_campaign_id uuid PRIMARY KEY,
            ad_account_ativo_id text NOT NULL,
            external_id text NOT NULL,
            ausente_desde timestamptz
          );

          CREATE TABLE public.trafego_meta_adset (
            meta_adset_id uuid PRIMARY KEY,
            meta_campaign_id uuid NOT NULL REFERENCES public.trafego_meta_campaign(meta_campaign_id),
            external_id text NOT NULL,
            ausente_desde timestamptz
          );

          CREATE TABLE public.trafego_meta_project_binding (
            binding_id uuid PRIMARY KEY,
            ad_account_ativo_id text NOT NULL,
            project_id bigint NOT NULL,
            desfeito_em timestamptz
          );
        """)
        assert schema.returncode == 0, schema.stderr
        yield {"sql": sql, "apply": apply}
    finally:
        subprocess.run(
            ["pg_ctl", "-D", str(data), "-m", "immediate", "stop"],
            env=env, capture_output=True, text=True,
        )
        shutil.rmtree(base, ignore_errors=True)


def scalar(pg, statement: str) -> str:
    result = pg["sql"](statement)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_migration_is_replayable_and_installs_one_trigger(postgres):
    first = postgres["apply"]()
    assert first.returncode == 0, first.stderr

    # Simulate the canonical Meta insight views being installed after the
    # router. Replaying the migration must then add the project-scoped revenue
    # views without changing the trigger count.
    meta_views = postgres["sql"]("""
      CREATE TABLE public.fixture_meta_fin_adset (
        ad_account_ativo_id text,
        account_external_id text,
        campaign_id text,
        adset_id text,
        meta_campaign_id uuid,
        meta_adset_id uuid,
        date date,
        metric_scope text,
        metric_version text,
        currency text,
        timezone text,
        spend numeric,
        impressions bigint,
        clicks bigint,
        reach bigint,
        completo boolean,
        source_freshness timestamptz,
        source text
      );
      CREATE VIEW public.vw_trafego_meta_financeiro_conjunto_dia
      WITH (security_invoker=true) AS SELECT * FROM public.fixture_meta_fin_adset;

      CREATE TABLE public.fixture_meta_fin_campaign (
        ad_account_ativo_id text,
        account_external_id text,
        campaign_id text,
        meta_campaign_id uuid,
        date date,
        metric_scope text,
        metric_version text,
        currency text,
        timezone text,
        moedas_no_dia bigint,
        fusos_no_dia bigint,
        conjuntos_no_dia bigint,
        linhas_incompletas bigint,
        spend numeric,
        impressions bigint,
        clicks bigint,
        reach bigint,
        conjuntos_conhecidos_na_campanha bigint,
        completo boolean,
        source_freshness timestamptz,
        source text
      );
      CREATE VIEW public.vw_trafego_meta_financeiro_campanha_dia
      WITH (security_invoker=true) AS SELECT * FROM public.fixture_meta_fin_campaign;
    """)
    assert meta_views.returncode == 0, meta_views.stderr

    second = postgres["apply"]()
    assert second.returncode == 0, second.stderr
    assert scalar(postgres, """
      SELECT count(*) FROM pg_trigger
      WHERE tgrelid='public.gam_metrics'::regclass
        AND tgname='sync_revenue_to_daily_metrics' AND NOT tgisinternal;
    """) == "1"
    assert scalar(postgres, """
      SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relname IN (
        'vw_trafego_meta_financeiro_conjunto_dia_gam',
        'vw_trafego_meta_financeiro_campanha_dia_gam'
      );
    """) == "2"


def test_google_campaign_is_the_only_route_projected_to_legacy(postgres):
    result = postgres["sql"]("""
      INSERT INTO public.campaigns(project_id,campaign_id) VALUES (10,'111');
      INSERT INTO public.gam_metrics(
        date,utm_campaign_value,revenue,gam_accounts_id,project_id,
        gam_impressions,gam_clicks,gam_ctr,gam_ecpm
      ) VALUES ('2026-09-09','111',123.45,'gam-1',10,1000,20,2,123.45);
    """)
    assert result.returncode == 0, result.stderr
    assert scalar(postgres, """
      SELECT campaign_id || '|' || date || '|' || revenue
      FROM public.daily_campaign_metrics WHERE campaign_id='111';
    """) == "111|2026-09-09|123.45"
    assert scalar(postgres, """
      SELECT attribution_route FROM public.vw_gam_attribution_route
      WHERE utm_campaign_value='111';
    """) == "GOOGLE_CAMPAIGN"


def test_meta_adset_stays_at_adset_grain_and_never_creates_fake_campaign(postgres):
    result = postgres["sql"]("""
      INSERT INTO public.trafego_meta_campaign(
        meta_campaign_id,ad_account_ativo_id,external_id
      ) VALUES ('00000000-0000-0000-0000-000000000201','meta-account-1','222');
      INSERT INTO public.trafego_meta_adset(
        meta_adset_id,meta_campaign_id,external_id
      ) VALUES (
        '00000000-0000-0000-0000-000000000301',
        '00000000-0000-0000-0000-000000000201','333'
      );
      INSERT INTO public.trafego_meta_project_binding(
        binding_id,ad_account_ativo_id,project_id
      ) VALUES ('00000000-0000-0000-0000-000000000401','meta-account-1',10);
      INSERT INTO public.gam_metrics(
        date,utm_campaign_value,revenue,gam_accounts_id,project_id
      ) VALUES ('2026-09-09','333',80,'gam-1',10);
    """)
    assert result.returncode == 0, result.stderr
    assert scalar(postgres, """
      SELECT count(*) FROM public.daily_campaign_metrics WHERE campaign_id='333';
    """) == "0"
    assert scalar(postgres, """
      SELECT attribution_route || '|' || meta_campaign_external_id
      FROM public.vw_gam_attribution_route WHERE utm_campaign_value='333';
    """) == "META_ADSET|222"


def test_unknown_key_is_visible_but_does_not_invent_campaign(postgres):
    result = postgres["sql"]("""
      INSERT INTO public.daily_campaign_metrics(campaign_id,date,revenue)
      VALUES ('444','2026-09-08',7);
      INSERT INTO public.gam_metrics(
        date,utm_campaign_value,revenue,gam_accounts_id,project_id
      ) VALUES ('2026-09-09','444',999,'gam-1',10);
    """)
    assert result.returncode == 0, result.stderr
    assert scalar(postgres, """
      SELECT count(*) FROM public.daily_campaign_metrics WHERE campaign_id='444';
    """) == "1"
    assert scalar(postgres, """
      SELECT revenue FROM public.daily_campaign_metrics
      WHERE campaign_id='444' AND date='2026-09-08';
    """) == "7"
    assert scalar(postgres, """
      SELECT attribution_route FROM public.vw_gam_attribution_route
      WHERE utm_campaign_value='444';
    """) == "UNMATCHED"


def test_namespace_collision_and_project_mismatch_fail_closed(postgres):
    result = postgres["sql"]("""
      INSERT INTO public.campaigns(project_id,campaign_id) VALUES (10,'333');
      INSERT INTO public.gam_metrics(
        date,utm_campaign_value,revenue,gam_accounts_id,project_id
      ) VALUES
        ('2026-09-10','333',10,'gam-1',10),
        ('2026-09-11','333',10,'gam-1',99);
    """)
    assert result.returncode == 0, result.stderr
    assert scalar(postgres, """
      SELECT count(*) FROM public.daily_campaign_metrics WHERE campaign_id='333';
    """) == "0"
    assert scalar(postgres, """
      SELECT string_agg(attribution_route, ',' ORDER BY date)
      FROM public.vw_gam_attribution_route
      WHERE utm_campaign_value='333' AND date >= '2026-09-10';
    """) == "AMBIGUOUS_NAMESPACE,META_ADSET_PROJECT_UNBOUND_OR_MISMATCHED"


def test_existing_google_row_is_updated_without_touching_delivery(postgres):
    result = postgres["sql"]("""
      INSERT INTO public.daily_campaign_metrics(
        campaign_id,date,revenue,spend,clicks,impressions
      ) VALUES ('111','2026-09-10',1,50,7,700);
      INSERT INTO public.gam_metrics(
        date,utm_campaign_value,revenue,gam_accounts_id,project_id
      ) VALUES ('2026-09-10','111',75,'gam-1',10);
    """)
    assert result.returncode == 0, result.stderr
    assert scalar(postgres, """
      SELECT revenue || '|' || spend || '|' || clicks || '|' || impressions
      FROM public.daily_campaign_metrics
      WHERE campaign_id='111' AND date='2026-09-10';
    """) == "75|50|7|700"


def test_meta_financial_views_join_at_adset_and_roll_up_children(postgres):
    result = postgres["sql"]("""
      INSERT INTO public.fixture_meta_fin_adset VALUES (
        'meta-account-1','meta-external-1','222','333',
        '00000000-0000-0000-0000-000000000201',
        '00000000-0000-0000-0000-000000000301',
        '2026-09-09','adset','meta-atribuicao-adset-v1','BRL',
        'America/Sao_Paulo',20,1000,20,900,true,now(),'META_ADS'
      );
      INSERT INTO public.fixture_meta_fin_campaign VALUES (
        'meta-account-1','meta-external-1','222',
        '00000000-0000-0000-0000-000000000201',
        '2026-09-09','campaign_rollup_de_adset','meta-atribuicao-adset-v1',
        'BRL','America/Sao_Paulo',1,1,1,0,20,1000,20,NULL,1,true,now(),'META_ADS'
      );
    """)
    assert result.returncode == 0, result.stderr
    assert scalar(postgres, """
      SELECT mapping_status || '|' || project_id || '|' || gam_revenue_original
      FROM public.vw_trafego_meta_financeiro_conjunto_dia_gam
      WHERE adset_id='333' AND date='2026-09-09';
    """) == "FATURAMENTO_ATRIBUIDO_VIA_ADSET|10|80"
    assert scalar(postgres, """
      SELECT revenue_rollup_status || '|' || gam_revenue_original
      FROM public.vw_trafego_meta_financeiro_campanha_dia_gam
      WHERE campaign_id='222' AND date='2026-09-09';
    """) == "FATURAMENTO_SOMADO_DOS_CONJUNTOS|80"


def test_diagnostic_view_is_not_granted_to_browser_roles(postgres):
    assert scalar(postgres, """
      SELECT count(*) FROM information_schema.role_table_grants
      WHERE table_schema='public' AND table_name='vw_gam_attribution_route'
        AND grantee IN ('PUBLIC','anon','authenticated');
    """) == "0"
    assert scalar(postgres, """
      SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relname='vw_gam_attribution_route'
        AND c.reloptions @> ARRAY['security_invoker=true'];
    """) == "1"
