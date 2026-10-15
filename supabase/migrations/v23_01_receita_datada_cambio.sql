-- v23_01 — receita com data de referência, as-of e câmbio versionado (W12)
--
-- Autoridade: database.agenciavolc.com.br. PROPOSTA: não aplicada em produção.
-- Prova oficial: tools/freedom-lab/db/suites/v23_w12.sh pelo lab.sh, no Mac.
-- Reverter: supabase/migrations/v23_01_rollback.sql.
--
-- ## O DEFEITO (Roadmap P06-T03 e P06-T04)
--
-- 1. RECEITA SEM AS-OF. `joinads_metrics` e `gam_metrics` são upsert do último
--    valor (`resolution=merge-duplicates`); o D-1 reescreve três dias. Não dá
--    para saber o que o sistema sabia num instante, nem quando um número mudou.
-- 2. CÂMBIO CONGELADO. `exchange_rate_history` tem linhas manuais até
--    18/02/2026 (5,25); `get_exchange_rate_for_date()` cai na taxa de hoje quando
--    falta a do período, e o front usa 5,50/5,35 fixos. Nenhum cálculo registra
--    qual taxa usou.
--
-- ## O QUE ESTA MIGRATION FAZ (reaproveita, não cria sistema paralelo)
--
-- A. `exchange_rate_history` (a tabela que já existe) ganha versão: par, fonte,
--    as_of (instante da cotação na fonte), coletado_em (instante em que o banco
--    soube) e proveniência. As linhas manuais de antes ficam como
--    fonte='legado_manual' e as_of NULL. Toda escrita de câmbio passa a ser
--    só de service_role/postgres/supabase_admin (guarda própria + REVOKE da
--    escrita de anon/authenticated nesta tabela). Linha manual nova vira
--    fonte='manual' com as_of/coletado_em do servidor e o ator na
--    proveniência; taxa <= 0 é recusada. Linha com as_of é imutável. No mesmo
--    dia, fonte coletada (PTAX) > manual > legado.
-- B. `cambio_resolver(data, par, max_defasagem, conhecido_ate)`: a única regra
--    de resolução. Data exata → 'exata'; senão a última anterior → 'anterior',
--    com a defasagem em dias; mais velha que o limite (7 dias por padrão) →
--    'defasada' SEM taxa; nenhuma → 'sem_cotacao' SEM taxa. Nunca constante.
-- C. `receita_observacao`: diário append-only alimentado por gatilho AFTER nas
--    duas tabelas de receita que já existem. Cada mudança de valor vira uma
--    versão com data de referência (o dia a que a receita pertence), coletado_em
--    (quando o banco recebeu), proveniência (papel, JWT, user-agent, cabeçalho
--    x-volc-proveniencia) e o câmbio que a conversão usou. Upsert idêntico não
--    gera versão (valor normalizado: 10 = 10.00). DELETE, troca de chave e
--    TRUNCATE viram versão "removida". Taxa impossível vira 'sem_cotacao':
--    câmbio nunca derruba a ingestão. Os adaptadores (n8n, front) não mudam.
-- D. `receita_as_of(conhecido_ate, fonte)` e `vw_receita_vigente`: o que se
--    sabia num instante e o que se sabe agora, sem as removidas.
--
-- ## O QUE ELA NÃO FAZ (de propósito)
--
-- · Não altera `revenue_converted` nem os gatilhos legados
--   (`calculate_revenue_converted_by_date`, `trigger_new_revenue_conversion_*`).
--   Trocar o número que o dashboard e a v17_04 leem é a decisão (c) do
--   `src/sql/volc-sync/04_monthly_exchange_rate.BLOQUEADO.sql`; aqui o valor
--   legado fica registrado ao lado (`receita_convertida_legado`) para comparar.
-- · Cálculo econômico nunca usa `revenue_converted`: `vw_receita_vigente`
--   (e o motor shadow) usam a receita de origem × `cambio_resolver`. O legado
--   é reescrito em massa: `trigger_exchange_rate_update` (system_settings) →
--   `update_all_revenue_converted()` refaz revenue_converted do histórico
--   inteiro, e em gam_metrics o gatilho que roda por último usa a taxa de HOJE
--   (bug pré-existente, fora do escopo). Por isso o diário só versiona por
--   campo de origem, e `receita_convertida_legado` é só comparação.
-- · Não coleta cotação: quem grava é `backend/app/monetizacao/cambio` (PTAX do
--   Banco Central), fora desta migration.
-- · O único GRANT existente que muda é a escrita de anon/authenticated em
--   `exchange_rate_history` (guardado e devolvido pelo rollback). O upsert de `gam_metrics` pelo
--   browser já falha com 42501 por causa do gatilho que lê
--   `trafego_meta_adset` (pacote authenticated do W4). O gatilho novo é
--   SECURITY DEFINER e não acrescenta exigência de GRANT ao cliente.
-- · ATENÇÃO ao ligar a coleta: `get_exchange_rate_for_date()` (legado, corpo
--   só conhecido por reconstrução) lê `rate`/`effective_date` desta mesma
--   tabela. Quando a PTAX começar a entrar, o `revenue_converted` legado de
--   linha nova ou alterada deixa de usar 5,25 e passa a usar a PTAX do dia, com
--   o desempate do legado (não verificado). É mudança visível no dashboard e
--   pede a decisão do dono antes da primeira coleta.
-- · coletado_em do diário é o início da transação que gravou (now()), não o
--   instante do COMMIT; um as-of exatamente na fronteira de uma transação
--   longa pode ver a versão antes de ela ser visível.
-- · session_replication_role = replica desliga os gatilhos: escrita feita
--   assim (restore, replicação lógica) não vira versão no diário.
-- · record_exchange_rate_change() (gatilho de system_settings) continua
--   INVOKER, como em produção. Por isso UPDATE de dollar_exchange_rate por
--   anon/authenticated passa a falhar (42501, guarda e REVOKE do histórico):
--   nenhum caminho vivo do repositório precisa disso, e como DEFINER a anon
--   transformaria a taxa do dia numa 'exata' qualquer. O servidor
--   (service_role/postgres) continua mudando e a versão sai 'manual'.
-- · Pré-existente, fora do escopo: o front chama rpc_set_dollar_exchange_rate
--   (ExchangeRateManager.tsx:74, secureApi.ts:229), que NÃO existe em produção.
-- · Quem aplica é o DONO das três tabelas (em produção, supabase_admin):
--   DROP TRIGGER do rollback exige dono, e a pré-checagem recusa sem isso.
-- · Até a coleta PTAX começar, receita_brl sai NULL (a última cotação manual,
--   5,25 de fevereiro, fica 'defasada'). É ausência, não zero, e aparece assim
--   em vw_receita_vigente.
-- · Moeda das duas fontes: USD, a mesma premissa que os gatilhos legados já
--   usam (revenue × taxa). Declarada no argumento do gatilho e gravada em cada
--   observação; GAM em outra moeda exige outro gatilho, não FX automático.

BEGIN;
SET LOCAL lock_timeout = '5s';   -- ACCESS EXCLUSIVE em 3 tabelas com o n8n gravando: falha cedo, não enfileira

-- ─────────────────────────────────────────────────────── pré-checagem ──
DO $pre$
DECLARE
  faltando text;
BEGIN
  SELECT string_agg(t, ', ') INTO faltando
    FROM unnest(ARRAY['public.exchange_rate_history', 'public.joinads_metrics', 'public.gam_metrics']) t
   WHERE to_regclass(t) IS NULL;
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'v23_01 recusada: faltam %', faltando;
  END IF;

  SELECT string_agg(format('%s.%s', c.table, c.col), ', ') INTO faltando
    FROM (VALUES ('exchange_rate_history', 'id'), ('exchange_rate_history', 'rate'),
                 ('exchange_rate_history', 'effective_date'),
                 ('joinads_metrics', 'date'), ('joinads_metrics', 'utm_campaign_value'),
                 ('joinads_metrics', 'joinads_domain'), ('joinads_metrics', 'revenue'),
                 ('joinads_metrics', 'revenue_converted'),
                 ('gam_metrics', 'date'), ('gam_metrics', 'utm_campaign_value'),
                 ('gam_metrics', 'gam_accounts_id'), ('gam_metrics', 'revenue'),
                 ('gam_metrics', 'revenue_converted')) AS c("table", col)
   WHERE NOT EXISTS (SELECT 1 FROM information_schema.columns i
                      WHERE i.table_schema = 'public' AND i.table_name = c.table AND i.column_name = c.col);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'v23_01 recusada: faltam colunas %', faltando;
  END IF;

  -- Quem aplica precisa ser DONO das três: o privilégio TRIGGER basta para
  -- criar o gatilho, mas o rollback (DROP TRIGGER) e o ALTER exigem dono.
  -- Em produção o dono é supabase_admin: aplique e reverta por ele.
  SELECT string_agg(t, ', ') INTO faltando
    FROM unnest(ARRAY['public.exchange_rate_history', 'public.joinads_metrics', 'public.gam_metrics']) t
   WHERE NOT pg_has_role(current_user, (SELECT relowner FROM pg_class WHERE oid = t::regclass), 'USAGE');
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'v23_01 recusada: % não é dono de % (aplique pelo dono, em produção supabase_admin)',
      current_user, faltando;
  END IF;

  -- O rollback derruba estas colunas; se alguma já existisse, ele apagaria
  -- coluna que não é desta migration.
  SELECT string_agg(column_name, ', ') INTO faltando
    FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'exchange_rate_history'
     AND column_name IN ('par', 'fonte', 'as_of', 'coletado_em', 'proveniencia');
  IF faltando IS NOT NULL OR to_regclass('public.receita_observacao') IS NOT NULL
     OR to_regclass('public.v23_01_acl_anterior') IS NOT NULL THEN
    RAISE EXCEPTION 'v23_01 recusada: % já existe — esta migration não reaplica por cima',
      coalesce('exchange_rate_history.' || faltando, 'receita_observacao/v23_01_acl_anterior');
  END IF;
END
$pre$;

-- ──────────────────────────────────────────── A. câmbio versionado ──
ALTER TABLE public.exchange_rate_history
  ADD COLUMN par          text  NOT NULL DEFAULT 'USD/BRL',
  ADD COLUMN fonte        text  NOT NULL DEFAULT 'legado_manual',
  ADD COLUMN as_of        timestamptz,
  ADD COLUMN coletado_em  timestamptz,      -- linhas antigas: desconhecido (NULL), não "agora"
  ADD COLUMN proveniencia jsonb;
ALTER TABLE public.exchange_rate_history ALTER COLUMN coletado_em SET DEFAULT now();

ALTER TABLE public.exchange_rate_history
  ADD CONSTRAINT exchange_rate_history_par_ck   CHECK (par ~ '^[A-Z]{3}/[A-Z]{3}$'),
  ADD CONSTRAINT exchange_rate_history_fonte_ck CHECK (fonte ~ '^[a-z0-9_.:-]{3,64}$'),
  -- legado (linha de antes da v23_01) ⇔ sem as_of. Toda linha nova tem as_of.
  ADD CONSTRAINT exchange_rate_history_versao_ck CHECK ((fonte = 'legado_manual') = (as_of IS NULL)),
  -- NOT VALID: vale para toda escrita nova; o legado não é reprovado (e o
  -- resolvedor ignora taxa <= 0 que já exista).
  ADD CONSTRAINT exchange_rate_history_taxa_ck  CHECK (rate > 0) NOT VALID;

-- Idempotência da coleta (on_conflict do PostgREST). NULLs são distintos:
-- as linhas manuais repetidas no mesmo dia continuam como estão.
CREATE UNIQUE INDEX exchange_rate_history_versao_uk
  ON public.exchange_rate_history (par, effective_date, fonte, as_of);

-- Só a coleta e o operador do servidor escrevem câmbio, mesmo enquanto o
-- default ACL do incidente (W4) estiver aberto: esta tabela passa a ser fonte
-- da receita em BRL e a guarda não pode depender do W4 ter fechado antes.
-- SECURITY INVOKER: current_user é o papel de quem grava (a RPC legada
-- rpc_set_dollar_exchange_rate é SECURITY DEFINER e passa como dona).
CREATE FUNCTION public.cambio_versao_guarda() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $f$
DECLARE
  v_claims jsonb;
BEGIN
  IF current_user NOT IN ('service_role', 'postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'câmbio só é gravado pela coleta ou pelo servidor (papel %)', current_user
      USING ERRCODE = '42501';
  END IF;
  IF TG_OP = 'INSERT' THEN
    BEGIN
      v_claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
    EXCEPTION WHEN others THEN v_claims := NULL;
    END;
    IF NEW.fonte IN ('legado_manual', 'manual') THEN
      -- Linha manual nova: o servidor diz quando e quem. Nada do cliente vale
      -- para o tempo (um "conhecido em 2021" inventado hoje vira hoje).
      NEW.fonte := 'manual';
      -- clock_timestamp: duas linhas manuais na mesma transação não colidem
      -- no índice de versão.
      NEW.as_of := clock_timestamp();
    ELSIF NEW.as_of IS NULL THEN
      RAISE EXCEPTION 'cotação de fonte % sem as_of da fonte', NEW.fonte USING ERRCODE = '23514';
    ELSIF NEW.as_of > now() + interval '5 minutes' THEN
      RAISE EXCEPTION 'cotação com as_of no futuro (%)', NEW.as_of USING ERRCODE = '22023';
    END IF;
    NEW.coletado_em := now();   -- o banco é quem diz quando soube
    NEW.proveniencia := coalesce(NEW.proveniencia, '{}'::jsonb) || jsonb_strip_nulls(jsonb_build_object(
      'ator',      current_user,
      'sessao',    session_user,
      'papel',     nullif(current_setting('role', true), 'none'),
      'jwt_sub',   v_claims ->> 'sub',
      'jwt_papel', v_claims ->> 'role',
      -- o que auth.uid() lê: quem estava logado
      'auth_uid',  coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''), v_claims ->> 'sub')));
    RETURN NEW;
  END IF;
  IF OLD.as_of IS NOT NULL OR (TG_OP = 'UPDATE' AND NEW.as_of IS NOT NULL) THEN
    RAISE EXCEPTION 'cotação versionada é imutável (id %): grave uma nova versão', OLD.id
      USING ERRCODE = '23001';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END
$f$;

CREATE TRIGGER cambio_versao_guarda
  BEFORE INSERT OR UPDATE OR DELETE ON public.exchange_rate_history
  FOR EACH ROW EXECUTE FUNCTION public.cambio_versao_guarda();

CREATE FUNCTION public.cambio_resolver(
  p_data date,
  p_par text DEFAULT 'USD/BRL',
  p_max_defasagem_dias integer DEFAULT 7,
  p_conhecido_ate timestamptz DEFAULT NULL
) RETURNS TABLE (cotacao_id bigint, par text, taxa numeric, data_cotacao date, as_of timestamptz,
                 fonte text, modo text, defasagem_dias integer)
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public AS $f$
DECLARE
  r record;
BEGIN
  IF p_data IS NULL OR p_par IS NULL OR p_max_defasagem_dias IS NULL OR p_max_defasagem_dias < 0 THEN
    RAISE EXCEPTION 'cambio_resolver: data, par e defasagem máxima (>= 0) são obrigatórios'
      USING ERRCODE = '22023';
  END IF;

  SELECT h.id::bigint AS id, h.par, h.rate::numeric AS rate, h.effective_date::date AS d,
         h.as_of, h.fonte
    INTO r
    FROM public.exchange_rate_history h
   WHERE h.par = p_par
     AND h.effective_date::date <= p_data
     AND h.rate > 0                      -- taxa impossível do legado não é cotação
     -- Replay: só o que o banco já sabia. Linha legada não sabe quando entrou.
     AND (p_conhecido_ate IS NULL OR h.coletado_em <= p_conhecido_ate)
   ORDER BY h.effective_date::date DESC,
            -- no mesmo dia: fonte coletada (PTAX) > manual nova > legado
            CASE h.fonte WHEN 'legado_manual' THEN 2 WHEN 'manual' THEN 1 ELSE 0 END,
            h.as_of DESC NULLS LAST,    -- e a última publicação da fonte vence
            h.id DESC
   LIMIT 1;

  IF NOT FOUND THEN
    RETURN QUERY SELECT NULL::bigint, p_par, NULL::numeric, NULL::date, NULL::timestamptz,
                        NULL::text, 'sem_cotacao'::text, NULL::integer;
    RETURN;
  END IF;

  RETURN QUERY SELECT r.id, r.par,
    CASE WHEN p_data - r.d > p_max_defasagem_dias THEN NULL ELSE r.rate END,
    r.d, r.as_of, r.fonte,
    CASE WHEN r.d = p_data THEN 'exata'
         WHEN p_data - r.d > p_max_defasagem_dias THEN 'defasada'
         ELSE 'anterior' END,
    p_data - r.d;
END
$f$;

COMMENT ON FUNCTION public.cambio_resolver(date, text, integer, timestamptz) IS
'Única regra de câmbio do W12 (v23_01). exata | anterior (com defasagem_dias) | defasada (taxa NULL) | sem_cotacao (taxa NULL). Nunca devolve constante.';

-- ───────────────────────────────────────── C. diário de receita as-of ──
CREATE TABLE public.receita_observacao (
  id                         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  fonte                      text        NOT NULL CHECK (fonte IN ('joinads', 'gam')),
  tabela_origem              text        NOT NULL,
  chave                      jsonb       NOT NULL,     -- a chave de upsert da tabela de origem
  data_referencia            date,                     -- o dia a que a receita pertence
  operacao                   text        NOT NULL CHECK (operacao IN ('CARGA', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')),
  removida                   boolean     NOT NULL,
  moeda                      text        NOT NULL CHECK (moeda ~ '^[A-Z]{3}$'),
  receita                    numeric,                  -- NULL = ausente, nunca zero inventado
  receita_convertida_legado  numeric,                  -- revenue_converted legado no instante da versão; só comparação, nunca cálculo
  cambio_modo                text        NOT NULL CHECK (cambio_modo IN
                               ('exata', 'anterior', 'defasada', 'sem_cotacao', 'moeda_local', 'sem_receita')),
  cambio_cotacao_id          bigint,
  cambio_par                 text,
  cambio_taxa                numeric,
  cambio_data                date,
  cambio_fonte               text,
  cambio_as_of               timestamptz,
  cambio_defasagem_dias      integer,
  receita_brl                numeric,
  coletado_em                timestamptz NOT NULL DEFAULT now(),   -- quando o banco recebeu
  proveniencia               jsonb       NOT NULL,
  impressao_digital          text        NOT NULL,
  CONSTRAINT receita_observacao_brl_ck
    CHECK (receita_brl IS NULL OR cambio_modo IN ('exata', 'anterior', 'moeda_local')),
  CONSTRAINT receita_observacao_taxa_ck
    CHECK (cambio_modo NOT IN ('exata', 'anterior') OR (cambio_taxa > 0 AND cambio_cotacao_id IS NOT NULL)),
  CONSTRAINT receita_observacao_removida_ck
    CHECK (NOT removida OR (receita IS NULL AND receita_brl IS NULL))
);

CREATE INDEX receita_observacao_chave_ix ON public.receita_observacao (tabela_origem, chave, id DESC);
CREATE INDEX receita_observacao_referencia_ix ON public.receita_observacao (fonte, data_referencia);
CREATE INDEX receita_observacao_coletado_ix ON public.receita_observacao (coletado_em);

ALTER TABLE public.receita_observacao ENABLE ROW LEVEL SECURITY;   -- sem policy: cliente não vê

COMMENT ON TABLE public.receita_observacao IS
'Diário append-only de receita (W12, v23_01): uma versão por mudança de valor em joinads_metrics/gam_metrics, com data de referência, coletado_em, proveniência e o câmbio usado.';

CREATE FUNCTION public.receita_observacao_imutavel() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $f$
BEGIN
  RAISE EXCEPTION 'receita_observacao é append-only (%)', TG_OP USING ERRCODE = '23001';
END
$f$;

CREATE TRIGGER receita_observacao_imutavel
  BEFORE UPDATE OR DELETE ON public.receita_observacao
  FOR EACH ROW EXECUTE FUNCTION public.receita_observacao_imutavel();
CREATE TRIGGER receita_observacao_sem_truncate
  BEFORE TRUNCATE ON public.receita_observacao
  FOR EACH STATEMENT EXECUTE FUNCTION public.receita_observacao_imutavel();

-- Grava uma versão se o fato mudou. Devolve true quando gravou.
-- Nunca levanta por falta de câmbio: a ingestão de receita não pode cair por isso.
CREATE FUNCTION public.receita_observar(
  p_fonte text, p_moeda text, p_tabela text, p_linha jsonb, p_chaves text[],
  p_operacao text, p_removida boolean, p_proveniencia jsonb
) RETURNS boolean
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $f$
DECLARE
  v_chave   jsonb := '{}'::jsonb;
  v_data    date;
  v_receita numeric;
  v_legado  numeric;
  v_dig     text;
  k         text;
  v_modo    text;
  v_cot     bigint;
  v_par     text;
  v_taxa    numeric;
  v_cdata   date;
  v_cas_of  timestamptz;
  v_cfonte  text;
  v_defas   integer;
BEGIN
  FOREACH k IN ARRAY p_chaves LOOP
    v_chave := v_chave || jsonb_build_object(k, p_linha -> k);
  END LOOP;
  v_data    := (p_linha ->> 'date')::date;
  v_receita := CASE WHEN p_removida THEN NULL ELSE (p_linha ->> 'revenue')::numeric END;
  v_legado  := CASE WHEN p_removida THEN NULL ELSE (p_linha ->> 'revenue_converted')::numeric END;
  -- Só campo de ORIGEM versiona: removida, data, chave, receita na moeda
  -- original e moeda. revenue_converted (derivado) fica fora: o legado
  -- update_all_revenue_converted() reescreve o histórico inteiro de gam_metrics
  -- a cada mudança do dólar, e isso não é fato novo de receita.
  -- trim_scale: 10 e 10.00 são o mesmo valor e não podem virar duas versões.
  v_dig     := md5(jsonb_build_array(p_removida, v_data, v_chave, trim_scale(v_receita), p_moeda)::text);

  -- Dois upserts concorrentes na mesma chave: um espera o outro, e o segundo
  -- já vê a versão do primeiro (sem versão duplicada).
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tabela || v_chave::text, 23));

  IF v_dig IS NOT DISTINCT FROM (SELECT o.impressao_digital FROM public.receita_observacao o
                                  WHERE o.tabela_origem = p_tabela AND o.chave = v_chave
                                  ORDER BY o.id DESC LIMIT 1) THEN
    RETURN false;   -- upsert idêntico (o D-1 reescreve 3 dias) não é versão nova
  END IF;

  IF p_removida OR v_receita IS NULL THEN
    v_modo := 'sem_receita';
  ELSIF p_moeda = 'BRL' THEN
    v_modo := 'moeda_local';
  ELSIF v_data IS NULL THEN
    v_modo := 'sem_cotacao';
  ELSE
    SELECT r.modo, r.cotacao_id, r.par, r.taxa, r.data_cotacao, r.as_of, r.fonte, r.defasagem_dias
      INTO v_modo, v_cot, v_par, v_taxa, v_cdata, v_cas_of, v_cfonte, v_defas
      FROM public.cambio_resolver(v_data, p_moeda || '/BRL') r;
    -- Defesa em profundidade: taxa impossível nunca derruba a ingestão.
    IF v_modo IN ('exata', 'anterior') AND (v_taxa IS NULL OR v_taxa <= 0 OR v_cot IS NULL) THEN
      v_modo := 'sem_cotacao';
      v_taxa := NULL;
    END IF;
  END IF;

  INSERT INTO public.receita_observacao (
    fonte, tabela_origem, chave, data_referencia, operacao, removida, moeda,
    receita, receita_convertida_legado,
    cambio_modo, cambio_cotacao_id, cambio_par, cambio_taxa, cambio_data, cambio_fonte,
    cambio_as_of, cambio_defasagem_dias, receita_brl, proveniencia, impressao_digital)
  VALUES (
    p_fonte, p_tabela, v_chave, v_data, p_operacao, p_removida, p_moeda,
    v_receita, v_legado,
    v_modo, v_cot, v_par, v_taxa, v_cdata, v_cfonte,
    v_cas_of, v_defas,
    CASE WHEN v_modo = 'moeda_local' THEN v_receita
         WHEN v_modo IN ('exata', 'anterior') THEN v_receita * v_taxa END,
    coalesce(p_proveniencia, '{}'::jsonb), v_dig);
  RETURN true;
END
$f$;

-- Gatilho das tabelas de receita. Argumentos: fonte, moeda, colunas da chave.
-- SECURITY DEFINER: grava no diário sem exigir GRANT do cliente; o cliente só
-- controla NEW, que já controlava na tabela de origem.
CREATE FUNCTION public.receita_registrar_observacao() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $f$
DECLARE
  v_chaves  text[] := TG_ARGV[2:TG_NARGS - 1];
  v_headers jsonb;
  v_claims  jsonb;
  v_prov    jsonb;
  v_old     jsonb;
  v_new     jsonb;
BEGIN
  BEGIN
    v_headers := nullif(current_setting('request.headers', true), '')::jsonb;
  EXCEPTION WHEN others THEN v_headers := NULL;
  END;
  BEGIN
    v_claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
  EXCEPTION WHEN others THEN v_claims := NULL;
  END;
  v_prov := jsonb_strip_nulls(jsonb_build_object(
    'papel',                 nullif(current_setting('role', true), 'none'),
    'sessao',                session_user,
    'jwt_papel',             v_claims ->> 'role',
    'aplicacao',             nullif(current_setting('application_name', true), ''),
    'user_agent',            left(v_headers ->> 'user-agent', 200),
    'declarada',             left(v_headers ->> 'x-volc-proveniencia', 200),
    'coletado_em_declarado', left(v_headers ->> 'x-volc-coletado-em', 64),
    'moeda_por',             'argumento do gatilho (premissa legada: revenue em ' || TG_ARGV[1] || ')',
    'gatilho',               TG_NAME));

  IF TG_OP IN ('UPDATE', 'DELETE') THEN v_old := to_jsonb(OLD); END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN v_new := to_jsonb(NEW); END IF;

  -- UPDATE que troca a chave: a chave antiga deixa de existir.
  IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND EXISTS (
       SELECT 1 FROM unnest(v_chaves) k WHERE v_old -> k IS DISTINCT FROM v_new -> k)) THEN
    PERFORM public.receita_observar(TG_ARGV[0], TG_ARGV[1], TG_TABLE_NAME, v_old, v_chaves,
                                    TG_OP, true, v_prov);
  END IF;
  IF TG_OP <> 'DELETE' THEN
    PERFORM public.receita_observar(TG_ARGV[0], TG_ARGV[1], TG_TABLE_NAME, v_new, v_chaves,
                                    TG_OP, false, v_prov);
  END IF;
  RETURN NULL;
END
$f$;

-- Nome com prefixo zz_: AFTER roda por ordem alfabética; este vê NEW já
-- final e não interfere nos gatilhos legados.
CREATE TRIGGER zz_receita_observacao
  AFTER INSERT OR UPDATE OR DELETE ON public.joinads_metrics
  FOR EACH ROW EXECUTE FUNCTION public.receita_registrar_observacao(
    'joinads', 'USD', 'date', 'utm_campaign_value', 'joinads_domain');

CREATE TRIGGER zz_receita_observacao
  AFTER INSERT OR UPDATE OR DELETE ON public.gam_metrics
  FOR EACH ROW EXECUTE FUNCTION public.receita_registrar_observacao(
    'gam', 'USD', 'date', 'utm_campaign_value', 'gam_accounts_id');

-- TRUNCATE não passa por gatilho de linha: um gatilho de comando registra a
-- remoção de cada chave vigente da tabela, para o diário não divergir da origem.
CREATE FUNCTION public.receita_registrar_truncate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $f$
DECLARE
  v_prov jsonb;
BEGIN
  v_prov := jsonb_strip_nulls(jsonb_build_object(
    'papel',     nullif(current_setting('role', true), 'none'),
    'sessao',    session_user,
    'aplicacao', nullif(current_setting('application_name', true), ''),
    'gatilho',   TG_NAME));
  INSERT INTO public.receita_observacao (
    fonte, tabela_origem, chave, data_referencia, operacao, removida, moeda,
    cambio_modo, proveniencia, impressao_digital)
  SELECT v.fonte, v.tabela_origem, v.chave, v.data_referencia, 'TRUNCATE', true, v.moeda,
         'sem_receita', v_prov,
         md5(jsonb_build_array(true, v.data_referencia, v.chave, NULL::numeric, NULL::numeric, v.moeda)::text)
    FROM (SELECT DISTINCT ON (o.chave) o.*
            FROM public.receita_observacao o
           WHERE o.tabela_origem = TG_TABLE_NAME
           ORDER BY o.chave, o.id DESC) v
   WHERE NOT v.removida;
  RETURN NULL;
END
$f$;

CREATE TRIGGER zz_receita_observacao_truncate
  AFTER TRUNCATE ON public.joinads_metrics
  FOR EACH STATEMENT EXECUTE FUNCTION public.receita_registrar_truncate();
CREATE TRIGGER zz_receita_observacao_truncate
  AFTER TRUNCATE ON public.gam_metrics
  FOR EACH STATEMENT EXECUTE FUNCTION public.receita_registrar_truncate();

-- ─────────────────────────────────────────── D. leitura as-of ──
CREATE FUNCTION public.receita_as_of(p_conhecido_ate timestamptz DEFAULT now(), p_fonte text DEFAULT NULL)
RETURNS SETOF public.receita_observacao
LANGUAGE sql STABLE SET search_path = pg_catalog, public AS $f$
  SELECT v.* FROM (
    SELECT DISTINCT ON (o.tabela_origem, o.chave) o.*
      FROM public.receita_observacao o
     WHERE o.coletado_em <= p_conhecido_ate
       AND (p_fonte IS NULL OR o.fonte = p_fonte)
     ORDER BY o.tabela_origem, o.chave, o.id DESC
  ) v
  WHERE NOT v.removida
$f$;

CREATE VIEW public.vw_receita_vigente WITH (security_invoker = true) AS
  SELECT v.* FROM (
    SELECT DISTINCT ON (o.tabela_origem, o.chave) o.*
      FROM public.receita_observacao o
     ORDER BY o.tabela_origem, o.chave, o.id DESC
  ) v
  WHERE NOT v.removida;

-- ───────────────────────────────────────────── privilégios ──
-- O default ACL do Supabase dá tudo a anon/authenticated em objeto novo do
-- public; e função nasce executável por PUBLIC. Fecha os dois.
-- service_role também perde a escrita: só o gatilho grava no diário.
REVOKE ALL ON TABLE public.receita_observacao FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.vw_receita_vigente FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.receita_observacao, public.vw_receita_vigente TO service_role;
-- A sequência do diário também nasce com o default ACL aberto: um setval de
-- quem não é dono faz o próximo gatilho do diário colidir na PK (23505) e
-- derruba o upsert de receita que o disparou. Ninguém além do dono precisa
-- dela (quem grava é o gatilho SECURITY DEFINER do dono).
REVOKE ALL ON SEQUENCE public.receita_observacao_id_seq FROM PUBLIC, anon, authenticated, service_role;
REVOKE USAGE, UPDATE ON SEQUENCE public.receita_observacao_id_seq FROM postgres;

-- Câmbio: anon e authenticated deixam de escrever. O que tinham fica guardado
-- em v23_01_acl_anterior para o rollback devolver exatamente.
CREATE TABLE public.v23_01_acl_anterior (papel text NOT NULL, privilegio text NOT NULL, PRIMARY KEY (papel, privilegio));
REVOKE ALL ON TABLE public.v23_01_acl_anterior FROM PUBLIC, anon, authenticated, service_role;
INSERT INTO public.v23_01_acl_anterior (papel, privilegio)
SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END, a.privilege_type
  FROM pg_class c, aclexplode(c.relacl) a
 WHERE c.oid = 'public.exchange_rate_history'::regclass
   AND a.privilege_type IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
   AND (a.grantee = 0 OR pg_get_userbyid(a.grantee) IN ('anon', 'authenticated'));
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.exchange_rate_history FROM PUBLIC, anon, authenticated;

-- record_exchange_rate_change() (AFTER UPDATE em system_settings) fica
-- INVOKER: anon/authenticated que mudarem dollar_exchange_rate recebem 42501.

REVOKE ALL ON FUNCTION public.cambio_versao_guarda() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.receita_registrar_truncate() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.receita_observacao_imutavel() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.receita_registrar_observacao() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.receita_observar(text, text, text, jsonb, text[], text, boolean, jsonb)
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.cambio_resolver(date, text, integer, timestamptz) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.receita_as_of(timestamptz, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cambio_resolver(date, text, integer, timestamptz) TO service_role;
GRANT EXECUTE ON FUNCTION public.receita_as_of(timestamptz, text) TO service_role;

-- ─────────────────────────────────────────── carga inicial ──
-- O as-of começa aqui: coletado_em é o instante da migration, não o
-- updated_at da linha (que só diz quando o último upsert passou).
SELECT count(*) FILTER (WHERE public.receita_observar('joinads', 'USD', 'joinads_metrics', to_jsonb(j),
         ARRAY['date', 'utm_campaign_value', 'joinads_domain'], 'CARGA', false,
         jsonb_build_object('origem', 'v23_01 carga inicial', 'updated_at_origem', to_jsonb(j) -> 'updated_at')))
  FROM public.joinads_metrics j;
SELECT count(*) FILTER (WHERE public.receita_observar('gam', 'USD', 'gam_metrics', to_jsonb(g),
         ARRAY['date', 'utm_campaign_value', 'gam_accounts_id'], 'CARGA', false,
         jsonb_build_object('origem', 'v23_01 carga inicial', 'updated_at_origem', to_jsonb(g) -> 'updated_at')))
  FROM public.gam_metrics g;

NOTIFY pgrst, 'reload schema';

COMMIT;
