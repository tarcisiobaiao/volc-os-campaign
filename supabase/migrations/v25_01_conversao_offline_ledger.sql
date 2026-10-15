-- =============================================================================
-- v25_01 — W14: registro de conversões offline enviadas à Data Manager API
--
-- ESTADO: PROPOSTA. Não aplicada. Aplicar exige janela e autorização do
-- Tarcisio. Prova: tools/freedom-lab/db/suites/v25_w14.sh (lab.sh recriar-prod).
-- Quem aplica e reverte: o mesmo papel (supabase_admin em produção), que vira
-- dono das tabelas e das funções SECURITY DEFINER.
--
-- POR QUE TABELAS NOVAS e não conversion_queue/conversion_batches: as duas
-- legadas não têm destino (conta dona + id da ação), conta, wbraid/gbraid,
-- consentimento nem chave de dedup, e não têm DDL no repo
-- (backend/app/trafego/data_manager.py, auditoria de 02/09/2026). Elas não são
-- tocadas aqui.
--
-- O QUE GARANTE:
--   1. decisão por clique (elegível ou pulado + motivo) com a proveniência do
--      valor, append-only, gravada antes de qualquer envio;
--   2. um lote abre `em_voo` ANTES da chamada; o mesmo envelope não tem dois
--      envios reais vivos, e o mesmo transaction_id também não (índices
--      únicos parciais: é o banco, não o processo, que garante no máximo uma vez);
--   3. envio real exige aprovação humana com a impressão EXATA do envelope,
--      um validate_only ACEITO do mesmo envelope com os MESMOS itens, e uma
--      decisão `elegivel` gravada com o mesmo valor para cada item;
--   3a. TETO DO RATEIO: num envio real, por coorte, a soma dos valores vivos
--      (os já enviados + os do lote) não passa do teto da coorte gravado na
--      proveniência, e o número de cliques não passa das sessões (23514);
--   3b. lote real `sem_resposta` só sai pelo reenvio do MESMO envelope
--      (vira `reenviado`): no Google, mesmo transactionId na mesma ação é
--      ajuste e não conta de novo;
--   4. transições de estado fechadas; request_id imutável depois de gravado;
--      DELETE e TRUNCATE recusados; identidade do lote imutável;
--   5. anon e authenticated sem acesso nenhum; service_role lê, grava decisão
--      e chama as duas RPCs.
-- =============================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';

DO $pre$
BEGIN
  IF to_regclass('public.conversao_offline_decisao') IS NOT NULL
     OR to_regclass('public.conversao_offline_lote') IS NOT NULL
     OR to_regclass('public.conversao_offline_item') IS NOT NULL THEN
    RAISE EXCEPTION 'v25_01: tabelas de conversão offline já existem; não reaplica por cima'
      USING ERRCODE = '55000';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
     OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    RAISE EXCEPTION 'v25_01: base errada (faltam papéis do Supabase)' USING ERRCODE = '55000';
  END IF;
END
$pre$;

-- ───────────────────────────────────────────────────────── decisões ──
CREATE TABLE public.conversao_offline_decisao (
  id                      bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  rodada                  text        NOT NULL CHECK (length(rodada) BETWEEN 1 AND 128),
  customer_id             text        NOT NULL CHECK (customer_id ~ '^[0-9]{10}$'),
  operating_account_id    text        NOT NULL CHECK (operating_account_id ~ '^[0-9]{10}$'),
  product_destination_id  text        NOT NULL CHECK (product_destination_id ~ '^[0-9]{1,20}$'),
  transaction_id          text        NOT NULL CHECK (transaction_id ~ '^volc-w14-[0-9a-f]{40}$'),
  visita_ref              text        NOT NULL,
  clique_tipo             text        NOT NULL CHECK (clique_tipo IN ('gclid', 'gbraid', 'wbraid')),
  -- ⚠️ o hash, nunca o identificador cru: o cru continua só em site_visits
  clique_sha256           text        NOT NULL CHECK (clique_sha256 ~ '^[0-9a-f]{64}$'),
  ocorrido_em             timestamptz,
  estado                  text        NOT NULL CHECK (estado IN ('elegivel', 'pulado')),
  -- a coorte do clique (campanha-dia-domínio): é por ela que o teto é somado
  coorte_data             date        NOT NULL,
  coorte_campanha         text        NOT NULL CHECK (length(btrim(coorte_campanha)) > 0),
  coorte_dominio          text        NOT NULL CHECK (length(btrim(coorte_dominio)) > 0),
  motivo                  text,
  detalhe                 text,
  valor                   numeric,
  moeda                   text,
  estimado                boolean,
  valor_impressao         text,
  proveniencia            jsonb       NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(proveniencia) = 'object'),
  decidido_em             timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT conversao_offline_decisao_unica UNIQUE (rodada, operating_account_id, product_destination_id, transaction_id),
  -- elegível: valor medido > 0 (nunca zero, nunca ausente), moeda, hora e proveniência.
  -- ⚠️ coalesce(…, false): CHECK que dá NULL PASSA, e jsonb_typeof de chave
  -- ausente é NULL. Sem ele, proveniência vazia entrava. (Suíte v25, ciclo 1.)
  CONSTRAINT conversao_offline_decisao_elegivel CHECK (estado <> 'elegivel' OR coalesce((
      valor > 0 AND moeda ~ '^[A-Z]{3}$' AND ocorrido_em IS NOT NULL AND estimado IS NOT NULL
      AND valor_impressao ~ '^[0-9a-f]{64}$' AND motivo IS NULL
      AND jsonb_typeof(proveniencia -> 'receita') = 'object'
      AND jsonb_typeof(proveniencia -> 'cambio') = 'object'
      -- rateio declara as sessões e o teto que o banco confere no envio real
      AND (proveniencia ->> 'metodo' IS DISTINCT FROM 'rateio_uniforme_por_sessao' OR (
           jsonb_typeof(proveniencia -> 'sessoes_da_coorte') = 'number'
           AND (proveniencia ->> 'sessoes_da_coorte') ~ '^[1-9][0-9]*$'
           AND (proveniencia ->> 'teto_da_coorte') ~ '^[0-9]+(\.[0-9]{1,2})?$'
           AND valor <= (proveniencia ->> 'teto_da_coorte')::numeric))), false)),
  -- pulado: motivo nomeado e nenhum valor
  CONSTRAINT conversao_offline_decisao_pulado CHECK (estado <> 'pulado' OR (
      length(btrim(coalesce(motivo, ''))) > 0 AND length(btrim(coalesce(detalhe, ''))) > 0
      AND valor IS NULL AND moeda IS NULL AND valor_impressao IS NULL))
);
CREATE INDEX conversao_offline_decisao_tid ON public.conversao_offline_decisao (operating_account_id, product_destination_id, transaction_id);

-- ───────────────────────────────────────────────────────────── lotes ──
CREATE TABLE public.conversao_offline_lote (
  id                      bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  impressao               text        NOT NULL CHECK (impressao ~ '^[0-9a-f]{64}$'),
  modo                    text        NOT NULL CHECK (modo IN ('validate_only', 'real')),
  customer_id             text        NOT NULL CHECK (customer_id ~ '^[0-9]{10}$'),
  login_customer_id       text        NOT NULL CHECK (login_customer_id ~ '^[0-9]{10}$'),
  operating_account_id    text        NOT NULL CHECK (operating_account_id ~ '^[0-9]{10}$'),
  product_destination_id  text        NOT NULL CHECK (product_destination_id ~ '^[0-9]{1,20}$'),
  itens                   integer     NOT NULL CHECK (itens BETWEEN 1 AND 2000),
  estado                  text        NOT NULL DEFAULT 'em_voo' CHECK (estado IN
                            ('em_voo', 'aceito', 'recusado', 'sem_resposta', 'reenviado',
                             'processando', 'sucesso', 'falha', 'sucesso_parcial')),
  request_id              text,
  aprovacao               jsonb,
  validacao_lote_id       bigint      REFERENCES public.conversao_offline_lote (id) ON DELETE RESTRICT,
  resposta                jsonb,
  historico               jsonb       NOT NULL DEFAULT '[]'::jsonb,
  criado_em               timestamptz NOT NULL DEFAULT now(),
  atualizado_em           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT conversao_offline_lote_real_exige CHECK (
      (modo = 'real') = (aprovacao IS NOT NULL AND validacao_lote_id IS NOT NULL)),
  CONSTRAINT conversao_offline_lote_aprovacao CHECK (aprovacao IS NULL OR coalesce((
      jsonb_typeof(aprovacao) = 'object' AND aprovacao ->> 'impressao' = impressao
      AND length(btrim(coalesce(aprovacao ->> 'aprovado_por', ''))) > 0
      AND length(btrim(coalesce(aprovacao ->> 'referencia', ''))) > 0
      AND jsonb_typeof(aprovacao -> 'destino_primario') = 'boolean'
      AND coalesce(aprovacao ->> 'aprovado_em', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?([+-][0-9]{2}:[0-9]{2}|Z)$'), false)),
  -- validate_only nunca passa de aceito/recusado/sem_resposta
  CONSTRAINT conversao_offline_lote_validacao_estados CHECK (
      modo = 'real' OR estado IN ('em_voo', 'aceito', 'recusado', 'sem_resposta')),
  CONSTRAINT conversao_offline_lote_real_aceito_tem_request CHECK (
      modo <> 'real' OR estado IN ('em_voo', 'recusado', 'sem_resposta', 'reenviado') OR request_id IS NOT NULL)
);
-- o MESMO envelope não tem dois envios reais vivos
CREATE UNIQUE INDEX conversao_offline_lote_real_vivo
  ON public.conversao_offline_lote (impressao) WHERE modo = 'real' AND estado NOT IN ('recusado', 'falha', 'reenviado');

CREATE TABLE public.conversao_offline_item (
  lote_id                 bigint      NOT NULL REFERENCES public.conversao_offline_lote (id) ON DELETE RESTRICT,
  modo                    text        NOT NULL CHECK (modo IN ('validate_only', 'real')),
  operating_account_id    text        NOT NULL CHECK (operating_account_id ~ '^[0-9]{10}$'),
  product_destination_id  text        NOT NULL CHECK (product_destination_id ~ '^[0-9]{1,20}$'),
  transaction_id          text        NOT NULL CHECK (transaction_id ~ '^volc-w14-[0-9a-f]{40}$'),
  valor_impressao         text        NOT NULL CHECK (valor_impressao ~ '^[0-9a-f]{64}$'),
  estado                  text        NOT NULL DEFAULT 'em_voo',
  PRIMARY KEY (lote_id, transaction_id)
);
-- o MESMO transaction_id não tem dois envios reais vivos, em lote nenhum
CREATE UNIQUE INDEX conversao_offline_item_real_vivo
  ON public.conversao_offline_item (operating_account_id, product_destination_id, transaction_id)
  WHERE modo = 'real' AND estado IN ('em_voo', 'aceito', 'sem_resposta', 'processando', 'sucesso', 'sucesso_parcial');

-- ───────────────────────────────────── envio real vivo por coorte ──
-- Cada item real vivo com a SUA decisão elegível (mesmo valor). A mesma
-- decisão pode se repetir em rodadas; o LATERAL pega uma só.
CREATE VIEW public.conversao_offline_envio_por_coorte WITH (security_invoker = true) AS
SELECT i.operating_account_id, i.product_destination_id,
       d.coorte_data, d.coorte_campanha, d.coorte_dominio,
       count(*)::integer AS itens_vivos, sum(d.valor) AS soma_valor
  FROM public.conversao_offline_item i
  CROSS JOIN LATERAL (
    SELECT x.coorte_data, x.coorte_campanha, x.coorte_dominio, x.valor
      FROM public.conversao_offline_decisao x
     WHERE x.operating_account_id = i.operating_account_id
       AND x.product_destination_id = i.product_destination_id
       AND x.transaction_id = i.transaction_id
       AND x.estado = 'elegivel' AND x.valor_impressao = i.valor_impressao
     ORDER BY x.id LIMIT 1) d
 WHERE i.modo = 'real'
   AND i.estado IN ('em_voo', 'aceito', 'sem_resposta', 'processando', 'sucesso', 'sucesso_parcial')
 GROUP BY 1, 2, 3, 4, 5;

-- ─────────────────────────────────────────────── imutabilidade ──
CREATE FUNCTION public.conversao_offline_imutavel() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $f$
BEGIN
  IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
    RAISE EXCEPTION 'conversão offline: % em % é recusado (registro de envio não se apaga)', TG_OP, TG_TABLE_NAME
      USING ERRCODE = '55000';
  END IF;
  IF TG_TABLE_NAME = 'conversao_offline_decisao' THEN
    RAISE EXCEPTION 'conversão offline: decisão é append-only' USING ERRCODE = '55000';
  END IF;
  IF TG_TABLE_NAME = 'conversao_offline_lote' THEN
    IF (NEW.impressao, NEW.modo, NEW.customer_id, NEW.login_customer_id, NEW.operating_account_id,
        NEW.product_destination_id, NEW.itens, NEW.aprovacao, NEW.validacao_lote_id, NEW.criado_em)
       IS DISTINCT FROM
       (OLD.impressao, OLD.modo, OLD.customer_id, OLD.login_customer_id, OLD.operating_account_id,
        OLD.product_destination_id, OLD.itens, OLD.aprovacao, OLD.validacao_lote_id, OLD.criado_em) THEN
      RAISE EXCEPTION 'conversão offline: a identidade do lote é imutável' USING ERRCODE = '55000';
    END IF;
    IF OLD.request_id IS NOT NULL AND NEW.request_id IS DISTINCT FROM OLD.request_id THEN
      RAISE EXCEPTION 'conversão offline: request_id gravado não muda' USING ERRCODE = '55000';
    END IF;
  END IF;
  IF TG_TABLE_NAME = 'conversao_offline_item' THEN
    IF (NEW.lote_id, NEW.modo, NEW.operating_account_id, NEW.product_destination_id,
        NEW.transaction_id, NEW.valor_impressao) IS DISTINCT FROM
       (OLD.lote_id, OLD.modo, OLD.operating_account_id, OLD.product_destination_id,
        OLD.transaction_id, OLD.valor_impressao) THEN
      RAISE EXCEPTION 'conversão offline: só o estado do item muda' USING ERRCODE = '55000';
    END IF;
  END IF;
  RETURN NEW;
END
$f$;

CREATE TRIGGER conversao_offline_decisao_imutavel BEFORE UPDATE OR DELETE ON public.conversao_offline_decisao
  FOR EACH ROW EXECUTE FUNCTION public.conversao_offline_imutavel();
CREATE TRIGGER conversao_offline_decisao_sem_truncate BEFORE TRUNCATE ON public.conversao_offline_decisao
  FOR EACH STATEMENT EXECUTE FUNCTION public.conversao_offline_imutavel();
CREATE TRIGGER conversao_offline_lote_imutavel BEFORE UPDATE OR DELETE ON public.conversao_offline_lote
  FOR EACH ROW EXECUTE FUNCTION public.conversao_offline_imutavel();
CREATE TRIGGER conversao_offline_lote_sem_truncate BEFORE TRUNCATE ON public.conversao_offline_lote
  FOR EACH STATEMENT EXECUTE FUNCTION public.conversao_offline_imutavel();
CREATE TRIGGER conversao_offline_item_imutavel BEFORE UPDATE OR DELETE ON public.conversao_offline_item
  FOR EACH ROW EXECUTE FUNCTION public.conversao_offline_imutavel();
CREATE TRIGGER conversao_offline_item_sem_truncate BEFORE TRUNCATE ON public.conversao_offline_item
  FOR EACH STATEMENT EXECUTE FUNCTION public.conversao_offline_imutavel();

-- ───────────────────────────────────────────────────── RPC: abrir ──
-- p = {modo, impressao, customer_id, login_customer_id, operating_account_id,
--      product_destination_id, itens: [{transaction_id, valor_impressao}],
--      aprovacao?, validacao_lote_id?}
CREATE FUNCTION public.conversao_offline_abrir_lote(p jsonb) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $f$
DECLARE
  v_id bigint;
  v_val public.conversao_offline_lote%ROWTYPE;
  v_n integer;
  v_diff integer;
BEGIN
  IF p IS NULL OR jsonb_typeof(p -> 'itens') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'abrir_lote: itens precisa ser uma lista' USING ERRCODE = '22023';
  END IF;
  v_n := jsonb_array_length(p -> 'itens');

  IF p ->> 'modo' = 'real' THEN
    SELECT * INTO v_val FROM public.conversao_offline_lote
     WHERE id = (p ->> 'validacao_lote_id')::bigint FOR SHARE;
    IF NOT FOUND OR v_val.modo <> 'validate_only' OR v_val.estado <> 'aceito'
       OR v_val.impressao <> p ->> 'impressao'
       OR v_val.operating_account_id <> p ->> 'operating_account_id'
       OR v_val.product_destination_id <> p ->> 'product_destination_id' THEN
      RAISE EXCEPTION 'abrir_lote: envio real sem validate_only aceito do mesmo envelope'
        USING ERRCODE = '55000';
    END IF;
    -- os itens do real são EXATAMENTE os validados (nos dois sentidos)
    SELECT count(*) INTO v_diff FROM (
      (SELECT i ->> 'transaction_id', i ->> 'valor_impressao' FROM jsonb_array_elements(p -> 'itens') i
       EXCEPT SELECT transaction_id, valor_impressao FROM public.conversao_offline_item WHERE lote_id = v_val.id)
      UNION ALL
      (SELECT transaction_id, valor_impressao FROM public.conversao_offline_item WHERE lote_id = v_val.id
       EXCEPT SELECT i ->> 'transaction_id', i ->> 'valor_impressao' FROM jsonb_array_elements(p -> 'itens') i)
    ) d;
    IF v_diff > 0 OR v_n <> v_val.itens THEN
      RAISE EXCEPTION 'abrir_lote: os itens do envio real não são os do validate_only aceito'
        USING ERRCODE = '55000';
    END IF;
    -- cada item tem uma decisão elegível gravada com o MESMO valor
    IF EXISTS (
      SELECT 1 FROM jsonb_array_elements(p -> 'itens') i
       WHERE NOT EXISTS (
         SELECT 1 FROM public.conversao_offline_decisao d
          WHERE d.operating_account_id = p ->> 'operating_account_id'
            AND d.product_destination_id = p ->> 'product_destination_id'
            AND d.transaction_id = i ->> 'transaction_id'
            AND d.estado = 'elegivel'
            AND d.valor_impressao = i ->> 'valor_impressao')) THEN
      RAISE EXCEPTION 'abrir_lote: item sem decisão elegível com o mesmo valor (proveniência ausente)'
        USING ERRCODE = '55000';
    END IF;
    -- reenvio do MESMO envelope que ficou sem resposta: o anterior vira 'reenviado'
    UPDATE public.conversao_offline_lote
       SET estado = 'reenviado', atualizado_em = now(),
           historico = historico || jsonb_build_array(jsonb_build_object(
                         'de', 'sem_resposta', 'para', 'reenviado', 'em', now()))
     WHERE modo = 'real' AND impressao = p ->> 'impressao' AND estado = 'sem_resposta';
    UPDATE public.conversao_offline_item it SET estado = 'reenviado'
      FROM public.conversao_offline_lote l
     WHERE it.lote_id = l.id AND l.modo = 'real' AND l.impressao = p ->> 'impressao'
       AND l.estado = 'reenviado' AND it.estado = 'sem_resposta';
    -- ⚠️ TETO DO RATEIO (revisão nuvem 2, obrigatório 2): por coorte, o que já
    -- está vivo + o que este lote leva não passa do teto nem das sessões.
    -- Conferido DEPOIS de liberar o reenvio do mesmo envelope, para que ele
    -- não conte duas vezes.
    IF EXISTS (
      WITH novos AS (
        SELECT DISTINCT ON (i ->> 'transaction_id')
               d.coorte_data, d.coorte_campanha, d.coorte_dominio, d.valor,
               (d.proveniencia ->> 'teto_da_coorte')::numeric AS teto,
               (d.proveniencia ->> 'sessoes_da_coorte')::integer AS sessoes
          FROM jsonb_array_elements(p -> 'itens') i
          JOIN public.conversao_offline_decisao d
            ON d.operating_account_id = p ->> 'operating_account_id'
           AND d.product_destination_id = p ->> 'product_destination_id'
           AND d.transaction_id = i ->> 'transaction_id'
           AND d.estado = 'elegivel' AND d.valor_impressao = i ->> 'valor_impressao'
         WHERE d.proveniencia ->> 'metodo' = 'rateio_uniforme_por_sessao'
         ORDER BY i ->> 'transaction_id', d.id),
      por_coorte AS (
        SELECT coorte_data, coorte_campanha, coorte_dominio,
               sum(valor) AS soma, count(*) AS n, min(teto) AS teto, min(sessoes) AS sessoes
          FROM novos GROUP BY 1, 2, 3)
      SELECT 1 FROM por_coorte n
        LEFT JOIN public.conversao_offline_envio_por_coorte e
          ON e.operating_account_id = p ->> 'operating_account_id'
         AND e.product_destination_id = p ->> 'product_destination_id'
         AND (e.coorte_data, e.coorte_campanha, e.coorte_dominio)
             = (n.coorte_data, n.coorte_campanha, n.coorte_dominio)
       WHERE n.teto IS NULL OR n.sessoes IS NULL
          OR n.soma + coalesce(e.soma_valor, 0) > n.teto
          OR n.n + coalesce(e.itens_vivos, 0) > n.sessoes) THEN
      RAISE EXCEPTION 'abrir_lote: a soma enviada da coorte passaria da receita medida (teto ou sessões)'
        USING ERRCODE = '23514';
    END IF;
  ELSIF (p ? 'aprovacao' AND p -> 'aprovacao' <> 'null'::jsonb)
        OR (p ? 'validacao_lote_id' AND p -> 'validacao_lote_id' <> 'null'::jsonb) THEN
    RAISE EXCEPTION 'abrir_lote: validate_only não carrega aprovação' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.conversao_offline_lote
    (impressao, modo, customer_id, login_customer_id, operating_account_id,
     product_destination_id, itens, aprovacao, validacao_lote_id)
  VALUES (p ->> 'impressao', p ->> 'modo', p ->> 'customer_id', p ->> 'login_customer_id',
          p ->> 'operating_account_id', p ->> 'product_destination_id', v_n,
          CASE WHEN p -> 'aprovacao' = 'null'::jsonb THEN NULL ELSE p -> 'aprovacao' END,
          (p ->> 'validacao_lote_id')::bigint)
  RETURNING id INTO v_id;

  INSERT INTO public.conversao_offline_item
    (lote_id, modo, operating_account_id, product_destination_id, transaction_id, valor_impressao)
  SELECT v_id, p ->> 'modo', p ->> 'operating_account_id', p ->> 'product_destination_id',
         i ->> 'transaction_id', i ->> 'valor_impressao'
    FROM jsonb_array_elements(p -> 'itens') i;

  RETURN v_id;
END
$f$;

-- ──────────────────────────────────────────────────── RPC: fechar ──
CREATE FUNCTION public.conversao_offline_fechar_lote(
  p_lote_id bigint, p_estado text, p_request_id text, p_resposta jsonb
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $f$
DECLARE
  l public.conversao_offline_lote%ROWTYPE;
  permitido boolean;
BEGIN
  SELECT * INTO l FROM public.conversao_offline_lote WHERE id = p_lote_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'fechar_lote: lote % não existe', p_lote_id USING ERRCODE = 'P0002';
  END IF;
  permitido := CASE
    WHEN l.estado = 'em_voo' THEN p_estado IN ('aceito', 'recusado', 'sem_resposta')
    WHEN l.modo = 'real' AND l.estado IN ('aceito', 'processando')
      THEN p_estado IN ('processando', 'sucesso', 'falha', 'sucesso_parcial')
    ELSE false END;
  IF NOT permitido THEN
    RAISE EXCEPTION 'fechar_lote: % (%) não vai para %', l.estado, l.modo, p_estado USING ERRCODE = '55000';
  END IF;
  IF l.request_id IS NOT NULL AND p_request_id IS DISTINCT FROM l.request_id THEN
    RAISE EXCEPTION 'fechar_lote: o lote % é do pedido %, não de %', p_lote_id, l.request_id, p_request_id
      USING ERRCODE = '55000';
  END IF;
  UPDATE public.conversao_offline_lote
     SET estado = p_estado,
         request_id = coalesce(l.request_id, p_request_id),
         resposta = p_resposta,
         historico = l.historico || jsonb_build_array(jsonb_build_object(
                       'de', l.estado, 'para', p_estado, 'em', now(), 'request_id', p_request_id)),
         atualizado_em = now()
   WHERE id = p_lote_id;
  UPDATE public.conversao_offline_item SET estado = p_estado WHERE lote_id = p_lote_id;
  RETURN p_estado;
END
$f$;

-- ───────────────────────────────────────────────────── privilégios ──
ALTER TABLE public.conversao_offline_decisao ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversao_offline_lote    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversao_offline_item    ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.conversao_offline_decisao, public.conversao_offline_lote,
                    public.conversao_offline_item FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.conversao_offline_decisao, public.conversao_offline_lote,
                     public.conversao_offline_item TO service_role;
REVOKE ALL ON TABLE public.conversao_offline_envio_por_coorte FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.conversao_offline_envio_por_coorte TO service_role;
GRANT INSERT ON TABLE public.conversao_offline_decisao TO service_role;
-- as sequências de identidade nascem com o default ACL do Supabase (anon incluída)
REVOKE ALL ON SEQUENCE public.conversao_offline_decisao_id_seq, public.conversao_offline_lote_id_seq
  FROM PUBLIC, anon, authenticated, service_role;

REVOKE ALL ON FUNCTION public.conversao_offline_imutavel() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.conversao_offline_abrir_lote(jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.conversao_offline_fechar_lote(bigint, text, text, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.conversao_offline_abrir_lote(jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.conversao_offline_fechar_lote(bigint, text, text, jsonb) TO service_role;

COMMENT ON TABLE public.conversao_offline_decisao IS 'W14 v25_01: decisão por clique (elegível/pulado) com proveniência do valor. Append-only.';
COMMENT ON TABLE public.conversao_offline_lote IS 'W14 v25_01: lote de events:ingest (validate_only ou real). Real exige aprovação + validate_only aceito do mesmo envelope.';
COMMENT ON TABLE public.conversao_offline_item IS 'W14 v25_01: transaction_id por lote. Um único envio real vivo por transaction_id.';

NOTIFY pgrst, 'reload schema';

COMMIT;
