/**
 * O vocabulário do Assistente Criativo, espelhando
 * `backend/app/criativo/agente/contrato.py`.
 *
 * Os nomes são os do servidor, em português, de propósito: um segundo
 * vocabulário na fronteira obrigaria um tradutor, e um tradutor é onde
 * `estado_mental_ref` vira `stateRef` e alguém depois compara os dois achando
 * que são campos diferentes. As refs são opacas aqui — a tela nunca as monta,
 * só as devolve.
 */

/** Fases do agente. Iguais ao enum `Fase` do servidor. */
export type Fase =
  | 'NOVA_OPERACAO'
  | 'DIAGNOSTICO'
  | 'ARQUITETURA'
  | 'MATRIZ'
  | 'COPY'
  | 'REFACAO';

export type EscopoFeedback = 'PONTUAL' | 'GRUPO' | 'PROJETO' | 'UNIVERSAL';

export type StatusDaOperacao = 'RUNNING' | 'READY_FOR_REVIEW' | 'FAILED' | 'ARCHIVED';

export type StatusDaRun = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED';

export type OrigemDoFato =
  | 'LANDING_PAGE'
  | 'OPERADOR'
  | 'POLICY_RECEIPT'
  | 'PERFORMANCE_RECEIPT';

export interface FatoDaOferta {
  ref: string;
  declaracao: string;
  origem: OrigemDoFato;
  evidencia_ref?: string | null;
}

export interface Restricao {
  ref: string;
  texto: string;
  escopo: EscopoFeedback;
  termos_bloqueados: string[];
}

export interface Diagnostico {
  oferta_real: string;
  promessa_maxima: string;
  tensao_central: string;
  desconhecidos: string[];
  fato_refs: string[];
}

export interface EstadoMental {
  ref: string;
  nome: string;
  ja_sabe: string;
  duvida: string;
  tensao: string;
  proximo_movimento: string;
}

export interface GrupoEstrategico {
  ref: string;
  nome: string;
  estado_mental_refs: string[];
  funcao: string;
  territorio: string;
  diferenca_material: string;
}

export interface CopyCompartilhada {
  ref: string;
  group_ref: string;
  texto_principal: string;
  titulo: string;
  descricao: string;
  cta_nativa: string;
  narracao?: string | null;
  fato_refs: string[];
}

export interface PecaCriativa {
  ref: string;
  group_ref: string;
  shared_copy_ref: string;
  estado_mental_ref: string;
  angulo: string;
  subangulo: string;
  hipotese: string;
  hook: string;
  mecanismo_de_interrupcao: string;
  formato: string;
  headline_interna: string;
  complemento_interno?: string | null;
  cta_visual?: string | null;
  direcao_visual: string;
  fato_refs: string[];
  rule_refs: string[];
}

/**
 * O recibo é do código do servidor, não do modelo, e NÃO é aprovação humana
 * nem elegibilidade Meta. A tela precisa dizer isso com todas as letras.
 */
export interface ReciboDeValidacao {
  valido: boolean;
  codigos: string[];
  avisos: string[];
  knowledge_base_version: string;
}

export interface SaidaDoAgente {
  schema_version: string;
  project_ref: string;
  fase_concluida: Fase;
  diagnostico: Diagnostico;
  jornada: EstadoMental[];
  grupos: GrupoEstrategico[];
  copies_compartilhadas: CopyCompartilhada[];
  pecas: PecaCriativa[];
  recibo: ReciboDeValidacao;
  proximo_ato: string;
}

/** Uma linha do histórico. Não carrega o lote — só o que a lista decide. */
export interface ResumoDaOperacao {
  project_ref: string;
  nome_da_operacao: string | null;
  status: StatusDaOperacao | null;
  latest_run_ref: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RunDaOperacao {
  run_ref: string;
  project_ref: string;
  status: StatusDaRun;
  phase: Fase;
  output: SaidaDoAgente | null;
  model?: string | null;
  tentativas?: number | null;
  error?: { codigo?: string; erros?: string[] } | null;
  created_at: string | null;
  finished_at?: string | null;
}

export interface OperacaoCompleta {
  operacao: {
    project_ref: string;
    status: StatusDaOperacao;
    input: EntradaNovaOperacao;
    latest_run_ref: string | null;
    created_at: string | null;
    updated_at: string | null;
  };
  runs: RunDaOperacao[];
  /**
   * As decisões persistidas, já reduzidas à efetiva de cada caminho — uma
   * reprovação posterior desfaz a aprovação anterior sem apagar a trilha.
   *
   * Sem isto, recarregar a página perdia a revisão inteira: as decisões estavam
   * no banco e a tela só as tinha em estado de sessão.
   */
  decisoes: DecisaoPersistida[];
  /**
   * Por run concluída, os caminhos cuja aprovação AINDA descreve o conteúdo
   * daquela run. Quem decide isso é o servidor: a tela não tem o hash aprovado
   * nem autoridade para comparar.
   */
  aprovacoes_validas: Record<string, string[]>;
}

export interface DecisaoPersistida {
  decision_ref: string;
  run_ref: string;
  path: string;
  decisao: 'APROVADO' | 'REPROVADO';
  scope: string;
  snapshot_sha256: string;
  feedback: string | null;
  created_at: string | null;
}

export interface EntradaNovaOperacao {
  nome_da_operacao: string;
  /** Vínculo interno opcional, preenchido por integrações que já conhecem o destino. */
  destination_ref?: string | null;
  objetivo_meta: string;
  pais?: string;
  idioma?: string;
  contexto_do_publico: string;
  fatos_da_oferta: FatoDaOferta[];
  restricoes?: Restricao[];
  brand_pack_ref?: string | null;
  formatos_permitidos: string[];
  quantidade_de_pecas: number;
}

/** O 201 de criar: identidade durável antes de qualquer modelo rodar. */
export interface OperacaoEnfileirada {
  project_ref: string;
  run_ref: string;
  status: 'QUEUED';
  proximo_ato: string;
}

export interface RunEnfileirada {
  run_ref: string;
  status: 'QUEUED';
  proximo_ato: string;
}

export interface RunExecutada {
  run_ref: string;
  status: StatusDaRun;
  output: SaidaDoAgente;
  /** `false` quando a run já estava concluída e nada foi gerado de novo. */
  reexecutado?: boolean;
}

export interface PedidoDeContinuacao {
  fase: Fase;
  quantidade_de_pecas?: number;
  formatos_permitidos?: string[];
  feedback?: string;
  feedback_escopo?: EscopoFeedback;
}

export interface PedidoDeDecisao {
  run_ref: string;
  decisao: 'APROVADO' | 'REPROVADO';
  escopo: EscopoFeedback;
  /** Caminho estável, endereçado por `ref` dentro de listas. Nunca por índice. */
  caminho: string;
  feedback?: string;
}

export interface DecisaoRegistrada {
  decision_ref: string;
  decisao: 'APROVADO' | 'REPROVADO';
  snapshot_sha256: string;
}

/**
 * Um formato que o Estúdio sabe produzir, vindo do servidor.
 *
 * A tela NÃO tem uma lista de formatos escrita nela: o catálogo é
 * `backend/app/criativo/dominio.py:FORMATOS`, e oferecer aqui um slot que o
 * motor não produz é prometer uma peça que nunca chega.
 */
export interface CanvasNativo {
  largura: number;
  altura: number;
  /** `false` quando a proporcao comercial nao coube no envelope do provider. */
  proporcao_preservada: boolean;
  observacao: string | null;
}

export interface FormatoDisponivel {
  slot: string;
  rotulo: string;
  proporcao: string;
  largura: number;
  altura: number;
  descricao: string;
  destinos_tipicos: string[];
  /**
   * O canvas em que o provider realmente compoe, antes da normalizacao.
   *
   * `null` quando o motor nao publica envelope. Quando existe e difere da
   * medida final, a peca passou por reducao e recorte: dizer isso e o que
   * impede a tela de prometer uma composicao nativa que nao aconteceu.
   */
  canvas_nativo: CanvasNativo | null;
  transformacao_final: string | null;
  aceita_fotografia_real: boolean;
}

/**
 * A fotografia real, depois de o servidor normaliza-la.
 *
 * O que volta e uma referencia opaca e um hash. Os BYTES nao voltam: a tela
 * nao precisa deles e carrega-los seria reabrir o caminho do base64 no estado.
 */
export interface Anexo {
  anexo_ref: string;
  mime: string;
  largura: number;
  altura: number;
  bytes_totais: number;
  /** Hash dos bytes NORMALIZADOS. A autorizacao de gasto e assinada contra ele. */
  content_sha256: string;
  exif_removido: boolean;
  criado_em: string | null;
}

export interface ModoDeComposicao {
  id: string;
  rotulo: string;
  descricao: string;
  /** `true` so no modo que preserva literalmente os pixels da fotografia. */
  preserva_pixels_da_foto: boolean;
}

/**
 * O que este servidor sabe produzir. Buscado, nunca escrito na tela.
 *
 * O catalogo ja morou em tres lugares e o do Assistente tinha tres formatos
 * enquanto o motor produzia quatro: o `1.91x1` simplesmente nao aparecia, e
 * nenhum teste falhava porque uma constante a menos nao quebra nada, ela so
 * some. Buscar do servidor remove a segunda copia em vez de corrigi-la.
 */
export interface Capacidades {
  formatos: FormatoDisponivel[];
  teto_de_renders_por_pedido: number;
  motor: {
    modelo: string | null;
    qualidade: string | null;
    configurado: boolean;
    publica_preco_por_imagem: boolean;
  };
  modos_de_composicao: ModoDeComposicao[];
}

// ── Produção ─────────────────────────────────────────────────────────────────

export interface Bloqueio {
  codigo: string;
  mensagem: string;
}

export interface BriefingResumido {
  creative_ref: string;
  formato_slot: string;
  texto_na_arte: string;
  direcao_visual: string;
}

/**
 * O plano é calculado NO SERVIDOR. A tela desenha; ela não decide o teto.
 *
 * `custo_estimado_usd` é `null` quando o motor não publica preço — e a tela
 * escreve ausência, nunca "US$ 0,00".
 */
export interface PlanoDeGeracao {
  conceitos: number;
  formatos: number;
  total_de_renders: number;
  teto: number;
  custo_estimado_usd: number | null;
  /**
   * Sempre `true`: o provider cobra por token e nunca devolve dólar, então o
   * número acima vem de tabela de referência. A tela precisa dizer isso — um
   * valor apresentado como fatura ao lado de um botão que gasta é uma promessa
   * que o mecanismo não sustenta.
   */
  custo_e_estimado: boolean;
  /**
   * `false` quando o motor nao publica preco por imagem.
   *
   * O `gpt-image-2` e cobrado por token e a OpenAI nao publica dolar por
   * imagem, entao para ele isto e sempre `false`. A tela usa este campo para
   * pedir o consentimento explicito de gastar sem estimativa, em vez de
   * desenhar um campo de teto que o servidor nao teria como honrar.
   */
  custo_tem_estimativa: boolean;
  /** Como o servidor nomeia o motor que rodaria. `null` quando não há motor. */
  modelo_de_imagem: string | null;
  /** A qualidade imposta pelo motor. Entra na frase que a pessoa confirma. */
  qualidade_de_imagem: string | null;
  motor_configurado: boolean;
  /**
   * O selo que a autorizacao precisa devolver inteiro.
   *
   * `null` quando o plano esta bloqueado: nao ha o que autorizar, e emitir um
   * selo convidaria o cliente a tentar assim mesmo.
   */
  selo_do_plano: string | null;
  /** Como a fotografia entra, ecoado pelo servidor. */
  modo_de_composicao: string;
  /** Hash dos bytes normalizados do anexo, quando ha um. */
  anexo_sha256: string | null;
  pode_executar: boolean;
  bloqueios: Bloqueio[];
  briefings: BriefingResumido[];
}

/**
 * O consentimento que a rota de geração exige. Espelha o que a tela mostrou.
 *
 * O servidor reconfere os três contra o que ele mesmo mediu; isto não é o teto,
 * é a declaração de que uma pessoa leu o teto.
 */
export interface AutorizacaoDeGasto {
  modelo: string;
  total_de_renders: number;
  teto_custo_usd: number | null;
  /**
   * O selo emitido pelo plano, devolvido inteiro.
   *
   * E ele que amarra o consentimento ao CONTEUDO do plano. Sem o selo,
   * autorizar duas pecas e produzir outras duas passava nas conferencias de
   * modelo e de total, porque nenhuma delas descreve qual conteudo.
   */
  selo_do_plano: string;
  /**
   * Consentimento explicito para gastar sem estimativa de preco.
   *
   * Obrigatorio quando `custo_tem_estimativa` e `false`. Antes, um teto
   * declarado sem estimativa era ignorado em silencio.
   */
  aceito_sem_estimativa?: boolean;
}

/** A procedência: de qual peça aprovada saiu qual job de mídia. */
export interface GeracaoRegistrada {
  ponte_ref: string;
  creative_ref: string;
  group_ref: string;
  run_ref: string;
  job_id: string;
  slots: string[];
  created_at: string | null;
  criado_agora?: boolean;
}
