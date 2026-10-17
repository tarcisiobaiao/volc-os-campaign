-- CANDIDATA (item 5, 2026-10-17). NÃO APLICADA. Contrato append-only de cotação USD/BRL e de conversão única.
-- Aplicar só com autorização nominal do dono e o sha256 deste arquivo. Não altera nenhuma tabela ou função legada.
--
-- Regras (CONTRATO-COTACAO-USD-BRL.md):
--  * cotação é observação append-only com fonte, referência, vigência [valid_from, valid_to) e instante de registro;
--    correção é uma linha nova que aponta `supersedes`, nunca UPDATE;
--  * fx_rate_as_of(...) resolve a taxa vigente para um dia COMO ERA CONHECIDA num instante (as_of); sem linha
--    válida devolve vazio: não existe fallback (nada de 5,2/5,5/5,25 implícito);
--  * a conversão é um evento append-only por observação de receita e cotação (unique), com micros half-even;
--    converter de novo um valor já convertido é recusado; mudar a cotação nunca reescreve conversões anteriores.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE public.fx_rate_observation (
  fx_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  base_currency text NOT NULL CHECK (base_currency ~ '^[A-Z]{3}$'),
  quote_currency text NOT NULL CHECK (quote_currency ~ '^[A-Z]{3}$' AND quote_currency <> base_currency),
  rate numeric(20, 10) NOT NULL CHECK (rate > 0),
  rate_kind text NOT NULL CHECK (rate_kind IN ('ptax_venda', 'ptax_compra', 'contratual', 'atestada_dono')),
  source text NOT NULL CHECK (btrim(source) <> ''),
  source_ref text NOT NULL CHECK (btrim(source_ref) <> ''),
  valid_from date NOT NULL,
  valid_to date CHECK (valid_to IS NULL OR valid_to > valid_from),
  published_at timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  recorded_by text NOT NULL CHECK (btrim(recorded_by) <> ''),
  supersedes uuid REFERENCES public.fx_rate_observation(fx_id),
  payload_sha256 text CHECK (payload_sha256 IS NULL OR payload_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX fx_rate_observation_lookup_ix ON public.fx_rate_observation (base_currency, quote_currency, rate_kind, valid_from DESC, recorded_at DESC);

CREATE FUNCTION public.fx_append_only() RETURNS trigger LANGUAGE plpgsql SET search_path TO 'pg_catalog', 'public' AS $$
BEGIN RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'append-only: corrija com uma linha nova (supersedes)'; END $$;
CREATE TRIGGER fx_rate_observation_append_only BEFORE UPDATE OR DELETE ON public.fx_rate_observation
  FOR EACH ROW EXECUTE FUNCTION public.fx_append_only();

-- Taxa vigente para p_dia, como conhecida em p_as_of. Vazio quando não há prova: o chamador grava 'nao_convertido'.
CREATE FUNCTION public.fx_rate_as_of(p_base text, p_quote text, p_kind text, p_dia date, p_as_of timestamptz)
RETURNS TABLE (fx_id uuid, rate numeric, source text, source_ref text, valid_from date, valid_to date, recorded_at timestamptz)
LANGUAGE sql STABLE SET search_path TO 'pg_catalog', 'public' AS $$
  SELECT f.fx_id, f.rate, f.source, f.source_ref, f.valid_from, f.valid_to, f.recorded_at
    FROM public.fx_rate_observation f
   WHERE f.base_currency = p_base AND f.quote_currency = p_quote AND f.rate_kind = p_kind
     AND f.valid_from <= p_dia AND (f.valid_to IS NULL OR p_dia < f.valid_to)
     AND f.recorded_at <= p_as_of
     AND NOT EXISTS (SELECT 1 FROM public.fx_rate_observation c
                      WHERE c.supersedes = f.fx_id AND c.recorded_at <= p_as_of)
   ORDER BY f.valid_from DESC, f.recorded_at DESC
   LIMIT 1
$$;

CREATE TABLE public.revenue_conversion (
  conversion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_table text NOT NULL CHECK (source_table IN ('joinads_observation')),
  observation_key text NOT NULL,
  metric_date date NOT NULL,
  revenue_original_micros bigint NOT NULL CHECK (revenue_original_micros >= 0),
  currency_original text NOT NULL CHECK (currency_original ~ '^[A-Z]{3}$'),
  currency_original_status text NOT NULL CHECK (currency_original_status IN ('observed', 'attested')),
  fx_id uuid NOT NULL REFERENCES public.fx_rate_observation(fx_id),
  rate numeric(20, 10) NOT NULL,
  revenue_converted_micros bigint NOT NULL CHECK (revenue_converted_micros >= 0),
  currency_converted text NOT NULL CHECK (currency_converted ~ '^[A-Z]{3}$' AND currency_converted <> currency_original),
  rounding text NOT NULL DEFAULT 'half_even_micros' CHECK (rounding = 'half_even_micros'),
  as_of timestamptz NOT NULL,
  converted_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_table, observation_key, fx_id)
);
CREATE TRIGGER revenue_conversion_append_only BEFORE UPDATE OR DELETE ON public.revenue_conversion
  FOR EACH ROW EXECUTE FUNCTION public.fx_append_only();

-- Conversão única: micros × taxa com arredondamento half-even; recusa entrada já convertida; idempotente.
CREATE FUNCTION public.volc_convert_revenue(p_observation_key text, p_metric_date date, p_revenue_micros bigint,
                                            p_currency text, p_currency_status text, p_target text, p_kind text,
                                            p_as_of timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'public' AS $$
DECLARE
  t record;
  v_bruto numeric;
  v_conv bigint;
  v_id uuid;
BEGIN
  IF p_revenue_micros IS NULL THEN
    RETURN jsonb_build_object('status', 'nao_convertido', 'motivo', 'receita_ausente');
  END IF;
  IF p_currency_status NOT IN ('observed', 'attested') THEN
    RETURN jsonb_build_object('status', 'nao_convertido', 'motivo', 'moeda_original_nao_provada');
  END IF;
  IF p_currency = p_target THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'valor já está na moeda alvo: conversão recusada';
  END IF;
  SELECT * INTO t FROM public.fx_rate_as_of(p_currency, p_target, p_kind, p_metric_date, p_as_of);
  IF NOT FOUND THEN
    RETURN jsonb_build_object('status', 'nao_convertido', 'motivo', 'cotacao_vigente_nao_provada');
  END IF;
  v_bruto := p_revenue_micros * t.rate;
  v_conv := round(v_bruto, 0);
  IF v_bruto - trunc(v_bruto) = 0.5 AND v_conv % 2 = 1 THEN
    v_conv := v_conv - 1;  -- half-even: empate vai para o par (round() do numeric arredonda o empate para longe do zero)
  END IF;
  INSERT INTO public.revenue_conversion (source_table, observation_key, metric_date, revenue_original_micros, currency_original,
                                         currency_original_status, fx_id, rate, revenue_converted_micros, currency_converted, as_of)
  VALUES ('joinads_observation', p_observation_key, p_metric_date, p_revenue_micros, p_currency, p_currency_status,
          t.fx_id, t.rate, v_conv, p_target, p_as_of)
  ON CONFLICT (source_table, observation_key, fx_id) DO NOTHING
  RETURNING conversion_id INTO v_id;
  RETURN jsonb_build_object('status', 'convertido', 'idempotente', v_id IS NULL, 'fx_id', t.fx_id, 'rate', t.rate,
                            'source', t.source, 'valid_from', t.valid_from, 'revenue_converted_micros', v_conv);
END $$;

REVOKE ALL ON public.fx_rate_observation, public.revenue_conversion FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON public.fx_rate_observation TO service_role;
GRANT SELECT ON public.revenue_conversion TO service_role;
REVOKE ALL ON FUNCTION public.volc_convert_revenue(text, date, bigint, text, text, text, text, timestamptz) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.volc_convert_revenue(text, date, bigint, text, text, text, text, timestamptz) TO service_role;
ALTER TABLE public.fx_rate_observation ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.revenue_conversion ENABLE ROW LEVEL SECURITY;
COMMIT;
