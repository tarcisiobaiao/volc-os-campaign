/**
 * Fixture de teste: a projeção do experimento `senac-shadow-20261015`, como a
 * rota a devolve, reduzida a poucos dias. Não é importada por código de tela.
 */
import type { RecomendacaoShadow } from '@/types/recomendacaoShadow';

export const RECOMENDACAO_SENAC: RecomendacaoShadow = {
  contrato: 'recomendacao_shadow.v1',
  campanha_externa: '24278665189',
  grao: 'campanha_dia',
  direcao: 'pausar',
  motivos: [
    'ROAS maduro 0.073 em 634 cliques',
    'mesmo no estresse a campanha não paga o próprio custo',
  ],
  ressalvas: [
    'câmbio fixo 5.25 (o mesmo do app); sem câmbio diário',
    'só grão campanha × dia; sem receita por URL, sessão, hora ou placement',
  ],
  valor_sugerido: null,
  executada: false,
  as_of: '2026-10-15',
  corte_maturidade: '2026-10-12',
  parametros: { estresse_receita: 2, estresse_cambio: 1.5 },
  janela_madura: {
    dias: 16, custo_brl: 554.75, receita_brl: 40.79, cliques: 634,
    roas: 0.0735, cpc: 0.875, rpc: 0.0643, contribuicao_bruta: -513.96,
  },
  janela_madura_recente: {
    dias: 5, custo_brl: 299.07, receita_brl: 27.46, cliques: 354,
    roas: 0.0918, cpc: 0.8448, rpc: 0.0776, contribuicao_bruta: -271.61,
  },
  roas_sob_estresse: 0.2205,
  fracao_custo_maduro_sem_receita: 0.0006,
  dias: [
    { data: '2026-09-23', custo_brl: null, cliques: null, receita_brl: null, contribuicao_brl: null, maduro: true, estado: 'sem_custo' },
    { data: '2026-10-01', custo_brl: 0.33, cliques: 2, receita_brl: null, contribuicao_brl: null, maduro: true, estado: 'sem_receita' },
    { data: '2026-10-11', custo_brl: 59.91, cliques: 67, receita_brl: 4.83, contribuicao_brl: -55.08, maduro: true, estado: 'reconciliado' },
    { data: '2026-10-14', custo_brl: 50.02, cliques: 69, receita_brl: 5.36, contribuicao_brl: -44.66, maduro: false, estado: 'reconciliado' },
  ],
  roas_nativo_google: {
    valor_conversao_total: 2380,
    confiavel: false,
    motivo: 'O valor de conversão do Google é fixo em 10 por conversão, configurado na conta; não é receita.',
  },
  origem: {
    experimento_id: 'senac-shadow-20261015',
    metodo: 'DuckDB: full outer join custo × receita por data',
    codigo_sha256: 'a1ccd5f18ccc83ac66a910af54ba035846cb0f96cbf9e71bd8c416a93593bf88',
    snapshot_sha256: '4ce831d2389226efda167492a0b93431a97fc42dcc9df1009bff940ad7477dbf',
    capturado_em: '2026-10-15T10:26:15Z',
    replay_sem_api: true,
    integridade: 'conferida',
  },
  isolamento: { chamadas_externas: 0, mutacoes_executadas: 0, oferece_aplicar: false },
};
