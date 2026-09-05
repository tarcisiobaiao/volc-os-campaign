/** Contrato único do rascunho de criação Meta.
 *
 * A bancada inteira lê e escreve por aqui: o formulário, o resumo lateral, a
 * revisão e o corpo enviado ao backend. Manter uma fonte só evita o defeito
 * clássico de a tela dizer uma coisa e o payload compilado dizer outra.
 *
 * O navegador nunca vê identificador real: `accountRef`, `pageRef`, `assetRef`
 * e `videoRef` são referências opacas que só o backend sabe resolver.
 */
import type { PlanoMetaPausadoInput } from '@/lib/pautadorApi';

export const LIMITE_VARIACOES = 10;

export type ModoCriativo = 'single' | 'batch' | 'flexible';
export type MidiaDaVariacao = 'image' | 'video';
export type EstadoDaEtapa = 'pendente' | 'pronto' | 'bloqueado' | 'validado';

export type EtapaId =
  | 'base' | 'campanha' | 'orcamento' | 'conjunto'
  | 'publico' | 'criativo' | 'mensuracao' | 'revisao';

export interface VariacaoDraft {
  key: string;
  midia: MidiaDaVariacao;
  assetRef: string;
  videoRef: string;
  creativeName: string;
  adName: string;
  message: string;
  headline: string;
  description: string;
  cta: string;
}

export interface Draft {
  accountRef: string;
  pageRef: string;
  campaignName: string;
  adsetName: string;
  destinationUrl: string;
  budgetBrl: string;
  startTime: string;
  categoryConfirmed: boolean;
  budgetSharing: boolean;
  /** Escolha explícita de Advantage+ público. Nunca "não declarado": omitir o
   *  campo faz a Meta assumir que o operador aceitou. */
  advantageAudience: boolean;
  creativeMode: ModoCriativo;
  variations: VariacaoDraft[];
}

/** O que o servidor declarou saber fazer nesta versão do contrato. */
export interface CapacidadesDaBancada {
  validateOnly: boolean;
  loteEstatico: boolean;
  video: boolean;
  videoMotivo: string | null;
  flexivel: boolean;
  flexivelMotivo: string | null;
  /** Causa declarada pelo servidor para o compartilhamento de verba entre
   *  conjuntos estar fechado NESTA receita. A capacidade segue planejada; o
   *  que não existe é a escolha do operador dentro de uma receita de conjunto
   *  único — a Meta recusou 100/4005 na validação real de 05/09/2026. */
  budgetSharingMotivo: string | null;
  /** O servidor autoriza criar objetos reais em estado PAUSED?
   *
   * ⚠️ Fechado por padrão, e o padrão é o que importa: um erro de leitura da
   * resposta precisa deixar a criação FECHADA, nunca aberta. */
  criarPausada: boolean;
  /** Qual autorização falta, em linguagem de operador. Nunca o nome de uma
   *  variável de ambiente — a tela explica a causa, não a configuração. */
  criarPausadaMotivo: string | null;
}

export const CAPACIDADES_FECHADAS: CapacidadesDaBancada = {
  validateOnly: false,
  loteEstatico: false,
  video: false,
  videoMotivo: null,
  flexivel: false,
  flexivelMotivo: null,
  budgetSharingMotivo: null,
  criarPausada: false,
  criarPausadaMotivo: null,
};

/** A frase que o operador digita para liberar a criação.
 *
 * Comparada exatamente, aqui e no servidor. Aceitar "criar pausada" ou "sim"
 * transformaria um gesto deliberado num reflexo — e o ponto do gesto é
 * justamente exigir que a pessoa pare para escrevê-lo. */
export const CONFIRMACAO_DE_CRIACAO = 'CRIAR PAUSADA';

export function confirmacaoDeCriacaoValida(digitado: string): boolean {
  return String(digitado ?? '').trim() === CONFIRMACAO_DE_CRIACAO;
}

/** Converte a digitação do operador em centavos, sem inventar cem vezes a verba.
 *
 * O separador decimal é o ÚLTIMO separador digitado. `10,00`, `10.00` e `10`
 * valem dez reais; `1.000` e `1.234,56` seguem a convenção pt-BR de milhar.
 * A tela sempre exibe de volta o valor interpretado, para que a ambiguidade
 * apareça antes de virar orçamento.
 */
export function reaisParaMinor(entrada: string): number {
  const bruto = String(entrada ?? '').trim();
  // ⚠️ Um sinal negativo não pode ser apagado em silêncio: "-10,00" viraria
  // dez reais de orçamento. Entrada com sinal é entrada inválida.
  if (/[-\u2212]/.test(bruto)) return 0;
  const limpo = bruto.replace(/[^\d.,]/g, '');
  if (!limpo) return 0;
  const ultimaVirgula = limpo.lastIndexOf(',');
  const ultimoPonto = limpo.lastIndexOf('.');
  let corte = -1;
  if (ultimaVirgula >= 0 && ultimoPonto >= 0) {
    corte = Math.max(ultimaVirgula, ultimoPonto);
  } else if (ultimaVirgula >= 0) {
    corte = ultimaVirgula;
  } else if (ultimoPonto >= 0) {
    // Um ponto único com exatamente três casas é milhar em pt-BR (`1.000`);
    // qualquer outra contagem é decimal (`10.00`, `10.5`).
    corte = /^\d{1,3}\.\d{3}$/.test(limpo) ? -1 : ultimoPonto;
  }
  const inteiro = (corte < 0 ? limpo : limpo.slice(0, corte)).replace(/\D/g, '');
  const fracao = corte < 0 ? '' : limpo.slice(corte + 1).replace(/\D/g, '');
  const numero = Number(`${inteiro || '0'}.${fracao || '0'}`);
  if (!Number.isFinite(numero) || numero <= 0) return 0;
  return Math.round(numero * 100);
}

export function formatarBrl(minor: number): string {
  return (minor / 100).toLocaleString('pt-BR', {
    style: 'currency', currency: 'BRL', minimumFractionDigits: 2,
  });
}

/** Primeira chave livre da sequência. Remover a linha do meio e adicionar
 *  outra não pode recriar uma `variation_key` que já existe: o backend recusa
 *  o lote inteiro com META_STATIC_BATCH_DUPLICATE_KEY. */
export function proximaChave(existentes: readonly string[]): string {
  const usadas = new Set(existentes);
  for (let i = 1; i <= 999; i += 1) {
    const chave = `variation-${String(i).padStart(3, '0')}`;
    if (!usadas.has(chave)) return chave;
  }
  return `variation-${Date.now()}`;
}

/** Limite do contrato backend para nome de criativo e de anúncio. */
export const LIMITE_NOME = 400;

/** O backend compara nomes JÁ aparados: " Criativo " e "Criativo" colidem lá.
 *  Comparar cru aqui deixaria a revisão dizer "pronto" sobre um lote que o
 *  compilador recusa com META_STATIC_BATCH_DUPLICATE_NAME. */
export function nomeCanonico(nome: string): string {
  return String(nome ?? '').trim();
}

export function nomeUnico(base: string, existentes: readonly string[]): string {
  const usados = new Set(existentes.map(nomeCanonico));
  const raiz = nomeCanonico(base);
  if (raiz && !usados.has(raiz)) return raiz.slice(0, LIMITE_NOME);
  for (let i = 2; i <= 999; i += 1) {
    const sufixo = ` · ${i}`;
    const candidato = `${raiz.slice(0, LIMITE_NOME - sufixo.length)}${sufixo}`;
    if (!usados.has(candidato)) return candidato;
  }
  return `${raiz.slice(0, LIMITE_NOME - 16)} · ${existentes.length + 1}`;
}

export function variacaoInicial(chave: string, numero: number): VariacaoDraft {
  return {
    key: chave,
    midia: 'image',
    assetRef: '',
    videoRef: '',
    creativeName: `Criativo estático · v${numero}`,
    adName: `Anúncio estático · v${numero}`,
    message: 'Descubra as informações importantes antes de decidir.',
    headline: 'Entenda como funciona',
    description: 'Conteúdo informativo e independente.',
    cta: 'LEARN_MORE',
  };
}

export function variacaoCompleta(variacao: VariacaoDraft): boolean {
  const midiaOk = variacao.midia === 'image'
    ? Boolean(variacao.assetRef)
    : Boolean(variacao.videoRef);
  return Boolean(
    midiaOk && variacao.creativeName.trim() && variacao.adName.trim()
    && variacao.message.trim() && variacao.headline.trim()
    && variacao.description.trim() && variacao.cta,
  );
}

/** As variações que o modo escolhido realmente emite.
 *
 * Escolher "Individual" precisa significar UM anúncio, não uma etiqueta sobre
 * um lote que continua sendo enviado inteiro. */
export function variacoesEmitidas(draft: Draft): VariacaoDraft[] {
  if (draft.creativeMode === 'single') return draft.variations.slice(0, 1);
  if (draft.creativeMode === 'batch') return draft.variations.slice(0, LIMITE_VARIACOES);
  return [];
}

export function destinoValido(url: string): boolean {
  try {
    const partes = new URL(url.trim());
    return partes.protocol === 'https:' && Boolean(partes.hostname);
  } catch {
    return false;
  }
}

export function dominioDoDestino(url: string): string | null {
  try {
    return new URL(url.trim()).hostname.toLowerCase() || null;
  } catch {
    return null;
  }
}

export function inicioEmIso(startTime: string): string | null {
  if (!startTime) return null;
  const instante = new Date(startTime);
  return Number.isNaN(instante.getTime()) ? null : instante.toISOString();
}

export function paraPlano(draft: Draft): PlanoMetaPausadoInput {
  const emitidas = variacoesEmitidas(draft);
  const primeira = emitidas[0] ?? draft.variations[0];
  return {
    account_ref: draft.accountRef,
    page_ref: draft.pageRef,
    asset_ref: primeira?.assetRef ?? '',
    campaign_name: draft.campaignName,
    adset_name: draft.adsetName,
    creative_name: primeira?.creativeName ?? '',
    ad_name: primeira?.adName ?? '',
    destination_url: draft.destinationUrl,
    message: primeira?.message ?? '',
    headline: primeira?.headline ?? '',
    description: primeira?.description ?? '',
    daily_budget_minor: reaisParaMinor(draft.budgetBrl),
    start_time: inicioEmIso(draft.startTime) ?? '',
    special_ad_categories: [],
    special_categories_confirmed: draft.categoryConfirmed,
    is_adset_budget_sharing_enabled: draft.budgetSharing,
    advantage_audience: draft.advantageAudience,
    call_to_action_type: primeira?.cta ?? 'LEARN_MORE',
    variations: emitidas.map((item) => ({
      variation_key: item.key,
      asset_ref: item.assetRef,
      creative_name: item.creativeName,
      ad_name: item.adName,
      message: item.message,
      headline: item.headline,
      description: item.description,
      call_to_action_type: item.cta,
    })),
  };
}

export interface ContextoDeProntidao {
  capacidades: CapacidadesDaBancada;
  compilado: boolean;
  validado: boolean;
}

/** Estado por etapa. Quatro estados distinguíveis por glifo e palavra, nunca
 *  só por cor: pendente, pronto, bloqueado e validado. */
export function prontidaoDasEtapas(
  draft: Draft,
  contexto: ContextoDeProntidao,
): Record<EtapaId, EstadoDaEtapa> {
  const emitidas = variacoesEmitidas(draft);
  const criativoBloqueado = draft.creativeMode === 'flexible'
    || (draft.creativeMode === 'batch' && !contexto.capacidades.loteEstatico)
    || emitidas.some((item) => item.midia === 'video' && !contexto.capacidades.video);
  const criativos = emitidas.map((item) => nomeCanonico(item.creativeName));
  const anuncios = emitidas.map((item) => nomeCanonico(item.adName));
  const nomesOk = new Set(criativos).size === criativos.length
    && new Set(anuncios).size === anuncios.length
    && [...criativos, ...anuncios].every(
      (nome) => nome.length > 0 && nome.length <= LIMITE_NOME);
  const criativoPronto = emitidas.length > 0
    && emitidas.length <= LIMITE_VARIACOES
    && emitidas.every(variacaoCompleta)
    && nomesOk;
  return {
    base: draft.accountRef && draft.pageRef ? 'pronto' : 'pendente',
    campanha: draft.campaignName.trim() && draft.categoryConfirmed ? 'pronto' : 'pendente',
    orcamento: reaisParaMinor(draft.budgetBrl) > 0 && inicioEmIso(draft.startTime)
      ? 'pronto' : 'pendente',
    conjunto: draft.adsetName.trim() ? 'pronto' : 'pendente',
    publico: 'pronto',
    criativo: criativoBloqueado ? 'bloqueado' : criativoPronto ? 'pronto' : 'pendente',
    mensuracao: destinoValido(draft.destinationUrl) ? 'pronto' : 'pendente',
    revisao: contexto.validado ? 'validado' : contexto.compilado ? 'pronto' : 'pendente',
  };
}

export function prontoParaCompilar(
  draft: Draft,
  capacidades: CapacidadesDaBancada,
): boolean {
  const estados = prontidaoDasEtapas(draft, {
    capacidades, compilado: false, validado: false,
  });
  return (['base', 'campanha', 'orcamento', 'conjunto', 'criativo', 'mensuracao'] as const)
    .every((etapa) => estados[etapa] === 'pronto');
}
