/**
 * Adapter visual do Hub multicanal.
 *
 * ⚠️ Este arquivo NÃO é o contrato compartilhado. `src/types/trafego.ts`
 * continua sendo a verdade do Claude nesta fase. Tudo aqui é vocabulário da
 * tela, com o ponto exato de adaptação registado em `ADAPTACAO.md`.
 *
 * Quando o contrato chegar, a troca deve caber nestas funções — não em
 * dezenas de componentes.
 */
import type { Canal, CandidatoNoQuadro, FiltrosDoInventario } from '@/types/trafego';

/** Eixo de rede. Google é o padrão enquanto Meta não tiver dados reais. */
export type RedeDoHub = 'google' | 'meta';

/**
 * Tarefas do Hub. `oportunidades` é alias de URL, nunca rótulo.
 *
 * O contrato antigo persistia `aba=oportunidades`. A tela agora diz Preparar;
 * o alias continua lendo o endereço velho para um link colado ontem não
 * abrir a aba errada.
 */
export type AbaDoHub = 'campanhas' | 'preparar' | 'criar' | 'atencao';

/**
 * ⚠️ A ORDEM é a do trabalho, não a do alfabeto: o que já gasta dinheiro, o que
 * está pronto para virar campanha, como criar, e o que pede decisão hoje.
 * `abaDaUrl` deriva a validação desta lista — uma aba nova entra aqui e passa a
 * sobreviver ao recarregamento sem tocar no parser.
 */
export const ABAS_DO_HUB: readonly AbaDoHub[] = ['campanhas', 'preparar', 'criar', 'atencao'];

/** Nível da árvore Meta. Nunca traduzir conjunto (ad set) para ad group. */
export type NivelMeta = 'campanhas' | 'conjuntos' | 'anuncios' | 'criativos';

export const NIVEIS_META: readonly NivelMeta[] = [
  'campanhas',
  'conjuntos',
  'anuncios',
  'criativos',
];

/**
 * Canais Google que a tela sabe nomear. Igual ao contrato: PERFORMANCE_MAX,
 * nunca PMAX. O alias legado entra só em `canalDaUrl` / `canalCanonico`.
 */
export type CanalDoHub = Canal;

export const CANAIS_GOOGLE: readonly CanalDoHub[] = [
  'SEARCH',
  'DISPLAY',
  'DEMAND_GEN',
  'PERFORMANCE_MAX',
  'VIDEO',
  'SHOPPING',
];

/** Estados que a tela trata como campanha operacional (não histórico). */
export const ESTADOS_OPERACIONAIS = ['ENABLED', 'PAUSED'] as const;

/**
 * Vocabulário visual da aba Preparar.
 *
 * `pendente` não é estado canônico: é a recusa de inventar um quando
 * `reconciliacao` falta ou veio `null`. Só `estado: 'sem_campanha'` com
 * `pode_montar: true` libera montagem.
 */
export type EstadoVisualDeReconciliacao =
  | import('@/types/trafego').EstadoDeReconciliacao
  | 'pendente';

/** O quadro já carrega `reconciliacao` no contrato. Alias de tela. */
export type CandidatoPreparar = CandidatoNoQuadro;

export interface EstadoDoHub {
  rede: RedeDoHub;
  aba: AbaDoHub;
  /** `null` = todos os canais. */
  canal: CanalDoHub | null;
  nivel: NivelMeta;
  historico: boolean;
  filtros: FiltrosDoInventario;
  foco: string | null;
}

export const ESTADO_PADRAO: EstadoDoHub = {
  rede: 'google',
  aba: 'campanhas',
  canal: null,
  nivel: 'campanhas',
  historico: false,
  filtros: {},
  foco: null,
};
