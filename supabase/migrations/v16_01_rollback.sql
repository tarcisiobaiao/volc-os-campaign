-- =============================================================================
-- v16_01 ROLLBACK — desfaz procedencia de modelo, composicao e anexo
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin.
--
-- ⚠️ ESTE ROLLBACK APAGA DADOS, e o aviso e literal: as colunas de procedencia
-- guardam o modelo SERVIDO e os hashes que provam o que gerou cada peca. Nenhum
-- deles e recuperavel depois do DROP. A tabela de anexos some junto, e com ela a
-- ligacao entre um job e a fotografia que o operador anexou — os ARQUIVOS
-- continuam no armazenamento, orfaos.
--
-- Rode isto so quando a v16_01 nao puder ficar. Para uma reversao de
-- emergencia que preserve os dados, prefira parar de ESCREVER nas colunas
-- (basta o codigo antigo) e deixar as colunas nulas onde estao: elas sao todas
-- NULLABLE e nao quebram nenhum caminho anterior.
--
-- ORDEM DE DESMONTE: a funcao volta primeiro (ela referencia as colunas), as
-- constraints depois, as colunas por ultimo.
-- =============================================================================

\set ON_ERROR_STOP on

begin;


-- =============================================================================
-- 1. A FUNCAO DE IMUTABILIDADE VOLTA A FORMA DA v11_02
-- =============================================================================
-- Precisa vir ANTES do drop das colunas: uma funcao que cita `new.modelo_pedido`
-- com a coluna ausente falha no proximo UPDATE, nao no `create or replace`.

do $imutabilidade$
begin
    if not exists (
        select 1 from pg_proc where proname = 'criativo_master_imutavel'
    ) then
        return;
    end if;

    -- ⚠️ O corpo abaixo e o da v11_02 na INTEGRA, incluindo a guarda de
    -- arquivamento e os `errcode`. Reescrever a partir de um resumo foi o
    -- defeito que a revisao adversarial pegou na versao anterior desta rodada.
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
        then
            raise exception
                'criativo_master %: conteudo, procedencia e declaracao sao imutaveis. Crie uma versao nova (versao=%).',
                old.id, old.versao + 1
                using errcode = 'integrity_constraint_violation';
        end if;

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
    $corpo$;
end
$imutabilidade$;


-- =============================================================================
-- 2. O ANEXO
-- =============================================================================

drop index if exists public.criativo_agente_anexo_operacao_ix;
drop table if exists public.criativo_agente_anexo;


-- =============================================================================
-- 3. CONSTRAINTS DAS COLUNAS NOVAS
-- =============================================================================
-- Nomeadas uma a uma, e nao por varredura: um `drop constraint` derivado de
-- consulta apagaria tambem constraints homonimas criadas por outra migration.

alter table public.criativo_job
    drop constraint if exists criativo_job_prompt_sha_forma,
    drop constraint if exists criativo_job_anexo_sha_forma,
    drop constraint if exists criativo_job_plano_sha_forma,
    drop constraint if exists criativo_job_qualidade_valida,
    drop constraint if exists criativo_job_modo_composicao_valido,
    drop constraint if exists criativo_job_teto_nao_negativo,
    drop constraint if exists criativo_job_autorizacao_completa;

alter table public.criativo_master
    drop constraint if exists criativo_master_prompt_sha_forma,
    drop constraint if exists criativo_master_anexo_sha_forma,
    drop constraint if exists criativo_master_qualidade_valida;

alter table public.criativo_rendition
    drop constraint if exists criativo_rendition_canvas_completo,
    drop constraint if exists criativo_rendition_canvas_positivo,
    drop constraint if exists criativo_rendition_posicao_nao_negativa,
    drop constraint if exists criativo_rendition_crop_completo,
    drop constraint if exists criativo_rendition_crop_positivo,
    drop constraint if exists criativo_rendition_escala_positiva,
    drop constraint if exists criativo_rendition_posicao_completa,
    drop constraint if exists criativo_rendition_compositor_com_versao;


-- =============================================================================
-- 4. AS COLUNAS
-- =============================================================================

alter table public.criativo_job
    drop column if exists modelo_pedido,
    drop column if exists modelo_servido,
    drop column if exists qualidade,
    drop column if exists prompt_sha256,
    drop column if exists anexo_sha256,
    drop column if exists teto_custo_usd,
    drop column if exists plano_sha256,
    drop column if exists autorizado_por,
    drop column if exists autorizado_em,
    drop column if exists modo_de_composicao;

alter table public.criativo_master
    drop column if exists modelo_pedido,
    drop column if exists modelo_servido,
    drop column if exists qualidade,
    drop column if exists prompt_sha256,
    drop column if exists anexo_sha256;

alter table public.criativo_rendition
    drop column if exists canvas_largura,
    drop column if exists canvas_altura,
    drop column if exists crop_x,
    drop column if exists crop_y,
    drop column if exists crop_largura,
    drop column if exists crop_altura,
    drop column if exists escala,
    drop column if exists posicao_x,
    drop column if exists posicao_y,
    drop column if exists compositor,
    drop column if exists compositor_versao;


-- =============================================================================
-- 5. VERIFICACAO EMBUTIDA
-- =============================================================================

do $verificacao$
declare
    n integer;
begin
    select count(*) into n
    from information_schema.columns
    where table_schema = 'public'
      and table_name in ('criativo_job', 'criativo_master', 'criativo_rendition')
      and column_name in ('modelo_pedido', 'modelo_servido', 'qualidade',
                          'prompt_sha256', 'anexo_sha256', 'plano_sha256',
                          'canvas_largura', 'compositor', 'compositor_versao');
    if n <> 0 then
        raise exception 'v16_01 ROLLBACK FALHOU: sobraram % colunas', n;
    end if;

    if to_regclass('public.criativo_agente_anexo') is not null then
        raise exception 'v16_01 ROLLBACK FALHOU: criativo_agente_anexo ainda existe';
    end if;

    raise notice 'v16_01 ROLLBACK OK: schema de volta ao estado anterior.';
end
$verificacao$;

commit;
