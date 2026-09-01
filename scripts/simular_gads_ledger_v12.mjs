#!/usr/bin/env node
// Simulador offline dos workflows n8n de ingestão Google Ads campanha-dia.
//
// ## Por que ele existe
//
// Validar o JSON prova que o desenho está bem formado. Não prova que o
// JavaScript dentro dele FAZ a coisa certa — e é dentro do Code node que mora o
// defeito que esta entrega corrige (`parseFloat(x || 0)` transformando ausência
// em zero). Este harness executa o `jsCode` EXATO que vai no workflow, num
// `vm` com um dublê do runtime do n8n, com relógio injetado e zero rede.
//
// ## O que ele NÃO é
//
// Não é o n8n. Ele reproduz a topologia declarada em `connections` (que o
// validador confere elo a elo), não o motor real: `$()` por índice de rodada,
// fila de execução e retry ficam de fora. Por isso o pacote de autorização
// mantém um passo de execução manual no n8n real antes de qualquer agenda.
//
// Uso:
//   node scripts/simular_gads_ledger_v12.mjs
//   node scripts/simular_gads_ledger_v12.mjs --rpc=psql --container=NOME

import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '..');
const ARQUIVOS = {
  D0: join(RAIZ, 'n8n', 'volc_gads_campanha_dia_d0.json'),
  'D-1': join(RAIZ, 'n8n', 'volc_gads_campanha_dia_d1.json'),
};

const argv = process.argv.slice(2);
const modoRpc = (argv.find((a) => a.startsWith('--rpc=')) || '--rpc=fake').split('=')[1];
const container = (argv.find((a) => a.startsWith('--container=')) || '--container=').split('=')[1];

let ok = 0;
const falhas = [];
function prova(nome, condicao, detalhe = '') {
  if (condicao) { ok += 1; console.log(`  ok   ${nome}`); }
  else { falhas.push(nome); console.log(`  FALHOU  ${nome}${detalhe ? ' — ' + detalhe : ''}`); }
}
function provaLanca(nome, fn, trecho) {
  try { fn(); falhas.push(nome); console.log(`  FALHOU  ${nome} (não lançou)`); }
  catch (e) {
    if (String(e.message).includes(trecho)) { ok += 1; console.log(`  ok   ${nome}`); }
    else { falhas.push(nome); console.log(`  FALHOU  ${nome} — lançou "${e.message.slice(0, 90)}"`); }
  }
}

// ───────────────────────────────────────────────── dublê do runtime n8n ──

function carregar(papel) {
  const wf = JSON.parse(readFileSync(ARQUIVOS[papel], 'utf8'));
  const porNome = new Map(wf.nodes.map((n) => [n.name, n]));
  return { wf, porNome };
}

class Runtime {
  constructor(wf, { agora, disparoPorAgenda }) {
    this.wf = wf;
    this.porNome = new Map(wf.nodes.map((n) => [n.name, n]));
    this.saidas = new Map();     // nome -> array de rodadas (cada rodada = itens)
    this.agora = agora;
    this.disparoPorAgenda = disparoPorAgenda;
  }

  registrar(nome, itens) {
    if (!this.saidas.has(nome)) this.saidas.set(nome, []);
    this.saidas.get(nome).push(itens);
  }

  // `$('No')` resolve pelo índice da rodada atual quando existe — é o que o n8n
  // documenta e o que o laço precisa. Sem rodada correspondente, cai na última.
  refNo(nome, runIndex) {
    const rodadas = this.saidas.get(nome);
    if (!rodadas || rodadas.length === 0) {
      const erro = new Error(`no "${nome}" nao foi executado`);
      erro.n8nNaoExecutado = true;
      throw erro;
    }
    const itens = rodadas[Math.min(runIndex, rodadas.length - 1)];
    return {
      first: () => itens[0],
      last: () => itens[itens.length - 1],
      all: () => itens,
      isExecuted: true,
    };
  }

  executar(nome, entrada, { runIndex = 0 } = {}) {
    const no = this.porNome.get(nome);
    if (!no) throw new Error(`no inexistente no workflow: ${nome}`);
    if (no.type !== 'n8n-nodes-base.code') throw new Error(`${nome} nao e Code node`);

    const rt = this;
    const instanteFixo = this.agora;
    class DataFixa extends Date {
      constructor(...args) {
        if (args.length === 0) super(instanteFixo.getTime());
        else super(...args);
      }
      static now() { return instanteFixo.getTime(); }
    }

    const sandbox = {
      $input: {
        all: () => entrada,
        first: () => entrada[0],
        last: () => entrada[entrada.length - 1],
      },
      $json: entrada.length ? entrada[0].json : {},
      $runIndex: runIndex,
      $workflow: { id: 'WF-SIMULADO', name: rt.wf.name, active: false },
      $execution: { id: 'EXEC-SIMULADA', mode: 'test' },
      $: (n) => {
        if (n === 'Agenda') {
          if (!rt.disparoPorAgenda) throw new Error('no "Agenda" nao foi executado');
          return { isExecuted: true, first: () => ({ json: {} }), all: () => [] };
        }
        return rt.refNo(n, runIndex);
      },
      Date: DataFixa,
      console,
    };
    const ctx = createContext(sandbox);
    const codigo = `(function volcCodeNode() {\n${no.parameters.jsCode}\n})()`;
    const saida = runInContext(codigo, ctx, { timeout: 5000, filename: `${nome}.js` });
    if (!Array.isArray(saida)) throw new Error(`${nome} nao devolveu array`);
    for (const item of saida) {
      if (!item || typeof item !== 'object' || !('json' in item)) {
        throw new Error(`${nome} devolveu item fora do formato { json }`);
      }
    }
    this.registrar(nome, saida);
    return saida;
  }
}

// ────────────────────────────────────────────────────── dublê do Google ──

function resultadoGoogle({ customerId, campaignId, date, metricas = {}, currency = 'BRL' }) {
  return {
    customer: { id: customerId, currencyCode: currency },
    campaign: {
      id: campaignId, name: `campanha ${campaignId}`,
      status: 'ENABLED', advertisingChannelType: 'SEARCH',
    },
    segments: { date },
    metrics: metricas,
  };
}

// ───────────────────────────────────────────────────────── dublê da RPC ──

function rpcFake(documento, estado) {
  const chave = documento.chave_idempotencia;
  if (estado.recibos.has(chave)) {
    const guardado = estado.recibos.get(chave);
    if (JSON.stringify(guardado.documento.linhas) !== JSON.stringify(documento.linhas)) {
      throw new Error('CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE');
    }
    return { ...guardado.recibo, repetida: true };
  }
  const linhas = documento.linhas || [];
  let aceitas = 0; let preteridas = 0; let rejeitadas = 0;
  for (const l of linhas) {
    const k = `${l.customer_id}|${l.campaign_id}|${l.metric_date}`;
    const posto = { D0: 1, 'D-1': 2, backfill: 3 }[documento.origem_janela];
    const atual = estado.fatos.get(k);
    if (atual && atual.posto > posto) { preteridas += 1; continue; }
    estado.fatos.set(k, { posto, linha: l });
    aceitas += 1;
  }
  const recibo = {
    execucao_id: `uuid-${chave}`,
    chave_idempotencia: chave,
    repetida: false,
    linhas_lidas: aceitas + preteridas + rejeitadas,
    linhas_aceitas: aceitas,
    linhas_preteridas: preteridas,
    linhas_rejeitadas: rejeitadas,
    rejeicoes: [],
    projecao_estado: documento.projetar_compat ? 'aplicada' : 'nao_solicitada',
    projecao_linhas: documento.projetar_compat ? aceitas : 0,
    resultado: documento.resultado,
  };
  estado.recibos.set(chave, { documento, recibo });
  return recibo;
}

function consultarPsql(sql) {
  return execFileSync('docker',
    ['exec', '-i', container, 'psql', '-U', 'postgres', '-d', 'postgres',
      '-v', 'ON_ERROR_STOP=1', '-X', '-q', '-At', '-c', sql],
    { encoding: 'utf8' }).trim();
}

function rpcPsql(documento) {
  const sql = 'select public.volc_registrar_gads_campanha_dia('
    + `$doc$${JSON.stringify(documento)}$doc$::jsonb)`;
  return JSON.parse(consultarPsql(sql));
}

// ⚠️ Estado NOVO por execução simulada. A primeira versão compartilhava um
// único mapa entre cenários e o segundo cenário reusava a chave do primeiro,
// levando um `CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE` que era defeito do
// arranjo de prova, não do workflow.
function fabricaRpc() {
  const estado = { recibos: new Map(), fatos: new Map() };
  return modoRpc === 'psql' ? rpcPsql : (d) => rpcFake(d, estado);
}

// ──────────────────────────────────────────────── motor de uma execução ──
//
// Segue a topologia declarada em `connections`; o validador confere elo a elo
// que ela é a ordem obrigatória do contrato.
function executarFluxo(papel, cenario) {
  const chamarRpc = fabricaRpc();
  const { wf } = carregar(papel);
  const rt = new Runtime(wf, {
    agora: cenario.agora,
    disparoPorAgenda: cenario.disparoPorAgenda !== false,
  });

  // O Config é um Set node: o dublê lê os assignments direto do JSON.
  const cfgNo = rt.porNome.get('Config');
  const cfg = {};
  for (const a of cfgNo.parameters.assignments.assignments) cfg[a.name] = a.value;
  Object.assign(cfg, cenario.configExtra || {});
  rt.registrar('Config', [{ json: cfg }]);

  const ident = rt.executar('Identidade da execucao', [{ json: {} }]);

  const contas = (cenario.contasInventario || []).map((c) => ({ json: c }));
  const selecionadas = rt.executar('Selecionar contas', contas);

  const campanhas = (cenario.campanhasInventario || []).map((c) => ({ json: c }));
  const itensConta = rt.executar('Identidade VOLC por conta', campanhas);

  // SplitInBatches batchSize 1: uma conta por iteração; a saída `done` acumula
  // tudo que reentrou no laço.
  const done = [];
  let runNormalizar = 0;
  const documentosEnviados = [];

  for (const itemConta of itensConta) {
    let atual = itemConta;
    let paginaIdx = 0;
    for (;;) {
      const preparado = rt.executar('Pagina: preparar pedido', [atual],
        { runIndex: rt.saidas.get('Pagina: preparar pedido')?.length || 0 });
      const ctxPagina = preparado[0].json;

      const resposta = cenario.google(ctxPagina, paginaIdx);

      // Dublê do Merge `combineByPosition`: a resposta (ou o erro) da MESMA
      // iteração é fundida com o contexto daquela iteração. É exatamente o que
      // os dois nós de merge fazem no workflow, e é o que substituiu o `$()`
      // por índice de rodada que este simulador derrubou.
      const juntar = (corpo) => ({ json: { ...corpo, ...ctxPagina } });

      if (resposta.erro) {
        const classificado = rt.executar('Classificar erro do Google',
          [juntar(resposta.erro)],
          { runIndex: (rt.saidas.get('Classificar erro do Google')?.length) || 0 });
        done.push(classificado[0]);
        break;
      }

      const normalizado = rt.executar('Pagina: normalizar', [juntar(resposta.corpo)],
        { runIndex: runNormalizar });
      const idxNormalizar = runNormalizar;
      runNormalizar += 1;

      const validado = rt.executar('Validar semanticamente', normalizado,
        { runIndex: idxNormalizar });
      const doc = validado[0].json.documento;
      documentosEnviados.push(doc);

      const recibo = cenario.rpc ? cenario.rpc(doc) : chamarRpc(doc);
      const reconciliado = rt.executar('Reconciliar lote', [{ json: recibo }],
        { runIndex: idxNormalizar });

      atual = reconciliado[0];
      paginaIdx += 1;
      if (!atual.json.tem_proxima_pagina) { done.push(atual); break; }
    }
  }

  const fechado = rt.executar('Fechar execucao', done);
  const docFechamento = fechado[0].json.documento;
  const reciboFechamento = cenario.rpcFechamento
    ? cenario.rpcFechamento(docFechamento)
    : { chave_idempotencia: docFechamento.chave_idempotencia, resultado: docFechamento.resultado };

  const releitura = cenario.releitura
    ? cenario.releitura(docFechamento, reciboFechamento)
    : [{
      execucao_chave: docFechamento.execucao_chave,
      resultado: docFechamento.resultado,
      motivo: docFechamento.motivo,
      linhas_aceitas: docFechamento.linhas_aceitas,
      batimento_em: docFechamento.batimento_em,
    }];

  const saude = rt.executar('Batimento e saude', releitura.map((l) => ({ json: l })));

  return {
    rt,
    identidade: ident[0].json,
    selecionadas: selecionadas[0].json,
    itensConta: itensConta.map((i) => i.json),
    done: done.map((i) => i.json),
    fechamento: fechado[0].json,
    documentosEnviados,
    saude: saude[0].json,
  };
}

// ───────────────────────────────────────────────────────────── cenários ──

const CONTAS = [{ customer_id: '8017851692', nome: 'Credito Up' }];
const CAMPANHAS = [
  { customer_id: '8017851692', campaign_id: '24155134757', volc_campaign_id: 'gads-8017851692-24155134757' },
];
const AGORA = new Date('2026-09-01T13:30:00.000Z'); // 10:30 em America/Sao_Paulo

function googleUmaPagina(linhas) {
  return () => ({ corpo: { results: linhas, fieldMask: 'x' } });
}

// ─────────────────────────────────────────────────── ponta a ponta real ──
//
// Aqui o dublê some do lado do banco: os documentos que o JavaScript do
// workflow monta vão para a RPC de verdade, num Postgres descartável com a
// v12_04 aplicada. É a costura onde dois artefatos costumam discordar em
// silêncio — o fluxo acha que mandou, o banco acha que recebeu outra coisa.
if (modoRpc === 'psql') {
  if (!container) { console.error('--rpc=psql exige --container=NOME'); process.exit(2); }

  console.log('\n── PONTA A PONTA: workflow → RPC v12_04 real');

  const linhaCheia = resultadoGoogle({
    customerId: '8017851692', campaignId: '24155134757', date: '2026-08-31',
    metricas: {
      impressions: '1200', clicks: '35', interactions: '35', costMicros: '15230000',
      conversions: 2, allConversions: 3, conversionsValue: 180.5,
      allConversionsValue: 190, ctr: 0.0291, averageCpc: 435142.85,
      costPerConversion: 7615000, searchImpressionShare: 0.62,
    },
  });
  const linhaZerada = resultadoGoogle({
    customerId: '8017851692', campaignId: '24156373085', date: '2026-08-31',
    metricas: { impressions: '0', clicks: '0', costMicros: '0', conversions: 0, ctr: 0 },
  });
  const linhaSemMetrica = resultadoGoogle({
    customerId: '7788990011', campaignId: '24155134757', date: '2026-08-31',
    metricas: { impressions: '9' },
  });

  const r = executarFluxo('D-1', {
    agora: new Date('2026-09-01T13:30:00.000Z'),
    contasInventario: [
      { customer_id: '8017851692', nome: 'A' }, { customer_id: '7788990011', nome: 'B' },
    ],
    campanhasInventario: CAMPANHAS,
    google: (ctx, idx) => (ctx.customer_id === '8017851692'
      ? [
        { corpo: { results: [linhaCheia], nextPageToken: 'p2' } },
        { corpo: { results: [linhaZerada] } },
      ][idx]
      : { corpo: { results: [linhaSemMetrica] } }),
    rpcFechamento: (doc) => rpcPsql(doc),
    releitura: (doc) => {
      const bruto = consultarPsql(
        'select coalesce(json_agg(row_to_json(s)), \'[]\')::text from '
        + `public.trafego_coleta_execucao_saude s where s.execucao_chave = '${doc.execucao_chave}'`);
      return JSON.parse(bruto);
    },
  });

  prova('a RPC real aceitou os três lotes do fluxo', r.documentosEnviados.length === 3);
  prova('o fechamento real reconciliou e fechou',
    r.saude.estado_saude === 'SAUDAVEL' && r.saude.alerta === false,
    `${r.saude.estado_saude} / ${r.saude.motivo_alerta || ''}`);
  prova('o batimento veio da RELEITURA do banco, não da memória do fluxo',
    r.saude.releitura_encontrada === true && Boolean(r.saude.batimento_em));

  const fatos = Number(consultarPsql(
    "select count(*) from public.google_ads_campanha_dia where metric_date = '2026-08-31'"));
  prova('o banco tem exatamente as três linhas persistidas', fatos === 3, String(fatos));

  const semColisao = consultarPsql(
    "select count(distinct customer_id) from public.google_ads_campanha_dia "
    + "where campaign_id = '24155134757' and metric_date = '2026-08-31'");
  prova('duas contas com o mesmo campaign_id coexistem no fato', semColisao === '2', semColisao);

  // A linha zerada mede impressões, cliques, custo, conversões e CTR como ZERO
  // e não mede o resto. As duas metades viajam juntas até o banco.
  const zero = consultarPsql(
    "select impressoes || '/' || cliques || '/' || custo_micros || '/' || conversoes "
    + "|| '/' || ctr from public.google_ads_campanha_dia where campaign_id = '24156373085'");
  prova('zero medido chegou ao banco como ZERO', zero === '0/0/0/0/0', zero);

  const nulos = consultarPsql(
    'select (valor_conversoes is null)::text || (search_impression_share is null)::text || '
    + "(cpc_medio_micros is null)::text || (custo_por_conversao_micros is null)::text "
    + "from public.google_ads_campanha_dia where campaign_id = '24156373085'");
  prova('métrica NÃO medida chegou ao banco como NULL, na MESMA linha do zero',
    nulos === 'truetruetruetrue', nulos);

  const micros = consultarPsql(
    "select custo_micros || '|' || currency_code from public.google_ads_campanha_dia "
    + "where campaign_id = '24155134757' and customer_id = '8017851692'");
  prova('dinheiro conservou micros e moeda', micros === '15230000|BRL', micros);

  const volc = consultarPsql(
    "select coalesce(volc_campaign_id,'(nulo)') from public.google_ads_campanha_dia "
    + "where campaign_id = '24155134757' and customer_id = '8017851692'");
  prova('a identidade VOLC do inventário viajou até o fato',
    volc === 'gads-8017851692-24155134757', volc);

  const recibo = consultarPsql(
    "select linhas_aceitas || '/' || linhas_preteridas || '/' || linhas_rejeitadas "
    + "|| '/' || resultado from public.trafego_coleta_execucao "
    + "where tipo_lote = 'fechamento'");
  prova('o recibo de fechamento resolve exatamente as linhas persistidas',
    recibo === '3/0/0/ok', recibo);

  // Repetir o lote 1 com o MESMO conteúdo tem de devolver o recibo guardado.
  const repetido = rpcPsql(r.documentosEnviados[0]);
  prova('repetir o lote não duplica: a RPC devolve o recibo guardado',
    repetido.repetida === true);
  const aindaTres = consultarPsql(
    "select count(*) from public.google_ads_campanha_dia where metric_date = '2026-08-31'");
  prova('depois da repetição o banco continua com três linhas', aindaTres === '3', aindaTres);

  console.log('\n════════════════════════════════════════════════════════');
  console.log(`  passaram ${ok} · falharam ${falhas.length}`);
  if (falhas.length) {
    for (const f of falhas) console.log(`    ✗ ${f}`);
    process.exit(1);
  }
  console.log('  PONTA A PONTA COMPLETA — documentos do n8n aceitos pela RPC v12_04');
  process.exit(0);
}

console.log('\n── JANELA, IDENTIDADE E DISPARO');
{
  const d0 = executarFluxo('D0', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina([]),
  });
  prova('D0 lê o dia de hoje em America/Sao_Paulo',
    d0.identidade.janela_inicio === '2026-09-01' && d0.identidade.janela_fim === '2026-09-01',
    d0.identidade.janela_inicio);
  prova('D0 encaixa o passo da agenda (10:30 pertence ao passo 06)',
    d0.identidade.passo === '06', d0.identidade.passo);
  prova('a chave da execução carrega job, janela e passo',
    d0.identidade.execucao_chave === 'gads_dia_d0:D0:2026-09-01:06',
    d0.identidade.execucao_chave);
  prova('D0 declara janela aberta', d0.identidade.origem_janela === 'D0');

  const d1 = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina([]),
  });
  prova('D-1 lê o dia ANTERIOR, fechado',
    d1.identidade.janela_inicio === '2026-08-31' && d1.identidade.janela_fim === '2026-08-31',
    d1.identidade.janela_inicio);
  prova('D0 e D-1 nunca disputam a chave',
    d0.identidade.execucao_chave !== d1.identidade.execucao_chave);

  // Virada de mês e de ano pela aritmética de calendário.
  const viradaAno = executarFluxo('D-1', {
    agora: new Date('2027-01-01T05:00:00.000Z'), // 02:00 de 01/01 em SP
    contasInventario: CONTAS, campanhasInventario: CAMPANHAS, google: googleUmaPagina([]),
  });
  prova('a virada de ano cai no dia 31/12, não em 00/01',
    viradaAno.identidade.janela_inicio === '2026-12-31',
    viradaAno.identidade.janela_inicio);

  const manual = executarFluxo('D0', {
    agora: AGORA, disparoPorAgenda: false,
    contasInventario: CONTAS, campanhasInventario: CAMPANHAS, google: googleUmaPagina([]),
  });
  prova('rodada manual declara disparo manual', manual.identidade.disparo === 'manual');
  prova('rodada manual ganha passo próprio, sem colidir com a agenda',
    manual.identidade.passo === 'm1030'
    && manual.identidade.execucao_chave !== d0.identidade.execucao_chave,
    manual.identidade.passo);

  const fixado = executarFluxo('D0', {
    agora: new Date('2026-09-01T19:41:00.000Z'), disparoPorAgenda: false,
    configExtra: { PASSO_FORCADO: 'canario' },
    contasInventario: CONTAS, campanhasInventario: CAMPANHAS, google: googleUmaPagina([]),
  });
  prova('PASSO_FORCADO torna o canário repetível (mesma chave em outro minuto)',
    fixado.identidade.execucao_chave === 'gads_dia_d0:D0:2026-09-01:canario',
    fixado.identidade.execucao_chave);
}

console.log('\n── NULL ≠ 0 NA NORMALIZAÇÃO');
{
  const linhas = [
    resultadoGoogle({
      customerId: '8017851692', campaignId: '24155134757', date: '2026-08-31',
      // int64 chega como STRING no REST; zero medido chega como "0".
      metricas: { impressions: '1200', clicks: '0', costMicros: '0', ctr: 0, conversions: 0 },
    }),
  ];
  const r = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina(linhas),
  });
  const l = r.documentosEnviados[0].linhas[0];
  prova('int64 em string vira número', l.impressoes === 1200);
  prova('zero medido continua ZERO, não nulo',
    l.cliques === 0 && l.custo_micros === 0 && l.ctr === 0 && l.conversoes === 0);
  prova('métrica ausente continua NULA, não zero',
    l.valor_conversoes === null && l.search_impression_share === null
    && l.custo_por_conversao_micros === null && l.cpc_medio_micros === null);
  prova('a identidade VOLC entra pelo mapa da conta',
    l.volc_campaign_id === 'gads-8017851692-24155134757');
  prova('moeda viaja com o dinheiro', l.currency_code === 'BRL');

  const vazias = [resultadoGoogle({
    customerId: '8017851692', campaignId: '24155134757', date: '2026-08-31',
    metricas: { impressions: '', clicks: null, conversions: undefined },
  })];
  const r2 = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina(vazias),
  });
  const l2 = r2.documentosEnviados[0].linhas[0];
  prova('string vazia é ausência, nunca zero',
    l2.impressoes === null && l2.cliques === null && l2.conversoes === null);
}

console.log('\n── IDENTIDADE DEVOLVIDA E CONTA COMPARTILHADA');
{
  provaLanca('conta devolvida diferente da pedida derruba a página', () => {
    executarFluxo('D-1', {
      agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
      google: googleUmaPagina([resultadoGoogle({
        customerId: '9999999999', campaignId: '1', date: '2026-08-31', metricas: {},
      })]),
    });
  }, 'IDENTIDADE_DIVERGENTE');

  const duas = executarFluxo('D-1', {
    agora: AGORA,
    contasInventario: [
      { customer_id: '8017851692', nome: 'A' }, { customer_id: '7788990011', nome: 'B' },
    ],
    campanhasInventario: CAMPANHAS,
    google: (ctx) => ({
      corpo: {
        results: [resultadoGoogle({
          customerId: ctx.customer_id, campaignId: '99999999',
          date: '2026-08-31', metricas: { impressions: '10' },
        })],
      },
    }),
  });
  const chaves = duas.documentosEnviados.flatMap((d) => d.linhas)
    .map((l) => `${l.customer_id}|${l.campaign_id}`);
  prova('duas contas com o MESMO campaign_id produzem duas linhas distintas',
    new Set(chaves).size === 2 && chaves.length === 2, chaves.join(' · '));
}

console.log('\n── VALIDAÇÃO, PARCIAL E LINHA VERDE');
{
  const linhas = [
    resultadoGoogle({
      customerId: '8017851692', campaignId: '111', date: '2026-08-31',
      metricas: { impressions: '10' },
    }),
    resultadoGoogle({
      customerId: '8017851692', campaignId: '222', date: '2026-08-31',
      currency: '', metricas: { impressions: '20' },
    }),
    resultadoGoogle({
      customerId: '8017851692', campaignId: '333', date: '2026-07-01',
      metricas: { impressions: '30' },
    }),
    resultadoGoogle({
      customerId: '8017851692', campaignId: '444', date: '2026-08-31',
      metricas: { impressions: '40', ctr: 62 },
    }),
  ];
  const r = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina(linhas),
  });
  const doc = r.documentosEnviados[0];
  prova('a linha boa sobreviveu', doc.linhas.length === 1 && doc.linhas[0].campaign_id === '111');
  prova('o lote se declara parcial e diz por quê',
    doc.resultado === 'parcial' && /3 de 4 linhas recusadas/.test(doc.motivo || ''), doc.motivo);
  const motivos = r.rt.saidas.get('Validar semanticamente').at(-1)[0].json.recusas_locais
    .map((x) => x.motivo);
  prova('cada recusa é NOMEADA (moeda, janela, taxa fora de 0..1)',
    motivos.includes('MOEDA_AUSENTE_OU_INVALIDA')
    && motivos.includes('DATA_FORA_DA_JANELA')
    && motivos.some((m) => m.startsWith('TAXA_FORA_DE_0_1')), motivos.join(','));
  prova('a recusa local entra no acumulado como rejeitada, não some',
    r.done[0].acumulado.linhas_rejeitadas === 3, String(r.done[0].acumulado.linhas_rejeitadas));
}

console.log('\n── PAGINAÇÃO, LOTES E ACUMULADO');
{
  const pagina = (n, token) => ({
    corpo: {
      results: Array.from({ length: n }, (_, i) => resultadoGoogle({
        customerId: '8017851692', campaignId: `${1000 + i}`,
        date: '2026-08-31', metricas: { impressions: String(i) },
      })),
      nextPageToken: token,
    },
  });
  const r = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: (_ctx, idx) => [pagina(3, 't1'), pagina(3, 't2'), pagina(1, undefined)][idx],
  });
  prova('as três páginas viraram três lotes', r.documentosEnviados.length === 3);
  prova('os ordinais de lote são contíguos a partir de 1',
    JSON.stringify(r.documentosEnviados.map((d) => d.lote_ordinal)) === '[1,2,3]',
    r.documentosEnviados.map((d) => d.lote_ordinal).join(','));
  prova('a chave de idempotência é uma por lote',
    new Set(r.documentosEnviados.map((d) => d.chave_idempotencia)).size === 3);
  prova('a ÚLTIMA página, parcial, não se perdeu',
    r.documentosEnviados[2].linhas.length === 1);
  prova('nenhuma linha foi descartada na paginação',
    r.documentosEnviados.reduce((s, d) => s + d.linhas.length, 0) === 7);
  prova('o token da página seguinte foi respeitado, não ignorado',
    r.documentosEnviados.length === 3 && r.done[0].acumulado.paginas === 3);
  prova('o acumulado cobre TODAS as páginas, não só a última',
    r.done[0].acumulado.linhas_aceitas === 7, String(r.done[0].acumulado.linhas_aceitas));
  prova('o fechamento soma o acumulado inteiro',
    r.fechamento.documento.linhas_aceitas === 7);

  provaLanca('estourar o teto de páginas para a execução em vez de truncar', () => {
    executarFluxo('D-1', {
      agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
      configExtra: { MAX_PAGINAS: '2' },
      google: () => pagina(1, 'sempre-tem-mais'),
    });
  }, 'PAGINACAO_ACIMA_DO_TETO');
}

console.log('\n── VÁRIAS CONTAS: O DONE ACUMULA TODAS');
{
  const r = executarFluxo('D-1', {
    agora: AGORA,
    contasInventario: [
      { customer_id: '8017851692', nome: 'A' },
      { customer_id: '7788990011', nome: 'B' },
      { customer_id: '5566778899', nome: 'C' },
    ],
    campanhasInventario: CAMPANHAS,
    google: (ctx) => ({
      corpo: {
        results: [resultadoGoogle({
          customerId: ctx.customer_id, campaignId: `9${ctx.customer_id.slice(0, 3)}`,
          date: '2026-08-31', metricas: { impressions: '5' },
        })],
      },
    }),
  });
  prova('o laço percorreu as três contas', r.done.length === 3);
  prova('o fechamento soma as três, não só a última',
    r.fechamento.documento.linhas_aceitas === 3
    && r.fechamento.documento.contas_aceitas.length === 3);
  prova('as contas tentadas são declaradas em ordem',
    JSON.stringify(r.fechamento.documento.contas_tentadas)
      === JSON.stringify(['5566778899', '7788990011', '8017851692']));
  prova('o fechamento é um só, com ordinal 0',
    r.fechamento.documento.tipo_lote === 'fechamento'
    && r.fechamento.documento.lote_ordinal === 0);
  prova('a chave do fechamento deriva da execução',
    r.fechamento.documento.chave_idempotencia === `${r.identidade.execucao_chave}|0`);
}

console.log('\n── FALHA NÃO VIRA VAZIO');
{
  const erro401 = { error: { message: 'Request failed with status code 401', httpCode: '401' } };
  const erro429 = { error: { message: 'Too Many Requests', httpCode: '429' } };
  const erro503 = { error: { message: 'Service Unavailable' , httpCode: '503' } };

  const parcial = executarFluxo('D-1', {
    agora: AGORA,
    contasInventario: [
      { customer_id: '8017851692', nome: 'A' }, { customer_id: '7788990011', nome: 'B' },
    ],
    campanhasInventario: CAMPANHAS,
    google: (ctx) => (ctx.customer_id === '7788990011'
      ? { erro: erro401 }
      : {
        corpo: {
          results: [resultadoGoogle({
            customerId: ctx.customer_id, campaignId: '111',
            date: '2026-08-31', metricas: { impressions: '1' },
          })],
        },
      }),
  });
  prova('401 é classificado como AUTENTICAÇÃO, sem retry recomendado',
    parcial.done.some((d) => d.erro_classe === 'AUTENTICACAO' && d.retry_recomendado === false));
  prova('a conta que falhou NÃO entra como vazio: ela entra como recusada',
    parcial.fechamento.documento.contas_recusadas.length === 1
    && parcial.fechamento.documento.contas_aceitas.length === 1);
  prova('com verde e vermelho, o desfecho é PARCIAL e nomeia a causa',
    parcial.fechamento.documento.resultado === 'parcial'
    && /AUTENTICACAO/.test(parcial.fechamento.documento.motivo || ''),
    parcial.fechamento.documento.motivo);
  prova('a linha verde sobreviveu à falha da outra conta',
    parcial.fechamento.documento.linhas_aceitas === 1);
  prova('erro classificado nunca reentra no pedido: a conta é encerrada',
    parcial.done.filter((d) => d.estado_conta === 'falhou')
      .every((d) => d.tem_proxima_pagina === false));

  const todasFalham = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: () => ({ erro: erro503 }),
  });
  prova('5xx vira INDISPONIVEL com retry recomendado',
    todasFalham.done[0].erro_classe === 'INDISPONIVEL'
    && todasFalham.done[0].retry_recomendado === true);
  prova('todas as contas falhando é FALHOU, com zero linha aceita',
    todasFalham.fechamento.documento.resultado === 'falhou'
    && todasFalham.fechamento.documento.linhas_aceitas === 0);
  prova('falha fechada NÃO produz alerta silencioso: ela alerta',
    todasFalham.saude.alerta === true && todasFalham.saude.estado_saude === 'FALHOU');

  const cota = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: () => ({ erro: erro429 }),
  });
  prova('429 vira COTA com retry recomendado',
    cota.done[0].erro_classe === 'COTA' && cota.done[0].retry_recomendado === true);

  const desconhecido = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: () => ({ erro: { error: { message: 'socket hang up' } } }),
  });
  prova('erro sem código vira DESCONHECIDA, jamais "ok"',
    desconhecido.done[0].erro_classe === 'DESCONHECIDA'
    && desconhecido.fechamento.documento.resultado === 'falhou');
}

console.log('\n── VAZIO CONFIRMADO ≠ FALHA');
{
  const r = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina([]),
  });
  prova('conta sem campanha na janela fecha como ok',
    r.fechamento.documento.resultado === 'ok'
    && r.fechamento.documento.linhas_aceitas === 0);
  prova('vazio confirmado é declarado, e NÃO alerta',
    r.saude.vazio_confirmado === true && r.saude.alerta === false
    && r.saude.estado_saude === 'SAUDAVEL');
}

console.log('\n── RECIBO, RELEITURA E BATIMENTO');
{
  provaLanca('recibo de outro lote derruba a execução', () => {
    executarFluxo('D-1', {
      agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
      google: googleUmaPagina([resultadoGoogle({
        customerId: '8017851692', campaignId: '1', date: '2026-08-31', metricas: {},
      })]),
      rpc: () => ({ chave_idempotencia: 'de-outra-execucao', linhas_lidas: 1, linhas_aceitas: 1, linhas_preteridas: 0, linhas_rejeitadas: 0 }),
    });
  }, 'RECIBO_DE_OUTRO_LOTE');

  provaLanca('recibo cujas contagens não fecham derruba a execução', () => {
    executarFluxo('D-1', {
      agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
      google: googleUmaPagina([resultadoGoogle({
        customerId: '8017851692', campaignId: '1', date: '2026-08-31', metricas: {},
      })]),
      rpc: (d) => ({
        chave_idempotencia: d.chave_idempotencia,
        linhas_lidas: 9, linhas_aceitas: 1, linhas_preteridas: 0, linhas_rejeitadas: 0,
      }),
    });
  }, 'RECIBO_NAO_FECHA');

  provaLanca('recibo que conta diferente do enviado derruba a execução', () => {
    executarFluxo('D-1', {
      agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
      google: googleUmaPagina([resultadoGoogle({
        customerId: '8017851692', campaignId: '1', date: '2026-08-31', metricas: {},
      })]),
      rpc: (d) => ({
        chave_idempotencia: d.chave_idempotencia,
        linhas_lidas: 0, linhas_aceitas: 0, linhas_preteridas: 0, linhas_rejeitadas: 0,
      }),
    });
  }, 'RECIBO_DIVERGE_DO_ENVIO');

  const semReleitura = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina([]),
    releitura: () => [],
  });
  prova('recibo que não aparece na releitura é INDETERMINADO e alerta',
    semReleitura.saude.estado_saude === 'INDETERMINADO'
    && semReleitura.saude.alerta === true
    && semReleitura.saude.releitura_encontrada === false);

  const divergente = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina([resultadoGoogle({
      customerId: '8017851692', campaignId: '1', date: '2026-08-31', metricas: {},
    })]),
    releitura: (doc) => [{
      execucao_chave: doc.execucao_chave, resultado: 'ok',
      linhas_aceitas: 99, batimento_em: doc.batimento_em,
    }],
  });
  prova('releitura que diverge do fluxo é INDETERMINADO e alerta',
    divergente.saude.estado_saude === 'INDETERMINADO' && divergente.saude.alerta === true);

  const outraExec = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina([]),
    releitura: () => [{
      execucao_chave: 'gads_dia_d1:D-1:2020-01-01:06', resultado: 'ok', linhas_aceitas: 0,
    }],
  });
  prova('recibo de OUTRA execução não conta como releitura desta',
    outraExec.saude.estado_saude === 'INDETERMINADO' && outraExec.saude.alerta === true);

  const bom = executarFluxo('D-1', {
    agora: AGORA, contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina([resultadoGoogle({
      customerId: '8017851692', campaignId: '1', date: '2026-08-31', metricas: { impressions: '1' },
    })]),
  });
  prova('batimento sai da releitura, não da memória do fluxo',
    bom.saude.batimento_em === bom.fechamento.documento.batimento_em
    && bom.saude.releitura_encontrada === true);
  prova('execução saudável não dispara alerta', bom.saude.alerta === false);
}

console.log('\n── FALHA FECHADA ANTES DE QUALQUER LEITURA');
{
  provaLanca('zero conta autorizada para a execução em vez de declarar vazio', () => {
    executarFluxo('D-1', {
      agora: AGORA, contasInventario: [], campanhasInventario: [],
      google: googleUmaPagina([]),
    });
  }, 'SEM_CONTA_AUTORIZADA');

  provaLanca('conta com identificador inválido não vira conta', () => {
    executarFluxo('D-1', {
      agora: AGORA, contasInventario: [{ customer_id: 'abc' }, { customer_id: '' }],
      campanhasInventario: [], google: googleUmaPagina([]),
    });
  }, 'SEM_CONTA_AUTORIZADA');

  const allowlist = executarFluxo('D-1', {
    agora: AGORA,
    configExtra: { CONTAS_PERMITIDAS: '7788990011' },
    contasInventario: [
      { customer_id: '8017851692' }, { customer_id: '7788990011' },
    ],
    campanhasInventario: [], google: googleUmaPagina([]),
  });
  prova('a allowlist do canário restringe a execução a UMA conta',
    allowlist.selecionadas.contas.length === 1
    && allowlist.selecionadas.contas[0] === '7788990011');

  const repetida = executarFluxo('D-1', {
    agora: AGORA,
    contasInventario: [
      { customer_id: '8017851692' }, { customer_id: '8017851692' },
    ],
    campanhasInventario: [], google: googleUmaPagina([]),
  });
  prova('conta repetida no inventário não vira duas leituras',
    repetida.selecionadas.contas.length === 1);
}

console.log('\n── IDEMPOTÊNCIA DA REPETIÇÃO');
{
  const cenario = () => ({
    agora: new Date('2026-09-01T13:30:00.000Z'),
    contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina([resultadoGoogle({
      customerId: '8017851692', campaignId: '24155134757',
      date: '2026-08-31', metricas: { impressions: '7' },
    })]),
  });
  const a = executarFluxo('D-1', cenario());
  const b = executarFluxo('D-1', cenario());
  prova('a mesma passada repetida produz a MESMA chave de lote',
    a.documentosEnviados[0].chave_idempotencia === b.documentosEnviados[0].chave_idempotencia,
    a.documentosEnviados[0].chave_idempotencia);
  prova('a mesma passada repetida produz o MESMO conteúdo de linhas',
    JSON.stringify(a.documentosEnviados[0].linhas) === JSON.stringify(b.documentosEnviados[0].linhas));

  // ⚠️ D-1 roda UMA vez por dia. Duas rodadas agendadas no mesmo dia são a
  // MESMA passada, e é isso que torna o retry idempotente — não um defeito.
  const d1MaisTarde = executarFluxo('D-1', {
    ...cenario(), agora: new Date('2026-09-01T21:30:00.000Z'),
  });
  prova('em D-1, outra hora do mesmo dia continua sendo a MESMA passada',
    d1MaisTarde.documentosEnviados[0].chave_idempotencia
      === a.documentosEnviados[0].chave_idempotencia,
    d1MaisTarde.documentosEnviados[0].chave_idempotencia);

  // D0 tem quatro passadas; cada uma é uma leitura nova da janela aberta.
  const cenarioD0 = (agora) => ({
    agora,
    contasInventario: CONTAS, campanhasInventario: CAMPANHAS,
    google: googleUmaPagina([resultadoGoogle({
      customerId: '8017851692', campaignId: '24155134757',
      date: '2026-09-01', metricas: { impressions: '7' },
    })]),
  });
  const d0Manha = executarFluxo('D0', cenarioD0(new Date('2026-09-01T13:30:00.000Z')));
  const d0Noite = executarFluxo('D0', cenarioD0(new Date('2026-09-02T01:30:00.000Z')));
  prova('em D0, a passada das 22:30 é OUTRA leitura, com outra chave',
    d0Noite.documentosEnviados[0].chave_idempotencia
      !== d0Manha.documentosEnviados[0].chave_idempotencia,
    `${d0Manha.documentosEnviados[0].chave_idempotencia} vs `
    + d0Noite.documentosEnviados[0].chave_idempotencia);
  prova('as quatro passadas D0 leem a MESMA janela do dia',
    d0Noite.identidade.janela_inicio === d0Manha.identidade.janela_inicio);
}

console.log('\n════════════════════════════════════════════════════════');
console.log(`  passaram ${ok} · falharam ${falhas.length}`);
if (falhas.length) {
  for (const f of falhas) console.log(`    ✗ ${f}`);
  process.exit(1);
}
console.log(`  SIMULAÇÃO OFFLINE COMPLETA (rpc=${modoRpc}) — zero rede, relógio injetado`);
