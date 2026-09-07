-- =============================================================================
-- 20260908000000_meta_insights_escopo.sql
--
-- ADITIVA. Nao apaga linha, nao apaga coluna, nao apaga tabela, nao estreita
-- dominio nenhum. Ela abre o caminho que hoje esta FECHADO entre o fluxo n8n de
-- insights (`n8n/volc_meta_insights_dia_d1.json`) e a RPC canonica
-- `public.trafego_meta_persistir_snapshot`.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- O QUE ESTAVA IMPOSSIVEL (tres incompatibilidades, todas verificadas)
-- ─────────────────────────────────────────────────────────────────────────────
--
-- (a) ESCOPO IMPOSSIVEL DE GRAVAR.
--     `v15_01_meta_ads_read_model.sql:238` declara
--     `CONSTRAINT trafego_meta_sync_escopo_conhecido CHECK (escopo = 'hierarchy')`,
--     e `20260907210000_meta_read_model_consistency.sql:1203-1205` grava o literal
--     `'hierarchy'` no INSERT do recibo. O fluxo produz `insights_pagina` (por
--     pagina lida) e `insights_fechamento` (o recibo da execucao). Nenhum dos dois
--     tinha como existir: a coluna nao aceitava o valor e a RPC nem o lia.
--
-- (b) FECHAMENTO DE EXECUCAO SEM CONTA.
--     `20260907210000:699` recusa `account_asset_id` nulo, e
--     `v15_01:221` declara `ad_account_ativo_id text NOT NULL`. Mas o snapshot de
--     `insights_fechamento` e da EXECUCAO, nao de uma conta: ele resume N contas
--     em `contas[]` e manda `account_asset_id: null` DE PROPOSITO
--     (`n8n/gerar_flows_meta_ledger.py`, bloco JS_FECHAR). Escolher uma das N
--     contas para preencher a coluna seria inventar um dono para um recibo que
--     nao tem um.
--
-- (c) COMPLETUDE DE HIERARQUIA EXIGIDA DE QUEM NAO LE HIERARQUIA.
--     `20260907210000:713` levanta `META_LEITURA_SEM_COMPLETUDE` quando
--     `hierarchy_complete` nao e booleano. A regra e certa e continua valendo: e
--     ela que impede marcar AUSENCIA de campanha/adset/ad a partir de uma leitura
--     truncada. So que o fluxo de insights nunca percorre a hierarquia — exigir
--     dele uma declaracao sobre o que ele nao olhou so ensina o produtor a
--     responder qualquer coisa para o INSERT passar, que e o oposto do que a
--     guarda existe para conseguir.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- POR QUE CADA PASSO E SEGURO, E POR QUE NENHUMA LINHA EXISTENTE VIOLA
-- ─────────────────────────────────────────────────────────────────────────────
--
-- PASSO 1 — alargar o CHECK de `escopo`.
--   `CHECK (escopo = 'hierarchy')` vira
--   `CHECK (escopo IN ('hierarchy','insights_pagina','insights_fechamento'))`.
--   O dominio novo CONTEM o antigo: alargar um CHECK nunca pode invalidar linha
--   que ja passava. E a prova de que nenhuma linha existente viola e o proprio
--   CHECK antigo — enquanto ele esteve em vigor, `escopo = 'hierarchy'` foi a
--   unica coisa gravavel. O `DEFAULT 'hierarchy'` da coluna fica onde esta: quem
--   nao declara escopo continua gravando hierarquia.
--
-- PASSO 2 — `ad_account_ativo_id` deixa de ser NOT NULL, e ganha um CHECK
--   CONDICIONAL no lugar.
--   ⚠️ NAO E "NULL LIBERADO". `DROP NOT NULL` sozinho permitiria uma pagina de
--   insights sem conta — e uma pagina de insights SEMPRE le uma conta so; sem ela
--   as linhas de `trafego_meta_insight_daily` ficariam sem por quem foram lidas.
--   Entao o NOT NULL e substituido por um CHECK que so abre a excecao onde ela e
--   verdadeira:
--       CHECK (ad_account_ativo_id IS NOT NULL OR escopo = 'insights_fechamento')
--   Ou seja: 'hierarchy' e 'insights_pagina' continuam exigindo conta, exatamente
--   como antes. So o recibo de execucao pode vir sem.
--   ⚠️ ESCOLHA MAIS ESTREITA QUE A PEDIDA, E DE PROPOSITO: o pedido dizia "NULL
--   nos escopos de insights"; aqui NULL vale so em 'insights_fechamento', porque
--   'insights_pagina' e o unico dos dois que de fato tem uma conta
--   (`gerar_flows_meta_ledger.py`, JS_VALIDAR, manda
--   `account_asset_id: String(ctx.conta_ativo_id)`). Permitir NULL ali seria abrir
--   uma porta que nenhum produtor usa e que orfanaria fatos.
--   Nenhuma linha existente viola: enquanto o NOT NULL esteve em vigor, nao houve
--   como gravar nulo. A FK para `trafego_meta_ad_account` CONTINUA — em SQL, FK
--   com valor nulo simplesmente nao e conferida, entao a integridade referencial
--   das linhas com conta nao muda em nada.
--   O indice `trafego_meta_sync_conta_ix (ad_account_ativo_id, concluido_em DESC)`
--   segue valido; nulos indexam normalmente em btree.
--
-- PASSO 3 — a RPC passa a LER o escopo em vez de fixa-lo.
--   `CREATE OR REPLACE FUNCTION` em plpgsql exige o corpo inteiro; por isso a
--   funcao aparece completa aqui. O corpo e o de
--   `20260907210000_meta_read_model_consistency.sql:657-1249`, e o diff contra ele
--   e exatamente este e nada mais:
--     1. `v_escopo` novo, com `DEFAULT 'hierarchy'` quando o campo falta —
--        compatibilidade com `backend/app/trafego/meta/read_model.py:payload_rpc()`,
--        que NAO envia `escopo`. Para o produtor Python de hoje, nada muda.
--     2. allowlist de escopo (`META_ESCOPO_DESCONHECIDO`), para que um escopo
--        errado pare no erro em vez de virar 'hierarchy' calado.
--     3. a exigencia de conta vira condicional ao escopo
--        (`META_SNAPSHOT_SEM_CONTA`), espelhando o CHECK do PASSO 2.
--     4. `hierarchy_complete` so e exigido no escopo 'hierarchy'. Fora dele a
--        completude vem de `completo`; AUSENTE VALE FALSE, porque "nao declarou"
--        nunca pode significar "completa".
--     5. o Cofre so declara o ativo da conta quando existe conta.
--     6. a marcacao de AUSENCIA (7.7) passa a exigir `v_escopo = 'hierarchy'`
--        alem de `v_completo`. Sem essa linha a migration teria ABERTO um buraco:
--        uma pagina de insights que se declarasse completa marcaria como ausente
--        todo objeto com `ultima_vez_visto_em` anterior a leitura — o inventario
--        inteiro, a partir de uma leitura que nunca listou objeto nenhum.
--     7. o recibo grava `v_escopo` e devolve `escopo` no documento de resposta.
--   O que NAO muda: autorizacao por service_role, `search_path` com `pg_catalog`
--   na frente, resolucao da credencial no servidor, guardas de monotonicidade,
--   recusas de `ordem` de action, e a idempotencia por chave estavel/volatil.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- ORDEM E TRANSACAO
-- ─────────────────────────────────────────────────────────────────────────────
-- Tudo num unico BEGIN/COMMIT: a RPC nova grava escopos que o CHECK antigo
-- recusaria, e o CHECK novo aceita escopos que a RPC antiga nunca produziria.
-- Aplicar metade deixaria o par incoerente. Sem metacomando de psql (`\set`,
-- `\if`): este arquivo tem de rodar igual por psql, pelo Supabase CLI ou colado
-- num console SQL.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. GUARDA DE PRE-CONDICAO — a migration recusa em vez de supor
-- -----------------------------------------------------------------------------
-- O cabecalho AFIRMA que nenhuma linha existente viola os CHECKs novos. Afirmar
-- e barato; conferir custa uma varredura de uma tabela de ledger. Se a afirmacao
-- estiver errada — porque alguem gravou por fora, ou porque um ambiente divergiu
-- —, a migration para aqui, com a transacao inteira desfeita, em vez de deixar um
-- `ADD CONSTRAINT` falhar no meio e sem explicacao.
DO $guarda$
DECLARE
  v_fora_do_dominio bigint;
  v_sem_conta       bigint;
BEGIN
  SELECT count(*) INTO v_fora_do_dominio
    FROM public.trafego_meta_sync_run
   WHERE escopo NOT IN ('hierarchy', 'insights_pagina', 'insights_fechamento');
  IF v_fora_do_dominio > 0 THEN
    RAISE EXCEPTION
      'META_ESCOPO_PREEXISTENTE_FORA_DO_DOMINIO: % linha(s) de trafego_meta_sync_run com escopo fora da allowlist nova; investigar antes de alargar o CHECK',
      v_fora_do_dominio;
  END IF;

  SELECT count(*) INTO v_sem_conta
    FROM public.trafego_meta_sync_run
   WHERE ad_account_ativo_id IS NULL
     AND escopo <> 'insights_fechamento';
  IF v_sem_conta > 0 THEN
    RAISE EXCEPTION
      'META_RUN_SEM_CONTA_PREEXISTENTE: % linha(s) sem conta em escopo que exige conta; o CHECK condicional nao pode ser criado por cima delas',
      v_sem_conta;
  END IF;
END;
$guarda$;

-- -----------------------------------------------------------------------------
-- 1. ESCOPO — o dominio alarga, e so alarga
-- -----------------------------------------------------------------------------
-- `IF EXISTS` porque a migration precisa ser reaplicavel: rodar duas vezes nao
-- pode virar erro. `DROP` seguido de `ADD` na mesma transacao mantem a coluna
-- protegida o tempo todo — nao existe janela em que qualquer valor passe.
ALTER TABLE public.trafego_meta_sync_run
  DROP CONSTRAINT IF EXISTS trafego_meta_sync_escopo_conhecido;
ALTER TABLE public.trafego_meta_sync_run
  ADD CONSTRAINT trafego_meta_sync_escopo_conhecido
  CHECK (escopo IN ('hierarchy', 'insights_pagina', 'insights_fechamento'));

-- -----------------------------------------------------------------------------
-- 2. CONTA — NOT NULL vira CHECK CONDICIONAL, nao permissao geral
-- -----------------------------------------------------------------------------
-- A ordem importa: o CHECK entra ANTES do DROP NOT NULL. Assim, em nenhum
-- instante da transacao a coluna fica sem guarda — se o ADD falhasse, o NOT NULL
-- ainda estaria de pe.
ALTER TABLE public.trafego_meta_sync_run
  DROP CONSTRAINT IF EXISTS trafego_meta_sync_conta_por_escopo;
ALTER TABLE public.trafego_meta_sync_run
  ADD CONSTRAINT trafego_meta_sync_conta_por_escopo
  CHECK (ad_account_ativo_id IS NOT NULL OR escopo = 'insights_fechamento');
ALTER TABLE public.trafego_meta_sync_run
  ALTER COLUMN ad_account_ativo_id DROP NOT NULL;

COMMENT ON CONSTRAINT trafego_meta_sync_conta_por_escopo
  ON public.trafego_meta_sync_run IS
  'Conta obrigatoria em hierarchy e insights_pagina; so o recibo de execucao (insights_fechamento) pode vir sem conta, porque ele resume N contas e nao tem uma.';

-- -----------------------------------------------------------------------------
-- 3. A RPC — mesma funcao de 20260907210000:657-1249, com o escopo LIDO
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trafego_meta_persistir_snapshot(p_snapshot jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_account_asset      text := p_snapshot->>'account_asset_id';
  -- ⚠️ ESCOPO LIDO, NAO FIXADO. DEFAULT 'hierarchy' porque o produtor Python
  -- (`read_model.payload_rpc()`) nao envia o campo: para ele, nada muda.
  v_escopo             text := coalesce(nullif(p_snapshot->>'escopo', ''), 'hierarchy');
  v_credencial_payload text := p_snapshot->>'credential_asset_id';
  v_credencial         text;
  v_snapshot_hash      text := p_snapshot->>'snapshot_hash';
  v_chave_volatil      text := p_snapshot->>'idempotency_key';
  v_chave_estavel      text := p_snapshot->>'stable_idempotency_key';
  v_chave              text;
  v_origem_chave       text;
  v_observed           timestamptz := (p_snapshot->>'observed_at')::timestamptz;
  v_window             text := p_snapshot->>'window';
  v_completo           boolean;
  v_parcialidade       jsonb;
  v_run                uuid := gen_random_uuid();
  v_moeda              text;
  v_fuso               text;
  v_entradas           bigint;
  v_gravadas           bigint;
  v_recusadas          jsonb := '{}'::jsonb;
  v_recusadas_total    bigint := 0;
  v_ausencias          jsonb := '{}'::jsonb;
  v_ausencias_total    bigint := 0;
  v_n                  bigint;
  v_anterior           uuid;
BEGIN
  -- ---------------------------------------------------------------------
  -- 7.1 autorizacao e forma do envelope
  -- ---------------------------------------------------------------------
  IF current_setting('role', true) <> 'service_role'
     AND session_user <> 'service_role'
     AND current_user <> 'service_role' THEN
    RAISE EXCEPTION 'trafego_meta_persistir_snapshot exige service_role';
  END IF;
  IF p_snapshot->>'provider' IS DISTINCT FROM 'META_ADS' THEN
    RAISE EXCEPTION 'provider invalido para snapshot Meta';
  END IF;
  IF v_escopo NOT IN ('hierarchy', 'insights_pagina', 'insights_fechamento') THEN
    RAISE EXCEPTION
      'META_ESCOPO_DESCONHECIDO: escopo % fora da allowlist (hierarchy, insights_pagina, insights_fechamento)',
      v_escopo;
  END IF;
  IF v_observed IS NULL THEN
    RAISE EXCEPTION 'snapshot Meta sem instante observado';
  END IF;
  -- ⚠️ CONTA OBRIGATORIA EM TODO ESCOPO MENOS UM. 'insights_fechamento' e o
  -- recibo de uma EXECUCAO, nao de uma conta: ele resume N contas e nao tem
  -- como escolher uma. Todo o resto — hierarquia e pagina de insights — le
  -- UMA conta, e um snapshot sem conta ali seria linha orfa.
  IF v_account_asset IS NULL AND v_escopo <> 'insights_fechamento' THEN
    RAISE EXCEPTION
      'META_SNAPSHOT_SEM_CONTA: escopo % exige account_asset_id; so o fechamento de execucao pode vir sem conta',
      v_escopo;
  END IF;
  IF v_snapshot_hash !~ '^meta_snapshot_[a-f0-9]{32}$' THEN
    RAISE EXCEPTION 'snapshot Meta sem hash canonico valido';
  END IF;

  -- ---------------------------------------------------------------------
  -- 7.2 COMPLETUDE (defeito 1) — a RPC recusa em vez de adivinhar
  -- ---------------------------------------------------------------------
  -- Marcar ausencia a partir de uma leitura truncada apaga inventario que
  -- existe. Uma pagina que faltou e uma conta que esvaziou tem exatamente a
  -- mesma forma no payload; sem uma declaracao explicita nao ha como
  -- distinguir, e adivinhar aqui e destrutivo. Entao: sem `hierarchy_complete`
  -- booleano, a RPC LEVANTA.
  -- ⚠️ A EXIGENCIA E DO ESCOPO 'hierarchy', E SO DELE — e isso NAO afrouxa a
  -- regra, delimita. `hierarchy_complete` autoriza marcar AUSENCIA de
  -- campanha/adset/ad (7.7). Uma leitura de insights nunca percorre a
  -- hierarquia: exigir dela uma declaracao sobre o que ela nao olhou so
  -- ensinaria o produtor a responder qualquer coisa para passar. Fora do
  -- escopo 'hierarchy' a completude que importa e a da propria leitura, e ela
  -- vem de `completo`; ausente, vale FALSE — porque 'nao declarou' nunca pode
  -- significar 'completa'.
  IF v_escopo = 'hierarchy' THEN
    IF jsonb_typeof(p_snapshot->'hierarchy_complete') IS DISTINCT FROM 'boolean' THEN
      RAISE EXCEPTION
        'META_LEITURA_SEM_COMPLETUDE: o snapshot precisa declarar hierarchy_complete (boolean). Sem ela nao ha como marcar ausencia sem inventar.';
    END IF;
    v_completo := (p_snapshot->>'hierarchy_complete')::boolean;
  ELSIF jsonb_typeof(p_snapshot->'completo') = 'boolean' THEN
    v_completo := (p_snapshot->>'completo')::boolean;
  ELSE
    v_completo := false;
  END IF;

  -- ---------------------------------------------------------------------
  -- 7.3 IDEMPOTENCIA (defeito 3)
  -- ---------------------------------------------------------------------
  -- `idempotency_key` deriva do `snapshot_hash`, que deriva das linhas, que
  -- contem `observado_em`: dois cliques com um segundo de diferenca produzem
  -- duas chaves. A chave ESTAVEL, quando enviada, e a identidade da unidade
  -- logica de trabalho e nao contem o instante.
  IF v_chave_estavel IS NOT NULL THEN
    IF v_chave_estavel !~ '^meta_sync_[a-f0-9]{32}$' THEN
      RAISE EXCEPTION 'stable_idempotency_key fora da forma meta_sync_<32 hex>';
    END IF;
    v_chave := v_chave_estavel;
    v_origem_chave := 'estavel';
  ELSE
    -- Tolerancia deliberada, e assimetrica em relacao a 7.2: cair para a chave
    -- volatil reproduz o comportamento de hoje (um run a mais), enquanto
    -- adivinhar completude apaga dado. Perda de deduplicacao e barulho; ausencia
    -- inventada e estrago.
    IF v_chave_volatil !~ '^meta_sync_[a-f0-9]{32}$' THEN
      RAISE EXCEPTION 'snapshot Meta sem chave de idempotencia valida';
    END IF;
    v_chave := v_chave_volatil;
    v_origem_chave := 'volatil';
  END IF;

  SELECT run_id INTO v_anterior
    FROM public.trafego_meta_sync_run
   WHERE chave_de_idempotencia = v_chave AND resultado = 'ok'
   ORDER BY concluido_em DESC LIMIT 1;
  IF v_anterior IS NOT NULL THEN
    RETURN jsonb_build_object(
      'ok', true, 'repetido', true, 'run_id', v_anterior::text,
      'escopo', v_escopo,
      'chave_origem', v_origem_chave,
      'leitura_completa', v_completo,
      'recusadas_por_desatualizacao', 0,
      'recusadas_por_tabela', '{}'::jsonb,
      'ausencias_marcadas', 0,
      'ausencias_por_tabela', '{}'::jsonb);
  END IF;

  -- ---------------------------------------------------------------------
  -- 7.4 CREDENCIAL RESOLVIDA NO SERVIDOR (defeito 7)
  -- ---------------------------------------------------------------------
  SELECT credential_ativo_id INTO v_credencial
    FROM public.trafego_meta_ad_account
   WHERE cofre_ativo_id = v_account_asset;
  v_credencial := coalesce(v_credencial, public.trafego_meta_credencial_pinada());

  -- O valor nao entra na mensagem: quem chamou ja sabe o que mandou, e repetir
  -- um identificador do chamador em erro so aumenta a chance de vaza-lo em log.
  IF v_credencial_payload IS NOT NULL AND v_credencial_payload <> v_credencial THEN
    RAISE EXCEPTION
      'META_CREDENCIAL_DIVERGENTE: credential_asset_id do payload discorda da credencial registrada para esta conta; identidade nao vem do chamador';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad_account}', '[]'::jsonb))
        AS x(credential_ativo_id text)
     WHERE x.credential_ativo_id IS DISTINCT FROM v_credencial
  ) THEN
    RAISE EXCEPTION
      'META_CREDENCIAL_DIVERGENTE: linha de trafego_meta_ad_account traz outra credencial; identidade nao vem do chamador';
  END IF;

  -- ---------------------------------------------------------------------
  -- 7.5 COFRE — pelo escritor governado, custodia 'declared' (defeito 6)
  -- ---------------------------------------------------------------------
  PERFORM public.trafego_meta_cofre_declarar_ativo(
    v_credencial, 'integration', 'automation',
    'Credencial Meta local (referencia)',
    'restricted', 'critical',
    'Referencia local sanitizada; o token vive no Keychain do backend e nunca no banco.',
    'Manter o token fora do banco e usar somente por backend autorizado.',
    ARRAY['meta_read'], ARRAY['meta','keychain']);

  -- O fechamento de execucao nao tem conta para declarar no Cofre; chamar o
  -- escritor com NULL criaria um ativo sem identidade.
  IF v_account_asset IS NOT NULL THEN
    PERFORM public.trafego_meta_cofre_declarar_ativo(
      v_account_asset, 'meta_ad_account', 'paid_media',
      coalesce(p_snapshot #>> '{rows,trafego_meta_ad_account,0,nome_observado}', 'Conta Meta'),
      'declared', 'high',
      'Conta Meta observada por snapshot somente leitura; custodia declarada, nao verificada.',
      'Consultar o inventario persistido; habilitar escrita apenas por missao autorizada.',
      ARRAY['meta_read'], ARRAY['meta','read-model']);
  END IF;

  PERFORM public.trafego_meta_cofre_declarar_ativo(
    b.cofre_ativo_id, 'meta_business_portfolio', 'paid_media',
    coalesce(b.nome_observado, 'Business Meta'),
    'declared', 'high',
    'Business Meta observado por snapshot somente leitura; custodia declarada, nao verificada.',
    'Manter como contexto da conta Meta observada.',
    ARRAY['meta_read'], ARRAY['meta','business'])
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_business}', '[]'::jsonb))
    AS b(cofre_ativo_id text, nome_observado text);

  -- ---------------------------------------------------------------------
  -- 7.6 UPSERTS COM GUARDA DE MONOTONICIDADE (defeito 2)
  -- ---------------------------------------------------------------------
  -- Cada bloco conta o que ENTROU e o que foi GRAVADO. A diferenca sao as
  -- linhas que a guarda recusou por serem mais velhas do que o que ja esta no
  -- banco — e elas vao para o recibo. Uma recusa que ninguem conta e
  -- indistinguivel de uma escrita que aconteceu.
  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_business}', '[]'::jsonb))
      AS x(cofre_ativo_id text, business_external_id text, nome_observado text, observado_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_business
      (cofre_ativo_id, business_external_id, nome_observado, observado_em)
    SELECT cofre_ativo_id, business_external_id, nome_observado, observado_em FROM entrada
    ON CONFLICT (cofre_ativo_id) DO UPDATE
       SET nome_observado = EXCLUDED.nome_observado,
           observado_em   = EXCLUDED.observado_em,
           atualizado_em  = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_business.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_business', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad_account}', '[]'::jsonb))
      AS x(cofre_ativo_id text, business_ativo_id text, account_external_id text,
           nome_observado text, moeda text, timezone_name text, account_status text,
           readiness_state text, observado_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_ad_account
      (cofre_ativo_id, business_ativo_id, credential_ativo_id, account_external_id,
       nome_observado, moeda, timezone_name, account_status, readiness_state,
       observado_em, ultima_leitura_ok_em)
    -- ⚠️ `v_credencial`, nunca `x.credential_ativo_id`: a coluna e FK de
    -- identidade e ela e resolvida no servidor (7.4).
    SELECT cofre_ativo_id, business_ativo_id, v_credencial, account_external_id,
           nome_observado, moeda, timezone_name, account_status, readiness_state,
           observado_em, observado_em
      FROM entrada
    ON CONFLICT (cofre_ativo_id) DO UPDATE
       SET nome_observado       = EXCLUDED.nome_observado,
           moeda                = EXCLUDED.moeda,
           timezone_name        = EXCLUDED.timezone_name,
           account_status       = EXCLUDED.account_status,
           readiness_state      = EXCLUDED.readiness_state,
           observado_em         = EXCLUDED.observado_em,
           ultima_leitura_ok_em = EXCLUDED.ultima_leitura_ok_em,
           atualizado_em        = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_ad_account.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_ad_account', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_campaign}', '[]'::jsonb))
      AS x(meta_campaign_id uuid, ad_account_ativo_id text, external_id text, nome text,
           status text, effective_status text, objetivo text,
           observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_campaign
      (meta_campaign_id, ad_account_ativo_id, external_id, nome, status,
       effective_status, objetivo, observado_em, ultima_vez_visto_em)
    SELECT meta_campaign_id, ad_account_ativo_id, external_id, nome, status,
           effective_status, objetivo, observado_em, ultima_vez_visto_em FROM entrada
    ON CONFLICT (ad_account_ativo_id, external_id) DO UPDATE
       SET nome                = EXCLUDED.nome,
           status              = EXCLUDED.status,
           effective_status    = EXCLUDED.effective_status,
           objetivo            = EXCLUDED.objetivo,
           observado_em        = EXCLUDED.observado_em,
           ultima_vez_visto_em = EXCLUDED.ultima_vez_visto_em,
           ausente_desde       = NULL,
           ausencia_causa      = NULL,
           atualizado_em       = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_campaign.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_campaign', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_adset}', '[]'::jsonb))
      AS x(meta_adset_id uuid, meta_campaign_id uuid, external_id text, nome text,
           status text, effective_status text, optimization_goal text,
           observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_adset
      (meta_adset_id, meta_campaign_id, external_id, nome, status,
       effective_status, optimization_goal, observado_em, ultima_vez_visto_em)
    SELECT meta_adset_id, meta_campaign_id, external_id, nome, status,
           effective_status, optimization_goal, observado_em, ultima_vez_visto_em FROM entrada
    ON CONFLICT (meta_campaign_id, external_id) DO UPDATE
       SET nome                = EXCLUDED.nome,
           status              = EXCLUDED.status,
           effective_status    = EXCLUDED.effective_status,
           optimization_goal   = EXCLUDED.optimization_goal,
           observado_em        = EXCLUDED.observado_em,
           ultima_vez_visto_em = EXCLUDED.ultima_vez_visto_em,
           ausente_desde       = NULL,
           ausencia_causa      = NULL,
           atualizado_em       = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_adset.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_adset', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_creative}', '[]'::jsonb))
      AS x(meta_creative_id uuid, ad_account_ativo_id text, external_id text, nome text,
           object_story_id text, observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_creative
      (meta_creative_id, ad_account_ativo_id, external_id, nome, object_story_id,
       observado_em, ultima_vez_visto_em)
    SELECT meta_creative_id, ad_account_ativo_id, external_id, nome, object_story_id,
           observado_em, ultima_vez_visto_em FROM entrada
    ON CONFLICT (ad_account_ativo_id, external_id) DO UPDATE
       SET nome                = EXCLUDED.nome,
           object_story_id     = EXCLUDED.object_story_id,
           observado_em        = EXCLUDED.observado_em,
           ultima_vez_visto_em = EXCLUDED.ultima_vez_visto_em,
           ausente_desde       = NULL,
           ausencia_causa      = NULL,
           atualizado_em       = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_creative.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_creative', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad}', '[]'::jsonb))
      AS x(meta_ad_id uuid, meta_adset_id uuid, external_id text, nome text,
           status text, effective_status text,
           observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_ad
      (meta_ad_id, meta_adset_id, external_id, nome, status, effective_status,
       observado_em, ultima_vez_visto_em)
    SELECT meta_ad_id, meta_adset_id, external_id, nome, status, effective_status,
           observado_em, ultima_vez_visto_em FROM entrada
    ON CONFLICT (meta_adset_id, external_id) DO UPDATE
       SET nome                = EXCLUDED.nome,
           status              = EXCLUDED.status,
           effective_status    = EXCLUDED.effective_status,
           observado_em        = EXCLUDED.observado_em,
           ultima_vez_visto_em = EXCLUDED.ultima_vez_visto_em,
           ausente_desde       = NULL,
           ausencia_causa      = NULL,
           atualizado_em       = now()
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_ad.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_ad', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad_creative_binding}', '[]'::jsonb))
      AS x(meta_ad_id uuid, meta_creative_id uuid, observado_em timestamptz)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_ad_creative_binding (meta_ad_id, meta_creative_id, observado_em)
    SELECT meta_ad_id, meta_creative_id, observado_em FROM entrada
    ON CONFLICT (meta_ad_id, meta_creative_id) DO UPDATE
       SET observado_em   = EXCLUDED.observado_em,
           ausente_desde  = NULL,
           ausencia_causa = NULL
     WHERE EXCLUDED.observado_em >= coalesce(trafego_meta_ad_creative_binding.observado_em, '-infinity'::timestamptz)
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_ad_creative_binding', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  -- ---------------------------------------------------------------------
  -- 7.7 AUSENCIA, e SO com leitura completa (defeito 1)
  -- ---------------------------------------------------------------------
  -- Marca o que a conta parou de mostrar: linha que existia, nao veio neste
  -- snapshot, e cujo `ultima_vez_visto_em` e ANTERIOR a este instante. O escopo
  -- e a conta lida, nunca o banco inteiro. `ausente_desde IS NULL` preserva o
  -- PRIMEIRO instante de ausencia — remarcar toda leitura apagaria ha quanto
  -- tempo o objeto sumiu.
  -- ⚠️ `v_escopo = 'hierarchy'` ENTROU NA GUARDA, e sem ele a migration teria
  -- aberto um buraco: uma pagina de insights que declarasse completude
  -- passaria a marcar como AUSENTE toda campanha cujo `ultima_vez_visto_em`
  -- fosse anterior ao instante da leitura — ou seja, o inventario inteiro,
  -- a partir de uma leitura que nunca listou campanha nenhuma.
  IF v_completo AND v_escopo = 'hierarchy' THEN
    UPDATE public.trafego_meta_campaign c
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada', atualizado_em = now()
     WHERE c.ad_account_ativo_id = v_account_asset
       AND c.ausente_desde IS NULL
       AND c.ultima_vez_visto_em < v_observed;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_campaign', v_n);
    v_ausencias_total := v_ausencias_total + v_n;

    UPDATE public.trafego_meta_adset s
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada', atualizado_em = now()
     WHERE s.ausente_desde IS NULL
       AND s.ultima_vez_visto_em < v_observed
       AND EXISTS (SELECT 1 FROM public.trafego_meta_campaign c
                    WHERE c.meta_campaign_id = s.meta_campaign_id
                      AND c.ad_account_ativo_id = v_account_asset);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_adset', v_n);
    v_ausencias_total := v_ausencias_total + v_n;

    UPDATE public.trafego_meta_ad a
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada', atualizado_em = now()
     WHERE a.ausente_desde IS NULL
       AND a.ultima_vez_visto_em < v_observed
       AND EXISTS (SELECT 1
                     FROM public.trafego_meta_adset s
                     JOIN public.trafego_meta_campaign c ON c.meta_campaign_id = s.meta_campaign_id
                    WHERE s.meta_adset_id = a.meta_adset_id
                      AND c.ad_account_ativo_id = v_account_asset);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_ad', v_n);
    v_ausencias_total := v_ausencias_total + v_n;

    UPDATE public.trafego_meta_creative cr
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada', atualizado_em = now()
     WHERE cr.ad_account_ativo_id = v_account_asset
       AND cr.ausente_desde IS NULL
       AND cr.ultima_vez_visto_em < v_observed;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_creative', v_n);
    v_ausencias_total := v_ausencias_total + v_n;

    UPDATE public.trafego_meta_ad_creative_binding b
       SET ausente_desde = v_observed, ausencia_causa = 'nao_encontrada'
     WHERE b.ausente_desde IS NULL
       AND b.observado_em < v_observed
       AND EXISTS (SELECT 1
                     FROM public.trafego_meta_ad a
                     JOIN public.trafego_meta_adset s ON s.meta_adset_id = a.meta_adset_id
                     JOIN public.trafego_meta_campaign c ON c.meta_campaign_id = s.meta_campaign_id
                    WHERE a.meta_ad_id = b.meta_ad_id
                      AND c.ad_account_ativo_id = v_account_asset);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_ausencias := v_ausencias || jsonb_build_object('trafego_meta_ad_creative_binding', v_n);
    v_ausencias_total := v_ausencias_total + v_n;
  END IF;

  -- ---------------------------------------------------------------------
  -- 7.8 INSIGHTS — grao completo, moeda e fuso CARIMBADOS (defeito 5)
  -- ---------------------------------------------------------------------
  -- A conta acabou de ser gravada acima; ler dela agora e ler o retrato DESTE
  -- snapshot. O valor e copiado para dentro do fato, e nao consultado por join
  -- na hora do relatorio: uma edicao futura da conta nao pode reescrever o que
  -- ja foi medido.
  SELECT moeda, timezone_name INTO v_moeda, v_fuso
    FROM public.trafego_meta_ad_account
   WHERE cofre_ativo_id = v_account_asset;

  WITH entrada AS (
    SELECT * FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_daily}', '[]'::jsonb))
      AS x(meta_insight_daily_id text, ad_account_ativo_id text, provider text,
           conta_externa text, nivel text, objeto_externo text,
           periodo_inicio date, periodo_fim date, janela_atribuicao text, breakdown text,
           observado_em timestamptz, spend numeric, impressions bigint, reach bigint,
           frequency numeric, clicks bigint, inline_link_clicks bigint,
           landing_page_views bigint, cpm numeric, cpc numeric, ctr numeric,
           time_increment text, action_report_time text, account_timezone text,
           currency text, completo boolean)
  ), gravadas AS (
    INSERT INTO public.trafego_meta_insight_daily
      (meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel,
       objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao, breakdown,
       observado_em, spend, impressions, reach, frequency, clicks, inline_link_clicks,
       landing_page_views, cpm, cpc, ctr,
       time_increment, action_report_time, account_timezone, currency, completo)
    SELECT meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel,
           objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao, breakdown,
           observado_em, spend, impressions, reach, frequency, clicks, inline_link_clicks,
           landing_page_views, cpm, cpc, ctr,
           coalesce(time_increment, '1'),
           coalesce(action_report_time, 'impression'),
           coalesce(account_timezone, v_fuso),
           coalesce(currency, v_moeda),
           -- Omitir a completude da LINHA nao pode significar "completa": a
           -- transacao ja sabe, por `hierarchy_complete`, que esta leitura foi
           -- truncada. Herdar `v_completo` diz a verdade; `true` inventaria a
           -- mesma ausencia que a RPC acabou de recusar la em cima.
           coalesce(completo, v_completo)
      FROM entrada
    ON CONFLICT (meta_insight_daily_id) DO UPDATE
       SET spend              = EXCLUDED.spend,
           impressions        = EXCLUDED.impressions,
           reach              = EXCLUDED.reach,
           frequency          = EXCLUDED.frequency,
           clicks             = EXCLUDED.clicks,
           inline_link_clicks = EXCLUDED.inline_link_clicks,
           landing_page_views = EXCLUDED.landing_page_views,
           cpm                = EXCLUDED.cpm,
           cpc                = EXCLUDED.cpc,
           ctr                = EXCLUDED.ctr,
           time_increment     = EXCLUDED.time_increment,
           action_report_time = EXCLUDED.action_report_time,
           account_timezone   = EXCLUDED.account_timezone,
           currency           = EXCLUDED.currency,
           completo           = EXCLUDED.completo
     WHERE EXCLUDED.observado_em >= trafego_meta_insight_daily.observado_em
    RETURNING 1
  )
  SELECT (SELECT count(*) FROM entrada), (SELECT count(*) FROM gravadas)
    INTO v_entradas, v_gravadas;
  v_recusadas := v_recusadas || jsonb_build_object('trafego_meta_insight_daily', v_entradas - v_gravadas);
  v_recusadas_total := v_recusadas_total + (v_entradas - v_gravadas);

  -- A PK (fato, ordem) separa duas acoes, mas nao impede que uma linha de
  -- `action_values` seja numerada por cima de uma de `actions` e a substitua em
  -- silencio — o mesmo `ordem` com outra identidade. As duas recusas abaixo
  -- transformam esse caso num erro alto em vez de numa contagem perdida.
  IF EXISTS (
    SELECT 1
      FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_action}', '[]'::jsonb))
        AS x(meta_insight_daily_id text, ordem integer)
     GROUP BY x.meta_insight_daily_id, x.ordem
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION
      'META_ACTION_ORDEM_DUPLICADA: duas acoes do mesmo fato com a mesma ordem no payload; numere actions e action_values numa sequencia unica';
  END IF;
  IF EXISTS (
    SELECT 1
      FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_action}', '[]'::jsonb))
        AS x(meta_insight_daily_id text, ordem integer, action_type text,
             attribution_window text, medida text)
      JOIN public.trafego_meta_insight_action a
        ON a.meta_insight_daily_id = x.meta_insight_daily_id AND a.ordem = x.ordem
     WHERE (a.action_type, a.attribution_window, a.medida)
        IS DISTINCT FROM (x.action_type, x.attribution_window, coalesce(x.medida, 'count'))
  ) THEN
    RAISE EXCEPTION
      'META_ACTION_ORDEM_COLIDE: a ordem recebida reinterpretaria uma acao ja gravada com outra identidade; corrija a numeracao em vez de sobrescrever';
  END IF;

  INSERT INTO public.trafego_meta_insight_action
    (meta_insight_daily_id, ordem, action_type, value, attribution_window,
     object_level, date_start, date_stop, medida)
  SELECT meta_insight_daily_id, ordem, action_type, value, attribution_window,
         object_level, date_start, date_stop, coalesce(medida, 'count')
    FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_action}', '[]'::jsonb))
      AS x(meta_insight_daily_id text, ordem integer, action_type text, value numeric,
           attribution_window text, object_level text, date_start date, date_stop date,
           medida text)
  ON CONFLICT (meta_insight_daily_id, ordem) DO UPDATE
     SET value      = EXCLUDED.value,
         date_start = EXCLUDED.date_start,
         date_stop  = EXCLUDED.date_stop,
         object_level = EXCLUDED.object_level;

  INSERT INTO public.trafego_meta_custom_measurement
    (ad_account_ativo_id, measurement_type, observed_count, observado_em, snapshot_hash)
  SELECT ad_account_ativo_id, measurement_type, observed_count, observado_em, snapshot_hash
    FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_custom_measurement}', '[]'::jsonb))
      AS x(ad_account_ativo_id text, measurement_type text, observed_count integer,
           observado_em timestamptz, snapshot_hash text)
  -- Sem guarda de monotonicidade aqui de proposito: `observado_em` faz parte da
  -- PK desta tabela, entao conflito so acontece com o MESMO instante — que e
  -- retry, nao regressao.
  ON CONFLICT (ad_account_ativo_id, measurement_type, observado_em) DO UPDATE
     SET observed_count = EXCLUDED.observed_count,
         snapshot_hash  = EXCLUDED.snapshot_hash;

  -- ---------------------------------------------------------------------
  -- 7.9 RECIBO
  -- ---------------------------------------------------------------------
  v_parcialidade := coalesce(p_snapshot->'partiality', '[]'::jsonb);
  IF jsonb_typeof(v_parcialidade) <> 'array' THEN
    v_parcialidade := '[]'::jsonb;
  END IF;
  -- A nota so descreve a verdade no escopo em que marcar ausencia era uma
  -- possibilidade. Carimbar 'ausencia_nao_marcada' num snapshot de insights
  -- sugeriria que algo deixou de ser feito; nada deixou — nunca esteve em
  -- questao. As parcialidades proprias do produtor ja chegam em `partiality`.
  IF NOT v_completo AND v_escopo = 'hierarchy' THEN
    v_parcialidade := v_parcialidade || jsonb_build_array(
      jsonb_build_object('escopo', v_escopo, 'efeito', 'ausencia_nao_marcada'));
  END IF;

  INSERT INTO public.trafego_meta_sync_run
    (run_id, ad_account_ativo_id, chave_de_idempotencia, escopo, resultado,
     iniciado_em, concluido_em, paginas_lidas, contagens, cursor_final,
     snapshot_hash, escrita_executada, parcialidade)
  VALUES (
    v_run, v_account_asset, v_chave, v_escopo, 'ok',
    v_observed, clock_timestamp(),
    coalesce((p_snapshot->>'page_count')::int, 0),
    coalesce(p_snapshot->'counts', '{}'::jsonb),
    jsonb_build_object(
      'window', v_window,
      'chave_origem', v_origem_chave,
      'chave_volatil', v_chave_volatil,
      'leitura_completa', v_completo,
      'recusadas_por_desatualizacao', v_recusadas,
      'ausencias_marcadas', v_ausencias),
    v_snapshot_hash, true, v_parcialidade);

  RETURN jsonb_build_object(
    'ok', true, 'repetido', false, 'run_id', v_run::text,
    'escopo', v_escopo,
    'chave_origem', v_origem_chave,
    'leitura_completa', v_completo,
    'recusadas_por_desatualizacao', v_recusadas_total,
    'recusadas_por_tabela', v_recusadas,
    'ausencias_marcadas', v_ausencias_total,
    'ausencias_por_tabela', v_ausencias);

EXCEPTION WHEN unique_violation THEN
  -- Corrida de duas execucoes com a MESMA chave. So e replay se houver um run
  -- 'ok' gravado com ela; qualquer outra unique_violation continua sendo erro e
  -- sobe.
  SELECT run_id INTO v_anterior
    FROM public.trafego_meta_sync_run
   WHERE chave_de_idempotencia = v_chave AND resultado = 'ok'
   ORDER BY concluido_em DESC LIMIT 1;
  IF v_anterior IS NOT NULL THEN
    RETURN jsonb_build_object(
      'ok', true, 'repetido', true, 'run_id', v_anterior::text,
      'escopo', v_escopo,
      'chave_origem', v_origem_chave,
      'leitura_completa', v_completo,
      'recusadas_por_desatualizacao', 0,
      'recusadas_por_tabela', '{}'::jsonb,
      'ausencias_marcadas', 0,
      'ausencias_por_tabela', '{}'::jsonb);
  END IF;
  RAISE;
END;
$$;

COMMENT ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) IS
  'Escrita unica e transacional do snapshot Meta. Le `escopo` do envelope (hierarchy | insights_pagina | insights_fechamento; DEFAULT hierarchy). Exige hierarchy_complete (boolean) SO no escopo hierarchy, porque so ele marca ausencia; exige account_asset_id em todo escopo menos insights_fechamento, que e recibo de execucao; aceita stable_idempotency_key (sem o instante) para deduplicar; recusa snapshot mais velho que o gravado e diz no recibo quantas linhas recusou; resolve credential_asset_id no servidor; registra ativos no Cofre pelo escritor governado com dono_custodia=declared.';

-- ⚠️ AS PERMISSOES SAO REAFIRMADAS DE PROPOSITO. `CREATE OR REPLACE FUNCTION`
-- preserva os privilegios de uma funcao que ja existia — mas se ela NAO existir
-- (banco novo, ambiente recriado), ela nasce com EXECUTE para PUBLIC. Repetir o
-- REVOKE/GRANT faz esta migration ser segura nos dois casos, em vez de depender
-- de o ambiente ter recebido a migration anterior.
REVOKE ALL ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) FROM anon;
REVOKE ALL ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) TO service_role;

COMMIT;

-- =============================================================================
-- ROLLBACK
-- =============================================================================
-- ⚠️ ESTE PACOTE NAO CRIOU UM ARQUIVO `..._rollback.sql` SEPARADO — a tarefa que
-- o produziu tinha autorizacao de escrita para ESTE arquivo e nao para outro.
-- Entao a reversao fica aqui, escrita e conferivel, em vez de ficar implicita.
--
-- ⚠️ E ELA SO E SEGURA ENQUANTO NAO HOUVER LINHA NOS ESCOPOS NOVOS. Voltar o
-- CHECK para `escopo = 'hierarchy'` com uma unica linha `insights_pagina` gravada
-- faz o `ADD CONSTRAINT` falhar — e isso e o comportamento certo: a alternativa
-- seria apagar recibo de leitura que aconteceu. Se houver linha nos escopos
-- novos, a decisao e humana (arquivar? migrar?), nao de um script.
--
-- BEGIN;
--   ALTER TABLE public.trafego_meta_sync_run
--     DROP CONSTRAINT IF EXISTS trafego_meta_sync_conta_por_escopo;
--   ALTER TABLE public.trafego_meta_sync_run
--     ALTER COLUMN ad_account_ativo_id SET NOT NULL;
--   ALTER TABLE public.trafego_meta_sync_run
--     DROP CONSTRAINT IF EXISTS trafego_meta_sync_escopo_conhecido;
--   ALTER TABLE public.trafego_meta_sync_run
--     ADD CONSTRAINT trafego_meta_sync_escopo_conhecido CHECK (escopo = 'hierarchy');
--   -- E reaplicar, na integra, a funcao de
--   -- supabase/migrations/20260907210000_meta_read_model_consistency.sql:657-1249.
-- COMMIT;
