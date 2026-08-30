/**
 * O contrato do `evidencia.json` — a saída bruta do runner somente-leitura.
 *
 * Produzido por `docs/growth-engine/diagnostico/consultas/rodar.py`. É um dump
 * de consultas, não um diagnóstico: cada entrada carrega o que foi perguntado,
 * por que, quando, e — o que mais importa aqui — se a pergunta foi respondida.
 *
 * ## As duas ausências deste arquivo, que NÃO são a mesma
 *
 *  1. `ok: false` — a consulta falhou. Nada se sabe sobre aquele assunto.
 *  2. `ok: true, n: 0` — a consulta respondeu e não há linha nenhuma.
 *
 * A primeira é `nao_apurado`; a segunda é um fato medido. Colapsar as duas é
 * exatamente o defeito que o Hub inteiro existe para não cometer.
 *
 * ## ⚠️ A terceira ausência, e a dependência de contrato que ela cria
 *
 * O runner serializa com `always_print_fields_with_no_presence=False`. Em
 * proto3 sem presença explícita isso OMITE o valor padrão: uma métrica de
 * `impressions: 0` não aparece na linha. Ou seja, dentro de uma linha que veio,
 * campo ausente significa **zero medido** — não "não sei".
 *
 * Este módulo trata assim, e `zeroMedido()` é onde a regra mora. A alternativa
 * segura está registada em `docs/growth-engine/frontend.md`: pedir ao runner
 * `always_print_fields_with_no_presence=True`, e aí campo ausente volta a
 * significar ausência de verdade.
 */

/** Uma linha crua, tal como `MessageToDict` a devolve: snake_case aninhado. */
export type LinhaDaConsulta = Record<string, unknown>;

export interface ConsultaRespondida {
  gaql: string;
  por_que: string;
  lido_em_utc: string;
  ok: true;
  n: number;
  linhas: LinhaDaConsulta[];
}

export interface ConsultaFalhada {
  gaql: string;
  por_que: string;
  lido_em_utc: string;
  ok: false;
  /** A mensagem literal da API. É a evidência da falha, não um rótulo nosso. */
  erro: string;
}

export type RegistroDeConsulta = ConsultaRespondida | ConsultaFalhada;

export interface MetaDaEvidencia {
  lido_em_utc: string;
  customer_id: string;
  login_customer_id: string;
  versao_api: string;
  janela_das_metricas: string;
  modo_de_escrita: string;
  somente_leitura: boolean;
}

/** Os nomes de consulta que o runner emite. Lista aberta de propósito. */
export type NomeDeConsulta =
  | 'conta'
  | 'campanhas'
  | 'grupos'
  | 'anuncios'
  | 'keywords'
  | 'keywords_estimativas'
  | 'keywords_metricas'
  | 'metricas_campanha'
  | 'metricas_campanha_diaria'
  | 'metricas_grupo'
  | 'criterios_campanha'
  | 'geo_alvo'
  | 'conversoes'
  | 'conversoes_metricas'
  | 'mudancas'
  | 'faturamento'
  | 'termos_de_busca'
  | 'recomendacoes';

export interface EvidenciaDeDiagnostico {
  _meta: MetaDaEvidencia;
  consultas: Partial<Record<NomeDeConsulta, RegistroDeConsulta>> &
    Record<string, RegistroDeConsulta | undefined>;
}

// ── leitura defensiva ───────────────────────────────────────────────────────

/** Uma consulta que respondeu, ou `null`. Nunca uma lista vazia por omissão. */
export function respondida(
  ev: EvidenciaDeDiagnostico,
  nome: string,
): ConsultaRespondida | null {
  const r = ev.consultas?.[nome];
  if (!r || r.ok !== true) return null;
  return r;
}

/** Por que uma consulta não respondeu. `null` quando ela respondeu. */
export function motivoDaFalha(
  ev: EvidenciaDeDiagnostico,
  nome: string,
): string | null {
  const r = ev.consultas?.[nome];
  if (!r) return `a consulta "${nome}" não estava nesta leitura`;
  if (r.ok === true) return null;
  return r.erro;
}

/** Caminho aninhado (`campaign.id`) sem lançar em nada que faltar. */
export function campo(linha: LinhaDaConsulta, caminho: string): unknown {
  let atual: unknown = linha;
  for (const parte of caminho.split('.')) {
    if (typeof atual !== 'object' || atual === null) return undefined;
    atual = (atual as Record<string, unknown>)[parte];
  }
  return atual;
}

export function texto(linha: LinhaDaConsulta, caminho: string): string | null {
  const v = campo(linha, caminho);
  return typeof v === 'string' && v !== '' ? v : null;
}

export function lista(linha: LinhaDaConsulta, caminho: string): string[] {
  const v = campo(linha, caminho);
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === 'string');
}

/**
 * Número de um campo com presença implícita.
 *
 * ⚠️ Campo ausente vira `0`, e isso é CORRETO aqui e só aqui: a linha veio, o
 * serializador omite o padrão, então "sem o campo" é "o valor é o padrão". Em
 * qualquer outro lugar deste código base transformar ausência em zero é o
 * defeito; aqui é a leitura fiel do formato. A função tem nome próprio para que
 * a exceção seja visível na chamada em vez de virar um `?? 0` distraído.
 */
export function zeroMedido(linha: LinhaDaConsulta, caminho: string): number {
  const v = campo(linha, caminho);
  if (typeof v === 'number') return v;
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) {
    return Number(v);
  }
  return 0;
}

/** Booleano com presença implícita. Ausente = `false`, pelo mesmo motivo. */
export function booleanoMedido(linha: LinhaDaConsulta, caminho: string): boolean {
  return campo(linha, caminho) === true;
}

/** O id da campanha de uma linha, como texto. `null` quando não há. */
export function idDaCampanha(linha: LinhaDaConsulta): string | null {
  const v = campo(linha, 'campaign.id');
  if (typeof v === 'string' && v !== '') return v;
  if (typeof v === 'number') return String(v);
  return null;
}

/** Só as linhas de uma campanha. Lista vazia quando a consulta não a trouxe. */
export function linhasDaCampanha(
  consulta: ConsultaRespondida | null,
  campaignId: string,
): LinhaDaConsulta[] {
  if (!consulta) return [];
  return consulta.linhas.filter((l) => idDaCampanha(l) === campaignId);
}
