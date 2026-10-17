// Item 5 — error workflow: decidir a transição do run a partir do estado LIDO no banco.
// Idempotente: só toca run que ainda está 'running' (ou, no Google, que não existe). Run já final não é
// alterado. Nunca repete escrita de dados: só registra o estado final e o motivo. Em teste, nunca escreve.
const c = $('Classificar e sanitizar').first().json;
const lido = $input.first().json ?? {};
const linhas = Array.isArray(lido) ? lido : (Array.isArray(lido.data) ? lido.data : (lido.status !== undefined || lido.run_key ? [lido] : []));
const erroLeitura = Boolean(lido.error);
const run = linhas[0] ?? null;
let estagio, acao = 'nenhuma', status_final = null, motivo;
if (!c.elegivel) {
  motivo = 'workflow_nao_canonico_ou_sem_execucao';
} else if (erroLeitura) {
  motivo = 'leitura_do_run_falhou_sem_escrita';
} else if (run && run.status !== 'running') {
  estagio = 'ja_finalizado';
  motivo = `run_ja_${run.status}_nao_alterado`;
} else {
  const lotes = Number(run?.batches_written ?? 0);
  if (!run || lotes === 0) estagio = 'antes_do_primeiro_lote';
  else if (c.ultimo_no && c.ultimo_no === c.no_finalizador) estagio = 'depois_da_gravacao';
  else estagio = 'falha_parcial';
  status_final = estagio === 'antes_do_primeiro_lote' ? 'failed' : 'partial';
  if (c.fonte === 'google') { acao = 'google_finish'; motivo = run ? 'run_running_finalizado' : 'run_inexistente_registrado_como_falha'; }
  else if (c.fonte === 'joinads' && run) { acao = 'joinads_patch'; motivo = 'run_running_finalizado'; }
  else { acao = 'nenhuma'; motivo = 'joinads_sem_run_no_banco_registro_so_no_n8n'; }
}
if (c.teste) { motivo = `teste_sem_escrita:${motivo}`; }
const registro = {
  error_workflow: 'volc-coletores-error-v1', estagio: estagio ?? null, classe_erro: c.classe_erro, ultimo_no: c.ultimo_no ?? null,
  mensagem: c.mensagem ?? null, falha_execution_id: c.falha_execution_id ?? null, error_execution_id: c.error_execution_id ?? null,
  instante: c.instante ?? new Date().toISOString(), retry_de: c.retry_de ?? null,
};
const finalizar = new Date().toISOString();
return [{json: {
  acao: c.teste ? 'nenhuma' : acao, acao_planejada: acao, motivo, status_final, estagio: estagio ?? null, fonte: c.fonte, teste: c.teste,
  run_lido: run ? {status: run.status, batches_written: run.batches_written ?? null} : null,
  google_documento: acao === 'google_finish' ? {documento: {
    run_key: c.run_key_google, workflow_id: c.workflow_id, workflow_execution_id: c.falha_execution_id,
    collector: c.collector, collector_version: 2, api_version: 'v25', mode: 'shadow',
    trigger_kind: c.modo_execucao === 'manual' ? 'manual' : (c.modo_execucao === 'webhook' ? 'webhook' : 'schedule'),
    timezone: 'America/Sao_Paulo', started_at: run?.started_at ?? c.instante, finished_at: finalizar,
    status: status_final, error_class: c.classe_erro, receipt: {error_workflow: registro}}} : null,
  joinads_patch: acao === 'joinads_patch' ? {run_key: run.run_key, corpo: {status: status_final, finished_at: finalizar,
    receipt: {...(run.receipt ?? {}), error_workflow: registro}, error_class: c.classe_erro}} : null,
  registro,
}}];
