/**
 * O contrato do Estúdio Criativo — o vocabulário canônico, e nada além dele.
 *
 * ## Por que este arquivo existe separado de `types/trafego.ts`
 *
 * Porque o Estúdio não pertence ao Google Ads. Ele é uma fábrica transversal:
 * Tráfego, Conteúdo Orgânico e exportação manual são DESTINOS que consomem o
 * patrimônio, não donos do formato. Colocar `CreativeJob` dentro do contrato de
 * Tráfego faria o primeiro destino virar o modelo central, e o segundo destino
 * (Meta, orgânico) chegaria pedindo para reescrever tudo.
 *
 * ## A regra que este arquivo protege, e que a interface não pode quebrar
 *
 * AUSÊNCIA É `null`. ZERO É MEDIDA. FALHA É OBJETO TIPADO.
 *
 * `largura: null` significa "ninguém mediu". `largura: 0` seria "medi e deu
 * zero", que é impossível para uma imagem — e é exatamente o que um `?? 0`
 * distraído produz. Por isso todo campo de medida aqui é `number | null` e
 * nunca `number` com default. O mesmo desenho de
 * `volc_ads/criativo/contrato.py`, e pelo mesmo motivo: um validador que lê
 * ausência como zero reprova o que não mediu e aprova o que mediu errado.
 *
 * `percentual: null` significa "o motor não mede progresso". A SPEC proíbe
 * inventar percentual (§7: "Não usar percentual quando o motor não medir
 * progresso determinístico"), e a única forma de a interface não inventar é o
 * contrato não ter onde guardar um número falso.
 *
 * ## O que NÃO está aqui, de propósito
 *
 * Nenhum caminho de filesystem, nenhum nome de bucket, nenhum prompt cru,
 * nenhuma chave. O browser recebe `previewUrl` (URL assinada e curta) e
 * `storageChave` NUNCA sai do backend. Se um campo destes aparecer aqui em
 * alguma refatoração futura, é regressão de segurança, não conveniência.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Estados canônicos
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Os sete estados de um job. `partial` é o que separa este contrato de um
 * booleano: um lote de três formatos com um recusado não é sucesso nem falha,
 * e chamá-lo de qualquer um dos dois joga fora informação que custou dinheiro.
 */
export type EstadoDoJob =
  | 'draft'
  | 'queued'
  | 'running'
  | 'partial'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export const ESTADOS_TERMINAIS: readonly EstadoDoJob[] = [
  'partial',
  'succeeded',
  'failed',
  'cancelled',
] as const;

export function jobTerminou(estado: EstadoDoJob): boolean {
  return (ESTADOS_TERMINAIS as readonly string[]).includes(estado);
}

/** Estado de UMA peça. O erro mora aqui, nunca no job (regra C da v11_01). */
export type EstadoDaRendition =
  | 'pendente'
  | 'gerando'
  | 'pronta'
  | 'falhou'
  | 'cancelada';

/**
 * Quem executou. `observado` significa que o VOLC O.S. LEU um build que já
 * existia — não que ele o produziu. A distinção existe no contrato porque é a
 * mentira mais fácil de cometer nesta fatia, e um campo booleano escondido
 * dentro de metadados seria fácil de ignorar na renderização.
 */
export type ProcedenciaDeExecucao = 'volc_os' | 'observado';

/** Os seis modos do ADR-001, mais `observado`. Nem todos estão implementados. */
export type ModoDeProducao =
  | 'typography_only'
  | 'deterministic_graphics'
  | 'full_llm'
  | 'photo_preserved'
  | 'prensa_hybrid'
  | 'full_llm_then_prensa'
  | 'observado';

export type TipoDeBriefing = 'imagem' | 'video' | 'audio' | 'texto';

export type KindDeMaster =
  | 'imagem'
  | 'video'
  | 'audio'
  | 'texto'
  | 'logo'
  | 'auxiliar';

export type DecisaoDeAprovacao = 'aprovado' | 'ajuste_solicitado' | 'rejeitado';

/**
 * Como a peça chegou na dimensão pedida. Sem este campo, "as três são formatos
 * reais" é afirmação sem prova: um bitmap esticado e uma composição nativa
 * chegam ao mesmo `1080x1350` e só este rótulo os separa.
 */
export type Enquadramento =
  | 'nativo'
  | 'resize'
  | 'cover_crop'
  | 'recomposto'
  /**
   * A normalizacao NAO pode rodar, e a peca ficou na dimensao que o provider
   * entregou, diferente da pedida. Rotulo proprio porque reusar `nativo` fazia
   * a tela dizer "o motor entregou ja nesta dimensao" ao lado de um pedido que
   * nao foi atendido.
   */
  | 'nao_normalizado';

// ─────────────────────────────────────────────────────────────────────────────
// Falha tipada
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Falha como DADO, nunca string crua do provider.
 *
 * `permanente` é o campo que decide o remédio, e é o mesmo contrato de
 * `volc_ads/criativo/porta.py`: `false` = retentar o mesmo insumo pode dar
 * certo (rede, cota, fila); `true` = retentar vai errar igual (prompt recusado
 * por política, formato não suportado). Sem a distinção, uma cascata de retry
 * queima cota repetindo um pedido que o motor já disse que nunca vai aceitar.
 *
 * `mensagem` é SANITIZADA no backend. Stack trace, nome de tabela, URL interna
 * e resposta bruta do provider não chegam aqui (SPEC §10 e DESIGN.md).
 */
export interface FalhaCriativa {
  codigo: string;
  mensagem: string;
  permanente: boolean;
  em: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Brand pack
// ─────────────────────────────────────────────────────────────────────────────

export interface BrandPack {
  id: string;
  slug: string;
  versao: number;
  nome: string;
  /** Paleta, tipografia e regras de logo como dado. Nunca `if` no componente. */
  tokens: Record<string, unknown>;
  /** `null` quando o pack não vendoriza fonte própria. */
  fontesHash: string | null;
  ativo: boolean;
  criadoEm: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Projeto e briefing
// ─────────────────────────────────────────────────────────────────────────────

export type OrigemDeProjeto = 'standalone' | 'trafego' | 'conteudo' | 'importado';

export interface CreativeProject {
  id: string;
  titulo: string;
  objetivo: string | null;
  brandPackId: string | null;
  origem: OrigemDeProjeto;
  criadoEm: string;
  arquivadoEm: string | null;
}

/**
 * Um formato pedido. `slot` é o identificador lógico que atravessa job, master
 * e rendition — é por ele que o retry sabe qual peça faltou.
 */
export interface FormatoPedido {
  slot: string;
  rotulo: string;
  largura: number;
  altura: number;
}

export interface CreativeBrief {
  id: string;
  projetoId: string;
  tipo: TipoDeBriefing;
  modo: ModoDeProducao;
  objetivo: string | null;
  audiencia: string | null;
  mensagem: string | null;
  brandPackId: string | null;
  formatosPedidos: FormatoPedido[];
  /**
   * Destinos PRETENDIDOS. Pretender não valida e não autoriza: um ativo só é
   * declarado compatível com um destino depois de validação de formato e
   * contrato (SPEC §5).
   */
  destinosPretendidos: string[];
  restricoes: Record<string, unknown>;
  criadoEm: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Job, evento e rendition
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Um evento do job. `seq` é ordem total e estável — é o cursor de reconexão do
 * SSE. Um cursor por timestamp empata no mesmo milissegundo e faz o cliente
 * perder ou duplicar evento; nenhum dos dois serve num painel que fala de custo.
 */
export interface EventoDoJob {
  seq: number;
  fase: string;
  mensagem: string | null;
  /** `null` = o motor não mede progresso. A interface mostra a ETAPA. */
  percentual: number | null;
  slot: string | null;
  em: string;
}

export interface Rendition {
  id: string;
  slot: string;
  rotulo: string;
  estado: EstadoDaRendition;

  /** O que foi PEDIDO. Sempre conhecido. */
  larguraPedida: number;
  alturaPedida: number;

  /** O que o provider entregou ANTES da normalização. `null` até chegar. */
  nativoLargura: number | null;
  nativoAltura: number | null;

  /** O que foi MEDIDO no arquivo final. `null` = ninguém mediu. */
  largura: number | null;
  altura: number | null;
  bytesTotais: number | null;
  mime: string | null;
  contentHash: string | null;

  enquadramento: Enquadramento | null;
  masterId: string | null;

  /** URL assinada e curta. `null` quando a peça ainda não tem arquivo. */
  previewUrl: string | null;

  /** Erro DESTA peça. As outras do lote continuam válidas. */
  erro: FalhaCriativa | null;

  custoUsd: number | null;
  concluidaEm: string | null;
}

export interface CreativeJob {
  id: string;
  briefingId: string;
  projetoId: string;
  projetoTitulo: string;
  tipo: TipoDeBriefing;
  modo: ModoDeProducao;
  motor: string;
  motorVersao: string;
  estado: EstadoDoJob;
  tentativa: number;
  procedenciaExecucao: ProcedenciaDeExecucao;
  /**
   * De onde um job `observado` foi lido. `null` para job `volc_os`.
   * Não contém caminho de filesystem: apenas identificador, hash e instante.
   */
  origemExterna: OrigemExterna | null;

  custoEstimadoUsd: number | null;
  custoRealUsd: number | null;

  iniciadoEm: string | null;
  terminadoEm: string | null;
  /**
   * PEDIDO de cancelamento, e nao confirmacao. Enquanto `canceladoEm` for
   * `null` e este campo nao, o job esta "cancelando": o motor pode ter uma peca
   * em voo que o provider ja vai cobrar. A SPEC §16 exige que a interface
   * distinga os dois, porque "pedi para parar" e "parou" nao sao a mesma
   * noticia para quem esta olhando o custo.
   */
  canceladoPedidoEm: string | null;
  /** Confirmacao: o executor parou de fato. */
  canceladoEm: string | null;
  criadoEm: string;

  /** Falha do JOB. Preenchida somente em `failed`. */
  falha: FalhaCriativa | null;

  renditions: Rendition[];

  /** Última `seq` conhecida. O cliente reconecta a partir dela. */
  cursorEventos: number;
}

/**
 * A prova de que um job foi OBSERVADO e não produzido aqui.
 *
 * Sem `hashDoArtefato` isto seria uma afirmação; com ele, qualquer pessoa
 * consegue reconferir que o arquivo que o VOLC O.S. mostra é byte a byte o que
 * a fábrica externa congelou. `motorVersaoConhecida: null` é honesto: a fábrica
 * não grava versão de motor dentro do build, e inventar uma seria pior que
 * declarar a ausência.
 */
export interface OrigemExterna {
  fabrica: string;
  identificadorDoBuild: string;
  hashDoArtefato: string;
  congeladoEm: string | null;
  motorVersaoConhecida: string | null;
  observadoEm: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Master, procedência e aprovação
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A procedência que a SPEC exige por ativo. Todo campo opcional é `null`
 * explícito, porque "não sei quanto custou" e "custou zero" são fatos
 * diferentes e a biblioteca precisa poder dizer qual dos dois é o caso.
 */
export interface Procedencia {
  motor: string;
  motorVersao: string;
  /** Hash do insumo. O prompt cru NUNCA chega ao browser. */
  insumoHash: string;
  brandPackId: string | null;
  brandPackVersao: number | null;
  criadoEm: string;
  custoUsd: number | null;
  licenca: string | null;
  credito: string | null;
  disclosure: string | null;
  sintetico: boolean;
}

export interface Aprovacao {
  id: string;
  subjectTipo: 'master' | 'pacote';
  subjectId: string;
  versao: number;
  finalidade: string;
  decisao: DecisaoDeAprovacao;
  atorId: string;
  atorNome: string | null;
  decididoEm: string;
  motivo: string | null;
  revogadaEm: string | null;
}

export interface AssetMaster {
  id: string;
  jobId: string;
  projetoId: string;
  projetoTitulo: string;
  slot: string;
  kind: KindDeMaster;
  mime: string;

  /** Medidas: `null` quando ninguém mediu. Nunca 0. */
  largura: number | null;
  altura: number | null;
  bytesTotais: number | null;
  duracaoMs: number | null;
  contentHash: string;

  versao: number;
  raizId: string | null;
  substituiId: string | null;

  procedencia: Procedencia;
  /**
   * Como o job que produziu este master foi executado.
   *
   * `null` significa **nao apurada**: o servidor nao leu o job desta peca. Nao
   * e o mesmo que `volc_os`, e a interface nao pode preencher o silencio com
   * uma afirmacao de autoria. O default anterior era exatamente isso, e fazia a
   * ficha de um build OBSERVADO dizer "Produzida pelo motor do VOLC O.S.".
   */
  procedenciaExecucao: ProcedenciaDeExecucao | null;

  previewUrl: string | null;
  posterUrl: string | null;

  /** Decisão VIGENTE, se houver. `null` = ainda aguardando revisão. */
  aprovacaoVigente: Aprovacao | null;

  /**
   * Usos conhecidos. Lista VAZIA significa "nenhum uso conhecido", que NÃO é o
   * mesmo que "sem uso": `usoApurado` diz se alguém chegou a olhar.
   * (SPEC §10: "`uso desconhecido` não é `sem uso`".)
   */
  usos: UsoDeAsset[];
  usoApurado: boolean;

  criadoEm: string;
  arquivadoEm: string | null;
}

export interface UsoDeAsset {
  destino: string;
  referencia: string;
  em: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Contrato de vídeo observado
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A leitura editorial de um build de vídeo. Não é um editor de timeline: é o
 * contrato resolvido, os beats e as evidências de QA, que é o que responde
 * "esta versão pode ou não ser usada?".
 */
export interface ContratoDeVideo {
  tema: string | null;
  nicho: string | null;
  skin: string | null;
  titulo: string | null;
  badge: string | null;
  duracaoS: number | null;
  fps: number | null;
  largura: number | null;
  altura: number | null;
  hook: HookDeVideo | null;
  voz: VozDeVideo | null;
  beats: BeatDeVideo[];
  elementosDeRetencao: string[];
  cta: string | null;
  /** `[]` = o build não registrou fatos/fontes. Não é "sem fontes". */
  fatos: FatoDeVideo[];
}

export interface HookDeVideo {
  tipo: string | null;
  linha: string | null;
  segundos: number | null;
  persona: string | null;
  cenario: string | null;
}

export interface VozDeVideo {
  provider: string | null;
  id: string | null;
  estilo: string | null;
  velocidade: number | null;
}

export interface BeatDeVideo {
  indice: number;
  papel: string | null;
  copy: string | null;
  visual: string | null;
  assetArquivo: string | null;
  duracaoFrames: number | null;
  duracaoS: number | null;
  inicioS: number | null;
}

export interface FatoDeVideo {
  afirmacao: string;
  fontes: string[];
  calibragem: string | null;
}

/** Um insumo do build, com licença e direitos declarados. */
export interface ItemDoLedger {
  arquivo: string;
  cena: number | null;
  fonte: string;
  licenca: string | null;
  credito: string | null;
  url: string | null;
  usoComercialOk: boolean | null;
  disclosure: string | null;
  sintetico: boolean;
}

export interface GateDeQa {
  id: string;
  rotulo: string;
  resultado: 'PASS' | 'WARN' | 'FAIL' | 'SKIPPED';
  detalhe: string | null;
}

export interface QaDeVideo {
  /** `null` quando aquele QA não foi executado neste build. */
  vereditoTecnico: 'PASS' | 'WARN' | 'FAIL' | 'SKIPPED' | null;
  vereditoVisual: 'PASS' | 'WARN' | 'FAIL' | 'SKIPPED' | null;
  gatesTecnicos: GateDeQa[];
  gatesVisuais: GateDeQa[];
  custoQaUsd: number | null;
}

export interface VideoObservado {
  job: CreativeJob;
  master: AssetMaster;
  contrato: ContratoDeVideo;
  ledger: ItemDoLedger[];
  qa: QaDeVideo;
  /** URL assinada para streaming. `null` se o arquivo não está disponível. */
  videoUrl: string | null;
  posterUrl: string | null;
  /**
   * Por que o VOLC O.S. ainda não renderiza vídeo novo. Texto vindo do backend
   * para que a interface não invente a limitação nem a esconda.
   */
  limitacaoDeclarada: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Pedidos (entrada da API)
// ─────────────────────────────────────────────────────────────────────────────

export interface PedidoDeJobDeImagem {
  projetoTitulo: string;
  objetivo: string;
  mensagem: string;
  audiencia: string | null;
  brandPackId: string | null;
  modo: ModoDeProducao;
  slots: string[];
  destinosPretendidos: string[];
}

/**
 * NAO existe `idempotencyKey` no pedido, e isso e deliberado.
 *
 * A versao anterior deste contrato dizia que "o cliente pode enviar a sua". Ele
 * nao pode: o modelo de entrada do backend descarta qualquer campo extra, entao
 * a chave calculada no navegador era montada, enviada e ignorada, e havia ate um
 * teste provando o comportamento de um valor que o servidor nunca lia.
 *
 * A idempotencia e resolvida no servidor, derivada do MESMO conteudo que o
 * formulario enviou. Duas submissoes iguais produzem a mesma chave la, e a
 * segunda volta com HTTP 200 e o cabecalho `X-Criativo-Idempotente: replay`.
 * E esse cabecalho que a interface deve ler para dizer "este pedido ja existia".
 */

export interface PedidoDeAprovacao {
  decisao: DecisaoDeAprovacao;
  finalidade: string;
  motivo?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Catálogo de formatos oferecidos
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Os formatos que o Estúdio sabe produzir hoje. Vive no contrato e não num
 * `<select>` porque o backend valida contra a MESMA lista: um slot que a
 * interface oferece e o motor não conhece vira job que falha depois de aceito.
 */
export interface FormatoDisponivel {
  slot: string;
  rotulo: string;
  proporcao: string;
  largura: number;
  altura: number;
  descricao: string;
  destinosTipicos: string[];
}

export const FORMATOS_DE_IMAGEM: readonly FormatoDisponivel[] = [
  {
    slot: '1x1',
    rotulo: 'Quadrado',
    proporcao: '1:1',
    largura: 1080,
    altura: 1080,
    descricao: 'Feed quadrado e display quadrado.',
    destinosTipicos: ['google_display', 'meta_feed', 'instagram_organic'],
  },
  {
    slot: '4x5',
    rotulo: 'Retrato',
    proporcao: '4:5',
    largura: 1080,
    altura: 1350,
    descricao: 'Ocupa mais altura no feed sem entrar em tela cheia.',
    destinosTipicos: ['meta_feed', 'instagram_organic'],
  },
  {
    slot: '9x16',
    rotulo: 'Vertical',
    proporcao: '9:16',
    largura: 1080,
    altura: 1920,
    descricao: 'Tela cheia de stories, reels e shorts.',
    destinosTipicos: ['meta_stories_reels', 'youtube_shorts'],
  },
  {
    slot: '1.91x1',
    rotulo: 'Paisagem',
    proporcao: '1.91:1',
    largura: 1200,
    altura: 628,
    descricao: 'Imagem de marketing paisagem do Display.',
    destinosTipicos: ['google_display', 'meta_feed'],
  },
] as const;

export function formatoDoSlot(slot: string): FormatoDisponivel | undefined {
  return FORMATOS_DE_IMAGEM.find((f) => f.slot === slot);
}

// ─────────────────────────────────────────────────────────────────────────────
// Rótulos de estado — glifo, palavra e descrição, nunca só cor
// ─────────────────────────────────────────────────────────────────────────────

/**
 * PRODUCT.md: "Estados nunca dependem só de cor: combinam glifo, palavra e
 * descrição." Este mapa é a única fonte desses três, para que a Home, a página
 * do job e a biblioteca não divirjam no vocabulário.
 *
 * `tom` é semântico e nunca usa a aurora VOLC: DESIGN.md reserva
 * `aurora-blue/purple/orange` para assinatura de marca, e um estado operacional
 * pintado de aurora faz a marca virar cor de alerta.
 */
export type TomDeEstado = 'neutro' | 'ativo' | 'sucesso' | 'atencao' | 'erro';

export interface RotuloDeEstado {
  palavra: string;
  descricao: string;
  tom: TomDeEstado;
}

export const ROTULO_DO_JOB: Record<EstadoDoJob, RotuloDeEstado> = {
  draft: {
    palavra: 'Rascunho',
    descricao: 'O briefing existe e ainda não foi enviado para produção.',
    tom: 'neutro',
  },
  queued: {
    palavra: 'Na fila',
    descricao: 'Aceito e aguardando o motor começar.',
    tom: 'neutro',
  },
  running: {
    palavra: 'Em execução',
    descricao: 'O motor está produzindo. Você pode sair desta tela.',
    tom: 'ativo',
  },
  partial: {
    palavra: 'Parcial',
    descricao: 'Parte das peças ficou pronta e parte falhou.',
    tom: 'atencao',
  },
  succeeded: {
    palavra: 'Concluído',
    descricao: 'Todas as peças pedidas ficaram prontas.',
    tom: 'sucesso',
  },
  failed: {
    palavra: 'Falhou',
    descricao: 'Nenhuma peça foi produzida.',
    tom: 'erro',
  },
  cancelled: {
    palavra: 'Cancelado',
    descricao: 'Interrompido antes de terminar.',
    tom: 'neutro',
  },
};

export const ROTULO_DA_RENDITION: Record<EstadoDaRendition, RotuloDeEstado> = {
  pendente: {
    palavra: 'Aguardando',
    descricao: 'Ainda não começou.',
    tom: 'neutro',
  },
  gerando: {
    palavra: 'Gerando',
    descricao: 'O motor está produzindo esta peça.',
    tom: 'ativo',
  },
  pronta: {
    palavra: 'Pronta',
    descricao: 'Arquivo gerado e medido.',
    tom: 'sucesso',
  },
  falhou: {
    palavra: 'Falhou',
    descricao: 'Esta peça não foi produzida. As demais não foram afetadas.',
    tom: 'erro',
  },
  cancelada: {
    palavra: 'Cancelada',
    descricao: 'Interrompida antes de gerar.',
    tom: 'neutro',
  },
};

export const ROTULO_DA_APROVACAO: Record<DecisaoDeAprovacao, RotuloDeEstado> = {
  aprovado: {
    palavra: 'Aprovado',
    descricao: 'Autorizado para a finalidade declarada.',
    tom: 'sucesso',
  },
  ajuste_solicitado: {
    palavra: 'Ajuste pedido',
    descricao: 'Precisa de correção antes de ser usado.',
    tom: 'atencao',
  },
  rejeitado: {
    palavra: 'Rejeitado',
    descricao: 'Não deve ser usado nesta versão.',
    tom: 'erro',
  },
};
