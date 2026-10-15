-- =============================================================================
-- v21_01_rollback — desfaz v7_13 + v21_01 (PROPOSTA, NÃO APLICADA)
-- =============================================================================
-- Só derruba a tabela se ela estiver VAZIA: uma linha ali é um site cadastrado
-- com token da Meta, e apagá-la sem querer desliga o rastreamento daquele site.
-- `set_pautador_updated_at()` já existia em produção antes da v7_13 e fica.
-- Rodar com `psql -1 -v ON_ERROR_STOP=1`.
-- =============================================================================

DO $guarda$
DECLARE
  n bigint;
BEGIN
  IF to_regclass('public.meta_capi_sites') IS NULL THEN
    RAISE NOTICE 'v21_01_rollback: meta_capi_sites já não existe; nada a fazer';
    RETURN;
  END IF;
  EXECUTE 'SELECT count(*) FROM public.meta_capi_sites' INTO n;
  IF n > 0 THEN
    RAISE EXCEPTION 'v21_01_rollback: meta_capi_sites tem % linha(s); exporte antes de derrubar', n;
  END IF;
  EXECUTE 'DROP TABLE public.meta_capi_sites';
END
$guarda$;

NOTIFY pgrst, 'reload schema';
