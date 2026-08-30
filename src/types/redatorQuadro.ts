// ============================================
// O QUADRO — onde cada funil está no ciclo PAUTA → FUNIL → CAMPANHA
// ============================================

/** Um card do Pautador aprovado e arquitetado, esperando ser escrito.
 *  NÃO vem da tabela de runs: vem de `pautador_entity_opportunities`. */
export interface CardPronto {
  opportunity_id: number;
  titulo: string;
  paginas: number;
  score: number | null;
  cpc_max: number | null;
  ecpm_band: string | null;
  estimated_volume: number | null;
  atualizado_em: string | null;
}

export interface FunilNoQuadro {
  id: number;
  opportunity_id: number;
  project_id: number;
  run_id: string | null;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  modo: string;
  custo_usd: number | null;
  paginas_planejadas: number | null;
  paginas_geradas: number | null;
  erro: string | null;
  criado_em: string | null;
  titulo: string;
  dominio: string;
  /** Quantas chegaram ao WordPress. É o número que conta: uma página "gerada"
   *  que não subiu não existe para a campanha. */
  paginas_publicadas: number;
  lp_url: string | null;
  etapas: number;
}

export interface QuadroDoRedator {
  prontos: CardPronto[];
  escrevendo: FunilNoQuadro[];
  escritos: FunilNoQuadro[];
  interrompidos: FunilNoQuadro[];
  totais: {
    /** Inclui os runs que falharam — dinheiro gasto é dinheiro gasto, e
     *  escondê-lo é como o custo de um funil deixa de ser confrontado com a
     *  receita dele. */
    gasto_usd: number;
    runs: number;
    paginas_no_ar: number;
  };
}

// ── a configuração do motor ────────────────────────────────────────────────

export interface ListaDaDoutrina {
  nome: string;
  rotulo: string;
  efeito: string;
  itens: string[];
  total: number;
}

export interface PromptDoAgente {
  arquivo: string;
  usado_por: string;
  linhas: number;
  caracteres: number;
  conteudo: string;
}

export interface PassoConfigurado {
  passo: string;
  modelo: string;
  reservas: string[];
  temperatura: number | null;
  validadores: string[];
}

export interface ConfiguracaoDoRedator {
  doutrina: ListaDaDoutrina[];
  aviso_de_conformidade: string;
  prompts: PromptDoAgente[];
  passos: PassoConfigurado[];
  corrida: Record<string, unknown>;
  /** Decisão declarada, não pendência: ver `por_que`. */
  somente_leitura: boolean;
  por_que: string;
}
