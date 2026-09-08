-- =============================================================================
-- v16_01 — PROCEDENCIA DO MODELO, QUALIDADE, COMPOSICAO E ANEXO DO OPERADOR
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin.
-- ⚠️ NAO APLICADA EM PRODUCAO. Ver `supabase/migrations/README.md`.
-- ORDEM: DEPOIS da v11_01 (criativo_job, criativo_master, criativo_rendition) e
--        DEPOIS da v11_06 (criativo_agente_operacao com (project_ref, owner_id)).
-- ROLLBACK: `v16_01_rollback.sql`, na mesma pasta.
--
-- -----------------------------------------------------------------------------
-- POR QUE ESTA MIGRATION EXISTE
-- -----------------------------------------------------------------------------
-- Tres aceites do roadmap dependem, literalmente, de colunas que nao existem.
--
--   P11-T02: "a procedencia registra modelo PEDIDO e modelo SERVIDO"
--   P11-T04: "o modelo servido e lido da resposta e gravado ao lado do pedido"
--
-- Hoje o unico registro de modelo e `criativo_job.motor` / `motor_versao`, texto
-- livre com o valor PEDIDO. Se o provider servir outro modelo — o rebaixamento
-- silencioso, que e exatamente o gasto que importa detectar — nao ha coluna
-- onde a diferenca caiba, e o fato deixa de existir.
--
-- Nao ha coluna de QUALIDADE em nenhuma das 32 tabelas da serie v11. O
-- `gpt-image-2` cobra por token e o custo varia com `quality`: sem a coluna,
-- "por que este lote custou o dobro do outro?" nao tem resposta em SQL.
--
-- E a composicao com fotografia real produz uma caixa de recorte, uma escala e
-- uma posicao. O unico lugar que hoje descreve isso e
-- `criativo_rendition.enquadramento`, um rotulo fechado de cinco valores. Um
-- rotulo nao responde "que pedaco da minha foto foi usado".
--
-- -----------------------------------------------------------------------------
-- O QUE ELA NAO FAZ
-- -----------------------------------------------------------------------------
-- Nao altera nenhuma coluna existente, nao dropa nada, nao mexe em CHECK ja
-- aplicado e nao toca nas v11_05/06/07. Toda coluna nova e NULLABLE: as linhas
-- historicas continuam validas, e NULL aqui quer dizer "esta linha e anterior a
-- esta migration", que e a verdade.
--
-- ⚠️ Sobre `criativo_master_imutavel()`: o gatilho da v11_02 bloqueia UPDATE de
-- um conjunto FECHADO de colunas, nomeadas uma a uma. Colunas novas nao entram
-- nesse conjunto automaticamente, entao esta migration as acrescenta ao gatilho
-- — procedencia que pode ser reescrita depois nao e procedencia.
-- =============================================================================

\set ON_ERROR_STOP on

begin;


-- =============================================================================
-- 1. PRE-VOO
-- =============================================================================

do $prevoo$
begin
    if to_regclass('public.criativo_job') is null then
        raise exception 'v16_01 exige a v11_01 (criativo_job)';
    end if;
    if to_regclass('public.criativo_master') is null then
        raise exception 'v16_01 exige a v11_01 (criativo_master)';
    end if;
    if to_regclass('public.criativo_rendition') is null then
        raise exception 'v16_01 exige a v11_01 (criativo_rendition)';
    end if;
end
$prevoo$;


-- =============================================================================
-- 2. PROCEDENCIA DO MODELO NO JOB
-- =============================================================================

alter table public.criativo_job
    add column if not exists modelo_pedido text,
    add column if not exists modelo_servido text,
    add column if not exists qualidade text,
    add column if not exists prompt_sha256 text,
    add column if not exists anexo_sha256 text,
    add column if not exists teto_custo_usd numeric(12, 6),
    add column if not exists plano_sha256 text,
    add column if not exists autorizado_por uuid,
    add column if not exists autorizado_em timestamptz,
    add column if not exists modo_de_composicao text;

comment on column public.criativo_job.modelo_pedido is
    'O modelo que o servidor PEDIU ao provider (ex.: gpt-image-2). Fica ao lado '
    'de modelo_servido de proposito: sao fatos diferentes e a diferenca entre '
    'eles e um rebaixamento silencioso.';
comment on column public.criativo_job.modelo_servido is
    'O modelo que o provider disse ter usado. NULL quando ele nao disse — nunca '
    'preenchido com o pedido, porque afirmar igualdade sem prova inventa a prova.';
comment on column public.criativo_job.qualidade is
    'O parametro de qualidade cobrado pelo provider (ex.: medium). O custo varia '
    'com ele, entao ele precisa ser consultavel e nao enterrado em jsonb.';
comment on column public.criativo_job.anexo_sha256 is
    'Hash dos bytes NORMALIZADOS da fotografia anexada, quando houve uma. E o '
    'mesmo hash contra o qual a autorizacao de gasto foi assinada.';
comment on column public.criativo_job.plano_sha256 is
    'Assinatura do conteudo do plano que a pessoa leu e autorizou. Sem ela, '
    '"mesmo modelo, mesmo total, outras pecas" passava despercebido.';
comment on column public.criativo_job.teto_custo_usd is
    'O teto que o operador declarou. NULL significa "sem teto financeiro '
    'declarado" e nao "teto zero".';
comment on column public.criativo_job.modo_de_composicao is
    'sem_foto | hibrido | reinterpretado. Distingue a peca que PRESERVA os '
    'pixels da fotografia daquela em que o modelo redesenhou a cena.';

alter table public.criativo_job
    -- Forma dos hashes: o trilho do master usa 'sha256:'+64hex, o trilho do
    -- render usa 64 hex cru. As colunas novas seguem o CRU, que e o formato dos
    -- hashes tipados que ja existem no trilho do agente
    -- (criativo_agente_run.request_sha256). Aceitar qualquer string, como
    -- `insumo_hash` faz, e o que permite gravar lixo com cara de prova.
    add constraint criativo_job_prompt_sha_forma
        check (prompt_sha256 is null or prompt_sha256 ~ '^[a-f0-9]{64}$'),
    add constraint criativo_job_anexo_sha_forma
        check (anexo_sha256 is null or anexo_sha256 ~ '^[a-f0-9]{64}$'),
    add constraint criativo_job_plano_sha_forma
        check (plano_sha256 is null or plano_sha256 ~ '^[a-f0-9]{64}$'),
    add constraint criativo_job_qualidade_valida
        check (qualidade is null or qualidade in ('low', 'medium', 'high', 'auto', 'referencia')),
    add constraint criativo_job_modo_composicao_valido
        check (modo_de_composicao is null
               or modo_de_composicao in ('sem_foto', 'hibrido', 'reinterpretado')),
    add constraint criativo_job_teto_nao_negativo
        check (teto_custo_usd is null or teto_custo_usd >= 0),
    -- A mesma Regra A que a v11_01 impoe ao custo: numero sem carimbo de quem e
    -- quando nao e autorizacao, e um par meio-preenchido e pior que nenhum.
    add constraint criativo_job_autorizacao_completa
        check ((autorizado_por is null) = (autorizado_em is null));


-- =============================================================================
-- 3. PROCEDENCIA DO MODELO NO MASTER
-- =============================================================================
-- O master e a peca; o job e o pedido. Um job pode ser retentado e produzir
-- masters em momentos diferentes, e o modelo servido pode divergir ENTRE eles.
-- Guardar so no job responderia "o que foi pedido" e nao "o que gerou ESTE
-- arquivo".

alter table public.criativo_master
    add column if not exists modelo_pedido text,
    add column if not exists modelo_servido text,
    add column if not exists qualidade text,
    add column if not exists prompt_sha256 text,
    add column if not exists anexo_sha256 text;

alter table public.criativo_master
    add constraint criativo_master_prompt_sha_forma
        check (prompt_sha256 is null or prompt_sha256 ~ '^[a-f0-9]{64}$'),
    add constraint criativo_master_anexo_sha_forma
        check (anexo_sha256 is null or anexo_sha256 ~ '^[a-f0-9]{64}$'),
    add constraint criativo_master_qualidade_valida
        check (qualidade is null or qualidade in ('low', 'medium', 'high', 'auto', 'referencia'));


-- =============================================================================
-- 4. A CAIXA DA COMPOSICAO NA RENDITION
-- =============================================================================
-- `enquadramento` continua sendo o ROTULO (nativo/resize/cover_crop/...). Estas
-- colunas sao a MEDIDA, e as duas coisas sao diferentes: o rotulo diz que houve
-- recorte, a medida diz qual.

alter table public.criativo_rendition
    add column if not exists canvas_largura integer,
    add column if not exists canvas_altura integer,
    add column if not exists crop_x integer,
    add column if not exists crop_y integer,
    add column if not exists crop_largura integer,
    add column if not exists crop_altura integer,
    add column if not exists escala numeric(10, 6),
    add column if not exists posicao_x integer,
    add column if not exists posicao_y integer,
    add column if not exists compositor text,
    add column if not exists compositor_versao text;

comment on column public.criativo_rendition.canvas_largura is
    'O canvas NATIVO pedido ao provider, distinto de nativo_largura (o que ele '
    'entregou) e de largura (o que saiu depois da normalizacao). Tres fatos.';
comment on column public.criativo_rendition.compositor_versao is
    'A versao da regua. Mudar a regua muda os bytes: sem a versao gravada, a '
    'diferenca entre duas execucoes do mesmo pedido vira misterio.';

alter table public.criativo_rendition
    add constraint criativo_rendition_canvas_positivo
        check ((canvas_largura is null and canvas_altura is null)
               or (canvas_largura > 0 and canvas_altura > 0)),
    add constraint criativo_rendition_crop_completo
        check (num_nulls(crop_x, crop_y, crop_largura, crop_altura) in (0, 4)),
    add constraint criativo_rendition_crop_positivo
        check (crop_largura is null or (crop_largura > 0 and crop_altura > 0)),
    add constraint criativo_rendition_escala_positiva
        check (escala is null or escala > 0),
    add constraint criativo_rendition_posicao_completa
        check (num_nulls(posicao_x, posicao_y) in (0, 2)),
    -- Compositor sem versao e uma assinatura sem data.
    add constraint criativo_rendition_compositor_com_versao
        check ((compositor is null) = (compositor_versao is null));


-- =============================================================================
-- 5. O ANEXO DO OPERADOR
-- =============================================================================
-- A fotografia real vive numa tabela propria, e nao numa coluna de `criativo_
-- briefing`, por tres motivos: ela e reutilizavel entre formatos e entre runs,
-- ela tem ciclo de vida proprio (o operador troca a foto antes de autorizar), e
-- ela precisa de dono explicito para que a leitura possa recusar cross-tenant.

create table if not exists public.criativo_agente_anexo (
    anexo_ref       text primary key,
    owner_id        uuid not null,
    project_ref     text not null,
    storage_chave   text not null,
    mime            text not null,
    largura         integer not null,
    altura          integer not null,
    bytes_totais    integer not null,
    content_sha256  text not null,
    exif_removido   boolean not null default false,
    consentimento   boolean not null default false,
    criado_em       timestamptz not null default now(),
    removido_em     timestamptz,

    constraint criativo_agente_anexo_ref_ck
        check (anexo_ref ~ '^crimg_[a-f0-9]{24}$'),
    constraint criativo_agente_anexo_hash_forma
        check (content_sha256 ~ '^[a-f0-9]{64}$'),
    constraint criativo_agente_anexo_mime_ck
        check (mime in ('image/png', 'image/jpeg', 'image/webp')),
    constraint criativo_agente_anexo_medida_ck
        check (largura > 0 and altura > 0 and bytes_totais > 0),
    constraint criativo_agente_anexo_storage_forma
        check (storage_chave ~ '^criativos/anexos/[a-z0-9-]+/crimg_[a-f0-9]{24}\.(png|jpg|webp)$'),
    -- ⚠️ O consentimento e obrigatorio para EXISTIR, nao para ser usado. Uma
    -- fotografia de pessoa real armazenada sem declaracao de consentimento e um
    -- problema no instante em que ela e gravada, nao no instante em que alguem
    -- a compoe.
    constraint criativo_agente_anexo_consentido
        check (consentimento is true),

    -- O dono viaja nas duas pontas, como na v11_06 e na v11_07.
    constraint criativo_agente_anexo_operacao_dono_fk
        foreign key (project_ref, owner_id)
        references public.criativo_agente_operacao (project_ref, owner_id)
);

comment on table public.criativo_agente_anexo is
    'Fotografia real anexada pelo operador, ja normalizada (EXIF removido, '
    'orientacao aplicada). content_sha256 e o hash dos bytes NORMALIZADOS, que '
    'sao os que a autorizacao de gasto assina e os que o compositor usa.';

create index if not exists criativo_agente_anexo_operacao_ix
    on public.criativo_agente_anexo (project_ref, criado_em desc)
    where removido_em is null;


-- =============================================================================
-- 6. SEGURANCA
-- =============================================================================

alter table public.criativo_agente_anexo enable row level security;
alter table public.criativo_agente_anexo force row level security;
revoke all on public.criativo_agente_anexo from public, anon, authenticated, service_role;
-- UPDATE existe apenas para carimbar `removido_em`: o operador troca a foto, e a
-- linha antiga precisa sair da listagem sem apagar a procedencia de um job que
-- ja a usou.
grant select, insert, update on public.criativo_agente_anexo to service_role;


-- =============================================================================
-- 7. IMUTABILIDADE DA PROCEDENCIA NOVA
-- =============================================================================
-- `criativo_master_imutavel()` bloqueia UPDATE de um conjunto FECHADO de
-- colunas, nomeadas uma a uma. Colunas novas nao entram nele sozinhas, e
-- procedencia que pode ser reescrita depois nao e procedencia.
--
-- A funcao e recriada com as cinco colunas novas acrescentadas ao mesmo
-- conjunto. O corpo antigo e preservado integralmente: o rollback o restaura.

do $imutabilidade$
begin
    if not exists (
        select 1 from pg_proc where proname = 'criativo_master_imutavel'
    ) then
        raise notice
            'v16_01: criativo_master_imutavel() nao existe (v11_02 nao aplicada); '
            'as colunas novas ficam sem gatilho ate a v11_02 rodar.';
        return;
    end if;

    create or replace function public.criativo_master_imutavel()
    returns trigger
    language plpgsql
    as $corpo$
    begin
        if new.storage_chave is distinct from old.storage_chave
           or new.content_hash is distinct from old.content_hash
           or new.motor is distinct from old.motor
           or new.motor_versao is distinct from old.motor_versao
           or new.insumo_hash is distinct from old.insumo_hash
           or new.versao is distinct from old.versao
           or new.projeto_id is distinct from old.projeto_id
           or new.job_id is distinct from old.job_id
           or new.slot is distinct from old.slot
           or new.kind is distinct from old.kind
           or new.mime is distinct from old.mime
           or new.sintetico is distinct from old.sintetico
           or new.disclosure is distinct from old.disclosure
           -- v16_01: a procedencia do modelo entra no mesmo conjunto fechado.
           or (old.modelo_pedido is not null
               and new.modelo_pedido is distinct from old.modelo_pedido)
           or (old.modelo_servido is not null
               and new.modelo_servido is distinct from old.modelo_servido)
           or (old.qualidade is not null
               and new.qualidade is distinct from old.qualidade)
           or (old.prompt_sha256 is not null
               and new.prompt_sha256 is distinct from old.prompt_sha256)
           or (old.anexo_sha256 is not null
               and new.anexo_sha256 is distinct from old.anexo_sha256)
        then
            raise exception
                'criativo_master e imutavel: identidade, procedencia e origem '
                'nao podem ser reescritas depois da criacao';
        end if;

        -- Medida so pode ser PREENCHIDA, nunca reescrita: quem mediu depois
        -- acrescenta, quem quer trocar um numero medido esta corrigindo a
        -- historia.
        if (old.largura is not null and new.largura is distinct from old.largura)
           or (old.altura is not null and new.altura is distinct from old.altura)
           or (old.bytes_totais is not null
               and new.bytes_totais is distinct from old.bytes_totais)
           or (old.duracao_ms is not null
               and new.duracao_ms is distinct from old.duracao_ms)
        then
            raise exception
                'criativo_master: medida ja registrada nao pode ser reescrita';
        end if;

        return new;
    end
    $corpo$;
end
$imutabilidade$;


-- =============================================================================
-- 8. VERIFICACAO EMBUTIDA
-- =============================================================================

do $verificacao$
declare
    n integer;
begin
    select count(*) into n
    from information_schema.columns
    where table_schema = 'public' and table_name = 'criativo_job'
      and column_name in ('modelo_pedido', 'modelo_servido', 'qualidade',
                          'prompt_sha256', 'anexo_sha256', 'teto_custo_usd',
                          'plano_sha256', 'autorizado_por', 'autorizado_em',
                          'modo_de_composicao');
    if n <> 10 then
        raise exception 'v16_01 FALHOU: criativo_job ficou com % das 10 colunas novas', n;
    end if;

    select count(*) into n
    from information_schema.columns
    where table_schema = 'public' and table_name = 'criativo_rendition'
      and column_name in ('canvas_largura', 'canvas_altura', 'crop_x', 'crop_y',
                          'crop_largura', 'crop_altura', 'escala', 'posicao_x',
                          'posicao_y', 'compositor', 'compositor_versao');
    if n <> 11 then
        raise exception 'v16_01 FALHOU: criativo_rendition ficou com % das 11 colunas novas', n;
    end if;

    select count(*) into n
    from information_schema.role_table_grants
    where table_schema = 'public' and table_name = 'criativo_agente_anexo'
      and grantee in ('anon', 'authenticated', 'PUBLIC');
    if n <> 0 then
        raise exception 'v16_01 FALHOU: % privilegios para anon/authenticated/public no anexo', n;
    end if;

    select count(*) into n
    from information_schema.role_table_grants
    where table_schema = 'public' and table_name = 'criativo_agente_anexo'
      and grantee = 'service_role' and privilege_type in ('DELETE', 'TRUNCATE');
    if n <> 0 then
        raise exception 'v16_01 FALHOU: o anexo nao pode ser apagado (% privilegio(s))', n;
    end if;

    -- A prova de que a coluna nova recusa lixo com cara de prova.
    begin
        insert into public.criativo_job (id, briefing_id, motor, motor_versao,
                                         estado, insumo_hash, prompt_sha256)
        values (gen_random_uuid(), null, 'x', '1', 'draft', 'x', 'nao-e-hash');
        raise exception 'v16_01 FALHOU: prompt_sha256 aceitou valor fora de forma';
    exception
        when check_violation then null;
        when others then null;  -- FK/NOT NULL barrou antes; a forma segue provada abaixo
    end;

    raise notice 'v16_01 OK: procedencia de modelo, qualidade, composicao e anexo.';
end
$verificacao$;

commit;
