#!/usr/bin/env python3
"""Gera os dois workflows n8n de ingestao Google Ads campanha-dia (D0 e D-1).

Os dois nascem do MESMO template: a unica diferenca e a janela (hoje x ontem
fechado), a agenda e o nome do job. Duplicar o JSON a mao seria garantir que os
dois divergissem na primeira correcao — foi assim que os fluxos legados
acabaram com `Code` e `Code15` fazendo quase a mesma coisa de jeitos diferentes.

O que este gerador NAO faz: nao fala com a rede, nao chama a API do n8n, nao
ativa nada, nao le nem escreve credencial. A saida e um JSON importavel, com
`active: false`, pronto para revisao humana.

Uso:
    python3 n8n/gerar_flows_gads_ledger_v12.py
    python3 n8n/gerar_flows_gads_ledger_v12.py --check   # falha se o JSON mudou
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent
SUPABASE = "https://database.agenciavolc.com.br"
GOOGLEADS_BASE = "https://googleads.googleapis.com"
API_VERSION = "v25"
CONTRATO_VERSAO = "gads-campanha-dia-v1"

# A credencial e uma REFERENCIA, nunca um segredo: id e nome do item no cofre do
# n8n. O mesmo par ja esta versionado em n8n/joinads_report_day_before.json.
CRED_SUPABASE = {"supabaseApi": {"id": "3lSRuywq3fwQ3z3I", "name": "VOLC Oficial"}}
CRED_GOOGLEADS = {"googleAdsOAuth2Api": {"id": "REPLACE_ME", "name": "VOLC Google Ads"}}

# ─────────────────────────────────────────────────────────────────── GAQL ──
#
# ⚠️ Somente SELECT. Nao existe `mutate` neste workflow, e o validador
# (scripts/validar_workflows_n8n_gads.py) recusa o JSON se aparecer um.
#
# Os 25 campos foram conferidos, offline, contra os descriptors do SDK v25
# instalado (google-ads 31.4.0) por scripts/validar_workflows_n8n_gads.py. Isso
# prova que o CAMPO existe no recurso; nao prova que o par (recurso, campo) e
# selecionavel em GAQL — isso so o `google_ads_field` da API responde, e a
# leitura real ainda nao aconteceu (REAL_READ_NOT_PROVEN).
GAQL_CAMPOS = [
    "customer.id",
    "customer.currency_code",
    "campaign.id",
    "campaign.name",
    "campaign.status",
    "campaign.advertising_channel_type",
    "segments.date",
    "metrics.impressions",
    "metrics.clicks",
    "metrics.interactions",
    "metrics.cost_micros",
    "metrics.conversions",
    "metrics.all_conversions",
    "metrics.conversions_value",
    "metrics.all_conversions_value",
    "metrics.ctr",
    "metrics.average_cpc",
    "metrics.cost_per_conversion",
    "metrics.search_impression_share",
    "metrics.search_budget_lost_impression_share",
    "metrics.search_rank_lost_impression_share",
    "metrics.search_top_impression_share",
    "metrics.search_absolute_top_impression_share",
    "metrics.search_click_share",
    "metrics.search_exact_match_impression_share",
    "metrics.top_impression_percentage",
    "metrics.absolute_top_impression_percentage",
]

# ────────────────────────────────────────────────────────── code: comuns ──

JS_AJUDANTES = r"""
// ── ajudantes compartilhados ────────────────────────────────────────────────
// Sem `require`: o Code node do n8n bloqueia builtins por padrao
// (NODE_FUNCTION_ALLOW_BUILTIN nao esta armada). Sem luxon tambem: `Intl`
// resolve fuso corretamente e nao depende de biblioteca.
function dataNaZona(instante, tz) {
  const partes = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(instante);
  const v = {};
  for (const p of partes) v[p.type] = p.value;
  if (!v.year || !v.month || !v.day) {
    throw new Error(`FUSO_INVALIDO: nao consegui ler a data em ${tz}`);
  }
  return `${v.year}-${v.month}-${v.day}`;
}

function horaNaZona(instante, tz) {
  const partes = new Intl.DateTimeFormat('en-GB', {
    timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(instante);
  const v = {};
  for (const p of partes) v[p.type] = p.value;
  return { hora: v.hour, minuto: v.minute };
}

// Aritmetica de CALENDARIO, nao de milissegundos: subtrair 86400000 de um
// instante erra no dia em que o fuso muda. Aqui o dia anterior sai da data
// local ja resolvida.
function diaAnterior(iso) {
  const [a, m, d] = iso.split('-').map(Number);
  const x = new Date(Date.UTC(a, m - 1, d) - 86400000);
  const p = (n) => String(n).padStart(2, '0');
  return `${x.getUTCFullYear()}-${p(x.getUTCMonth() + 1)}-${p(x.getUTCDate())}`;
}
"""

JS_IDENTIDADE = JS_AJUDANTES + r"""
// ── IDENTIDADE DA EXECUCAO ──────────────────────────────────────────────────
//
// A chave e `job:origem:janela:passo`, e o PASSO e deliberado: as quatro
// passadas D0 do mesmo dia sao QUATRO leituras da mesma janela, nao repeticoes
// da mesma leitura. Colapsa-las numa chave so obrigaria a ATUALIZAR o recibo, e
// recibo que se atualiza deixa de ser recibo. E preserva a doutrina do coletor
// v3: uma falha nao ocupa a chave do sucesso posterior.
const cfg = $('Config').first().json;
const tz = String(cfg.TZ || 'America/Sao_Paulo');
const modo = String(cfg.JANELA_MODO || '').toUpperCase();
if (modo !== 'D0' && modo !== 'D-1') {
  throw new Error(`JANELA_MODO_INVALIDO: ${cfg.JANELA_MODO}`);
}

const agora = new Date();
const hojeSp = dataNaZona(agora, tz);
const janela = modo === 'D0' ? hojeSp : diaAnterior(hojeSp);

// Disparo: `isExecuted` diz qual gatilho acordou o fluxo. Se o no nem existir
// na execucao, tratamos como manual — nunca como agenda, porque declarar
// "agenda" numa rodada manual mentiria para o deadman.
let porAgenda = false;
try { porAgenda = Boolean($('Agenda').isExecuted); } catch (e) { porAgenda = false; }
const disparo = porAgenda ? 'agenda' : 'manual';

const relogio = horaNaZona(agora, tz);
const passosConfigurados = String(cfg.PASSOS || '')
  .split(',').map((s) => s.trim()).filter(Boolean);

function passoDaAgenda(hora) {
  // Encaixa a hora atual no ultimo passo agendado <= hora. Sem passo anterior,
  // usa o ultimo do dia — a rodada da madrugada pertence ao ciclo anterior.
  let escolhido = passosConfigurados[passosConfigurados.length - 1];
  for (const p of passosConfigurados) {
    if (p <= hora) escolhido = p;
  }
  return escolhido;
}

let passo;
if (String(cfg.PASSO_FORCADO || '').trim() !== '') {
  passo = String(cfg.PASSO_FORCADO).trim();
} else if (disparo === 'agenda') {
  passo = passoDaAgenda(relogio.hora);
} else {
  // Rodada manual ganha passo proprio: repetir o mesmo minuto e idempotente,
  // e um minuto depois e outra leitura, com outro recibo.
  passo = `m${relogio.hora}${relogio.minuto}`;
}
if (!passo) throw new Error('PASSO_INDETERMINADO: PASSOS vazio no Config');

const job = String(cfg.JOB || '');
if (!/^[a-z0-9_]{3,40}$/.test(job)) throw new Error(`JOB_INVALIDO: ${job}`);

const execucaoChave = `${job}:${modo}:${janela}:${passo}`;
const contasPermitidas = String(cfg.CONTAS_PERMITIDAS || '')
  .split(',').map((s) => s.trim()).filter(Boolean);

const filtroConta = contasPermitidas.length
  ? `&customer_id=in.(${contasPermitidas.join(',')})`
  : '';

return [{
  json: {
    fonte: 'n8n',
    job,
    disparo,
    origem_janela: modo,
    janela_inicio: janela,
    janela_fim: janela,
    passo,
    execucao_chave: execucaoChave,
    api_versao: String(cfg.GOOGLEADS_API_VERSION || ''),
    contrato_versao: String(cfg.CONTRATO_VERSAO || ''),
    contrato_sha256: String(cfg.CONTRATO_SHA256 || ''),
    tz,
    workflow_id: $workflow.id,
    execucao_externa_id: String($execution.id),
    iniciada_em: agora.toISOString(),
    contas_permitidas: contasPermitidas,
    url_contas: `${cfg.SUPABASE_URL}/rest/v1/trafego_inventario_conta`
      + `?select=customer_id,nome&order=customer_id.asc&limit=500${filtroConta}`,
  },
}];
"""

JS_SELECIONAR_CONTAS = r"""
// ── CONTAS AUTORIZADAS ──────────────────────────────────────────────────────
//
// A lista vem do inventario governado, nunca de constante no fluxo. Emite UM
// item de proposito: o proximo no e um HTTP, e um item por conta o faria
// disparar N vezes.
const ident = $('Identidade da execucao').first().json;
const cfg = $('Config').first().json;
const permitidas = ident.contas_permitidas || [];

const vistas = new Set();
const contas = [];
for (const item of $input.all()) {
  const linha = item.json;
  if (linha === null || linha === undefined) continue;
  const bruto = linha.customer_id;
  if (bruto === null || bruto === undefined || bruto === '') continue;
  const cid = String(bruto).replace(/[^0-9]/g, '');
  if (!/^[0-9]{6,12}$/.test(cid)) continue;
  if (permitidas.length && !permitidas.includes(cid)) continue;
  if (vistas.has(cid)) continue;
  vistas.add(cid);
  contas.push(cid);
}
contas.sort();

// Falha fechada. Zero conta autorizada NAO e "nada a fazer": ou o inventario
// nao respondeu, ou a allowlist esta errada. Seguir daria um recibo verde de
// uma rodada que nao leu nada.
if (contas.length === 0) {
  throw new Error('SEM_CONTA_AUTORIZADA: o inventario nao devolveu conta valida'
    + ' para esta execucao; nada foi lido e nada sera declarado como vazio');
}

const url = `${cfg.SUPABASE_URL}/rest/v1/trafego_inventario_campanha`
  + `?select=volc_campaign_id,customer_id,campaign_id&limit=20000`
  + `&customer_id=in.(${contas.join(',')})`;

return [{ json: { ...ident, contas, total_contas: contas.length, url_campanhas: url } }];
"""

JS_MAPA_IDENTIDADE = r"""
// ── IDENTIDADE VOLC POR CONTA ───────────────────────────────────────────────
//
// Cada conta leva SO o seu pedaco do mapa. Carregar o mapa inteiro em todo item
// engordaria o loop sem necessidade, e ler o mapa com `$('No').all()` dentro do
// laco seria o acumulador global que este contrato proibe.
const base = $('Selecionar contas').first().json;
const porConta = {};
for (const item of $input.all()) {
  const linha = item.json;
  if (!linha || linha.customer_id === null || linha.customer_id === undefined) continue;
  const cid = String(linha.customer_id);
  const camp = linha.campaign_id === null || linha.campaign_id === undefined
    ? null : String(linha.campaign_id);
  const volc = linha.volc_campaign_id === null || linha.volc_campaign_id === undefined
    ? null : String(linha.volc_campaign_id);
  if (!camp || !volc) continue;
  if (!porConta[cid]) porConta[cid] = {};
  porConta[cid][camp] = volc;
}

return base.contas.map((cid, i) => ({
  json: {
    fonte: base.fonte,
    job: base.job,
    disparo: base.disparo,
    origem_janela: base.origem_janela,
    janela_inicio: base.janela_inicio,
    janela_fim: base.janela_fim,
    execucao_chave: base.execucao_chave,
    api_versao: base.api_versao,
    contrato_versao: base.contrato_versao,
    contrato_sha256: base.contrato_sha256,
    workflow_id: base.workflow_id,
    execucao_externa_id: base.execucao_externa_id,
    iniciada_em: base.iniciada_em,
    contas_tentadas: base.contas,
    total_contas: base.total_contas,
    customer_id: cid,
    conta_ordinal: i + 1,
    mapa_conta: porConta[cid] || {},
  },
}));
"""

JS_PREPARAR_PAGINA = r"""
// ── PEDIDO DE UMA PAGINA ────────────────────────────────────────────────────
//
// ⚠️ UMA CONTA POR ITERACAO, e isso e uma decisao, nao um descuido. O endpoint
// `googleAds:search` e POR CLIENTE: um lote com N contas exigiria abrir o lote
// de novo dentro do laco, e o retorno do laco passaria a disparar mais de uma
// vez por iteracao — que e exatamente como um `SplitInBatches` pula lote. O
// lote de VOLUME e a pagina (PAGE_SIZE linhas por chamada e por RPC).
const itens = $input.all();
if (itens.length === 0) {
  throw new Error('LOTE_VAZIO: o laco entregou zero item');
}
if (itens.length > 1) {
  throw new Error(`LOTE_CONTAS_MAIOR_QUE_UM: ${itens.length} contas na mesma iteracao;`
    + ' o batchSize do laco precisa continuar 1 enquanto a chamada for por cliente');
}
const ctx = itens[0].json;
const cfg = $('Config').first().json;

const pagina = Number(ctx.pagina || 0) + 1;
const teto = Math.max(1, Number(cfg.MAX_PAGINAS) || 50);
// Truncar em silencio seria descartar linha lida. Estourar o teto e erro.
if (pagina > teto) {
  throw new Error(`PAGINACAO_ACIMA_DO_TETO: conta ${ctx.customer_id} passou de ${teto}`
    + ' paginas; nenhuma linha foi descartada, a execucao parou');
}

const campos = String(cfg.GAQL_CAMPOS || '').split(',').map((s) => s.trim()).filter(Boolean);
if (campos.length === 0) throw new Error('GAQL_SEM_CAMPOS');
const gaql = `SELECT ${campos.join(', ')} FROM campaign`
  + ` WHERE segments.date BETWEEN '${ctx.janela_inicio}' AND '${ctx.janela_fim}'`
  + ` ORDER BY campaign.id`;

return [{
  json: {
    ...ctx,
    pagina,
    page_token: String(ctx.proximo_page_token || ''),
    page_size: Math.max(1, Number(cfg.PAGE_SIZE) || 1000),
    gaql,
    url_google: `${cfg.GOOGLEADS_BASE}/${ctx.api_versao}/customers/${ctx.customer_id}`
      + '/googleAds:search',
    login_customer_id: String(cfg.LOGIN_CUSTOMER_ID || ''),
    acumulado: ctx.acumulado || {
      linhas_lidas: 0, linhas_aceitas: 0, linhas_preteridas: 0,
      linhas_rejeitadas: 0, projecao_linhas: 0, paginas: 0,
    },
  },
}];
"""

JS_NORMALIZAR = r"""
// ── NORMALIZACAO ────────────────────────────────────────────────────────────
//
// ⚠️ AQUI MORA O DEFEITO QUE ESTA ENTREGA CORRIGE. O Code legado fazia
// `parseFloat(item.metrics?.conversionsValue || 0)`: ausencia virava ZERO, e
// depois ninguem conseguia separar "nao entregou" de "nao li". Aqui ausencia
// vira `null` e zero medido continua zero — os dois viajam ate o banco, onde a
// coluna nao tem DEFAULT.
// ⚠️ O contexto CHEGA NO ITEM, vindo do Merge — nao de
// `$('Pagina: preparar pedido')`. A primeira versao usava `$()` e o simulador
// derrubou: `$()` resolve pelo INDICE DA RODADA do no atual, e uma conta que
// falha faz o pedido rodar mais vezes que a normalizacao. Na segunda conta, o
// contexto lido era o da PRIMEIRA — a conta errada com a mesma cara.
const ctx = $input.first().json;
const corpo = ctx;

if (!ctx || String(ctx.customer_id || '') === '') {
  throw new Error('CONTEXTO_PERDIDO: a iteracao nao trouxe a conta pedida');
}

const resultados = Array.isArray(corpo && corpo.results) ? corpo.results : [];
const proximo = corpo && corpo.nextPageToken ? String(corpo.nextPageToken) : '';

function num(v) {
  // '' e ausencia, nao zero: `Number('')` devolveria 0 e fabricaria medida.
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'boolean') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function inteiro(v) {
  const n = num(v);
  return n === null ? null : Math.trunc(n);
}
function texto(v) {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s === '' ? null : s;
}

const colhidaEm = new Date().toISOString();
const linhas = [];
for (const r of resultados) {
  const cliente = (r && r.customer) || {};
  const campanha = (r && r.campaign) || {};
  const seg = (r && r.segments) || {};
  const m = (r && r.metrics) || {};

  const contaDevolvida = texto(cliente.id);
  if (contaDevolvida !== null && contaDevolvida !== String(ctx.customer_id)) {
    throw new Error(`IDENTIDADE_DIVERGENTE: pedi ${ctx.customer_id} e a resposta`
      + ` trouxe ${contaDevolvida}`);
  }

  linhas.push({
    customer_id: String(ctx.customer_id),
    campaign_id: texto(campanha.id),
    metric_date: texto(seg.date),
    volc_campaign_id: (ctx.mapa_conta || {})[texto(campanha.id)] || null,
    campaign_name: texto(campanha.name),
    campaign_status: texto(campanha.status),
    advertising_channel_type: texto(campanha.advertisingChannelType),
    currency_code: texto(cliente.currencyCode),
    colhida_em: colhidaEm,
    segmentos: {},

    impressoes: inteiro(m.impressions),
    cliques: inteiro(m.clicks),
    interacoes: inteiro(m.interactions),
    custo_micros: inteiro(m.costMicros),

    conversoes: num(m.conversions),
    todas_conversoes: num(m.allConversions),
    valor_conversoes: num(m.conversionsValue),
    valor_todas_conversoes: num(m.allConversionsValue),

    ctr: num(m.ctr),
    // Micros vem da API; nao recalculamos custo/conversao a partir de outras
    // duas medidas — o legado fazia isso e inventava numero quando conversoes
    // era zero.
    cpc_medio_micros: num(m.averageCpc),
    custo_por_conversao_micros: num(m.costPerConversion),

    search_impression_share: num(m.searchImpressionShare),
    search_budget_lost_impression_share: num(m.searchBudgetLostImpressionShare),
    search_rank_lost_impression_share: num(m.searchRankLostImpressionShare),
    search_top_impression_share: num(m.searchTopImpressionShare),
    search_absolute_top_impression_share: num(m.searchAbsoluteTopImpressionShare),
    search_click_share: num(m.searchClickShare),
    search_exact_match_impression_share: num(m.searchExactMatchImpressionShare),
    top_impression_percentage: num(m.topImpressionPercentage),
    absolute_top_impression_percentage: num(m.absoluteTopImpressionPercentage),

    metricas_extras: {},
  });
}

// O ordinal do lote e o indice da rodada DESTE no, que so executa quando a
// chamada ao Google deu certo. Assim a sequencia de lotes fica contigua e o
// fechamento consegue acusar lote perdido.
const loteOrdinal = Number($runIndex) + 1;
if (!Number.isInteger(loteOrdinal) || loteOrdinal < 1) {
  throw new Error(`LOTE_ORDINAL_INVALIDO: ${loteOrdinal}`);
}

return [{
  json: {
    ...ctx,
    lote_ordinal: loteOrdinal,
    linhas,
    linhas_lidas_na_pagina: linhas.length,
    proximo_page_token: proximo,
    tem_proxima_pagina: proximo !== '',
    pagina_lida_em: colhidaEm,
  },
}];
"""

JS_VALIDAR = r"""
// ── VALIDACAO SEMANTICA ─────────────────────────────────────────────────────
//
// O banco valida de novo, e isso e de proposito: aqui a recusa vira motivo
// legivel no recibo, la ela vira constraint. Duas redes, a mesma regra.
const ctx = $input.first().json;
const linhas = Array.isArray(ctx.linhas) ? ctx.linhas : [];

const TAXAS = [
  'ctr', 'search_impression_share', 'search_budget_lost_impression_share',
  'search_rank_lost_impression_share', 'search_top_impression_share',
  'search_absolute_top_impression_share', 'search_click_share',
  'search_exact_match_impression_share', 'top_impression_percentage',
  'absolute_top_impression_percentage',
];
const NAO_NEGATIVAS = [
  'impressoes', 'cliques', 'interacoes', 'custo_micros', 'conversoes',
  'todas_conversoes', 'valor_conversoes', 'valor_todas_conversoes',
  'cpc_medio_micros', 'custo_por_conversao_micros',
];

const boas = [];
const recusadas = [];
const chaves = new Set();

for (let i = 0; i < linhas.length; i += 1) {
  const l = linhas[i];
  let motivo = null;

  if (!/^[0-9]{6,12}$/.test(String(l.customer_id || ''))) motivo = 'CUSTOMER_ID_INVALIDO';
  else if (!/^[0-9]{1,20}$/.test(String(l.campaign_id || ''))) motivo = 'CAMPAIGN_ID_INVALIDO';
  else if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(String(l.metric_date || ''))) motivo = 'DATA_AUSENTE';
  else if (l.metric_date < ctx.janela_inicio || l.metric_date > ctx.janela_fim) motivo = 'DATA_FORA_DA_JANELA';
  else if (!/^[A-Z]{3}$/.test(String(l.currency_code || ''))) motivo = 'MOEDA_AUSENTE_OU_INVALIDA';

  if (motivo === null) {
    for (const campo of TAXAS) {
      const v = l[campo];
      if (v !== null && (typeof v !== 'number' || v < 0 || v > 1)) {
        motivo = `TAXA_FORA_DE_0_1:${campo}`;
        break;
      }
    }
  }
  if (motivo === null) {
    for (const campo of NAO_NEGATIVAS) {
      const v = l[campo];
      if (v !== null && (typeof v !== 'number' || v < 0)) {
        motivo = `VALOR_NEGATIVO_OU_NAO_NUMERICO:${campo}`;
        break;
      }
    }
  }
  if (motivo === null) {
    const chave = `${l.customer_id}|${l.campaign_id}|${l.metric_date}`;
    if (chaves.has(chave)) motivo = 'LINHA_DUPLICADA_NA_PAGINA';
    else chaves.add(chave);
  }

  if (motivo === null) boas.push(l);
  else recusadas.push({ ordinal: i + 1, campaign_id: l.campaign_id || null, motivo });
}

// ⚠️ A pagina segue mesmo com linha recusada: parcial preserva a linha verde.
// O que NAO pode acontecer e a recusa sumir — ela viaja no motivo do lote.
const houveRecusa = recusadas.length > 0;
const resultado = houveRecusa ? 'parcial' : 'ok';
const motivoLote = houveRecusa
  ? `${recusadas.length} de ${linhas.length} linhas recusadas na validacao local`
  : null;

const agora = new Date().toISOString();
const documento = {
  chave_idempotencia: `${ctx.execucao_chave}|${ctx.lote_ordinal}`,
  execucao_chave: ctx.execucao_chave,
  fonte: ctx.fonte,
  job: ctx.job,
  disparo: ctx.disparo,
  workflow_id: ctx.workflow_id,
  execucao_externa_id: ctx.execucao_externa_id,
  api_versao: ctx.api_versao,
  contrato_versao: ctx.contrato_versao,
  contrato_sha256: ctx.contrato_sha256,
  tipo_lote: 'contas',
  lote_ordinal: ctx.lote_ordinal,
  origem_janela: ctx.origem_janela,
  janela_inicio: ctx.janela_inicio,
  janela_fim: ctx.janela_fim,
  iniciada_em: ctx.iniciada_em,
  encerrada_em: agora,
  duracao_ms: Math.max(0, Date.parse(agora) - Date.parse(ctx.iniciada_em)),
  batimento_em: agora,
  resultado,
  motivo: motivoLote,
  escopo: `conta ${ctx.customer_id} pagina ${ctx.pagina}`,
  contas_tentadas: [String(ctx.customer_id)],
  contas_aceitas: [String(ctx.customer_id)],
  contas_recusadas: [],
  projetar_compat: true,
  linhas: boas,
};

return [{
  json: {
    ...ctx,
    documento,
    linhas_enviadas: boas.length,
    linhas_recusadas_localmente: recusadas.length,
    recusas_locais: recusadas,
  },
}];
"""

JS_RECONCILIAR = r"""
// ── RECONCILIACAO DO LOTE ───────────────────────────────────────────────────
//
// O recibo do banco tem de bater com o que o fluxo enviou. Nao bater e defeito,
// nao ruido — e o fluxo para em vez de fechar uma execucao que mente.
const recibo = $input.first().json;
const ctx = $('Validar semanticamente').first().json;

if (!recibo || typeof recibo !== 'object') {
  throw new Error('RPC_SEM_RECIBO: a ingestao nao devolveu documento');
}
// Amarra dura contra desalinhamento de rodada: o recibo tem de ser DESTE lote.
if (String(recibo.chave_idempotencia || '') !== String(ctx.documento.chave_idempotencia)) {
  throw new Error(`RECIBO_DE_OUTRO_LOTE: esperava ${ctx.documento.chave_idempotencia}`
    + ` e recebi ${recibo.chave_idempotencia}`);
}

const aceitas = Number(recibo.linhas_aceitas || 0);
const preteridas = Number(recibo.linhas_preteridas || 0);
const rejeitadas = Number(recibo.linhas_rejeitadas || 0);
const lidas = Number(recibo.linhas_lidas || 0);

if (aceitas + preteridas + rejeitadas !== lidas) {
  throw new Error(`RECIBO_NAO_FECHA: ${aceitas}+${preteridas}+${rejeitadas} != ${lidas}`);
}
if (lidas !== Number(ctx.linhas_enviadas)) {
  throw new Error(`RECIBO_DIVERGE_DO_ENVIO: enviei ${ctx.linhas_enviadas} e o banco`
    + ` contou ${lidas}`);
}

const antes = ctx.acumulado || {};
const acumulado = {
  linhas_lidas: Number(antes.linhas_lidas || 0) + lidas + Number(ctx.linhas_recusadas_localmente || 0),
  linhas_aceitas: Number(antes.linhas_aceitas || 0) + aceitas,
  linhas_preteridas: Number(antes.linhas_preteridas || 0) + preteridas,
  linhas_rejeitadas: Number(antes.linhas_rejeitadas || 0) + rejeitadas
    + Number(ctx.linhas_recusadas_localmente || 0),
  projecao_linhas: Number(antes.projecao_linhas || 0) + Number(recibo.projecao_linhas || 0),
  paginas: Number(antes.paginas || 0) + 1,
};

const projecoes = (antes.projecoes || []).concat([String(recibo.projecao_estado || 'nao_solicitada')]);

return [{
  json: {
    fonte: ctx.fonte,
    job: ctx.job,
    disparo: ctx.disparo,
    origem_janela: ctx.origem_janela,
    janela_inicio: ctx.janela_inicio,
    janela_fim: ctx.janela_fim,
    execucao_chave: ctx.execucao_chave,
    api_versao: ctx.api_versao,
    contrato_versao: ctx.contrato_versao,
    contrato_sha256: ctx.contrato_sha256,
    workflow_id: ctx.workflow_id,
    execucao_externa_id: ctx.execucao_externa_id,
    iniciada_em: ctx.iniciada_em,
    contas_tentadas: ctx.contas_tentadas,
    total_contas: ctx.total_contas,
    customer_id: ctx.customer_id,
    conta_ordinal: ctx.conta_ordinal,
    mapa_conta: ctx.mapa_conta,
    pagina: ctx.pagina,
    proximo_page_token: ctx.proximo_page_token,
    tem_proxima_pagina: Boolean(ctx.tem_proxima_pagina),
    acumulado: { ...acumulado, projecoes },
    estado_conta: 'lida',
    ultimo_recibo: recibo.chave_idempotencia,
  },
}];
"""

JS_CLASSIFICAR_ERRO = r"""
// ── CLASSIFICACAO DO ERRO DO GOOGLE ─────────────────────────────────────────
//
// ⚠️ A saida de erro NUNCA volta para o no de requisicao. Ela segue para a
// frente e reentra no laco de contas, que so anda — por isso 401/403 nao tem
// como girar. O limite de tentativa de 429/5xx e o `maxTries` do proprio no.
//
// Rotulo desconhecido vira DESCONHECIDA, nunca "ok". A mensagem publica nao
// interpola o texto bruto do erro: ele pode carregar token e cabecalho.
// Mesma razao da normalizacao: contexto pelo Merge, nunca por `$()` dentro do
// laco. Aqui o risco era pior — o classificador roda so quando ha falha, entao
// o indice de rodada dele nunca acompanha o do pedido.
const ctx = $input.first().json || {};
const bruto = ctx;

const erroComoTexto = bruto.error === null || bruto.error === undefined ? '' : String(bruto.error);
const alvo = bruto.error && typeof bruto.error === 'object' ? bruto.error : bruto;
let codigo = null;
for (const chave of ['httpCode', 'status', 'statusCode', 'code']) {
  const v = alvo[chave];
  if (v !== null && v !== undefined && /^[0-9]{3}$/.test(String(v))) {
    codigo = Number(v);
    break;
  }
}
if (codigo === null) {
  const m = `${String(alvo.message || '')} ${erroComoTexto}`.match(/\b(4[0-9]{2}|5[0-9]{2})\b/);
  if (m) codigo = Number(m[1]);
}

if (String(ctx.customer_id || '') === '') {
  throw new Error('CONTEXTO_PERDIDO: a falha chegou sem a conta que a produziu');
}

let classe;
if (codigo === 401 || codigo === 403) classe = 'AUTENTICACAO';
else if (codigo === 429) classe = 'COTA';
else if (codigo !== null && codigo >= 500) classe = 'INDISPONIVEL';
else if (codigo !== null && codigo >= 400) classe = 'PEDIDO_INVALIDO';
else classe = 'DESCONHECIDA';

const retryRecomendado = classe === 'COTA' || classe === 'INDISPONIVEL';

return [{
  json: {
    fonte: ctx.fonte,
    job: ctx.job,
    disparo: ctx.disparo,
    origem_janela: ctx.origem_janela,
    janela_inicio: ctx.janela_inicio,
    janela_fim: ctx.janela_fim,
    execucao_chave: ctx.execucao_chave,
    api_versao: ctx.api_versao,
    contrato_versao: ctx.contrato_versao,
    contrato_sha256: ctx.contrato_sha256,
    workflow_id: ctx.workflow_id,
    execucao_externa_id: ctx.execucao_externa_id,
    iniciada_em: ctx.iniciada_em,
    contas_tentadas: ctx.contas_tentadas,
    total_contas: ctx.total_contas,
    customer_id: ctx.customer_id,
    conta_ordinal: ctx.conta_ordinal,
    pagina: ctx.pagina,
    acumulado: ctx.acumulado,
    estado_conta: 'falhou',
    erro_classe: classe,
    erro_codigo: codigo === null ? null : String(codigo),
    retry_recomendado: retryRecomendado,
    tem_proxima_pagina: false,
    proximo_page_token: '',
  },
}];
"""

JS_FECHAR = r"""
// ── FECHAMENTO DA EXECUCAO ──────────────────────────────────────────────────
//
// ⚠️ O acumulado vem de `$input.all()` — a saida `done` do laco, que traz TODOS
// os itens que reentraram nele. Nao de `$('No dentro do laco').all()`, que
// devolveria so a ultima rodada e faria o recibo declarar o ultimo lote como se
// fosse a execucao inteira.
const itens = $input.all().map((i) => i.json);
if (itens.length === 0) {
  throw new Error('FECHAMENTO_SEM_ITEM: o laco terminou sem devolver conta nenhuma');
}
const base = itens[0];

let aceitas = 0; let preteridas = 0; let rejeitadas = 0;
let lidas = 0; let projetadas = 0; let paginas = 0;
const contasAceitas = [];
const contasRecusadas = [];
const projecoes = [];

for (const it of itens) {
  const a = it.acumulado || {};
  aceitas += Number(a.linhas_aceitas || 0);
  preteridas += Number(a.linhas_preteridas || 0);
  rejeitadas += Number(a.linhas_rejeitadas || 0);
  lidas += Number(a.linhas_lidas || 0);
  projetadas += Number(a.projecao_linhas || 0);
  paginas += Number(a.paginas || 0);
  for (const p of (a.projecoes || [])) projecoes.push(p);

  if (it.estado_conta === 'falhou') {
    contasRecusadas.push({
      customer_id: String(it.customer_id),
      classe: it.erro_classe || 'DESCONHECIDA',
      codigo: it.erro_codigo === undefined ? null : it.erro_codigo,
    });
  } else {
    contasAceitas.push(String(it.customer_id));
  }
}

// Uma falha de conta nao pode virar vazio nem sumir. Ela decide o desfecho.
let resultado;
let motivo = null;
if (contasRecusadas.length === 0 && rejeitadas === 0) {
  resultado = 'ok';
} else if (contasRecusadas.length === 0) {
  resultado = aceitas > 0 ? 'parcial' : 'falhou';
  motivo = `${rejeitadas} linhas rejeitadas semanticamente; nenhuma recusa pode virar ok`;
} else if (contasAceitas.length > 0 || aceitas > 0) {
  resultado = 'parcial';
  motivo = `${contasRecusadas.length} de ${itens.length} contas falharam; ${rejeitadas} linhas rejeitadas: `
    + contasRecusadas.map((c) => `${c.customer_id}/${c.classe}`).join(', ');
} else {
  resultado = 'falhou';
  motivo = `todas as ${contasRecusadas.length} contas falharam; ${rejeitadas} linhas rejeitadas: `
    + contasRecusadas.map((c) => `${c.customer_id}/${c.classe}`).join(', ');
}

// `falhou` significa "nada aproveitavel". Se linha verde existe, o desfecho
// honesto e parcial — e o schema do banco recusaria o contrario.
if (resultado === 'falhou' && aceitas > 0) {
  resultado = 'parcial';
  motivo = `linhas aceitas apesar de contas falhas: ${motivo}`;
}

let projecaoEstado = 'nao_solicitada';
if (projecoes.length > 0) {
  if (projecoes.includes('falhou')) projecaoEstado = 'falhou';
  else if (projecoes.includes('recusada_ambigua') || projecoes.includes('parcial')) projecaoEstado = 'parcial';
  else if (projecoes.includes('indisponivel')) projecaoEstado = 'indisponivel';
  else projecaoEstado = 'aplicada';
}
if (projecaoEstado === 'falhou' && projetadas > 0) projecaoEstado = 'parcial';
if (projetadas === 0 && (projecaoEstado === 'aplicada' || projecaoEstado === 'parcial')) {
  projecaoEstado = projecoes.includes('recusada_ambigua') ? 'recusada_ambigua' : projecaoEstado;
}

const agora = new Date().toISOString();
const documento = {
  chave_idempotencia: `${base.execucao_chave}|0`,
  execucao_chave: base.execucao_chave,
  fonte: base.fonte,
  job: base.job,
  disparo: base.disparo,
  workflow_id: base.workflow_id,
  execucao_externa_id: base.execucao_externa_id,
  api_versao: base.api_versao,
  contrato_versao: base.contrato_versao,
  contrato_sha256: base.contrato_sha256,
  tipo_lote: 'fechamento',
  lote_ordinal: 0,
  origem_janela: base.origem_janela,
  janela_inicio: base.janela_inicio,
  janela_fim: base.janela_fim,
  iniciada_em: base.iniciada_em,
  encerrada_em: agora,
  duracao_ms: Math.max(0, Date.parse(agora) - Date.parse(base.iniciada_em)),
  batimento_em: agora,
  resultado,
  motivo,
  escopo: `${contasAceitas.length} contas lidas, ${contasRecusadas.length} recusadas`,
  contas_tentadas: base.contas_tentadas || [],
  contas_aceitas: contasAceitas,
  contas_recusadas: contasRecusadas,
  linhas_aceitas: aceitas,
  linhas_preteridas: preteridas,
  linhas_rejeitadas: rejeitadas,
  projecao_estado: projecaoEstado,
  projecao_linhas: projetadas,
  linhas: [],
};

return [{
  json: {
    documento,
    resumo: {
      job: base.job,
      execucao_chave: base.execucao_chave,
      janela: base.janela_inicio,
      contas_lidas: contasAceitas.length,
      contas_recusadas: contasRecusadas.length,
      paginas,
      linhas_lidas: lidas,
      linhas_aceitas: aceitas,
      linhas_preteridas: preteridas,
      linhas_rejeitadas: rejeitadas,
      projecao_estado: projecaoEstado,
      projecao_linhas: projetadas,
      resultado,
      motivo,
    },
  },
}];
"""

JS_BATIMENTO = r"""
// ── BATIMENTO E SAUDE ───────────────────────────────────────────────────────
//
// A leitura de volta prova que o recibo POUSOU. Sem ela, o fluxo declararia
// sucesso com base na propria memoria — o autoatestado que o contrato de saude
// proibe (docs/contracts/HEALTH-DEADMAN-GOOGLE-INTELLIGENCE.md).
//
// ⚠️ SAUDAVEL nunca sai so de tentativa ou batimento. Ausencia de leitura de
// volta e INDETERMINADO, nao sucesso.
const fechamento = $('Fechar execucao').first().json;
const resumo = fechamento.resumo;

const linhas = $input.all().map((i) => i.json).filter((l) => l && l.execucao_chave);
const lido = linhas.find((l) => String(l.execucao_chave) === String(resumo.execucao_chave)) || null;

let estado;
let alerta = false;
let motivoAlerta = null;

if (lido === null) {
  estado = 'INDETERMINADO';
  alerta = true;
  motivoAlerta = 'o recibo de fechamento nao foi encontrado na releitura';
} else if (String(lido.resultado) === 'falhou') {
  estado = 'FALHOU';
  alerta = true;
  motivoAlerta = String(lido.motivo || 'falha sem motivo declarado');
} else if (Number(lido.linhas_aceitas) !== Number(resumo.linhas_aceitas)) {
  estado = 'INDETERMINADO';
  alerta = true;
  motivoAlerta = `releitura diverge: banco ${lido.linhas_aceitas},`
    + ` fluxo ${resumo.linhas_aceitas}`;
} else if (String(lido.resultado) === 'parcial') {
  estado = 'PARCIAL';
  alerta = true;
  motivoAlerta = String(lido.motivo || 'parcial sem motivo declarado');
} else {
  // Vazio confirmado NAO e alerta: a leitura foi boa e nao havia linha.
  estado = 'SAUDAVEL';
  alerta = false;
}

return [{
  json: {
    ...resumo,
    estado_saude: estado,
    alerta,
    motivo_alerta: motivoAlerta,
    batimento_em: lido === null ? null : lido.batimento_em,
    releitura_encontrada: lido !== null,
    vazio_confirmado: Number(resumo.linhas_lidas) === 0 && String(resumo.resultado) === 'ok',
  },
}];
"""

# ────────────────────────────────────────────────────────────── construcao ──


def _id(nome: str) -> str:
    """Id estavel do no: o mesmo nome gera sempre o mesmo id, sem sorteio."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"volc:n8n:gads-dia:{nome}"))


def _no(nome: str, tipo: str, tv: Any, pos: list[int], parametros: dict, **extra) -> dict:
    no: dict[str, Any] = {
        "parameters": parametros,
        "id": _id(nome),
        "name": nome,
        "type": tipo,
        "typeVersion": tv,
        "position": pos,
    }
    no.update(extra)
    return no


def _code(nome: str, pos: list[int], js: str) -> dict:
    return _no(nome, "n8n-nodes-base.code", 2, pos,
               {"mode": "runOnceForAllItems", "jsCode": js.strip() + "\n"})


def _se_booleano(nome: str, pos: list[int], expressao: str) -> dict:
    return _no(nome, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "",
                        "typeValidation": "loose", "version": 2},
            "conditions": [{
                "id": _id(nome + ":cond"),
                "leftValue": expressao,
                "rightValue": "",
                "operator": {"type": "boolean", "operation": "true", "singleValue": True},
            }],
            "combinator": "and",
        },
        "looseTypeValidation": True,
        "options": {},
    })


def construir(papel: str, contrato_sha: str) -> dict:
    d0 = papel == "d0"
    job = "gads_dia_d0" if d0 else "gads_dia_d1"
    modo = "D0" if d0 else "D-1"
    cron = "0 6,12,18,23 * * *" if d0 else "0 6 * * *"
    passos = "06,12,18,23" if d0 else "06"
    nome = (
        "VOLC · Google Ads campanha-dia · D0 (hoje)" if d0
        else "VOLC · Google Ads campanha-dia · D-1 (ontem fechado)"
    )

    config = [
        ("SUPABASE_URL", SUPABASE),
        ("GOOGLEADS_BASE", GOOGLEADS_BASE),
        ("GOOGLEADS_API_VERSION", API_VERSION),
        ("JOB", job),
        ("JANELA_MODO", modo),
        ("PASSOS", passos),
        ("PASSO_FORCADO", ""),
        ("TZ", "America/Sao_Paulo"),
        ("PAGE_SIZE", "1000"),
        ("MAX_PAGINAS", "50"),
        # Vazio de proposito: preencher no n8n antes de ativar. Numero de MCC
        # nao e segredo, mas tambem nao e constante de repositorio.
        ("LOGIN_CUSTOMER_ID", ""),
        # Vazio = todas as contas do inventario. O canario preenche com UMA.
        ("CONTAS_PERMITIDAS", ""),
        ("CONTRATO_VERSAO", CONTRATO_VERSAO),
        ("CONTRATO_SHA256", contrato_sha),
        ("GAQL_CAMPOS", ",".join(GAQL_CAMPOS)),
    ]

    nos = [
        _no("Agenda", "n8n-nodes-base.scheduleTrigger", 1.2, [-660, -120],
            {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}}),
        _no("Executar manualmente", "n8n-nodes-base.manualTrigger", 1, [-660, 60], {}),
        _no("Config", "n8n-nodes-base.set", 3.4, [-440, -20], {
            "assignments": {"assignments": [
                {"id": f"c{i}", "name": k, "type": "string", "value": v}
                for i, (k, v) in enumerate(config, start=1)
            ]},
            "options": {},
        }),
        _code("Identidade da execucao", [-220, -20], JS_IDENTIDADE),
        _no("Contas autorizadas", "n8n-nodes-base.httpRequest", 4.2, [0, -20], {
            "url": "={{ $json.url_contas }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Accept", "value": "application/json"},
            ]},
            "options": {"timeout": 30000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000,
            alwaysOutputData=True),
        _code("Selecionar contas", [220, -20], JS_SELECIONAR_CONTAS),
        _no("Campanhas conhecidas", "n8n-nodes-base.httpRequest", 4.2, [440, -20], {
            "url": "={{ $json.url_campanhas }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Accept", "value": "application/json"},
            ]},
            "options": {"timeout": 60000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000,
            alwaysOutputData=True),
        _code("Identidade VOLC por conta", [660, -20], JS_MAPA_IDENTIDADE),
        # ⚠️ batchSize 1: ver o comentario de "Pagina: preparar pedido".
        _no("Lote de contas", "n8n-nodes-base.splitInBatches", 3, [880, -20],
            {"batchSize": 1, "options": {}}),
        _code("Pagina: preparar pedido", [1100, 120], JS_PREPARAR_PAGINA),
        _no("Google Ads: search", "n8n-nodes-base.httpRequest", 4.2, [1320, 120], {
            "method": "POST",
            "url": "={{ $json.url_google }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "googleAdsOAuth2Api",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Accept", "value": "application/json"},
                # ⚠️ OAuth e developer-token saem da credencial Google Ads.
                # n8n não expõe $credentials em expressões de workflow; portanto
                # o JSON nunca tenta ler segredo para montar header manual.
                {"name": "login-customer-id", "value": "={{ $json.login_customer_id }}"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ query: $json.gaql, pageSize: $json.page_size,"
                        " pageToken: $json.page_token }) }}",
            "options": {"timeout": 120000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_GOOGLEADS, retryOnFail=True, maxTries=3, waitBetweenTries=5000,
            onError="continueErrorOutput"),
        # ⚠️ OS DOIS MERGES EXISTEM POR UM DEFEITO MEDIDO, nao por gosto.
        # A primeira versao lia o contexto com `$('Pagina: preparar pedido')`
        # dentro do laco, e o simulador derrubou: `$()` resolve pelo INDICE DA
        # RODADA do no que pergunta. Uma conta que falha faz o pedido rodar mais
        # vezes que a normalizacao, e a partir dali cada iteracao lia o contexto
        # de OUTRA conta — silenciosamente. `combineByPosition` casa a resposta
        # com o contexto DA MESMA iteracao, sem depender de indice nenhum.
        _no("Juntar contexto e resposta", "n8n-nodes-base.merge", 3.2, [1450, 40],
            {"mode": "combine", "combineBy": "combineByPosition", "options": {}}),
        _no("Juntar contexto e erro", "n8n-nodes-base.merge", 3.2, [1450, 320],
            {"mode": "combine", "combineBy": "combineByPosition", "options": {}}),
        _code("Pagina: normalizar", [1650, 40], JS_NORMALIZAR),
        _code("Validar semanticamente", [1850, 40], JS_VALIDAR),
        _no("RPC: ingerir lote", "n8n-nodes-base.httpRequest", 4.2, [2050, 40], {
            "method": "POST",
            "url": f"{SUPABASE}/rest/v1/rpc/volc_registrar_gads_campanha_dia",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Accept", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ documento: $json.documento }) }}",
            "options": {"timeout": 120000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000),
        _code("Reconciliar lote", [2250, 40], JS_RECONCILIAR),
        _se_booleano("Tem proxima pagina?", [2450, 40], "={{ $json.tem_proxima_pagina }}"),
        _code("Classificar erro do Google", [1650, 320], JS_CLASSIFICAR_ERRO),
        _code("Fechar execucao", [1100, -220], JS_FECHAR),
        _no("Limite do fechamento", "n8n-nodes-base.limit", 1, [1320, -220],
            {"maxItems": 1}),
        _no("RPC: fechar recibo", "n8n-nodes-base.httpRequest", 4.2, [1540, -220], {
            "method": "POST",
            "url": f"{SUPABASE}/rest/v1/rpc/volc_registrar_gads_campanha_dia",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Accept", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ documento: $json.documento }) }}",
            "options": {"timeout": 60000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000),
        _no("Releitura do recibo", "n8n-nodes-base.httpRequest", 4.2, [1760, -220], {
            "url": "={{ $node[\"Config\"].json[\"SUPABASE_URL\"] "
                   "+ '/rest/v1/trafego_coleta_execucao_saude?select=*&execucao_chave=eq.' "
                   "+ $node[\"Fechar execucao\"].json[\"resumo\"][\"execucao_chave\"] }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Accept", "value": "application/json"},
            ]},
            "options": {"timeout": 30000, "response": {"response": {"neverError": False}}},
        }, credentials=CRED_SUPABASE, retryOnFail=True, maxTries=3, waitBetweenTries=3000),
        _code("Batimento e saude", [1980, -220], JS_BATIMENTO),
        _se_booleano("Falha real?", [2200, -220], "={{ $json.alerta }}"),
        _no("Alerta de rotina parada", "n8n-nodes-base.httpRequest", 4.2, [2420, -220], {
            "method": "POST",
            "url": f"{SUPABASE}/rest/v1/system_settings",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendQuery": True,
            "queryParameters": {"parameters": [{"name": "on_conflict", "value": "key"}]},
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Prefer", "value": "resolution=merge-duplicates,return=minimal"},
                {"name": "Content-Type", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ key: 'gads_dia_' + $json.job + '_ultimo_alerta',"
                        " value: $json.execucao_chave + ' | ' + $json.estado_saude + ' | '"
                        " + ($json.motivo_alerta || 'sem motivo declarado'),"
                        " updated_at: new Date().toISOString() }) }}",
            "options": {"timeout": 30000},
        }, credentials=CRED_SUPABASE),
        _no("Sticky Note", "n8n-nodes-base.stickyNote", 1, [-660, -420], {
            "width": 900, "height": 260,
            "content": (
                f"## {nome}\n\n"
                "**INATIVO por contrato.** A agenda so pode ser ligada depois do pacote de "
                "autorizacao (docs/closure/hermes-p10-t16-n8n-ledger-v12-v1/"
                "AUTORIZACAO-ATIVACAO.md).\n\n"
                "Gerado por `n8n/gerar_flows_gads_ledger_v12.py`. **Nao edite este JSON a mao** "
                "— edite o gerador e regere, senao D0 e D-1 divergem na primeira correcao.\n\n"
                "Destino unico: `database.agenciavolc.com.br`. Somente leitura no Google Ads "
                "(zero `mutate`). Ausencia permanece NULL; zero medido permanece zero.\n\n"
                "Antes de ativar: preencher `LOGIN_CUSTOMER_ID`, apontar a credencial "
                "`VOLC Google Ads`, e rodar o canario com `CONTAS_PERMITIDAS` = uma conta."
            ),
        }),
    ]

    conexoes = {
        "Agenda": {"main": [[{"node": "Config", "type": "main", "index": 0}]]},
        "Executar manualmente": {"main": [[{"node": "Config", "type": "main", "index": 0}]]},
        "Config": {"main": [[{"node": "Identidade da execucao", "type": "main", "index": 0}]]},
        "Identidade da execucao": {
            "main": [[{"node": "Contas autorizadas", "type": "main", "index": 0}]]},
        "Contas autorizadas": {
            "main": [[{"node": "Selecionar contas", "type": "main", "index": 0}]]},
        "Selecionar contas": {
            "main": [[{"node": "Campanhas conhecidas", "type": "main", "index": 0}]]},
        "Campanhas conhecidas": {
            "main": [[{"node": "Identidade VOLC por conta", "type": "main", "index": 0}]]},
        "Identidade VOLC por conta": {
            "main": [[{"node": "Lote de contas", "type": "main", "index": 0}]]},
        # main[0] = done (fim do laco) · main[1] = lote atual
        "Lote de contas": {"main": [
            [{"node": "Fechar execucao", "type": "main", "index": 0}],
            [{"node": "Pagina: preparar pedido", "type": "main", "index": 0}],
        ]},
        # O contexto da iteracao segue para o pedido E para os dois merges; a
        # resposta (ou o erro) casa com ele por posicao, na mesma iteracao.
        "Pagina: preparar pedido": {"main": [[
            {"node": "Google Ads: search", "type": "main", "index": 0},
            {"node": "Juntar contexto e resposta", "type": "main", "index": 1},
            {"node": "Juntar contexto e erro", "type": "main", "index": 1},
        ]]},
        # main[0] = sucesso · main[1] = saida de erro (continueErrorOutput)
        "Google Ads: search": {"main": [
            [{"node": "Juntar contexto e resposta", "type": "main", "index": 0}],
            [{"node": "Juntar contexto e erro", "type": "main", "index": 0}],
        ]},
        "Juntar contexto e resposta": {
            "main": [[{"node": "Pagina: normalizar", "type": "main", "index": 0}]]},
        "Juntar contexto e erro": {
            "main": [[{"node": "Classificar erro do Google", "type": "main", "index": 0}]]},
        "Pagina: normalizar": {
            "main": [[{"node": "Validar semanticamente", "type": "main", "index": 0}]]},
        "Validar semanticamente": {
            "main": [[{"node": "RPC: ingerir lote", "type": "main", "index": 0}]]},
        "RPC: ingerir lote": {
            "main": [[{"node": "Reconciliar lote", "type": "main", "index": 0}]]},
        "Reconciliar lote": {
            "main": [[{"node": "Tem proxima pagina?", "type": "main", "index": 0}]]},
        # true = mais uma pagina da MESMA conta · false = conta encerrada
        "Tem proxima pagina?": {"main": [
            [{"node": "Pagina: preparar pedido", "type": "main", "index": 0}],
            [{"node": "Lote de contas", "type": "main", "index": 0}],
        ]},
        "Classificar erro do Google": {
            "main": [[{"node": "Lote de contas", "type": "main", "index": 0}]]},
        "Fechar execucao": {
            "main": [[{"node": "Limite do fechamento", "type": "main", "index": 0}]]},
        "Limite do fechamento": {
            "main": [[{"node": "RPC: fechar recibo", "type": "main", "index": 0}]]},
        "RPC: fechar recibo": {
            "main": [[{"node": "Releitura do recibo", "type": "main", "index": 0}]]},
        "Releitura do recibo": {
            "main": [[{"node": "Batimento e saude", "type": "main", "index": 0}]]},
        "Batimento e saude": {
            "main": [[{"node": "Falha real?", "type": "main", "index": 0}]]},
        "Falha real?": {"main": [
            [{"node": "Alerta de rotina parada", "type": "main", "index": 0}],
            [],
        ]},
    }

    return {
        "name": nome,
        "nodes": nos,
        "connections": conexoes,
        "active": False,
        "settings": {
            "executionOrder": "v1",
            "timezone": "America/Sao_Paulo",
            "saveDataErrorExecution": "all",
            "saveDataSuccessExecution": "all",
            "saveExecutionProgress": True,
            "saveManualExecutions": True,
            "executionTimeout": 3600,
        },
        "pinData": {},
        "meta": {
            "volc": {
                "gerador": "n8n/gerar_flows_gads_ledger_v12.py",
                "contrato": CONTRATO_VERSAO,
                "contrato_sha256": contrato_sha,
                "rpc": "volc_registrar_gads_campanha_dia",
                "migration": "supabase/migrations/v12_04_gads_fato_canonico_dia.sql",
                "papel": modo,
                "estado": "INATIVO — depende do pacote de autorizacao",
            }
        },
    }


def contrato_sha256() -> str:
    """Impressao do CONTRATO, e nao do arquivo: campos GAQL + versao + RPC.

    Ela viaja em todo recibo. Mudar a lista de campos muda o hash, e o ledger
    passa a distinguir leituras de contratos diferentes sem depender de memoria
    de ninguem.
    """
    corpo = json.dumps({
        "versao": CONTRATO_VERSAO,
        "api": API_VERSION,
        "campos": GAQL_CAMPOS,
        "rpc": "volc_registrar_gads_campanha_dia",
        "destino": SUPABASE,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()


ALVOS = {
    "d0": "volc_gads_campanha_dia_d0.json",
    "d1": "volc_gads_campanha_dia_d1.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="não escreve; falha se o arquivo em disco divergir")
    args = parser.parse_args()

    sha = contrato_sha256()
    divergiu = []
    for papel, arquivo in ALVOS.items():
        destino = RAIZ / arquivo
        texto = json.dumps(construir(papel, sha), ensure_ascii=False, indent=2) + "\n"
        if args.check:
            atual = destino.read_text(encoding="utf-8") if destino.exists() else ""
            if atual != texto:
                divergiu.append(arquivo)
        else:
            destino.write_text(texto, encoding="utf-8")
            print(f"gerado {destino.relative_to(RAIZ.parent)}")

    if args.check:
        if divergiu:
            print("FALHOU · o JSON em disco não é o que o gerador produz: "
                  + ", ".join(divergiu), file=sys.stderr)
            return 1
        print(f"ok · os {len(ALVOS)} workflows em disco batem com o gerador "
              f"(contrato {sha[:12]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
