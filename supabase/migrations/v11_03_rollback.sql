-- =============================================================================
-- v11_03 ROLLBACK — derruba a execução criativa persistida
-- =============================================================================
-- ⚠️ TRANSACIONAL. Sem `begin`, o `psql -f` autocomita cada DROP e um aborto no
-- meio deixa o banco num estado que não é nem o de antes nem o de depois. Já
-- aconteceu neste projeto: o rollback da v11_01 destruía as aprovações humanas
-- ANTES de "abortar em segurança".
--
-- ⚠️ ESTE ARQUIVO É RODADO, NÃO SÓ ESCRITO. `scripts/provar-ciclo-v11_03.sh` o
-- executa a cada rodada, num cluster descartável.
--
-- -----------------------------------------------------------------------------
-- O QUE ELE APAGA, E O QUE NÃO É RECONSTRUÍVEL
-- -----------------------------------------------------------------------------
-- `criativo_render_transicao` é a trilha append-only de quem mudou o quê e
-- quando. Ela é a base de "failed só volta por gesto explícito e AUDITÁVEL":
-- sem ela, a retomada continua explícita e vira invisível. NÃO é reconstruível.
--
-- `criativo_render_recibo` + `artefato` + `validacao` são a prova de que uma
-- peça foi produzida com determinada semente, versões e hashes. Perder isso é
-- perder a capacidade de responder "esta peça é a mesma de ontem?".
--
-- EXPORTE ANTES:
--   \copy public.criativo_render_transicao TO 'transicao.csv' CSV HEADER
--   \copy public.criativo_render_recibo    TO 'recibo.csv'    CSV HEADER
--   \copy public.criativo_render_artefato  TO 'artefato.csv'  CSV HEADER
--
-- As tabelas das v11_01/v11_02 não são tocadas — e a verificação final confere
-- isso POR NOME, não por contagem.
--
-- -----------------------------------------------------------------------------
-- A PROMESSA, EXATAMENTE (achado A2)
-- -----------------------------------------------------------------------------
-- O cabeçalho anterior dizia "uma v11_04 futura não impede reverter esta". Meia
-- verdade, e por isso um defeito: uma v11_04 que ACRESCENTA tabelas de fato não
-- impede — mas uma que APOSENTA uma das 21 (por exemplo
-- `drop table public.criativo_pacote cascade`) fazia este rollback abortar com
-- "tabela(s) da v11_01/02 sumiram", justamente na hora em que reverter é o que
-- se precisa. Isto é o que se promete agora, e é o que se entrega:
--
--   • uma v11_04 que ACRESCENTA tabelas não impede reverter esta;
--   • uma v11_01/02 MUTILADA (tabela trocada, renomeada, restaurada pela metade)
--     continua ABORTANDO por padrão — é o sinal de "esta não é a base que você
--     pensa que é";
--   • se a base encolheu DE PROPÓSITO, há um escape explícito e auditável:
--         psql ... -v v11_03_base_encolhida=confirmo -f v11_03_rollback.sql
--     que registra um WARNING nomeando as tabelas ausentes e segue.
--
-- -----------------------------------------------------------------------------
-- POR QUE O DEFAULT CONTINUA SENDO ABORTAR, SE NÃO HÁ DEPENDÊNCIA
-- -----------------------------------------------------------------------------
-- Medido em cluster descartável, com a v11_01+v11_02+v11_03 aplicadas, por três
-- caminhos independentes, todos com resultado VAZIO:
--   1. `pg_constraint contype='f'` saindo de `criativo_render_*` para fora dela;
--   2. `pg_depend` das 5 tabelas e das 9 funções contra as 21 tabelas da base;
--   3. `pg_proc.prosrc` das 9 funções citando qualquer uma das 21.
-- Ou seja: este rollback dropa 5 tabelas, 9 funções e 7 gatilhos que são TODOS
-- dele, e não precisa de NENHUMA tabela da v11_01/02 para concluir.
--
-- A conferência, então, não é um pré-requisito técnico — é um CANÁRIO. Ela custa
-- nada e pega o erro que mais dói: rodar o rollback no banco errado, ou num
-- restore parcial, achando que se está revertendo a v11_03 do ambiente certo.
-- Um canário que não pode ser desligado deixa de ser canário e vira grade; por
-- isso ele grita por padrão e tem uma chave, em vez de sumir.
--
-- O token é `confirmo` e mais nenhum: qualquer outro valor ABORTA dizendo o
-- token esperado, para que um `-v v11_03_base_encolhida=1` digitado às pressas
-- não passe como consentimento.
-- =============================================================================

\set ON_ERROR_STOP on

-- Escape do canário acima. Só define o padrão vazio quando a linha de comando
-- NÃO passou a variável — `:{?nome}` (psql >= 10) pergunta se ela existe, e sem
-- este `\if` um `-v` do operador seria sobrescrito pelo próprio arquivo.
\if :{?v11_03_base_encolhida}
\else
\set v11_03_base_encolhida ''
\endif

begin;

-- A interpolação `:'...'` do psql NÃO acontece dentro de string dollar-quoted,
-- então o valor entra no bloco `do $verifica$` por GUC de transação. `is_local
-- => true`: morre no commit/rollback, não vaza para a sessão.
select set_config('v11_03.base_encolhida', :'v11_03_base_encolhida', true) \g /dev/null

do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception 'v11_03_rollback deve rodar como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
end
$guarda$;

drop trigger if exists criativo_render_transicao_append_only_tg on public.criativo_render_transicao;
drop trigger if exists criativo_render_retomada_legitima_tg on public.criativo_render_job;
drop trigger if exists criativo_render_recibo_coerente_tg on public.criativo_render_recibo;
-- Gatilho da revisao de 2026-08-29: veredito de job concluido nao muda nem cresce.
drop trigger if exists criativo_render_validacao_imutavel_tg on public.criativo_render_validacao;
drop trigger if exists criativo_render_artefato_imutavel_tg on public.criativo_render_artefato;
drop trigger if exists criativo_render_storage_do_dono_tg on public.criativo_render_artefato;
drop trigger if exists criativo_render_transicao_valida_tg on public.criativo_render_job;

drop function if exists public.criativo_render_transicao_append_only();
drop function if exists public.criativo_render_retomada_legitima();
drop function if exists public.criativo_render_recibo_coerente();
drop function if exists public.criativo_render_validacao_imutavel_apos_render();
drop function if exists public.criativo_render_artefato_imutavel();
drop function if exists public.criativo_render_storage_do_dono();
drop function if exists public.criativo_storage_chave_valida(text, text, uuid, text);
drop function if exists public.criativo_storage_chave(text, uuid, text, text);
drop function if exists public.criativo_render_transicao_valida();

-- Ordem inversa da dependência.
drop table if exists public.criativo_render_validacao;
drop table if exists public.criativo_render_artefato;
drop table if exists public.criativo_render_recibo;
drop table if exists public.criativo_render_transicao;
drop table if exists public.criativo_render_job;

do $verifica$
declare
    n_tab integer; n_fun integer;
    sobrando text[];
    faltando text[];
    escape text := coalesce(current_setting('v11_03.base_encolhida', true), '');
    -- ⚠️ DEFEITO D3, corrigido. Antes: `if n_v11 <> 21 then raise exception`.
    -- Aquele numero acoplava o rollback da v11_03 a uma contagem que qualquer
    -- migration POSTERIOR muda, e o efeito era invertido: uma v11_04 legitima
    -- nao quebraria a v11_03 — quebraria a capacidade de REVERTE-la, justamente
    -- na hora em que reverter e o que se precisa. E o numero nao expressava a
    -- intencao: 21 tabelas com uma trocada por outra tambem da 21.
    --
    -- A intencao real e "nenhuma tabela da v11_01/v11_02 pode ter sumido". Isso
    -- se confere por NOME, e uma tabela a mais deixa de ser um problema.
    -- Escolhemos a lista literal, e nao `>= 21`, porque `>= 21` continuaria
    -- aceitando a troca de uma tabela por outra — o caso que mais assusta, ja
    -- que e o unico que a contagem nunca ia ver.
    esperadas text[] := array[
        'criativo_motor', 'criativo_modo_de_producao', 'criativo_formato',
        'criativo_finalidade', 'criativo_exigencia_de_canal', 'criativo_teto_combinado',
        'criativo_skin', 'criativo_voz', 'criativo_gate', 'criativo_master_gate',
        'criativo_master_direito', 'criativo_brand_pack', 'criativo_projeto',
        'criativo_briefing', 'criativo_job', 'criativo_job_evento', 'criativo_master',
        'criativo_rendition', 'criativo_aprovacao', 'criativo_pacote', 'criativo_entrega'
    ];
begin
    select count(*) into n_tab from pg_tables
     where schemaname='public' and tablename like 'criativo_render_%';

    -- ⚠️ DEFEITO D1, corrigido. Antes esta contagem era so
    -- `p.proname like 'criativo_render_%'`, e DUAS das nove funcoes criadas pela
    -- v11_03 nao casam com esse prefixo: `criativo_storage_chave` e
    -- `criativo_storage_chave_valida`. Os DROPs delas sempre estiveram acima, de
    -- modo que o ciclo feliz nunca acusou nada — mas um leftover DELAS (uma
    -- sobrecarga com outra assinatura, por exemplo) passava como reversao
    -- bem-sucedida, e leftover de funcao e exatamente o que faz a reaplicacao
    -- seguinte encontrar assinatura antiga. A conferencia agora cobre as NOVE, e
    -- diz quais sobraram em vez de so contar.
    select coalesce(array_agg(p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')'
                              order by p.proname), '{}')
      into sobrando
      from pg_proc p join pg_namespace n on n.oid=p.pronamespace
     where n.nspname='public'
       and (p.proname like 'criativo_render_%' or p.proname like 'criativo_storage_chave%');

    select coalesce(array_agg(e order by e), '{}') into faltando
      from unnest(esperadas) e
     where not exists (select 1 from pg_tables t
                        where t.schemaname='public' and t.tablename = e);

    if n_tab <> 0 then raise exception 'v11_03_rollback: sobraram % tabela(s)', n_tab; end if;
    if cardinality(sobrando) <> 0 then
        raise exception 'v11_03_rollback: sobraram funcao(oes) da v11_03: %',
            array_to_string(sobrando, ', ');
    end if;
    -- ⚠️ ACHADO A2, corrigido. Este ramo continua sendo o DEFAULT: base mutilada
    -- aborta, e o rollback inteiro volta atras (e `begin/commit`, nao ha meia
    -- reversao). O que mudou e que agora existe uma chave, e ela e explicita,
    -- nomeada e registrada no log — nao um `>= 21` frouxo que aceitaria tambem a
    -- troca silenciosa de uma tabela por outra.
    if cardinality(faltando) <> 0 then
        if escape = 'confirmo' then
            raise warning
                'v11_03_rollback: ESCAPE ACIONADO (-v v11_03_base_encolhida=confirmo). Tabela(s) da v11_01/02 ausente(s): %. Seguindo porque o rollback da v11_03 nao depende delas (sem FK, sem pg_depend, sem citacao no corpo das 9 funcoes). Se voce NAO aposentou essas tabelas de proposito, esta e a base errada.',
                array_to_string(faltando, ', ');
        elsif escape = '' then
            raise exception
                'v11_03_rollback: tabela(s) da v11_01/02 sumiram: %. O rollback nao toca nelas e nao depende delas — isto e um canario de "base errada ou restore parcial". Se a base encolheu DE PROPOSITO (uma v11_04 aposentou a tabela), rode com: psql ... -v v11_03_base_encolhida=confirmo -f v11_03_rollback.sql',
                array_to_string(faltando, ', ');
        else
            raise exception
                'v11_03_rollback: v11_03_base_encolhida=<%> nao e consentimento. O unico token aceito e ''confirmo''; tabela(s) ausente(s): %',
                escape, array_to_string(faltando, ', ');
        end if;
    end if;
    if cardinality(faltando) = 0 then
        raise notice 'v11_03_rollback OK: execucao removida, as % tabelas da v11_01/02 intactas (por nome).',
            cardinality(esperadas);
    else
        raise notice 'v11_03_rollback OK: execucao removida; % das % tabelas da v11_01/02 estavam ausentes e o escape foi aceito.',
            cardinality(faltando), cardinality(esperadas);
    end if;
end
$verifica$;

commit;
