import type { CaixaDePropostas, DiagnosticoDeEntrega } from '@/types/diagnostico';

export type EstadoDaSuperficieLab =
  | 'atual'
  | 'stale'
  | 'parcial'
  | 'vazio_confirmado'
  | 'falha_ultimo_bom'
  | 'falha_sem_fotografia'
  | 'versao_desconhecida';

export interface CenarioDoLab {
  scenario_id: string;
  rotulo: string;
  grupo: 'dourado' | 'estado' | string;
}

export interface FatorDoLab {
  chave: string;
  frase: string;
  evidencia: string;
}

export interface PoliticaDoLab {
  regra_id: string;
  versao: number;
  titulo: string;
  owner: string;
  fonte: string;
  nivel_autonomia: 'T0' | 'T1' | string;
  publicavel: false;
  aplicavel: boolean;
  suficiencia: string;
  motivo_suficiencia: string | null;
  faltantes: string[];
  objetivo?: string;
  parametros_efetivos?: {
    janela_minima_dias: number;
    frescor_maximo_horas: number;
    amostra_minima_cliques: number | null;
    amostra_minima_impressoes: number | null;
    amostra_minima_conversoes: number | null;
    cooldown_horas: number;
    limite_alteracao_pct: number | null;
    perfil: string | null;
    quality_healthy_min?: number;
    cost_spike_ratio_min?: number;
    routine_max_age_hours?: number;
    onboarding_max_age_hours?: number;
    share_loss_min?: number;
  };
  deteccao_efetiva?: string;
  disparou: boolean;
  resultado: string;
}

export interface ConflitoDoLab {
  codigo: string;
  efeito: string;
  motivo: string;
  politicas?: string[];
  evidencia_refs?: string[];
  resolucao?: string;
}

export interface EventoDoLab {
  evento_id: string;
  tipo: string;
  entidade: string;
  observado_em: string;
  janela_inicio: string;
  janela_fim: string;
  evidencia_refs: string[];
  severidade: string;
  dedup_key: string;
  resolucao: string;
}

export interface PropostaTipadaDoLab {
  proposta_id: string;
  idempotency_key: string;
  evento_id: string;
  regra_chave: string;
  regra_versao: number;
  operacao: string;
  alvo: string;
  antes: string | null;
  depois: string | null;
  confianca: string;
  bloqueios: string[];
  aprovacao: 'nao_submetida';
  aplicacao: 'nao_executada';
  recibo: null;
}

export interface ResultadoDecisionLab {
  versao_contrato: number;
  scenario_id: string;
  rotulo: string;
  estado_da_superficie: 'atual' | 'stale' | 'parcial';
  estado_da_leitura: 'atual' | 'stale' | 'parcial' | 'invalida';
  health_gate: { estado: string; rotulo: string; motivo: string };
  veredito: { tipo: string; titulo: string; resumo: string };
  fatores: {
    favorece: FatorDoLab[];
    limita: FatorDoLab[];
    desconhecido: FatorDoLab[];
  };
  politicas: PoliticaDoLab[];
  conflitos: ConflitoDoLab[];
  eventos: EventoDoLab[];
  diagnostico: DiagnosticoDeEntrega;
  caixa_de_propostas: CaixaDePropostas;
  propostas_tipadas: PropostaTipadaDoLab[];
  execucao: {
    estado: 'bloqueada';
    autorizacao: null;
    aplicacao: null;
    recibo: null;
    mutacoes_executadas: 0;
  };
  evidencias: Array<Record<string, unknown>>;
  features: Record<string, unknown>;
  timeline: Array<{ ordem: number; tipo: string; estado: string; texto: string; observado_em?: string; janela?: { inicio: string; fim: string }; evidencia_ref?: string }>;
  critica: {
    estado: string;
    autoridade: 'explicador_sem_poder_decisorio';
    resposta: null | { resumo: string; questoes: string[]; campos_considerados: string[] };
  };
  autoridade: { calculadora: string; llm: string; decisao: string; mutacao: string };
  api_google_ads: { namespace: 'v25'; minor_documentada_localmente: 'v25.1'; v25_2: 'nao_afirmada' };
  marcas: ['PROTÓTIPO', 'DADOS SINTÉTICOS'];
  replay?: { dataset_version: number; as_of: string; total: number; passaram: number; falharam: number };
}

export interface EstadoDecisionLab {
  versao_contrato: number;
  scenario_id: string;
  rotulo: string;
  estado_da_superficie: Exclude<EstadoDaSuperficieLab, 'atual' | 'stale' | 'parcial'>;
  ultima_fotografia?: ResultadoDecisionLab | null;
  falha?: { codigo: string; mensagem: string };
  confirmacao?: { fonte: string; lido_em: string; linhas: 0 };
  versao_recebida?: string;
  marcas: ['PROTÓTIPO', 'DADOS SINTÉTICOS'];
}

export type RespostaDoDecisionLab = (ResultadoDecisionLab | EstadoDecisionLab) & {
  catalogo: CenarioDoLab[];
  replay: { dataset_version: number; as_of: string; total: number; passaram: number; falharam: number };
  isolamento: {
    somente_sintetico: true;
    entra_em_contagens_reais: false;
    aceita_volc_campaign_id: false;
    oferece_aplicar: false;
    chamadas_externas: 0;
    escopo_chamadas_externas: string;
    mutacoes_executadas: 0;
  };
};

export function ehResultadoDecisionLab(
  valor: RespostaDoDecisionLab,
): valor is ResultadoDecisionLab & RespostaDoDecisionLab {
  return 'veredito' in valor && 'diagnostico' in valor;
}
