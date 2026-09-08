export interface TrackingAutomaticoMeta {
  template: string;
  parametros: Array<{ nome: string; valor: string }>;
  revenue_join: string;
  grao: 'ADSET';
  campo_api: string;
  previa_url: string | null;
  destino_valido: boolean;
  erro: { codigo: string; mensagem: string } | null;
  prova: 'TEMPLATE_LOCAL';
  efeito_externo: 'NENHUM';
}

export type AcaoGestaoMeta = 'PAUSAR' | 'ORCAMENTO_DIARIO' | 'LANCE' | 'DUPLICAR_CONJUNTO';
export interface PedidoGestaoMeta {
  conta_ref: string;
  campanha_ref: string;
  entidade: 'campanha' | 'conjunto';
  referencia: string;
  acao: AcaoGestaoMeta;
  valor_minor?: number;
  estrategia?: 'LOWEST_COST_WITHOUT_CAP' | 'COST_CAP' | 'LOWEST_COST_WITH_BID_CAP';
  nome?: string;
}
export interface PropostaGestaoMeta {
  estado: 'PROPOSTA_LOCAL_NAO_EXECUTAVEL';
  efeito_externo: 'NENHUM';
  executavel: false;
  persistida: false;
  plano_sha256: string;
  nome: string | null;
  observado_em: string | null;
  antes: Record<string, unknown>;
  depois: Record<string, unknown>;
  efeito_proposto: string;
  requisitos_para_executar: string[];
  receita: string;
}
