-- =============================================================================
-- v11_02 — O parque criativo vira DADO: motores, modos, formatos, skins, vozes,
--          gates, exigencias de canal e direitos. Mais a blindagem da v11_01.
-- ESTUDIO CRIATIVO VOLC. APLICAR DEPOIS DA v11_01.
-- =============================================================================
-- APLICAR COMO: postgres (supabase_admin tambem serve; a guarda aceita os dois)
--
-- ORDEM: DEPOIS da v11_01. Ela referencia `criativo_job`, `criativo_briefing`,
--        `criativo_master` e `criativo_aprovacao`.
-- ROLLBACK: supabase/migrations/v11_02_rollback.sql (executavel, e RODADO —
--           ver scripts/provar-ciclo-v11.sh)
--
-- -----------------------------------------------------------------------------
-- POR QUE ESTA MIGRATION EXISTE
-- -----------------------------------------------------------------------------
-- A v11_01 modelou o CICLO (projeto -> briefing -> job -> master -> aprovacao).
-- Ela nao modelou o PARQUE: quais motores existem, o que cada um sabe fazer,
-- quais formatos o canal exige, quais skins e vozes o motor de video oferece,
-- quais gates cada motor executa.
--
-- Hoje esse parque vive em quatro lugares que ninguem compara:
--
--   1. `docs/creative-engines/*.json`  — manifesto para humano e agente
--   2. `volc_ads/criativo/requisitos.yaml` — exigencia por canal, lida em runtime
--   3. `backend/app/criativo/dominio.py::FORMATOS` — catalogo em Python
--   4. `src/types/criativos.ts::FORMATOS_DE_IMAGEM` — catalogo em TypeScript
--
-- Quatro copias divergem. Ja divergiram: o teste que compara (3) com (4) passa
-- com as alturas de `4x5` e `9x16` TROCADAS, porque ele so confere substring.
-- A curadoria chama o registro de motores de `partial` exatamente por isto:
-- "Persistencia, leitura runtime e adaptacao ainda nao existem".
--
-- Esta migration faz o parque virar dado com dono unico. As copias em codigo
-- passam a ser CACHE de uma verdade que mora aqui.
--
-- -----------------------------------------------------------------------------
-- O ELO COM O COFRE DE ATIVOS, E POR QUE ELE NAO E UMA FK
-- -----------------------------------------------------------------------------
-- `docs/architecture/COFRE-DE-ATIVOS-CONTRATO.md` ja declara o motor como
-- patrimonio: gaveta `creative_production`, `kind = creative_engine`, com dois
-- ativos de identidade estavel em `src/features/asset-vault/fixtures.ts`:
--
--     asset:engine:image-volc   Motor de Imagem VOLC / PRENSA
--     asset:engine:video-volc   Motor de Video VOLC
--
-- O `nextAction` dos dois pede, literalmente, o que esta tabela entrega:
-- "Registrar endpoint/adaptador interno quando a integracao runtime comecar" e
-- "Definir adaptador, fila de jobs, armazenamento e recibo".
--
-- O Cofre inventaria o MOTOR; o Estudio inventaria as PECAS que o motor produz.
-- Sao autoridades vizinhas, e `criativo_motor.cofre_asset_id` e a costura.
--
-- ⚠️ E `text` e nao FK porque o Cofre AINDA NAO TEM TABELA — ele e contrato mais
-- fixture (`grep supabase src/features/asset-vault/` nao acha consulta nenhuma).
-- Uma FK para tabela inexistente nao compila; um id declarado hoje faz o join
-- existir no dia em que o Cofre persistir, e impede que alguem invente uma
-- segunda identidade de motor nesse meio tempo. A CHECK de forma protege o
-- formato do id para que a costura futura nao precise de limpeza.
--
-- -----------------------------------------------------------------------------
-- AS REGRAS DA CASA, HERDADAS E VALIDAS AQUI
-- -----------------------------------------------------------------------------
-- A. NENHUM NUMERO SEM FRESCOR. `verificado_em` acompanha toda afirmacao sobre
--    o parque externo. Um motor "verificado" sem data e uma promessa.
-- B. AUSENCIA E NULL, NUNCA ZERO. `bytes_maximos = null` significa "o canal nao
--    declara teto", e o validador NAO checa peso — diferente de `0`, que
--    reprovaria todo arquivo. Esta distincao ja custou caro em `requisitos.py`.
-- C. DOMINIO FECHADO ONDE HA DOMINIO. Modo, formato, finalidade, skin, voz e
--    gate deixam de ser texto livre. O que continua livre (`insumo`, `nota`,
--    `estilo` de voz) continua porque nao tem dominio de verdade.
-- D. O PARQUE E DECLARADO, NAO INFERIDO. Toda linha de dominio carrega
--    `fonte`: o arquivo e a data de onde o valor saiu. Sem isso, ninguem sabe
--    se `1080x1350` veio da especificacao do Google ou do chute de alguem.
-- E. SEED IDEMPOTENTE. Todo `insert` de dominio usa `on conflict do update`.
--    Reaplicar a migration atualiza o parque; nao duplica e nao apaga uso.
-- =============================================================================

\set ON_ERROR_STOP on

begin;

do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception
            'v11_02 deve ser aplicada como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
    if not exists (select 1 from pg_tables
                    where schemaname = 'public' and tablename = 'criativo_job') then
        raise exception 'v11_02 exige a v11_01 aplicada antes (criativo_job nao existe)';
    end if;
end
$guarda$;


-- =============================================================================
-- 1. MOTOR — o registro que a curadoria chama de `partial` por nao existir
-- =============================================================================

create table if not exists public.criativo_motor (
    id                  uuid primary key default gen_random_uuid(),
    slug                text not null,
    nome                text not null,
    -- O que ele PRODUZ. Um motor pode produzir mais de um tipo; a lista e o
    -- dominio, e a CHECK garante que cada item pertence a ele.
    produz              text[] not null,
    -- `interno`  roda no processo do VOLC O.S.
    -- `servico`  runtime separavel, chamado por contrato (alvo do ADR-001)
    -- `observado` a fabrica e externa e nos apenas LEMOS o que ela produziu
    runtime             text not null,
    -- A costura com o Cofre de Ativos. Ver o cabecalho.
    cofre_asset_id      text,
    provider            text,
    modelo              text,
    versao_do_adaptador text,
    -- Preco de REFERENCIA do provider, nunca fatura. `null` quando o motor nao
    -- cobra (PRENSA) ou quando ninguem levantou o preco.
    custo_referencia_usd numeric(12, 6),
    custo_unidade       text,
    custo_fonte         text,
    -- O que ele sabe fazer, como dado. Consultavel sem ler codigo.
    capacidades         jsonb not null default '[]'::jsonb,
    -- Hash do snapshot reproduzivel que provou o parque deste motor.
    snapshot_hash       text,
    fonte               text not null,
    verificado_em       timestamptz,
    ativo               boolean not null default true,
    criado_em           timestamptz not null default now(),

    constraint criativo_motor_slug_ux unique (slug),
    constraint criativo_motor_slug_forma
        check (slug ~ '^[a-z0-9][a-z0-9_.:-]{1,62}$'),
    constraint criativo_motor_runtime_valido
        check (runtime in ('interno', 'servico', 'observado')),
    constraint criativo_motor_produz_valido
        check (produz <@ array['imagem', 'video', 'audio', 'texto']::text[]
               and array_length(produz, 1) >= 1),
    -- Regra A: afirmacao sobre parque externo carrega a data em que foi vista.
    constraint criativo_motor_verificacao_com_carimbo
        check (verificado_em is null or fonte is not null),
    -- Regra B: custo ausente e NULL. Zero seria "medi e nao custou".
    constraint criativo_motor_custo_nao_negativo
        check (custo_referencia_usd is null or custo_referencia_usd >= 0),
    constraint criativo_motor_custo_com_unidade
        check ((custo_referencia_usd is null) = (custo_unidade is null)),
    -- A forma do id do Cofre, para que a costura futura nao precise de limpeza.
    constraint criativo_motor_cofre_forma
        check (cofre_asset_id is null or cofre_asset_id ~ '^asset:[a-z0-9_-]+:[a-z0-9_-]+$')
);

comment on table public.criativo_motor is
    'Registro de motores criativos. `cofre_asset_id` costura com o Cofre de Ativos, que inventaria o motor como patrimonio.';


-- =============================================================================
-- 2. MODO DE PRODUCAO — os seis do ADR-001, com o estado REAL de prova
-- =============================================================================
-- `estado_de_prova` e o campo que impede a interface de oferecer um modo como
-- pronto. Ele nao e opiniao: sai do snapshot de 26/08/2026, que classificou 94
-- artefatos por modo.

create table if not exists public.criativo_modo_de_producao (
    id                       uuid primary key default gen_random_uuid(),
    slug                     text not null,
    nome                     text not null,
    descricao                text not null,
    exige_provider_de_imagem boolean not null,
    renderer                 text not null,
    estado_de_prova          text not null,
    prova                    text,
    saidas_no_snapshot       integer,
    fonte                    text not null,
    ordem                    integer not null default 100,

    constraint criativo_modo_slug_ux unique (slug),
    constraint criativo_modo_estado_valido
        check (estado_de_prova in ('executado_externo', 'componentes_observados',
                                   'planejado', 'implementado_no_volc')),
    -- Regra B: contagem ausente e NULL. `0` significa "contei e deu zero".
    constraint criativo_modo_saidas_medidas
        check (saidas_no_snapshot is null or saidas_no_snapshot >= 0)
);


-- =============================================================================
-- 3. FORMATO — a quarta copia vira a primeira fonte
-- =============================================================================
-- Hoje o catalogo existe em `dominio.py::FORMATOS` e em
-- `criativos.ts::FORMATOS_DE_IMAGEM`, e o teste que os compara passa com as
-- alturas de `4x5` e `9x16` trocadas (ele so confere substring). Duas copias
-- sem arbitro divergem; esta tabela e o arbitro.

create table if not exists public.criativo_formato (
    id                uuid primary key default gen_random_uuid(),
    slot              text not null,
    rotulo            text not null,
    proporcao         text not null,
    largura           integer not null,
    altura            integer not null,
    -- Amarra ao vocabulario de `volc_ads/criativo/contrato.py::TipoDeAsset`,
    -- que e quem ja sabe o que cada canal exige de cada papel.
    tipo_de_asset     text not null,
    midia             text not null default 'imagem',
    descricao         text,
    destinos_tipicos  text[] not null default '{}',
    -- De onde a dimensao saiu. Ver regra D.
    fonte             text not null,
    ativo             boolean not null default true,
    ordem             integer not null default 100,

    constraint criativo_formato_slot_ux unique (slot),
    constraint criativo_formato_medida_positiva check (largura > 0 and altura > 0),
    constraint criativo_formato_midia_valida
        check (midia in ('imagem', 'video', 'audio')),
    constraint criativo_formato_tipo_valido
        check (tipo_de_asset in (
            'imagem_marketing', 'imagem_marketing_quadrada',
            'imagem_marketing_retrato', 'imagem_marketing_retrato_alto',
            'logo_quadrado', 'logo_paisagem', 'video'))
);


-- =============================================================================
-- 4. FINALIDADE — fecha o texto livre que era chave de indice unico
-- =============================================================================
-- `criativo_aprovacao.finalidade` era `text` sem allowlist, E fazia parte do
-- indice de vigencia. Consequencia medida: "google display", "Google Display" e
-- "Google  Display" eram tres tuplas distintas, com decisoes vigentes
-- CONTRADITORIAS ao mesmo tempo, e a tela mostrava so a mais recente.

create table if not exists public.criativo_finalidade (
    id        uuid primary key default gen_random_uuid(),
    slug      text not null,
    nome      text not null,
    descricao text not null,
    -- `interna` nao autoriza gasto nem publicacao. `midia_paga` e `organica`
    -- exigem autorizacao independente (SPEC secao 5).
    classe    text not null,
    ativo     boolean not null default true,
    ordem     integer not null default 100,

    constraint criativo_finalidade_slug_ux unique (slug),
    constraint criativo_finalidade_slug_forma check (slug ~ '^[a-z][a-z0-9_]{2,48}$'),
    constraint criativo_finalidade_classe_valida
        check (classe in ('interna', 'midia_paga', 'organica', 'exportacao'))
);


-- =============================================================================
-- 5. EXIGENCIA DE CANAL — o que o destino cobra, como dado
-- =============================================================================
-- Espelha `volc_ads/criativo/requisitos.yaml`. Aqui porque a validacao de
-- pacote de destino (C2) precisa consultar isto pelo banco, e porque
-- `fonte_dos_numeros` deixa separar num relance verdade medida de chute
-- defensavel — que e exatamente o que `EspecificacaoDeAsset` ja faz em Python.

create table if not exists public.criativo_exigencia_de_canal (
    id                       uuid primary key default gen_random_uuid(),
    canal                    text not null,
    tipo_de_asset            text not null,
    quantidade_minima        integer not null default 0,
    quantidade_maxima        integer,
    quantidade_recomendada   integer,
    proporcao_alvo           text,
    tolerancia_proporcao     numeric(5, 4) not null default 0.01,
    largura_minima           integer,
    altura_minima            integer,
    largura_recomendada      integer,
    altura_recomendada       integer,
    bytes_maximos            bigint,
    mimes_aceitos            text[] not null default '{}',
    duracao_minima_s         numeric(8, 2),
    duracao_maxima_s         numeric(8, 2),
    caracteres_maximos       integer,
    caracteres_de_pelo_menos_um integer,
    -- Regra D. `provisorio` diz que o numero ainda nao veio da matriz oficial.
    provisorio               boolean not null default true,
    fonte_dos_numeros        text not null,
    verificado_em            timestamptz,

    constraint criativo_exigencia_ux unique (canal, tipo_de_asset),
    constraint criativo_exigencia_quantidades
        check (quantidade_maxima is null or quantidade_maxima >= quantidade_minima),
    -- Regra B, e ela e literal aqui: `bytes_maximos = 0` reprovaria todo
    -- arquivo; ausencia significa "o canal nao declara teto".
    constraint criativo_exigencia_medidas_positivas
        check ((largura_minima is null or largura_minima > 0)
               and (altura_minima is null or altura_minima > 0)
               and (bytes_maximos is null or bytes_maximos > 0)
               and (caracteres_maximos is null or caracteres_maximos > 0)),
    constraint criativo_exigencia_duracao
        check (duracao_maxima_s is null or duracao_minima_s is null
               or duracao_maxima_s >= duracao_minima_s)
);

-- Teto que vale para VARIOS tipos somados. Existe porque a API tem exatamente
-- isso e um modelo por tipo nao consegue dize-lo: no responsive display ad,
-- `marketing_image` e `square_marketing_image` dividem um teto de 15, e quinze
-- paisagens mais uma quadrada sao recusadas — o payload inteiro, nao o excedente.
create table if not exists public.criativo_teto_combinado (
    id       uuid primary key default gen_random_uuid(),
    canal    text not null,
    rotulo   text not null,
    tipos    text[] not null,
    minimo   integer not null default 0,
    maximo   integer,
    fonte    text not null,

    constraint criativo_teto_ux unique (canal, rotulo),
    constraint criativo_teto_tipos_nao_vazio check (array_length(tipos, 1) >= 1),
    constraint criativo_teto_faixa check (maximo is null or maximo >= minimo)
);


-- =============================================================================
-- 6. SKIN e VOZ — o parque do motor de video
-- =============================================================================
-- 15 skins, 15 nichos e 14 vozes existem hoje so em `contrato/motor/mapa.json`,
-- na maquina de quem opera a fabrica. Persistir aqui e o que permite o Estudio
-- OFERECER uma skin sem ler o disco de outra pessoa.

create table if not exists public.criativo_skin (
    id        uuid primary key default gen_random_uuid(),
    slug      text not null,
    nicho     text not null,
    -- O arco narrativo REAL desta skin, em ordem. A SPEC generica fala
    -- Hook -> Contexto -> Virada -> Prova -> Revelacao -> CTA; o motor usa
    -- arcos proprios por skin, e sao os dele que valem.
    arco      text[] not null default '{}',
    papeis_obrigatorios text[] not null default '{}',
    elementos text[] not null default '{}',
    motor_id  uuid references public.criativo_motor(id),
    fonte     text not null,
    ativo     boolean not null default true,

    constraint criativo_skin_slug_ux unique (slug)
);

create table if not exists public.criativo_voz (
    id         uuid primary key default gen_random_uuid(),
    slug       text not null,
    voice_id   text not null,
    fallbacks  text[] not null default '{}',
    -- ⚠️ `estilo` continua TEXTO LIVRE de proposito. O `mapa.json` guarda uma
    -- frase de direcao ("agil, com pausas naturais de conversa"), nao um
    -- enum. Fechar um dominio que nao existe inventaria uma taxonomia.
    estilo     text,
    idioma     text not null default 'pt-BR',
    provider   text,
    motor_id   uuid references public.criativo_motor(id),
    fonte      text not null,
    ativo      boolean not null default true,

    constraint criativo_voz_slug_ux unique (slug)
);


-- =============================================================================
-- 7. GATE — o catalogo de portoes, e o resultado por peca
-- =============================================================================
-- Imagem e video executam gates com vocabularios diferentes: a PRENSA tem
-- `contrast`, `box_fit`, `clipping` com veredito `PIXEL_READY|REJECTED`; o
-- video tem ~34 checks com `PASS|WARN|FAIL`. O catalogo unifica a IDENTIDADE do
-- portao sem achatar o vocabulario do resultado.

create table if not exists public.criativo_gate (
    id         uuid primary key default gen_random_uuid(),
    slug       text not null,
    motor_id   uuid references public.criativo_motor(id),
    -- `pixel` (PRENSA), `tecnico` (ffprobe/audio/video), `visual` (modelo
    -- julgando quadro), `compliance` (ledger, licenca, disclosure).
    familia    text not null,
    midia      text not null,
    descricao  text not null,
    bloqueante boolean not null default true,
    fonte      text not null,

    constraint criativo_gate_slug_ux unique (slug, midia),
    constraint criativo_gate_familia_valida
        check (familia in ('pixel', 'tecnico', 'visual', 'compliance')),
    constraint criativo_gate_midia_valida check (midia in ('imagem', 'video', 'audio'))
);

-- O resultado do gate PARA UMA PECA. Append-only: um gate reexecutado gera
-- linha nova, porque "passou depois de falhar" e uma historia que importa.
create table if not exists public.criativo_master_gate (
    id           uuid primary key default gen_random_uuid(),
    master_id    uuid not null references public.criativo_master(id),
    gate_slug    text not null,
    resultado    text not null,
    detalhe      jsonb,
    -- Confianca do julgamento, quando o gate a reporta (o QA visual reporta).
    -- Regra B: ausencia e NULL, e `0.0` seria "medi e deu zero confianca".
    confianca    numeric(4, 3),
    executado_em timestamptz not null default now(),

    constraint criativo_master_gate_resultado_valido
        check (resultado in ('PASS', 'WARN', 'FAIL', 'SKIPPED',
                             'PIXEL_READY', 'REJECTED')),
    constraint criativo_master_gate_confianca_faixa
        check (confianca is null or (confianca >= 0 and confianca <= 1))
);

create index if not exists criativo_master_gate_master_ix
    on public.criativo_master_gate (master_id, executado_em desc);


-- =============================================================================
-- 8. DIREITOS — o ledger de insumos, que hoje so o video tem
-- =============================================================================
-- O `clips_registry.json` do motor de video ja carrega licenca, credito, url,
-- `commercial_ok`, `disclosure` e `synthid` por insumo. Imagem nao tem
-- equivalente, e precisa: uma peca `photo_preserved` usa foto real de pessoa.
--
-- ⚠️ `licenca` e `credito` sao TEXTO e nao enum, e isso e deliberado: a licenca
-- real de um arquivo da Wikimedia e uma string de SPDX ou uma frase de uso
-- editorial, e fechar esse dominio recusaria licenca legitima. O que e fechado
-- e `origem`, que tem dominio de verdade.

create table if not exists public.criativo_master_direito (
    id             uuid primary key default gen_random_uuid(),
    master_id      uuid not null references public.criativo_master(id),
    arquivo        text not null,
    papel          text,
    origem         text not null,
    fonte_externa  text,
    licenca        text,
    credito        text,
    url            text,
    -- ⚠️ TRES estados, e nao booleano: `null` significa "ninguem apurou", que e
    -- diferente de "apurei e NAO pode". O ledger real do `short_odete` tem
    -- `license: null` em 12 de 12 insumos — tratar isso como `false` bloquearia
    -- um build inteiro, e tratar como `true` autorizaria uso sem base.
    uso_comercial_ok boolean,
    disclosure     text,
    sintetico      boolean not null default false,
    nota           text,
    apurado_em     timestamptz,

    constraint criativo_direito_origem_valida
        check (origem in ('gerado', 'humano', 'estoque', 'derivado', 'terceiro')),
    -- Regra A: afirmacao sobre direito carrega quando foi apurada.
    constraint criativo_direito_apuracao_com_carimbo
        check (uso_comercial_ok is null or apurado_em is not null)
);

create index if not exists criativo_direito_master_ix
    on public.criativo_master_direito (master_id);


-- =============================================================================
-- 9. BLINDAGEM DA v11_01 — os buracos que a auditoria de sete lentes achou
-- =============================================================================

-- 9.1 O job passa a apontar para um motor REGISTRADO
alter table public.criativo_job
    add column if not exists motor_id uuid references public.criativo_motor(id);

-- 9.2 O briefing aponta para um modo REGISTRADO
alter table public.criativo_briefing
    add column if not exists modo_id uuid references public.criativo_modo_de_producao(id);

-- 9.3 A aprovacao aponta para uma finalidade REGISTRADA
alter table public.criativo_aprovacao
    add column if not exists finalidade_id uuid references public.criativo_finalidade(id);

-- 9.4 A chave de storage tem forma, e a forma diz de onde o arquivo vem
--
-- Sem isto, um master com `storage_chave = 'fabrica/short_odete/video.mp4'`
-- seria assinado e servido como ativo proprio: o prefixo `fabrica/` e o que faz
-- o endpoint ler do disco da fabrica externa. Nao ha caminho de aplicacao que
-- gere isso hoje (a chave e sempre derivada do conteudo), mas a impossibilidade
-- dependia de o codigo nunca errar, e nao do banco recusar.
do $blindagem$
declare
    n_fora integer;
begin
    -- ⚠️ VALIDADA ou `NOT VALID`, conforme o que ja existe na tabela.
    --
    -- Uma `CHECK` comum falha o `ALTER` inteiro se UMA linha antiga a violar, e
    -- a mensagem que sai nao diz qual linha nem quantas. `scripts/provar-ciclo-v11.sh`
    -- pegou isso: o cluster de prova tem masters com chave historica e a
    -- migration abortava — em producao a tabela esta vazia e passaria, o que e
    -- pior, porque o defeito so apareceria no primeiro banco com historico.
    --
    -- `NOT VALID` protege TODA escrita nova e deixa o passado em paz, com a
    -- contagem dita em voz alta para alguem limpar. Proteger o futuro nao pode
    -- depender de o passado estar limpo.
    if not exists (select 1 from pg_constraint
                    where conname = 'criativo_master_storage_forma') then
        select count(*) into n_fora
          from public.criativo_master
         where storage_chave !~ '^criativos/[a-z0-9/_.-]+$';

        if n_fora = 0 then
            alter table public.criativo_master
                add constraint criativo_master_storage_forma
                check (storage_chave ~ '^criativos/[a-z0-9/_.-]+$');
        else
            alter table public.criativo_master
                add constraint criativo_master_storage_forma
                check (storage_chave ~ '^criativos/[a-z0-9/_.-]+$') not valid;
            raise notice
                'v11_02: % master(s) com storage_chave fora do prefixo `criativos/`. '
                'A guarda vale para toda escrita NOVA; as linhas antigas seguem como estao. '
                'Depois de limpar, rode: ALTER TABLE public.criativo_master VALIDATE CONSTRAINT criativo_master_storage_forma;',
                n_fora;
        end if;
    end if;

    -- 9.5 A rendition nao pode concluir antes de comecar.
    if not exists (select 1 from pg_constraint
                    where conname = 'criativo_rendition_ordem_temporal') then
        alter table public.criativo_rendition
            add constraint criativo_rendition_ordem_temporal
            check (concluida_em is null or iniciada_em is null
                   or concluida_em >= iniciada_em);
    end if;

    -- 9.6 Uma peca `pronta` nao carrega erro pendurado.
    --
    -- `apresentacao.rendition_dto` monta o bloco de erro olhando so
    -- `erro_codigo`: a tela mostraria a imagem E o erro na mesma peca.
    if not exists (select 1 from pg_constraint
                    where conname = 'criativo_rendition_pronta_sem_erro') then
        alter table public.criativo_rendition
            add constraint criativo_rendition_pronta_sem_erro
            check (estado <> 'pronta' or erro_codigo is null);
    end if;

    -- 9.7 Um master nao e a propria raiz.
    if not exists (select 1 from pg_constraint
                    where conname = 'criativo_master_raiz_e_outro') then
        alter table public.criativo_master
            add constraint criativo_master_raiz_e_outro
            check (raiz_id is null or raiz_id <> id);
    end if;

    -- 9.8 A chave de idempotencia da entrega tem forma, como a do job.
    --
    -- `criativo_job_idem_forma` exige 16 caracteres; a entrega nao exigia nada,
    -- e o indice de sucesso unico e sobre `(idempotency_key, operacao)`. Chave
    -- de uma letra colide, e uma colisao aqui e uma entrega adotando o recibo
    -- de outra.
    if not exists (select 1 from pg_constraint
                    where conname = 'criativo_entrega_idem_forma') then
        alter table public.criativo_entrega
            add constraint criativo_entrega_idem_forma
            check (length(idempotency_key) >= 16);
    end if;
end
$blindagem$;

-- 9.9 A imutabilidade do master cobre a DECLARACAO, nao so o conteudo
--
-- A v11_01 protegia 6 colunas. A auditoria reescreveu `sintetico`, `disclosure`,
-- `projeto_id`, `mime`, `largura` e `slot` num master COM APROVACAO VIGENTE, num
-- unico UPDATE. O dano concreto: `sintetico=false` mais `disclosure=null` remove
-- a divulgacao de conteudo gerado por IA que a SPEC secao 15 exige, DEPOIS de
-- aprovado, sem tocar no hash — a assinatura continua batendo.
create or replace function public.criativo_master_imutavel()
returns trigger
language plpgsql
as $$
begin
    if new.storage_chave is distinct from old.storage_chave
       or new.content_hash is distinct from old.content_hash
       or new.motor is distinct from old.motor
       or new.motor_versao is distinct from old.motor_versao
       or new.insumo_hash is distinct from old.insumo_hash
       or new.versao is distinct from old.versao
       -- acrescentados em v11_02:
       or new.projeto_id is distinct from old.projeto_id
       or new.job_id is distinct from old.job_id
       or new.slot is distinct from old.slot
       or new.kind is distinct from old.kind
       or new.mime is distinct from old.mime
       or new.sintetico is distinct from old.sintetico
       or new.disclosure is distinct from old.disclosure
    then
        raise exception
            'criativo_master %: conteudo, procedencia e declaracao sao imutaveis. Crie uma versao nova (versao=%).',
            old.id, old.versao + 1
            using errcode = 'integrity_constraint_violation';
    end if;

    -- Medida so pode ser PREENCHIDA, nunca reescrita: medir depois e legitimo,
    -- trocar a medida de um arquivo que nao mudou nao e.
    if (old.largura is not null and new.largura is distinct from old.largura)
       or (old.altura is not null and new.altura is distinct from old.altura)
       or (old.bytes_totais is not null and new.bytes_totais is distinct from old.bytes_totais)
       or (old.duracao_ms is not null and new.duracao_ms is distinct from old.duracao_ms)
    then
        raise exception
            'criativo_master %: medida ja registrada nao se reescreve. O arquivo nao mudou.',
            old.id
            using errcode = 'integrity_constraint_violation';
    end if;

    if new.arquivado_em is not null and old.arquivado_em is null then
        if exists (
            select 1 from public.criativo_aprovacao a
            where a.subject_tipo = 'master'
              and a.subject_id = old.id
              and a.decisao = 'aprovado'
              and a.revogada_em is null
        ) then
            raise exception
                'criativo_master %: nao arquiva master com aprovacao vigente. Revogue a aprovacao antes.',
                old.id
                using errcode = 'integrity_constraint_violation';
        end if;
    end if;

    return new;
end;
$$;

-- 9.10 A aprovacao de PACOTE tambem passa por gatilho
--
-- O gatilho da v11_01 saia cedo quando `subject_tipo <> 'master'`, entao
-- `subject_tipo='pacote'` com `subject_id` inexistente era ACEITO — e a
-- aprovacao de pacote e justamente a que `criativo_entrega` consome.
create or replace function public.criativo_aprovacao_subject_existe()
returns trigger
language plpgsql
as $$
begin
    if new.subject_tipo = 'master' then
        if not exists (select 1 from public.criativo_master m where m.id = new.subject_id) then
            raise exception 'criativo_aprovacao: master % nao existe', new.subject_id
                using errcode = 'foreign_key_violation';
        end if;
    elsif new.subject_tipo = 'pacote' then
        if not exists (select 1 from public.criativo_pacote p where p.id = new.subject_id) then
            raise exception 'criativo_aprovacao: pacote % nao existe', new.subject_id
                using errcode = 'foreign_key_violation';
        end if;
    end if;
    return new;
end;
$$;

drop trigger if exists criativo_aprovacao_subject_existe_tg on public.criativo_aprovacao;
create trigger criativo_aprovacao_subject_existe_tg
    before insert on public.criativo_aprovacao
    for each row execute function public.criativo_aprovacao_subject_existe();

-- 9.11 A entrega so nasce sob aprovacao VIGENTE e POSITIVA do proprio pacote
--
-- A FK garantia existencia, nada mais. A auditoria inseriu uma entrega
-- `sucesso`, com recibo nulo, para um pacote em `rascunho`, autorizada por uma
-- aprovacao `rejeitado` cujo subject era um master. Aprovar A e aplicar B.
create or replace function public.criativo_entrega_autorizada()
returns trigger
language plpgsql
as $$
declare
    a record;
begin
    select decisao, revogada_em, subject_tipo, subject_id
      into a
      from public.criativo_aprovacao
     where id = new.autorizacao_id;

    if a is null then
        raise exception 'criativo_entrega: autorizacao % nao existe', new.autorizacao_id
            using errcode = 'foreign_key_violation';
    end if;
    if a.decisao <> 'aprovado' then
        raise exception
            'criativo_entrega: autorizacao esta como %, e entrega exige aprovacao', a.decisao
            using errcode = 'integrity_constraint_violation';
    end if;
    if a.revogada_em is not null then
        raise exception 'criativo_entrega: autorizacao foi revogada'
            using errcode = 'integrity_constraint_violation';
    end if;
    if a.subject_tipo <> 'pacote' or a.subject_id <> new.pacote_id then
        raise exception
            'criativo_entrega: a autorizacao nao e deste pacote (heranca vaga de aprovacao)'
            using errcode = 'integrity_constraint_violation';
    end if;
    return new;
end;
$$;

drop trigger if exists criativo_entrega_autorizada_tg on public.criativo_entrega;
create trigger criativo_entrega_autorizada_tg
    before insert on public.criativo_entrega
    for each row execute function public.criativo_entrega_autorizada();


-- =============================================================================
-- 10. RLS, GRANTS E O FECHAMENTO DA PORTA (mesmo desenho da v11_01)
-- =============================================================================
-- O default ACL de `public` neste banco concede ALL em tabela nova para anon,
-- authenticated e service_role — medido em producao em 28/08/2026. Sem o REVOKE
-- alcancando `service_role`, o papel que a API usa sai com DELETE e TRUNCATE.

do $rls$
declare
    t text;
begin
    foreach t in array array[
        'criativo_motor', 'criativo_modo_de_producao', 'criativo_formato',
        'criativo_finalidade', 'criativo_exigencia_de_canal',
        'criativo_teto_combinado', 'criativo_skin', 'criativo_voz',
        'criativo_gate', 'criativo_master_gate', 'criativo_master_direito'
    ]
    loop
        execute format('alter table public.%I enable row level security', t);
        execute format('alter table public.%I force row level security', t);
        execute format(
            'revoke all on public.%I from public, anon, authenticated, service_role', t);
        execute format(
            'grant select, insert, update on public.%I to service_role', t);
    end loop;
end
$rls$;


-- =============================================================================
-- 11. SEED DO PARQUE — declarado, com fonte e data
-- =============================================================================
-- Regra E: `on conflict do update`. Reaplicar atualiza o parque, nao duplica.

insert into public.criativo_motor
    (slug, nome, produz, runtime, cofre_asset_id, provider, modelo,
     versao_do_adaptador, custo_referencia_usd, custo_unidade, custo_fonte,
     capacidades, fonte, verificado_em)
values
    ('gemini-imagem', 'Motor de imagem full_llm (Gemini)',
     array['imagem'], 'interno', 'asset:engine:image-volc',
     'google', 'gemini-3.1-flash-image', '1.0.0',
     0.039, 'imagem', 'volc-factory/contrato/motor/mapa.json::custos_referencia.SRC:geminiimg',
     '["composicao full_llm","proporcao nativa por formato","normalizacao para dimensao exata"]'::jsonb,
     'services/creative_engine/motores/gemini_imagem.py', now()),
    ('prensa', 'PRENSA — composicao deterministica',
     array['imagem'], 'servico', 'asset:engine:image-volc',
     null, null, null,
     null, null, null,
     '["tipografia real","layers","gates de pixel","ledger de variantes","zero provider"]'::jsonb,
     'docs/creative-engines/CATALOGO-PRENSA-E-MOTOR-IMAGEM.md', null),
    ('volc-factory', 'Motor de Video VOLC (fabrica externa)',
     array['video','audio'], 'observado', 'asset:engine:video-volc',
     null, null, null,
     null, null, null,
     '["1080x1920","narracao","QA tecnico","QA visual","ledger de direitos"]'::jsonb,
     'docs/creative-engines/CATALOGO-MOTOR-DE-VIDEO.md', null)
on conflict (slug) do update set
    nome = excluded.nome, produz = excluded.produz, runtime = excluded.runtime,
    cofre_asset_id = excluded.cofre_asset_id, provider = excluded.provider,
    modelo = excluded.modelo, versao_do_adaptador = excluded.versao_do_adaptador,
    custo_referencia_usd = excluded.custo_referencia_usd,
    custo_unidade = excluded.custo_unidade, custo_fonte = excluded.custo_fonte,
    capacidades = excluded.capacidades, fonte = excluded.fonte;

insert into public.criativo_modo_de_producao
    (slug, nome, descricao, exige_provider_de_imagem, renderer, estado_de_prova,
     prova, saidas_no_snapshot, fonte, ordem)
values
    ('full_llm', 'Geracao completa pelo modelo',
     'A peca inteira e composta pelo modelo, na proporcao pedida.',
     true, 'provider_de_imagem', 'implementado_no_volc',
     'Job real de 28/08/2026 com tres formatos e tres hashes distintos.',
     null, 'docs/creative-engines/ADR-001-SERVICO-CRIATIVO-VOLC.md', 10),
    ('typography_only', 'Tipografia sem imagem generativa',
     'PRENSA produz texto, formas e atmosfera sem provider de imagem.',
     false, 'prensa', 'executado_externo',
     'carrossel_produtividade_metodo90', 26,
     'docs/creative-engines/snapshots/motor-imagem-2026-08-26.json', 20),
    ('deterministic_graphics', 'Graficos deterministicos',
     'PRENSA combina texto com graficos SVG produzidos por codigo.',
     false, 'prensa', 'executado_externo', 'anderson_grafico', 13,
     'docs/creative-engines/snapshots/motor-imagem-2026-08-26.json', 30),
    ('prensa_hybrid', 'Cena por IA, acabamento pela PRENSA',
     'A IA produz a cena; a PRENSA controla texto, fonte, layers e gates.',
     true, 'provider_depois_prensa', 'executado_externo',
     'kintsugi_planejado e volcnews_iphone_laranja', 26,
     'docs/creative-engines/snapshots/motor-imagem-2026-08-26.json', 40),
    ('photo_preserved', 'Foto real preservada',
     'Uma foto real permanece como asset controlado e o anuncio e composto ao redor dela.',
     false, 'positivo_photo', 'componentes_observados',
     'Preservacao de foto observada no Positivo; adaptador combinado pendente.',
     null, 'docs/creative-engines/PACOTE-REUSO-MOTOR-IMAGEM.json', 50),
    ('full_llm_then_prensa', 'Geracao completa promovida a acabamento',
     'Uma peca full_llm aprovada vira asset rastreado para acabamento PRENSA.',
     true, 'provider_depois_prensa', 'planejado',
     'Os dois componentes existem separados; a combinacao nao foi executada.',
     null, 'docs/creative-engines/ADR-001-SERVICO-CRIATIVO-VOLC.md', 60),
    ('observado', 'Build observado de fabrica externa',
     'O VOLC O.S. le um build que ja existia. Ele nao renderizou a peca.',
     false, 'nenhum', 'implementado_no_volc',
     'short_odete lido em 27/08/2026 com sha256 batendo o freeze.json.',
     null, 'docs/creative-engines/ADR-002-INTEGRACAO-MOTOR-VIDEO.md', 70)
on conflict (slug) do update set
    nome = excluded.nome, descricao = excluded.descricao,
    exige_provider_de_imagem = excluded.exige_provider_de_imagem,
    renderer = excluded.renderer, estado_de_prova = excluded.estado_de_prova,
    prova = excluded.prova, saidas_no_snapshot = excluded.saidas_no_snapshot,
    fonte = excluded.fonte, ordem = excluded.ordem;

insert into public.criativo_formato
    (slot, rotulo, proporcao, largura, altura, tipo_de_asset, midia, descricao,
     destinos_tipicos, fonte, ordem)
values
    ('1x1', 'Quadrado', '1:1', 1080, 1080, 'imagem_marketing_quadrada', 'imagem',
     'Feed quadrado e display quadrado.',
     array['google_display','meta_feed','instagram_organic'],
     'backend/app/criativo/dominio.py::FORMATOS', 10),
    ('4x5', 'Retrato', '4:5', 1080, 1350, 'imagem_marketing_retrato', 'imagem',
     'Ocupa mais altura no feed sem entrar em tela cheia.',
     array['meta_feed','instagram_organic'],
     'backend/app/criativo/dominio.py::FORMATOS', 20),
    ('9x16', 'Vertical', '9:16', 1080, 1920, 'imagem_marketing_retrato_alto', 'imagem',
     'Tela cheia de stories, reels e shorts.',
     array['meta_stories_reels','youtube_shorts'],
     'backend/app/criativo/dominio.py::FORMATOS', 30),
    ('1.91x1', 'Paisagem', '1.91:1', 1200, 628, 'imagem_marketing', 'imagem',
     'Imagem de marketing paisagem do Display.',
     array['google_display','meta_feed'],
     'backend/app/criativo/dominio.py::FORMATOS', 40),
    ('16x9', 'Paisagem larga', '16:9', 1920, 1080, 'imagem_marketing', 'imagem',
     'Paisagem larga; presente nos dois estudios externos.',
     array['google_display','youtube'],
     'positivo-ad-studio/backend/app/agents/orchestrator.py:104-119', 50),
    ('3x4', 'Retrato suave', '3:4', 1080, 1440, 'imagem_marketing_retrato', 'imagem',
     'Retrato menos alto que 4:5.', array['meta_feed'],
     'positivo-ad-studio/backend/app/agents/orchestrator.py:104-119', 60),
    ('video-9x16', 'Video vertical', '9:16', 1080, 1920, 'video', 'video',
     'Envelope comprovado do motor de video: 38 MP4, todos 1080x1920 a 30fps.',
     array['youtube_shorts','meta_stories_reels'],
     'docs/creative-engines/snapshots/motor-video-2026-08-26.json', 70)
on conflict (slot) do update set
    rotulo = excluded.rotulo, proporcao = excluded.proporcao,
    largura = excluded.largura, altura = excluded.altura,
    tipo_de_asset = excluded.tipo_de_asset, midia = excluded.midia,
    descricao = excluded.descricao, destinos_tipicos = excluded.destinos_tipicos,
    fonte = excluded.fonte, ordem = excluded.ordem;

insert into public.criativo_finalidade (slug, nome, descricao, classe, ordem)
values
    ('interno', 'Uso interno',
     'Autoriza a peca dentro da casa. NAO autoriza gasto nem publicacao.', 'interna', 10),
    ('google_display', 'Google Display', 'Midia paga em Display.', 'midia_paga', 20),
    ('google_demand_gen', 'Google Demand Gen', 'Midia paga em Demand Gen.', 'midia_paga', 30),
    ('google_performance_max', 'Performance Max', 'Midia paga em PMax.', 'midia_paga', 40),
    ('meta_feed', 'Meta feed', 'Midia paga no feed da Meta.', 'midia_paga', 50),
    ('meta_stories_reels', 'Meta stories e reels', 'Midia paga vertical na Meta.', 'midia_paga', 60),
    ('instagram_organic', 'Instagram organico', 'Publicacao organica.', 'organica', 70),
    ('youtube_shorts', 'YouTube Shorts', 'Publicacao vertical organica.', 'organica', 80),
    ('manual_export', 'Exportacao manual', 'Download para uso fora do sistema.', 'exportacao', 90)
on conflict (slug) do update set
    nome = excluded.nome, descricao = excluded.descricao,
    classe = excluded.classe, ordem = excluded.ordem;

-- Vozes e skins do motor de video, do `contrato/motor/mapa.json` v1.2.1.
insert into public.criativo_voz (slug, voice_id, fallbacks, estilo, idioma, provider, fonte)
values
    ('VOZ:fofoqueira-natural','Aoede','{}',null,'pt-BR','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:amigo-contador','Charon','{}',null,'pt-BR','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:documentarista-grave','Charon','{}',null,'pt-BR','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:leiloeiro-contido','Fenrir','{}',null,'pt-BR','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:ancora-urgente','Fenrir','{}',null,'pt-BR','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:mistica','Vindemiatrix','{}',null,'pt-BR','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:sussurro-confissao','Sulafat','{}',null,'pt-BR','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:narrador-esportivo','Fenrir','{}',null,'pt-BR','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:documentarista-en','Charon','{}',null,'en','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:documentarista-es','Charon','{}',null,'es','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:fofoqueira-es','Aoede','{}',null,'es','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:fofoqueira-en','Aoede','{}',null,'en','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:amigo-contador-es','Charon','{}',null,'es','gemini','volc-factory/contrato/motor/mapa.json'),
    ('VOZ:amigo-contador-en','Charon','{}',null,'en','gemini','volc-factory/contrato/motor/mapa.json')
on conflict (slug) do update set
    voice_id = excluded.voice_id, idioma = excluded.idioma,
    provider = excluded.provider, fonte = excluded.fonte;

insert into public.criativo_skin (slug, nicho, arco, papeis_obrigatorios, fonte)
values
    ('gossip','novela',
     array['hook','contexto','virada','segredo','suspeitos/opcoes','revelacao','payoff+cta'],
     array['hook','revelacao','payoff+cta'],'volc-factory/contrato/motor/mapa.json'),
    ('corta','cinema-classico',
     array['hook','ficha-do-caso','escala','dilema-moral','prova-real','consequencia','legado','payoff-still','corta+cta'],
     array['hook','prova-real','corta+cta'],'volc-factory/contrato/motor/mapa.json'),
    ('holerite','dinheiro','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('arquivo','historia-absurda','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('main','ent-news','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('esoterico','esoterico','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('lendas','terror-folclore','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('copa','futebol','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('achadinhos','achadinhos','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('tribunalzap','justica-zap','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('relatoproibido','relato','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('cartasperdidas','cartas','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('causafamilia','familia','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('brigaestado','briga-consumidor','{}','{}','volc-factory/contrato/motor/mapa.json'),
    ('promo','promo','{}','{}','volc-factory/contrato/motor/mapa.json')
on conflict (slug) do update set
    nicho = excluded.nicho, fonte = excluded.fonte;

-- O motor de cada skin e voz, resolvido depois do seed dos motores.
update public.criativo_skin s set motor_id = m.id
  from public.criativo_motor m where m.slug = 'volc-factory' and s.motor_id is null;
update public.criativo_voz v set motor_id = m.id
  from public.criativo_motor m where m.slug = 'volc-factory' and v.motor_id is null;

-- Gates: PRENSA (pixel) e motor de video (tecnico/visual/compliance).
insert into public.criativo_gate (slug, familia, midia, descricao, bloqueante, fonte)
values
    ('contrast','pixel','imagem','Contraste minimo do texto contra o fundo.',true,
     'motor-imagem/contrato/saida/provas/*.pixelgate.json'),
    ('box_fit','pixel','imagem','O texto cabe na caixa planejada.',true,
     'motor-imagem/contrato/saida/provas/*.pixelgate.json'),
    ('clipping','pixel','imagem','Nada foi cortado na borda.',true,
     'motor-imagem/contrato/saida/provas/*.pixelgate.json'),
    ('resolucao','tecnico','video','Resolucao do arquivo final.',true,'volc-factory/pipeline/qa.py'),
    ('fps','tecnico','video','Quadros por segundo.',true,'volc-factory/pipeline/qa.py'),
    ('codec','tecnico','video','Codec de video e audio.',true,'volc-factory/pipeline/qa.py'),
    ('audio_sr','tecnico','video','Taxa de amostragem do audio.',true,'volc-factory/pipeline/qa.py'),
    ('duracao','tecnico','video','Duracao total.',true,'volc-factory/pipeline/qa.py'),
    ('loudness_integrado','tecnico','video','Volume integrado.',true,'volc-factory/pipeline/qa.py'),
    ('true_peak','tecnico','video','Pico real do audio.',true,'volc-factory/pipeline/qa.py'),
    ('black_frames','tecnico','video','Quadros pretos.',true,'volc-factory/pipeline/qa.py'),
    ('freeze_frames','tecnico','video','Imagem congelada.',true,'volc-factory/pipeline/qa.py'),
    ('gap_de_voz','tecnico','video','Silencio no meio da narracao.',true,'volc-factory/pipeline/qa.py'),
    ('hook_video_min','tecnico','video','Duracao minima do gancho.',true,'volc-factory/pipeline/qa.py'),
    ('cobertura_legendas','tecnico','video','Cobertura das legendas.',true,'volc-factory/pipeline/qa.py'),
    ('card_sobre_rosto','tecnico','video','Card cobrindo rosto.',true,'volc-factory/pipeline/qa.py'),
    ('ledger_broll','compliance','video','B-roll com uso comercial declarado.',true,'volc-factory/pipeline/qa.py'),
    ('ledger_credit','compliance','video','Still editorial com credito.',true,'volc-factory/pipeline/qa.py'),
    ('legenda_cortada','visual','video','Legenda decapitada no quadro.',false,'volc-factory/pipeline/qa_visual.py'),
    ('texto_sobre_rosto','visual','video','Texto sobre o rosto.',false,'volc-factory/pipeline/qa_visual.py'),
    ('emoji_errado','visual','video','Emoji fora de contexto.',false,'volc-factory/pipeline/qa_visual.py'),
    ('selo_cortado','visual','video','Selo cortado na borda.',false,'volc-factory/pipeline/qa_visual.py'),
    ('texto_ilegivel','visual','video','Texto ilegivel no quadro.',false,'volc-factory/pipeline/qa_visual.py'),
    ('artefato_ia','visual','video','Artefato visivel de geracao por IA.',false,'volc-factory/pipeline/qa_visual.py'),
    ('ui_occlusion','visual','video','Elemento na zona da interface da plataforma.',false,'volc-factory/pipeline/qa_visual.py'),
    ('rosto_inesperado','visual','video','Rosto onde nao deveria haver.',false,'volc-factory/pipeline/qa_visual.py'),
    ('hook_weak','visual','video','Gancho fraco no primeiro quadro.',false,'volc-factory/pipeline/qa_visual.py'),
    ('elemento_esperado','visual','video','O elemento planejado aparece.',false,'volc-factory/pipeline/qa_visual.py')
on conflict (slug, midia) do update set
    familia = excluded.familia, descricao = excluded.descricao,
    bloqueante = excluded.bloqueante, fonte = excluded.fonte;

update public.criativo_gate g set motor_id = m.id
  from public.criativo_motor m
 where g.motor_id is null
   and ((g.midia = 'video' and m.slug = 'volc-factory')
     or (g.familia = 'pixel' and m.slug = 'prensa'));

-- Exigencias por canal, de `volc_ads/criativo/requisitos.yaml`.
insert into public.criativo_exigencia_de_canal
    (canal, tipo_de_asset, quantidade_minima, quantidade_maxima, quantidade_recomendada,
     proporcao_alvo, largura_minima, altura_minima, largura_recomendada, altura_recomendada,
     bytes_maximos, mimes_aceitos, duracao_minima_s, caracteres_maximos,
     caracteres_de_pelo_menos_um, provisorio, fonte_dos_numeros)
values
    ('DISPLAY','imagem_marketing',1,15,null,'1.91:1',600,314,null,null,null,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DISPLAY','imagem_marketing_quadrada',1,15,null,'1:1',300,300,null,null,null,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DISPLAY','logo_quadrado',0,5,1,'1:1',128,128,null,null,null,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DISPLAY','logo_paisagem',0,5,null,'4:1',512,128,null,null,null,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DISPLAY','headline',1,5,null,null,null,null,null,null,null,'{}',null,30,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DISPLAY','headline_longa',1,1,null,null,null,null,null,null,null,'{}',null,90,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DISPLAY','descricao',1,5,null,null,null,null,null,null,null,'{}',null,90,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DEMAND_GEN','imagem_marketing',0,20,null,'1.91:1',600,314,1200,628,5242880,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DEMAND_GEN','imagem_marketing_quadrada',0,20,null,'1:1',300,300,1200,1200,5242880,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DEMAND_GEN','imagem_marketing_retrato',0,20,null,'4:5',480,600,960,1200,5242880,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DEMAND_GEN','imagem_marketing_retrato_alto',0,20,null,'9:16',600,1067,1080,1920,5242880,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DEMAND_GEN','logo_quadrado',1,5,null,'1:1',144,144,null,null,153600,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('DEMAND_GEN','video',0,5,null,null,null,null,null,null,null,array['video/mp4','video/mpeg'],5.0,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('PERFORMANCE_MAX','imagem_marketing',1,20,null,'1.91:1',600,314,1200,628,5242880,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('PERFORMANCE_MAX','imagem_marketing_quadrada',1,20,null,'1:1',300,300,1200,1200,5242880,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('PERFORMANCE_MAX','logo_quadrado',1,5,null,'1:1',128,128,null,null,5242880,'{}',null,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('PERFORMANCE_MAX','video',0,15,null,null,null,null,null,null,null,'{}',10.0,null,null,true,'volc_ads/criativo/requisitos.yaml'),
    ('PERFORMANCE_MAX','descricao',2,5,null,null,null,null,null,null,null,'{}',null,90,60,true,'volc_ads/criativo/requisitos.yaml')
on conflict (canal, tipo_de_asset) do update set
    quantidade_minima = excluded.quantidade_minima,
    quantidade_maxima = excluded.quantidade_maxima,
    quantidade_recomendada = excluded.quantidade_recomendada,
    proporcao_alvo = excluded.proporcao_alvo,
    largura_minima = excluded.largura_minima, altura_minima = excluded.altura_minima,
    largura_recomendada = excluded.largura_recomendada,
    altura_recomendada = excluded.altura_recomendada,
    bytes_maximos = excluded.bytes_maximos, mimes_aceitos = excluded.mimes_aceitos,
    duracao_minima_s = excluded.duracao_minima_s,
    caracteres_maximos = excluded.caracteres_maximos,
    caracteres_de_pelo_menos_um = excluded.caracteres_de_pelo_menos_um,
    fonte_dos_numeros = excluded.fonte_dos_numeros;

insert into public.criativo_teto_combinado (canal, rotulo, tipos, minimo, maximo, fonte)
values
    ('DISPLAY','imagens de marketing',
     array['imagem_marketing','imagem_marketing_quadrada'],1,15,'volc_ads/criativo/requisitos.yaml'),
    ('DISPLAY','logos',array['logo_quadrado','logo_paisagem'],0,5,'volc_ads/criativo/requisitos.yaml'),
    ('DEMAND_GEN','imagens em todas as orientacoes',
     array['imagem_marketing','imagem_marketing_quadrada','imagem_marketing_retrato','imagem_marketing_retrato_alto'],
     1,20,'volc_ads/criativo/requisitos.yaml')
on conflict (canal, rotulo) do update set
    tipos = excluded.tipos, minimo = excluded.minimo,
    maximo = excluded.maximo, fonte = excluded.fonte;


-- =============================================================================
-- 12. VERIFICACAO EMBUTIDA
-- =============================================================================
do $verifica$
declare
    n_tab integer; n_sem_rls integer; n_extra integer;
    n_motor integer; n_modo integer; n_formato integer; n_finalidade integer;
    n_skin integer; n_voz integer; n_gate integer; n_exig integer;
begin
    select count(*) into n_tab from pg_tables
     where schemaname='public' and tablename like 'criativo_%';
    select count(*) into n_sem_rls
      from pg_class c join pg_namespace n on n.oid=c.relnamespace
     where n.nspname='public' and c.relname like 'criativo_%' and c.relkind='r'
       and (not c.relrowsecurity or not c.relforcerowsecurity);
    select count(*) into n_extra
      from information_schema.role_table_grants g
     where g.table_schema='public' and g.table_name like 'criativo_%'
       and g.grantee='service_role'
       and g.privilege_type not in ('SELECT','INSERT','UPDATE');

    select count(*) into n_motor from public.criativo_motor;
    select count(*) into n_modo from public.criativo_modo_de_producao;
    select count(*) into n_formato from public.criativo_formato;
    select count(*) into n_finalidade from public.criativo_finalidade;
    select count(*) into n_skin from public.criativo_skin;
    select count(*) into n_voz from public.criativo_voz;
    select count(*) into n_gate from public.criativo_gate;
    select count(*) into n_exig from public.criativo_exigencia_de_canal;

    if n_tab <> 21 then
        raise exception 'v11_02: esperava 21 tabelas criativo_* (10 da v11_01 + 11), achei %', n_tab;
    end if;
    if n_sem_rls <> 0 then
        raise exception 'v11_02: % tabela(s) sem RLS ligada E forcada', n_sem_rls;
    end if;
    if n_extra <> 0 then
        raise exception 'v11_02: service_role com % privilegio(s) alem de SELECT/INSERT/UPDATE', n_extra;
    end if;
    if n_motor < 3 or n_modo < 7 or n_formato < 7 or n_finalidade < 9
       or n_skin < 15 or n_voz < 14 or n_gate < 28 or n_exig < 18 then
        raise exception
            'v11_02: seed incompleto (motor=% modo=% formato=% finalidade=% skin=% voz=% gate=% exigencia=%)',
            n_motor, n_modo, n_formato, n_finalidade, n_skin, n_voz, n_gate, n_exig;
    end if;

    raise notice
        'v11_02 OK: 21 tabelas, RLS forcada, service_role restrito. Parque: % motores, % modos, % formatos, % finalidades, % skins, % vozes, % gates, % exigencias.',
        n_motor, n_modo, n_formato, n_finalidade, n_skin, n_voz, n_gate, n_exig;
end
$verifica$;

commit;
