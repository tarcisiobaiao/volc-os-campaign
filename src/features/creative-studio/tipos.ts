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
}

export interface EntradaNovaOperacao {
  nome_da_operacao: string;
  destination_ref: string;
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
export interface FormatoDisponivel {
  slot: string;
  rotulo: string;
  proporcao: string;
  largura: number;
  altura: number;
  descricao: string;
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
  pode_executar: boolean;
  bloqueios: Bloqueio[];
  briefings: BriefingResumido[];
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
