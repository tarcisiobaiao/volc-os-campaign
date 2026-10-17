// Item 5 — error workflow comum dos coletores canônicos: classificar e sanitizar.
// Entrada: saída do Error Trigger ({execution, workflow}) ou, no teste, {teste: {...mesma forma}}.
// Nunca lança: qualquer falha aqui vira {acao:'nenhuma'} para não criar laço de erro.
const COLETORES = {
  Ps9yLfQkHeaAbyZZ: {fonte: 'google', collector: 'n8n-google-ads-d0', finalizador: 'Supabase | Finalizar run'},
  '7yxs1aOlzWkkkSf9': {fonte: 'google', collector: 'n8n-google-ads-d1', finalizador: 'Supabase | Finalizar run'},
  TFlmThr4930oPneE: {fonte: 'google', collector: 'n8n-google-ads-terms-keywords', finalizador: 'Supabase | Finalizar run'},
  cpb6tNxt211UkAn2: {fonte: 'joinads', collector: 'n8n_joinads_v2', finalizador: 'Finaliza run'},
  jDX397ViVcRQft4A: {fonte: 'joinads', collector: 'n8n_joinads_v2', finalizador: 'Finaliza run'},
};
function sanitizar(texto) {
  return String(texto ?? '')
    .replace(/https?:\/\/[^\s"']+/gi, '<url>')
    .replace(/(bearer|token|apikey|api_key|authorization|password|secret|developer-token)\s*[:=]?\s*[^\s,;"']+/gi, '$1 <redacted>')
    .replace(/eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}(\.[A-Za-z0-9_-]+)?/g, '<jwt>')
    .replace(/[\w.+-]+@[\w-]+\.[\w.]+/g, '<email>')
    .replace(/\d{6,}/g, '<n>')
    .replace(/\s+/g, ' ').trim().slice(0, 300);
}
function classe(err) {
  const t = `${err?.name ?? ''} ${err?.message ?? ''} ${err?.description ?? ''}`.toLowerCase();
  if (/timeout|timed out|etimedout|esockettimedout/.test(t)) return 'timeout';
  if (/econnreset|econnrefused|enotfound|socket hang up|network/.test(t)) return 'rede';
  if (/\b(401|403)\b|unauthori|forbidden|permission/.test(t)) return 'autorizacao';
  if (/\b429\b|rate limit|quota|resource_exhausted/.test(t)) return 'quota';
  if (/\b5\d\d\b|internal server|bad gateway|unavailable/.test(t)) return 'servidor_remoto';
  if (/\b(400|404|409|422)\b|invalid|violat|constraint|duplicate/.test(t)) return 'requisicao_rejeitada';
  if (/referenced node|expression|is not defined|cannot read|undefined/.test(t)) return 'codigo_workflow';
  return 'desconhecido';
}
let saida;
try {
  const bruto = $json.teste ?? $json;
  const teste = $json.teste !== undefined;
  const exec = bruto.execution ?? {};
  const wf = bruto.workflow ?? {};
  const info = COLETORES[String(wf.id ?? '')];
  const err = exec.error ?? {};
  const execId = String(exec.id ?? '');
  saida = {
    teste,
    fonte: info?.fonte ?? 'desconhecida',
    collector: info?.collector ?? null,
    workflow_id: String(wf.id ?? ''),
    falha_execution_id: execId,
    error_execution_id: String($execution.id ?? ''),
    ultimo_no: sanitizar(exec.lastNodeExecuted ?? ''),
    no_finalizador: info?.finalizador ?? null,
    classe_erro: classe(err),
    mensagem: sanitizar(err.message ?? err.description ?? ''),
    modo_execucao: String(exec.mode ?? ''),
    retry_de: exec.retryOf ? String(exec.retryOf) : null,
    instante: new Date().toISOString(),
    run_key_google: info?.fonte === 'google' && execId ? `${wf.id}:${execId}` : null,
    elegivel: Boolean(info) && Boolean(execId),
  };
} catch (e) {
  saida = {elegivel: false, fonte: 'desconhecida', classe_erro: 'falha_no_error_workflow', mensagem: String(e.message).slice(0, 120)};
}
return [{json: saida}];
