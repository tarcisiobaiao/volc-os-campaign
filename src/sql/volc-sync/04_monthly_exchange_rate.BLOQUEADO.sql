-- #####################################################################################
-- ##                                                                                 ##
-- ##   NAO APLIQUE ESTE ARQUIVO AINDA.  BLOQUEADO POR REVISAO ADVERSARIAL.            ##
-- ##                                                                                 ##
-- #####################################################################################
--
-- Data do bloqueio: 2026-08-05
--
-- Este DDL foi reconstruido a partir do Supabase do webgo e revisado carregando 261
-- linhas reais do banco do VOLC num PostgreSQL 16 local. A revisao encontrou DOIS
-- defeitos DESTRUTIVOS e um conflito de modelo. Os tres exigem decisao humana antes
-- de qualquer aplicacao.
--
-- ------------------------------------------------------------------------------------
-- DEFEITO 1 (DESTRUTIVO) — achatamento de taxa por data em taxa unica do mes
-- ------------------------------------------------------------------------------------
-- recalculate_month_revenue() aplica UMA taxa a todas as linhas do mes e sobrescreve
-- revenue_converted / revenue_converted_revshare. O banco do VOLC guarda conversoes
-- feitas com taxa POR DATA. Evidencia real medida:
--     daily_project_metrics id=3  (2026-02-12): revenue=19.38  revenue_converted=100.776
--                                                -> taxa embutida 5.2
-- Rodar a funcao com a taxa do mes reescreve esse valor e a taxa historica se perde,
-- sem backup e sem como reconstruir.
--
-- ------------------------------------------------------------------------------------
-- DEFEITO 2 (DESTRUTIVO) — mes passado sem taxa fixada usa a taxa de HOJE
-- ------------------------------------------------------------------------------------
-- get_monthly_exchange_rate() cai numa cascata de 3 degraus e o ultimo devolve a taxa
-- corrente. Medido: get_monthly_exchange_rate('2025-06-15') e ('2019-01-01') devolvem
-- ambos 5.25, que e o dollar_exchange_rate de hoje, porque exchange_rate_history so
-- tem linhas a partir de 2026-02-13. Pior: o valor errado e entao GRAVADO em
-- monthly_exchange_rates como se fosse verdade historica.
--
-- ------------------------------------------------------------------------------------
-- DEFEITO 3 (QUEBRA) — dois modelos de conversao concorrentes
-- ------------------------------------------------------------------------------------
-- src/components/currency/ExchangeRateManager.tsx:74 chama rpc_set_dollar_exchange_rate
-- (modelo mensal, deste arquivo) e logo em seguida chama updateDatabaseConversions(),
-- que executa update_all_revenue_conversions (modelo legado, JA EXISTENTE no VOLC).
-- Os dois recalculam a mesma coisa por criterios diferentes: o ultimo a rodar vence.
-- Precisa escolher UM modelo antes de expor isso na UI.
--
-- ------------------------------------------------------------------------------------
-- O QUE PRECISA SER DECIDIDO
-- ------------------------------------------------------------------------------------
--   (a) Taxa por data ou taxa por mes? Se por data, trocar a taxa unica dos UPDATEs por
--       public.get_exchange_rate_for_date(m.date), preservando a semantica atual.
--   (b) Mes sem taxa: abortar com RAISE EXCEPTION, ou exigir p_rate explicito?
--       Adivinhar com a taxa de hoje nao pode continuar sendo o comportamento.
--   (c) Modelo mensal ou update_all_revenue_conversions? Manter os dois garante
--       divergencia entre o que o dashboard mostra e o que esta gravado.
--
-- ------------------------------------------------------------------------------------
-- JA CORRIGIDO NESTE ARQUIVO (mas insuficiente para desbloquear)
-- ------------------------------------------------------------------------------------
--   - GRANT EXECUTE para 'anon' removido das funcoes SECURITY DEFINER. A anon key do
--     VOLC vai embutida no bundle do browser; com o grant, qualquer visitante poderia
--     disparar UPDATE em massa na base financeira.
--
-- ------------------------------------------------------------------------------------
-- ANTES DE DESBLOQUEAR, SEM EXCECAO
-- ------------------------------------------------------------------------------------
--   pg_dump das 4 tabelas afetadas: daily_campaign_metrics, daily_project_metrics,
--   gam_metrics, adsense_metrics. Sao elas que as funcoes sobrescrevem.
--
-- #####################################################################################

-- =====================================================================================
-- BLOCO: CÂMBIO MENSAL  (reconstrução de DDL — webgo -> VOLC OS Campaign)
-- =====================================================================================
-- Objetos criados por este arquivo:
--   TABELA    public.monthly_exchange_rates
--   FUNÇÃO    public.get_monthly_exchange_rate(target_date date) -> numeric
--   FUNÇÃO    public.recalculate_month_revenue(target_month text, override_rate numeric) -> jsonb
--   FUNÇÃO    public.rpc_recalculate_month(p_year_month text, p_rate numeric) -> jsonb
--   FUNÇÃO    public.rpc_set_dollar_exchange_rate(p_rate numeric) -> jsonb
--
-- DEPENDÊNCIAS (precisam já existir no VOLC — todas VERIFICADAS via OpenAPI em 2026-08-05):
--   public.system_settings          (key, value, updated_at)                 OK
--   public.exchange_rate_history    (rate, effective_date, id)               OK
--   public.projects                 (id, revshare)                           OK
--   public.campaigns                (campaign_id, project_id)                OK
--   public.daily_campaign_metrics   (date, revenue, revenue_converted,
--                                    revenue_converted_revshare, campaign_id,
--                                    updated_at)                             OK
--   public.daily_project_metrics    (date, revenue, revenue_converted,
--                                    revenue_converted_revshare, project_id,
--                                    updated_at)                             OK
--   public.gam_metrics              (date, revenue, revenue_converted, updated_at)  OK
--   public.adsense_metrics          (date, revenue, revenue_converted, updated_at)  OK
--
-- ORIGEM DE CADA DECISÃO
--   [OBSERVADO] = veio do spec OpenAPI do webgo, de linhas reais lidas por GET,
--                 ou do comportamento medido chamando as funções de leitura.
--   [INFERIDO]  = deduzido do código consumidor ou de bom senso. NÃO é cópia do original.
--
--   O CORPO DAS 4 FUNÇÕES É RECONSTRUÇÃO. Não existe forma de ler o corpo original
--   (sem acesso a pg_catalog / pg_get_functiondef). As assinaturas são OBSERVADAS;
--   a lógica interna é INFERIDA a partir do comportamento medido e do código cliente.
--
-- NADA DESTRUTIVO: sem DROP TABLE, DROP COLUMN, TRUNCATE ou DELETE.
-- O único DROP presente é um DROP FUNCTION guardado por assinatura (explicado adiante).
-- =====================================================================================

BEGIN;

-- -------------------------------------------------------------------------------------
-- 1. TABELA public.monthly_exchange_rates
-- -------------------------------------------------------------------------------------
-- Colunas, tipos, defaults e NOT NULL: [OBSERVADO] no spec OpenAPI do webgo
--   definitions.monthly_exchange_rates:
--     required = [id, year_month, rate]  (no PostgREST = NOT NULL sem default)
--     source          default 'manual'
--     created_at      default now()
--     updated_at      default now()
--     recalculated_at timestamptz, nullable
--
-- Formato do mês: [OBSERVADO] em 20 linhas reais -> year_month é TEXT 'YYYY-MM'
--   ('2026-05', '2026-04', ..., '2025-02'). NÃO é date do dia 1, NÃO é int.
--
-- Escala do rate: [OBSERVADO] valores reais 5.1, 4.963, 4.925, 5.21, 5.2, 5.5.
--   O spec reporta format "numeric" sem modificador. Confirmado que este PostgREST
--   NÃO emite modificadores de tipo em NENHUMA coluna do schema (varredura: zero
--   formatos contendo parênteses), então "numeric" pode ser numeric puro OU
--   numeric(p,s). Como há valores de 3 casas (4.963) armazenados, a escala é >= 3.
--   [INFERIDO] usamos numeric sem modificador — é o superconjunto seguro.
--
-- id: [OBSERVADO] integer, PK, e SEM "default" no spec. Uma coluna serial apareceria
--   com default nextval(...). Ausência de default + PK integer + ids sequenciais (1..37)
--   => coluna IDENTITY. [INFERIDO] BY DEFAULT (permite INSERT com id explícito numa
--   eventual migração de dados; GENERATED ALWAYS proibiria).
CREATE TABLE IF NOT EXISTS public.monthly_exchange_rates (
    id               integer     GENERATED BY DEFAULT AS IDENTITY,
    year_month       text        NOT NULL,                       -- 'YYYY-MM' [OBSERVADO]
    rate             numeric     NOT NULL,                       -- BRL por 1 USD [OBSERVADO]
    source           text        NOT NULL DEFAULT 'manual',      -- valores vistos: 'manual', 'migrated' [OBSERVADO]
    recalculated_at  timestamptz,                                -- null enquanto nunca recalculado [OBSERVADO]
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT monthly_exchange_rates_pkey PRIMARY KEY (id)
);

-- UNIQUE em year_month.
-- [OBSERVADO indiretamente] src/hooks/useMonthlyExchangeRates.ts faz
--   .upsert({...}, { onConflict: 'year_month' })
-- Um upsert com onConflict só funciona se existir constraint/índice único —
-- logo o webgo tem esse único. Além disso não há mês duplicado nas 10 linhas reais.
-- Guarda idempotente: só cria se ainda não existir.
DO $guard$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
          JOIN pg_class t     ON t.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
         WHERE n.nspname = 'public'
           AND t.relname = 'monthly_exchange_rates'
           AND c.conname = 'monthly_exchange_rates_year_month_key'
    ) THEN
        ALTER TABLE public.monthly_exchange_rates
            ADD CONSTRAINT monthly_exchange_rates_year_month_key UNIQUE (year_month);
    END IF;
END
$guard$;

COMMENT ON TABLE  public.monthly_exchange_rates              IS 'Taxa USD->BRL fixada por mês (YYYY-MM). Fonte da verdade para o recálculo mensal das colunas *_converted. Reconstruída a partir do spec OpenAPI do webgo em 2026-08-05.';
COMMENT ON COLUMN public.monthly_exchange_rates.year_month   IS 'Mês no formato texto YYYY-MM (ex.: 2026-05). [OBSERVADO em dados reais]';
COMMENT ON COLUMN public.monthly_exchange_rates.rate         IS 'Reais por 1 dólar. Ex.: 4.963.';
COMMENT ON COLUMN public.monthly_exchange_rates.source       IS 'Origem do valor. Valores vistos no webgo: manual, migrated.';
COMMENT ON COLUMN public.monthly_exchange_rates.recalculated_at IS 'Quando rpc_recalculate_month rodou por último para este mês. NULL = nunca recalculado.';

-- Grants: [INFERIDO] o frontend lê e faz upsert nesta tabela com a ANON KEY
-- (src/hooks/useMonthlyExchangeRates.ts usa supabase.from('monthly_exchange_rates')),
-- então anon precisa de SELECT/INSERT/UPDATE, igual às tabelas irmãs.
-- DELIBERADAMENTE NÃO habilitamos RLS: as tabelas irmãs do VOLC (daily_campaign_metrics
-- etc.) são lidas hoje com a anon key sem policy; habilitar RLS aqui quebraria a tela.
-- Os GRANTs são emitidos papel a papel, e só para papéis que EXISTAM neste banco.
-- Motivo: este é um Supabase self-hosted; se algum dos papéis padrão não existisse,
-- um GRANT direto abortaria a transação inteira e nada seria criado.
DO $grants_tbl$
DECLARE
    v_role text;
    v_seq  text;
BEGIN
    v_seq := pg_get_serial_sequence('public.monthly_exchange_rates', 'id');

    FOREACH v_role IN ARRAY ARRAY['authenticated', 'service_role']  -- 'anon' REMOVIDO: a anon key vai no bundle publico LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
            EXECUTE format('GRANT SELECT, INSERT, UPDATE ON public.monthly_exchange_rates TO %I', v_role);
            IF v_seq IS NOT NULL THEN
                EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO %I', v_seq, v_role);
            END IF;
        ELSE
            RAISE NOTICE 'Papel % nao existe neste banco; GRANT ignorado.', v_role;
        END IF;
    END LOOP;
END
$grants_tbl$;


-- -------------------------------------------------------------------------------------
-- 2. GUARDA DE ASSINATURA (único DROP deste arquivo, e ele é condicional)
-- -------------------------------------------------------------------------------------
-- Por que um DROP é inevitável aqui: CREATE OR REPLACE FUNCTION do PostgreSQL NÃO
-- consegue (a) renomear parâmetros, (b) mudar o número de parâmetros, nem (c) mudar o
-- tipo de retorno. Se o banco de destino já tiver uma versão dessas funções com
-- assinatura diferente da que vamos criar, o CREATE OR REPLACE falha com erro.
-- Este bloco derruba SOMENTE funções com esses nomes cuja assinatura completa
-- (argumentos -> retorno) seja diferente da alvo. Se a assinatura já bate, nada é
-- derrubado e o CREATE OR REPLACE abaixo apenas troca o corpo.
-- No VOLC, em 2026-08-05, NENHUMA das 4 funções existe (verificado no /rest/v1/ do VOLC),
-- então na primeira execução este bloco é no-op.
DO $sigguard$
DECLARE
    r          record;
    v_expected text;
BEGIN
    FOR r IN
        SELECT p.oid,
               p.proname,
               p.oid::regprocedure::text AS sig,
               pg_get_function_arguments(p.oid) || ' -> ' || pg_get_function_result(p.oid) AS actual
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.prokind = 'f'          -- só funções normais; nunca agregados/procedures
           AND p.proname IN (
                 'get_monthly_exchange_rate',
                 'recalculate_month_revenue',
                 'rpc_recalculate_month',
                 'rpc_set_dollar_exchange_rate'
               )
    LOOP
        v_expected := CASE r.proname
            WHEN 'get_monthly_exchange_rate'    THEN 'target_date date -> numeric'
            WHEN 'recalculate_month_revenue'    THEN 'target_month text, override_rate numeric DEFAULT NULL::numeric -> jsonb'
            WHEN 'rpc_recalculate_month'        THEN 'p_year_month text, p_rate numeric DEFAULT NULL::numeric -> jsonb'
            WHEN 'rpc_set_dollar_exchange_rate' THEN 'p_rate numeric -> jsonb'
        END;

        IF r.actual IS DISTINCT FROM v_expected THEN
            RAISE NOTICE 'Assinatura divergente em %: "%" (esperado "%"). Derrubando para recriar.',
                         r.sig, r.actual, v_expected;
            EXECUTE format('DROP FUNCTION %s', r.sig);
        END IF;
    END LOOP;
END
$sigguard$;


-- -------------------------------------------------------------------------------------
-- 3. FUNÇÃO public.get_monthly_exchange_rate(target_date date) -> numeric
-- -------------------------------------------------------------------------------------
-- Assinatura: [OBSERVADO] paths./rpc/get_monthly_exchange_rate -> parâmetro
--   único "target_date" format date, required.
--
-- Comportamento reconstruído a partir de 13 chamadas GET reais no webgo
-- (leitura pura, nenhuma escrita). Medições:
--   2026-05-15 -> 5.1000   (existe linha 2026-05 rate 5.1)      -> tabela mensal, ROUND 4
--   2026-03-10 -> 4.9250   (existe linha 2026-03 rate 4.925)    -> tabela mensal, ROUND 4
--   2026-02-28 -> 5.2100   (existe linha 2026-02 rate 5.21)     -> tabela mensal, ROUND 4
--   2026-04-24 -> 4.9630   (existe linha 2026-04 rate 4.963)    -> tabela mensal, ROUND 4
--   2026-06-10 -> 4.9000   (NÃO existe 2026-06; erh 2026-04-23 = 4.9) -> histórico, ROUND 4
--   2026-07-15 -> 4.9000   idem
--   2026-08-05 -> 4.9000   idem
--   2025-08-15 -> 4.9      (NÃO existe 2025-08; erh não tem nada <= essa data) -> system_settings, SEM round
--   2025-01-15 -> 4.9      idem
--   2019-01-01 -> 4.9      idem
-- A troca de "4.9000" (4 casas) por "4.9" (cru) entre os dois últimos degraus é a
-- evidência de que existem exatamente 3 degraus e de que os 2 primeiros aplicam
-- ROUND(x, 4) e o último não. [OBSERVADO — comportamento; INFERIDO — estrutura interna]
--
-- A ordenação do histórico (effective_date DESC, id DESC) foi confirmada com
-- get_exchange_rate_for_date('2025-09-25') = 5.2000: naquele dia existem duas linhas
-- em exchange_rate_history com effective_date 2025-09-24 (5.5 id=4 e 5.2 id=13) e a
-- função devolve a de id maior. [OBSERVADO]
CREATE OR REPLACE FUNCTION public.get_monthly_exchange_rate(target_date date)
RETURNS numeric
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_rate numeric;
BEGIN
    IF target_date IS NULL THEN
        RETURN NULL;
    END IF;

    -- Degrau 1: taxa fixada para o mês (fonte da verdade).
    SELECT m.rate
      INTO v_rate
      FROM public.monthly_exchange_rates m
     WHERE m.year_month = to_char(target_date, 'YYYY-MM')
     LIMIT 1;

    IF v_rate IS NOT NULL THEN
        RETURN ROUND(v_rate, 4);
    END IF;

    -- Degrau 2: última taxa vigente no histórico até a data pedida.
    SELECT h.rate
      INTO v_rate
      FROM public.exchange_rate_history h
     WHERE h.effective_date <= target_date
     ORDER BY h.effective_date DESC, h.id DESC
     LIMIT 1;

    IF v_rate IS NOT NULL THEN
        RETURN ROUND(v_rate, 4);
    END IF;

    -- Degrau 3: taxa corrente do sistema, sem arredondar (bate com o observado).
    SELECT NULLIF(btrim(s.value), '')::numeric
      INTO v_rate
      FROM public.system_settings s
     WHERE s.key = 'dollar_exchange_rate'
     LIMIT 1;

    -- Sem 4º degrau inventado: se nada foi encontrado devolvemos NULL de propósito,
    -- para que quem chama exploda com mensagem clara em vez de converter com uma
    -- constante chutada. (No VOLC a chave dollar_exchange_rate existe = '5.25'.)
    RETURN v_rate;
END;
$fn$;

COMMENT ON FUNCTION public.get_monthly_exchange_rate(date) IS
'Taxa USD->BRL aplicável a uma data. Cascata: monthly_exchange_rates (mês) -> exchange_rate_history (vigência) -> system_settings.dollar_exchange_rate. Corpo RECONSTRUÍDO (2026-08-05) a partir do comportamento medido no webgo; não é cópia do original.';


-- -------------------------------------------------------------------------------------
-- 4. FUNÇÃO public.recalculate_month_revenue(target_month text, override_rate numeric)
-- -------------------------------------------------------------------------------------
-- Assinatura: [OBSERVADO] paths./rpc/recalculate_month_revenue ->
--   target_month  text     required
--   override_rate numeric  opcional (logo tem DEFAULT)
-- Tipo de retorno: [INFERIDO] jsonb. Nenhum código do repositório chama esta função
--   diretamente (git grep não acha), então o formato de retorno original é DESCONHECIDO.
--   Escolhemos o mesmo envelope de rpc_recalculate_month porque este é o worker que
--   aquele wrapper usa.
--
-- É este o motor do recálculo: converte USD -> BRL nas 4 tabelas de métrica.
-- NÃO APAGA NADA: só UPDATE de colunas derivadas (*_converted*) e de updated_at.
--
-- Fórmulas — todas [OBSERVADO] conferindo linha real contra a taxa do mês:
--   revenue_converted = ROUND(revenue * taxa, 2)
--     conferido em 2026-04-24 (taxa mensal 4.963): 283.83*4.963=1408.6479 -> 1408.65 (dpm)
--                                                  11.95*4.963=59.30785  -> 59.31   (adsense)
--     conferido em 2026-05-10 (taxa mensal 5.1):   209.56*5.1  =1068.756 -> 1068.76 (dpm)
--                                                  0.36*5.1    =1.836    -> 1.84    (gam)
--     (ROUND numeric do Postgres arredonda "half away from zero", que é exatamente o
--      que os dados mostram: 19.45*0.9=17.505 -> 17.51)
--
--   revenue_converted_revshare = revenue_converted * (1 - revshare_do_projeto)
--     em daily_project_metrics: COM ROUND(...,2)  [OBSERVADO: 2877.48*0.9=2589.732 -> 2589.73]
--     em daily_campaign_metrics: SEM ROUND        [OBSERVADO: 667.97*0.9 -> 601.173 (3 casas)]
--     A diferença de escala nas linhas cruas do webgo (601.173 com 3 casas em dcm vs
--     2589.73 com 2 casas em dpm) é prova de que dcm não arredonda e dpm arredonda.
--     Quando revshare = 0, o fator vira o inteiro 1 e a escala fica preservada (2.30
--     continua "2.30"), o que também bate com as regras de escala do numeric do Postgres.
--
--   gam_metrics e adsense_metrics não têm coluna de revshare — só revenue_converted.
CREATE OR REPLACE FUNCTION public.recalculate_month_revenue(
    target_month  text,
    override_rate numeric DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_start            date;
    v_end              date;
    v_rate             numeric;
    v_default_revshare numeric;
    n_dcm              bigint := 0;
    n_dpm              bigint := 0;
    n_gam              bigint := 0;
    n_ads              bigint := 0;
BEGIN
    -- Validação do formato do mês. [INFERIDO] — não há CHECK observado no webgo,
    -- validamos aqui para não converter o mês errado por typo.
    IF target_month IS NULL OR target_month !~ '^[0-9]{4}-(0[1-9]|1[0-2])$' THEN
        RAISE EXCEPTION 'target_month invalido: % (esperado YYYY-MM)', target_month
            USING ERRCODE = '22023';
    END IF;

    v_start := to_date(target_month || '-01', 'YYYY-MM-DD');
    v_end   := (v_start + interval '1 month')::date;   -- intervalo semiaberto [v_start, v_end)

    v_rate := COALESCE(override_rate, public.get_monthly_exchange_rate(v_start));

    -- Faixa de sanidade igual à do frontend (>0 e <100), ver
    -- src/components/currency/MonthlyExchangeRates.tsx e FinalExchangeRateManager.tsx.
    IF v_rate IS NULL OR v_rate <= 0 OR v_rate >= 100 THEN
        RAISE EXCEPTION 'Taxa invalida para o mes % : %', target_month, v_rate
            USING ERRCODE = '22023';
    END IF;

    -- Revshare padrão quando o projeto não tem revshare definido (NULL) ou quando a
    -- campanha não casa com nenhum projeto.
    -- ATENÇÃO — DIVERGÊNCIA REAL ENTRE AS DUAS INSTÂNCIAS, LEIA ANTES DE RODAR:
    --   No webgo, daily_project_metrics trata revshare NULL como 0 (projeto 78,
    --   revshare NULL, tem revenue_converted_revshare == revenue_converted),
    --   MAS daily_campaign_metrics trata revshare NULL como 0.1 (campanhas dos
    --   projetos 67 e 78, ambos com revshare NULL, têm fator 0.9). [OBSERVADO]
    --   Não consegui determinar de onde vem esse 0.1 do lado de campanha.
    --   Aqui adotamos 0 como padrão (comportamento conservador, que é também o que os
    --   dados atuais do VOLC mostram: o único projeto tem revshare NULL e as linhas de
    --   daily_campaign_metrics estão com fator 1.0).
    --   Para reproduzir o webgo basta inserir a chave abaixo — sem editar a função:
    --     INSERT INTO public.system_settings (key, value, data_type, category, description)
    --     VALUES ('default_revshare','0.1','number','currency','Revshare padrao quando projects.revshare e NULL');
    SELECT COALESCE(NULLIF(btrim(s.value), '')::numeric, 0)
      INTO v_default_revshare
      FROM public.system_settings s
     WHERE s.key = 'default_revshare'
     LIMIT 1;

    v_default_revshare := COALESCE(v_default_revshare, 0);

    -- ---------------------------------------------------------------------------------
    -- 4.1 daily_campaign_metrics
    -- O vínculo com o projeto é daily_campaign_metrics.campaign_id -> campaigns.campaign_id
    -- -> campaigns.project_id -> projects.revshare. [INFERIDO do modelo de dados]
    -- Usamos subconsulta escalar (e não UPDATE ... FROM) de propósito: com JOIN, as
    -- linhas cujo campaign_id não existe em campaigns ficariam de fora do UPDATE.
    -- No webgo existem MUITAS linhas assim (ex.: '19-30-whatsapp-seg-elecol'), e elas
    -- também precisam ter revenue_converted recalculado.
    -- ---------------------------------------------------------------------------------
    UPDATE public.daily_campaign_metrics m
       SET revenue_converted = ROUND(COALESCE(m.revenue, 0) * v_rate, 2),
           revenue_converted_revshare =
               ROUND(COALESCE(m.revenue, 0) * v_rate, 2)
               * (1 - COALESCE(
                        (SELECT p.revshare
                           FROM public.campaigns c
                           JOIN public.projects  p ON p.id = c.project_id
                          WHERE c.campaign_id = m.campaign_id
                          LIMIT 1),
                        v_default_revshare)),
           updated_at = now()
     WHERE m.date >= v_start
       AND m.date <  v_end;
    GET DIAGNOSTICS n_dcm = ROW_COUNT;

    -- ---------------------------------------------------------------------------------
    -- 4.2 daily_project_metrics  (tem project_id direto; aqui o revshare É arredondado)
    -- revenue_converted e revenue_converted_revshare são NOT NULL nesta tabela no VOLC,
    -- por isso o COALESCE(revenue, 0) — nunca gravamos NULL.
    -- ---------------------------------------------------------------------------------
    UPDATE public.daily_project_metrics m
       SET revenue_converted = ROUND(COALESCE(m.revenue, 0) * v_rate, 2),
           revenue_converted_revshare =
               ROUND(
                   ROUND(COALESCE(m.revenue, 0) * v_rate, 2)
                   * (1 - COALESCE(
                            (SELECT p.revshare
                               FROM public.projects p
                              WHERE p.id = m.project_id
                              LIMIT 1),
                            v_default_revshare)),
                   2),
           updated_at = now()
     WHERE m.date >= v_start
       AND m.date <  v_end;
    GET DIAGNOSTICS n_dpm = ROW_COUNT;

    -- ---------------------------------------------------------------------------------
    -- 4.3 gam_metrics  (sem revshare)
    -- ---------------------------------------------------------------------------------
    UPDATE public.gam_metrics m
       SET revenue_converted = ROUND(COALESCE(m.revenue, 0) * v_rate, 2),
           updated_at = now()
     WHERE m.date >= v_start
       AND m.date <  v_end;
    GET DIAGNOSTICS n_gam = ROW_COUNT;

    -- ---------------------------------------------------------------------------------
    -- 4.4 adsense_metrics  (sem revshare)
    -- As 5 colunas extras do VOLC (clicks, impressions, page_views, ctr, calculated_rpm)
    -- NÃO são derivadas de câmbio e por isso NÃO são tocadas aqui — nem calculated_rpm,
    -- que depende de page_views e não da taxa. Mesma coisa para as 7 colunas extras de
    -- daily_campaign_metrics (top_impression_percentage, absolute_top_impression_percentage,
    -- search_click_share, search_exact_match_impression_share, otimizacao_resumo,
    -- otimizacao_json, otimizacao_realizada_em): nenhuma é derivada de câmbio.
    -- ---------------------------------------------------------------------------------
    UPDATE public.adsense_metrics m
       SET revenue_converted = ROUND(COALESCE(m.revenue, 0) * v_rate, 2),
           updated_at = now()
     WHERE m.date >= v_start
       AND m.date <  v_end;
    GET DIAGNOSTICS n_ads = ROW_COUNT;

    RETURN jsonb_build_object(
        'month', target_month,
        'rate',  v_rate,
        'affected', jsonb_build_object(
            'daily_campaign_metrics', n_dcm,
            'daily_project_metrics',  n_dpm,
            'gam_metrics',            n_gam,
            'adsense_metrics',        n_ads
        ),
        'total_rows', n_dcm + n_dpm + n_gam + n_ads
    );
END;
$fn$;

COMMENT ON FUNCTION public.recalculate_month_revenue(text, numeric) IS
'Worker do recalculo mensal: reconverte USD->BRL nas colunas *_converted de daily_campaign_metrics, daily_project_metrics, gam_metrics e adsense_metrics para o mes YYYY-MM. Somente UPDATE de colunas derivadas. Corpo RECONSTRUIDO (2026-08-05), nao e copia do original.';


-- -------------------------------------------------------------------------------------
-- 5. FUNÇÃO public.rpc_recalculate_month(p_year_month text, p_rate numeric)
-- -------------------------------------------------------------------------------------
-- Assinatura: [OBSERVADO] paths./rpc/rpc_recalculate_month ->
--   p_year_month text required ; p_rate numeric opcional (tem DEFAULT)
--
-- Formato do retorno: [OBSERVADO no código cliente] src/hooks/useMonthlyExchangeRates.ts
--   interface RecalculateResult {
--     month: string; rate: number;
--     affected: { daily_campaign_metrics, daily_project_metrics, gam_metrics, adsense_metrics };
--     total_rows: number;
--   }
--   e src/components/currency/MonthlyExchangeRates.tsx usa result.total_rows no toast.
--   O hook consome `data` diretamente como objeto => a função devolve um ESCALAR json/jsonb
--   (não SETOF, não TABLE). Aqui usamos jsonb.
--
-- Efeitos: [INFERIDO, com apoio nos dados]
--   grava/atualiza a taxa do mês em monthly_exchange_rates e carimba recalculated_at.
--   Apoio: a tela MonthlyExchangeRates.tsx mostra "Último recálculo" lendo
--   selectedRate.recalculated_at logo depois de chamar só esta RPC, e no webgo a linha
--   id=37 (2026-05) tem created_at == updated_at == recalculated_at e source='manual',
--   ou seja nasceu do próprio recálculo.
--
-- Transacional por construção: uma função plpgsql roda dentro da transação do chamador.
-- Se qualquer UPDATE falhar, o upsert da taxa também é desfeito.
CREATE OR REPLACE FUNCTION public.rpc_recalculate_month(
    p_year_month text,
    p_rate       numeric DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_start  date;
    v_rate   numeric;
    v_result jsonb;
BEGIN
    IF p_year_month IS NULL OR p_year_month !~ '^[0-9]{4}-(0[1-9]|1[0-2])$' THEN
        RAISE EXCEPTION 'p_year_month invalido: % (esperado YYYY-MM)', p_year_month
            USING ERRCODE = '22023';
    END IF;

    v_start := to_date(p_year_month || '-01', 'YYYY-MM-DD');

    -- Se o chamador não mandar taxa, reutiliza a que já vale para o mês.
    v_rate := COALESCE(p_rate, public.get_monthly_exchange_rate(v_start));

    IF v_rate IS NULL OR v_rate <= 0 OR v_rate >= 100 THEN
        RAISE EXCEPTION 'Taxa invalida para o mes % : %', p_year_month, v_rate
            USING ERRCODE = '22023';
    END IF;

    -- Fixa a taxa do mês ANTES de recalcular, para que qualquer leitura concorrente
    -- (e o próprio get_monthly_exchange_rate) já enxergue o novo valor.
    -- source='manual' porque é o único valor que o webgo usa para linhas criadas por
    -- interação humana ('migrated' é só carga histórica). [OBSERVADO nos dados]
    INSERT INTO public.monthly_exchange_rates (year_month, rate, source, recalculated_at, created_at, updated_at)
    VALUES (p_year_month, v_rate, 'manual', now(), now(), now())
    ON CONFLICT (year_month) DO UPDATE
        SET rate            = EXCLUDED.rate,
            source          = 'manual',
            recalculated_at = now(),
            updated_at      = now();

    v_result := public.recalculate_month_revenue(p_year_month, v_rate);

    RETURN v_result;
END;
$fn$;

COMMENT ON FUNCTION public.rpc_recalculate_month(text, numeric) IS
'Fixa a taxa do mes em monthly_exchange_rates e recalcula todas as colunas convertidas do mes. Devolve {month, rate, affected:{...}, total_rows}. Consumida por src/hooks/useMonthlyExchangeRates.ts. Corpo RECONSTRUIDO (2026-08-05).';


-- -------------------------------------------------------------------------------------
-- 6. FUNÇÃO public.rpc_set_dollar_exchange_rate(p_rate numeric)
-- -------------------------------------------------------------------------------------
-- Assinatura: [OBSERVADO] paths./rpc/rpc_set_dollar_exchange_rate -> p_rate numeric required.
-- Chamadores: src/components/currency/FinalExchangeRateManager.tsx (via
-- secureApi.setExchangeRate -> PUT /api/settings/exchange-rate, rota nomeada que
-- exige ADMIN; ate 24/08/2026 era secureApi.rpc,
--   params { p_rate }) e src/components/currency/ExchangeRateManager.tsx
--   (supabase.rpc('rpc_set_dollar_exchange_rate', { p_rate: rateValue })).
--   NENHUM dos dois usa o valor de retorno — só checam erro. [OBSERVADO]
--   Logo o tipo de retorno original é DESCONHECIDO; devolvemos jsonb informativo.
--
-- Efeito exigido pelo enunciado e coerente com a UI ("Recalcula o mês inteiro ao alterar"):
--   1) grava a taxa corrente em system_settings.dollar_exchange_rate
--   2) dispara o recálculo do mês corrente
--   Tudo na mesma transação (função plpgsql).
--
-- Espelho da chave usd_brl_rate: [OBSERVADO no webgo] as chaves 'dollar_exchange_rate'
--   e 'usd_brl_rate' têm valor idêntico ('4.9') e updated_at idêntico até o microssegundo
--   (2026-04-23T13:49:12.40094) — ou seja, algo grava as duas juntas. Replicamos, mas
--   SOMENTE com UPDATE: se a chave não existir (é o caso do VOLC hoje), o UPDATE é no-op
--   e nenhuma chave nova é inventada no banco de destino.
--
-- last_currency_update NÃO é tocada aqui de propósito: o FinalExchangeRateManager.tsx
--   já a atualiza logo depois, num segundo request. Gravar aqui duplicaria a escrita.
CREATE OR REPLACE FUNCTION public.rpc_set_dollar_exchange_rate(p_rate numeric)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_month  text;
    v_found  integer;
    v_result jsonb;
BEGIN
    -- Mesma faixa validada no frontend (> 0 e < 100).
    IF p_rate IS NULL OR p_rate <= 0 OR p_rate >= 100 THEN
        RAISE EXCEPTION 'Taxa invalida: % (esperado > 0 e < 100)', p_rate
            USING ERRCODE = '22023';
    END IF;

    -- 1) taxa corrente do sistema
    UPDATE public.system_settings
       SET value      = p_rate::text,
           updated_at = now()
     WHERE key = 'dollar_exchange_rate';
    GET DIAGNOSTICS v_found = ROW_COUNT;

    IF v_found = 0 THEN
        INSERT INTO public.system_settings (key, value, description, data_type, category, is_editable, created_at, updated_at)
        VALUES ('dollar_exchange_rate', p_rate::text,
                'Taxa de cambio dolar para real (USD/BRL)', 'number', 'currency', true, now(), now());
    END IF;

    -- 1b) espelho opcional (no-op se a chave não existir neste banco)
    UPDATE public.system_settings
       SET value      = p_rate::text,
           updated_at = now()
     WHERE key = 'usd_brl_rate';

    -- 2) recálculo do mês corrente
    -- CURRENT_DATE usa o timezone do servidor. Em Supabase self-hosted isso costuma ser
    -- UTC; no último dia do mês, entre 21h e 00h no horário de Brasília, o "mês corrente"
    -- do banco já é o mês seguinte. Documentado como incerteza.
    v_month  := to_char(CURRENT_DATE, 'YYYY-MM');
    v_result := public.rpc_recalculate_month(v_month, p_rate);

    RETURN jsonb_build_object(
        'rate',          p_rate,
        'month',         v_month,
        'recalculation', v_result
    );
END;
$fn$;

COMMENT ON FUNCTION public.rpc_set_dollar_exchange_rate(numeric) IS
'Grava a taxa corrente USD->BRL em system_settings.dollar_exchange_rate e recalcula o mes corrente na mesma transacao. Consumida por FinalExchangeRateManager.tsx e ExchangeRateManager.tsx. Corpo RECONSTRUIDO (2026-08-05).';


-- -------------------------------------------------------------------------------------
-- 7. PERMISSÕES DE EXECUÇÃO
-- -------------------------------------------------------------------------------------
-- O frontend chama rpc_recalculate_month e rpc_set_dollar_exchange_rate direto do browser
-- com a ANON KEY (supabase.rpc em useMonthlyExchangeRates.ts e ExchangeRateManager.tsx),
-- então anon precisa de EXECUTE. Por isso as funções de escrita são SECURITY DEFINER com
-- search_path fixo: elas não dependem de o papel anon ter UPDATE nas tabelas de métrica.
DO $grants_fn$
DECLARE
    v_role text;
    v_fn   text;
BEGIN
    FOREACH v_role IN ARRAY ARRAY['authenticated', 'service_role']  -- 'anon' REMOVIDO: a anon key vai no bundle publico LOOP
        CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role);
        FOREACH v_fn IN ARRAY ARRAY[
            'public.get_monthly_exchange_rate(date)',
            'public.recalculate_month_revenue(text, numeric)',
            'public.rpc_recalculate_month(text, numeric)',
            'public.rpc_set_dollar_exchange_rate(numeric)'
        ] LOOP
            EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO %I', v_fn, v_role);
        END LOOP;
    END LOOP;
END
$grants_fn$;

COMMIT;

-- =====================================================================================
-- PÓS-INSTALAÇÃO RECOMENDADA (fora da transação, rodar à mão e só se necessário)
-- =====================================================================================
-- O recálculo filtra por "date" nas 4 tabelas. Se não houver índice em date, o UPDATE
-- vira seq scan (no webgo daily_campaign_metrics tem ~3,26 milhões de linhas).
-- CREATE INDEX CONCURRENTLY não pode rodar dentro de transação — por isso está aqui fora
-- e comentado: confira antes com \d se o índice já existe.
--
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dcm_date ON public.daily_campaign_metrics (date);
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dpm_date ON public.daily_project_metrics  (date);
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gam_date ON public.gam_metrics            (date);
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ads_date ON public.adsense_metrics        (date);
