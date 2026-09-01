-- Provas de COMPORTAMENTO da v12_02, em SQL e não em bash.
--
-- ⚠️ Em SQL de propósito. A primeira versão das provas da v11_03 vivia dentro de
-- `eval` com aspas em três níveis; a primeira inserção falhava por quoting e
-- todas as seguintes cascateavam. Um arranjo de prova que falha por si mesmo não
-- mede nada.
--
-- Cada bloco tenta gravar UM plano e afirma se ele devia entrar ou ser recusado.
-- A escrita passa sempre pela função — que é a única porta — porque é isso que
-- o `service_role` de produção pode fazer.

\set ON_ERROR_STOP 0
\pset tuples_only on
\pset format unaligned

-- Um plano-base VÁLIDO e INCOMPLETO: é o caso normal do nascimento.
create or replace function pg_temp.doc(patch jsonb default '{}'::jsonb)
returns jsonb language sql as $$
  select jsonb_build_object(
    'impressao', repeat('a', 64),
    'versao', 1,
    'customer_id', '5478096539',
    'login_customer_id', '6016739364',
    'campaign_id', null,
    'nivel', 'CUSTOMER',
    'nivel_estado', 'com_dados',
    'metas_da_conta_estado', 'com_dados',
    'metas_da_campanha_estado', 'inelegivel',
    'metas_biddable', jsonb_build_array('DOWNLOAD/APP'),
    'meta_resolvida', true,
    'acoes_estado', 'com_dados',
    'acao_alvo_id', null,
    'acao_alvo_causa', 'a unica acao que mede este objetivo nao e primaria',
    'destino_resolvido', false,
    'destino_causa', 'nenhuma acao eleita',
    'frescor_estado', 'inelegivel',
    'marcacao_estado', 'com_dados',
    'auto_tagging', true,
    'completo', false,
    'bloqueadores', jsonb_build_array('a unica acao que mede este objetivo nao e primaria'),
    'payload', '{}'::jsonb,
    'api_versao', 'v25',
    'lido_em', '2026-09-01T12:00:00Z'
  ) || patch
$$;

create or replace function pg_temp.tenta(nome text, patch jsonb, deve_passar boolean)
returns void language plpgsql as $$
declare
    r uuid;
begin
    begin
        select public.volc_registrar_plano_de_mensuracao(pg_temp.doc(patch)) into r;
        if deve_passar then
            raise notice '  ok   %', nome;
        else
            raise notice 'FALHOU  % (foi aceito e devia ser recusado)', nome;
        end if;
    exception when others then
        if deve_passar then
            raise notice 'FALHOU  % (recusado: %)', nome, sqlerrm;
        else
            raise notice '  ok   %', nome;
        end if;
    end;
end;
$$;

do $$
begin
  -- ── o caso normal ────────────────────────────────────────────────────────
  perform pg_temp.tenta(
    'plano do NASCIMENTO grava com campaign_id nulo',
    '{}'::jsonb, true);

  -- ── idempotência pela impressão ──────────────────────────────────────────
  perform pg_temp.tenta(
    'a MESMA impressao gravada de novo nao cria segunda linha',
    '{}'::jsonb, true);
end $$;

do $$
declare n integer;
begin
  select count(*) into n from public.trafego_campanha_plano_de_mensuracao;
  if n = 1 then raise notice '  ok   idempotencia: 1 linha depois de duas gravacoes';
  else raise notice 'FALHOU  idempotencia: % linhas', n; end if;
end $$;

do $$
begin
  -- ── INVARIANTE 1: destino por dono + id numérico, nunca por nome ─────────
  perform pg_temp.tenta(
    'INV1 destino resolvido SEM conta dona e recusado',
    '{"impressao":"b0000000000000000000000000000000000000000000000000000000000000b0",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "destino_resolvido":true,"destino_product_destination_id":"7498530235",
      "destino_causa":null,"frescor_estado":"com_dados",
      "frescor_ultima_em":"2026-08-30","frescor_conversoes":1,
      "completo":false,"bloqueadores":["x"]}'::jsonb, false);

  perform pg_temp.tenta(
    'INV1 destino resolvido SEM id de destino (nulo) e recusado',
    '{"impressao":"b4000000000000000000000000000000000000000000000000000000000000b4",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_causa":null,"frescor_estado":"com_dados",
      "frescor_ultima_em":"2026-08-30","frescor_conversoes":1,
      "completo":false,"bloqueadores":["x"]}'::jsonb, false);

  perform pg_temp.tenta(
    'INV1 destino resolvido com NOME no lugar do id e recusado',
    '{"impressao":"b1000000000000000000000000000000000000000000000000000000000000b1",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_product_destination_id":"Compra no site","destino_causa":null,
      "frescor_estado":"com_dados","frescor_ultima_em":"2026-08-30",
      "frescor_conversoes":1,"completo":false,"bloqueadores":["x"]}'::jsonb, false);

  perform pg_temp.tenta(
    'INV1 destino resolvido apontando para OUTRA acao e recusado',
    '{"impressao":"b2000000000000000000000000000000000000000000000000000000000000b2",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_product_destination_id":"9999999999","destino_causa":null,
      "frescor_estado":"com_dados","frescor_ultima_em":"2026-08-30",
      "frescor_conversoes":1,"completo":false,"bloqueadores":["x"]}'::jsonb, false);

  perform pg_temp.tenta(
    'INV1 destino nao resolvido SEM causa e recusado',
    '{"impressao":"b3000000000000000000000000000000000000000000000000000000000000b3",
      "destino_resolvido":false,"destino_causa":null}'::jsonb, false);

  -- ── INVARIANTE 2: ação XOR causa ─────────────────────────────────────────
  perform pg_temp.tenta(
    'INV2 acao eleita E causa ao mesmo tempo e recusado',
    '{"impressao":"c0000000000000000000000000000000000000000000000000000000000000c0",
      "acao_alvo_id":"7498530235",
      "acao_alvo_causa":"nao elegi"}'::jsonb, false);

  perform pg_temp.tenta(
    'INV2 sem acao e sem causa e recusado',
    '{"impressao":"c1000000000000000000000000000000000000000000000000000000000000c1",
      "acao_alvo_id":null,"acao_alvo_causa":null}'::jsonb, false);

  -- ── INVARIANTE 3: completo exige as provas ───────────────────────────────
  perform pg_temp.tenta(
    'INV3 completo SEM acao eleita e recusado',
    '{"impressao":"d0000000000000000000000000000000000000000000000000000000000000d0",
      "completo":true,"bloqueadores":[]}'::jsonb, false);

  perform pg_temp.tenta(
    'INV3 completo com acao e SEM destino resolvido e recusado',
    '{"impressao":"d1000000000000000000000000000000000000000000000000000000000000d1",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "destino_resolvido":false,"destino_causa":"tipo nao aceito",
      "frescor_estado":"com_dados","frescor_ultima_em":"2026-08-30",
      "frescor_conversoes":1,"completo":true,"bloqueadores":[]}'::jsonb, false);

  perform pg_temp.tenta(
    'INV3 completo com frescor VAZIO_CONFIRMADO e recusado',
    '{"impressao":"d2000000000000000000000000000000000000000000000000000000000000d2",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_product_destination_id":"7498530235","destino_causa":null,
      "frescor_estado":"vazio_confirmado","frescor_conversoes":0,
      "completo":true,"bloqueadores":[]}'::jsonb, false);

  perform pg_temp.tenta(
    'INV3 completo COM as tres provas e ACEITO',
    '{"impressao":"d3000000000000000000000000000000000000000000000000000000000000d3",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "acao_alvo_owner_id":"5478096539","acao_alvo_tipo":"WEBPAGE",
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_product_destination_id":"7498530235","destino_causa":null,
      "frescor_estado":"com_dados","frescor_ultima_em":"2026-08-30",
      "frescor_dias":2,"frescor_conversoes":14,
      "completo":true,"bloqueadores":[]}'::jsonb, true);

  -- ── INVARIANTE 4: bloqueador ou completude ───────────────────────────────
  perform pg_temp.tenta(
    'INV4 plano incompleto SEM bloqueador e recusado',
    '{"impressao":"e0000000000000000000000000000000000000000000000000000000000000e0",
      "completo":false,"bloqueadores":[]}'::jsonb, false);

  -- ── INVARIANTE 5: leitura sem conclusão não carrega número ───────────────
  perform pg_temp.tenta(
    'INV5 frescor FALHOU com contagem e recusado',
    '{"impressao":"f0000000000000000000000000000000000000000000000000000000000000f0",
      "frescor_estado":"falhou","frescor_conversoes":0}'::jsonb, false);

  perform pg_temp.tenta(
    'INV5 frescor NAO_COLETADO com data e recusado',
    '{"impressao":"f1000000000000000000000000000000000000000000000000000000000000f1",
      "frescor_estado":"nao_coletado","frescor_ultima_em":"2026-08-30"}'::jsonb, false);

  perform pg_temp.tenta(
    'INV5 frescor VAZIO_CONFIRMADO com zero MEDIDO e aceito',
    '{"impressao":"f2000000000000000000000000000000000000000000000000000000000000f2",
      "frescor_estado":"vazio_confirmado","frescor_conversoes":0}'::jsonb, true);

  -- ⚠️ Esta prova nasceu DEPOIS do defeito. A anterior mandava
  -- `frescor_conversoes: 0` explicitamente e por isso nunca exercia o caminho em
  -- que a coluna é nula — que era exatamente o caminho em que o CHECK valia NULL
  -- e deixava passar.
  perform pg_temp.tenta(
    'INV5 frescor VAZIO_CONFIRMADO SEM contagem (nula) e recusado',
    '{"impressao":"f4000000000000000000000000000000000000000000000000000000000000f4",
      "frescor_estado":"vazio_confirmado"}'::jsonb, false);

  perform pg_temp.tenta(
    'INV5 frescor VAZIO_CONFIRMADO com data de ultima conversao e recusado',
    '{"impressao":"f3000000000000000000000000000000000000000000000000000000000000f3",
      "frescor_estado":"vazio_confirmado","frescor_conversoes":0,
      "frescor_ultima_em":"2026-08-30"}'::jsonb, false);

  -- ── INVARIANTE 6: campanha que não nasceu não tem meta de campanha ───────
  perform pg_temp.tenta(
    'INV6 campaign_id nulo com metas_da_campanha COM_DADOS e recusado',
    '{"impressao":"a0000000000000000000000000000000000000000000000000000000000000a0",
      "campaign_id":null,"metas_da_campanha_estado":"com_dados"}'::jsonb, false);

  perform pg_temp.tenta(
    'INV6 campanha nascida PODE ter meta de campanha',
    '{"impressao":"a1000000000000000000000000000000000000000000000000000000000000a1",
      "campaign_id":"24195821946","metas_da_campanha_estado":"com_dados"}'::jsonb, true);

  -- ── nivel: UNKNOWN nao vira CUSTOMER ─────────────────────────────────────
  perform pg_temp.tenta(
    'nivel fora do enum v25 e recusado',
    '{"impressao":"a2000000000000000000000000000000000000000000000000000000000000a2",
      "nivel":"CONTA","nivel_estado":"com_dados"}'::jsonb, false);

  perform pg_temp.tenta(
    'nivel lido COM_DADOS e nulo ao mesmo tempo e recusado',
    '{"impressao":"a3000000000000000000000000000000000000000000000000000000000000a3",
      "nivel":null,"nivel_estado":"com_dados"}'::jsonb, false);

  perform pg_temp.tenta(
    'nivel UNKNOWN e gravavel e NAO vira CUSTOMER',
    '{"impressao":"a4000000000000000000000000000000000000000000000000000000000000a4",
      "nivel":"UNKNOWN","nivel_estado":"com_dados"}'::jsonb, true);

  -- ── conta: id de conta com forma errada ──────────────────────────────────
  perform pg_temp.tenta(
    'customer_id nao numerico e recusado',
    '{"impressao":"a5000000000000000000000000000000000000000000000000000000000000a5",
      "customer_id":"portal-mundo-mais"}'::jsonb, false);
end $$;

-- ── append-only ─────────────────────────────────────────────────────────────
do $$
begin
    begin
        update public.trafego_campanha_plano_de_mensuracao
           set completo = true where impressao = repeat('a', 64);
        raise notice 'FALHOU  append-only: UPDATE foi aceito';
    exception when others then
        raise notice '  ok   append-only: UPDATE recusado (%)', sqlstate;
    end;
    begin
        delete from public.trafego_campanha_plano_de_mensuracao
         where impressao = repeat('a', 64);
        raise notice 'FALHOU  append-only: DELETE foi aceito';
    exception when others then
        raise notice '  ok   append-only: DELETE recusado (%)', sqlstate;
    end;
end $$;

-- ── o nivel UNKNOWN sobreviveu como UNKNOWN ────────────────────────────────
do $$
declare v text;
begin
    select nivel into v from public.trafego_campanha_plano_de_mensuracao
     where impressao = 'a4000000000000000000000000000000000000000000000000000000000000a4';
    if v = 'UNKNOWN' then raise notice '  ok   UNKNOWN persistiu como UNKNOWN, e nao como CUSTOMER';
    else raise notice 'FALHOU  UNKNOWN virou %', coalesce(v, '<null>'); end if;
end $$;
