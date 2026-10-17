// Item 5 (17/10/2026) — Code node dos coletores canônicos Google Ads campanha-dia (D0 e D-1).
// Contrato: sem linha de métrica na GAQL, nenhuma métrica é fabricada (metrics = {} e
// metric_row_status = 'metric_row_absent'); com linha, campo omitido é o zero do proto3 e vale como
// zero medido. Moeda só da origem: customer.currency_code devolvido pela GAQL; sem ele, null + 'unproven'.
// O builder substitui o objeto N pelos nomes de nó de cada workflow.
const N = __NOMES__;
const flatten = (name) => $(name).all().flatMap(i => i.json?.results || []);
const campaigns = flatten(N.campaigns).filter(x => x.campaign?.status !== 'REMOVED');
const goals = flatten(N.goals);
const budgets = flatten(N.budgets);
const metricRows = flatten(N.metrics);
const customerId = $(N.split).item.json.customerClient?.id?.toString() || '';
const metricDate = $(N.fields).item.json['Start date'];

const byCampaign = (rows, getId) => new Map(rows.map(r => [getId(r), r]).filter(x => x[0]));
const goalMap = byCampaign(goals, r => r.campaign?.id?.toString());
const budgetMap = byCampaign(budgets, r => r.campaign?.id?.toString());
const metricMap = byCampaign(metricRows, r => r.campaign?.id?.toString());
const has = (obj, key) => Boolean(obj) && Object.prototype.hasOwnProperty.call(obj, key);
// só chamado com linha de métrica presente: campo omitido = valor padrão do proto3 (zero medido)
const measured = (obj, key) => has(obj, key) ? Number(obj[key]) : 0;
const optional = (obj, key) => has(obj, key) ? Number(obj[key]) : null;
const currencyOf = (row) => {
  const c = row?.customer?.currencyCode;
  return typeof c === 'string' && /^[A-Z]{3}$/.test(c) ? c : null;
};

const data = campaigns.map(row => {
  const c = row.campaign || {};
  const id = c.id?.toString() || '';
  const metricRow = metricMap.get(id);
  const hasMetricRow = metricRow !== undefined;
  const m = metricRow?.metrics || {};
  const budgetRow = budgetMap.get(id) || {};
  const b = budgetRow.campaignBudget || {};
  const goalRow = goalMap.get(id) || {};
  const metrics = hasMetricRow ? {
    cost_micros: measured(m, 'costMicros'),
    impressions: measured(m, 'impressions'),
    clicks: measured(m, 'clicks'),
    interactions: measured(m, 'interactions'),
    conversions: measured(m, 'conversions'),
    conversions_value: measured(m, 'conversionsValue'),
    all_conversions: measured(m, 'allConversions'),
    all_conversions_value: measured(m, 'allConversionsValue'),
    ctr: optional(m, 'ctr'),
    average_cpc_micros: optional(m, 'averageCpc'),
    cost_per_conversion_micros: optional(m, 'costPerConversion'),
    search_impression_share: optional(m, 'searchImpressionShare'),
    search_budget_lost_impression_share: optional(m, 'searchBudgetLostImpressionShare'),
    search_rank_lost_impression_share: optional(m, 'searchRankLostImpressionShare'),
    top_impression_percentage: optional(m, 'topImpressionPercentage'),
    absolute_top_impression_percentage: optional(m, 'absoluteTopImpressionPercentage'),
    search_click_share: optional(m, 'searchClickShare'),
    search_exact_match_impression_share: optional(m, 'searchExactMatchImpressionShare')
  } : {};
  const currency = currencyOf(row) ?? currencyOf(metricRow);
  return {
    customer_id: customerId,
    campaign_id: id,
    metric_date: metricDate,
    campaign_name: c.name || '',
    status: c.status || '',
    channel: c.advertisingChannelType || '',
    bidding_strategy: c.biddingStrategyType || '',
    budget_id: b.id?.toString() || null,
    budget_micros: optional(b, 'amountMicros'),
    custom_goal: goalRow.customConversionGoal?.name || null,
    currency_code: currency,
    metric_row_status: hasMetricRow ? 'present' : 'metric_row_absent',
    currency_status: currency ? 'observed' : 'unproven',
    currency_source: currency ? 'gaql:customer.currency_code' : null,
    metrics,
    raw_source: { campaign: row, metrics: metricRow || {}, budget: budgetRow, goal: goalRow }
  };
}).filter(x => x.campaign_id && x.customer_id);

const unique = new Map(data.map(x => [`${x.customer_id}:${x.campaign_id}`, x]));
return [{ json: { data: [...unique.values()] } }];
