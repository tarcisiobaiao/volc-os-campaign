-- =====================================================================
-- v6 RBAC — Etapa 1 / Arquivo 5 de 6
-- Funções auxiliares do novo modelo. NOMES NOVOS, prefixados v6_*.
-- Não substituem nenhuma função existente. Não criam triggers.
--
-- Pré-requisito: a função public.get_tax_rate_for_date(date) já existe
-- em produção (usada pelo cálculo legado calculate_operator_commission).
--
-- Idempotente via CREATE OR REPLACE.
-- =====================================================================

-- ----------------------------------------------------------------------
-- v6_get_active_commission_rate
-- Retorna a taxa vigente em uma data específica para um par (user, campaign).
-- Retorna NULL se não houver vigência ativa nessa data.
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.v6_get_active_commission_rate(
    p_user_id     uuid,
    p_campaign_id varchar,
    p_date        date
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT cc.percentage
      FROM public.campaign_commissions cc
     WHERE cc.user_id     = p_user_id
       AND cc.campaign_id = p_campaign_id
       AND cc.valid_from <= p_date
       AND (cc.valid_to IS NULL OR cc.valid_to >= p_date)
     ORDER BY cc.valid_from DESC
     LIMIT 1;
$$;

COMMENT ON FUNCTION public.v6_get_active_commission_rate(uuid, varchar, date) IS
    'v6 RBAC — taxa de comissão vigente em uma data específica. Read-only.';

-- ----------------------------------------------------------------------
-- v6_calculate_member_commission
-- Equivalente do calculate_operator_commission legado, mas como função
-- pura (sem dependência implícita de user_campaigns).
-- Retorna a comissão calculada para os parâmetros dados.
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.v6_calculate_member_commission(
    p_revenue_revshare    numeric,
    p_spend               numeric,
    p_commission_pct      numeric,
    p_date                date
)
RETURNS numeric
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_tax_rate   numeric;
    v_tax_amount numeric;
    v_net_profit numeric;
BEGIN
    -- Sem comissão configurada → 0.
    IF p_commission_pct IS NULL OR p_commission_pct <= 0 THEN
        RETURN 0;
    END IF;

    -- Reusa a função existente de imposto vigente.
    v_tax_rate   := public.get_tax_rate_for_date(p_date);
    v_tax_amount := COALESCE(p_revenue_revshare, 0) * v_tax_rate;
    v_net_profit := COALESCE(p_revenue_revshare, 0)
                    - COALESCE(p_spend, 0)
                    - v_tax_amount;

    IF v_net_profit <= 0 THEN
        RETURN 0;
    END IF;

    RETURN v_net_profit * (p_commission_pct / 100.0);
END;
$$;

COMMENT ON FUNCTION public.v6_calculate_member_commission(numeric, numeric, numeric, date) IS
    'v6 RBAC — fórmula pura de comissão. Mesma matemática do calculate_operator_commission legado, sem acoplamento com user_campaigns.';

-- ----------------------------------------------------------------------
-- v6_populate_member_payouts_for_date
-- Calcula e UPSERT em daily_campaign_member_payouts para uma data específica.
-- Para cada (campaign_id, date) em daily_campaign_metrics, busca todos os
-- (user_id) com vigência ativa em campaign_commissions e produz uma
-- linha em payouts.
--
-- Retorna o número de linhas afetadas (inserted + updated).
-- Operação 100% manual. NÃO é trigger. Roda apenas quando chamada.
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.v6_populate_member_payouts_for_date(p_date date)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_count integer;
BEGIN
    WITH src AS (
        SELECT
            dcm."date"                       AS d,
            dcm.campaign_id,
            cc.user_id,
            cc.percentage                    AS pct,
            COALESCE(dcm.revenue_converted_revshare, 0) AS rev,
            COALESCE(dcm.spend, 0)                       AS spd
        FROM public.daily_campaign_metrics dcm
        JOIN public.campaign_commissions cc
          ON cc.campaign_id = dcm.campaign_id
         AND cc.valid_from <= dcm."date"
         AND (cc.valid_to IS NULL OR cc.valid_to >= dcm."date")
        WHERE dcm."date" = p_date
    ),
    calc AS (
        SELECT
            s.*,
            public.get_tax_rate_for_date(s.d) AS tax_rate
        FROM src s
    ),
    final AS (
        SELECT
            c.d,
            c.campaign_id,
            c.user_id,
            c.pct,
            c.rev,
            c.spd,
            c.tax_rate,
            (c.rev * c.tax_rate)                                AS tax_amount,
            (c.rev - c.spd - (c.rev * c.tax_rate))              AS net_profit,
            public.v6_calculate_member_commission(c.rev, c.spd, c.pct, c.d) AS amount
        FROM calc c
    )
    INSERT INTO public.daily_campaign_member_payouts AS p (
        "date", campaign_id, user_id,
        commission_percentage, revenue_revshare, spend,
        tax_rate, tax_amount, net_profit, amount,
        calculated_at, source
    )
    SELECT
        f.d, f.campaign_id, f.user_id,
        f.pct, f.rev, f.spd,
        f.tax_rate, f.tax_amount, f.net_profit, f.amount,
        now(), 'v6_populate_member_payouts_for_date'
    FROM final f
    ON CONFLICT ("date", campaign_id, user_id)
    DO UPDATE SET
        commission_percentage = EXCLUDED.commission_percentage,
        revenue_revshare      = EXCLUDED.revenue_revshare,
        spend                 = EXCLUDED.spend,
        tax_rate              = EXCLUDED.tax_rate,
        tax_amount            = EXCLUDED.tax_amount,
        net_profit            = EXCLUDED.net_profit,
        amount                = EXCLUDED.amount,
        calculated_at         = now(),
        source                = EXCLUDED.source;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION public.v6_populate_member_payouts_for_date(date) IS
    'v6 RBAC — popula daily_campaign_member_payouts para uma data específica. Manual, sem trigger. Idempotente via UPSERT.';

-- ----------------------------------------------------------------------
-- v6_populate_member_payouts_for_range
-- Conveniência: roda v6_populate_member_payouts_for_date para cada dia
-- num intervalo. Retorna o total de linhas afetadas.
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.v6_populate_member_payouts_for_range(
    p_from date,
    p_to   date
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_d     date;
    v_total integer := 0;
BEGIN
    IF p_to < p_from THEN
        RAISE EXCEPTION 'p_to (%) deve ser >= p_from (%)', p_to, p_from;
    END IF;

    v_d := p_from;
    WHILE v_d <= p_to LOOP
        v_total := v_total + public.v6_populate_member_payouts_for_date(v_d);
        v_d := v_d + 1;
    END LOOP;

    RETURN v_total;
END;
$$;

COMMENT ON FUNCTION public.v6_populate_member_payouts_for_range(date, date) IS
    'v6 RBAC — wrapper que aplica v6_populate_member_payouts_for_date dia a dia num intervalo.';
