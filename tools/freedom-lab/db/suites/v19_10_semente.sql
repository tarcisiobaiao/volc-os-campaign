-- db/suites/v19_10_semente.sql — linhas sintéticas para a suíte v19_10 exercitar gatilhos de verdade.
-- Base: seed do revisor local de 15/10 (/private/tmp/claude-502/v1910/seed.sql + seed2.sql). Só @example.invalid,
-- ids 9001, domínios .example. Aplicada como supabase_admin depois da semente do pacote anon.
\set ON_ERROR_STOP on
BEGIN;
INSERT INTO public.system_settings (key, value) VALUES ('dollar_exchange_rate', '5.5');
INSERT INTO public.exchange_rate_history (rate, effective_date) VALUES (5.4, current_date - 10);
INSERT INTO public.tax_history (month, percentage, effective_date) VALUES (date_trunc('month', current_date)::date, 10, now());
INSERT INTO public.projects (id, project_name, main_url, domain, start_date, status, revshare) VALUES (9001, 'p1.example', 'https://p1.example', 'p1.example', current_date - 30, 'Active', 0.2);
INSERT INTO public.campaigns (id, project_id, campaign_name, campaign_id, start_date, status) VALUES (9001, 9001, 'c1 / p1.example', '123456789', current_date - 30, 'Active');
INSERT INTO public.campaign_funnel_urls (campaign_id, url, "Active") VALUES ('123456789', 'p1.example/a', true);
INSERT INTO public.adsense_metrics (date, url, revenue) VALUES (current_date, 'p1.example/a', 10);
INSERT INTO public.daily_campaign_metrics (campaign_id, date, revenue, spend) VALUES ('123456789', current_date, 1, 2) ON CONFLICT (campaign_id, date) DO UPDATE SET revenue=1, spend=2;
INSERT INTO public.daily_project_metrics (project_id, url_projeto, date, revenue, revenue_converted) VALUES (9001, 'p1.example', current_date, 3, 0);
INSERT INTO public.gam_metrics (date, utm_campaign_value, revenue, gam_accounts_id) VALUES (current_date, '123456789', 2, 'g1');
UPDATE public.gam_metrics SET revenue_converted = 0;  -- força update_all_revenue_conversions a tocar a linha
UPDATE public.daily_campaign_metrics SET revenue_converted = 0;
UPDATE public.adsense_metrics SET revenue_converted = 0;
INSERT INTO public.incubator_sites (id, site_name, site_niche, site_audience, wp_url) VALUES (9001, 's1', 'n', 'a', 'https://s1.example');
INSERT INTO public.incubator_articles (id, site_id, title) VALUES (9001, 9001, 't1');
INSERT INTO public.pautador_runs (id, country) VALUES (9001, 'BR');
INSERT INTO public.pautador_opportunities (id, run_id, country, keyword, main_keyword, tier, category) VALUES (9001, 9001, 'BR', 'k', 'k', 'S', 'S1');
INSERT INTO public.pautador_entities (id, country_code, canonical_name, slug) VALUES (9001, 'BR', 'e', 'e');
INSERT INTO public.pautador_entity_opportunities (id, entity_id, country_code) VALUES (9001, 9001, 'BR');
INSERT INTO public.operational_cost_categories (id, name) VALUES (9001, 'cat1');
INSERT INTO public.operational_costs (id, name, amount, category_id, month) VALUES (9001, 'cost1', 10, 9001, date_trunc('month', current_date)::date);
INSERT INTO public.user_campaigns (user_id, campaign_id) VALUES ('b0000000-0000-4000-8000-00000000000b', '123456789');
INSERT INTO public.user_projects (user_id, project_id) VALUES ('b0000000-0000-4000-8000-00000000000b', 9001);
COMMIT;
select 'gam', revenue_converted from public.gam_metrics; select 'dcm', revenue_converted from public.daily_campaign_metrics;
BEGIN;
SET LOCAL session_replication_role = replica;
UPDATE public.gam_metrics SET revenue_converted = 0;
UPDATE public.daily_campaign_metrics SET revenue_converted = 0;
UPDATE public.daily_project_metrics SET revenue_converted = 0;
UPDATE public.adsense_metrics SET revenue_converted = 0;
UPDATE public.users SET commission_percentage = 5 WHERE role='OPERATOR';
COMMIT;

-- Vítima dos ataques da revisão de 15/10 (ciclo 2): outro projeto, outra campanha,
-- sem vínculo com o operador sintético.
BEGIN;
INSERT INTO public.projects (id, project_name, main_url, domain, start_date, status, revshare) VALUES (9002, 'p2v.example', 'https://p2v.example', 'p2v.example', current_date - 30, 'Active', 0.2);
INSERT INTO public.campaigns (id, project_id, campaign_name, campaign_id, start_date, status) VALUES (9002, 9002, 'v1 / p2v.example', '222222222', current_date - 30, 'Active');
INSERT INTO public.campaign_funnel_urls (campaign_id, url, "Active") VALUES ('222222222', 'p2v.example/x', true);
INSERT INTO public.adsense_metrics (date, url, revenue) VALUES (current_date, 'p2v.example/x', 50);
INSERT INTO public.daily_campaign_metrics (campaign_id, date, revenue, spend, revenue_converted_revshare) VALUES ('222222222', current_date, 1, 2, 486) ON CONFLICT (campaign_id, date) DO UPDATE SET revenue_converted_revshare = 486;
COMMIT;
