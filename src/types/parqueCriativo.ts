/**
 * O parque criativo — o catálogo que o BANCO arbitra.
 *
 * ## Por que este arquivo não vive em `criativos.ts`
 *
 * `criativos.ts` declara `FORMATOS_DE_IMAGEM` como constante: os quatro slots que
 * o motor sabe executar. Este arquivo declara a leitura de uma tabela que hoje tem
 * sete. Se os dois morassem juntos, a próxima pessoa acharia que a constante é um
 * recorte do parque, e passaria a mexer nela achando que estava mexendo no catálogo.
 * São duas verdades diferentes com o mesmo nome, e a separação é o que impede a
 * confusão de virar defeito.
 *
 * ## Ausência não é lista vazia
 *
 * Cada coleção é `T[] | null`. `[]` significa "o banco respondeu e não há linha";
 * `null` significa "esta tabela não respondeu". Uma tela que tratasse as duas igual
 * diria "nenhum motor cadastrado" com o banco fora do ar, e alguém cadastraria um
 * motor que já existe.
 */

/** Um desacordo medido entre o catálogo do banco e o que o executor roda. */
export interface DivergenciaDoParque {
  onde: string;
  oQue: string;
  /** O que o banco declara. `null` quando o banco não tem a linha. */
  banco: string | null;
  /** O que o executor conhece. `null` quando o executor não conhece. */
  runtime: string | null;
}

export interface MotorRegistrado {
  id: string;
  slug: string;
  nome: string;
  produz: string[];
  runtime: string;
  /** Identidade no Cofre de Ativos. `null` enquanto o Cofre não persistir. */
  cofreAssetId: string | null;
  provider: string | null;
  modelo: string | null;
  versaoDoAdaptador: string | null;
  /** Estimativa declarada com fonte, nunca custo medido. */
  custoReferenciaUsd: number | null;
  custoUnidade: string | null;
  custoFonte: string | null;
  capacidades: unknown;
  fonte: string;
  /** Quando alguém conferiu de fato. `null` = nunca conferido. */
  verificadoEm: string | null;
  ativo: boolean;
}

/**
 * O quanto um modo de produção foi PROVADO — não o quanto ele foi prometido.
 *
 * Esta é a coluna que sustenta o estado "sem runtime" da tela. Ela vem do banco
 * justamente para que a indisponibilidade não seja uma constante do bundle que
 * ninguém atualiza quando o modo passa a funcionar.
 */
export type EstadoDeProva =
  | 'planejado'
  | 'componentes_observados'
  | 'executado_externo'
  | 'implementado_no_volc';

export interface ModoDeProducao {
  id: string;
  slug: string;
  nome: string;
  descricao: string;
  exigeProviderDeImagem: boolean;
  renderer: string;
  estadoDeProva: EstadoDeProva;
  /** A evidência concreta. `null` quando o modo é só declarado. */
  prova: string | null;
  /** Quantas peças este modo já produziu de fato. `null` = ninguém contou. */
  saidasNoSnapshot: number | null;
  fonte: string;
  ordem: number;
}

export interface FormatoDoParque {
  id: string;
  slot: string;
  rotulo: string;
  proporcao: string;
  largura: number;
  altura: number;
  tipoDeAsset: string;
  midia: 'imagem' | 'video' | string;
  descricao: string | null;
  destinosTipicos: string[];
  fonte: string;
  ativo: boolean;
  ordem: number;
  /**
   * O EXECUTOR deste ambiente sabe produzir este slot?
   *
   * ⚠️ Vem do servidor, não do bundle. O banco declara 7 formatos e o executor
   * conhece 4; sem esta marca a tela oferece os 7 e o operador descobre a recusa
   * só depois de montar a receita inteira.
   */
  executavelAgora: boolean;
  /** Por que não. `null` quando é executável. */
  motivoSeNao: string | null;
}

export type ClasseDeFinalidade =
  | 'midia_paga'
  | 'organica'
  | 'interna'
  | 'exportacao'
  | string;

export interface Finalidade {
  id: string;
  slug: string;
  nome: string;
  descricao: string;
  classe: ClasseDeFinalidade;
  ativo: boolean;
  ordem: number;
}

export interface Skin {
  id: string;
  slug: string;
  nicho: string;
  /** O arco narrativo real do motor, não o genérico da SPEC. */
  arco: string[];
  papeisObrigatorios: string[];
  elementos: string[];
  motorId: string | null;
  fonte: string;
  ativo: boolean;
}

export interface Voz {
  id: string;
  slug: string;
  voiceId: string;
  fallbacks: string[];
  estilo: string | null;
  idioma: string;
  provider: string | null;
  motorId: string | null;
  fonte: string;
  ativo: boolean;
}

export type FamiliaDeGate = 'pixel' | 'tecnico' | 'visual' | 'compliance' | string;

export interface Gate {
  id: string;
  slug: string;
  motorId: string | null;
  familia: FamiliaDeGate;
  midia: string;
  descricao: string;
  /** `true` = impede publicar. `false` = avisa e deixa seguir. */
  bloqueante: boolean;
  fonte: string;
}

export interface ExigenciaDeCanal {
  id: string;
  canal: string;
  tipoDeAsset: string;
  quantidadeMinima: number;
  quantidadeMaxima: number | null;
  quantidadeRecomendada: number | null;
  proporcaoAlvo: string | null;
  toleranciaProporcao: number;
  larguraMinima: number | null;
  alturaMinima: number | null;
  larguraRecomendada: number | null;
  alturaRecomendada: number | null;
  bytesMaximos: number | null;
  mimesAceitos: string[];
  duracaoMinimaS: number | null;
  duracaoMaximaS: number | null;
  caracteresMaximos: number | null;
  caracteresDePeloMenosUm: number | null;
  /** `true` = número ainda não conferido contra a fonte oficial. */
  provisorio: boolean;
  fonteDosNumeros: string;
  verificadoEm: string | null;
}

export interface TetoCombinado {
  id: string;
  canal: string;
  rotulo: string;
  tipos: string[];
  minimo: number;
  maximo: number | null;
  fonte: string;
}

export interface Parque {
  motores: MotorRegistrado[] | null;
  modos: ModoDeProducao[] | null;
  formatos: FormatoDoParque[] | null;
  finalidades: Finalidade[] | null;
  skins: Skin[] | null;
  vozes: Voz[] | null;
  gates: Gate[] | null;
  exigenciasDeCanal: ExigenciaDeCanal[] | null;
  tetosCombinados: TetoCombinado[] | null;
  /** Nomes das coleções que não puderam ser lidas. */
  naoLidas: string[];
  divergencias: DivergenciaDoParque[];
  /** Quando esta leitura aconteceu. Medida sem carimbo envelhece em silêncio. */
  lidoEm: string;
  completa: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Vocabulário de operação
// ─────────────────────────────────────────────────────────────────────────────

/**
 * O que cada grau de prova significa para quem vai clicar.
 *
 * `podeProduzir` é a única pergunta que a tela precisa responder antes de deixar
 * alguém escolher um modo. Os outros três graus não são falha: são degraus de
 * evidência, e a diferença entre eles é o que o operador precisa saber para
 * decidir se pede ao time de conteúdo ou se tenta aqui.
 */
export const PROVA: Record<
  EstadoDeProva,
  { palavra: string; explicacao: string; podeProduzir: boolean }
> = {
  implementado_no_volc: {
    palavra: 'Produz aqui',
    explicacao: 'O VOLC O.S. executa este modo do início ao fim.',
    podeProduzir: true,
  },
  executado_externo: {
    palavra: 'Só fora daqui',
    explicacao:
      'Este modo já produziu peça de verdade, mas fora do VOLC O.S. Aqui ele ainda não roda.',
    podeProduzir: false,
  },
  componentes_observados: {
    palavra: 'Peças soltas',
    explicacao:
      'Partes deste modo foram vistas funcionando, sem nada que as ligue de ponta a ponta.',
    podeProduzir: false,
  },
  planejado: {
    palavra: 'Só no papel',
    explicacao: 'Este modo está descrito e nunca produziu nada.',
    podeProduzir: false,
  },
};

export const CLASSE_DE_FINALIDADE: Record<string, { palavra: string; explicacao: string }> = {
  midia_paga: {
    palavra: 'Mídia paga',
    explicacao: 'A peça vira anúncio. Exigência de canal e disclosure de anúncio se aplicam.',
  },
  organica: {
    palavra: 'Orgânico',
    explicacao: 'A peça vira publicação de perfil. Regras de plataforma, não de anúncio.',
  },
  interna: { palavra: 'Interno', explicacao: 'Uso interno; não sai para o público.' },
  exportacao: {
    palavra: 'Exportação',
    explicacao: 'A peça sai como arquivo para alguém usar fora do VOLC O.S.',
  },
};

export const FAMILIA_DE_GATE: Record<string, string> = {
  pixel: 'Verificação de pixel',
  tecnico: 'Verificação técnica',
  visual: 'Verificação visual',
  compliance: 'Verificação de conformidade',
};

// ─────────────────────────────────────────────────────────────────────────────
// A bancada: o que ESTA máquina consegue produzir agora
// ─────────────────────────────────────────────────────────────────────────────

/**
 * ⚠️ Isto é diferente de `MotorRegistrado`. Aquele diz quais motores existem no
 * patrimônio; este diz quais o executor desta máquina consegue rodar. A tela
 * precisa dos dois: um motor registrado que a máquina não roda não pode oferecer
 * botão de produzir.
 */
export interface MotorDaBancada {
  slug: string;
  versao: string | null;
  /** Tudo que participa do render e pode mudar o resultado. Vai ao recibo. */
  versoes: Record<string, string>;
  produz: string[];
  /**
   * `producao` | `local` | `fixture`. **Opcional de propósito:** um servidor
   * mais antigo não manda o campo, e ausência NÃO é "produção" — ela é
   * `nao_declarada`, tratada em `laboratorio/procedencia.ts`.
   */
  natureza?: string | null;
  /**
   * ⚠️ Derivado NO SERVIDOR de `natureza === 'producao'`, nunca um booleano
   * gravado que envelhece. A tela lê; não recalcula. Ausente = não autorizado.
   */
  publicavel?: boolean | null;
}

export type EstadoDoTrabalho =
  | 'queued'
  | 'claimed'
  | 'running'
  | 'validating'
  | 'rendered'
  | 'failed'
  | 'cancelled';

export interface ArtefatoDoRecibo {
  slot: string;
  mime: string;
  /** ⚠️ `bytes`, não `bytes_`. O sufixo era artefato de palavra reservada do
   * Python e vazava para o TypeScript; `caminho` era caminho de disco do
   * servidor e não sai mais. */
  bytes: number;
  sha256: string;
  largura: number | null;
  altura: number | null;
  duracaoS: number | null;
}

export interface ValidacaoDoRecibo {
  gate: string;
  resultado: 'PASS' | 'WARN' | 'FAIL' | 'SKIPPED' | string;
  /** O NÚMERO mora aqui. Um gate que só diz "passou" esconde por quanto. */
  detalhe: Record<string, unknown> | null;
  bloqueante: boolean;
}

export interface Recibo {
  trabalhoId: string;
  /** Quem produziu. Permanente, ao contrário de `TrabalhoDaBancada.operario`. */
  produzidoPor: string;
  motorSlug: string;
  motorVersao: string;
  seed: number;
  versoes: Record<string, string>;
  parametros: Record<string, unknown>;
  artefatos: ArtefatoDoRecibo[];
  validacoes: ValidacaoDoRecibo[];
  audio: Record<string, unknown> | null;
  iniciadoEm: string;
  terminadoEm: string;
  custoEstimadoUsd: number | null;
  custoRealUsd: number | null;
  assinaturaDeterminista: string;
}

export interface TrabalhoDaBancada {
  id: string;
  estado: EstadoDoTrabalho;
  tentativa: number;
  maxTentativas: number;
  operario: string | null;
  leaseAte: string | null;
  batimentoEm: string | null;
  /**
   * O lease ainda vale.
   *
   * ⚠️ Calculado do lease, não deduzido do estado. Um trabalho em `running` cujo
   * lease venceu NÃO está rodando, e tratar ausência de batimento como execução
   * ativa é exatamente o defeito que este campo existe para impedir.
   */
  vivo: boolean;
  falha: { codigo?: string; mensagem?: string; permanente?: boolean } | null;
  recibo: Recibo | null;
  /** De qual trabalho terminal este nasceu. `null` no original. */
  retomaDe: string | null;
  /** Ordinal da retomada. `0` no original. */
  retomadaN: number;
  canceladoPor: string | null;
  canceladoMotivo: string | null;
  criadoEm: string | null;
  /**
   * O que faz sentido AGORA, decidido pelo servidor.
   *
   * ⚠️ A tela NÃO reimplementa a regra de transição. Duas cópias da mesma regra
   * divergem, e quem diverge a favor do botão oferece uma ação que o servidor
   * recusa depois do clique.
   */
  podeRetomar: boolean;
  podeCancelar: boolean;
}

export const ESTADO_DO_TRABALHO: Record<
  EstadoDoTrabalho,
  { palavra: string; descricao: string; tom: 'neutro' | 'ativo' | 'sucesso' | 'atencao' | 'erro' }
> = {
  queued: { palavra: 'Na fila', descricao: 'Aguardando um operário pegar.', tom: 'neutro' },
  claimed: {
    palavra: 'Reservado',
    descricao: 'Um operário pegou o trabalho e ainda não começou a produzir.',
    tom: 'ativo',
  },
  running: { palavra: 'Produzindo', descricao: 'O motor está trabalhando.', tom: 'ativo' },
  validating: {
    palavra: 'Conferindo',
    descricao: 'A peça existe; os portões estão decidindo se ela serve.',
    tom: 'ativo',
  },
  rendered: {
    palavra: 'Pronta',
    descricao: 'A peça foi produzida e passou nos portões. Há recibo.',
    tom: 'sucesso',
  },
  failed: { palavra: 'Falhou', descricao: 'O trabalho não produziu peça.', tom: 'erro' },
  cancelled: { palavra: 'Cancelado', descricao: 'O trabalho foi interrompido.', tom: 'neutro' },
};
