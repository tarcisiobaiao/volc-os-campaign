-- Provas de COMPORTAMENTO do ledger de inteligencia Google, em SQL.
--
-- ⚠️ Em SQL de proposito, pela mesma razao da v12_02: a primeira versao das
-- provas da v11_03 vivia dentro de `eval` com aspas em tres niveis, a primeira
-- insercao falhava por quoting e todas as seguintes cascateavam. Um arranjo de
-- prova que falha por si mesmo nao mede nada.
--
-- ## Este arquivo roda TRES vezes, e ele mesmo descobre em qual fase esta
--
-- A fase nao vem de fora por parametro: ela e LIDA do proprio CHECK
-- (`pg_temp.admite_pmax()`). Um parametro externo poderia mentir — dizer
-- "depois" enquanto a migration nem foi aplicada — e as provas passariam
-- descrevendo um banco que nao existe. Lendo o schema, a fase e um fato.
--
--   * `v12_01`     — antes da v12_03. Os seis `tipo_sinal` PMax sao RECUSADOS.
--   * `v12_03`     — depois. Os mesmos seis sao ACEITOS.
--   * `revertido`  — depois do rollback. Voltam a ser recusados.
--
-- As provas que NAO dependem da fase rodam nas tres, porque preservar a v12_01
-- e uma afirmacao sobre o antes E o depois.

\set ON_ERROR_STOP 0
\pset tuples_only on
\pset format unaligned

-- ── a campanha alvo, para a FK de `volc_campaign_id` ────────────────────────
insert into public.trafego_campanha
  (volc_campaign_id, customer_id, campaign_id, criada_por)
values
  ('gads-8017851692-24156373100', '8017851692', '24156373100', 'provas-v12_03'),
  ('gads-7016739360-24156373100', '7016739360', '24156373100', 'provas-v12_03')
on conflict (volc_campaign_id) do nothing;

-- ── a fase, lida do schema ─────────────────────────────────────────────────
create or replace function pg_temp.admite_pmax() returns boolean
language sql stable as $$
  select coalesce(position('PMAX_CAMPANHA' in pg_get_constraintdef(c.oid)) > 0, false)
    from pg_constraint c
   where c.conrelid = 'public.trafego_google_inteligencia_coleta'::regclass
     and c.conname  = 'trafego_google_coleta_tipo'
$$;

create or replace function pg_temp.fase() returns text
language sql stable as $$
  select case
    when pg_temp.admite_pmax() then 'v12_03'
    when exists (select 1 from public.trafego_google_inteligencia_coleta
                  where payload->>'fase' = 'v12_03') then 'revertido'
    else 'v12_01'
  end
$$;

-- ── o documento base, valido ───────────────────────────────────────────────
--
-- Escopo de CAMPANHA por padrao. `campaign_id` e `volc_campaign_id` viajam
-- juntos por CHECK, entao trocar um sem o outro e recusado pelo banco — e e por
-- isso que o patch de conta zera os dois de uma vez.
create or replace function pg_temp.doc(nome text, patch jsonb default '{}'::jsonb)
returns jsonb language sql as $$
  select (
    jsonb_build_object(
      'chave_idempotencia', 'v1203|' || pg_temp.fase() || '|' || nome,
      'tipo_sinal',        'DIAGNOSTICO_ENTREGA',
      'estado',            'com_dados',
      'customer_id',       '8017851692',
      'login_customer_id', '6016739364',
      'volc_campaign_id',  'gads-8017851692-24156373100',
      'campaign_id',       '24156373100',
      'janela_inicio',     null,
      'janela_fim',        null,
      'competencia',       '2026-09-01',
      'coletada_em',       '2026-09-01T12:00:00Z',
      'api_versao',        'v25',
      'coletor_versao',    3,
      'quantidade',        1,
      'request_ids',       jsonb_build_array(),
      'payload',           jsonb_build_object(
                             'somente_leitura', true,
                             'fonte', 'google_ads_api',
                             'fase', pg_temp.fase()),
      'payload_sha256',    repeat('a', 64),
      'itens',             jsonb_build_array(),
      'metricas',          jsonb_build_array()
    ) || patch
  )
$$;

-- ⚠️ ESTA FUNCAO NAO PODE ACEITAR QUALQUER ERRO.
--
-- A licao e da v12_02: um `exception when others` engolia "function does not
-- exist" e 14 de 22 casos imprimiam `ok` sem NADA ter chegado a funcao sob
-- teste. Aqui a recusa esperada tem SQLSTATE (`check_violation`) e NOME de
-- constraint; qualquer outro erro e defeito da propria prova e grita.
create or replace function pg_temp.tenta(nome text, doc jsonb,
                                         deve_passar boolean,
                                         esperada text default null)
returns uuid language plpgsql as $$
declare
  r uuid;
  quem text;
begin
  begin
    select public.volc_registrar_google_inteligencia(doc) into r;
    if deve_passar then
      raise notice '  ok   %', nome;
    else
      raise notice 'FALHOU  % (foi aceito e devia ser recusado)', nome;
    end if;
    return r;
  exception
    when check_violation then
      get stacked diagnostics quem = constraint_name;
      if deve_passar then
        raise notice 'FALHOU  % (recusado por %, e devia passar)', nome, quem;
      elsif esperada is not null and quem is distinct from esperada then
        raise notice 'FALHOU  % (recusado por %, esperava %)', nome, quem, esperada;
      else
        raise notice '  ok   % (recusado por %)', nome, quem;
      end if;
      return null;
    when others then
      raise notice 'FALHOU  % (erro inesperado %: %)', nome, sqlstate, sqlerrm;
      return null;
  end;
end;
$$;

create or replace function pg_temp.afirma(nome text, condicao boolean)
returns void language plpgsql as $$
begin
  if condicao then raise notice '  ok   %', nome;
  else raise notice 'FALHOU  %', nome; end if;
end;
$$;

-- ═══════════════════════════════════════════════════════════════════════════
DO $$ BEGIN RAISE NOTICE '-- fase detectada no schema: %', pg_temp.fase(); END $$;

-- ── B. os seis `tipo_sinal` da v12_01 continuam aceitos, nas TRES fases ─────
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'DIAGNOSTICO_ENTREGA', 'RECOMENDACOES_ARMAZENADAS', 'RECOMENDACOES_GERADAS',
    'SIMULACOES_CAMPANHA', 'FORECAST_KEYWORDS', 'EXPERIMENTOS'
  ] LOOP
    PERFORM pg_temp.tenta(
      format('B. v12_01 preservada: %s aceito', t),
      pg_temp.doc('B-' || t, jsonb_build_object('tipo_sinal', t)),
      true);
  END LOOP;
END $$;

-- ── C. tipo desconhecido continua recusado, nas TRES fases ─────────────────
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'PMAX_QUALQUER_COISA', 'DIAGNOSTICO', 'pmax_campanha', 'PMAX_RECOMENDACOES_FORCA'
  ] LOOP
    PERFORM pg_temp.tenta(
      format('C. vocabulario fechado: %s recusado', t),
      pg_temp.doc('C-' || t, jsonb_build_object('tipo_sinal', t)),
      false, 'trafego_google_coleta_tipo');
  END LOOP;
END $$;

-- ⚠️ `PMAX_RECOMENDACOES_FORCA` esta na lista acima DE PROPOSITO. Ela e a
-- setima familia, e ela NUNCA ganhou `tipo_sinal` proprio — nem na v12_03.
-- Se um dia alguem a acrescentar ao CHECK, esta prova cai e a duplicidade
-- aparece antes de virar duas respostas para a mesma pergunta.

-- ── A / v12_03. as seis familias estruturais, conforme a fase ──────────────
DO $$
DECLARE
  t text;
  admite boolean := pg_temp.admite_pmax();
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'PMAX_CAMPANHA', 'PMAX_ASSET_GROUPS', 'PMAX_ASSET_GROUP_ASSETS',
    'PMAX_ASSETS', 'PMAX_DESEMPENHO_ASSET_GROUP', 'PMAX_SINAIS'
  ] LOOP
    PERFORM pg_temp.tenta(
      format('%s: %s %s',
             case when admite then 'v12_03' else 'A. v12_01 recusa' end,
             t,
             case when admite then 'cabe no ledger' else 'sem lugar no ledger' end),
      pg_temp.doc('F6-' || t, jsonb_build_object(
        'tipo_sinal', t,
        'payload', jsonb_build_object(
          'somente_leitura', true, 'fonte', 'google_ads_api',
          'canal', 'PERFORMANCE_MAX', 'familia', t,
          'bucket', 'daily:2026-09-01', 'origem', 'alvo_nomeado',
          'fase', pg_temp.fase()))),
      admite,
      case when admite then null else 'trafego_google_coleta_tipo' end);
  END LOOP;
END $$;

-- ── E. a setima familia continua em RECOMENDACOES_ARMAZENADAS ──────────────
--
-- E ela precisa conviver com a varredura de CONTA sob o mesmo `tipo_sinal` sem
-- se confundir: o que as separa e `campaign_id` mais `payload.familia`. Se um
-- consumidor filtrar so por `tipo_sinal` + `customer_id`, ele mistura as duas.
DO $$
DECLARE
  id_pmax uuid;
  id_conta uuid;
BEGIN
  id_pmax := pg_temp.tenta(
    'E. PMAX_RECOMENDACOES_FORCA grava em RECOMENDACOES_ARMAZENADAS',
    pg_temp.doc('E-pmax', jsonb_build_object(
      'tipo_sinal', 'RECOMENDACOES_ARMAZENADAS',
      'payload', jsonb_build_object(
        'somente_leitura', true, 'fonte', 'google_ads_api',
        'canal', 'PERFORMANCE_MAX', 'familia', 'PMAX_RECOMENDACOES_FORCA',
        'bucket', 'daily:2026-09-01', 'origem', 'alvo_nomeado',
        'fase', pg_temp.fase()))),
    true);

  id_conta := pg_temp.tenta(
    'E. varredura de conta usa o mesmo tipo_sinal sem campanha',
    pg_temp.doc('E-conta', jsonb_build_object(
      'tipo_sinal', 'RECOMENDACOES_ARMAZENADAS',
      'volc_campaign_id', null, 'campaign_id', null)),
    true);

  PERFORM pg_temp.afirma(
    'E. as duas leituras sao linhas distintas, nao uma sobrescrevendo a outra',
    id_pmax is not null and id_conta is not null and id_pmax <> id_conta);

  PERFORM pg_temp.afirma(
    'E. o recorte PMax e alcancavel por campaign_id + payload.familia',
    (select count(*) = 1
       from public.trafego_google_inteligencia_coleta
      where tipo_sinal = 'RECOMENDACOES_ARMAZENADAS'
        and customer_id = '8017851692'
        and campaign_id = '24156373100'
        and payload->>'familia' = 'PMAX_RECOMENDACOES_FORCA'
        and payload->>'fase' = pg_temp.fase()));

  PERFORM pg_temp.afirma(
    'E. filtrar so por tipo_sinal + customer_id misturaria conta com campanha',
    (select count(*) > 1
       from public.trafego_google_inteligencia_coleta
      where tipo_sinal = 'RECOMENDACOES_ARMAZENADAS'
        and customer_id = '8017851692'
        and payload->>'fase' = pg_temp.fase()));
END $$;

-- ── F. repeticao idempotente nao cria duas coletas ─────────────────────────
DO $$
DECLARE
  a uuid; b uuid; doc jsonb;
BEGIN
  doc := pg_temp.doc('F-idempotente');
  a := pg_temp.tenta('F. primeira gravacao entra', doc, true);
  b := pg_temp.tenta('F. repetir a mesma chave nao cria outra coleta', doc, true);
  PERFORM pg_temp.afirma('F. a repeticao devolveu o MESMO coleta_id', a = b);
  PERFORM pg_temp.afirma(
    'F. existe exatamente uma linha para a chave repetida',
    (select count(*) = 1 from public.trafego_google_inteligencia_coleta
      where chave_idempotencia = doc->>'chave_idempotencia'));
END $$;

-- ── G. o coleta_id devolvido resolve EXATAMENTE uma linha ──────────────────
DO $$
DECLARE cid uuid;
BEGIN
  cid := pg_temp.tenta('G. coleta com item e metrica entra',
    pg_temp.doc('G-resolve', jsonb_build_object(
      'itens', jsonb_build_array(jsonb_build_object(
        'ordinal', 0, 'tipo_item', 'campaign',
        'recurso_externo', 'customers/8017851692/campaigns/24156373100',
        'payload', jsonb_build_object('status', 'PAUSED'))),
      'metricas', jsonb_build_array(jsonb_build_object(
        'recurso_tipo', 'asset_group', 'recurso_externo', '2001',
        'nome', 'impressions', 'estado_valor', 'medido',
        'valor_numerico', '0', 'valor_texto', null,
        'unidade', null, 'moeda', null)))),
    true);

  PERFORM pg_temp.afirma('G. o id devolvido resolve uma unica coleta',
    (select count(*) = 1 from public.trafego_google_inteligencia_coleta
      where coleta_id = cid));
  PERFORM pg_temp.afirma('G. o item ficou pendurado nessa coleta',
    (select count(*) = 1 from public.trafego_google_inteligencia_item
      where coleta_id = cid));
  PERFORM pg_temp.afirma('G. zero MEDIDO atravessou como zero, nao como ausencia',
    (select count(*) = 1 from public.trafego_google_inteligencia_metrica
      where coleta_id = cid and estado_valor = 'medido' and valor_numerico = 0));
END $$;

-- ── H (metade SQL). zero, vazio, falha e ausencia nao se achatam ───────────
DO $$
BEGIN
  PERFORM pg_temp.tenta('H. vazio_confirmado com quantidade 0 e aceito',
    pg_temp.doc('H-vazio', jsonb_build_object(
      'estado', 'vazio_confirmado', 'quantidade', 0)), true);

  PERFORM pg_temp.tenta('H. vazio_confirmado com quantidade nula preserva ausencia',
    pg_temp.doc('H-vazio-nulo', jsonb_build_object(
      'estado', 'vazio_confirmado', 'quantidade', null)),
    true);

  PERFORM pg_temp.tenta('H. com_dados com quantidade 0 e recusado',
    pg_temp.doc('H-com-dados-zero', jsonb_build_object(
      'estado', 'com_dados', 'quantidade', 0)),
    false, 'trafego_google_coleta_quantidade_semantica');

  PERFORM pg_temp.tenta('H. falhou com quantidade 0 e recusado',
    pg_temp.doc('H-falhou-zero', jsonb_build_object(
      'estado', 'falhou', 'quantidade', 0,
      'erro_codigo', 'DEPENDENCIA_FALHOU:PMAX_ASSET_GROUPS',
      'erro_classe', 'DependenciaDeLeitura')),
    false, 'trafego_google_coleta_quantidade_semantica');

  PERFORM pg_temp.tenta('H. falhou sem codigo e classe e recusado',
    pg_temp.doc('H-falhou-mudo', jsonb_build_object(
      'estado', 'falhou', 'quantidade', null)),
    false, 'trafego_google_coleta_erro_semantica');

  PERFORM pg_temp.tenta('H. causa estruturada DEPENDENCIA_FALHOU:<familia> cabe',
    pg_temp.doc('H-dependencia', jsonb_build_object(
      'estado', 'falhou', 'quantidade', null,
      'erro_codigo', 'DEPENDENCIA_FALHOU:PMAX_ASSET_GROUP_ASSETS',
      'erro_classe', 'DependenciaDeLeitura')), true);

  PERFORM pg_temp.tenta('H. inelegivel nao carrega quantidade',
    pg_temp.doc('H-inelegivel', jsonb_build_object(
      'estado', 'inelegivel', 'quantidade', null)), true);
END $$;

-- ── I (metade SQL). identidade frouxa nao passa pelo banco ─────────────────
DO $$
BEGIN
  PERFORM pg_temp.tenta('I. campanha externa sem identidade interna e recusada',
    pg_temp.doc('I-so-externo', jsonb_build_object('volc_campaign_id', null)),
    false, 'trafego_google_coleta_campanha_par');

  PERFORM pg_temp.tenta('I. conta fora de forma e recusada',
    pg_temp.doc('I-conta', jsonb_build_object('customer_id', '80-178-516')),
    false, 'trafego_google_coleta_contas');

  -- ⚠️ As DUAS contas precisam gravar. Sem a linha desta conta, a afirmacao
  -- abaixo contaria uma unica conta e passaria por acidente.
  PERFORM pg_temp.tenta('I. a campanha desta conta entra',
    pg_temp.doc('I-esta-conta'), true);

  PERFORM pg_temp.tenta('I. a MESMA campanha em outra conta e outra linha',
    pg_temp.doc('I-outra-conta', jsonb_build_object(
      'customer_id', '7016739360',
      'volc_campaign_id', 'gads-7016739360-24156373100')), true);

  PERFORM pg_temp.afirma(
    'I. mesmo campaign_id em duas contas produz DUAS linhas, nao uma',
    (select count(distinct customer_id) = 2
       from public.trafego_google_inteligencia_coleta
      where campaign_id = '24156373100'
        and payload->>'fase' = pg_temp.fase()
        and chave_idempotencia like '%|I-%'));
END $$;

-- ── append-only: o ledger nao reescreve fato, em fase nenhuma ──────────────
DO $$
DECLARE quem text;
BEGIN
  BEGIN
    UPDATE public.trafego_google_inteligencia_coleta SET estado = 'com_dados'
     WHERE chave_idempotencia = 'v1203|' || pg_temp.fase() || '|F-idempotente';
    RAISE NOTICE 'FALHOU  append-only: UPDATE foi aceito';
  EXCEPTION WHEN others THEN
    RAISE NOTICE '  ok   append-only: UPDATE recusado (%)', sqlstate;
  END;
  BEGIN
    DELETE FROM public.trafego_google_inteligencia_coleta
     WHERE chave_idempotencia = 'v1203|' || pg_temp.fase() || '|F-idempotente';
    RAISE NOTICE 'FALHOU  append-only: DELETE foi aceito';
  EXCEPTION WHEN others THEN
    RAISE NOTICE '  ok   append-only: DELETE recusado (%)', sqlstate;
  END;
END $$;

-- ── D. o que ja estava gravado sobrevive a fase seguinte ───────────────────
--
-- Cada fase confere as linhas da fase ANTERIOR. Na primeira nao ha anterior, e
-- a prova diz isso em vez de afirmar preservacao de nada.
DO $$
DECLARE
  anterior text := case pg_temp.fase()
                     when 'v12_03' then 'v12_01'
                     when 'revertido' then 'v12_01'
                     else null end;
BEGIN
  IF anterior IS NULL THEN
    RAISE NOTICE '  ok   D. fase inicial: nao ha linha anterior a preservar';
  ELSE
    PERFORM pg_temp.afirma(
      format('D. os seis recibos da fase %s continuam la', anterior),
      (select count(*) = 6 from public.trafego_google_inteligencia_coleta
        where payload->>'fase' = anterior and chave_idempotencia like '%|B-%'));
    PERFORM pg_temp.afirma(
      format('D. nenhum recibo da fase %s foi reescrito', anterior),
      (select count(*) = 0 from public.trafego_google_inteligencia_coleta
        where payload->>'fase' = anterior and payload->>'fonte' <> 'google_ads_api'));
  END IF;
END $$;
