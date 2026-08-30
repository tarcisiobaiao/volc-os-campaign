-- Provas de SEGURANÇA da v11_03 sob os papéis reais, executando de verdade.
--
-- ## Por que este arquivo existe (achado #10)
--
-- As provas de segurança do ciclo liam CATÁLOGO: contavam grants em
-- `information_schema.role_table_grants`, conferiam `relrowsecurity` e
-- `pg_policies`. Nenhuma delas executava um `select` como anon, um `delete` como
-- service_role, ou qualquer outra coisa sob o papel que a superfície real usa.
-- "RLS forçada protege" era uma afirmação sobre metadados.
--
-- Pior: o cluster descartável criava `service_role` SEM `BYPASSRLS`. Medido no
-- Supabase oficial em 2026-08-29, somente pelo catálogo e sem tocar em dado:
--
--     rolname       | rolsuper | rolbypassrls
--     anon          | f        | f
--     authenticated | f        | f
--     service_role  | f        | t      <-- ignora RLS
--
-- Ou seja: no cluster de prova o papel operacional ficava trancado pela própria
-- RLS e lia zero linhas, enquanto em produção ele atravessa a RLS inteira. A
-- prova antiga media um banco MAIS SEGURO que o real, e por isso não podia
-- reprovar nada. Aqui o papel privilegiado nasce com `BYPASSRLS`, como o de
-- verdade, e o que sobra protegendo as tabelas passa a ser visível: o GRANT.
--
-- ## As quatro respostas que estas provas separam
--
--   · "grant bloqueou"   -> erro 42501, a instrução nem chega à tabela;
--   · "RLS bloqueou"     -> SEM erro nenhum: o select devolve ZERO linhas, e o
--                           insert falha com 42501 citando row-level security;
--   · "gatilho recusou"  -> erro P0001 com a mensagem da guarda;
--   · "teste quebrado"   -> 42P01/42703/42601/42883 — tabela, coluna, sintaxe ou
--                           função que não existe. Isto NUNCA conta como verde.
--
-- A quarta é a que faz esta prova valer: um `recusa()` que aceita qualquer erro
-- passa igualmente quando o objeto sumiu, e aí ela mede o próprio typo.

\set ON_ERROR_STOP on

begin;

-- ── ferramenta ──────────────────────────────────────────────────────────────

-- SQLSTATEs que denunciam prova quebrada, jamais guarda funcionando.
create or replace function pg_temp.prova_quebrada(st text) returns boolean
language sql immutable as $$
    select st in ('42P01',  -- undefined_table
                  '42703',  -- undefined_column
                  '42601',  -- syntax_error
                  '42883',  -- undefined_function
                  '3F000',  -- invalid_schema_name
                  '42P02'); -- undefined_parameter
$$;

/* Executa `sql` sob `papel` e devolve o SQLSTATE ('00000' quando passa). */
create or replace function pg_temp.st_como(papel text, sql text) returns text
language plpgsql as $$
declare st text;
begin
    execute format('set role %I', papel);
    begin
        execute sql;
        st := '00000';
    exception when others then
        get stacked diagnostics st = returned_sqlstate;
    end;
    reset role;
    return st;
end;
$$;

/* Idem, mas devolve também a mensagem — para conferir a guarda pelo texto. */
create or replace function pg_temp.msg_como(papel text, sql text) returns text
language plpgsql as $$
declare msg text;
begin
    execute format('set role %I', papel);
    begin
        execute sql;
        msg := '';
    exception when others then
        get stacked diagnostics msg = message_text;
    end;
    reset role;
    return msg;
end;
$$;

/* Quantas linhas `papel` consegue ENXERGAR. Devolve o número, ou o SQLSTATE
   quando nem chegou a ler — é assim que "RLS filtrou" (0) se separa de
   "grant barrou" (42501). */
create or replace function pg_temp.visiveis_como(papel text, tabela text) returns text
language plpgsql as $$
declare n bigint; st text;
begin
    execute format('set role %I', papel);
    begin
        execute format('select count(*) from public.%I', tabela) into n;
        st := n::text;
    exception when others then
        get stacked diagnostics st = returned_sqlstate;
    end;
    reset role;
    return st;
end;
$$;

/* Espera um SQLSTATE EXATO. Qualquer outro — inclusive sucesso, inclusive erro
   de prova quebrada — reprova, e o relatório diz qual foi. */
create or replace function pg_temp.espera_estado(
    rotulo text, papel text, sql text, esperado text, trecho text default null
) returns text language plpgsql as $$
declare st text; msg text;
begin
    st := pg_temp.st_como(papel, sql);
    if st = esperado then
        if trecho is not null then
            msg := pg_temp.msg_como(papel, sql);
            if position(lower(trecho) in lower(msg)) = 0 then
                return 'FALHOU  ' || rotulo || ' :: SQLSTATE certo (' || st
                       || ') mas mensagem inesperada: ' || msg;
            end if;
        end if;
        return '  ok   ' || rotulo || ' [' || st || ']';
    end if;
    if pg_temp.prova_quebrada(st) then
        return 'FALHOU  ' || rotulo || ' :: a PROVA quebrou (' || st || '): '
               || pg_temp.msg_como(papel, sql);
    end if;
    if st = '00000' then
        return 'FALHOU  ' || rotulo || ' :: foi ACEITO e devia ser recusado com '
               || esperado;
    end if;
    return 'FALHOU  ' || rotulo || ' :: esperava ' || esperado || ', veio ' || st
           || ': ' || pg_temp.msg_como(papel, sql);
end;
$$;

create or replace function pg_temp.espera_sucesso(rotulo text, papel text, sql text)
returns text language plpgsql as $$
declare st text;
begin
    st := pg_temp.st_como(papel, sql);
    if st = '00000' then return '  ok   ' || rotulo; end if;
    return 'FALHOU  ' || rotulo || ' :: ' || st || ' — ' || pg_temp.msg_como(papel, sql);
end;
$$;

grant execute on function pg_temp.st_como(text, text) to public;
grant execute on function pg_temp.msg_como(text, text) to public;

\pset tuples_only on
\pset format unaligned

-- Uma linha para as provas de leitura olharem.
insert into public.criativo_render_job (id, tenant_id, idempotency_key, encomenda, motor_slug, seed)
values ('aaaaaaaa-0000-0000-0000-00000000000a','tenant-A','papeis-1','{}'::jsonb,'m',7),
       ('bbbbbbbb-0000-0000-0000-00000000000b','tenant-B','papeis-2','{}'::jsonb,'m',7);

-- Um job CONCLUÍDO de verdade, com recibo e validação, para as provas de
-- imutabilidade terem o que tentar reescrever. Montado como postgres, que é
-- quem o operário representa no caminho real.
insert into public.criativo_render_job (id, tenant_id, idempotency_key, encomenda, motor_slug, seed)
values ('cccccccc-0000-0000-0000-00000000000c','tenant-A','papeis-rendered','{}'::jsonb,'m',7);
update public.criativo_render_job set estado='claimed', owner='op-1',
       lease_ate=now()+interval '60s', batimento_em=now(), tentativa=1
 where id='cccccccc-0000-0000-0000-00000000000c';
update public.criativo_render_job set estado='running'
 where id='cccccccc-0000-0000-0000-00000000000c';
update public.criativo_render_job set estado='validating'
 where id='cccccccc-0000-0000-0000-00000000000c';
insert into public.criativo_render_recibo
    (id, job_id, tenant_id, produzido_por, motor_slug, motor_versao, seed,
     versoes, parametros, assinatura, iniciado_em, terminado_em)
values ('dddddddd-0000-0000-0000-00000000000d','cccccccc-0000-0000-0000-00000000000c',
        'tenant-A','op-1','m','1',7,
        '{}'::jsonb,'{}'::jsonb, repeat('a',64), now(), now());
insert into public.criativo_render_artefato
    (recibo_id, slot, mime, bytes, sha256, largura, altura)
values ('dddddddd-0000-0000-0000-00000000000d','1x1','image/png',4096, repeat('c',64),1080,1080);
insert into public.criativo_render_validacao (recibo_id, gate, resultado, bloqueante)
values ('dddddddd-0000-0000-0000-00000000000d','dimensao','PASS',true);
update public.criativo_render_job set estado='rendered', owner=null, lease_ate=null,
       terminado_em=now()
 where id='cccccccc-0000-0000-0000-00000000000c';

select '── a ferramenta se auto-testa ──';

-- ⚠️ A prova mais importante do arquivo: se a tabela não existisse, a prova
-- ANTIGA teria dito "ok, foi recusado". Esta diz que a prova quebrou.
select case when pg_temp.prova_quebrada(pg_temp.st_como('anon',
            'select 1 from public.tabela_que_nao_existe'))
            then '  ok   objeto inexistente é reportado como PROVA QUEBRADA, não como guarda'
            else 'FALHOU  objeto inexistente passou por guarda' end;
select case when pg_temp.st_como('anon', 'select 1') = '00000'
            then '  ok   a ferramenta reconhece sucesso'
            else 'FALHOU  a ferramenta não reconhece sucesso' end;

select '── papel público (anon): nada, e por GRANT ──';
select pg_temp.espera_estado('anon não lê job', 'anon',
    'select * from public.criativo_render_job', '42501');
select pg_temp.espera_estado('anon não insere job', 'anon',
    $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed)
       values ('tenant-A','anon-1','{}'::jsonb,'m',1)$q$, '42501');
select pg_temp.espera_estado('anon não atualiza job', 'anon',
    $q$update public.criativo_render_job set estado='running'$q$, '42501');
select pg_temp.espera_estado('anon não apaga job', 'anon',
    'delete from public.criativo_render_job', '42501');
select pg_temp.espera_estado('anon não lê recibo', 'anon',
    'select * from public.criativo_render_recibo', '42501');
select pg_temp.espera_estado('anon não lê a trilha', 'anon',
    'select * from public.criativo_render_transicao', '42501');
select pg_temp.espera_estado('anon não trunca', 'anon',
    'truncate public.criativo_render_job', '42501');

select '── papel autenticado comum: idem ──';
select pg_temp.espera_estado('authenticated não lê job', 'authenticated',
    'select * from public.criativo_render_job', '42501');
select pg_temp.espera_estado('authenticated não insere recibo', 'authenticated',
    $q$insert into public.criativo_render_recibo
       (job_id, tenant_id, produzido_por, motor_slug, motor_versao, seed,
        versoes, parametros, assinatura, iniciado_em, terminado_em)
       values ('aaaaaaaa-0000-0000-0000-00000000000a','tenant-A','op-1','m','1',7,
               '{}'::jsonb,'{}'::jsonb, repeat('a',64), now(), now())$q$, '42501');
select pg_temp.espera_estado('authenticated não apaga artefato', 'authenticated',
    'delete from public.criativo_render_artefato', '42501');

select '── papel privilegiado, como o de produção (BYPASSRLS) ──';
-- ⚠️ Aqui está a verdade que a prova de catálogo escondia: a RLS NÃO protege
-- destes olhos. O papel atravessa a RLS e enxerga tudo, inclusive outro tenant.
-- ⚠️ Contagem RELATIVA, não absoluta: a primeira versão exigia exatamente 2
-- linhas e reprovava porque as provas anteriores do ciclo já haviam inserido
-- outras. Uma prova que depende de quem rodou antes mede a ordem, não a guarda.
select case when pg_temp.visiveis_como('service_role','criativo_render_job')
                 = (select count(*)::text from public.criativo_render_job)
            then '  ok   service_role ATRAVESSA a RLS e vê TODAS as linhas (é assim em produção)'
            else 'FALHOU  service_role viu ' || pg_temp.visiveis_como('service_role','criativo_render_job')
                 || ' de ' || (select count(*) from public.criativo_render_job)
                 || '; a premissa BYPASSRLS não está reproduzida' end;
select case when pg_temp.visiveis_como('service_role','criativo_render_job')::bigint
                 >= (select count(distinct tenant_id) from public.criativo_render_job)
                 and (select count(distinct tenant_id) from public.criativo_render_job) > 1
            then '  ok   este papel enxerga MAIS DE UM tenant: isolar tenant é da aplicação, não do banco'
            else 'FALHOU  a base de prova não tem dois tenants para medir o cruzamento' end;
select pg_temp.espera_sucesso('service_role insere job', 'service_role',
    $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed)
       values ('tenant-A','papeis-3','{}'::jsonb,'m',9)$q$);
select pg_temp.espera_sucesso('service_role reivindica (transição válida)', 'service_role',
    $q$update public.criativo_render_job set estado='claimed', owner='op-1',
       lease_ate=now()+interval '60s', batimento_em=now(), tentativa=1
       where id='aaaaaaaa-0000-0000-0000-00000000000a'$q$);

-- O que de fato protege, já que a RLS não protege deste papel: o GRANT.
select pg_temp.espera_estado('service_role NÃO apaga job (apagar job é apagar auditoria)',
    'service_role', 'delete from public.criativo_render_job', '42501');
select pg_temp.espera_estado('service_role NÃO trunca job', 'service_role',
    'truncate public.criativo_render_job', '42501');
select pg_temp.espera_estado('service_role NÃO apaga recibo', 'service_role',
    'delete from public.criativo_render_recibo', '42501');
select pg_temp.espera_estado('service_role NÃO reescreve a trilha', 'service_role',
    $q$update public.criativo_render_transicao set para='queued'$q$, '42501');
select pg_temp.espera_estado('service_role NÃO apaga a trilha', 'service_role',
    'delete from public.criativo_render_transicao', '42501');

select '── as guardas de negócio valem TAMBÉM para o papel privilegiado ──';
-- Não basta o grant: quem pode escrever ainda esbarra nos gatilhos.
select pg_temp.espera_estado('service_role não pula validating', 'service_role',
    $q$update public.criativo_render_job set estado='rendered', owner=null,
       lease_ate=null, terminado_em=now()
       where id='aaaaaaaa-0000-0000-0000-00000000000a'$q$, '23000', 'transicao proibida');
select pg_temp.espera_estado('service_role não renova lease por transição', 'service_role',
    $q$update public.criativo_render_job set estado='running',
       lease_ate=now()+interval '600s'
       where id='aaaaaaaa-0000-0000-0000-00000000000a'$q$, '23000', 'nao renova lease');
select pg_temp.espera_estado('service_role não troca o dono no meio', 'service_role',
    $q$update public.criativo_render_job set estado='running', owner='op-2'
       where id='aaaaaaaa-0000-0000-0000-00000000000a'$q$, '23000', 'dono nao muda');

select '── RLS bloqueando: silencioso, e por isso perigoso de confundir ──';
-- ⚠️ Medido nas contraprovas desta missão, e vale escrever porque contraria a
-- leitura natural do relatório de catálogo: trocar `force row level security`
-- por `no force` NÃO derruba nenhuma prova daqui. `FORCE` só alcança o DONO da
-- tabela; para qualquer outro papel sem `BYPASSRLS`, quem filtra é o `enable`
-- com zero policies. Derrubar estas duas linhas exige `disable row level
-- security` — foi assim que a contraprova ficou vermelha (2 provas). Ou seja:
-- a linha "RLS forçada nas 5" do catálogo prova uma coisa (o dono também é
-- filtrado) e estas provam outra (o papel comum não enxerga nada).
-- Mesmo GRANT do service_role, mas SEM bypassrls. É o que o cluster de prova
-- tinha antes por engano — e o comportamento é OUTRO: não dá erro, some com as
-- linhas. Um "select count(*) = 0" que alguém leia como "não há trabalho" é o
-- modo mais silencioso de a RLS mentir para quem não sabe que ela está lá.
select case when pg_temp.visiveis_como('prova_sem_bypass','criativo_render_job') = '0'
            then '  ok   sem BYPASSRLS a leitura NÃO dá erro: devolve zero linhas'
            else 'FALHOU  esperava 0 linhas visíveis, veio '
                 || pg_temp.visiveis_como('prova_sem_bypass','criativo_render_job') end;
select pg_temp.espera_estado('sem BYPASSRLS o insert é barrado pela RLS, não pelo grant',
    'prova_sem_bypass',
    $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed)
       values ('tenant-A','papeis-4','{}'::jsonb,'m',1)$q$,
    '42501', 'row-level security');

select '── o recibo concluído é PROVA: ninguém reescreve, nem quem pode escrever ──';
-- ⚠️ ACHADO ADVERSARIAL (revisão de 2026-08-29). As provas cobriam DELETE de
-- recibo e UPDATE da trilha, mas não o UPDATE do próprio recibo. O papel
-- privilegiado tem GRANT de UPDATE e o gatilho de coerência libera a escrita
-- quando o job está `rendered` — então assinatura, autoria e parâmetros de um
-- recibo concluído eram reescrevíveis. Um recibo que pode ser reescrito depois
-- do fato não prova mais nada, e era essa a única coisa que ele existia para fazer.
select pg_temp.espera_estado('service_role NÃO reescreve a assinatura de recibo concluído',
    'service_role',
    $q$update public.criativo_render_recibo set assinatura = repeat('b',64)
       where job_id='cccccccc-0000-0000-0000-00000000000c'$q$, '23000', 'imutavel');
select pg_temp.espera_estado('service_role NÃO reescreve a autoria de recibo concluído',
    'service_role',
    $q$update public.criativo_render_recibo set produzido_por='outro-operario'
       where job_id='cccccccc-0000-0000-0000-00000000000c'$q$, '23000', 'imutavel');
select pg_temp.espera_estado('service_role NÃO reescreve a validação de um job concluído',
    'service_role',
    $q$update public.criativo_render_validacao set resultado='PASS'
       where recibo_id='dddddddd-0000-0000-0000-00000000000d'$q$, '23000');
select pg_temp.espera_estado('service_role NÃO acrescenta validação depois do render',
    'service_role',
    $q$insert into public.criativo_render_validacao (recibo_id, gate, resultado, bloqueante)
       values ('dddddddd-0000-0000-0000-00000000000d','inventado','PASS',false)$q$, '23000');

select '── superfície de funções ──';
-- Nenhuma função SECURITY DEFINER: uma delas seria um buraco que atravessa
-- tudo o que está acima, executando com os privilégios de quem a criou.
select case when count(*) = 0 then '  ok   nenhuma função SECURITY DEFINER em criativo_render_*'
            else 'FALHOU  ' || count(*) || ' função(ões) SECURITY DEFINER' end
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public' and p.proname like 'criativo_render_%' and p.prosecdef;
-- As funções de gatilho não são chamáveis fora do gatilho, nem por anon.
-- ⚠️ ACHADO ADVERSARIAL (revisão de 2026-08-29). A primeira versão aceitava
-- `42883` aqui — o MESMO código que a linha 49 deste arquivo declara "prova
-- quebrada". Renomear ou apagar a função deixaria esta prova verde, que é
-- exatamente o defeito que o arquivo existe para impedir. Agora a existência é
-- pré-condição conferida à parte, e a recusa tem código próprio.
select case when to_regprocedure('public.criativo_render_transicao_append_only()') is not null
            then '  ok   a função de gatilho EXISTE (pré-condição da prova seguinte)'
            else 'FALHOU  a função de gatilho não existe: a prova seguinte seria vazia' end;
select case when pg_temp.st_como('anon',
            'select public.criativo_render_transicao_append_only()') in ('0A000','42501','2F005')
            then '  ok   função de gatilho não roda como função comum'
            else 'FALHOU  função de gatilho executou fora do gatilho: '
                 || pg_temp.st_como('anon','select public.criativo_render_transicao_append_only()') end;

rollback;
