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

-- ⚠️ ESTA FUNÇÃO JÁ ACEITOU QUALQUER ERRO, e a revisão adversarial provou:
-- trocando `pg_temp.doc` por `pg_temp.doc_TYPO` dentro dela, 14 dos 22 casos
-- continuavam imprimindo `ok`, com a mensagem "function does not exist"
-- engolida pelo `exception when others`. As provas de comportamento passavam
-- sem NADA ter sido enviado à função sob teste.
--
-- Agora ela exige `check_violation` (23514) — o SQLSTATE que uma guarda do
-- schema levanta — e o NOME da constraint que recusou. Qualquer outro erro é
-- defeito da própria prova, e ele grita em vez de virar `ok`. E `esperada`
-- amarra cada caso à guarda que ele diz exercer: sem isso, um caso podia ser
-- recusado por OUTRA constraint e a guarda nomeada continuar removível sem que
-- nada acusasse — foi exatamente o que aconteceu com o id numérico do destino.
create or replace function pg_temp.tenta(nome text, patch jsonb,
                                         deve_passar boolean,
                                         esperada text default null)
returns void language plpgsql as $$
declare
    r uuid;
    quem text;
begin
    begin
        select public.volc_registrar_plano_de_mensuracao(pg_temp.doc(patch)) into r;
        if deve_passar then
            raise notice '  ok   %', nome;
        else
            raise notice 'FALHOU  % (foi aceito e devia ser recusado)', nome;
        end if;
    exception
        when check_violation then
            get stacked diagnostics quem = constraint_name;
            if deve_passar then
                raise notice 'FALHOU  % (recusado por %)', nome, quem;
            elsif esperada is not null and quem is distinct from esperada then
                raise notice 'FALHOU  % (recusado por % — a prova diz exercer %)',
                    nome, quem, esperada;
            else
                raise notice '  ok   % [%]', nome, coalesce(quem, '?');
            end if;
        when others then
            -- ⚠️ NUNCA `ok`. Um cast que explode, uma função inexistente ou uma
            -- chave malformada é defeito DA PROVA, e um arranjo de prova que
            -- falha por si mesmo não mede nada.
            raise notice 'FALHOU  % (a PROVA quebrou: % / %)', nome, sqlstate, sqlerrm;
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
      "completo":false,"bloqueadores":["x"]}'::jsonb, false,
    'trafego_plano_destino_e_do_dono_da_acao');

  perform pg_temp.tenta(
    'INV1 destino resolvido SEM id de destino (nulo) e recusado',
    '{"impressao":"b4000000000000000000000000000000000000000000000000000000000000b4",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_causa":null,"frescor_estado":"com_dados",
      "frescor_ultima_em":"2026-08-30","frescor_conversoes":1,
      "completo":false,"bloqueadores":["x"]}'::jsonb, false,
    'trafego_plano_destino_e_da_acao_eleita');

  -- ⚠️ Este caso é recusado por `destino_e_da_acao_eleita` (o id do destino tem
  -- de ser o da ação eleita), e NÃO pela guarda de id numérico. A revisão
  -- provou que a guarda numérica podia ser removida sem nada acusar — porque
  -- `acao_alvo_id ~ '^[0-9]+$'` já impede que a ação eleita tenha id não
  -- numérico, e o destino tem de ser igual a ele. A guarda numérica do destino
  -- é, portanto, REDUNDANTE hoje; ela fica como defesa em profundidade e este
  -- comentário existe para que ninguém a confunda com a prova do item 6.
  perform pg_temp.tenta(
    'INV1 destino com NOME e recusado (pela guarda da acao eleita)',
    '{"impressao":"b1000000000000000000000000000000000000000000000000000000000000b1",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_product_destination_id":"Compra no site","destino_causa":null,
      "frescor_estado":"com_dados","frescor_ultima_em":"2026-08-30",
      "frescor_conversoes":1,"completo":false,"bloqueadores":["x"]}'::jsonb, false,
    'trafego_plano_destino_e_da_acao_eleita');

  perform pg_temp.tenta(
    'INV1 destino resolvido apontando para OUTRA acao e recusado',
    '{"impressao":"b2000000000000000000000000000000000000000000000000000000000000b2",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_product_destination_id":"9999999999","destino_causa":null,
      "frescor_estado":"com_dados","frescor_ultima_em":"2026-08-30",
      "frescor_conversoes":1,"completo":false,"bloqueadores":["x"]}'::jsonb, false,
    'trafego_plano_destino_e_da_acao_eleita');

  perform pg_temp.tenta(
    'INV1 destino nao resolvido SEM causa e recusado',
    '{"impressao":"b3000000000000000000000000000000000000000000000000000000000000b3",
      "destino_resolvido":false,"destino_causa":null}'::jsonb, false,
    'trafego_plano_destino_por_dono_e_id');

  -- ── INVARIANTE 2: ação XOR causa ─────────────────────────────────────────
  perform pg_temp.tenta(
    'INV2 acao eleita E causa ao mesmo tempo e recusado',
    '{"impressao":"c0000000000000000000000000000000000000000000000000000000000000c0",
      "acao_alvo_id":"7498530235",
      "acao_alvo_causa":"nao elegi"}'::jsonb, false,
    'trafego_plano_acao_xor_causa');

  perform pg_temp.tenta(
    'INV2 sem acao e sem causa e recusado',
    '{"impressao":"c1000000000000000000000000000000000000000000000000000000000000c1",
      "acao_alvo_id":null,"acao_alvo_causa":null}'::jsonb, false,
    'trafego_plano_acao_xor_causa');

  -- ── INVARIANTE 3: completo exige as provas ───────────────────────────────
  perform pg_temp.tenta(
    'INV3 completo SEM acao eleita e recusado',
    '{"impressao":"d0000000000000000000000000000000000000000000000000000000000000d0",
      "completo":true,"bloqueadores":[]}'::jsonb, false,
    'trafego_plano_completo_exige_prova');

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
      "completo":true,"bloqueadores":[]}'::jsonb, false,
    'trafego_plano_completo_exige_prova');

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
      "completo":false,"bloqueadores":[]}'::jsonb, false,
    'trafego_plano_bloqueador_ou_completude');

  -- ── INVARIANTE 5: leitura sem conclusão não carrega número ───────────────
  perform pg_temp.tenta(
    'INV5 frescor FALHOU com contagem e recusado',
    '{"impressao":"f0000000000000000000000000000000000000000000000000000000000000f0",
      "frescor_estado":"falhou","frescor_conversoes":0}'::jsonb, false,
    'trafego_plano_frescor_sem_conclusao_nao_conta');

  perform pg_temp.tenta(
    'INV5 frescor NAO_COLETADO com data e recusado',
    '{"impressao":"f1000000000000000000000000000000000000000000000000000000000000f1",
      "frescor_estado":"nao_coletado","frescor_ultima_em":"2026-08-30"}'::jsonb, false,
    'trafego_plano_frescor_sem_conclusao_nao_conta');

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
      "frescor_estado":"vazio_confirmado"}'::jsonb, false,
    'trafego_plano_frescor_vazio_e_zero');

  perform pg_temp.tenta(
    'INV5 frescor VAZIO_CONFIRMADO com data de ultima conversao e recusado',
    '{"impressao":"f3000000000000000000000000000000000000000000000000000000000000f3",
      "frescor_estado":"vazio_confirmado","frescor_conversoes":0,
      "frescor_ultima_em":"2026-08-30"}'::jsonb, false,
    'trafego_plano_frescor_vazio_e_zero');

  -- ── INVARIANTE 6: campanha que não nasceu não tem meta de campanha ───────
  perform pg_temp.tenta(
    'INV6 campaign_id nulo com metas_da_campanha COM_DADOS e recusado',
    '{"impressao":"a0000000000000000000000000000000000000000000000000000000000000a0",
      "campaign_id":null,"metas_da_campanha_estado":"com_dados"}'::jsonb, false,
    'trafego_plano_campanha_inexistente_nao_tem_meta');

  perform pg_temp.tenta(
    'INV6 campanha nascida PODE ter meta de campanha',
    '{"impressao":"a1000000000000000000000000000000000000000000000000000000000000a1",
      "campaign_id":"24195821946","metas_da_campanha_estado":"com_dados"}'::jsonb, true);

  -- ── nivel: UNKNOWN nao vira CUSTOMER ─────────────────────────────────────
  perform pg_temp.tenta(
    'nivel fora do enum v25 e recusado',
    '{"impressao":"a2000000000000000000000000000000000000000000000000000000000000a2",
      "nivel":"CONTA","nivel_estado":"com_dados","meta_resolvida":false}'::jsonb, false,
    'trafego_plano_nivel');

  perform pg_temp.tenta(
    'nivel lido COM_DADOS e nulo ao mesmo tempo e recusado',
    '{"impressao":"a3000000000000000000000000000000000000000000000000000000000000a3",
      "nivel":null,"nivel_estado":"com_dados"}'::jsonb, false,
    'trafego_plano_nivel_lido');

  -- ⚠️ `meta_resolvida:false` de proposito. Com UNKNOWN, o nivel NAO decide, e
  -- o CHECK `meta_resolvida_exige_evidencia` recusa a linha que afirma o
  -- contrario — que e exatamente o que ele existe para fazer.
  perform pg_temp.tenta(
    'nivel UNKNOWN e gravavel e NAO vira CUSTOMER',
    '{"impressao":"a4000000000000000000000000000000000000000000000000000000000000a4",
      "nivel":"UNKNOWN","nivel_estado":"com_dados","meta_resolvida":false}'::jsonb, true);

  perform pg_temp.tenta(
    'meta_resolvida=true com nivel UNKNOWN e recusado',
    '{"impressao":"a6000000000000000000000000000000000000000000000000000000000000a6",
      "nivel":"UNKNOWN","nivel_estado":"com_dados","meta_resolvida":true}'::jsonb, false,
    'trafego_plano_meta_resolvida_exige_evidencia');

  perform pg_temp.tenta(
    'meta_resolvida=true com nivel_estado FALHOU e recusado',
    '{"impressao":"a7000000000000000000000000000000000000000000000000000000000000a7",
      "nivel":null,"nivel_estado":"falhou","meta_resolvida":true}'::jsonb, false,
    'trafego_plano_meta_resolvida_exige_evidencia');

  perform pg_temp.tenta(
    'meta_resolvida=true com metas_biddable VAZIO e recusado',
    '{"impressao":"a8000000000000000000000000000000000000000000000000000000000000a8",
      "metas_biddable":[],"meta_resolvida":true}'::jsonb, false,
    'trafego_plano_meta_resolvida_exige_evidencia');

  perform pg_temp.tenta(
    'meta_resolvida=true com meta CUSTOMIZADA ativa e recusado',
    '{"impressao":"a9000000000000000000000000000000000000000000000000000000000000a9",
      "custom_conversion_goal":"customers/1/customConversionGoals/9",
      "meta_resolvida":true}'::jsonb, false,
    'trafego_plano_meta_resolvida_exige_evidencia');

  -- ⚠️ O nivel HERDADO decide, e o LIDO tambem — os outros nao.
  perform pg_temp.tenta(
    'nivel HERDADO com estado inelegivel sustenta meta_resolvida',
    '{"impressao":"aa000000000000000000000000000000000000000000000000000000000000aa",
      "nivel":"CUSTOMER","nivel_estado":"inelegivel","nivel_herdado":true,
      "meta_resolvida":true}'::jsonb, true);

  perform pg_temp.tenta(
    'nivel inelegivel SEM herdado nao sustenta meta_resolvida',
    '{"impressao":"ab000000000000000000000000000000000000000000000000000000000000ab",
      "nivel":"CUSTOMER","nivel_estado":"inelegivel","nivel_herdado":false,
      "meta_resolvida":true}'::jsonb, false,
    'trafego_plano_meta_resolvida_exige_evidencia');

  -- ── INVARIANTE 1 (segunda metade): o destino e da conta DONA da acao ────
  perform pg_temp.tenta(
    'INV1 destino numa conta que NAO e a dona da acao e recusado',
    '{"impressao":"ba000000000000000000000000000000000000000000000000000000000000ba",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "acao_alvo_owner_id":"5478096539",
      "destino_resolvido":true,"destino_operating_account_id":"9999999999",
      "destino_product_destination_id":"7498530235","destino_causa":null,
      "frescor_estado":"com_dados","frescor_ultima_em":"2026-08-30",
      "frescor_dias":2,"frescor_conversoes":1,
      "completo":false,"bloqueadores":["x"]}'::jsonb, false,
    'trafego_plano_destino_e_do_dono_da_acao');

  perform pg_temp.tenta(
    'INV1 destino resolvido com a acao SEM dono lido e recusado',
    '{"impressao":"bb000000000000000000000000000000000000000000000000000000000000bb",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "acao_alvo_owner_id":null,
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_product_destination_id":"7498530235","destino_causa":null,
      "frescor_estado":"com_dados","frescor_ultima_em":"2026-08-30",
      "frescor_dias":2,"frescor_conversoes":1,
      "completo":false,"bloqueadores":["x"]}'::jsonb, false,
    'trafego_plano_destino_e_do_dono_da_acao');

  -- ── INVARIANTE 3 reforcada: o ROTULO nao basta ─────────────────────────
  perform pg_temp.tenta(
    'INV3 completo com frescor com_dados e SEM data nem contagem e recusado',
    '{"impressao":"da000000000000000000000000000000000000000000000000000000000000da",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "acao_alvo_owner_id":"5478096539",
      "destino_resolvido":true,"destino_operating_account_id":"5478096539",
      "destino_product_destination_id":"7498530235","destino_causa":null,
      "frescor_estado":"com_dados","completo":true,"bloqueadores":[]}'::jsonb, false,
    'trafego_plano_completo_exige_prova');

  -- ⚠️ E o caso que a mudanca de doutrina LIBERA: conta que mede por tag,
  -- completa, e SEM destino offline resolvido. Sinal != Data Manager.
  perform pg_temp.tenta(
    'INV3 completo por TAG, sem destino offline, e ACEITO',
    '{"impressao":"db000000000000000000000000000000000000000000000000000000000000db",
      "acao_alvo_id":"7498530235","acao_alvo_causa":null,
      "acao_alvo_owner_id":"5478096539",
      "destino_resolvido":false,"destino_causa":"tipo nao aceito pela ingestao offline",
      "frescor_estado":"com_dados","frescor_ultima_em":"2026-08-30",
      "frescor_dias":2,"frescor_conversoes":3,
      "completo":true,"bloqueadores":[]}'::jsonb, true);

  -- ── INVARIANTE 4: bloqueador NULL ou vazio nao e bloqueador nomeado ────
  perform pg_temp.tenta(
    'INV4 bloqueador NULO nao conta como razao nomeada',
    '{"impressao":"ea000000000000000000000000000000000000000000000000000000000000ea",
      "completo":false,"bloqueadores":[null]}'::jsonb, false,
    'trafego_plano_bloqueador_ou_completude');

  perform pg_temp.tenta(
    'INV4 bloqueador VAZIO nao conta como razao nomeada',
    '{"impressao":"eb000000000000000000000000000000000000000000000000000000000000eb",
      "completo":false,"bloqueadores":[""]}'::jsonb, false,
    'trafego_plano_bloqueador_ou_completude');

  perform pg_temp.tenta(
    'INV4 um bloqueador nomeado e outro NULO ainda e recusado',
    '{"impressao":"ec000000000000000000000000000000000000000000000000000000000000ec",
      "completo":false,"bloqueadores":["a acao nao e primaria", null]}'::jsonb, false,
    'trafego_plano_bloqueador_ou_completude');

  -- ── conta: id de conta com forma errada ──────────────────────────────────
  perform pg_temp.tenta(
    'customer_id nao numerico e recusado',
    '{"impressao":"a5000000000000000000000000000000000000000000000000000000000000a5",
      "customer_id":"portal-mundo-mais"}'::jsonb, false,
    'trafego_plano_contas');
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

-- ⚠️ TRUNCATE apaga esta tabela em silencio, e isso e DELIBERADO — ver o
-- comentario da v12_02 ao lado do gatilho. Nao ha prova aqui porque nao ha
-- guarda: a bancada de testes do dominio de trafego depende desse escape hatch.

-- ── o nivel UNKNOWN sobreviveu como UNKNOWN ────────────────────────────────
do $$
declare v text;
begin
    select nivel into v from public.trafego_campanha_plano_de_mensuracao
     where impressao = 'a4000000000000000000000000000000000000000000000000000000000000a4';
    if v = 'UNKNOWN' then raise notice '  ok   UNKNOWN persistiu como UNKNOWN, e nao como CUSTOMER';
    else raise notice 'FALHOU  UNKNOWN virou %', coalesce(v, '<null>'); end if;
end $$;
