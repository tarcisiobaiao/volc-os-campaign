-- =============================================================================
-- v12_02 — o plano canônico de mensuração da campanha (campaign_measurement_plan)
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin.
-- ⚠️ NÃO APLICADA EM PRODUÇÃO. Ver `supabase/migrations/README.md`.
-- Autoridade: database.agenciavolc.com.br.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTA MIGRATION É
-- -----------------------------------------------------------------------------
-- Ela persiste, de forma append-only, o `campaign_measurement_plan` de P05-T12:
-- o que uma campanha persegue, de quem é a ação que mede isso, por onde o sinal
-- chega e quão fresco ele é — decidido ANTES do nascimento.
--
-- Ela NÃO cria campanha, NÃO cria ação de conversão, NÃO altera meta e NÃO
-- decide. Ela registra leitura, com o ESTADO de cada leitura, inclusive vazio,
-- inelegível, não suportado e falha. Zero medido continua sendo zero.
--
-- -----------------------------------------------------------------------------
-- O FATO QUE A ORIGINOU
-- -----------------------------------------------------------------------------
-- Medido ao vivo em 01/09/2026 na conta 5478096539 (Portal Mundo Mais):
-- `goal_config_level = CUSTOMER`, e a ÚNICA meta biddable da conta é
-- DOWNLOAD/APP. A única ação de conversão com essa semântica
-- (#7498530235, ANDROID_INSTALLS_ALL_OTHER_APPS) tem `primary_for_goal = false`
-- DECLARADO — logo é não-biddable em toda campanha, qualquer que seja a meta.
--
-- Em MANUAL_CPC nada disso muda o lance e ninguém percebe. Sob Smart Bidding, a
-- campanha aprenderia a perseguir um objetivo que ninguém escolheu — e que
-- nenhuma ação mede. Este schema existe para que esse fato fique GRAVADO antes
-- de alguém apertar o botão, e não descoberto depois do orçamento gasto.
--
-- -----------------------------------------------------------------------------
-- AS SEIS INVARIANTES QUE O SCHEMA DEFENDE (não a aplicação — o schema)
-- -----------------------------------------------------------------------------
-- 1. DESTINO É DONO + ID NUMÉRICO, NUNCA NOME. `destino_resolvido = true` exige
--    `operating_account_id` e um `product_destination_id` que casa com '^[0-9]+$'.
--    A Data Manager exige que a operating account seja a conta que POSSUI a
--    ação; mandar para a conta errada não dá erro, dá SILÊNCIO.
-- 2. AÇÃO ELEITA XOR CAUSA. Ou existe ação, ou existe a razão nomeada de não
--    haver. Nunca as duas, nunca nenhuma — plano sem ação e sem causa é
--    ignorância anônima, indistinguível de silêncio.
-- 3. COMPLETO EXIGE AS TRÊS PROVAS. `completo = true` só é gravável com ação
--    eleita, destino resolvido e frescor com dados. Um plano "completo" sem
--    prova é opinião com força de fato.
-- 4. BLOQUEADOR OU COMPLETUDE, NUNCA OS DOIS NEM NENHUM. Plano incompleto sem
--    bloqueador nomeado é botão cinza com outro nome.
-- 5. LEITURA SEM CONCLUSÃO NÃO CARREGA NÚMERO. `nao_coletado`, `inelegivel`,
--    `nao_suportado` e `falhou` proíbem contagem de conversão — um número ali
--    seria precisão inventada sobre o que ninguém mediu.
-- 6. CAMPANHA QUE NÃO NASCEU NÃO TEM META DE CAMPANHA. Com `campaign_id` nulo,
--    `metas_da_campanha_estado` só pode ser `inelegivel`. Dizer
--    `vazio_confirmado` afirmaria que a campanha existe e não tem meta.
--
-- -----------------------------------------------------------------------------
-- A ARMADILHA DO `CHECK` QUE VALE NULL
-- -----------------------------------------------------------------------------
-- ⚠️ Um CHECK que avalia para NULL **PASSA**. Não é opinião: é a lógica de três
-- valores do SQL, e ela transforma uma guarda em decoração sem avisar ninguém.
--
-- Medido no ciclo descartável em 01/09/2026, nesta própria migration: a guarda
-- do destino era
--     (destino_resolvido and destino_operating_account_id ~ '^[0-9]{6,12}$' ...)
-- e, com `destino_operating_account_id` NULO, `NULL ~ '...'` vale NULL,
-- `true AND NULL` vale NULL, e a linha ENTROU. A prova
-- "destino resolvido sem conta dona é recusado" acusou o defeito — a guarda que
-- existe para impedir o destino sem dono estava aceitando exatamente isso.
--
-- Por isso toda comparação com coluna NULÁVEL aqui passa por `coalesce` ou por
-- um `IS NOT NULL` explícito. `IS NULL`/`IS NOT NULL` nunca valem NULL; `=`,
-- `<>` e `~` valem, sempre que um dos lados for nulo.
--
-- -----------------------------------------------------------------------------
-- ACHADO H: O ACL PADRÃO QUEBRADO
-- -----------------------------------------------------------------------------
-- `public` concede `arwdDxt` a anon, authenticated e service_role em TODA tabela
-- nova, e EXECUTE em toda função nova. Isso é real e está ativo em produção.
-- `REVOKE ... FROM PUBLIC` não resolve: os grants do default ACL são NOMINAIS.
-- Por isso há REVOKE explícito por papel, inclusive de `service_role`, ANTES do
-- GRANT mínimo.
-- =============================================================================

\set ON_ERROR_STOP on

begin;

do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception 'v12_02 deve rodar como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
    if to_regclass('public.trafego_campanha') is null then
        raise exception using
            errcode = '55000',
            message = 'v12_02 exige v9_01: public.trafego_campanha nao existe';
    end if;
    if to_regclass('public.trafego_campanha_plano_de_mensuracao') is not null then
        raise exception using
            errcode = '42P07',
            message = 'v12_02 ja aplicada: public.trafego_campanha_plano_de_mensuracao existe';
    end if;
end
$guarda$;

-- ── 1. o plano ──────────────────────────────────────────────────────────────

create table public.trafego_campanha_plano_de_mensuracao (
    plano_id                uuid primary key default gen_random_uuid(),

    -- ⚠️ A IDENTIDADE É A IMPRESSÃO DO CONTEÚDO, e ela cobre conta, campanha,
    -- nível, metas que mandam, ação eleita e destino — nunca o frescor, que
    -- muda de hora em hora sem o plano ter mudado. Incluir frescor faria cada
    -- leitura gravar um plano "novo": o histórico viraria ruído e a
    -- idempotência deixaria de existir.
    impressao               text not null unique,
    versao                  integer not null,

    customer_id             text not null,
    login_customer_id       text not null,

    -- ⚠️ NULO É O CASO NORMAL. O plano existe ANTES do nascimento — é esse o
    -- ponto inteiro de P05-T12. Uma coluna NOT NULL aqui obrigaria a inventar
    -- um id de campanha que não existe, ou a não gravar o plano justamente
    -- quando ele mais importa.
    campaign_id             text,
    volc_campaign_id        text references public.trafego_campanha (volc_campaign_id)
                                 on delete restrict,
    chave_intencao          text,

    -- ── meta efetiva ────────────────────────────────────────────────────────
    nivel                   text,
    nivel_estado            text not null,
    -- ⚠️ O nível foi INFERIDO pela herança documentada, e não LIDO do recurso.
    -- Antes do nascimento `conversion_goal_campaign_config` nao pode ser
    -- consultado. Sintetizar `nivel_estado='com_dados'` para dizer isso — como
    -- a primeira versao fazia — afirmaria que o recurso foi lido, e a coluna
    -- ficaria indistinguivel de um nivel de fato consultado.
    nivel_herdado           boolean not null default false,
    custom_conversion_goal  text,
    metas_da_conta_estado   text not null,
    metas_da_campanha_estado text not null,
    metas_biddable          text[] not null default '{}'::text[],
    meta_resolvida          boolean not null,

    -- ── a ação que mede ─────────────────────────────────────────────────────
    acoes_estado            text not null,
    acao_alvo_id            text,
    acao_alvo_owner_id      text,
    acao_alvo_tipo          text,
    acao_alvo_semantica     text,
    acao_alvo_causa         text,

    -- ── destino de conversão offline ────────────────────────────────────────
    destino_resolvido               boolean not null,
    destino_operating_account_id    text,
    destino_product_destination_id  text,
    destino_causa                   text,

    -- ── frescor ─────────────────────────────────────────────────────────────
    frescor_estado          text not null,
    frescor_ultima_em       date,
    frescor_dias            integer,
    frescor_conversoes      numeric,

    -- ── marcação da conta ───────────────────────────────────────────────────
    marcacao_estado         text not null,
    auto_tagging            boolean,
    conversion_tracking_id  text,
    conversion_tracking_owner_id text,
    conversion_tracking_status   text,
    aceitou_termos_de_dados boolean,
    -- `customer.time_zone`: o fuso em que a data da ultima conversao foi
    -- escrita. Sem ele, `frescor_dias` seria a subtracao de duas datas de
    -- fusos diferentes.
    fuso                    text,

    -- ── veredito ────────────────────────────────────────────────────────────
    completo                boolean not null,
    bloqueadores            text[] not null default '{}'::text[],

    payload                 jsonb not null default '{}'::jsonb,
    api_versao              text not null,
    lido_em                 timestamptz not null,
    registrado_em           timestamptz not null default now(),

    -- ── as guardas ──────────────────────────────────────────────────────────

    constraint trafego_plano_impressao
        check (impressao ~ '^[0-9a-f]{64}$'),
    constraint trafego_plano_versao
        check (versao > 0),
    constraint trafego_plano_contas
        check (customer_id ~ '^[0-9]{6,12}$' and login_customer_id ~ '^[0-9]{6,12}$'),
    constraint trafego_plano_campaign_id
        check (campaign_id is null or campaign_id ~ '^[0-9]+$'),

    -- Espelho não pode existir sem a campanha externa a que ele se refere.
    constraint trafego_plano_vinculo
        check (volc_campaign_id is null or campaign_id is not null),

    -- Os sete estados de leitura, escritos uma vez por coluna. Deliberadamente
    -- os MESMOS de `volc_ads.inteligencia_google.modelo.EstadoColeta`, mais
    -- `nao_coletado` — que lá é expresso pela ausência de linha e aqui precisa
    -- de nome, porque a linha existe.
    constraint trafego_plano_nivel_estado
        check (nivel_estado in ('nao_coletado','com_dados','vazio_confirmado',
                                'parcial','inelegivel','nao_suportado','falhou')),
    constraint trafego_plano_metas_conta_estado
        check (metas_da_conta_estado in ('nao_coletado','com_dados','vazio_confirmado',
                                'parcial','inelegivel','nao_suportado','falhou')),
    constraint trafego_plano_metas_campanha_estado
        check (metas_da_campanha_estado in ('nao_coletado','com_dados','vazio_confirmado',
                                'parcial','inelegivel','nao_suportado','falhou')),
    constraint trafego_plano_acoes_estado
        check (acoes_estado in ('nao_coletado','com_dados','vazio_confirmado',
                                'parcial','inelegivel','nao_suportado','falhou')),
    constraint trafego_plano_frescor_estado
        check (frescor_estado in ('nao_coletado','com_dados','vazio_confirmado',
                                'parcial','inelegivel','nao_suportado','falhou')),
    constraint trafego_plano_marcacao_estado
        check (marcacao_estado in ('nao_coletado','com_dados','vazio_confirmado',
                                'parcial','inelegivel','nao_suportado','falhou')),

    -- O enum de v25, os QUATRO valores. `UNSPECIFIED` e `UNKNOWN` existem e não
    -- são `CUSTOMER`: tratá-los como herança afirmaria o que a API não disse.
    constraint trafego_plano_nivel
        check (nivel is null or nivel in ('CUSTOMER','CAMPAIGN','UNSPECIFIED','UNKNOWN')),
    constraint trafego_plano_nivel_lido
        check (nivel_estado <> 'com_dados' or nivel is not null),

    -- INVARIANTE 6.
    constraint trafego_plano_campanha_inexistente_nao_tem_meta
        check (campaign_id is not null or metas_da_campanha_estado = 'inelegivel'),

    -- INVARIANTE 2.
    constraint trafego_plano_acao_xor_causa
        check ((acao_alvo_id is null) = (btrim(coalesce(acao_alvo_causa,'')) <> '')),
    constraint trafego_plano_acao_numerica
        check (acao_alvo_id is null or acao_alvo_id ~ '^[0-9]+$'),
    constraint trafego_plano_acao_owner_numerico
        check (acao_alvo_owner_id is null or acao_alvo_owner_id ~ '^[0-9]{6,12}$'),

    -- INVARIANTE 1 — a que impede o destino por nome.
    -- ⚠️ `coalesce(...,'')` em cada lado NULÁVEL. Sem ele esta guarda vale NULL
    -- quando a conta dona é nula — e um CHECK que vale NULL PASSA. Foi assim que
    -- um destino resolvido SEM dono entrou no cluster de prova.
    constraint trafego_plano_destino_por_dono_e_id
        check (
            (destino_resolvido
             and coalesce(destino_operating_account_id, '') ~ '^[0-9]{6,12}$'
             and coalesce(destino_product_destination_id, '') ~ '^[0-9]+$')
            or (not destino_resolvido
                and btrim(coalesce(destino_causa,'')) <> '')
        ),
    -- Destino resolvido tem de apontar para a ação ELEITA, e não para outra.
    constraint trafego_plano_destino_e_da_acao_eleita
        check (not destino_resolvido
               or (destino_product_destination_id is not null
                   and acao_alvo_id is not null
                   and destino_product_destination_id = acao_alvo_id)),
    -- ⚠️ E A CONTA TEM DE SER A DONA DA ACAO. Este CHECK faltava, e sem ele o
    -- cabecalho da INVARIANTE 1 dizia uma coisa que o schema nao defendia: uma
    -- linha entrava com `acao_alvo_owner_id` NULO e
    -- `destino_operating_account_id` apontando para outra conta qualquer.
    -- A Data Manager exige que a operating account POSSUA a acao; mandar para a
    -- conta errada nao da erro, da SILENCIO.
    constraint trafego_plano_destino_e_do_dono_da_acao
        check (not destino_resolvido
               or (acao_alvo_owner_id is not null
                   and destino_operating_account_id = acao_alvo_owner_id)),

    -- INVARIANTE 5.
    constraint trafego_plano_frescor_sem_conclusao_nao_conta
        check (frescor_estado not in ('nao_coletado','inelegivel','nao_suportado','falhou')
               or (frescor_conversoes is null and frescor_ultima_em is null
                   and frescor_dias is null)),
    -- Zero medido é zero, e zero medido não tem data de última conversão.
    -- ⚠️ `is not null and = 0`, e não só `= 0`. Com `frescor_conversoes` nulo,
    -- `NULL = 0` vale NULL e o CHECK inteiro passa — ou seja, `vazio_confirmado`
    -- entraria SEM o zero medido que é a única coisa que ele afirma.
    constraint trafego_plano_frescor_vazio_e_zero
        check (frescor_estado <> 'vazio_confirmado'
               or (frescor_conversoes is not null and frescor_conversoes = 0
                   and frescor_ultima_em is null)),
    constraint trafego_plano_frescor_dias_precisa_de_data
        check (frescor_dias is null or frescor_ultima_em is not null),

    -- INVARIANTE 3.
    --
    -- ⚠️ A primeira versao exigia apenas o ROTULO `frescor_estado='com_dados'` e
    -- o booleano livre `meta_resolvida` — e as duas "provas" eram satisfativeis
    -- com ZERO dado: `com_dados` entrava com data, dias e contagem TODOS nulos,
    -- e `meta_resolvida` passava `true` com `nivel_estado='falhou'` e
    -- `metas_biddable={}`. Era exatamente a "opiniao com forca de fato" que o
    -- cabecalho diz que esta invariante existe para impedir.
    --
    -- ⚠️ E `destino_resolvido` SAIU da exigencia. Ele descreve a via de ingestao
    -- OFFLINE, e este sistema impoe desde `prontidao.py` que sinal != Data
    -- Manager: uma conta que converte por tag do Google mede perfeitamente e
    -- nunca vai ter destino offline. Exigi-lo declarava despreparo onde nao ha.
    constraint trafego_plano_completo_exige_prova
        check (not completo
               or (acao_alvo_id is not null
                   and meta_resolvida
                   and frescor_estado = 'com_dados'
                   and frescor_ultima_em is not null
                   and frescor_dias is not null
                   and frescor_conversoes is not null
                   and frescor_conversoes > 0)),

    -- `meta_resolvida` tambem precisa de lastro: ele e um booleano que a
    -- aplicacao calcula, e o schema nao pode aceitar a palavra dela.
    constraint trafego_plano_meta_resolvida_exige_evidencia
        check (not meta_resolvida
               or (nivel in ('CUSTOMER', 'CAMPAIGN')
                   and (nivel_estado = 'com_dados' or nivel_herdado)
                   and cardinality(metas_biddable) > 0
                   -- Meta customizada tira as duas listas do comando: ela nao
                   -- respeita `primary_for_goal`, e o que ela persegue mora num
                   -- recurso que este sistema ainda nao le.
                   and custom_conversion_goal is null)),

    -- INVARIANTE 4.
    --
    -- ⚠️ `cardinality` CONTA elemento NULL: `cardinality('{NULL}')` = 1. E a
    -- funcao de escrita monta o array com `jsonb_array_elements_text`, que
    -- converte um `null` de JSON em NULL de SQL. Entao um plano incompleto cujo
    -- unico "bloqueador" fosse NULL — ou string vazia — satisfazia a guarda de
    -- "bloqueador NOMEADO", e a tela renderizava a caixa de bloqueio com um
    -- item em branco: o portao fechado e nenhuma razao. E a mesma familia dos
    -- CHECKs que valem NULL, so que aqui o NULL entra por dentro do array.
    constraint trafego_plano_bloqueador_ou_completude
        check ((completo and cardinality(bloqueadores) = 0)
               or (not completo
                   and cardinality(bloqueadores) > 0
                   and cardinality(array_remove(array_remove(bloqueadores, null), ''))
                       = cardinality(bloqueadores))),

    constraint trafego_plano_payload_objeto
        check (jsonb_typeof(payload) = 'object'),
    constraint trafego_plano_api_versao
        check (btrim(api_versao) <> '')
);

create index trafego_plano_conta_ix
    on public.trafego_campanha_plano_de_mensuracao
    (customer_id, lido_em desc);
create index trafego_plano_campanha_ix
    on public.trafego_campanha_plano_de_mensuracao
    (volc_campaign_id, lido_em desc)
    where volc_campaign_id is not null;
create index trafego_plano_intencao_ix
    on public.trafego_campanha_plano_de_mensuracao
    (chave_intencao, lido_em desc)
    where chave_intencao is not null;
create index trafego_plano_completo_ix
    on public.trafego_campanha_plano_de_mensuracao
    (completo, lido_em desc);

comment on table public.trafego_campanha_plano_de_mensuracao is
  'O campaign_measurement_plan de P05-T12: meta efetiva, acao que mede, dono, destino offline e frescor, decididos ANTES do nascimento. Append-only. Ausencia, zero medido, inelegibilidade e falha sao estados distintos.';
comment on column public.trafego_campanha_plano_de_mensuracao.campaign_id is
  'Nulo e o caso NORMAL: o plano existe antes de a campanha nascer.';
comment on column public.trafego_campanha_plano_de_mensuracao.nivel is
  'goal_config_level do Google Ads v25: CUSTOMER, CAMPAIGN, UNSPECIFIED ou UNKNOWN. Os dois ultimos NAO sao heranca da conta.';
comment on column public.trafego_campanha_plano_de_mensuracao.destino_product_destination_id is
  'O ID NUMERICO da ConversionAction. Nunca o nome, nunca o resource_name: a Data Manager resolve destino por conta dona + id.';
comment on column public.trafego_campanha_plano_de_mensuracao.acao_alvo_causa is
  'Por que nenhuma acao foi eleita. Excludente com acao_alvo_id: uma das duas sempre existe, nunca as duas.';
comment on column public.trafego_campanha_plano_de_mensuracao.frescor_conversoes is
  'Zero e MEDIDO. Nulo e nao medido. As duas coisas pedem acoes opostas.';
comment on column public.trafego_campanha_plano_de_mensuracao.impressao is
  'sha256 do conteudo que DECIDE (conta, campanha, nivel, metas, acao, destino). Frescor nao entra: ele muda sem o plano mudar.';

-- ── 2. append-only ──────────────────────────────────────────────────────────
--
-- ⚠️ Um plano é a fotografia de uma leitura. Corrigi-lo depois apagaria o que
-- se sabia no instante em que alguém decidiu — e é justamente esse instante que
-- o plano existe para registrar. Leitura nova é linha nova.

create or replace function public.trafego_plano_append_only()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    raise exception using
        errcode = '55000',
        message = format('%s e append-only: UPDATE e DELETE recusados', tg_table_name);
end;
$$;

create trigger trafego_plano_append_only_tg
    before update or delete on public.trafego_campanha_plano_de_mensuracao
    for each row execute function public.trafego_plano_append_only();

-- ⚠️ TRUNCATE NAO DISPARA GATILHO DE LINHA, e AQUI ISSO E DELIBERADO.
--
-- Medido no cluster descartavel: `delete` e recusado com 55000, e `truncate`
-- apaga em silencio. Um `before truncate ... for each statement` fecharia essa
-- porta — e foi escrito, e foi REVERTIDO, porque ele quebra uma decisao que
-- esta casa ja tinha tomado: a bancada usa TRUNCATE como escape hatch do
-- append-only, e o diz em voz alta em backend/tests/test_trafego_persistencia.py
-- ("o gatilho protege o dominio, nao a bancada"). Com a FK desta tabela para
-- `trafego_campanha`, o `TRUNCATE ... CASCADE` da bancada alcanca esta tabela
-- por forca do proprio Postgres, e nao ha como pedir que ele nao alcance.
--
-- O risco residual e real e esta registrado: no SQL editor do Studio, que roda
-- como `postgres`, o DELETE grita e o TRUNCATE apaga sem aviso uma tabela que o
-- rollback declara NAO reconstruivel. `service_role` nao tem TRUNCATE, entao o
-- backend e o PostgREST nao alcancam. Fechar essa porta e uma decisao de dono,
-- e ela custa o arranjo de testes de todo o dominio de trafego.

-- ── 3. a única porta de escrita ─────────────────────────────────────────────
--
-- ⚠️ `service_role` recebe SELECT e EXECUTE, e NÃO recebe INSERT. Toda escrita
-- passa por esta função: uma requisição PostgREST é uma transação, e uma função
-- é uma requisição — logo um BEGIN/COMMIT. Um INSERT direto pela API deixaria a
-- idempotência do lado de quem chama, e ela sumiria no primeiro retry.

create or replace function public.volc_registrar_plano_de_mensuracao(documento jsonb)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    novo uuid;
    existente uuid;
begin
    if jsonb_typeof(documento) <> 'object' then
        raise exception using errcode='22023', message='documento precisa ser objeto JSON';
    end if;

    -- Idempotência pela impressão: a MESMA leitura gravada duas vezes devolve a
    -- mesma linha, e não uma segunda. É o que torna seguro chamar isto de
    -- dentro de um retry.
    select plano_id into existente
      from public.trafego_campanha_plano_de_mensuracao
     where impressao = documento->>'impressao';
    if existente is not null then
        return existente;
    end if;

    insert into public.trafego_campanha_plano_de_mensuracao (
        impressao, versao, customer_id, login_customer_id, campaign_id,
        volc_campaign_id, chave_intencao,
        nivel, nivel_estado, nivel_herdado, custom_conversion_goal,
        metas_da_conta_estado, metas_da_campanha_estado, metas_biddable,
        meta_resolvida,
        acoes_estado, acao_alvo_id, acao_alvo_owner_id, acao_alvo_tipo,
        acao_alvo_semantica, acao_alvo_causa,
        destino_resolvido, destino_operating_account_id,
        destino_product_destination_id, destino_causa,
        frescor_estado, frescor_ultima_em, frescor_dias, frescor_conversoes,
        marcacao_estado, auto_tagging, conversion_tracking_id,
        conversion_tracking_owner_id, conversion_tracking_status,
        aceitou_termos_de_dados, fuso,
        completo, bloqueadores, payload, api_versao, lido_em
    ) values (
        documento->>'impressao',
        (documento->>'versao')::integer,
        documento->>'customer_id',
        documento->>'login_customer_id',
        nullif(documento->>'campaign_id',''),
        nullif(documento->>'volc_campaign_id',''),
        nullif(documento->>'chave_intencao',''),
        nullif(documento->>'nivel',''),
        documento->>'nivel_estado',
        coalesce((documento->>'nivel_herdado')::boolean, false),
        nullif(documento->>'custom_conversion_goal',''),
        documento->>'metas_da_conta_estado',
        documento->>'metas_da_campanha_estado',
        array(select jsonb_array_elements_text(
                       coalesce(documento->'metas_biddable','[]'::jsonb))),
        (documento->>'meta_resolvida')::boolean,
        documento->>'acoes_estado',
        nullif(documento->>'acao_alvo_id',''),
        nullif(documento->>'acao_alvo_owner_id',''),
        nullif(documento->>'acao_alvo_tipo',''),
        nullif(documento->>'acao_alvo_semantica',''),
        nullif(documento->>'acao_alvo_causa',''),
        (documento->>'destino_resolvido')::boolean,
        nullif(documento->>'destino_operating_account_id',''),
        nullif(documento->>'destino_product_destination_id',''),
        nullif(documento->>'destino_causa',''),
        documento->>'frescor_estado',
        nullif(documento->>'frescor_ultima_em','')::date,
        nullif(documento->>'frescor_dias','')::integer,
        -- ⚠️ `nullif(...,'')` e NÃO `coalesce(...,0)`. Um zero no lugar de uma
        -- leitura ausente é a mentira mais barata deste schema.
        nullif(documento->>'frescor_conversoes','')::numeric,
        documento->>'marcacao_estado',
        nullif(documento->>'auto_tagging','')::boolean,
        nullif(documento->>'conversion_tracking_id',''),
        nullif(documento->>'conversion_tracking_owner_id',''),
        nullif(documento->>'conversion_tracking_status',''),
        nullif(documento->>'aceitou_termos_de_dados','')::boolean,
        nullif(documento->>'fuso',''),
        (documento->>'completo')::boolean,
        array(select jsonb_array_elements_text(
                       coalesce(documento->'bloqueadores','[]'::jsonb))),
        coalesce(documento->'payload','{}'::jsonb),
        documento->>'api_versao',
        (documento->>'lido_em')::timestamptz
    ) returning plano_id into novo;

    return novo;
exception
    when unique_violation then
        select plano_id into existente
          from public.trafego_campanha_plano_de_mensuracao
         where impressao = documento->>'impressao';
        if existente is null then raise; end if;
        return existente;
end;
$$;

-- ── 4. contenção ────────────────────────────────────────────────────────────

alter table public.trafego_campanha_plano_de_mensuracao enable row level security;
alter table public.trafego_campanha_plano_de_mensuracao force row level security;

revoke all on public.trafego_campanha_plano_de_mensuracao from public;
revoke all on public.trafego_campanha_plano_de_mensuracao from anon;
revoke all on public.trafego_campanha_plano_de_mensuracao from authenticated;
revoke all on public.trafego_campanha_plano_de_mensuracao from service_role;
revoke all on function public.volc_registrar_plano_de_mensuracao(jsonb) from public;
revoke all on function public.volc_registrar_plano_de_mensuracao(jsonb) from anon;
revoke all on function public.volc_registrar_plano_de_mensuracao(jsonb) from authenticated;

grant select on public.trafego_campanha_plano_de_mensuracao to service_role;
grant execute on function public.volc_registrar_plano_de_mensuracao(jsonb) to service_role;

-- ── 5. verificação embutida ─────────────────────────────────────────────────

do $verifica$
declare
    n_tab integer; n_rls integer; n_pol integer; n_trg integer;
    n_priv integer; n_ins integer; n_chk integer;
begin
    select count(*) into n_tab from pg_tables
     where schemaname='public' and tablename = 'trafego_campanha_plano_de_mensuracao';
    select count(*) into n_rls from pg_class c join pg_namespace n on n.oid=c.relnamespace
     where n.nspname='public' and c.relname='trafego_campanha_plano_de_mensuracao'
       and c.relkind='r' and c.relrowsecurity and c.relforcerowsecurity;
    select count(*) into n_pol from pg_policies
     where schemaname='public' and tablename='trafego_campanha_plano_de_mensuracao';
    select count(*) into n_trg from pg_trigger t join pg_class c on c.oid=t.tgrelid
     join pg_namespace n on n.oid=c.relnamespace
     where n.nspname='public' and c.relname='trafego_campanha_plano_de_mensuracao'
       and not t.tgisinternal;
    select count(*) into n_priv from information_schema.role_table_grants
     where table_schema='public' and table_name='trafego_campanha_plano_de_mensuracao'
       and grantee in ('anon','authenticated','PUBLIC');
    -- ⚠️ A guarda que importa: `service_role` NÃO pode inserir direto. Se ela
    -- pudesse, a idempotência sairia da função e viraria responsabilidade de
    -- quem chama — e sumiria no primeiro retry.
    select count(*) into n_ins from information_schema.role_table_grants
     where table_schema='public' and table_name='trafego_campanha_plano_de_mensuracao'
       and grantee='service_role' and privilege_type in ('INSERT','UPDATE','DELETE');
    select count(*) into n_chk from pg_constraint c join pg_class t on t.oid=c.conrelid
     join pg_namespace n on n.oid=t.relnamespace
     where n.nspname='public' and t.relname='trafego_campanha_plano_de_mensuracao'
       and c.contype='c';

    if n_tab <> 1 then raise exception 'v12_02: esperava 1 tabela, achei %', n_tab; end if;
    if n_rls <> 1 then raise exception 'v12_02: RLS nao esta forcada'; end if;
    if n_pol <> 0 then raise exception 'v12_02: esperava 0 policies, achei %', n_pol; end if;
    if n_trg <> 1 then raise exception 'v12_02: esperava 1 gatilho, achei %', n_trg; end if;
    if n_priv <> 0 then raise exception 'v12_02: anon/authenticated tem % privilegio(s)', n_priv; end if;
    if n_ins <> 0 then raise exception 'v12_02: service_role tem % privilegio de escrita direta', n_ins; end if;
    if n_chk < 20 then raise exception 'v12_02: esperava >=20 CHECKs, achei %', n_chk; end if;

    raise notice 'v12_02 OK: 1 tabela, RLS forcada, 0 policies, 1 gatilho, % CHECKs, escrita so por funcao.', n_chk;
end
$verifica$;

notify pgrst, 'reload schema';
commit;
