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

/**
 * Estado do dado no motor da carteira (W13). `sem_dado` é receita ou câmbio
 * ausente (nunca zero); `amostra_insuficiente` é clique maduro abaixo do
 * limiar. `null` no experimento Senac, que é anterior ao motor.
 */
export type EstadoDadoShadow = 'completo' | 'sem_dado' | 'amostra_insuficiente';

export interface RecomendacaoShadow {
  contrato: 'recomendacao_shadow.v1';
  campanha_externa: string;
  campanha_nome?: string | null;
  campanha_status?: string | null;
  estado_dado?: EstadoDadoShadow | null;
  motivo_estado_dado?: string | null;
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
    /** sha256 comparado com o manifesto da mesma pasta: deriva, não adulteração. */
    integridade: 'coerente_com_manifesto';
    /** Experimentos mais antigos da mesma campanha, preteridos pelo `as_of`. */
    experimentos_substituidos: string[];
  };
  isolamento: {
    chamadas_externas: number;
    mutacoes_executadas: number;
    oferece_aplicar: false;
  };
}

/** Uma linha da carteira — `GET /api/trafego/recomendacao-shadow` (`carteira_shadow.v1`). */
export interface LinhaCarteiraShadow {
  campanha_externa: string;
  campanha_nome: string | null;
  campanha_status: string | null;
  conta: string | null;
  /**
   * `ambigua`: dois experimentos com o mesmo `as_of` mais recente; `ilegivel`:
   * experimento da campanha sem `as_of` legível. Nos dois, sem direção.
   */
  situacao: 'lida' | 'ambigua' | 'ilegivel';
  mensagem: string | null;
  direcao: DirecaoShadow | null;
  estado_dado: EstadoDadoShadow | null;
  motivo_estado_dado: string | null;
  as_of: string | null;
  experimento_id: string | null;
  experimentos_substituidos?: string[];
  janela_madura: JanelaShadow | null;
  fracao_custo_maduro_sem_receita: number | null;
  /** Experimento mais de 2 dias mais velho que o mais novo da carteira. */
  defasada: boolean | null;
  valor_sugerido: null;
  executada: false;
}

export interface CarteiraShadow {
  contrato: 'carteira_shadow.v1';
  /** `as_of` do experimento mais novo da carteira; null sem nenhuma linha datada. */
  leitura_mais_nova: string | null;
  /** A carteira inteira está mais de 2 dias atrás do relógio: a agenda parou. */
  carteira_defasada: boolean;
  campanhas: LinhaCarteiraShadow[];
  isolamento: { chamadas_externas: number; mutacoes_executadas: number; oferece_aplicar: false };
  integridade: 'coerente_com_manifesto';
}
