/** Contrato único do rascunho de criação Meta.
 *
 * A bancada inteira lê e escreve por aqui: o formulário, o resumo lateral, a
 * revisão e o corpo enviado ao backend. Manter uma fonte só evita o defeito
 * clássico de a tela dizer uma coisa e o payload compilado dizer outra.
 *
 * O navegador nunca vê identificador real: `accountRef`, `pageRef`, `assetRef`
 * e `videoRef` são referências opacas que só o backend sabe resolver.
 *
 * ## ⚠️ DUAS VERSÕES DE CONTRATO, E A ESCOLHA É VISÍVEL
 *
 * O backend manteve as duas de propósito (`trafego_meta_validacao.py`, comentário
 * "Contrato V2"): o V1 descreve UMA campanha com UM conjunto, verba diária no
 * conjunto, Brasil inteiro, Facebook-only — e é a única receita que a Meta
 * aceitou em 05/09/2026, com aprovação e criação PAUSED ligadas a ela. O V2
 * descreve campanha + N conjuntos + N anúncios, ABO/CBO, público de verdade e
 * mensuração com propósito — e tem apenas `compilar` e `validar`.
 *
 * `contratoDoPlano` decide qual versão este rascunho fala, e a decisão é
 * DERIVADA DA FORMA DO PLANO, nunca de um interruptor escondido: um plano que
 * cabe inteiro na receita provada continua indo pelo V1 (e por isso continua
 * podendo nascer); qualquer recurso que só existe no V2 leva o plano para o V2
 * (e a criação fecha, porque não existe rota de aprovação V2). A tela mostra a
 * versão e o motivo — um operador nunca precisa adivinhar por que o botão de
 * criar sumiu.
 */
import type { PlanoMetaPausadoInput, PlanoMetaV2Input } from '@/lib/pautadorApi';

export const LIMITE_VARIACOES = 10;
/** Espelha `contrato_v2.MAX_CONJUNTOS`. Limite operacional do produto, não da Meta. */
export const LIMITE_CONJUNTOS = 10;

/** Faixa etária que a receita aceita (`contrato_v2.IDADE_MINIMA/MAXIMA`).
 *  Serve de fallback enquanto `/v2/receitas` não foi lido; o servidor manda. */
export const IDADE_MINIMA_PADRAO = 18;
export const IDADE_MAXIMA_PADRAO = 65;

/** A receita com prova remota aceita — e a única que o V1 sabe emitir. */
export const RECEITA_PADRAO = 'TRAFFIC_WEBSITE_LPV_STATIC';

export type ModoCriativo = 'single' | 'batch' | 'flexible';
export type MidiaDaVariacao = 'image' | 'video';
export type EstadoDaEtapa = 'pendente' | 'pronto' | 'bloqueado' | 'validado';

export type EtapaId =
  | 'base' | 'campanha' | 'orcamento' | 'conjunto'
  | 'publico' | 'criativo' | 'mensuracao' | 'revisao';

// ─────────────────────────────────────────────────────────────────────────────
// Vocabulário do V2. Cada união abaixo é a TRANSCRIÇÃO do `pattern` do DTO em
// `trafego_meta_validacao.py`; inventar um valor aqui produziria 422 com o nome
// do campo, e o operador leria um erro de servidor por causa de um enum nosso.
// ─────────────────────────────────────────────────────────────────────────────
export type NivelDeOrcamento = 'ADSET' | 'CAMPAIGN';
export type PeriodoDeOrcamento = 'DAILY' | 'LIFETIME';
export type ModoDePublico = 'BROAD' | 'MANUAL' | 'EXISTING_CUSTOM' | 'EXISTING_LOOKALIKE';
export type ModoDePosicionamento = 'FACEBOOK_ONLY' | 'MANUAL';
export type PropositoDeMensuracao = 'REPORT_ONLY' | 'OPTIMIZE';
export type TipoDeFonteDeMensuracao = 'PIXEL' | 'DATASET';

/** As plataformas que a Graph aceita em `publisher_platforms` (v26).
 *
 * ⚠️ `instagram` exige identidade validada: o backend recusa com
 * `META_INSTAGRAM_IDENTITY_REQUIRED` quando `instagram_actor_ref` não viaja. */
export const PLATAFORMAS: readonly [string, string][] = [
  ['facebook', 'Facebook'],
  ['instagram', 'Instagram'],
  ['audience_network', 'Audience Network'],
  ['messenger', 'Messenger'],
  ['threads', 'Threads'],
];

export interface PontoComRaio {
  latitude: string;
  longitude: string;
  /** Inteiro em `distanceUnit`. O DTO limita a 80. */
  raio: string;
  unidade: 'kilometer' | 'mile';
}

export interface GeografiaDraft {
  /** O TEXTO digitado, não a lista já interpretada.
   *
   * ⚠️ Guardar a lista faria o campo se reescrever a cada tecla: digitar "BR, U"
   * viraria "BR" no meio da digitação, o cursor saltaria para o fim e o "S"
   * seguinte cairia no lugar errado. É o mesmo defeito de `A31` no orçamento, e
   * a cura é a mesma: o texto é o estado, a interpretação aparece ao lado.
   *
   * Códigos ISO-3166 alfa-2. Não é catálogo da Meta — é norma pública — e por
   * isso pode ser digitado sem inventar chave de provedor. */
  paisesTexto: string;
  exclusoesTexto: string;
  pontos: PontoComRaio[];
  /** Região, cidade e CEP ESCOLHIDOS DO CATÁLOGO da Meta.
   *
   * ⚠️ Guardamos o item inteiro, não a `key` solta, e a diferença é a garantia:
   * um item só entra aqui vindo de `/catalogos/geografia`, então não existe
   * caminho pelo qual um texto digitado vire `region_keys`. O nome viaja junto
   * para a revisão poder dizer "Curitiba" em vez de um número. */
  lugares: LugarEscolhido[];
}

/** Um lugar do catálogo, com a decisão do operador sobre ele. */
export interface LugarEscolhido {
  /** A chave CANÔNICA que veio do catálogo. Nunca digitada. */
  key: string;
  nome: string;
  /** `region`, `city` ou `zip`, como a Meta classificou. */
  tipo: string;
  /** `false` = alcançar aqui. `true` = não alcançar aqui. Excluir é decisão
   *  tão material quanto incluir, e por isso mora no mesmo item. */
  excluido: boolean;
}

export interface PublicoDraft {
  modo: ModoDePublico;
  geo: GeografiaDraft;
  idadeMin: number;
  idadeMax: number;
  /** Referências OPACAS de públicos/idiomas/interesses existentes na conta.
   *  Ficam vazias enquanto não houver rota de catálogo — ver `BLOQUEIOS`. */
  incluirRefs: string[];
  excluirRefs: string[];
  lookalikeRefs: string[];
  interesseRefs: string[];
  localeRefs: string[];
  /** Escolha explícita de Advantage+ público. Nunca "não declarado": omitir o
   *  campo faz a Meta assumir 1 desde a v23.0, quer dizer, LIGA a expansão. */
  expansao: boolean;
}

export interface MensuracaoDraft {
  proposito: PropositoDeMensuracao;
  /** `''` = nenhuma fonte escolhida. `null` no corpo. */
  fonteTipo: TipoDeFonteDeMensuracao | '';
  fonteRef: string;
  conversaoRef: string;
  eventoPadrao: string;
}

export interface ConjuntoDraft {
  /** `adset_key`: identidade ESTÁVEL. Reordenar a lista não a troca — é ela
   *  que amarra cada anúncio ao conjunto certo (`F34`). */
  key: string;
  nome: string;
  /** `datetime-local`. Vira ISO com fuso explícito em `inicioEmIso`. */
  startTime: string;
  endTime: string;
  /** Texto DIGITADO, não número. Guardar o número reinterpretaria "1.0" a cada
   *  tecla e o campo perderia o foco no primeiro dígito (`A31`). */
  orcamentoBrl: string;
  publico: PublicoDraft;
  posicionamentoModo: ModoDePosicionamento;
  posicionamentoValores: string[];
  mensuracao: MensuracaoDraft;
}

export interface VariacaoDraft {
  key: string;
  /** A qual conjunto este anúncio pertence. Escolha EXPLÍCITA (`F34`). */
  adsetKey: string;
  midia: MidiaDaVariacao;
  assetRef: string;
  videoRef: string;
  creativeName: string;
  adName: string;
  message: string;
  headline: string;
  description: string;
  cta: string;
  assetRightsConfirmed: boolean;
  thirdPartyIdentityCleared: boolean;
  assetPolicyConfirmedAt: string;
}

export interface Draft {
  /** `recipe_id` do registro do servidor. O V1 só sabe emitir a padrão. */
  recipeId: string;
  accountRef: string;
  pageRef: string;
  /** Identidade do Instagram. Sem rota de catálogo nesta árvore, fica vazia —
   *  e é por isso que o posicionamento no Instagram aparece indisponível. */
  instagramActorRef: string;
  campaignName: string;
  destinationUrl: string;
  nivelDeOrcamento: NivelDeOrcamento;
  periodoDeOrcamento: PeriodoDeOrcamento;
  /** Verba da CAMPANHA (CBO). Em ABO ela não viaja. Texto digitado (`A31`). */
  budgetBrl: string;
  categoryConfirmed: boolean;
  creativeMode: ModoCriativo;
  conjuntos: ConjuntoDraft[];
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

/** As capacidades que ESTA árvore não tem, com a causa em linguagem de operador.
 *
 * ⚠️ Elas não são "ainda não implementei": são rotas que o backend não expõe.
 * Um seletor de público personalizado sem catálogo seria um campo de texto
 * pedindo um id que o operador não tem como conhecer — e um id digitado que
 * virasse referência seria segmentação inventada com cara de escolha dele.
 * Ver `meta_execucao/publicos.py`: resolver uma referência é LISTAR o catálogo
 * da conta, e não existe rota HTTP que liste. */
export const BLOQUEIOS = {
  catalogoDePublicos:
    'Só entram aqui públicos que JÁ EXISTEM nesta conta, lidos do catálogo por '
    + 'clique. Esta bancada não cria público nem semelhante, e nenhuma lista de '
    + 'pessoas atravessa: o que viaja é a referência opaca do objeto.',
  catalogoDeGeografia:
    'Região, cidade e CEP vêm da BUSCA no catálogo da Meta, e é a chave devolvida '
    + 'por ela que viaja no plano. O texto que você digita é busca, nunca chave: '
    + 'se virasse, uma segmentação inventada teria cara de escolha sua.',
  interessesEIdiomas:
    'Segmentação detalhada por interesse e por idioma ainda não tem rota de '
    + 'catálogo neste servidor. Digitar um identificador à mão viraria '
    + 'segmentação inventada com cara de escolha sua.',
  identidadeInstagram:
    'O posicionamento no Instagram exige uma identidade validada, e esta bancada '
    + 'ainda não lê identidades do Instagram da conta. O backend recusa o plano '
    + 'sem ela (META_INSTAGRAM_IDENTITY_REQUIRED).',
  fonteDeMensuracao:
    'Otimizar por conversão exige escolher o pixel ou dataset da conta e um evento '
    + 'elegível. Relatar não exige fonte nenhuma: ele não toca o que a campanha '
    + 'otimiza.',
  publicoAmploNaoAceitaSalvos:
    'Público amplo é geografia e idade, sem público salvo e sem segmentação '
    + 'detalhada. Para usar os públicos escolhidos, mude o modo para Manual, '
    + 'Personalizado ou Semelhante — a Meta recusa a combinação '
    + '(META_AUDIENCE_MODE_CONFLICT).',
  videoNoCorpo:
    'Nenhum dos dois contratos transporta vídeo: tanto `variations[]` no V1 '
    + 'quanto `ads[]` no V2 têm só `asset_ref`. Um anúncio em vídeo sairia com a '
    + 'peça vazia, e a Meta recusaria o lote inteiro.',
} as const;

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
  if (/[-−]/.test(bruto)) return 0;
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
 *  outra não pode recriar uma chave que já existe: o backend recusa o lote
 *  inteiro com META_STATIC_BATCH_DUPLICATE_KEY (anúncios) ou
 *  META_ADSET_DUPLICATE_KEY (conjuntos).
 *
 *  ⚠️ O prefixo é parâmetro porque `adset_key` e `variation_key` vivem em
 *  espaços de nome DIFERENTES no plano: `adset-001` e `variation-001` podem
 *  coexistir, e misturá-los num gerador só faria a segunda lista pular
 *  números sem motivo visível. */
export function proximaChave(
  existentes: readonly string[], prefixo: 'variation' | 'adset' = 'variation',
): string {
  const usadas = new Set(existentes);
  for (let i = 1; i <= 999; i += 1) {
    const chave = `${prefixo}-${String(i).padStart(3, '0')}`;
    if (!usadas.has(chave)) return chave;
  }
  return `${prefixo}-${Date.now()}`;
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

export function publicoInicial(): PublicoDraft {
  return {
    modo: 'BROAD',
    geo: { paisesTexto: 'BR', exclusoesTexto: '', pontos: [], lugares: [] },
    idadeMin: IDADE_MINIMA_PADRAO,
    idadeMax: IDADE_MAXIMA_PADRAO,
    incluirRefs: [], excluirRefs: [], lookalikeRefs: [], interesseRefs: [], localeRefs: [],
    // ⚠️ Recusado por padrão. O default nunca pode ser a opção que amplia
    // alcance sem o operador pedir.
    expansao: false,
  };
}

export function mensuracaoInicial(): MensuracaoDraft {
  return {
    proposito: 'REPORT_ONLY', fonteTipo: '', fonteRef: '',
    conversaoRef: '', eventoPadrao: '',
  };
}

export function conjuntoInicial(
  chave: string, nome: string, startTime: string, orcamentoBrl = '10,00',
): ConjuntoDraft {
  return {
    key: chave,
    nome,
    startTime,
    endTime: '',
    orcamentoBrl,
    publico: publicoInicial(),
    posicionamentoModo: 'FACEBOOK_ONLY',
    posicionamentoValores: [],
    mensuracao: mensuracaoInicial(),
  };
}

export function variacaoInicial(
  chave: string, numero: number, adsetKey: string,
): VariacaoDraft {
  return {
    key: chave,
    adsetKey,
    midia: 'image',
    assetRef: '',
    videoRef: '',
    creativeName: `Criativo estático · v${numero}`,
    adName: `Anúncio estático · v${numero}`,
    message: 'Descubra as informações importantes antes de decidir.',
    headline: 'Entenda como funciona',
    description: 'Conteúdo informativo e independente.',
    cta: 'LEARN_MORE',
    assetRightsConfirmed: false,
    thirdPartyIdentityCleared: false,
    assetPolicyConfirmedAt: '',
  };
}

export function variacaoCompleta(variacao: VariacaoDraft): boolean {
  // ⚠️ VÍDEO NUNCA É COMPLETO, e a razão não é a capacidade do servidor.
  // Nem `variations[]` (V1) nem `ads[]` (V2) têm campo de vídeo: o corpo sairia
  // com `asset_ref` vazio. Antes isto dependia só de `capacidades.video`, e um
  // servidor que anunciasse o vídeo como disponível faria a bancada emitir uma
  // peça vazia. A recusa passou a ser do CONTRATO, que é onde ela é verdadeira.
  if (variacao.midia === 'video') return false;
  return Boolean(
    variacao.assetRef && variacao.adsetKey
    && variacao.creativeName.trim() && variacao.adName.trim()
    && variacao.message.trim() && variacao.headline.trim()
    && variacao.description.trim() && variacao.cta
    && variacao.assetRightsConfirmed && variacao.thirdPartyIdentityCleared
    && variacao.assetPolicyConfirmedAt,
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

/** O código ISO-3166 alfa-2, ou `null`. Nunca um texto livre virando país. */
export function paisCanonico(entrada: string): string | null {
  const bruto = String(entrada ?? '').trim().toUpperCase();
  return /^[A-Z]{2}$/.test(bruto) ? bruto : null;
}

/** Lista de países a partir de uma digitação separada por vírgula/espaço.
 *  Descarta o que não é ISO-2 em vez de inventar um código de duas letras. */
export function paisesDeTexto(entrada: string): string[] {
  const vistos = new Set<string>();
  for (const parte of String(entrada ?? '').split(/[,\s;]+/)) {
    const codigo = paisCanonico(parte);
    if (codigo) vistos.add(codigo);
  }
  return [...vistos];
}

/** Os países realmente incluídos, já canônicos. */
export function paisesIncluidos(geo: GeografiaDraft): string[] {
  return paisesDeTexto(geo.paisesTexto);
}

/** Os países realmente excluídos, já canônicos. */
export function paisesExcluidos(geo: GeografiaDraft): string[] {
  return paisesDeTexto(geo.exclusoesTexto);
}

/** As chaves de UM tipo, do lado incluído ou do excluído.
 *
 * ⚠️ Sempre derivadas de `lugares`, que só é alimentado pelo catálogo. Não
 * existe outra porta de entrada para `region_keys`/`city_keys`/`zip_keys`. */
export function chavesDeLugar(
  geo: GeografiaDraft, tipo: string, excluido: boolean,
): string[] {
  return [...new Set(geo.lugares
    .filter((item) => item.tipo === tipo && item.excluido === excluido)
    .map((item) => item.key))];
}

export function geografiaTemInclusao(geo: GeografiaDraft): boolean {
  return paisesIncluidos(geo).length > 0
    || geo.pontos.length > 0
    || geo.lugares.some((item) => !item.excluido);
}

/** A frase de `A16`, decidida ANTES de o servidor responder.
 *
 * ⚠️ É uma PROJEÇÃO, não a autoridade: quando o `resumo` do servidor existe, é
 * ele que manda (`resumo.conjuntos[].promete_alcance_exclusivo`). Esta função
 * serve o intervalo em que ainda não houve compilação, e repete a mesma regra
 * de `contrato_v2.PublicoMeta.promete_alcance_exclusivo`: com a expansão ligada
 * a Meta trata o público selecionado como SUGESTÃO e alcança fora dele. */
export function prometeAlcanceExclusivo(publico: PublicoDraft): boolean {
  const temPublicoProprio = publico.incluirRefs.length > 0 || publico.lookalikeRefs.length > 0;
  return temPublicoProprio && !publico.expansao;
}

/** Onde a verba mora, na frase que o servidor devolve em `resumo.orcamento`.
 *  Usada só enquanto não existe resumo do servidor — e a tela diz isso. */
export function ondeAVerbaMoraLocal(draft: Draft): string {
  return draft.nivelDeOrcamento === 'CAMPAIGN'
    ? 'na campanha (CBO)' : 'em cada conjunto (ABO)';
}

// ─────────────────────────────────────────────────────────────────────────────
// A ESCOLHA DO CONTRATO
// ─────────────────────────────────────────────────────────────────────────────

export type VersaoDoContrato = 'V1' | 'V2';

/** Qual contrato este rascunho fala, e por quê.
 *
 * ⚠️ `motivos` vazio ⇒ V1. Cada motivo é um recurso que SÓ existe no V2, escrito
 * em linguagem de operador porque é ele quem lê a consequência: no V2 a
 * validação continua aberta (é ela que produz a prova), e a criação PAUSED não
 * existe, porque o backend não tem rota de aprovação para o plano V2. */
export function contratoDoPlano(draft: Draft): {
  contrato: VersaoDoContrato; motivos: string[];
} {
  const motivos: string[] = [];
  if (draft.recipeId !== RECEITA_PADRAO) {
    motivos.push('a receita escolhida não é a receita de tráfego provada');
  }
  if (draft.conjuntos.length !== 1) {
    motivos.push(`o plano tem ${draft.conjuntos.length} conjuntos`);
  }
  if (draft.nivelDeOrcamento !== 'ADSET') {
    motivos.push('a verba mora na campanha (CBO)');
  }
  if (draft.periodoDeOrcamento !== 'DAILY') {
    motivos.push('a verba é total, não diária');
  }
  if (draft.instagramActorRef) motivos.push('há identidade do Instagram no plano');
  for (const conjunto of draft.conjuntos) {
    const p = conjunto.publico;
    if (p.modo !== 'BROAD') motivos.push(`o público do conjunto "${conjunto.nome}" não é amplo`);
    const incluidos = paisesIncluidos(p.geo);
    if (incluidos.length !== 1 || incluidos[0] !== 'BR') {
      motivos.push(`a geografia do conjunto "${conjunto.nome}" não é só o Brasil`);
    }
    if (paisesExcluidos(p.geo).length || p.geo.pontos.length) {
      motivos.push(`o conjunto "${conjunto.nome}" tem exclusão ou raio`);
    }
    if (p.geo.lugares.length) {
      motivos.push(`o conjunto "${conjunto.nome}" escolhe região, cidade ou CEP`);
    }
    if (p.incluirRefs.length || p.excluirRefs.length || p.lookalikeRefs.length) {
      motivos.push(`o conjunto "${conjunto.nome}" usa públicos salvos da conta`);
    }
    if (p.idadeMin !== IDADE_MINIMA_PADRAO || p.idadeMax !== IDADE_MAXIMA_PADRAO) {
      motivos.push(`a faixa etária do conjunto "${conjunto.nome}" não é a da receita`);
    }
    if (p.expansao) motivos.push(`o conjunto "${conjunto.nome}" aceita a expansão Advantage+`);
    if (conjunto.posicionamentoModo !== 'FACEBOOK_ONLY') {
      motivos.push(`o conjunto "${conjunto.nome}" escolhe posicionamentos à mão`);
    }
    if (conjunto.mensuracao.proposito !== 'REPORT_ONLY'
      || conjunto.mensuracao.conversaoRef || conjunto.mensuracao.fonteRef) {
      motivos.push(`o conjunto "${conjunto.nome}" declara mensuração`);
    }
    if (conjunto.endTime) motivos.push(`o conjunto "${conjunto.nome}" tem data de término`);
  }
  return { contrato: motivos.length ? 'V2' : 'V1', motivos: [...new Set(motivos)] };
}

// ─────────────────────────────────────────────────────────────────────────────
// OS CORPOS
// ─────────────────────────────────────────────────────────────────────────────

/** O corpo do contrato V1 — a receita provada, e a única que pode NASCER.
 *
 * ⚠️ Os campos de topo (`asset_ref`, `creative_name`, `message`…) REPETEM a
 * primeira variação porque o DTO V1 os exige: eles são o plano de anúncio único
 * e `variations[]` é a extensão em lote. Não é duplicação por descuido, é a
 * forma daquele contrato — e é exatamente por isso que o V2 não a tem: lá
 * `ads[]` é a única fonte. Mexer aqui produziria 422 numa rota que ainda
 * sustenta aprovação e criação PAUSED. */
export function paraPlano(draft: Draft): PlanoMetaPausadoInput {
  const emitidas = variacoesEmitidas(draft);
  const primeira = emitidas[0] ?? draft.variations[0];
  const conjunto = draft.conjuntos[0];
  return {
    account_ref: draft.accountRef,
    page_ref: draft.pageRef,
    asset_ref: primeira?.assetRef ?? '',
    campaign_name: draft.campaignName,
    adset_name: conjunto?.nome ?? '',
    creative_name: primeira?.creativeName ?? '',
    ad_name: primeira?.adName ?? '',
    destination_url: draft.destinationUrl,
    message: primeira?.message ?? '',
    headline: primeira?.headline ?? '',
    description: primeira?.description ?? '',
    daily_budget_minor: reaisParaMinor(conjunto?.orcamentoBrl ?? ''),
    start_time: inicioEmIso(conjunto?.startTime ?? '') ?? '',
    // ⚠️ Categoria especial: a lista viaja VAZIA e não existe caminho para
    // declarar uma. O backend recusa qualquer categoria com
    // META_SPECIAL_CATEGORY_RECIPE_UNPROVEN, então um seletor aqui ofereceria
    // uma escolha que a rota nega. A caixa marcada afirma a AUSÊNCIA delas.
    special_ad_categories: [],
    special_categories_confirmed: draft.categoryConfirmed,
    // ⚠️ Literal `false`, sem controle de UI e sem campo no rascunho. A Meta
    // recusou o compartilhamento em 05/09/2026 (100/4005) e o V2 recusa `true`
    // com nome próprio. Guardá-lo como estado editável seria manter viva uma
    // escolha que nenhuma das duas rotas aceita.
    is_adset_budget_sharing_enabled: false,
    advantage_audience: conjunto?.publico.expansao ?? false,
    call_to_action_type: primeira?.cta ?? 'LEARN_MORE',
    asset_rights_confirmed: primeira?.assetRightsConfirmed ?? false,
    third_party_identity_cleared: primeira?.thirdPartyIdentityCleared ?? false,
    asset_policy_confirmed_at: primeira?.assetPolicyConfirmedAt || null,
    variations: emitidas.map((item) => ({
      variation_key: item.key,
      asset_ref: item.assetRef,
      creative_name: item.creativeName,
      ad_name: item.adName,
      message: item.message,
      headline: item.headline,
      description: item.description,
      call_to_action_type: item.cta,
      asset_rights_confirmed: item.assetRightsConfirmed,
      third_party_identity_cleared: item.thirdPartyIdentityCleared,
      asset_policy_confirmed_at: item.assetPolicyConfirmedAt || null,
    })),
  };
}

/** O corpo do contrato V2.
 *
 * ⚠️ `PedidoPlanoMetaV2` é `extra="forbid"`: UM campo a mais volta 422 com o
 * nome do campo. Nada aqui pode ser "por via das dúvidas".
 *
 * ⚠️ `audience.expansion` VIAJA SEMPRE. O DTO não tem default de propósito —
 * omitir liga o Advantage+ na Meta desde a v23.0, então a ausência do campo
 * seria uma ampliação de alcance que ninguém escolheu.
 *
 * ⚠️ ABO e CBO são EXCLUSIVOS. Em ABO cada conjunto leva `budget` e
 * `campaign_budget` é `null`; em CBO é o inverso. Os dois juntos são
 * META_BUDGET_DUPLICATED (409), e o `null` explícito é o que impede um
 * `...spread` de deixar o campo do modo anterior no corpo. */
export function paraPlanoV2(draft: Draft): PlanoMetaV2Input {
  const emitidas = variacoesEmitidas(draft);
  const cbo = draft.nivelDeOrcamento === 'CAMPAIGN';
  const periodo = draft.periodoDeOrcamento;
  return {
    recipe_id: draft.recipeId,
    account_ref: draft.accountRef,
    page_ref: draft.pageRef,
    instagram_actor_ref: draft.instagramActorRef || null,
    campaign_name: draft.campaignName,
    destination_url: draft.destinationUrl,
    campaign_budget: cbo
      ? {
        nivel: 'CAMPAIGN', periodo,
        amount_minor: reaisParaMinor(draft.budgetBrl), currency: 'BRL',
      }
      : null,
    special_ad_categories: [],
    special_categories_confirmed: draft.categoryConfirmed,
    is_adset_budget_sharing_enabled: false,
    adsets: draft.conjuntos.map((conjunto) => ({
      adset_key: conjunto.key,
      name: conjunto.nome,
      start_time: inicioEmIso(conjunto.startTime) ?? '',
      end_time: inicioEmIso(conjunto.endTime),
      audience: {
        mode: conjunto.publico.modo,
        geo: {
          countries: paisesIncluidos(conjunto.publico.geo),
          region_keys: chavesDeLugar(conjunto.publico.geo, 'region', false),
          city_keys: chavesDeLugar(conjunto.publico.geo, 'city', false),
          zip_keys: chavesDeLugar(conjunto.publico.geo, 'zip', false),
          custom_locations: conjunto.publico.geo.pontos.map((ponto) => ({
            latitude: Number(ponto.latitude),
            longitude: Number(ponto.longitude),
            radius: Math.trunc(Number(ponto.raio)),
            distance_unit: ponto.unidade,
          })),
          excluded_countries: paisesExcluidos(conjunto.publico.geo),
          excluded_region_keys: chavesDeLugar(conjunto.publico.geo, 'region', true),
          excluded_city_keys: chavesDeLugar(conjunto.publico.geo, 'city', true),
          excluded_zip_keys: chavesDeLugar(conjunto.publico.geo, 'zip', true),
        },
        age_min: conjunto.publico.idadeMin,
        age_max: conjunto.publico.idadeMax,
        locale_refs: [...conjunto.publico.localeRefs],
        include_custom_refs: [...conjunto.publico.incluirRefs],
        exclude_custom_refs: [...conjunto.publico.excluirRefs],
        lookalike_refs: [...conjunto.publico.lookalikeRefs],
        interest_refs: [...conjunto.publico.interesseRefs],
        expansion: conjunto.publico.expansao,
      },
      placements: {
        mode: conjunto.posicionamentoModo,
        values: conjunto.posicionamentoModo === 'MANUAL'
          ? [...conjunto.posicionamentoValores] : [],
      },
      measurement: {
        purpose: conjunto.mensuracao.proposito,
        source_kind: conjunto.mensuracao.fonteTipo || null,
        source_ref: conjunto.mensuracao.fonteRef || null,
        custom_conversion_ref: conjunto.mensuracao.conversaoRef || null,
        standard_event: conjunto.mensuracao.eventoPadrao || null,
      },
      budget: cbo ? null : {
        nivel: 'ADSET', periodo,
        amount_minor: reaisParaMinor(conjunto.orcamentoBrl), currency: 'BRL',
      },
    })),
    ads: emitidas.map((item) => ({
      variation_key: item.key,
      adset_key: item.adsetKey,
      asset_ref: item.assetRef,
      creative_name: item.creativeName,
      ad_name: item.adName,
      message: item.message,
      headline: item.headline,
      description: item.description,
      call_to_action_type: item.cta,
      asset_rights_confirmed: item.assetRightsConfirmed,
      third_party_identity_cleared: item.thirdPartyIdentityCleared,
      asset_policy_confirmed_at: item.assetPolicyConfirmedAt || null,
    })),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// PRONTIDÃO
// ─────────────────────────────────────────────────────────────────────────────

export interface ContextoDeProntidao {
  capacidades: CapacidadesDaBancada;
  compilado: boolean;
  validado: boolean;
  /** Propósitos que a receita escolhida admite. Vazio = ainda não lido, e a
   *  ausência de catálogo não pode BLOQUEAR nada: ela só deixa de liberar. */
  propositosDaReceita?: readonly PropositoDeMensuracao[];
}

/** O orçamento de cada objeto que carrega verba, em centavos. */
export function orcamentosDoPlano(draft: Draft): { rotulo: string; minor: number }[] {
  if (draft.nivelDeOrcamento === 'CAMPAIGN') {
    return [{ rotulo: draft.campaignName || 'a campanha', minor: reaisParaMinor(draft.budgetBrl) }];
  }
  return draft.conjuntos.map((conjunto) => ({
    rotulo: conjunto.nome || 'conjunto sem nome',
    minor: reaisParaMinor(conjunto.orcamentoBrl),
  }));
}

function publicoValido(conjunto: ConjuntoDraft, draft: Draft): boolean {
  const p = conjunto.publico;
  if (!geografiaTemInclusao(p.geo)) return false;
  const excluidos = paisesExcluidos(p.geo);
  // Incluir e excluir o mesmo país é META_GEO_INCLUDE_EXCLUDE_CONFLICT: a Meta
  // aceitaria e a entrega seria vazia sem ninguém entender por quê.
  if (paisesIncluidos(p.geo).some((pais) => excluidos.includes(pais))) return false;
  if (p.idadeMin < IDADE_MINIMA_PADRAO || p.idadeMax > IDADE_MAXIMA_PADRAO) return false;
  if (p.idadeMin > p.idadeMax) return false;
  if (p.geo.pontos.some((ponto) => !(
    Number.isFinite(Number(ponto.latitude)) && Number.isFinite(Number(ponto.longitude))
    && Math.trunc(Number(ponto.raio)) > 0 && ponto.latitude !== '' && ponto.longitude !== ''
  ))) return false;
  if ((p.modo === 'EXISTING_CUSTOM' || p.modo === 'EXISTING_LOOKALIKE')
    && !(p.incluirRefs.length || p.lookalikeRefs.length)) return false;
  // ⚠️ Público amplo NÃO aceita público salvo nem segmentação detalhada:
  // META_AUDIENCE_MODE_CONFLICT. A tela precisa saber disso antes do 409.
  if (p.modo === 'BROAD' && (
    p.incluirRefs.length || p.excluirRefs.length
    || p.lookalikeRefs.length || p.interesseRefs.length)) return false;
  // O mesmo público incluído e excluído entrega vazio sem ninguém entender.
  const inclusos = new Set([...p.incluirRefs, ...p.lookalikeRefs]);
  if (p.excluirRefs.some((ref) => inclusos.has(ref))) return false;
  // O mesmo lugar nos dois lados é META_GEO_INCLUDE_EXCLUDE_CONFLICT.
  const chavesIncluidas = new Set(
    p.geo.lugares.filter((item) => !item.excluido).map((item) => item.key));
  if (p.geo.lugares.some((item) => item.excluido && chavesIncluidas.has(item.key))) {
    return false;
  }
  if (conjunto.posicionamentoModo === 'MANUAL' && conjunto.posicionamentoValores.length === 0) {
    return false;
  }
  if (conjunto.posicionamentoValores.includes('instagram') && !draft.instagramActorRef) {
    return false;
  }
  return true;
}

function mensuracaoValida(
  conjunto: ConjuntoDraft, propositos: readonly PropositoDeMensuracao[] | undefined,
): boolean {
  const m = conjunto.mensuracao;
  if (propositos && propositos.length && !propositos.includes(m.proposito)) return false;
  if (m.proposito === 'OPTIMIZE') {
    if (!m.fonteRef || !m.fonteTipo) return false;
    if (!m.conversaoRef && !m.eventoPadrao) return false;
    if (m.conversaoRef && m.eventoPadrao) return false;
  }
  if (m.fonteRef && !m.fonteTipo) return false;
  return true;
}

/** Estado por etapa. Quatro estados distinguíveis por glifo e palavra, nunca
 *  só por cor: pendente, pronto, bloqueado e validado.
 *
 * ⚠️ `publico` deixou de ser `'pronto'` INCONDICIONAL. Enquanto foi, o glifo do
 * trilho afirmava que a etapa estava resolvida sem olhar para nada — e o botão
 * discordava dele, porque `prontoParaCompilar` simplesmente OMITIA a etapa.
 * Eram dois lugares dizendo coisas diferentes sobre o mesmo fato; agora é um
 * cálculo só, consumido pelos dois. */
export function prontidaoDasEtapas(
  draft: Draft,
  contexto: ContextoDeProntidao,
): Record<EtapaId, EstadoDaEtapa> {
  const emitidas = variacoesEmitidas(draft);
  const chaves = new Set(draft.conjuntos.map((item) => item.key));
  const criativoBloqueado = draft.creativeMode === 'flexible'
    || (draft.creativeMode === 'batch' && !contexto.capacidades.loteEstatico)
    // ⚠️ Vídeo bloqueia INDEPENDENTE da capacidade: nenhum dos dois corpos o
    // transporta. Ver `variacaoCompleta`.
    || emitidas.some((item) => item.midia === 'video');
  const criativos = emitidas.map((item) => nomeCanonico(item.creativeName));
  const anuncios = emitidas.map((item) => nomeCanonico(item.adName));
  const nomesOk = new Set(criativos).size === criativos.length
    && new Set(anuncios).size === anuncios.length
    && [...criativos, ...anuncios].every(
      (nome) => nome.length > 0 && nome.length <= LIMITE_NOME);
  const criativoPronto = emitidas.length > 0
    && emitidas.length <= LIMITE_VARIACOES
    && emitidas.every(variacaoCompleta)
    && emitidas.every((item) => chaves.has(item.adsetKey))
    && nomesOk;

  const nomesDeConjunto = draft.conjuntos.map((item) => nomeCanonico(item.nome));
  const conjuntoPronto = draft.conjuntos.length > 0
    && draft.conjuntos.length <= LIMITE_CONJUNTOS
    && nomesDeConjunto.every((nome) => nome.length > 0 && nome.length <= LIMITE_NOME)
    && new Set(nomesDeConjunto).size === nomesDeConjunto.length
    && draft.conjuntos.every((item) => Boolean(inicioEmIso(item.startTime)))
    // Um conjunto sem anúncio nasceria vazio: META_ADSET_WITHOUT_AD.
    && draft.conjuntos.every((item) => emitidas.some((ad) => ad.adsetKey === item.key));

  const orcamentoPronto = orcamentosDoPlano(draft).every((item) => item.minor > 0)
    && (draft.periodoDeOrcamento !== 'LIFETIME'
      || draft.conjuntos.every((item) => Boolean(inicioEmIso(item.endTime))));

  return {
    base: draft.accountRef && draft.pageRef ? 'pronto' : 'pendente',
    campanha: draft.campaignName.trim() && draft.categoryConfirmed && draft.recipeId
      ? 'pronto' : 'pendente',
    orcamento: orcamentoPronto ? 'pronto' : 'pendente',
    conjunto: conjuntoPronto ? 'pronto' : 'pendente',
    publico: draft.conjuntos.every((item) => publicoValido(item, draft))
      ? 'pronto' : 'pendente',
    criativo: criativoBloqueado ? 'bloqueado' : criativoPronto ? 'pronto' : 'pendente',
    mensuracao: destinoValido(draft.destinationUrl)
      && draft.conjuntos.every(
        (item) => mensuracaoValida(item, contexto.propositosDaReceita))
      ? 'pronto' : 'pendente',
    revisao: contexto.validado ? 'validado' : contexto.compilado ? 'pronto' : 'pendente',
  };
}

/** ⚠️ A MESMA LISTA QUE O TRILHO. Ela omitia `publico`, e a omissão era
 *  invisível: o glifo dizia "pronto" porque `prontidaoDasEtapas` devolvia
 *  `'pronto'` fixo, e o botão nem consultava a etapa. Agora as duas leem o
 *  mesmo cálculo, e acrescentar uma etapa sem incluí-la aqui é um erro de
 *  compilação — `EtapaId` é exaustiva nos dois pontos. */
export const ETAPAS_QUE_LIBERAM_COMPILAR = [
  'base', 'campanha', 'orcamento', 'conjunto', 'publico', 'criativo', 'mensuracao',
] as const satisfies readonly EtapaId[];

export function prontoParaCompilar(
  draft: Draft,
  capacidades: CapacidadesDaBancada,
  propositosDaReceita?: readonly PropositoDeMensuracao[],
): boolean {
  const estados = prontidaoDasEtapas(draft, {
    capacidades, compilado: false, validado: false, propositosDaReceita,
  });
  return ETAPAS_QUE_LIBERAM_COMPILAR.every((etapa) => estados[etapa] === 'pronto');
}
