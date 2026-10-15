/**
 * Carimbos de "última atualização" guardados em `system_settings`.
 *
 * A mesma tabela tem DOIS formatos ao mesmo tempo (medido em produção em
 * 15/10/2026):
 *   - ISO 8601 (`gam_last_update`, `joinads_last_update`);
 *   - "dd/mm/aaaa, hh:mm:ss" em horário de Brasília (`google_ads_last_update`),
 *     gravado pelo n8n com `toLocaleString('pt-BR')`.
 *
 * A RPC `get_last_data_update` faz `value::timestamptz` e quebra (HTTP 400)
 * no formato pt-BR. Por isso a leitura acontece aqui, tolerante aos dois.
 * Formato desconhecido vira `null` — ausência, não "agora".
 */

// Brasil sem horário de verão desde 2019: Brasília é sempre UTC-3.
const FUSO_BRASILIA = '-03:00';
const PT_BR = /^(\d{1,2})\/(\d{1,2})\/(\d{4}),?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?$/;

const doisDigitos = (n: string) => n.padStart(2, '0');

export function interpretarCarimbo(valor: string | null | undefined): Date | null {
  if (!valor) return null;
  const texto = valor.trim();
  if (!texto) return null;

  const ptBr = PT_BR.exec(texto);
  if (ptBr) {
    const [, dia, mes, ano, hora, minuto, segundo = '00'] = ptBr;
    const iso = `${ano}-${doisDigitos(mes)}-${doisDigitos(dia)}T${doisDigitos(hora)}:${minuto}:${segundo}${FUSO_BRASILIA}`;
    const data = new Date(iso);
    // Rejeita datas que o Date "conserta" (32/13 virando outro mês).
    if (Number.isNaN(data.getTime())) return null;
    const naData = new Date(data.getTime() - 3 * 3600 * 1000);
    if (naData.getUTCDate() !== Number(dia) || naData.getUTCMonth() + 1 !== Number(mes)) return null;
    return data;
  }

  // Só ISO; `new Date` aceita textos demais para servir de detector.
  if (!/^\d{4}-\d{2}-\d{2}/.test(texto)) return null;
  const data = new Date(texto);
  return Number.isNaN(data.getTime()) ? null : data;
}

/** Devolve o valor ORIGINAL do carimbo mais recente legível, ou `null`. */
export function carimboMaisRecente(valores: Array<string | null | undefined>): string | null {
  let melhor: { valor: string; instante: number } | null = null;
  for (const valor of valores) {
    const data = interpretarCarimbo(valor);
    if (!data || !valor) continue;
    if (!melhor || data.getTime() > melhor.instante) {
      melhor = { valor, instante: data.getTime() };
    }
  }
  return melhor ? melhor.valor : null;
}
