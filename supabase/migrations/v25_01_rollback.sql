-- =============================================================================
-- v25_01 rollback — W14: remove o registro de conversões offline.
--
-- Recusa se houver QUALQUER linha nas três tabelas: elas são o rastro de envio
-- (o que foi decidido, validado e mandado ao Google). Apagar esse rastro faria
-- um reenvio parecer o primeiro. Com dado, exporte e decida antes; este
-- arquivo não apaga histórico. Idempotente: sem as tabelas, não faz nada.
-- Aplicar pelo mesmo papel que aplicou a v25_01 (dono).
-- =============================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $rb$
DECLARE
  n bigint := 0;
BEGIN
  IF to_regclass('public.conversao_offline_decisao') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.conversao_offline_decisao' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'v25_01 rollback: conversao_offline_decisao tem % linha(s); o rastro não é apagado', n
        USING ERRCODE = '55000';
    END IF;
  END IF;
  IF to_regclass('public.conversao_offline_lote') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.conversao_offline_lote' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'v25_01 rollback: conversao_offline_lote tem % linha(s); o rastro não é apagado', n
        USING ERRCODE = '55000';
    END IF;
  END IF;
END
$rb$;

DROP FUNCTION IF EXISTS public.conversao_offline_fechar_lote(bigint, text, text, jsonb);
DROP FUNCTION IF EXISTS public.conversao_offline_abrir_lote(jsonb);
DROP VIEW IF EXISTS public.conversao_offline_envio_por_coorte;
DROP TABLE IF EXISTS public.conversao_offline_item;
DROP TABLE IF EXISTS public.conversao_offline_lote;
DROP TABLE IF EXISTS public.conversao_offline_decisao;
DROP FUNCTION IF EXISTS public.conversao_offline_imutavel();

NOTIFY pgrst, 'reload schema';

COMMIT;
