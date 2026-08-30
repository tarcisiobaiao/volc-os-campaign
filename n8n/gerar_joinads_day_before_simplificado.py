#!/usr/bin/env python3
"""Gera a versão simplificada do day-before: data fixa (D-1), sem 'Monta janelas'."""
import json, os

SUPA = "https://database.agenciavolc.com.br"
SUPA_CRED = {"supabaseApi": {"id": "3lSRuywq3fwQ3z3I", "name": "VOLC Oficial"}}
TOKEN_HEADER = "Bearer 102704|1Er7FQ1rnGrzsEPrsvbVHpE3RCCO2VJo88U3iyNx35fc125c"

# ── helper compartilhado ────────────────────────────────────────────────────
HELPERS = r"""
// A data alvo vem do Config1, calculada UMA vez. E exatamente a mesma que os
// nos de HTTP pediram -- por isso os dois leem dali em vez de recalcular $now
// cada um por si (duas chamadas a $now podem cair em dias diferentes se a
// execucao atravessar a meia-noite).
const dataAlvo = String(cfg.DATA_ALVO || '').trim();
if (!/^\d{4}-\d{2}-\d{2}$/.test(dataAlvo)) {
  throw new Error(`DATA_ALVO invalida no Config1: ${JSON.stringify(cfg.DATA_ALVO)}`);
}

function parseData(bruto) {
  if (bruto == null) return { date: null, ambigua: false, intervalo: false };
  const s = String(bruto).trim();

  // CINTO DE SEGURANCA. Se o request cobrir mais de um dia, a Join devolve UMA
  // linha agregada com o campo date como rotulo de intervalo:
  //     "09/08/2026 a 10/08/2026"
  // Uma regex ancorada so no inicio casaria o prefixo "09/08/2026" e gravaria o
  // total de dois dias como se fosse do dia 09 -- errado, e calado. Contamos
  // quantas datas existem na string: mais de uma = agregado, descarta.
  const tokens = s.match(/\d{1,4}[\/\-]\d{1,2}[\/\-]\d{1,4}/g) || [];
  if (tokens.length > 1) return { date: null, ambigua: false, intervalo: true };

  // report_type=Analytical devolve ISO; Synthetic devolve DD/MM/AAAA.
  const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return { date: `${iso[1]}-${iso[2]}-${iso[3]}`, ambigua: false, intervalo: false };

  const m = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})/);
  if (!m) return { date: null, ambigua: false, intervalo: false };

  const a = m[1].padStart(2, '0');
  const b = m[2].padStart(2, '0');
  const ano = m[3];
  const dmy = `${ano}-${b}-${a}`;   // a = dia,  b = mes
  const mdy = `${ano}-${a}-${b}`;   // a = mes,  b = dia

  // So existe UM dia possivel: o que pedimos. Isso resolve a ambiguidade de
  // "10/08/2026" sem chute -- so uma das duas leituras bate com DATA_ALVO.
  const okDmy = dmy === dataAlvo;
  const okMdy = mdy === dataAlvo;

  if (okDmy && !okMdy) return { date: dmy, ambigua: false, intervalo: false };
  if (okMdy && !okDmy) return { date: mdy, ambigua: false, intervalo: false };
  if (okDmy && okMdy)  return { date: dataAlvo, ambigua: false, intervalo: false };

  // Nenhuma leitura bate com o dia pedido: a API devolveu outra data.
  return { date: null, ambigua: true, intervalo: false };
}

function limpaDominio(v) {
  return String(v || '')
    .trim().toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .replace(/\/.*$/, '');
}

function emLotes(linhas, tamanho, extras) {
  if (linhas.length === 0) {
    return [{ json: { rows: [], totalLinhas: 0, lote: 0, totalLotes: 0, ...extras } }];
  }
  const lotes = [];
  for (let i = 0; i < linhas.length; i += tamanho) lotes.push(linhas.slice(i, i + tamanho));
  return lotes.map((rows, idx) => ({
    json: { rows, totalLinhas: linhas.length, lote: idx + 1, totalLotes: lotes.length, ...extras },
  }));
}
"""

JS_EARNINGS = r"""// /earnings  ->  daily_project_metrics   (dia fixo: D-1)
//
// O VOLC O.S. grava SEMPRE o bruto: quem aplica o revshare de 10% e o trigger
// do banco, a partir de projects.revshare.
//
// A API devolve OS DOIS valores -- `revenue` (bruto) e `revenue_client`
// (liquido) -- apesar de a doc so citar o segundo. Confirmado em dado real:
// ecpm 1.25 vs ecpm_client 1.13 = 0.904, que e o revshare. Usamos `revenue`.
// O EARNINGS_IS_NET so governa o fallback, caso um dia venha so o liquido.
const cfg = $('Config1').first().json;

const revshare  = Number(cfg.JOIN_REVSHARE) || 0;
const ehLiquido = String(cfg.EARNINGS_IS_NET).toLowerCase() === 'true';
const batchSize = Math.max(1, Number(cfg.BATCH_SIZE) || 500);
__HELPERS__

const porChave = new Map();
let descartadas = 0;
let foraDoDia = 0;
let intervalos = 0;
let reconstruidas = 0;

for (const item of $input.all()) {
  const linhas = Array.isArray(item.json?.data) ? item.json.data : [];
  for (const r of linhas) {
    const { date, ambigua, intervalo } = parseData(r.date);
    if (intervalo) { intervalos++; continue; }
    if (ambigua)   { foraDoDia++; continue; }
    if (!date)     { descartadas++; continue; }

    const dominio = limpaDominio(r.domain);
    if (!dominio) { descartadas++; continue; }

    let receita = Number(r.revenue);
    if (!Number.isFinite(receita)) {
      const liquido = Number(r.revenue_client);
      if (!Number.isFinite(liquido)) { descartadas++; continue; }
      receita = (ehLiquido && revshare > 0 && revshare < 1)
        ? liquido / (1 - revshare)
        : liquido;
      reconstruidas++;
    }
    receita = Math.round(receita * 1e6) / 1e6;

    // Deduplica pela MESMA chave do on_conflict. Um POST em lote com a chave
    // repetida faz o Postgres estourar "cannot affect row a second time".
    porChave.set(`${date}|${dominio}`, { date, url_projeto: dominio, revenue: receita });
  }
}

return emLotes([...porChave.values()], batchSize, {
  dataAlvo, descartadas, foraDoDia, intervalos, reconstruidas,
});
"""

JS_KEYVALUE = r"""// /key-value  ->  joinads_metrics   (dia fixo: D-1)
//
// Usamos `earnings` (BRUTO), nao `earnings_client`: o revshare e aplicado pelo
// trigger do banco. Gravar liquido aqui descontaria duas vezes.
const cfg = $('Config1').first().json;

const batchSize     = Math.max(1, Number(cfg.BATCH_SIZE) || 500);
const dominioCfg    = String(cfg.JOIN_DOMAIN || '').trim().toLowerCase().replace(/^www\./, '');
const chaveEsperada = String(cfg.CUSTOM_KEY || 'utm_campaign').trim();
__HELPERS__

function num(v) {
  if (v == null) return 0;
  const n = Number(String(v).replace(/\s/g, '').replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
}

const porChave = new Map();
let descartadas = 0;
let foraDoDia = 0;
let intervalos = 0;
let chaveTrocada = 0;
const chavesVistas = {};

for (const item of $input.all()) {
  const linhas = Array.isArray(item.json?.data) ? item.json.data : [];
  for (const r of linhas) {

    // ══════════════════════════════════════════════════════════════════════
    // FILTRO: so passa linha cuja custom_key seja EXATAMENTE a pedida.
    //
    // Nao da para confiar no parametro custom_key do request: quando nao ha
    // dado para a chave pedida, a API IGNORA o parametro e devolve outra, sem
    // avisar. Verificado em dado real -- pedimos utm_campaign e voltou
    // land_uri, cujo valor "/" chegou a entrar em utm_campaign_value como se
    // fosse id de campanha.
    //
    // O filtro tem que ser aqui e nao num no Filter do n8n: a resposta inteira
    // vem como UM item com um array `data` dentro, e o no Filter atua sobre
    // itens, nao sobre elementos de array dentro de um item.
    // ══════════════════════════════════════════════════════════════════════
    const chaveVinda = String(r.custom_key ?? r.custon_key ?? '').trim();
    chavesVistas[chaveVinda || '(sem custom_key)'] =
      (chavesVistas[chaveVinda || '(sem custom_key)'] || 0) + 1;
    if (chaveVinda !== chaveEsperada) { chaveTrocada++; continue; }

    const { date, ambigua, intervalo } = parseData(r.date);
    if (intervalo) { intervalos++; continue; }
    if (ambigua)   { foraDoDia++; continue; }
    if (!date)     { descartadas++; continue; }

    // A doc escreve "custon_value" (typo deles); a API real devolve
    // "custom_value". Aceitamos as duas grafias.
    const campanha = String(r.custom_value ?? r.custon_value ?? '').trim();
    if (!campanha || campanha === 'null' || campanha === '{{campaign.id}}') {
      descartadas++; continue;
    }

    const dominio = limpaDominio(r.name) || dominioCfg;
    const chave = `${date}|${campanha}|${dominio}`;

    const acc = porChave.get(chave) || {
      date, utm_campaign_value: campanha, joinads_domain: dominio,
      revenue: 0, impressions: 0, clicks: 0, viewableAcc: 0,
    };

    // report_type=Analytical devolve uma linha por bloco de anuncio. Somando
    // aqui, Analytical e Synthetic produzem exatamente o mesmo total.
    acc.revenue     += num(r.earnings);
    acc.impressions += num(r.impressions);
    acc.clicks      += num(r.clicks);
    // a API real devolve `active_view`; a doc chama de `active_view_viewable`
    acc.viewableAcc += num(r.active_view ?? r.active_view_viewable) * num(r.impressions);

    porChave.set(chave, acc);
  }
}

const linhas = [...porChave.values()].map((a) => {
  const imp = a.impressions;
  return {
    date: a.date,
    utm_campaign_value: a.utm_campaign_value,
    joinads_domain: a.joinads_domain,
    revenue: Math.round(a.revenue * 1e6) / 1e6,
    impressions: Math.round(imp),
    clicks: Math.round(a.clicks),
    // CTR e eCPM recalculados do cru: os valores que a API devolve por linha
    // nao sobrevivem a soma de linhas. CTR em PERCENTUAL (igual gam_metrics).
    ctr:  imp > 0 ? Math.round((a.clicks / imp) * 100 * 1e4) / 1e4 : 0,
    ecpm: imp > 0 ? Math.round((a.revenue / imp) * 1000 * 100) / 100 : 0,
    viewable_impressions: imp > 0 ? Math.round((a.viewableAcc / imp) * 100) / 100 : 0,
  };
});

return emLotes(linhas, batchSize, {
  dataAlvo, descartadas, foraDoDia, intervalos, chaveTrocada, chaveEsperada, chavesVistas,
});
"""

JS_RESUMO = r"""// Resumo da execucao. Aparece no log do n8n e vira o corpo gravado em
// system_settings.joinads_last_update.
const cfg = $('Config1').first().json;

function stats(no) {
  try {
    const j = $(no).first().json;
    return {
      linhas: j.totalLinhas ?? 0,
      lotes: j.totalLotes ?? 0,
      descartadas: j.descartadas ?? 0,
      fora_do_dia: j.foraDoDia ?? 0,
      intervalos: j.intervalos ?? 0,
      chave_trocada: j.chaveTrocada ?? 0,
      chaves_vistas: j.chavesVistas ?? undefined,
      reconstruidas: j.reconstruidas ?? undefined,
    };
  } catch (e) {
    return { linhas: 0, lotes: 0, erro: String(e.message || e) };
  }
}

const projeto  = stats('Normaliza earnings1');
const campanha = stats('Normaliza key-value1');

// Cada alerta abaixo significa "o numero que voce esta vendo pode estar errado".
// Nenhum derruba a execucao de proposito: gravamos so o que da para confiar e
// deixamos o rastro do que foi jogado fora.
const alertas = [];

if ((projeto.intervalos || 0) + (campanha.intervalos || 0) > 0) {
  alertas.push(
    'A Join devolveu linha AGREGADA de intervalo (date como "dd/mm/aaaa a dd/mm/aaaa") e ela ' +
    'foi descartada. Isso so acontece se o request cobriu mais de um dia -- confira se ' +
    'start_date e end_date nos nos de HTTP estao os dois em DATA_ALVO.'
  );
}

if ((campanha.chave_trocada || 0) > 0) {
  alertas.push(
    `Filtro de custom_key barrou ${campanha.chave_trocada} linha(s) que nao eram ` +
    `"${cfg.CUSTOM_KEY}". Chaves que a API devolveu: ` +
    `${JSON.stringify(campanha.chaves_vistas || {})}. Isso e o comportamento dela quando nao ha ` +
    'dado para a chave pedida: ignora o parametro e manda outra. Enquanto o site nao tiver ' +
    'trafego com utm_campaign, o eixo de campanha fica vazio -- que e o certo.'
  );
}

if ((projeto.fora_do_dia || 0) + (campanha.fora_do_dia || 0) > 0) {
  alertas.push(
    `A API devolveu linha com data diferente de DATA_ALVO (${cfg.DATA_ALVO}) e ela foi ` +
    'descartada. Pode ser diferenca de timezone no fechamento do dia deles.'
  );
}

return [{
  json: {
    ok: true,
    fonte: 'joinads',
    dominio: cfg.JOIN_DOMAIN,
    data: cfg.DATA_ALVO,
    projeto,
    campanha,
    alertas: alertas.length ? alertas : null,
    executado_em: new Date().toISOString(),
  },
}];
"""


def code(js):
    return {"jsCode": js.replace("__HELPERS__", HELPERS.rstrip())}


DATA_ALVO = ("={{ $json.body?.date || "
             "$now.setZone('America/Sao_Paulo').minus({ days: 1 }).toISODate() }}")

nodes = [
    {"parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 6 * * *"}]}},
     "id": "ec55c02d-062a-4d8e-885a-91e29ff26448", "name": "Schedule Trigger1",
     "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [848, 1088]},

    {"parameters": {}, "id": "0b60c2de-f680-4d8e-b869-99a2417a3e43",
     "name": "When clicking ‘Execute workflow’", "type": "n8n-nodes-base.manualTrigger",
     "typeVersion": 1, "position": [576, 1264]},

    {"parameters": {"httpMethod": "POST", "path": "joinads-day-before", "options": {}},
     "id": "f3847ffb-391e-40b5-bb67-2e687d693f9f", "name": "Webhook - Atualizar agora1",
     "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [848, 1440],
     "webhookId": "joinads-day-before"},

    {"parameters": {"assignments": {"assignments": [
        {"id": "c1", "name": "JOIN_DOMAIN", "type": "string",
         "value": "={{ $json.body?.domain || 'creditoup.com.br' }}"},
        # dia fixo: ontem. O webhook pode pedir outro dia com {"date":"2026-08-05"}
        {"id": "c2", "name": "DATA_ALVO", "type": "string", "value": DATA_ALVO},
        {"id": "c3", "name": "JOIN_REVSHARE", "type": "string", "value": "0.10"},
        {"id": "c4", "name": "EARNINGS_IS_NET", "type": "string", "value": "true"},
        {"id": "c5", "name": "TZ", "type": "string", "value": "America/Sao_Paulo"},
        {"id": "c6", "name": "BATCH_SIZE", "type": "string", "value": "500"},
        {"id": "c7", "name": "CUSTOM_KEY", "type": "string", "value": "utm_campaign"},
    ]}, "options": {}},
     "id": "39bd2c20-e4c0-4a2f-9057-f419815db03f", "name": "Config1",
     "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [1088, 1264]},
]

HDRS = [{"name": "Accept", "value": "application/json"},
        {"name": "Authorization", "value": TOKEN_HEADER}]
DATA_Q = "={{ $('Config1').first().json.DATA_ALVO }}"
DOM_Q = "={{ $('Config1').first().json.JOIN_DOMAIN }}"
HTTP_OPTS = {"response": {"response": {}}, "timeout": 60000}

nodes += [
    {"parameters": {
        "url": "https://office.joinads.me/api/clients-endpoints/earnings",
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "start_date", "value": DATA_Q},
            {"name": "end_date", "value": DATA_Q},
            {"name": "domain", "value": DOM_Q}]},
        "sendHeaders": True, "headerParameters": {"parameters": HDRS},
        "options": HTTP_OPTS},
     "id": "a1968f4f-75bc-4d50-b357-3675179134d7", "name": "Join - GET /earnings1",
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1344, 1136],
     "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 3000,
     "onError": "continueErrorOutput"},

    {"parameters": {
        "url": "https://office.joinads.me/api/clients-endpoints/key-value",
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "start_date", "value": DATA_Q},
            {"name": "end_date", "value": DATA_Q},
            {"name": "domain", "value": DOM_Q},
            {"name": "report_type", "value": "Synthetic"},
            {"name": "custom_key", "value": "={{ $('Config1').first().json.CUSTOM_KEY }}"}]},
        "sendHeaders": True, "headerParameters": {"parameters": HDRS},
        "options": HTTP_OPTS},
     "id": "db1593a4-0182-4117-b512-f2d6fee50391", "name": "Join - GET /key-value1",
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1360, 1456],
     "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 3000,
     "onError": "continueErrorOutput"},

    {"parameters": code(JS_EARNINGS), "id": "02df714d-4404-40ad-9b77-8b69da9990be",
     "name": "Normaliza earnings1", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [1600, 1120]},

    {"parameters": code(JS_KEYVALUE), "id": "baaa43a8-51c5-4dae-99d6-18af43e54dab",
     "name": "Normaliza key-value1", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [1600, 1392]},
]


def cond(nid):
    return {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "",
                    "typeValidation": "loose", "version": 2},
        "conditions": [{"id": nid, "leftValue": "={{ $json.rows.length }}",
                        "rightValue": 0,
                        "operator": {"type": "number", "operation": "gt"}}],
        "combinator": "and"}, "options": {}}


def upsert(nid, nome, tabela, conflito, pos):
    return {"parameters": {
        "method": "POST", "url": f"{SUPA}/rest/v1/{tabela}",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "on_conflict", "value": conflito}]},
        "sendHeaders": True, "headerParameters": {"parameters": [
            {"name": "Prefer", "value": "resolution=merge-duplicates,return=minimal"},
            {"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
        "body": "={{ JSON.stringify($json.rows) }}",
        "options": {"timeout": 120000}},
        "id": nid, "name": nome, "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2, "position": pos, "retryOnFail": True, "maxTries": 3,
        "waitBetweenTries": 2000, "credentials": SUPA_CRED}


def settings_post(nid, nome, chave, valor, pos):
    return {"parameters": {
        "method": "POST", "url": f"{SUPA}/rest/v1/system_settings",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "on_conflict", "value": "key"}]},
        "sendHeaders": True, "headerParameters": {"parameters": [
            {"name": "Prefer", "value": "resolution=merge-duplicates,return=minimal"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": '={\n  "key": "%s",\n  "value": "%s",\n  "updated_at": "%s"\n}'
                    % (chave, valor, "{{ $now.toISO() }}"),
        "options": {}},
        "id": nid, "name": nome, "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2, "position": pos, "credentials": SUPA_CRED}


nodes += [
    {"parameters": cond("p1"), "id": "dead1917-6a8d-4c45-849d-bf0f4916811c",
     "name": "Tem linha? (projeto)1", "type": "n8n-nodes-base.if",
     "typeVersion": 2.2, "position": [1840, 1120]},
    {"parameters": cond("c1"), "id": "7be1c1a8-c6c0-405a-856e-9d8cc8e0db28",
     "name": "Tem linha? (campanha)1", "type": "n8n-nodes-base.if",
     "typeVersion": 2.2, "position": [1840, 1456]},

    upsert("35adb345-5c13-485c-98c0-1c70f70dd051", "Upsert daily_project_metrics1",
           "daily_project_metrics", "date,url_projeto", [2080, 1120]),
    upsert("ae37452a-8823-4809-9fb5-eab8c326aa7f", "Upsert joinads_metrics1",
           "joinads_metrics", "date,utm_campaign_value,joinads_domain", [2080, 1456]),

    {"parameters": {"numberInputs": 2, "options": {}},
     "id": "a0a6f1a0-bdf4-441c-bb53-e1c38a37eb12", "name": "Junta ramos1",
     "type": "n8n-nodes-base.merge", "typeVersion": 3, "position": [2320, 1296]},

    {"parameters": code(JS_RESUMO), "id": "cd7d830a-9d11-48b2-8426-4469247e62f0",
     "name": "Resumo1", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [2544, 1296]},

    settings_post("33eefadc-6d19-45f9-97ce-7f6e8d14fe33", "Marca joinads_last_update1",
                  "joinads_last_update", "{{ $json.executado_em }}", [2752, 1296]),

    settings_post("cb4a947b-6df6-4922-a3eb-5e1d6d6dbce0", "Registra falha1",
                  "joinads_last_error",
                  "{{ $now.toISO() }} | DAY BEFORE | "
                  "{{ JSON.stringify($json.error ?? $json).slice(0, 400) }}",
                  [1840, 1776]),
]


def m(*destinos):
    return {"main": [[{"node": d, "type": "main", "index": i} for d, i in destinos]]}


conns = {
    "Schedule Trigger1": m(("Config1", 0)),
    "When clicking ‘Execute workflow’": m(("Config1", 0)),
    "Webhook - Atualizar agora1": m(("Config1", 0)),
    "Config1": m(("Join - GET /earnings1", 0), ("Join - GET /key-value1", 0)),
    "Join - GET /earnings1": {"main": [
        [{"node": "Normaliza earnings1", "type": "main", "index": 0}],
        [{"node": "Registra falha1", "type": "main", "index": 0}]]},
    "Join - GET /key-value1": {"main": [
        [{"node": "Normaliza key-value1", "type": "main", "index": 0}],
        [{"node": "Registra falha1", "type": "main", "index": 0}]]},
    "Normaliza earnings1": m(("Tem linha? (projeto)1", 0)),
    "Normaliza key-value1": m(("Tem linha? (campanha)1", 0)),
    "Tem linha? (projeto)1": {"main": [
        [{"node": "Upsert daily_project_metrics1", "type": "main", "index": 0}],
        [{"node": "Junta ramos1", "type": "main", "index": 0}]]},
    "Tem linha? (campanha)1": {"main": [
        [{"node": "Upsert joinads_metrics1", "type": "main", "index": 0}],
        [{"node": "Junta ramos1", "type": "main", "index": 1}]]},
    "Upsert daily_project_metrics1": m(("Junta ramos1", 0)),
    "Upsert joinads_metrics1": {"main": [[{"node": "Junta ramos1", "type": "main", "index": 1}]]},
    "Junta ramos1": m(("Resumo1", 0)),
    "Resumo1": m(("Marca joinads_last_update1", 0)),
}

wf = {"name": "JOIN ADS - REPORT - DAY BEFORE", "nodes": nodes, "connections": conns,
      "settings": {"executionOrder": "v1"}, "pinData": {},
      "meta": {"instanceId": "56064576fd4c52e94380d8455de8466e1090116bf11be158a94d8489bb3c9993"}}

destino = "/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/n8n/joinads_day_before_simplificado.json"
with open(destino, "w", encoding="utf-8") as fh:
    json.dump(wf, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
print(f"ok {destino}  ({len(nodes)} nós)")
