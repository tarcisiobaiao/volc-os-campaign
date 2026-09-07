-- =============================================================================
-- ROLLBACK — registro de midia Meta (20260908020000)
-- =============================================================================
-- ⚠️ NUNCA ENTRA NUMA LISTA DE APPLY. Ele pertence a
-- `rollback_files_never_in_apply` do SCHEMA-DEPLOY-MANIFEST.json, e um glob de
-- diretorio que o inclua e erro de CONSTRUCAO da janela, nao aviso.
--
-- ⚠️ E ELE DESTROI RECIBO. Depois de existir UM registro real nesta tabela,
-- rodar isto apaga a unica prova de quais bytes ja viraram ativo naquela conta
-- — e a proxima tentativa reenviaria tudo, duplicando a biblioteca do cliente.
-- Depois de dados reais a compensacao e para frente, nunca este arquivo.
--
-- O uso legitimo e um so: desfazer a janela em Postgres DESCARTAVEL, ou
-- desfazer uma aplicacao que ainda nao registrou nada.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
DECLARE v_linhas bigint;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'rollback de meta_asset_registration exige postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF to_regclass('public.trafego_meta_asset_registration') IS NULL THEN
    RAISE EXCEPTION 'meta_asset_registration nao esta aplicado; nada a desfazer';
  END IF;
  EXECUTE 'SELECT count(*) FROM public.trafego_meta_asset_registration' INTO v_linhas;
  IF v_linhas > 0 AND coalesce(current_setting('volc.rollback_destrutivo_autorizado', true), '') <> 'sim' THEN
    -- A recusa e o ponto. Um rollback que apaga recibo real precisa de um ato
    -- deliberado, e nao de um script rodado por engano numa janela apertada.
    RAISE EXCEPTION
      'recusado: % recibo(s) de registro existem. Apagar perde a prova de quais bytes ja viraram ativo. Para prosseguir em base descartavel: SET volc.rollback_destrutivo_autorizado = ''sim''',
      v_linhas;
  END IF;
END
$guarda$;

DROP FUNCTION IF EXISTS public.trafego_meta_falhar_registro_ativo(uuid, text, uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_marcar_registro_ativo_ambiguo(uuid, uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_concluir_registro_ativo(uuid, text, uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_reservar_registro_ativo(text, text, text, text);
DROP TABLE IF EXISTS public.trafego_meta_asset_registration;

COMMIT;
