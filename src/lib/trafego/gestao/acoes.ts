/**
 * As 15 ações da gestão, nos 9 grupos — formulário → payload do contrato.
 *
 * ## O critério é o do motor, repetido de propósito
 *
 * Cada validação aqui espelha a recusa de `volc_ads/gestao/acoes.py` (o
 * `__post_init__` de cada ação) e de `backend/app/trafego/gestao/application/
 * payload.py`. A tela recusa antes para o operador não montar um pedido que o
 * servidor devolveria com 422 — e o servidor continua sendo quem decide: nada
 * aqui substitui a leitura do "antes" na conta (estado, duplicata, compartilhado).
 *
 * Dinheiro sempre em micros inteiros múltiplos de 10.000 (0,01 da moeda).
 *
 * Módulo puro: sem React, sem HTTP.
 */
import type {
  AcaoDeGestao,
  AlvoDeLance,
  Correspondencia,
  DiaDaSemana,
  Dispositivo,
  EscopoDeExclusao,
  EscopoDeNegativa,
  EstrategiaEscrevivel,
  GrupoDeAcao,
  Janela,
  NivelDeStatus,
  Placement,
  StatusGerivel,
  Termo,
  TipoDeAcao,
  TipoDeLista,
  TipoDePlacement,
} from '@/types/gestao';

// ── vocabulário ─────────────────────────────────────────────────────────────

export const GRUPOS: ReadonlyArray<{ grupo: GrupoDeAcao; rotulo: string; tipos: TipoDeAcao[] }> = [
  { grupo: 'status', rotulo: 'Status', tipos: ['status'] },
  { grupo: 'orcamento', rotulo: 'Orçamento diário', tipos: ['orcamento.diario'] },
  { grupo: 'alvo_de_lance', rotulo: 'Alvo de lance', tipos: ['lance.alvo'] },
  { grupo: 'estrategia', rotulo: 'Troca de estratégia', tipos: ['lance.estrategia'] },
  {
    grupo: 'negativas_e_listas',
    rotulo: 'Negativas e listas',
    tipos: ['negativa.keyword', 'lista.criar', 'lista.adicionar', 'lista.anexar'],
  },
  { grupo: 'placements', rotulo: 'Exclusão de placement', tipos: ['exclusao.placement'] },
  { grupo: 'ip', rotulo: 'Exclusão de IP', tipos: ['exclusao.ip'] },
  {
    grupo: 'agenda_e_ajustes',
    rotulo: 'Agenda e ajustes',
    tipos: ['programacao.anuncios', 'ajuste.dispositivo', 'ajuste.horario'],
  },
  {
    grupo: 'recomendacoes',
    rotulo: 'Recomendações',
    tipos: ['recomendacao.aplicar', 'recomendacao.dispensar'],
  },
];

export const ROTULO_DO_TIPO: Record<TipoDeAcao, string> = {
  status: 'status',
  'orcamento.diario': 'orçamento diário',
  'lance.alvo': 'alvo de lance',
  'lance.estrategia': 'troca de estratégia',
  'negativa.keyword': 'negativas de palavra-chave',
  'lista.criar': 'nova lista compartilhada',
  'lista.adicionar': 'itens numa lista',
  'lista.anexar': 'lista anexada a campanhas',
  'exclusao.placement': 'exclusão de placement',
  'exclusao.ip': 'exclusão de IP',
  'programacao.anuncios': 'programação de anúncios',
  'ajuste.dispositivo': 'ajuste por dispositivo',
  'ajuste.horario': 'ajuste de horário',
  'recomendacao.aplicar': 'aplicar recomendação',
  'recomendacao.dispensar': 'dispensar recomendação',
};

/**
 * §5.1 — as monetárias (orçamento, alvo de lance) nascem sempre que o delta
 * couber na regra. As outras 13 só nascem se a regra vigente as listar em
 * `operacoes_sem_delta` (v17_03) e o pedido couber no teto delas; a tela não
 * lê a regra, então monta, envia e mostra a recusa — avisando antes.
 */
export const TIPOS_MONETARIOS: ReadonlySet<TipoDeAcao> = new Set([
  'orcamento.diario',
  'lance.alvo',
]);

/**
 * Recomendação que mexe em verba, alvo, estratégia ou tarifa — o servidor
 * recusa aplicá-la como recomendação mesmo que a regra a liste. Mesmo padrão
 * de `backend/app/trafego/gestao/application/sem_delta.py`.
 */
const REC_MONETARIA = /(BUDGET|TARGET_CPA|TARGET_ROAS|MAXIMIZE_|ENHANCED_CPC|_FEE$|OPERATING_C)/;

export function recomendacaoMonetaria(tipo: string | null | undefined): boolean {
  return REC_MONETARIA.test(tipo ?? '');
}

export const MICROS_MINIMO = 10_000;
export const TROAS_MAXIMO = 1000;
export const LIMITE_IPS = 500;
export const MAX_JANELAS_POR_DIA = 6;

export const ESTRATEGIAS_POR_CANAL: Record<string, EstrategiaEscrevivel[]> = {
  SEARCH: ['MANUAL_CPC', 'TARGET_SPEND', 'MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE', 'PORTFOLIO'],
  DISPLAY: ['MANUAL_CPC', 'TARGET_SPEND', 'MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE', 'PORTFOLIO'],
  DEMAND_GEN: ['TARGET_SPEND', 'MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE'],
  PERFORMANCE_MAX: ['MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE'],
};

export const ROTULO_DA_ESTRATEGIA: Record<string, string> = {
  MANUAL_CPC: 'CPC manual',
  TARGET_SPEND: 'Maximizar cliques',
  MAXIMIZE_CONVERSIONS: 'Maximizar conversões',
  MAXIMIZE_CONVERSION_VALUE: 'Maximizar valor de conversão',
  TARGET_CPA: 'CPA desejado (padrão)',
  TARGET_ROAS: 'ROAS desejado (padrão)',
  PORTFOLIO: 'Estratégia de portfólio',
};

export const DIAS: ReadonlyArray<{ dia: DiaDaSemana; rotulo: string }> = [
  { dia: 'MONDAY', rotulo: 'segunda' },
  { dia: 'TUESDAY', rotulo: 'terça' },
  { dia: 'WEDNESDAY', rotulo: 'quarta' },
  { dia: 'THURSDAY', rotulo: 'quinta' },
  { dia: 'FRIDAY', rotulo: 'sexta' },
  { dia: 'SATURDAY', rotulo: 'sábado' },
  { dia: 'SUNDAY', rotulo: 'domingo' },
];

export const DISPOSITIVOS: ReadonlyArray<{ dispositivo: Dispositivo; rotulo: string }> = [
  { dispositivo: 'DESKTOP', rotulo: 'computador' },
  { dispositivo: 'MOBILE', rotulo: 'celular' },
  { dispositivo: 'TABLET', rotulo: 'tablet' },
  { dispositivo: 'CONNECTED_TV', rotulo: 'TV conectada' },
];

/** O alvo que a estratégia LIDA aceita no nível da campanha (`CAMPO_DO_ALVO`). */
export interface AlvoDaEstrategia {
  alvo: AlvoDeLance;
  rotulo: string;
  /** `troas` = razão (digitada em %); os outros em dinheiro. */
  unidade: 'dinheiro' | 'percentual';
  /** 0 limpa o alvo (só nas estratégias Maximizar*). */
  aceitaZero: boolean;
}

const ALVO_POR_ESTRATEGIA: Record<string, AlvoDaEstrategia> = {
  TARGET_SPEND: { alvo: 'teto_cpc', rotulo: 'teto de CPC', unidade: 'dinheiro', aceitaZero: true },
  MAXIMIZE_CONVERSIONS: { alvo: 'tcpa', rotulo: 'CPA desejado', unidade: 'dinheiro', aceitaZero: true },
  MAXIMIZE_CONVERSION_VALUE: {
    alvo: 'troas',
    rotulo: 'ROAS desejado',
    unidade: 'percentual',
    aceitaZero: true,
  },
  TARGET_CPA: { alvo: 'tcpa', rotulo: 'CPA desejado', unidade: 'dinheiro', aceitaZero: false },
  TARGET_ROAS: { alvo: 'troas', rotulo: 'ROAS desejado', unidade: 'percentual', aceitaZero: false },
};

export function alvoDaEstrategia(estrategia: string | null | undefined): AlvoDaEstrategia | null {
  return (estrategia && ALVO_POR_ESTRATEGIA[estrategia]) || null;
}

/** Por que não há alvo para a estratégia lida — em linguagem de operação. */
export function semAlvoPorque(estrategia: string | null | undefined): string {
  if (!estrategia) return 'A estratégia de lance desta campanha não foi lida; sem ela não dá para saber qual campo ajustar.';
  if (estrategia === 'MANUAL_CPC') {
    return 'Em CPC manual o lance vive no grupo e na palavra-chave; não há alvo no nível da campanha.';
  }
  if (estrategia === 'PORTFOLIO' || estrategia.startsWith('customers/')) {
    return 'A campanha usa estratégia de portfólio; o alvo é da estratégia compartilhada, não da campanha.';
  }
  return `A estratégia ${estrategia} não tem alvo ajustável no nível da campanha.`;
}

// ── resultado ───────────────────────────────────────────────────────────────

export type Erros = Record<string, string>;
export type Montagem<T extends AcaoDeGestao = AcaoDeGestao> =
  | { ok: true; acao: T }
  | { ok: false; erros: Erros };

/** Os erros de uma montagem recusada; `null` quando ela passou. */
export function errosDe(m: Montagem): Erros | null {
  return 'erros' in m ? m.erros : null;
}

function falha(erros: Erros): { ok: false; erros: Erros } {
  return { ok: false, erros };
}

// ── conversões ──────────────────────────────────────────────────────────────

/**
 * "33,50" / "1.234,56" / "33.5" / "R$ 33" → micros inteiros. `null` se não é
 * dinheiro com até 2 casas. Inteiro puro (sem ponto flutuante): 0,1 + 0,2.
 */
export function reaisParaMicros(texto: string): number | null {
  let t = String(texto ?? '').replace(/R\$|\s/g, '');
  if (!t) return null;
  if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');
  const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(t);
  if (!m) return null;
  const inteiro = Number(m[1]);
  const centavos = Number((m[2] ?? '').padEnd(2, '0') || '0');
  if (!Number.isSafeInteger(inteiro)) return null;
  return inteiro * 1_000_000 + centavos * MICROS_MINIMO;
}

/** "450" / "450,5" → razão 4.505. `null` se não é número. */
export function percentualParaRazao(texto: string): number | null {
  const t = String(texto ?? '').replace(/%|\s/g, '').replace(',', '.');
  if (!/^\d+(\.\d+)?$/.test(t)) return null;
  return Math.round((Number(t) / 100) * 10_000) / 10_000;
}

/** "+20" / "-30" / "20" → multiplicador 1.2 / 0.7. `null` se não é número. */
export function ajusteParaModificador(texto: string): number | null {
  const t = String(texto ?? '').replace(/%|\s/g, '').replace(',', '.');
  if (!/^[+-]?\d+(\.\d+)?$/.test(t)) return null;
  return Math.round((1 + Number(t) / 100) * 10_000) / 10_000;
}

export function ehId(texto: string | null | undefined): boolean {
  return /^\d+$/.test(String(texto ?? '').trim()) && Number(String(texto).trim()) > 0;
}

function idLimpo(texto: string): string {
  return String(texto ?? '').trim();
}

/** Lista de ids separados por vírgula, espaço ou quebra de linha. */
export function listaDeIds(texto: string): string[] {
  return String(texto ?? '')
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function linhas(texto: string): string[] {
  return String(texto ?? '')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
}

function validarMicros(
  micros: number | null,
  { zeroOk }: { zeroOk: boolean },
): string | null {
  if (micros == null) return 'digite um valor em dinheiro com até 2 casas (ex.: 33,50)';
  if (micros === 0 && !zeroOk) return 'o valor tem de ser maior que zero';
  if (micros % MICROS_MINIMO) return 'o valor tem de ser múltiplo de 0,01';
  return null;
}

// ── itens: termo, placement, IP, janela ─────────────────────────────────────

const PROIBIDOS_KEYWORD = new Set('!@%,*(){};~`<>?\\|^='.split(''));

/**
 * Uma linha de negativa. Aceita a notação do Google para a correspondência:
 * `"termo"` = frase, `[termo]` = exata; sem marca, vale o padrão escolhido.
 */
export function lerTermo(linha: string, padrao: Correspondencia): Termo | string {
  let texto = linha.trim();
  let correspondencia = padrao;
  if (/^".*"$/.test(texto)) {
    correspondencia = 'PHRASE';
    texto = texto.slice(1, -1);
  } else if (/^\[.*\]$/.test(texto)) {
    correspondencia = 'EXACT';
    texto = texto.slice(1, -1);
  }
  texto = texto.split(/\s+/).filter(Boolean).join(' ');
  if (!texto) return 'negativa vazia';
  if (texto.length > 80) return `"${texto}" passa de 80 caracteres`;
  if (texto.split(' ').length > 10) return `"${texto}" passa de 10 palavras`;
  const ruins = [...new Set(texto.split(''))].filter((c) => PROIBIDOS_KEYWORD.has(c));
  if (ruins.length) return `"${texto}" tem caractere que o Google recusa: ${ruins.join(' ')}`;
  return { texto, correspondencia };
}

const PADRAO_DO_PLACEMENT: Record<TipoDePlacement, RegExp> = {
  site: /^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(\/\S*)?$/,
  app: /^[12]-[\w.-]+$/,
  youtube_canal: /^UC[\w-]{22}$/,
  youtube_video: /^[\w-]{11}$/,
};

export const ROTULO_DO_PLACEMENT: Record<TipoDePlacement, string> = {
  site: 'site',
  app: 'app (1-<id iOS> ou 2-<pacote Android>)',
  youtube_canal: 'canal do YouTube (UC…)',
  youtube_video: 'vídeo do YouTube (id de 11 caracteres)',
};

export function lerPlacement(tipo: TipoDePlacement, valor: string): Placement | string {
  let v = String(valor ?? '').trim();
  if (tipo === 'site') {
    v = v.toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/+$/, '');
  }
  const padrao = PADRAO_DO_PLACEMENT[tipo];
  if (!padrao) return `tipo de placement desconhecido: ${tipo}`;
  if (!padrao.test(v)) return `${ROTULO_DO_PLACEMENT[tipo]} inválido: "${valor}"`;
  return { tipo, valor: v };
}

function semRepetidos<T>(itens: T[], chave: (i: T) => string, rotulo: string): string | null {
  const vistos = new Set<string>();
  for (const i of itens) {
    const k = chave(i);
    if (vistos.has(k)) return `${rotulo} repetido: ${k}`;
    vistos.add(k);
  }
  return null;
}

const chaveDoTermo = (t: Termo) => `${t.texto.toLowerCase()} (${t.correspondencia})`;
const chaveDoPlacement = (p: Placement) => `${p.tipo}:${p.valor.toLowerCase()}`;

function octetos(ip: string): number[] | null {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(ip);
  if (!m) return null;
  const partes = m.slice(1).map((p) => (p.length > 1 && p.startsWith('0') ? NaN : Number(p)));
  return partes.every((n) => Number.isInteger(n) && n >= 0 && n <= 255) ? partes : null;
}

function ehIpv6(ip: string): boolean {
  if (!/^[0-9a-fA-F:]+$/.test(ip) || !ip.includes(':')) return false;
  const duplos = ip.split('::').length - 1;
  if (duplos > 1) return false;
  const grupos = ip.split(':').filter((g) => g !== '');
  if (grupos.some((g) => g.length > 4)) return false;
  return duplos === 1 ? grupos.length < 8 : grupos.length === 8;
}

/** Endereço único (IPv4/IPv6) ou faixa IPv4 /24–/32 alinhada. Devolve o texto ou o erro. */
export function lerIp(texto: string): { ip: string } | string {
  const t = String(texto ?? '').trim();
  if (!t.includes('/')) {
    if (octetos(t)) return { ip: t };
    if (ehIpv6(t)) return { ip: t.toLowerCase() };
    return `IP inválido: "${texto}"`;
  }
  const [endereco, prefixoTxt] = t.split('/');
  const o = octetos(endereco);
  const prefixo = Number(prefixoTxt);
  if (!o || !/^\d{1,2}$/.test(prefixoTxt ?? '')) {
    return `faixa de IP aceita só IPv4 /24 a /32: "${texto}"`;
  }
  if (prefixo < 24 || prefixo > 32) return `faixa de IP aceita só IPv4 /24 a /32: "${texto}"`;
  const hostBits = 32 - prefixo;
  const ultimo = o[3];
  if (hostBits > 0 && ultimo % 2 ** hostBits !== 0) {
    return `faixa "${texto}" não começa no início da rede (use o endereço de rede)`;
  }
  return { ip: `${endereco}/${prefixo}` };
}

const MINUTOS_VALIDOS = new Set([0, 15, 30, 45]);

export function minutosDoHorario(texto: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(texto ?? '').trim());
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (!MINUTOS_VALIDOS.has(mi) || h < 0 || h > 24 || (h === 24 && mi !== 0)) return null;
  return h * 60 + mi;
}

function validarModificador(m: number | null, { zeroOk }: { zeroOk: boolean }): string | null {
  if (m == null) return 'digite o ajuste em % (ex.: +20 ou -30)';
  if (m === 0 && zeroOk) return null;
  if (m < 0.1 || m > 10) {
    return zeroOk
      ? 'o ajuste vai de −90% a +900%, ou −100% para não exibir'
      : 'o ajuste vai de −90% a +900%';
  }
  return null;
}

export interface JanelaDoFormulario {
  dia: DiaDaSemana;
  inicio: string;
  fim: string;
  /** Ajuste em % ("+20"), vazio = sem ajuste. */
  ajuste: string;
}

export function lerJanelas(janelas: JanelaDoFormulario[]): { janelas: Janela[] } | string {
  const saida: Janela[] = [];
  for (const j of janelas) {
    const a = minutosDoHorario(j.inicio);
    const b = minutosDoHorario(j.fim);
    if (a == null || b == null) {
      return `horário fora da grade de 15 min (00:00–24:00): ${j.inicio}–${j.fim}`;
    }
    if (b <= a) return `janela de ${j.dia} termina antes de começar: ${j.inicio}–${j.fim}`;
    let modificador: number | null = null;
    if (j.ajuste.trim()) {
      modificador = ajusteParaModificador(j.ajuste);
      const e = validarModificador(modificador, { zeroOk: false });
      if (e) return `janela ${j.inicio}–${j.fim}: ${e}`;
    }
    saida.push({ dia: j.dia, inicio: j.inicio.trim(), fim: j.fim.trim(), modificador });
  }
  for (let i = 0; i < saida.length; i++) {
    for (let k = i + 1; k < saida.length; k++) {
      const x = saida[i];
      const y = saida[k];
      if (x.dia !== y.dia) continue;
      const [a, b] = [minutosDoHorario(x.inicio)!, minutosDoHorario(x.fim)!];
      const [c, d] = [minutosDoHorario(y.inicio)!, minutosDoHorario(y.fim)!];
      if (a < d && c < b) return `janelas sobrepostas em ${x.dia}: ${x.inicio}–${x.fim} × ${y.inicio}–${y.fim}`;
    }
  }
  const porDia = new Map<string, number>();
  for (const j of saida) porDia.set(j.dia, (porDia.get(j.dia) ?? 0) + 1);
  for (const [dia, n] of porDia) {
    if (n > MAX_JANELAS_POR_DIA) return `mais de ${MAX_JANELAS_POR_DIA} janelas em ${dia}`;
  }
  return { janelas: saida };
}

// ── contexto lido da campanha ───────────────────────────────────────────────

export interface ContextoDaCampanha {
  customerId: string;
  /** id externo (Google) da campanha desta página. */
  campaignId: string;
  estrategia: string | null;
  canal: string | null;
}

// ── os formulários e a montagem ─────────────────────────────────────────────

export interface FormStatus {
  nivel: NivelDeStatus;
  ident: string;
  status: StatusGerivel | '';
}

export function montarStatus(f: FormStatus): Montagem {
  const erros: Erros = {};
  if (!f.status) erros.status = 'escolha ativar ou pausar';
  const ident = idLimpo(f.ident);
  if (f.nivel === 'anuncio') {
    const [g, a, ...resto] = ident.split('~');
    if (resto.length || !ehId(g) || !ehId(a)) erros.ident = 'anúncio é <id do grupo>~<id do anúncio>';
  } else if (!ehId(ident)) {
    erros.ident = 'id numérico do Google';
  }
  if (Object.keys(erros).length) return falha(erros);
  return { ok: true, acao: { tipo: 'status', nivel: f.nivel, ident, status: f.status as StatusGerivel } };
}

export interface FormOrcamento {
  valor: string;
  budgetId: string;
  compartilhadoCiente: boolean;
}

export function montarOrcamento(f: FormOrcamento, ctx: ContextoDaCampanha): Montagem {
  const erros: Erros = {};
  if (!ehId(ctx.campaignId)) erros.campaign_id = 'a campanha não tem id do Google';
  const micros = reaisParaMicros(f.valor);
  const e = validarMicros(micros, { zeroOk: false });
  if (e) erros.valor = e;
  const budget = idLimpo(f.budgetId);
  if (budget && !ehId(budget)) erros.budgetId = 'id numérico do orçamento, ou vazio para o da campanha';
  if (Object.keys(erros).length) return falha(erros);
  return {
    ok: true,
    acao: {
      tipo: 'orcamento.diario',
      campaign_id: ctx.campaignId,
      amount_micros: micros as number,
      ...(budget ? { budget_id: budget } : {}),
      compartilhado_ciente: f.compartilhadoCiente,
    },
  };
}

export interface FormAlvo {
  valor: string;
}

export function montarAlvo(f: FormAlvo, ctx: ContextoDaCampanha): Montagem {
  const alvo = alvoDaEstrategia(ctx.estrategia);
  if (!alvo) return falha({ valor: semAlvoPorque(ctx.estrategia) });
  if (!ehId(ctx.campaignId)) return falha({ campaign_id: 'a campanha não tem id do Google' });
  let valor: number;
  if (alvo.unidade === 'percentual') {
    const r = percentualParaRazao(f.valor);
    if (r == null) return falha({ valor: 'digite o ROAS em % (ex.: 450 para 450%)' });
    if (r < 0 || r > TROAS_MAXIMO || (r === 0 && !alvo.aceitaZero)) {
      return falha({ valor: `ROAS fora de (0%, ${TROAS_MAXIMO * 100}%]` });
    }
    valor = r;
  } else {
    const micros = reaisParaMicros(f.valor);
    const e = validarMicros(micros, { zeroOk: alvo.aceitaZero });
    if (e) return falha({ valor: e });
    valor = micros as number;
  }
  return {
    ok: true,
    acao: {
      tipo: 'lance.alvo',
      campaign_id: ctx.campaignId,
      alvo: alvo.alvo,
      valor,
      // A estratégia LIDA vai junto: se a conta mudou de estratégia desde a
      // leitura, o servidor recusa em vez de escrever no campo errado.
      ...(ctx.estrategia ? { estrategia: ctx.estrategia } : {}),
    },
  };
}

export interface FormEstrategia {
  nova: EstrategiaEscrevivel | '';
  tcpa: string;
  troas: string;
  tetoCpc: string;
  portfolio: string;
}

export function estrategiasPermitidas(canal: string | null): EstrategiaEscrevivel[] {
  if (canal && ESTRATEGIAS_POR_CANAL[canal]) return ESTRATEGIAS_POR_CANAL[canal];
  return ESTRATEGIAS_POR_CANAL.SEARCH;
}

export function montarEstrategia(f: FormEstrategia, ctx: ContextoDaCampanha): Montagem {
  const erros: Erros = {};
  if (!ehId(ctx.campaignId)) erros.campaign_id = 'a campanha não tem id do Google';
  if (!f.nova) {
    erros.nova = 'escolha a estratégia nova';
    return falha(erros);
  }
  if (!estrategiasPermitidas(ctx.canal).includes(f.nova)) {
    erros.nova = `${ROTULO_DA_ESTRATEGIA[f.nova] ?? f.nova} não é escrita pela gestão neste canal`;
  }
  if (ctx.estrategia && ctx.estrategia === f.nova) erros.nova = 'a campanha já está nesta estratégia';
  const acao: Extract<AcaoDeGestao, { tipo: 'lance.estrategia' }> = {
    tipo: 'lance.estrategia',
    campaign_id: ctx.campaignId,
    nova: f.nova,
  };
  if (f.nova === 'MAXIMIZE_CONVERSIONS' && f.tcpa.trim()) {
    const m = reaisParaMicros(f.tcpa);
    const e = validarMicros(m, { zeroOk: true });
    if (e) erros.tcpa = e;
    else acao.tcpa_micros = m as number;
  }
  if (f.nova === 'MAXIMIZE_CONVERSION_VALUE' && f.troas.trim()) {
    const r = percentualParaRazao(f.troas);
    if (r == null || r < 0 || r > TROAS_MAXIMO) erros.troas = `ROAS em % entre 0 e ${TROAS_MAXIMO * 100}`;
    else acao.troas = r;
  }
  if (f.nova === 'TARGET_SPEND' && f.tetoCpc.trim()) {
    const m = reaisParaMicros(f.tetoCpc);
    const e = validarMicros(m, { zeroOk: true });
    if (e) erros.tetoCpc = e;
    else acao.teto_cpc_micros = m as number;
  }
  if (f.nova === 'PORTFOLIO') {
    const p = f.portfolio.trim();
    if (!/^customers\/\d+\/biddingStrategies\/\d+$/.test(p)) {
      erros.portfolio = 'resource name: customers/<conta>/biddingStrategies/<id>';
    } else acao.portfolio = p;
  }
  if (Object.keys(erros).length) return falha(erros);
  return { ok: true, acao };
}

export type SubtipoDeNegativa = 'negativa.keyword' | 'lista.criar' | 'lista.adicionar' | 'lista.anexar';

export interface FormNegativas {
  subtipo: SubtipoDeNegativa;
  escopo: EscopoDeNegativa;
  alvo: string;
  /** Uma por linha; `"frase"` e `[exata]` são entendidas. */
  termos: string;
  correspondencia: Correspondencia;
  tipoLista: TipoDeLista;
  nome: string;
  tipoPlacement: TipoDePlacement;
  /** Placements, um por linha (listas de placement). */
  placements: string;
  sharedSetId: string;
  /** Ids de campanha separados por vírgula/espaço. */
  campanhas: string;
}

function lerTermos(texto: string, padrao: Correspondencia): { termos: Termo[] } | string {
  const ls = linhas(texto);
  if (!ls.length) return 'digite ao menos uma negativa';
  const termos: Termo[] = [];
  for (const l of ls) {
    const t = lerTermo(l, padrao);
    if (typeof t === 'string') return t;
    termos.push(t);
  }
  const rep = semRepetidos(termos, chaveDoTermo, 'termo');
  return rep ?? { termos };
}

function lerPlacements(tipo: TipoDePlacement, texto: string): { itens: Placement[] } | string {
  const ls = linhas(texto);
  if (!ls.length) return 'digite ao menos um placement';
  const itens: Placement[] = [];
  for (const l of ls) {
    const p = lerPlacement(tipo, l);
    if (typeof p === 'string') return p;
    itens.push(p);
  }
  const rep = semRepetidos(itens, chaveDoPlacement, 'placement');
  return rep ?? { itens };
}

function lerItensDaLista(f: FormNegativas): { itens: Array<Termo | Placement> } | string {
  if (f.tipoLista === 'NEGATIVE_KEYWORDS') {
    const r = lerTermos(f.termos, f.correspondencia);
    return typeof r === 'string' ? r : { itens: r.termos };
  }
  const r = lerPlacements(f.tipoPlacement, f.placements);
  return typeof r === 'string' ? r : { itens: r.itens };
}

function lerCampanhas(texto: string, obrigatoria: boolean): { campanhas: string[] } | string {
  const ids = listaDeIds(texto);
  if (!ids.length) return obrigatoria ? 'informe ao menos uma campanha' : { campanhas: [] };
  if (ids.some((i) => !ehId(i))) return 'ids de campanha são numéricos';
  if (new Set(ids).size !== ids.length) return 'campanha repetida';
  return { campanhas: ids };
}

export function montarNegativas(f: FormNegativas): Montagem {
  const erros: Erros = {};
  if (f.subtipo === 'negativa.keyword') {
    if (!ehId(f.alvo)) erros.alvo = `id numérico do ${f.escopo === 'grupo' ? 'grupo' : 'campanha'}`;
    const r = lerTermos(f.termos, f.correspondencia);
    if (typeof r === 'string') erros.termos = r;
    if (Object.keys(erros).length || typeof r === 'string') return falha(erros);
    return { ok: true, acao: { tipo: 'negativa.keyword', escopo: f.escopo, alvo: idLimpo(f.alvo), termos: r.termos } };
  }
  if (f.subtipo === 'lista.criar') {
    const nome = f.nome.split(/\s+/).filter(Boolean).join(' ');
    if (!nome || nome.length > 255) erros.nome = 'nome da lista (até 255 caracteres)';
    const itens = lerItensDaLista(f);
    if (typeof itens === 'string') erros.itens = itens;
    const camp = lerCampanhas(f.campanhas, false);
    if (typeof camp === 'string') erros.campanhas = camp;
    if (Object.keys(erros).length || typeof itens === 'string' || typeof camp === 'string') return falha(erros);
    return {
      ok: true,
      acao: {
        tipo: 'lista.criar',
        tipo_lista: f.tipoLista,
        nome,
        itens: itens.itens,
        ...(camp.campanhas.length ? { campanhas: camp.campanhas } : {}),
      },
    };
  }
  if (!ehId(f.sharedSetId)) erros.sharedSetId = 'id numérico da lista compartilhada';
  if (f.subtipo === 'lista.adicionar') {
    const itens = lerItensDaLista(f);
    if (typeof itens === 'string') erros.itens = itens;
    if (Object.keys(erros).length || typeof itens === 'string') return falha(erros);
    return {
      ok: true,
      acao: { tipo: 'lista.adicionar', shared_set_id: idLimpo(f.sharedSetId), tipo_lista: f.tipoLista, itens: itens.itens },
    };
  }
  const camp = lerCampanhas(f.campanhas, true);
  if (typeof camp === 'string') erros.campanhas = camp;
  if (Object.keys(erros).length || typeof camp === 'string') return falha(erros);
  return { ok: true, acao: { tipo: 'lista.anexar', shared_set_id: idLimpo(f.sharedSetId), campanhas: camp.campanhas } };
}

export interface FormPlacements {
  escopo: EscopoDeExclusao;
  tipo: TipoDePlacement;
  valores: string;
}

export function montarPlacements(f: FormPlacements, ctx: ContextoDaCampanha): Montagem {
  const erros: Erros = {};
  if (f.escopo === 'campanha' && !ehId(ctx.campaignId)) erros.campaign_id = 'a campanha não tem id do Google';
  const r = lerPlacements(f.tipo, f.valores);
  if (typeof r === 'string') erros.valores = r;
  if (Object.keys(erros).length || typeof r === 'string') return falha(erros);
  return {
    ok: true,
    acao: {
      tipo: 'exclusao.placement',
      escopo: f.escopo,
      ...(f.escopo === 'campanha' ? { campaign_id: ctx.campaignId } : {}),
      itens: r.itens,
    },
  };
}

export interface FormIp {
  escopo: EscopoDeExclusao;
  ips: string;
}

export function montarIp(f: FormIp, ctx: ContextoDaCampanha): Montagem {
  const erros: Erros = {};
  if (f.escopo === 'campanha' && !ehId(ctx.campaignId)) erros.campaign_id = 'a campanha não tem id do Google';
  const brutos = listaDeIds(f.ips);
  const ips: string[] = [];
  for (const b of brutos) {
    const r = lerIp(b);
    if (typeof r === 'string') {
      erros.ips = r;
      break;
    }
    ips.push(r.ip);
  }
  if (!erros.ips) {
    if (!ips.length) erros.ips = 'digite ao menos um IP';
    else if (new Set(ips).size !== ips.length) erros.ips = 'IP repetido';
    else if (ips.length > LIMITE_IPS) erros.ips = `mais de ${LIMITE_IPS} IPs numa ação`;
  }
  if (Object.keys(erros).length) return falha(erros);
  return {
    ok: true,
    acao: { tipo: 'exclusao.ip', escopo: f.escopo, ...(f.escopo === 'campanha' ? { campaign_id: ctx.campaignId } : {}), ips },
  };
}

export type SubtipoDeAgenda = 'programacao.anuncios' | 'ajuste.dispositivo' | 'ajuste.horario';

export interface FormAgenda {
  subtipo: SubtipoDeAgenda;
  janelas: JanelaDoFormulario[];
  /** criterion_ids a remover, separados por vírgula. */
  remover: string;
  substituir: boolean;
  dispositivo: Dispositivo;
  /** Ajuste em % ("+20", "-100"). */
  ajuste: string;
  criterionId: string;
}

export function montarAgenda(f: FormAgenda, ctx: ContextoDaCampanha): Montagem {
  if (!ehId(ctx.campaignId)) return falha({ campaign_id: 'a campanha não tem id do Google' });
  if (f.subtipo === 'programacao.anuncios') {
    const erros: Erros = {};
    const r = lerJanelas(f.janelas);
    if (typeof r === 'string') erros.janelas = r;
    const remover = listaDeIds(f.remover);
    if (remover.some((i) => !ehId(i))) erros.remover = 'ids de critério são numéricos';
    if (f.substituir && remover.length) {
      erros.remover = 'substituir já remove todas as janelas atuais; deixe este campo vazio';
    }
    if (typeof r !== 'string' && !r.janelas.length && !remover.length && !f.substituir) {
      erros.janelas = 'programação sem janela a criar nem a remover';
    }
    if (Object.keys(erros).length || typeof r === 'string') return falha(erros);
    return {
      ok: true,
      acao: {
        tipo: 'programacao.anuncios',
        campaign_id: ctx.campaignId,
        janelas: r.janelas,
        ...(remover.length ? { remover } : {}),
        ...(f.substituir ? { substituir: true } : {}),
      },
    };
  }
  if (f.subtipo === 'ajuste.dispositivo') {
    const m = ajusteParaModificador(f.ajuste);
    const e = validarModificador(m, { zeroOk: true });
    if (e) return falha({ ajuste: e });
    return {
      ok: true,
      acao: { tipo: 'ajuste.dispositivo', campaign_id: ctx.campaignId, dispositivo: f.dispositivo, modificador: m as number },
    };
  }
  const erros: Erros = {};
  if (!ehId(f.criterionId)) erros.criterionId = 'id numérico da janela (critério)';
  const m = ajusteParaModificador(f.ajuste);
  const e = validarModificador(m, { zeroOk: false });
  if (e) erros.ajuste = e;
  if (Object.keys(erros).length) return falha(erros);
  return {
    ok: true,
    acao: { tipo: 'ajuste.horario', campaign_id: ctx.campaignId, criterion_id: idLimpo(f.criterionId), modificador: m as number },
  };
}

const RN_RECOMENDACAO = /^customers\/\d+\/recommendations\/[A-Za-z0-9+=_\-~]+$/;

export function montarRecomendacao(
  tipo: 'recomendacao.aplicar' | 'recomendacao.dispensar',
  recurso: string,
): Montagem {
  if (!RN_RECOMENDACAO.test(String(recurso ?? ''))) {
    return falha({ recurso: 'resource name de recomendação inválido' });
  }
  return { ok: true, acao: { tipo, recurso } };
}

// ── o pedido inteiro ────────────────────────────────────────────────────────

export const VALIDADE_PADRAO_HORAS = 24;

export function validarMotivo(motivo: string): string | null {
  return motivo.trim() ? null : 'diga por que mudar — é o que quem aprova vai ler';
}

export function validarValidade(horas: string): string | null {
  if (!horas.trim()) return null;
  const n = Number(horas);
  return Number.isInteger(n) && n >= 1 && n <= 168 ? null : 'validade entre 1 e 168 horas';
}
