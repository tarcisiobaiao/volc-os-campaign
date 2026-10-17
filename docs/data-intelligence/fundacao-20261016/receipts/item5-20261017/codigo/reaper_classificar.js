// Item 5 — reaper dos coletores canônicos, MODO SHADOW. Só lê e classifica; não escreve nada.
// Motivo: o CHECK de status de google_ads_collection_run e joinads_collection_run aceita só
// running/completed/partial/failed; marcar 'abandoned' exige migration (não autorizada). Até lá o reaper
// aponta candidatos com evidência e o operador decide.
// Candidato: status 'running' e sem lote novo nem heartbeat há mais de LIMITE_MIN minutos. A execução n8n
// dona do run NÃO é verificada aqui (exigiria credencial da API do n8n dentro do n8n); por isso nenhum
// candidato é "seguro para fechar" sem a verificação externa registrada no recibo.
const LIMITE_MIN = 60;
const agora = Date.now();
const parse = (t) => (t ? Date.parse(t) : NaN);
const linhas = (nome) => {
  try { return $(nome).all().map(i => i.json).filter(j => j && (j.run_id || j.run_key)); } catch (_) { return []; }
};
// FNV-1a 64 bits: rótulo estável para o log, sem depender de módulo nativo no sandbox do n8n
function pseudo(v) {
  let h = 0xcbf29ce484222325n;
  for (const ch of `volc-reaper:${v}`) { h ^= BigInt(ch.codePointAt(0)); h = (h * 0x100000001b3n) & 0xffffffffffffffffn; }
  return h.toString(16).padStart(16, '0').slice(0, 12);
}
const saida = [];
for (const [fonte, nome, lotes] of [['google', 'Runs Google em running', 'google_ads_raw_batch'], ['joinads', 'Runs JoinAds em running', 'joinads_raw_batch']]) {
  for (const r of linhas(nome)) {
    const ultimoLote = Array.isArray(r[lotes]) && r[lotes][0] ? r[lotes][0].created_at : null;
    const marcos = [parse(r.started_at), parse(ultimoLote), parse(r.updated_at)].filter(Number.isFinite);
    const ultima = marcos.length ? Math.max(...marcos) : NaN;
    const minutos = Number.isFinite(ultima) ? Math.floor((agora - ultima) / 60000) : null;
    const candidato = minutos !== null && minutos > LIMITE_MIN;
    saida.push({
      fonte, collector: r.collector ?? null, run_pseudo: pseudo(r.run_id ?? r.run_key),
      started_at: r.started_at ?? null, ultima_atividade: Number.isFinite(ultima) ? new Date(ultima).toISOString() : null,
      minutos_sem_atividade: minutos, candidato_orfao: candidato,
      execucao_n8n_verificada: false,
      acao: candidato ? 'nenhuma_shadow:abandoned_inexistente_no_schema' : 'nenhuma',
    });
  }
}
return [{json: {modo: 'shadow', limite_minutos: LIMITE_MIN, instante: new Date(agora).toISOString(),
  n_running: saida.length, n_candidatos: saida.filter(s => s.candidato_orfao).length, runs: saida}}];
