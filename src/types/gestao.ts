/**
 * GADS-GESTAO v1 — tipos do contrato de `/api/trafego/gestao`.
 *
 * Fonte: `docs/contracts/GADS-GESTAO-v1.md` (rotas, payloads, estados, erros).
 * Backend: `backend/app/routers/trafego_gestao.py` → `app/trafego/gestao/`.
 *
 * Ciclo: propor → aprovar (humano) → aplicar → verificar → (reverter).
 * Nada é escrito no Google sem aprovação humana gravada (T1).
 *
 * ⚠️ Arquivo só de tipos. Regra de validação e montagem de payload mora em
 * `src/lib/trafego/gestao/`; HTTP mora em `src/lib/trafego/gestaoApi.ts`.
 */

// ── as ações: 9 grupos, 15 tipos (§5) ───────────────────────────────────────

export type TipoDeAcao =
  | 'status'
  | 'orcamento.diario'
  | 'lance.alvo'
  | 'lance.estrategia'
  | 'negativa.keyword'
  | 'lista.criar'
  | 'lista.adicionar'
  | 'lista.anexar'
  | 'exclusao.placement'
  | 'exclusao.ip'
  | 'programacao.anuncios'
  | 'ajuste.dispositivo'
  | 'ajuste.horario'
  | 'recomendacao.aplicar'
  | 'recomendacao.dispensar';

export type GrupoDeAcao =
  | 'status'
  | 'orcamento'
  | 'alvo_de_lance'
  | 'estrategia'
  | 'negativas_e_listas'
  | 'placements'
  | 'ip'
  | 'agenda_e_ajustes'
  | 'recomendacoes';

/** IDs vão como número ou string de dígitos; a tela manda string. */
export type IdExterno = string;

export type NivelDeStatus = 'campanha' | 'grupo' | 'anuncio' | 'asset_group';
export type StatusGerivel = 'ENABLED' | 'PAUSED';
export type AlvoDeLance = 'tcpa' | 'troas' | 'teto_cpc';
export type EstrategiaEscrevivel =
  | 'MANUAL_CPC'
  | 'TARGET_SPEND'
  | 'MAXIMIZE_CONVERSIONS'
  | 'MAXIMIZE_CONVERSION_VALUE'
  | 'PORTFOLIO';
export type Correspondencia = 'PHRASE' | 'EXACT' | 'BROAD';
export type TipoDeLista = 'NEGATIVE_KEYWORDS' | 'NEGATIVE_PLACEMENTS';
export type TipoDePlacement = 'site' | 'app' | 'youtube_canal' | 'youtube_video';
export type EscopoDeExclusao = 'campanha' | 'conta';
export type EscopoDeNegativa = 'campanha' | 'grupo';
export type DiaDaSemana =
  | 'MONDAY'
  | 'TUESDAY'
  | 'WEDNESDAY'
  | 'THURSDAY'
  | 'FRIDAY'
  | 'SATURDAY'
  | 'SUNDAY';
export type Dispositivo = 'DESKTOP' | 'MOBILE' | 'TABLET' | 'CONNECTED_TV';

export interface Termo {
  texto: string;
  correspondencia: Correspondencia;
}

export interface Placement {
  tipo: TipoDePlacement;
  valor: string;
}

export interface Janela {
  dia: DiaDaSemana;
  /** HH:MM na grade de 15 min (00:00–24:00). */
  inicio: string;
  fim: string;
  /** 1.2 = +20%. `null` = sem ajuste. */
  modificador: number | null;
}

export interface AcaoStatus {
  tipo: 'status';
  nivel: NivelDeStatus;
  /** Anúncio: `"<ad_group_id>~<ad_id>"`. */
  ident: IdExterno;
  status: StatusGerivel;
}

/**
 * De onde veio o número de verba/lance. A tela só manda `operador` (o humano
 * digitou); o servidor carimba quem e quando. `medido_na_conta` exige a GAQL em
 * `evidencia`. Qualquer outra origem (SERP, ferramenta externa) é recusada.
 */
export type OrigemDoValor = 'operador' | 'medido_na_conta';

export interface AcaoOrcamento {
  tipo: 'orcamento.diario';
  campaign_id: IdExterno;
  /** Micros inteiros, múltiplos de 10.000. */
  amount_micros: number;
  origem: OrigemDoValor;
  evidencia?: string;
  budget_id?: IdExterno;
  compartilhado_ciente?: boolean;
}

export interface AcaoAlvoDeLance {
  tipo: 'lance.alvo';
  campaign_id: IdExterno;
  alvo: AlvoDeLance;
  /** `troas` é razão (4.5 = 450%); os outros em micros. */
  valor: number;
  /** Obrigatória para tcpa/teto_cpc (dinheiro); tROAS é razão e não leva. */
  origem?: OrigemDoValor;
  evidencia?: string;
  estrategia?: string;
}

export interface AcaoTrocaDeEstrategia {
  tipo: 'lance.estrategia';
  campaign_id: IdExterno;
  nova: EstrategiaEscrevivel;
  tcpa_micros?: number;
  troas?: number;
  teto_cpc_micros?: number;
  /** Obrigatória quando há tcpa_micros/teto_cpc_micros. */
  origem?: OrigemDoValor;
  evidencia?: string;
  portfolio?: string;
}

export interface AcaoNegativaKeyword {
  tipo: 'negativa.keyword';
  escopo: EscopoDeNegativa;
  alvo: IdExterno;
  termos: Termo[];
}

export interface AcaoListaCriar {
  tipo: 'lista.criar';
  tipo_lista: TipoDeLista;
  nome: string;
  itens: Array<Termo | Placement>;
  campanhas?: IdExterno[];
}

export interface AcaoListaAdicionar {
  tipo: 'lista.adicionar';
  shared_set_id: IdExterno;
  tipo_lista: TipoDeLista;
  itens: Array<Termo | Placement>;
}

export interface AcaoListaAnexar {
  tipo: 'lista.anexar';
  shared_set_id: IdExterno;
  campanhas: IdExterno[];
}

export interface AcaoExclusaoPlacement {
  tipo: 'exclusao.placement';
  escopo: EscopoDeExclusao;
  /** Só quando `escopo = campanha`. */
  campaign_id?: IdExterno;
  itens: Placement[];
}

export interface AcaoExclusaoIp {
  tipo: 'exclusao.ip';
  escopo: EscopoDeExclusao;
  campaign_id?: IdExterno;
  /** IPv4 /24–/32 ou endereço único; até 500. */
  ips: string[];
}

export interface AcaoProgramacao {
  tipo: 'programacao.anuncios';
  campaign_id: IdExterno;
  janelas: Janela[];
  remover?: IdExterno[];
  /** `true` remove TODAS as janelas atuais na mesma ação. */
  substituir?: boolean;
}

export interface AcaoAjusteDispositivo {
  tipo: 'ajuste.dispositivo';
  campaign_id: IdExterno;
  dispositivo: Dispositivo;
  /** 0 = −100%; senão 0,1–10. */
  modificador: number;
}

export interface AcaoAjusteHorario {
  tipo: 'ajuste.horario';
  campaign_id: IdExterno;
  criterion_id: IdExterno;
  modificador: number;
}

export interface AcaoRecomendacao {
  tipo: 'recomendacao.aplicar' | 'recomendacao.dispensar';
  /** `customers/…/recommendations/…` */
  recurso: string;
}

export type AcaoDeGestao =
  | AcaoStatus
  | AcaoOrcamento
  | AcaoAlvoDeLance
  | AcaoTrocaDeEstrategia
  | AcaoNegativaKeyword
  | AcaoListaCriar
  | AcaoListaAdicionar
  | AcaoListaAnexar
  | AcaoExclusaoPlacement
  | AcaoExclusaoIp
  | AcaoProgramacao
  | AcaoAjusteDispositivo
  | AcaoAjusteHorario
  | AcaoRecomendacao;

// ── estados (§6) ────────────────────────────────────────────────────────────

export type EstadoDaProposta =
  | 'aguardando_aprovacao'
  | 'aprovada'
  | 'recusada'
  | 'aplicada'
  | 'revertida'
  | 'expirada'
  | 'cancelada';

export type ProximoPasso =
  | 'aguardar_humano'
  | 'aplicar'
  | 'verificar'
  | 'acompanhar'
  | 'expirar'
  | 'nada';

export type DesfechoDaAplicacao = 'em_voo' | 'sucesso' | 'erro' | 'sem_resposta';
export type DesfechoDaReversao = 'pendente' | 'sucesso' | 'erro' | 'sem_resposta';
export type DecisaoHumana = 'aprovada' | 'recusada';

// ── §3.1 painel ─────────────────────────────────────────────────────────────

export type ValorDoLedger = Record<string, unknown>;

export interface PropostaDoPainel {
  proposta_id: string;
  volc_campaign_id: string | null;
  alvo_nivel: string;
  /** `google_ads:<conta>:<nivel>:<alvo>` */
  alvo_chave: string;
  operacao: TipoDeAcao | string;
  valor_atual: ValorDoLedger | null;
  valor_proposto: ValorDoLedger | null;
  valor_atual_lido_em: string | null;
  delta_pct: number | null;
  delta_absoluto_micros: number | null;
  moeda: string | null;
  estado: EstadoDaProposta | string;
  criada_em: string | null;
  expira_em: string | null;
  regra_chave: string | null;
  regra_versao: number | null;
  regra_objetivo: string | null;
  regra_responsavel: string | null;
  nivel_autonomia: string | null;
  condicao_rollback: string | null;
  sintoma: string | null;
  explicacao: string | null;
  confianca: number | null;
  severidade: string | null;
  evidencia_colhida_em: string | null;
  evidencia_suficiencia: string | null;
  janela_inicio: string | null;
  janela_fim: string | null;
  aprovacao_decisao: DecisaoHumana | null;
  aprovacao_por: string | null;
  aprovacao_em: string | null;
  aplicacao_id: string | null;
  aplicacao_desfecho: DesfechoDaAplicacao | null;
  aplicacao_enviada_em: string | null;
  vencida: boolean;
  proximo_passo: ProximoPasso | string;
}

export interface RespostaDoPainel {
  propostas: PropostaDoPainel[];
  total: number;
}

// ── §3.2 propor ─────────────────────────────────────────────────────────────

export interface PedidoDeProposta {
  customer_id: string;
  acao: AcaoDeGestao;
  motivo: string;
  regra_chave?: string;
  /** 1–168; padrão 24. */
  validade_horas?: number;
}

export interface RespostaDaProposta {
  proposta: Partial<PropostaDoPainel> & {
    proposta_id: string;
    estado: string;
    idempotency_key?: string;
  };
  /** Presentes também quando `ja_existia` (contrato de gestão v1.1, §3.2). */
  evidencia_id?: string;
  diagnostico_id?: string;
  ja_existia: boolean;
}

// ── §3.3 / §3.4 decisão ─────────────────────────────────────────────────────

export interface DiffApresentado {
  valor_atual: ValorDoLedger | null;
  valor_proposto: ValorDoLedger | null;
  delta_pct?: number | null;
}

export interface PedidoDeAprovacao {
  diff_apresentado: DiffApresentado;
  motivo?: string;
}

export interface PedidoDeRecusa {
  motivo: string;
  diff_apresentado?: DiffApresentado;
}

export interface RespostaDaDecisao {
  aprovacao: Record<string, unknown>;
  proposta: Partial<PropostaDoPainel> & { estado: string };
  ja_existia: boolean;
}

// ── §3.5 aplicar ────────────────────────────────────────────────────────────

export interface Aplicacao {
  aplicacao_id: string;
  tentativa?: number;
  desfecho: DesfechoDaAplicacao;
  valor_anterior?: ValorDoLedger | null;
  request_id?: string | null;
  resposta_bruta?: Record<string, unknown> | null;
}

export interface RespostaDaAplicacao {
  aplicacao: Aplicacao;
  proposta: Partial<PropostaDoPainel> & { estado: string };
  desfecho: DesfechoDaAplicacao;
  ja_aplicada: boolean;
}

// ── §3.6 verificar ──────────────────────────────────────────────────────────

export interface RespostaDaVerificacao {
  acompanhamento: {
    acompanhamento_id: string;
    confere: boolean | null;
    motivo: string | null;
    valor_observado?: ValorDoLedger | null;
  };
  /** Tri-estado: `null` = a leitura não permite saber (sempre com motivo). */
  confere: boolean | null;
  motivo: string | null;
  aplicacao: Partial<Aplicacao>;
  proposta: Partial<PropostaDoPainel> & { estado: string };
}

// ── §3.7 reverter ───────────────────────────────────────────────────────────

export interface PedidoDeReversao {
  motivo: string;
  acompanhamento_id?: string;
}

export interface RespostaDaReversao {
  reversao: {
    reversao_id: string;
    desfecho: DesfechoDaReversao;
    valor_restaurado?: {
      reversivel: boolean;
      motivo: string;
      passos: Array<{ operacao: string; valor: ValorDoLedger }>;
    } | null;
  };
  proposta: Partial<PropostaDoPainel> & { estado: string };
  ja_revertida: boolean;
}

// ── §3.8 importar ───────────────────────────────────────────────────────────

export interface PedidoDeImportacao {
  customer_id: string;
  campaign_id: string;
}

export interface RespostaDaImportacao {
  campanha: {
    volc_campaign_id: string;
    customer_id: string;
    campaign_id: string;
    procedencia: string;
  };
  google: { nome: string; status: string; canal: string; moeda: string | null };
  ja_existia: boolean;
  procedencia_resolvida: boolean;
}

// ── §3.9 recomendações ──────────────────────────────────────────────────────

export interface MetricasDeImpacto {
  impressoes?: number | null;
  cliques?: number | null;
  custo_micros?: number | null;
  conversoes?: number | null;
}

export interface RecomendacaoDoGoogle {
  recurso: string;
  tipo: string;
  campanha: string | null;
  orcamento: string | null;
  grupo: string | null;
  dispensada: boolean;
  impacto: { base: MetricasDeImpacto; potencial: MetricasDeImpacto } | null;
  acoes: AcaoRecomendacao[];
}

export interface RespostaDeRecomendacoes {
  recomendacoes: RecomendacaoDoGoogle[];
  total: number;
}

// ── §2 erros ────────────────────────────────────────────────────────────────

export type CodigoDeErroDaGestao =
  | 'nao_encontrado'
  | 'acao_invalida'
  | 'estado_nao_permite'
  | 'sem_motivo'
  | 'recusa_sem_motivo'
  | 'sem_diff_apresentado'
  | 'google_recusou'
  | 'regra_ausente'
  | 'campanha_nao_importada'
  | 'evidencia_insuficiente'
  | 'regra_exige_delta'
  | 'repropostas_demais'
  | 'teto_sem_delta'
  | 'limite_pct'
  | 'limite_absoluto'
  | 'teto_orcamento'
  | 'moeda_do_teto'
  | 'antes_velho'
  | 'diff_divergente'
  | 'ja_decidida'
  | 'proposta_expirada'
  | 'exige_aprovacao_humana'
  | 'em_carencia'
  | 'antes_divergiu'
  | 'verificar_antes'
  | 'aplicacao_em_andamento'
  | 'escrita_bloqueada'
  | 'nada_a_reverter'
  | 'irreversivel'
  | 'estado_mudou_depois'
  | 'reversao_ja_existe'
  | 'banco_recusou'
  | 'estado_invalido'
  | 'campanha_removida'
  | 'regra_invalida'
  | 'plataforma'
  | 'fora_do_escopo'
  | 'proposta_ilegivel'
  | 'valor_sem_origem'
  | 'valor_sem_autoridade'
  | 'indisponivel'
  | 'escopo_indisponivel'
  | 'sdk_ausente'
  | 'motor_ausente'
  | 'sem_resposta'
  | 'desfecho_nao_gravado';

/** `{"detail": {codigo, mensagem, detalhe?}}` — decida pela `codigo`, nunca pela mensagem. */
export interface CorpoDeErroDaGestao {
  codigo: CodigoDeErroDaGestao | string;
  mensagem: string;
  detalhe?: unknown;
}
