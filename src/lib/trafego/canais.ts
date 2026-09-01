/**
 * O contrato dos quatro canais, do lado da tela.
 *
 * ## A regra que este módulo existe para cumprir
 *
 * **Autorização nunca é calculada no navegador.** Nenhuma função aqui decide se
 * um canal pode ser planejado, conferido, criado ou ativado — o servidor já
 * decidiu, e o que chega é o veredito e o motivo. O que este arquivo faz é
 * *ler* essa decisão sem perdê-la no caminho.
 *
 * A tentação que ele fecha é concreta: `capacidades.google_mutate &&
 * manifesto.sabe_criar` escrito em TypeScript pareceria correto e estaria
 * errado — a janela do canário recusa Display mesmo com as duas verdadeiras, e
 * uma tela que não soubesse disso ofereceria um botão que o servidor nega no
 * clique, depois de o operador montar o pedido inteiro.
 *
 * ## Por que os tipos são estes, e não os de `types/trafego.ts`
 *
 * `EstadoDeProntidao` já existe lá, e descreve os cinco estados dos portões
 * G0–G3 de UMA campanha Search. Isto aqui é outra pergunta — o que cada CANAL
 * pode fazer — e ela tem quatro estados, não cinco. Reaproveitar o nome faria
 * dois vocabulários diferentes responderem pelo mesmo identificador, e o dia em
 * que alguém acrescentasse um estado a um deles quebraria o outro em silêncio.
 *
 * ## Nada aqui deriva um campo de outro
 *
 * `aberto` vem do servidor. `quantidade` vem do servidor. `smart_bidding_eligible`
 * vem do servidor. Recalcular qualquer um recriaria, no navegador, exatamente a
 * decisão que o backend existe para tomar.
 */

// ── os quatro estados, e por que quatro ─────────────────────────────────────
//
//   PERMITIDO       medido, e a resposta é sim
//   BLOQUEADO       medido, e a resposta é não — sempre com causa nomeada
//   INDETERMINADO   NÃO medido. Não é "não", é "ninguém olhou"
//   NAO_APLICAVEL   a pergunta não cabe neste canal
//
// ⚠️ `INDETERMINADO` NÃO pode ser desenhado como `BLOQUEADO`. As duas pedem
// ações opostas: uma pede que alguém abra uma permissão ou conserte algo; a
// outra pede uma leitura que ninguém fez. Pintar ignorância de vermelho ensina
// o operador a ignorar o vermelho.
export type EstadoDePortao =
  | 'PERMITIDO'
  | 'BLOQUEADO'
  | 'INDETERMINADO'
  | 'NAO_APLICAVEL';

/** Os quatro portões, na ordem em que o operador os atravessa. */
export type NomeDePortao =
  | 'planejavel'
  | 'validavel'
  | 'criavel_pausada'
  | 'ativavel';

/**
 * De onde vem uma recusa — e portanto **a quem o operador vai pedir**.
 *
 * ⚠️ Esta é a informação que transforma um botão cinza numa próxima ação. Um
 * bloqueio de `operador` se resolve com quem administra o sistema; um de
 * `construtor` com quem escreve o motor; um de `produto` ou `politica` é uma
 * decisão do dono, e não um defeito. Errar a origem manda a pessoa para a
 * porta errada.
 */
export type OrigemDeBloqueio =
  | 'construtor'
  | 'manifesto'
  | 'servidor'
  | 'operador'
  | 'politica'
  | 'mensuracao'
  | 'observabilidade'
  | 'produto';

export interface BloqueadorDeCanal {
  /** Estável. Ligue comportamento de UI a ele, nunca ao texto de `causa`. */
  codigo: string;
  /** Escrita para o operador. Já vem pronta do servidor — não a remonte. */
  causa: string;
  origem: OrigemDeBloqueio;
  /** Quando o fato foi observado. `null` para regra — regra não tem data. */
  observado_em: string | null;
  /** Como conferir de novo. `null` quando não há caminho de revalidação. */
  revalidacao: string | null;
}

export interface PortaoDeCanal {
  nome: NomeDePortao;
  estado: EstadoDePortao;
  /** ⚠️ Vem do servidor. Só `PERMITIDO` abre — e isto não é derivado aqui. */
  aberto: boolean;
  bloqueadores: BloqueadorDeCanal[];
}

export interface ManifestoDoCanal {
  plataforma: string;
  canal: string;
  rotulo: string;
  hierarquia: string[];
  paineis: string[];
  campos_do_pedido: string[];
  capacidades: string[];
  provas_obrigatorias: string[];
  indisponibilidades: string[];
  sabe_criar: boolean;
  sabe_provar: boolean;
}

export interface AssetsDoCanal {
  estado: EstadoDePortao;
  recursos: string[];
  /**
   * ⚠️ `null` quando o estado não é `PERMITIDO`. Um canal sem contrato de
   * assets não monta "0 de uma lista" — dizer `0` sugeriria que a lista existe
   * e ele preenche nenhuma dela.
   */
  quantidade: number | null;
  fonte: string | null;
  causa: string | null;
}

/** Os cinco estados de `prontidao.py`, sem colapso. */
export type EstadoDeMensuracao =
  | 'PRONTO'
  | 'PARCIAL'
  | 'NAO_PRONTO'
  | 'INDETERMINADO'
  | 'NAO_APLICAVEL';

export interface MensuracaoDoCanal {
  /** ⚠️ `false` = ninguém leu a conta. Os campos abaixo são o padrão de
   *  ignorância, e não um veredito. */
  lida: boolean;
  conversion_goal_status: EstadoDeMensuracao;
  conversion_signal_status: EstadoDeMensuracao;
  signal_sources: string[];
  measurement_readiness: EstadoDeMensuracao;
  data_manager_status: EstadoDeMensuracao;
  observability_status: EstadoDeMensuracao;
  /** ⚠️ Nunca ligado por ausência de bloqueio conhecido. Vem do servidor. */
  smart_bidding_eligible: boolean;
  fonte: string | null;
  notas: Record<string, unknown>;
}

export interface ObservabilidadeDoCanal {
  estado: EstadoDePortao;
  coletor: string | null;
  causa: string | null;
  /** ⚠️ `null` ≠ `0`. `null` é "não contei"; `0` é "contei e não há nenhuma". */
  campanhas_no_espelho: number | null;
  /** Quando `true`, o número acima é um PISO, não um total. */
  contagem_truncada: boolean;
}

/** Uma razão do `primary_status` do Google, com natureza própria. */
export interface RazaoDoEstado {
  codigo: string;
  /**
   * ⚠️ `em_revisao` não é `ok` nem `falha`. É o terceiro estado, e pintá-lo de
   * verde afirmaria uma aprovação que não houve.
   */
  natureza: 'por_desenho' | 'em_revisao' | string;
  texto: string;
}

export interface LeituraDeCampoDoCanario {
  observado_em: string;
  estrategia_de_lance: {
    valor: string;
    /** `escolhido` — o campo tem valor, e o valor é uma decisão. */
    estado: string;
    por_que_importa: string;
  };
  primary_status: string;
  /** ⚠️ LISTA. São razões simultâneas, e reduzir a uma apagaria a que ainda
   *  pode mudar. */
  primary_status_reasons: RazaoDoEstado[];
}

export interface SuperficieDoCanario {
  nome: string;
  descricao: string;
  /** ⚠️ TRI-ESTADO. `null` é leitura que não aconteceu — nunca "não existe". */
  visivel: boolean | null;
  causa: string | null;
  detalhe: Record<string, unknown> | null;
}

export interface CanarioOperacional {
  campaign_id: string;
  conta: string;
  conta_label: string;
  canal: string;
  estado_declarado: string;
  leitura_de_campo: LeituraDeCampoDoCanario;
  superficies: SuperficieDoCanario[];
  resumo: string;
}

export interface ObservabilidadeDePMax {
  /** Um dos cinco `CollectionState`. `NOT_COLLECTED` ≠ `PRESENT_EMPTY`. */
  estado_da_coleta: string;
  fonte: string;
  causa: string | null;
  /** `null` = não coletei. `[]` = coletei, e a conta não tem nenhuma. */
  campanhas: unknown[] | null;
  quantidade: number | null;
}

export interface AssetsExigidosDePMax {
  estado: string;
  causa: string | null;
  papeis:
    | {
        papel: string;
        minimo: number;
        maximo: number;
        obrigatorio: boolean;
        descricao: string;
      }[]
    | null;
}

export interface OperacionalDoCanal {
  canario?: CanarioOperacional;
  observabilidade?: ObservabilidadeDePMax;
  assets_exigidos?: AssetsExigidosDePMax;
}

export interface ContratoDeCanal {
  plataforma: string;
  canal: string;
  rotulo: string;
  manifesto: ManifestoDoCanal;
  /** Os quatro, sempre, nesta ordem. */
  portoes: PortaoDeCanal[];
  assets: AssetsDoCanal;
  mensuracao: MensuracaoDoCanal;
  observabilidade: ObservabilidadeDoCanal;
  operacional: OperacionalDoCanal;
}

export interface CapacidadesProjetadas {
  is_admin: boolean;
  lab_mode: boolean;
  google_read: boolean;
  google_validate_only: boolean;
  google_mutate: boolean;
  google_demand_gen_validate_only: boolean;
  porque_sem_mutacao: string | null;
}

export interface FontesDoContrato {
  manifesto?: string;
  capacidades?: string;
  /** ⚠️ `false` distingue "a conta não tem campanhas" de "ninguém perguntou". */
  espelho_lido: boolean;
  leitura_viva_do_google: boolean;
  por_que_sem_leitura_viva: string;
}

export interface RespostaDosCanais {
  operador: CapacidadesProjetadas;
  politica_canario: Record<string, unknown>;
  canais: ContratoDeCanal[];
  fontes: FontesDoContrato;
}

// ── leitura, sem decisão ────────────────────────────────────────────────────

export const ORDEM_DOS_PORTOES: NomeDePortao[] = [
  'planejavel',
  'validavel',
  'criavel_pausada',
  'ativavel',
];

/**
 * O rótulo de cada portão — a pergunta que ele responde, em português.
 *
 * ⚠️ "Criável pausada" carrega a restrição no nome de propósito. Não existe
 * "criável" solto neste sistema: a janela autorizada cria pausada, e uma
 * campanha pausada não entra em leilão nem gasta. Chamar o portão de "criável"
 * faria o operador ler permissão de gasto onde há permissão de existência.
 */
export const ROTULO_DO_PORTAO: Record<NomeDePortao, string> = {
  planejavel: 'Planejável',
  validavel: 'Validável',
  criavel_pausada: 'Criável pausada',
  ativavel: 'Ativável',
};

export const PERGUNTA_DO_PORTAO: Record<NomeDePortao, string> = {
  planejavel: 'Existe um pedido de campanha para montar?',
  validavel: 'Dá para o Google conferir o pedido sem criar nada?',
  criavel_pausada: 'Dá para criar de verdade, sempre pausada?',
  ativavel: 'Dá para despausar?',
};

/** O portão pedido, ou `null` quando o servidor não o mandou. */
export function portao(
  contrato: ContratoDeCanal,
  nome: NomeDePortao,
): PortaoDeCanal | null {
  return contrato.portoes.find((p) => p.nome === nome) ?? null;
}

/**
 * O tom visual de um estado — e ele tem QUATRO valores, não dois.
 *
 * ⚠️ `INDETERMINADO` tem tom próprio (`ignorado`) e nunca herda o de
 * `BLOQUEADO`. Uma tela que pinta "não sei" de vermelho está afirmando uma
 * recusa que ninguém fez, e ensina o operador a tratar todo vermelho como
 * ruído.
 */
export type TomDoPortao = 'aberto' | 'fechado' | 'ignorado' | 'nao_cabe';

export function tomDoEstado(estado: EstadoDePortao): TomDoPortao {
  switch (estado) {
    case 'PERMITIDO':
      return 'aberto';
    case 'BLOQUEADO':
      return 'fechado';
    case 'INDETERMINADO':
      return 'ignorado';
    default:
      return 'nao_cabe';
  }
}

/**
 * O tom de um BLOQUEADOR, que não é o mesmo do portão.
 *
 * ⚠️ "Não habilitado nesta versão" **não é falha, não é ausência e não é
 * zero**. É uma decisão registrada, e desenhá-la em vermelho de erro diria ao
 * operador que algo quebrou. Bloqueios de `produto` e `politica` são neutros:
 * eles têm dono, data e caminho de reversão.
 */
export type TomDoBloqueio = 'decidido' | 'permissao' | 'ausencia' | 'sem_prova';

export function tomDoBloqueio(origem: OrigemDeBloqueio): TomDoBloqueio {
  switch (origem) {
    case 'produto':
    case 'politica':
      return 'decidido';
    case 'operador':
    case 'servidor':
      return 'permissao';
    case 'construtor':
    case 'manifesto':
      return 'ausencia';
    default:
      return 'sem_prova';
  }
}

/**
 * A quem o operador vai pedir para destravar isto.
 *
 * Escrito uma vez, aqui, porque é a informação que transforma um botão cinza
 * numa próxima ação.
 */
export const A_QUEM_PEDIR: Record<OrigemDeBloqueio, string> = {
  construtor: 'Depende de o sistema aprender a montar este canal.',
  manifesto: 'Depende de o sistema liberar esta etapa para o canal.',
  servidor: 'Depende de quem administra o sistema.',
  operador: 'Depende do papel da sua sessão.',
  politica: 'Depende de uma decisão do dono da operação.',
  produto: 'Depende de uma decisão registrada, com data e reversão.',
  mensuracao: 'Depende de medição comprovada antes de gastar.',
  observabilidade: 'Depende de conseguirmos reler a campanha depois de criada.',
};

/**
 * Nenhum portão pode aparecer verde sem evidência.
 *
 * ⚠️ Esta função NÃO decide autorização — ela audita a resposta. Se o servidor
 * mandasse um portão `PERMITIDO` com bloqueador, ou `BLOQUEADO` sem causa, a
 * tela teria de mostrar as duas coisas ao mesmo tempo. Preferimos que ela
 * mostre que a resposta é incoerente.
 */
export function incoerenciasDoContrato(contrato: ContratoDeCanal): string[] {
  const achados: string[] = [];
  for (const p of contrato.portoes) {
    if (p.estado === 'PERMITIDO' && p.bloqueadores.length > 0) {
      achados.push(`${p.nome}: liberado e com motivo de recusa ao mesmo tempo`);
    }
    if (p.estado !== 'PERMITIDO' && p.bloqueadores.length === 0) {
      achados.push(`${p.nome}: fechado sem dizer por quê`);
    }
    if (p.aberto !== (p.estado === 'PERMITIDO')) {
      achados.push(`${p.nome}: o veredito e o estado discordam`);
    }
  }
  return achados;
}

/**
 * Quantos portões estão abertos — sobre o que o SERVIDOR disse.
 *
 * ⚠️ Conta `aberto`, e não `estado === 'PERMITIDO'`, porque `aberto` é o campo
 * que o servidor emite. Reimplementar a regra aqui criaria uma segunda
 * definição de "aberto", e ela divergiria no dia em que o servidor mudasse.
 */
export function portoesAbertos(contrato: ContratoDeCanal): number {
  return contrato.portoes.filter((p) => p.aberto).length;
}

/**
 * O texto de um número que pode ser desconhecido.
 *
 * ⚠️ `null` vira `'—'`, nunca `'0'`. Um zero inventado no lugar de uma leitura
 * ausente é a mentira mais barata desta tela — e a mais cara de descobrir.
 */
export function numeroOuTraco(
  valor: number | null | undefined,
  sufixoQuandoPiso = '',
): string {
  if (valor === null || valor === undefined) return '—';
  return `${valor}${sufixoQuandoPiso}`;
}
