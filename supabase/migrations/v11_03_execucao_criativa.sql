-- =============================================================================
-- v11_03 — a execução criativa vira dado: job, tentativa, lease, recibo, linhagem
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin.
-- ⚠️ NÃO APLICADA EM PRODUÇÃO. Ver `supabase/migrations/README.md`.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTA MIGRATION É, E O QUE ELA NÃO É
-- -----------------------------------------------------------------------------
-- Ela persiste o contrato que a bancada local JÁ PROVOU, com 79 testes e 95,2%
-- de mutation score. Não inventa campo: cada coluna aqui tem um comportamento
-- correspondente que falha quando ela some.
--
-- O SQLite da bancada continua sendo a fila LOCAL do worker. Isto aqui é a
-- autoridade do domínio. Confundir os dois foi o que fez o executor anterior
-- virar `asyncio.create_task` num processo serverless.
--
-- -----------------------------------------------------------------------------
-- AS SETE INVARIANTES QUE O SCHEMA DEFENDE
-- -----------------------------------------------------------------------------
-- 1. LEASE NÃO É RENOVADO POR TRANSIÇÃO. Renovar lease é trabalho do batimento,
--    que confere dono. A versão local disso gravava `agora + 60s` em toda
--    transição, e passar de `claimed` para `running` ressuscitava um lease
--    vencido — o trabalho abandonado nunca voltava para a fila.
-- 2. SÓ O DONO BATE O CORAÇÃO. Sem isso, quem já perdeu o trabalho mantinha o
--    lease no futuro e o dono real morto nunca era detectado.
-- 3. RENDERED É TERMINAL E EXIGE RECIBO. "Concluído" sem prova é opinião.
-- 4. FAILED SÓ VOLTA POR GESTO EXPLÍCITO. Não se reabre um terminal: nasce um
--    job novo com `retry_of`, porque o `failed` guarda por que falhou.
-- 5. ARTEFATO É IMUTÁVEL DEPOIS DE RENDERED, e `bytes`/`sha256` são NOT NULL:
--    o executor confere contra o disco, e o banco não aceita a versão declarada.
-- 6. TENANT ENTRA NA IDENTIDADE. Dois inquilinos com o mesmo pedido são dois
--    jobs. A chave única é (tenant, idempotency_key), não a chave sozinha.
-- 7. MENSAGEM DE ERRO NÃO CARREGA CAMINHO. Há CHECK, porque documentação não
--    impede ninguém de gravar `/var/folders/...` num campo de texto.
--
-- -----------------------------------------------------------------------------
-- ACHADO H: O ACL PADRÃO QUEBRADO
-- -----------------------------------------------------------------------------
-- `public` concede `arwdDxt` a anon, authenticated e service_role em TODA tabela
-- nova. Isso é real e está ativo em produção. Por isso cada tabela abaixo leva
-- REVOKE explícito, inclusive de `service_role`, antes do GRANT mínimo.
-- =============================================================================

\set ON_ERROR_STOP on

begin;

do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception 'v11_03 deve rodar como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
end
$guarda$;

-- ── 1. o job ────────────────────────────────────────────────────────────────

create table if not exists public.criativo_render_job (
    id                  uuid primary key default gen_random_uuid(),

    -- ⚠️ NOT NULL sem default. Um job sem dono é um job que qualquer um lê.
    tenant_id           text not null,
    criado_por          text,

    idempotency_key     text not null,
    estado              text not null default 'queued',

    -- A encomenda inteira, congelada. Um job não muda de pedido.
    encomenda           jsonb not null,
    motor_slug          text not null,
    modo_slug           text,
    finalidade_slug     text,
    seed                bigint not null,

    tentativa           integer not null default 0,
    max_tentativas      integer not null default 3,

    -- ── lease ──
    -- `owner` é quem detém o lease AGORA. Some quando o job sai de execução.
    -- Quem produziu fica no recibo, que é o registro permanente.
    owner               text,
    lease_ate           timestamptz,
    batimento_em        timestamptz,

    -- ── linhagem ──
    retry_of            uuid references public.criativo_render_job(id),
    retry_n             integer not null default 0,

    -- ── cancelamento ──
    cancelado_por       text,
    cancelado_motivo    text,
    cancelado_em        timestamptz,

    -- ── falha ──
    falha_codigo        text,
    falha_mensagem      text,
    falha_permanente    boolean,

    criado_em           timestamptz not null default now(),
    atualizado_em       timestamptz not null default now(),
    terminado_em        timestamptz,

    constraint criativo_render_job_estado_valido check (
        estado in ('queued','claimed','running','validating','rendered','failed','cancelled')
    ),
    constraint criativo_render_job_tenant_nao_vazio check (length(trim(tenant_id)) > 0),
    constraint criativo_render_job_seed_nao_negativa check (seed >= 0),
    constraint criativo_render_job_tentativa_faixa check (
        tentativa >= 0 and max_tentativas >= 0 and tentativa <= max_tentativas + 1
    ),

    -- Invariante 1: em execução, tem dono. Fora dela, não tem.
    constraint criativo_render_job_dono_coerente check (
        (estado in ('claimed','running','validating')) = (owner is not null)
    ),
    -- Lease e dono andam juntos: lease sem dono é lease de ninguém.
    constraint criativo_render_job_lease_com_dono check (
        lease_ate is null or owner is not null
    ),

    -- Terminal é carimbado. Não-terminal não é.
    constraint criativo_render_job_terminal_carimbado check (
        (estado in ('rendered','failed','cancelled')) = (terminado_em is not null)
    ),
    -- Falha tem motivo; não-falha não tem.
    constraint criativo_render_job_falha_coerente check (
        (estado = 'failed') = (falha_codigo is not null)
    ),
    constraint criativo_render_job_falha_completa check (
        falha_codigo is null
        or (length(trim(coalesce(falha_mensagem,''))) > 0 and falha_permanente is not null)
    ),
    -- Invariante 7: a mensagem de erro não carrega caminho de disco nem stack.
    -- ⚠️ Tres bypasses medidos na auditoria: `device:/var/...` (sem espaco antes
    -- da barra), `(/Users/...)` (parentese antes) e `\\servidor\share` (UNC do
    -- Windows). A ancora de inicio-de-palavra era frouxa demais; agora a barra
    -- seguida de dois segmentos e recusada em qualquer posicao.
    constraint criativo_render_job_mensagem_sem_caminho check (
        falha_mensagem is null
        or (falha_mensagem !~ '/[^[:space:]''"/]+/[^[:space:]''"/]+'
            and falha_mensagem !~ '~/'
            and falha_mensagem !~ 'Traceback \(most recent'
            and falha_mensagem !~ '[A-Za-z]:\\'
            and falha_mensagem !~ '\\\\[^[:space:]]+\\')
    ),
    -- Cancelamento tem autor, motivo e carimbo, ou não existe.
    constraint criativo_render_job_cancelamento_completo check (
        (estado = 'cancelled') = (cancelado_em is not null)
    ),
    constraint criativo_render_job_cancelamento_justificado check (
        cancelado_em is null
        or (length(trim(coalesce(cancelado_motivo,''))) > 0 and cancelado_por is not null)
    ),
    -- Invariante 4: retomada tem origem e ordinal, ou é original.
    constraint criativo_render_job_retomada_coerente check (
        (retry_of is null) = (retry_n = 0)
    ),
    constraint criativo_render_job_retomada_positiva check (retry_n >= 0)
);

-- Invariante 6: a identidade é (tenant, chave). Dois inquilinos com o mesmo
-- pedido são dois jobs, e o segundo não lê o artefato do primeiro.
create unique index if not exists criativo_render_job_idem_ux
    on public.criativo_render_job (tenant_id, idempotency_key);

create index if not exists criativo_render_job_fila
    on public.criativo_render_job (estado, criado_em)
    where estado = 'queued';
create index if not exists criativo_render_job_tenant
    on public.criativo_render_job (tenant_id, criado_em desc);
create index if not exists criativo_render_job_retry_of
    on public.criativo_render_job (retry_of);
-- Lease vencido: índice parcial, porque o reaper só olha o que está em execução.
create index if not exists criativo_render_job_lease
    on public.criativo_render_job (lease_ate)
    where estado in ('claimed','running','validating');

-- ── 2. a trilha de transições, append-only ──────────────────────────────────
-- ⚠️ Invariante 4 depende disto: "failed só volta por gesto explícito e
-- AUDITÁVEL". Sem trilha, a retomada é explícita e invisível.

create table if not exists public.criativo_render_transicao (
    id            bigserial primary key,
    job_id        uuid not null references public.criativo_render_job(id),
    de            text,
    para          text not null,
    por           text,
    motivo        text,
    em            timestamptz not null default now(),
    constraint criativo_render_transicao_para_valido check (
        para in ('queued','claimed','running','validating','rendered','failed','cancelled')
    )
);
create index if not exists criativo_render_transicao_job
    on public.criativo_render_transicao (job_id, id);

-- ── 3. o recibo ─────────────────────────────────────────────────────────────

create table if not exists public.criativo_render_recibo (
    id                    uuid primary key default gen_random_uuid(),
    job_id                uuid not null unique references public.criativo_render_job(id),
    tenant_id             text not null,

    -- Quem PRODUZIU. `criativo_render_job.owner` é o portador do lease e some
    -- quando o job termina; isto é permanente.
    produzido_por         text not null,
    motor_slug            text not null,
    motor_versao          text not null,
    seed                  bigint not null,

    -- Tudo que participa do render e pode mudar o resultado.
    versoes               jsonb not null,
    parametros            jsonb not null,

    -- Hash do que DEVE ser igual entre duas execuções do mesmo pedido.
    assinatura            text not null,

    iniciado_em           timestamptz not null,
    terminado_em          timestamptz not null,

    -- ⚠️ NULL, nunca 0. "Não sei quanto custou" e "foi de graça" são diferentes.
    custo_estimado_usd    numeric,
    custo_real_usd        numeric,

    -- Medidas de áudio como NÚMEROS. Um gate que só diz "passou" impede a
    -- próxima pergunta: passou por quanto?
    lufs_integrado        numeric,
    true_peak_dbtp        numeric,
    alvo_lufs             numeric,

    criado_em             timestamptz not null default now(),

    constraint criativo_render_recibo_assinatura_forma
        check (assinatura ~ '^[0-9a-f]{64}$'),
    constraint criativo_render_recibo_ordem
        check (terminado_em >= iniciado_em),
    constraint criativo_render_recibo_custo_nao_negativo
        check ((custo_estimado_usd is null or custo_estimado_usd >= 0)
           and (custo_real_usd is null or custo_real_usd >= 0)),
    constraint criativo_render_recibo_produtor_nao_vazio
        check (length(trim(produzido_por)) > 0)
);

-- ── 4. o artefato ───────────────────────────────────────────────────────────

create table if not exists public.criativo_render_artefato (
    id            uuid primary key default gen_random_uuid(),
    recibo_id     uuid not null references public.criativo_render_recibo(id),
    slot          text not null,
    mime          text not null,

    -- Invariante 5: os dois são NOT NULL e conferidos contra o disco pelo
    -- executor. O banco não aceita "o motor declarou 4096 bytes".
    bytes         bigint not null,
    sha256        text not null,

    largura       integer,
    altura        integer,
    duracao_s     numeric,

    -- ── ciclo de vida do endereço no armazenamento ──
    -- ⚠️ NASCE NULA e só pode ser preenchida UMA VEZ, depois do upload. Antes,
    -- duas coisas estavam erradas ao mesmo tempo: a coluna era editável em job
    -- concluído (mutabilidade arbitrária) e, quando fechei o INSERT pós-render
    -- para tapar isso, o caminho legítimo `local → storage` deixou de existir.
    -- O upload acontece DEPOIS do render, por definição.
    --
    -- A forma amarra a chave ao tenant, ao job e ao slot, e a validação do
    -- conteúdo é registrada à parte: `criativos/<tenant>/<job>/<slot>_<hash12>.<ext>`.
    storage_chave text,
    -- Quando o objeto foi conferido no armazenamento. NULL = subiu e ninguém
    -- conferiu, que é diferente de "não subiu".
    storage_conferido_em timestamptz,
    -- ⚠️ `null` NÃO é "hash bate". É "ninguém comparou o objeto remoto com o
    -- sha256 local". Afirmar coincidência sem download é afirmar o que não se mediu.
    storage_hash_conferido boolean,

    constraint criativo_render_artefato_bytes_positivos check (bytes > 0),
    constraint criativo_render_artefato_hash_forma check (sha256 ~ '^[0-9a-f]{64}$'),
    constraint criativo_render_artefato_medida_positiva check (
        (largura is null or largura > 0) and (altura is null or altura > 0)
        and (duracao_s is null or duracao_s > 0)
    ),
    constraint criativo_render_artefato_storage_forma check (
        -- Forma minima. A identidade (tenant/job/slot) e conferida pelo gatilho
        -- `criativo_render_storage_do_dono`, que usa a funcao unica de validacao
        -- — aqui so barra o que nem parece chave.
        storage_chave is null
        or (storage_chave ~ '^criativos/[A-Za-z0-9][A-Za-z0-9/_.-]*$'
            and storage_chave not like '%..%'
            and storage_chave not like '%//%'
            and storage_chave not like '%/')
    ),
    -- Conferência sem carimbo, ou carimbo sem conferência, é meia verdade.
    constraint criativo_render_artefato_conferencia_coerente check (
        (storage_conferido_em is null) = (storage_hash_conferido is null)
    ),
    -- Não se confere o que não subiu.
    constraint criativo_render_artefato_conferencia_exige_chave check (
        storage_conferido_em is null or storage_chave is not null
    )
);
create unique index if not exists criativo_render_artefato_slot_ux
    on public.criativo_render_artefato (recibo_id, slot);

-- ── 5. as validações ────────────────────────────────────────────────────────

create table if not exists public.criativo_render_validacao (
    id            uuid primary key default gen_random_uuid(),
    recibo_id     uuid not null references public.criativo_render_recibo(id),
    gate          text not null,
    resultado     text not null,
    -- O NÚMERO mora aqui.
    detalhe       jsonb,
    bloqueante    boolean not null,
    constraint criativo_render_validacao_resultado_valido
        check (resultado in ('PASS','WARN','FAIL','SKIPPED')),
    constraint criativo_render_validacao_gate_nao_vazio
        check (length(trim(gate)) > 0)
);
create index if not exists criativo_render_validacao_recibo
    on public.criativo_render_validacao (recibo_id);

-- ── 6. a máquina de estados, no banco ───────────────────────────────────────

create or replace function public.criativo_render_transicao_valida()
returns trigger
language plpgsql
as $$
declare
    permitido text[];
begin
    -- ⚠️ A conferencia de DONO vem ANTES do atalho de "estado nao mudou". A
    -- primeira versao retornava cedo quando o estado era o mesmo, e um
    -- `update ... set owner='outro'` sem mudar estado passava sem nenhuma
    -- guarda — exatamente o roubo de trabalho que a invariante 3 existe para
    -- impedir. O ciclo em cluster descartavel pegou.
    if old.estado in ('claimed','running','validating')
       and new.estado in ('claimed','running','validating')
       and new.owner is distinct from old.owner then
        raise exception
            'criativo_render_job %: o dono nao muda no meio da execucao (% -> %)',
            old.id, old.owner, new.owner
            using errcode = 'integrity_constraint_violation';
    end if;

    -- ⚠️ ACHADO ADVERSARIAL, o mais grave da auditoria. O atalho `if new.estado =
    -- old.estado then return new` matava TODAS as guardas quando o estado nao
    -- mudava. Media: `encomenda`, `seed`, `motor_slug` e ATE `tenant_id` eram
    -- reescritos num job `rendered`, sem uma linha de trilha. Como `tenant_id` do
    -- job e o unico filtro de leitura, isso entregava recibo e artefatos de um
    -- inquilino a outro. "Um job nao muda de pedido" era falso.
    if new.encomenda is distinct from old.encomenda
       or new.seed is distinct from old.seed
       or new.motor_slug is distinct from old.motor_slug
       or new.modo_slug is distinct from old.modo_slug
       or new.finalidade_slug is distinct from old.finalidade_slug
       or new.idempotency_key is distinct from old.idempotency_key
       or new.tenant_id is distinct from old.tenant_id
       or new.criado_em is distinct from old.criado_em
    then
        raise exception
            'criativo_render_job %: pedido, tenant e identidade sao imutaveis',
            old.id
            using errcode = 'integrity_constraint_violation';
    end if;

    -- A linhagem tambem: `retry_of` por UPDATE ligava job de um tenant a job
    -- terminal de OUTRO, furando as invariantes 4 e 6 de uma vez.
    if new.retry_of is distinct from old.retry_of
       or new.retry_n is distinct from old.retry_n then
        raise exception
            'criativo_render_job %: a linhagem so nasce no insert', old.id
            using errcode = 'integrity_constraint_violation';
    end if;

    if new.estado = old.estado then
        return new;
    end if;

    permitido := case old.estado
        when 'queued'     then array['claimed','cancelled']
        when 'claimed'    then array['running','failed','cancelled','queued']
        when 'running'    then array['validating','failed','cancelled','queued']
        when 'validating' then array['rendered','failed','cancelled']
        else array[]::text[]
    end;

    if not (new.estado = any(permitido)) then
        raise exception
            'criativo_render_job %: transicao proibida %  ->  %',
            old.id, old.estado, new.estado
            using errcode = 'integrity_constraint_violation';
    end if;

    -- ⚠️ INVARIANTE 1. A transição NÃO renova o lease. A versão local disto
    -- gravava `agora + 60s` em toda transição de execução, e passar de `claimed`
    -- para `running` ressuscitava um lease vencido. Renovar é trabalho do
    -- batimento, que confere dono.
    if new.estado in ('running','validating')
       and new.lease_ate is distinct from old.lease_ate then
        raise exception
            'criativo_render_job %: transicao nao renova lease. Use o batimento.',
            old.id
            using errcode = 'integrity_constraint_violation';
    end if;

    -- ⚠️ ACHADO #8. Nenhuma transicao conferia a VALIDADE do lease: um dono com
    -- lease vencido ha duas horas avancava `claimed -> running -> validating`
    -- livremente, e a devolucao dependia inteiramente de o reaper vencer a
    -- corrida. Agora o lease vencido barra o avanco na hora, e a corrida some:
    -- quem perdeu o prazo nao anda, tenha o reaper passado por ali ou nao.
    if new.estado in ('running', 'validating')
       and (old.lease_ate is null or old.lease_ate < now()) then
        raise exception
            'criativo_render_job %: lease vencido em % — nao avanca sem renovar',
            old.id, old.lease_ate
            using errcode = 'integrity_constraint_violation';
    end if;

    -- INVARIANTE 3: `rendered` exige recibo COM ARTEFATO.
    -- ⚠️ A primeira versao exigia so a linha do recibo. Media: um job chegava a
    -- `rendered`, com recibo de assinatura valida e ZERO artefatos, e a tela
    -- dizia "pronto" sobre peca nenhuma. Recibo sem artefato e promessa, nao prova.
    if new.estado = 'rendered' then
        if not exists (
            select 1 from public.criativo_render_recibo r
              join public.criativo_render_artefato a on a.recibo_id = r.id
             where r.job_id = old.id
        ) then
            raise exception
                'criativo_render_job %: nao se conclui sem recibo COM artefato', old.id
                using errcode = 'integrity_constraint_violation';
        end if;
    end if;

    -- ⚠️ `coalesce`: o CHECK `dono_coerente` OBRIGA `owner is null` fora de
    -- execucao, entao gravar `new.owner` deixava a trilha com autor NULO em todo
    -- `cancelled`, `failed` e `rendered` — exatamente os eventos que a invariante
    -- 4 chama de "explicito e AUDITAVEL".
    insert into public.criativo_render_transicao (job_id, de, para, por, motivo)
    values (old.id, old.estado, new.estado,
            coalesce(new.owner, old.owner, new.cancelado_por),
            case when new.estado = 'cancelled' then new.cancelado_motivo
                 when new.estado = 'failed' then new.falha_codigo end);

    return new;
end;
$$;

drop trigger if exists criativo_render_transicao_valida_tg on public.criativo_render_job;
create trigger criativo_render_transicao_valida_tg
    before update on public.criativo_render_job
    for each row execute function public.criativo_render_transicao_valida();

-- ── 7. imutabilidade do artefato depois de rendered ─────────────────────────

create or replace function public.criativo_render_artefato_imutavel()
returns trigger
language plpgsql
as $$
declare
    estado_do_job text;
begin
    select j.estado into estado_do_job
      from public.criativo_render_recibo r
      join public.criativo_render_job j on j.id = r.job_id
     where r.id = coalesce(new.recibo_id, old.recibo_id);

    if estado_do_job = 'rendered' then
        if tg_op <> 'UPDATE' then
            raise exception
                'criativo_render_artefato: nao se insere nem apaga artefato de '
                'job concluido'
                using errcode = 'integrity_constraint_violation';
        end if;

        -- ⚠️ CONTEUDO E SEMPRE IMUTAVEL. A chave e a conferencia sao endereco e
        -- auditoria, nao conteudo — mas elas so andam para FRENTE.
        if new.slot      is distinct from old.slot
           or new.mime   is distinct from old.mime
           or new.bytes  is distinct from old.bytes
           or new.sha256 is distinct from old.sha256
           or new.largura is distinct from old.largura
           or new.altura  is distinct from old.altura
           or new.duracao_s is distinct from old.duracao_s
           or new.recibo_id is distinct from old.recibo_id
        then
            raise exception
                'criativo_render_artefato: conteudo e imutavel depois de concluido'
                using errcode = 'integrity_constraint_violation';
        end if;

        -- ── A MAQUINA DE ESTADOS DO ARMAZENAMENTO ──
        --
        --   LOCAL                 chave NULL, conferencia NULL
        --   UPLOADED_UNVERIFIED   chave preenchida, conferencia NULL
        --   VERIFIED_OK           chave + carimbo + conferido = true
        --   VERIFIED_MISMATCH     chave + carimbo + conferido = false
        --
        -- Setas permitidas, e so estas:
        --   LOCAL -> UPLOADED_UNVERIFIED
        --   UPLOADED_UNVERIFIED -> VERIFIED_OK | VERIFIED_MISMATCH
        --   LOCAL -> VERIFIED_*   (upload e conferencia no mesmo UPDATE)
        --
        -- Nunca volta, nunca reaponta, e VERIFIED_* e final: mudar o veredito
        -- depois de conferido apagaria a auditoria de uma divergencia.

        -- 1. a chave nao se apaga nem se repontia
        if old.storage_chave is not null
           and new.storage_chave is distinct from old.storage_chave then
            raise exception
                'criativo_render_artefato: storage_chave ja aponta para %; nao se '
                'repontia nem se apaga', old.storage_chave
                using errcode = 'integrity_constraint_violation';
        end if;

        -- 2. conferido e terminal
        if old.storage_conferido_em is not null
           and (new.storage_conferido_em is distinct from old.storage_conferido_em
                or new.storage_hash_conferido is distinct from old.storage_hash_conferido)
        then
            raise exception
                'criativo_render_artefato: a conferencia de % ja foi registrada e '
                'nao se reescreve', old.storage_chave
                using errcode = 'integrity_constraint_violation';
        end if;

        -- 3. nao se confere o que nao subiu (vale tambem quando sobe no mesmo UPDATE)
        if new.storage_conferido_em is not null and new.storage_chave is null then
            raise exception
                'criativo_render_artefato: conferencia sem endereco no armazenamento'
                using errcode = 'integrity_constraint_violation';
        end if;

        -- 4. o UPDATE precisa avancar alguma coisa
        if new.storage_chave is not distinct from old.storage_chave
           and new.storage_conferido_em is not distinct from old.storage_conferido_em
        then
            raise exception
                'criativo_render_artefato: artefato de job concluido e imutavel'
                using errcode = 'integrity_constraint_violation';
        end if;
        return new;
    end if;
    return coalesce(new, old);
end;
$$;

-- ⚠️ `insert` tambem. A primeira versao cobria so UPDATE e DELETE, e qualquer
-- escritor podia ACRESCENTAR um artefato a um job ja concluido — com bytes e
-- hash nunca conferidos contra disco nenhum, porque o executor ja tinha saido.
drop trigger if exists criativo_render_artefato_imutavel_tg on public.criativo_render_artefato;
create trigger criativo_render_artefato_imutavel_tg
    before insert or update or delete on public.criativo_render_artefato
    for each row execute function public.criativo_render_artefato_imutavel();

-- ── 8. o recibo pertence ao tenant do job ───────────────────────────────────

create or replace function public.criativo_render_recibo_coerente()
returns trigger
language plpgsql
as $$
declare
    t text;
    estado_do_job text;
begin
    select tenant_id, estado into t, estado_do_job
      from public.criativo_render_job where id = new.job_id;
    if t is null then
        raise exception 'criativo_render_recibo: job % nao existe', new.job_id
            using errcode = 'foreign_key_violation';
    end if;
    if t is distinct from new.tenant_id then
        raise exception
            'criativo_render_recibo: tenant do recibo difere do tenant do job'
            using errcode = 'integrity_constraint_violation';
    end if;

    -- ⚠️ ACHADO #9. Nada ligava o recibo ao fato de ter havido producao: um
    -- recibo completo podia ser colado num job `failed`, `cancelled` ou `queued`.
    -- `rendered` exigia recibo; recibo nao exigia nada.
    --
    -- `validating` e a fase legitima: o arquivo existe, os portoes estao
    -- decidindo, e o recibo precisa estar gravado ANTES da conclusao — senao a
    -- transicao para `rendered` nao teria o que conferir. `rendered` tambem
    -- passa, para o UPDATE de `storage_chave` nao derrubar o proprio recibo.
    if estado_do_job not in ('validating', 'rendered') then
        raise exception
            'criativo_render_recibo: recibo so nasce em validating (job esta em %)',
            estado_do_job
            using errcode = 'integrity_constraint_violation';
    end if;

    -- ⚠️ ACHADO ADVERSARIAL (revisao de 2026-08-29). Este gatilho conferia
    -- tenant e estado, e liberava `rendered` para o UPDATE de storage. So que
    -- ele liberava o UPDATE INTEIRO: `assinatura`, `produzido_por`, `seed`,
    -- `versoes` e `parametros` de um recibo JA CONCLUIDO eram reescreviveis por
    -- quem tem GRANT de update — o papel privilegiado de producao. Um recibo que
    -- pode ser reescrito depois do fato nao prova mais nada, e provar era a
    -- unica coisa que ele existia para fazer. Medido: quatro forjas aceitas.
    --
    -- Depois de `rendered` o recibo e imutavel. Nao ha excecao de coluna aqui:
    -- `storage_chave` mora no ARTEFATO, e a imutabilidade dele ja tem gatilho
    -- proprio, com a excecao estreita da conferencia de storage.
    if tg_op = 'UPDATE' and estado_do_job = 'rendered' then
        if to_jsonb(new) is distinct from to_jsonb(old) then
            raise exception
                'criativo_render_recibo: recibo concluido e imutavel'
                using errcode = 'integrity_constraint_violation';
        end if;
    end if;
    return new;
end;
$$;

-- ── 8b. a validacao de um job concluido tambem e prova ──────────────────────
-- ⚠️ ACHADO ADVERSARIAL (revisao de 2026-08-29). `criativo_render_validacao`
-- nao tinha guarda nenhuma: o resultado de um gate podia ser reescrito de FAIL
-- para PASS, e gates novos podiam ser acrescentados DEPOIS do render. O veredito
-- de qualidade era editavel a posteriori por quem escreve.

create or replace function public.criativo_render_validacao_imutavel_apos_render()
returns trigger
language plpgsql
as $$
declare
    alvo uuid;
    estado_do_job text;
begin
    alvo := coalesce(new.recibo_id, old.recibo_id);
    select j.estado into estado_do_job
      from public.criativo_render_recibo r
      join public.criativo_render_job j on j.id = r.job_id
     where r.id = alvo;
    if estado_do_job = 'rendered' then
        raise exception
            'criativo_render_validacao: veredito de job concluido nao muda nem cresce'
            using errcode = 'integrity_constraint_violation';
    end if;
    return coalesce(new, old);
end;
$$;

drop trigger if exists criativo_render_validacao_imutavel_tg
    on public.criativo_render_validacao;
create trigger criativo_render_validacao_imutavel_tg
    before insert or update or delete on public.criativo_render_validacao
    for each row execute function public.criativo_render_validacao_imutavel_apos_render();

-- ⚠️ FUNCAO UNICA de construcao da chave. Antes o formato vivia como string
-- montada em dois lugares (gatilho e Python) e comparada por prefixo — e prefixo
-- parcial aceita `1x1-malicioso` quando o slot e `1x1`. Uma funcao so, usada
-- pelos dois lados, e a unica forma de os dois nao divergirem.
create or replace function public.criativo_storage_chave(
    p_tenant text, p_job uuid, p_slot text, p_sufixo text
) returns text
language sql immutable
as $$
    select 'criativos/' || p_tenant || '/' || p_job::text || '/' || p_slot || '__'
           || p_sufixo;
$$;

create or replace function public.criativo_storage_chave_valida(
    p_chave text, p_tenant text, p_job uuid, p_slot text
) returns boolean
language plpgsql immutable
as $$
declare
    prefixo text := 'criativos/' || p_tenant || '/' || p_job::text || '/' || p_slot || '__';
begin
    if p_chave is null then
        return true;
    end if;
    -- Formas nao canonicas: travessia, barra dupla, segmento vazio, barra final.
    if p_chave like '%..%' or p_chave like '%//%' or p_chave like '%/' then
        return false;
    end if;
    -- ⚠️ O delimitador `__` depois do slot e obrigatorio. Sem ele, o prefixo
    -- `criativos/T/J/1x1` casa tambem com `criativos/T/J/1x1-malicioso.png`, e a
    -- chave de um slot passaria a apontar para o objeto de outro.
    if position(prefixo in p_chave) <> 1 then
        return false;
    end if;
    -- Depois do delimitador tem de sobrar sufixo, e ele nao pode ter barra: a
    -- chave termina no objeto, nao abre outra pasta.
    return substr(p_chave, length(prefixo) + 1) ~ '^[A-Za-z0-9_.-]+$';
end;
$$;

create or replace function public.criativo_render_storage_do_dono()
returns trigger
language plpgsql
as $$
declare
    dono record;
begin
    if new.storage_chave is null then
        return new;
    end if;
    select j.tenant_id as tenant, j.id as job into dono
      from public.criativo_render_recibo r
      join public.criativo_render_job j on j.id = r.job_id
     where r.id = new.recibo_id;

    if dono is null then
        raise exception 'criativo_render_artefato: recibo % nao existe', new.recibo_id
            using errcode = 'foreign_key_violation';
    end if;
    if not public.criativo_storage_chave_valida(
        new.storage_chave, dono.tenant, dono.job, new.slot
    ) then
        raise exception
            'criativo_render_artefato: storage_chave nao pertence a este artefato. '
            'Esperado o prefixo %, veio %',
            public.criativo_storage_chave(dono.tenant, dono.job, new.slot, ''),
            new.storage_chave
            using errcode = 'integrity_constraint_violation';
    end if;
    return new;
end;
$$;

drop trigger if exists criativo_render_storage_do_dono_tg on public.criativo_render_artefato;
create trigger criativo_render_storage_do_dono_tg
    before insert or update on public.criativo_render_artefato
    for each row execute function public.criativo_render_storage_do_dono();

drop trigger if exists criativo_render_recibo_coerente_tg on public.criativo_render_recibo;
create trigger criativo_render_recibo_coerente_tg
    before insert or update on public.criativo_render_recibo
    for each row execute function public.criativo_render_recibo_coerente();

-- ── 9. a retomada só nasce de um terminal que não deu certo ─────────────────

create or replace function public.criativo_render_retomada_legitima()
returns trigger
language plpgsql
as $$
declare
    origem record;
begin
    if new.retry_of is null then
        return new;
    end if;
    select estado, tenant_id, retry_n into origem
      from public.criativo_render_job where id = new.retry_of;
    if origem is null then
        raise exception 'criativo_render_job: origem % nao existe', new.retry_of
            using errcode = 'foreign_key_violation';
    end if;
    if origem.tenant_id is distinct from new.tenant_id then
        raise exception 'criativo_render_job: nao se retoma trabalho de outro tenant'
            using errcode = 'integrity_constraint_violation';
    end if;
    -- INVARIANTE 4: `rendered` não se retoma — produziria a MESMA peça, pagando
    -- de novo. Quem quer outra peça muda o pedido.
    if origem.estado not in ('failed','cancelled') then
        raise exception
            'criativo_render_job: so se retoma failed ou cancelled (origem: %)',
            origem.estado
            using errcode = 'integrity_constraint_violation';
    end if;
    if new.retry_n <> origem.retry_n + 1 then
        raise exception
            'criativo_render_job: retry_n tem de ser % (veio %)',
            origem.retry_n + 1, new.retry_n
            using errcode = 'integrity_constraint_violation';
    end if;
    return new;
end;
$$;

drop trigger if exists criativo_render_retomada_legitima_tg on public.criativo_render_job;
create trigger criativo_render_retomada_legitima_tg
    before insert on public.criativo_render_job
    for each row execute function public.criativo_render_retomada_legitima();

-- ── 10. a trilha é append-only ──────────────────────────────────────────────

create or replace function public.criativo_render_transicao_append_only()
returns trigger
language plpgsql
as $$
begin
    raise exception 'criativo_render_transicao e append-only'
        using errcode = 'integrity_constraint_violation';
end;
$$;

drop trigger if exists criativo_render_transicao_append_only_tg
    on public.criativo_render_transicao;
create trigger criativo_render_transicao_append_only_tg
    before update or delete on public.criativo_render_transicao
    for each row execute function public.criativo_render_transicao_append_only();

-- ── 11. segurança ───────────────────────────────────────────────────────────
-- ⚠️ ACHADO H. O ACL padrão de `public` concede `arwdDxt` a anon, authenticated
-- E service_role em toda tabela nova. REVOKE de todos, GRANT mínimo ao
-- service_role. Sem DELETE: apagar job é apagar auditoria.

do $seguranca$
declare
    t text;
begin
    foreach t in array array[
        'criativo_render_job', 'criativo_render_transicao', 'criativo_render_recibo',
        'criativo_render_artefato', 'criativo_render_validacao'
    ] loop
        execute format('alter table public.%I enable row level security', t);
        execute format('alter table public.%I force row level security', t);
        execute format('revoke all on public.%I from public, anon, authenticated, service_role', t);
        execute format('grant select, insert, update on public.%I to service_role', t);
    end loop;
    -- A trilha não é atualizável nem pelo service_role.
    revoke update on public.criativo_render_transicao from service_role;
    grant usage, select on sequence public.criativo_render_transicao_id_seq to service_role;
end
$seguranca$;

-- ── 12. verificação embutida ────────────────────────────────────────────────

do $verifica$
declare
    n_tab integer; n_rls integer; n_pol integer; n_trg integer; n_priv integer;
begin
    select count(*) into n_tab from pg_tables
     where schemaname='public' and tablename like 'criativo_render_%';
    select count(*) into n_rls from pg_class c join pg_namespace n on n.oid=c.relnamespace
     where n.nspname='public' and c.relname like 'criativo_render_%'
       and c.relkind='r' and c.relrowsecurity and c.relforcerowsecurity;
    select count(*) into n_pol from pg_policies
     where schemaname='public' and tablename like 'criativo_render_%';
    select count(*) into n_trg from pg_trigger t join pg_class c on c.oid=t.tgrelid
     join pg_namespace n on n.oid=c.relnamespace
     where n.nspname='public' and c.relname like 'criativo_render_%' and not t.tgisinternal;
    select count(*) into n_priv from information_schema.role_table_grants
     where table_schema='public' and table_name like 'criativo_render_%'
       and grantee in ('anon','authenticated','PUBLIC');

    if n_tab <> 5 then raise exception 'v11_03: esperava 5 tabelas, achei %', n_tab; end if;
    if n_rls <> 5 then raise exception 'v11_03: RLS forcada em % de 5', n_rls; end if;
    if n_pol <> 0 then raise exception 'v11_03: esperava 0 policies, achei %', n_pol; end if;
    if n_trg < 6 then raise exception 'v11_03: esperava >=6 gatilhos, achei %', n_trg; end if;
    if n_priv <> 0 then raise exception 'v11_03: anon/authenticated tem % privilegio(s)', n_priv; end if;

    raise notice 'v11_03 OK: 5 tabelas, RLS forcada, 0 policies, % gatilhos.', n_trg;
end
$verifica$;

commit;
