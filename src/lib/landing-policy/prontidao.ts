/**
 * A prontidão de um DESTINO PAGO, do lado da tela.
 *
 * ## Por que este arquivo existe
 *
 * Até esta entrega o frontend não tinha vocabulário nenhum de política de
 * destino: nem papel, nem prontidão, nem bloqueador. Ele decidia se a landing
 * page estava boa com uma linha:
 *
 * ```ts
 * pronto={cockpit.origem.status_wp !== 'draft'}   // NovaCampanhaPage ~499
 * ```
 *
 * `status_wp` é `string | null`, e `null` significa "o servidor NUNCA leu o
 * WordPress". A comparação `!== 'draft'` transforma esse "ninguém leu" num
 * verde escrito "LP no ar". É o mesmo defeito que o portão do backend existe
 * para fechar, só que na camada onde o operador toma a decisão de gastar.
 *
 * ## A regra que organiza tudo aqui
 *
 * **Nada é derivado desta camada.** Quem avalia é `app.landing_policy`, que tem
 * o HTML. O que este arquivo faz é TRADUZIR o recibo — e traduzir preservando
 * as cinco distinções que o backend pagou caro para manter, porque colapsá-las
 * num único verde foi como uma LP com sete links de governo virou destino de
 * campanha:
 *
 *   1. **apto segundo o VOLC** — nesta avaliação, neste ponto, não sobrou
 *      bloqueio nem desconhecido;
 *   2. **publicado** — o WordPress diz `publish`;
 *   3. **verificado ao vivo** — alguém comparou o que está servindo hoje;
 *   4. **elegível para campanha** — avaliado no ponto onde o papel é FORÇADO
 *      para destino pago;
 *   5. **aprovação do Google** — DESCONHECIDA, e continuará: este portão lê
 *      HTML, não lê a decisão do revisor.
 *
 * ⚠️ E nunca verde por ausência. `APTO` é o único estado positivo, e ele exige
 * recibo presente, datável, fresco e da versão vigente do contrato. Recibo que
 * não chegou, evidência vencida e política antiga saem daqui como
 * `INDETERMINADO` — que é ignorância, e ignorância nunca é uma cor boa.
 *
 * O desenho (união fechada, mapas de ORDEM/RÓTULO/EXIGÊNCIA, `tom…` e um
 * adaptador cujo `estado()` manda o desconhecido para `INDETERMINADO`) é o de
 * `src/lib/trafego/portoes.ts`, de propósito: o operador lê a mesma língua nas
 * duas telas. A dependência é que não existe — são contratos diferentes,
 * emitidos por rotas diferentes.
 */

/**
 * A chave sob a qual o recibo viaja dentro do dict da página publicada.
 *
 * ⚠️ Espelha `app.landing_policy.CHAVE_DO_RECIBO`. Ela é o contrato de
 * transporte: o recibo entra em `state.published[n]` e viaja verbatim para
 * `pautador_funnel_runs.paginas_publicadas` — não há tabela nova, e por isso
 * não há schema que valide a chave. Errá-la aqui não dá erro: some.
 */
export const CHAVE_DO_RECIBO = 'landing_policy_receipt';

/**
 * A versão do CONTRATO que esta tela sabe ler.
 *
 * ⚠️ Recibo de outra versão REPROVA — não é lido "na medida do possível". A
 * versão muda quando muda a FORMA da avaliação (quais verificações existem, o
 * que cada papel exige), então um recibo antigo pode estar afirmando prontidão
 * contra um conjunto de verificações que nem inclui a que hoje bloqueia.
 */
export const VERSAO_DO_CONTRATO = 'paid_destination_policy_spine.v2';

/** Espelha `app.landing_policy.JANELA_DE_FRESCOR_PADRAO_S`. */
export const JANELA_DE_FRESCOR_PADRAO_S = 86400;

/** O ponto de portão onde o papel é FORÇADO para destino pago. */
export const PONTO_DE_CAMPANHA = 'campaign_destination_eligibility';

/** O código de achado que o backend emite quando a página mudou desde o hash aprovado. */
const CODIGO_DE_DERIVA = 'DERIVA_AO_VIVO';

// ═══════════════════════════════════════════════════════════════════════════
// OS ESTADOS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Os cinco estados de uma pergunta de prontidão. `INDETERMINADO` é o default.
 *
 * ⚠️ `NAO_AVALIADO` e `INDETERMINADO` não são sinônimos, e a diferença é
 * acionável: o primeiro é "esta pergunta não pertence a este ponto de portão"
 * (antes de publicar não existe deriva para observar), o segundo é "esta
 * pergunta pertence e ninguém a respondeu". Só o segundo pede uma leitura.
 *
 * ⚠️ `DESCONHECIDA_POR_CONTRATO` existe para UMA pergunta só — a do Google — e
 * existe porque `INDETERMINADO` convidaria o operador a ir buscar a resposta.
 * Não há onde buscar: este portão lê HTML.
 */
export type EstadoDaProntidao =
  | 'APTO'
  | 'BLOQUEADO'
  | 'INDETERMINADO'
  | 'NAO_AVALIADO'
  | 'DESCONHECIDA_POR_CONTRATO';

/** As CINCO perguntas, que são cinco coisas diferentes. */
export type PerguntaDaProntidao =
  | 'volc'
  | 'publicacao'
  | 'ao_vivo'
  | 'campanha'
  | 'google';

export const ORDEM_DAS_PERGUNTAS: PerguntaDaProntidao[] = [
  'volc',
  'publicacao',
  'ao_vivo',
  'campanha',
  'google',
];

/**
 * O rótulo de cada pergunta, em português operacional.
 *
 * ⚠️ Nomes de PERGUNTA, e não de estado — a mesma escolha de
 * `ROTULO_DO_PORTAO`. "Prontidão" sozinho vira um substantivo que o operador lê
 * como permissão; "O VOLC aprova este destino?" é a pergunta que a linha de
 * fato responde, e ela admite "não sei" sem parecer erro de sistema.
 */
export const ROTULO_DA_PERGUNTA: Record<PerguntaDaProntidao, string> = {
  volc: 'O VOLC aprova este destino?',
  publicacao: 'A página está publicada?',
  ao_vivo: 'Alguém conferiu o que está no ar?',
  campanha: 'Serve de destino de campanha?',
  google: 'O Google aprovou?',
};

/**
 * O que cada pergunta exige — a frase que o operador lê quando ela não é `APTO`.
 *
 * ⚠️ Ela diz o REQUISITO, não o problema. "Exige X" ensina o caminho; "faltou X"
 * só descreve o buraco, e numa tela onde as cinco aparecem juntas a segunda
 * forma vira uma lista de reclamações sem ordem de conserto.
 */
export const EXIGENCIA_DA_PERGUNTA: Record<PerguntaDaProntidao, string> = {
  volc:
    'exige uma avaliação sem bloqueio E sem desconhecido, datável, dentro da '
    + 'janela de frescor e contra a versão vigente da política. Verificação que '
    + 'não pôde ser concluída conta como desconhecido, não como página limpa.',
  publicacao:
    'exige o status lido do WordPress. `publish` é a única resposta que serve: '
    + 'rascunho não é visível para quem não está logado, e "ninguém leu" não é '
    + 'sinônimo de "está no ar".',
  ao_vivo:
    'exige a comparação com o hash aprovado feita contra a página no ar. '
    + 'Avaliar o artefato local não responde o que o servidor está entregando '
    + 'hoje.',
  campanha:
    'exige avaliação no ponto de elegibilidade de destino de campanha, onde o '
    + 'papel é FORÇADO para destino pago. Aprovação obtida em outro ponto de '
    + 'portão foi medida com rigor menor e não vale aqui.',
  google:
    'não é respondível por este portão: ele lê HTML, não lê a decisão do '
    + 'revisor do Google. Nenhuma leitura desta tela muda este estado.',
};

/**
 * O tom visual de um estado.
 *
 * ⚠️ SÓ `APTO` é positivo. `INDETERMINADO` não é "quase apto": é "ninguém
 * respondeu", e pintá-lo de verde-claro faria o operador tratá-lo como degrau.
 * `DESCONHECIDA_POR_CONTRATO` também é cinza — o Google não fica mais aprovado
 * porque o resto da tela ficou verde.
 */
export type TomDaProntidao = 'provado' | 'negado' | 'ignorado' | 'ausente';

/**
 * ⚠️ FALHA FECHADA, e é aqui que ela mora. Só `APTO` — a string exata — sai como
 * `provado`; TUDO o mais cai no `return` final. Inclusive `undefined`, string
 * vazia e um estado que uma versão futura do contrato invente, que chegariam
 * aqui se algum dia esta leitura vier de um servidor em vez de ser construída
 * neste arquivo.
 *
 * É a mesma trava de `portoes.estado()`, pelo mesmo motivo: um valor não
 * reconhecido vazando para o `Record` de cores pinta de "sem tom" — que no CSS
 * desta casa é indistinguível de neutro — um destino que ninguém avaliou.
 */
export function tomDaProntidao(estado: EstadoDaProntidao): TomDaProntidao {
  if (estado === 'APTO') return 'provado';
  if (estado === 'BLOQUEADO') return 'negado';
  if (estado === 'NAO_AVALIADO') return 'ausente';
  return 'ignorado';
}

/**
 * O estado em palavras — nunca "sem dados".
 *
 * ⚠️ As cinco frases pedem coisas diferentes: `bloqueado` pede consertar a
 * página, `não se sabe` pede uma leitura, `não avaliado aqui` não pede nada
 * neste ponto, e `desconhecida` não pede nada nunca. Uma frase só para todas
 * apagaria justamente a ordem de conserto.
 */
export function textoDaProntidao(estado: EstadoDaProntidao): string {
  switch (estado) {
    case 'APTO':
      return 'apto';
    case 'BLOQUEADO':
      return 'bloqueado';
    case 'NAO_AVALIADO':
      return 'não avaliado neste ponto';
    case 'DESCONHECIDA_POR_CONTRATO':
      return 'desconhecida — e continuará';
    default:
      return 'não se sabe';
  }
}

/** A deriva, em palavras. `APTO` aqui significa "não derivou". */
export function textoDaDeriva(estado: EstadoDaProntidao): string {
  switch (estado) {
    case 'APTO':
      return 'nenhuma deriva desde o conteúdo aprovado';
    case 'BLOQUEADO':
      return 'a página MUDOU desde o conteúdo aprovado';
    case 'NAO_AVALIADO':
      return 'deriva não se aplica antes de publicar';
    default:
      return 'ninguém comparou com o conteúdo aprovado';
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// O PAPEL
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Os papéis de `app.landing_policy.PapelDestino`, em português.
 *
 * ⚠️ O papel é do SERVIDOR. Esta tela só exibe o que o recibo carimbou; ela
 * nunca escolhe um papel, e nunca escolhe o mais frouxo quando dois divergem.
 * `role_declared` diferente de `role` não é erro — no ponto de campanha o papel
 * é forçado, e ver as duas linhas é como o operador entende por que o rigor
 * subiu.
 */
export const ROTULO_DO_PAPEL: Record<string, string> = {
  paid_destination: 'destino pago',
  conversion_page: 'página de conversão',
  presell: 'pré-venda',
  editorial_solution: 'solução editorial',
  organic_article: 'artigo orgânico',
};

export function textoDoPapel(papel: string | null): string {
  if (!papel) return 'papel não carimbado no recibo';
  return ROTULO_DO_PAPEL[papel] ?? papel;
}

export const ROTULO_DO_PONTO: Record<string, string> = {
  generation_artifact: 'artefato de geração',
  pre_publication_wordpress: 'pré-publicação no WordPress',
  campaign_destination_eligibility: 'elegibilidade de destino de campanha',
};

export function textoDoPonto(ponto: string | null): string {
  if (!ponto) return 'ponto de portão não carimbado';
  return ROTULO_DO_PONTO[ponto] ?? ponto;
}

// ═══════════════════════════════════════════════════════════════════════════
// A LEITURA DO RECIBO
// ═══════════════════════════════════════════════════════════════════════════

export interface AchadoDaPolitica {
  codigo: string;
  severidade: string;
  mensagem: string;
}

export interface DesconhecidoDaPolitica {
  verificacao: string;
  motivo: string;
}

export interface LeituraDoDestinoPago {
  /**
   * ⚠️ O PREDICADO. É `paid_destination_ready` do recibo, endurecido pelas
   * travas que o navegador consegue checar sozinho (frescor, versão do
   * contrato). NUNCA teste `bloqueadores.length === 0` no lugar dele: testar só
   * bloqueio ignora `desconhecidos`, e foi assim que o handoff anterior
   * deixaria publicar uma página cuja varredura falhou.
   */
  pode_seguir: boolean;
  /** `pode_seguir` MAIS publicada MAIS avaliada no ponto de campanha. */
  apto_para_campanha: boolean;
  /** Nenhum recibo chegou. Não é "reprovado": é "ninguém avaliou". */
  sem_recibo: boolean;
  perguntas: Record<PerguntaDaProntidao, EstadoDaProntidao>;
  papel_avaliado: string | null;
  papel_declarado: string | null;
  ponto_do_portao: string | null;
  veredito: string | null;
  url: string | null;
  avaliado_em: string | null;
  versao_do_contrato: string | null;
  versao_da_fonte: string | null;
  /** Doze caracteres do sha256. Bastam para reconciliar e não convidam a copiar. */
  hash_curto: string | null;
  impressao_curta: string | null;
  deriva: EstadoDaProntidao;
  /** `7/10` — quantas verificações chegaram a desfecho conclusivo. */
  completude: string | null;
  verificacoes_inconclusivas: string[];
  bloqueadores: AchadoDaPolitica[];
  avisos: AchadoDaPolitica[];
  desconhecidos: DesconhecidoDaPolitica[];
  /** De onde veio o HTML avaliado, ou a frase que admite não saber. */
  origem_da_evidencia: string;
  nota_do_google: string;
  /**
   * Por que esta tela está barrando, em pt-BR e na ordem do conserto. Vazio
   * quando `apto_para_campanha`.
   */
  recusas: string[];
  /**
   * As mesmas recusas em forma curta e minúscula, para a barra fixa.
   *
   * ⚠️ Duas formas do mesmo fato, e não duas fontes. A barra mostra duas
   * pendências e conta o resto num espaço de ~40 caracteres; enfiar ali a frase
   * inteira faria o operador ler metade de uma e nenhuma das outras. Elas são
   * geradas no mesmo ponto, então nunca divergem em número nem em ordem.
   */
  pendencias: string[];
}

const NOTA_DO_GOOGLE_PADRAO =
  'Este portão lê HTML; ele não lê a decisão do revisor do Google. "Apto" aqui '
  + 'significa apenas: nesta avaliação, neste ponto de portão, contra esta '
  + 'versão da política, não sobrou bloqueio nem desconhecido.';

function ehObjeto(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function texto(v: unknown): string | null {
  return typeof v === 'string' && v.trim() !== '' ? v : null;
}

function lista(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function achados(v: unknown): AchadoDaPolitica[] {
  return lista(v)
    .filter(ehObjeto)
    .map((a) => ({
      codigo: texto(a.code) ?? 'CODIGO_AUSENTE',
      severidade: texto(a.severity) ?? 'desconhecida',
      // ⚠️ Achado sem mensagem não vira linha em branco: uma linha em branco na
      // lista de bloqueios é lida como "nada aqui", que é o oposto do que ela é.
      mensagem: texto(a.message) ?? 'achado sem mensagem no recibo.',
    }));
}

function desconhecidos(v: unknown): DesconhecidoDaPolitica[] {
  return lista(v)
    .filter(ehObjeto)
    .map((d) => ({
      verificacao: texto(d.verificacao) ?? texto(d.check) ?? 'verificação sem nome',
      motivo: texto(d.motivo) ?? texto(d.reason) ?? 'motivo não declarado',
    }));
}

function curto(v: unknown): string | null {
  const s = texto(v);
  return s === null ? null : s.slice(0, 12);
}

/**
 * O recibo de dentro do portador, ou `null`.
 *
 * O portador é o dict que o backend já trafega — `cockpit.origem` no lançamento,
 * `pagina.publicada` no redator — e o recibo mora nele sob `CHAVE_DO_RECIBO`.
 * Aceita também o próprio recibo, reconhecido pelo `schema`, para que uma rota
 * futura que devolva o recibo direto não precise embrulhá-lo.
 *
 * ⚠️ Duas formas, e só duas. Procurar o recibo em vários lugares plausíveis
 * seria adivinhar — e adivinhação que erra devolve `null`, que aqui vira
 * "ninguém avaliou" e barra o lançamento de uma página que talvez estivesse
 * avaliada. Uma chave só, documentada, é o que mantém o erro visível.
 */
export function reciboDoPortador(portador: unknown): Record<string, unknown> | null {
  if (!ehObjeto(portador)) return null;
  if (portador.schema === 'LandingPolicyGateReceipt') return portador;
  const dentro = portador[CHAVE_DO_RECIBO];
  return ehObjeto(dentro) ? dentro : null;
}

/**
 * O status do WordPress vira estado — e `null` NÃO vira verde.
 *
 * ⚠️ Este é o conserto do defeito medido em `NovaCampanhaPage` ~499:
 * `status_wp !== 'draft'` marcava a etapa como pronta quando `status_wp` era
 * `null`, ou seja, exatamente quando o servidor nunca conseguiu ler o
 * WordPress. `publish` é a única resposta que abre.
 */
export function estadoDaPublicacao(status_wp: unknown): EstadoDaProntidao {
  const s = texto(status_wp);
  if (s === null) return 'INDETERMINADO';
  if (s === 'publish') return 'APTO';
  // `draft`, `pending`, `private`, `future`, `trash` — e qualquer status que uma
  // versão futura do WordPress invente. Todos significam "não está servindo para
  // quem não está logado", que é o que interessa a um clique pago.
  return 'BLOQUEADO';
}

export interface OpcoesDaLeitura {
  /** Injetado para o teste poder envelhecer evidência sem esperar um dia. */
  agora_epoch?: number;
  status_wp?: unknown;
  /**
   * Se esta leitura precisa do ponto de campanha. `false` no redator, onde a
   * página é avaliada antes de publicar e a pergunta de campanha não se aplica.
   */
  exige_ponto_de_campanha?: boolean;
}

/**
 * Traduz o recibo do portão em algo que a tela possa desenhar sem mentir.
 *
 * ⚠️ Toda saída desta função é fail-closed: recibo ausente, ilegível, sem
 * carimbo comparável, vencido ou de outra versão do contrato sai como
 * `INDETERMINADO` com `pode_seguir: false`. Não existe caminho por onde uma
 * leitura que falhou vire prontidão.
 */
export function leituraDoDestinoPago(
  portador: unknown,
  opcoes: OpcoesDaLeitura = {},
): LeituraDoDestinoPago {
  const {
    agora_epoch = Date.now() / 1000,
    status_wp,
    exige_ponto_de_campanha = true,
  } = opcoes;

  const publicacao = estadoDaPublicacao(status_wp);
  const recibo = reciboDoPortador(portador);
  const recusas: string[] = [];
  const pendencias: string[] = [];
  // As duas formas do mesmo fato, geradas juntas para nunca divergirem: a curta
  // cabe na barra fixa, a longa explica o conserto no painel.
  const recusar = (curta: string, longa: string) => {
    pendencias.push(curta);
    recusas.push(longa);
  };

  if (publicacao === 'BLOQUEADO') {
    recusar(
      'publicar a LP',
      `publicar a página no WordPress — o status lido é \`${texto(status_wp)}\`, `
      + 'e um clique pago cairia em 404 ou numa tela de login.',
    );
  }
  if (publicacao === 'INDETERMINADO') {
    recusar(
      'ler o status da LP',
      'ler o status da página no WordPress — o servidor não devolveu nenhum, e '
      + '"não li" não é "está no ar".',
    );
  }

  if (recibo === null) {
    // O caso que este arquivo existe para não deixar passar em silêncio.
    recusar(
      'avaliar o destino pago',
      'avaliar o destino pago — nenhum recibo de política chegou nesta '
      + 'resposta, então ninguém olhou esta página contra as regras.',
    );
    return {
      pode_seguir: false,
      apto_para_campanha: false,
      sem_recibo: true,
      perguntas: {
        volc: 'INDETERMINADO',
        publicacao,
        ao_vivo: 'INDETERMINADO',
        campanha: 'INDETERMINADO',
        google: 'DESCONHECIDA_POR_CONTRATO',
      },
      papel_avaliado: null,
      papel_declarado: null,
      ponto_do_portao: null,
      veredito: null,
      url: null,
      avaliado_em: null,
      versao_do_contrato: null,
      versao_da_fonte: null,
      hash_curto: null,
      impressao_curta: null,
      deriva: 'INDETERMINADO',
      completude: null,
      verificacoes_inconclusivas: [],
      bloqueadores: [],
      avisos: [],
      desconhecidos: [],
      origem_da_evidencia: 'nenhuma evidência chegou nesta resposta',
      nota_do_google: NOTA_DO_GOOGLE_PADRAO,
      recusas,
      pendencias,
    };
  }

  const prontidao = ehObjeto(recibo.readiness) ? recibo.readiness : {};
  const completudeBruta = ehObjeto(recibo.evidence_completeness)
    ? recibo.evidence_completeness
    : {};

  const bloqueadores = achados(recibo.blockers);
  const riscos = achados(recibo.risks);
  const observacoes = achados(recibo.observations);
  const naoSabidos = desconhecidos(recibo.unknowns);

  const versaoDoContrato = texto(recibo.policy_contract_version);
  const pontoDoPortao = texto(recibo.gate_point);

  // ── as travas que o navegador consegue conferir sozinho ──────────────────
  //
  // Elas não substituem o portão; elas impedem que um recibo VÁLIDO de ontem,
  // ou de outra versão da política, continue afirmando prontidão hoje. Sem
  // isso, "apto" seria uma afirmação sem prazo — e a evidência que a sustenta
  // tem prazo.
  const versaoBate = versaoDoContrato === VERSAO_DO_CONTRATO;
  if (!versaoBate) {
    recusar(
      'reavaliar: política antiga',
      `reavaliar contra a política vigente — o recibo é da versão \`${versaoDoContrato ?? 'não declarada'}\`, `
      + `e esta tela lê \`${VERSAO_DO_CONTRATO}\`.`,
    );
  }

  const epoch = typeof recibo.observed_at_epoch === 'number'
    && Number.isFinite(recibo.observed_at_epoch)
    ? recibo.observed_at_epoch
    : null;
  const janelaBruta = recibo.freshness_window_s;
  const janela = typeof janelaBruta === 'number'
    && Number.isFinite(janelaBruta)
    && janelaBruta > 0
    ? janelaBruta
    : JANELA_DE_FRESCOR_PADRAO_S;
  // ⚠️ `observed_at_epoch: null` é "esta avaliação não é datável" — e uma
  // avaliação sem data não pode ser chamada de fresca. É a mesma decisão do
  // `varrer_recibo` do backend, que responde `unavailable` nesse caso.
  const fresco = epoch !== null && agora_epoch - epoch <= janela;
  if (epoch === null) {
    recusar(
      'reavaliar: sem carimbo',
      'reavaliar com carimbo comparável — o recibo não traz o instante da '
      + 'observação, então não dá para dizer se ele ainda vale.',
    );
  } else if (!fresco) {
    const horas = Math.floor((agora_epoch - epoch) / 3600);
    recusar(
      'reavaliar: evidência vencida',
      `reavaliar o destino — a evidência tem ${horas} h e a janela de frescor `
      + `é de ${Math.floor(janela / 3600)} h.`,
    );
  }

  const declaradoPronto = recibo.paid_destination_ready === true;
  const portaoDoVolc = texto(prontidao.volc_gate);
  // ⚠️ Duas fontes concordando, e não uma. `paid_destination_ready` é o
  // predicado do backend; `readiness.volc_gate` é a mesma verdade em palavras.
  // Exigir as duas custa nada e fecha o caso de um recibo parcialmente montado.
  const pode_seguir = declaradoPronto
    && portaoDoVolc === 'ready'
    && bloqueadores.length === 0
    && naoSabidos.length === 0
    && versaoBate
    && fresco;

  if (bloqueadores.length > 0) {
    recusar(
      `corrigir ${bloqueadores.length} bloqueio(s) de política`,
      `corrigir ${bloqueadores.length} bloqueio(s) de política na página.`,
    );
  }
  if (naoSabidos.length > 0) {
    recusar(
      `concluir ${naoSabidos.length} verificação(ões)`,
      `concluir ${naoSabidos.length} verificação(ões) que não puderam ser feitas `
      + '— verificação exigida e inconclusiva conta como reprovação, não como '
      + 'página limpa.',
    );
  }
  if (declaradoPronto === false && bloqueadores.length === 0 && naoSabidos.length === 0) {
    // Recibo que diz "não pronto" sem apontar bloqueio nem desconhecido: a tela
    // não inventa a causa, mas também não trata a falta de causa como permissão.
    recusar(
      'reler o recibo',
      'reler o recibo — ele nega a prontidão sem listar bloqueio nem '
      + 'desconhecido, e esta tela não completa a lacuna a favor do lançamento.',
    );
  }

  const volc: EstadoDaProntidao = pode_seguir
    ? 'APTO'
    : bloqueadores.length > 0
      ? 'BLOQUEADO'
      : 'INDETERMINADO';

  const verificadoAoVivo = prontidao.live_verified === true;
  const ao_vivo: EstadoDaProntidao = verificadoAoVivo ? 'APTO' : 'INDETERMINADO';

  const noPontoDeCampanha = pontoDoPortao === PONTO_DE_CAMPANHA;
  const campanha: EstadoDaProntidao = !noPontoDeCampanha
    ? 'NAO_AVALIADO'
    : volc;
  if (exige_ponto_de_campanha && !noPontoDeCampanha) {
    recusar(
      'avaliar no ponto de campanha',
      'avaliar no ponto de elegibilidade de destino de campanha — este recibo é '
      + `de \`${textoDoPonto(pontoDoPortao)}\`, onde o rigor é menor.`,
    );
  }

  const derivou = [...bloqueadores, ...riscos].some(
    (a) => a.codigo === CODIGO_DE_DERIVA,
  );
  const deriva: EstadoDaProntidao = derivou
    ? 'BLOQUEADO'
    : verificadoAoVivo
      ? 'APTO'
      : 'INDETERMINADO';

  const apto_para_campanha =
    pode_seguir && publicacao === 'APTO' && (!exige_ponto_de_campanha || noPontoDeCampanha);

  return {
    pode_seguir,
    apto_para_campanha,
    sem_recibo: false,
    perguntas: {
      volc,
      publicacao,
      ao_vivo,
      campanha,
      google: 'DESCONHECIDA_POR_CONTRATO',
    },
    papel_avaliado: texto(recibo.role),
    papel_declarado: texto(recibo.role_declared),
    ponto_do_portao: pontoDoPortao,
    veredito: texto(recibo.verdict),
    url: texto(recibo.url),
    avaliado_em: texto(recibo.observed_at),
    versao_do_contrato: versaoDoContrato,
    versao_da_fonte: texto(recibo.policy_source_version),
    hash_curto: curto(recibo.content_sha256),
    impressao_curta: curto(recibo.content_fingerprint),
    deriva,
    completude: texto(completudeBruta.ratio),
    verificacoes_inconclusivas: lista(completudeBruta.inconclusive)
      .map((v) => texto(v))
      .filter((v): v is string => v !== null),
    bloqueadores,
    // Riscos e observações viajam juntos como AVISO: nenhum dos dois barra, e
    // separá-los na tela pediria do operador uma distinção que ele não usa para
    // decidir nada aqui. A severidade original continua em cada linha.
    avisos: [...riscos, ...observacoes],
    desconhecidos: naoSabidos,
    origem_da_evidencia: origemDaEvidencia(recibo, verificadoAoVivo),
    nota_do_google: texto(prontidao.google_approval_note) ?? NOTA_DO_GOOGLE_PADRAO,
    recusas,
    pendencias,
  };
}

/**
 * De onde veio o HTML avaliado.
 *
 * ⚠️ O recibo v2 NÃO carrega a origem da observação — `PaginaObservada.origem`
 * fica no backend e não entra em `recibo.emitir`. Então esta função lê o campo
 * se ele aparecer um dia, e enquanto não aparece diz o que dá para afirmar: se
 * a leitura ao vivo foi conclusiva. Inventar "artefato local" a partir da
 * ausência seria afirmar procedência sem evidência.
 */
function origemDaEvidencia(
  recibo: Record<string, unknown>,
  verificadoAoVivo: boolean,
): string {
  const declarada = texto(recibo.evidence_origin) ?? texto(recibo.origem);
  if (declarada) return declarada;
  const refs = lista(recibo.evidence_refs).length;
  const sufixo = refs > 0 ? ` · ${refs} referência(s) de evidência` : '';
  return verificadoAoVivo
    ? `página lida ao vivo${sufixo}`
    : `origem não declarada no recibo; a leitura ao vivo não foi conclusiva${sufixo}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// O QUE A BARRA DE LANÇAMENTO PRECISA
// ═══════════════════════════════════════════════════════════════════════════

/**
 * As severidades de aviso do cockpit que esta tela reconhece como NÃO barrantes.
 *
 * ⚠️ A lista é das que PASSAM, e não das que barram — e a inversão é o conserto
 * do segundo defeito medido: `NovaCampanhaPage` ~63 tinha um
 * `Set(['LP_EM_RASCUNHO','URL_PROVISORIA'])` no cliente, e qualquer código de
 * política que não estivesse nele virava observação recolhida enquanto
 * `podeLancar` seguia verdadeiro. Com a lista invertida, um código novo do
 * servidor barra por padrão e é o servidor que decide.
 */
const SEVERIDADES_QUE_NAO_BARRAM = new Set(['informacao', 'atencao']);

/**
 * ⚠️ FALHA FECHADA: severidade não reconhecida BARRA. `undefined`, string vazia
 * e uma severidade que o servidor invente amanhã caem todas no bloqueio.
 */
export function avisoBarraOLancamento(severidade: unknown): boolean {
  return !(typeof severidade === 'string'
    && SEVERIDADES_QUE_NAO_BARRAM.has(severidade));
}

/**
 * As pendências do destino, curtas e em minúsculas, para a barra de lançamento.
 *
 * A barra mostra duas e conta o resto; por isso a ordem importa, e ela é a do
 * conserto: publicar antes de avaliar, avaliar antes de discutir frescor.
 */
export function pendenciasDoDestino(leitura: LeituraDoDestinoPago): string[] {
  return leitura.apto_para_campanha ? [] : leitura.pendencias;
}

/** Uma linha para o cabeçalho do cartão: o estado do destino em três palavras. */
export function resumoDoDestino(leitura: LeituraDoDestinoPago): string {
  if (leitura.apto_para_campanha) return 'destino apto · Google desconhecido';
  if (leitura.sem_recibo) return 'destino não avaliado';
  if (leitura.perguntas.volc === 'BLOQUEADO') return 'destino bloqueado';
  if (leitura.perguntas.publicacao === 'BLOQUEADO') return 'página não publicada';
  return 'destino indeterminado';
}
