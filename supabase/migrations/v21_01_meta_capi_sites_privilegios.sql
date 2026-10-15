-- =============================================================================
-- v21_01 — privilégios de public.meta_capi_sites (PROPOSTA, NÃO APLICADA)
-- =============================================================================
-- Contexto (15/10/2026): /api/meta-capi/sites responde 500 porque a tabela não
-- existe em produção — `src/sql/v7_13_meta_capi_sites.sql` nunca foi aplicada.
--
-- NÃO APLICAR SOZINHO. Este arquivo é PARTE de
-- `supabase/migrations/v21_pacote_aplicar.sql` (montado por
-- `scripts/montar-pacote-v21.sh`), que roda v7_13 + v21_01 + v6_01..v6_05 +
-- v21_02 numa transação só. Aplicado à parte, a v7_13 confirmaria antes deste
-- arquivo, e nesse intervalo a anon teria SELECT, DELETE e TRUNCATE na tabela.
-- Uso isolado só como remédio, se a tabela já existir sem estes privilégios.
--
-- POR QUE ESTE ARQUIVO EXISTE: em produção o default ACL de `public` concede
-- `arwdDxt` a anon e authenticated em toda tabela nova (medido em 24/08 e
-- reconfirmado em 15/10). A v7_13 liga RLS sem policy, o que esconde as linhas
-- via PostgREST, mas deixa GRANT de TRUNCATE/REFERENCES/TRIGGER aberto, e
-- TRUNCATE não passa por RLS. A tabela guarda o token da Meta cifrado: só o
-- service_role (backend e Edge Function capi-router) precisa dela.
-- =============================================================================

DO $guarda$
BEGIN
  IF to_regclass('public.meta_capi_sites') IS NULL THEN
    RAISE EXCEPTION 'v21_01: aplique src/sql/v7_13_meta_capi_sites.sql antes';
  END IF;
END
$guarda$;

REVOKE ALL ON TABLE public.meta_capi_sites FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.meta_capi_sites_id_seq FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.meta_capi_sites TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.meta_capi_sites_id_seq TO service_role;

NOTIFY pgrst, 'reload schema';
