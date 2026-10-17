-- Rollback da candidata item5_0002. Recusa se já houver cotação ou conversão registrada (seria apagar histórico);
-- nesse caso o rollback seguro é parar novas conversões:
--   REVOKE EXECUTE ON FUNCTION public.volc_convert_revenue(text, date, bigint, text, text, text, text, timestamptz) FROM service_role;
BEGIN;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM public.revenue_conversion) OR EXISTS (SELECT 1 FROM public.fx_rate_observation) THEN
    RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'há cotação ou conversão registrada: rollback recusado (use o REVOKE do cabeçalho)';
  END IF;
END $$;
DROP FUNCTION public.volc_convert_revenue(text, date, bigint, text, text, text, text, timestamptz);
DROP TABLE public.revenue_conversion;
DROP FUNCTION public.fx_rate_as_of(text, text, text, date, timestamptz);
DROP TABLE public.fx_rate_observation;
DROP FUNCTION public.fx_append_only();
COMMIT;
