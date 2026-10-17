// Canonical JoinAds v2 normalizer.
// Input data stays aggregate: this workflow never requests raw visitor documents.
const cfg = $('Config').first().json;
const windows = $('Monta janelas').all().map(x => x.json);
const collectedAt = new Date().toISOString();

function wasExecuted(name) {
  try { return $(name).all().length >= 0; } catch (_) { return false; }
}

const triggerKind = wasExecuted('Webhook') ? 'webhook' :
  (wasExecuted('Manual') ? 'manual' : 'schedule');
const slot = collectedAt.slice(0, 13).replace(/[-T:]/g, '');
const runKey = [
  `joinads-v${cfg.COLLECTOR_VERSION || 4}`, cfg.MODE, windows[0].start_date,
  windows[windows.length - 1].end_date, triggerKind, slot,
].join(':');

const rawBatches = [];
const observations = [];
const warnings = [];
const endpointRows = {};
let rejected = 0;

function cleanDomain(value) {
  return String(value || '').trim().toLowerCase()
    .replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/.*$/, '');
}

function numeric(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(String(value).trim().replace(/\s/g, '').replace(',', '.'));
  return Number.isFinite(n) ? n : null;
}

function integer(value) {
  const n = numeric(value);
  return n === null ? null : Math.round(n);
}

// [item 5] Dinheiro em micros por aritmética decimal exata (BigInt), arredondamento half-even.
// Nunca usa float binário para normalizar. Fail-closed: não numérico, NaN/infinito, negativo,
// precisão excessiva (mais de 34 dígitos significativos ou escala além de 40) e overflow
// (acima de 1e12 unidades) rejeitam a linha. A representação recebida fica em attributes.revenue_original.
const MICROS_MAX = 10n ** 18n;
function quantizeMicros(value) {
  if (value === null || value === undefined || value === '') return {ok: true, text: null, original: null};
  let s;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return {ok: false, reason: 'nao_finito'};
    s = String(value);
  } else if (typeof value === 'string') {
    s = value.trim().replace(/\s/g, '');
  } else {
    return {ok: false, reason: 'tipo_invalido'};
  }
  const original = s;
  if (s.includes(',') && !s.includes('.')) s = s.replace(',', '.');
  const m = s.match(/^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/) || s.match(/^([+-]?)()\.(\d+)(?:[eE]([+-]?\d+))?$/);
  if (!m) return {ok: false, reason: /nan|inf/i.test(s) ? 'nao_finito' : 'nao_numerico'};
  const frac = m[3] || '';
  const digits = ((m[2] || '0') + frac).replace(/^0+(?=\d)/, '');
  const scale = frac.length - Number(m[4] || 0);
  if (digits.replace(/^0+/, '').length > 34 || Math.abs(scale) > 40) return {ok: false, reason: 'precisao_excessiva'};
  if (m[1] === '-' && /[1-9]/.test(digits)) return {ok: false, reason: 'negativo'};
  const n = BigInt(digits);
  const shift = 6 - scale;
  let micros;
  if (shift >= 0) {
    micros = n * (10n ** BigInt(shift));
  } else {
    const d = 10n ** BigInt(-shift);
    const q = n / d;
    const twice = 2n * (n % d);
    micros = (twice > d || (twice === d && q % 2n === 1n)) ? q + 1n : q;
  }
  if (micros > MICROS_MAX) return {ok: false, reason: 'overflow'};
  return {ok: true, text: `${micros / 1000000n}.${(micros % 1000000n).toString().padStart(6, '0')}`, original};
}

function currencyFromRow(row) {
  const c = row?.currency ?? row?.currency_code ?? row?.moeda;
  return typeof c === 'string' && /^[A-Z]{3}$/.test(c.trim()) ? c.trim() : null;
}

function contractAttributes(row, qGross, qClient) {
  // Moeda: a API não declara moeda. Vale a atestação operacional do dono (17/10/2026: earnings bruto da
  // JoinAds é USD), registrada como tal — não é prova técnica. Conversão para BRL NÃO acontece no ledger:
  // a cotação configurada no VOLC está congelada desde 18/02/2026 e não pode ser provada vigente; a conversão
  // única fica para a camada de leitura, com taxa, fonte e vigência explícitas.
  const rowCurrency = currencyFromRow(row);
  const attrs = rowCurrency
    ? {currency_status: 'observed', currency_source: 'joinads_api:row', currency_original: rowCurrency}
    : {currency_status: 'attested', currency_source: 'owner_attestation', currency_original: 'USD',
       currency_attestation_ref: 'dono 2026-10-17T10:51Z; docs/SPEC-ARBITRAGEM.md:10'};
  if (qGross.original !== null || qClient.original !== null) {
    attrs.revenue_quantization = 'decimal_half_even_micros';
    attrs.revenue_original = {revenue_gross: qGross.original, revenue_client: qClient.original};
    attrs.conversion = {status: 'nao_convertido', motivo: 'cotacao_vigente_nao_provada', currency_converted: 'BRL',
      revenue_converted: null, taxa: null, fonte_taxa: null, vigencia: null};
  }
  return attrs;
}

function dateOf(value, fallback) {
  const text = String(value || '').trim();
  let match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return `${match[1]}-${match[2]}-${match[3]}`;
  match = text.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);
  if (match) return `${match[3]}-${match[2].padStart(2, '0')}-${match[1].padStart(2, '0')}`;
  return fallback || null;
}

function safePart(value) {
  return encodeURIComponent(String(value ?? '')).replace(/%/g, '_').slice(0, 180);
}

function dataRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.data)) return payload.data;
  if (payload?.data && typeof payload.data === 'object') return [payload.data];
  return [];
}

function metricStatus(values) {
  const present = values.filter(v => v !== null && v !== undefined);
  return present.length && present.every(v => Number(v) === 0) ? 'zero_confirmed' : 'observed';
}

function baseObservation(endpoint, grain, batchKey, row, day, index) {
  const qGross = quantizeMicros(row.revenue ?? row.earnings ?? row.AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE);
  const qClient = quantizeMicros(row.revenue_client ?? row.earnings_client);
  for (const [nome, q] of [['revenue_gross', qGross], ['revenue_client', qClient]]) {
    if (!q.ok) throw new Error(`revenue_invalid:${nome}:${q.reason}`);
  }
  const customKey = String(row.custom_key ?? row.custon_key ?? '').trim() || null;
  const customValue = String(row.custom_value ?? row.custon_value ?? '').trim() || null;
  const campaign = customKey === 'utm_campaign' && customValue && /^\d+$/.test(customValue)
    ? customValue : null;
  const rawCountryIso = String(row.iso ?? '').trim();
  const countryIso = /^[A-Za-z]{2,3}$/.test(rawCountryIso) ? rawCountryIso.toUpperCase() : null;
  const dimension = [campaign, row.id_post ?? row.id_post_wp, row.url, row.ad_unit_name,
    row.country, row.iso, row.hour, index].map(safePart).join(':');
  return {
    observation_key: `${batchKey}:${dimension}`,
    run_key: runKey,
    batch_key: batchKey,
    endpoint,
    grain,
    metric_date: dateOf(row.date ?? row.DATE, day),
    metric_hour: row.hour === undefined ? null : integer(row.hour),
    domain: cleanDomain(row.domain ?? row.DOMAIN ?? row.name ?? cfg.DOMAIN) || null,
    campaign_id: campaign,
    custom_key: customKey,
    custom_value: customValue,
    post_id: String(row.id_post ?? row.id_post_wp ??
      (customKey === 'id_post_wp' ? customValue : '')).trim() || null,
    land_uri: String(row.url ?? (customKey === 'land_uri' ? customValue : '')).trim() || null,
    ad_unit_name: String(row.ad_unit_name ?? '').trim() || null,
    country: String(row.country ?? '').trim() || null,
    country_iso: countryIso,
    advertiser: String(row.ADVERTISER ?? '').trim() || null,
    network: String(row.network ?? '').trim() || null,
    currency_code: currencyFromRow(row) || cfg.CURRENCY || 'USD',
    revenue_gross: qGross.text,
    revenue_client: qClient.text,
    impressions: integer(row.impressions ?? row.AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS),
    clicks: integer(row.clicks ?? row.AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS),
    requests_served: integer(row.requests_served),
    unfilled: integer(row.unfilled_impressions),
    active_view: numeric(row.active_view ?? row.active_view_viewable ??
      row.AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS_RATE),
    pmr: numeric(row.pmr),
    ctr: numeric(row.ctr ?? row.AD_EXCHANGE_LINE_ITEM_LEVEL_CTR),
    ecpm_gross: numeric(row.ecpm ?? row.AD_EXCHANGE_LINE_ITEM_LEVEL_AVERAGE_ECPM),
    ecpm_client: numeric(row.ecpm_client),
    pageviews: null,
    unique_views: null,
    first_views: null,
    dimensions: rawCountryIso && !countryIso ? {source_country_iso: rawCountryIso} : {},
    attributes: contractAttributes(row, qGross, qClient),
    data_status: 'observed',
    collected_at: collectedAt,
  };
}

function collect(nodeName, endpoint, grain, transform, requestMeta = {}) {
  let items = [];
  try { items = $(nodeName).all(); }
  catch (error) {
    warnings.push({endpoint, code: 'node_unavailable', detail: String(error.message || error).slice(0, 180)});
    return;
  }
  items.forEach((item, itemIndex) => {
    const window = windows[itemIndex] || windows[0];
    const originalPayload = item.json ?? {};
    const hasError = Boolean(originalPayload.error);
    const payload = hasError ? {
      error: {
        name: String(originalPayload.error?.name ?? 'JoinAdsEndpointError').slice(0, 100),
        message: 'endpoint request failed; inspect the protected n8n execution log',
      },
    } : originalPayload;
    const rows = dataRows(payload);
    const batchKey = `${runKey}:${endpoint}:${window.start_date}:${itemIndex}`;
    rawBatches.push({
      batch_key: batchKey,
      run_key: runKey,
      endpoint,
      grain,
      request_meta: {start_date: window.start_date, end_date: window.end_date,
        domain: cleanDomain(window.domain), ...requestMeta},
      http_status: hasError ? 599 : 200,
      row_count: rows.length,
      payload,
      collected_at: collectedAt,
    });
    endpointRows[endpoint] = (endpointRows[endpoint] || 0) + rows.length;
    if (hasError) {
      warnings.push({endpoint, code: 'endpoint_unavailable', detail: payload.error.message});
    }
    rows.forEach((row, rowIndex) => {
      try {
        const observation = transform(row, window.start_date, batchKey, rowIndex);
        if (observation) observations.push(observation);
      } catch (error) {
        rejected += 1;
        warnings.push({endpoint, code: 'row_rejected', row: rowIndex,
          detail: String(error.message || error).slice(0, 180)});
      }
    });
  });
}

function standard(endpoint, grain, expectedKey = null) {
  return (row, day, batchKey, index) => {
    const obs = baseObservation(endpoint, grain, batchKey, row, day, index);
    if (expectedKey && obs.custom_key && obs.custom_key !== expectedKey) {
      rejected += 1;
      warnings.push({endpoint, code: 'custom_key_substituted', expected: expectedKey,
        received: obs.custom_key});
      return null;
    }
    if (expectedKey === 'utm_campaign' && !obs.campaign_id) {
      rejected += 1;
      warnings.push({endpoint, code: 'invalid_campaign_id'});
      return null;
    }
    obs.data_status = metricStatus([obs.revenue_gross, obs.impressions, obs.clicks,
      obs.requests_served, obs.pageviews]);
    return obs;
  };
}

collect('API earnings', 'earnings', 'domain_day', standard('earnings', 'domain_day'));
collect('API campaign adunit', 'key_value_campaign_adunit', 'campaign_adunit_day',
  standard('key_value_campaign_adunit', 'campaign_adunit_day', 'utm_campaign'),
  {report_type: 'Analytical', custom_key: 'utm_campaign', include: 'ad_unit_name'});
collect('API post', 'key_value_post', 'post_day',
  standard('key_value_post', 'post_day', 'id_post_wp'),
  {report_type: 'Synthetic', custom_key: 'id_post_wp'});
collect('API land', 'key_value_land', 'land_day',
  (row, day, batchKey, index) => {
    const obs = standard('key_value_land', 'land_day', 'land_uri')(row, day, batchKey, index);
    if (obs && !obs.land_uri) obs.land_uri = obs.custom_value;
    return obs;
  }, {report_type: 'Synthetic', custom_key: 'land_uri'});
collect('API country adunit', 'key_value_country_adunit', 'campaign_country_adunit_day',
  (row, day, batchKey, index) => standard(
    'key_value_country_adunit', 'campaign_country_adunit_day', 'utm_campaign'
  )({...row, custom_key: 'utm_campaign'}, day, batchKey, index),
  {report_type: 'Analytical', custom_key: 'utm_campaign', include: 'ad_unit_name'});
collect('API top url', 'top_url', 'url_day', standard('top_url', 'url_day'), {limit: 250});
collect('API top country', 'top_country', 'country_day', standard('top_country', 'country_day'), {limit: 250});

collect('API pageviews domain', 'pageviews_domain', 'domain_day', (row, day, batchKey, index) => {
  const obs = baseObservation('pageviews_domain', 'domain_day', batchKey, row, day, index);
  obs.pageviews = integer(row.visitas ?? row.pageview);
  obs.unique_views = integer(row.unique ?? row.uniqueview);
  obs.data_status = metricStatus([obs.pageviews, obs.unique_views]);
  return obs;
});

collect('API pageviews batch', 'pageviews_campaign_batch', 'campaign_day',
  (row, day, batchKey, index) => {
    const inner = row.data && typeof row.data === 'object' ? row.data : {};
    const rawKeyValue = String(row.keyvalue ?? '').trim();
    const keyValue = rawKeyValue.startsWith('utm_campaign=')
      ? rawKeyValue.slice('utm_campaign='.length) : rawKeyValue;
    const synthetic = {...inner, custom_key: 'utm_campaign', custom_value: keyValue};
    const obs = baseObservation('pageviews_campaign_batch', 'campaign_day', batchKey, synthetic, day, index);
    if (!obs.campaign_id) {
      rejected += 1;
      warnings.push({endpoint: 'pageviews_campaign_batch', code: 'invalid_campaign_id'});
      return null;
    }
    obs.pageviews = integer(inner.pageview ?? inner.visitas);
    obs.unique_views = integer(inner.unique ?? inner.uniqueview);
    obs.attributes = {...obs.attributes, source_status: row.status ?? null};
    obs.data_status = metricStatus([obs.pageviews, obs.unique_views]);
    return obs;
  }, {key: 'utm_campaign', count: true});

collect('API policies', 'policies', 'account_snapshot', (row, day, batchKey, index) => {
  const obs = baseObservation('policies', 'account_snapshot', batchKey, row, day, index);
  obs.metric_date = day;
  obs.dimensions = {total_count: integer(row.total_count), high_priority_count: integer(row.high_priority_count)};
  obs.attributes = {...obs.attributes, message: String(row.message ?? '').slice(0, 500) || null};
  return obs;
});

return [{json: {
  run: {
    run_key: runKey,
    workflow_id: String($workflow.id || ''),
    workflow_execution_id: String($execution.id || ''),
    collector: 'n8n_joinads_v2',
    collector_version: Number(cfg.COLLECTOR_VERSION || 4),
    mode: cfg.MODE,
    trigger_kind: triggerKind,
    window_start: windows[0].start_date,
    window_end: windows[windows.length - 1].end_date,
    timezone: cfg.TIMEZONE,
    status: 'running',
    started_at: collectedAt,
    receipt: {phase: 'collecting', endpoint_contract: 'joinads-v2', contract: 'item5-20261017'},
  },
  raw_batches: rawBatches,
  observations,
  endpoint_count: Object.keys(endpointRows).length,
  endpoint_rows: endpointRows,
  rows_read: Object.values(endpointRows).reduce((a, b) => a + b, 0),
  rows_rejected: rejected,
  warnings,
}}];
