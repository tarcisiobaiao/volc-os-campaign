/**
 * Leitura do carimbo `system_settings.{google_ads,gam}_last_update`.
 *
 * O servidor e o n8n gravam esse valor com `toLocaleString('pt-BR')`
 * (`systemSettingsService.ts`), ou seja "11/03/2026, 06:00:17", hora de
 * Brasília. `new Date()` lê isso como MM/DD: 11/03 vira 3 de novembro
 * ("relógio fora de sincronia") e qualquer dia > 12 vira data inválida
 * ("nunca lido"). Os dois mentem sobre uma coleta parada.
 *
 * Aceita o formato pt-BR e ISO 8601. Qualquer outro texto é "ilegível",
 * nunca "nunca lido": havia um carimbo, só não sabemos lê-lo.
 */
export type CarimboDaFonte =
  | { tipo: "vazio" }
  | { tipo: "data"; instante: Date }
  | { tipo: "ilegivel"; bruto: string };

/** Brasília não tem horário de verão desde 2019: UTC−3 fixo. */
const DESLOCAMENTO_SAO_PAULO_H = 3;

const PT_BR = /^(\d{1,2})\/(\d{1,2})\/(\d{4}),?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?$/;
const ISO = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;

export function lerCarimboDaFonte(valor: unknown): CarimboDaFonte {
  if (valor == null) return { tipo: "vazio" };
  const texto = String(valor).replace(/ /g, " ").trim();
  if (texto === "") return { tipo: "vazio" };

  const br = PT_BR.exec(texto);
  if (br) {
    const [, d, m, a, h, min, s] = br;
    const dia = Number(d);
    const mes = Number(m);
    const ano = Number(a);
    const hora = Number(h);
    const minuto = Number(min);
    const segundo = s ? Number(s) : 0;
    const instante = new Date(Date.UTC(ano, mes - 1, dia, hora + DESLOCAMENTO_SAO_PAULO_H, minuto, segundo));
    // Date.UTC rola 31/02 para março; o carimbo só vale se os campos voltarem iguais.
    const devolta = new Date(instante.getTime() - DESLOCAMENTO_SAO_PAULO_H * 3_600_000);
    const valido =
      hora < 24 &&
      minuto < 60 &&
      segundo < 60 &&
      devolta.getUTCFullYear() === ano &&
      devolta.getUTCMonth() === mes - 1 &&
      devolta.getUTCDate() === dia;
    return valido ? { tipo: "data", instante } : { tipo: "ilegivel", bruto: texto };
  }

  if (ISO.test(texto)) {
    const instante = new Date(texto);
    if (!Number.isNaN(instante.getTime())) return { tipo: "data", instante };
  }

  return { tipo: "ilegivel", bruto: texto };
}
