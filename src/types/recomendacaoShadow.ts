/**
 * Contrato `recomendacao_shadow.v1` — `GET /api/trafego/recomendacao-shadow/{id}`.
 *
 * Espelho de `backend/app/trafego/recomendacao_shadow.py`. A recomendação sai
 * de um experimento versionado e conferido por sha256; ela nunca é executada
 * e nunca traz valor sugerido. `null` é ausência, nunca zero.
 */
export type DirecaoShadow =
  | 'manter'
  | 'reduzir'
  | 'aumentar'
  | 'pausar'
  | 'evidencia_insuficiente';

export interface JanelaShadow {
  dias: number | null;
  custo_brl: number | null;
  receita_brl: number | null;
  cliques: number | null;
  roas: number | null;
  cpc: number | null;
  rpc: number | null;
  contribuicao_bruta: number | null;
}

export interface DiaShadow {
  data: string;
  custo_brl: number | null;
  cliques: number | null;
  receita_brl: number | null;
  contribuicao_brl: number | null;
  maduro: boolean;
  estado: string | null;
}

export interface RecomendacaoShadow {
  contrato: 'recomendacao_shadow.v1';
  campanha_externa: string;
  grao: 'campanha_dia';
  direcao: DirecaoShadow;
  motivos: string[];
  ressalvas: string[];
  valor_sugerido: null;
  executada: false;
  as_of: string | null;
  corte_maturidade: string | null;
  parametros: Record<string, number>;
  janela_madura: JanelaShadow | null;
  janela_madura_recente: JanelaShadow | null;
  roas_sob_estresse: number | null;
  fracao_custo_maduro_sem_receita: number | null;
  dias: DiaShadow[];
  roas_nativo_google: {
    valor_conversao_total: number | null;
    confiavel: false;
    motivo: string;
  };
  origem: {
    experimento_id: string;
    metodo: string | null;
    codigo_sha256: string | null;
    snapshot_sha256: string | null;
    capturado_em: string | null;
    replay_sem_api: boolean;
    integridade: 'conferida';
  };
  isolamento: {
    chamadas_externas: number;
    mutacoes_executadas: number;
    oferece_aplicar: false;
  };
}
