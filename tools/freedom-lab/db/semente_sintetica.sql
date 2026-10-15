-- =============================================================================
-- semente_sintetica.sql — fixtures do banco descartável do Freedom Lab.
-- Nenhum dado real: e-mails @example.invalid, customer 0000000001, IDs fixos.
-- Reproduz as quatro classes de tabela que a identidade de leitura precisa
-- distinguir, mais a função SECURITY DEFINER aberta a PUBLIC (limite da v18_01).
-- O gate de `lab.sh semear` recusa este arquivo se achar e-mail real, JWT,
-- CPF/CNPJ formatado ou domínio da agência.
-- =============================================================================
BEGIN;
CREATE SCHEMA IF NOT EXISTS volc_lab;
CREATE TABLE IF NOT EXISTS volc_lab.migracao_aplicada (
  arquivo text NOT NULL, sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  aplicada_em timestamptz NOT NULL DEFAULT now(), base text NOT NULL, resultado text NOT NULL);
COMMENT ON SCHEMA volc_lab IS 'Ledger do laboratório; morre com o container. Não é fonte de verdade.';

-- classe 1: fato de mídia SEM RLS (aberto pelo default ACL da imagem Supabase)
CREATE TABLE public.google_ads_campanha_dia (customer_id text, campaign_id text, dia date, custo_micros bigint);
INSERT INTO public.google_ads_campanha_dia VALUES ('0000000001','1','2026-10-01',1000000);
-- classe 2: RLS forçada e zero policy (padrão v12_04/v13_01)
CREATE TABLE public.trafego_coleta_execucao (id int, estado text);
ALTER TABLE public.trafego_coleta_execucao ENABLE ROW LEVEL SECURITY, FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.trafego_coleta_execucao FROM anon, authenticated;
INSERT INTO public.trafego_coleta_execucao VALUES (1,'ok');
-- classe 3: view security_invoker sobre a tabela RLS
CREATE VIEW public.trafego_coleta_execucao_saude WITH (security_invoker = true) AS
  SELECT estado, count(*) n FROM public.trafego_coleta_execucao GROUP BY 1;
-- o resto da allowlist da v18_01, para que NENHUM item seja pulado no lab
CREATE TABLE public.google_ads_fato_granular (customer_id text, dia date, custo_micros bigint);
CREATE TABLE public.google_ads_fato_granular_asset (LIKE public.google_ads_fato_granular);
CREATE TABLE public.google_ads_fato_granular_geo (LIKE public.google_ads_fato_granular);
CREATE TABLE public.google_ads_fato_granular_hora_dispositivo (LIKE public.google_ads_fato_granular);
CREATE TABLE public.google_ads_fato_granular_keyword (LIKE public.google_ads_fato_granular);
CREATE TABLE public.google_ads_fato_granular_placement (LIKE public.google_ads_fato_granular);
CREATE TABLE public.google_ads_fato_granular_termo (LIKE public.google_ads_fato_granular);
CREATE TABLE public.google_ads_fato_granular_url (LIKE public.google_ads_fato_granular);
CREATE TABLE public.trafego_meta_insight_daily (ad_account text, dia date, spend numeric);
ALTER TABLE public.trafego_meta_insight_daily ENABLE ROW LEVEL SECURITY;
CREATE VIEW public.vw_gads_campanha_dia WITH (security_invoker = true) AS
  SELECT customer_id, campaign_id, dia, custo_micros FROM public.google_ads_campanha_dia;
-- classe 4: pessoa e segredo — nunca na allowlist
CREATE TABLE public.users (id int, email text, password_hash text);
INSERT INTO public.users VALUES (1,'pessoa@example.invalid','x');
CREATE TABLE public.meta_business_credentials (id int, segredo text);
-- SECURITY DEFINER mutável executável por PUBLIC (o buraco que a v18_01 NÃO fecha)
CREATE FUNCTION public.fn_definer_grava() RETURNS void LANGUAGE sql SECURITY DEFINER
  AS $f$ INSERT INTO public.google_ads_campanha_dia VALUES ('x','x',current_date,0) $f$;
COMMIT;
