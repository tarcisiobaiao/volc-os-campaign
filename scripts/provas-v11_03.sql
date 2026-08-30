-- Provas de COMPORTAMENTO da v11_03, em SQL puro.
-- ⚠️ Em SQL e não em bash: a primeira versão destas provas vivia dentro de
-- `eval` com aspas aninhadas em três níveis, e a primeira inserção falhava por
-- quoting — fazendo TODAS as provas seguintes cascatearem. Um arranjo de prova
-- que falha por si mesmo não mede nada.
\set ON_ERROR_STOP on

-- ⚠️ ACHADO #10. Este `recusa` aceitava QUALQUER erro como prova verde: uma
-- tabela renomeada, um typo de coluna ou um ponto-e-vírgula fora do lugar
-- passavam como "a guarda funcionou". Uma prova assim mede o próprio erro de
-- digitação. Agora os SQLSTATEs que denunciam prova quebrada reprovam, e o
-- rótulo carrega o estado observado para quem lê o relatório.
-- ⚠️ ACHADO ADVERSARIAL (revisão de 2026-08-29). Endurecer contra "prova
-- quebrada" não bastava: `esperado` era opcional e NENHUMA das 57 chamadas o
-- passava, então qualquer erro plausível-porém-errado seguia verde. Exemplo
-- concreto do revisor: a prova de "recibo com tenant diferente" ficaria verde
-- com 23503 se o fixture apontasse para um job inexistente — provando a chave
-- estrangeira, não a guarda de tenant.
--
-- O padrão agora é 23000 (`integrity_constraint_violation`), que é o errcode com
-- que TODAS as guardas de negócio desta migration levantam. Uma recusa por outro
-- motivo — FK (23503), NOT NULL (23502), tipo (22P02), unique (23505) — deixa de
-- passar por guarda. Quem legitimamente espera outro código declara o seu.
create or replace function pg_temp.recusa(
    rotulo text, sql text, esperado text default '23000', trecho text default null
) returns text
language plpgsql as $$
declare st text; msg text;
begin
    execute sql;
    return 'FALHOU  ' || rotulo || ' (foi aceito e devia ser recusado)';
exception when others then
    get stacked diagnostics st = returned_sqlstate, msg = message_text;
    if st in ('42P01',  -- tabela inexistente
              '42703',  -- coluna inexistente
              '42601',  -- erro de sintaxe
              '42883',  -- função inexistente
              '3F000',  -- schema inexistente
              '42P02')  -- parâmetro inexistente
    then
        return 'FALHOU  ' || rotulo || ' :: a PROVA quebrou (' || st || '): ' || msg;
    end if;
    if esperado is not null and st <> esperado then
        return 'FALHOU  ' || rotulo || ' :: esperava SQLSTATE ' || esperado
               || ', veio ' || st || ': ' || msg;
    end if;
    -- Um código certo ainda pode vir da guarda ERRADA: duas CHECKs da mesma
    -- tabela levantam 23514 igual. Quem declara o nome, prova a sua.
    if trecho is not null and position(lower(trecho) in lower(msg)) = 0 then
        return 'FALHOU  ' || rotulo || ' :: SQLSTATE ' || st
               || ' mas a guarda que respondeu foi outra: ' || msg;
    end if;
    return '  ok   ' || rotulo || ' [' || st || ']';
end;
$$;

create or replace function pg_temp.aceita(rotulo text, sql text) returns text
language plpgsql as $$
begin
    execute sql;
    return '  ok   ' || rotulo;
exception when others then
    return 'FALHOU  ' || rotulo || ' :: ' || sqlerrm;
end;
$$;

\pset tuples_only on
\pset format unaligned

-- ── nascimento ──────────────────────────────────────────────────────────────
select pg_temp.aceita('job nasce em queued sem dono',
 $q$insert into public.criativo_render_job (id, tenant_id, idempotency_key, encomenda, motor_slug, seed)
    values ('11111111-1111-1111-1111-111111111111','tenant-A','k1','{}'::jsonb,'tipografico-local',7)$q$);
select case when estado='queued' and owner is null then '  ok   estado inicial correto'
            else 'FALHOU  estado inicial: '||estado end
  from public.criativo_render_job where id='11111111-1111-1111-1111-111111111111';

-- ── 1. transições ───────────────────────────────────────────────────────────
select pg_temp.aceita('queued -> claimed com dono',
 $q$update public.criativo_render_job set estado='claimed', owner='op-1',
    lease_ate=now()+interval '60s', batimento_em=now(), tentativa=1
    where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('claimed -> rendered (pula validating)',
 $q$update public.criativo_render_job set estado='rendered', owner=null, lease_ate=null,
    terminado_em=now() where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.aceita('claimed -> running',
 $q$update public.criativo_render_job set estado='running'
    where id='11111111-1111-1111-1111-111111111111'$q$);

-- ── 2. INVARIANTE 1: a transição não renova o lease ─────────────────────────
select pg_temp.recusa('running -> validating renovando o lease',
 $q$update public.criativo_render_job set estado='validating',
    lease_ate=now()+interval '600s' where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.aceita('running -> validating preservando o lease',
 $q$update public.criativo_render_job set estado='validating'
    where id='11111111-1111-1111-1111-111111111111'$q$);

-- ── 3. o dono não troca no meio ─────────────────────────────────────────────
select pg_temp.recusa('trocar de dono dentro da execução',
 $q$update public.criativo_render_job set owner='op-2'
    where id='11111111-1111-1111-1111-111111111111'$q$);

-- ── 4. rendered exige recibo ────────────────────────────────────────────────
select pg_temp.recusa('validating -> rendered sem recibo',
 $q$update public.criativo_render_job set estado='rendered', owner=null, lease_ate=null,
    terminado_em=now() where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('recibo com tenant diferente do job',
 $q$insert into public.criativo_render_recibo (job_id, tenant_id, produzido_por, motor_slug,
    motor_versao, seed, versoes, parametros, assinatura, iniciado_em, terminado_em)
    values ('11111111-1111-1111-1111-111111111111','tenant-B','op-1','m','1',7,
    '{}'::jsonb,'{}'::jsonb, repeat('b',64), now(), now())$q$);
select pg_temp.aceita('recibo gravado antes de concluir',
 $q$insert into public.criativo_render_recibo (job_id, tenant_id, produzido_por, motor_slug,
    motor_versao, seed, versoes, parametros, assinatura, iniciado_em, terminado_em)
    values ('11111111-1111-1111-1111-111111111111','tenant-A','op-1','tipografico-local','1.0.0',7,
    '{"pillow":"12.3.0"}'::jsonb,'{"titulo":"x"}'::jsonb, repeat('a',64), now(), now())$q$);
-- ⚠️ ACHADO ADVERSARIAL: `rendered` exigia só a LINHA do recibo. Um job chegava
-- a concluído com recibo de assinatura válida e ZERO artefatos, e a tela dizia
-- "pronto" sobre peça nenhuma. Recibo sem artefato é promessa, não prova.
select pg_temp.recusa('rendered com recibo mas SEM artefato',
 $q$update public.criativo_render_job set estado='rendered', owner=null, lease_ate=null,
    terminado_em=now() where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.aceita('artefato entra antes de concluir',
 $q$insert into public.criativo_render_artefato (recibo_id, slot, mime, bytes, sha256, largura, altura)
    select id,'1x1','image/png',36369,repeat('c',64),1080,1080 from public.criativo_render_recibo
    where job_id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.aceita('validating -> rendered com recibo E artefato',
 $q$update public.criativo_render_job set estado='rendered', owner=null, lease_ate=null,
    terminado_em=now() where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('rendered -> queued',
 $q$update public.criativo_render_job set estado='queued', terminado_em=null
    where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('rendered -> cancelled',
 $q$update public.criativo_render_job set estado='cancelled', cancelado_em=now(),
    cancelado_por='u', cancelado_motivo='tarde'
    where id='11111111-1111-1111-1111-111111111111'$q$);

-- ── 5. artefato ─────────────────────────────────────────────────────────────
select pg_temp.recusa('artefato com bytes zero',
 $q$insert into public.criativo_render_artefato (recibo_id, slot, mime, bytes, sha256)
    select id,'zz','image/png',0,repeat('d',64) from public.criativo_render_recibo
    where job_id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('artefato com hash malformado',
 $q$insert into public.criativo_render_artefato (recibo_id, slot, mime, bytes, sha256)
    select id,'yy','image/png',10,'curto' from public.criativo_render_recibo
    where job_id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('alterar artefato de job concluído',
 $q$update public.criativo_render_artefato set bytes=1 where slot='1x1'$q$);
select pg_temp.recusa('apagar artefato de job concluído',
 $q$delete from public.criativo_render_artefato where slot='1x1'$q$);

-- ── 6. retomada ─────────────────────────────────────────────────────────────
select pg_temp.recusa('retomar um rendered',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug,
    seed, retry_of, retry_n)
    values ('tenant-A','k1r','{}'::jsonb,'m',7,'11111111-1111-1111-1111-111111111111',1)$q$);
select pg_temp.aceita('job que falha',
 $q$insert into public.criativo_render_job (id, tenant_id, idempotency_key, encomenda, motor_slug,
    seed, estado, falha_codigo, falha_mensagem, falha_permanente, terminado_em)
    values ('33333333-3333-3333-3333-333333333333','tenant-A','kf','{}'::jsonb,'m',7,
    'failed','motor_desconhecido','nenhum motor com esse slug',true,now())$q$);
select pg_temp.aceita('retomar um failed',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug,
    seed, retry_of, retry_n)
    values ('tenant-A','kf-r1','{}'::jsonb,'m',7,'33333333-3333-3333-3333-333333333333',1)$q$);
select pg_temp.recusa('retomada com retry_n fora de ordem',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug,
    seed, retry_of, retry_n)
    values ('tenant-A','kf-r9','{}'::jsonb,'m',7,'33333333-3333-3333-3333-333333333333',9)$q$);
select pg_temp.recusa('retomar trabalho de outro tenant',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug,
    seed, retry_of, retry_n)
    values ('tenant-B','kf-rx','{}'::jsonb,'m',7,'33333333-3333-3333-3333-333333333333',1)$q$);
select pg_temp.recusa('linhagem sem retry_n',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug,
    seed, retry_of, retry_n)
    values ('tenant-A','kf-r0','{}'::jsonb,'m',7,'33333333-3333-3333-3333-333333333333',0)$q$);

-- ── 7. tenant e idempotência ────────────────────────────────────────────────
select pg_temp.aceita('mesma chave, tenants diferentes: dois jobs',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed)
    values ('tenant-B','k1','{}'::jsonb,'m',7)$q$);
select pg_temp.recusa('mesma chave no mesmo tenant',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed)
    values ('tenant-A','k1','{}'::jsonb,'m',7)$q$, '23505', 'criativo_render_job_idem_ux');
select pg_temp.recusa('tenant vazio',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed)
    values ('   ','kv','{}'::jsonb,'m',7)$q$, '23514', 'criativo_render_job_tenant_nao_vazio');

-- ── 8. cancelamento ─────────────────────────────────────────────────────────
select pg_temp.aceita('cancelar na fila',
 $q$insert into public.criativo_render_job (id, tenant_id, idempotency_key, encomenda, motor_slug, seed)
    values ('44444444-4444-4444-4444-444444444444','tenant-A','kc','{}'::jsonb,'m',7);
    update public.criativo_render_job set estado='cancelled', cancelado_por='u',
    cancelado_motivo='mudei de ideia', cancelado_em=now(), terminado_em=now()
    where id='44444444-4444-4444-4444-444444444444'$q$);
select pg_temp.recusa('cancelar sem motivo',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado, cancelado_por, cancelado_em, terminado_em)
    values ('tenant-A','kc2','{}'::jsonb,'m',7,'cancelled','u',now(),now())$q$, '23514', 'criativo_render_job_cancelamento_justificado');
select pg_temp.aceita('cancelar durante a execução',
 $q$insert into public.criativo_render_job (id, tenant_id, idempotency_key, encomenda, motor_slug, seed)
    values ('55555555-5555-5555-5555-555555555555','tenant-A','ke','{}'::jsonb,'m',7);
    update public.criativo_render_job set estado='claimed', owner='op-9',
    lease_ate=now()+interval '60s' where id='55555555-5555-5555-5555-555555555555';
    update public.criativo_render_job set estado='cancelled', owner=null, lease_ate=null,
    cancelado_por='u', cancelado_motivo='parar', cancelado_em=now(), terminado_em=now()
    where id='55555555-5555-5555-5555-555555555555'$q$);
select pg_temp.aceita('retomar um cancelled',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug,
    seed, retry_of, retry_n)
    values ('tenant-A','ke-r1','{}'::jsonb,'m',7,'55555555-5555-5555-5555-555555555555',1)$q$);

-- ── 9. mensagem sanitizada ──────────────────────────────────────────────────
select pg_temp.recusa('falha com caminho unix',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado, falha_codigo, falha_mensagem, falha_permanente, terminado_em)
    values ('tenant-A','kp','{}'::jsonb,'m',7,'failed','x',
    'No space left on device: /var/folders/ab/1x1.png',true,now())$q$, '23514', 'criativo_render_job_mensagem_sem_caminho');
select pg_temp.recusa('falha com stack trace',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado, falha_codigo, falha_mensagem, falha_permanente, terminado_em)
    values ('tenant-A','kt','{}'::jsonb,'m',7,'failed','x',
    'Traceback (most recent call last): boom',true,now())$q$, '23514', 'criativo_render_job_mensagem_sem_caminho');
select pg_temp.recusa('falha com caminho windows',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado, falha_codigo, falha_mensagem, falha_permanente, terminado_em)
    values ('tenant-A','kw','{}'::jsonb,'m',7,'failed','x',
    'erro em C:\Users\op\peca.png',true,now())$q$, '23514', 'criativo_render_job_mensagem_sem_caminho');
select pg_temp.aceita('falha sanitizada é aceita',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado, falha_codigo, falha_mensagem, falha_permanente, terminado_em)
    values ('tenant-A','ks','{}'::jsonb,'m',7,'failed','x',
    'sem espaco em disco ao gravar a peca',true,now())$q$);
select pg_temp.recusa('falha sem mensagem',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado, falha_codigo, falha_permanente, terminado_em)
    values ('tenant-A','kn','{}'::jsonb,'m',7,'failed','x',true,now())$q$, '23514', 'criativo_render_job_falha_completa');

-- ── 10. lease sem dono ──────────────────────────────────────────────────────
select pg_temp.recusa('lease sem dono',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    lease_ate) values ('tenant-A','kl','{}'::jsonb,'m',7, now()+interval '60s')$q$, '23514', 'criativo_render_job_lease_com_dono');
select pg_temp.recusa('estado em execução sem dono',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado) values ('tenant-A','kd','{}'::jsonb,'m',7,'running')$q$, '23514', 'criativo_render_job_dono_coerente');

-- ── 11. trilha append-only ──────────────────────────────────────────────────
select case when count(*) >= 6 then '  ok   a trilha registrou '||count(*)||' transições'
            else 'FALHOU  trilha com só '||count(*) end
  from public.criativo_render_transicao;
select pg_temp.recusa('editar a trilha',
 $q$update public.criativo_render_transicao set para='rendered'
    where id=(select min(id) from public.criativo_render_transicao)$q$);
select pg_temp.recusa('apagar da trilha',
 $q$delete from public.criativo_render_transicao
    where id=(select min(id) from public.criativo_render_transicao)$q$);

-- ── 12. achados da auditoria adversarial de 29/08/2026 ──────────────────────

-- O atalho "estado não mudou" matava TODAS as guardas.
select pg_temp.recusa('reescrever a encomenda de um job rendered',
 $q$update public.criativo_render_job set encomenda='{"outro":"pedido"}'::jsonb
    where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('reescrever a semente de um job rendered',
 $q$update public.criativo_render_job set seed=999
    where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('roubar o job trocando o tenant',
 $q$update public.criativo_render_job set tenant_id='tenant-INTRUSO'
    where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('trocar o motor de um job concluído',
 $q$update public.criativo_render_job set motor_slug='caro-pago'
    where id='11111111-1111-1111-1111-111111111111'$q$);
select pg_temp.recusa('trocar a chave de idempotência',
 $q$update public.criativo_render_job set idempotency_key='outra'
    where id='11111111-1111-1111-1111-111111111111'$q$);

-- Linhagem por UPDATE ligava job de um tenant a job terminal de OUTRO.
-- ⚠️ O alvo é um job que JÁ EXISTE neste ponto. A primeira versão desta prova
-- usava `idempotency_key='c1'`, que só nasce depois, no trecho de bash: o UPDATE
-- afetava ZERO linhas, nenhum gatilho disparava, e a prova passava por vazio.
select pg_temp.recusa('forjar linhagem por UPDATE',
 $q$update public.criativo_render_job set retry_of='33333333-3333-3333-3333-333333333333',
    retry_n=1 where idempotency_key='ks'$q$);
select case when count(*)=1 then '  ok   o alvo da prova de linhagem existe'
            else 'FALHOU  a prova de linhagem mirou em zero linhas' end
  from public.criativo_render_job where idempotency_key='ks';

-- Artefato acrescentado DEPOIS de concluído, com bytes e hash nunca conferidos.
select pg_temp.recusa('inserir artefato novo em job concluído',
 $q$insert into public.criativo_render_artefato (recibo_id, slot, mime, bytes, sha256)
    select id,'9x16','image/png',1,repeat('f',64) from public.criativo_render_recibo
    where job_id='11111111-1111-1111-1111-111111111111'$q$);

-- Os três bypasses do regex de caminho.
select pg_temp.recusa('caminho sem espaço antes da barra',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado, falha_codigo, falha_mensagem, falha_permanente, terminado_em)
    values ('tenant-A','kb1','{}'::jsonb,'m',7,'failed','x',
    'No space left on device:/var/folders/ab/T/xyz/1x1.png',true,now())$q$, '23514', 'criativo_render_job_mensagem_sem_caminho');
select pg_temp.recusa('caminho entre parênteses',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado, falha_codigo, falha_mensagem, falha_permanente, terminado_em)
    values ('tenant-A','kb2','{}'::jsonb,'m',7,'failed','x',
    'falha em(/Users/mac/.volc-os/bancada/trabalhos/abc/1x1.png)',true,now())$q$, '23514', 'criativo_render_job_mensagem_sem_caminho');
select pg_temp.recusa('caminho UNC do Windows',
 $q$insert into public.criativo_render_job (tenant_id, idempotency_key, encomenda, motor_slug, seed,
    estado, falha_codigo, falha_mensagem, falha_permanente, terminado_em)
    values ('tenant-A','kb3','{}'::jsonb,'m',7,'failed','x',
    'erro em \\servidor\share\segredo\peca.png',true,now())$q$, '23514', 'criativo_render_job_mensagem_sem_caminho');

-- A trilha precisa do autor nos eventos TERMINAIS, que é onde ela mais importa.
select case when count(*) = 0 then '  ok   a trilha tem autor em todo evento terminal'
            else 'FALHOU  '||count(*)||' evento(s) terminal(is) sem autor na trilha' end
  from public.criativo_render_transicao
 where para in ('cancelled','failed','rendered') and por is null;

-- ── 13. achados #3, #8 e #9 ────────────────────────────────────────────────

-- #8: lease vencido nao avanca, e a corrida com o reaper some.
select pg_temp.aceita('job com lease vencido nasce',
 $q$insert into public.criativo_render_job (id, tenant_id, idempotency_key, encomenda,
    motor_slug, seed, estado, owner, lease_ate, batimento_em)
    values ('66666666-6666-6666-6666-666666666666','tenant-A','kv1','{}'::jsonb,'m',7,
    'claimed','op-morto', now() - interval '2 hours', now() - interval '2 hours')$q$);
select pg_temp.recusa('lease vencido ha 2h avanca para running',
 $q$update public.criativo_render_job set estado='running'
    where id='66666666-6666-6666-6666-666666666666'$q$);
select pg_temp.aceita('renovar o lease destrava',
 $q$update public.criativo_render_job set lease_ate=now()+interval '60s',
    batimento_em=now() where id='66666666-6666-6666-6666-666666666666'$q$);
select pg_temp.aceita('com lease valido, avanca',
 $q$update public.criativo_render_job set estado='running'
    where id='66666666-6666-6666-6666-666666666666'$q$);

-- #9: recibo so nasce em fase coerente com producao.
select pg_temp.recusa('recibo colado num job failed',
 $q$insert into public.criativo_render_recibo (job_id, tenant_id, produzido_por,
    motor_slug, motor_versao, seed, versoes, parametros, assinatura, iniciado_em,
    terminado_em)
    values ('33333333-3333-3333-3333-333333333333','tenant-A','op','m','1',7,
    '{}'::jsonb,'{}'::jsonb, repeat('e',64), now(), now())$q$);
select pg_temp.recusa('recibo colado num job cancelled',
 $q$insert into public.criativo_render_recibo (job_id, tenant_id, produzido_por,
    motor_slug, motor_versao, seed, versoes, parametros, assinatura, iniciado_em,
    terminado_em)
    values ('44444444-4444-4444-4444-444444444444','tenant-A','op','m','1',7,
    '{}'::jsonb,'{}'::jsonb, repeat('e',64), now(), now())$q$);
select pg_temp.recusa('recibo colado num job na fila',
 $q$insert into public.criativo_render_job (id, tenant_id, idempotency_key, encomenda,
    motor_slug, seed) values ('77777777-7777-7777-7777-777777777777','tenant-A','kq',
    '{}'::jsonb,'m',7);
    insert into public.criativo_render_recibo (job_id, tenant_id, produzido_por,
    motor_slug, motor_versao, seed, versoes, parametros, assinatura, iniciado_em,
    terminado_em) values ('77777777-7777-7777-7777-777777777777','tenant-A','op','m',
    '1',7,'{}'::jsonb,'{}'::jsonb, repeat('e',64), now(), now())$q$);

-- #3: storage_chave nasce nula e sobe UMA vez, amarrada ao dono.
select pg_temp.recusa('storage_chave de outro tenant',
 $q$update public.criativo_render_artefato
    set storage_chave='criativos/tenant-INTRUSO/xxx/1x1_abc.png'
    where slot='1x1'$q$);
select pg_temp.recusa('storage_chave com prefixo errado',
 $q$update public.criativo_render_artefato set storage_chave='criativos/qualquer/coisa.png'
    where slot='1x1'$q$);
-- ── o ciclo de vida completo, estado a estado ──────────────────────────────
-- LOCAL -> UPLOADED_UNVERIFIED -> VERIFIED_OK. Nunca volta, nunca reaponta.

select case when storage_chave is null and storage_conferido_em is null
              and storage_hash_conferido is null
            then '  ok   estado LOCAL: sem endereco e sem conferencia'
            else 'FALHOU  o artefato nao nasceu LOCAL' end
  from public.criativo_render_artefato where slot='1x1';

-- delimitador obrigatorio: prefixo parcial nao pode aceitar outro slot
select pg_temp.recusa('chave de slot vizinho (prefixo parcial)',
 $q$update public.criativo_render_artefato a
    set storage_chave = public.criativo_storage_chave(j.tenant_id, j.id, '1x1-malicioso', 'x.png')
    from public.criativo_render_recibo r
    join public.criativo_render_job j on j.id = r.job_id
    where a.recibo_id = r.id and a.slot='1x1'$q$);
select pg_temp.recusa('chave com travessia de diretorio',
 $q$update public.criativo_render_artefato a
    set storage_chave = 'criativos/' || j.tenant_id || '/' || j.id::text || '/../../etc/senha'
    from public.criativo_render_recibo r
    join public.criativo_render_job j on j.id = r.job_id
    where a.recibo_id = r.id and a.slot='1x1'$q$);
select pg_temp.recusa('chave com barra dupla',
 $q$update public.criativo_render_artefato a
    set storage_chave = 'criativos//' || j.tenant_id || '/' || j.id::text || '/1x1__x.png'
    from public.criativo_render_recibo r
    join public.criativo_render_job j on j.id = r.job_id
    where a.recibo_id = r.id and a.slot='1x1'$q$);
select pg_temp.recusa('chave que abre outra pasta depois do slot',
 $q$update public.criativo_render_artefato a
    set storage_chave = public.criativo_storage_chave(j.tenant_id, j.id, '1x1', 'sub/x.png')
    from public.criativo_render_recibo r
    join public.criativo_render_job j on j.id = r.job_id
    where a.recibo_id = r.id and a.slot='1x1'$q$);

-- LOCAL -> UPLOADED_UNVERIFIED
select pg_temp.aceita('LOCAL -> UPLOADED_UNVERIFIED',
 $q$update public.criativo_render_artefato a
    set storage_chave = public.criativo_storage_chave(j.tenant_id, j.id, '1x1', 'abc12.png')
    from public.criativo_render_recibo r
    join public.criativo_render_job j on j.id = r.job_id
    where a.recibo_id = r.id and a.slot='1x1'$q$);
select case when storage_chave is not null and storage_hash_conferido is null then
            '  ok   UPLOADED_UNVERIFIED: subiu e NINGUEM conferiu'
       else 'FALHOU  o upload afirmou conferencia que nao houve' end
  from public.criativo_render_artefato where slot='1x1';

select pg_temp.recusa('repontar a chave para outro objeto',
 $q$update public.criativo_render_artefato
    set storage_chave = storage_chave || '.outro' where slot='1x1'$q$);
select pg_temp.recusa('apagar a chave (voltar para LOCAL)',
 $q$update public.criativo_render_artefato set storage_chave=null where slot='1x1'$q$);
select pg_temp.recusa('repetir a promocao com endereco diferente',
 $q$update public.criativo_render_artefato a
    set storage_chave = public.criativo_storage_chave(j.tenant_id, j.id, '1x1', 'zzz99.png')
    from public.criativo_render_recibo r
    join public.criativo_render_job j on j.id = r.job_id
    where a.recibo_id = r.id and a.slot='1x1'$q$);
select pg_temp.recusa('mudar bytes junto com a conferencia',
 $q$update public.criativo_render_artefato set bytes=1, storage_conferido_em=now(),
    storage_hash_conferido=true where slot='1x1'$q$);
select pg_temp.recusa('mudar o hash local junto com a conferencia',
 $q$update public.criativo_render_artefato set sha256=repeat('9',64),
    storage_conferido_em=now(), storage_hash_conferido=true where slot='1x1'$q$);
select pg_temp.recusa('conferencia sem carimbo',
 $q$update public.criativo_render_artefato set storage_hash_conferido=true
    where slot='1x1'$q$);
select pg_temp.recusa('carimbo sem veredito',
 $q$update public.criativo_render_artefato set storage_conferido_em=now()
    where slot='1x1'$q$, '23514', 'criativo_render_artefato_conferencia_coerente');
select pg_temp.recusa('UPDATE que nao avanca nada',
 $q$update public.criativo_render_artefato set mime=mime where slot='1x1'$q$);

-- UPLOADED_UNVERIFIED -> VERIFIED_MISMATCH (o caso honesto: nao bateu)
select pg_temp.aceita('UPLOADED_UNVERIFIED -> VERIFIED_MISMATCH',
 $q$update public.criativo_render_artefato set storage_conferido_em=now(),
    storage_hash_conferido=false where slot='1x1'$q$);
select case when storage_hash_conferido = false then
            '  ok   VERIFIED_MISMATCH registrado, nao escondido'
       else 'FALHOU  a divergencia sumiu' end
  from public.criativo_render_artefato where slot='1x1';

select pg_temp.recusa('mudar o veredito depois de conferido',
 $q$update public.criativo_render_artefato set storage_hash_conferido=true
    where slot='1x1'$q$);
select pg_temp.recusa('apagar a conferencia',
 $q$update public.criativo_render_artefato set storage_conferido_em=null,
    storage_hash_conferido=null where slot='1x1'$q$);

-- LOCAL -> VERIFIED_* atomico, noutro artefato
select pg_temp.aceita('segundo artefato entra antes de concluir outro job',
 $q$insert into public.criativo_render_job (id, tenant_id, idempotency_key, encomenda,
    motor_slug, seed) values ('88888888-8888-8888-8888-888888888888','tenant-A','ka2',
    '{}'::jsonb,'m',7);
    update public.criativo_render_job set estado='claimed', owner='op-2',
    lease_ate=now()+interval '60s' where id='88888888-8888-8888-8888-888888888888';
    update public.criativo_render_job set estado='running'
    where id='88888888-8888-8888-8888-888888888888';
    update public.criativo_render_job set estado='validating'
    where id='88888888-8888-8888-8888-888888888888';
    insert into public.criativo_render_recibo (job_id, tenant_id, produzido_por,
    motor_slug, motor_versao, seed, versoes, parametros, assinatura, iniciado_em,
    terminado_em) values ('88888888-8888-8888-8888-888888888888','tenant-A','op-2',
    'm','1',7,'{}'::jsonb,'{}'::jsonb, repeat('7',64), now(), now());
    insert into public.criativo_render_artefato (recibo_id, slot, mime, bytes, sha256)
    select id,'4x5','image/png',200,repeat('8',64) from public.criativo_render_recibo
    where job_id='88888888-8888-8888-8888-888888888888';
    update public.criativo_render_job set estado='rendered', owner=null,
    lease_ate=null, terminado_em=now()
    where id='88888888-8888-8888-8888-888888888888'$q$);
select pg_temp.aceita('LOCAL -> VERIFIED_OK num unico UPDATE atomico',
 $q$update public.criativo_render_artefato a
    set storage_chave = public.criativo_storage_chave(j.tenant_id, j.id, '4x5', 'ok.png'),
        storage_conferido_em = now(), storage_hash_conferido = true
    from public.criativo_render_recibo r
    join public.criativo_render_job j on j.id = r.job_id
    where a.recibo_id = r.id and a.slot='4x5'$q$);
