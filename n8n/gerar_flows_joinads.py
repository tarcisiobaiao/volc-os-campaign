#!/usr/bin/env python3
"""Gera os dois flows n8n da Join Ads a partir de um template unico."""
import json, os

SUPABASE = "https://database.agenciavolc.com.br"
SUPA_CRED = {"supabaseApi": {"id": "3lSRuywq3fwQ3z3I", "name": "VOLC Oficial"}}
JOIN_CRED = {"httpHeaderAuth": {"id": "REPLACE_ME", "name": "JoinAds - Bearer Token"}}
DOMINIO_PADRAO = "SEU-DOMINIO-MI.com.br"

# ─────────────────────────────────────────────────────────── code nodes ──

JS_JANELAS = r"""// Emite UMA JANELA POR DIA (start_date == end_date).
//
//   OFFSET_DAYS   de quantos dias atras a janela TERMINA   (0 = hoje, 1 = ontem)
//   LOOKBACK_DAYS quantos dias antes desse fim ela COMECA  (sobreposicao)
//
// POR QUE UM DIA POR REQUEST, e nao um intervalo:
// a API da Join AGREGA o periodo inteiro numa unica linha quando
// start_date != end_date, e devolve o campo `date` como rotulo de intervalo.
// Verificado em dado real (2026-08-11), nos dois endpoints:
//
//   start=2026-08-10 end=2026-08-10 -> { "date": "10/08/2026",              imp: 8 }
//   start=2026-08-09 end=2026-08-10 -> { "date": "09/08/2026 a 10/08/2026", imp: 8 }
//
// Ou seja: NAO existe quebra por dia dentro de um intervalo. Pedir um range
// perde a granularidade diaria e devolve um total que, se fosse gravado, seria
// atribuido a um dia so. Vale para /earnings e /key-value (Synthetic e
// Analytical). Por isso o teto de 15 dias da doc nao nos serve de nada.
//
// A sobreposicao (LOOKBACK_DAYS) existe porque a Join pode revisar numero
// retroativamente. O upsert e idempotente, entao reprocessar dia nao duplica.
const cfg = $('Config').first().json;

const tz       = cfg.TZ || 'America/Sao_Paulo';
const offset   = Math.max(0, Number(cfg.OFFSET_DAYS) || 0);
const lookback = Math.max(0, Number(cfg.LOOKBACK_DAYS) || 0);
const tetoDias = Math.max(1, Number(cfg.MAX_DIAS_POR_RUN) || 62);

const fim    = DateTime.now().setZone(tz).startOf('day').minus({ days: offset });
const inicio = fim.minus({ days: lookback });

const janelas = [];
for (let d = inicio; d <= fim; d = d.plus({ days: 1 })) {
  const dia = d.toISODate();
  janelas.push({ json: { start_date: dia, end_date: dia, domain: cfg.JOIN_DOMAIN } });
}

if (janelas.length === 0) {
  throw new Error('Nenhuma janela gerada - confira OFFSET_DAYS/LOOKBACK_DAYS no Config.');
}

// Freio: como agora e 1 request por dia por endpoint, um LOOKBACK_DAYS gordo
// por engano viraria centenas de chamadas na API deles.
if (janelas.length > tetoDias) {
  throw new Error(
    `${janelas.length} dias pedidos (${inicio.toISODate()} a ${fim.toISODate()}), ` +
    `acima do teto de ${tetoDias}. Suba MAX_DIAS_POR_RUN de proposito ou reduza LOOKBACK_DAYS.`
  );
}

return janelas;
"""

# helper compartilhado pelos dois normalizadores
JS_PARSE_DATA = r"""
// A janela pedida serve para desambiguar datas como "08/04/2024": testamos as
// duas leituras possiveis e ficamos com a que cai dentro do intervalo pedido.
const janelas   = $('Monta janelas').all().map((i) => i.json);
const limiteIni = janelas.map((j) => j.start_date).sort()[0];
const limiteFim = janelas.map((j) => j.end_date).sort().slice(-1)[0];

function parseData(bruto) {
  if (bruto == null) return { date: null, ambigua: false, intervalo: false };
  const s = String(bruto).trim();

  // CINTO DE SEGURANCA. Quando o request cobre mais de um dia, a Join devolve
  // UMA linha agregada com o campo date como rotulo de intervalo:
  //     "09/08/2026 a 10/08/2026"
  // Uma regex ancorada so no inicio casaria o prefixo "09/08/2026" e gravaria o
  // total de dois dias como se fosse do dia 09 -- errado, e calado. Contamos
  // quantas datas existem na string: mais de uma = agregado, descarta.
  // O 'Monta janelas' ja garante 1 dia por request, entao isso nunca deveria
  // disparar. Se disparar, alguem mexeu na janela e o Resumo vai gritar.
  const tokens = s.match(/\d{1,4}[\/\-]\d{1,2}[\/\-]\d{1,4}/g) || [];
  if (tokens.length > 1) return { date: null, ambigua: false, intervalo: true };

  const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return { date: `${iso[1]}-${iso[2]}-${iso[3]}`, ambigua: false, intervalo: false };

  const m = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})/);
  if (!m) return { date: null, ambigua: false, intervalo: false };

  const a = m[1].padStart(2, '0');
  const b = m[2].padStart(2, '0');
  const ano = m[3];
  const dmy = `${ano}-${b}-${a}`;   // a = dia,  b = mes
  const mdy = `${ano}-${a}-${b}`;   // a = mes,  b = dia

  const dentro = (d) =>
    DateTime.fromISO(d).isValid && d >= limiteIni && d <= limiteFim;

  const okDmy = dentro(dmy);
  const okMdy = dentro(mdy);

  if (okDmy && !okMdy) return { date: dmy, ambigua: false, intervalo: false };
  if (okMdy && !okDmy) return { date: mdy, ambigua: false, intervalo: false };
  if (okDmy && okMdy)  return { date: pref === 'MDY' ? mdy : dmy, ambigua: dmy !== mdy, intervalo: false };
  return { date: null, ambigua: false, intervalo: false };
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

JS_NORM_EARNINGS = r"""// /earnings  ->  daily_project_metrics
//
// O VOLC O.S. grava SEMPRE o bruto: quem aplica o revshare e o trigger do
// banco, a partir de projects.revshare.
//
// A API devolve OS DOIS valores -- `revenue` (bruto) e `revenue_client`
// (liquido) -- apesar de a doc so citar o segundo. Confirmado em dado real:
// ecpm 1.25 vs ecpm_client 1.13 = 0.904, que e o revshare de 10%.
// Entao usamos `revenue` direto. O EARNINGS_IS_NET so governa o fallback,
// para o caso de um dia vir so o liquido.
const cfg = $('Config').first().json;

const revshare  = Number(cfg.JOIN_REVSHARE) || 0;
const ehLiquido = String(cfg.EARNINGS_IS_NET).toLowerCase() === 'true';
const pref      = String(cfg.DATE_PREFERENCE || 'DMY').toUpperCase();
const batchSize = Math.max(1, Number(cfg.BATCH_SIZE) || 500);
__HELPERS__

const porChave = new Map();
let descartadas = 0;
let ambiguas = 0;
let intervalos = 0;
let reconstruidas = 0;

for (const item of $input.all()) {
  const linhas = Array.isArray(item.json?.data) ? item.json.data : [];
  for (const r of linhas) {
    const { date, ambigua, intervalo } = parseData(r.date);
    if (intervalo) { intervalos++; continue; }
    if (!date) { descartadas++; continue; }
    if (ambigua) ambiguas++;

    const dominio = limpaDominio(r.domain);
    if (!dominio) { descartadas++; continue; }

    let receita = Number(r.revenue);
    if (!Number.isFinite(receita)) {
      // fallback: veio so o liquido -- reconstroi o bruto
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
  descartadas, datasAmbiguas: ambiguas, intervalos, reconstruidas,
});
"""

JS_NORM_KEYVALUE = r"""// /key-value (custom_key=utm_campaign)  ->  joinads_metrics
//
// Usamos `earnings` (BRUTO), nao `earnings_client`: o revshare e aplicado pelo
// trigger do banco. Gravar liquido aqui descontaria duas vezes.
const cfg = $('Config').first().json;

const pref       = String(cfg.DATE_PREFERENCE || 'DMY').toUpperCase();
const batchSize  = Math.max(1, Number(cfg.BATCH_SIZE) || 500);
const dominioCfg = String(cfg.JOIN_DOMAIN || '').trim().toLowerCase().replace(/^www\./, '');
const chaveEsperada = String(cfg.CUSTOM_KEY || 'utm_campaign').trim();
__HELPERS__

function num(v) {
  if (v == null) return 0;
  const n = Number(String(v).replace(/\s/g, '').replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
}

const porChave = new Map();
let descartadas = 0;
let ambiguas = 0;
let intervalos = 0;
let chaveTrocada = 0;

for (const item of $input.all()) {
  const linhas = Array.isArray(item.json?.data) ? item.json.data : [];
  for (const r of linhas) {
    const { date, ambigua, intervalo } = parseData(r.date);
    if (intervalo) { intervalos++; continue; }
    if (!date) { descartadas++; continue; }
    if (ambigua) ambiguas++;

    // GUARDA CRITICA. Quando nao ha dado para a chave pedida, a API IGNORA o
    // parametro e devolve OUTRA chave, sem avisar. Verificado em dado real:
    // pedimos custom_key=utm_campaign e voltou custom_key=land_uri.
    // Sem esta guarda, URLs entrariam na coluna utm_campaign_value como se
    // fossem id de campanha, e o dashboard mostraria lixo com cara de dado.
    const chaveVinda = String(r.custom_key ?? r.custon_key ?? '').trim();
    if (chaveVinda && chaveVinda !== chaveEsperada) { chaveTrocada++; continue; }

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
  descartadas, datasAmbiguas: ambiguas, intervalos, chaveTrocada, chaveEsperada,
});
"""

JS_RESUMO = r"""// Resumo da execucao. Aparece no log do n8n e e o corpo gravado em
// system_settings.joinads_last_update.
const cfg     = $('Config').first().json;
const janelas = $('Monta janelas').all().map((i) => i.json);

function stats(no) {
  try {
    const j = $(no).first().json;
    return {
      linhas: j.totalLinhas ?? 0,
      lotes: j.totalLotes ?? 0,
      descartadas: j.descartadas ?? 0,
      datas_ambiguas: j.datasAmbiguas ?? 0,
      intervalos: j.intervalos ?? 0,
      chave_trocada: j.chaveTrocada ?? 0,
      reconstruidas: j.reconstruidas ?? 0,
    };
  } catch (e) {
    return { linhas: 0, lotes: 0, erro: String(e.message || e) };
  }
}

const projeto  = stats('Normaliza earnings');
const campanha = stats('Normaliza key-value');

// Cada alerta abaixo significa "o numero que voce esta vendo pode estar errado".
// Nenhum deles derruba a execucao de proposito: preferimos gravar so o que da
// para confiar e deixar o rastro do que foi jogado fora.
const alertas = [];

if (projeto.intervalos + campanha.intervalos > 0) {
  alertas.push(
    'A Join devolveu linha AGREGADA de intervalo (campo date como "dd/mm/aaaa a dd/mm/aaaa") ' +
    'e ela foi descartada. Isso so acontece se o request cobriu mais de um dia -- ' +
    'confira o no "Monta janelas", ele deve emitir start_date == end_date.'
  );
}

if (campanha.chave_trocada > 0) {
  alertas.push(
    `A API devolveu ${campanha.chave_trocada} linha(s) com custom_key diferente de ` +
    `"${cfg.CUSTOM_KEY || 'utm_campaign'}" e elas foram descartadas. Isso e o comportamento ` +
    'dela quando nao ha dado para a chave pedida: ela ignora o parametro e manda outra. ' +
    'Enquanto o site nao tiver trafego com utm_campaign, o eixo de campanha fica vazio -- ' +
    'o que esta certo, melhor vazio do que com land_uri fingindo ser campanha.'
  );
}

if (projeto.datas_ambiguas + campanha.datas_ambiguas > 0) {
  alertas.push(
    'Houve data ambigua resolvida por DATE_PREFERENCE. Confirmado em dado real que a Join ' +
    'usa DD/MM/AAAA no report_type=Synthetic e ISO no Analytical, entao isso nao deveria ' +
    'aparecer -- se apareceu, o formato mudou.'
  );
}

return [{
  json: {
    ok: true,
    fonte: 'joinads',
    dominio: cfg.JOIN_DOMAIN,
    janela: { de: janelas[0].start_date, ate: janelas[janelas.length - 1].end_date, dias: janelas.length },
    projeto,
    campanha,
    alertas: alertas.length ? alertas : null,
    executado_em: new Date().toISOString(),
  },
}];
"""


def code(js):
    return {"jsCode": js}


def norm_js(template):
    return template.replace("__HELPERS__", JS_PARSE_DATA.rstrip())


# ──────────────────────────────────────────────────────────── template ──

def build(nome, path_webhook, cron, offset_days, lookback_days, nota):
    N = []

    def add(name, ntype, tv, params, pos, **extra):
        n = {"parameters": params, "id": name, "name": name,
             "type": ntype, "typeVersion": tv, "position": pos}
        n.update(extra)
        N.append(n)

    add("Schedule Trigger", "n8n-nodes-base.scheduleTrigger", 1.2,
        {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}},
        [-420, -40])

    add("Executar manualmente", "n8n-nodes-base.manualTrigger", 1, {}, [-420, 140])

    add("Webhook - Atualizar agora", "n8n-nodes-base.webhook", 2,
        {"httpMethod": "POST", "path": path_webhook,
         "responseMode": "onReceived", "options": {}},
        [-420, 320], webhookId=path_webhook)

    add("Config", "n8n-nodes-base.set", 3.4, {
        "assignments": {"assignments": [
            {"id": "c1", "name": "JOIN_DOMAIN", "type": "string",
             "value": "={{ $json.body?.domain || '%s' }}" % DOMINIO_PADRAO},
            {"id": "c2", "name": "JOIN_REVSHARE", "type": "string", "value": "0.10"},
            {"id": "c3", "name": "EARNINGS_IS_NET", "type": "string", "value": "true"},
            {"id": "c4", "name": "OFFSET_DAYS", "type": "string", "value": str(offset_days)},
            {"id": "c5", "name": "LOOKBACK_DAYS", "type": "string",
             "value": "={{ $json.body?.lookback_days ?? %d }}" % lookback_days},
            # teto de dias por execucao: agora e 1 request por DIA, entao um
            # lookback gordo por engano viraria centenas de chamadas
            {"id": "c6", "name": "MAX_DIAS_POR_RUN", "type": "string", "value": "62"},
            {"id": "c7", "name": "TZ", "type": "string", "value": "America/Sao_Paulo"},
            {"id": "c8", "name": "DATE_PREFERENCE", "type": "string", "value": "DMY"},
            {"id": "c9", "name": "BATCH_SIZE", "type": "string", "value": "500"},
            # chaves validas: utm_campaign, id_post_wp, id_post, utm_source,
            # utm_medium, utm_content, land_uri
            {"id": "c10", "name": "CUSTOM_KEY", "type": "string", "value": "utm_campaign"},
        ]}, "options": {}}, [-180, 140])

    add("Monta janelas", "n8n-nodes-base.code", 2, code(JS_JANELAS), [60, 140])

    http_opts = {"timeout": 60000, "response": {"response": {"neverError": False}}}
    retry = dict(retryOnFail=True, maxTries=3, waitBetweenTries=3000,
                 onError="continueErrorOutput")

    add("Join - GET /earnings", "n8n-nodes-base.httpRequest", 4.2, {
        "url": "https://office.joinads.me/api/clients-endpoints/earnings",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True, "headerParameters": {"parameters": [
            {"name": "Accept", "value": "application/json"}]},
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "start_date", "value": "={{ $json.start_date }}"},
            {"name": "end_date", "value": "={{ $json.end_date }}"},
            {"name": "domain", "value": "={{ $json.domain }}"}]},
        "options": http_opts},
        [300, -20], credentials=JOIN_CRED, **retry)

    add("Join - GET /key-value", "n8n-nodes-base.httpRequest", 4.2, {
        "url": "https://office.joinads.me/api/clients-endpoints/key-value",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True, "headerParameters": {"parameters": [
            {"name": "Accept", "value": "application/json"}]},
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "start_date", "value": "={{ $json.start_date }}"},
            {"name": "end_date", "value": "={{ $json.end_date }}"},
            {"name": "domain", "value": "={{ $json.domain }}"},
            {"name": "report_type", "value": "Synthetic"},
            {"name": "custom_key",
             "value": "={{ $('Config').first().json.CUSTOM_KEY }}"}]},
        "options": http_opts},
        [300, 320], credentials=JOIN_CRED, **retry)

    add("Normaliza earnings", "n8n-nodes-base.code", 2,
        code(norm_js(JS_NORM_EARNINGS)), [540, -20])
    add("Normaliza key-value", "n8n-nodes-base.code", 2,
        code(norm_js(JS_NORM_KEYVALUE)), [540, 320])

    def cond_if(nid):
        return {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "",
                        "typeValidation": "loose", "version": 2},
            "conditions": [{"id": nid,
                            "leftValue": "={{ $json.rows.length }}",
                            "rightValue": 0,
                            "operator": {"type": "number", "operation": "gt"}}],
            "combinator": "and"}, "options": {}}

    add("Tem linha? (projeto)", "n8n-nodes-base.if", 2.2, cond_if("p1"), [780, -20])
    add("Tem linha? (campanha)", "n8n-nodes-base.if", 2.2, cond_if("c1"), [780, 320])

    def upsert(name, tabela, conflito, pos):
        add(name, "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST", "url": f"{SUPABASE}/rest/v1/{tabela}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendQuery": True, "queryParameters": {"parameters": [
                {"name": "on_conflict", "value": conflito}]},
            "sendHeaders": True, "headerParameters": {"parameters": [
                {"name": "Prefer", "value": "resolution=merge-duplicates,return=minimal"},
                {"name": "Content-Type", "value": "application/json"}]},
            "sendBody": True, "contentType": "raw",
            "rawContentType": "application/json",
            # lote inteiro num POST so, em vez de uma requisicao por linha
            "body": "={{ JSON.stringify($json.rows) }}",
            "options": {"timeout": 120000}},
            pos, credentials=SUPA_CRED,
            retryOnFail=True, maxTries=3, waitBetweenTries=2000)

    upsert("Upsert daily_project_metrics", "daily_project_metrics",
           "date,url_projeto", [1020, -20])
    upsert("Upsert joinads_metrics", "joinads_metrics",
           "date,utm_campaign_value,joinads_domain", [1020, 320])

    add("Junta ramos", "n8n-nodes-base.merge", 3,
        {"numberInputs": 2, "options": {}}, [1260, 150])

    add("Resumo", "n8n-nodes-base.code", 2, code(JS_RESUMO), [1480, 150])

    add("Marca joinads_last_update", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"{SUPABASE}/rest/v1/system_settings",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "on_conflict", "value": "key"}]},
        "sendHeaders": True, "headerParameters": {"parameters": [
            {"name": "Prefer", "value": "resolution=merge-duplicates,return=minimal"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": '={\n  "key": "joinads_last_update",\n'
                    '  "value": "{{ $json.executado_em }}",\n'
                    '  "updated_at": "{{ $json.executado_em }}"\n}',
        "options": {}},
        [1700, 150], credentials=SUPA_CRED)

    add("Registra falha", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"{SUPABASE}/rest/v1/system_settings",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "on_conflict", "value": "key"}]},
        "sendHeaders": True, "headerParameters": {"parameters": [
            {"name": "Prefer", "value": "resolution=merge-duplicates,return=minimal"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": '={\n  "key": "joinads_last_error",\n'
                    '  "value": "{{ $now.toISO() }} | ' + nome +
                    ' | {{ JSON.stringify($json.error ?? $json).slice(0, 400) }}",\n'
                    '  "updated_at": "{{ $now.toISO() }}"\n}',
        "options": {}},
        [780, 640], credentials=SUPA_CRED)

    add("Sticky Note", "n8n-nodes-base.stickyNote", 1,
        {"width": 520, "height": 620, "content": nota}, [-1020, -60])

    conns = {
        "Schedule Trigger":          {"main": [[{"node": "Config", "type": "main", "index": 0}]]},
        "Executar manualmente":      {"main": [[{"node": "Config", "type": "main", "index": 0}]]},
        "Webhook - Atualizar agora": {"main": [[{"node": "Config", "type": "main", "index": 0}]]},
        "Config":                    {"main": [[{"node": "Monta janelas", "type": "main", "index": 0}]]},
        "Monta janelas": {"main": [[
            {"node": "Join - GET /earnings", "type": "main", "index": 0},
            {"node": "Join - GET /key-value", "type": "main", "index": 0}]]},
        "Join - GET /earnings": {"main": [
            [{"node": "Normaliza earnings", "type": "main", "index": 0}],
            [{"node": "Registra falha", "type": "main", "index": 0}]]},
        "Join - GET /key-value": {"main": [
            [{"node": "Normaliza key-value", "type": "main", "index": 0}],
            [{"node": "Registra falha", "type": "main", "index": 0}]]},
        "Normaliza earnings":  {"main": [[{"node": "Tem linha? (projeto)", "type": "main", "index": 0}]]},
        "Normaliza key-value": {"main": [[{"node": "Tem linha? (campanha)", "type": "main", "index": 0}]]},
        # ramo falso vai direto pro merge: dia sem dado nao pode travar o resumo
        "Tem linha? (projeto)": {"main": [
            [{"node": "Upsert daily_project_metrics", "type": "main", "index": 0}],
            [{"node": "Junta ramos", "type": "main", "index": 0}]]},
        "Tem linha? (campanha)": {"main": [
            [{"node": "Upsert joinads_metrics", "type": "main", "index": 0}],
            [{"node": "Junta ramos", "type": "main", "index": 1}]]},
        "Upsert daily_project_metrics": {"main": [[{"node": "Junta ramos", "type": "main", "index": 0}]]},
        "Upsert joinads_metrics":       {"main": [[{"node": "Junta ramos", "type": "main", "index": 1}]]},
        "Junta ramos": {"main": [[{"node": "Resumo", "type": "main", "index": 0}]]},
        "Resumo":      {"main": [[{"node": "Marca joinads_last_update", "type": "main", "index": 0}]]},
    }

    return {"name": nome, "nodes": N, "connections": conns,
            "settings": {"executionOrder": "v1"}, "pinData": {},
            "meta": {"templateCredsSetupCompleted": False}}


NOTA_COMUM = """## Join Ads -> VOLC O.S.

**Antes de rodar:**
1. Aplicar `src/sql/joinads/01_joinads_metrics.sql` e `02_project_type_joinads.sql`.
2. Criar a credencial n8n **Header Auth** chamada `JoinAds - Bearer Token`:
   - Name: `Authorization`
   - Value: `Bearer SEU_TOKEN`
3. Trocar `JOIN_DOMAIN` no no **Config** pelo dominio real do MI.
4. Cadastrar o projeto em `projects` com `revshare = 0.10`.

**Como o dado entra**
- `/earnings`  -> `daily_project_metrics`  (eixo projeto)
- `/key-value` -> `joinads_metrics` -> trigger -> `daily_campaign_metrics` (eixo campanha)

Gravamos sempre o valor **BRUTO** (`revenue` / `earnings`, nao os `_client`).
Quem desconta o revshare de 10% e o trigger do banco, via `projects.revshare`.

**UMA REQUISICAO POR DIA.** A Join agrega o periodo inteiro numa linha so
quando `start_date != end_date` (o campo `date` volta como
`"09/08/2026 a 10/08/2026"`). Nao existe quebra por dia dentro de um intervalo.

**A API troca o `custom_key` calada** quando nao ha dado para a chave pedida
(pedimos `utm_campaign`, veio `land_uri`). O normalizador descarta essas linhas
e o Resumo avisa -- eixo de campanha vazio ate o site ter trafego com UTM.

**Webhook (botao "atualizar agora")**
`POST https://fluxos.agenciavolc.com.br/webhook/__PATH__`
```json
{ "domain": "exemplo.com.br", "lookback_days": 3 }
```
Os dois campos sao opcionais; sem corpo, usa o padrao do Config.

__EXTRA__"""

FLOWS = [
    dict(
        arquivo="joinads_report_intraday.json",
        nome="JOIN ADS - REPORT - INTRA DAY",
        path_webhook="joinads-intraday",
        cron="0 6,12,18,23 * * *",
        offset_days=0,
        lookback_days=0,
        extra="**Janela:** hoje (`OFFSET_DAYS=0`, `LOOKBACK_DAYS=0`).\n"
              "Roda as 06/12/18/23, mesma cadencia do flow de GAM.",
    ),
    dict(
        arquivo="joinads_report_day_before.json",
        nome="JOIN ADS - REPORT - DAY BEFORE",
        path_webhook="joinads-day-before",
        cron="0 6 * * *",
        offset_days=1,
        lookback_days=2,
        extra="**Janela:** D-1 voltando 2 dias (`OFFSET_DAYS=1`, `LOOKBACK_DAYS=2`),\n"
              "para reabsorver revisao retroativa da Join. Como o upsert e\n"
              "idempotente, reprocessar nao duplica. Se quiser exatamente so o\n"
              "D-1 do jeito antigo, ponha `LOOKBACK_DAYS = 0`.",
    ),
]

destino = os.path.dirname(os.path.abspath(__file__))

for f in FLOWS:
    nota = (NOTA_COMUM
            .replace("__PATH__", f["path_webhook"])
            .replace("__EXTRA__", f["extra"]))
    wf = build(f["nome"], f["path_webhook"], f["cron"],
               f["offset_days"], f["lookback_days"], nota)
    caminho = os.path.join(destino, f["arquivo"])
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(wf, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"ok {f['arquivo']}  ({len(wf['nodes'])} nos)")
