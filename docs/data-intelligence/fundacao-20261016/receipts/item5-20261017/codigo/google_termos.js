// Item 5 (17/10/2026) — Code node do coletor Google Ads termos e keywords.
// Só emite observação para linha devolvida pela GAQL (não há linha fabricada); campo omitido dentro de
// linha existente é o zero do proto3 (zero medido) e a linha leva metric_row_status = 'present'.
// Moeda: customer.currency_code devolvido na própria linha; sem ele, null + currency_status 'unproven'.
const flatten = (name) => $(name).all().flatMap(i => i.json?.results || []);
const customerId = $('Split Out2').item.json.customerClient?.id?.toString() || '';
const terms = flatten('Google Ads | Search terms 7d');
const keywords = flatten('Google Ads | Keywords 7d');
const num = (o,k) => o && Object.prototype.hasOwnProperty.call(o,k) ? Number(o[k]) : 0;
const opt = (o,k) => o && Object.prototype.hasOwnProperty.call(o,k) ? Number(o[k]) : null;
const currencyOf = (row) => {
  const c = row?.customer?.currencyCode;
  return typeof c === 'string' && /^[A-Z]{3}$/.test(c) ? c : null;
};
const contractAttrs = (row) => {
  const currency = currencyOf(row);
  return {metric_row_status: 'present', currency_status: currency ? 'observed' : 'unproven',
    currency_source: currency ? 'gaql:customer.currency_code' : null};
};
const pii = [
  /\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b/,
  /\b\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}\b/,
  /[\w.+-]+@[\w-]+\.[\w.]+/,
  /(?:\d[\s.\-]?){10,}/
];
const safe = (text) => text && !pii.some(r => r.test(text));
const metric = (m) => ({
  impressions: num(m,'impressions'), clicks: num(m,'clicks'),
  cost_micros: num(m,'costMicros'), conversions: num(m,'conversions'),
  conversions_value: num(m,'conversionsValue'), ctr: opt(m,'ctr'),
  average_cpc_micros: opt(m,'averageCpc')
});

const out = [];
for (const row of terms) {
  const text = row.searchTermView?.searchTerm?.trim();
  if (!safe(text)) continue;
  const cid = row.campaign?.id?.toString() || '';
  const aid = row.adGroup?.id?.toString() || '';
  const day = row.segments?.date || '';
  if (!cid || !aid || !day) continue;
  out.push({
    resource_type:'search_term', grain:'search_term_day', customer_id:customerId,
    campaign_id:cid, ad_group_id:aid, criterion_id:null, resource_id:null,
    metric_date:day, currency_code:currencyOf(row),
    observation_key:`${customerId}:${cid}:${aid}:${day}:term:${text}`,
    dimensions:{search_term:text,campaign_name:row.campaign?.name || null,ad_group_name:row.adGroup?.name || null},
    metrics:metric(row.metrics || {}), attributes:{status:row.searchTermView?.status || null, ...contractAttrs(row)},
    raw_source:row
  });
}
for (const row of keywords) {
  const text = row.adGroupCriterion?.keyword?.text?.trim();
  if (!safe(text)) continue;
  const cid = row.campaign?.id?.toString() || '';
  const aid = row.adGroup?.id?.toString() || '';
  const kid = row.adGroupCriterion?.criterionId?.toString() || '';
  const day = row.segments?.date || '';
  if (!cid || !aid || !kid || !day) continue;
  out.push({
    resource_type:'keyword', grain:'keyword_day', customer_id:customerId,
    campaign_id:cid, ad_group_id:aid, criterion_id:kid, resource_id:kid,
    metric_date:day, currency_code:currencyOf(row),
    observation_key:`${customerId}:${cid}:${aid}:${kid}:${day}`,
    dimensions:{keyword:text,match_type:row.adGroupCriterion?.keyword?.matchType || null,campaign_name:row.campaign?.name || null,ad_group_name:row.adGroup?.name || null},
    metrics:metric(row.metrics || {}), attributes:{status:row.adGroupCriterion?.status || null, ...contractAttrs(row)},
    raw_source:row
  });
}
const grouped = new Map();
for (const row of out) {
  const key = `${row.customer_id}:${row.resource_type}:${row.grain}`;
  if (!grouped.has(key)) grouped.set(key, []);
  grouped.get(key).push(row);
}
const data = [...grouped.values()].map(rows => {
  const days = rows.map(r => r.metric_date).sort();
  return {
    customer_id: rows[0].customer_id,
    resource_type: rows[0].resource_type,
    grain: rows[0].grain,
    window_start: days[0], window_end: days[days.length - 1],
    batch_key: `${rows[0].customer_id}:${rows[0].resource_type}:${days[0]}:${days[days.length - 1]}`,
    payload: rows.map(r => r.raw_source),
    observations: rows.map(({raw_source, resource_type, grain, customer_id, ...r}) => r)
  };
});
return [{json:{data}}];
