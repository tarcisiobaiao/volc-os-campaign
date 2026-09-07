-- =============================================================================
-- v11_04 — IMPORTAR NAO E PRODUZIR, E TAMBEM NAO E OBSERVAR
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin.
-- ⚠️ NAO APLICADA EM PRODUCAO. Ver `supabase/migrations/README.md`.
-- ORDEM: DEPOIS da v11_01 (referencia `criativo_job` e `criativo_briefing`).
--        Independente da v11_02 e da v11_03.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTA MIGRATION RESOLVE
-- -----------------------------------------------------------------------------
-- A regra F do cabecalho da v11_01 abriu duas procedencias de execucao:
--
--     `volc_os`    -> nos rodamos um motor, e pagamos por isso
--     `observado`  -> lemos um build que JA EXISTIA no nosso pipeline
--
-- Um arquivo que um operador subiu do proprio computador nao e nenhum dos dois.
-- Nao rodamos motor nenhum (entao `volc_os` seria custo e autoria inventados) e
-- nao ha build para observar (entao `observado` seria procedencia externa sem a
-- fabrica que a v11_01 descreve). Sem um terceiro valor, a lane de importacao
-- so tinha saidas erradas: mentir a autoria ou mentir a observacao.
--
-- `importado` e esse terceiro valor. Ele NAO afrouxa nada: herda as DUAS
-- travas de custodia que `observado` ja tinha.
--
-- -----------------------------------------------------------------------------
-- POR QUE CADA PASSO E SEGURO
-- -----------------------------------------------------------------------------
-- 1. TROCA DE CHECK EM `criativo_job.procedencia_execucao`.
--    A CHECK nova aceita `('volc_os','observado','importado')` — um
--    SUPERCONJUNTO ESTRITO do dominio antigo `('volc_os','observado')`. Toda
--    linha que passava na CHECK velha passa na nova por construcao, entao o
--    `alter table ... add constraint` nao pode falhar por dado existente e nao
--    ha janela em que a tabela fique sem trava: o `drop` e o `add` estao na
--    MESMA transacao, e um `ACCESS EXCLUSIVE` cobre os dois.
--
--    O `drop` e da CONSTRAINT, nao de dados. Nenhuma linha e tocada.
--
-- 2. AS DUAS TRAVAS DE CUSTODIA, ESPELHADAS.
--    `criativo_job_observado_sem_custo_proprio` (v11_01:296-297) e
--    `criativo_job_observado_com_origem` (v11_01:299-301) sao o que impede um
--    job de fora declarar gasto nosso e procedencia sem prova. Elas citam
--    `'observado'` literalmente, entao um `importado` nasceria SEM elas — livre
--    para gravar `custo_real_usd` e `origem_externa is null`.
--
--    ⚠️ Constraints NOVAS, e nao edicao das antigas. Reescrever
--    `..._observado_...` para `procedencia_execucao not in ('observado',
--    'importado')` daria o mesmo efeito e apagaria o nome que a auditoria da
--    v11_01 procura. Duas constraints com nome proprio dizem qual procedencia
--    falhou na mensagem do erro; uma constraint generica diz "alguma".
--
-- 3. O BRIEFING.
--    `criativo_briefing_modo_valido` (v11_01:225-231) e um vocabulario fechado
--    de seis modos + `observado`. `criativo_briefing_formatos_nao_vazio`
--    (v11_01:232-234) exige pelo menos um formato, com `observado` como UNICA
--    excecao. Quem importa esta na mesma situacao do observado, e pela mesma
--    razao: ele nao PEDE formato, ele recebe o que o arquivo e. Medir a peca
--    depois e o unico jeito de saber a dimensao — pedir antes seria inventar.
--
--    As duas CHECKs sao superconjunto do dominio antigo. Mesmo argumento do 1.
--
-- 4. AS TABELAS NOVAS.
--    `create table if not exists` — nao derruba nada. `criativo_projeto.origem`
--    JA aceita `'importado'` desde a v11_01 (linha 186); nada a fazer la.
--
--    O lote leva `estado` e `motivo_recusa` ALEM do minimo pedido, e a razao
--    esta na coluna: um archive recusado nao gera entrada nenhuma, entao sem
--    estas duas colunas a recusa nao teria onde morar e a tela leria "lote sem
--    entradas" como "ainda processando".
--
--    `criativo_importacao_lote.job_id` e NULLABLE de proposito, e essa e a
--    decisao mais consequente do arquivo. Um ZIP com traversal e RECUSADO
--    INTEIRO: nenhum master nasce, nenhum job roda. Exigir `job_id` obrigaria a
--    lane a FABRICAR um job para poder registrar a recusa — um job que nao
--    executou nada, no mesmo ledger onde `criativo_job` significa "uma
--    execucao". A auditoria da tentativa recusada e mais valiosa que a coluna
--    NOT NULL, e a posse dela fica em `criado_por`.
--
-- 5. RLS E GRANTS.
--    Copia exata da forma da v11_01 secao 11 e da v11_03 secao 11: RLS LIGADA E
--    FORCADA, zero policies, REVOKE de todos (`service_role` INCLUSIVE — achado
--    H, o default ACL de `public` concede `arwdDxt` em toda tabela nova), GRANT
--    minimo de SELECT/INSERT/UPDATE. Sem DELETE e sem TRUNCATE: a trilha de uma
--    importacao recusada e exatamente o que alguem gostaria de apagar.
--
-- 6. O QUE ESTE ARQUIVO NAO TEM, E POR QUE.
--    Sem `\set` nem qualquer metacomando psql: a v11_03 usa `\set ON_ERROR_STOP`
--    e por isso exige runner psql (`SCHEMA-DEPLOY-MANIFEST` registra o risco em
--    `schema.safety`). Este arquivo roda tambem por SQL API bruto. O
--    `begin/commit` da o mesmo tudo-ou-nada.
--    Sem DROP de dado, sem TRUNCATE, sem rollback destrutivo embutido. Correcao
--    de dado real e forward, nunca `drop`+reapply.
-- =============================================================================

begin;

do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception 'v11_04 deve rodar como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
    if to_regclass('public.criativo_job') is null then
        raise exception 'v11_04 exige a v11_01 aplicada antes (criativo_job nao existe)';
    end if;
    if to_regclass('public.criativo_briefing') is null then
        raise exception 'v11_04 exige a v11_01 aplicada antes (criativo_briefing nao existe)';
    end if;
end
$guarda$;


-- =============================================================================
-- 1. A TERCEIRA PROCEDENCIA DE EXECUCAO
-- =============================================================================
-- Superconjunto do dominio antigo. Ver o passo 1 do cabecalho.

alter table public.criativo_job
    drop constraint if exists criativo_job_procedencia_valida;

alter table public.criativo_job
    add constraint criativo_job_procedencia_valida
    check (procedencia_execucao in ('volc_os', 'observado', 'importado'));


-- =============================================================================
-- 2. A CUSTODIA DO `importado`, ESPELHADA DO `observado`
-- =============================================================================
-- Sem estas duas, `importado` seria a procedencia MAIS FROUXA do sistema — o
-- oposto do que ela existe para ser.

alter table public.criativo_job
    drop constraint if exists criativo_job_importado_sem_custo_proprio;

-- Um arquivo que um humano subiu nao consumiu credito de provider nenhum.
-- Gravar `custo_real_usd` aqui contaminaria todo relatorio de custo de
-- producao com dinheiro que ninguem gastou.
alter table public.criativo_job
    add constraint criativo_job_importado_sem_custo_proprio
    check (procedencia_execucao <> 'importado' or custo_real_usd is null);

alter table public.criativo_job
    drop constraint if exists criativo_job_importado_com_origem;

-- De onde veio? Sem resposta, "importado" e so uma palavra: nao da para
-- distinguir um arquivo do cliente de um still baixado de um banco de imagens,
-- e essa distincao e exatamente a que o portao de direitos precisa fazer.
alter table public.criativo_job
    add constraint criativo_job_importado_com_origem
    check (procedencia_execucao <> 'importado' or origem_externa is not null);


-- =============================================================================
-- 3. O BRIEFING QUE NAO PEDE FORMATO
-- =============================================================================

alter table public.criativo_briefing
    drop constraint if exists criativo_briefing_modo_valido;

alter table public.criativo_briefing
    add constraint criativo_briefing_modo_valido
    check (modo in ('typography_only', 'deterministic_graphics', 'full_llm',
                    'photo_preserved', 'prensa_hybrid', 'full_llm_then_prensa',
                    'observado', 'importado'));

alter table public.criativo_briefing
    drop constraint if exists criativo_briefing_formatos_nao_vazio;

-- `importado` entra ao lado de `observado` pela mesma razao: a dimensao e
-- MEDIDA nos bytes depois, e declara-la antes seria inventar o pedido.
alter table public.criativo_briefing
    add constraint criativo_briefing_formatos_nao_vazio
    check (modo in ('observado', 'importado')
           or jsonb_array_length(formatos_pedidos) >= 1);


-- =============================================================================
-- 4. O LOTE — uma tentativa de importacao, aceita ou recusada
-- =============================================================================
-- Ele existe para responder "o que o operador subiu, e o que aconteceu com
-- aquilo?" — inclusive quando a resposta e "nada entrou, o ZIP tinha symlink".

create table if not exists public.criativo_importacao_lote (
    id                    uuid primary key default gen_random_uuid(),
    -- NULLABLE. Ver o passo 4 do cabecalho: um lote recusado nao gera job, e
    -- fabricar um job vazio para satisfazer a coluna poluiria o ledger de
    -- execucoes com execucoes que nao existiram.
    job_id                uuid references public.criativo_job(id),
    -- A posse. Para lote SEM job, ela e a unica; para lote COM job, o job e a
    -- autoridade e esta coluna e a copia que permite filtrar sem embed.
    -- `text` e nao `uuid` porque o identificador do ator vem do JWT como
    -- string e o backend nao o reinterpreta.
    criado_por            text not null,
    origem                text not null,
    -- O nome que o operador viu no proprio computador. Metadado, nunca
    -- endereco: o caminho de armazenamento e opaco e deriva do hash.
    nome_arquivo_original text,
    -- Quanto ENTROU pela rede. Ausencia e NULL, nunca 0 (regra B da v11_01):
    -- um lote sem bytes medidos e diferente de um lote de zero byte, que nem
    -- chega a existir.
    bytes_comprimidos     bigint,
    entradas_total        integer,
    -- O desfecho do LOTE, DERIVADO das entradas no instante da importacao e
    -- congelado aqui.
    --
    -- ⚠️ A alternativa — derivar na leitura — perde exatamente o caso que mais
    -- importa: um ZIP com traversal e recusado INTEIRO e nao produz entrada
    -- nenhuma, entao `select ... from criativo_importacao_entrada` devolveria
    -- vazio e a tela nao saberia dizer se foi "recusado" ou "ainda nao chegou".
    -- O lote e um FATO HISTORICO; o estado dele foi calculado uma vez, por um
    -- escritor so, no unico instante em que era calculavel.
    estado                text not null,
    motivo_recusa         text,
    criado_em             timestamptz not null default now(),

    constraint criativo_importacao_lote_origem_valida
        check (origem in ('UPLOAD_INDIVIDUAL', 'UPLOAD_ZIP')),
    -- Mesmo vocabulario fechado da entrada. Ver a secao 5.
    constraint criativo_importacao_lote_estado_valido
        check (estado in ('RECEIVED', 'QUARANTINED', 'INSPECTED',
                          'IMPORTED_PRIVATE', 'POLICY_PENDING',
                          'READY_FOR_REGISTRATION', 'REJECTED',
                          'PARTIAL_BATCH')),
    -- Recusa sem motivo e o silencio que a SPEC proibe.
    constraint criativo_importacao_lote_recusado_com_motivo
        check (estado <> 'REJECTED' or motivo_recusa is not null),
    constraint criativo_importacao_lote_criado_por_nao_vazio
        check (btrim(criado_por) <> ''),
    constraint criativo_importacao_lote_bytes_medidos
        check (bytes_comprimidos is null or bytes_comprimidos > 0),
    constraint criativo_importacao_lote_entradas_nao_negativas
        check (entradas_total is null or entradas_total >= 0)
);

create index if not exists criativo_importacao_lote_dono_ix
    on public.criativo_importacao_lote (criado_por, criado_em desc);
create index if not exists criativo_importacao_lote_job_ix
    on public.criativo_importacao_lote (job_id);

comment on table public.criativo_importacao_lote is
    'Uma tentativa de importacao privada. Existe mesmo quando recusada: '
    'a recusa e o registro mais importante que ela produz.';


-- =============================================================================
-- 5. A ENTRADA — um arquivo dentro do lote, com desfecho PROPRIO
-- =============================================================================
-- Regra C da v11_01 aplicada ao intake: falha de uma peca nao contamina as
-- outras. Um ZIP de 10 imagens com 1 PDF disfarcado entrega 9 e registra 1
-- recusa NOMEADA — nunca 9 e silencio.

create table if not exists public.criativo_importacao_entrada (
    id                uuid primary key default gen_random_uuid(),
    lote_id           uuid not null references public.criativo_importacao_lote(id),
    indice            integer not null,
    -- O nome sanitizado do arquivo, para o humano reconhecer qual falhou.
    nome_normalizado  text,
    estado            text not null,
    -- O MIME lido dos BYTES. NULL quando a assinatura nao foi reconhecida —
    -- e "nao reconheci" e um fato diferente de "nao olhei".
    mime_detectado    text,
    -- Medida dos bytes FINAIS (ja saneados). Ausencia e NULL, nunca 0.
    bytes             bigint,
    content_hash      text,
    master_id         uuid references public.criativo_master(id),
    motivo_recusa     text,
    criado_em         timestamptz not null default now(),

    -- Uma entrada por posicao no lote. O indice e a identidade estavel do
    -- arquivo dentro da importacao, e reusa-lo faria duas recusas diferentes
    -- se confundirem na tela.
    constraint criativo_importacao_entrada_indice_ux unique (lote_id, indice),
    constraint criativo_importacao_entrada_indice_nao_negativo
        check (indice >= 0),
    -- Vocabulario FECHADO, identico ao de
    -- `backend/app/criativo/importacao.py::ESTADOS`, que por sua vez transcreve
    -- `SPEC.json -> media_contract.pipeline` + `.failures`.
    constraint criativo_importacao_entrada_estado_valido
        check (estado in ('RECEIVED', 'QUARANTINED', 'INSPECTED',
                          'IMPORTED_PRIVATE', 'POLICY_PENDING',
                          'READY_FOR_REGISTRATION', 'REJECTED',
                          'PARTIAL_BATCH')),
    constraint criativo_importacao_entrada_bytes_medidos
        check (bytes is null or bytes > 0),
    -- Mesma forma do `criativo_master.content_hash` (v11_01:416-417): hash sem
    -- algoritmo declarado e impossivel de migrar depois.
    constraint criativo_importacao_entrada_hash_forma
        check (content_hash is null or content_hash ~ '^sha256:[0-9a-f]{64}$'),
    -- Uma entrada recusada nao pode apontar para um master: seria dizer que o
    -- arquivo que nao entrou virou patrimonio.
    constraint criativo_importacao_entrada_recusada_sem_master
        check (estado <> 'REJECTED' or master_id is null),
    -- E uma entrada recusada tem de dizer POR QUE. Recusa sem motivo e o
    -- silencio que a SPEC proibe.
    constraint criativo_importacao_entrada_recusada_com_motivo
        check (estado <> 'REJECTED' or motivo_recusa is not null)
);

create index if not exists criativo_importacao_entrada_lote_ix
    on public.criativo_importacao_entrada (lote_id, indice);
create index if not exists criativo_importacao_entrada_hash_ix
    on public.criativo_importacao_entrada (content_hash);

comment on table public.criativo_importacao_entrada is
    'Um arquivo dentro de um lote de importacao, com desfecho proprio. '
    'Midia nao suportada e resultado POR ENTRADA, nunca silencio.';


-- =============================================================================
-- 6. RLS, GRANTS E O FECHAMENTO DA PORTA
-- =============================================================================
-- ⚠️ ACHADO H (24/08/2026): o default ACL de `public` neste banco concede
-- `arwdDxt` a anon, authenticated E service_role em TODA tabela nova. Por isso o
-- REVOKE inclui `service_role` — sem ele, o GRANT abaixo pareceria restringir e
-- so reafirmaria tres dos sete privilegios que a tabela ja nasceu tendo.

do $seguranca$
declare
    t text;
begin
    foreach t in array array[
        'criativo_importacao_lote', 'criativo_importacao_entrada'
    ]
    loop
        execute format('alter table public.%I enable row level security', t);
        execute format('alter table public.%I force row level security', t);
        execute format(
            'revoke all on public.%I from public, anon, authenticated, service_role', t);
        -- Sem DELETE e sem TRUNCATE para ninguem: a trilha de uma importacao
        -- recusada e justamente o que alguem gostaria de fazer sumir.
        execute format(
            'grant select, insert, update on public.%I to service_role', t);
    end loop;
end
$seguranca$;


-- =============================================================================
-- 7. VERIFICACAO EMBUTIDA
-- =============================================================================
-- Uma migration que aplica "sem erro" e deixa uma tabela sem RLS passa
-- despercebida ate a auditoria seguinte. Esta confere a si mesma.
--
-- ⚠️ O escopo do `like` e `criativo_importacao_%`, e nao `criativo_%`. A
-- verificacao da v11_01 conta 10 tabelas `criativo_*` e a da v11_02 conta 21:
-- uma contagem larga aqui quebraria as duas ou seria quebrada por elas na
-- proxima familia de tabelas. Cada migration verifica O QUE ELA CRIOU.

do $verifica$
declare
    n_tab       integer;
    n_rls       integer;
    n_pol       integer;
    n_anon      integer;
    n_extra     integer;
    n_proc      integer;
    n_modo      integer;
begin
    select count(*) into n_tab from pg_tables
     where schemaname = 'public' and tablename like 'criativo_importacao_%';

    select count(*) into n_rls
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relname like 'criativo_importacao_%'
       and c.relkind = 'r' and c.relrowsecurity and c.relforcerowsecurity;

    select count(*) into n_pol from pg_policies
     where schemaname = 'public' and tablename like 'criativo_importacao_%';

    select count(*) into n_anon from information_schema.role_table_grants
     where table_schema = 'public' and table_name like 'criativo_importacao_%'
       and grantee in ('anon', 'authenticated', 'PUBLIC');

    -- O conjunto EXATO do service_role, e nao "pelo menos". Ver v11_01 secao 12:
    -- conferir so o que foi concedido deixa passar o privilegio herdado do
    -- default ACL que ninguem pediu.
    select count(*) into n_extra from information_schema.role_table_grants
     where table_schema = 'public' and table_name like 'criativo_importacao_%'
       and grantee = 'service_role'
       and privilege_type not in ('SELECT', 'INSERT', 'UPDATE');

    -- As CHECKs alteradas existem E citam `importado`? Uma migration que
    -- "aplicou" sem trocar a CHECK deixaria a lane inteira gravando erro 23514
    -- em producao, e o sintoma apareceria como falha de aplicacao, nao de
    -- schema.
    select count(*) into n_proc from pg_constraint
     where conrelid = 'public.criativo_job'::regclass
       and conname in ('criativo_job_procedencia_valida',
                       'criativo_job_importado_sem_custo_proprio',
                       'criativo_job_importado_com_origem')
       and pg_get_constraintdef(oid) like '%importado%';

    select count(*) into n_modo from pg_constraint
     where conrelid = 'public.criativo_briefing'::regclass
       and conname in ('criativo_briefing_modo_valido',
                       'criativo_briefing_formatos_nao_vazio')
       and pg_get_constraintdef(oid) like '%importado%';

    if n_tab <> 2 then
        raise exception 'v11_04: esperava 2 tabelas criativo_importacao_*, achei %', n_tab;
    end if;
    if n_rls <> 2 then
        raise exception 'v11_04: RLS ligada E forcada em % de 2', n_rls;
    end if;
    if n_pol <> 0 then
        raise exception 'v11_04: esperava zero policies, achei %', n_pol;
    end if;
    if n_anon <> 0 then
        raise exception 'v11_04: anon/authenticated com % privilegio(s)', n_anon;
    end if;
    if n_extra <> 0 then
        raise exception
            'v11_04: service_role com % privilegio(s) alem de SELECT/INSERT/UPDATE', n_extra;
    end if;
    if n_proc <> 3 then
        raise exception
            'v11_04: esperava 3 CHECKs de job citando `importado`, achei %', n_proc;
    end if;
    if n_modo <> 2 then
        raise exception
            'v11_04: esperava 2 CHECKs de briefing citando `importado`, achei %', n_modo;
    end if;

    raise notice
        'v11_04 OK: 2 tabelas, RLS forcada, 0 policies, service_role restrito, '
        '3 CHECKs de job e 2 de briefing com `importado`.';
end
$verifica$;

commit;
