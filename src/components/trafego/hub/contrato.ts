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
/**
 * ⚠️ `canais` e `criar` SAÍRAM da navegação principal. As duas respondiam à
 * pergunta técnica "o que cada canal pode?", mas o trabalho real do operador
 * começa em Preparar e continua na bancada de uma campanha.
 *
 * `canais` lia o veredito PRONTO do servidor (`GET /api/trafego/canais`: quatro
 * portões por canal, quatro canais). `criar` DERIVAVA no cliente a partir de
 * manifesto + capacidades + trava (`canal/jornada.ts`), sobre seis canais, e
 * nunca consultava a janela do canário.
 *
 * A divergência era mensurável e cara: `plataforma.py:373` declara
 * `sabe_criar=True` para Display, então `jornada.ts:644` liberava o cockpit e a
 * bancada oferecia o botão primário "Começar campanha" — com o mesmo desenho de
 * Search. Só que o servidor RECUSA `criavel_pausada` de Display com
 * `fora_da_janela_do_canario` (`contrato_canais.py:946`), porque a janela
 * autorizada é de um canal só. Simetria falsa: dois canais desenhados iguais,
 * um cria e o outro não.
 *
 * O veredito do servidor continua sendo autoridade na bancada. Os aliases
 * `?aba=canais` e `?aba=criar` desembocam em Preparar para preservar links.
 */
export type AbaDoHub = 'campanhas' | 'preparar' | 'atencao';

/**
 * ⚠️ A ORDEM é a do trabalho, não a do alfabeto: o que já gasta dinheiro, o que
 * está pronto para virar campanha e o que pede decisão hoje.
 * `abaDaUrl` deriva a validação desta lista — uma aba nova entra aqui e passa a
 * sobreviver ao recarregamento sem tocar no parser.
 */
export const ABAS_DO_HUB: readonly AbaDoHub[] = [
  'campanhas', 'preparar', 'atencao',
];

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
