/**
 * O vocabulário de tela de cada canal — e só isso.
 *
 * ## O defeito que este arquivo tinha, e por que ele era grave
 *
 * Até 27/08/2026 este módulo carregava uma SEGUNDA declaração do que cada canal
 * sabe fazer, cravada no cliente, ao lado da que o backend emite em
 * `app/trafego/plataforma.py:ManifestoDeCanal`. Duas verdades sobre o mesmo
 * fato divergem no primeiro ajuste, e tinham divergido:
 *
 * * **Display ganhou construtor em 26/08** (`volc_ads/campanha/display.py`), o
 *   manifesto do backend passou a declarar `sabe_criar` na mesma entrega — e
 *   aqui continuava `integrado: false`. A tela escondia capacidade real com a
 *   autoridade de um registro, que é pior que não ter registro.
 * * **Vídeo e Shopping caíam no `default:` do `switch`** e recebiam o perfil do
 *   **Search**: rótulo "Search", `integrado: true`, estrutura com RSA e
 *   keyword. Selecionar Vídeo mostrava Search integrado, e nada na tela
 *   denunciava.
 *
 * ## A regra que passa a valer
 *
 * > O manifesto do backend é a autoridade sobre CAPACIDADE. Este módulo só sabe
 * > de NOME e de FORMA — como o canal se chama na tela e quantos degraus a
 * > árvore dele tem.
 *
 * ⚠️ E este módulo NÃO reimplementa a leitura do manifesto. Quem traduz
 * manifesto em capacidade é `components/trafego/canal/capacidades.ts`, que já
 * está no ar na página canônica. Uma terceira declaração — que foi o que esta
 * correção quase criou — teria as mesmas três respostas com outros três nomes,
 * e divergiria delas no primeiro ajuste.
 *
 * ⚠️ Nenhuma função aqui decide o que pode ser feito. Quem decide é o backend —
 * `plataforma.exigir_construtor` na porta e `volc_ads/subir.py` no engine. Isto
 * aqui evita oferecer o que será recusado; não é a recusa.
 */
import type { CanalDoHub, NivelMeta, RedeDoHub } from './contrato';

export type AbaDaCampanha =
  | 'resumo'
  | 'estrutura'
  | 'criativos'
  | 'segmentacao'
  | 'desempenho'
  | 'recomendacoes'
  | 'historico';

export const ABAS_DA_CAMPANHA: readonly AbaDaCampanha[] = [
  'resumo',
  'estrutura',
  'criativos',
  'segmentacao',
  'desempenho',
  'recomendacoes',
  'historico',
];

export const ROTULO_DA_ABA: Record<AbaDaCampanha, string> = {
  resumo: 'Resumo',
  estrutura: 'Estrutura',
  criativos: 'Criativos',
  segmentacao: 'Segmentação',
  desempenho: 'Desempenho',
  recomendacoes: 'Recomendações',
  historico: 'Histórico',
};

export type NoDaEstrutura =
  | 'campanha'
  | 'grupo'
  | 'rsa'
  | 'keyword'
  | 'anuncio'
  | 'asset'
  | 'asset_group'
  | 'conjunto'
  | 'criativo';

export interface PerfilDeCanal {
  rede: RedeDoHub;
  canal: CanalDoHub | 'meta';
  rotulo: string;
  abas: readonly AbaDaCampanha[];
  estrutura: readonly NoDaEstrutura[];
  fraseDaEstrutura: string;
  /**
   * Existe adaptador de leitura das entidades FILHAS deste canal?
   *
   * ⚠️ Isto é diferente de "o Hub opera o canal". Medido em 27/08/2026: o
   * sincronizador lê a camada comum (id, nome, status, canal, orçamento,
   * impressões, cliques, custo) para QUALQUER canal que a conta devolva, e só
   * o Search tem adaptador para lance e URL final
   * (`backend/app/trafego/adaptador_search.py` é o único registro em
   * `sincronizador._PERFIS`).
   *
   * Display sabe CRIAR e não tem adaptador de leitura profunda. Colapsar as
   * duas coisas num booleano só foi exatamente o que fez este arquivo declarar
   * Display como não integrado depois de ele ganhar construtor.
   */
  leituraProfunda: boolean;
}

const ABAS_COMPLETAS = ABAS_DA_CAMPANHA;

/**
 * O canal, dito na língua da tela. NÃO responde o que ele pode fazer.
 *
 * ⚠️ Sem `default:`. Cada canal do vocabulário tem um caso explícito, e o
 * `switch` é exaustivo sobre `CanalDoHub` — se alguém acrescentar um canal ao
 * contrato sem passar por aqui, o TypeScript acusa em vez de o canal novo
 * herdar o perfil do Search em silêncio.
 */
export function perfilDoCanal(rede: RedeDoHub, canal: CanalDoHub | null): PerfilDeCanal {
  if (rede === 'meta') {
    return {
      rede: 'meta',
      canal: 'meta',
      rotulo: 'Meta Ads',
      abas: ABAS_COMPLETAS,
      estrutura: ['campanha', 'conjunto', 'anuncio', 'criativo'],
      fraseDaEstrutura: 'campanha → conjunto → anúncio → criativo',
      leituraProfunda: false,
    };
  }

  // `null` = "todos os canais". A árvore comum é a que vale para qualquer um
  // deles, e afirmar a do Search aqui seria escolher um canal sem que ninguém
  // tivesse escolhido.
  if (canal == null) {
    return {
      rede: 'google',
      canal: 'SEARCH',
      rotulo: 'Todos os canais',
      abas: ABAS_COMPLETAS,
      estrutura: ['campanha'],
      fraseDaEstrutura: 'campanha — a árvore abaixo depende do canal',
      leituraProfunda: false,
    };
  }

  switch (canal) {
    case 'SEARCH':
      return {
        rede: 'google',
        canal: 'SEARCH',
        rotulo: 'Search',
        abas: ABAS_COMPLETAS,
        estrutura: ['campanha', 'grupo', 'rsa', 'keyword'],
        fraseDaEstrutura: 'campanha → grupo → RSA / keyword',
        leituraProfunda: true,
      };
    case 'DISPLAY':
      return {
        rede: 'google',
        canal: 'DISPLAY',
        rotulo: 'Display',
        abas: ABAS_COMPLETAS,
        estrutura: ['campanha', 'grupo', 'anuncio', 'asset'],
        fraseDaEstrutura: 'campanha → grupo → anúncio / asset',
        leituraProfunda: false,
      };
    case 'DEMAND_GEN':
      return {
        rede: 'google',
        canal: 'DEMAND_GEN',
        rotulo: 'Demand Gen',
        abas: ABAS_COMPLETAS,
        estrutura: ['campanha', 'grupo', 'anuncio', 'asset'],
        fraseDaEstrutura: 'campanha → grupo → anúncio / asset',
        leituraProfunda: false,
      };
    case 'PERFORMANCE_MAX':
      return {
        rede: 'google',
        canal: 'PERFORMANCE_MAX',
        rotulo: 'Performance Max',
        abas: ABAS_COMPLETAS,
        estrutura: ['campanha', 'asset_group', 'asset'],
        fraseDaEstrutura: 'campanha → grupo de assets → asset',
        leituraProfunda: false,
      };
    // ⚠️ Vídeo e Shopping existem no inventário — a conta pode ter campanhas
    // deles, e escondê-las seria mentir sobre o que está gastando. O que NÃO
    // existe é manifesto: `plataforma.manifesto()` devolve `null` para os dois,
    // e a tela precisa dizer isso em vez de emprestar a árvore do Search.
    case 'VIDEO':
      return {
        rede: 'google',
        canal: 'VIDEO',
        rotulo: 'Vídeo',
        abas: ABAS_COMPLETAS,
        estrutura: ['campanha', 'grupo', 'anuncio'],
        fraseDaEstrutura: 'campanha → grupo → anúncio',
        leituraProfunda: false,
      };
    case 'SHOPPING':
      return {
        rede: 'google',
        canal: 'SHOPPING',
        rotulo: 'Shopping',
        abas: ABAS_COMPLETAS,
        estrutura: ['campanha', 'grupo', 'anuncio'],
        fraseDaEstrutura: 'campanha → grupo → anúncio',
        leituraProfunda: false,
      };
  }
}

export function rotuloDoNo(no: NoDaEstrutura): string {
  switch (no) {
    case 'campanha':
      return 'Campanha';
    case 'grupo':
      return 'Grupo';
    case 'rsa':
      return 'RSA';
    case 'keyword':
      return 'Keyword';
    case 'anuncio':
      return 'Anúncio';
    case 'asset':
      return 'Asset';
    case 'asset_group':
      return 'Grupo de assets';
    case 'conjunto':
      return 'Conjunto';
    case 'criativo':
      return 'Criativo';
  }
}

export function rotuloDoNivelMeta(nivel: NivelMeta): string {
  switch (nivel) {
    case 'campanhas':
      return 'Campanhas';
    case 'conjuntos':
      return 'Conjuntos';
    case 'anuncios':
      return 'Anúncios';
    case 'criativos':
      return 'Criativos';
  }
}
