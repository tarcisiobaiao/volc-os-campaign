-- =============================================================================
-- v11_01 — Estudio Criativo: projeto, briefing, job, master, rendition,
--          aprovacao, pacote de destino e entrega
-- ESTUDIO CRIATIVO VOLC / FASE C0+C1+C3. NAO APLICADA EM PRODUCAO.
-- =============================================================================
-- APLICAR COMO: postgres (supabase_admin tambem serve; a guarda aceita os dois)
--
-- ORDEM: INDEPENDENTE das series v9 e v10. Este arquivo nao referencia
--        `trafego_*` de proposito: o Estudio produz patrimonio criativo e o
--        Trafego CONSOME por id. Amarrar as duas series aqui faria o Estudio
--        nascer preso a um destino, e destino e justamente o que a SPEC manda
--        manter do lado de fora (SPEC secao 2).
-- ROLLBACK: supabase/migrations/v11_01_rollback.sql  (executavel, e RODADO —
--           ver scripts/provar-ciclo-v11.sh)
--
-- -----------------------------------------------------------------------------
-- O CICLO QUE ESTE ARQUIVO PERSISTE
-- -----------------------------------------------------------------------------
--
--   projeto -> briefing -> job -> (evento*) -> master -> rendition*
--           -> aprovacao -> pacote de destino -> entrega
--
-- Nove tabelas, e cada uma existe porque um degrau desse ciclo precisa
-- sobreviver a uma queda de processo, a um refresh do navegador ou a um retry:
--
--   criativo_brand_pack   identidade visual versionada, com hash das fontes
--   criativo_projeto      a intencao duravel que pode gerar muitas versoes
--   criativo_briefing     objetivo, mensagem, formatos pedidos, restricoes
--   criativo_job          UMA execucao de um briefing por um motor e versao
--   criativo_job_evento   diario append-only do job; e o cursor do SSE
--   criativo_master       a saida principal preservada, com procedencia e hash
--   criativo_rendition    derivacao do master por formato/uso, com erro PROPRIO
--   criativo_aprovacao    decisao humana por VERSAO e por FINALIDADE
--   criativo_pacote       selecao validada para um destino (google/meta/organico)
--   criativo_entrega      tentativa explicita de entregar um pacote, com recibo
--
-- -----------------------------------------------------------------------------
-- O REQUISITO MAIS IMPORTANTE DO ARQUIVO: "O OPERADOR CLICOU GERAR DUAS VEZES"
-- -----------------------------------------------------------------------------
-- Um job de imagem custa dinheiro por peca. Duplo clique, refresh no meio do
-- POST, retry de rede e reenvio do formulario sao a mesma coisa para o banco:
-- duas requisicoes com o mesmo conteudo. A defesa tem TRES camadas, e nenhuma
-- depende de o executor lembrar de nada:
--
--  1. CHAVE DERIVADA DO CONTEUDO, NAO SORTEADA. `criativo_job.idempotency_key`
--     e o sha256 de (briefing_id + motor + versao + formatos + insumo). Se o
--     operador NAO mudou nada, a segunda submissao produz a MESMA chave e o
--     backend devolve o job que ja existe. Se ele mudou o briefing, a chave
--     muda e o job novo e outra coisa — que e a verdade. Uma chave sorteada
--     faria todo reenvio parecer um pedido novo, e cobraria por ele.
--
--  2. UM JOB POR CHAVE, FISICAMENTE. `criativo_job_idem_ux` e UNIQUE sobre
--     `idempotency_key`. Nao e indice parcial por estado: um job que falhou
--     continua ocupando a chave, e isso e proposital — retry e uma TENTATIVA
--     nova dentro do MESMO job (`tentativa`), nao um job novo. Cobrar de novo
--     tem de ser um ato explicito, com briefing novo e chave nova.
--
--  3. UM MASTER POR (JOB, SLOT, VERSAO). `criativo_master_slot_ux` impede que um
--     retry que reprocessa o lote inteiro crie um segundo master para um formato
--     que ja tinha concluido NA MESMA VERSAO. Retry preenche buraco; ele nao
--     reescreve o que deu certo.
--
--     ⚠️ A `versao` faz parte da chave, e isso e deliberado: a doutrina desta
--     migration e que "uma correcao cria linha nova com `versao` maior". A
--     consequencia, que precisa ficar dita em vez de descoberta: um escritor que
--     grave `versao+1` PODE ter dois masters do mesmo slot, e e responsabilidade
--     dele que o segundo seja de fato uma versao nova, e nao uma duplicata. O
--     executor de hoje grava `versao` fixa em 1 e nao alcanca esse caso.
--
-- -----------------------------------------------------------------------------
-- AS REGRAS DA CASA, HERDADAS DA v9/v10 E VALIDAS AQUI SEM EXCECAO
-- -----------------------------------------------------------------------------
-- A. NENHUM NUMERO SEM FRESCOR. Medida e instante viajam juntos. As CHECKs
--    `..._sem_carimbo` recusam o par incompleto (custo sem `medido_em`,
--    aprovacao sem `decidido_em`).
-- B. AUSENCIA E NULL, NUNCA ZERO. Nenhuma coluna de MEDIDA tem DEFAULT 0.
--    `largura`, `altura`, `bytes_totais`, `duracao_ms` e `custo_usd` sao
--    NULL quando ninguem mediu, e as CHECKs recusam <= 0. Isto espelha
--    `volc_ads/criativo/contrato.py` linha a linha, e nao por gosto: um
--    validador que le 0 como medida reprova o que nao mediu e aprova o que
--    mediu errado.
-- C. FALHA DE UMA PECA NAO CONTAMINA AS OUTRAS. O erro e coluna da RENDITION
--    (`erro_codigo`, `erro_mensagem`, `erro_em`, `erro_permanente`), nunca do
--    job. O job AGREGA (`parcial`); ele nao substitui. Um lote de 3 formatos
--    com 1 recusado entrega 2 e registra 1 falha.
-- D. DECLARADO E OBSERVADO NAO DIVIDEM COLUNA. `criativo_rendition.
--    largura_pedida` e o que o contrato pediu; `largura` e o que foi medido
--    nos bytes. `nativo_largura` e o que o provider realmente entregou antes
--    da normalizacao. Tres fatos, tres colunas — porque a pergunta "houve
--    crop?" so e respondivel se os tres existirem separados.
-- E. PROCEDENCIA E OBRIGATORIA. `motor`, `motor_versao` e `insumo_hash` sao
--    NOT NULL no master. Um asset sem procedencia nao responde "o que produziu
--    o criativo que performou?", e sem essa resposta o aprendizado nao fecha.
-- F. IMPORTAR NAO E PRODUZIR. `criativo_job.procedencia_execucao` distingue
--    `volc_os` (nos rodamos) de `observado` (lemos um build que ja existia).
--    A CHECK `criativo_job_observado_sem_custo_proprio` impede que um job
--    observado declare custo nosso. Dizer que o VOLC O.S. renderizou um video
--    que ele apenas leu e a mentira mais facil de cometer nesta fatia.
-- G. NINGUEM APAGA. Nenhum DELETE e concedido. Exclusao e logica
--    (`arquivado_em`), e a CHECK impede arquivar o que esta aprovado.
--
-- -----------------------------------------------------------------------------
-- O QUE ESTE ARQUIVO NAO FAZ
-- -----------------------------------------------------------------------------
-- Nao cria bucket de storage. `storage_chave` e uma referencia opaca resolvida
-- pelo backend; qual bucket, qual provedor e qual prefixo e decisao de
-- infraestrutura, e colocar isso na coluna amarraria o banco ao storage de
-- hoje. Nao guarda bytes: nenhuma coluna e `bytea` nem base64 (SPEC secao 14).
-- Nao concede nada a `anon` nem a `authenticated`: o unico caminho ate estas
-- tabelas e o backend autenticado, com `service_role`.
-- =============================================================================

\set ON_ERROR_STOP on

-- -----------------------------------------------------------------------------
-- 0. GUARDA DE PAPEL
-- -----------------------------------------------------------------------------
-- Aplicar como um papel sem OWNER correto deixa as tabelas com dono errado e o
-- rollback falha depois, no pior momento. A guarda aborta antes de criar nada.
do $guarda$
begin
    if current_user not in ('postgres', 'supabase_admin') then
        raise exception
            'v11_01 deve ser aplicada como postgres ou supabase_admin (atual: %)',
            current_user;
    end if;
end
$guarda$;


-- =============================================================================
-- 1. BRAND PACK — identidade visual versionada
-- =============================================================================
-- Versionada porque uma peca aprovada em setembro precisa continuar dizendo
-- QUAL identidade ela usou, mesmo depois que a marca mudar de paleta. O
-- Positivo guarda isto em `localStorage` (evidencia: `src/lib/api.ts:512`,
-- comentario literal "localStorage is the durable source of truth"), e por isso
-- perde a resposta assim que o navegador limpa. Aqui e linha de banco.

create table if not exists public.criativo_brand_pack (
    id              uuid primary key default gen_random_uuid(),
    slug            text not null,
    versao          integer not null,
    nome            text not null,
    -- Tokens de marca como dado, nunca como `if` no codigo: paleta, tipografia,
    -- regras de logo. O formato e do consumidor; o banco guarda e versiona.
    tokens          jsonb not null,
    -- Hash do conjunto de fontes vendorizadas. Sem ele, "a peca usou a fonte da
    -- marca" e afirmacao sem prova, e o gate tipografico da PRENSA mede outra
    -- coisa do que renderizou.
    fontes_hash     text,
    ativo           boolean not null default true,
    criado_em       timestamptz not null default now(),
    criado_por      uuid,

    constraint criativo_brand_pack_slug_versao_ux unique (slug, versao),
    constraint criativo_brand_pack_versao_positiva check (versao >= 1),
    constraint criativo_brand_pack_slug_forma
        check (slug ~ '^[a-z0-9][a-z0-9_-]{1,62}$')
);

comment on table public.criativo_brand_pack is
    'Identidade visual versionada. Uma peca aprovada aponta para a VERSAO que usou.';


-- =============================================================================
-- 2. PROJETO — a intencao duravel
-- =============================================================================

create table if not exists public.criativo_projeto (
    id              uuid primary key default gen_random_uuid(),
    titulo          text not null,
    objetivo        text,
    brand_pack_id   uuid references public.criativo_brand_pack(id),
    dono_id         uuid,
    -- De onde o projeto nasceu. `trafego` e `conteudo` importam porque a volta
    -- ao chamador e um contrato (SPEC secao 12); `standalone` e patrimonio sem
    -- destino imediato, e isso e um estado legitimo, nao um buraco.
    origem          text not null default 'standalone',
    arquivado_em    timestamptz,
    criado_em       timestamptz not null default now(),
    atualizado_em   timestamptz not null default now(),

    constraint criativo_projeto_titulo_nao_vazio check (btrim(titulo) <> ''),
    constraint criativo_projeto_origem_valida
        check (origem in ('standalone', 'trafego', 'conteudo', 'importado'))
);

create index if not exists criativo_projeto_criado_ix
    on public.criativo_projeto (criado_em desc);


-- =============================================================================
-- 3. BRIEFING — o pedido, imutavel depois que vira job
-- =============================================================================
-- `formatos_pedidos` e jsonb e nao tabela filha de proposito: ele e o PEDIDO,
-- congelado, e entra no hash de idempotencia. Uma tabela filha convidaria a
-- editar formato depois que o job rodou, e ai a chave de idempotencia deixaria
-- de descrever o que foi executado.

create table if not exists public.criativo_briefing (
    id                    uuid primary key default gen_random_uuid(),
    projeto_id            uuid not null references public.criativo_projeto(id),
    tipo                  text not null,
    modo                  text not null,
    objetivo              text,
    audiencia             text,
    mensagem              text,
    brand_pack_id         uuid references public.criativo_brand_pack(id),
    -- Lista de formatos pedidos: [{"slot":"1x1","largura":1080,"altura":1080}, ...]
    formatos_pedidos      jsonb not null,
    -- Destinos PRETENDIDOS. Pretender nao valida e nao autoriza (SPEC secao 5).
    destinos_pretendidos  text[] not null default '{}',
    restricoes            jsonb not null default '{}'::jsonb,
    fatos                 jsonb not null default '[]'::jsonb,
    referencias           jsonb not null default '[]'::jsonb,
    criado_em             timestamptz not null default now(),
    criado_por            uuid,

    constraint criativo_briefing_tipo_valido
        check (tipo in ('imagem', 'video', 'audio', 'texto')),
    -- Os seis modos oficiais do ADR-001. `full_llm` e o unico implementado
    -- nesta fatia; os outros existem no vocabulario para que o dado nao precise
    -- migrar quando o adapter chegar, e a interface NAO os oferece como prontos.
    constraint criativo_briefing_modo_valido
        check (modo in ('typography_only', 'deterministic_graphics', 'full_llm',
                        'photo_preserved', 'prensa_hybrid', 'full_llm_then_prensa',
                        'observado')),
    constraint criativo_briefing_formatos_lista
        check (jsonb_typeof(formatos_pedidos) = 'array'),
    -- Um briefing de imagem sem nenhum formato produz um job que nao sabe o que
    -- gerar. Recusar aqui e mais barato que descobrir no motor.
    constraint criativo_briefing_formatos_nao_vazio
        check (modo = 'observado' or jsonb_array_length(formatos_pedidos) >= 1)
);

create index if not exists criativo_briefing_projeto_ix
    on public.criativo_briefing (projeto_id, criado_em desc);


-- =============================================================================
-- 4. JOB — uma execucao, com idempotencia e estado canonico
-- =============================================================================

create table if not exists public.criativo_job (
    id                     uuid primary key default gen_random_uuid(),
    briefing_id            uuid not null references public.criativo_briefing(id),
    motor                  text not null,
    motor_versao           text not null,
    estado                 text not null default 'draft',
    -- Tentativas do MESMO job. Retry incrementa; ele nao cria job novo (secao 2
    -- do cabecalho). Contagem de ato nosso, sempre conhecida: default 1 e
    -- legitimo aqui, e a excecao explicada da regra B.
    tentativa              integer not null default 1,
    idempotency_key        text not null,
    -- Hash do insumo efetivamente enviado ao motor. Diferente da chave de
    -- idempotencia: a chave identifica O PEDIDO, este identifica O QUE FOI
    -- MANDADO. Os dois divergem quando o motor reescreve o prompt, e saber
    -- disso e o que permite reproduzir uma geracao que deu certo.
    insumo_hash            text not null,
    -- `volc_os` = nos executamos. `observado` = lemos um build que ja existia.
    -- Ver regra F do cabecalho.
    procedencia_execucao   text not null default 'volc_os',
    origem_externa         jsonb,
    custo_estimado_usd     numeric(12, 6),
    custo_real_usd         numeric(12, 6),
    custo_medido_em        timestamptz,
    iniciado_em            timestamptz,
    terminado_em           timestamptz,
    -- Falha do JOB (nao da peca): objeto tipado, nunca string crua do provider.
    falha                  jsonb,
    cancelado_pedido_em    timestamptz,
    cancelado_em           timestamptz,
    criado_em              timestamptz not null default now(),
    criado_por             uuid,

    constraint criativo_job_idem_ux unique (idempotency_key),

    constraint criativo_job_estado_valido
        check (estado in ('draft', 'queued', 'running', 'partial',
                          'succeeded', 'failed', 'cancelled')),
    constraint criativo_job_tentativa_positiva check (tentativa >= 1),
    constraint criativo_job_procedencia_valida
        check (procedencia_execucao in ('volc_os', 'observado')),
    constraint criativo_job_idem_forma
        check (length(idempotency_key) >= 16),
    -- Regra A: custo sem instante de medicao e numero sem frescor.
    constraint criativo_job_custo_sem_carimbo
        check ((custo_real_usd is null) = (custo_medido_em is null)),
    -- Regra B: custo ausente e NULL. Zero e uma medida — "rodou e nao custou".
    constraint criativo_job_custo_nao_negativo
        check (custo_real_usd is null or custo_real_usd >= 0),
    constraint criativo_job_custo_estimado_nao_negativo
        check (custo_estimado_usd is null or custo_estimado_usd >= 0),
    -- Regra F: um job observado nao pode declarar que NOS gastamos.
    constraint criativo_job_observado_sem_custo_proprio
        check (procedencia_execucao <> 'observado' or custo_real_usd is null),
    -- Um job observado tem de dizer de onde foi observado. Sem isso a
    -- procedencia externa vira afirmacao sem prova.
    constraint criativo_job_observado_com_origem
        check (procedencia_execucao <> 'observado' or origem_externa is not null),
    -- Terminou tem de ter comecado, e nao pode terminar antes de comecar.
    constraint criativo_job_ordem_temporal
        check (terminado_em is null
               or (iniciado_em is not null and terminado_em >= iniciado_em)),
    -- Um job em estado terminal tem de ter instante de termino. Sem isso a fila
    -- nao sabe distinguir "acabou" de "morreu sem avisar".
    constraint criativo_job_terminal_carimbado
        check (estado not in ('succeeded', 'partial', 'failed', 'cancelled')
               or terminado_em is not null),
    -- Falha e obrigatoria em `failed`, e proibida fora dela. Um job `succeeded`
    -- com objeto de falha pendurado e um dado que ninguem sabe ler.
    constraint criativo_job_falha_coerente
        check ((estado = 'failed') = (falha is not null))
);

create index if not exists criativo_job_briefing_ix
    on public.criativo_job (briefing_id, criado_em desc);
create index if not exists criativo_job_estado_ix
    on public.criativo_job (estado, criado_em desc);


-- =============================================================================
-- 5. EVENTO DO JOB — diario append-only e cursor do SSE
-- =============================================================================
-- `seq` e bigserial e nao timestamp porque o cliente reconecta com "vi ate o
-- 42" e precisa de uma ordem total, estavel e sem empate. Dois eventos no mesmo
-- milissegundo com cursor de tempo fazem o cliente perder um ou receber duas
-- vezes; nenhum dos dois e aceitavel num painel que fala de dinheiro.
--
-- `percentual` e NULLABLE e nao tem default: o motor de imagem nao mede
-- progresso continuo, e inventar 37% e exatamente o que a SPEC proibe
-- ("Nao usar percentual quando o motor nao medir progresso deterministico").
-- Quando o motor nao mede, a coluna fica NULL e a interface mostra a ETAPA.

create table if not exists public.criativo_job_evento (
    seq             bigserial primary key,
    job_id          uuid not null references public.criativo_job(id),
    fase            text not null,
    mensagem        text,
    -- Progresso MEDIDO, quando existir. NULL = o motor nao mede.
    percentual      numeric(5, 2),
    -- Peca a que este evento se refere, quando for por peca.
    slot            text,
    detalhe         jsonb,
    em              timestamptz not null default now(),

    constraint criativo_job_evento_percentual_faixa
        check (percentual is null or (percentual >= 0 and percentual <= 100)),
    constraint criativo_job_evento_fase_nao_vazia
        check (btrim(fase) <> '')
);

create index if not exists criativo_job_evento_job_seq_ix
    on public.criativo_job_evento (job_id, seq);


-- =============================================================================
-- 6. MASTER — a saida principal, imutavel
-- =============================================================================
-- `slot` e o formato logico pedido ("1x1", "4x5", "9x16"). Ele existe como
-- coluna, e nao so dentro de `criativo_rendition`, porque a unicidade que
-- impede o retry de duplicar patrimonio bom e por (job, slot) — e um indice
-- nao alcanca coluna de tabela neta.

create table if not exists public.criativo_master (
    id                  uuid primary key default gen_random_uuid(),
    job_id              uuid not null references public.criativo_job(id),
    projeto_id          uuid not null references public.criativo_projeto(id),
    slot                text not null,
    kind                text not null,
    -- Referencia OPACA ao object storage. Nao e path de filesystem e nunca
    -- chega ao browser (SPEC secao 15).
    storage_chave       text not null,
    content_hash        text not null,
    mime                text not null,
    bytes_totais        integer,
    largura             integer,
    altura              integer,
    duracao_ms          integer,

    -- --- procedencia (regra E: NOT NULL) ---
    motor               text not null,
    motor_versao        text not null,
    insumo_hash         text not null,
    -- Prompt/blueprint SANITIZADO. Nunca vai para a interface do operador
    -- (SPEC secao 10: "Nao exponha prompt sensivel").
    insumo_sanitizado   text,
    brand_pack_id       uuid references public.criativo_brand_pack(id),
    brand_pack_versao   integer,

    -- --- direitos ---
    licenca             text,
    credito             text,
    -- Conteudo sintetico exige disclosure quando aplicavel (SPEC secao 15).
    disclosure          text,
    sintetico           boolean not null default true,

    -- --- versao imutavel ---
    versao              integer not null default 1,
    -- Linhagem: masters que sao versoes do MESMO artefato compartilham raiz.
    -- Uma correcao cria linha nova com `versao` maior; ela NAO sobrescreve.
    raiz_id             uuid references public.criativo_master(id),
    substitui_id        uuid references public.criativo_master(id),

    arquivado_em        timestamptz,
    criado_em           timestamptz not null default now(),

    -- Camada 3 da idempotencia: retry preenche buraco, nao reescreve acerto.
    constraint criativo_master_slot_ux unique (job_id, slot, versao),

    constraint criativo_master_kind_valido
        check (kind in ('imagem', 'video', 'audio', 'texto', 'logo', 'auxiliar')),
    -- Hash sem algoritmo declarado e impossivel de migrar depois. Mesma regra
    -- de `volc_ads/criativo/contrato.py::hash_de_conteudo`.
    constraint criativo_master_hash_forma
        check (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    constraint criativo_master_storage_nao_vazia
        check (btrim(storage_chave) <> ''),
    -- Regra B, replicada de `Asset.__post_init__`: medida ausente e NULL,
    -- nunca 0. Um `or 0` de quem nao mediu entra aqui como zero e vira
    -- "medi e deu zero".
    constraint criativo_master_largura_medida
        check (largura is null or largura > 0),
    constraint criativo_master_altura_medida
        check (altura is null or altura > 0),
    constraint criativo_master_bytes_medidos
        check (bytes_totais is null or bytes_totais > 0),
    constraint criativo_master_duracao_medida
        check (duracao_ms is null or duracao_ms > 0),
    constraint criativo_master_versao_positiva check (versao >= 1),
    constraint criativo_master_procedencia_completa
        check (btrim(motor) <> '' and btrim(insumo_hash) <> ''),
    -- Uma peca nao pode substituir a si mesma.
    constraint criativo_master_substitui_outro
        check (substitui_id is null or substitui_id <> id)
);

create index if not exists criativo_master_projeto_ix
    on public.criativo_master (projeto_id, criado_em desc);
create index if not exists criativo_master_job_ix
    on public.criativo_master (job_id);
create index if not exists criativo_master_hash_ix
    on public.criativo_master (content_hash);
create index if not exists criativo_master_raiz_ix
    on public.criativo_master (raiz_id, versao desc);


-- =============================================================================
-- 7. RENDITION — derivacao por formato, com erro PROPRIO
-- =============================================================================
-- Esta e a tabela que faz "falha parcial" ser verdade e nao slogan. Ela nasce
-- ANTES da geracao, em estado `pendente`, uma linha por formato pedido. O
-- motor preenche ou marca erro. Um lote de 3 com 1 recusado tem 2 linhas
-- `pronta` e 1 `falhou` — e as 2 boas continuam existindo, com hash e storage.
--
-- Nascer antes tambem e o que permite a interface mostrar "3 formatos, 1 ainda
-- rodando" sem inventar: a lista de pecas esperadas e dado, nao contagem.

create table if not exists public.criativo_rendition (
    id                  uuid primary key default gen_random_uuid(),
    job_id              uuid not null references public.criativo_job(id),
    master_id           uuid references public.criativo_master(id),
    slot                text not null,
    estado              text not null default 'pendente',

    -- --- o que foi PEDIDO (declarado) ---
    largura_pedida      integer not null,
    altura_pedida       integer not null,
    proporcao_rotulo    text not null,

    -- --- o que o provider entregou ANTES da normalizacao (observado) ---
    nativo_largura      integer,
    nativo_altura       integer,

    -- --- o que foi MEDIDO no arquivo final (observado) ---
    largura             integer,
    altura              integer,
    bytes_totais        integer,
    mime                text,
    storage_chave       text,
    content_hash        text,

    -- Como se saiu do nativo ate o pedido. `nativo` = o provider ja entregou na
    -- medida. `cover_crop` = houve recorte. `resize` = so escala. Sem esta
    -- coluna, "as tres sao formatos reais" e afirmacao sem prova, e a diferenca
    -- entre gerar tres pecas e esticar uma some do registro.
    enquadramento       text,
    transformacoes      jsonb not null default '[]'::jsonb,

    -- --- erro DA PECA (regra C) ---
    erro_codigo         text,
    erro_mensagem       text,
    erro_permanente     boolean,
    erro_em             timestamptz,

    custo_usd           numeric(12, 6),
    custo_medido_em     timestamptz,
    iniciada_em         timestamptz,
    concluida_em        timestamptz,
    criado_em           timestamptz not null default now(),

    -- Um slot aparece uma vez por job. O retry reaproveita a linha.
    constraint criativo_rendition_slot_ux unique (job_id, slot),

    constraint criativo_rendition_estado_valido
        check (estado in ('pendente', 'gerando', 'pronta', 'falhou', 'cancelada')),
    constraint criativo_rendition_enquadramento_valido
        check (enquadramento is null
               -- `nao_normalizado`: a normalizacao nao pode rodar (dependencia
               -- ausente ou bytes ilegiveis) e a peca ficou na dimensao do
               -- provider, DIFERENTE da pedida. Rotulo proprio porque reusar
               -- `nativo` fazia a interface dizer "entregou ja nesta dimensao".
               or enquadramento in ('nativo', 'resize', 'cover_crop',
                                    'recomposto', 'nao_normalizado')),
    constraint criativo_rendition_pedido_positivo
        check (largura_pedida > 0 and altura_pedida > 0),
    constraint criativo_rendition_medida_positiva
        check ((largura is null or largura > 0)
               and (altura is null or altura > 0)
               and (bytes_totais is null or bytes_totais > 0)
               and (nativo_largura is null or nativo_largura > 0)
               and (nativo_altura is null or nativo_altura > 0)),
    constraint criativo_rendition_hash_forma
        check (content_hash is null or content_hash ~ '^sha256:[0-9a-f]{64}$'),
    constraint criativo_rendition_custo_sem_carimbo
        check ((custo_usd is null) = (custo_medido_em is null)),
    -- Uma peca `pronta` tem de ter arquivo, hash e master. Sem isso ela e uma
    -- promessa, e a biblioteca mostraria um card que nao abre.
    constraint criativo_rendition_pronta_tem_arquivo
        check (estado <> 'pronta'
               or (storage_chave is not null
                   and content_hash is not null
                   and master_id is not null
                   and concluida_em is not null)),
    -- Uma peca `falhou` tem de dizer por que. Erro sem codigo vira "algo deu
    -- errado" na tela, que e a mensagem que nao deixa ninguem agir.
    constraint criativo_rendition_falhou_tem_motivo
        check (estado <> 'falhou'
               or (erro_codigo is not null and erro_em is not null
                   and erro_permanente is not null))
);

create index if not exists criativo_rendition_job_ix
    on public.criativo_rendition (job_id, slot);
create index if not exists criativo_rendition_master_ix
    on public.criativo_rendition (master_id);


-- =============================================================================
-- 8. APROVACAO — decisao humana por VERSAO e por FINALIDADE
-- =============================================================================
-- Nao ha `unique (subject)`: o mesmo master pode ser aprovado para `interno` e
-- reprovado para `google_display`, e as duas decisoes sao verdadeiras ao mesmo
-- tempo. A unicidade e por (subject, versao, finalidade) e so vale para a
-- decisao VIGENTE — historico e append-only, e por isso `revogada_em` existe
-- em vez de UPDATE destrutivo.

create table if not exists public.criativo_aprovacao (
    id              uuid primary key default gen_random_uuid(),
    subject_tipo    text not null,
    subject_id      uuid not null,
    versao          integer not null,
    finalidade      text not null,
    decisao         text not null,
    -- Quem decidiu. NOT NULL: aprovacao sem ator nao e auditavel, e a SPEC
    -- exige "registrar ator e instante".
    ator_id         uuid not null,
    decidido_em     timestamptz not null default now(),
    motivo          text,
    ressalvas       jsonb not null default '[]'::jsonb,
    revogada_em     timestamptz,
    revogada_por    uuid,

    constraint criativo_aprovacao_subject_valido
        check (subject_tipo in ('master', 'pacote')),
    constraint criativo_aprovacao_decisao_valida
        check (decisao in ('aprovado', 'ajuste_solicitado', 'rejeitado')),
    -- Reprovar e pedir ajuste exigem motivo. Aprovar nao exige — mas quem
    -- rejeita sem dizer por que devolve trabalho sem direcao.
    constraint criativo_aprovacao_negativa_tem_motivo
        check (decisao = 'aprovado' or btrim(coalesce(motivo, '')) <> ''),
    constraint criativo_aprovacao_versao_positiva check (versao >= 1)
);

-- Uma decisao VIGENTE por (subject, versao, finalidade). Revogadas nao ocupam.
create unique index if not exists criativo_aprovacao_vigente_ux
    on public.criativo_aprovacao (subject_tipo, subject_id, versao, finalidade)
    where revogada_em is null;

create index if not exists criativo_aprovacao_subject_ix
    on public.criativo_aprovacao (subject_tipo, subject_id, decidido_em desc);


-- =============================================================================
-- 9. PACOTE DE DESTINO e ENTREGA
-- =============================================================================
-- Criados nesta migration mesmo sem consumidor em C1, e a razao e migracao:
-- adicionar as duas depois exigiria uma v11_02 que mexe em tabela ja povoada.
-- Elas nascem vazias e a interface nao promete nenhum destino como pronto.

create table if not exists public.criativo_pacote (
    id                  uuid primary key default gen_random_uuid(),
    projeto_id          uuid not null references public.criativo_projeto(id),
    destino             text not null,
    -- Regras de plataforma tem VERSAO e DATA de verificacao (SPEC secao 11).
    -- Um pacote validado contra a regra de julho nao e um pacote validado hoje.
    regra_versao        text not null,
    regra_verificada_em timestamptz not null,
    assets              jsonb not null default '[]'::jsonb,
    copy                jsonb not null default '{}'::jsonb,
    validacao           jsonb,
    estado              text not null default 'rascunho',
    criado_em           timestamptz not null default now(),
    criado_por          uuid,

    constraint criativo_pacote_estado_valido
        check (estado in ('rascunho', 'validado', 'reprovado', 'aprovado')),
    constraint criativo_pacote_destino_nao_vazio check (btrim(destino) <> ''),
    -- Um pacote `validado` sem objeto de validacao afirma uma checagem que
    -- ninguem consegue reler.
    constraint criativo_pacote_validado_tem_prova
        check (estado not in ('validado', 'reprovado') or validacao is not null)
);

create table if not exists public.criativo_entrega (
    id                  uuid primary key default gen_random_uuid(),
    pacote_id           uuid not null references public.criativo_pacote(id),
    alvo                text not null,
    operacao            text not null,
    idempotency_key     text not null,
    -- A entrega SO existe amarrada a uma aprovacao explicita. Sem esta coluna,
    -- "foi aprovado" viraria heranca vaga, que e o que a SPEC secao 5 proibe.
    autorizacao_id      uuid not null references public.criativo_aprovacao(id),
    estado              text not null default 'em_voo',
    recibo              jsonb,
    criado_em           timestamptz not null default now(),
    respondido_em       timestamptz,

    constraint criativo_entrega_estado_valido
        check (estado in ('em_voo', 'sucesso', 'falhou', 'indeterminado')),
    constraint criativo_entrega_respondida_carimbada
        check (estado = 'em_voo' or respondido_em is not null)
);

-- Um sucesso por chave, fisicamente. Mesmo desenho da v10_01: um executor com
-- defeito que reenviasse NAO consegue registrar o segundo sucesso.
create unique index if not exists criativo_entrega_sucesso_ux
    on public.criativo_entrega (idempotency_key, operacao)
    where estado = 'sucesso';


-- =============================================================================
-- 10. GATILHOS — as invariantes que uma CHECK nao alcanca
-- =============================================================================

-- 10.1 O MASTER APROVADO NAO E SOBRESCRITO
-- ----------------------------------------------------------------------------
-- "Novo prompt, crop, render, adaptacao ou correcao produz nova versao. Nao
-- sobrescreva silenciosamente o master aprovado." (SPEC secao 6 do prompt.)
-- Uma CHECK nao consegue ver a tabela de aprovacao; um gatilho consegue.
create or replace function public.criativo_master_imutavel()
returns trigger
language plpgsql
as $$
begin
    -- Campos de conteudo e procedencia sao imutaveis SEMPRE, aprovado ou nao.
    -- Trocar o arquivo debaixo de um id ja distribuido quebra qualquer hash que
    -- alguem tenha guardado, inclusive o de um pacote de destino ja validado.
    if new.storage_chave is distinct from old.storage_chave
       or new.content_hash is distinct from old.content_hash
       or new.motor is distinct from old.motor
       or new.motor_versao is distinct from old.motor_versao
       or new.insumo_hash is distinct from old.insumo_hash
       or new.versao is distinct from old.versao
    then
        raise exception
            'criativo_master %: conteudo e procedencia sao imutaveis. Crie uma versao nova (versao=%).',
            old.id, old.versao + 1
            using errcode = 'integrity_constraint_violation';
    end if;

    -- Arquivar o que esta aprovado esconderia patrimonio que alguem autorizou.
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

drop trigger if exists criativo_master_imutavel_tg on public.criativo_master;
create trigger criativo_master_imutavel_tg
    before update on public.criativo_master
    for each row execute function public.criativo_master_imutavel();


-- 10.2 NUNCA PROMOVER AUTOMATICAMENTE UM ATIVO PARCIAL OU FALHO
-- ----------------------------------------------------------------------------
-- "nunca promover automaticamente um ativo parcial ou falho." Aprovar um master
-- cuja rendition nao ficou pronta e aprovar uma promessa.
create or replace function public.criativo_aprovacao_exige_peca_pronta()
returns trigger
language plpgsql
as $$
declare
    v_estado_job text;
    v_pronta     boolean;
begin
    if new.subject_tipo <> 'master' or new.decisao <> 'aprovado' then
        return new;
    end if;

    select j.estado into v_estado_job
      from public.criativo_master m
      join public.criativo_job j on j.id = m.job_id
     where m.id = new.subject_id;

    if v_estado_job is null then
        raise exception 'criativo_aprovacao: master % nao existe', new.subject_id
            using errcode = 'foreign_key_violation';
    end if;

    -- `running` NAO entra na lista, e isso e deliberado: um lote de tres pecas
    -- pode ter a primeira pronta enquanto a terceira ainda gera, e recusar a
    -- revisao dela obrigaria o revisor a esperar por um trabalho que ja esta
    -- pronto para ver. O que protege a regra "nunca promover um ativo parcial
    -- ou falho" nao e o estado do JOB, e sim a checagem seguinte: ESTE master
    -- precisa ter uma rendition `pronta`.
    if v_estado_job in ('draft', 'queued', 'cancelled', 'failed') then
        raise exception
            'criativo_aprovacao: job em estado % nao produz ativo aprovavel',
            v_estado_job
            using errcode = 'integrity_constraint_violation';
    end if;

    -- O job pode estar `partial` e ESTA peca ter ficado pronta. Aprovar a peca
    -- boa de um lote parcial e legitimo; aprovar a peca que falhou nao e.
    --
    -- ⚠️ O `join` com o master e a conferencia de `job_id` sao conserto de um
    -- defeito medido em 28/08/2026: a versao anterior olhava so `master_id`, e
    -- `criativo_rendition` tem `job_id` e `master_id` como FKs INDEPENDENTES.
    -- Uma rendition do job A apontando para um master do job C servia de prova
    -- para aprovar aquele master, mesmo com a unica peca propria dele `falhou`.
    -- O gatilho e a ultima barreira antes de "aprovar um ativo parcial ou
    -- falho", e ele produzia a conclusao errada sem produzir erro.
    select exists (
        select 1
          from public.criativo_rendition r
          join public.criativo_master m on m.id = r.master_id
         where r.master_id = new.subject_id
           and r.job_id = m.job_id
           and r.estado = 'pronta'
    ) into v_pronta;

    if not v_pronta then
        raise exception
            'criativo_aprovacao: master % nao tem nenhuma rendition pronta',
            new.subject_id
            using errcode = 'integrity_constraint_violation';
    end if;

    return new;
end;
$$;

drop trigger if exists criativo_aprovacao_peca_pronta_tg on public.criativo_aprovacao;
create trigger criativo_aprovacao_peca_pronta_tg
    before insert on public.criativo_aprovacao
    for each row execute function public.criativo_aprovacao_exige_peca_pronta();


-- 10.3 O EVENTO E APPEND-ONLY
-- ----------------------------------------------------------------------------
-- O cursor do SSE so e confiavel se o passado nao muda. Um UPDATE em evento ja
-- entregue faria o cliente que reconecta ver uma historia diferente da que ja
-- tinha visto.
create or replace function public.criativo_evento_append_only()
returns trigger
language plpgsql
as $$
begin
    raise exception 'criativo_job_evento e append-only (seq %)', old.seq
        using errcode = 'integrity_constraint_violation';
end;
$$;

-- 10.4 A CHAVE DE IDEMPOTENCIA E IMUTAVEL
-- ----------------------------------------------------------------------------
-- O cabecalho chama a camada 2 de "UM JOB POR CHAVE, FISICAMENTE". Fisicamente
-- era o indice unico -- e nada impedia um `UPDATE` de trocar a coluna. Liberada
-- a chave original, o reenvio do mesmo briefing deixava de conflitar e COBRAVA
-- DO PROVIDER DE NOVO, que e exatamente o que a secao 2 inteira existe para
-- impedir. Medido em 28/08/2026.
create or replace function public.criativo_job_chave_imutavel()
returns trigger
language plpgsql
as $$
begin
    if new.idempotency_key is distinct from old.idempotency_key then
        raise exception
            'criativo_job %: idempotency_key e imutavel. Trocar a chave libera o '
            'briefing para ser cobrado de novo.', old.id
            using errcode = 'integrity_constraint_violation';
    end if;
    return new;
end;
$$;

drop trigger if exists criativo_job_chave_imutavel_tg on public.criativo_job;
create trigger criativo_job_chave_imutavel_tg
    before update on public.criativo_job
    for each row execute function public.criativo_job_chave_imutavel();


drop trigger if exists criativo_evento_append_only_tg on public.criativo_job_evento;
create trigger criativo_evento_append_only_tg
    before update on public.criativo_job_evento
    for each row execute function public.criativo_evento_append_only();


-- =============================================================================
-- 11. RLS, GRANTS E O FECHAMENTO DA PORTA
-- =============================================================================
-- Mesmo desenho da v9_01: RLS LIGADA E FORCADA com ZERO policies, e nenhum
-- privilegio para `anon`/`authenticated`. O unico caminho ate estas tabelas e o
-- backend autenticado do VOLC O.S. com `service_role` (que tem BYPASSRLS).
--
-- Duas camadas e proposital: o REVOKE ja bastaria hoje, mas o default ACL de
-- `public` neste banco concede ALL em tabelas novas (achado H, 24/08/2026), e
-- uma migration futura que criasse tabela nesta familia herdaria a porta
-- aberta. RLS forcada e a rede embaixo.

do $rls$
declare
    t text;
begin
    foreach t in array array[
        'criativo_brand_pack', 'criativo_projeto', 'criativo_briefing',
        'criativo_job', 'criativo_job_evento', 'criativo_master',
        'criativo_rendition', 'criativo_aprovacao', 'criativo_pacote',
        'criativo_entrega'
    ]
    loop
        execute format('alter table public.%I enable row level security', t);
        execute format('alter table public.%I force row level security', t);
        -- ⚠️ `service_role` ENTRA no REVOKE, e essa linha é o conserto de um
        -- defeito medido por `scripts/provar-ciclo-v11.sh` em 27/08/2026.
        --
        -- Revogar so de `public, anon, authenticated` NAO bastava: o default ACL
        -- de `public` neste banco concede ALL em toda tabela nova para os tres
        -- papeis (achado H, 24/08/2026), e o `service_role` saia da migration
        -- com os SETE privilegios, DELETE e TRUNCATE inclusive. O `grant`
        -- seguinte parecia restringir e so reafirmava tres do que ele ja tinha.
        --
        -- Um cluster sem o default ACL quebrado nao mostra isso: la o REVOKE
        -- antigo passava. Foi preciso reproduzir o defeito real para ver.
        execute format(
            'revoke all on public.%I from public, anon, authenticated, service_role', t);
        -- Sem DELETE e sem TRUNCATE para ninguem. Exclusao e logica
        -- (`arquivado_em`), e um `truncate` acidental levaria a procedencia
        -- inteira sem deixar rastro.
        execute format(
            'grant select, insert, update on public.%I to service_role', t);
    end loop;
end
$rls$;

-- A sequence do evento precisa ser usavel por quem insere.
grant usage, select on sequence public.criativo_job_evento_seq_seq to service_role;
revoke all on sequence public.criativo_job_evento_seq_seq from public, anon, authenticated;


-- =============================================================================
-- 12. VERIFICACAO EMBUTIDA
-- =============================================================================
-- A migration confere a si mesma. Uma migration que aplica "sem erro" e deixa
-- uma tabela sem RLS passa despercebida ate a auditoria seguinte.

do $verifica$
declare
    n_tabelas   integer;
    n_sem_rls   integer;
    n_policies  integer;
    n_delete    integer;
    n_anon      integer;
    n_extra     integer;
begin
    select count(*) into n_tabelas
      from pg_tables where schemaname = 'public' and tablename like 'criativo_%';

    select count(*) into n_sem_rls
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relname like 'criativo_%'
       and c.relkind = 'r' and (not c.relrowsecurity or not c.relforcerowsecurity);

    select count(*) into n_policies
      from pg_policies where schemaname = 'public' and tablename like 'criativo_%';

    -- O DONO da tabela tem DELETE por POSSE, e isso nao e concessao: nao da
    -- para revoga-lo de forma util (ele volta a poder por ser owner) e nenhum
    -- caminho de aplicacao usa o papel dono. O que precisa ser zero e DELETE
    -- para qualquer OUTRO papel — em especial `service_role`, que e o unico que
    -- a API usa. Contar o dono junto faria esta guarda falhar sempre e ensinaria
    -- a proxima pessoa a desliga-la.
    select count(*) into n_delete
      from information_schema.role_table_grants g
     where g.table_schema = 'public' and g.table_name like 'criativo_%'
       and g.privilege_type = 'DELETE'
       and g.grantee <> (select tableowner from pg_tables
                          where schemaname = 'public' and tablename = g.table_name);

    select count(*) into n_anon
      from information_schema.role_table_grants
     where table_schema = 'public' and table_name like 'criativo_%'
       and grantee in ('anon', 'authenticated');

    if n_tabelas <> 10 then
        raise exception 'v11_01: esperava 10 tabelas criativo_*, achei %', n_tabelas;
    end if;
    if n_sem_rls <> 0 then
        raise exception 'v11_01: % tabela(s) sem RLS ligada E forcada', n_sem_rls;
    end if;
    if n_policies <> 0 then
        raise exception 'v11_01: esperava zero policies, achei %', n_policies;
    end if;
    if n_delete <> 0 then
        raise exception 'v11_01: DELETE concedido em % lugar(es)', n_delete;
    end if;
    if n_anon <> 0 then
        raise exception 'v11_01: anon/authenticated com % privilegio(s)', n_anon;
    end if;

    -- O conjunto EXATO do service_role, e nao "pelo menos". Conferir so o que
    -- foi concedido deixaria passar exatamente o defeito que esta verificacao
    -- existe para pegar: privilegio herdado do default ACL que ninguem pediu.
    select count(*) into n_extra
      from information_schema.role_table_grants g
     where g.table_schema = 'public' and g.table_name like 'criativo_%'
       and g.grantee = 'service_role'
       and g.privilege_type not in ('SELECT', 'INSERT', 'UPDATE');
    if n_extra <> 0 then
        raise exception
            'v11_01: service_role com % privilegio(s) alem de SELECT/INSERT/UPDATE', n_extra;
    end if;

    raise notice
        'v11_01 OK: 10 tabelas, RLS forcada, 0 policies, 0 DELETE, 0 anon, service_role restrito.';
end
$verifica$;
