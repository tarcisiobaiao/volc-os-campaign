/**
 * Os SETE portões e o perfil de mensuração, do lado da tela.
 *
 * ## Por que este arquivo existe separado de `canais.ts`
 *
 * `canais.ts` descreve o CONTRATO DO CANAL — o que o cockpit lê para desenhar
 * um cartão por canal. O que está aqui é o contrato da MEDIÇÃO de uma campanha
 * específica: quem decide, o que se mede, e o que impede cada ato. As duas
 * coisas viajam em respostas diferentes (`GET /canais` e
 * `GET /plano-de-mensuracao`), e misturá-las faria a tela do lançamento
 * depender do cockpit para saber se pode gastar dinheiro.
 *
 * ## A regra que organiza tudo aqui
 *
 * **Nenhum estado é derivado nesta camada.** Os sete portões, os bloqueadores e
 * a aplicabilidade do perfil vêm prontos do servidor, que é quem tem a
 * evidência. O que este arquivo faz é TRADUZIR — e traduzir preservando as
 * distinções que o servidor pagou caro para manter: `não medido`, `zero medido`
 * e `falhou` são três frases diferentes, nunca "sem dados".
 *
 * ⚠️ E nunca verde por configuração. `PRONTO` é o único estado que pinta
 * positivo, e ele só chega aqui quando o servidor provou a evidência. `PARCIAL`
 * e `INDETERMINADO` são amarelos de "não sei", não degraus para o verde.
 */

/** Os cinco estados de um portão. `INDETERMINADO` é o default do servidor. */
export type EstadoDePortao =
  | 'PRONTO'
  | 'PARCIAL'
  | 'NAO_PRONTO'
  | 'INDETERMINADO'
  | 'NAO_APLICAVEL';

/**
 * Os SETE portões, cada um respondendo a UMA pergunta.
 *
 * ⚠️ Eles existem separados porque "pronto" sem sujeito virou palavra vazia.
 * Poder NASCER não diz nada sobre poder MEDIR, e nenhum dos dois diz nada sobre
 * poder ATIVAR — a campanha do canário atravessa o primeiro e é reprovada nos
 * outros dois.
 */
export interface PortoesDaMensuracao {
  /** O PLANO está pronto para criar — a campanha ainda não nasceu. */
  creation_plan_ready: EstadoDePortao;
  /** Só vira PRONTO depois de mutate + recibo fechado + releitura na conta. */
  campaign_birth: EstadoDePortao;
  /** Meta efetiva resolvida E sinal comprovado. Ter uma sem a outra é nenhuma. */
  measurement_ready: EstadoDePortao;
  /** Conseguimos reler a campanha depois de criada? */
  observability_ready: EstadoDePortao;
  /** Despausar é seguro? Exige política, plano PERSISTIDO e observabilidade. */
  activation_ready: EstadoDePortao;
  /** O lance pode aprender? Exige medição provada e observabilidade. */
  smart_bidding_ready: EstadoDePortao;
  /** Ingestão offline operante E destino resolvido (conta dona + id numérico). */
  data_manager_ready: EstadoDePortao;
}

export const ORDEM_DOS_PORTOES: (keyof PortoesDaMensuracao)[] = [
  'creation_plan_ready',
  'campaign_birth',
  'measurement_ready',
  'observability_ready',
  'data_manager_ready',
  'activation_ready',
  'smart_bidding_ready',
];

/**
 * O rótulo de cada portão, em português operacional.
 *
 * ⚠️ Nomes de PERGUNTA, e não de estado. "Ativação" sozinho vira um substantivo
 * que o operador lê como permissão; "Pode ativar?" é a pergunta que o portão de
 * fato responde, e ela admite "não" sem parecer erro.
 */
export const ROTULO_DO_PORTAO: Record<keyof PortoesDaMensuracao, string> = {
  creation_plan_ready: 'O plano pode criar?',
  campaign_birth: 'A campanha nasceu?',
  measurement_ready: 'A conta mede?',
  observability_ready: 'Conseguimos reler?',
  data_manager_ready: 'Ingestão offline pronta?',
  activation_ready: 'Pode ativar?',
  smart_bidding_ready: 'O lance pode aprender?',
};

/**
 * O que cada portão exige — a frase que o operador lê quando ele está fechado.
 *
 * ⚠️ Ela diz o REQUISITO, e não o problema. "Exige X" ensina o caminho; "faltou
 * X" só descreve o buraco, e nas telas em que os sete aparecem juntos a segunda
 * forma vira uma lista de reclamações sem ordem de conserto.
 */
export const EXIGENCIA_DO_PORTAO: Record<keyof PortoesDaMensuracao, string> = {
  creation_plan_ready: 'exige um plano de mensuração montado para este pedido.',
  campaign_birth:
    'exige mutate feito, recibo fechado e o id externo relido na conta.',
  measurement_ready:
    'exige meta de conversão efetiva resolvida E conversão observada. Ter uma sem a outra não é meia medição — é nenhuma.',
  observability_ready:
    'exige que a releitura pós-criação tenha sido exercida contra uma campanha real.',
  data_manager_ready:
    'exige ingestão offline operante E destino resolvido — conta dona mais id numérico da ação.',
  activation_ready:
    'exige autorização de política, plano PERSISTIDO no banco e observabilidade provada. Medir bem não autoriza despausar.',
  smart_bidding_ready:
    'exige medição provada e observabilidade. Um lance automático sem sinal chegando gasta o orçamento aprendendo o que ninguém mediu.',
};

/**
 * O tom visual de um estado.
 *
 * ⚠️ SÓ `PRONTO` é positivo. `PARCIAL` não é "quase pronto": é "li alguma coisa
 * verdadeira e não o bastante", e pintá-lo de verde-claro faria o operador
 * tratá-lo como degrau. `INDETERMINADO` é ignorância, e ignorância nunca é uma
 * cor boa.
 */
export type TomDoPortao = 'provado' | 'negado' | 'ignorado' | 'ausente';

export function tomDoEstado(estado: EstadoDePortao): TomDoPortao {
  if (estado === 'PRONTO') return 'provado';
  if (estado === 'NAO_PRONTO') return 'negado';
  if (estado === 'NAO_APLICAVEL') return 'ausente';
  return 'ignorado';
}

export function textoDoEstado(estado: EstadoDePortao): string {
  switch (estado) {
    case 'PRONTO':
      return 'provado';
    case 'NAO_PRONTO':
      return 'não';
    case 'PARCIAL':
      return 'parcial';
    case 'NAO_APLICAVEL':
      return 'não se aplica';
    default:
      return 'não se sabe';
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// O PERFIL DE MENSURAÇÃO
// ═══════════════════════════════════════════════════════════════════════════

export type FunilDoPerfil = 'descoberta' | 'consideracao' | 'acao';

/**
 * A fonte do sinal — TRÊS estados, e os dois primeiros não se confundem.
 *
 * ⚠️ `caminho_declarado` é a distinção que este sistema pagou caro para manter:
 * auto-tagging ligado, tag configurada e importação declarada dizem por onde a
 * conversão PODERIA chegar. Nenhuma delas diz que alguma chegou.
 */
export type FonteDoSinal =
  | 'nao_comprovada'
  | 'caminho_declarado'
  | 'conversao_observada';

export type ConsentimentoDoPerfil =
  | 'concedido'
  | 'negado'
  | 'nao_declarado'
  | 'nao_aplicavel';

export interface RegraDeValorDoPerfil {
  modo: 'sem_valor' | 'fixo' | 'por_evento';
  /** String, e não `number`: dinheiro que passa por float deixa de ser o mesmo. */
  valor: string | null;
  moeda: string | null;
}

export interface JanelaDoPerfil {
  estado: 'declarada' | 'nao_declarada';
  dias_de_clique: number | null;
  dias_de_engajamento: number | null;
  modelo: string | null;
  causa: string | null;
}

/**
 * O que esta campanha DECIDIU medir.
 *
 * ⚠️ Ele não é a `chave_intencao`. Aquela é o sha256 do pedido inteiro e muda
 * quando a verba muda; esta identidade é da MEDIÇÃO, e duas campanhas da mesma
 * oferta com orçamentos diferentes compartilham uma só.
 *
 * ⚠️ Não existe campo de NOME da ação, e a ausência é o contrato: renomear a
 * ação no painel do Google não muda o que ela mede.
 */
export interface PerfilDeMensuracao {
  negocio: string;
  intencao: string;
  funil: FunilDoPerfil;
  evento: string;
  /** A conta que POSSUI a ação — não necessariamente a que roda a campanha. */
  acao_owner_id: string | null;
  /** O id NUMÉRICO. */
  acao_id: string | null;
  semantica: string | null;
  regra_de_valor: RegraDeValorDoPerfil;
  janela: JanelaDoPerfil;
  fonte_do_sinal: FonteDoSinal;
  consentimento: ConsentimentoDoPerfil;
  causa_sem_acao: string | null;
  /** Prontos do servidor. ⚠️ Não os recalcule aqui. */
  aplicavel_a_ativacao: boolean;
  aplicavel_a_smart_bidding: boolean;
  aplicavel_a_envio_offline: boolean;
  chave: string;
}

export const ROTULO_DO_FUNIL: Record<FunilDoPerfil, string> = {
  descoberta: 'descoberta',
  consideracao: 'consideração',
  acao: 'ação',
};

/**
 * A fonte do sinal, em português — e a distinção preservada.
 *
 * ⚠️ Nunca "sem dados". As três frases pedem coisas diferentes: nenhuma via
 * pede configurar; via sem conversão pede conferir a instrumentação; conversão
 * observada não pede nada.
 */
export function textoDaFonte(fonte: FonteDoSinal): string {
  switch (fonte) {
    case 'conversao_observada':
      return 'conversão observada';
    case 'caminho_declarado':
      return 'há caminho declarado e nenhuma conversão observada';
    default:
      return 'nenhuma via de medição comprovada';
  }
}

export function textoDoConsentimento(c: ConsentimentoDoPerfil): string {
  switch (c) {
    case 'concedido':
      return 'termos de dados aceitos pela conta';
    case 'negado':
      return 'termos de dados NÃO aceitos pela conta';
    case 'nao_aplicavel':
      return 'não se aplica';
    default:
      return 'ninguém leu os termos de dados desta conta';
  }
}

/**
 * A regra de valor, em português.
 *
 * ⚠️ `sem_valor` é uma DECISÃO declarada, e não uma lacuna. Escrevê-la como
 * "não informado" faria parecer que alguém esqueceu de preencher — e a
 * diferença importa porque é ela que fecha o portão de MAXIMIZE_CONVERSION_VALUE.
 */
export function textoDaRegraDeValor(r: RegraDeValorDoPerfil): string {
  if (r.modo === 'fixo' && r.valor !== null) {
    return `valor fixo de ${r.valor} ${r.moeda ?? ''}`.trim();
  }
  if (r.modo === 'por_evento') return 'valor variável por evento';
  return 'sem valor declarado';
}

export function textoDaJanela(j: JanelaDoPerfil): string {
  if (j.estado !== 'declarada') {
    return 'janela de atribuição não declarada';
  }
  const partes: string[] = [];
  if (j.dias_de_clique !== null) partes.push(`${j.dias_de_clique} d de clique`);
  if (j.dias_de_engajamento !== null) {
    partes.push(`${j.dias_de_engajamento} d de engajamento`);
  }
  if (j.modelo) partes.push(j.modelo);
  return partes.join(' · ');
}

/**
 * Quem é o dono da ação que mede — e se ele é a conta que roda a campanha.
 *
 * ⚠️ A distinção não é decoração. Numa hierarquia de MCC com conversão
 * centralizada, a conta que POSSUI a ação não é a que roda a campanha, e a
 * ingestão offline precisa ir para a primeira. Mandar para a segunda não dá
 * erro de permissão: some.
 */
export function textoDoDonoDaAcao(
  perfil: PerfilDeMensuracao,
  customerId: string,
): string {
  if (perfil.acao_id === null) {
    return perfil.causa_sem_acao ?? 'nenhuma ação de conversão foi eleita.';
  }
  const dono = perfil.acao_owner_id;
  if (!dono) return `ação #${perfil.acao_id}, conta dona não lida`;
  if (dono === customerId) return `ação #${perfil.acao_id}, da própria conta`;
  return `ação #${perfil.acao_id}, da conta ${dono} (conversão centralizada)`;
}

// ═══════════════════════════════════════════════════════════════════════════
// COBERTURA DE CLICK IDS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * O que a conta consegue TRANSPORTAR — e por que isso não é medição.
 *
 * ⚠️ Auto-tagging ligado prova que o clique carrega `gclid`. É pré-requisito de
 * reconciliação offline e **não é conversão chegando**. Esta função existe para
 * que a tela possa mostrar a cobertura sem que ela vire um selo verde: o texto
 * termina sempre dizendo o que ela não prova.
 */
export function textoDaCoberturaDeClickIds(
  clickIds: string[],
  autoTagging: boolean | null,
): string {
  const lista = clickIds.length > 0 ? clickIds.join(', ') : 'nenhum declarado';
  if (autoTagging === null) {
    return `${lista} · auto-tagging não lido`;
  }
  if (autoTagging) {
    return `${lista} · auto-tagging ligado (transporta o id; não é conversão)`;
  }
  return `${lista} · auto-tagging DESLIGADO (o clique não carrega gclid)`;
}

// ═══════════════════════════════════════════════════════════════════════════
// A RESPOSTA DA RELEITURA
// ═══════════════════════════════════════════════════════════════════════════

/**
 * `GET /api/trafego/plano-de-mensuracao`.
 *
 * ⚠️ `persistido: false` com `plano: null` é "ninguém gravou plano para esta
 * conta" — e NÃO "a conta não está pronta". As duas pedem coisas opostas: a
 * primeira pede uma leitura, a segunda pede consertar a medição. A rota
 * responde 503 quando falha em LER, justamente para que ausência e falha nunca
 * cheguem aqui com a mesma forma.
 */
export interface PlanoVigenteResposta {
  persistido: boolean;
  plano_id: string | null;
  impressao?: string;
  lido_em?: string | null;
  registrado_em?: string | null;
  campaign_id?: string | null;
  chave_intencao?: string | null;
  versao?: number;
  plano: unknown | null;
  perfil: PerfilDeMensuracao | null;
  porque?: string;
  portoes: PortoesDaMensuracao;
  bloqueadores: string[];
  bloqueadores_materiais?: string[];
}

/**
 * Separa os bloqueadores em dois grupos, porque eles fecham portas diferentes.
 *
 * ⚠️ `activation_blockers` mistura naturezas de propósito. Uma recusa de
 * política ("ativar não é ato deste fluxo") e uma de medição ("nenhuma conversão
 * chegou") fecham a mesma porta por motivos que não se comparam — e só a
 * segunda contradiz `smart_bidding_ready`. Mostrá-los numa lista só faria o
 * operador tentar consertar a política com instrumentação.
 *
 * O servidor já emite o subconjunto MATERIAL; esta função apenas o usa como
 * recorte, e nunca reclassifica por texto. Classificar por palavra aqui seria
 * adivinhar a natureza de uma frase que o servidor já sabia.
 */
export function separarBloqueadores(
  todos: string[],
  materiais: string[] | undefined,
): { medicao: string[]; outros: string[] } {
  const material = new Set(materiais ?? []);
  return {
    medicao: todos.filter((b) => material.has(b)),
    // ⚠️ Quando o servidor não emite `materiais`, TUDO cai em `outros` — e não
    // tudo em `medicao`. Um servidor que não respondeu a distinção não pode
    // fazer a tela afirmar que uma razão é de medição.
    outros: todos.filter((b) => !material.has(b)),
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// ADAPTAÇÃO DA RESPOSTA DE `/provar`
// ═══════════════════════════════════════════════════════════════════════════

/** A forma mínima que este adaptador precisa. Deliberadamente frouxa. */
export interface ProntidaoBruta {
  creation_plan_ready?: string;
  campaign_birth?: string;
  measurement_ready?: string;
  measurement_readiness?: string;
  observability_ready?: string;
  observability_status?: string;
  data_manager_ready?: string;
  data_manager_status?: string;
  activation_ready?: string;
  smart_bidding_ready?: string;
}

const ESTADOS: EstadoDePortao[] = [
  'PRONTO',
  'PARCIAL',
  'NAO_PRONTO',
  'INDETERMINADO',
  'NAO_APLICAVEL',
];

/**
 * ⚠️ FALHA FECHADA. Qualquer coisa que não seja um dos cinco estados conhecidos
 * vira `INDETERMINADO` — inclusive `undefined`, string vazia e um valor novo que
 * um servidor futuro invente.
 *
 * O caso que importa é `undefined`: um servidor anterior a 02/09/2026 não emite
 * os nomes canônicos, e tratar a ausência como `PRONTO` — ou deixá-la vazar
 * como `undefined` para o `Record` de cores — faria a tela pintar de verde um
 * portão que ninguém avaliou.
 */
function estado(bruto: string | undefined): EstadoDePortao {
  return ESTADOS.includes(bruto as EstadoDePortao)
    ? (bruto as EstadoDePortao)
    : 'INDETERMINADO';
}

/**
 * Os sete portões a partir do que `/provar` respondeu.
 *
 * ⚠️ Os nomes canônicos têm precedência, e os antigos são o fallback — nunca o
 * contrário. Um servidor que emite os dois emite o MESMO valor; a ordem existe
 * para o dia em que os antigos saírem.
 */
export function portoesDaProntidao(bruta: ProntidaoBruta | null | undefined): PortoesDaMensuracao {
  const p = bruta ?? {};
  return {
    creation_plan_ready: estado(p.creation_plan_ready),
    campaign_birth: estado(p.campaign_birth),
    measurement_ready: estado(p.measurement_ready ?? p.measurement_readiness),
    observability_ready: estado(
      p.observability_ready ?? p.observability_status,
    ),
    data_manager_ready: estado(p.data_manager_ready ?? p.data_manager_status),
    activation_ready: estado(p.activation_ready),
    smart_bidding_ready: estado(p.smart_bidding_ready),
  };
}
