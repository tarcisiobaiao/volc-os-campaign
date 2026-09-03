// ============================================
// GOOGLE GROWTH ENGINE — o contrato das superfícies de decisão
//
// O Hub de Tráfego responde "o que existe e em que estado está".
// Este módulo responde as três perguntas seguintes:
//
//   1. por que esta campanha não entrega?        → DiagnosticoDeEntrega
//   2. o que deveria mudar, e com que evidência? → Proposta
//   3. quem autorizou, e o que exatamente saiu?  → Aprovacao + Recibo
//
// ⚠️ NENHUM tipo daqui descreve uma chamada ao Google Ads. A tela lê o que o
// backend já apurou. O vocabulário de ausência é o mesmo do inventário:
// `null` é "não foi possível apurar" e NUNCA degrada para zero, vazio ou "ok".
// ============================================

import type {
  CanalComManifesto,
  Leitura,
  ManifestoDeCanal,
} from '@/types/trafego';

/** Versão do contrato de diagnóstico. Sobe quando um consumidor precisa saber. */
export const VERSAO_DIAGNOSTICO = 1 as const;

// ── evidência ───────────────────────────────────────────────────────────────

/**
 * De onde um fato veio. Não é enfeite: muda o que ele autoriza concluir.
 *
 * `conta` é observado na conta de anúncio agora; `declarado` é o que NÓS
 * dissemos em algum momento (pode estar velho); `derivado` é conta feita a
 * partir de dois fatos observados — herda a fraqueza do mais fraco deles.
 */
export type OrigemDaEvidencia = 'conta' | 'declarado' | 'derivado';

/**
 * Um fato colhido, com o que o produziu colado.
 *
 * ⚠️ `rotulo` é o que o operador lê; `campo` é o nome de máquina e só aparece
 * na evidência expandida, que é o texto que ele COPIA quando pede ajuda.
 * DESIGN.md proíbe vocabulário de máquina na leitura normal, e permite
 * exatamente onde ele serve: no recado para quem cuida do sistema.
 */
export interface EvidenciaDeCampo {
  rotulo: string;
  /** Já formatado. `null` = a conta não respondeu este campo. Nunca `'0'`. */
  valor: string | null;
  /** Nome do campo na conta de anúncio. Só no detalhe copiável. */
  campo: string;
  /** A janela que produziu a medida, em português. `null` = fato sem janela. */
  janela: string | null;
  /** Quando foi lido. Sem isto, o número não deveria estar na tela. */
  leitura: Leitura | null;
  origem: OrigemDaEvidencia;
}

// ── a escada de entrega ─────────────────────────────────────────────────────

/**
 * Os degraus em que uma campanha pode falhar, NA ORDEM CAUSAL.
 *
 * A ordem não é organização visual: é a regra que impede a tela de mentir.
 * Uma conta sem faturamento faz todo o resto ficar sem sentido — os anúncios
 * podem estar aprovados e as keywords elegíveis, e nada disso vai a leilão.
 * Diagnosticar "keyword com lance baixo" acima de "conta suspensa" manda o
 * operador mexer em lance para resolver um problema de cobrança.
 */
export type EixoDeEntrega =
  | 'conta'
  | 'campanha'
  | 'orcamento'
  | 'grupo'
  | 'anuncio'
  | 'keyword'
  | 'segmentacao'
  | 'conversao'
  | 'leilao';

export const EIXOS_DE_ENTREGA: readonly EixoDeEntrega[] = [
  'conta',
  'campanha',
  'orcamento',
  'grupo',
  'anuncio',
  'keyword',
  'segmentacao',
  'conversao',
  'leilao',
];

/**
 * O estado de um degrau.
 *
 * ⚠️ `nao_apurado` existe para que a ausência de prova NUNCA vire `ok`. É a
 * mesma lei de `reconciliacao: null` do inventário, aplicada ao diagnóstico:
 * "a consulta falhou" e "está tudo bem aqui" levam a ações opostas, e achatá-las
 * produz a ação errada exatamente quando a informação falta.
 */
export type EstadoDoDegrau = 'bloqueia' | 'limita' | 'ok' | 'nao_apurado';

/** Desfecho persistido pelo ledger v12_01; `null` significa que nunca houve coleta. */
export type EstadoDaColetaDiagnostico =
  | 'com_dados'
  | 'vazio_confirmado'
  | 'parcial'
  | 'inelegivel'
  | 'nao_suportado'
  | 'falhou';

/** Frescor da fotografia, pela mesma janela canônica usada pelo inventário. */
export type FrescorDoDiagnostico = 'recente' | 'velho' | 'nao_apurado';

export interface DegrauDeEntrega {
  eixo: EixoDeEntrega;
  estado: EstadoDoDegrau;
  /** Palavra curta do estado neste degrau. Acompanha glifo e frase. */
  palavra: string;
  /** Uma frase em linguagem de operação. O que este degrau AFIRMA. */
  frase: string;
  /**
   * O que a própria conta de anúncio diz, quando diz.
   *
   * Vem de `primary_status_reasons` e equivalentes. Não é a nossa inferência,
   * e por isso aparece separado dela: quando o Google já nomeou a causa, uma
   * segunda opinião nossa por cima é ruído — ou pior, contradição.
   */
  motivo_da_conta: string[];
  evidencias: EvidenciaDeCampo[];
  /** Por que não foi apurado. Obrigatório quando `estado === 'nao_apurado'`. */
  impedimento: string | null;
  /** Ids das propostas que nasceram deste degrau. */
  propostas: string[];
}

/**
 * O veredito da escada — uma união, não um campo que possa vir nulo.
 *
 * Modelar como `primeiro_bloqueio: EixoDeEntrega | null` deixaria "nada
 * bloqueia" e "nada pôde ser apurado" com a MESMA representação, e o consumidor
 * escolheria a leitura otimista. A união torna esse erro impossível de escrever.
 */
export type VereditoDaEscada =
  | { tipo: 'bloqueada'; eixo: EixoDeEntrega }
  | { tipo: 'limitada'; eixo: EixoDeEntrega }
  | { tipo: 'sem_impedimento' }
  | { tipo: 'nao_apurado'; eixo: EixoDeEntrega };

/** `GET /api/trafego/campanhas/{id}/diagnostico` — projeção já apurada. */
export interface DiagnosticoDeEntrega {
  versao: typeof VERSAO_DIAGNOSTICO;
  volc_campaign_id: string;
  customer_id: string;
  nome_campanha: string;
  /** Moeda da conta. `null` = não declarada — nunca assumida como BRL. */
  moeda: string | null;
  /** Estado exato do ledger; `null` = campanha existente ainda sem coleta. */
  estado_coleta: EstadoDaColetaDiagnostico | null;
  /** Leitura velha ou sem carimbo nunca autoriza um degrau `ok`. */
  frescor: FrescorDoDiagnostico;
  /** A janela das métricas, em português. Número sem janela não é medição. */
  janela: string;
  /** Quando o diagnóstico foi apurado. */
  leitura: Leitura | null;
  /** A escada COMPLETA. Um eixo não medido entra como `nao_apurado`. */
  degraus: DegrauDeEntrega[];
  /** `true` quando ao menos um degrau é `nao_apurado`. */
  parcial: boolean;
}

// ── propostas ───────────────────────────────────────────────────────────────

export type AlvoDaProposta = 'orcamento' | 'lance' | 'status' | 'estrutura';

/**
 * Confiança na RECOMENDAÇÃO.
 *
 * ⚠️ Não é `SinalDeReconciliacao.forca` com outro nome. Aquele mede quão forte
 * é um sinal de IDENTIDADE ("esta campanha é deste funil"); este mede quão bem
 * a evidência sustenta uma MUDANÇA. Um sinal `forte` de identidade pode
 * sustentar uma proposta de confiança `baixa` se a amostra for de dois dias.
 * Vocabulários separados porque as perguntas são separadas.
 */
export type ConfiancaDaProposta = 'alta' | 'media' | 'baixa';

/** Quanta observação sustenta a proposta. Amostra pequena é dita, não escondida. */
export interface AmostraDaProposta {
  /** `null` = não apurado. Nunca `0` para dizer "não sei". */
  n: number | null;
  /** O que foi contado: "dias com entrega", "cliques", "leilões". */
  unidade: string;
  janela: string;
  /** `true` quando a amostra não sustenta a recomendação sozinha. */
  insuficiente: boolean;
}

/** Uma linha do antes/depois. */
export interface LinhaDeDiff {
  rotulo: string;
  /** `null` = valor atual desconhecido. A proposta continua legível e o diz. */
  antes: string | null;
  depois: string | null;
  /** Variação, só quando os dois lados existem e são comparáveis. */
  delta: string | null;
}

export interface DiffDaProposta {
  linhas: LinhaDeDiff[];
  /** O que explicitamente NÃO muda. Evita a pergunta que não foi feita. */
  inalterado: string[];
  /**
   * Efeito no gasto diário. `null` = não estimável.
   *
   * O campo inteiro é anulável de propósito: um objeto com micros zerados diria
   * "não muda o gasto", que é a afirmação mais perigosa que esta tela pode
   * fazer por engano.
   */
  gasto_diario: {
    antes_micros: number | null;
    depois_micros: number | null;
    moeda: string | null;
  } | null;
}

// ── aprovação ───────────────────────────────────────────────────────────────

export type EstadoDeAprovacao =
  /** Ninguém pediu autorização ainda. */
  | 'nao_submetida'
  /** Submetida, sem decisão humana. */
  | 'aguardando'
  | 'aprovada'
  | 'recusada'
  /** Aprovada, mas a evidência envelheceu — vale de novo só com nova prova. */
  | 'expirada'
  /** Já foi aplicada. O recibo é a prova do que saiu. */
  | 'aplicada';

/**
 * O portão. Guarda quem, quando, e — o que quase todo sistema esquece — O QUÊ.
 *
 * `impressao` é a mesma impressão digital que o recibo carrega: o resumo do
 * grafo de operações que seria enviado. Aprovar sem ela deixa "aprovado" sem
 * objeto: a proposta muda depois da aprovação e o carimbo continua lá, dizendo
 * que alguém autorizou algo que já não é o que vai acontecer.
 */
export interface Aprovacao {
  estado: EstadoDeAprovacao;
  /** Quem decidiu. `null` enquanto não há decisão. */
  por: string | null;
  /** ISO 8601. `null` enquanto não há decisão. */
  em: string | null;
  /** Impressão do que foi aprovado. `null` = a proposta não foi carimbada. */
  impressao: string | null;
  /** Motivo declarado. Vai para o recibo — é o campo `motivo` de lá. */
  motivo: string | null;
  /** Até quando vale. `null` = sem prazo declarado. */
  vale_ate: string | null;
}

/**
 * Por que a aplicação não está disponível — em uma frase, no estilo de
 * `PropostaDeAcao`.
 *
 * Um botão cinza mudo é a forma mais cara de indisponibilidade: o operador
 * tenta, não acontece nada, e ele não sabe se o sistema falhou ou se ele não
 * tem permissão. `dependencia` diz qual é a dependência REAL.
 */
export interface DependenciaDeAplicacao {
  /** A frase que o operador lê. Uma linha. */
  dependencia: string;
  /** O que destravaria. Pode ser papel, endpoint, trava, ou prova. */
  destrava: 'papel' | 'endpoint' | 'trava' | 'prova' | 'manifesto';
}

export interface Proposta {
  id: string;
  alvo: AlvoDaProposta;
  titulo: string;
  /** O que muda, em uma frase. */
  frase: string;
  /** O degrau da escada que originou esta proposta. */
  eixo: EixoDeEntrega;
  evidencias: EvidenciaDeCampo[];
  confianca: ConfiancaDaProposta;
  amostra: AmostraDaProposta;
  diff: DiffDaProposta;
  aprovacao: Aprovacao;
  /**
   * `null` = aplicável (o caminho existe e está liberado).
   * Preenchido = por que não dá, e o que destravaria.
   */
  bloqueio: DependenciaDeAplicacao | null;
}

export interface CaixaDePropostas {
  versao: typeof VERSAO_DIAGNOSTICO;
  volc_campaign_id: string;
  propostas: Proposta[];
  /**
   * `null` = a apuração de propostas falhou. Diferente de `[]`, que é
   * "apurei e não há nada a propor".
   */
  leitura: Leitura | null;
}

// ── recibos ─────────────────────────────────────────────────────────────────

/** Uma operação que a conta de anúncio confirmou ter criado. */
export interface OperacaoCriada {
  posicao: number;
  tipo: string;
  resource_name: string;
}

/**
 * A falha de um recibo.
 *
 * ⚠️ Os cinco recibos reais de `volc_ads/dados/recibos/` são todos `ACEITO`
 * com `falha: null` — o ramo de falha NÃO tem amostra observada. Por isso todo
 * campo é anulável e a leitura é tolerante (`lerRecibo`): inventar a forma de
 * um erro que nunca se viu produz uma tela que quebra no primeiro erro real.
 */
export interface FalhaDoRecibo {
  mensagem: string | null;
  codigo: string | null;
  /** Em que posição do grafo de operações parou. */
  posicao: number | null;
  campo: string | null;
}

/**
 * O recibo, na forma exata que `volc_ads` grava.
 *
 * `estado` não é união fechada de propósito: o gravador pode ganhar um estado
 * antes deste pacote, e uma tela que quebra ao ver palavra nova é pior que uma
 * que diz não reconhecer a palavra.
 */
export interface Recibo {
  estado: string;
  /** `20260819_123825`. Formato do gravador, traduzido para leitura na tela. */
  carimbo: string;
  customer_id: string;
  login_customer_id: string | null;
  nome_campanha: string;
  /**
   * O tamanho do grafo enviado. `null` quando o recibo não o declara — e isso
   * é diferente de zero: um recibo que não diz quantas operações mandou não
   * afirma que mandou nenhuma.
   */
  n_operacoes: number | null;
  /** Impressão digital do grafo enviado. É o que amarra recibo e aprovação. */
  impressao: string;
  motivo: string;
  criados: OperacaoCriada[];
  request_id: string;
  falha: FalhaDoRecibo | null;
  explicacao: string;
  /** `true` = a conta não criou nada. É afirmação, não ausência de dado. */
  nada_foi_criado: boolean;
}

// ── lote ────────────────────────────────────────────────────────────────────

/**
 * O estado de UM item do lote.
 *
 * ⚠️ **O vocabulário é o do backend** (`backend/app/trafego/lote.py`,
 * `ESTADOS_DO_ITEM`, e as CHECKs da migração v10_01). A tela não inventa nome de
 * estado nem traduz para um sinônimo "mais amigável": dois vocabulários para a
 * mesma máquina é como a tela e o executor passam a discordar sobre o mesmo
 * item, sem que exista uma resposta certa entre os dois.
 *
 * ## `indeterminado` é o mais importante da lista
 *
 * Ele diz: a chamada saiu, e não sabemos se criou. Não é `falhou` — falhou
 * AFIRMA que não criou, e essa afirmação autoriza reenviar. Achatar os dois é
 * como um timeout de rede vira uma segunda campanha real na conta do cliente,
 * disputando o mesmo leilão contra a primeira.
 *
 * ## `nao_tentado` não existe aqui
 *
 * O item que o lote não alcançou continua em `planejado`. O backend distingue
 * "não chegou a vez" de "falhou" pela máquina de estados, não por um estado
 * extra — e a tela usa a mesma distinção.
 */
export type EstadoDoItemDoLote =
  | 'planejado'
  | 'validado_local'
  | 'validado_remoto'
  | 'aprovado'
  | 'criando'
  /** A chamada saiu e não se sabe se criou. NUNCA reenviar: verificar. */
  | 'indeterminado'
  | 'criada_pausada'
  | 'verificada'
  | 'canario'
  | 'ativa'
  /** Tentado, e a conta recusou. Afirma que NÃO criou. */
  | 'falhou'
  | 'cancelada'
  | 'revertida';

/** Itens que existem na conta de anúncio. Mesma lista de `ESTADOS_CRIADOS`. */
export const ESTADOS_CRIADOS: readonly EstadoDoItemDoLote[] = [
  'criada_pausada',
  'verificada',
  'canario',
  'ativa',
];

/**
 * A próxima ação de um item — **decidida pelo servidor**, nunca recalculada aqui.
 *
 * A regra vive em `trafego_item_situacao.proxima_acao` (SQL) e em
 * `lote.proxima_acao()` (Python), que já são duas definições comparadas contra
 * um Postgres real. Uma terceira, em TypeScript, seria a que ninguém compara —
 * e a divergência apareceria como a tela oferecendo "criar" para um item que o
 * executor considera em voo.
 */
export type AcaoDoItem =
  | 'verificar'
  | 'parar_duplicidade'
  | 'nada'
  | 'decidir_retomada'
  | 'ativar_canario'
  | 'ativar'
  | 'criar'
  | 'preparar';

export interface ItemDoLote {
  id: string;
  rotulo: string;
  estado: EstadoDoItemDoLote;
  /** O que fazer com este item, segundo o servidor. */
  proxima_acao: AcaoDoItem;
  /** A falha DESTE item. Nunca contamina a leitura dos outros. */
  falha: { mensagem: string; codigo: string | null } | null;
  /** O recibo, quando houve criação. `null` = ainda não há recibo. */
  recibo: Recibo | null;
  /**
   * `true` quando há recibo em voo — chamada enviada, resposta não recebida.
   * Enquanto for `true`, a única ação correta é verificar na conta.
   */
  recibo_em_voo: boolean;
  /**
   * Quantas campanhas a última verificação achou na conta para este item.
   * `null` = ainda não verificado. `>= 2` é duplicidade, e trava o lote.
   */
  encontradas_na_conta: number | null;
}

export type EstadoDoLote =
  | 'preparando'
  | 'validando'
  | 'aguardando_aprovacao'
  | 'aprovado'
  | 'executando'
  | 'interrompido'
  | 'concluido'
  | 'concluido_com_falhas'
  | 'recusado'
  | 'cancelado'
  | 'revertido';

export interface Lote {
  id: string;
  estado: EstadoDoLote;
  /** `null` = ainda sem aprovação humana. Nada é executado antes disso. */
  aprovado_em: string | null;
  aprovado_por: string | null;
  itens: ItemDoLote[];
  cancelado_por: string | null;
  cancelado_em: string | null;
  motivo_do_cancelamento: string | null;
}

// ── criação orientada por intenção ──────────────────────────────────────────

/**
 * As etapas da criação, na ordem em que a conversa acontece.
 *
 * Não é o formulário da API traduzido: `validacao_local` → `prova` →
 * `aprovacao` → `criacao` → `ativacao` são cinco portões distintos porque cada
 * um responde uma pergunta diferente, e juntá-los é o que transforma gasto em
 * clique. `criacao` cria PAUSADA; `ativacao` é uma decisão separada.
 */
export type EtapaDaCriacao =
  | 'objetivo'
  | 'conta'
  | 'destino'
  | 'conversao'
  | 'targeting'
  | 'orcamento'
  | 'criativos'
  | 'revisao'
  | 'validacao_local'
  | 'prova'
  | 'aprovacao'
  | 'criacao'
  | 'ativacao';

export const ETAPAS_DA_CRIACAO: readonly EtapaDaCriacao[] = [
  'objetivo',
  'conta',
  'destino',
  'conversao',
  'targeting',
  'orcamento',
  'criativos',
  'revisao',
  'validacao_local',
  'prova',
  'aprovacao',
  'criacao',
  'ativacao',
];

export type EstadoDaEtapa =
  | 'pendente'
  | 'atual'
  | 'respondida'
  /** Não dá para responder ainda, e a frase diz por quê. */
  | 'bloqueada'
  /** O manifesto do canal não pede esta etapa. Não é pular: é não existir. */
  | 'nao_se_aplica';

export interface PassoDaCriacao {
  etapa: EtapaDaCriacao;
  estado: EstadoDaEtapa;
  /** O que esta etapa pergunta, em uma frase. */
  pergunta: string;
  /** A resposta já dada, legível. `null` = ainda não respondida. */
  resposta: string | null;
  /** Por que está bloqueada. Obrigatório quando `estado === 'bloqueada'`. */
  dependencia: DependenciaDeAplicacao | null;
}

// ── criativos ───────────────────────────────────────────────────────────────

export type TipoDeCriativo =
  | 'titulo'
  | 'descricao'
  | 'sitelink'
  | 'imagem'
  | 'video'
  | 'logo';

export type ProcedenciaDoCriativo =
  /** Escrito ou produzido pelo VOLC O.S., com run de origem. */
  | 'volc_os'
  /** Trazido de fora e registrado por uma pessoa. */
  | 'importado'
  /** Encontrado na conta de anúncio durante uma leitura. */
  | 'conta'
  | 'desconhecida';

export interface ValidacaoDoCriativo {
  canal: CanalComManifesto;
  /** `nao_apurado` quando a regra do canal não pôde ser conferida. */
  situacao: 'serve' | 'nao_serve' | 'nao_apurado';
  /** Por que não serve, ou por que não deu para conferir. */
  motivo: string | null;
}

export interface UsoDoCriativo {
  volc_campaign_id: string;
  nome_campanha: string;
  estado_externo: string | null;
}

export interface Criativo {
  id: string;
  tipo: TipoDeCriativo;
  /** Texto, ou o nome do arquivo. Nunca uma URL privilegiada. */
  conteudo: string;
  /** Hash do conteúdo. `null` = não calculado — não prova identidade. */
  hash: string | null;
  procedencia: ProcedenciaDoCriativo;
  /** Origem declarada: run do Redator, pessoa, ou leitura da conta. */
  origem: string | null;
  validacoes: ValidacaoDoCriativo[];
  /**
   * Onde está em uso. `null` = não apurado; `[]` = apurado e não está em uso.
   * São fatos diferentes: o primeiro não autoriza excluir nada.
   */
  uso: UsoDoCriativo[] | null;
}

// ── visão por canal ─────────────────────────────────────────────────────────

/**
 * O que a tela pode oferecer neste canal — derivado do MANIFESTO.
 *
 * ⚠️ Nunca de uma lista de canais no cliente. Quatro canais na lista não são
 * quatro botões: `manifesto: null` significa "o Hub não opera este canal", e é
 * afirmação diferente de um manifesto que chega vazio ("opera, e não pode
 * nada"). A união abaixo impede o consumidor de confundir os dois.
 */
export type CapacidadeDoCanal =
  | { tipo: 'nao_operado'; frase: string }
  | { tipo: 'sem_capacidade'; frase: string; rotulo: string }
  | {
      tipo: 'operado';
      rotulo: string;
      /** Já traduzidas para o operador. */
      capacidades: string[];
      sabe_criar: boolean;
      /** A frase da recusa quando `sabe_criar` é falso. */
      recusa: string | null;
    /**
     * O que este canal NÃO monta, mesmo sabendo criar.
     *
     * ⚠️ Distinto de `recusa`. `recusa` responde "por que não dá para criar
     * aqui"; `limites` responde "o que a primeira fatia deste canal não faz".
     * Display declara CINCO limites — sem segmentação, sem placement positivo,
     * sem sitelink, sem lance manual, keywords não viram critério — e sabe
     * criar. Enquanto os dois moravam no mesmo campo, `sabe_criar: true`
     * zerava a recusa e os cinco sumiam da tela: o operador montava o pedido e
     * descobria a ausência depois.
     */
    limites: readonly string[];
      provas_obrigatorias: string[];
    };

export type { ManifestoDeCanal };

// ── o envelope da rota ──────────────────────────────────────────────────────

/**
 * `GET /api/trafego/campanhas/{volc_campaign_id}/diagnostico`
 *
 * Diagnóstico e propostas viajam JUNTOS de propósito. São a mesma apuração
 * vista de dois lados: a caixa nasce da escada, e duas rotas separadas
 * produziriam o dia em que a tela mostra um diagnóstico de agora ao lado de
 * propostas de meia hora atrás — sem nada na tela dizendo isso.
 *
 * ⚠️ Esta rota é LEITURA. Não cria, não altera e não consulta o Google Ads em
 * tempo de render: ela projeta o que a apuração já gravou.
 */
export interface RespostaDoDiagnostico {
  /**
   * ⚠️ O envelope está na **versão 2** desde 03/09/2026, e o campo continua
   * tipado como `number` de propósito: uma tela que quebra ao ver uma versão
   * nova é pior que uma que lê os campos que conhece.
   */
  versao: number;
  diagnostico: DiagnosticoDeEntrega;
  propostas: CaixaDePropostas;
  /**
   * O veredito da sentinela, **servido pelo backend**.
   *
   * `null` quando o servidor é anterior a este contrato. `null` NÃO significa
   * "está tudo bem": a tela que recebe `null` diz que não recebeu veredito, e
   * não desenha saúde.
   */
  sentinela: VeredictoDaSentinela | null;
}

// ── a sentinela de entrega ──────────────────────────────────────────────────
//
// ## Por que o veredito passou a vir do servidor
//
// `vereditoDaEscada` (em `@/lib/diagnostico/escada`) derivava o veredito aqui,
// no cliente, a partir dos degraus. A regra dela estava certa e a entrada,
// errada: o backend nunca preenchia o degrau `conta`, que é o PRIMEIRO da ordem
// causal — então a função devolvia `{tipo:'nao_apurado', eixo:'conta'}` em toda
// campanha e `degrausConfiaveis` devolvia lista vazia. A escada inteira era
// leitura suspensa permanente: a tela nunca mentia de verde porque nunca
// diagnosticava nada.
//
// O veredito servido é o que faz a tela, o sino e o alerta concordarem por
// construção em vez de por coincidência. `vereditoDaEscada` permanece como
// leitura local dos degraus — ela responde "até onde a escada foi lida", que é
// uma pergunta diferente e continua útil.

/** Em que nível o fato foi observado. */
export type EscopoDaSentinela =
  | 'account'
  | 'campaign'
  | 'ad_group'
  | 'ad'
  | 'keyword'
  | 'measurement'
  | 'destination';

/**
 * Os estados da sentinela.
 *
 * ⚠️ Tipado como união ABERTA (`| (string & {})`) de propósito: o servidor pode
 * ganhar um estado antes deste pacote, e a mesma lei do resto deste arquivo
 * vale aqui — uma tela que apaga o veredito por causa de uma palavra
 * desconhecida é pior que uma que diz não reconhecer a palavra. Quem consome
 * usa `vocabularioDaSentinela`, cujo fallback nunca é `bom`.
 */
export type StatusDaSentinela =
  | 'ACCOUNT_BLOCKED'
  | 'ACCESS_UNAVAILABLE'
  | 'POLICY_BLOCKED'
  | 'POLICY_REVIEW'
  | 'DATA_UNAVAILABLE'
  /** Desligada por decisão. Não gastar é o esperado — não é incidente. */
  | 'CAMPAIGN_OFF'
  | 'ADS_NOT_READY'
  | 'NO_DELIVERY'
  | 'LIMITED_BY_BUDGET'
  | 'LIMITED_BY_RANK'
  | 'KEYWORD_STRUCTURE_RISK'
  | 'MEASUREMENT_NOT_READY'
  | 'LOW_DEMAND'
  | 'LEARNING'
  | 'OBSERVING'
  | 'HEALTHY'
  | (string & {});

export type SeveridadeDaSentinela =
  | 'critica' | 'alta' | 'media' | 'baixa' | 'informativa' | (string & {});

/** A fase da vida da campanha, na janela do guardião de 72 horas. */
export type JanelaDoGuardiao =
  | 'nascimento'
  | 'ate_24h'
  | '24_72h'
  | 'apos_72h'
  /** Idade desconhecida. NÃO é zero, e não autoriza incidente de entrega. */
  | 'indeterminada'
  | (string & {});

/** Uma contagem com o denominador colado. Nenhum percentual viaja sozinho. */
export interface DenominadorDaSentinela {
  rotulo: string;
  quantos: number;
  de_quantos: number;
  /** Observados que não puderam ser classificados por falta de dado. */
  fora_da_conta: number;
  unidade: string;
  /** `null` quando a amostra é pequena demais para sustentar proporção. */
  proporcao: number | null;
  /** A contagem já em português, com o denominador visível. */
  frase: string;
}

export interface EvidenciaDaSentinela {
  rotulo: string;
  campo: string;
  /** `null` = a conta não respondeu este campo. Nunca `'0'`. */
  valor: string | null;
  observado_em: string | null;
  origem: string;
}

export interface CausaDaSentinela {
  status: StatusDaSentinela;
  escopo: EscopoDaSentinela | (string & {});
  severidade: SeveridadeDaSentinela;
  frase: string;
  evidencias: EvidenciaDaSentinela[];
  /** O que a conta disse com as próprias palavras. Separado da nossa inferência. */
  motivo_da_conta: string[];
  denominador: DenominadorDaSentinela | null;
  proximo_ato: string | null;
}

/**
 * Uma recomendação do Google, registrada e julgada — **nunca aplicada**.
 *
 * `aplicada` é sempre `false` e viaja no fio por isso: o operador LÊ que nada
 * foi aplicado, em vez de deduzir da ausência de um botão.
 */
export interface RecomendacaoAdjudicada {
  tipo: string;
  alvo: string | null;
  /** O que a plataforma DIZ que aconteceria. Não é medida nossa. */
  impacto_informado: string | null;
  observado_em: string | null;
  frescor: string;
  evidencia: EvidenciaDaSentinela[];
  adjudicacao:
    | 'nova' | 'revisada' | 'aceita_como_hipotese' | 'rejeitada' | 'superada'
    | (string & {});
  confianca: string;
  proximo_ato: string;
  aplicada: false;
}

/**
 * As recomendações E o estado da apuração delas, juntos.
 *
 * ⚠️ `itens: null` é "não apurei"; `itens: []` é "apurei e o Google não sugeriu
 * nada". Separar os dois é o ponto: uma lista vazia sem o estado da coleta
 * ofereceria "zero recomendações" sem dizer se ninguém perguntou.
 */
export interface QuadroDeRecomendacoes {
  estado_da_coleta:
    | 'nao_executada' | 'falhou' | 'vazio_confirmado' | 'com_dados'
    | (string & {});
  apurado: boolean;
  itens: RecomendacaoAdjudicada[] | null;
  quantidade: number | null;
  impedimento: string | null;
}

export interface VeredictoDaSentinela {
  versao: number;
  customer_id: string;
  volc_campaign_id: string;
  escopo: EscopoDaSentinela | (string & {});
  status: StatusDaSentinela;
  severidade: SeveridadeDaSentinela;
  /** `true` quando este veredito pede alguém. `HEALTHY`/`OBSERVING` não pedem. */
  incidente: boolean;
  observado_em: string | null;
  janela_inicio: string | null;
  janela_fim: string | null;
  janela_do_guardiao: JanelaDoGuardiao;
  frescor: FrescorDoDiagnostico | (string & {});
  /** `apurada` | `parcial` | `ausente` — o estado da PROVA, não da campanha. */
  estado_da_evidencia: 'apurada' | 'parcial' | 'ausente' | (string & {});
  causa_primaria: CausaDaSentinela | null;
  causas_secundarias: CausaDaSentinela[];
  /** O que permanece sem resposta. Dito, e não escondido num campo nulo. */
  desconhecidos: string[];
  recomendacoes: QuadroDeRecomendacoes;
  proximo_ato: string | null;
  /** Identidade determinística do incidente. Mesma condição, mesma chave. */
  chave: string;
  /** Sempre `false`. Declarado, não presumido. */
  mutacao_externa: boolean;
}
