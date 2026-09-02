-- Provas de COMPORTAMENTO da v12_04, em SQL e não em bash.
--
-- ⚠️ Em SQL de propósito. As provas da v11_03 nasceram dentro de `eval` com
-- aspas em três níveis: a primeira inserção falhava por quoting e todas as
-- seguintes cascateavam, produzindo um relatório cheio de "ok" que não media
-- nada. Um arranjo de prova que falha por si mesmo não mede nada.
--
-- ⚠️ E o `exception when others` também já enganou este projeto: nas provas da
-- v12_02, trocar o nome da função por um typo mantinha 14 de 22 casos verdes,
-- com "function does not exist" engolido pelo handler. Por isso aqui TODO caso
-- negativo é obrigado a nomear o TOKEN que espera ver na mensagem. Sem token, a
-- própria prova grita — ela não vira `ok` por sorte.
--
-- Toda escrita passa pela RPC, porque é isso que o papel operacional pode fazer.

\set ON_ERROR_STOP 0
\pset tuples_only on
\pset format unaligned

-- ─────────────────────────────────────────────────────────────── fixtures ──

-- Uma linha de fato PLENAMENTE medida. Cada caso a modifica com um patch.
create or replace function pg_temp.linha(patch jsonb default '{}'::jsonb)
returns jsonb language sql as $$
  select jsonb_build_object(
    'customer_id',                          '8017851692',
    'campaign_id',                          '24155134757',
    'metric_date',                          '2026-08-30',
    'colhida_em',                           '2026-08-31T09:00:00Z',
    'currency_code',                        'BRL',
    'segmentos',                            '{}'::jsonb,
    'campaign_name',                        'Maquininha',
    'campaign_status',                      'ENABLED',
    'advertising_channel_type',             'SEARCH',
    'impressoes',                           1200,
    'cliques',                              35,
    'interacoes',                           35,
    'custo_micros',                         15230000,
    'conversoes',                           2,
    'todas_conversoes',                     3,
    'valor_conversoes',                     180.5,
    'valor_todas_conversoes',               190.0,
    'ctr',                                  0.0291,
    'cpc_medio_micros',                     435142.85,
    'custo_por_conversao_micros',           7615000,
    'search_impression_share',              0.62,
    'search_budget_lost_impression_share',  0.11,
    'search_rank_lost_impression_share',    0.27,
    'search_top_impression_share',          0.44,
    'search_absolute_top_impression_share', 0.21,
    'search_click_share',                   0.58,
    'search_exact_match_impression_share',  0.74,
    'top_impression_percentage',            0.80,
    'absolute_top_impression_percentage',   0.40
  ) || patch
$$;

create or replace function pg_temp.doc(patch jsonb default '{}'::jsonb)
returns jsonb language sql as $$
  select jsonb_build_object(
    'chave_idempotencia', 'base|1',
    'execucao_chave',     'gads_dia_d1:D-1:2026-08-30:06',
    'fonte',              'n8n',
    'job',                'gads_dia_d1',
    'disparo',            'agenda',
    'workflow_id',        'WORKFLOW-DE-PROVA',
    'execucao_externa_id','1',
    'api_versao',         'v25',
    'contrato_versao',    'gads-dia-v1',
    'contrato_sha256',    repeat('a', 64),
    'tipo_lote',          'contas',
    'lote_ordinal',       1,
    'origem_janela',      'D-1',
    'janela_inicio',      '2026-08-30',
    'janela_fim',         '2026-08-30',
    'iniciada_em',        '2026-08-31T09:00:00Z',
    'encerrada_em',       '2026-08-31T09:00:05Z',
    'duracao_ms',         5000,
    'batimento_em',       '2026-08-31T09:00:05Z',
    'resultado',          'ok',
    'contas_tentadas',    jsonb_build_array('8017851692'),
    'contas_aceitas',     jsonb_build_array('8017851692'),
    'contas_recusadas',   '[]'::jsonb,
    'projetar_compat',    false,
    'linhas',             jsonb_build_array(pg_temp.linha())
  ) || patch
$$;

-- ⚠️ Caso negativo SEM token é defeito da prova, não prova. Aqui ele grita.
create or replace function pg_temp.tenta(nome text, d jsonb,
                                         deve_passar boolean,
                                         token text default null)
returns void language plpgsql as $$
declare
  r      jsonb;
  msg    text;
  estado text;
begin
  if not deve_passar and token is null then
    raise notice 'FALHOU  % (a prova é inválida: caso negativo sem token esperado)', nome;
    return;
  end if;
  begin
    select public.volc_registrar_gads_campanha_dia(d) into r;
    if deve_passar then
      raise notice '  ok   %', nome;
    else
      raise notice 'FALHOU  % (foi aceito e devia ser recusado)', nome;
    end if;
  exception when others then
    get stacked diagnostics msg = message_text, estado = returned_sqlstate;
    if deve_passar then
      raise notice 'FALHOU  % (recusado por % %)', nome, estado, left(msg, 140);
    elsif position(token in msg) = 0 then
      raise notice 'FALHOU  % (recusado por outro motivo: % %)', nome, estado, left(msg, 140);
    else
      raise notice '  ok   %', nome;
    end if;
  end;
end $$;

create or replace function pg_temp.afirma(nome text, condicao boolean)
returns void language plpgsql as $$
begin
  if condicao is true then
    raise notice '  ok   %', nome;
  else
    raise notice 'FALHOU  % (condição % )', nome, coalesce(condicao::text, 'nula');
  end if;
end $$;


-- ═══════════════════════════════════════════════════════ 1 · identidade ══

-- CP-01 · duas contas com o MESMO campaign_id não colidem.
select pg_temp.tenta('CP-01a conta A grava o campaign_id compartilhado',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia', 'cp01a|1',
    'execucao_chave',     'cp01a',
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('customer_id','8017851692','campaign_id','99999999')))
  )), true);

select pg_temp.tenta('CP-01b conta B grava O MESMO campaign_id',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia', 'cp01b|1',
    'execucao_chave',     'cp01b',
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('customer_id','7788990011','campaign_id','99999999',
                         'impressoes', 7)))
  )), true);

select pg_temp.afirma('CP-01c as duas contas coexistem, com números próprios',
  (select count(*) = 2 and count(distinct customer_id) = 2
          and sum(impressoes) = 1207
     from public.google_ads_campanha_dia
    where campaign_id = '99999999' and metric_date = '2026-08-30'));


-- ═════════════════════════════════════════════ 2 · NULL ≠ 0, e string ≠ número ══

-- CP-05 · ausência permanece NULL.
select pg_temp.tenta('CP-05a linha sem conversões declaradas como null',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp05|1','execucao_chave','cp05',
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','5000000001',
      'conversoes', null, 'valor_conversoes', null,
      'search_impression_share', null)))
  )), true);

select pg_temp.afirma('CP-05b NULL entrou como NULL, não como zero',
  (select conversoes is null and valor_conversoes is null
          and search_impression_share is null
     from public.google_ads_campanha_dia where campaign_id = '5000000001'));

-- CP-06 · zero medido permanece zero.
select pg_temp.tenta('CP-06a campanha que rodou e não entregou nada',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp06|1','execucao_chave','cp06',
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','5000000002',
      'impressoes', 0, 'cliques', 0, 'custo_micros', 0, 'conversoes', 0,
      'ctr', 0, 'search_impression_share', 0)))
  )), true);

select pg_temp.afirma('CP-06b zero medido continua zero, e é distinguível de NULL',
  (select impressoes = 0 and cliques = 0 and custo_micros = 0
          and conversoes = 0 and ctr = 0 and search_impression_share = 0
          and impressoes is not null
     from public.google_ads_campanha_dia where campaign_id = '5000000002'));

select pg_temp.tenta('CP-05c métrica que chega como STRING é recusada, não coagida',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp05c|1','execucao_chave','cp05c',
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','5000000003', 'impressoes', '')))
  )), true);

select pg_temp.afirma('CP-05d a linha com métrica string foi REJEITADA e nomeada',
  (select linhas_rejeitadas = 1 and linhas_aceitas = 0
          and rejeicoes->0->>'motivo' like 'METRICA_NAO_NUMERICA%'
     from public.trafego_coleta_execucao where chave_idempotencia = 'cp05c|1'));

select pg_temp.afirma('CP-05e nenhum fato nasceu da linha recusada',
  (select count(*) = 0 from public.google_ads_campanha_dia
    where campaign_id = '5000000003'));


-- ══════════════════════════════════════════ 3 · precedência D0 × D-1 ══

select pg_temp.tenta('CP-02a D0 lê o dia aberto',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp02-d0-06|1','execucao_chave','gads_dia_d0:D0:2026-08-31:06',
    'job','gads_dia_d0','origem_janela','D0',
    'janela_inicio','2026-08-31','janela_fim','2026-08-31',
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','6000000001','metric_date','2026-08-31',
      'colhida_em','2026-08-31T09:00:00Z','impressoes', 100)))
  )), true);

select pg_temp.tenta('CP-02b D-1 fecha o mesmo dia e prevalece',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp02-d1-06|1','execucao_chave','gads_dia_d1:D-1:2026-08-31:06',
    'job','gads_dia_d1','origem_janela','D-1',
    'janela_inicio','2026-08-31','janela_fim','2026-08-31',
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','6000000001','metric_date','2026-08-31',
      'colhida_em','2026-09-01T09:00:00Z','impressoes', 137)))
  )), true);

select pg_temp.afirma('CP-02c o dia fechado venceu o intradia',
  (select impressoes = 137 and origem_janela = 'D-1' and janela_fechada
     from public.google_ads_campanha_dia where campaign_id = '6000000001'));

select pg_temp.tenta('CP-02d D0 posterior NÃO rebaixa a janela fechada',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp02-d0-12|1','execucao_chave','gads_dia_d0:D0:2026-08-31:12',
    'job','gads_dia_d0','origem_janela','D0',
    'janela_inicio','2026-08-31','janela_fim','2026-08-31',
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','6000000001','metric_date','2026-08-31',
      'colhida_em','2026-09-02T09:00:00Z','impressoes', 5)))
  )), true);

select pg_temp.afirma('CP-02e a linha foi PRETERIDA, não rejeitada nem aplicada',
  (select linhas_preteridas = 1 and linhas_aceitas = 0 and linhas_rejeitadas = 0
     from public.trafego_coleta_execucao where chave_idempotencia = 'cp02-d0-12|1'));

select pg_temp.afirma('CP-02f o fato continua com o número do dia fechado',
  (select impressoes = 137 from public.google_ads_campanha_dia
    where campaign_id = '6000000001'));


-- ═══════════════════════════════════════════════════ 4 · idempotência ══

select pg_temp.tenta('CP-03a primeira gravação',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp03|1','execucao_chave','cp03',
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','7000000001')))
  )), true);

select pg_temp.tenta('CP-03b repetição idêntica é aceita',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp03|1','execucao_chave','cp03',
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','7000000001')))
  )), true);

select pg_temp.afirma('CP-03c a repetição devolveu o recibo guardado (repetida=true)',
  ((select public.volc_registrar_gads_campanha_dia(pg_temp.doc(jsonb_build_object(
      'chave_idempotencia','cp03|1','execucao_chave','cp03',
      'linhas', jsonb_build_array(pg_temp.linha(
        jsonb_build_object('campaign_id','7000000001'))))))->>'repetida')::boolean));

select pg_temp.afirma('CP-03d repetir não duplicou recibo nem fato',
  (select (select count(*) from public.trafego_coleta_execucao
            where chave_idempotencia = 'cp03|1') = 1
      and (select count(*) from public.google_ads_campanha_dia
            where campaign_id = '7000000001') = 1));

select pg_temp.tenta('CP-04 mesma chave com conteúdo diferente é RECUSADA',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp03|1','execucao_chave','cp03',
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','7000000001','impressoes', 1)))
  )), false, 'CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE');

select pg_temp.tenta('CP-04b retry com outro carimbo de tempo NÃO é conteúdo diferente',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp03|1','execucao_chave','cp03',
    'encerrada_em','2026-08-31T23:59:59Z','duracao_ms', 91000,
    'batimento_em','2026-08-31T23:59:59Z',
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','7000000001')))
  )), true);

select pg_temp.afirma('CP-04c identidade da execução é derivada, não sorteada',
  (select public.volc_gads_uuid_da_chave('cp03|1')
        = (select execucao_id from public.trafego_coleta_execucao
            where chave_idempotencia = 'cp03|1')));


-- ═════════════════════════════════════════════ 5 · falha, parcial, vazio ══

select pg_temp.tenta('CP-07a falha declarada com zero linha é aceita como falha',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp07|1','execucao_chave','cp07',
    'resultado','falhou','motivo','GOOGLE_ADS_5XX apos 3 tentativas',
    'escopo','conta 8017851692',
    'contas_aceitas','[]'::jsonb,
    'linhas','[]'::jsonb
  )), true);

select pg_temp.afirma('CP-07b falha NÃO virou vazio: resultado e motivo preservados',
  (select resultado = 'falhou' and motivo like 'GOOGLE_ADS_5XX%'
          and linhas_lidas = 0 and linhas_aceitas = 0
     from public.trafego_coleta_execucao where chave_idempotencia = 'cp07|1'));

select pg_temp.tenta('CP-07c "falhou" com linha aceita é recusado pelo schema',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp07c|1','execucao_chave','cp07c',
    'resultado','falhou','motivo','contraditório',
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','7000000009')))
  )), false, 'trafego_coleta_execucao_falha_sem_linha');

select pg_temp.tenta('CP-07d resultado diferente de ok sem motivo é recusado',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp07d|1','execucao_chave','cp07d',
    'resultado','parcial','linhas','[]'::jsonb
  )), false, 'trafego_coleta_execucao_motivo_semantico');

-- CP-08 · parcial preserva a linha verde e nomeia a que caiu.
select pg_temp.tenta('CP-08a lote parcial: uma linha boa, uma sem moeda',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp08|1','execucao_chave','cp08',
    'resultado','parcial','motivo','1 de 2 linhas recusadas na validacao',
    'linhas', jsonb_build_array(
      pg_temp.linha(jsonb_build_object('campaign_id','8000000001')),
      pg_temp.linha(jsonb_build_object('campaign_id','8000000002','currency_code','')))
  )), true);

select pg_temp.afirma('CP-08b a linha verde sobreviveu e a vermelha foi nomeada',
  (select linhas_lidas = 2 and linhas_aceitas = 1 and linhas_rejeitadas = 1
          and rejeicoes->0->>'motivo' = 'MOEDA_AUSENTE_OU_INVALIDA'
     from public.trafego_coleta_execucao where chave_idempotencia = 'cp08|1'));

select pg_temp.afirma('CP-08c só a linha boa virou fato',
  (select (select count(*) from public.google_ads_campanha_dia
            where campaign_id = '8000000001') = 1
      and (select count(*) from public.google_ads_campanha_dia
            where campaign_id = '8000000002') = 0));

select pg_temp.tenta('CP-08d data fora da janela pedida é rejeitada',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp08d|1','execucao_chave','cp08d',
    'resultado','parcial','motivo','linha fora da janela',
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','8000000003','metric_date','2026-07-01')))
  )), true);

select pg_temp.afirma('CP-08e a data fora da janela foi rejeitada com nome',
  (select linhas_rejeitadas = 1
          and rejeicoes->0->>'motivo' = 'DATA_FORA_DA_JANELA'
     from public.trafego_coleta_execucao where chave_idempotencia = 'cp08d|1'));


-- ═════════════════════════════════════════ 6 · paginação e lotes ══

select pg_temp.tenta('CP-11a linha duplicada dentro do mesmo lote é recusada',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp11|1','execucao_chave','cp11',
    'linhas', jsonb_build_array(
      pg_temp.linha(jsonb_build_object('campaign_id','9000000001')),
      pg_temp.linha(jsonb_build_object('campaign_id','9000000001')))
  )), false, 'LINHAS_DUPLICADAS_NO_LOTE');

select pg_temp.tenta('CP-11b página 1 de duas',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp11b|1','execucao_chave','cp11b','lote_ordinal',1,
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','9100000001')))
  )), true);

select pg_temp.tenta('CP-11c página 2 de duas, com outra campanha',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp11b|2','execucao_chave','cp11b','lote_ordinal',2,
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','9100000002')))
  )), true);

select pg_temp.tenta('CP-11d a MESMA linha em duas páginas da mesma execução é recusada',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp11b|3','execucao_chave','cp11b','lote_ordinal',3,
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','9100000001')))
  )), false, 'FATO_DUPLICADO_NA_EXECUCAO');

select pg_temp.afirma('CP-11e as duas páginas persistiram: nenhuma foi descartada',
  (select count(*) = 2 from public.google_ads_campanha_dia
    where campaign_id in ('9100000001','9100000002')));


-- ═══════════════════════════════════ 7 · recibo, fechamento, reconciliação ══

select pg_temp.tenta('CP-16a fechar antes de qualquer escrita é recusado',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp16|0','execucao_chave','cp16-vazia',
    'tipo_lote','fechamento','lote_ordinal',0,
    'linhas','[]'::jsonb,
    'linhas_aceitas', 3, 'linhas_preteridas', 0, 'linhas_rejeitadas', 0
  )), false, 'FECHAMENTO_SEM_ESCRITA');

select pg_temp.tenta('CP-15a fechamento com contagem inflada é recusado',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp11b|0','execucao_chave','cp11b',
    'tipo_lote','fechamento','lote_ordinal',0,
    'linhas','[]'::jsonb,
    'linhas_aceitas', 99, 'linhas_preteridas', 0, 'linhas_rejeitadas', 0
  )), false, 'RECONCILIACAO_DIVERGENTE');

select pg_temp.tenta('CP-15b fechamento honesto fecha',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp11b|0','execucao_chave','cp11b',
    'tipo_lote','fechamento','lote_ordinal',0,
    'linhas','[]'::jsonb,
    'linhas_aceitas', 2, 'linhas_preteridas', 0, 'linhas_rejeitadas', 0
  )), true);

select pg_temp.afirma('CP-15c o recibo resolve EXATAMENTE as linhas persistidas',
  (select f.linhas_aceitas = (select count(*) from public.google_ads_campanha_dia g
                                join public.trafego_coleta_execucao e
                                  on e.execucao_id = g.execucao_id
                               where e.execucao_chave = 'cp11b' and e.tipo_lote = 'contas')
     from public.trafego_coleta_execucao f
    where f.execucao_chave = 'cp11b' and f.tipo_lote = 'fechamento'));

-- Lote faltando: ordinal 1 e 3 sem o 2.
select pg_temp.tenta('CP-12a lote 1',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp12|1','execucao_chave','cp12','lote_ordinal',1,
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','9200000001')))
  )), true);

select pg_temp.tenta('CP-12b lote 3 (o 2 se perdeu)',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp12|3','execucao_chave','cp12','lote_ordinal',3,
    'linhas', jsonb_build_array(pg_temp.linha(
      jsonb_build_object('campaign_id','9200000003')))
  )), true);

select pg_temp.tenta('CP-12c o fechamento acusa o lote perdido',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp12|0','execucao_chave','cp12',
    'tipo_lote','fechamento','lote_ordinal',0,'linhas','[]'::jsonb,
    'linhas_aceitas', 2, 'linhas_preteridas', 0, 'linhas_rejeitadas', 0
  )), false, 'LOTE_FALTANDO');

select pg_temp.tenta('CP-14a acumulado do fechamento cobre TODOS os lotes, não o último',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp08|0','execucao_chave','cp08',
    'tipo_lote','fechamento','lote_ordinal',0,'linhas','[]'::jsonb,
    'resultado','parcial','motivo','1 de 2 linhas recusadas na validacao',
    'linhas_aceitas', 1, 'linhas_preteridas', 0, 'linhas_rejeitadas', 1
  )), true);

-- O ledger é append-only, e isso é um gatilho, não uma promessa de documentação.
do $$
declare
  msg_u text := null;
  msg_d text := null;
begin
  begin
    update public.trafego_coleta_execucao set resultado = 'ok'
     where chave_idempotencia = 'cp07|1';
  exception when others then
    get stacked diagnostics msg_u = message_text;
  end;
  begin
    delete from public.trafego_coleta_execucao where chave_idempotencia = 'cp07|1';
  exception when others then
    get stacked diagnostics msg_d = message_text;
  end;
  if msg_u like '%append-only%' then
    raise notice '  ok   CP-23a UPDATE no ledger é recusado (append-only)';
  else
    raise notice 'FALHOU  CP-23a UPDATE no ledger passou (%)', coalesce(msg_u, 'sem erro');
  end if;
  if msg_d like '%append-only%' then
    raise notice '  ok   CP-23b DELETE no ledger é recusado (append-only)';
  else
    raise notice 'FALHOU  CP-23b DELETE no ledger passou (%)', coalesce(msg_d, 'sem erro');
  end if;
end $$;


-- ══════════════════════════════════════ 8 · projeção de compatibilidade ══

-- A legada é criada pelo arranjo de prova, com o formato medido em 22/08/2026
-- (46 colunas). A migration NÃO cria nem altera esta tabela.
create table if not exists public.daily_campaign_metrics (
  id                     uuid primary key default gen_random_uuid(),
  campaign_id            text not null,
  date                   date not null,
  impressions            numeric,
  clicks                 numeric,
  spend                  numeric,
  conversions            numeric,
  ctr                    numeric,
  cpc                    numeric,
  cost_per_conversion    numeric,
  search_impression_share numeric,
  lost_impression_share_budget numeric,
  lost_impression_share_rank   numeric,
  top_impression_percentage    numeric,
  absolute_top_impression_percentage numeric,
  search_click_share     numeric,
  search_exact_match_impression_share numeric,
  revenue                numeric,
  revenue_converted      numeric,
  revenue_converted_revshare numeric,
  roas                   numeric,
  rps                    numeric,
  ecpm                   numeric,
  gam_impressions        numeric,
  commission_operator    numeric,
  orientacao_texto       text,
  orientacao_resumo      text,
  otimizacao_resumo      text,
  updated_at             timestamptz,
  created_at             timestamptz default now(),
  unique (campaign_id, date)
);

insert into public.daily_campaign_metrics
  (campaign_id, date, impressions, clicks, spend, conversions,
   revenue, revenue_converted, revenue_converted_revshare, roas, rps,
   gam_impressions, commission_operator, orientacao_texto, orientacao_resumo,
   otimizacao_resumo)
values
  ('4100000001','2026-08-30', 0, 0, 0, 0,
   1234.56, 1234.56, 1111.10, 3.2, 0.44, 98765, 12.5,
   'subir orcamento na quinta', 'resumo antigo', 'otimizacao antiga')
on conflict do nothing;

select pg_temp.tenta('CP-18a ingestão com projeção ligada',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp18|1','execucao_chave','cp18',
    'projetar_compat', true,
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','4100000001',
      'conversoes', null, 'search_impression_share', null)))
  )), true);

select pg_temp.afirma('CP-18b a projeção escreveu entrega na legada',
  (select impressions = 1200 and clicks = 35
          and round(spend, 6) = 15.23 and round(cpc, 8) = 0.43514285
          and round(cost_per_conversion, 6) = 7.615
     from public.daily_campaign_metrics
    where campaign_id = '4100000001' and date = '2026-08-30'));

select pg_temp.afirma('CP-18c receita, revshare, GAM, comissão e orientação INTACTAS',
  (select revenue = 1234.56 and revenue_converted = 1234.56
          and revenue_converted_revshare = 1111.10 and roas = 3.2 and rps = 0.44
          and gam_impressions = 98765 and commission_operator = 12.5
          and orientacao_texto = 'subir orcamento na quinta'
          and orientacao_resumo = 'resumo antigo'
          and otimizacao_resumo = 'otimizacao antiga'
     from public.daily_campaign_metrics
    where campaign_id = '4100000001' and date = '2026-08-30'));

select pg_temp.afirma('CP-05f na legada, NULL do canônico virou NULL — nunca zero',
  (select conversions is null and search_impression_share is null
     from public.daily_campaign_metrics
    where campaign_id = '4100000001' and date = '2026-08-30'));

select pg_temp.afirma('CP-18d o recibo declara a projeção aplicada',
  (select projecao_estado = 'aplicada' and projecao_linhas = 1
     from public.trafego_coleta_execucao where chave_idempotencia = 'cp18|1'));

-- Ambiguidade: duas contas, mesmo campaign_id, mesma data → a legada não sabe
-- de qual conta é a linha, então a projeção recusa em vez de sobrescrever.
insert into public.daily_campaign_metrics (campaign_id, date, revenue)
values ('4200000002','2026-08-30', 500.0) on conflict do nothing;

select pg_temp.tenta('CP-19a conta A com campanha ambígua',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp19a|1','execucao_chave','cp19a','projetar_compat', true,
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'customer_id','8017851692','campaign_id','4200000002')))
  )), true);

select pg_temp.tenta('CP-19b conta B com o MESMO campaign_id',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp19b|1','execucao_chave','cp19b','projetar_compat', true,
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'customer_id','7788990011','campaign_id','4200000002')))
  )), true);

select pg_temp.afirma('CP-19c a segunda projeção foi RECUSADA por ambiguidade',
  (select projecao_estado = 'recusada_ambigua' and projecao_linhas = 0
     from public.trafego_coleta_execucao where chave_idempotencia = 'cp19b|1'));

select pg_temp.afirma('CP-19d o fato canônico das DUAS contas continua íntegro',
  (select count(*) = 2 from public.google_ads_campanha_dia
    where campaign_id = '4200000002'));

-- CP-17 · a legada ganha uma constraint hostil; a projeção falha e o fato vive.
--
-- ⚠️ A constraint é escopada à campanha do caso. A primeira versão era global
-- (`impressions > 100000`) e as LINHAS JÁ PROJETADAS de CP-18 a violavam: o
-- `ALTER TABLE` falhava, a constraint nunca entrava, a projeção passava e a
-- prova media a ausência da armadilha em vez da reação a ela.
insert into public.daily_campaign_metrics (campaign_id, date, revenue)
values ('4300000003','2026-08-30', 77.0) on conflict do nothing;

alter table public.daily_campaign_metrics
  add constraint daily_impressions_hostil
  check (campaign_id <> '4300000003' or impressions is null or impressions < 10);

select pg_temp.tenta('CP-17a ingestão com a legada hostil',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp17|1','execucao_chave','cp17','projetar_compat', true,
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','4300000003')))
  )), true);

select pg_temp.afirma('CP-17b o FATO canônico sobreviveu à falha da projeção',
  (select count(*) = 1 from public.google_ads_campanha_dia
    where campaign_id = '4300000003'));

select pg_temp.afirma('CP-17c a falha da projeção foi NOMEADA no recibo, não engolida',
  (select projecao_estado = 'falhou' and projecao_erro_codigo = '23514'
          and projecao_linhas = 0
     from public.trafego_coleta_execucao where chave_idempotencia = 'cp17|1'));

alter table public.daily_campaign_metrics drop constraint daily_impressions_hostil;


-- ══════════════════════════════════════════════ 9 · guardas do schema ══

select pg_temp.tenta('CP-24a D-1 com janela de mais de um dia é recusada',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp24a|1','execucao_chave','cp24a',
    'janela_inicio','2026-08-01','janela_fim','2026-08-30','linhas','[]'::jsonb
  )), false, 'trafego_coleta_execucao_janela');

select pg_temp.tenta('CP-24b conta em branco no array é recusada',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp24b|1','execucao_chave','cp24b',
    'contas_tentadas', jsonb_build_array(''), 'linhas','[]'::jsonb
  )), false, 'trafego_coleta_execucao_contas_tentadas_forma');

select pg_temp.tenta('CP-24c taxa acima de 1 é recusada (percentual disfarçado de taxa)',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp24c|1','execucao_chave','cp24c',
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','9900000001','ctr', 62.0)))
  )), false, 'google_ads_campanha_dia_taxas');

select pg_temp.tenta('CP-24d custo negativo é recusado',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp24d|1','execucao_chave','cp24d',
    'linhas', jsonb_build_array(pg_temp.linha(jsonb_build_object(
      'campaign_id','9900000002','custo_micros', -1)))
  )), false, 'google_ads_campanha_dia_entrega_nao_negativa');

select pg_temp.tenta('CP-24e tipo de lote desconhecido é recusado',
  pg_temp.doc(jsonb_build_object(
    'chave_idempotencia','cp24e|1','execucao_chave','cp24e',
    'tipo_lote','qualquer','linhas','[]'::jsonb
  )), false, 'TIPO_LOTE_INVALIDO');

-- Fato órfão não sobrevive ao COMMIT: a FK é DEFERRABLE, não ausente.
do $$
declare falhou boolean := false;
begin
  begin
    insert into public.google_ads_campanha_dia (
      customer_id, campaign_id, metric_date, segments_hash,
      execucao_id, colhida_em, api_versao, currency_code,
      origem_janela, janela_fechada, precedencia)
    values ('8017851692','9990000001','2026-08-30', repeat('f',64),
            '00000000-0000-8000-8000-000000000000', now(), 'v25', 'BRL',
            'D-1', true, 2);
    -- força a checagem das constraints adiadas ainda dentro do bloco
    set constraints all immediate;
  exception when others then
    falhou := true;
  end;
  if falhou then
    raise notice '  ok   CP-16b fato sem recibo é recusado no fim da transação';
  else
    raise notice 'FALHOU  CP-16b fato órfão sobreviveu ao COMMIT';
  end if;
end $$;
